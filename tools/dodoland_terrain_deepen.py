"""Open sea -> deep water, keeping a light coastal band; lakes and rivers untouched."""
import json
import sys
from collections import deque

sys.path.insert(0, r"C:\Users\Lenovo\Documents\DodoTheBot")
from config import database as d
from helpers.dodoland import terrain as T

G = 783594413632520203
BAND = int(sys.argv[2]) if len(sys.argv) > 2 else 3
store = T.TerrainStore(d.dodoland_chunks, d.dodoland_world)
w = store.world(G)
W, H = w["cells_w"], w["cells_h"]
labels = [k["label"] for k in w["kinds"]]
LAKE, DEEP = labels.index("Lake water"), labels.index("Deep water")
cxs, cys = store.chunk_counts(G)
keys = [(x, y) for y in range(cys) for x in range(cxs)]
chunks = store.chunks(G, keys)
cell = lambda x, y: chunks[(x // 64, y // 64)][(y % 64) * 64 + (x % 64)]
water = {LAKE, DEEP}
# distance from land, in cells (multi-source BFS from every land cell)
dist = {}
q = deque()
for y in range(H):
    for x in range(W):
        if cell(x, y) not in water:
            dist[(x, y)] = 0
            q.append((x, y))
while q:
    x, y = q.popleft()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y + dy)
        if 0 <= n[0] < W and 0 <= n[1] < H and n not in dist:
            dist[n] = dist[(x, y)] + 1
            q.append(n)
# open sea: water further than BAND from land, connected to the map's edge
seen = set()
q = deque((x, y) for x in range(W) for y in (0, H - 1)) 
q.extend((x, y) for y in range(H) for x in (0, W - 1))
while q:
    c = q.popleft()
    if c in seen or cell(*c) not in water or dist[c] <= BAND:
        continue
    seen.add(c)
    x, y = c
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y + dy)
        if 0 <= n[0] < W and 0 <= n[1] < H and n not in seen:
            q.append(n)
edits = {c: DEEP for c in seen if cell(*c) == LAKE}
print(f"band {BAND}: {len(seen)} open-sea cells, {len(edits)} to turn deep")
if sys.argv[1] == "--write":
    touched = sorted({(x // 64, y // 64) for x, y in edits})
    snap = store.snapshot(G, touched)
    json.dump({f"{a},{b}": v for (a, b), v in snap.items()}, open(r"%s" % sys.argv[3], "w"))
    store.paint(G, edits)
    print("written; backup", sys.argv[3])
