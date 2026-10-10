"""
Roads between towns that have something to do with each other.

Layer 2 of the new map: nobody draws roads, the bot does. Two placed towns get
a road when their people talk to each other — the **pair rows** (who replied
to, mentioned, sat in voice with whom) — and each town keeps only its
**strongest few** connections (decided 10 Oct 2026), so a map of a busy server
is a network rather than a hairball.

**How a road finds its way.** A* over the terrain grid, on a coarser copy of it
(``grid`` cells to a step) so a cross-continent road is a second of work, not a
minute:

* open ground costs its kind's ``move`` (1 for every passable tile);
* water a town may spread over (shallows, rivers, lakes) can be crossed at
  ``bridge`` per step — so roads cross a river where it is narrow, and the
  crossing is drawn as a bridge;
* deep sea, mountains and anything else with no ``move`` are impassable, and
  so are the footprints of placed pieces whose tile blocks roads;
* ground that already carries a road costs ``reuse`` times as much, so roads
  routed later run along earlier ones and the result merges into a network.

The strongest connections are routed first, so the main roads are the ones the
others join. A path is then straightened (string-pulled where the straight line
is no dearer) and rounded for drawing.

Pure: arrays and lists in, polylines out. The orchestration lives in
``web/dodoland/roads_api.py``.
"""

from __future__ import annotations

import heapq
import math
from typing import Iterable, Optional

SQRT2 = math.sqrt(2.0)
# A hard ceiling on nodes one road may expand, so a road with no way through
# gives up instead of flooding a continent.
MAX_EXPANDED = 600_000


def connections(plots: Iterable, pairs: Iterable[dict], per_town: int,
                minimum: int = 1) -> list[tuple[str, str, int]]:
    """``(a, b, weight)`` for the roads to build, strongest first.

    ``pairs`` are the pair rows (``a``, ``b``, ``n``) over the standing window;
    only pairs whose both people have a placed town count. Each town keeps its
    ``per_town`` heaviest links; a link either end keeps is built.
    """
    placed = {str(p) for p in plots}
    weight: dict[tuple[str, str], int] = {}
    for row in pairs:
        a, b = str(row.get("a") or ""), str(row.get("b") or "")
        if a == b or a not in placed or b not in placed:
            continue
        key = (a, b) if a < b else (b, a)
        weight[key] = weight.get(key, 0) + int(row.get("n") or 1)
    kept: set[tuple[str, str]] = set()
    for town in placed:
        mine = sorted(((w, k) for k, w in weight.items() if town in k and w >= minimum), reverse=True)
        kept.update(k for _, k in mine[:max(0, int(per_town))])
    return sorted(((a, b, weight[(a, b)]) for a, b in kept), key=lambda e: -e[2])


