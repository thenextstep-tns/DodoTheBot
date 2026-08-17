"""
Embed rendering for the Tabletop surface.

Rendering is kept away from command logic for the reason given in
``docs/dnd/04-ENTITIES.md`` §8: a sheet is a *render of an entity for an
audience*, and there will soon be several audiences (the player, another player,
the GM, the simulation). Keeping the render in one place means adding the GM's
view later is a new function here rather than a branch inside a command.

Stat fields come from the **ruleset**, never from this module. A 5e sheet and a
freeform sheet are the same code path with different `sheet_fields`.
"""

from __future__ import annotations

import discord

import config_py
import lang
from helpers.dnd import rules
from helpers.dnd.rules.ruleset import COST, FAIL, SUCCESS, TRIUMPH
from helpers.dnd.world.campaign import Campaign
from helpers.dnd.world.entity import Entity
from helpers.dnd.world.scene import Scene

# Degree → colour. Green for clean success, amber for "yes, but", red for
# failure: the mechanical result should be readable before the text is.
_DEGREE_COLOURS = {
    FAIL: 0xE74C3C,
    COST: 0xE67E22,
    SUCCESS: 0x2ECC71,
    TRIUMPH: 0x1ABC9C,
}

_DEGREE_LABELS = {
    FAIL: "Fail",
    COST: "Success at a cost",
    SUCCESS: "Success",
    TRIUMPH: "Triumph",
}


def character_sheet(entity: Entity, campaign: Campaign) -> discord.Embed:
    """A character sheet, as its own player sees it."""
    ruleset = rules.get(campaign.ruleset)
    identity = entity.identity

    subtitle = " · ".join(part for part in (identity.role, identity.species, identity.pronouns) if part)
    embed = discord.Embed(
        title=identity.name,
        description=subtitle or None,
        color=config_py.main_color,
    )

    for label, value in ruleset.sheet_fields(entity.stats):
        embed.add_field(name=label, value=value, inline=True)

    if entity.conditions:
        embed.add_field(name="Conditions", value=", ".join(entity.conditions), inline=False)
    if entity.inventory:
        carried = ", ".join(
            f"{item.get('item', '?')}" + (f" ×{item['qty']}" if item.get("qty", 1) > 1 else "")
            for item in entity.inventory[:12]
        )
        embed.add_field(name="Carried", value=carried, inline=False)
    if identity.appearance:
        embed.add_field(name="Appearance", value=identity.appearance[:1024], inline=False)

    if entity.retired:
        embed.set_footer(text=f"Retired · {ruleset.label} · {campaign.name}")
    else:
        embed.set_footer(text=lang.TT_SHEET_FOOTER.format(ruleset=ruleset.label, campaign=campaign.name))
    return embed


def campaign_info(campaign: Campaign, *, characters: int, scenes: int) -> discord.Embed:
    """The campaign's own card."""
    ruleset = rules.get(campaign.ruleset)
    embed = discord.Embed(
        title=campaign.name,
        description=campaign.settings.get("tone") or None,
        color=config_py.main_color,
    )
    embed.add_field(name="Ruleset", value=ruleset.label, inline=True)
    embed.add_field(name="Status", value=campaign.status, inline=True)
    embed.add_field(name="Characters", value=str(characters), inline=True)
    embed.add_field(
        name="GMs",
        value=", ".join(f"<@{uid}>" for uid in campaign.gm_ids) or "—",
        inline=False,
    )
    embed.add_field(
        name="Players",
        value=", ".join(f"<@{uid}>" for uid in campaign.player_ids) or "—",
        inline=False,
    )
    if scenes:
        embed.add_field(name="Scenes", value=str(scenes), inline=True)
    # World time is minutes since the campaign epoch; days are the unit a table
    # actually thinks in.
    embed.set_footer(text=f"Day {campaign.world_time // 1440 + 1} · {campaign.seq} events recorded")
    return embed


def scene_card(scene: Scene, campaign: Campaign, present: list[Entity]) -> discord.Embed:
    """The pinned card at the top of a scene thread, edited in place as the
    scene changes."""
    embed = discord.Embed(
        title=scene.title,
        color=config_py.main_color,
    )
    environment = " · ".join(p for p in (scene.time_of_day, scene.weather, scene.lighting) if p)
    if environment:
        embed.add_field(name="Where & when", value=environment, inline=False)
    embed.add_field(
        name="Present",
        value=", ".join(e.identity.name for e in present) or "Nobody yet",
        inline=False,
    )
    embed.set_footer(text=f"{campaign.name} · {'open' if scene.is_open else 'closed'}")
    return embed


def roll_result(expression: str, roll, *, author: str) -> discord.Embed:
    """A bare dice roll — no resolution attached."""
    embed = discord.Embed(
        title=lang.TT_ROLL_RESULT.format(expr=expression, total=roll.total),
        description=roll.breakdown(),
        color=config_py.main_color,
    )
    embed.set_author(name=author)
    return embed


def check_result(entity: Entity, outcome, campaign: Campaign) -> discord.Embed:
    """A resolved check.

    The mechanical outcome is the whole embed on purpose. Prose arrives later
    from a renderer (P4) and may never arrive at all if no model is reachable —
    so what the table sees first has to stand on its own
    (``docs/dnd/08-LLM-LAYER.md`` §8).
    """
    embed = discord.Embed(
        title=f"{entity.identity.name} — {_DEGREE_LABELS.get(outcome.degree, outcome.degree)}",
        description=outcome.summary,
        color=_DEGREE_COLOURS.get(outcome.degree, config_py.main_color),
    )
    if outcome.roll is not None:
        embed.add_field(name="Roll", value=outcome.roll.breakdown(), inline=True)
        embed.add_field(name="Total", value=str(outcome.roll.total), inline=True)
    embed.add_field(name="DC", value=str(outcome.dc), inline=True)
    embed.set_footer(text=f"{rules.get(campaign.ruleset).label} · {campaign.name}")
    return embed


def campaign_list(campaigns: list, counts: dict) -> discord.Embed:
    """All campaigns on a server."""
    embed = discord.Embed(title=lang.TT_CAMPAIGN_LIST_TITLE, color=config_py.main_color)
    if not campaigns:
        embed.description = lang.TT_CAMPAIGN_LIST_EMPTY
        return embed
    embed.description = "\n".join(
        lang.TT_CAMPAIGN_LIST_LINE.format(
            name=c.name,
            ruleset=rules.get(c.ruleset).label,
            players=len(c.player_ids),
            status=c.status,
        )
        for c in campaigns
    )
    return embed
