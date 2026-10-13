"""
The map, for a member: their own town's area to paint and build in.

The admin map (``mappage``) is the same page; a member gets it through the
player gate (``player.require_town(world=True)``) under ``/guild/{gid}/dodoland
/me/…``, with ``request["player"]`` set so every handler on the way knows to
narrow what it offers and accepts:

* **reading** — the terrain, the overview picture, the areas, the tile art and
  the towns' drawings — goes through :func:`reader`, the admin handlers
  unchanged apart from the URLs they hand back (``request["dl_base"]``);
* **painting** is the admin stroke with two rules added: only tiles the library
  gives *players* access to, and only the cells inside the painter's own town's
  area (``request["paint_filter"]``). Undo and redo are the painter's own: their
  strokes, recorded cell by cell, and a cell is only put back if it still holds
  what they painted (``terrain_api.api_player_terrain_undo``);
* **building** is :func:`build` — their own town's buildings only, at the tier
  they have reached, one of each, inside their area. The same rules the admin
  Build button follows (``decor_api._town_may_build``);
* **decorating** is :func:`build` too — anything from the library with player
  access that they have unlocked, inside their own area, up to
  ``dodoland_member_pieces`` pieces, with the pencil or the brush.

The handlers never read a user id from the request: whose town it is comes from
the session, through the gate, as everywhere on the player side.
"""

from __future__ import annotations

import asyncio
import time

from aiohttp import web

# What a member has unlocked, for a minute: working it out reads their standing,
# and a pencil click each second should not do that each time.
_UNLOCKED: dict = {}
_UNLOCKED_S = 60.0


def _base(request: web.Request) -> str:
    return f"/guild/{request['guild'].id}/dodoland/me/w"


def reader(handler):
    """An admin read handler, served to a member of the map."""
    async def run(request: web.Request):
        request["player"] = True
        request["dl_base"] = _base(request)
        return await handler(request)
    return run


async def page(request: web.Request):
    """``GET /guild/{gid}/dodoland/me/map`` — the map, as a member sees it."""
    from web.dodoland import mappage

    request["player"] = True
    request["dl_base"] = _base(request)
    return await mappage.map_page(request)


def _area(bot, guild, uid) -> set:
    from web.dodoland import influence_api

    influence_api.current(bot, guild)
    return influence_api._CELLS.get(guild.id, {}).get(str(uid)) or set()


async def paint(request: web.Request):
    """A stroke inside the member's own town's area, with player tiles only."""
    from web.dodoland import terrain_api

    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    area = await asyncio.get_running_loop().run_in_executor(None, _area, bot, guild, uid)
    if not area:
        return web.json_response({"ok": False, "error": "Your town is not on the map yet."}, status=400)
    from web.dodoland import influence_api

    world = bot.dodoland_terrain.world(guild.id)
    held = await asyncio.get_running_loop().run_in_executor(
        None, lambda: influence_api._blocked(bot, guild.id, world["cells_w"], world["cells_h"],
                                             landmarks=True))
    request["player"] = True
    # Their area, less the ground landmarks stand on.
    request["paint_filter"] = lambda cell: cell in area and cell not in held
    return await terrain_api.api_terrain_paint(request)


async def undo(request: web.Request):
    """The member's own last stroke, back or forward."""
    from web.dodoland import terrain_api

    request["player"] = True
    return await terrain_api.api_player_terrain_undo(request)


def _bad(error) -> web.Response:
    return web.json_response({"ok": False, "error": str(error)}, status=400)


def _unlocked(bot, guild, uid) -> set:
    from web.dodoland import decor_api

    key = (guild.id, int(uid))
    hit = _UNLOCKED.get(key)
    if hit and time.time() - hit[0] < _UNLOCKED_S:
        return hit[1]
    allowed = decor_api._unlocked(bot, guild, int(uid))
    _UNLOCKED[key] = (time.time(), allowed)
    return allowed


