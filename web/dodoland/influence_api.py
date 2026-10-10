"""
Every placed town's area of influence, for the map's Influence layer.

Reads the terrain grid, the placed features that block growth, the plots and the
standings, and hands each town's area to ``helpers.dodoland.influence``. The
answer is cached per guild and thrown away when anything it was made from
changes: the terrain version, the world's pieces, the plots or the settings.
"""

from __future__ import annotations

import asyncio
import time

from aiohttp import web

from helpers.dodoland import influence
from helpers.dodoland import standing
from helpers.dodoland import store as store_module
from helpers.dodoland import terrain as T
from helpers.dodoland import townart

# guild -> (key, built_at, payload)
_CACHE: dict[int, tuple] = {}
# guild -> {town id: set of cells}, made alongside the payload. What "is this
# inside that town's area" is asked of when a building is placed.
_CELLS: dict[int, dict[str, set]] = {}
_TTL = 300


def _blocked(bot, guild_id: int, cells_w: int, cells_h: int, flag: str = "spreads") -> set:
    """Cells under placed features whose tile says no to ``flag`` — for a
    town's area ``spreads`` (a mountain range, a pond), for a road ``passable``
    (those, and every building: a road goes round a house). Their footprint is
    the lower part of the drawing, where it stands on the ground."""
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild_id)}
    pieces = [p for p in bot.dodoland_decor.world(guild_id)
              if (tiles.get(p["asset_id"]) or {}).get(flag) is False]
    sizes = bot.dodoland_tiles.art_sizes(
        p.get("variant") or tiles[p["asset_id"]]["variants"][0] for p in pieces
        if tiles[p["asset_id"]]["variants"])
    shrink = max(0.1, float(bot.dodoland_params.get(guild_id, "dodoland_tile_scale")))
    out = set()
    for p in pieces:
        tile = tiles[p["asset_id"]]
        vid = p.get("variant") or (tile["variants"][0] if tile["variants"] else "")
        w, h = sizes.get(vid, (0, 0))
        if not w:
            continue
        wc = w / tile["cell_px"] / shrink * float(p.get("scale", 1))
        hc = wc * h / w
        cx, cy = p["x"] / 100 * cells_w, p["y"] / 100 * cells_h
        # The anchor is 85% down the drawing; the footprint is its bottom 40%.
        top, bottom = cy - hc * 0.25, cy + hc * 0.15
        for y in range(int(top), int(bottom) + 1):
            for x in range(int(cx - wc * 0.45), int(cx + wc * 0.45) + 1):
                if 0 <= x < cells_w and 0 <= y < cells_h:
                    out.add((x, y))
    return out


