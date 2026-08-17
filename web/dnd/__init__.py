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
    from web.dnd.pages import campaign_page, tabletop_page
    from web.routes import require_scope

    gate = require_scope(panel_access.SCOPE_STATS)
    return [
        web.get("/guild/{gid}/tabletop", gate(tabletop_page)),
        web.get("/guild/{gid}/tabletop/{cid}", gate(campaign_page)),
    ]
