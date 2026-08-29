"""
Rendering for the minds surface — NPCs, memory, relationships.

Separate from ``embeds.py`` so the P0/P1 rendering stays readable, and separate
from ``cog.py`` so the commands stay a list of signatures.

The guiding rule for everything here: **show the working**. A GM looking at an
NPC's memory should be able to see not just that something faded but *why* — how
much it mattered, whose head it is in, and whether that character's values were
holding on to it. A number without a reason is not inspectable.
"""

from __future__ import annotations

import discord

import config_py
import lang_dnd
from helpers.dnd.mind.needs import NEED_LABELS
from helpers.dnd.mind.traits import DRIVES, TEMPERAMENT, TRAIT_LABELS
from helpers.dnd.world.memory import TIER_IMPRINT, TIER_LONG, TIER_MID, TIER_WORKING

# Clarity bar for a memory field. Eight steps is enough to read at a glance and
# short enough to fit several on one embed line.
_BAR = "▰"
_EMPTY = "▱"
_BAR_WIDTH = 8

_TIER_ORDER = (TIER_IMPRINT, TIER_LONG, TIER_MID, TIER_WORKING)
_TIER_LABELS = {
    TIER_IMPRINT: "⚡ Imprints (never fade)",
    TIER_LONG: "Long-term",
    TIER_MID: "This arc",
    TIER_WORKING: "Right now",
}


def bar(value: float, width: int = _BAR_WIDTH) -> str:
    filled = max(0, min(width, round(value * width)))
    return _BAR * filled + _EMPTY * (width - filled)


def axis_bar(value: float, low: float = -1.0, high: float = 1.0) -> str:
    """A bar for an axis that may be negative, normalised to 0..1."""
    return bar((value - low) / (high - low))


# --------------------------------------------------------------------------- #
#  NPCs
# --------------------------------------------------------------------------- #
def npc_list(entities: list, campaign_name: str) -> discord.Embed:
    embed = discord.Embed(
        title=lang_dnd.TT_NPC_LIST_TITLE.format(campaign=campaign_name),
        color=config_py.main_color,
    )
    if not entities:
        embed.description = lang_dnd.TT_NPC_LIST_EMPTY
        return embed

    from helpers.dnd.mind.traits import Traits

    lines = []
    for entity in entities[:25]:
        traits = Traits.from_doc(entity.traits)
        lines.append(
            lang_dnd.TT_NPC_LIST_LINE.format(
                name=entity.identity.name,
                role=entity.identity.role or "—",
                traits=traits.describe(),
            )
        )
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(entities)} NPC(s)")
    return embed


def mind_view(entity, traits, needs, memories, impulses, relations, *, tuning, explain=None) -> discord.Embed:
    """The full inside of someone's head, for a GM.

    The one screen that shows this is a simulation and not a prop.
    """
    embed = discord.Embed(
        title=lang_dnd.TT_MIND_TITLE.format(name=entity.identity.name),
        description=traits.describe(),
        color=config_py.main_color,
    )

    # --- disposition ---
    temperament = "\n".join(
        f"`{axis_bar(traits.axis(a))}` {TRAIT_LABELS[a]} {traits.axis(a):+.2f}"
        for a in TEMPERAMENT
    )
    drives = "\n".join(
        f"`{bar(traits.axis(a))}` {TRAIT_LABELS[a]} {traits.axis(a):.2f}"
        for a in DRIVES
    )
    embed.add_field(name=lang_dnd.TT_MIND_TRAITS, value=temperament, inline=True)
    embed.add_field(name="Drives", value=drives, inline=True)

    # --- body ---
    pressing = needs.pressing(tuning.needs()) if hasattr(needs, "pressing") else []
    if pressing:
        body = "\n".join(
            f"`{bar(needs.value(n))}` {NEED_LABELS[n]} (urgency {u:.2f})"
            for n, u in pressing[:4]
        )
    else:
        body = "Comfortable."
    embed.add_field(name=lang_dnd.TT_MIND_NEEDS, value=body, inline=False)

    if impulses:
        embed.add_field(
            name=lang_dnd.TT_MIND_IMPULSES,
            value=", ".join(f"**{i.kind}** ({i.strength:.2f})" for i in impulses[:5]),
            inline=False,
        )

    # --- memory, grouped by tier ---
    by_tier: dict = {}
    for memory in memories:
        by_tier.setdefault(memory.tier, []).append(memory)

    if not memories:
        embed.add_field(name=lang_dnd.TT_MIND_MEMORY, value=lang_dnd.TT_MIND_NO_MEMORIES, inline=False)
    else:
        for tier in _TIER_ORDER:
            entries = by_tier.get(tier)
            if not entries:
                continue
            entries.sort(key=lambda m: -m.salience)
            lines = []
            for memory in entries[:5]:
                lines.append(_memory_line(memory, explain))
            embed.add_field(
                name=f"{_TIER_LABELS[tier]} ({len(entries)})",
                value="\n".join(lines)[:1024],
                inline=False,
            )

    # --- relationships ---
    if relations:
        embed.add_field(
            name=lang_dnd.TT_MIND_RELATIONS,
            value="\n".join(
                f"**{name}** — {rel.summary()}" for name, rel in relations[:8]
            )[:1024],
            inline=False,
        )

    counts = ", ".join(f"{len(v)} {k}" for k, v in by_tier.items()) or "no memories"
    embed.set_footer(
        text=lang_dnd.TT_MIND_FOOTER.format(
            retention=f"{traits.retention:.2f}", counts=counts
        )
    )
    return embed


