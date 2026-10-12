"""
Knowledge — the four-tier fact model.

World knowledge is **chunked into facts**, never stored as prose blobs. A blob
cannot be retrieved selectively, which is exactly how prompts get fat and how the
old cog's ``history`` string ate its own context window.

Four tiers, resolved most-specific-first::

    scene  →  campaign  →  server  →  global

Deliberately the same fallback shape as ``helpers/lang_manager.LangManager.get``,
so the codebase has one mental model for layered configuration.

``overrides`` is what makes the layering honest: a campaign fact can *replace* a
global rule rather than merely sitting beside it. Without it, "layered knowledge"
quietly means "contradictory knowledge", and the engine would cheerfully retrieve
both halves of a contradiction and hand them to a renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Tiers, least specific first. The order matters: `TIER_WEIGHT` reads from it.
SCOPE_GLOBAL = "global"
SCOPE_SERVER = "server"
SCOPE_CAMPAIGN = "campaign"
SCOPE_SCENE = "scene"
SCOPES = (SCOPE_GLOBAL, SCOPE_SERVER, SCOPE_CAMPAIGN, SCOPE_SCENE)

# Retrieval bias per tier. What is on screen beats the campaign bible, which
# beats a server house rule, which beats a generic global fact.
TIER_WEIGHT = {
    SCOPE_SCENE: 1.0,
    SCOPE_CAMPAIGN: 0.75,
    SCOPE_SERVER: 0.45,
    SCOPE_GLOBAL: 0.25,
}

# What a fact is about. Free enough to be useful, closed enough that the panel
# can group and filter by it.
KIND_LORE = "lore"
KIND_RULE = "rule"
KIND_LOCATION = "location"
KIND_FACTION = "faction"
KIND_PERSON = "person"
KIND_ITEM = "item"
KIND_TONE = "tone"
KIND_CUSTOM = "custom"
KINDS = (KIND_LORE, KIND_RULE, KIND_LOCATION, KIND_FACTION,
         KIND_PERSON, KIND_ITEM, KIND_TONE, KIND_CUSTOM)

# Where a fact came from. `llm_promoted` marks something a model invented that a
# GM later accepted — worth being able to audit separately from hand-written lore.
SOURCE_GM = "gm"
SOURCE_SEED = "seed"
SOURCE_IMPORT = "import"
SOURCE_LLM = "llm_promoted"


@dataclass
class Fact:
    """One retrievable piece of world knowledge."""

    id: Any = None
    scope: str = SCOPE_CAMPAIGN
    scope_id: Any = None            # guild_id, campaign_id or scene_id; None for global
    guild_id: int = 0               # denormalised so the scope filter is one index hit

    kind: str = KIND_LORE
    title: str = ""
    text: str = ""
    tags: list[str] = field(default_factory=list)
    entities: list = field(default_factory=list)

    weight: float = 0.5             # GM-set importance, biases retrieval
    secret: bool = False            # GM/simulation only — never rendered to a player
    overrides: Any = None           # id of a lower-tier fact this replaces
    source: str = SOURCE_GM

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> dict:
        doc = {
            "scope": self.scope,
            "scope_id": self.scope_id,
            "guild_id": self.guild_id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "tags": [t.lower() for t in self.tags],
            "entities": list(self.entities),
            "weight": float(self.weight),
            "secret": bool(self.secret),
            "overrides": self.overrides,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Fact":
        return cls(
            id=doc.get("_id"),
            scope=doc.get("scope", SCOPE_CAMPAIGN),
            scope_id=doc.get("scope_id"),
            guild_id=int(doc.get("guild_id", 0)),
            kind=doc.get("kind", KIND_LORE),
            title=str(doc.get("title", "")),
            text=str(doc.get("text", "")),
            tags=[str(t).lower() for t in (doc.get("tags") or [])],
            entities=list(doc.get("entities") or []),
            weight=float(doc.get("weight", 0.5)),
            secret=bool(doc.get("secret", False)),
            overrides=doc.get("overrides"),
            source=doc.get("source", SOURCE_GM),
            created_at=doc.get("created_at") or datetime.now(timezone.utc),
            updated_at=doc.get("updated_at") or datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------ #
    #  Retrieval support
    # ------------------------------------------------------------------ #
    @property
    def cost(self) -> int:
        """Rough token cost, for budgeting a retrieval.

        Four characters per token is the usual English approximation and is
        deliberate: a real tokenizer would be a dependency and a per-fact CPU
        cost, to decide something a budget already treats as approximate.
        """
        return max(1, (len(self.title) + len(self.text)) // 4)

    def matches(self, terms: set[str]) -> int:
        """How many query terms this fact answers to, across tags and title."""
        if not terms:
            return 0
        haystack = set(self.tags) | set(self.title.lower().split())
        return len(terms & haystack)


def auto_tags(title: str, text: str, limit: int = 8) -> list[str]:
    """Tags derived from a fact's own words, so a GM never *has* to supply them.

    Deliberately dumb: lowercase words over three characters, minus a small
    stoplist, most-frequent first. A GM writing lore should not have to think
    about the retrieval index, and a mediocre tag beats an empty one — an
    untagged fact is invisible to tag-scored retrieval.
    """
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "was", "were",
        "has", "have", "had", "are", "but", "not", "you", "your", "his", "her",
        "its", "their", "them", "they", "who", "what", "when", "where", "which",
        "all", "any", "one", "two", "some", "more", "than", "then", "there",
    }
    counts: dict[str, int] = {}
    for raw in f"{title} {text}".lower().split():
        word = "".join(c for c in raw if c.isalnum())
        if len(word) > 3 and word not in stop:
            counts[word] = counts.get(word, 0) + 1
    return sorted(counts, key=lambda w: (-counts[w], w))[:limit]
