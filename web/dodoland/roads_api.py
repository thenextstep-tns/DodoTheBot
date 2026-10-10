"""
The map's roads, for the Roads layer: worked out by the bot, never drawn by hand.

Reads the placed towns, who talks to whom (the pair rows over the standing
window), the terrain and the pieces that block a road, and hands them to
``helpers.dodoland.roads``. The answer is cached per guild and thrown away when
anything it was made from changes — the terrain version, the plots, the
blocking pieces, the settings — and at least once a day, because the pair rows
behind it move every day.
"""

from __future__ import annotations

import asyncio
import datetime
import time

from aiohttp import web

from helpers.dodoland import roads
from helpers.dodoland import standing
from helpers.dodoland import store as store_module
from helpers.dodoland import terrain as T

# guild -> (key, built_at, payload)
_CACHE: dict[int, tuple] = {}
_TTL = 6 * 3600
_PARAMS = ("dodoland_roads_on", "dodoland_roads_per_town", "dodoland_roads_min",
           "dodoland_roads_bridge", "dodoland_roads_reuse", "dodoland_roads_step",
           "dodoland_roads_width", "dodoland_window_days")


def _key(bot, guild) -> tuple:
    from web.dodoland import terrain_api

    tiles = bot.dodoland_tiles.tiles(guild.id)
    blocking = {t["tile_id"] for t in tiles if not t["passable"]}
    params = bot.dodoland_params
    return (terrain_api.version(guild.id),
            tuple(sorted((k, tuple(sorted(v.items()))) for k, v in bot.dodoland_buildings.plots(guild.id).items())),
            tuple(sorted((str(p.get("piece_id")), p.get("x"), p.get("y"), p.get("scale"))
                         for p in bot.dodoland_decor.world(guild.id) if p.get("asset_id") in blocking)),
            tuple(params.get(guild.id, k) for k in _PARAMS),
            datetime.date.today().isoformat())


def compute(bot, guild) -> dict:
    """Every road on the map. Blocking: a few seconds for a busy continent."""
    import numpy as np

    from helpers.dodoland import terrain_raster
    from web.dodoland import influence_api

    params = bot.dodoland_params
    width = float(params.get(guild.id, "dodoland_roads_width"))
    world = bot.dodoland_terrain.world(guild.id)
    cells_w, cells_h = world["cells_w"], world["cells_h"]
    plots = bot.dodoland_buildings.plots(guild.id)
    empty = {"roads": [], "width": width, "cells_w": cells_w, "cells_h": cells_h}
    if not cells_w or len(plots) < 2 or not bool(params.get(guild.id, "dodoland_roads_on")):
        return empty

    since = store_module.days_back(int(params.get(guild.id, "dodoland_window_days")))
    _, pairs = standing.recent_rows(bot.dodoland, params, guild.id, since)
    edges = roads.connections(plots, pairs, int(params.get(guild.id, "dodoland_roads_per_town")),
                              int(params.get(guild.id, "dodoland_roads_min")))
    if not edges:
        return empty

    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    chunks = bot.dodoland_terrain.chunks(guild.id, [(x, y) for y in range(cys) for x in range(cxs)])
    cells = terrain_raster.grid(chunks, cells_w, cells_h)
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild.id)}
    kinds = T.sync_tile_kinds(world["kinds"], tiles)
    blocked = np.zeros((cells_h, cells_w), dtype=bool)
    for x, y in influence_api._blocked(bot, guild.id, cells_w, cells_h, flag="passable"):
        blocked[y, x] = True

    step = max(1, int(params.get(guild.id, "dodoland_roads_step")))
    cost, water = roads.coarse_costs(cells, kinds, step, float(params.get(guild.id, "dodoland_roads_bridge")),
                                     blocked)
    carried = np.zeros(cost.shape, dtype=bool)
    reuse = float(params.get(guild.id, "dodoland_roads_reuse"))
    half = step / 2.0

    def block_of(uid) -> tuple[int, int]:
        plot = plots[int(uid)]
        return (min(cost.shape[1] - 1, int(float(plot.get("x", 50)) / 100 * cells_w) // step),
                min(cost.shape[0] - 1, int(float(plot.get("y", 50)) / 100 * cells_h) // step))

    def svg(points) -> str:
        return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points)

    open_image = roads.regions(cost)
    out = []
    for a, b, weight in edges:
        if not roads.same_region(open_image, block_of(a), block_of(b)):
            continue   # across open sea or mountains: no road can join them
        path = roads.astar(cost, block_of(a), block_of(b), carried, reuse)
        if not path:
            continue
        for x, y in path:
            carried[y, x] = True
        line = roads.straighten(path, cost, water)
        points = roads.smooth([(x * step + half, y * step + half) for x, y in line])
        bridges = [svg([(x * step + half, y * step + half) for x, y in path[i:j + 1]])
                   for i, j in roads.spans(path, water)]
        out.append({"a": a, "b": b, "weight": weight, "d": svg(points), "bridges": bridges})
    return {"roads": out, "width": width, "cells_w": cells_w, "cells_h": cells_h}


def current(bot, guild) -> dict:
    """The payload, cached until something it was made from changes. Blocking."""
    key = _key(bot, guild)
    cached = _CACHE.get(guild.id)
    if not cached or cached[0] != key or time.time() - cached[1] > _TTL:
        _CACHE[guild.id] = (key, time.time(), compute(bot, guild))
        cached = _CACHE[guild.id]
    return cached[2]


async def roads_layer(request: web.Request):
    """``GET /guild/{gid}/dodoland/roads`` — the Roads layer's data."""
    bot, guild = request.app["bot"], request["guild"]
    payload = await asyncio.get_running_loop().run_in_executor(None, current, bot, guild)
    return web.json_response({"ok": True, **payload})
