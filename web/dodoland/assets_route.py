"""
Serving an uploaded asset's bytes to the panel.

This is all that remains of DodoLand's outward-facing surface, and it is
deliberately small. The public map, the per-player settle page and the ``/town``
command were built and then removed: none of DodoLand is ready to be seen by the
server, and a half-finished thing behind a link somebody can paste is worse than
no thing at all. When it is ready it gets a proper front end with a Discord
login and an account that can manage its own stuff, not a capability URL.

The route is panel-scoped like every other DodoLand route, so an asset is
readable by the same people who can already read the page it appears on.
"""

from __future__ import annotations

from aiohttp import web


async def asset_image(request: web.Request):
    """One asset's bytes, for the library and the toolkit strip."""
    bot = request.app["bot"]
    guild = request["guild"]
    row = bot.dodoland_assets.get(guild.id, request.match_info.get("aid") or "")
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # An asset id is never reused, so a long cache is safe and keeps a
        # library of fifty icons from being refetched on every page load.
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )
