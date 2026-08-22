"""
Relationship change — driven by events, never by a language model.

A fixed table of deltas per event kind, scaled by how hard the witness felt it
and modulated by their traits. That last part is what stops every NPC reacting
identically to the same act: a high-`honour` character weighs a debt far more
than a grasping one does, and a fearful one takes a threat harder.

Faction standing propagates as a **prior**, not a fact — a member of a hostile
faction *starts* hostile, and their own experiences move them off it. That is how
you get the sympathetic enemy soldier without scripting one.
"""

from __future__ import annotations

from helpers.dnd.mind.traits import Traits
from helpers.dnd.tuning import DEFAULT_RELATIONSHIPS, RelationshipTuning
from helpers.dnd.world.relationship import AXES, Relationship

# Base deltas per event kind. Tuned so a single act moves a relationship
# noticeably but not decisively — except betrayal, which should.
# **Written from the point of view of the person it happened TO.** Debt is
# positive when *this* person owes the other: being helped puts you in someone's
# debt. It read -1 before, which `summary()` renders as "is owed", so the man
# whose debt had just been cleared was recorded as the creditor.
DELTAS: dict[str, dict] = {
    "helped":     {"affinity": +0.15, "trust": +0.10, "debt": +1},
    "saved":      {"affinity": +0.35, "trust": +0.25, "respect": +0.20, "debt": +2},
    "gifted":     {"affinity": +0.10, "debt": +1},
    "healed":     {"affinity": +0.20, "trust": +0.15, "debt": +1},
    "praised":    {"affinity": +0.10, "respect": +0.05},
    "kept_word":  {"trust": +0.20, "respect": +0.10},

    "betrayed":   {"affinity": -0.50, "trust": -0.70, "fear": +0.20},
    "attacked":   {"affinity": -0.35, "fear": +0.35, "trust": -0.25},
    "threatened": {"fear": +0.30, "respect": +0.10, "affinity": -0.20},
    "stole":      {"affinity": -0.25, "trust": -0.40},
    "lied":       {"trust": -0.30},
    "insulted":   {"affinity": -0.15, "respect": -0.10},
    "bested":     {"respect": +0.20, "fear": +0.15, "affinity": -0.05},

    "met":        {"familiarity": +0.10},
    "talked":     {"familiarity": +0.05, "affinity": +0.02},
    "travelled":  {"familiarity": +0.15, "affinity": +0.05},
}

# How each kind reads as a sentence, so an event that nobody described still
# forms a memory someone could tell back. "Ondry helped Marla", not
# "Ondry kept_word Marla".
PHRASES: dict[str, str] = {
    "helped": "helped", "saved": "saved", "gifted": "gave something to",
    "healed": "healed", "praised": "praised", "kept_word": "kept their word to",
    "betrayed": "betrayed", "attacked": "attacked", "threatened": "threatened",
    "stole": "stole from", "lied": "lied to", "insulted": "insulted",
    "bested": "bested", "met": "met", "talked": "talked with",
    "travelled": "travelled with",
}


def phrase(kind: str, actor: str, subject: str) -> str:
    """One line describing what happened, for a memory nobody wrote a gist for."""
    return f"{actor} {PHRASES.get(kind, kind.replace('_', ' '))} {subject}"


def actor_view(kind: str, echo: float = 0.3) -> dict:
    """The same act, from the side of the person who *did* it.

    ``DELTAS`` is written from the point of view of the person it happened to,
    and applying it unchanged to the actor produces nonsense: a lord who settles
    a stranger's debt ends up liking and trusting that stranger exactly as much
    as the stranger likes him, and both of them are recorded as the creditor.
    Teo was saved and came out indifferent while Vashen came out *"fond of them,
    and is owed 4"*.

    Two changes, and they are the whole asymmetry:

    * **Debt inverts.** If I helped you, you owe me. Same number, other sign.
    * **Feeling is an echo, not a mirror.** Doing someone a kindness warms you to
      them a little (and wronging them cools you a little — people devalue those
      they have harmed), but nothing like as much as receiving it. ``echo``
      scales that and at 0 the actor's feelings simply do not move.
    """
    deltas = DELTAS.get(kind)
    if not deltas:
        return {}
    out = {}
    for axis, base in deltas.items():
        if axis == "debt":
            out[axis] = -int(base)
        elif echo:
            out[axis] = base * echo
    return out


