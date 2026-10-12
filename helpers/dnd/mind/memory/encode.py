"""
Encoding — witnesses perceive, they do not observe.

The most important function in the memory model, and the one that makes the rest
of the simulation generative rather than scripted:

    Two witnesses to one event produce **two different memories**.

Different valence (it meant different things to them), different detail (they
were standing further away), sometimes different participants (they missed who
else was in the room). Every grudge, rumour, false accusation and misunderstanding
in the game originates here — not from a feature that generates misunderstandings.

Perception clarity is a product of distance, light, distraction and the witness's
own traits. A `diligent` witness notices detail; a `volatile` one fixates on the
threat and loses the periphery. Nothing about this needs a model.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.mind.memory import salience as sal
from helpers.dnd.mind.memory import values as value_model
from helpers.dnd.mind.traits import Traits
from helpers.dnd.tuning import DEFAULT_MEMORY, DEFAULT_SALIENCE, MemoryTuning, SalienceTuning
from helpers.dnd.world.memory import TIER_WORKING, Memory

# Below this, detail and participants start dropping out.
PARTIAL_CLARITY = 0.7
# Below this, even the gist coarsens — you saw "a fight", not who started it.
COARSE_CLARITY = 0.4

# Words worth keeping as recall cues. Everything else is noise that would match
# every memory and make cue-triggered recall useless.
_CUE_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "was", "were",
    "has", "have", "had", "are", "but", "not", "you", "your", "his", "her",
    "its", "their", "them", "they", "who", "what", "when", "where", "which",
    "all", "any", "one", "two", "some", "more", "than", "then", "there", "it",
    "a", "an", "of", "at", "in", "on", "to", "by", "is", "as", "he", "she",
}


def clarity(
    *,
    traits: Traits | None = None,
    distance: float = 0.0,
    light: float = 1.0,
    distracted: float = 0.0,
) -> float:
    """How well this witness perceived the event, 0..1.

    ``distance`` 0 is arm's length and 1 is across a square; ``light`` 1 is
    daylight and 0 is pitch dark; ``distracted`` 0 is attentive.
    """
    base = 1.0 - 0.45 * max(0.0, min(1.0, distance))
    base *= 0.4 + 0.6 * max(0.0, min(1.0, light))
    base *= 1.0 - 0.4 * max(0.0, min(1.0, distracted))
    if traits is not None:
        # Attentive people see more; volatile people tunnel on the threat.
        base *= 1.0 + 0.15 * traits.axis("diligence")
        base *= 1.0 - 0.12 * max(0.0, traits.axis("volatility"))
    return round(max(0.05, min(1.0, base)), 4)


def appraise(
    *,
    valence: float,
    traits: Traits | None,
    relationship_to_actor: float = 0.0,
    was_target: bool = False,
) -> tuple[float, float]:
    """How the event felt **to this witness** — their valence and arousal.

    The event's own valence is only a starting point. Someone who likes the actor
    reads the same act more kindly; someone it happened *to* feels it far more
    sharply than a bystander.
    """
    felt = valence + 0.35 * relationship_to_actor
    intensity = 0.4 + (0.5 if was_target else 0.0)
    if traits is not None:
        intensity += 0.25 * max(0.0, traits.axis("volatility"))
        felt += 0.15 * traits.axis("warmth") * (1 if valence > 0 else -1)
    return (
        round(max(-1.0, min(1.0, felt)), 4),
        round(max(0.0, min(1.0, intensity * (0.5 + abs(felt)))), 4),
    )


def extract_cues(gist: str, details, limit: int = 8) -> list[str]:
    """Words that could later trigger this memory.

    Cues are what make recall feel involuntary — walking into the rain surfaces
    the rain memories without anyone querying for them.
    """
    words: list[str] = []
    for chunk in [gist, *(details or [])]:
        for raw in str(chunk).lower().split():
            word = "".join(c for c in raw if c.isalnum())
            if len(word) > 2 and word not in _CUE_STOP and word not in words:
                words.append(word)
    return words[:limit]


def encode(
    *,
    witness_id,
    gist: str,
    world_time: int,
    rng: Random,
    valence: float = 0.0,
    participants=None,
    details=None,
    location_id=None,
    traits: Traits | None = None,
    perception: float = 1.0,
    relationship_to_actor: float = 0.0,
    existing_gists=(),
    affinities: dict | None = None,
    source_event_seq: int | None = None,
    salience_scale: float = 1.0,
    salience_tuning: SalienceTuning = DEFAULT_SALIENCE,
    memory_tuning: MemoryTuning = DEFAULT_MEMORY,
) -> Memory | None:
    """Form one witness's memory of an event.

    Returns ``None`` if perception was too poor to register anything at all —
    they were there, and they have no memory of it.
    """
    if perception < 0.05:
        return None

    participants = list(participants or [])
    details = list(details or [])
    was_target = witness_id in participants

    felt, arousal = appraise(
        valence=valence,
        traits=traits,
        relationship_to_actor=relationship_to_actor,
        was_target=was_target,
    )

    # Partial perception: pieces simply were not taken in. Dropped at encoding
    # rather than decayed later, because they were never there to begin with.
    if perception < PARTIAL_CLARITY:
        keep = perception / PARTIAL_CLARITY
        details = [d for d in details if rng.random() < keep]
        # Never drop the witness themselves — you know whether it happened to you.
        participants = [
            p for p in participants if p == witness_id or rng.random() < keep
        ]

    if perception < COARSE_CLARITY:
        gist = _coarsen(gist)

    memory = Memory(
        entity_id=witness_id,
        tier=TIER_WORKING,
        encoded_at=world_time,
        gist=gist,
        valence=felt,
        arousal=arousal,
        participants=participants,
        details=details,
        location_id=location_id,
        source_event_seq=source_event_seq,
        cues=extract_cues(gist, details),
    )
    memory.salience = sal.score(
        valence=felt,
        arousal=arousal,
        participants=participants,
        witness_id=witness_id,
        existing_gists=existing_gists,
        gist=gist,
        affinities=affinities,
        tuning=salience_tuning,
    )
    # Attention is not neutral. Someone grasping *notices* a debt that a
    # generous person lets pass without registering — so value alignment lifts
    # (or flattens) salience at encoding, not only retention afterwards. The two
    # compound: what you notice more, you also keep longer.
    if traits is not None and salience_tuning.value_weight:
        align = value_model.alignment(memory, traits)
        memory.salience = round(
            max(0.0, min(1.0, memory.salience * (1 + salience_tuning.value_weight * align))), 4
        )
    # How much the event was *worth* to this witness scales how firmly it is
    # held — and only that. It must never reach the fidelity block below:
    # perception is sensory access, stake is significance, and routing stake
    # through perception made a trivial thing that happened this morning render
    # as "a while ago, maybe". You do not misremember *when* something happened
    # because it did not matter; you remember it accurately and briefly.
    if salience_scale != 1.0:
        memory.salience = round(
            max(0.0, min(1.0, memory.salience * max(0.0, salience_scale))), 4
        )

    # Poor perception means a hazier record from the start, not just a shorter
    # one — the fidelity it begins with is the fidelity it perceived.
    if perception < PARTIAL_CLARITY:
        for f in ("participants", "details", "when"):
            memory.fidelity[f] = round(memory.fidelity[f] * perception, 4)
    return memory


def _coarsen(gist: str) -> str:
    """Reduce a specific gist to the impression that survived.

    Deliberately crude: it keeps the verb and drops the specifics, which is
    roughly what a glimpse across a dark room leaves you with.
    """
    lowered = gist.lower()
    for verb, vague in _COARSE.items():
        if verb in lowered:
            return vague
    words = gist.split()
    return " ".join(words[:3]) + ("…" if len(words) > 3 else "")


_COARSE = {
    "stab": "a fight, someone hurt",
    "kill": "a fight, someone hurt",
    "attack": "a fight",
    "steal": "something taken",
    "give": "something changed hands",
    "argue": "raised voices",
    "shout": "raised voices",
    "burn": "fire, and shouting",
}
