"""
Who may see and edit a campaign on the panel.

``helpers/panel_access.py`` answers "how much of this **server** do you see?" —
one scope per guild, ordered ``none < stats < config < full < owner``. A campaign
GM is a different kind of person: they need complete control of *their campaign*
and no authority over the server at all.

Rather than overload ``PanelAccessManager`` with per-object ownership (which
would make both questions harder to reason about), this resolves a **campaign
scope** that consults it:

    gm      — a GM of this campaign, or anyone with server-level ``full``
    player  — in the campaign's player list
    none    — everyone else

Server admins count as GMs deliberately: a campaign whose GM leaves the server
would otherwise be unreachable, with no way to promote anyone.
"""

from __future__ import annotations

from helpers import panel_access

CAMPAIGN_NONE = "none"
CAMPAIGN_PLAYER = "player"
CAMPAIGN_GM = "gm"

_ORDER = {CAMPAIGN_NONE: 0, CAMPAIGN_PLAYER: 1, CAMPAIGN_GM: 2}


def at_least(scope: str, minimum: str) -> bool:
    return _ORDER.get(scope, 0) >= _ORDER.get(minimum, 0)


def campaign_scope(campaign, user_id: int, guild_scope: str) -> str:
    """This user's scope in one campaign."""
    if campaign is None:
        return CAMPAIGN_NONE
    if panel_access.at_least(guild_scope, panel_access.SCOPE_FULL):
        return CAMPAIGN_GM
    if campaign.is_gm(user_id):
        return CAMPAIGN_GM
    if campaign.is_player(user_id):
        return CAMPAIGN_PLAYER
    return CAMPAIGN_NONE


def visible_campaigns(campaigns: list, user_id: int, guild_scope: str) -> list:
    """The campaigns this user may see, with their scope in each.

    Returns ``[(campaign, scope)]``. Someone with server-level ``full`` sees
    every campaign; everyone else sees only the ones they are in — a server
    member with no involvement has no business reading another group's notes.
    """
    out = []
    for campaign in campaigns:
        scope = campaign_scope(campaign, user_id, guild_scope)
        if scope != CAMPAIGN_NONE:
            out.append((campaign, scope))
    return out
