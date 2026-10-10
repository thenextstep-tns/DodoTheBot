"""
The toolkit's endpoints: putting something from the library on the ground.

Two callers, two scopes, and they are deliberately separate handlers rather
than one with a flag.

``api_world_decor`` is administrative. It dresses the **map** — forests, rivers,
mountains, a ruin on a headland — and what it writes everybody sees in the same
place, so it takes the panel's ``full`` scope and the tier locks do not apply
to it. An admin placing a forest has not earned a forest; they are drawing the
world.

``api_town_decor`` belongs to a player. It dresses **their own town**, it takes
no user id from the request (the session decides whose town it is, the same
rule the rest of ``player.py`` follows), and the tier locks are enforced here
rather than in the browser. The toolkit dims what is locked as a courtesy; this
is what actually refuses it.

Positions are percentages in both cases, for the same reason a town's are: of
the base image for world decor, and of the town's own box for town decor. So
re-uploading a redrawn map moves nothing, and moving a town takes its cart and
its bonfire with it.
"""

from __future__ import annotations

import json

from aiohttp import web

from helpers.dodoland import tiles as tile_rules
from helpers.dodoland import decor as decor_rules
from helpers.dodoland import standing
from helpers.dodoland import store as store_module


def _bad(error: str):
    return web.json_response({"ok": False, "error": str(error)})


async def _body(request: web.Request):
    try:
        return await request.json()
    except (ValueError, json.JSONDecodeError):
        return None


def _piece_range(bot, guild, piece_id) -> tuple:
    """What an existing piece may be resized to, from the tile it came from."""
    piece = bot.dodoland_decor.piece(guild.id, piece_id) or {}
    return tile_rules.scale_range(bot.dodoland_tiles.visible(piece.get("asset_id"), guild.id))


def _admin_tile(bot, guild, request, tile_id) -> dict:
    """The tile an admin asked to place, if admins may place it here.

    The bot owner may place anything visible to the server; a server admin only
    map objects and buildings whose access includes admins.
    """
    from helpers import panel_access

    tile = bot.dodoland_tiles.visible(tile_id, guild.id)
    if tile is None:
        raise decor_rules.DecorError("That tile is not available on this server.")
    if tile["placement"] == "paint":
        raise decor_rules.DecorError("Ground is painted with the terrain brush, not placed.")
    if request.get("scope") != panel_access.SCOPE_OWNER and "admin" not in tile["access"]:
        raise decor_rules.DecorError("Server admins do not have access to that tile.")
    return tile


# --------------------------------------------------------------------------- #
#  The world, dressed by an administrator
# --------------------------------------------------------------------------- #
async def api_world_decor(request: web.Request):
    """Place, move or remove one piece of the map's own decor."""
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    body = await _body(request)
    if body is None:
        return _bad("That request could not be read.")
    action = str(body.get("action") or "place")

    try:
        if action == "remove":
            gone = bot.dodoland_decor.remove(guild.id, body.get("piece_id"))
            if gone:
                await _record_change(request, "dodoland_decor", "world", "", "removed",
                                     "DodoLand map decor removed")
            return web.json_response({"ok": True, "removed": bool(gone)})

        if action == "move":
            changed = bot.dodoland_decor.move(
                guild.id, body.get("piece_id"), x=body.get("x"), y=body.get("y"),
                scale=body.get("scale"), flip=body.get("flip"),
                scale_range=_piece_range(bot, guild, body.get("piece_id")))
            return web.json_response({"ok": True, "changed": bool(changed)})

        tile = _admin_tile(bot, guild, request, body.get("asset_id"))
        # An admin dressing the world is not spending an unlock, so no
        # ``allowed`` set is passed: the locks exist to pace what players may
        # place, and the person who wrote them is not the person they pace.
        piece = bot.dodoland_decor.place(
            guild.id, scope=decor_rules.SCOPE_WORLD,
            asset_id=tile["tile_id"], x=body.get("x"), y=body.get("y"),
            scale=body.get("scale") or 1.0, flip=bool(body.get("flip")),
            scale_range=tile_rules.scale_range(tile),
            # A placed tile is a stamp: the thing you picked is the thing that
            # lands. Variants are for painted ground, where a field must not
            # repeat; tools/dodoland_split_stamps.py made every look-alike its
            # own tile, and this keeps a stamp that gains a variant from
            # turning into a lucky dip again.
            variant=tile["variants"][0] if tile["variants"] else "",
            layer=tile["layer"])
        await _record_change(request, "dodoland_decor", "world", "", "placed",
                             "DodoLand map decor placed")
        return web.json_response({"ok": True, "piece": piece})
    except decor_rules.DecorError as error:
        return _bad(error)


