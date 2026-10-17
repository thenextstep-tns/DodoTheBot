"""
Real members travelling between towns, and the way they go.

Who: the people whose towns talk most (the pair rows over the standing window),
one traveller per person - each pair sends whichever of the two is not
already out - up to ``dodoland_travellers``, and always the viewer's own: to
whoever they talk to most, else the nearest town.

The way: over the terrain, never through the sea, avoiding water (a river is
crossed only where there is no way round: ``dodoland_travel_water_cost``) and
keeping to paths and roads where it can (ground whose kind's name has one of
``dodoland_travel_path_words`` costs ``dodoland_travel_path_cost`` of open
ground). The same coarse grid and A* the Roads layer uses
(``helpers.dodoland.roads``). Routes are cached until the terrain, the towns,
the settings or the day change, and at least every hour - not on every paint
stroke, as working them out takes seconds.

``GET /guild/{gid}/dodoland/travel`` (and the member's reader): ``{travel:
[{w: walker id, t: destination id, d: path in cells}]}``.
"""

from __future__ import annotations

import asyncio
import datetime
import re
import time

from aiohttp import web

from helpers.dodoland import roads
from helpers.dodoland import standing
from helpers.dodoland import store as store_module
from helpers.dodoland import terrain as T

_PARAMS = ("dodoland_travellers", "dodoland_travel_path_words", "dodoland_travel_path_cost",
           "dodoland_travel_water_cost", "dodoland_roads_step", "dodoland_window_days")
# guild -> (key, grid) and (guild, a, b, key) -> points
_GRID: dict = {}
_ROUTES: dict = {}


def _key(bot, guild) -> tuple:
    params = bot.dodoland_params
    return (int(time.time() // 3600),
            tuple(sorted((k, tuple(sorted(v.items()))) for k, v in bot.dodoland_buildings.plots(guild.id).items())),
            tuple(params.get(guild.id, k) for k in _PARAMS),
            datetime.date.today().isoformat())


def _grid(bot, guild, key):
    """The travel cost grid at the roads' step, and its step. Blocking."""
    hit = _GRID.get(guild.id)
    if hit and hit[0] == key:
        return hit[1]
    import numpy as np

    from helpers.dodoland import terrain_raster

    params = bot.dodoland_params
    world = bot.dodoland_terrain.world(guild.id)
    cells_w, cells_h = world["cells_w"], world["cells_h"]
    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    chunks = bot.dodoland_terrain.chunks(guild.id, [(x, y) for y in range(cys) for x in range(cxs)])
    cells = terrain_raster.grid(chunks, cells_w, cells_h)
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild.id)}
    kinds = T.sync_tile_kinds(world["kinds"], tiles)
    step = max(1, int(params.get(guild.id, "dodoland_roads_step")))
    cost, water = roads.coarse_costs(cells, kinds, step, float(params.get(guild.id, "dodoland_travel_water_cost")))
    # Paths and roads: the share of a block that is one makes it cheaper.
    words = [w.strip().lower() for w in str(params.get(guild.id, "dodoland_travel_path_words") or "").split(",") if w.strip()]
    pattern = re.compile("|".join(re.escape(w) for w in words)) if words else None
    is_path = np.array([bool(pattern and pattern.search(f"{k.get('key', '')} {k.get('label', '')}".lower()))
                        for k in kinds] or [False])
    paths = np.where((cells >= 0) & (cells < len(is_path)), is_path[np.clip(cells, 0, len(is_path) - 1)], False)
    hh, ww = cost.shape
    pad = np.zeros((hh * step, ww * step), dtype=float)
    pad[:paths.shape[0], :paths.shape[1]] = paths[:hh * step, :ww * step]
    share = pad.reshape(hh, step, ww, step).mean(axis=(1, 3))
    cheap = float(params.get(guild.id, "dodoland_travel_path_cost"))
    cost = np.where(np.isfinite(cost), cost * (1 - share * (1 - cheap)), cost).astype("float32")
    grid = (cost, step, cells_w, cells_h)
    _GRID[guild.id] = (key, grid)
    return grid


