"""
Serving the world: vector tiles, and the brush that paints them.

Three reads and one write.

``world``    — how big the grid is and what the kinds of ground are. Once.
``overview`` — the whole continent, coarse, as one SVG. For the zoomed-out view.
``chunks``   — full detail for a rectangle of chunks. For when somebody looks close.
``paint``    — a brush stroke, which is the only thing that writes.

**Why two read paths rather than a pyramid.** A proper tile pyramid is four or
five levels and a lot of bookkeeping, and it buys nothing here: a map is either
being looked at whole — one request, coarse, cached forever — or being worked on
up close, where only a handful of chunks are on screen. The middle of that range
does not exist in practice. Two tiers covers it and is a tenth of the code.

**Everything is SVG, never a raster.** The map must stay crisp however far in
anybody goes. That rules out baking tiles to PNG, which is why the renderer
merges cells into rectangles and emits one path per kind instead — see
``helpers/dodoland/terrainart.py``.

**Rendered chunks are cached in memory, keyed by a version that a paint bumps.**
That is not the periodic bake this design deliberately does not have: nothing is
stale, there is no job, and a stroke invalidates exactly what it touched.
"""

from __future__ import annotations

import json

from aiohttp import web

from helpers.dodoland import palette as palette_rules
from helpers.dodoland import terrain as T
from helpers.dodoland import terrainart

# (guild, layer, cx, cy, step) -> svg. Bounded so a big world browsed end to end
# cannot grow it without limit.
_CACHE: dict[tuple, str] = {}
_VERSION: dict[int, int] = {}
_CACHE_MAX = 3000

# Undo, as the previous encoded state of whatever chunks a stroke touched. A
# stroke covers tens of thousands of cells but only a handful of chunks, and a
# chunk's whole state is a few hundred bytes — recording cells would be
# megabytes for the same information. In memory on purpose: undo is a property
# of the session somebody is painting in, not of the world.
_UNDO: dict[int, list] = {}
_REDO: dict[int, list] = {}
_HISTORY_MAX = 40


def version(guild_id: int) -> int:
    return _VERSION.get(int(guild_id), 0)


def invalidate(guild_id: int, chunks=None) -> None:
    """Drop what a write changed, and **only** that.

    Bumping a global version instead meant every brush stroke threw away the
    whole rendered world: the overview was rebuilt from nine hundred chunks and
    the viewport refetched, about a second of lag for a change that touched
    four. The version still moves, because the *browser* needs a cache key, but
    the server now forgets exactly what stopped being true.
    """
    guild_id = int(guild_id)
    _VERSION[guild_id] = version(guild_id) + 1
    if chunks is None:
        for key in [k for k in _CACHE if k[0] == guild_id]:
            _CACHE.pop(key, None)
        return
    touched = {(int(cx), int(cy)) for cx, cy in chunks}
    for key in [k for k in _CACHE if k[0] == guild_id
                and (k[2] == "overview" or (k[2], k[3]) in touched)]:
        _CACHE.pop(key, None)


def _line(x0: int, y0: int, x1: int, y1: int):
    """Every cell between two points, Bresenham.

    A pointer reports about sixty times a second and a drag moves further than
    that between samples — at a low zoom one pixel of mouse movement is several
    cells. Stamping the brush only where the pointer happened to be sampled left
    a trail of disconnected blobs, which is what a stroke looked like: random
    tiles scattered through the area somebody dragged across.
    """
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        err2 = err * 2
        if err2 > -dy:
            err -= dy
            x0 += sx
        if err2 < dx:
            err += dx
            y0 += sy


def _bad(error: str):
    return web.json_response({"ok": False, "error": str(error)})


def _colours(bot, guild_id: int) -> dict:
    row = bot.dodoland_terrain.world(guild_id)
    return palette_rules.resolve(world=row.get("palette"))


def _overview_step(cells_w: int) -> int:
    """Coarse enough to be one quick request, fine enough to be the same coast.

    Aims for roughly four hundred cells across, which is about the width a whole
    continent is ever drawn at on screen anyway.
    """
    return max(1, round(cells_w / 400.0))


