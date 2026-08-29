"""
Campaign repository — guild-scoped, since listing a server's campaigns is the one
query that legitimately spans them.

Also owns sequence allocation. ``next_seq`` uses a single atomic ``$inc`` on the
campaign document, which is what makes the unique ``(campaign_id, seq)`` index on
the event log a real concurrency control rather than a hopeful one: two players
acting at the same instant get different numbers from the database, not from a
counter in this process that a restart would forget.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Optional

from config.database import dnd_campaigns
from helpers.dnd.store.repo import ScopedRepo
from helpers.dnd.world.campaign import STATUS_ARCHIVED, Campaign


class CampaignRepo(ScopedRepo):
    """Campaigns for one guild."""

    collection = dnd_campaigns
    requires_campaign = False

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, campaign_id: Any) -> Optional[Campaign]:
        doc = self.by_id(campaign_id)
        return Campaign.from_doc(doc) if doc else None

    def by_name(self, name: str) -> Optional[Campaign]:
        """Look up by name, case-insensitively.

        Names are what players type, and nobody remembers capitalisation. The
        regex is escaped because a campaign called ``The Ash(en) Compact`` should
        be findable rather than a pattern error.
        """
        import re

        doc = self.find_one({"name": re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)})
        return Campaign.from_doc(doc) if doc else None

    def list(self, *, include_archived: bool = False) -> list[Campaign]:
        query: dict = {} if include_archived else {"status": {"$ne": STATUS_ARCHIVED}}
        return [Campaign.from_doc(d) for d in self.find(query, sort=[("created_at", 1)])]

    def for_member(self, user_id: int) -> list[Campaign]:
        """Campaigns this user plays in or runs."""
        return [
            campaign
            for campaign in self.list()
            if campaign.is_member(user_id)
        ]

    def by_channel(self, channel_id: int) -> Optional[Campaign]:
        doc = self.find_one({"channel_id": int(channel_id)})
        return Campaign.from_doc(doc) if doc else None

    def by_legacy_id(self, legacy_id: Any) -> Optional[Campaign]:
        doc = self.find_one({"legacy_id": legacy_id})
        return Campaign.from_doc(doc) if doc else None

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def create(self, campaign: Campaign) -> Campaign:
        if not campaign.seed:
            campaign.seed = random.getrandbits(32)
        campaign.created_at = campaign.updated_at = datetime.now(timezone.utc)
        doc = campaign.to_doc()
        doc.pop("_id", None)
        campaign.id = self.insert(doc)
        return campaign

    def save_settings(self, campaign_id: Any, settings: dict) -> int:
        return self.update_by_id(
            campaign_id, {"settings": settings, "updated_at": datetime.now(timezone.utc)}
        )

    def set_status(self, campaign_id: Any, status: str) -> int:
        return self.update_by_id(
            campaign_id, {"status": status, "updated_at": datetime.now(timezone.utc)}
        )

    def set_channel(self, campaign_id: Any, channel_id: int) -> int:
        return self.update_by_id(campaign_id, {"channel_id": int(channel_id)})

    def add_player(self, campaign_id: Any, user_id: int) -> int:
        return self.apply({"_id": campaign_id}, {"$addToSet": {"player_ids": int(user_id)}})

    def remove_player(self, campaign_id: Any, user_id: int) -> int:
        return self.apply({"_id": campaign_id}, {"$pull": {"player_ids": int(user_id)}})

    def add_gm(self, campaign_id: Any, user_id: int) -> int:
        return self.apply({"_id": campaign_id}, {"$addToSet": {"gm_ids": int(user_id)}})

    def remove_gm(self, campaign_id: Any, user_id: int) -> int:
        return self.apply({"_id": campaign_id}, {"$pull": {"gm_ids": int(user_id)}})

    # ------------------------------------------------------------------ #
    #  Sequence & world time
    # ------------------------------------------------------------------ #
    def next_seq(self, campaign_id: Any) -> int:
        """Atomically allocate the next event sequence number.

        Returns 0 if the campaign is gone, which callers treat as "don't write" —
        appending to a deleted campaign's log would resurrect it as a
        half-document.
        """
        doc = self._col.find_one_and_update(
            self._filter({"_id": campaign_id}),
            {"$inc": {"seq": 1}},
            return_document=True,   # pymongo.ReturnDocument.AFTER
        )
        return int(doc.get("seq", 0)) if doc else 0

    def advance_time(self, campaign_id: Any, minutes: int) -> int:
        doc = self._col.find_one_and_update(
            self._filter({"_id": campaign_id}),
            {"$inc": {"world_time": int(minutes)}},
            return_document=True,
        )
        return int(doc.get("world_time", 0)) if doc else 0
