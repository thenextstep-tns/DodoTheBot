"""
Import a prepared tile bundle into the global tile library.

    py tools/dodoland_import_tile_bundle.py bundle.json [--dry-run]

A bundle is a JSON list of tiles, already curated::

    [{"category": "Map art · Monsters", "name": "Sea serpent", "pack": "...",
      "cell_px": 57, "uses": ["objects:admin", "objects:player"],
      "source": "miro:Sea serpent", "images": ["<base64 png>", ...]}, ...]

It is the generic half of an import: whoever builds the bundle decides what is a
tile and what is a variant; this only writes it. Categories are created as they
are first met, in the order they appear. Like the pack importer it is
re-runnable — a tile whose ``source`` is already in the library is left alone,
so later renames and ticks survive a second run.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def split_uses(uses: list) -> tuple:
    """A manifest's "layer:role" list as the library's one layer and its roles."""
    layers = [u.split(":")[0] for u in uses if ":" in u]
    layer = layers[0] if layers else "objects"
    return layer, [u.split(":")[1] for u in uses if u.startswith(layer + ":")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bundle", type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true", help="check the bundle, write nothing")
    args = parser.parse_args()

    from helpers.dodoland import tiles as tile_rules

    tiles = json.loads(args.bundle.read_text(encoding="utf-8"))
    # Check everything before writing anything, so a bad entry halfway down
    # does not leave half a bundle in the library.
    for n, tile in enumerate(tiles):
        where = f"entry {n} ({tile.get('name')!r})"
        if not tile.get("images"):
            raise SystemExit(f"{where}: no images")
        if len(tile["images"]) > tile_rules.MAX_VARIANTS:
            raise SystemExit(f"{where}: {len(tile['images'])} images, max {tile_rules.MAX_VARIANTS}")
        tile_rules.clean_cell(tile.get("cell_px", tile_rules.DEFAULT_CELL))
        for image in tile["images"]:
            tile_rules.check_image(base64.b64decode(image), "image/png")
    categories = list(dict.fromkeys(tile["category"] for tile in tiles))
    print(f"{len(tiles)} tiles, {sum(len(t['images']) for t in tiles)} images, "
          f"{len(categories)} categories — bundle is valid")
    if args.dry_run:
        return

    from config import database

    library = tile_rules.TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                                     database.dodoland_tile_art)
    have = {cat["name"]: cat["cat_id"] for cat in library.categories()}
    for name in categories:
        if name not in have:
            have[name] = library.add_category(name)["cat_id"]
    added = kept = 0
    for tile in tiles:
        if library.by_source(tile["source"]):
            kept += 1
            continue
        first, *rest = (base64.b64decode(image) for image in tile["images"])
        layer, access = split_uses(tile.get("uses") or [])
        row = library.add_tile(name=tile["name"], cat_id=have[tile["category"]], data=first,
                               content_type="image/png", layer=tile.get("layer", layer),
                               access=tile.get("access", access),
                               requires=tile.get("requires"),
                               passable=tile.get("passable", True),
                               resizable=tile.get("resizable", False),
                               cell_px=tile.get("cell_px", tile_rules.DEFAULT_CELL),
                               pack=tile.get("pack", ""), source=tile["source"])
        for data in rest:
            library.add_variant(row["tile_id"], data=data, content_type="image/png")
        added += 1
    print(f"added {added} tiles, {kept} were already there")


if __name__ == "__main__":
    main()