def compute(bot, guild) -> dict:
    """The payload: one entry per placed town."""
    params = bot.dodoland_params
    world = bot.dodoland_terrain.world(guild.id)
    cells_w, cells_h = world["cells_w"], world["cells_h"]
    plots = bot.dodoland_buildings.plots(guild.id)
    if not cells_w or not plots:
        return {"towns": [], "cells_w": cells_w, "cells_h": cells_h}
    base = float(params.get(guild.id, "dodoland_influence_base"))
    top = max(base, float(params.get(guild.id, "dodoland_influence_top")))
    clears = bool(params.get(guild.id, "dodoland_influence_clear_forest"))
    water_cost = max(0.1, float(params.get(guild.id, "dodoland_influence_water_cost")))

    since = store_module.days_back(int(params.get(guild.id, "dodoland_window_days")))
    rows, pairs = standing.recent_rows(bot.dodoland, params, guild.id, since)
    result = standing.guild_standings(bot.dodoland, params, guild.id,
                                      bot.dodoland_buildings.buildings(guild.id), since=since,
                                      rows=rows, pair_rows=pairs)
    strongest = max((p["power"] for p in result["order"]), default=0)

    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    chunks = bot.dodoland_terrain.chunks(guild.id, [(x, y) for y in range(cys) for x in range(cxs)])
    # Re-read from the tiles as they are now, so ticking "influence spreads"
    # on a tile changes every area at once, without a repaint.
    kinds = T.sync_tile_kinds(world["kinds"], {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild.id)})
    grow_cost = [T.grow_cost(k, clears_forest=clears) for k in kinds]
    # Water the tile lets a town spread over (shallows) costs more than land.
    grow_cost = [c * water_cost if c is not None and k.get("water") else c
                 for c, k in zip(grow_cost, kinds)]
    blocked = _blocked(bot, guild.id, cells_w, cells_h)

    def cost(x, y):
        if (x, y) in blocked:
            return None
        value = chunks[(x // T.CHUNK, y // T.CHUNK)][(y % T.CHUNK) * T.CHUNK + (x % T.CHUNK)]
        return grow_cost[value] if 0 <= value < len(grow_cost) else None

    towns = []
    areas: dict[str, set] = {}
    for uid, plot in plots.items():
        person = result["people"].get(int(uid))
        power = person["power"] if person else 0
        budget = influence.reach(power, strongest, base, top)
        origin = (int(float(plot.get("x", 50)) / 100 * cells_w),
                  int(float(plot.get("y", 50)) / 100 * cells_h))
        cells = influence.grow(origin, budget, cost, cells_w, cells_h)
        areas[str(uid)] = cells
        towns.append({"id": str(uid), "colour": townart.colour_for(str(uid)),
                      "reach": round(budget, 1), "cells": len(cells),
                      "fill": influence.fill_path(cells), "line": influence.outline_path(cells),
                      # The border smoothed: the area's line, and where walls go.
                      "ring": influence.ring_path(cells)})
    _CELLS[guild.id] = areas
    return {"towns": towns, "cells_w": cells_w, "cells_h": cells_h}


def _key(bot, guild) -> tuple:
    from web.dodoland import terrain_api

    params = bot.dodoland_params
    tiles = bot.dodoland_tiles.tiles(guild.id)
    spreading = tuple(sorted(t["tile_id"] for t in tiles if t["spreads"]))
    # Where every *blocking* piece stands: moving a mountain range changes who
    # it blocks without changing the count, and a passable flower bed changes
    # nothing — so it must not throw a second of work away either.
    blocking = {t["tile_id"] for t in tiles if not t["spreads"]}
    return (terrain_api.version(guild.id), spreading,
            tuple(sorted((str(p.get("piece_id")), p.get("x"), p.get("y"), p.get("scale"))
                         for p in bot.dodoland_decor.world(guild.id)
                         if p.get("asset_id") in blocking)),
            tuple(sorted((k, tuple(sorted(v.items()))) for k, v in bot.dodoland_buildings.plots(guild.id).items())),
            tuple(params.get(guild.id, k) for k in ("dodoland_influence_base", "dodoland_influence_top",
                                                    "dodoland_influence_clear_forest",
                                                    "dodoland_influence_water_cost")))


def current(bot, guild) -> dict:
    """The payload, from the cache when nothing it was made from has changed.
    Blocking."""
    key = _key(bot, guild)
    cached = _CACHE.get(guild.id)
    if not cached or cached[0] != key or time.time() - cached[1] > _TTL or guild.id not in _CELLS:
        _CACHE[guild.id] = (key, time.time(), compute(bot, guild))
        cached = _CACHE[guild.id]
    return cached[2]


def warm(bot, guild) -> None:
    """Work the areas out ahead of the first visitor. Blocking."""
    current(bot, guild)


def inside(bot, guild, town_id, x_pct: float, y_pct: float) -> bool:
    """Whether a map position (percentages, as pieces are stored) lies in that
    town's area. A town with no area — not placed — contains nothing."""
    payload = current(bot, guild)
    cells = _CELLS.get(guild.id, {}).get(str(town_id))
    if not cells:
        return False
    x = int(float(x_pct) / 100 * payload["cells_w"])
    y = int(float(y_pct) / 100 * payload["cells_h"])
    return (x, y) in cells


async def influence_layer(request: web.Request):
    """``GET /guild/{gid}/dodoland/influence`` — the Influence layer's data."""
    bot, guild = request.app["bot"], request["guild"]
    payload = await asyncio.get_running_loop().run_in_executor(None, current, bot, guild)
    return web.json_response({"ok": True, **payload})
