"""DodoLand: how a town's area of influence grows.

It spreads from the town hall like water, paying what each cell costs, and stops
where its budget runs out — so on open ground it is round, beside a lake it flows
round the lake, and against impassable ground it stops. Its size follows town
power on a square root, and its outline is exactly the border of its cells.
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from helpers.dodoland import influence as I  # noqa: E402

W = H = 101
open_ground = lambda x, y: 1.0  # noqa: E731

# Open ground grows round: the area is close to a disc of the budget's radius,
# not a diamond (which is what four neighbours alone would give).
area = I.grow((50, 50), 10, open_ground, W, H)
assert abs(len(area) - math.pi * 10 * 10) / (math.pi * 100) < 0.12, len(area)
assert (57, 57) in area and (60, 50) in area and (61, 50) not in area
print(f"growth          open ground grows round: {len(area)} cells for a radius of 10")

# The budget is a hard edge and the origin always belongs to the town.
assert I.grow((50, 50), 0, open_ground, W, H) == {(50, 50)}
assert I.grow((500, 5), 10, open_ground, W, H) == set(), "a town off the map has no area"
print("growth          a zero budget is the plot itself; off the map is nothing")

# A lake: impassable cells it must flow round, not across.
lake = {(x, y) for x in range(52, 58) for y in range(40, 61)}
cost = lambda x, y: None if (x, y) in lake else 1.0  # noqa: E731
area = I.grow((50, 50), 25, cost, W, H)
assert not area & lake, "influence crossed the lake"
assert (59, 50) not in area, "it should not reach straight through the lake"
assert (59, 38) in area or (59, 62) in area, "it should flow round the lake's ends"
print("growth          an area flows round a lake rather than across it")

# Dearer ground shortens the reach.
hills = lambda x, y: 3.0 if x > 50 else 1.0  # noqa: E731
area = I.grow((50, 50), 12, hills, W, H)
# Three times the cost is a third of the reach: 12 cells west, 4 east.
assert max(x for x, y in area if y == 50) == 54, "hills should cut the reach to a third"
assert min(x for x, y in area if y == 50) == 38
print("growth          dearer ground shortens the reach on that side")

# Reach follows power on a square root, between the weakest and the strongest.
assert I.reach(0, 100, 6, 40) == 6 and I.reach(100, 100, 6, 40) == 40
assert I.reach(25, 100, 6, 40) == 6 + 34 * 0.5
assert I.reach(50, 0, 6, 40) == 6, "no standings anywhere is the base reach"
print("reach           power maps to reach on a square root between base and top")

# The outline is exactly the border: a 3x2 block has a perimeter of 10 edges.
block = {(x, y) for x in range(3) for y in range(2)}
line = I.outline_path(block)
total = sum(int(part[1:].split("h")[-1].split("v")[-1]) for part in line.split("M")[1:])
assert total == 10, (line, total)
assert I.fill_path(block).count("M") == 1, "a solid block should be one rectangle"
assert I.outline_path(set()) == "" and I.fill_path(set()) == ""
print("drawing         the outline is the area's exact border, the fill merged rectangles")

# The smoothed border: one loop per edge, holes included, corners only.
ring = {(x, y) for x in range(20) for y in range(20)} - {(x, y) for x in range(8, 12) for y in range(8, 12)}
edges = I.loops(ring)
assert len(edges) == 2, "an area with a hole has an outer and an inner border"
assert sorted(len(e) for e in edges) == [4, 4], "a square border keeps only its four corners"
strip = I.loops({(0, 0), (1, 0), (2, 0)})
assert len(strip) == 1 and set(strip[0]) == {(0, 0), (3, 0), (3, 1), (0, 1)}
path = I.ring_path({(x, y) for x in range(30) for y in range(30) if (x - 15) ** 2 + (y - 15) ** 2 < 150})
assert path.startswith("M") and path.endswith("Z") and path.count("M") == 1
assert I.ring_path({(5, 5)}) == "", "a stray cell gets no wall"
print("ring            the border smoothed into closed loops; a stray cell gets none")

# The fast search over a flat cost list is the same search: same cells for a
# lake, dear hills and the map's edges (where a step must not wrap a row).
import random  # noqa: E402
rng = random.Random(4)
rough = {(x, y): (None if rng.random() < 0.15 else rng.choice((1.0, 1.0, 2.0, 3.0)))
         for x in range(W) for y in range(H)}
flat = [math.inf if rough[(i % W, i // W)] is None else rough[(i % W, i // W)] for i in range(W * H)]
for origin, budget in (((50, 50), 30), ((0, 50), 20), ((W - 1, 10), 25), ((3, H - 2), 40)):
    slow = I.grow(origin, budget, lambda x, y: rough[(x, y)], W, H)
    assert I.grow_grid(origin, budget, flat, W, H) == slow, origin
assert I.grow_grid((500, 5), 10, flat, W, H) == set()
blob = I.grow((50, 50), 30, lambda x, y: rough[(x, y)], W, H)
covered = set()
for part in I.fill_path(blob).split("M")[1:]:
    x, rest = part.split(" ", 1)
    y, rest = rest.split("h", 1)
    w, rest = rest.split("v", 1)
    h = rest.split("h", 1)[0]
    covered |= {(int(x) + i, int(y) + j) for i in range(int(w)) for j in range(int(h))}
assert covered == blob, "the fill does not cover the area exactly"
print("growth          the flat-list search finds the same cells; the fill covers them exactly")

# A due refresh serves the areas already made at once and works the new ones
# out behind them; a real change is worked out before answering.
import time as _time  # noqa: E402
from web.dodoland import influence_api as IA  # noqa: E402
made, keys = [], {"k": 1}
IA._key = lambda bot, guild: keys["k"]
IA.compute = lambda bot, guild: (made.append(1), IA._CELLS.__setitem__(guild.id, {}), {"n": len(made)})[2]
class _G:
    id = 99
assert IA.current(None, _G)["n"] == 1
IA._CACHE[99] = (1, _time.time() - IA._TTL - 1, IA._CACHE[99][2])
assert IA.current(None, _G)["n"] == 1, "a due refresh made the caller wait"
for _ in range(100):
    if 99 not in IA._REFRESHING and len(made) == 2:
        break
    _time.sleep(0.02)
assert IA.current(None, _G)["n"] == 2, "the refresh behind never landed"
keys["k"] = 2
assert IA.current(None, _G)["n"] == 3, "a change was answered from the old areas"
print("cache           a due refresh happens behind the answer; a change is never served stale")

# Walls are a town's style, not pieces: only the known styles are accepted.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from fake_mongo import FakeCollection  # noqa: E402
from helpers.dodoland import towns as town_rules  # noqa: E402

store = town_rules.TownStore(FakeCollection())
assert store.save(1, 2, walls="stone")["walls"] == "stone"
assert store.save(1, 2, walls="")["walls"] == ""
try:
    store.save(1, 2, walls="lava")
    raise AssertionError("an unknown wall style was accepted")
except town_rules.TownError:
    pass
print("walls           a town is walled in a known style or not at all")

# Where walls stand: round walled towns' land as one territory. Two overlapping
# walled towns share their outer wall and have none through the overlap; a wall
# stops at the shore and leaves the water open.
from helpers.dodoland import influence as _inf  # noqa: E402

_A = {(x, y) for x in range(5, 25) for y in range(5, 25)}          # stone
_B = {(x, y) for x in range(17, 37) for y in range(5, 25)}         # palisade
_water = {(x, y) for x in range(33, 45) for y in range(0, 40)}     # the sea, east
_wet = lambda c: not (0 <= c[0] < 45 and 0 <= c[1] < 40) or c in _water  # noqa: E731
_owner = {c: "b" for c in _B if not _wet(c)}
_owner.update({c: "a" for c in _A})
_runs = _inf.wall_runs(set(_owner), lambda c: {"a": "stone", "b": "palisade"}[_owner[c]], _wet)
_pts = [pt for _style, pts in _runs for pt in pts]
assert {style for style, _pts2 in _runs} == {"stone", "palisade"}, _runs
assert not [pt for pt in _pts if 17.5 < pt[0] < 24.5 and 5.5 < pt[1] < 24.5], \
    "a wall runs through the overlap of two walled towns"
assert max(pt[0] for pt in _pts) <= 33, "a wall went out into the water"
assert not [pt for pt in _pts if pt[0] == 33 and 6 < pt[1] < 24], "the shore was walled off"
print("walls           walled towns share one outer wall, and it stops at the shore")

print("PASS")
