"""
Dodo Tabletop — P1 acceptance tests.

``docs/dnd/12-ROADMAP.md`` asks P1 to prove two things:

1. ``/look`` shows a player **their character's beliefs**, not world truth;
2. a campaign fact **overriding** a global rule visibly changes what is retrieved.

Plus the properties the rest of the phase rests on: retrieval stays inside its
budget, secrets never reach a player view, and the canon queue only turns a
proposal into canon through an explicit acceptance.

Run with ``py tests/test_dnd_p1.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fake_mongo import DuplicateKeyError, FakeCollection  # noqa: E402

import config.database as database  # noqa: E402

_FAKES = {
    name: FakeCollection(name)
    for name in (
        "dnd_campaigns", "dnd_entities", "dnd_scenes", "dnd_events", "dnd_knowledge",
        "dnd_memories", "dnd_beliefs", "dnd_relations", "dnd_clocks",
        "dnd_canon_queue", "dnd_snapshots",
    )
}
for _name, _fake in _FAKES.items():
    setattr(database, _name, _fake)

import pymongo.errors  # noqa: E402

pymongo.errors.DuplicateKeyError = DuplicateKeyError

from helpers.dnd.store import campaign_store, campaigns_for  # noqa: E402
from helpers.dnd.store import beliefs as beliefs_module  # noqa: E402
from helpers.dnd.store import campaigns as campaigns_module  # noqa: E402
from helpers.dnd.store import canon as canon_module  # noqa: E402
from helpers.dnd.store import entities as entities_module  # noqa: E402
from helpers.dnd.store import events as events_module  # noqa: E402
from helpers.dnd.store import knowledge as knowledge_module  # noqa: E402
from helpers.dnd.store import scenes as scenes_module  # noqa: E402
from helpers.dnd.world.belief import (  # noqa: E402
    SOURCE_TOLD,
    SOURCE_WITNESSED,
    adopt,
)
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.entity import KIND_NPC, KIND_PC, Entity, Identity  # noqa: E402
from helpers.dnd.world.knowledge import (  # noqa: E402
    SCOPE_CAMPAIGN,
    SCOPE_GLOBAL,
    SCOPE_SERVER,
    Fact,
    auto_tags,
)

for _module, _attr in (
    (campaigns_module.CampaignRepo, "dnd_campaigns"),
    (entities_module.EntityRepo, "dnd_entities"),
    (events_module.EventRepo, "dnd_events"),
    (scenes_module.SceneRepo, "dnd_scenes"),
    (knowledge_module.KnowledgeRepo, "dnd_knowledge"),
    (beliefs_module.BeliefRepo, "dnd_beliefs"),
    (canon_module.CanonRepo, "dnd_canon_queue"),
):
    _module.collection = _FAKES[_attr]
events_module.DuplicateKeyError = DuplicateKeyError

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


def _campaign(guild: int, name: str) -> tuple:
    campaign = campaigns_for(guild).create(
        Campaign(guild_id=guild, name=name, ruleset="freeform", gm_ids=[1])
    )
    return campaign, campaign_store(guild, campaign.id)


# --------------------------------------------------------------------------- #
#  1. The fact model
# --------------------------------------------------------------------------- #
def test_facts() -> None:
    tags = auto_tags("The Ashen Compact", "Twelve houses swore to burn their own fleet.")
    check("facts: auto-tags skip stopwords", "the" not in tags and "compact" in tags, str(tags))
    check("facts: auto-tags are bounded", len(tags) <= 8)

    fact = Fact(title="A", text="x" * 400)
    check("facts: cost tracks length", 90 < fact.cost < 110, str(fact.cost))
    check("facts: roundtrip", Fact.from_doc(fact.to_doc()).text == fact.text)
    check("facts: tags are lowercased on write",
          Fact(title="T", text="t", tags=["Harbour"]).to_doc()["tags"] == ["harbour"])

    _campaign(9101, "Tagging")
    check("facts: matching counts overlapping terms",
          Fact(title="Marla Venn", text="", tags=["harbour", "dock"]).matches({"harbour", "venn"}) == 2)


# --------------------------------------------------------------------------- #
#  2. Tier layering and overrides — a P1 acceptance criterion
# --------------------------------------------------------------------------- #
def test_tiers_and_overrides() -> None:
    campaign, store = _campaign(9102, "Layers")
    kb = store.knowledge

    # A global rule everyone inherits.
    global_rule = kb.add(Fact(
        scope=SCOPE_GLOBAL, kind="rule", title="Falling damage",
        text="1d6 per 10 feet.", weight=0.5,
    ))
    kb.add(Fact(scope=SCOPE_SERVER, kind="rule", title="House rule: crits",
                text="Crits max the first die.", weight=0.6))
    kb.add(Fact(scope=SCOPE_CAMPAIGN, kind="lore", title="The Ashen Compact",
                text="Twelve houses swore to burn their own fleet.", weight=0.8))

    visible = {f.title for f in kb.all_visible()}
    check("tiers: campaign sees all three tiers",
          visible == {"Falling damage", "House rule: crits", "The Ashen Compact"}, str(visible))

    # Now the campaign explicitly replaces the global rule.
    kb.add(Fact(
        scope=SCOPE_CAMPAIGN, kind="rule", title="Falling damage (Ashen)",
        text="1d6 per 10 feet, and you land badly.", overrides=global_rule.id, weight=0.9,
    ))
    after = {f.title for f in kb.all_visible()}
    check("tiers: an override removes the fact it replaces",
          "Falling damage" not in after and "Falling damage (Ashen)" in after, str(after))

    # Retrieval reflects the override too, not just the listing.
    retrieved = {f.title for f in kb.retrieve("falling damage", budget=2000)}
    check("tiers: retrieval honours the override", "Falling damage" not in retrieved)

    # A more specific tier outranks a general one at equal relevance. Needs a
    # global fact that survives, since the first one was just overridden away.
    kb.add(Fact(scope=SCOPE_GLOBAL, kind="rule", title="Cover",
                text="Half cover grants +2.", weight=0.5))
    ranked = kb.retrieve("", budget=4000)
    scopes = [f.scope for f in ranked]
    check("tiers: campaign facts outrank global ones",
          scopes.index(SCOPE_CAMPAIGN) < scopes.index(SCOPE_GLOBAL), str(scopes))


# --------------------------------------------------------------------------- #
#  3. Retrieval: budget, relevance, tone
# --------------------------------------------------------------------------- #
def test_retrieval() -> None:
    campaign, store = _campaign(9103, "Retrieval")
    kb = store.knowledge

    for i in range(40):
        kb.add(Fact(kind="lore", title=f"Fact {i}", text="filler " * 40, weight=0.5))
    kb.add(Fact(kind="tone", title="Tone", text="grim, wry, low-magic", weight=0.2))
    kb.add(Fact(kind="location", title="North dock", text="Rope, tar and rain.",
                tags=["dock", "harbour"], weight=0.9))

    tight = kb.retrieve("", budget=300)
    spent = sum(f.cost for f in tight)
    check("retrieval: stays inside the budget", spent <= 300 + 60, f"spent {spent}")
    check("retrieval: returns something at a small budget", len(tight) >= 1)

    check("retrieval: tone is always included",
          any(f.kind == "tone" for f in kb.retrieve("", budget=200)))

    hits = kb.retrieve("harbour dock", budget=2000)
    check("retrieval: relevant facts rank first", hits[0].title in ("Tone", "North dock"),
          hits[0].title)
    check("retrieval: query beats filler",
          hits.index(next(f for f in hits if f.title == "North dock")) < 3)

    capped = kb.retrieve("", budget=100000, max_facts=5)
    check("retrieval: respects max_facts", len(capped) <= 5, str(len(capped)))


# --------------------------------------------------------------------------- #
#  4. Secrets never reach a player — the fog-of-war guarantee
# --------------------------------------------------------------------------- #
def test_secrets() -> None:
    campaign, store = _campaign(9104, "Secrets")
    kb = store.knowledge
    kb.add(Fact(kind="lore", title="Public", text="The harbour smells of tar.", weight=0.5))
    kb.add(Fact(kind="lore", title="Hidden", text="The harbourmaster is a Compact plant.",
                secret=True, weight=1.0))

    gm_facts = {f.title for f in kb.retrieve("harbour", budget=5000)}
    player_facts = {f.title for f in kb.retrieve("harbour", budget=5000, for_player=True)}
    check("secrets: GM sees the secret", "Hidden" in gm_facts)
    check("secrets: player never does", "Hidden" not in player_facts, str(player_facts))
    check("secrets: player still sees public lore", "Public" in player_facts)

    # Even a direct search must respect it.
    found = {f.title for f in kb.search("Compact", include_secret=False)}
    check("secrets: search excludes them too", "Hidden" not in found)
    check("secrets: a high weight cannot smuggle one through",
          "Hidden" not in {f.title for f in kb.retrieve("", budget=5000, for_player=True)})


# --------------------------------------------------------------------------- #
#  5. Beliefs
# --------------------------------------------------------------------------- #
def test_beliefs() -> None:
    campaign, store = _campaign(9105, "Beliefs")
    marla = store.entities.create(Entity(
        guild_id=9105, campaign_id=campaign.id, kind=KIND_NPC,
        identity=Identity(name="Marla Venn"),
    ))
    ondry = store.entities.create(Entity(
        guild_id=9105, campaign_id=campaign.id, kind=KIND_NPC,
        identity=Identity(name="Ondry"),
    ))

    witnessed = adopt("the dock burned", holder_id=marla.id, subject_id=ondry.id,
                      source_kind=SOURCE_WITNESSED)
    third_hand = adopt("the dock burned", holder_id=ondry.id, subject_id=marla.id,
                       source_kind=SOURCE_TOLD, trust=0.5, mutations=2)
    check("beliefs: witnessing beats hearsay", witnessed.confidence > third_hand.confidence,
          f"{witnessed.confidence:.2f} vs {third_hand.confidence:.2f}")
    check("beliefs: retelling degrades confidence", third_hand.confidence < 0.4)
    check("beliefs: certainty reads in words",
          witnessed.certainty == "certain" and third_hand.certainty == "doubtful")

    store.beliefs.add(witnessed)
    store.beliefs.add(third_hand)
    check("beliefs: held_by is per entity",
          len(store.beliefs.held_by(marla.id)) == 1 and len(store.beliefs.held_by(ondry.id)) == 1)
    check("beliefs: about finds every holder", len(store.beliefs.about(ondry.id)) == 1)

    # Reinforcement saturates rather than reaching certainty.
    stored = store.beliefs.held_by(ondry.id)[0]
    for _ in range(50):
        store.beliefs.reinforce(stored.id, 0.2)
    reinforced = store.beliefs.get(stored.id)
    check("beliefs: reinforcement rises", reinforced.confidence > third_hand.confidence)
    check("beliefs: but never reaches certainty", reinforced.confidence < 1.0,
          str(reinforced.confidence))

    # Truth is the GM's, and separate from what the holder feels.
    store.beliefs.set_truth(stored.id, False)
    check("beliefs: a belief can be false while confidently held",
          store.beliefs.get(stored.id).is_wrong() and store.beliefs.get(stored.id).confidence > 0.5)

    check("beliefs: knows_that finds an existing claim",
          store.beliefs.knows_that(marla.id, "the dock burned") is not None)
    check("beliefs: knows_that does not invent one",
          store.beliefs.knows_that(marla.id, "never said") is None)


# --------------------------------------------------------------------------- #
#  6. Belief is per entity, not per world — the /look guarantee
# --------------------------------------------------------------------------- #
def test_fog_of_war() -> None:
    campaign, store = _campaign(9106, "Fog")
    pc = store.entities.create(Entity(
        guild_id=9106, campaign_id=campaign.id, kind=KIND_PC, owner_id=42,
        identity=Identity(name="Kesh"),
    ))
    npc = store.entities.create(Entity(
        guild_id=9106, campaign_id=campaign.id, kind=KIND_NPC,
        identity=Identity(name="Marla Venn"),
    ))

    store.beliefs.add(adopt("the north dock is safe", holder_id=pc.id, subject_id=npc.id,
                            source_kind=SOURCE_TOLD))
    store.beliefs.add(adopt("the north dock is watched", holder_id=npc.id, subject_id=npc.id,
                            source_kind=SOURCE_WITNESSED))
    store.knowledge.add(Fact(kind="lore", title="The watch",
                             text="The Compact watches the north dock.", secret=True))

    kesh_sees = [b.claim for b in store.beliefs.held_by(pc.id)]
    check("fog: the player sees only their own belief", kesh_sees == ["the north dock is safe"],
          str(kesh_sees))
    check("fog: the player does not inherit the NPC's belief",
          "the north dock is watched" not in kesh_sees)
    check("fog: nor the secret fact",
          "The watch" not in {f.title for f in store.knowledge.retrieve("dock", for_player=True)})
    check("fog: the GM can see all of it",
          len(store.beliefs.held_by(npc.id)) == 1
          and "The watch" in {f.title for f in store.knowledge.retrieve("dock")})


# --------------------------------------------------------------------------- #
#  7. The canon queue
# --------------------------------------------------------------------------- #
def test_canon() -> None:
    campaign, store = _campaign(9107, "Canon")
    proposal = store.canon.propose(
        kind="person", title="Ondry the ferryman",
        text="Poles the estuary crossing; never speaks of the fire.",
        confidence=0.7, task="render_dialogue",
    )
    check("canon: a proposal starts pending", store.canon.pending_count() == 1)
    check("canon: it is NOT canon yet",
          not any(f.title == "Ondry the ferryman" for f in store.knowledge.campaign_facts()))

    # Soft canon keeps a scene coherent without being authoritative.
    soft = store.canon.soft_canon()
    check("canon: pending is retrievable as soft canon", len(soft) == 1)
    check("canon: soft canon is low-weight", soft[0].weight <= 0.2, str(soft[0].weight))

    fact = store.canon.accept(proposal["_id"], store.knowledge, actor_id=7)
    check("canon: accepting creates a real fact", fact is not None)
    check("canon: it is canon now",
          any(f.title == "Ondry the ferryman" for f in store.knowledge.campaign_facts()))
    check("canon: provenance is recorded", fact.source == "llm_promoted")
    check("canon: the queue is empty again", store.canon.pending_count() == 0)

    # Accepting twice must not duplicate the fact.
    again = store.canon.accept(proposal["_id"], store.knowledge, actor_id=7)
    check("canon: double-accept is refused", again is None)
    check("canon: no duplicate fact",
          sum(1 for f in store.knowledge.campaign_facts()
              if f.title == "Ondry the ferryman") == 1)

    rejected = store.canon.propose(kind="lore", title="A bad idea", text="...")
    store.canon.reject(rejected["_id"], actor_id=7)
    check("canon: rejection clears the queue", store.canon.pending_count() == 0)
    check("canon: a rejected proposal never becomes a fact",
          not any(f.title == "A bad idea" for f in store.knowledge.campaign_facts()))


# --------------------------------------------------------------------------- #
#  8. Knowledge and belief stay inside their tenant
# --------------------------------------------------------------------------- #
def test_tenancy() -> None:
    campaign_a, store_a = _campaign(9201, "Twin")
    campaign_b, store_b = _campaign(9202, "Twin")

    store_a.knowledge.add(Fact(kind="lore", title="Shared name", text="A's version."))
    store_b.knowledge.add(Fact(kind="lore", title="Shared name", text="B's version."))
    store_a.knowledge.add(Fact(scope=SCOPE_SERVER, kind="rule", title="A house rule",
                               text="Only on server A."))

    a_titles = [f.text for f in store_a.knowledge.campaign_facts()]
    b_titles = [f.text for f in store_b.knowledge.campaign_facts()]
    check("tenancy: campaign facts do not cross", a_titles == ["A's version."], str(a_titles))
    check("tenancy: nor the other way", b_titles == ["B's version."], str(b_titles))

    b_visible = {f.title for f in store_b.knowledge.all_visible()}
    check("tenancy: server-tier facts stay on their server",
          "A house rule" not in b_visible, str(b_visible))

    entity_a = store_a.entities.create(Entity(
        guild_id=9201, campaign_id=campaign_a.id, identity=Identity(name="X")))
    store_a.beliefs.add(adopt("secret plan", holder_id=entity_a.id, subject_id=entity_a.id))
    check("tenancy: beliefs do not cross", len(store_b.beliefs.held_by(entity_a.id)) == 0)

    store_b.canon.propose(kind="lore", title="B only", text="...")
    check("tenancy: canon queues are separate",
          store_a.canon.pending_count() == 0 and store_b.canon.pending_count() == 1)


def main() -> int:
    for test in (
        test_facts,
        test_tiers_and_overrides,
        test_retrieval,
        test_secrets,
        test_beliefs,
        test_fog_of_war,
        test_canon,
        test_tenancy,
    ):
        test()

    for line in PASSED:
        print(f"  ok   {line}")
    for line in FAILED:
        print(f"  FAIL {line}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
