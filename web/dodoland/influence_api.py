"""
Every placed town's area of influence, for the map's Influence layer.

Reads the terrain grid, the placed features that block growth, the plots and the
standings, and hands each town's area to ``helpers.dodoland.influence``. The
answer is cached per guild and thrown away when anything it was made from
changes: the terrain version, the world's pieces, the plots or the settings.
Those are worked out again before answering. When only the standings may have
moved (``_TTL``), the areas already made are served at once and the new ones
are worked out behind them, so nobody waits for a refresh.
"""

from __future__ import annotations

import asyncio
import logging
import threading
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
# Where the water is, per guild, from the same pass (a bool grid, [y, x]).
_WATER: dict[int, object] = {}
# The walls last worked out: guild -> (what they were made from, runs).
_WALLS: dict[int, tuple] = {}
_TTL = 300
# One computation per guild at a time; which guilds are refreshing behind.
_LOCKS: dict[int, threading.Lock] = {}
_REFRESHING: set[int] = set()
_log = logging.getLogger(__name__)


def _blocked(bot, guild_id: int, cells_w: int, cells_h: int, flag: str = "spreads",
             landmarks: bool = False) -> set:
    """Cells under placed features whose tile says no to ``flag`` — for a
    town's area ``spreads`` (a mountain range, a pond), for a road ``passable``
    (those, and every building: a road goes round a house). Their footprint is
    the lower part of the drawing, where it stands on the ground."""
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild_id)}
    # ``landmarks``: the ground under every landmark instead, whatever its tile.
    pieces = [p for p in bot.dodoland_decor.world(guild_id)
              if (p.get("locked") if landmarks else (tiles.get(p["asset_id"]) or {}).get(flag) is False)
              and p["asset_id"] in tiles]
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


def _cost_grid(chunks: dict, grow_cost: list, blocked: set, cells_w: int, cells_h: int) -> list:
    """What growing onto each cell costs, as one flat list (``y * w + x``),
    ``inf`` where an area never goes: built once and shared by every town."""
    import math

    import numpy as np

    from helpers.dodoland import terrain_raster

    grid = terrain_raster.grid(chunks, cells_w, cells_h)
    table = np.array([math.inf if c is None else float(c) for c in grow_cost] or [math.inf])
    costs = np.where((grid >= 0) & (grid < len(table)), table[np.clip(grid, 0, len(table) - 1)], math.inf)
    if blocked:
        xs, ys = zip(*blocked)
        costs[np.asarray(ys), np.asarray(xs)] = math.inf
    return costs.ravel().tolist()


def _water_grid(chunks: dict, kinds: list, cells_w: int, cells_h: int):
    """Which cells are water (shallow or deep): where a wall stops."""
    import numpy as np

    from helpers.dodoland import terrain_raster

    grid = terrain_raster.grid(chunks, cells_w, cells_h)
    table = np.array([bool(k.get("water")) for k in kinds] or [False])
    return np.where((grid >= 0) & (grid < len(table)), table[np.clip(grid, 0, len(table) - 1)], False)


