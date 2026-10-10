"""
One-off migration: the tile library takes over from the asset library.

    py tools/dodoland_tiles_migrate.py            # report what would change
    py tools/dodoland_tiles_migrate.py --write    # do it

Three things, each of which only fills what is **not set yet**, so a second
run changes nothing and never overwrites an edit made in the panel:

1. **Layer and access.** Tiles stored with the old ``uses`` list ("layer:role")
   get an explicit ``layer`` and ``access``.
2. **Passable and resizable**, judged per tile from what it is (the rules are
   below and are the whole of the judgement). Map art resizes; pixel art does
   not. Water, mountains, buildings, walls, solid props block roads; ground,
   flowers, tufts, creatures, items and bridges do not.
3. **The asset library's uploads** become that server's own tiles, with their
   lock carried over (building + tier; admin-only becomes admin access only).
   ``DodoLandAssets`` itself is left untouched — production still reads it.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

MAP_ART = "DodoLand Miro board"

# Category -> passable. Anything not listed is passable.
BLOCKING_CATEGORIES = {
    "Water", "Houses", "House parts", "Walls & ruins", "Monuments & graves",
    "Containers", "Camp & furniture",
    "Map art · Waves", "Map art · Ponds", "Map art · Big Mountain",
    "Map art · Small Mountain", "Map art · Moronobu Gansai (Mountains) and Clouds",
    "Map art · Castles", "Map art · Settlements - Ruins", "Map art · Settlements - Steampunk",
    "Map art · Settlements - Futuristic", "Map art · More Settlements",
    "Map art · Shrines & Monuments", "Map art · Fountains", "Map art · Caves",
    "Map art · Random Rocks",
}
# Within otherwise passable or blocking categories, by name.
BLOCKING_NAMES = re.compile(r"boulder|rubble|\brock\b|monolith|fence|\bpost\b|\bpole\b", re.I)
PASSABLE_NAMES = re.compile(r"pebble|dock|plank|bridge|stairs|stone patch|floor slab", re.I)
# Resizable map art may be drawn from a quarter to four times its natural size.
ART_RANGE = (0.25, 4.0)


def passable(tile: dict, category: str) -> bool:
    name = tile["name"]
    if PASSABLE_NAMES.search(name):
        return True
    if category in BLOCKING_CATEGORIES:
        return False
    if category == "Rocks" or category.startswith("Map art · ") and "Rock" in category:
        return False
    if BLOCKING_NAMES.search(name) and category not in ("Grass tufts", "Items"):
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import tiles as tile_rules

    library = tile_rules.TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                                     database.dodoland_tile_art)
    cats = {c["cat_id"]: c["name"] for c in library.categories()}
    planned = []
    for raw in database.dodoland_tiles.find({}, {"_id": 0}):
        tile = tile_rules._complete(dict(raw))
        category = cats.get(tile["cat_id"], "")
        changes = {}
        for key in ("layer", "access", "requires", "guild_id"):
            if key not in raw:
                changes[key] = tile[key]
        if "passable" not in raw:
            changes["passable"] = passable(tile, category)
        if "resizable" not in raw:
            art = tile.get("pack") == MAP_ART
            changes["resizable"] = art
            if art:
                changes["scale_min"], changes["scale_max"] = ART_RANGE
        if changes:
            planned.append((tile["tile_id"], tile["name"], category, changes))

    blocked = sum(1 for *_, c in planned if c.get("passable") is False)
    sized = sum(1 for *_, c in planned if c.get("resizable"))
    print(f"{len(planned)} tiles to update: {blocked} set to block roads, {sized} made resizable")
    for _, name, category, changes in planned:
        if changes.get("passable") is False:
            print(f"   blocks roads  {category} / {name}")

    assets = list(database.dodoland_assets.find({}))
    todo = [a for a in assets if not library.by_source(f"asset:{a['guild_id']}:{a['asset_id']}")]
    print(f"{len(todo)} asset-library uploads to copy in as server tiles")
    for asset in todo:
        print(f"   {asset['guild_id']}: {asset.get('name')} "
              f"({'admin only' if asset.get('admin_only') else 'admins and players'})")

    if not args.write:
        print("dry run; pass --write to apply")
        return
    for tile_id, _, _, changes in planned:
        database.dodoland_tiles.update_one({"tile_id": tile_id}, {"$set": changes})
    for asset in todo:
        data = asset.get("data")
        if not data:
            continue
        library.add_tile(
            name=asset.get("name") or "Asset", cat_id="", data=bytes(data),
            content_type=str(asset.get("content_type") or "image/png"),
            guild_id=int(asset["guild_id"]), layer="objects",
            access=["admin"] if asset.get("admin_only") else ["admin", "player"],
            requires={"building": asset.get("building") or "",
                      "tier": int(asset.get("min_tier") or 0)},
            passable=True, resizable=True, scale_min=ART_RANGE[0], scale_max=ART_RANGE[1],
            pack="Asset library", source=f"asset:{asset['guild_id']}:{asset['asset_id']}")
    print(f"done: {len(planned)} tiles updated, {len(todo)} assets copied")


if __name__ == "__main__":
    main()
