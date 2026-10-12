"""
Turn the open sea into deep water, keeping a light band along every coast.

    py tools/dodoland_terrain_deepen.py GUILD [--band 3]                          # report
    py tools/dodoland_terrain_deepen.py GUILD [--band 3] --write --backup b.json  # do it

Open sea is water further than ``band`` cells from land and connected to the
map's edge through such water. Lakes and rivers stay as they are: a river is
too narrow to connect an inland lake to the open sea at that distance.
Expects the world's water kinds to be labelled "Lake water" and "Deep water"
(what ``tools/dodoland_terrain_rebuild.py`` leaves).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import deque

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("--band", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", type=pathlib.Path, default=pathlib.Path("dodoland_before_deepen.json"))
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import terrain as T

    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)
    world = store.world(args.guild)
    W, H = world["cells_w"], world["cells_h"]
    labels = [k["label"] for k in world["kinds"]]
    lake, deep = labels.index("Lake water"), labels.index("Deep water")
    cxs, cys = store.chunk_counts(args.guild)
    keys = [(x, y) for y in range(cys) for x in range(cxs)]
    chunks = store.chunks(args.guild, keys)

    def cell(x, y):
        return chunks[(x // T.CHUNK, y // T.CHUNK)][(y % T.CHUNK) * T.CHUNK + (x % T.CHUNK)]

    water = {lake, deep}
    dist, queue = {}, deque()
    for y in range(H):
        for x in range(W):
            if cell(x, y) not in water:
                dist[(x, y)] = 0
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= n[0] < W and 0 <= n[1] < H and n not in dist:
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    seen = set()
    queue = deque([(x, y) for x in range(W) for y in (0, H - 1)] +
                  [(x, y) for y in range(H) for x in (0, W - 1)])
    while queue:
        c = queue.popleft()
        if c in seen or cell(*c) not in water or dist.get(c, 99) <= args.band:
            continue
        seen.add(c)
        x, y = c
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= n[0] < W and 0 <= n[1] < H and n not in seen:
                queue.append(n)
    edits = {c: deep for c in seen if cell(*c) == lake}
    print(f"band {args.band}: {len(seen)} open-sea cells, {len(edits)} to turn deep")
    if not args.write:
        print("dry run; pass --write")
        return
    touched = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in edits})
    snap = store.snapshot(args.guild, touched)
    args.backup.write_text(json.dumps({f"{a},{b}": v for (a, b), v in snap.items()}), encoding="utf-8")
    store.paint(args.guild, edits)
    store.touch(args.guild)
    print(f"written; backup {args.backup}")


if __name__ == "__main__":
    main()
