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

from helpers.dodoland import assets as asset_rules
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
                scale=body.get("scale"), flip=body.get("flip"))
            return web.json_response({"ok": True, "changed": bool(changed)})

        # An admin dressing the world is not spending an unlock, so no
        # ``allowed`` set is passed: the locks exist to pace what players may
        # place, and the person who wrote them is not the person they pace.
        piece = bot.dodoland_decor.place(
            guild.id, scope=decor_rules.SCOPE_WORLD,
            asset_id=body.get("asset_id"), x=body.get("x"), y=body.get("y"),
            scale=body.get("scale") or 1.0, flip=bool(body.get("flip")))
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
    library = bot.dodoland_assets.list(guild.id)
    return asset_rules.unlocked_for(library, result["people"].get(int(user_id)))


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
                scale=body.get("scale"), flip=body.get("flip"), owner_id=uid)
            return web.json_response({"ok": True, "changed": bool(changed)})

        # Reading the library and scoring one person is blocking pymongo, and
        # this handler runs on the bot's own event loop.
        allowed = await asyncio.get_running_loop().run_in_executor(
            None, _unlocked, bot, guild, uid)
        piece = bot.dodoland_decor.place(
            guild.id, scope=decor_rules.SCOPE_TOWN, owner_id=uid,
            asset_id=body.get("asset_id"), x=body.get("x"), y=body.get("y"),
            scale=body.get("scale") or 1.0, flip=bool(body.get("flip")),
            allowed=allowed)
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
    library = bot.dodoland_assets.list(guild.id)
    placed = bot.dodoland_decor.town(guild.id, uid)
    return web.json_response({
        "ok": True,
        "assets": [{"asset_id": row["asset_id"], "name": row.get("name") or "",
                    "building": row.get("building") or "",
                    "min_tier": int(row.get("min_tier") or 0),
                    "locked": row["asset_id"] not in allowed}
                   for row in library],
        "placed": [{"piece_id": row["piece_id"], "asset_id": row["asset_id"],
                    "x": row.get("x"), "y": row.get("y"),
                    "scale": row.get("scale", 1.0), "flip": bool(row.get("flip"))}
                   for row in placed],
        "limit": decor_rules.MAX_PER_TOWN,
    })


async def player_asset_image(request: web.Request):
    """One library asset's bytes, for a member's own toolkit.

    An **asset** id in the path, which is a server-owned library entry, not a
    person. The rule ``player.py`` keeps — never read a *user* id from a
    request — is about whose data is being touched, and this touches nobody's.
    It lives here rather than in ``player.py`` so that file's own guarantee
    stays checkable by grepping it for ``match_info``.
    """
    bot, guild = request.app["bot"], request["guild"]
    row = bot.dodoland_assets.get(guild.id, request.match_info.get("aid") or "")
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # An asset id is never reused, so a long cache is safe.
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )
