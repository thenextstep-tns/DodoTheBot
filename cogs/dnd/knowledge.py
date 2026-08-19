"""
Knowledge, lore and belief — the logic behind the P1 commands.

Kept out of ``cog.py`` so that file stays a list of command signatures rather
than a wall of rendering. The commands there are thin wrappers; everything that
decides *what* to show lives here.

The rule this module exists to enforce, from ``docs/dnd/03-KNOWLEDGE-BASE.md``
section 4:

    A player-facing view is built from that character's **beliefs**.
    A GM-facing view may read the **facts**.

They are separate functions below — :func:`player_view` and :func:`gm_view` —
rather than one function with a flag, because the flag is the thing that
eventually gets passed wrong and leaks a secret into a player's embed.
"""

from __future__ import annotations

import discord

import config_py
import lang_dnd
from helpers.dnd.world.knowledge import KINDS, Fact

# A fact is a retrievable chunk, not an essay. The cap keeps retrieval honest
# (one enormous fact would eat a whole prompt budget) and nudges a GM toward
# several small facts, which is what the scoring can actually work with.
MAX_FACT_CHARS = 1500
MAX_TITLE_CHARS = 100

_KIND_EMOJI = {
    "lore": "📜", "rule": "⚖️", "location": "🗺️", "faction": "🏴",
    "person": "👤", "item": "🗝️", "tone": "🎭", "custom": "✳️",
}


def kind_choices() -> list:
    """Autocomplete choices for a fact's kind."""
    return [discord.app_commands.Choice(name=k.title(), value=k) for k in KINDS]


# --------------------------------------------------------------------------- #
#  Lore rendering
# --------------------------------------------------------------------------- #
def _fact_line(fact: Fact, *, show_secret: bool) -> str:
    emoji = _KIND_EMOJI.get(fact.kind, "•")
    lock = " 🔒" if fact.secret and show_secret else ""
    body = fact.text if len(fact.text) <= 160 else fact.text[:157] + "…"
    return f"{emoji} **{fact.title}**{lock}\n{body}"


def lore_list(facts: list[Fact], campaign_name: str, *, show_secret: bool) -> discord.Embed:
    """The campaign's own facts. Secrets are filtered by the caller, not here —
    this only decides how to draw what it was handed."""
    embed = discord.Embed(
        title=lang_dnd.TT_LORE_LIST_TITLE.format(campaign=campaign_name),
        color=config_py.main_color,
    )
    if not facts:
        embed.description = lang_dnd.TT_LORE_EMPTY
        return embed

    by_kind: dict[str, list[Fact]] = {}
    for fact in facts:
        by_kind.setdefault(fact.kind, []).append(fact)

    for kind in sorted(by_kind):
        lines = "\n".join(_fact_line(f, show_secret=show_secret) for f in by_kind[kind][:8])
        extra = len(by_kind[kind]) - 8
        if extra > 0:
            lines += f"\n*…and {extra} more*"
        embed.add_field(
            name=f"{_KIND_EMOJI.get(kind, '•')} {kind.title()} ({len(by_kind[kind])})",
            value=lines[:1024],
            inline=False,
        )
    embed.set_footer(text=f"{len(facts)} fact(s)")
    return embed


def lore_search(facts: list[Fact], query: str, *, show_secret: bool) -> discord.Embed:
    embed = discord.Embed(
        title=lang_dnd.TT_LORE_SEARCH_TITLE.format(query=query),
        color=config_py.main_color,
    )
    if not facts:
        embed.description = lang_dnd.TT_LORE_SEARCH_EMPTY
        return embed
    embed.description = "\n\n".join(_fact_line(f, show_secret=show_secret) for f in facts[:10])
    return embed


# --------------------------------------------------------------------------- #
#  Fog of war
# --------------------------------------------------------------------------- #
def player_view(entity, scene, present, beliefs, facts) -> discord.Embed:
    """What a player sees when they look around.

    Built from *their character's* beliefs plus non-secret knowledge. This
    function is never handed a secret fact — the caller retrieves with
    ``for_player=True`` — so there is no path here that could leak one even if
    this code is wrong.
    """
    embed = discord.Embed(
        title=lang_dnd.TT_LOOK_TITLE.format(name=entity.identity.name),
        color=config_py.main_color,
    )
    if scene is not None:
        environment = " · ".join(
            p for p in (scene.time_of_day, scene.weather, scene.lighting) if p
        )
        embed.description = f"**{scene.title}**" + (f"\n{environment}" if environment else "")
        embed.add_field(
            name=lang_dnd.TT_LOOK_PRESENT,
            value=", ".join(e.identity.name for e in present if e.id != entity.id) or "Only you.",
            inline=False,
        )

    if beliefs:
        lines = "\n".join(
            f"*{b.certainty}* — {b.claim}" for b in beliefs[:8]
        )
        embed.add_field(name=lang_dnd.TT_LOOK_BELIEFS, value=lines[:1024], inline=False)

    if facts:
        lines = "\n".join(f"{_KIND_EMOJI.get(f.kind, '•')} **{f.title}** — {f.text[:120]}"
                          for f in facts[:5])
        embed.add_field(name="What you know of this place", value=lines[:1024], inline=False)

    if not beliefs and not facts and scene is None:
        embed.description = lang_dnd.TT_LOOK_NOTHING_KNOWN

    embed.set_footer(text=lang_dnd.TT_LOOK_FOOTER.format(name=entity.identity.name))
    return embed


def gm_view(entity, beliefs, *, is_gm: bool) -> discord.Embed:
    """What one entity believes.

    The GM sees the truth flag beside each belief; the holder never does. That
    asymmetry is the whole feature: an NPC confidently wrong is only interesting
    if someone at the table can see that they are wrong.
    """
    embed = discord.Embed(
        title=lang_dnd.TT_KNOWS_TITLE.format(name=entity.identity.name),
        color=config_py.main_color,
    )
    if not beliefs:
        embed.description = lang_dnd.TT_KNOWS_EMPTY.format(name=entity.identity.name)
        return embed

    lines = []
    for belief in beliefs[:15]:
        wrong = lang_dnd.TT_KNOWS_WRONG if (is_gm and belief.is_wrong()) else ""
        source = ""
        if is_gm and belief.source_kind:
            source = f" `{belief.source_kind}`"
            if belief.mutations:
                source += f" `×{belief.mutations} retold`"
        lines.append(
            lang_dnd.TT_KNOWS_LINE.format(certainty=belief.certainty, claim=belief.claim)
            + source
            + wrong
        )
    embed.description = "\n".join(lines)[:4000]
    if is_gm:
        wrong_count = sum(1 for b in beliefs if b.is_wrong())
        embed.set_footer(
            text=f"{len(beliefs)} belief(s)" + (f" · {wrong_count} false" if wrong_count else "")
        )
    return embed


def canon_queue(pending: list[dict]) -> discord.Embed:
    """Proposed canon awaiting review. Empty until the narrator ships in P4."""
    embed = discord.Embed(color=config_py.main_color)
    if not pending:
        embed.description = lang_dnd.TT_CANON_EMPTY
        return embed
    embed.title = lang_dnd.TT_CANON_TITLE.format(count=len(pending))
    embed.description = "\n\n".join(
        lang_dnd.TT_CANON_LINE.format(
            title=(p.get("proposal") or {}).get("title", "?"),
            text=((p.get("proposal") or {}).get("text", ""))[:160],
        )
        for p in pending[:10]
    )
    return embed
