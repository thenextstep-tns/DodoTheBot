"""
DodoLand panel routes.

Mounted from ``web/routes.py:create_app`` with a function-level import, so this
package can import the shared chrome from ``routes`` without closing an import
cycle at module load. Same arrangement as ``web/dnd``, and for the same reason:
``web/routes.py`` is already too long to take a whole subsystem's pages.

Everything here is **owner and admin scoped**. DodoLand computes standings for
every member of a server, and until the map is public that preview is exactly
the sort of thing that should not leak: it ranks people who never asked to be
ranked and were never told they were being counted.
"""

from __future__ import annotations

from aiohttp import web


def dodoland_routes() -> list:
    """Route table for the DodoLand pages."""
    from helpers import panel_access
    from web.dodoland.api import (
        api_dodoland_backfill, api_dodoland_buildings, api_dodoland_map,
        api_dodoland_param, api_dodoland_settle, api_dodoland_suggest,
    )
    from web.dodoland.pages import dodoland_page
    from web.dodoland.settle import api_settle_own, settle_page
    from web.routes import require_scope

    # Reading the page means reading everybody's standing, so it takes the same
    # scope the settings page does rather than the softer stats scope.
    configure = require_scope(panel_access.SCOPE_CONFIG)
    full = require_scope(panel_access.SCOPE_FULL)
    return [
        web.get("/guild/{gid}/dodoland", configure(dodoland_page)),
        web.post("/api/guild/{gid}/dodoland/param", full(api_dodoland_param)),
        web.post("/api/guild/{gid}/dodoland/buildings", full(api_dodoland_buildings)),
        web.post("/api/guild/{gid}/dodoland/map", full(api_dodoland_map)),
        # Rewrites historical rows, so it takes the highest scope on the page.
        web.post("/api/guild/{gid}/dodoland/backfill", full(api_dodoland_backfill)),
        # Moving somebody's town is configuration, not a game action yet.
        web.post("/api/guild/{gid}/dodoland/settle", full(api_dodoland_settle)),
        web.post("/api/guild/{gid}/dodoland/suggest", full(api_dodoland_suggest)),
        # The player's own link. No scope decorator on purpose: there is no
        # session here, the token in the path IS the credential, and it names
        # exactly one person whose only power is to move their own town.
        web.get("/t/{gid}/{token}", settle_page),
        web.post("/t/{gid}/{token}/settle", api_settle_own),
    ]
