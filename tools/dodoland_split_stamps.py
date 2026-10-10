"""
Split every placed tile that holds several drawings into one tile per drawing.

    py tools/dodoland_split_stamps.py              # dry run: what would split
    py tools/dodoland_split_stamps.py --write --backup b.json

Variants are for ground: a meadow tile drawn four ways so a painted field does
not repeat. Anything placed is a stamp — you pick a thing and that thing lands.
The importers grouped look-alike sprites ("Olive bush" with six different
bushes) into one tile, and placing it put down a random one of them. This makes
each drawing its own tile, named "<name> 2", "<name> 3"…, right after the first
in its category, sharing every other setting. The art rows are moved, not
copied, and every placed piece that showed a moved drawing is pointed at its
new tile, so nothing on the map changes.
"""

from __future__ import annotations

import argparse
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", type=pathlib.Path, default=pathlib.Path("dodoland_before_split.json"))
    args = parser.parse_args()

    from bson import json_util

    from config import database as db
    from helpers.dodoland import tiles as T

    lib = T.TileLibrary(db.dodoland_tiles, db.dodoland_tile_cats, db.dodoland_tile_art)
    # Placement as the library reads it: older rows have no field and get the
    # layer's default, so asking the database for "place" misses them.
    stamps = {t["tile_id"] for t in lib.tiles() if t["placement"] == "place"}
    for guild_id in {int(r.get("guild_id") or 0) for r in db.dodoland_tiles.find({}, {"guild_id": 1})} - {0}:
        stamps |= {t["tile_id"] for t in lib.tiles(guild_id) if t["placement"] == "place"}
    groups = [t for t in db.dodoland_tiles.find({"tile_id": {"$in": sorted(stamps)}})
              if len(t.get("variants") or []) > 1]
    extra = sum(len(t["variants"]) - 1 for t in groups)
    total = db.dodoland_tiles.count_documents({})
    print(f"{len(groups)} placed tiles hold several drawings; splitting adds {extra} tiles "
          f"({total} -> {total + extra}, cap {T.MAX_TILES})")
    if total + extra > T.MAX_TILES:
        raise SystemExit("That would pass the library's cap.")
    for t in groups[:8]:
        print(f"  {t['name']}: {len(t['variants'])}")
    if not args.write:
        print("dry run; pass --write")
        return

    tile_ids = [t["tile_id"] for t in groups]
    args.backup.write_text(json_util.dumps({
        "tiles": list(db.dodoland_tiles.find({"tile_id": {"$in": tile_ids}})),
        "art": list(db.dodoland_tile_art.find({"tile_id": {"$in": tile_ids}}, {"data": 0})),
        "decor": list(db.dodoland_decor.find({"asset_id": {"$in": tile_ids}})),
    }), encoding="utf-8")

    moved_pieces = 0
    touched_cats = set()
    taken: dict = {}
    for tile in groups:
        first, rest = tile["variants"][0], tile["variants"][1:]
        cat = (tile.get("cat_id") or "", tile.get("guild_id", 0))
        if cat not in taken:
            taken[cat] = {r["name"] for r in db.dodoland_tiles.find({"cat_id": cat[0]})}
        base = {k: v for k, v in tile.items() if k not in ("_id", "tile_id", "variants", "name", "source")}
        for n, vid in enumerate(rest, start=2):
            new_id = secrets.token_hex(8)
            # The next free number: "Sand Dune 2" may already be a tile.
            k = n
            while f"{tile['name']} {k}"[:T.MAX_NAME] in taken[cat]:
                k += 1
            name = f"{tile['name']} {k}"[:T.MAX_NAME]
            taken[cat].add(name)
            source = f"{tile.get('source') or ''}#{n}" if tile.get("source") else ""
            # Fractional order slots it right after its first; renumbered below.
            db.dodoland_tiles.insert_one({**base, "tile_id": new_id, "name": name, "source": source,
                                          "variants": [vid], "order": float(tile.get("order", 0)) + n / 100})
            db.dodoland_tile_art.update_one({"vid": vid}, {"$set": {"tile_id": new_id}})
            moved_pieces += db.dodoland_decor.update_many(
                {"asset_id": tile["tile_id"], "variant": vid}, {"$set": {"asset_id": new_id}}).modified_count
        db.dodoland_tiles.update_one({"tile_id": tile["tile_id"]}, {"$set": {"variants": [first]}})
        touched_cats.add((tile.get("cat_id") or "", tile.get("guild_id", 0)))

    for cat_id, guild_id in touched_cats:
        rows = sorted(db.dodoland_tiles.find({"cat_id": cat_id}),
                      key=lambda r: float(r.get("order", 0)))
        for i, row in enumerate(rows):
            db.dodoland_tiles.update_one({"_id": row["_id"]}, {"$set": {"order": i}})
    print(f"split; {moved_pieces} placed pieces repointed; backup {args.backup}")


if __name__ == "__main__":
    main()
