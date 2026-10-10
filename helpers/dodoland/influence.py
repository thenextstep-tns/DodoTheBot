"""
How far a town's influence reaches, and what shape it takes.

A town is a town hall at its plot plus an **area of influence** that grows out
over the terrain grid. It is not a circle: it spreads like water from the hall,
each step paying what the ground costs to grow onto (``kind["grow"]``), and
stops where its budget runs out. Sea, mountains and anything impassable cost
infinitely, so an area flows round a lake, stops at the coast and the map's
edge, and reaches further across open plains than through hills.

**The budget comes from town power**, on the square-root curve town width has
always used: the weakest town reaches ``base`` cells, the strongest ``top``,
and everything in between sits on ``sqrt(power / strongest)``. The root is why
one prolific person's area cannot swallow the map.

**Areas may overlap** (decided 10 Oct 2026): each town's area is its own set of
cells, computed alone. Nothing is ever taken away from a town by a neighbour.

Everything here is pure: a cost function in, a set of cells and SVG paths out.
The orchestration (reading the grid, the decor, the standings) lives in
``web/dodoland/influence_api.py``.
"""

from __future__ import annotations

import heapq
import math
from typing import Callable, Iterable, Optional

from helpers.dodoland import terrainart

DIAGONAL = math.sqrt(2.0)
# A hard ceiling on cells per area, so a mis-set budget cannot make one request
# flood a whole continent cell by cell.
MAX_CELLS = 400_000


def reach(power: float, strongest: float, base: float, top: float) -> float:
    """The growth budget, in cells of open ground, for a town of ``power``."""
    if strongest <= 0 or power <= 0:
        return float(base)
    return float(base) + (float(top) - float(base)) * min(1.0, (power / strongest) ** 0.5)


def grow(origin: tuple[int, int], budget: float, cost: Callable[[int, int], Optional[float]],
         width: int, height: int) -> set[tuple[int, int]]:
    """Every cell reachable from ``origin`` for at most ``budget``.

    ``cost(x, y)`` is what it costs to grow onto a cell, or ``None`` for never.
    Eight neighbours, diagonals at root-two, so open ground grows round rather
    than diamond-shaped. The origin is always included: a town stands on its
    own plot even if that cell is awkward.
    """
    ox, oy = int(origin[0]), int(origin[1])
    if not (0 <= ox < width and 0 <= oy < height):
        return set()
    best = {(ox, oy): 0.0}
    queue = [(0.0, ox, oy)]
    done: set[tuple[int, int]] = set()
    while queue and len(done) < MAX_CELLS:
        spent, x, y = heapq.heappop(queue)
        if (x, y) in done:
            continue
        done.add((x, y))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height) or (nx, ny) in done:
                continue
            step = cost(nx, ny)
            if step is None:
                continue
            total = spent + step * (DIAGONAL if dx and dy else 1.0)
            if total <= budget and total < best.get((nx, ny), math.inf):
                best[(nx, ny)] = total
                heapq.heappush(queue, (total, nx, ny))
    return done


def _bounds(cells: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = zip(*cells)
    return min(xs), min(ys), max(xs), max(ys)


def fill_path(cells: set[tuple[int, int]]) -> str:
    """The area as one SVG path of merged rectangles, in cell units."""
    if not cells:
        return ""
    x0, y0, x1, y1 = _bounds(cells)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    mask = [1 if (x0 + i % w, y0 + i // w) in cells else 0 for i in range(w * h)]
    return "".join(f"M{x + x0} {y + y0}h{rw}v{rh}h{-rw}z"
                   for x, y, rw, rh, _ in terrainart.rects(mask, w, h, skip=(0,)))


def outline_path(cells: set[tuple[int, int]]) -> str:
    """The area's border: every cell edge with outside on one side, joined into
    runs so a long straight border is one segment rather than a hundred."""
    if not cells:
        return ""
    horizontal: dict[int, list[int]] = {}
    vertical: dict[int, list[int]] = {}
    for x, y in cells:
        if (x, y - 1) not in cells:
            horizontal.setdefault(y, []).append(x)
        if (x, y + 1) not in cells:
            horizontal.setdefault(y + 1, []).append(x)
        if (x - 1, y) not in cells:
            vertical.setdefault(x, []).append(y)
        if (x + 1, y) not in cells:
            vertical.setdefault(x + 1, []).append(y)
    out = []
    for y, xs in horizontal.items():
        for start, length in _runs(xs):
            out.append(f"M{start} {y}h{length}")
    for x, ys in vertical.items():
        for start, length in _runs(ys):
            out.append(f"M{x} {start}v{length}")
    return "".join(out)


def _runs(values: list[int]) -> list[tuple[int, int]]:
    values = sorted(set(values))
    runs, start, prev = [], values[0], values[0]
    for v in values[1:]:
        if v != prev + 1:
            runs.append((start, prev - start + 1))
            start = v
        prev = v
    runs.append((start, prev - start + 1))
    return runs
