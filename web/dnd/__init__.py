"""
Tabletop panel routes.

Mounted from ``web/routes.py:create_app`` with a function-level import, so this
package can import the shared chrome from ``routes`` without a circular import at
module load.

Access is two-layered: :func:`require_scope` gates the guild (a viewer must have
at least ``stats`` on the server), and then the per-campaign scope in
``web/dnd/access.py`` decides which campaigns they actually see. Server-level
access is not campaign-level access — being able to read a server's stats does
not entitle you to another group's game.
"""

from __future__ import annotations

from aiohttp import web


def dnd_routes() -> list:
    """Route table for the Tabletop pages."""
    from helpers import panel_access
    from web.dnd.api import (
        api_dnd_canon,
        api_dnd_cog,
        api_dnd_lore,
        api_dnd_param,
        api_dnd_tune,
    )
    from web.dnd.pages import campaign_page, entity_page, tabletop_page
    from web.routes import require_scope

    # Pages are stats-scoped so players can see their own campaign; which
    # campaigns they actually get is decided per campaign in web/dnd/access.py.
    view = require_scope(panel_access.SCOPE_STATS)
    # Engine settings change server configuration, so they need the same scope
    # the general settings page does.
    configure = require_scope(panel_access.SCOPE_FULL)
    return [
        web.get("/guild/{gid}/tabletop", view(tabletop_page)),
        web.get("/guild/{gid}/tabletop/{cid}", view(campaign_page)),
        # The inspector is GM-only, enforced inside the handler.
        web.get("/guild/{gid}/tabletop/{cid}/entity/{eid}", view(entity_page)),
        web.post("/api/guild/{gid}/dnd/param", configure(api_dnd_param)),
        web.post("/api/guild/{gid}/dnd/cog", configure(api_dnd_cog)),
        # Lore and canon are gated per campaign inside the handler, so a GM who
        # is not a server admin can still run their own game.
        web.post("/api/guild/{gid}/dnd/lore", view(api_dnd_lore)),
        web.post("/api/guild/{gid}/dnd/canon", view(api_dnd_canon)),
        web.post("/api/guild/{gid}/dnd/tune", view(api_dnd_tune)),
    ]