def _route(bot, guild, key, a: str, b: str):
    """The way from a's town to b's, in cells, or None. Blocking."""
    cached = _ROUTES.get((guild.id, a, b))
    if cached and cached[0] == key:
        return cached[1]
    cost, step, cells_w, cells_h = _grid(bot, guild, key)
    plots = bot.dodoland_buildings.plots(guild.id)

    def block(uid):
        """The town's block, or the nearest open one: a hall can stand on
        ground no traveller walks through."""
        import numpy as np

        plot = plots[int(uid)]
        bx = min(cost.shape[1] - 1, int(float(plot.get("x", 50)) / 100 * cells_w) // step)
        by = min(cost.shape[0] - 1, int(float(plot.get("y", 50)) / 100 * cells_h) // step)
        for r in range(0, 12):
            y0, y1, x0, x1 = max(0, by - r), min(cost.shape[0], by + r + 1), max(0, bx - r), min(cost.shape[1], bx + r + 1)
            open_ = np.argwhere(np.isfinite(cost[y0:y1, x0:x1]))
            if len(open_):
                best = min(open_, key=lambda q: (q[0] + y0 - by) ** 2 + (q[1] + x0 - bx) ** 2)
                return (int(best[1] + x0), int(best[0] + y0))
        return (bx, by)
    # Greedy: a long way over cheap paths is otherwise more than the search allows.
    path = roads.astar(cost, block(a), block(b), greed=2.5)
    if not path:
        # The search gives up after so many steps, and from a town amid
        # cheap paths it can run out going one way and not the other.
        back = roads.astar(cost, block(b), block(a), greed=2.5)
        path = list(reversed(back)) if back else None
    half = step / 2.0
    points = roads.smooth([(x * step + half, y * step + half) for x, y in path]) if path else None
    _ROUTES[(guild.id, a, b)] = (key, points)
    return points


def who_travels(bot, guild, viewer: str) -> list[tuple[str, str]]:
    """``[(walker, destination)]``: one traveller per person. Blocking."""
    params = bot.dodoland_params
    most = max(0, int(params.get(guild.id, "dodoland_travellers")))
    plots = {str(k): v for k, v in bot.dodoland_buildings.plots(guild.id).items()}
    if most <= 0 or len(plots) < 2:
        return []
    since = store_module.days_back(int(params.get(guild.id, "dodoland_window_days")))
    _, pairs = standing.recent_rows(bot.dodoland, params, guild.id, since)
    talk: dict = {}
    for row in pairs:
        a, b = str(row.get("a")), str(row.get("b"))
        if a in plots and b in plots and a != b:
            talk[(a, b)] = talk.get((a, b), 0) + int(row.get("n") or 0)
    ranked = sorted(talk.items(), key=lambda kv: -kv[1])
    out, out_of_town = [], set()

    def send(walker, to):
        out.append((walker, to))
        out_of_town.add(walker)
    # The viewer's own first, so they are always out.
    if viewer in plots:
        mine = next(((a, b) for (a, b), _ in ranked if viewer in (a, b)), None)
        if mine:
            send(viewer, mine[1] if mine[0] == viewer else mine[0])
        else:
            me = plots[viewer]
            near = min((u for u in plots if u != viewer),
                       key=lambda u: (plots[u]["x"] - me["x"]) ** 2 + (plots[u]["y"] - me["y"]) ** 2)
            send(viewer, near)
    for (a, b), _ in ranked:
        if len(out) >= most + (1 if viewer in plots else 0):
            break
        if a not in out_of_town:
            send(a, b)
        elif b not in out_of_town:
            send(b, a)
    return out


def travel(bot, guild, viewer: str) -> dict:
    """The travellers and their ways. Blocking; the routes are cached."""
    key = _key(bot, guild)
    out = []
    for walker, to in who_travels(bot, guild, viewer):
        points = _route(bot, guild, key, walker, to)
        if points and len(points) >= 2:
            out.append({"w": walker, "t": to, "d": "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points)})
    return {"travel": out}


async def travel_layer(request: web.Request):
    """``GET .../dodoland/travel``: who travels, and the way they go."""
    bot, guild = request.app["bot"], request["guild"]
    viewer = str(request.get("uid") or "")
    payload = await asyncio.get_running_loop().run_in_executor(None, travel, bot, guild, viewer)
    return web.json_response({"ok": True, **payload})