def walls(bot, guild, payload: dict) -> list[dict]:
    """The walls of every walled town, as one walled territory.

    Walled towns' land is one region: overlapping walled areas share their
    outer wall and have none between them (the overlap stays inside both, so
    both towns build there). A wall stops at the shore: edges facing water or
    the map's edge are left open. Each run takes the style of the town inside
    it. Cached on the areas and the choices, so a page load costs nothing.
    Blocking."""
    choices = {str(uid): str(d.get("walls") or "")
               for uid, d in (bot.dodoland_towns.all(guild.id) or {}).items()}
    areas = _CELLS.get(guild.id) or {}
    walled = {t: s for t, s in choices.items() if s and t in areas}
    key = (id(areas), tuple(sorted(walled.items())))
    hit = _WALLS.get(guild.id)
    if hit and hit[0] == key:
        return hit[1]
    water = _WATER.get(guild.id)
    w, h = payload.get("cells_w") or 0, payload.get("cells_h") or 0
    if not walled or water is None or not w or not h:
        _WALLS[guild.id] = (key, [])
        return []

    def wet(cell) -> bool:
        x, y = cell
        return not (0 <= x < w and 0 <= y < h) or bool(water[y, x])

    # Strongest first: where two walled towns share land, the bigger one's wall
    # stands there.
    order = sorted(walled, key=lambda t: -len(areas[t]))
    owner: dict = {}
    for town in reversed(order):
        for cell in areas[town]:
            if not wet(cell):
                owner[cell] = town
    runs = influence.wall_runs(set(owner), lambda c: walled.get(owner.get(c, ""), ""), wet)
    out = [{"style": style, "town": "",
            "d": "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in pts)}
           for style, pts in runs]
    _WALLS[guild.id] = (key, out)
    return out


def _breadth(bot, guild, plots: dict, result: dict) -> tuple[dict, dict]:
    """Each placed town's power for reach, breadth included, and its breadth:
    ``({town: power}, {town: {joined, open, share, boost}})``."""
    import discord

    from helpers.dodoland import breadth

    params = bot.dodoland_params
    gid = guild.id
    powers = {str(uid): float((result["people"].get(int(uid)) or {}).get("power", 0)) for uid in plots}
    bonus = float(params.get(gid, "dodoland_breadth_bonus"))
    if bonus <= 0 or not plots:
        return powers, {}
    since = store_module.days_back(int(params.get(gid, "dodoland_breadth_days")))
    rows, _pairs = standing.recent_rows(bot.dodoland, params, gid, since)
    get_channel = getattr(guild, "get_channel", None)
    get_thread = getattr(guild, "get_thread", None)

    def room(cid: int):
        # A forum's posts are one room, the forum; a channel gone is no room.
        if get_channel is None:
            return cid
        channel = get_channel(cid) or (get_thread(cid) if get_thread else None)
        if channel is None:
            return None
        # (A thread in an ordinary channel is already charged to its channel
        # when it is recorded; what is left as a thread here is a forum post.)
        if isinstance(channel, discord.Thread):
            return int(channel.parent_id) if channel.parent_id else None
        return int(cid)

    def may_write(uid: int, where: int) -> bool:
        if get_channel is None:
            return True
        member = guild.get_member(uid) if hasattr(guild, "get_member") else None
        channel = get_channel(where)
        if member is None or channel is None:
            return False
        try:
            return bool(channel.permissions_for(member).send_messages)
        except Exception:  # noqa: BLE001 — a room we cannot judge is not held against anyone
            return False

    rooms = breadth.talkers(rows, room=room)
    curve = float(params.get(gid, "dodoland_breadth_curve"))
    out = {}
    for uid in plots:
        got = breadth.share(int(uid), rooms,
                            others=int(params.get(gid, "dodoland_breadth_others")),
                            min_messages=int(params.get(gid, "dodoland_breadth_min_messages")),
                            min_rooms=int(params.get(gid, "dodoland_breadth_min_rooms")),
                            may_write=may_write)
        got["boost"] = round(breadth.boost(got["share"], bonus, curve), 3)
        powers[str(uid)] *= got["boost"]
        out[str(uid)] = got
    return powers, out


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
    # Shared with every other reader of the same rows (cached, read-only).
    result = standing.recent_standings(bot.dodoland, params, guild.id,
                                       bot.dodoland_buildings.buildings(guild.id), since)
    strongest = max((p["power"] for p in result["order"]), default=0)
    reach_power, breadths = _breadth(bot, guild, plots, result)
    # A town boosted past everybody's power sets the scale: the strongest town
    # still reaches ``top``, never further.
    strongest = max([strongest] + list(reach_power.values()))

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
    costs = _cost_grid(chunks, grow_cost, blocked, cells_w, cells_h)
    _WATER[guild.id] = _water_grid(chunks, kinds, cells_w, cells_h)

    towns = []
    areas: dict[str, set] = {}
    for uid, plot in plots.items():
        power = reach_power.get(str(uid), 0)
        budget = influence.reach(power, strongest, base, top)
        origin = (int(float(plot.get("x", 50)) / 100 * cells_w),
                  int(float(plot.get("y", 50)) / 100 * cells_h))
        cells = influence.grow_grid(origin, budget, costs, cells_w, cells_h)
        areas[str(uid)] = cells
        # The border smoothed: the area's line, and where walls go. The stepped
        # line is only the page's fallback when there is no ring to draw.
        ring = influence.ring_path(cells)
        towns.append({"id": str(uid), "colour": townart.colour_for(str(uid)),
                      "reach": round(budget, 1), "cells": len(cells),
                      "fill": influence.fill_path(cells),
                      "line": "" if ring else influence.outline_path(cells),
                      "ring": ring, "breadth": breadths.get(str(uid))})
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
                                                    "dodoland_influence_water_cost",
                                                    "dodoland_breadth_bonus", "dodoland_breadth_days",
                                                    "dodoland_breadth_others", "dodoland_breadth_min_messages",
                                                    "dodoland_breadth_min_rooms", "dodoland_breadth_curve")))


