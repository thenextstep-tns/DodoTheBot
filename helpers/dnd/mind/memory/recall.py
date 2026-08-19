"""
Recall and reconsolidation.

Recall is **cue-driven**, not query-driven. Nobody searches their memory by
keyword; a smell, a name, a place drags something up unbidden. So retrieval
scores stored cues against whatever is present in the scene.

Reconsolidation is the part that earns its keep for one line of code: **recalling
a memory rewrites it.** The gist strengthens, and occasionally the present leaks
in as a false detail. The NPC who has told the story a hundred times remembers it
vividly and wrongly, with details borrowed from the tellings rather than the
event. That is exactly how human memory behaves, and it costs nothing.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.mind.memory import salience as sal
from helpers.dnd.world.memory import HEDGE_THRESHOLD, Memory

# How much a recall firms up the gist.
GIST_STRENGTHEN = 0.05
# Chance the present moment contaminates the memory on recall.
CONTAMINATION_CHANCE = 0.10
# Recent recalls are easier to reach again.
RECENCY_WINDOW_DAYS = 14.0

MINUTES_PER_DAY = 1440


def cue_overlap(memory: Memory, cues) -> float:
    """Fraction of the offered cues this memory answers to."""
    cues = {str(c).lower() for c in cues if c}
    if not cues or not memory.cues:
        return 0.0
    return len(cues & set(memory.cues)) / len(cues)


def strength(memory: Memory, cues, world_time: int) -> float:
    """How readily this memory comes to mind right now.

    Salience and cue match dominate; recency is a small thumb on the scale.
    A memory whose gist has faded past hedging is hard to reach at all, which is
    why the fidelity term is a multiplier rather than an addend.
    """
    match = cue_overlap(memory, cues)
    if match == 0.0 and not memory.is_imprint:
        return 0.0

    days_since = max(0, world_time - memory.last_recalled_at) / MINUTES_PER_DAY
    recency = max(0.0, 1.0 - days_since / RECENCY_WINDOW_DAYS)

    # An imprint answers to its cues far more strongly than anything else —
    # that is what "he goes quiet when he sees the sigil" is made of.
    imprint_bonus = 0.4 if memory.is_imprint and match > 0 else 0.0

    return round(
        (0.5 * match + 0.3 * memory.salience + 0.2 * recency + imprint_bonus)
        * max(0.15, memory.fidelity.get("gist", 1.0)),
        4,
    )


def recall(memories: list[Memory], cues, world_time: int, limit: int = 5) -> list[Memory]:
    """The memories these cues bring up, strongest first. Read-only."""
    scored = [(strength(m, cues, world_time), m) for m in memories]
    scored = [(s, m) for s, m in scored if s > 0]
    scored.sort(key=lambda pair: -pair[0])
    return [m for _s, m in scored[:limit]]


def reconsolidate(
    memory: Memory, world_time: int, rng: Random, present_details=None
) -> Memory:
    """Recalling rewrites. Mutates and returns the memory.

    The gist firms up and salience rises — but with a small chance the current
    surroundings are absorbed as a detail of the original event. Over many
    tellings that is how a story drifts away from what happened while feeling
    *more* certain, not less.
    """
    memory.recall_count += 1
    memory.last_recalled_at = int(world_time)
    memory.salience = sal.reinforce(memory.salience)
    memory.fidelity["gist"] = round(
        min(1.0, memory.fidelity.get("gist", 1.0) + GIST_STRENGTHEN), 4
    )

    if present_details and rng.random() < CONTAMINATION_CHANCE:
        borrowed = rng.choice(list(present_details))
        if borrowed not in memory.details:
            memory.details.append(borrowed)
            if "details" not in memory.confabulated:
                memory.confabulated.append("details")
    return memory


def triggered_by(memories: list[Memory], cues, world_time: int) -> Memory | None:
    """The single imprint a scene has just set off, if any.

    Separate from :func:`recall` because an imprint firing is a *dramatic event*,
    not a lookup: it is the moment the NPC goes quiet, and the caller wants to
    know whether one happened at all.
    """
    hits = [
        m for m in memories
        if m.is_imprint and cue_overlap(m, cues) > 0
    ]
    if not hits:
        return None
    return max(hits, key=lambda m: (cue_overlap(m, cues), m.salience))


def describe_recall(memory: Memory) -> str:
    """One line explaining why this surfaced — for the GM's inspector."""
    bits = [f"salience {memory.salience:.2f}"]
    if memory.is_imprint:
        bits.append("imprint")
    if memory.recall_count:
        bits.append(f"recalled ×{memory.recall_count}")
    if memory.confabulated:
        bits.append("confabulated: " + ", ".join(memory.confabulated))
    if memory.fidelity.get("gist", 1.0) < HEDGE_THRESHOLD:
        bits.append("barely there")
    return " · ".join(bits)