def _decor_tile(bot, guild, uid, tile_id):
    """The tile, if a member may decorate with it; else why not. Blocking."""
    tile = bot.dodoland_tiles.visible(tile_id, guild.id)
    if tile is None:
        return None, "That is not in this server's library."
    if "player" not in tile["access"] or tile["placement"] != "place":
        return None, "Members cannot place that one; it is for admins."
    if tile["tile_id"] not in _unlocked(bot, guild, uid):
        need = tile.get("requires") or {}
        return None, (f"That unlocks at tier {need.get('tier')} of the {need.get('building')}."
                      if need.get("building") else "That one is not unlocked yet.")
    return tile, ""


def _inside(area: set, world: dict, x, y) -> bool:
    try:
        cx = int(float(x) / 100 * world["cells_w"])
        cy = int(float(y) / 100 * world["cells_h"])
    except (TypeError, ValueError):
        return False
    return (cx, cy) in area


def _decorate(bot, guild, uid, member, body, many: bool):
    """Put a member's own decoration down: one piece, or a brush stroke.
    Blocking. Returns ``(response payload, error)``."""
    from helpers.dodoland import tiles as tile_rules

    mine = str(uid)
    area = _area(bot, guild, uid)
    if not area:
        return None, "Your town is not on the map yet. Place it first."
    world = bot.dodoland_terrain.world(guild.id)
    room = (int(bot.dodoland_params.get(guild.id, "dodoland_member_pieces"))
            - bot.dodoland_decor.town_count(guild.id, mine))
    if room <= 0:
        return None, "Your town has as much placed as a member may place. Remove something first."
    raw = (body.get("items") or []) if many else [body]
    if not isinstance(raw, list) or not raw:
        return None, "A stroke needs at least one piece."
    tiles: dict = {}
    items = []
    for item in raw[:400]:
        tid = str((item or {}).get("asset_id") or "")
        if tid not in tiles:
            tiles[tid] = _decor_tile(bot, guild, uid, tid)
        tile, why = tiles[tid]
        if tile is None:
            return None, why
        # Only inside the town's own area. A stroke that spills over its edge
        # keeps what landed inside.
        if not _inside(area, world, item.get("x"), item.get("y")):
            continue
        items.append({"asset_id": tile["tile_id"], "x": item.get("x"), "y": item.get("y"),
                      "scale": item.get("scale") or 1.0, "flip": bool(item.get("flip")),
                      "scale_range": tile_rules.scale_range(tile),
                      "variant": tile["variants"][0] if tile["variants"] else "",
                      "layer": tile["layer"]})
    if not items:
        return None, "That is outside your town's area. Decorate inside its reach."
    items = items[:room]
    rows = bot.dodoland_decor.place_many(
        guild.id, items, placed_by=int(uid),
        placed_by_name=getattr(member, "display_name", "") or "", town=mine)
    if many:
        return {"ok": True, "pieces": rows}, ""
    return {"ok": True, "piece": rows[0]}, ""


