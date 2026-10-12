"""
Relationship repository — campaign-scoped.

One document per ordered pair, with a unique index on
``(campaign_id, from_id, to_id)``. Directed, so ``A → B`` and ``B → A`` are two
rows and are expected to disagree.

:meth:`between` upserts rather than returning ``None``: a relationship that has
never been touched is not missing, it is neutral, and making every caller handle
that distinction would put the same three lines in a dozen places.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import dnd_relations
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.relationship import Relationship


class RelationRepo(ScopedRepo):
    """Directed relationships in one campaign."""

    collection = dnd_relations
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def between(self, from_id: Any, to_id: Any) -> Relationship:
        """How ``from_id`` stands toward ``to_id``. Neutral if never recorded."""
        doc = self.find_one({"from_id": from_id, "to_id": to_id})
        if doc:
            return Relationship.from_doc(doc)
        return Relationship(
            guild_id=self._scope.guild_id,
            campaign_id=self._scope.campaign_id,
            from_id=from_id,
            to_id=to_id,
        )

    def stored(self, from_id: Any, to_id: Any) -> Optional[Relationship]:
        """Only if it actually exists — for the panel, which should not invent
        rows just by rendering a page."""
        doc = self.find_one({"from_id": from_id, "to_id": to_id})
        return Relationship.from_doc(doc) if doc else None

    def outgoing(self, from_id: Any) -> list[Relationship]:
        """Everyone this entity has feelings about."""
        docs = self.find({"from_id": from_id}, sort=[("familiarity", -1)])
        return [Relationship.from_doc(d) for d in docs]

    def familiar(self, floor: float = 0.15, limit: int = 400) -> list[Relationship]:
        """Every directed pair who know each other well enough to talk.

        The rumour tick's one read. Bounded rather than complete: a town does
        not need every acquaintance considered every turn, and an unbounded
        query here is how a big campaign starts costing real money.
        """
        docs = self.find(
            {"familiarity": {"$gte": float(floor)}},
            sort=[("familiarity", -1)], limit=limit,
        )
        return [Relationship.from_doc(d) for d in docs]

    def incoming(self, to_id: Any) -> list[Relationship]:
        """Everyone who has feelings about this entity — often the more
        interesting direction, and the one a GM forgets to ask about."""
        docs = self.find({"to_id": to_id}, sort=[("familiarity", -1)])
        return [Relationship.from_doc(d) for d in docs]

    def count_for(self, from_id: Any) -> int:
        return self.count({"from_id": from_id})

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def save(self, relationship: Relationship) -> Relationship:
        """Upsert one side of a pair."""
        relationship.guild_id = self._scope.guild_id
        relationship.campaign_id = self._scope.campaign_id
        doc = relationship.to_doc()
        doc.pop("_id", None)

        existing = self.find_one(
            {"from_id": relationship.from_id, "to_id": relationship.to_id}
        )
        if existing:
            self.update({"_id": existing["_id"]}, doc)
            relationship.id = existing["_id"]
        else:
            relationship.id = self.insert(doc)
        return relationship

    def wipe_entity(self, entity_id: Any) -> int:
        """Remove both directions for an entity that is gone."""
        return self.delete_many({"from_id": entity_id}) + self.delete_many({"to_id": entity_id})


def relations_for(guild_id: int, campaign_id: Any) -> RelationRepo:
    return RelationRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
