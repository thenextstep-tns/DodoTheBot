"""
Import smart-ground tilesets: a 3 x 3 border set with extra centres, per ground.

    py tools/dodoland_import_autotiles.py <folder>            # report
    py tools/dodoland_import_autotiles.py <folder> --write    # import

Every sub-folder whose name ends in ``_tileset`` is one ground, and holds (in
its ``128x128`` folder, else the folder itself)::

    01_top_left  02_top_center  03_top_right
    04_mid_left  05_center      06_mid_right
    07_bottom_left 08_bottom_center 09_bottom_right
    10-13_variation_*   (more centres)
    14_single_standalone (a ground one cell across, on its own)

Each becomes one paintable environment tile in the **Smart ground** category,
its pictures stored in that order (the centre first, so it is what the palette
shows) and an ``autotile`` field saying which is which. The map draws a smart
ground cell by cell from its neighbours (``web/dodoland/terrain_ui.py``,
``autoTile``): the centre or a variation inside, the edge or corner tile at a
border, the single tile on its own. Re-running replaces a ground's pictures in
place (same tile, so what is painted keeps showing it).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

CATEGORY = "Smart ground"
PACK = "DodoLand smart ground"
EDGES = ("top_left", "top_center", "top_right", "mid_left", "mid_right",
         "bottom_left", "bottom_center", "bottom_right")
# Names, and the grounds that are not open ground. Water stops a wall and a
# road; the shallows still let a town spread over them (at the water cost).
NAMES = {"water_lake": "Lake water", "ocean_shallows": "Shallow sea water",
         "farm_furrows": "Farm furrows", "wooden_dock": "Wooden dock"}
CLOSED = {"water_lake": True, "ocean_shallows": True, "lava": False, "abyss_chasm": False}


def roles(folder: pathlib.Path) -> dict:
    """``{center: [paths], edges: {name: path}, single: path}``, or why not."""
    files = sorted(folder.glob("*.png"))

    def one(pattern):
        found = [f for f in files if re.match(pattern, f.name)]
        return found[0] if found else None
    centre = one(r"05_")
    variations = [f for f in files if re.match(r"1[0-3]_", f.name)]
    edges = {name: one(rf"\d\d_{name}") for name in EDGES}
    single = one(r"14_")
    missing = [n for n, f in edges.items() if f is None] + ([] if centre else ["center"]) + \
              ([] if single else ["single"])
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    return {"center": [centre] + variations, "edges": edges, "single": single}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from config import database
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    sets = sorted(p for p in args.folder.iterdir() if p.is_dir() and p.name.endswith("_tileset"))
    plan = []
    for path in sets:
        key = path.name[: -len("_tileset")]
        where = path / "128x128" if (path / "128x128").is_dir() else path
        try:
            got = roles(where)
        except ValueError as error:
            print(f"  {path.name}: skipped, {error}")
            continue
        name = NAMES.get(key, key.replace("_", " ").capitalize())
        spreads = CLOSED.get(key)
        plan.append((key, name, got, spreads))
        print(f"  {path.name}: '{name}', {len(got['center'])} centres, 8 edges, single"
              f"{'' if spreads is None else ', closed ground' + (' (towns spread over it)' if spreads else '')}")
    print(f"{len(plan)} smart grounds from {args.folder}")
    if not args.write:
        print("Nothing written. Add --write to import.")
        return

    cat = next((c for c in library.categories() if c["name"] == CATEGORY), None) or library.add_category(CATEGORY)
    for key, name, got, spreads in plan:
        source = f"autotile:{key}"
        files = got["center"] + [got["edges"][n] for n in EDGES] + [got["single"]]
        existing = library.by_source(source)
        if existing is None:
            tile = library.add_tile(name=name, cat_id=cat["cat_id"], data=files[0].read_bytes(),
                                    content_type="image/png", layer="environment", placement="paint",
                                    access=["admin", "player"], passable=spreads is None,
                                    spreads=True if spreads is None else spreads,
                                    resizable=False, cell_px=128, pack=PACK, source=source)
            tile_id, old = tile["tile_id"], []
            vids = [tile["variants"][0]]
        else:
            tile_id, old = existing["tile_id"], list(existing["variants"])
            vids = []
            database.dodoland_tiles.update_one({"tile_id": tile_id}, {"$set": {"variants": []}})
            vids.append(library.add_variant(tile_id, data=files[0].read_bytes(), content_type="image/png"))
        for f in files[1:]:
            vids.append(library.add_variant(tile_id, data=f.read_bytes(), content_type="image/png"))
        n = len(got["center"])
        auto = {"center": vids[:n], "edges": dict(zip(EDGES, vids[n:n + 8])), "single": vids[n + 8]}
        database.dodoland_tiles.update_one({"tile_id": tile_id},
                                           {"$set": {"variants": vids, "autotile": auto}})
        for vid in old:
            database.dodoland_tile_art.delete_one({"vid": vid})
        print(f"  {name}: {'updated' if old else 'added'} ({len(vids)} pictures)")


if __name__ == "__main__":
    main()
