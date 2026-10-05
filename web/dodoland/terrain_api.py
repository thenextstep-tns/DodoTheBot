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

# (guild, layer, cx, cy, step, version) -> svg. Bounded so a big world browsed
# end to end cannot grow it without limit.
_CACHE: dict[tuple, str] = {}
_VERSION: dict[int, int] = {}
_CACHE_MAX = 3000


def version(guild_id: int) -> int:
    return _VERSION.get(int(guild_id), 0)


def invalidate(guild_id: int) -> None:
    """Called by anything that writes terrain. Cheap and always safe."""
    _VERSION[int(guild_id)] = version(guild_id) + 1


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


async def terrain_overview(request: web.Request):
    """The whole continent in one coarse SVG."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    if not world["cells_w"]:
        return web.Response(text="", content_type="image/svg+xml")
    step = _overview_step(world["cells_w"])
    key = (guild.id, T.TERRAIN, "overview", step, version(guild.id))
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

    ver = version(guild.id)
    missing = [key for key in wanted
               if (guild.id, T.TERRAIN, key[0], key[1], 1, ver) not in _CACHE]

    if missing:
        def draw():
            colours = _colours(bot, guild.id)
            cells = store.chunks(guild.id, missing)
            out = {}
            for key, chunk in cells.items():
                out[key] = terrainart.chunk_svg(
                    chunk, world["kinds"], colours=colours,
                    offset=(key[0] * T.CHUNK, key[1] * T.CHUNK))
            return out

        drawn = await asyncio.get_running_loop().run_in_executor(None, draw)
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        for key, svg in drawn.items():
            _CACHE[(guild.id, T.TERRAIN, key[0], key[1], 1, ver)] = svg

    body = "".join(_CACHE.get((guild.id, T.TERRAIN, cx, cy, 1, ver), "")
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

    edits: dict[tuple[int, int], int] = {}
    span = range(-radius, radius + 1)
    limit = radius * radius
    for point in points:
        try:
            px, py = int(point[0]), int(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        for dy in span:
            for dx in span:
                # Round, not square: a square brush leaves corners that read as
                # deliberate when they are not.
                if radius and dx * dx + dy * dy > limit:
                    continue
                x, y = px + dx, py + dy
                if 0 <= x < world["cells_w"] and 0 <= y < world["cells_h"]:
                    edits[(x, y)] = kind
    if not edits:
        return _bad("That stroke fell outside the world.")

    touched = store.paint(guild.id, edits, layer=T.TERRAIN)
    invalidate(guild.id)
    await _record_change(request, "dodoland_terrain", world["kinds"][kind]["key"],
                         "", f"{len(edits)} cells", "DodoLand terrain painted")
    return web.json_response({"ok": True, "cells": len(edits), "chunks": touched,
                              "version": version(guild.id)})