def deepen(relationship, amount: float):
    """Close the distance between two people by ``amount``.

    Familiarity in ``DELTAS`` is a flat token — ``met`` is +0.10 whoever you met
    and whatever came of it. But the night someone saved your life you know them
    incomparably better than after a chat, so the orchestration edge scales this
    by what the event was worth (``mind/stakes.py``). Kept here rather than
    written into the deltas because it is not a property of the *kind*.
    """
    relationship.familiarity = max(0.0, min(1.0, relationship.familiarity + amount))
    return relationship


def felt_valence(kind: str) -> float:
    """How an event of this kind feels, derived from the deltas rather than a
    second table that could drift out of step with them.

    Affinity is the emotional axis, so it leads; trust carries the kinds that
    are about reliability rather than warmth (``kept_word``, ``lied``), and
    familiarity covers the neutral ones. Doubled because the deltas are sized
    for a relationship axis, and a memory's valence spans the full -1..1.
    """
    deltas = DELTAS.get(kind)
    if not deltas:
        return 0.0
    for axis in ("affinity", "trust", "familiarity"):
        if axis in deltas:
            return _clamp(float(deltas[axis]) * 2.0)
    return 0.0


# Which trait sharpens which axis, and how much. Applied on top of the base.
TRAIT_MODIFIERS = {
    "fear": ("fear_of_death", 0.5),
    "trust": ("openness", 0.25),
    "affinity": ("warmth", 0.3),
    "respect": ("honour", 0.3),
}

# Defaults; both the swing per event and the faction prior are tunable per
# server and per campaign (helpers/dnd/tuning.py).


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def apply(
    relationship: Relationship,
    kind: str,
    *,
    traits: Traits | None = None,
    intensity: float = 1.0,
    world_time: int = 0,
    deltas: dict | None = None,
    tuning: RelationshipTuning = DEFAULT_RELATIONSHIPS,
) -> Relationship:
    """Move a relationship in response to something that happened.

    ``intensity`` is the witness's arousal — the same act lands harder on someone
    it frightened. Mutates and returns the relationship.
    """
    deltas = DELTAS.get(kind) if deltas is None else deltas
    if not deltas:
        return relationship

    scale = max(0.1, min(2.0, intensity)) * tuning.scale
    for axis, base in deltas.items():
        if axis == "debt":
            relationship.debt += int(base)
            continue

        change = base * scale
        if traits is not None and axis in TRAIT_MODIFIERS:
            trait_name, weight = TRAIT_MODIFIERS[axis]
            # Drives sit 0..1 with 0.5 neutral; centre them before modulating.
            centred = traits.axis(trait_name) - 0.5
            change *= 1.0 + weight * centred * 2

        setattr(relationship, axis, round(_clamp(getattr(relationship, axis) + change), 4))

    # Anything happening at all means you know them a little better.
    relationship.familiarity = round(_clamp(relationship.familiarity + 0.02 * scale), 4)
    relationship.updated_at = int(world_time)
    return relationship


def blank(from_id, to_id, *, guild_id: int = 0, campaign_id=None) -> Relationship:
    return Relationship(
        guild_id=guild_id, campaign_id=campaign_id, from_id=from_id, to_id=to_id
    )


def seeded_from_faction(
    from_id, to_id, faction_standing: float, *, guild_id: int = 0, campaign_id=None,
    tuning: RelationshipTuning = DEFAULT_RELATIONSHIPS,
) -> Relationship:
    """A starting relationship implied by whose side someone is on.

    Only affinity and trust are seeded. Fear and respect are earned in person —
    a soldier does not fear you because of your flag, they fear you because of
    what you did in front of them.
    """
    relationship = blank(from_id, to_id, guild_id=guild_id, campaign_id=campaign_id)
    relationship.affinity = round(_clamp(faction_standing * tuning.faction_prior), 4)
    relationship.trust = round(_clamp(faction_standing * tuning.faction_prior * 0.7), 4)
    return relationship


def affinity_map(relationships: list[Relationship]) -> dict:
    """``{other_id: affinity}`` — what the salience scorer needs to know about
    who this entity cares about."""
    return {r.to_id: r.affinity for r in relationships}


def kinds() -> list[str]:
    return sorted(DELTAS)
