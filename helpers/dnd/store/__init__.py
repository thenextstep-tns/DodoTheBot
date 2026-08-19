"""
Storage layer.

Nothing outside this package touches a ``dnd_*`` collection handle. Everything
goes through a scoped repository, so a query that forgets its tenant is not a bug
waiting to happen — it does not compile into a valid call.

Two entry points:

``campaign_store(guild_id, campaign_id)``
    Every repository for one campaign, sharing one scope.

``campaigns_for(guild_id)``
    Just the campaign repository, for the guild-wide questions ("what campaigns
    are on this server?") that legitimately precede knowing a campaign.
"""

from __future__ import annotations

from typing import Any

from helpers.dnd.store.beliefs import BeliefRepo
from helpers.dnd.store.campaigns import CampaignRepo
from helpers.dnd.store.canon import CanonRepo
from helpers.dnd.store.entities import EntityRepo
from helpers.dnd.store.events import EventRepo
from helpers.dnd.store.indices import ensure_indices  # noqa: F401  (re-exported)
from helpers.dnd.store.knowledge import KnowledgeRepo
from helpers.dnd.store.repo import Scope, ScopedRepo, ScopeError  # noqa: F401
from helpers.dnd.store.scenes import SceneRepo


class CampaignStore:
    """The repositories for one campaign, all sharing a single scope.

    Holding them together is what keeps the scope from being re-derived (and
    mistyped) at each call site, and it gives the cog one object to pass around
    instead of four.
    """

    def __init__(self, guild_id: int, campaign_id: Any) -> None:
        self.scope = Scope(guild_id=guild_id, campaign_id=campaign_id)
        # Campaign lookups are guild-wide even from inside a campaign — the
        # campaign document itself is not campaign-scoped.
        self.campaigns = CampaignRepo(Scope(guild_id=guild_id))
        self.entities = EntityRepo(self.scope)
        self.scenes = SceneRepo(self.scope)
        self.events = EventRepo(self.scope, self.campaigns)
        # P1: layered world knowledge, per-entity belief, and the review queue
        # that keeps invented facts out of canon until a GM says otherwise.
        self.knowledge = KnowledgeRepo(self.scope)
        self.beliefs = BeliefRepo(self.scope)
        self.canon = CanonRepo(self.scope)

    @property
    def guild_id(self) -> int:
        return self.scope.guild_id

    @property
    def campaign_id(self) -> Any:
        return self.scope.campaign_id


def campaign_store(guild_id: int, campaign_id: Any) -> CampaignStore:
    return CampaignStore(guild_id, campaign_id)


def campaigns_for(guild_id: int) -> CampaignRepo:
    return CampaignRepo(Scope(guild_id=guild_id))
