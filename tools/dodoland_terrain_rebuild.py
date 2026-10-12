"""
Repaint a server's whole terrain grid with library tiles, and nothing else.

    py tools/dodoland_terrain_rebuild.py GUILD [--regions regions.json]            # report + preview
    py tools/dodoland_terrain_rebuild.py GUILD [--regions regions.json] --write    # do it

Afterwards the world's vocabulary is **only tiles**: index 0 (nothing said
about this cell) and one kind per library tile used. No built-in ground types
remain — every cell is drawn with, and costs what, a real tile says.

* **Water** keeps the coastline the grid already has: deep sea, sea, shallows,
  lakes and rivers each become a water tile.
* **Land** becomes the base grass.
* ``--regions`` (``{"forest": [[x, y], ...], "mountains": ..., ...}``) paints
  terrain types over the land, in order: fields, dunes, forest, swamp, hills,
  mountains, then ponds — so a mountain range wins over the forest at its foot,
  and nothing ever paints over the sea.

``--preview out.png`` draws the result in each tile's average colour.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from io import BytesIO

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# What the grid's existing ground becomes. Keys are the imported kinds' keys.
WATER = {"deep": "sp:Deep water", "sea": "fan:Lake water", "shallows": "fan:Lake water",
         "lake": "fan:Lake water", "river": "fan:Lake water"}
LAND = "fan:Meadow grass"
# Region -> tile, in painting order (later wins).
REGIONS = [("fields", "sp:Summer grass"), ("dunes", "sp:Summer sand"),
           ("forest", "px:Olive grass"), ("swamp", "vr:Valley grass"),
           ("hills", "vr:Valley dirt"), ("mountains", "px:Stone paving"),
           ("ponds", "fan:Lake water")]
# Regions drawn as scattered pieces (single trees in lines and rings) are merged
# into continuous ground: gaps up to this many cells are closed (dilate, then
# erode), so a wood reads as a wood rather than as speckle.
CLOSE = {"forest": 2, "swamp": 1}
# Regions whose ground blocks roads and growth here whatever its tile says.
BLOCKING = {"mountains"}


def close(cells: set, radius: int) -> set:
    disc = [(dx, dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
            if dx * dx + dy * dy <= radius * radius]
    grown = {(x + dx, y + dy) for x, y in cells for dx, dy in disc}
    return {(x, y) for x, y in grown
            if all((x + dx, y + dy) in grown for dx, dy in disc)} | cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("--regions", type=pathlib.Path)
    parser.add_argument("--preview", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from PIL import Image

    from config import database
    from helpers.dodoland import terrain as T
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                          database.dodoland_tile_art)
    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)
    world = store.world(args.guild)
    W, H = world["cells_w"], world["cells_h"]
    old = world["kinds"]
    # It reads water from the imported kinds (deep, sea, lake...). Run over a
    # grid it already rebuilt, those are gone and every sea would come out as
    # one water — so it refuses, rather than quietly flattening the ocean.
    if not any(k.get("key") in WATER for k in old):
        raise SystemExit("This grid has no imported water kinds left: it was already rebuilt. "
                         "Restore the chunks and kinds from a backup first.")

    sources = sorted({LAND, *WATER.values(), *(s for _, s in REGIONS)})
    tiles = {s: library.by_source(s) for s in sources}
    missing = [s for s, t in tiles.items() if not t]
    if missing:
        raise SystemExit(f"tiles not in the library: {missing}")

    def hex_of(tile):
        art = library.art(tile["variants"][0])
        with Image.open(BytesIO(bytes(art["data"]))) as image:
            rgb = image.convert("RGBA").resize((1, 1), Image.BOX).getpixel((0, 0))
        return "#%02x%02x%02x" % rgb[:3]

    kinds = [dict(old[0]) if old and old[0].get("key") == "unknown" else T.base_kinds()[0]]
    index = {}
    for s in sources:
        index[s] = len(kinds)
        kinds.append(T.tile_kind(tiles[s], hex_of(tiles[s])))
    for name, s in REGIONS:
        if name in BLOCKING:
            # Its own kind, so the tile stays passable everywhere else.
            index[name] = len(kinds)
            kinds.append({**T.tile_kind(tiles[s], hex_of(tiles[s])), "key": f"{T.TILE_PREFIX}{tiles[s]['tile_id']}_{name}",
                          "label": name.capitalize(), "move": None, "grow": None,
                          "build": False, "fixed": True})

    cxs, cys = store.chunk_counts(args.guild)
    keys = [(x, y) for y in range(cys) for x in range(cxs)]
    chunks = store.chunks(args.guild, keys)
    grid = {}
    for (cx, cy), cells in chunks.items():
        for i, v in enumerate(cells):
            x, y = cx * T.CHUNK + i % T.CHUNK, cy * T.CHUNK + i // T.CHUNK
            if x < W and y < H and v:
                key = old[v].get("key") if v < len(old) else ""
                water = WATER.get(key) or ((old[v].get("water") and "fan:Lake water") if v < len(old) else None)
                grid[(x, y)] = index[water] if water else index[LAND]
    land = {c for c, v in grid.items() if v == index[LAND]}
    counts = {"water": len(grid) - len(land), "land": len(land)}
    if args.regions:
        regions = json.loads(args.regions.read_text(encoding="utf-8"))
        for name, source in REGIONS:
            n = 0
            cells = {tuple(c) for c in regions.get(name, [])}
            if name in CLOSE:
                cells = close(cells, CLOSE[name])
            for x, y in cells:
                if (x, y) in land:
                    grid[(x, y)] = index[name] if name in BLOCKING else index[source]
                    n += 1
            counts[name] = n
    print("cells:", counts)
    print("kinds:", [k["label"] for k in kinds])

    if args.preview:
        image = Image.new("RGB", (W, H), (20, 20, 20))
        colours = [tuple(int(k.get("hex", "#141414")[i:i + 2], 16) for i in (1, 3, 5)) for k in kinds]
        for (x, y), v in grid.items():
            image.putpixel((x, y), colours[v])
        image.resize((W * 2, H * 2), Image.NEAREST).save(args.preview)
        print("preview:", args.preview)
    if not args.write:
        print("dry run; pass --write")
        return

    store.set_kinds(args.guild, kinds)
    for cx, cy in keys:
        cells = [T.UNKNOWN] * T.CELLS
        for i in range(T.CELLS):
            x, y = cx * T.CHUNK + i % T.CHUNK, cy * T.CHUNK + i // T.CHUNK
            cells[i] = grid.get((x, y), T.UNKNOWN)
        store.write_chunk(args.guild, cx, cy, cells)
    store.touch(args.guild)
    print(f"rewrote {len(keys)} chunks with {len(kinds) - 1} tile kinds")


if __name__ == "__main__":
    main()
