"""
Working out which campaign a command means.

Most servers will run one campaign and nobody should have to name it every time
they roll a die. But the data model is multi-tenant from the first commit, so
"the campaign" is never assumed — it is *resolved*, in a fixed order, and the
command says so plainly when it can't be.

Resolution order, most specific first:

1. an explicit name, when the command took one;
2. the campaign bound to this channel (or to the scene open in it);
3. the single campaign this user belongs to, if there is exactly one.

If none of those answer, the caller is asked to name it. Guessing between two
campaigns is worse than a question: it writes an event into the wrong world's
log, and the event log is the one thing that must never be wrong.
"""

from __future__ import annotations

from typing import Optional

import discord

import lang_dnd
from helpers.dnd.store import CampaignStore, campaign_store, campaigns_for
from helpers.dnd.world.campaign import Campaign


class Resolved:
    """A resolved campaign plus its store, or the reason there isn't one."""

    __slots__ = ("campaign", "store", "error")

    def __init__(
        self,
        campaign: Optional[Campaign] = None,
        store: Optional[CampaignStore] = None,
        error: str = "",
    ) -> None:
        self.campaign = campaign
        self.store = store
        self.error = error

    def __bool__(self) -> bool:
        return self.campaign is not None


def _store_for(campaign: Campaign) -> CampaignStore:
    return campaign_store(campaign.guild_id, campaign.id)


def resolve(interaction: discord.Interaction, name: str | None = None) -> Resolved:
    """Resolve the campaign a command refers to. Never raises."""
    if interaction.guild_id is None:
        return Resolved(error=lang_dnd.TT_NEEDS_GUILD)

    repo = campaigns_for(interaction.guild_id)

    # 1. Named explicitly.
    if name:
        campaign = repo.by_name(name)
        if campaign is None:
            return Resolved(error=lang_dnd.TT_CAMPAIGN_NOT_FOUND.format(name=name))
        return Resolved(campaign, _store_for(campaign))

    # 2. Bound to this channel. A scene thread's parent counts, so rolling
    #    inside a scene works without naming anything.
    channel = interaction.channel
    channel_ids = [interaction.channel_id]
    parent_id = getattr(channel, "parent_id", None)
    if parent_id:
        channel_ids.append(parent_id)
    for channel_id in channel_ids:
        if not channel_id:
            continue
        campaign = repo.by_channel(channel_id)
        if campaign is not None:
            return Resolved(campaign, _store_for(campaign))

    # 3. The only campaign this person is in.
    mine = repo.for_member(interaction.user.id)
    if len(mine) == 1:
        return Resolved(mine[0], _store_for(mine[0]))
    if not mine:
        return Resolved(error=lang_dnd.TT_NO_CAMPAIGN)

    names = ", ".join(f"**{c.name}**" for c in mine)
    return Resolved(error=f"You're in several campaigns ({names}) — name the one you mean.")


def require_gm(campaign: Campaign, user: discord.abc.User, *, is_admin: bool = False) -> str:
    """``""`` if this user may act as GM, otherwise the refusal to show.

    Server admins count as GMs so a campaign is never orphaned when its GM
    leaves — someone with Manage Server can always pick it back up.
    """
    if is_admin or campaign.is_gm(user.id):
        return ""
    return lang_dnd.TT_NOT_GM.format(name=campaign.name)


def is_guild_admin(interaction: discord.Interaction) -> bool:
    """Manage Server, guild owner, or a bot owner — via the existing manager."""
    perms = getattr(interaction.user, "guild_permissions", None)
    has_manage = bool(interaction.guild_id and perms and perms.manage_guild)
    visibility = getattr(interaction.client, "visibility", None)
    if visibility is None:
        return has_manage
    return visibility.is_guild_admin(
        interaction.guild_id, interaction.user.id, has_manage_guild=has_manage
    )
