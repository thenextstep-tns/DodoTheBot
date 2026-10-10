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

print("PASS")
