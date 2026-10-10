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
# vid -> average colour of that tile image.
_HEX: dict[str, str] = {}


_REV: dict[int, int] = {}


def _fresh(guild_id: int, world: dict) -> None:
    """Drop everything drawn for a guild whose world a tool rewrote since."""
    rev = int(world.get("rev") or 0)
    if _REV.get(int(guild_id)) != rev:
        if int(guild_id) in _REV:
            invalidate(guild_id)
        _REV[int(guild_id)] = rev


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
def _hex(bot, tile: dict) -> str:
    """A tile's average colour, for the zoomed-out view. Cached per variant id,
    which is never reused, so the cache can never be stale."""
    vids = tile.get("variants") or []
    if not vids:
        return "#777777"
    vid = vids[0]
    if vid not in _HEX:
        colour = "#777777"
        row = bot.dodoland_tiles.art(vid)
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(bytes(row["data"]))) as image:
                rgba = image.convert("RGBA").resize((1, 1), Image.BOX).getpixel((0, 0))
            colour = "#%02x%02x%02x" % rgba[:3]
        except Exception:  # noqa: BLE001 - a colour is cosmetic
            pass
        _HEX[vid] = colour
    return _HEX[vid]


def _env_tiles(bot, guild, request) -> list[dict]:
    """Ground tiles the person painting may use: every environment tile for
    the bot owner, those with admin access for a server admin."""
    from helpers import panel_access

    tiles = [t for t in bot.dodoland_tiles.tiles(guild.id)
             if t["layer"] == "environment" and t["placement"] == "paint"]
    if request.get("scope") != panel_access.SCOPE_OWNER:
        tiles = [t for t in tiles if "admin" in t["access"]]
    return tiles


def _tile_index(bot, guild) -> dict:
    return {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild.id)}


