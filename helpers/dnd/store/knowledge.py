"""
Knowledge repository and retrieval.

Two jobs: store facts across the four tiers, and answer "what does a renderer
need to know about *this* moment" within a token budget.

**Never stuff the whole knowledge base into a prompt.** Retrieval scores facts
and fills a budget, because a campaign bible grows without bound and a prompt
must not. This is also why the retriever is deterministic arithmetic rather than
a vector search: it runs in microseconds on one core, and, more usefully, you can
read *why* it ranked something first. A GM asking "why did it mention the
harbour?" deserves an answer.

MERGE NOTE (embeddings): if tag scoring proves too blunt, a 384-dim MiniLM is
~90 MB and would run locally alongside the bot. It is an encoder, not a
generator, so nothing like the arithmetic in ``docs/dnd/08-LLM-LAYER.md`` section
2, and still local. Keep it behind :meth:`KnowledgeRepo.retrieve` so the swap
stays additive.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from config.database import dnd_knowledge
from helpers.dnd.store.repo import Scope, ScopedRepo
from helpers.dnd.world.knowledge import (
    SCOPE_CAMPAIGN,
    SCOPE_GLOBAL,
    SCOPE_SCENE,
    SCOPE_SERVER,
    TIER_WEIGHT,
    Fact,
    auto_tags,
)

_WORD = re.compile(r"[a-z0-9]+")

# Retrieval weights. They sum to 1.0 so a score reads as a fraction and the terms
# stay comparable when one of them is tuned.
W_TAGS = 0.35
W_ENTITIES = 0.25
W_WEIGHT = 0.15
W_TIER = 0.15
W_RECENCY = 0.10

# Facts edited within this many days still earn some recency credit.
RECENCY_DAYS = 30.0


def terms_of(text: str) -> set[str]:
    """The query terms in a piece of text."""
    return {w for w in _WORD.findall((text or "").lower()) if len(w) > 2}


class KnowledgeRepo(ScopedRepo):
    """Facts for one campaign, plus the tiers above it.

    Campaign-scoped like every other repository, but reads deliberately reach
    *up* the tiers: a campaign needs its server's house rules and the global
    ruleset, and neither of those is a campaign document. Each tier builds its own
    filter in :meth:`_tier_query` rather than going through the base
    ``_filter``, so reaching up can never turn into reaching sideways into
    another guild.
    """

    collection = dnd_knowledge
    requires_campaign = True

    def _tier_query(self, scope: str, scope_id: Any = None) -> dict:
        """One tier's filter. Global facts have no guild and server facts have no
        campaign, which is why this cannot use the base scope filter."""
        if scope == SCOPE_GLOBAL:
            return {"scope": SCOPE_GLOBAL}
        if scope == SCOPE_SERVER:
            return {"scope": SCOPE_SERVER, "guild_id": self._scope.guild_id}
        if scope == SCOPE_SCENE:
            return {
                "scope": SCOPE_SCENE,
                "guild_id": self._scope.guild_id,
                "scope_id": scope_id,
            }
        return {
            "scope": SCOPE_CAMPAIGN,
            "guild_id": self._scope.guild_id,
            "scope_id": self._scope.campaign_id,
        }

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def add(self, fact: Fact) -> Fact:
        """Store a fact, filling in its scope and tags when the caller didn't."""
        if fact.scope == SCOPE_CAMPAIGN and fact.scope_id is None:
            fact.scope_id = self._scope.campaign_id
        if fact.scope == SCOPE_SERVER and fact.scope_id is None:
            fact.scope_id = self._scope.guild_id
        if fact.scope != SCOPE_GLOBAL:
            fact.guild_id = self._scope.guild_id
        if not fact.tags:
            fact.tags = auto_tags(fact.title, fact.text)
        fact.updated_at = datetime.now(timezone.utc)

        doc = fact.to_doc()
        doc.pop("_id", None)
        fact.id = self._col.insert_one(doc).inserted_id
        return fact

    def edit(self, fact_id: Any, patch: dict) -> int:
        patch = dict(patch)
        patch["updated_at"] = datetime.now(timezone.utc)
        return self._col.update_one(
            {"_id": fact_id, "guild_id": self._scope.guild_id}, {"$set": patch}
        ).modified_count

    def remove(self, fact_id: Any) -> int:
        # Scoped by guild: a fact id from another server must not be deletable
        # even by someone who guessed the id.
        return self._col.delete_one(
            {"_id": fact_id, "guild_id": self._scope.guild_id}
        ).deleted_count

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def get(self, fact_id: Any) -> Optional[Fact]:
        doc = self._col.find_one({"_id": fact_id, "guild_id": self._scope.guild_id})
        return Fact.from_doc(doc) if doc else None

    def tier(self, scope: str, scope_id: Any = None) -> list[Fact]:
        return [Fact.from_doc(d) for d in self._col.find(self._tier_query(scope, scope_id))]

    def all_visible(self, scene_id: Any = None, *, include_secret: bool = True) -> list[Fact]:
        """Every fact this campaign can see, across all four tiers, with
        overridden ones removed."""
        facts: list[Fact] = []
        for scope in (SCOPE_GLOBAL, SCOPE_SERVER, SCOPE_CAMPAIGN):
            facts.extend(self.tier(scope))
        if scene_id is not None:
            facts.extend(self.tier(SCOPE_SCENE, scene_id))
        if not include_secret:
            facts = [f for f in facts if not f.secret]
        return _drop_overridden(facts)

    def campaign_facts(self, *, kind: str | None = None) -> list[Fact]:
        """This campaign's own facts, for the panel and the lore commands."""
        query = self._tier_query(SCOPE_CAMPAIGN)
        if kind:
            query["kind"] = kind
        return [Fact.from_doc(d) for d in self._col.find(query)]

    def search(self, text: str, *, limit: int = 10, include_secret: bool = True) -> list[Fact]:
        wanted = terms_of(text)
        hits = [
            (f, f.matches(wanted))
            for f in self.all_visible(include_secret=include_secret)
        ]
        hits = [(f, n) for f, n in hits if n]
        hits.sort(key=lambda pair: (-pair[1], -pair[0].weight))
        return [f for f, _ in hits[:limit]]

    # ------------------------------------------------------------------ #
    #  Retrieval
    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        query: str = "",
        *,
        budget: int = 1200,
        max_facts: int = 40,
        scene_id: Any = None,
        present_entities: Optional[list] = None,
        for_player: bool = False,
    ) -> list[Fact]:
        """The facts worth knowing right now, inside a token budget.

        ``for_player`` drops secrets, so the same call serves both a GM view and
        a player view without a second code path. One path is what keeps the two
        from drifting apart and leaking something in the gap.
        """
        wanted = terms_of(query)
        present = set(present_entities or [])
        now = datetime.now(timezone.utc)

        scored: list[tuple[float, Fact]] = []
        for fact in self.all_visible(scene_id, include_secret=not for_player):
            tag_score = fact.matches(wanted) / max(1, len(wanted)) if wanted else 0.0
            entity_score = (
                len(present & set(fact.entities)) / len(present)
                if present and fact.entities
                else 0.0
            )
            age_days = max(0.0, (now - _aware(fact.updated_at)).total_seconds() / 86400.0)
            recency = max(0.0, 1.0 - age_days / RECENCY_DAYS)

            scored.append((
                W_TAGS * tag_score
                + W_ENTITIES * entity_score
                + W_WEIGHT * fact.weight
                + W_TIER * TIER_WEIGHT.get(fact.scope, 0.25)
                + W_RECENCY * recency,
                fact,
            ))

        scored.sort(key=lambda pair: -pair[0])

        # Tone facts are force-included: they are how the campaign *sounds*, and a
        # renderer that loses them produces generic prose no matter how good the
        # rest of the retrieval was.
        out: list[Fact] = []
        spent = 0
        for _score, fact in scored:
            if fact.kind == "tone":
                out.append(fact)
                spent += fact.cost

        chosen = {id(f) for f in out}
        for _score, fact in scored:
            if id(fact) in chosen:
                continue
            if len(out) >= max_facts or spent + fact.cost > budget:
                continue
            out.append(fact)
            chosen.add(id(fact))
            spent += fact.cost
        return out


def _aware(value: datetime) -> datetime:
    """Mongo can hand back naive datetimes, and comparing one to an aware ``now``
    raises. Treat naive values as UTC, which is what they are."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _drop_overridden(facts: list[Fact]) -> list[Fact]:
    """Remove any fact that a more specific tier explicitly replaced."""
    overridden = {f.overrides for f in facts if f.overrides is not None}
    return [f for f in facts if f.id not in overridden]


def knowledge_for(guild_id: int, campaign_id: Any) -> KnowledgeRepo:
    return KnowledgeRepo(Scope(guild_id=guild_id, campaign_id=campaign_id))