def _memory_line(memory, explain=None) -> str:
    """One memory, with its clarity shown per field and its reason for sticking.

    Confabulated fields are flagged, because a GM needs to know the NPC is about
    to say something confidently wrong.
    """
    head = f"**{memory.describe()}**"
    clarity = " ".join(
        f"{f[0].upper()}`{bar(memory.fidelity.get(f, 1.0), 4)}`"
        for f in ("gist", "valence", "participants", "details", "when")
    )
    bits = [f"salience {memory.salience:.2f}", memory.feels]
    if memory.recall_count:
        bits.append(f"recalled ×{memory.recall_count}")
    if memory.confabulated:
        bits.append("⚠️ misremembers " + "/".join(memory.confabulated))
    if explain:
        reason = explain(memory)
        if reason:
            bits.append(reason)
    return f"{head}\n{clarity}\n*{' · '.join(bits)}*"


def recall_view(entity, memories, imprint=None) -> discord.Embed:
    embed = discord.Embed(
        title=lang_dnd.TT_RECALL_TITLE.format(name=entity.identity.name),
        color=config_py.main_color,
    )
    if imprint is not None:
        embed.description = lang_dnd.TT_RECALL_IMPRINT.format(gist=imprint.describe())
    if not memories:
        embed.description = (embed.description or "") + f"\n{lang_dnd.TT_RECALL_EMPTY}"
        return embed
    embed.add_field(
        name="Comes to mind",
        value="\n\n".join(_memory_line(m) for m in memories[:5])[:1024],
        inline=False,
    )
    return embed


def relationship_view(a_name: str, b_name: str, forward, backward) -> discord.Embed:
    """Both directions side by side — the asymmetry is the point."""
    embed = discord.Embed(
        title=lang_dnd.TT_RELATE_TITLE.format(a=a_name, b=b_name),
        color=config_py.main_color,
    )
    for label, rel in ((f"{a_name} → {b_name}", forward), (f"{b_name} → {a_name}", backward)):
        lines = [f"*{rel.summary()}*"]
        for axis in ("affinity", "trust", "fear", "respect", "familiarity"):
            value = getattr(rel, axis)
            lines.append(f"`{axis_bar(value)}` {axis.title()} {value:+.2f}")
        if rel.debt:
            lines.append(f"Debt: {rel.debt:+d}")
        embed.add_field(name=label, value="\n".join(lines), inline=True)
    return embed


def tuning_view(entries: list[dict], campaign_name: str) -> discord.Embed:
    """Current simulation settings and where each one came from."""
    embed = discord.Embed(
        title=lang_dnd.TT_TUNING_TITLE.format(campaign=campaign_name),
        color=config_py.main_color,
    )
    by_group: dict = {}
    for entry in entries:
        by_group.setdefault(entry["group"], []).append(entry)

    for group, items in by_group.items():
        lines = [
            lang_dnd.TT_TUNING_LINE.format(
                key=item["key"], value=item["value"], source=item["source"]
            )
            for item in items
        ]
        embed.add_field(name=group, value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text="Change these on the panel, or with /tune set")
    return embed


# --------------------------------------------------------------------------- #
#  Why somebody did what they did
# --------------------------------------------------------------------------- #
# The nine terms, in words rather than in field names. The panel says the same
# things; two renderings of one decision that disagree is how a GM stops
# trusting either.
TERM_LABELS = {
    "need": "their body wanted it",
    "impulse": "an urge they kept coming back to",
    "goal": "it served what they are after",
    "relation": "how they feel about them",
    "risk": "what it might cost",
    "trait": "the sort of thing they do",
    "imprint": "something they cannot forget",
    "norm": "what it would look like",
    "archetype": "the sort of person they are",
}


def decision_view(entity, event) -> discord.Embed:
    """One committed decision, with its working. Read from the event log."""
    payload = event.payload or {}
    trace = payload.get("trace") or {}
    verb = payload.get("verb", "acted")
    target = f" \u2192 **{payload.get('target')}**" if payload.get("target") else ""

    embed = discord.Embed(
        title=lang_dnd.TT_WHY_TITLE.format(name=entity.identity.name, verb=verb),
        description=lang_dnd.TT_WHY_CHOICE.format(
            verb=verb, target=target, utility=float(trace.get("utility", 0.0))
        ),
        colour=discord.Colour.blurple(),
    )

    considered = trace.get("considered") or []
    runner_up = next((c for c in considered if c.get("verb") != verb), None)
    if runner_up is not None:
        line = lang_dnd.TT_WHY_OVER.format(
            verb=runner_up.get("verb", ""),
            utility=float(runner_up.get("utility", 0.0)),
            temperature=float(trace.get("temperature", 0.0)),
        )
        if abs(float(trace.get("margin", 1.0))) < 0.1:
            line += lang_dnd.TT_WHY_CLOSE
        embed.description += line

    terms = sorted((trace.get("terms") or {}).items(), key=lambda pair: -abs(pair[1]))
    lines = [
        lang_dnd.TT_WHY_TERM_LINE.format(
            label=TERM_LABELS.get(name, name), value=value
        )
        for name, value in terms if abs(value) >= 0.005
    ]
    if lines:
        embed.description += lang_dnd.TT_WHY_TERMS.format(lines="\n".join(lines))
    return embed
