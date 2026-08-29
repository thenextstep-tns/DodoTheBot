"""
Entity repository — campaign-scoped.

One collection holds PCs, NPCs, creatures and factions across every ruleset,
which is only possible because ``stats`` is opaque here: its shape belongs to the
ruleset, and this layer never looks inside it.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import dnd_entities
from helpers.dnd.store.repo import ScopedRepo
from helpers.dnd.world.entity import KIND_NPC, KIND_PC, TIERS, Entity


# Fields a caller may not write through :meth:`EntityRepo.save`. The scope owns
# the tenancy keys — a wholesale overwrite is how a stale in-memory copy silently
# reparents a record — and ``legacy_id`` belongs to the importer, which sets it
# once at creation for idempotency.
NOT_THE_CALLERS = frozenset({"_id", "guild_id", "campaign_id", "legacy_id"})


class EntityRepo(ScopedRepo):
    """Entities in one campaign."""

    collection = dnd_entities
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, entity_id: Any) -> Optional[Entity]:
        doc = self.by_id(entity_id)
        return Entity.from_doc(doc) if doc else None

    def character_of(self, user_id: int, *, include_retired: bool = False) -> Optional[Entity]:
        """The PC a user plays in this campaign."""
        query: dict = {"kind": KIND_PC, "owner_id": int(user_id)}
        if not include_retired:
            query["retired"] = False
        doc = self.find_one(query)
        return Entity.from_doc(doc) if doc else None

    def by_name(self, name: str) -> Optional[Entity]:
        import re

        doc = self.find_one(
            {"identity.name": re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)}
        )
        return Entity.from_doc(doc) if doc else None

    def list(self, *, kind: str | None = None, tier: str | None = None,
             include_retired: bool = False, limit: int = 0) -> list[Entity]:
        query: dict = {}
        if kind:
            query["kind"] = kind
        if tier in TIERS:
            query["tier"] = tier
        if not include_retired:
            query["retired"] = False
        docs = self.find(query, sort=[("importance", -1), ("identity.name", 1)], limit=limit)
        return [Entity.from_doc(d) for d in docs]

    def characters(self) -> list[Entity]:
        return self.list(kind=KIND_PC)

    def npcs(self) -> list[Entity]:
        return self.list(kind=KIND_NPC)

    def by_legacy_id(self, legacy_id: Any) -> Optional[Entity]:
        doc = self.find_one({"legacy_id": legacy_id})
        return Entity.from_doc(doc) if doc else None

    def identities_of(self, entity_ids) -> dict:
        """``{id: {"name", "kind"}}`` for a set of ids, in one query.

        Building an entity's view needs a name for everyone they have any
        standing toward, and that is the one place where fetching whole entities
        would turn a decision into a hundred round trips.
        """
        wanted = [i for i in dict.fromkeys(entity_ids) if i is not None]
        if not wanted:
            return {}
        return {
            doc.get("_id"): {
                "name": ((doc.get("identity") or {}).get("name") or ""),
                "kind": doc.get("kind", ""),
                "allure": float(doc.get("allure", 0.5)),
            }
            for doc in self.find({"_id": {"$in": wanted}})
        }

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def create(self, entity: Entity) -> Entity:
        doc = entity.to_doc()
        doc.pop("_id", None)
        entity.id = self.insert(doc)
        return entity

    def save(self, entity: Entity) -> int:
        """Persist an entity's mutable state.

        Deliberately not a whole-document replace: ``guild_id`` and
        ``campaign_id`` are the scope's to set, never the caller's, and a
        wholesale overwrite is how a stale in-memory copy silently reparents a
        record.

        Everything the entity carries is written **except** the fields listed in
        :data:`NOT_THE_CALLERS`. This used to be the other way round — a list of
        fields to save — and a list like that rots silently: ``standing`` was
        added for stakes and never added here, so the inspector's control posted,
        the endpoint set it, this method dropped it, and the panel said "Saved."
        for months. An exclusion list fails the safe way: a new field is
        persisted unless somebody says otherwise.
        """
        doc = entity.to_doc()
        patch = {k: v for k, v in doc.items() if k not in NOT_THE_CALLERS}
        return self.update_by_id(entity.id, patch)

    def set_tier(self, entity_id: Any, tier: str) -> int:
        if tier not in TIERS:
            raise ValueError(f"unknown simulation tier: {tier!r}")
        return self.update_by_id(entity_id, {"tier": tier})

    def retire(self, entity_id: Any) -> int:
        return self.update_by_id(entity_id, {"retired": True})
