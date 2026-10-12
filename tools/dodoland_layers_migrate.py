"""
One-off: give the map real layers.

    py tools/dodoland_layers_migrate.py GUILD [--plan plan.json]            # report
    py tools/dodoland_layers_migrate.py GUILD [--plan plan.json] --write    # do it

1. **Terrain art belongs to the environment.** The Miro map's mountains, forests,
   hills, fields, dunes, flowers, ponds, rocks, caves, swamp and waves are part of
   the base map, not decor: their tiles move to layer 1 as *placed features*
   (the environment's painted ground stays painted), admins only.
2. **Every placed piece records its layer**, from its tile, so the map can draw,
   show, hide and lock layers separately.
3. With ``--plan`` (the placement plan that put the pieces there): each terrain
   tile's px-per-cell is re-derived from how its own drawings sit on the map —
   the median of image width over placed width — and its pieces resized to
   match. The first estimate came from a section's median and put 259 oaks at
   the 4x ceiling; this one comes from where every oak actually stands.

Fills and fixes only; re-running it changes nothing further.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TERRAIN = {"Trees", "Big Mountain", "Small Mountain", "Hills",
           "Moronobu Gansai (Mountains) and Clouds", "Fields", "Sand Dunes", "Flowers",
           "Bushes/Plantlife", "Ponds", "Random Rocks", "Caves", "Swampy swamp", "Waves"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("--plan", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import decor as decor_rules
    from helpers.dodoland import tiles as tile_rules

    library = tile_rules.TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                                     database.dodoland_tile_art)
    cats = {c["cat_id"]: c["name"] for c in library.categories()}
    terrain_tiles = [t for t in library.tiles()
                     if cats.get(t["cat_id"], "").replace("Map art · ", "") in TERRAIN
                     and cats.get(t["cat_id"], "").startswith("Map art · ")]
    move = [t for t in terrain_tiles
            if (t["layer"], t["placement"], t["access"]) != ("environment", "place", ["admin"])]
    print(f"{len(move)} of {len(terrain_tiles)} terrain tiles to move to layer 1 as placed features")

    rows = list(database.dodoland_decor.find({"guild_id": args.guild}))
    tiles = {t["tile_id"]: t for t in library.tiles(args.guild)}
    want = {t["tile_id"]: "environment" for t in terrain_tiles}
    relayer = [r for r in rows if r.get("layer") != want.get(
        r["asset_id"], (tiles.get(r["asset_id"]) or {}).get("layer", "objects"))]
    print(f"{len(relayer)} of {len(rows)} pieces to record their layer")

    rescale = {}
    if args.plan:
        plan = {p["source"]: p for p in json.loads(args.plan.read_text(encoding="utf-8"))["decor"]}
        widths = {}
        for t in terrain_tiles:
            widths.update(library.art_sizes(t["variants"]))
        samples: dict = {}
        for r in rows:
            p = plan.get(r.get("source") or "")
            t = tiles.get(r["asset_id"])
            if not p or not t or not p["width_cells"]:
                continue
            w = widths.get(r.get("variant") or t["variants"][0], (0, 0))[0]
            if w:
                samples.setdefault(t["tile_id"], []).append(w / p["width_cells"])
        for tile_id, values in samples.items():
            cell = max(tile_rules.MIN_CELL, min(tile_rules.MAX_CELL, round(statistics.median(values))))
            if cell != tiles[tile_id]["cell_px"]:
                rescale[tile_id] = cell
        print(f"{len(rescale)} terrain tiles get a px-per-cell read off the map, e.g. "
              + ", ".join(f"{tiles[k]['name']} {tiles[k]['cell_px']}->{v}" for k, v in list(rescale.items())[:5]))
    if not args.write:
        print("dry run; pass --write")
        return

    for t in move:
        library.update_tile(t["tile_id"], layer="environment", placement="place", access=["admin"])
    for tile_id, cell in rescale.items():
        library.update_tile(tile_id, cell_px=cell)
    tiles = {t["tile_id"]: t for t in library.tiles(args.guild)}
    resized = 0
    if args.plan:
        sizes = {}
        for t in tiles.values():
            if t["tile_id"] in rescale:
                sizes.update(library.art_sizes(t["variants"][:1]))
    for r in rows:
        t = tiles.get(r["asset_id"])
        changes = {"layer": t["layer"] if t else r.get("layer", "objects")}
        if args.plan and t and t["tile_id"] in rescale:
            p = plan.get(r.get("source") or "")
            w = sizes.get(t["variants"][0], (0, 0))[0]
            if p and w:
                low, high = tile_rules.scale_range(t)
                changes["scale"] = round(max(low, min(high, p["width_cells"] / (w / t["cell_px"]))), 3)
                resized += 1
        database.dodoland_decor.update_one({"_id": r["_id"]}, {"$set": changes})
    print(f"done: {len(move)} tiles moved, {len(rescale)} rescaled, {len(rows)} pieces layered, {resized} resized")


if __name__ == "__main__":
    main()