def coarse_costs(cells, kinds: list[dict], step: int, bridge: float, blocked=None):
    """The grid as a cost array at one value per ``step`` x ``step`` block.

    Returns ``(cost, water)``: ``cost`` is float32 with ``inf`` for impassable,
    ``water`` marks blocks crossed as a bridge. A block is impassable if any of
    its cells is (so a mountain's edge is not shaved off), a bridge if any of
    its cells is water (so a three-cell river survives the coarsening), and
    otherwise as dear as its dearest cell.
    """
    import numpy as np

    h, w = cells.shape
    move = np.array([float(k["move"]) if k.get("move") is not None else np.inf for k in kinds] or [np.inf],
                    dtype="float32")
    wet = np.array([bool(k.get("water")) and k.get("grow") is not None for k in kinds] or [False])
    index = np.clip(cells, 0, len(kinds) - 1)
    fine = move[index]
    is_bridge = wet[index]
    fine = np.where(is_bridge, np.float32(bridge), fine)
    if blocked is not None:
        fine = np.where(blocked, np.inf, fine)
    hh, ww = -(-h // step), -(-w // step)
    pad = np.full((hh * step, ww * step), np.inf, dtype="float32")
    pad[:h, :w] = fine
    wpad = np.zeros((hh * step, ww * step), dtype=bool)
    wpad[:h, :w] = is_bridge
    blocks = pad.reshape(hh, step, ww, step)
    cost = blocks.max(axis=(1, 3))
    water = wpad.reshape(hh, step, ww, step).any(axis=(1, 3)) & np.isfinite(cost)
    return cost, water


def astar(cost, start: tuple[int, int], goal: tuple[int, int], road=None,
          reuse: float = 1.0) -> Optional[list[tuple[int, int]]]:
    """The cheapest 8-neighbour path from ``start`` to ``goal`` on ``cost``,
    or ``None``. ``road`` marks blocks already carrying a road, which cost
    ``reuse`` times as much. Diagonal steps cost sqrt(2) times a straight one.
    """
    import numpy as np

    h, w = cost.shape
    sx, sy = start
    gx, gy = goal
    if not (0 <= sx < w and 0 <= sy < h and 0 <= gx < w and 0 <= gy < h):
        return None
    flat = cost.ravel()
    roads = road.ravel() if road is not None else None
    # The cheapest open step, for the heuristic. Not discounted for roads: an
    # estimate that assumes every step could be road (0.35) is admissible but
    # so weak the search floods the continent — a road that should take a
    # second gave up after six. Undiscounted it may pass up a slightly cheaper
    # merge, which nobody can see on a map.
    cheapest = float(np.min(flat[np.isfinite(flat)])) if np.isfinite(flat).any() else 1.0
    start_i, goal_i = sy * w + sx, gy * w + gx
    best = {start_i: 0.0}
    came: dict[int, int] = {}
    queue = [(0.0, 0.0, start_i)]
    expanded = 0
    steps = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2))
    while queue:
        _, spent, here = heapq.heappop(queue)
        if here == goal_i:
            path = [here]
            while here in came:
                here = came[here]
                path.append(here)
            return [(i % w, i // w) for i in reversed(path)]
        if spent > best.get(here, math.inf):
            continue
        expanded += 1
        if expanded > MAX_EXPANDED:
            return None
        x, y = here % w, here // w
        for dx, dy, length in steps:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            c = flat[ni]
            # The two endpoints are a town hall's own block: always enterable.
            if not math.isfinite(c):
                if ni != goal_i:
                    continue
                c = 1.0
            if roads is not None and roads[ni]:
                c *= reuse
            total = spent + c * length
            if total < best.get(ni, math.inf):
                best[ni] = total
                came[ni] = here
                ddx, ddy = abs(gx - nx), abs(gy - ny)
                guess = (max(ddx, ddy) + (SQRT2 - 1) * min(ddx, ddy)) * cheapest
                heapq.heappush(queue, (total + guess, total, ni))
    return None


def regions(cost):
    """The open blocks as an image for :func:`same_region`: Pillow's flood fill
    is C speed with no scipy, so a road between towns on different islands is
    refused at once instead of being searched for until the search gives up.
    (A copy: an image made straight from an array ignores a flood fill.)"""
    import numpy as np
    from PIL import Image

    return Image.fromarray((np.isfinite(cost) * 255).astype("uint8")).copy()


def same_region(image, start: tuple[int, int], goal: tuple[int, int]) -> bool:
    """Whether ``goal`` is reachable from ``start`` on the open-block image."""
    from PIL import ImageDraw

    probe = image.copy()
    w, h = probe.size
    for x, y in (start, goal):
        if not (0 <= x < w and 0 <= y < h):
            return False
    # The endpoints are town halls: count them as open even on a blocked block.
    probe.putpixel(start, 255)
    probe.putpixel(goal, 255)
    ImageDraw.floodfill(probe, start, 128)
    return probe.getpixel(goal) == 128


def _line(x0: int, y0: int, x1: int, y1: int):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def straighten(path: list[tuple[int, int]], cost, water) -> list[tuple[int, int]]:
    """Drop the corners a grid path is made of where the straight line between
    two kept points crosses nothing dearer and keeps to the same side of a
    river — so a road across a plain is a line, not a staircase, and a bridge
    stays where the search put it."""
    import math as _m

    if len(path) < 3:
        return path
    out = [path[0]]
    i = 0
    while i < len(path) - 1:
        # A window, not the whole rest of the path: looking from every point to
        # every later one was quadratic, twelve seconds for one long road.
        j = min(len(path) - 1, i + 80)
        while j > i + 1:
            (ax, ay), (bx, by) = path[i], path[j]
            ok = True
            for x, y in _line(ax, ay, bx, by):
                c = cost[y, x]
                if not _m.isfinite(c) or c > 1.0 or water[y, x]:
                    ok = False
                    break
            if ok:
                break
            j -= 1
        out.append(path[j])
        i = j
    return out


def smooth(points: list[tuple[float, float]], rounds: int = 2) -> list[tuple[float, float]]:
    """Chaikin corner-cutting that keeps the two ends where they are."""
    for _ in range(rounds):
        if len(points) < 3:
            return points
        out = [points[0]]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            out.append((ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25))
            out.append((ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75))
        out.append(points[-1])
        points = out
    return points


def spans(path: list[tuple[int, int]], water) -> list[tuple[int, int]]:
    """Index ranges ``(i, j)`` of a path that run over water: its bridges."""
    out, start = [], None
    for i, (x, y) in enumerate(path):
        if water[y, x] and start is None:
            start = i
        elif not water[y, x] and start is not None:
            out.append((max(0, start - 1), i))
            start = None
    if start is not None:
        out.append((max(0, start - 1), len(path) - 1))
    return out
