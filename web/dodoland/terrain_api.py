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
import time

from aiohttp import web

from helpers.dodoland import palette as palette_rules
from helpers.dodoland import terrain as T
from helpers.dodoland import terrainart

# (guild, layer, cx, cy, step) -> svg. Bounded so a big world browsed end to end
# cannot grow it without limit.
_CACHE: dict[tuple, str] = {}
_VERSION: dict[int, int] = {}
_CACHE_MAX = 3000
# When this process started. Part of every version: the counter starts at 0
# again on a restart, and the browser holds terrain for ten minutes, so without
# it a restart served yesterday's ground under today's "v=0" — after the 4x
# regrid, old-grid chunks laid out on the new grid.
_BOOT = int(time.time())

# Undo, as the previous encoded state of whatever chunks a stroke touched. A
# stroke covers tens of thousands of cells but only a handful of chunks, and a
# chunk's whole state is a few hundred bytes — recording cells would be
# megabytes for the same information. In memory on purpose: undo is a property
# of the session somebody is painting in, not of the world.
_UNDO: dict[int, list] = {}
_REDO: dict[int, list] = {}
# A member's own strokes, (guild, user) -> [{cells: [(x, y, old, new)], keys}].
# Cell by cell rather than whole chunks: a member's undo must never take back
# somebody else's work painted into the same chunk since.
_PUNDO: dict[tuple, list] = {}
_PREDO: dict[tuple, list] = {}
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


def version(guild_id: int) -> str:
    """The browser's cache key for a guild's terrain: this process, the world's
    revision (bumped by tools that rewrite it), and the paints since."""
    g = int(guild_id)
    return f"{_BOOT}.{_REV.get(g, 0)}.{_VERSION.get(g, 0)}"


def invalidate(guild_id: int, chunks=None) -> None:
    """Drop what a write changed, and **only** that.

    Bumping a global version instead meant every brush stroke threw away the
    whole rendered world: the overview was rebuilt from nine hundred chunks and
    the viewport refetched, about a second of lag for a change that touched
    four. The version still moves, because the *browser* needs a cache key, but
    the server now forgets exactly what stopped being true.
    """
    guild_id = int(guild_id)
    _VERSION[guild_id] = _VERSION.get(guild_id, 0) + 1
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
    continent is ever drawn at on screen anyway. A power of two, so it divides a
    chunk evenly: a step of 10 on 64-cell chunks puts every chunk 6.4 cells from
    the next but draws it 7 wide, and the seams overlap.
    """
    step = 1
    while step * 2 <= min(T.CHUNK, cells_w / 400.0):
        step *= 2
    return step


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
    if request.get("player"):
        # A member paints with what the library gives players, whoever they are.
        return [t for t in tiles if "player" in t["access"]]
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
    art = request.get("dl_base", f"/guild/{guild.id}/dodoland") + "/tiles/art/"
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


# guild -> (version, webp bytes). One picture per guild: a few hundred KB.
_PICTURES: dict[int, tuple[str, bytes]] = {}


def picture_bytes(bot, guild_id: int) -> bytes:
    """The world drawn as one shaded picture (``terrain_raster``), made once per
    terrain version. Blocking: a few seconds for a continent, so callers run it
    in an executor, and the cog makes it at startup so nobody waits for it."""
    from helpers.dodoland import terrain_raster

    world = bot.dodoland_terrain.world(guild_id)
    _fresh(guild_id, world)
    if not world["cells_w"]:
        return b""
    ver = version(guild_id)
    hit = _PICTURES.get(int(guild_id))
    if hit and hit[0] == ver:
        return hit[1]
    params = bot.dodoland_params
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild_id)}
    data = terrain_raster.picture(
        bot.dodoland_terrain, guild_id, _colours(bot, guild_id),
        kinds=T.sync_tile_kinds(world["kinds"], tiles),
        shading=float(params.get(guild_id, "dodoland_overview_shading")),
        grain=float(params.get(guild_id, "dodoland_overview_grain")))
    _PICTURES[int(guild_id)] = (ver, data)
    return data


# guild -> (version, webp bytes) of the shading layer.
_SHADES: dict[int, tuple[str, bytes]] = {}


def shade_bytes(bot, guild_id: int) -> bytes:
    """The overview's shading alone (``terrain_raster.render_shade``), laid over
    the close-up tiles. Made once per terrain version. Blocking."""
    from helpers.dodoland import terrain_raster

    world = bot.dodoland_terrain.world(guild_id)
    _fresh(guild_id, world)
    strength = float(bot.dodoland_params.get(guild_id, "dodoland_detail_shading"))
    if not world["cells_w"] or strength <= 0:
        return b""
    ver = version(guild_id) + f".{strength}.nocoast"
    hit = _SHADES.get(int(guild_id))
    if hit and hit[0] == ver:
        return hit[1]
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild_id)}
    data = terrain_raster.shade(bot.dodoland_terrain, guild_id,
                                shading=strength * float(bot.dodoland_params.get(guild_id, "dodoland_overview_shading")),
                                kinds=T.sync_tile_kinds(world["kinds"], tiles),
                                # The coast band and surf are drawn by the page
                                # from the smoothed shore (terrain_ui bake).
                                coast=False)
    _SHADES[int(guild_id)] = (ver, data)
    return data


async def terrain_shade(request: web.Request):
    """``GET …/terrain/shade?v=`` — the shading laid over the close-up tiles."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    data = await asyncio.get_running_loop().run_in_executor(None, shade_bytes, bot, guild.id)
    if not data:
        return web.Response(status=404, text="No shading.", content_type="text/plain")
    return web.Response(body=data, content_type="image/webp",
                        headers={"Cache-Control": "private, max-age=600"})


