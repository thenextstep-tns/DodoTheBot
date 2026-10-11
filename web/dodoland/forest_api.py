"""
The forest layer's two endpoints: painting it and reading it.

A forest is painted, not placed (``helpers/dodoland/forest.py``): a stroke
writes a stand's index into the cells it covers — 0 to erase — in the terrain
store's ``cover`` layer. Nothing per tree is stored or sent; the map grows the
trees from the cells itself (``web/dodoland/forest_ui.py``). So a forest of a
hundred thousand trees costs the server a few chunk writes, and influence,
roads and the placed-object count never see it.
"""

from __future__ import annotations

import json
import time

from aiohttp import web

from helpers.dodoland import forest
from helpers.dodoland import terrain as T

_BOOT = int(time.time())
# guild -> strokes since boot: the browser's cache key for the forest layer.
_VERSION: dict[int, int] = {}


def version(guild_id: int) -> str:
    return f"{_BOOT}.{_VERSION.get(int(guild_id), 0)}"


def _bad(error) -> web.Response:
    return web.json_response({"ok": False, "error": str(error)}, status=400)


def _empty(rle: str) -> bool:
    return not rle or rle == f"{T.CELLS}x{forest.NONE}"


async def api_forest_paint(request: web.Request):
    """One forest stroke: ``points``, ``radius`` and ``shape`` as the ground
    brush takes them, then either ``erase: true`` or the stand to paint —
    ``mix`` (tile ids), ``density``, ``scale``, ``jitter``, ``flip``."""
    from helpers.dodoland import decor as decor_rules
    from web.dodoland import decor_api
    from web.dodoland.terrain_api import StrokeError, stroke_reach
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
        reach = stroke_reach(body, world["cells_w"], world["cells_h"])
    except StrokeError as error:
        return _bad(error)
    if not reach:
        return _bad("That stroke covers nothing.")

    if body.get("erase"):
        index = forest.NONE
    else:
        try:
            spec = forest.stand_spec(mix=body.get("mix") or [], density=body.get("density"),
                                     scale=body.get("scale"), jitter=body.get("jitter"),
                                     flip=body.get("flip", True))
            # Only what an admin could place here goes into a forest.
            for tile_id in spec["mix"]:
                decor_api._admin_tile(bot, guild, request, tile_id)
            index, stands = forest.stand_index(world["stands"], spec)
        except (forest.ForestError, decor_rules.DecorError) as error:
            return _bad(error)
        if len(stands) != len(world["stands"]):
            store.set_stands(guild.id, stands)

    edits = {cell: index for cell in reach}
    keys = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in edits})
    store.paint(guild.id, edits, layer=T.COVER)
    _VERSION[int(guild.id)] = _VERSION.get(int(guild.id), 0) + 1
    await _record_change(request, "dodoland_forest", "erase" if index == forest.NONE else "paint",
                         "", f"{len(edits)} cells", "DodoLand forest painted")
    return web.json_response({"ok": True, "cells": len(edits), "stand": index,
                              "touched": [[cx, cy] for cx, cy in keys],
                              "version": version(guild.id)})


async def forest_chunks(request: web.Request):
    """``GET …/forest/chunks?r=cx0,cy0,cx1,cy1`` — the forest in a box of
    chunks: the stands, and the run-length rows of every chunk with forest in
    it (empty ones are left out)."""
    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    if not world["cells_w"]:
        return web.json_response({"ok": True, "stands": [], "chunks": {}, "version": version(guild.id)})
    cxs, cys = store.chunk_counts(guild.id)
    try:
        x0, y0, x1, y1 = (int(v) for v in str(request.query.get("r", "")).split(","))
    except ValueError:
        x0, y0, x1, y1 = 0, 0, cxs - 1, cys - 1
    x0, x1 = max(0, min(x0, x1)), min(cxs - 1, max(x0, x1))
    y0, y1 = max(0, min(y0, y1)), min(cys - 1, max(y0, y1))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 2500:
        return _bad("That is too much of the map at once.")
    keys = [(cx, cy) for cy in range(y0, y1 + 1) for cx in range(x0, x1 + 1)]
    rows = store.snapshot(guild.id, keys, layer=T.COVER)
    return web.json_response(
        {"ok": True, "stands": world["stands"], "version": version(guild.id),
         "chunks": {f"{cx},{cy}": rle for (cx, cy), rle in rows.items() if not _empty(rle)}},
        headers={"Cache-Control": "private, max-age=600"})
