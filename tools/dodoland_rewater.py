"""
Repaint a server's water with the smart water grounds.

The world was painted with plain water kinds: deep water round the continent,
shallow water along the coast, lake water in lakes and rivers. This turns
every cell of each into its smart ground (a 3 x 3 tileset with its shore):

* deep water    -> Deep ocean water   (deep_ocean_tileset; the open sea)
* shallow water -> Shallow sea water  (ocean_shallows_tileset)
* lake water    -> Lake water (smart) (water_lake_tileset)

Old kinds are found by label among the kinds that are *not* smart grounds;
new ones by the smart tiles' names. Every chunk it changes is backed up first
(``logs/terrain_backup_<time>.json``, ``--restore`` puts one back).

    py -3.13 tools/dodoland_rewater.py            # what it would do
    py -3.13 tools/dodoland_rewater.py --write    # do it, then restart the bot
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

GUILD = 783594413632520203
# old kind label -> new smart tile name
SWAPS = {"Deep water": "Deep ocean water", "Shallow water": "Shallow sea water", "Lake water": "Lake water"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--guild", type=int, default=GUILD)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--restore", type=pathlib.Path)
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import terrain as T
    from helpers.dodoland.tiles import TileLibrary

    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)
    gid = args.guild
    if args.restore:
        snap = json.loads(args.restore.read_text(encoding="utf-8"))
        n = store.restore(gid, {tuple(map(int, k.split(","))): v for k, v in snap.items()})
        store.touch(gid)
        print(f"restored {n} chunks from {args.restore}")
        return
    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    smart = {t["name"]: t for t in library.tiles(gid) if t.get("autotile")}
    kinds = store.world(gid)["kinds"]
    mapping = {}
    for old_label, new_name in SWAPS.items():
        tile = smart.get(new_name)
        if tile is None:
            sys.exit(f"no smart ground called {new_name!r} - import it first")
        olds = [i for i, k in enumerate(kinds) if k.get("label") == old_label
                and not (smart.get(k.get("label")) and k.get("tile_id") == smart[k["label"]]["tile_id"])]
        new = store.kind_for_tile(gid, tile) if args.write else next(
            (i for i, k in enumerate(kinds) if k.get("tile_id") == tile["tile_id"]), "(new)")
        for i in olds:
            mapping[i] = new
        print(f"  {old_label} {olds} -> {new_name} kind {new}")
    if not mapping:
        print("nothing to repaint")
        return
    cxs, cys = store.chunk_counts(gid)
    boxes = [(x, y) for y in range(cys) for x in range(cxs)]
    chunks = store.chunks(gid, boxes)
    changed, cells_changed = {}, 0
    for key, cells in chunks.items():
        if not cells:
            continue
        hit = sum(1 for v in cells if v in mapping)
        if hit:
            changed[key] = cells
            cells_changed += hit
    print(f"{cells_changed} cells in {len(changed)} of {len(boxes)} chunks")
    if not args.write:
        print("Nothing written. Add --write to repaint.")
        return
    backup = pathlib.Path("logs") / f"terrain_backup_{int(time.time())}.json"
    backup.parent.mkdir(exist_ok=True)
    backup.write_text(json.dumps({f"{cx},{cy}": T.encode(c) for (cx, cy), c in changed.items()}), encoding="utf-8")
    print(f"backed up to {backup}")
    for (cx, cy), cells in changed.items():
        store.write_chunk(gid, cx, cy, [mapping.get(v, v) for v in cells])
    store.touch(gid)
    print(f"repainted {len(changed)} chunks. Restart the bot (it keeps the old chunks in memory).")


if __name__ == "__main__":
    main()
