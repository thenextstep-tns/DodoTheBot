"""
Event log repository — append-only, campaign-scoped.

The only write method is :meth:`append`. There is no update and no delete: an
event is a record of something that happened, and editing one would make replay
a lie. A correction is another event.

Sequence numbers come from :meth:`CampaignRepo.next_seq`, which allocates them
with an atomic ``$inc``, and the unique ``(campaign_id, seq)`` index catches the
case where two writers somehow land on the same number anyway. On a duplicate we
retry with a fresh number rather than dropping the event — losing an event is
worse than writing it a moment later, because everything downstream (memory,
explainability, undo) is derived from this log.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from pymongo.errors import DuplicateKeyError

from config.database import dnd_events
from helpers.dnd.store.repo import ScopedRepo
from helpers.dnd.world.event import WorldEvent

# How many times to retry an append that collided on (campaign_id, seq).
_MAX_SEQ_RETRIES = 5


class EventRepo(ScopedRepo):
    """The event log for one campaign."""

    collection = dnd_events
    requires_campaign = True

    def __init__(self, scope, campaigns, collection=None) -> None:
        super().__init__(scope, collection)
        self._campaigns = campaigns

    # ------------------------------------------------------------------ #
    #  Append
    # ------------------------------------------------------------------ #
    def append(
        self,
        kind: str,
        *,
        actor_id: Any = None,
        targets: tuple = (),
        payload: Optional[dict] = None,
        seed: int = 0,
        caused_by: int | None = None,
        world_time: int = 0,
        seq: int | None = None,
    ) -> Optional[WorldEvent]:
        """Append an event, allocating its sequence number atomically.

        Pass ``seq`` when the caller already allocated one — a resolution has to
        derive its RNG seed from the sequence number *before* it can roll, so
        letting this method allocate a second one would burn a number and leave
        the event's ``seq`` disagreeing with the seed it was resolved under.

        A pre-allocated number that turns out to be taken is not fatal: the
        event is re-numbered and the seed it already carries keeps the
        resolution replayable.

        Returns ``None`` when the campaign is gone — appending to a deleted
        campaign would resurrect it as a fragment.
        """
        for attempt in range(_MAX_SEQ_RETRIES):
            if seq is None or attempt:
                seq = self._campaigns.next_seq(self._scope.campaign_id)
            if not seq:
                return None
            event = WorldEvent(
                guild_id=self._scope.guild_id,
                campaign_id=self._scope.campaign_id,
                seq=seq,
                kind=kind,
                world_time=world_time,
                actor_id=actor_id,
                targets=tuple(targets),
                payload=payload or {},
                seed=seed,
                caused_by=caused_by,
            )
            try:
                self.insert(event.to_doc())
            except DuplicateKeyError:
                continue        # someone took that number; take the next one
            return event
        return None

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def recent(self, limit: int = 20, *, kind: str | None = None) -> list[WorldEvent]:
        query: dict = {"kind": kind} if kind else {}
        docs = self.find(query, sort=[("seq", -1)], limit=limit)
        return [WorldEvent.from_doc(d) for d in docs]

    def since(self, seq: int) -> Iterator[WorldEvent]:
        """Every event after ``seq``, in order — the replay entry point."""
        for doc in self.find({"seq": {"$gt": int(seq)}}, sort=[("seq", 1)]):
            yield WorldEvent.from_doc(doc)

    def by_actor(self, actor_id: Any, limit: int = 20) -> list[WorldEvent]:
        docs = self.find({"actor_id": actor_id}, sort=[("seq", -1)], limit=limit)
        return [WorldEvent.from_doc(d) for d in docs]

    def by_legacy_id(self, legacy_id: Any) -> Optional[dict]:
        return self.find_one({"payload.legacy_id": legacy_id})