def current(bot, guild) -> dict:
    """The payload, from the cache when nothing it was made from has changed.
    Blocking."""
    key = _key(bot, guild)
    cached = _CACHE.get(guild.id)
    if cached and cached[0] == key and guild.id in _CELLS:
        # Nothing it was made from has changed; only the standings may have.
        # Serve it, and if it is due, refresh it behind the answer.
        if time.time() - cached[1] > _TTL and guild.id not in _REFRESHING:
            _REFRESHING.add(guild.id)
            threading.Thread(target=_refresh, args=(bot, guild, key), daemon=True).start()
        return cached[2]
    with _LOCKS.setdefault(guild.id, threading.Lock()):
        cached = _CACHE.get(guild.id)
        if not cached or cached[0] != key or guild.id not in _CELLS:
            _CACHE[guild.id] = (key, time.time(), compute(bot, guild))
            cached = _CACHE[guild.id]
    return cached[2]


def _refresh(bot, guild, key) -> None:
    """The due refresh, on its own thread."""
    try:
        with _LOCKS.setdefault(guild.id, threading.Lock()):
            cached = _CACHE.get(guild.id)
            if cached and cached[0] == key and time.time() - cached[1] <= _TTL:
                return   # somebody else just made it
            _CACHE[guild.id] = (key, time.time(), compute(bot, guild))
    except Exception:  # noqa: BLE001 — the old areas keep being served
        _log.exception("DodoLand influence refresh failed for guild %s", guild.id)
    finally:
        _REFRESHING.discard(guild.id)


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


def claimed_by(bot, guild, x_pct: float, y_pct: float, *, but: str = "") -> str:
    """Whose area a map position lies in, other than ``but``'s, or ``""``.
    Blocking. A town is founded on open ground: never inside somebody else's
    reach, though it may grow into it later."""
    payload = current(bot, guild)
    x = int(float(x_pct) / 100 * payload["cells_w"])
    y = int(float(y_pct) / 100 * payload["cells_h"])
    for town, cells in (_CELLS.get(guild.id) or {}).items():
        if town != str(but) and (x, y) in cells:
            return town
    return ""


async def influence_layer(request: web.Request):
    """``GET /guild/{gid}/dodoland/influence`` — the Influence layer's data."""
    bot, guild = request.app["bot"], request["guild"]
    def both():
        payload = current(bot, guild)
        return payload, walls(bot, guild, payload)

    payload, wall_runs = await asyncio.get_running_loop().run_in_executor(None, both)
    return web.json_response({"ok": True, **payload, "walls": wall_runs})
