"""
Decay — degradation, not deletion, and never uniform.

Three things this deliberately is not:

**Not linear, and not exponential either.** Human forgetting follows a *power
law* — a steep drop in the first hours and days, then a very long tail. An
exponential curve loses too little at first and then wipes everything out at the
same moment; a power law matches how you lose the details of last Tuesday within
a week but still hold the gist of a bad night ten years on. The retention curve
here is the Ebbinghaus form::

    R(t) = (1 + t / S) ** -d

where ``S`` is the memory's **stability** (how long it holds together) and ``d``
shapes how sharply it falls. Only ``S`` varies per memory and per person — which
is where the other two properties come from.

**Not the same for everyone.** ``retention`` is a per-entity faculty
(``Traits.retention``). Some people remember nearly everything; some lose names
by the following week. It multiplies stability directly.

**Not indiscriminate.** Stability is stretched or shortened by how well a memory
aligns with what that character actually *values* (``values.py``). A grasping
NPC keeps every debt and forgets every kindness; a sworn one does the reverse.
This is the part that stops decay feeling like a timer and starts it feeling like
a personality.

Fields still rot in order — gist outlasts valence outlasts participants outlasts
details outlasts time-and-place — but that ordering is now expressed as *relative
stability* rather than separate rates, so all three modulations above apply to
every field at once.

Imprints do not decay at all. And **nothing here is baked in**: every constant
arrives as a :class:`~helpers.dnd.tuning.MemoryTuning`, resolved per server and
per campaign, so a GM can retune forgetting for their own table — including
setting ``memory_decay_rate`` to 0, which freezes memory exactly as encoded, or
``memory_alignment_reach`` to 0 for value-blind forgetting.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.mind.memory import values as value_model
from helpers.dnd.mind.traits import Traits
from helpers.dnd.tuning import DEFAULT_MEMORY, MemoryTuning
from helpers.dnd.world.memory import (
    DECAYING_FIELDS,
    IMPRINT_RECALL_SALIENCE,
    TIER_IMPRINT,
    WHEN_PRECISION,
    Memory,
)

MINUTES_PER_DAY = 1440

# How much a strong memory in a good head aligned with someone's values
# outlasts a quiet misaligned one in a poor head: roughly an order of magnitude,
# which is about the spread real people show. Every reach below is tunable per
# server and per campaign (helpers/dnd/tuning.py) — including to zero, which
# switches that whole influence off.

# High-retention people imprint a little more readily: the same night marks them
# more deeply. Shifts the threshold by at most this much.
RETENTION_IMPRINT_SHIFT = 0.15


def stability(
    memory: Memory,
    field: str,
    *,
    retention: float = 0.5,
    alignment: float = 0.0,
    tuning: MemoryTuning = DEFAULT_MEMORY,
) -> float:
    """How many days this field of this memory holds together, for this person.

    The single number every other property feeds into. Three multipliers on a
    per-field base: how much it mattered, whose head it is in, and whether their
    values are holding on to it. Never zero, so nothing is instantaneous.
    """
    base = tuning.stability.get(field, 1.0)
    by_salience = 1.0 + tuning.salience_reach * max(0.0, min(1.0, memory.salience))
    # Centred on 0.5 so an ordinary memory for faces is the neutral case.
    by_retention = tuning.retention_reach ** ((max(0.0, min(1.0, retention)) - 0.5) * 2)
    by_alignment = (1.0 + tuning.alignment_reach) ** max(-1.0, min(1.0, alignment))
    return max(0.05, base * by_salience * by_retention * by_alignment)


def retained(elapsed_days: float, stability_days: float,
             shape: float = DEFAULT_MEMORY.shape) -> float:
    """The Ebbinghaus retention curve. 1.0 at t=0, falling with a long tail."""
    if elapsed_days <= 0:
        return 1.0
    return (1.0 + elapsed_days / max(0.05, stability_days)) ** -shape


def decay(
    memory: Memory,
    days: float,
    rng: Random | None = None,
    *,
    traits: Traits | None = None,
    tuning: MemoryTuning = DEFAULT_MEMORY,
) -> Memory:
    """Age one memory. Mutates and returns it.

    **With ``tuning.decay_rate`` at 0 nothing changes at all** — forgetting is
    switched off and memories stay exactly as encoded. That is a supported way to
    run a campaign, not a broken state, so it is checked before anything else.
    """
    if memory.is_imprint or days <= 0 or tuning.frozen:
        return memory

    effective_days = days * tuning.decay_rate
    retention = traits.retention if traits is not None else 0.5
    align = (
        value_model.alignment(memory, traits) if traits is not None else 0.0
    )

    for field in DECAYING_FIELDS:
        current = memory.fidelity.get(field, 1.0)
        if current <= 0.0:
            continue
        span = stability(
            memory, field, retention=retention, alignment=align, tuning=tuning
        )
        # Resume from where this memory already sits on the curve rather than
        # restarting it, or ten one-day steps would decay far less than one
        # ten-day step and the whole thing would depend on how often you looked.
        already = (current ** (-1.0 / tuning.shape) - 1.0) * span
        memory.fidelity[field] = round(
            retained(already + effective_days, span, tuning.shape), 4
        )

    memory.when_precision = _precision_for(memory.fidelity.get("when", 1.0))

    if rng is not None:
        _confabulate(memory, rng, tuning)
    return memory


def _precision_for(fidelity: float) -> str:
    """Losing your grip on *when* is a coarsening, not a blur: "last Tuesday"
    becomes "a while back" becomes "years ago"."""
    index = min(len(WHEN_PRECISION) - 1, int((1.0 - fidelity) * len(WHEN_PRECISION)))
    return WHEN_PRECISION[index]


def _confabulate(memory: Memory, rng: Random,
                 tuning: MemoryTuning = DEFAULT_MEMORY) -> None:
    """Blank a faded field, or mark it for a plausible wrong value.

    Only ``details`` and ``participants``. Confabulating the *gist* would replace
    the memory with a different event, which is not misremembering — it is a
    different memory, and a GM would have no way to reason about it.
    """
    for field in ("details", "participants"):
        if memory.fidelity.get(field, 1.0) >= tuning.confabulate_threshold:
            continue
        if field in memory.confabulated or not getattr(memory, field):
            continue
        if rng.random() < tuning.confabulate_chance:
            memory.confabulated.append(field)
        else:
            setattr(memory, field, [])


def substitute(memory: Memory, pool: dict, rng: Random) -> Memory:
    """Fill confabulated fields from the entity's *other* memories.

    Why the mistake is characteristic: they do not invent a stranger, they insert
    someone else they know, from somewhere else they have been.
    """
    if "participants" in memory.confabulated and pool.get("participants"):
        candidates = [p for p in pool["participants"] if p not in memory.participants]
        if candidates:
            memory.participants = [rng.choice(candidates)]
    if "details" in memory.confabulated and pool.get("details"):
        candidates = [d for d in pool["details"] if d not in memory.details]
        if candidates:
            memory.details = [rng.choice(candidates)]
    return memory


def should_imprint(memory: Memory, *, retention: float = 0.5,
                   tuning: MemoryTuning = DEFAULT_MEMORY) -> bool:
    """Whether this memory has become formative.

    Two routes, both real: one overwhelming moment, or something returned to
    again and again until it is load-bearing. People with a good memory imprint
    a little more readily.
    """
    if memory.is_imprint:
        return False
    threshold = tuning.imprint_threshold - RETENTION_IMPRINT_SHIFT * ((retention - 0.5) * 2)
    if memory.salience >= threshold:
        return True
    return (
        memory.recall_count >= tuning.imprint_recalls
        and memory.salience >= IMPRINT_RECALL_SALIENCE
    )


def promote(memory: Memory) -> Memory:
    """Make a memory an imprint: immune to decay, restored to full clarity.

    Restoring fidelity is deliberate. An imprint is not a well-preserved ordinary
    memory — it is the one you can still *see*. Whether it is accurate is a
    separate question the GM controls.
    """
    memory.tier = TIER_IMPRINT
    memory.fidelity = {f: 1.0 for f in DECAYING_FIELDS}
    memory.when_precision = "exact"
    return memory


def age_all(
    memories: list[Memory],
    days: float,
    rng: Random,
    *,
    traits: Traits | None = None,
    tuning: MemoryTuning = DEFAULT_MEMORY,
) -> list[Memory]:
    """Decay a whole set, promoting anything that has become formative."""
    retention = traits.retention if traits is not None else 0.5
    for memory in memories:
        decay(memory, days, rng, traits=traits, tuning=tuning)
        if should_imprint(memory, retention=retention, tuning=tuning):
            promote(memory)
    return memories


def half_life(memory: Memory, field: str = "gist", *, retention: float = 0.5,
              alignment: float = 0.0, tuning: MemoryTuning = DEFAULT_MEMORY) -> float:
    """Days until this field is at half clarity — for the GM inspector.

    "This fades in about 40 days" is worth more to a GM than a stability
    constant, and it is the same arithmetic run backwards. Returns ``inf`` when
    forgetting is switched off, which the inspector renders as "never".
    """
    if tuning.frozen or memory.is_imprint:
        return float("inf")
    span = stability(memory, field, retention=retention, alignment=alignment, tuning=tuning)
    return round(span * (2 ** (1.0 / tuning.shape) - 1.0), 1)
