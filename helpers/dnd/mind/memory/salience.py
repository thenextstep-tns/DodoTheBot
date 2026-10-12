"""
Salience — the master value.

Computed once at encoding and updated on reinforcement, it drives everything
downstream: whether a memory becomes an imprint, how fast it decays, how likely
it is to be recalled, and what survives when a budget is exceeded.

Four contributions, weighted to sum to 1.0 so a salience reads as a fraction:

* **emotional** — how hard it hit, ``|valence| * arousal``
* **relevance** — whether it was *about you*
* **novelty**   — whether anything like it had happened before
* **social**    — whether it involved someone you care about

Nothing here consults a model. Salience is arithmetic over a draft memory and
the witness's existing state.
"""

from __future__ import annotations

# Defaults only. Every weight is overridable per server and per campaign
# (helpers/dnd/tuning.py) — a GM who wants a table where only emotionally
# charged things are remembered can have one.
from helpers.dnd.tuning import DEFAULT_SALIENCE, SalienceTuning  # noqa: E402


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def emotional(valence: float, arousal: float) -> float:
    return clamp01(abs(valence) * arousal)


def relevance(participants, witness_id) -> float:
    """Was this about them, or did they merely see it?

    Being a participant is the difference between a story you tell and a story
    that happened to you, so the gap here is deliberately wide.
    """
    if witness_id in (participants or []):
        return 1.0
    return 0.25 if participants else 0.1


def novelty(gist: str, existing_gists) -> float:
    """1.0 for something unlike anything remembered, falling as it repeats.

    Word-overlap rather than anything cleverer: the tenth time a guard watches a
    cart pass, the gist is nearly identical and the memory should barely register.
    """
    if not existing_gists:
        return 1.0
    words = set(gist.lower().split())
    if not words:
        return 0.5
    best = 0.0
    for other in existing_gists:
        other_words = set(other.lower().split())
        if not other_words:
            continue
        overlap = len(words & other_words) / len(words | other_words)
        best = max(best, overlap)
    return clamp01(1.0 - best)


def social(participants, affinities: dict) -> float:
    """How much the witness cares about whoever was involved.

    Uses absolute affinity: something happening to someone you hate is every bit
    as memorable as something happening to someone you love.
    """
    if not participants:
        return 0.0
    return clamp01(max((abs(affinities.get(p, 0.0)) for p in participants), default=0.0))


def score(
    *,
    valence: float,
    arousal: float,
    participants,
    witness_id,
    existing_gists=(),
    gist: str = "",
    affinities: dict | None = None,
    tuning: SalienceTuning = DEFAULT_SALIENCE,
) -> float:
    """The salience of a memory about to be encoded."""
    return round(
        clamp01(
            tuning.emotional * emotional(valence, arousal)
            + tuning.relevance * relevance(participants, witness_id)
            + tuning.novelty * novelty(gist, existing_gists)
            + tuning.social * social(participants, affinities or {})
        ),
        4,
    )


def reinforce(current: float, gain: float | None = None,
              tuning: SalienceTuning = DEFAULT_SALIENCE) -> float:
    """Strengthen toward, but never to, certainty.

    Multiplicative and saturating, so repetition deepens a memory without ever
    making it absolute — repeated small slights accumulate into a grudge, but
    nothing becomes unforgettable merely by happening twice.
    """
    step = tuning.reinforce if gain is None else gain
    return round(1 - (1 - current) * (1 - clamp01(step)), 4)