# --------------------------------------------------------------------------- #
#  A town, dressed by whoever owns it
# --------------------------------------------------------------------------- #
def _unlocked(bot, guild, user_id: int) -> set:
    """Which assets this person has earned the right to place.

    Their own standing only, so this is one person's rows rather than the whole
    server's — the tier locks are per building and a person's own tiers are all
    it takes to answer.
    """
    buildings = bot.dodoland_buildings.buildings(guild.id)
    since = store_module.days_back(
        int(bot.dodoland_params.get(guild.id, "dodoland_window_days")))
    result = standing.guild_standings(
        bot.dodoland, bot.dodoland_params, guild.id, buildings,
        since=since, user_ids=[user_id],
        rows=bot.dodoland.rows(guild.id, user_id=user_id, since=since),
        pair_rows=bot.dodoland.pair_rows(guild.id, since=since),
    )
    return tile_rules.unlocked_for(_player_tiles(bot, guild),
                                   result["people"].get(int(user_id)), buildings)


def _player_tiles(bot, guild) -> list[dict]:
    """What players may place on their towns here: map objects with player
    access. Tiles nobody but admins may use are not shown locked — a lock says
    "you can earn this", and an admin-only mountain range is not earnable."""
    # Map objects (layer 3) and the server's buildings (layer 4).
    return (bot.dodoland_tiles.usable(guild.id, "objects", "player")
            + bot.dodoland_tiles.usable(guild.id, "buildings", "player"))


async def api_town_decor(request: web.Request):
    """Place, move or remove one piece in your own town.

    Whose town is the session's, never the request's. ``owner_id`` is passed to
    every write so it narrows the query rather than being checked after the
    fact: knowing another person's piece id gets you nothing.
    """
    import asyncio

    from web.dodoland import player

    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    body = await _body(request)
    if body is None:
        return _bad("That request could not be read.")
    action = str(body.get("action") or "place")

    try:
        if action == "remove":
            gone = bot.dodoland_decor.remove(guild.id, body.get("piece_id"),
                                             owner_id=uid)
            return web.json_response({"ok": True, "removed": bool(gone)})

        if action == "move":
            changed = bot.dodoland_decor.move(
                guild.id, body.get("piece_id"), x=body.get("x"), y=body.get("y"),
                scale=body.get("scale"), flip=body.get("flip"), owner_id=uid,
                scale_range=_piece_range(bot, guild, body.get("piece_id")))
            return web.json_response({"ok": True, "changed": bool(changed)})

        # Reading the library and scoring one person is blocking pymongo, and
        # this handler runs on the bot's own event loop.
        allowed = await asyncio.get_running_loop().run_in_executor(
            None, _unlocked, bot, guild, uid)
        placed = bot.dodoland_tiles.visible(body.get("asset_id"), guild.id)
        piece = bot.dodoland_decor.place(
            guild.id, scope=decor_rules.SCOPE_TOWN, owner_id=uid,
            asset_id=body.get("asset_id"), x=body.get("x"), y=body.get("y"),
            scale=body.get("scale") or 1.0, flip=bool(body.get("flip")),
            allowed=allowed,
            layer=(placed or {}).get("layer", "objects"),
            scale_range=tile_rules.scale_range(placed))
        # The map reads decor out of the shared snapshot, so a piece nobody can
        # see for a minute looks exactly like a piece that did not save.
        player.invalidate(guild.id)
        return web.json_response({"ok": True, "piece": piece})
    except decor_rules.DecorError as error:
        return _bad(error)


async def api_town_toolkit(request: web.Request):
    """What this person may place, and what they have placed already.

    Locked assets are returned too, with ``locked`` set. A reward you cannot
    see is not a reward: knowing the gilded banner exists at the third tier of
    the Gallery is the reason to want the third tier of the Gallery.
    """
    import asyncio

    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    allowed = await asyncio.get_running_loop().run_in_executor(
        None, _unlocked, bot, guild, uid)
    # Scenery is filtered out rather than shown locked: a lock says "you can
    # earn this", and a mountain range is not a thing anybody earns.
    library = _player_tiles(bot, guild)
    placed = bot.dodoland_decor.town(guild.id, uid)
    return web.json_response({
        "ok": True,
        "assets": [{"asset_id": row["tile_id"], "name": row["name"],
                    "building": row["requires"]["building"],
                    "min_tier": row["requires"]["tier"],
                    "resizable": row["resizable"],
                    "scale_min": tile_rules.scale_range(row)[0],
                    "scale_max": tile_rules.scale_range(row)[1],
                    "locked": row["tile_id"] not in allowed}
                   for row in library],
        "placed": [{"piece_id": row["piece_id"], "asset_id": row["asset_id"],
                    "x": row.get("x"), "y": row.get("y"),
                    "scale": row.get("scale", 1.0), "flip": bool(row.get("flip"))}
                   for row in placed],
        "limit": decor_rules.MAX_PER_TOWN,
    })


async def player_asset_image(request: web.Request):
    """One tile's first image, for a member's own toolkit and town.

    A **tile** id in the path, which is a library entry, not a person. The rule ``player.py`` keeps — never read a *user* id from a
    request — is about whose data is being touched, and this touches nobody's.
    It lives here rather than in ``player.py`` so that file's own guarantee
    stays checkable by grepping it for ``match_info``.
    """
    bot, guild = request.app["bot"], request["guild"]
    tile_id = request.match_info.get("aid") or ""
    row = (bot.dodoland_tiles.first_art(tile_id)
           if bot.dodoland_tiles.visible(tile_id, guild.id) else None)
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # An asset id is never reused, so a long cache is safe.
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )
