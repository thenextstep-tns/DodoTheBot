"""
Real members travelling between towns, and the way they go.

Who: one traveller per settled person (the busiest first, up to
``dodoland_travellers``), touring the towns of the people they talk to most
(the pair rows over the standing window; ``dodoland_travel_stops`` of them,
else the nearest towns): home, one town, the next, ..., home, round and round.

The way: over the terrain, never through the sea, avoiding water (a river is
crossed only where there is no way round: ``dodoland_travel_water_cost``) and
keeping to paths and roads where it can (ground whose kind's name has one of
``dodoland_travel_path_words`` costs ``dodoland_travel_path_cost`` of open
ground). The same coarse grid and A* the Roads layer uses
(``helpers.dodoland.roads``). Routes are cached until the terrain, the towns,
the settings or the day change, and at least every hour - not on every paint
stroke, as working them out takes seconds.

``GET /guild/{gid}/dodoland/travel`` (and the member's reader): ``{tours:
[{w: traveller, stops: [town ids, from their own]}], routes: {"a|b": path in
cells from a's town to b's, a < b}}``.
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


def tours(bot, guild) -> list[tuple[str, list[str]]]:
    """``[(traveller, [their town, stop, stop, ...])]``: one traveller per
    settled person (up to ``dodoland_travellers``), each touring round the
    towns of the people they talk to most (up to ``dodoland_travel_stops``;
    with nobody, the nearest towns) and home again, round and round. Blocking."""
    params = bot.dodoland_params
    most = max(0, int(params.get(guild.id, "dodoland_travellers")))
    stops = max(1, int(params.get(guild.id, "dodoland_travel_stops")))
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
    busy = {}
    for (a, b), n in talk.items():
        busy[a] = busy.get(a, 0) + n
        busy[b] = busy.get(b, 0) + n
    out = []
    for who in sorted(plots, key=lambda u: -busy.get(u, 0))[:most]:
        friends = sorted(((n, b if a == who else a) for (a, b), n in talk.items() if who in (a, b)), reverse=True)
        visit = [u for _, u in friends][:stops]
        if not visit:
            me = plots[who]
            visit = sorted((u for u in plots if u != who),
                           key=lambda u: (plots[u]["x"] - me["x"]) ** 2 + (plots[u]["y"] - me["y"]) ** 2)[:min(2, stops)]
        out.append((who, [who] + visit))
    return out


def travel(bot, guild) -> dict:
    """``{tours: [{w, stops}], routes: {"a|b": path}}``: who tours where, and
    the way between each two towns next to each other on a tour. A tour goes
    out through its stops and back the same way (home, A, B, C, B, A, home,
    ...); a town no way leads to is left out. Blocking; routes are cached."""
    key = _key(bot, guild)
    routes, out = {}, []

    def leg(a, b) -> bool:
        lo, hi = sorted((a, b))
        name = f"{lo}|{hi}"
        if name not in routes:
            points = _route(bot, guild, key, lo, hi)
            routes[name] = ("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points)) if points and len(points) >= 2 else ""
        return bool(routes[name])
    for who, stops in tours(bot, guild):
        kept = [stops[0]]
        for town in stops[1:]:
            if leg(kept[-1], town):
                kept.append(town)
        if len(kept) >= 2:
            out.append({"w": who, "stops": kept})
    return {"tours": out, "routes": {k: v for k, v in routes.items() if v}}


# guild -> (key, payload); and which guilds are being worked out right now.
_LAST: dict = {}
_BUSY: set = set()


def current(bot, guild) -> dict:
    """The tours, never waiting on a recalculation once there is one: an old
    answer is served while a fresh one is worked out in the background
    (routes take seconds). Blocking only the very first time."""
    import threading

    key = _key(bot, guild)
    hit = _LAST.get(guild.id)
    if hit and hit[0] == key:
        return hit[1]
    if hit:
        if guild.id not in _BUSY:
            _BUSY.add(guild.id)

            def refresh():
                try:
                    _LAST[guild.id] = (key, travel(bot, guild))
                finally:
                    _BUSY.discard(guild.id)
            threading.Thread(target=refresh, name="dodoland-travel", daemon=True).start()
        return hit[1]
    payload = travel(bot, guild)
    _LAST[guild.id] = (key, payload)
    return payload


async def travel_layer(request: web.Request):
    """``GET .../dodoland/travel``: who tours where, and the ways between."""
    bot, guild = request.app["bot"], request["guild"]
    payload = await asyncio.get_running_loop().run_in_executor(None, current, bot, guild)
    return web.json_response({"ok": True, **payload})
