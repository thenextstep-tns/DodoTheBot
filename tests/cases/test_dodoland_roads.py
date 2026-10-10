"""DodoLand: roads the bot lays between towns whose people talk.

Each town keeps its strongest few connections; a road goes round what it cannot
cross, bridges water it may cross, joins roads already laid, and is refused at
once between towns no road could ever join.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from helpers.dodoland import roads as R  # noqa: E402

# --- who gets a road --------------------------------------------------------
pairs = [{"a": 1, "b": 2, "n": 9}, {"a": 2, "b": 1, "n": 3}, {"a": 1, "b": 3, "n": 4},
         {"a": 1, "b": 4, "n": 1}, {"a": 1, "b": 99, "n": 50}, {"a": 3, "b": 3, "n": 7}]
edges = R.connections([1, 2, 3, 4], pairs, per_town=1, minimum=2)
assert edges[0] == ("1", "2", 12), "pair rows are summed both ways, strongest first"
assert ("1", "4") not in {(a, b) for a, b, _ in edges}, "a link below the minimum got a road"
assert all("99" not in (a, b) for a, b, _ in edges), "a road led to a town that is not on the map"
assert ("1", "3", 4) in edges, "a link one end keeps is built even if the other end has better"
print("links           strongest few per town, summed both ways, placed towns only")

# --- the way ------------------------------------------------------------------
land = {"move": 1, "grow": 1}
mountain = {"move": None, "grow": None}
river = {"move": None, "grow": 1, "water": True}
sea = {"move": None, "grow": None, "water": True}
kinds = [land, mountain, river, sea]
cells = np.zeros((20, 30), dtype=np.int16)
cells[:15, 10] = 1                         # a wall of mountain with a gap at the bottom
cells[:, 20] = 2                           # a river right across
cost, water = R.coarse_costs(cells, kinds, 1, bridge=6.0)
path = R.astar(cost, (2, 2), (27, 2))
assert path and path[0] == (2, 2) and path[-1] == (27, 2)
assert all(cells[y, x] != 1 for x, y in path), "a road went through a mountain"
assert max(y for _, y in path) >= 15, "the road did not go round the mountain"
bridges = R.spans(path, water)
assert len(bridges) == 1, "the river is crossed once, as a bridge"
print("routing         round mountains, over the river by a bridge")

# Ground that carries a road is cheaper, so a second road joins the first.
carried = np.zeros(cost.shape, dtype=bool)
for x, y in path:
    carried[y, x] = True
second = R.astar(cost, (2, 4), (27, 4), carried, reuse=0.2)
shared = sum(1 for x, y in second if carried[y, x])
assert shared > len(second) // 2, "a later road did not run along the earlier one"
print("network         later roads run along earlier ones")

# Coarsening keeps a thin river and a mountain's edge.
c2, w2 = R.coarse_costs(cells, kinds, 2, bridge=6.0)
assert w2[:, 10].any(), "a one-cell river vanished when the grid was coarsened"
assert not np.isfinite(c2[0, 5]), "a mountain's edge was shaved off when the grid was coarsened"
print("coarse          a thin river and a mountain's edge survive the coarser grid")

# Towns on different islands: refused at once.
island = np.zeros((10, 20), dtype=np.int16)
island[:, 9:11] = 3
cost3, _ = R.coarse_costs(island, kinds, 1, bridge=6.0)
image = R.regions(cost3)
assert not R.same_region(image, (2, 5), (17, 5)), "open sea did not separate two islands"
assert R.same_region(image, (2, 5), (5, 5))
print("islands         towns no road could join are refused before searching")

line = R.straighten([(0, 0), (1, 0), (2, 0), (3, 0), (3, 1)], np.ones((3, 5), dtype="float32"),
                    np.zeros((3, 5), dtype=bool))
assert line[0] == (0, 0) and line[-1] == (3, 1) and len(line) < 5
print("drawing         a grid path is straightened where nothing is in the way")

print("PASS")
