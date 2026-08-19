"""
Beliefs — what an entity *thinks* is true.

The highest-leverage idea in the design, and the one that separates this from a
notes database with dice attached:

    **Facts are what is true. Beliefs are what someone thinks is true.**
    NPC decisions read beliefs. Never world truth.

They are different collections and must never be conflated. Once belief is
per-entity and carries a source and a confidence, several things that products in
this space script individually all fall out of one model for free:

* NPCs who are **wrong**, and act confidently on it;
* NPCs who **lie** — asserting a belief they do not hold is just an action;
* **rumours** that propagate along the social graph, mutating as they go (P3);
* **fog of war**, because a player sheet renders that character's beliefs rather
  than the world;
* **dramatic irony**, which is most of what makes a table laugh.

This generalises the rumour system in ``cogs/chat.py``, which already stores a
fact about someone else with a source attribution — the best idea in the old
codebase, currently used for jokes.

MERGE NOTE: if the chat cog's ``rumours_heard`` is ever unified with this, the
shape to keep is *this* one — it has confidence, truth and mutation count, which
the chat version lacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# How a holder came by a belief. Source matters because it decides how confidence
# decays when it is passed on, and who gets blamed when it turns out to be wrong.
SOURCE_WITNESSED = "witnessed"   # saw it happen — highest confidence
SOURCE_TOLD = "told"             # heard it from someone
SOURCE_INFERRED = "inferred"     # worked it out
SOURCE_ASSUMED = "assumed"       # cultural or factional prior
SOURCES = (SOURCE_WITNESSED, SOURCE_TOLD, SOURCE_INFERRED, SOURCE_ASSUMED)

# Starting confidence per source.
SOURCE_CONFIDENCE = {
    SOURCE_WITNESSED: 0.95,
    SOURCE_TOLD: 0.6,
    SOURCE_INFERRED: 0.5,
    SOURCE_ASSUMED: 0.35,
}


@dataclass
class Belief:
    """One thing one entity holds to be true about another."""

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None

    holder_id: Any = None           # who believes it
    subject_id: Any = None          # who or what it is about
    claim: str = ""

    confidence: float = 0.6         # 0..1
    source_kind: str = SOURCE_TOLD
    source_id: Any = None           # who told them, when kind is "told"
    at: int = 0                     # world time it was formed

    # GM-visible only. The holder cannot see this and neither can the renderer
    # when it is building a player-facing view — an NPC that knows its own belief
    # is false is not holding a belief, it is lying, which is a different act.
    truth: bool | None = None

    mutations: int = 0              # times it changed hands and drifted
    shared_with: list = field(default_factory=list)

    def to_doc(self) -> dict:
        doc = {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "holder_id": self.holder_id,
            "subject_id": self.subject_id,
            "claim": self.claim,
            "confidence": float(self.confidence),
            "source": {"kind": self.source_kind, "by": self.source_id, "at": self.at},
            "truth": self.truth,
            "mutations": int(self.mutations),
            "shared_with": list(self.shared_with),
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Belief":
        source = doc.get("source") or {}
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            holder_id=doc.get("holder_id"),
            subject_id=doc.get("subject_id"),
            claim=str(doc.get("claim", "")),
            confidence=float(doc.get("confidence", 0.6)),
            source_kind=source.get("kind", SOURCE_TOLD),
            source_id=source.get("by"),
            at=int(source.get("at", 0)),
            truth=doc.get("truth"),
            mutations=int(doc.get("mutations", 0)),
            shared_with=list(doc.get("shared_with") or []),
        )

    # ------------------------------------------------------------------ #
    #  Presentation
    # ------------------------------------------------------------------ #
    @property
    def certainty(self) -> str:
        """How sure the holder sounds. Used when rendering a belief as speech,
        so an NPC hedges a rumour instead of stating it like a fact."""
        if self.confidence >= 0.85:
            return "certain"
        if self.confidence >= 0.6:
            return "confident"
        if self.confidence >= 0.35:
            return "unsure"
        return "doubtful"

    def is_wrong(self) -> bool:
        """Whether the GM has marked this belief false. Never shown to players."""
        return self.truth is False


def adopt(claim: str, *, holder_id, subject_id, source_kind: str = SOURCE_TOLD,
          source_id=None, at: int = 0, trust: float = 1.0, mutations: int = 0) -> Belief:
    """Form a belief, with confidence discounted by how it arrived.

    A belief heard from someone you barely trust is held weakly, and one that has
    already changed hands several times is weaker still — which is what makes a
    rumour degrade as it travels rather than arriving as gospel.
    """
    base = SOURCE_CONFIDENCE.get(source_kind, 0.5)
    drift = 0.85 ** max(0, mutations)
    return Belief(
        holder_id=holder_id,
        subject_id=subject_id,
        claim=claim,
        confidence=max(0.05, min(1.0, base * max(0.0, min(1.0, trust)) * drift)),
        source_kind=source_kind,
        source_id=source_id,
        at=at,
        mutations=mutations,
    )