async def terrain_picture(request: web.Request):
    """``GET …/terrain/picture?v=`` — the overview the map shows zoomed out."""
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    data = await asyncio.get_running_loop().run_in_executor(None, picture_bytes, bot, guild.id)
    if not data:
        return web.Response(status=404, text="No world yet.", content_type="text/plain")
    return web.Response(body=data, content_type="image/webp",
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


async def terrain_rle(request: web.Request):
    """``GET …/terrain/rle?r=cx0,cy0,cx1,cy1`` — what the map bakes the close-up
    ground from: every chunk's run-length cells in the box (empty for none),
    and for each kind of ground how to draw it (its tile's layout, or a flat
    colour) and whether it is land, for blending."""
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
    # A viewport, not a world.
    if len(wanted) > 600:
        return _bad("Too many chunks at once; zoom in or ask for fewer.")
    rows = store.snapshot(guild.id, wanted, layer=T.TERRAIN)
    tiles = _tile_index(bot, guild)
    kinds = T.sync_tile_kinds(world["kinds"], tiles)
    used = [tiles[k["tile_id"]] for k in kinds if k.get("tile_id") in tiles]
    dims = bot.dodoland_tiles.art_sizes(v for t in used for v in t["variants"])
    shrink = float(bot.dodoland_params.get(guild.id, "dodoland_tile_scale"))
    colours = _colours(bot, guild.id)
    out_kinds = []
    for kind in kinds:
        tile = tiles.get(kind.get("tile_id"))
        out_kinds.append({
            "fill": terrainart.kind_fill(kind, colours),
            "layout": terrainart.pattern_layout(str(kind.get("key") or ""), tile, dims, shrink) if tile else None,
            "land": bool(kind) and not kind.get("water") and str(kind.get("key") or "") != "unknown"})
    return web.json_response(
        {"ok": True, "version": version(guild.id), "kinds": out_kinds,
         "art": request.get("dl_base", f"/guild/{guild.id}/dodoland") + "/tiles/art/",
         "chunks": {f"{cx},{cy}": rle for (cx, cy), rle in rows.items()}},
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


class StrokeError(ValueError):
    pass


def stroke_reach(body: dict, width: int, height: int) -> dict[tuple[int, int], float]:
    """The cells a stroke covers, each with how far into the brush it is: 0 at
    the centre, 1 at the rim. Shared by every brush that paints the grid (the
    ground and the forest), so a radius means the same thing to all of them.

    * ``mode: "brush"`` — ``points`` in cells and a ``radius``: a disc (or with
      ``shape: "square"`` a square) dragged along the line between the points.
    * ``mode: "rect"`` — ``rect: [x0, y0, x1, y1]``: a selection filled at once.
    """
    # cell -> how far into the brush it is: 0 at the centre, 1 at the rim.
    reach: dict[tuple[int, int], float] = {}
    mode = str(body.get("mode") or "brush")
    if mode == "rect":
        try:
            x0, y0, x1, y1 = (int(v) for v in body.get("rect"))
        except (TypeError, ValueError):
            raise StrokeError("A selection is four numbers.")
        x0, x1 = sorted((max(0, min(x0, x1)), min(width - 1, max(x0, x1))))
        y0, y1 = sorted((max(0, min(y0, y1)), min(height - 1, max(y0, y1))))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 400_000:
            raise StrokeError("That selection is too big to fill at once.")
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                reach[(x, y)] = 0.0
        return reach
    try:
        radius = max(0, min(64, int(body.get("radius") or 0)))
    except (TypeError, ValueError):
        raise StrokeError("That stroke could not be read.")
    points = body.get("points") or []
    if not isinstance(points, list) or not points:
        raise StrokeError("A stroke needs at least one point.")
    if len(points) > 4000:
        raise StrokeError("That stroke is too long; it will arrive in pieces.")
    # The brush, once: which offsets a disc of this radius covers, and how
    # far out each one is. Round, not square — square corners read as
    # deliberate when they are not.
    # Round by default; square for roads, walls of hedge, anything with an
    # edge that should run straight. "far" is the distance to the rim in
    # the brush's own shape, so a soft edge softens a square as a square.
    if str(body.get("shape") or "round") == "square":
        disc = [(dx, dy, max(abs(dx), abs(dy)) / radius if radius else 0.0)
                for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
    else:
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
        raise StrokeError("A stroke needs at least one point.")
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
            raise StrokeError("That stroke covers too much at once. "
                              "Use a smaller brush or shorter strokes.")
    return reach


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

    mode = str(body.get("mode") or "brush")
    try:
        reach = stroke_reach(body, width, height)
    except StrokeError as error:
        return _bad(error)

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
    # A member paints inside their own town's area and nowhere else.
    inside = request.get("paint_filter")
    if inside is not None:
        edits = {cell: kind for cell, kind in edits.items() if inside(cell)}
        if not edits:
            return _bad("You can paint inside your own town's area.")
    if not edits:
        return _bad("That stroke painted nothing; raise the density.")

    keys = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in edits})
    if request.get("player"):
        return await _player_stroke(request, bot, guild, store, edits, keys, world)
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


def _cells_now(store, guild_id: int, cells) -> dict:
    """The kind every one of these cells holds now."""
    keys = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in cells})
    chunks = store.chunks(guild_id, keys, layer=T.TERRAIN)
    return {(x, y): chunks[(x // T.CHUNK, y // T.CHUNK)][(y % T.CHUNK) * T.CHUNK + (x % T.CHUNK)]
            for x, y in cells}


def _player_counts(key) -> dict:
    return {"undo": len(_PUNDO.get(key) or []), "redo": len(_PREDO.get(key) or [])}


async def _player_stroke(request, bot, guild, store, edits, keys, world):
    """A member's stroke: painted like any other, remembered in their own history."""
    key = (guild.id, int(request["uid"]))
    before = _cells_now(store, guild.id, edits)
    changed = {cell: kind for cell, kind in edits.items() if before[cell] != kind}
    if not changed:
        return _bad("That is already painted that way.")
    store.paint(guild.id, changed, layer=T.TERRAIN)
    history = _PUNDO.setdefault(key, [])
    history.append({"cells": [(x, y, before[(x, y)], kind) for (x, y), kind in changed.items()],
                    "keys": keys})
    del history[:-_HISTORY_MAX]
    _PREDO.pop(key, None)
    invalidate(guild.id, keys)
    return web.json_response({"ok": True, "cells": len(changed), "chunks": len(keys),
                              "touched": [[cx, cy] for cx, cy in keys],
                              "kinds": len(world["kinds"]), **_player_counts(key),
                              "version": version(guild.id)})


async def api_player_terrain_undo(request: web.Request):
    """A member's own last stroke, back (or forward with ``{"redo": true}``).

    Only their strokes, and only the cells that still hold what the stroke left:
    a cell somebody has painted over since is theirs now, and stays as it is.
    """
    bot, guild = request.app["bot"], request["guild"]
    store = bot.dodoland_terrain
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}
    forward = bool(body.get("redo"))
    key = (guild.id, int(request["uid"]))
    source, target = (_PREDO, _PUNDO) if forward else (_PUNDO, _PREDO)
    stack = source.get(key) or []
    if not stack:
        return web.json_response({"ok": True, "moved": False, **_player_counts(key),
                                  "version": version(guild.id)})
    entry = stack.pop()
    now = _cells_now(store, guild.id, [(x, y) for x, y, _, _ in entry["cells"]])
    edits = {}
    for x, y, old, new in entry["cells"]:
        expect, put = (old, new) if forward else (new, old)
        if now[(x, y)] == expect:
            edits[(x, y)] = put
    if edits:
        store.paint(guild.id, edits, layer=T.TERRAIN)
    target.setdefault(key, []).append(entry)
    invalidate(guild.id, entry["keys"])
    return web.json_response({"ok": True, "moved": True, "cells": len(edits),
                              "touched": [[cx, cy] for cx, cy in entry["keys"]],
                              **_player_counts(key), "version": version(guild.id)})


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
