"""
Clock repository — campaign-scoped.

Fronts are per campaign and there are never many, so this is deliberately plain:
the only read that matters is "everything still ticking", which the world tick
asks for once per campaign per turn.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import dnd_clocks
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.clock import COMPLETE, RUNNING, Clock


class ClockRepo(ScopedRepo):
    """Faction clocks in one campaign."""

    collection = dnd_clocks
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def create(self, clock: Clock) -> Clock:
        clock.guild_id = self._scope.guild_id
        clock.campaign_id = self._scope.campaign_id
        doc = clock.to_doc()
        doc.pop("_id", None)
        clock.id = self.insert(doc)
        return clock

    def save(self, clock: Clock) -> int:
        """Write a clock back after the pure layer has moved it."""
        doc = clock.to_doc()
        doc.pop("_id", None)
        doc.pop("guild_id", None)
        doc.pop("campaign_id", None)
        return self.update_by_id(clock.id, doc)

    def set_status(self, clock_id: Any, status: str) -> int:
        return self.update_by_id(clock_id, {"status": status})

    def block(self, clock_id: Any, entity_id: Any) -> int:
        """Someone is holding this front shut. Idempotent."""
        clock = self.get(clock_id)
        if clock is None or entity_id in clock.blocked_by:
            return 0
        return self.update_by_id(
            clock_id, {"blocked_by": clock.blocked_by + [entity_id]}
        )

    def unblock(self, clock_id: Any, entity_id: Any) -> int:
        clock = self.get(clock_id)
        if clock is None:
            return 0
        remaining = [e for e in clock.blocked_by if str(e) != str(entity_id)]
        return self.update_by_id(clock_id, {"blocked_by": remaining})

    def remove(self, clock_id: Any) -> int:
        return self.delete({"_id": clock_id})

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, clock_id: Any) -> Optional[Clock]:
        doc = self.by_id(clock_id)
        return Clock.from_doc(doc) if doc else None

    def list(self, *, status: str | None = None) -> list[Clock]:
        query = {"status": status} if status else {}
        return [Clock.from_doc(d) for d in self.find(query, sort=[("created_at", 1)])]

    def ticking(self) -> list[Clock]:
        """Every clock the world tick should try to move.

        Blocked ones are included on purpose: whether a front is held shut is a
        property of the clock, not of the query, and the pure layer decides. A
        repository that filtered them would put game rules in the storage layer.
        """
        return [Clock.from_doc(d) for d in self.find({"status": RUNNING})]

    def by_name(self, name: str) -> Optional[Clock]:
        doc = self.find_one({"name": name})
        return Clock.from_doc(doc) if doc else None

    def completed(self) -> list[Clock]:
        return [Clock.from_doc(d) for d in self.find({"status": COMPLETE})]


def clocks_for(guild_id: int, campaign_id: Any) -> ClockRepo:
    return ClockRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
