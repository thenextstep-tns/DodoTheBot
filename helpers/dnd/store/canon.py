"""
The canon queue — the mechanism that stops the world drifting.

Anything a model invents (a name, a tavern, a cousin, a rule interpretation)
lands here, never straight into ``dnd_knowledge``. A GM promotes it, edits it, or
throws it out.

Nothing writes to this queue yet: the renderer that fills it arrives in P4. The
machinery and its panel page exist now because the *shape* of P4 depends on it —
building the renderer first and bolting on review afterwards is precisely how
every competitor ended up with a world that contradicts itself by hour three.

**Soft canon** is the compromise that makes this usable. A pending proposal stays
retrievable at low weight for continuity *within the current arc*, but is not
authoritative and is not exported. Hard-rejecting an invention mid-scene produces
incoherent prose; accepting everything produces drift. Soft canon keeps the scene
readable and defers the ruling to someone with authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from config.database import dnd_canon_queue
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.knowledge import SOURCE_LLM, Fact

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_AUTO = "auto"          # accepted automatically by the confidence threshold
STATUSES = (STATUS_PENDING, STATUS_ACCEPTED, STATUS_REJECTED, STATUS_AUTO)

# Weight a pending proposal carries in retrieval. Low enough that real canon
# always outranks it, high enough that a scene stays coherent while the GM sleeps.
SOFT_CANON_WEIGHT = 0.15


class CanonRepo(ScopedRepo):
    """Proposed canon awaiting a GM's ruling, for one campaign."""

    collection = dnd_canon_queue
    requires_campaign = True

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def propose(
        self,
        *,
        kind: str,
        title: str,
        text: str,
        tags: Optional[list] = None,
        confidence: float = 0.5,
        event_seq: int | None = None,
        task: str = "",
    ) -> dict:
        """Queue something a model invented. Called by the renderer in P4."""
        doc = {
            "status": STATUS_PENDING,
            "kind": kind,
            "proposal": {
                "title": title,
                "text": text,
                "tags": [str(t).lower() for t in (tags or [])],
            },
            "context": {"event_seq": event_seq, "task": task},
            "confidence": float(confidence),
            "created_at": datetime.now(timezone.utc),
            "resolved_by": None,
            "resolved_at": None,
        }
        doc["_id"] = self.insert(doc)
        return doc

    def accept(self, proposal_id: Any, knowledge_repo, *, actor_id: int = 0,
               auto: bool = False) -> Optional[Fact]:
        """Promote a proposal into real campaign knowledge.

        Returns the created :class:`Fact`, or ``None`` if the proposal is gone or
        already resolved. Resolving is guarded so two GMs clicking at once can't
        promote the same invention twice.
        """
        doc = self.find_one({"_id": proposal_id, "status": STATUS_PENDING})
        if doc is None:
            return None

        proposal = doc.get("proposal") or {}
        fact = knowledge_repo.add(
            Fact(
                kind=doc.get("kind", "lore"),
                title=str(proposal.get("title", "")),
                text=str(proposal.get("text", "")),
                tags=list(proposal.get("tags") or []),
                source=SOURCE_LLM,
                weight=0.5,
            )
        )
        self.update(
            {"_id": proposal_id},
            {
                "status": STATUS_AUTO if auto else STATUS_ACCEPTED,
                "resolved_by": int(actor_id),
                "resolved_at": datetime.now(timezone.utc),
                "fact_id": fact.id,
            },
        )
        return fact

    def reject(self, proposal_id: Any, *, actor_id: int = 0) -> int:
        return self.update(
            {"_id": proposal_id, "status": STATUS_PENDING},
            {
                "status": STATUS_REJECTED,
                "resolved_by": int(actor_id),
                "resolved_at": datetime.now(timezone.utc),
            },
        )

    def edit_proposal(self, proposal_id: Any, *, title: str = None, text: str = None) -> int:
        patch = {}
        if title is not None:
            patch["proposal.title"] = title
        if text is not None:
            patch["proposal.text"] = text
        return self.update({"_id": proposal_id}, patch) if patch else 0

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def pending(self, limit: int = 50) -> list[dict]:
        return list(self.find({"status": STATUS_PENDING}, sort=[("created_at", 1)], limit=limit))

    def pending_count(self) -> int:
        return self.count({"status": STATUS_PENDING})

    def recent(self, limit: int = 25) -> list[dict]:
        return list(self.find(sort=[("created_at", -1)], limit=limit))

    def soft_canon(self) -> list[Fact]:
        """Pending proposals as low-weight facts, for within-arc continuity.

        These are never exported and never authoritative — see the module
        docstring on why they are retrievable at all.
        """
        out = []
        for doc in self.pending(limit=25):
            proposal = doc.get("proposal") or {}
            out.append(
                Fact(
                    id=doc.get("_id"),
                    scope="campaign",
                    scope_id=self._scope.campaign_id,
                    guild_id=self._scope.guild_id,
                    kind=doc.get("kind", "lore"),
                    title=str(proposal.get("title", "")),
                    text=str(proposal.get("text", "")),
                    tags=list(proposal.get("tags") or []),
                    weight=SOFT_CANON_WEIGHT,
                    source=SOURCE_LLM,
                )
            )
        return out


def canon_for(guild_id: int, campaign_id: Any) -> CanonRepo:
    return CanonRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
