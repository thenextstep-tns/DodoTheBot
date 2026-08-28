"""
DodoLand panel routes.

Mounted from ``web/routes.py:create_app`` with a function-level import, so this
package can import the shared chrome from ``routes`` without closing an import
cycle at module load.

**Everything here is admin-scoped, and that is the current design rather than an
oversight.** DodoLand computes standings for every member of a server, and until
there is a proper front end — a Discord login, and an account that can manage
its own town — none of it should be reachable by the people it ranks. A public
map link, a per-player settle page and a ``/town`` command were all built and
then deliberately removed: a half-finished thing behind a URL somebody can paste
is worse than no thing at all.
"""

from __future__ import annotations

from aiohttp import web


def dodoland_routes() -> list:
    """Route table for the DodoLand pages."""
    from helpers import panel_access
    from web.dodoland.api import (
        api_dodoland_asset, api_dodoland_backfill, api_dodoland_buildings,
        api_dodoland_map, api_dodoland_param, api_dodoland_settle,
        api_dodoland_suggest,
    )
    from web.dodoland.assets_route import asset_image
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
        web.post("/api/guild/{gid}/dodoland/param", full(api_dodoland_param)),
        web.post("/api/guild/{gid}/dodoland/buildings", full(api_dodoland_buildings)),
        web.post("/api/guild/{gid}/dodoland/map", full(api_dodoland_map)),
        web.post("/api/guild/{gid}/dodoland/asset", full(api_dodoland_asset)),
        web.post("/api/guild/{gid}/dodoland/suggest", full(api_dodoland_suggest)),
        # Moving somebody's town is configuration while there is no player-facing
        # way for them to move it themselves.
        web.post("/api/guild/{gid}/dodoland/settle", full(api_dodoland_settle)),
        # Rewrites historical rows, so it takes the highest scope on the page.
        web.post("/api/guild/{gid}/dodoland/backfill", full(api_dodoland_backfill)),
    ]
