"""
Make the Lights category: the library's lamps, lanterns, torches and fires,
each given a light that shines at night.

    py tools/dodoland_lights_category.py            # report
    py tools/dodoland_lights_category.py --write    # do it

Moves the tiles named below into **Lights** (made if missing) and sets each
one's light reach (cells) and colour, which the tile library shows and edits
like any other setting. Any other tile can be given a light there too.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

CATEGORY = "Lights"
WARM, FIRE = "#ffc46b", "#ff9a3c"
# name -> (reach in cells, colour)
LIGHTS = {"Lamp post": (6.0, WARM), "Lantern pedestal": (5.0, WARM), "Oil lantern": (3.5, WARM),
          "Wall torch": (4.0, FIRE), "Fireplace": (4.0, FIRE), "Campfire": (6.0, FIRE)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from config import database
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    cats = {c["cat_id"]: c["name"] for c in library.categories()}
    found = [t for t in library.tiles() if t["name"] in LIGHTS]
    for t in found:
        reach, colour = LIGHTS[t["name"]]
        print(f"  {t['name']}: {cats.get(t['cat_id'], '?')} -> {CATEGORY}, light {reach} cells {colour}")
    missing = sorted(set(LIGHTS) - {t["name"] for t in found})
    if missing:
        print(f"  not in the library: {', '.join(missing)}")
    if not args.write:
        print("Nothing written. Add --write to do it.")
        return
    cat = next((c for c in library.categories() if c["name"] == CATEGORY), None) or library.add_category(CATEGORY)
    for t in found:
        reach, colour = LIGHTS[t["name"]]
        library.update_tile(t["tile_id"], cat_id=cat["cat_id"], light_radius=reach, light_colour=colour)
    print(f"{len(found)} tiles are in {CATEGORY} and light up at night.")


if __name__ == "__main__":
    main()
