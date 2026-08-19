"""
Consolidation and budgets — what keeps this lightweight.

Memory flows ``working → mid → long``, compressing at each step, and anything
that crosses the imprint threshold is promoted instead of consolidated.

The **budget** is the bounded-cost guarantee, and it is why 500 NPCs is a fixed,
known bill rather than an unbounded one. Each entity gets a cap per tier scaled
by how much it matters:

    mid     12 …  72
    long    20 … 220
    imprint  3 …  15

A nameless guard costs almost nothing to remember with; a named questgiver gets
room for a life. Over budget, the lowest-salience entries are pruned first —
never an imprint, and never something recalled recently.

Pruned mid-term memories are **merged into a summary** rather than deleted, so
the gist of a forgotten week survives even when its episodes do not. That is the
difference between forgetting and amnesia.
"""

from __future__ import annotations

from helpers.dnd.tuning import DEFAULT_MEMORY, MemoryTuning
from helpers.dnd.world.memory import (
    TIER_IMPRINT,
    TIER_LONG,
    TIER_MID,
    TIER_WORKING,
    Memory,
)

MINUTES_PER_DAY = 1440

# Below this a working memory is not worth keeping past the scene.
WORKING_FLOOR = 0.15
# Below this a mid-term memory does not make it into long-term.
MID_FLOOR = 0.2
# Recently-recalled memories are protected from pruning for this long.
PROTECT_DAYS = 7.0


def budget_for(importance: float, tuning: MemoryTuning = DEFAULT_MEMORY) -> dict:
    """Per-tier caps for an entity of this importance (0..1).

    Scaled by ``memory_budget_scale``, so a GM who wants everyone to remember
    everything can raise it — at a proportional cost in storage and tick time,
    which is exactly the trade the cap exists to expose.
    """
    importance = max(0.0, min(1.0, importance))
    scale = max(0.1, tuning.budget_scale)
    return {
        TIER_MID: max(1, int((12 + 60 * importance) * scale)),
        TIER_LONG: max(1, int((20 + 200 * importance) * scale)),
        TIER_IMPRINT: max(1, int((3 + 12 * importance) * scale)),
    }


def consolidate_scene(memories: list[Memory]) -> tuple[list[Memory], list[Memory]]:
    """End of scene: working → mid. Returns ``(kept, dropped)``.

    Compression here is mostly *selection* — the trivia of a scene is dropped and
    what mattered is promoted. Nothing is rewritten, so nothing is lost that the
    salience score did not judge unimportant.
    """
    kept, dropped = [], []
    for memory in memories:
        if memory.tier != TIER_WORKING:
            continue
        if memory.salience >= WORKING_FLOOR:
            memory.tier = TIER_MID
            kept.append(memory)
        else:
            dropped.append(memory)
    return kept, dropped


def consolidate_arc(memories: list[Memory]) -> tuple[list[Memory], list[Memory]]:
    """End of arc: mid → long. Returns ``(kept, dropped)``."""
    kept, dropped = [], []
    for memory in memories:
        if memory.tier != TIER_MID:
            continue
        if memory.salience >= MID_FLOOR:
            memory.tier = TIER_LONG
            kept.append(memory)
        else:
            dropped.append(memory)
    return kept, dropped


def over_budget(memories: list[Memory], importance: float,
                tuning: MemoryTuning = DEFAULT_MEMORY) -> dict[str, int]:
    """How far past its cap each tier is."""
    caps = budget_for(importance, tuning)
    counts: dict[str, int] = {}
    for memory in memories:
        counts[memory.tier] = counts.get(memory.tier, 0) + 1
    return {
        tier: max(0, counts.get(tier, 0) - cap)
        for tier, cap in caps.items()
        if counts.get(tier, 0) > cap
    }


def prune(
    memories: list[Memory], importance: float, world_time: int,
    tuning: MemoryTuning = DEFAULT_MEMORY,
) -> tuple[list[Memory], list[Memory]]:
    """Bring an entity back inside its budget. Returns ``(surviving, pruned)``.

    Lowest salience goes first. Imprints are never pruned, and anything recalled
    in the last week is protected — a memory someone keeps reaching for is by
    definition still in use.
    """
    caps = budget_for(importance, tuning)
    by_tier: dict[str, list[Memory]] = {}
    for memory in memories:
        by_tier.setdefault(memory.tier, []).append(memory)

    surviving: list[Memory] = list(by_tier.get(TIER_WORKING, []))
    pruned: list[Memory] = []

    for tier, cap in caps.items():
        entries = by_tier.get(tier, [])
        if tier == TIER_IMPRINT:
            # Imprints are capped too, but only the weakest ever go, and only
            # when there are genuinely too many to be formative any more.
            entries.sort(key=lambda m: -m.salience)
            surviving.extend(entries[:cap])
            pruned.extend(entries[cap:])
            continue

        protected, ordinary = [], []
        for memory in entries:
            recent = (world_time - memory.last_recalled_at) / MINUTES_PER_DAY
            (protected if memory.last_recalled_at and recent <= PROTECT_DAYS else ordinary).append(memory)

        ordinary.sort(key=lambda m: -m.salience)
        room = max(0, cap - len(protected))
        surviving.extend(protected + ordinary[:room])
        pruned.extend(ordinary[room:])

    return surviving, pruned


def summarise(pruned: list[Memory], entity_id, world_time: int) -> Memory | None:
    """Fold pruned memories into one low-salience summary.

    Keeps the shape of a forgotten stretch without its episodes: "a hard winter
    at the docks" rather than forty individual cold mornings. Returns ``None``
    when there is nothing to fold.
    """
    if not pruned:
        return None

    participants: list = []
    for memory in pruned:
        for person in memory.participants:
            if person not in participants:
                participants.append(person)

    mean_valence = sum(m.valence for m in pruned) / len(pruned)
    return Memory(
        entity_id=entity_id,
        tier=TIER_LONG,
        encoded_at=min(m.encoded_at for m in pruned),
        gist=f"a stretch of {len(pruned)} things that no longer come to mind clearly",
        valence=round(mean_valence, 3),
        arousal=0.1,
        participants=participants[:5],
        salience=round(max(0.05, min(0.2, sum(m.salience for m in pruned) / len(pruned) / 2)), 4),
        # A summary is hazy by construction — it never had detail to lose.
        fidelity={"gist": 0.6, "valence": 0.5, "participants": 0.3, "details": 0.0, "when": 0.1},
        when_precision="sometime",
        cues=[],
    )
