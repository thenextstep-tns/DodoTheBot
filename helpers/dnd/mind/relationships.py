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
from helpers.dnd import interactions as interaction_data
from helpers.dnd.world import interaction as interaction_model
from helpers.dnd.world.relationship import AXES, OPTIONAL_AXES, Relationship

# The kinds themselves are **data** now — `helpers/dnd/data/interactions.json`,
# resolved built-in -> server -> campaign by `helpers/dnd/interactions.py`. What
# used to live here as three hand-maintained tables (`DELTAS`, `PHRASES`,
# `ROMANTIC`), alongside a fourth in `mind/stakes.py`, is one definition per
# kind in one file.
#
# These module-level names survive as the **built-in** view of that file, so the
# many callers that only ever wanted the shipped numbers keep working and there
# is still exactly one place the numbers are written. Anything that should
# respect a campaign's own social physics takes the resolved table as an
# argument instead — this module is pure and does not read configuration.
DELTAS: dict[str, dict] = interaction_model.as_deltas(interaction_data.built_in())
PHRASES: dict[str, str] = interaction_model.as_phrases(interaction_data.built_in())

# The acts that only exist in a campaign that asked for them.
ROMANTIC = interaction_model.requiring(interaction_data.built_in(), "desire")


def phrase(kind: str, actor: str, subject: str,
           phrases: dict | None = None) -> str:
    """One line describing what happened, for a memory nobody wrote a gist for.

    ``phrases`` is a campaign's resolved wording; without it the shipped table
    is used, which is right for anything that has no campaign in hand.
    """
    table = PHRASES if phrases is None else phrases
    return f"{actor} {table.get(kind, kind.replace('_', ' '))} {subject}"


def actor_view(kind: str, echo: float = 0.3, deltas: dict | None = None) -> dict:
    """The same act, from the side of the person who *did* it.

    The asymmetry itself lives on :class:`~helpers.dnd.world.interaction.Interaction`
    so there is one implementation of it; this is the by-kind way in, kept
    because callers had it first. ``deltas`` overrides the shipped table with a
    campaign's own.
    """
    table = DELTAS if deltas is None else deltas
    base = table.get(kind)
    if not base:
        return {}
    return interaction_model.Interaction(key=kind, deltas=base).actor_view(echo)


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


def felt_valence(kind: str, deltas: dict | None = None) -> float:
    """How an event of this kind feels, derived from the deltas rather than a
    second table that could drift out of step with them.

    The derivation is on the model; this is the by-kind way in.
    """
    table = DELTAS if deltas is None else deltas
    base = table.get(kind)
    if not base:
        return 0.0
    return interaction_model.Interaction(key=kind, deltas=base).felt_valence()


# Which trait sharpens which axis, and how much. Applied on top of the base.
TRAIT_MODIFIERS = {
    "fear": ("fear_of_death", 0.5),
    "trust": ("openness", 0.25),
    "affinity": ("warmth", 0.3),
    "respect": ("honour", 0.3),
}

# Defaults; both the swing per event and the faction prior are tunable per
# server and per campaign (helpers/dnd/tuning.py).


def _clamp(value: float, axis: str = "") -> float:
    """Hold an axis inside −1…1, where the negative half is a real state.

    Desire included. It briefly ran 0…1 here on the theory that the absence of
    wanting somebody is nothing rather than its opposite — which confused
    *neutral* with *repelled*. Indifference is 0. Finding somebody repellent is
    its own condition, it is not the lack of anything, and a model that cannot
    say it cannot say why two people who ought to get along never will.
    """
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

        setattr(relationship, axis,
                round(_clamp(getattr(relationship, axis) + change, axis), 4))

    # Anything happening at all means you know them a little better.
    relationship.familiarity = round(_clamp(relationship.familiarity + 0.02 * scale), 4)
    bleed(relationship, tuning)
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


def kinds(catalogue: dict | None = None) -> list[str]:
    """Every kind that can be recorded. The shipped set unless given one."""
    return sorted(DELTAS if catalogue is None else catalogue)


# --------------------------------------------------------------------------- #
#  Attraction — a fact about a pair, not a score on a person
# --------------------------------------------------------------------------- #
# What decides how drawn one person is to another. `allure` is deliberately the
# smallest term: how much somebody wants a particular person is mostly about
# what the two of them already are to each other, and a model where the
# best-looking NPC is universally the most wanted is both duller and wronger.
ATTRACTION_WEIGHTS = {
    "allure": 0.30,        # how they strike people, generally
    "affinity": 0.30,      # whether they are liked
    "familiarity": 0.15,   # whether they are known at all
    "trust": 0.15,         # whether they are safe to want
    "respect": 0.10,
}
# And what puts it out entirely. Fear is not a complication here; it is a stop.
FEAR_SUPPRESSES = 1.2


def attraction(relationship, allure: float = 0.5, *, pressure: float = 0.0) -> float:
    """How drawn this person is to that one, 0..1.

    ``relationship`` is the viewer's own ``A → B``, so this is asymmetric like
    everything else here — being wanted is not the same as wanting, and the gap
    is most of what makes it a story rather than a statistic.

    ``pressure`` is the viewer's standing bodily desire (``mind/needs.py``),
    which raises what is already there. It cannot *create* attraction to
    somebody: a need with nowhere to go is a need, not an interest in whoever
    happens to be nearby, and modelling it the other way round produces exactly
    the NPC nobody wants at their table.
    """
    if relationship is None:
        return 0.0
    scored = 0.0
    for axis, weight in ATTRACTION_WEIGHTS.items():
        value = float(allure) if axis == "allure" else float(getattr(relationship, axis, 0.0))
        scored += weight * max(0.0, min(1.0, value if axis == "allure" else (value + 1.0) / 2.0))

    # Standing desire amplifies an existing pull rather than manufacturing one —
    # and when it is negative it is repulsion, which cancels a pull outright
    # rather than merely failing to add to one.
    standing = float(getattr(relationship, "desire", 0.0))
    if standing < 0:
        return 0.0
    base = max(0.0, min(1.0, 0.5 * scored + 0.5 * standing))
    afraid = max(0.0, min(1.0, float(getattr(relationship, "fear", 0.0))))
    return max(0.0, min(1.0, base * (1.0 + 0.4 * max(0.0, pressure))
                        * (1.0 - FEAR_SUPPRESSES * afraid)))


def bleed(relationship, tuning: RelationshipTuning = DEFAULT_RELATIONSHIPS) -> None:
    """Let repulsion colour everything else about how they see somebody.

    Finding a person physically repellent does not sit in its own column. It
    sours the whole acquaintance — you like them less, you respect them less,
    and neither of you could tell you exactly why. Applied whenever anything at
    all happens between the two of them, so it accumulates through contact
    rather than on a clock.

    **One direction only.** Attraction deliberately does *not* bleed the other
    way: wanting somebody would raise affinity, which raises attraction
    (:func:`attraction` reads affinity), which raises affinity — a loop that
    ends with every fond acquaintance in the campaign infatuated. Repulsion has
    no such path back, so it is safe to let it spread and it is the half that
    was asked for.

    ``bleed = 0`` keeps it in its column.
    """
    repulsion = min(0.0, float(getattr(relationship, "desire", 0.0)))
    if not repulsion or tuning.desire_bleed <= 0:
        return
    seep = tuning.desire_bleed * repulsion
    relationship.affinity = round(_clamp(relationship.affinity + seep), 4)
    relationship.respect = round(_clamp(relationship.respect + seep * 0.5), 4)
