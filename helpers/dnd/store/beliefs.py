"""
Belief repository — campaign-scoped.

Kept apart from the knowledge repository on purpose. Facts and beliefs live in
different collections because conflating them is the mistake that makes an NPC
omniscient: the moment "what is true" and "what Marla thinks" share a table,
someone writes a query that forgets the difference and the fog of war evaporates.

The read that matters is :meth:`held_by` — everything a single entity believes.
That is what a player's ``/look`` renders and what an NPC's decision will consume
in P3, and neither is ever handed the fact table.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import dnd_beliefs
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.belief import Belief


class BeliefRepo(ScopedRepo):
    """Beliefs in one campaign."""

    collection = dnd_beliefs
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def add(self, belief: Belief) -> Belief:
        belief.guild_id = self._scope.guild_id
        belief.campaign_id = self._scope.campaign_id
        doc = belief.to_doc()
        doc.pop("_id", None)
        belief.id = self.insert(doc)
        return belief

    def reinforce(self, belief_id: Any, amount: float = 0.1) -> int:
        """Strengthen a belief that was confirmed, saturating at 1.0.

        Multiplicative toward the ceiling rather than additive, so repetition
        strengthens conviction without ever making it absolute. Nobody should end
        up unable to be wrong.
        """
        current = self.get(belief_id)
        if current is None:
            return 0
        raised = 1 - (1 - current.confidence) * (1 - max(0.0, min(1.0, amount)))
        return self.update_by_id(belief_id, {"confidence": round(raised, 4)})

    def set_truth(self, belief_id: Any, truth: bool | None) -> int:
        """GM marks a belief true or false. Never visible to the holder."""
        return self.update_by_id(belief_id, {"truth": truth})

    def forget(self, belief_id: Any) -> int:
        return self.delete({"_id": belief_id})

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, belief_id: Any) -> Optional[Belief]:
        doc = self.by_id(belief_id)
        return Belief.from_doc(doc) if doc else None

    def held_by(self, holder_id: Any, *, limit: int = 0) -> list[Belief]:
        """Everything one entity believes — the fog-of-war read."""
        docs = self.find({"holder_id": holder_id}, sort=[("confidence", -1)], limit=limit)
        return [Belief.from_doc(d) for d in docs]

    def about(self, subject_id: Any) -> list[Belief]:
        """Everything anyone believes about one subject — the GM's "who is wrong
        about whom" view."""
        docs = self.find({"subject_id": subject_id}, sort=[("confidence", -1)])
        return [Belief.from_doc(d) for d in docs]

    def between(self, holder_id: Any, subject_id: Any) -> list[Belief]:
        docs = self.find({"holder_id": holder_id, "subject_id": subject_id})
        return [Belief.from_doc(d) for d in docs]

    def knows_that(self, holder_id: Any, claim: str) -> Optional[Belief]:
        """Whether this entity already holds a claim, so adopting it again
        reinforces rather than duplicates."""
        doc = self.find_one({"holder_id": holder_id, "claim": claim})
        return Belief.from_doc(doc) if doc else None

    def count_for(self, holder_id: Any) -> int:
        return self.count({"holder_id": holder_id})


def beliefs_for(guild_id: int, campaign_id: Any) -> BeliefRepo:
    return BeliefRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
