"""
Replace the pictures of a category's tiles with redrawn ones, keeping the tiles.

    py tools/dodoland_replace_tile_art.py "Map art · Castles" path/to/folder            # report
    py tools/dodoland_replace_tile_art.py "Map art · Castles" path/to/folder --write    # do it

Each PNG in the folder replaces the tile whose name it is named after
("castles-1.png" is the tile "Castles 1": the name lower-cased, spaces as
hyphens). The tile keeps its id, category, layer, access, locks and whether it
resizes, so everything that refers to it still does:

* its ``cell_px`` is scaled with the new picture, so it is drawn **the same
  width** on the map as before (``--keep-size``, the default; ``--cell-px N``
  sets it outright);
* the new picture is a new variant (a new address, so no browser keeps showing
  the cached old one), every placed piece that showed the old picture is moved
  to it, and the old picture is removed;
* the old pictures are written to ``--backup`` (default ``logs/tile_art_backup``)
  before anything is deleted.

Files with no matching tile, and tiles with no file, are listed and left alone.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("category", help='the category, e.g. "Map art · Castles"')
    parser.add_argument("folder", type=pathlib.Path, help="the redrawn PNGs")
    parser.add_argument("--write", action="store_true", help="replace them (otherwise only report)")
    parser.add_argument("--cell-px", type=int, default=0, help="set every tile's px per cell instead")
    parser.add_argument("--backup", type=pathlib.Path, default=pathlib.Path("logs/tile_art_backup"))
    args = parser.parse_args()

    from PIL import Image

    from config import database
    from helpers.dodoland import tiles as tile_rules
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    cat = next((c for c in library.categories() if c["name"] == args.category), None)
    if cat is None:
        sys.exit(f"No category called {args.category!r}.")
    tiles = {slug(t["name"]): t for t in library.tiles() if t["cat_id"] == cat["cat_id"]}
    files = {p.stem.lower(): p for p in sorted(args.folder.glob("*.png"))}
    print(f"{args.category}: {len(tiles)} tiles, {len(files)} pictures")
    for name in sorted(set(files) - set(tiles)):
        print(f"  no tile for {files[name].name}; left alone")
    for name in sorted(set(tiles) - set(files)):
        print(f"  no picture for {tiles[name]['name']}; left alone")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = args.backup / f"{slug(args.category)}-{stamp}"
    plan = []
    for name in sorted(set(files) & set(tiles)):
        tile, path = tiles[name], files[name]
        data = path.read_bytes()
        image = Image.open(path)
        if image.mode != "RGBA":
            sys.exit(f"{path.name} has no transparency ({image.mode}); export it as RGBA PNG.")
        new_w, new_h = image.size
        old = library.art_sizes(tile["variants"])
        old_w = old.get(tile["variants"][0], (0, 0))[0] if tile["variants"] else 0
        if args.cell_px:
            cell = args.cell_px
        elif old_w:
            # The same width on the map: width / cell_px stays what it was.
            cell = max(1, round(new_w * tile["cell_px"] / old_w))
        else:
            cell = tile["cell_px"]
        cell = tile_rules.clean_cell(cell)
        placed = database.dodoland_decor.count_documents({"asset_id": tile["tile_id"]})
        print(f"  {tile['name']}: {old_w}px at {tile['cell_px']} px/cell -> {new_w}x{new_h}px at {cell} px/cell "
              f"({new_w / cell:.1f} cells wide, was {old_w / tile['cell_px']:.1f}); {placed} placed")
        plan.append((tile, data, cell))

    if not args.write:
        print("Nothing written. Add --write to replace them.")
        return
    backup.mkdir(parents=True, exist_ok=True)
    for tile, data, cell in plan:
        olds = list(tile["variants"])
        record = {"tile": {k: v for k, v in tile.items() if k != "_id"}, "variants": []}
        for vid in olds:
            row = library.art(vid)
            if row:
                (backup / f"{slug(tile['name'])}-{vid}.png").write_bytes(bytes(row["data"]))
                record["variants"].append(vid)
        (backup / f"{slug(tile['name'])}.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        # The new picture first, so it is the one the toolkit shows.
        new_vid = library.add_variant(tile["tile_id"], data=data, content_type="image/png")
        database.dodoland_tiles.update_one({"tile_id": tile["tile_id"]},
                                           {"$set": {"variants": [new_vid]}})
        moved = database.dodoland_decor.update_many(
            {"asset_id": tile["tile_id"], "variant": {"$in": olds + [""]}},
            {"$set": {"variant": new_vid}}).modified_count
        for vid in olds:
            database.dodoland_tile_art.delete_one({"vid": vid})
        library.update_tile(tile["tile_id"], cell_px=cell)
        print(f"  {tile['name']}: replaced; {moved} placed pieces now show it")
    print(f"Old pictures kept in {backup}")


if __name__ == "__main__":
    main()
