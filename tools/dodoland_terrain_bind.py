"""
Give the imported ground types tiles to be drawn with.

    py tools/dodoland_terrain_bind.py GUILD_ID            # report
    py tools/dodoland_terrain_bind.py GUILD_ID --write    # do it

The terrain was imported from the uploaded reference map as kinds of ground
(plains, deep sea, lake...). Since the generated motifs were removed, a kind is
drawn with the library tile it is bound to (``kind["tile_id"]``), or flat if it
has none.

The reference map is six flat colours — paper-white land, four bands of sea and
a lake blue — so the faithful look is ground tiles in *those* colours, with a
faint paper grain and four variants each so a field of them does not read as a
flat fill. This creates them once in a global **Map art · Ground** category
(re-runnable by ``source``) and binds each imported kind to one.

A kind keeps its own movement and growth costs; only its look comes from the
tile. A kind that is already bound is left alone, so a binding changed later
survives a second run; ``--rebind`` overrides that.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

CATEGORY = "Map art · Ground"
PACK = "DodoLand reference map"
# name -> (hex, passable). Colours read from the uploaded reference SVG.
GROUNDS = {
    "Parchment land": ("#e8eff4", True),
    "Ink deep sea": ("#6a8abb", False),
    "Ink sea": ("#7b97c2", False),
    "Ink coastal sea": ("#8aa3c9", False),
    "Ink shallows": ("#95abcd", False),
    "Ink lake": ("#99b3e4", False),
}
# imported kind key -> ground
BINDINGS = {
    "deep": "Ink deep sea", "sea": "Ink sea", "shallows": "Ink coastal sea",
    "river": "Ink shallows", "lake": "Ink lake",
    "plains": "Parchment land", "grass": "Parchment land", "marsh": "Parchment land",
    "sand": "Parchment land", "forest": "Parchment land", "hills": "Parchment land",
    "mountain": "Parchment land", "cliff": "Parchment land",
}


def grain(hex_colour: str, seed: int, size: int = 16) -> bytes:
    """A 16px tile of one colour with a faint, fixed paper grain."""
    from PIL import Image

    rgb = tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    rng = random.Random(seed)
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            d = rng.choice((-3, -2, -1, 0, 0, 0, 0, 1, 2))
            pixels[x, y] = tuple(max(0, min(255, c + d)) for c in rgb)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rebind", action="store_true", help="also rebind kinds already bound")
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import terrain as T
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                          database.dodoland_tile_art)
    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)

    tiles = {}
    for name, (hex_colour, passable) in GROUNDS.items():
        found = library.by_source(f"ground:{name}")
        tiles[name] = found
        print(f"{'have' if found else 'make'}  {name} {hex_colour}")
    kinds = store.world(args.guild)["kinds"]
    plan = [(i, k["key"], BINDINGS[k["key"]]) for i, k in enumerate(kinds)
            if k.get("key") in BINDINGS and (args.rebind or not k.get("tile_id"))]
    for i, key, name in plan:
        print(f"bind  {key:<10} -> {name}")
    if not args.write:
        print("dry run; pass --write")
        return

    cat = next((c for c in library.categories() if c["name"] == CATEGORY), None)
    cat = cat or library.add_category(CATEGORY)
    for name, (hex_colour, passable) in GROUNDS.items():
        if tiles[name]:
            continue
        seeds = [sum(map(ord, name)) * 31 + n for n in range(4)]
        row = library.add_tile(name=name, cat_id=cat["cat_id"], data=grain(hex_colour, seeds[0]),
                               content_type="image/png", layer="environment", access=["admin"],
                               passable=passable, cell_px=16, pack=PACK, source=f"ground:{name}")
        for seed in seeds[1:]:
            library.add_variant(row["tile_id"], data=grain(hex_colour, seed), content_type="image/png")
        tiles[name] = library.get(row["tile_id"])
    for i, key, name in plan:
        kinds[i] = {**kinds[i], "tile_id": tiles[name]["tile_id"], "hex": GROUNDS[name][0]}
    store.set_kinds(args.guild, kinds)
    print(f"done: {len(plan)} kinds bound")


if __name__ == "__main__":
    main()
