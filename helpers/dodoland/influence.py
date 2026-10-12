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


def grow_grid(origin: tuple[int, int], budget: float, costs: list, width: int,
              height: int) -> set[tuple[int, int]]:
    """``grow`` over a flat cost list instead of a cost function — the same
    search, several times faster, for a whole map of towns at once.

    ``costs[y * width + x]`` is what growing onto a cell costs; ``math.inf``
    for never (an infinite step is over any budget, so it needs no check).
    """
    ox, oy = int(origin[0]), int(origin[1])
    if not (0 <= ox < width and 0 <= oy < height):
        return set()
    n, last = width * height, width - 1
    d = DIAGONAL
    middle = ((1, 1.0), (-1, 1.0), (width, 1.0), (-width, 1.0),
              (width + 1, d), (width - 1, d), (-width + 1, d), (-width - 1, d))
    # Along the map's left and right edges a step sideways would wrap a row.
    left = tuple(s for s in middle if s[0] not in (-1, width - 1, -width - 1))
    right = tuple(s for s in middle if s[0] not in (1, width + 1, -width + 1))
    start = oy * width + ox
    best = {start: 0.0}
    queue = [(0.0, start)]
    done: set[int] = set()
    pop, push, get = heapq.heappop, heapq.heappush, best.get
    inf = math.inf
    while queue and len(done) < MAX_CELLS:
        spent, i = pop(queue)
        if i in done:
            continue
        done.add(i)
        x = i % width
        for off, mul in (left if x == 0 else right if x == last else middle):
            j = i + off
            if j < 0 or j >= n or j in done:
                continue
            total = spent + costs[j] * mul
            if total <= budget and total < get(j, inf):
                best[j] = total
                push(queue, (total, j))
    return {(i % width, i // width) for i in done}


def _mask(cells: set[tuple[int, int]]):
    """The cells as a boolean array over their bounding box, with its corner."""
    import numpy as np

    xy = np.fromiter((v for c in cells for v in c), dtype=np.int64, count=2 * len(cells)).reshape(-1, 2)
    x0, y0 = int(xy[:, 0].min()), int(xy[:, 1].min())
    mask = np.zeros((int(xy[:, 1].max()) - y0 + 1, int(xy[:, 0].max()) - x0 + 1), dtype=bool)
    mask[xy[:, 1] - y0, xy[:, 0] - x0] = True
    return mask, x0, y0


def _bounds(cells: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = zip(*cells)
    return min(xs), min(ys), max(xs), max(ys)


def fill_path(cells: set[tuple[int, int]]) -> str:
    """The area as one SVG path of merged rectangles, in cell units."""
    if not cells:
        return ""
    import numpy as np

    # Each row's runs, and a run carried down for as long as the rows below
    # have exactly the same one: rectangles that cover the area, in numpy
    # rather than cell by cell (an area can be hundreds of thousands).
    mask, x0, y0 = _mask(cells)
    edges = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    rows_s, starts = np.nonzero(edges == 1)
    ends = np.nonzero(edges == -1)[1]
    by_row: dict[int, list[tuple[int, int]]] = {}
    for r, s, e in zip(rows_s.tolist(), starts.tolist(), ends.tolist()):
        by_row.setdefault(r, []).append((s, e))
    out, opened = [], {}
    for r in range(mask.shape[0] + 1):
        runs = set(by_row.get(r, ()))
        for run in [k for k in opened if k not in runs]:
            top = opened.pop(run)
            out.append(f"M{run[0] + x0} {top + y0}h{run[1] - run[0]}v{r - top}h{run[0] - run[1]}z")
        for run in by_row.get(r, ()):
            opened.setdefault(run, r)
    return "".join(out)


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


def loops(cells: set[tuple[int, int]]) -> list[list[tuple[float, float]]]:
    """The area's border as closed loops of corner points, in cell units.

    Every cell edge with outside beyond it is a directed segment, oriented so
    the area is always on the same side; following them end to start walks each
    border once, holes included. Only the corners are kept, where a loop turns.
    """
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = {}
    if not cells:
        return []
    import numpy as np

    # The border edges found in numpy (an area is often 100,000s of cells, its
    # border a few thousand edges); only those are walked in Python.
    mask, x0, y0 = _mask(cells)
    pad = np.pad(mask, 1)
    inner = pad[1:-1, 1:-1]
    for side, (dx0, dy0, dx1, dy1) in (
            (~pad[:-2, 1:-1], (0, 0, 1, 0)),     # nothing above: the top edge
            (~pad[1:-1, 2:], (1, 0, 1, 1)),      # nothing right
            (~pad[2:, 1:-1], (1, 1, 0, 1)),      # nothing below
            (~pad[1:-1, :-2], (0, 1, 0, 0))):    # nothing left
        ys, xs = np.nonzero(inner & side)
        for x, y in zip((xs + x0).tolist(), (ys + y0).tolist()):
            nxt.setdefault((x + dx0, y + dy0), []).append((x + dx1, y + dy1))
    out = []
    while nxt:
        start = next(iter(nxt))
        loop, here = [start], start
        while True:
            ways = nxt.get(here)
            if not ways:
                break
            step = ways.pop()
            if not ways:
                del nxt[here]
            if step == start:
                break
            loop.append(step)
            here = step
        corners = [p for i, p in enumerate(loop)
                   if (p[0] - loop[i - 1][0], p[1] - loop[i - 1][1])
                   != (loop[(i + 1) % len(loop)][0] - p[0], loop[(i + 1) % len(loop)][1] - p[1])]
        if len(corners) >= 3:
            out.append(corners)
    return out


def _edge_cells(a: tuple[int, int], b: tuple[int, int]):
    """The cell inside and the cell outside a directed border edge (as
    :func:`loops` orients them: the area on the walker's right)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 1:      # a top edge
        return (a[0], a[1]), (a[0], a[1] - 1)
    if dy == 1:      # a right edge
        return (a[0] - 1, a[1]), (a[0], a[1])
    if dx == -1:     # a bottom edge
        return (b[0], a[1] - 1), (b[0], a[1])
    return (a[0], b[1]), (a[0] - 1, b[1])   # a left edge


def wall_runs(region: set[tuple[int, int]], style_of: Callable[[tuple[int, int]], str],
              open_beyond: Callable[[tuple[int, int]], bool], *, rounds: int = 2,
              min_edges: int = 3) -> list[tuple[str, list[tuple[float, float]]]]:
    """Where walls stand round a walled territory: ``[(style, points), ...]``.

    ``region`` is every walled town's land, as one territory, so where two
    walled areas overlap the wall runs only round the outside of both and
    nowhere through the middle. Each border edge is walled in the style of the
    town whose land is inside it (``style_of``), unless what is beyond it is
    open (``open_beyond``: water, or off the map), where the wall stops — it
    meets the shore and leaves the water open. Runs are smoothed like the
    area's own line, their ends kept where they are.
    """
    if not region:
        return []
    import numpy as np

    mask, x0, y0 = _mask(region)
    pad = np.pad(mask, 1)
    inner = pad[1:-1, 1:-1]
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for side, (dx0, dy0, dx1, dy1) in (
            (~pad[:-2, 1:-1], (0, 0, 1, 0)),
            (~pad[1:-1, 2:], (1, 0, 1, 1)),
            (~pad[2:, 1:-1], (1, 1, 0, 1)),
            (~pad[1:-1, :-2], (0, 1, 0, 0))):
        ys, xs = np.nonzero(inner & side)
        for x, y in zip((xs + x0).tolist(), (ys + y0).tolist()):
            nxt.setdefault((x + dx0, y + dy0), []).append((x + dx1, y + dy1))
    out = []
    while nxt:
        start = next(iter(nxt))
        loop, here = [start], start
        while True:
            ways = nxt.get(here)
            if not ways:
                break
            step = ways.pop()
            if not ways:
                del nxt[here]
            if step == start:
                break
            loop.append(step)
            here = step
        n = len(loop)
        if n < 4:
            continue
        # The style of every edge of this loop ("" where it is open).
        styles = []
        for i in range(n):
            inside, outside = _edge_cells(loop[i], loop[(i + 1) % n])
            styles.append("" if open_beyond(outside) else (style_of(inside) or ""))
        if not any(styles):
            continue
        # Start the walk where the style changes, so no run is cut in two by
        # where the loop happened to begin.
        first = next((i for i in range(n) if styles[i] != styles[i - 1]), 0)
        run, kind = [], None
        for k in range(n + 1):
            i = (first + k) % n
            style = styles[i] if k < n else None
            if style != kind:
                if kind and len(run) - 1 >= min_edges:
                    out.append((kind, _open_smooth(run, rounds)))
                run, kind = [loop[i]], style
            if k < n:
                run.append(loop[(i + 1) % n])
    return out


def _open_smooth(points: list[tuple[int, int]], rounds: int) -> list[tuple[float, float]]:
    """An open run rounded like :func:`_chaikin`, its two ends kept."""
    corners = [points[0]] + [p for i, p in enumerate(points[1:-1], 1)
                             if (p[0] - points[i - 1][0], p[1] - points[i - 1][1])
                             != (points[i + 1][0] - p[0], points[i + 1][1] - p[1])] + [points[-1]]
    pts = [(float(x), float(y)) for x, y in corners]
    for _ in range(rounds):
        if len(pts) < 3:
            break
        smooth = [pts[0]]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            smooth.append((ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25))
            smooth.append((ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75))
        smooth.append(pts[-1])
        pts = smooth
    return pts


def _chaikin(points: list[tuple[float, float]], rounds: int) -> list[tuple[float, float]]:
    for _ in range(rounds):
        smooth = []
        for i, (ax, ay) in enumerate(points):
            bx, by = points[(i + 1) % len(points)]
            smooth.append((ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25))
            smooth.append((ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75))
        points = smooth
    return points


def ring_path(cells: set[tuple[int, int]], *, rounds: int = 2, min_loop: int = 12) -> str:
    """The border smoothed into curves, for walls and for the area's line.

    The stair-step of cell edges, rounded by a few passes of Chaikin's corner
    cutting: at map scale a stepped diagonal becomes a straight one and a
    stepped curve a curve. Loops shorter than ``min_loop`` corners (a stray
    cell, a pinhole) are left out — nobody builds a wall round one cell.
    """
    parts = []
    for loop in loops(cells):
        if len(loop) < min_loop:
            continue
        smooth = _chaikin(loop, rounds)
        parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in smooth) + "Z")
    return "".join(parts)
