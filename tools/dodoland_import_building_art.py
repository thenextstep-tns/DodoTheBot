"""
Upload painted pictures for a server's town buildings, one per tier, beside
the generated ones.

    py tools/dodoland_import_building_art.py <guild id> <folder>            # report
    py tools/dodoland_import_building_art.py <guild id> <folder> --write    # upload
    ... --map museum=library                                                 # a folder for a building

The folder holds one sub-folder per building, each with ``tier_<n>_*.png`` at
full resolution (any ``64x64`` sub-folder is ignored). A sub-folder is matched
to a building by :data:`FOLDERS`, or by ``--map folder=key``. Each picture is
stored on that building tier's tile (``building:<guild>:<key>:<tier>``) as its
``uploaded`` picture: the generated drawing stays exactly as it is, and the
server's *Building artwork* setting (``dodoland_building_art``) chooses which the
map draws. Re-running replaces a tier's uploaded picture.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# The DodoArt/buildings folders, by what they were painted for.
FOLDERS = {
    "tavern_inn": "tavern", "magic_academy": "library", "royal_castle": "warroom",
    "red_fortress": "barracks", "theater_opera": "playhouse", "zoo": "menagerie",
    "hall_of_wonders": "gallery", "portrait_hall": "portraits", "endless_feast": "bakery",
    "clockwork_workshop": "workshop", "sanctuary": "sanctuary", "undercroft": "undercroft",
    "dodo_monument": "statue",
}


def tiers(folder: pathlib.Path) -> dict:
    out = {}
    for f in sorted(folder.glob("tier_*.png")):
        m = re.match(r"tier_(\d+)", f.name)
        if m:
            out[int(m.group(1))] = f
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--map", action="append", default=[], help="folder=building key")
    args = parser.parse_args()

    from PIL import Image

    from config import database
    from helpers.dodoland import building_tiles
    from helpers.dodoland.buildings import BuildingStore
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    keys = {b["key"]: b for b in BuildingStore(database.dodoland_config).buildings(args.guild)}
    mapping = dict(FOLDERS)
    for pair in args.map:
        folder, _, key = pair.partition("=")
        mapping[folder.strip()] = key.strip()

    plan = []
    for sub in sorted(p for p in args.folder.iterdir() if p.is_dir()):
        key = mapping.get(sub.name)
        if not key:
            print(f"  {sub.name}: no building is set for it; left out (use --map {sub.name}=<key>)")
            continue
        if key not in keys:
            print(f"  {sub.name}: this server has no building {key!r}; left out")
            continue
        found = tiers(sub)
        want = len(keys[key]["tiers"])
        row = []
        for tier in range(1, want + 1):
            path = found.get(tier)
            tile = library.by_source(building_tiles._source(args.guild, key, tier))
            if path is None or tile is None:
                row.append(f"t{tier} {'no picture' if path is None else 'no tile'}")
                continue
            image = Image.open(path)
            if image.mode != "RGBA":
                sys.exit(f"{path} has no transparency ({image.mode}).")
            plan.append((tile, path, key, tier))
            row.append(f"t{tier} {image.size[0]}x{image.size[1]}")
        extra = sorted(set(found) - set(range(1, want + 1)))
        print(f"  {sub.name} -> {keys[key].get('name') or key}: " + ", ".join(row) +
              (f"; tiers {extra} have no building tier" if extra else ""))
    unpainted = sorted(set(keys) - {mapping.get(s.name) for s in args.folder.iterdir() if s.is_dir()})
    if unpainted:
        print(f"  no pictures for: {', '.join(keys[k].get('name') or k for k in unpainted)} (they keep their generated art)")
    print(f"{len(plan)} pictures to upload")
    if not args.write:
        print("Nothing written. Add --write to upload.")
        return
    for tile, path, key, tier in plan:
        old = str(tile.get("uploaded") or "")
        vid = library._store_art(tile["tile_id"], path.read_bytes(), "image/png")
        database.dodoland_tiles.update_one({"tile_id": tile["tile_id"]}, {"$set": {"uploaded": vid}})
        if old and old != vid:
            database.dodoland_tile_art.delete_one({"vid": old})
    print(f"Uploaded {len(plan)}. The generated drawings are untouched; switch with Building artwork.")


if __name__ == "__main__":
    main()
