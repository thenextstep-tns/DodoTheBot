"""
Memory repository — campaign-scoped.

Memories live in their own collection rather than inside the entity document for
two reasons: they are the only thing about an entity that grows, and they are
paged in only for entities that are actually thinking. Embedding them would
recreate the old cog's ever-growing ``history`` string and, on a long campaign,
walk into the 16 MB document ceiling.

The read that matters is :meth:`for_entity`, and the write that matters is
:meth:`replace_all` — decay, consolidation and pruning all operate on an
entity's whole set at once, because a budget is a property of the set.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import dnd_memories
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.memory import TIER_IMPRINT, TIERS, Memory


class MemoryRepo(ScopedRepo):
    """Memories in one campaign."""

    collection = dnd_memories
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, memory_id: Any) -> Optional[Memory]:
        doc = self.by_id(memory_id)
        return Memory.from_doc(doc) if doc else None

    def for_entity(self, entity_id: Any, *, tier: str | None = None) -> list[Memory]:
        query: dict = {"entity_id": entity_id}
        if tier in TIERS:
            query["tier"] = tier
        docs = self.find(query, sort=[("salience", -1)])
        return [Memory.from_doc(d) for d in docs]

    def imprints(self, entity_id: Any) -> list[Memory]:
        return self.for_entity(entity_id, tier=TIER_IMPRINT)

    def gists_of(self, entity_id: Any) -> list[str]:
        """Existing gists, for the novelty term when encoding something new."""
        return [str(d.get("gist", "")) for d in self.find({"entity_id": entity_id})]

    def count_for(self, entity_id: Any, *, tier: str | None = None) -> int:
        query: dict = {"entity_id": entity_id}
        if tier in TIERS:
            query["tier"] = tier
        return self.count(query)

    def tier_counts(self, entity_id: Any) -> dict:
        counts: dict[str, int] = {}
        for doc in self.find({"entity_id": entity_id}):
            tier = doc.get("tier", "working")
            counts[tier] = counts.get(tier, 0) + 1
        return counts

    def detail_pool(self, entity_id: Any) -> dict:
        """Candidate values for confabulation, drawn from this entity's *other*
        memories — which is what makes a false recollection characteristic
        rather than random."""
        participants: list = []
        details: list[str] = []
        for memory in self.for_entity(entity_id):
            for person in memory.participants:
                if person not in participants:
                    participants.append(person)
            for detail in memory.details:
                if detail not in details:
                    details.append(detail)
        return {"participants": participants, "details": details}

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def add(self, memory: Memory) -> Memory:
        memory.guild_id = self._scope.guild_id
        memory.campaign_id = self._scope.campaign_id
        doc = memory.to_doc()
        doc.pop("_id", None)
        memory.id = self.insert(doc)
        return memory

    def save(self, memory: Memory) -> int:
        """Persist a memory's mutable state.

        A field list rather than a whole-document replace: scope keys belong to
        the repository, and a stale in-memory copy must not be able to reparent
        a record into another campaign.
        """
        doc = memory.to_doc()
        patch = {
            key: doc[key]
            for key in (
                "tier", "encoded_at", "last_recalled_at", "recall_count", "gist",
                "valence", "arousal", "participants", "location_id", "details",
                "when_precision", "salience", "fidelity", "confabulated", "cues",
            )
        }
        return self.update_by_id(memory.id, patch)

    def save_all(self, memories: list[Memory]) -> int:
        return sum(self.save(m) for m in memories if m.id is not None)

    def forget(self, memory_id: Any) -> int:
        return self.delete({"_id": memory_id})

    def forget_many(self, memories: list[Memory]) -> int:
        return sum(self.forget(m.id) for m in memories if m.id is not None)

    def wipe_entity(self, entity_id: Any) -> int:
        return self.delete_many({"entity_id": entity_id})


def memories_for(guild_id: int, campaign_id: Any) -> MemoryRepo:
    return MemoryRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
