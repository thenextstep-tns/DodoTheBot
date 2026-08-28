"""
DodoLand's write endpoints.

Three things can be changed: a tunable, the buildings, and the map. Each
validates through the same helper the rest of the system reads from, so a value
that reaches storage is a value the scorer can already use, and every change is
written to the config audit the way the rest of the panel's edits are.
"""

from __future__ import annotations

import base64

from aiohttp import web

from helpers.dodoland import buildings as building_rules
from helpers.dodoland import parameters as dodo_params

# An uploaded map is stored inline in the guild's config document, so it has to
# stay well under Mongo's 16MB per-document ceiling with room for everything
# else in the row. This is generous for a stylised map and mean for a photo.
MAX_MAP_BYTES = 4 * 1024 * 1024
ALLOWED_MAP_TYPES = ("image/png", "image/jpeg", "image/webp", "image/svg+xml")


def _bad(error: str, status: int = 200):
    return web.json_response({"ok": False, "error": str(error)}, status=status)


async def api_dodoland_param(request: web.Request):
    """Set one DodoLand tunable for this guild."""
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    body = await request.json()
    key, raw = body.get("key"), body.get("value")
    params = bot.dodoland_params
    try:
        old = params.get(guild.id, key)
        value = params.set(guild.id, key, raw)
    except KeyError:
        return _bad(f"Unknown setting: {key}")
    except ValueError as error:
        return _bad(error)
    await _record_change(request, "dodoland_param", str(key), old, value,
                         f"DodoLand setting {key}")
    return web.json_response({"ok": True, "value": value})


async def api_dodoland_buildings(request: web.Request):
    """Replace this guild's buildings."""
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    body = await request.json()
    try:
        saved = bot.dodoland_buildings.save_buildings(
            guild.id, body.get("buildings"), guild=guild
        )
    except building_rules.DodoLandError as error:
        return _bad(error)
    except KeyError as error:
        return _bad(f"Unknown metric: {error}")
    await _record_change(request, "dodoland_buildings", "buildings", "",
                         f"{len(saved)} buildings", "DodoLand buildings")
    return web.json_response({"ok": True, "buildings": saved})


async def api_dodoland_suggest(request: web.Request):
    """Attach each building to the channels whose names look like it.

    Only fills in buildings that have no rooms yet, so pressing it after
    hand-tuning cannot undo the tuning, and a channel is offered to at most one
    building. It is a starting guess meant to be corrected, the same bargain
    "Suggest from role names" makes on the trials page.
    """
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    current = bot.dodoland_buildings.buildings(guild.id)
    suggested = building_rules.suggest_channels(guild, current)
    try:
        saved = bot.dodoland_buildings.save_buildings(guild.id, suggested, guild=guild)
    except building_rules.DodoLandError as error:
        return _bad(error)
    attached = sum(len(building.get("channels") or {}) for building in saved)
    await _record_change(request, "dodoland_buildings", "suggest", "",
                         f"{attached} rooms attached", "DodoLand rooms suggested")
    return web.json_response({"ok": True, "attached": attached,
                              "buildings": len(saved)})


async def api_dodoland_settle(request: web.Request):
    """Place one town on the map, in percentages of the base image.

    Re-settling moves a town rather than making a second one: a person has one
    town per server, which is what makes the map readable at a glance.
    """
    bot, guild = request.app["bot"], request["guild"]
    body = await request.json()
    try:
        user_id = int(body.get("user_id") or 0)
        x, y = float(body.get("x")), float(body.get("y"))
    except (TypeError, ValueError):
        return _bad("A town needs a person and a position.")
    if not user_id:
        return _bad("A town needs a person.")
    spot = bot.dodoland_buildings.settle(guild.id, user_id, x, y)
    return web.json_response({"ok": True, **spot})


async def api_dodoland_backfill(request: web.Request):
    """Rebuild the archivable history from the message archive.

    Reads the whole archive for this guild's channels, so it runs in an executor:
    the panel is served from inside the bot process and doing this on the event
    loop would stop the bot answering Discord for the duration.

    ``preview`` aggregates and reports without writing anything, which is how to
    look at it before letting it near real rows.
    """
    import asyncio

    import config_py
    from helpers.dodoland import backfill as backfill_rules
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    body = await request.json()
    dry_run = bool(body.get("preview"))

    def work():
        return backfill_rules.run(bot, guild, archive=config_py.messages, dry_run=dry_run)

    try:
        result = await asyncio.get_running_loop().run_in_executor(None, work)
    except Exception as error:
        return _bad(f"The backfill failed: {error}")

    if not dry_run:
        await _record_change(
            request, "dodoland_backfill", "archive", "",
            f"{result['written']} rows from {result['messages']} messages",
            "DodoLand history rebuilt from the message archive",
        )
    return web.json_response({"ok": True, **result})


async def api_dodoland_map(request: web.Request):
    """Store (or clear) the uploaded base map for this server's continent.

    The map is an image an admin drew or commissioned, not something generated.
    That was a deliberate simplification: it removes the vector editor, the
    procedural coastlines and the elevation polygons from the build entirely,
    and it gets a handcrafted world in on day one instead of never.
    """
    from web.routes import _record_change

    bot, guild = request.app["bot"], request["guild"]
    body = await request.json()

    if not body.get("data"):
        bot.dodoland_buildings.save_map(guild.id, None)
        await _record_change(request, "dodoland_map", "map", "set", "cleared",
                             "DodoLand map removed")
        return web.json_response({"ok": True, "cleared": True})

    content_type = str(body.get("content_type") or "").lower()
    if content_type not in ALLOWED_MAP_TYPES:
        return _bad("The map must be a PNG, JPEG, WebP or SVG.")
    try:
        blob = base64.b64decode(str(body["data"]).split(",")[-1], validate=True)
    except Exception:
        return _bad("That upload could not be read.")
    if not blob:
        return _bad("That file is empty.")
    if len(blob) > MAX_MAP_BYTES:
        return _bad(f"The map must be under {MAX_MAP_BYTES // (1024 * 1024)}MB.")

    bot.dodoland_buildings.save_map(
        guild.id, {"data": blob, "content_type": content_type,
                   "width": int(body.get("width") or 0),
                   "height": int(body.get("height") or 0)},
    )
    await _record_change(request, "dodoland_map", "map", "", f"{len(blob)} bytes",
                         "DodoLand map uploaded")
    return web.json_response({"ok": True, "bytes": len(blob)})