async def build(request: web.Request):
    """Place, move or remove one of the member's own town's buildings.

    Actions mirror the admin decor endpoint (``place``, ``move``,
    ``move_many``, ``remove_many``) so the page sends the same requests; every
    one is narrowed to pieces built for the session's own town.
    """
    from helpers.dodoland import decor as decor_rules
    from helpers.dodoland import tiles as tile_rules
    from web.dodoland import decor_api, influence_api

    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _bad("That request could not be read.")
    action = str(body.get("action") or "place")
    loop = asyncio.get_running_loop()
    mine = str(uid)

    def own(piece_id) -> dict:
        row = bot.dodoland_decor.piece(guild.id, str(piece_id or ""))
        # Their own town's, and never a landmark, even one built for them.
        ok = row and str(row.get("town") or "") == mine and not row.get("locked")
        return row if ok else None

    try:
        if action in ("lock", "unlock"):
            ids = [str(i) for i in (body.get("piece_ids") or [])[:200]]
            rows = [bot.dodoland_decor.piece(guild.id, i) for i in ids]
            if any(r and r.get("locked") for r in rows):
                return _bad("That is a landmark the server's admins set. Only they can unlock it.")
            if not ids or any(own(i) is None for i in ids):
                return _bad("You can lock only your own town's buildings.")
            n = bot.dodoland_decor.set_pinned(guild.id, ids, action == "lock", town=mine)
            return web.json_response({"ok": True, "changed": n})

        if action == "stack":
            ids = [str(i) for i in (body.get("piece_ids") or [])[:2000]]
            if not ids or any(own(i) is None for i in ids):
                return _bad("You can only stack your own town's things.")
            n = bot.dodoland_decor.set_stack(guild.id, ids, str(body.get("stack") or ""), town=mine)
            return web.json_response({"ok": True, "changed": n})

        def unpinned(ids) -> bool:
            return not bot.dodoland_decor.held(guild.id, ids)

        if action in ("move", "move_many"):
            moves = body.get("moves") if action == "move_many" else [body]
            moves = [m for m in (moves or [])[:200] if m]
            if any(own(m.get("piece_id")) is None for m in moves):
                return _bad("That is not one of your town's buildings.")
            if not unpinned([m.get("piece_id") for m in moves]):
                return _bad("You locked that in place. Unlock it first to move it.")
            refused = await decor_api._outside_area(bot, guild, moves)
            if refused:
                return _bad(refused)
            changed = 0
            for m in moves:
                changed += bool(bot.dodoland_decor.move(
                    guild.id, m.get("piece_id"), x=m.get("x"), y=m.get("y"),
                    scale=m.get("scale"), flip=m.get("flip"),
                    scale_range=decor_api._piece_range(bot, guild, m.get("piece_id"))))
            return web.json_response({"ok": True, "changed": changed})

        if action in ("remove", "remove_many"):
            ids = body.get("piece_ids") if action == "remove_many" else [body.get("piece_id")]
            ids = [str(i) for i in (ids or []) if own(i) is not None]
            if not unpinned(ids):
                return _bad("You locked that in place. Unlock it first to delete it.")
            gone = bot.dodoland_decor.remove_many(guild.id, ids)
            return web.json_response({"ok": True, "removed": gone})

        if action == "place_many":
            done, why = await loop.run_in_executor(
                None, _decorate, bot, guild, uid, request.get("member"), body, True)
            return web.json_response(done) if done else _bad(why)
        if action != "place":
            return _bad("Members place, move and remove their own town's things.")
        tile = bot.dodoland_tiles.visible(body.get("asset_id"), guild.id)
        if tile is None:
            return _bad("That is not in this server's library.")
        if not (tile.get("layer") == "buildings" and (tile.get("requires") or {}).get("building")):
            # Not one of the town's own buildings: a decoration from the toolkit.
            done, why = await loop.run_in_executor(
                None, _decorate, bot, guild, uid, request.get("member"), body, False)
            return web.json_response(done) if done else _bad(why)
        ok = await loop.run_in_executor(None, influence_api.inside, bot, guild, mine,
                                        body.get("x") or 0, body.get("y") or 0)
        if not ok:
            return _bad("That is outside your town's area. Build inside its reach.")
        refused = await loop.run_in_executor(None, decor_api._town_may_build, bot, guild, mine, tile)
        if refused:
            return _bad(refused)
        member = request.get("member")
        piece = bot.dodoland_decor.place(
            guild.id, scope=decor_rules.SCOPE_WORLD, asset_id=tile["tile_id"],
            x=body.get("x"), y=body.get("y"), scale=body.get("scale") or 1.0,
            scale_range=tile_rules.scale_range(tile),
            variant=tile["variants"][0] if tile["variants"] else "",
            layer=tile["layer"], placed_by=int(uid),
            placed_by_name=getattr(member, "display_name", "") or "", town=mine)
        return web.json_response({"ok": True, "piece": piece})
    except decor_rules.DecorError as error:
        return _bad(error)
