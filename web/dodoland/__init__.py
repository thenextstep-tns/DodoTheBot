"""
DodoLand panel routes.

Mounted from ``web/routes.py:create_app`` with a function-level import, so this
package can import the shared chrome from ``routes`` without closing an import
cycle at module load.

**Every route is gated, and there are exactly two kinds of gate.**

``configure``/``full`` are the panel's scopes: an administrator acting on a whole
server, which is why those handlers take a user id — they are legitimately
working on other people's towns.

``player`` is ``web/dodoland/player.py``'s own gate: signed in with Discord,
still a member of that guild right now, and the server has switched this surface
on. **A player handler never reads a user id from the request** — not from the
path, the query or the body — so there is nothing to tamper with. That property
is what a public map link and a capability URL could not offer, which is why
both were built here and removed again.
"""

from __future__ import annotations

from aiohttp import web


def dodoland_routes() -> list:
    """Route table for the DodoLand pages."""
    from helpers import panel_access
    from web.dodoland.api import (
        api_dodoland_asset, api_dodoland_backfill, api_dodoland_buildings,
        api_dodoland_map, api_dodoland_param, api_dodoland_settle,
        api_dodoland_suggest, api_dodoland_town,
    )
    from web.dodoland.assets_route import (
        asset_image, town_art, town_picture,
    )
    from web.dodoland import player
    from web.dodoland.decor_api import (
        api_town_decor, api_town_toolkit, api_world_decor,
        player_asset_image,
    )
    from web.dodoland.mappage import map_page
    from web.dodoland.pages import dodoland_page
    from web.routes import require_scope

    # Reading the page means reading everybody's standing, so it takes the same
    # scope the settings page does rather than the softer stats scope.
    configure = require_scope(panel_access.SCOPE_CONFIG)
    full = require_scope(panel_access.SCOPE_FULL)
    return [
        web.get("/guild/{gid}/dodoland", configure(dodoland_page)),
        # The map deserves the whole window, so it is its own page.
        web.get("/guild/{gid}/dodoland/map", configure(map_page)),
        web.get("/guild/{gid}/dodoland/asset/{aid}", configure(asset_image)),
        web.get("/guild/{gid}/dodoland/town/{uid}/picture", configure(town_picture)),
        # Drawn on demand, so the map ships no artwork it may never show.
        web.get("/guild/{gid}/dodoland/town/{uid}/art", configure(town_art)),
        web.post("/api/guild/{gid}/dodoland/param", full(api_dodoland_param)),
        web.post("/api/guild/{gid}/dodoland/buildings", full(api_dodoland_buildings)),
        web.post("/api/guild/{gid}/dodoland/map", full(api_dodoland_map)),
        web.post("/api/guild/{gid}/dodoland/asset", full(api_dodoland_asset)),
        web.post("/api/guild/{gid}/dodoland/suggest", full(api_dodoland_suggest)),
        # Moving somebody's town is configuration while there is no player-facing
        # way for them to move it themselves.
        web.post("/api/guild/{gid}/dodoland/settle", full(api_dodoland_settle)),
        # Names, descriptions and pictures. Authored, never scored.
        web.post("/api/guild/{gid}/dodoland/town", full(api_dodoland_town)),
        # Rewrites historical rows, so it takes the highest scope on the page.
        web.post("/api/guild/{gid}/dodoland/backfill", full(api_dodoland_backfill)),
        # --- the player front end ----------------------------------------- #
        # Its gate lives in player.py and is applied by the handlers themselves,
        # because it has to answer three questions the panel's scopes do not:
        # is this person still in the guild, has this server switched the
        # surface on, and — for settling — is it the kind that lets a member
        # place their own town. None of these take a user id.
        web.get("/guild/{gid}/dodoland/me", player.my_town_page),
        web.get("/guild/{gid}/dodoland/me/picture", player.my_picture),
        web.post("/api/guild/{gid}/dodoland/me/town", player.api_my_town),
        web.post("/api/guild/{gid}/dodoland/me/settle", player.api_my_settle),
        # The toolkit. An admin dresses the map; a member dresses their own
        # town and only their own — the handler never reads a user id from the
        # request, and the tier locks are enforced there rather than in the UI.
        web.post("/api/guild/{gid}/dodoland/decor", full(api_world_decor)),
        web.get("/api/guild/{gid}/dodoland/me/toolkit",
                player.require_town(api_town_toolkit)),
        web.post("/api/guild/{gid}/dodoland/me/decor",
                 player.require_town(api_town_decor)),
        web.get("/guild/{gid}/dodoland/me/asset/{aid}",
                player.require_town(player_asset_image)),
        # Not under /guild/{gid}: it is the page that tells somebody which
        # guilds they have a town in, so it cannot already know one.
        web.get("/towns", player.towns_home),
    ]