async def terrain_world(request: web.Request):
    """The shape of the world, the vocabulary of its ground, and the palette
    of tiles the brush paints with."""
    bot, guild = request.app["bot"], request["guild"]
    world = bot.dodoland_terrain.world(guild.id)
    _fresh(guild.id, world)
    tiles = _tile_index(bot, guild)
    world["kinds"] = T.sync_tile_kinds(world["kinds"], tiles)
    cats = {c["cat_id"]: c["name"] for c in bot.dodoland_tiles.categories()}
    art = f"/guild/{guild.id}/dodoland/tiles/art/"
    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    return web.json_response({
        "ok": True,
        "cells_w": world["cells_w"], "cells_h": world["cells_h"],
        "source_w": world["source_w"], "source_h": world["source_h"],
        "chunk": T.CHUNK, "chunks_x": cxs, "chunks_y": cys,
        "overview_step": _overview_step(world["cells_w"]),
        "version": version(guild.id),
        "painted": bot.dodoland_terrain.painted(guild.id),
        "palette": [{"id": t["tile_id"], "name": t["name"], "cat": cats.get(t["cat_id"], ""),
                     "thumb": art + t["variants"][0] if t["variants"] else "",
                     "hex": _hex(bot, t), "passable": t["passable"]}
                    for t in _env_tiles(bot, guild, request)],
        "kinds": [{"key": k.get("key"), "label": k.get("label"),
                   "tile_id": k.get("tile_id") or "",
                   "colour": terrainart.kind_fill(k, _colours(bot, guild.id)),
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
    _fresh(guild.id, world)
    tiles = _tile_index(bot, guild)
    used = [tiles[k["tile_id"]] for k in world["kinds"] if k.get("tile_id") in tiles]
    dims = bot.dodoland_tiles.art_sizes(v for t in used for v in t["variants"])
    return web.Response(
        text=terrainart.pattern_defs(world["kinds"], tiles,
                                     f"/guild/{guild.id}/dodoland/tiles/art/", dims),
        content_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=600"})


async def terrain_overview(request: web.Request):
    """The whole continent in one coarse SVG."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    _fresh(guild.id, world)
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
    _fresh(guild.id, world)
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
def _noise(x: int, y: int, seed: int, salt: int = 0) -> float:
    """A fixed pseudo-random number in [0, 1) for one cell of one stroke.

    Seeded per stroke rather than drawn from a generator, so the server decides
    which cells a scattered brush hits and the same stroke can never come out
    two different ways.
    """
    value = (x * 374761393 + y * 668265263 + seed * 2246822519 + salt * 3266489917) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((value ^ (value >> 16)) & 0xFFFFFF) / float(0x1000000)


def _choices(store, bot, guild, request, world, body) -> list[int]:
    """What the stroke paints, as kind indices: a mix of tiles (each becomes a
    kind the first time it is painted), or raw kinds (the eraser)."""
    allowed = ({t["tile_id"]: t for t in _env_tiles(bot, guild, request)}
               if body.get("tiles") else {})
    out = []
    for tile_id in body.get("tiles") or []:
        tile = allowed.get(str(tile_id))
        if tile is None:
            raise T.TerrainError("That tile is not available to paint with here.")
        out.append(store.kind_for_tile(guild.id, tile, _hex(bot, tile)))
    for kind in body.get("kinds") or []:
        kind = int(kind)
        if not 0 <= kind < len(world["kinds"]):
            raise T.TerrainError("There is no such terrain.")
        out.append(kind)
    if not out and body.get("kind") is not None:          # the old single-kind form
        kind = int(body.get("kind"))
        if not 0 <= kind < len(world["kinds"]):
            raise T.TerrainError("There is no such terrain.")
        out.append(kind)
    if len(out) > 16:
        raise T.TerrainError("A brush mixes at most sixteen tiles.")
    return out


async def api_terrain_paint(request: web.Request):
    """One stroke. Two shapes and two ways of choosing what lands:

    * ``mode: "brush"`` — ``points`` in cells and a ``radius``: a disc dragged
      along the line between the points.
    * ``mode: "rect"`` — ``rect: [x0, y0, x1, y1]``: a selection filled at once.

    A cell receives from the ``pattern`` (``{w, h, cells}`` of kind indices,
    tiled across the world from its origin) if one is given, otherwise one of
    the ``tiles`` in the mix, picked per cell. ``density`` (0-1) scatters the
    stroke so only that share of cells is painted, and ``soft`` (0-1) thins it
    towards the edge of the brush, which is what makes a wide brush read as a
    coastline instead of a stamp.

    Everything is rasterised here, so the server decides what a radius means
    and two clients cannot disagree about it.
    """
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return _bad("That request could not be read.")

    world = store.world(guild.id)
    _fresh(guild.id, world)
    if not world["cells_w"]:
        return _bad("This server has no world yet. Import the map first.")
    width, height = world["cells_w"], world["cells_h"]
    try:
        density = max(0.0, min(1.0, float(body.get("density", 1.0))))
        soft = max(0.0, min(1.0, float(body.get("soft", 0.0))))
        seed = int(body.get("seed") or 1) & 0x7FFFFFFF
        pattern = body.get("pattern")
        pw = ph = 0
        pcells: list[int] = []
        choices: list[int] = []
        if pattern:
            pw, ph = int(pattern["w"]), int(pattern["h"])
            pcells = [int(v) for v in pattern["cells"]]
            if not (1 <= pw <= 128 and 1 <= ph <= 128 and len(pcells) == pw * ph):
                return _bad("A pattern is at most 128 by 128 cells.")
            if any(not 0 <= v < len(world["kinds"]) for v in pcells):
                return _bad("That pattern names ground this world does not have.")
        else:
            choices = _choices(store, bot, guild, request, world, body)
            if not choices:
                return _bad("Pick something to paint with.")
            world = store.world(guild.id)   # a new tile may have added a kind
    except T.TerrainError as error:
        return _bad(error)
    except (TypeError, ValueError, KeyError):
        return _bad("That stroke could not be read.")

    # cell -> how far into the brush it is: 0 at the centre, 1 at the rim.
    reach: dict[tuple[int, int], float] = {}
    mode = str(body.get("mode") or "brush")
    if mode == "rect":
        try:
            x0, y0, x1, y1 = (int(v) for v in body.get("rect"))
        except (TypeError, ValueError):
            return _bad("A selection is four numbers.")
        x0, x1 = sorted((max(0, min(x0, x1)), min(width - 1, max(x0, x1))))
        y0, y1 = sorted((max(0, min(y0, y1)), min(height - 1, max(y0, y1))))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 400_000:
            return _bad("That selection is too big to fill at once.")
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                reach[(x, y)] = 0.0
    else:
        radius = max(0, min(64, int(body.get("radius") or 0)))
        points = body.get("points") or []
        if not isinstance(points, list) or not points:
            return _bad("A stroke needs at least one point.")
        if len(points) > 4000:
            return _bad("That stroke is too long; it will arrive in pieces.")
        # The brush, once: which offsets a disc of this radius covers, and how
        # far out each one is. Round, not square — square corners read as
        # deliberate when they are not.
        disc = [(dx, dy, ((dx * dx + dy * dy) ** 0.5) / radius if radius else 0.0)
                for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
                if not radius or dx * dx + dy * dy <= radius * radius]
        clean = []
        for point in points:
            try:
                clean.append((int(point[0]), int(point[1])))
            except (TypeError, ValueError, IndexError):
                continue
        if not clean:
            return _bad("A stroke needs at least one point.")
        previous = clean[0]
        for point in clean:
            for cx, cy in _line(previous[0], previous[1], point[0], point[1]):
                for dx, dy, far in disc:
                    x, y = cx + dx, cy + dy
                    if 0 <= x < width and 0 <= y < height:
                        key = (x, y)
                        if far < reach.get(key, 2.0):
                            reach[key] = far
            previous = point
            if len(reach) > 400_000:
                return _bad("That stroke covers too much at once. "
                            "Use a smaller brush or shorter strokes.")

    edits: dict[tuple[int, int], int] = {}
    inner = 1.0 - soft
    for (x, y), far in reach.items():
        chance = density
        if soft and far > inner:
            chance *= max(0.0, 1.0 - (far - inner) / soft)
        if chance < 1.0 and _noise(x, y, seed) >= chance:
            continue
        if pcells:
            edits[(x, y)] = pcells[(y % ph) * pw + (x % pw)]
        else:
            edits[(x, y)] = choices[int(_noise(x, y, seed, 1) * len(choices))]
    if not edits:
        return _bad("That stroke painted nothing; raise the density.")

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
    await _record_change(request, "dodoland_terrain", mode, "",
                         f"{len(edits)} cells", "DodoLand terrain painted")
    return web.json_response({"ok": True, "cells": len(edits), "chunks": len(keys),
                              "touched": [[cx, cy] for cx, cy in keys],
                              "kinds": len(world["kinds"]),
                              "undo": len(history), "redo": 0,
                              "version": version(guild.id)})


async def terrain_cells(request: web.Request):
    """The kinds in a rectangle, ``?r=x0,y0,x1,y1`` in cells: what the pattern
    tool copies. Capped, because it is a stamp, not an export."""
    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    world = store.world(guild.id)
    _fresh(guild.id, world)
    try:
        x0, y0, x1, y1 = (int(v) for v in (request.query.get("r") or "").split(","))
    except (TypeError, ValueError):
        return _bad("A rectangle is four numbers.")
    x0, x1 = sorted((max(0, min(x0, x1)), min(world["cells_w"] - 1, max(x0, x1))))
    y0, y1 = sorted((max(0, min(y0, y1)), min(world["cells_h"] - 1, max(y0, y1))))
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w > 128 or h > 128:
        return _bad("A pattern is at most 128 by 128 cells; select less.")
    keys = sorted({(cx, cy) for cx in range(x0 // T.CHUNK, x1 // T.CHUNK + 1)
                   for cy in range(y0 // T.CHUNK, y1 // T.CHUNK + 1)})
    chunks = store.chunks(guild.id, keys)
    cells = [chunks[(x // T.CHUNK, y // T.CHUNK)][(y % T.CHUNK) * T.CHUNK + (x % T.CHUNK)]
             for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    return web.json_response({"ok": True, "x": x0, "y": y0, "w": w, "h": h, "cells": cells})


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