# --------------------------------------------------------------------------- #
#  Reads
# --------------------------------------------------------------------------- #
async def terrain_world(request: web.Request):
    """The shape of the world and the vocabulary of its ground."""
    bot, guild = request.app["bot"], request["guild"]
    world = bot.dodoland_terrain.world(guild.id)
    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    return web.json_response({
        "ok": True,
        "cells_w": world["cells_w"], "cells_h": world["cells_h"],
        "source_w": world["source_w"], "source_h": world["source_h"],
        "chunk": T.CHUNK, "chunks_x": cxs, "chunks_y": cys,
        "overview_step": _overview_step(world["cells_w"]),
        "version": version(guild.id),
        "painted": bot.dodoland_terrain.painted(guild.id),
        "kinds": [{"key": k.get("key"), "label": k.get("label"),
                   "colour": _colours(bot, guild.id).get(k.get("colour"), "#000"),
                   "build": bool(k.get("build")), "water": bool(k.get("water")),
                   "move": k.get("move"), "grow": k.get("grow"),
                   "clearable": bool(k.get("clearable"))}
                  for k in world["kinds"]],
    })


async def terrain_defs(request: web.Request):
    """The texture patterns, once for the whole map.

    Separate from the chunks because a pattern is defined once and referenced by
    every region that uses it; shipping them inside each of sixty chunks would
    be sixty copies of every tile.
    """
    bot, guild = request.app["bot"], request["guild"]
    world = bot.dodoland_terrain.world(guild.id)
    return web.Response(
        text=terrainart.pattern_defs(world["kinds"], _colours(bot, guild.id)),
        content_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=600"})


async def terrain_overview(request: web.Request):
    """The whole continent in one coarse SVG."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    if not world["cells_w"]:
        return web.Response(text="", content_type="image/svg+xml")
    step = _overview_step(world["cells_w"])
    key = (guild.id, T.TERRAIN, "overview", step)
    if key not in _CACHE:
        def draw():
            cxs, cys = store.chunk_counts(guild.id)
            cells = store.chunks(guild.id, [(cx, cy) for cy in range(cys)
                                            for cx in range(cxs)])
            colours = _colours(bot, guild.id)
            parts = []
            for (cx, cy), chunk in cells.items():
                small, w, h = terrainart.downsample(chunk, T.CHUNK, T.CHUNK, step)
                parts.append(terrainart.chunk_svg(
                    small, world["kinds"], colours=colours, width=w, height=h,
                    offset=(cx * T.CHUNK / step, cy * T.CHUNK / step)))
            return "".join(parts)

        body = await asyncio.get_running_loop().run_in_executor(None, draw)
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = body
    return web.Response(
        text=_CACHE[key], content_type="image/svg+xml",
        # Keyed by a version the paint bumps, so this may be held hard.
        headers={"Cache-Control": "private, max-age=600"})


async def terrain_chunks(request: web.Request):
    """Full detail for a rectangle of chunks: ``?r=cx0,cy0,cx1,cy1``."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    cxs, cys = store.chunk_counts(guild.id)
    try:
        x0, y0, x1, y1 = (int(v) for v in (request.query.get("r") or "").split(","))
    except (TypeError, ValueError):
        return _bad("A chunk rectangle is four numbers.")
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(cxs - 1, x1), min(cys - 1, y1)
    wanted = [(cx, cy) for cy in range(y0, y1 + 1) for cx in range(x0, x1 + 1)]
    # A viewport, not a world. Without this a crafted request asks for the whole
    # continent at full detail in one go.
    if len(wanted) > 400:
        return _bad("Too many chunks at once; zoom in or ask for fewer.")

    missing = [key for key in wanted
               if (guild.id, T.TERRAIN, key[0], key[1], 1) not in _CACHE]

    if missing:
        def draw():
            colours = _colours(bot, guild.id)
            cells = store.chunks(guild.id, missing)
            out = {}
            for key, chunk in cells.items():
                out[key] = terrainart.chunk_svg(
                    chunk, world["kinds"], colours=colours, textured=True,
                    offset=(key[0] * T.CHUNK, key[1] * T.CHUNK))
            return out

        drawn = await asyncio.get_running_loop().run_in_executor(None, draw)
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        for key, svg in drawn.items():
            _CACHE[(guild.id, T.TERRAIN, key[0], key[1], 1)] = svg

    body = "".join(_CACHE.get((guild.id, T.TERRAIN, cx, cy, 1), "")
                   for cx, cy in wanted)
    return web.Response(text=body, content_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=600"})


# --------------------------------------------------------------------------- #
#  The brush
# --------------------------------------------------------------------------- #
async def api_terrain_paint(request: web.Request):
    """One brush stroke: ``{kind, radius, points: [[x, y], ...]}`` in cells.

    Points rather than one cell per request: a drag is hundreds of cells and a
    request each would be unusable. The stroke is rasterised here so the server
    decides what a radius means and two clients cannot disagree about it.
    """
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return _bad("That request could not be read.")

    world = store.world(guild.id)
    if not world["cells_w"]:
        return _bad("This server has no world yet. Import the map first.")
    try:
        kind = int(body.get("kind"))
    except (TypeError, ValueError):
        return _bad("Which terrain?")
    if not 0 <= kind < len(world["kinds"]):
        return _bad("There is no such terrain.")
    radius = max(0, min(64, int(body.get("radius") or 0)))
    points = body.get("points") or []
    if not isinstance(points, list) or not points:
        return _bad("A stroke needs at least one point.")
    if len(points) > 4000:
        return _bad("That stroke is too long; it will arrive in pieces.")

    # The brush, once: which offsets a disc of this radius covers. Round, not
    # square — square corners read as deliberate when they are not.
    disc = [(dx, dy) for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if not radius or dx * dx + dy * dy <= radius * radius]

    clean: list[tuple[int, int]] = []
    for point in points:
        try:
            clean.append((int(point[0]), int(point[1])))
        except (TypeError, ValueError, IndexError):
            continue
    if not clean:
        return _bad("A stroke needs at least one point.")

    width, height = world["cells_w"], world["cells_h"]
    edits: dict[tuple[int, int], int] = {}
    previous = clean[0]
    for point in clean:
        for cx, cy in _line(previous[0], previous[1], point[0], point[1]):
            for dx, dy in disc:
                x, y = cx + dx, cy + dy
                if 0 <= x < width and 0 <= y < height:
                    edits[(x, y)] = kind
        previous = point
        # A ceiling, so a long drag with a wide brush cannot ask for the world.
        if len(edits) > 400_000:
            return _bad("That stroke covers too much at once. "
                        "Use a smaller brush or shorter strokes.")
    if not edits:
        return _bad("That stroke fell outside the world.")

    keys = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in edits})
    # Snapshot before and after, so undo and redo are both exact rather than a
    # replay that has to get the arithmetic right a second time.
    before = store.snapshot(guild.id, keys, layer=T.TERRAIN)
    store.paint(guild.id, edits, layer=T.TERRAIN)
    after = store.snapshot(guild.id, keys, layer=T.TERRAIN)

    history = _UNDO.setdefault(guild.id, [])
    history.append({"before": before, "after": after, "keys": keys})
    del history[:-_HISTORY_MAX]
    # A new stroke ends the future, the way it does in every editor ever made.
    _REDO.pop(guild.id, None)

    invalidate(guild.id, keys)
    await _record_change(request, "dodoland_terrain", world["kinds"][kind]["key"],
                         "", f"{len(edits)} cells", "DodoLand terrain painted")
    return web.json_response({"ok": True, "cells": len(edits), "chunks": len(keys),
                              "touched": [[cx, cy] for cx, cy in keys],
                              "undo": len(history), "redo": 0,
                              "version": version(guild.id)})


async def api_terrain_undo(request: web.Request):
    """Step one stroke back, or forward with ``{"redo": true}``.

    Undo restores the chunks a stroke replaced; redo reapplies the ones it
    wrote. Both are whole-chunk writes rather than a recomputation, so neither
    can drift from what actually happened.
    """
    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}
    forward = bool(body.get("redo"))

    source = _REDO if forward else _UNDO
    target = _UNDO if forward else _REDO
    stack = source.get(guild.id) or []
    if not stack:
        return web.json_response({"ok": True, "moved": False,
                                  "undo": len(_UNDO.get(guild.id) or []),
                                  "redo": len(_REDO.get(guild.id) or []),
                                  "version": version(guild.id)})
    entry = stack.pop()
    store.restore(guild.id, entry["after" if forward else "before"], layer=T.TERRAIN)
    target.setdefault(guild.id, []).append(entry)
    invalidate(guild.id, entry["keys"])
    return web.json_response({
        "ok": True, "moved": True,
        "touched": [[cx, cy] for cx, cy in entry["keys"]],
        "undo": len(_UNDO.get(guild.id) or []),
        "redo": len(_REDO.get(guild.id) or []),
        "version": version(guild.id)})
