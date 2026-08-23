"""
Dodo Tabletop — P2 acceptance tests.

``docs/dnd/12-ROADMAP.md`` asks P2 to prove four things:

1. two witnesses to one event hold **measurably different** memories;
2. a memory **degrades over simulated months and confabulates** a detail;
3. an **imprint survives** everything;
4. memory **never exceeds its budget**.

Plus the properties of the forgetting model itself, which are the substance of
the phase:

* the curve is a **power law** — steep early, long tail — not linear;
* **retention is per character**: some remember nearly everything, some don't;
* what is kept **correlates with the value system**, not just with volume;
* **nothing is baked in**: every constant is tunable, and forgetting can be
  switched off entirely.

Run with ``py tests/test_dnd_p2.py``.
"""

from __future__ import annotations

import os
import sys
from random import Random
from typing import Mapping

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

from helpers.dnd import minds  # noqa: E402
from helpers.dnd.mind import needs as needs_mod  # noqa: E402
from helpers.dnd.mind import relationships as rel_mod  # noqa: E402
from helpers.dnd.mind import stakes  # noqa: E402
from helpers.dnd.mind import traits as traits_mod  # noqa: E402
from helpers.dnd.mind.memory import consolidate, decay, encode, recall  # noqa: E402
from helpers.dnd.mind.memory import values as value_model  # noqa: E402
from helpers.dnd.mind.traits import Traits, derive_traits  # noqa: E402
from helpers.dnd.store import campaign_store, campaigns_for  # noqa: E402
from helpers.dnd.store import beliefs as beliefs_module  # noqa: E402
from helpers.dnd.store import campaigns as campaigns_module  # noqa: E402
from helpers.dnd.store import canon as canon_module  # noqa: E402
from helpers.dnd.store import clocks as clocks_module  # noqa: E402
from helpers.dnd.store import entities as entities_module  # noqa: E402
from helpers.dnd.store import events as events_module  # noqa: E402
from helpers.dnd.store import knowledge as knowledge_module  # noqa: E402
from helpers.dnd.store import memories as memories_module  # noqa: E402
from helpers.dnd.store import relations as relations_module  # noqa: E402
from helpers.dnd.store import scenes as scenes_module  # noqa: E402
from helpers.dnd import rules  # noqa: E402
from helpers.dnd.mind import goals as goal_math  # noqa: E402
from helpers.dnd.world import goal as goal_model  # noqa: E402
from helpers.dnd.rules import ruleset as rs  # noqa: E402
from helpers.dnd.tuning import TUNABLES, Tuning  # noqa: E402
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.scene import Scene  # noqa: E402
from helpers.dnd.world.entity import KIND_NPC, Entity, Identity  # noqa: E402
from helpers.dnd.world.belief import Belief, adopt  # noqa: E402
from helpers.dnd.world.memory import TIER_IMPRINT, TIER_MID, Memory  # noqa: E402
from helpers.dnd.world.relationship import Relationship  # noqa: E402

for _cls, _name in (
    (campaigns_module.CampaignRepo, "dnd_campaigns"),
    (entities_module.EntityRepo, "dnd_entities"),
    (events_module.EventRepo, "dnd_events"),
    (scenes_module.SceneRepo, "dnd_scenes"),
    (knowledge_module.KnowledgeRepo, "dnd_knowledge"),
    (beliefs_module.BeliefRepo, "dnd_beliefs"),
    (canon_module.CanonRepo, "dnd_canon_queue"),
    (clocks_module.ClockRepo, "dnd_clocks"),
    (memories_module.MemoryRepo, "dnd_memories"),
    (relations_module.RelationRepo, "dnd_relations"),
):
    _cls.collection = _FAKES[_name]

# Server-level tuning lives in Mongo too; keep the tests off the real database.
from helpers.dnd import parameters as dnd_parameters  # noqa: E402

dnd_parameters.TUNING_COLLECTION = FakeCollection("DndTuning")

PASSED: list[str] = []
FAILED: list[str] = []

TUNE = Tuning()
MEM = TUNE.memory()
SAL = TUNE.salience()


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


def _campaign(guild: int, name: str):
    campaign = campaigns_for(guild).create(
        Campaign(guild_id=guild, name=name, ruleset="freeform", gm_ids=[1])
    )
    return campaign, campaign_store(guild, campaign.id)


def _npc(store, campaign, name, **traits):
    return store.entities.create(Entity(
        guild_id=campaign.guild_id, campaign_id=campaign.id, kind=KIND_NPC,
        identity=Identity(name=name), traits=Traits(**traits).to_doc(),
        needs=needs_mod.Needs().to_doc(), importance=0.5,
    ))


def _mem(gist, salience=0.4, valence=-0.3, details=None, participants=None):
    return Memory(
        gist=gist, salience=salience, valence=valence,
        details=list(details or ["a green lantern"]),
        participants=list(participants or ["X"]),
        cues=gist.lower().split(),
    )


# --------------------------------------------------------------------------- #
#  1. Traits, inheritance, retention
# --------------------------------------------------------------------------- #
def test_traits() -> None:
    a = derive_traits(Random(1), culture="tidewater", role="harbourmaster")
    b = derive_traits(Random(2), culture="wanderer", role="thief")
    check("traits: two NPCs differ", a.to_doc() != b.to_doc())
    check("traits: temperament in range",
          all(-1 <= a.axis(x) <= 1 for x in ("warmth", "volatility", "boldness")))
    check("traits: drives in range", all(0 <= a.axis(x) <= 1 for x in ("greed", "honour")))
    check("traits: describes itself in words", bool(a.describe()))

    # Retention is a faculty, not a disposition, and varies widely.
    spread = [derive_traits(Random(s)).retention for s in range(40)]
    check("traits: retention varies between people",
          max(spread) - min(spread) > 0.4, f"{min(spread):.2f}..{max(spread):.2f}")
    check("traits: an archivist tends to remember",
          sum(derive_traits(Random(s), role="archivist").retention for s in range(20)) / 20
          > sum(derive_traits(Random(s)).retention for s in range(20)) / 20)

    # Children resemble their parents without being copies.
    parents = [Traits(warmth=0.9, greed=0.9), Traits(warmth=0.8, greed=0.85)]
    kids = [derive_traits(Random(s), parents=parents) for s in range(12)]
    mean_warmth = sum(k.warmth for k in kids) / len(kids)
    check("inheritance: children lean toward their parents", mean_warmth > 0.15,
          f"mean warmth {mean_warmth:.2f}")
    check("inheritance: siblings still differ",
          len({round(k.warmth, 2) for k in kids}) > 6)


# --------------------------------------------------------------------------- #
#  2. Needs
# --------------------------------------------------------------------------- #
def test_needs() -> None:
    fresh = needs_mod.Needs(hunger=0.0, thirst=0.0, fatigue=0.0, ticked_at=0)
    day = needs_mod.advanced(fresh, 24 * 60)
    check("needs: rise with time", day.hunger > fresh.hunger)
    check("needs: pure — the original is untouched", fresh.hunger == 0.0)
    check("needs: clamp at 1.0", needs_mod.advanced(fresh, 100 * 24 * 60).hunger == 1.0)

    # The cube is what stops NPCs fretting about being slightly peckish.
    mild, severe = needs_mod.Needs(hunger=0.4), needs_mod.Needs(hunger=0.9)
    check("needs: urgency is non-linear",
          severe.urgency("hunger") / max(1e-9, mild.urgency("hunger")) > 8,
          f"{mild.urgency('hunger'):.3f} vs {severe.urgency('hunger'):.3f}")
    check("needs: mild needs are ignorable", mild.urgency("hunger") < 0.1)

    check("needs: impulses only past the threshold",
          not needs_mod.from_needs(mild, 0) and bool(needs_mod.from_needs(severe, 0)))
    impulse = needs_mod.from_needs(severe, 0)[0]
    check("needs: impulses decay", impulse.at(600) < impulse.at(0))
    check("needs: satisfying one lowers it",
          needs_mod.satisfy(needs_mod.Needs(hunger=0.9), "hunger", 0.8).hunger < 0.2)


# --------------------------------------------------------------------------- #
#  3. Two witnesses, two memories — a P2 acceptance criterion
# --------------------------------------------------------------------------- #
def test_witnesses_differ() -> None:
    close = encode.encode(
        witness_id="A", gist="Marla stabbed Ondry at the north dock", world_time=0,
        rng=Random(1), valence=-0.8, participants=["A", "M", "O"],
        details=["a green lantern", "rain", "a dropped rope"],
        traits=Traits(diligence=0.6), perception=1.0,
        salience_tuning=SAL, memory_tuning=MEM,
    )
    far = encode.encode(
        witness_id="B", gist="Marla stabbed Ondry at the north dock", world_time=0,
        rng=Random(1), valence=-0.8, participants=["M", "O"],
        details=["a green lantern", "rain", "a dropped rope"],
        traits=Traits(volatility=0.7), perception=0.3,
        salience_tuning=SAL, memory_tuning=MEM,
    )
    check("witnesses: both formed a memory", close is not None and far is not None)
    check("witnesses: the distant one kept less detail",
          len(far.details) < len(close.details), f"{len(far.details)} vs {len(close.details)}")
    check("witnesses: the distant one saw only 'a fight'",
          far.gist != close.gist, f"{far.gist!r}")
    check("witnesses: the one it happened TO felt it more",
          close.salience > far.salience, f"{close.salience:.2f} vs {far.salience:.2f}")
    check("witnesses: the distant memory starts hazier",
          far.fidelity["details"] < close.fidelity["details"])

    # Perception can be so poor that nothing registers at all.
    check("witnesses: nothing is encoded below the perception floor",
          encode.encode(witness_id="C", gist="x", world_time=0, rng=Random(1),
                        perception=0.0, salience_tuning=SAL, memory_tuning=MEM) is None)


# --------------------------------------------------------------------------- #
#  4. The forgetting curve — power law, not linear
# --------------------------------------------------------------------------- #
def test_curve_is_power_law() -> None:
    def clarity(days, field="details"):
        m = _mem("a quiet afternoon")
        decay.decay(m, days, Random(1), traits=Traits(), tuning=MEM)
        return m.fidelity[field]

    first_week = 1.0 - clarity(7)
    fifth_year = clarity(1460) - clarity(1825)
    check("curve: loses more in the first week than in the fifth year",
          first_week > fifth_year, f"{first_week:.3f} vs {fifth_year:.3f}")
    check("curve: never reaches exactly zero", clarity(36500) > 0.0)
    check("curve: is monotonic", clarity(30) > clarity(90) > clarity(365))

    # Field ordering: gist outlasts everything, when goes first.
    m = _mem("a quiet afternoon")
    decay.decay(m, 365, Random(1), traits=Traits(), tuning=MEM)
    order = [m.fidelity[f] for f in ("gist", "valence", "participants", "details", "when")]
    check("curve: fields rot in the right order", order == sorted(order, reverse=True),
          str([round(x, 2) for x in order]))

    # Stepping must not depend on how often you look.
    one_jump = _mem("x")
    decay.decay(one_jump, 100, Random(1), traits=Traits(), tuning=MEM)
    many_steps = _mem("x")
    for _ in range(100):
        decay.decay(many_steps, 1, Random(1), traits=Traits(), tuning=MEM)
    drift = abs(one_jump.fidelity["gist"] - many_steps.fidelity["gist"])
    check("curve: 100 one-day steps == one 100-day step", drift < 0.02, f"drift {drift:.4f}")


# --------------------------------------------------------------------------- #
#  5. Retention is personal
# --------------------------------------------------------------------------- #
def test_retention_is_personal() -> None:
    def after(retention, days=365):
        m = _mem("a quiet afternoon")
        decay.decay(m, days, Random(1), traits=Traits(retention=retention), tuning=MEM)
        return m.fidelity["participants"]

    forgetful, average, sharp = after(0.0), after(0.5), after(1.0)
    check("retention: the sharp remember more than the forgetful",
          sharp > average > forgetful, f"{forgetful:.2f} < {average:.2f} < {sharp:.2f}")
    check("retention: the difference is substantial", sharp - forgetful > 0.15,
          f"{sharp - forgetful:.2f}")

    # And it can be switched off, making everyone identical.
    flat = Tuning(server={"memory_retention_reach": 1.0}).memory()
    a = _mem("x"); decay.decay(a, 365, Random(1), traits=Traits(retention=0.0), tuning=flat)
    b = _mem("x"); decay.decay(b, 365, Random(1), traits=Traits(retention=1.0), tuning=flat)
    check("retention: can be disabled so everyone is the same",
          abs(a.fidelity["gist"] - b.fidelity["gist"]) < 1e-6)


# --------------------------------------------------------------------------- #
#  6. What is kept correlates with the value system
# --------------------------------------------------------------------------- #
def test_values_drive_forgetting() -> None:
    DEBT = "he still owes me four marks and never paid"
    OATH = "he swore an oath and betrayed it"

    grasping = Traits(greed=0.95, honour=0.2)
    sworn = Traits(greed=0.2, honour=0.95)

    check("values: the grasping hold onto debts",
          value_model.alignment(_mem(DEBT), grasping) > 0.3)
    check("values: the grasping let go of oaths",
          value_model.alignment(_mem(OATH), grasping) < 0)
    check("values: the sworn hold onto oaths",
          value_model.alignment(_mem(OATH), sworn) > 0.3)
    check("values: the sworn let go of debts",
          value_model.alignment(_mem(DEBT), sworn) < 0)

    # Attention as well as retention: they *notice* what they care about.
    def encoded(gist, traits):
        return encode.encode(
            witness_id="W", gist=gist, world_time=0, rng=Random(1), valence=-0.5,
            traits=traits, salience_tuning=SAL, memory_tuning=MEM,
        ).salience

    check("values: the grasping notice a debt more than the sworn do",
          encoded(DEBT, grasping) > encoded(DEBT, sworn))
    check("values: the sworn notice a broken oath more than the grasping do",
          encoded(OATH, sworn) > encoded(OATH, grasping))

    # End to end: the same two memories, three years on, in two different heads.
    def survives(gist, traits):
        m = encode.encode(
            witness_id="W", gist=gist, world_time=0, rng=Random(1), valence=-0.5,
            traits=traits, salience_tuning=SAL, memory_tuning=MEM,
        )
        decay.decay(m, 1095, Random(1), traits=traits, tuning=MEM)
        return m.fidelity["gist"]

    check("values: after 3 years the grasping still have the debt, not the oath",
          survives(DEBT, grasping) > survives(OATH, grasping),
          f"{survives(DEBT, grasping):.2f} vs {survives(OATH, grasping):.2f}")
    check("values: and the sworn have the oath, not the debt",
          survives(OATH, sworn) > survives(DEBT, sworn),
          f"{survives(OATH, sworn):.2f} vs {survives(DEBT, sworn):.2f}")

    check("values: a GM is told why", "greed" in value_model.explain(_mem(DEBT), grasping))
    check("values: and why not",
          "nothing in their values" in value_model.explain(
              _mem("she took me in and asked nothing", valence=0.7), Traits()))

    # And the whole influence can be switched off.
    blind = Tuning(server={"memory_alignment_reach": 0.0}).memory()
    a = _mem(DEBT); decay.decay(a, 730, Random(1), traits=grasping, tuning=blind)
    b = _mem(OATH); decay.decay(b, 730, Random(1), traits=grasping, tuning=blind)
    check("values: value-blind forgetting is available",
          abs(a.fidelity["gist"] - b.fidelity["gist"]) < 1e-6)


# --------------------------------------------------------------------------- #
#  7. Confabulation and imprints — P2 acceptance criteria
# --------------------------------------------------------------------------- #
def test_confabulation_and_imprints() -> None:
    m = _mem("a quiet afternoon", salience=0.1)
    decay.decay(m, 3650, Random(3), traits=Traits(retention=0.0), tuning=MEM)
    check("confabulation: an old faint memory degrades or misremembers",
          bool(m.confabulated) or not m.details,
          f"confabulated={m.confabulated} details={m.details}")
    check("confabulation: the gist is never confabulated", "gist" not in m.confabulated)
    check("confabulation: time and place is the first thing lost",
          m.when_precision != "exact", m.when_precision)

    # A wrong value is drawn from their *other* memories, so it is characteristic.
    wrong = _mem("something", salience=0.05)
    wrong.confabulated = ["participants"]
    decay.substitute(wrong, {"participants": ["Ondry", "Marla"], "details": []}, Random(1))
    check("confabulation: the wrong face is someone they know",
          wrong.participants[0] in ("Ondry", "Marla"), str(wrong.participants))

    # Imprints: formed by intensity, and immune to everything after.
    strong = _mem("the night of the fire", salience=0.95)
    check("imprint: forms from one overwhelming event", decay.should_imprint(strong, tuning=MEM))
    decay.promote(strong)
    before = dict(strong.fidelity)
    decay.decay(strong, 36500, Random(1), traits=Traits(retention=0.0), tuning=MEM)
    check("imprint: survives a century untouched", strong.fidelity == before)
    check("imprint: half-life is infinite", decay.half_life(strong, tuning=MEM) == float("inf"))

    # Or from rehearsal.
    rehearsed = _mem("the argument", salience=0.65)
    rehearsed.recall_count = 8
    check("imprint: also forms by being returned to", decay.should_imprint(rehearsed, tuning=MEM))

    # Cue-triggered.
    imprint = _mem("the night of the fire", salience=0.95)
    decay.promote(imprint)
    check("imprint: a cue sets it off",
          recall.triggered_by([imprint], ["fire"], 0) is not None)
    check("imprint: an unrelated cue does not",
          recall.triggered_by([imprint], ["bread"], 0) is None)


# --------------------------------------------------------------------------- #
#  8. Recall rewrites
# --------------------------------------------------------------------------- #
def test_recall() -> None:
    m = _mem("the night at the harbour", salience=0.5)
    check("recall: a matching cue reaches it", recall.strength(m, ["harbour"], 0) > 0)
    check("recall: an unrelated cue does not", recall.strength(m, ["bread"], 0) == 0)

    before = m.salience
    recall.reconsolidate(m, 100, Random(1), present_details=["candlelight"])
    check("recall: recalling strengthens", m.salience > before)
    check("recall: and counts", m.recall_count == 1)
    check("recall: the gist firms up", m.fidelity["gist"] >= 1.0)

    # Over many tellings the present leaks in as false detail.
    story = _mem("the night at the harbour", salience=0.5)
    for i in range(60):
        recall.reconsolidate(story, 100 + i, Random(i), present_details=["a candle", "wine"])
    check("recall: repeated telling contaminates the memory",
          len(story.details) > 1, str(story.details))
    check("recall: never reaches certainty", story.salience < 1.0, f"{story.salience:.4f}")


# --------------------------------------------------------------------------- #
#  9. Budgets — a P2 acceptance criterion
# --------------------------------------------------------------------------- #
def test_budgets() -> None:
    small = consolidate.budget_for(0.0, MEM)
    big = consolidate.budget_for(1.0, MEM)
    check("budget: importance buys capacity", big[TIER_MID] > small[TIER_MID])
    check("budget: a nobody stays cheap", small[TIER_MID] <= 12)

    memories = [_mem(f"thing {i}", salience=i / 100) for i in range(100)]
    for m in memories:
        m.tier = TIER_MID
    surviving, pruned = consolidate.prune(memories, 0.0, 10_000, MEM)
    kept = [m for m in surviving if m.tier == TIER_MID]
    check("budget: pruning brings it inside the cap", len(kept) <= small[TIER_MID],
          f"{len(kept)} <= {small[TIER_MID]}")
    check("budget: the least important go first",
          min(m.salience for m in kept) > max(m.salience for m in pruned))

    # Imprints are never pruned by the ordinary path.
    imprints = [_mem(f"formative {i}", salience=0.9) for i in range(3)]
    for m in imprints:
        m.tier = TIER_IMPRINT
    surviving, pruned = consolidate.prune(memories + imprints, 0.0, 10_000, MEM)
    check("budget: imprints survive pruning",
          sum(1 for m in surviving if m.is_imprint) == 3)

    summary = consolidate.summarise(pruned, "E", 10_000)
    check("budget: what is pruned leaves a summary behind", summary is not None)
    check("budget: the summary is hazy and unimportant",
          summary.salience < 0.25 and summary.fidelity["details"] == 0.0)

    # Capacity is tunable.
    generous = Tuning(server={"memory_budget_scale": 5.0}).memory()
    check("budget: capacity is tunable",
          consolidate.budget_for(0.0, generous)[TIER_MID] > small[TIER_MID] * 3)


# --------------------------------------------------------------------------- #
#  10. Nothing is baked in
# --------------------------------------------------------------------------- #
def test_everything_tunable() -> None:
    check("tuning: a registry exists", len(TUNABLES) >= 30, str(len(TUNABLES)))
    check("tuning: every tunable is documented",
          all(s["label"] and s["description"] and s["group"] for s in TUNABLES))
    numeric = [s for s in TUNABLES if s["type"] not in ("choice",)]
    check("tuning: every numeric tunable has a range",
          all(s["min"] <= s["default"] <= s["max"] for s in numeric),
          str([s["key"] for s in numeric if not s["min"] <= s["default"] <= s["max"]]))
    # A choice has options instead of a range, and its default must be one of
    # them — a tunable whose default is not selectable cannot be reset.
    choices = [s for s in TUNABLES if s["type"] == "choice"]
    check("tuning: every choice offers its own default",
          all(s["choices"] and s["default"] in s["choices"] for s in choices),
          str([s["key"] for s in choices if s["default"] not in (s["choices"] or ())]))

    # Layering: campaign beats server beats default.
    layered = Tuning(server={"memory_decay_rate": 0.5}, campaign={"memory_decay_rate": 2.0})
    check("tuning: campaign overrides server", layered.get("memory_decay_rate") == 2.0)
    check("tuning: the source is reported", layered.source_of("memory_decay_rate") == "campaign")
    check("tuning: server is inherited when the campaign is silent",
          Tuning(server={"imprint_threshold": 0.6}).get("imprint_threshold") == 0.6)
    check("tuning: otherwise the default applies", Tuning().get("imprint_threshold") == 0.85)
    check("tuning: out-of-range values are clamped, not rejected",
          Tuning(campaign={"memory_decay_rate": 999}).get("memory_decay_rate") <= 5.0)

    # THE switch: forgetting off entirely.
    frozen = Tuning(campaign={"memory_decay_rate": 0}).memory()
    check("tuning: rate 0 reports frozen", frozen.frozen)
    m = _mem("a quiet afternoon")
    before = dict(m.fidelity)
    decay.decay(m, 36500, Random(1), traits=Traits(retention=0.0), tuning=frozen)
    check("tuning: FORGETTING CAN BE SWITCHED OFF ENTIRELY", m.fidelity == before)
    check("tuning: and a frozen memory never confabulates", not m.confabulated)

    # Curve shape, stabilities and salience weights are all reachable.
    sharp = Tuning(campaign={"memory_curve_shape": 1.5}).memory()
    a = _mem("x"); decay.decay(a, 90, Random(1), traits=Traits(), tuning=MEM)
    b = _mem("x"); decay.decay(b, 90, Random(1), traits=Traits(), tuning=sharp)
    check("tuning: curve shape changes the fade", b.fidelity["gist"] < a.fidelity["gist"])

    long_gist = Tuning(campaign={"stability_gist": 5000}).memory()
    c = _mem("x"); decay.decay(c, 3650, Random(1), traits=Traits(), tuning=long_gist)
    d = _mem("x"); decay.decay(d, 3650, Random(1), traits=Traits(), tuning=MEM)
    check("tuning: per-field stability is adjustable", c.fidelity["gist"] > d.fidelity["gist"])


# --------------------------------------------------------------------------- #
#  11. Relationships
# --------------------------------------------------------------------------- #
def test_relationships() -> None:
    rel = rel_mod.blank("A", "B")
    rel_mod.apply(rel, "betrayed", traits=Traits(), world_time=0)
    check("relations: betrayal wrecks trust", rel.trust < -0.5, f"{rel.trust:.2f}")
    check("relations: and affinity", rel.affinity < -0.3)
    check("relations: and raises fear", rel.fear > 0)
    check("relations: it reads in words", "suspicious" in rel.summary() or "dislike" in rel.summary())

    helped = rel_mod.blank("A", "B")
    rel_mod.apply(helped, "helped", traits=Traits(), world_time=0)
    # Positive debt is "I owe them" (`Relationship.summary`). The table is
    # written from the point of view of the person it happened to, so being
    # helped puts you in someone's debt. This asserted -1 before, which reads as
    # "is owed" — the beneficiary was recorded as the creditor.
    check("relations: being helped puts you in their debt", helped.debt == 1)

    # Traits modulate: an honourable character weighs things differently.
    honourable = rel_mod.blank("A", "B")
    grasping = rel_mod.blank("A", "B")
    rel_mod.apply(honourable, "betrayed", traits=Traits(honour=1.0, fear_of_death=0.9), world_time=0)
    rel_mod.apply(grasping, "betrayed", traits=Traits(honour=0.0, fear_of_death=0.1), world_time=0)
    check("relations: traits change the reaction", honourable.fear != grasping.fear,
          f"{honourable.fear:.2f} vs {grasping.fear:.2f}")

    check("relations: axes stay in range",
          all(-1 <= getattr(rel, a) <= 1 for a in ("affinity", "trust", "fear", "respect")))
    check("relations: an unknown event does nothing",
          rel_mod.apply(rel_mod.blank("A", "B"), "nonsense", world_time=0).affinity == 0)

    # Direction matters.
    check("relations: A->B and B->A are separate",
          rel_mod.blank("A", "B").to_doc()["from_id"] == "A")

    # Swing is tunable.
    gentle = rel_mod.blank("A", "B")
    rel_mod.apply(gentle, "betrayed", traits=Traits(), world_time=0,
                  tuning=Tuning(campaign={"relationship_scale": 0.2}).relationships())
    check("relations: swing is tunable", abs(gentle.trust) < abs(rel.trust))


# --------------------------------------------------------------------------- #
#  12. End to end through the store
# --------------------------------------------------------------------------- #
def test_rumours() -> None:
    """A claim about a PC reaches someone who has never met them.

    Half of P3's acceptance criterion, and the whole of reputation: word travels
    the relationship graph on its own, arriving weaker and slightly wrong.
    """
    from helpers.dnd.mind import rumour
    from helpers.dnd.world.belief import SOURCE_WITNESSED, adopt

    campaign, store = _campaign(9801, "Gossip")
    chain = {n: minds.spawn_npc(store, name=n, world_time=0, rng=Random(i))
             for i, n in enumerate(("Marla", "Sennet", "Teo", "Wren"))}
    subject = minds.spawn_npc(store, name="Kesh", world_time=0, rng=Random(90))

    # A line, not a clique: Wren only knows Teo, and Teo only knows Sennet.
    for left, right in (("Marla", "Sennet"), ("Sennet", "Teo"), ("Teo", "Wren")):
        for a, b in ((left, right), (right, left)):
            rel = store.relations.between(chain[a].id, chain[b].id)
            rel.familiarity, rel.trust = 0.8, 0.7
            store.relations.save(rel)

    store.beliefs.add(adopt(
        "Kesh owes the Compact a debt", holder_id=chain["Marla"].id,
        subject_id=subject.id, source_kind=SOURCE_WITNESSED, at=0,
    ))

    def knows(name):
        return next((b for b in store.beliefs.held_by(chain[name].id)
                     if str(b.subject_id) == str(subject.id)), None)

    check("rumours: only the witness knows to begin with",
          knows("Marla") is not None and knows("Wren") is None)

    for turn in range(1, 12):
        minds.advance(store, store.campaigns.get(campaign.id), 1.0, Random(turn))

    far = knows("Wren")
    check("rumours: IT REACHES SOMEONE WHO NEVER MET THE SUBJECT", far is not None)
    check("rumours: and arrives weaker than it started",
          far is not None and far.confidence < knows("Marla").confidence,
          f"{far.confidence:.2f} vs {knows('Marla').confidence:.2f}" if far else "")
    check("rumours: the witness's own belief is not damaged by the retelling",
          knows("Marla").confidence > 0.9 and knows("Marla").mutations == 0)
    check("rumours: nobody accumulates echoes of one claim",
          len(store.beliefs.about(subject.id)) <= len(chain),
          str(len(store.beliefs.about(subject.id))))

    # The drift vocabulary must terminate, or six retellings produce soup.
    keys = set(rumour._DRIFT_WORDS)
    produced = {w.lower() for opts in rumour._DRIFT_WORDS.values()
                for o in opts for w in o.split()}
    check("rumours: a drift replacement is never itself driftable",
          not (keys & produced), str(keys & produced))

    # And it can be switched off entirely, like everything else.
    quiet, quiet_store = _campaign(9802, "Silent")
    quiet.settings = {"tuning": {"rumour_exchanges": 0}}
    quiet_store.campaigns.save_settings(quiet.id, quiet.settings)
    report = minds.advance(quiet_store, quiet_store.campaigns.get(quiet.id), 5.0, Random(1))
    check("rumours: can be switched off entirely", report["rumours"]["told"] == 0)


def test_clocks() -> None:
    """Fronts fill whether anyone engages or not.

    `06-DECISION-ENGINE.md` §10: a clock is a thing that is going to happen
    unless somebody stops it. A campaign where nothing moves between sessions is
    a diorama, and this is the difference.
    """
    from helpers.dnd.world.clock import Clock, advance as tick_clock, nudge

    campaign, store = _campaign(9701, "Fronts")
    slow = store.clocks.create(Clock(name="The tide wall fails", segments=4, rate=0.1))
    front = store.clocks.create(Clock(
        name="The Compact seizes the north dock", segments=8, rate=0.5,
        on_complete=[
            {"kind": "announce", "payload": {"text": "The dock is theirs."}},
            {"kind": "start_clock", "payload": {"name": "The Compact taxes the fishers",
                                                "segments": 6, "rate": 0.2}},
        ],
    ))
    check("clocks: a new front has not started filling", front.filled == 0.0)

    minds.advance(store, store.campaigns.get(campaign.id), 10.0, Random(1))
    front = store.clocks.by_name("The Compact seizes the north dock")
    check("clocks: TIME FILLS THEM WITH NOBODY WATCHING",
          front.filled == 5.0, f"{front.filled} of {front.segments}")
    check("clocks: each at its own rate",
          store.clocks.by_name("The tide wall fails").filled == 1.0)
    check("clocks: and they say how long is left",
          "6d left" in front.describe(), front.describe())

    minds.advance(store, store.campaigns.get(campaign.id), 8.0, Random(2))
    front = store.clocks.by_name("The Compact seizes the north dock")
    check("clocks: a full front completes", front.status == "complete")
    kinds = [e.kind for e in store.events.recent(8)]
    check("clocks: completing is an event", "clock_filled" in kinds)
    check("clocks: and its consequences fire", "clock_effect" in kinds)
    check("clocks: a front can start another one",
          store.clocks.by_name("The Compact taxes the fishers") is not None)

    minds.advance(store, store.campaigns.get(campaign.id), 30.0, Random(3))
    check("clocks: a completed one does not keep filling",
          store.clocks.by_name("The Compact seizes the north dock").filled == 8.0)

    # Players hold a front shut. That is the whole feedback loop between play
    # and world: ignoring a problem costs you, and acting on it buys time.
    # A fresh front, because the tide wall has long since filled by now — and a
    # completed clock not moving would pass this check for the wrong reason.
    siege = store.clocks.create(Clock(name="The siege tightens", segments=20, rate=0.5))
    store.clocks.block(siege.id, "someone")
    before = store.clocks.by_name("The siege tightens").filled
    minds.advance(store, store.campaigns.get(campaign.id), 20.0, Random(4))
    check("clocks: A BLOCKED FRONT DOES NOT MOVE",
          store.clocks.by_name("The siege tightens").filled == before,
          f"moved to {store.clocks.by_name('The siege tightens').filled}")
    store.clocks.unblock(siege.id, "someone")
    minds.advance(store, store.campaigns.get(campaign.id), 5.0, Random(5))
    check("clocks: and resumes the moment they let go",
          store.clocks.by_name("The siege tightens").filled > before)

    # Nudging is the GM's hand, and dragging one back below the line revives it.
    done = store.clocks.by_name("The Compact seizes the north dock")
    nudge(done, -3)
    check("clocks: dragged back below the line, a front lives again",
          done.status == "running" and done.completed_at is None)


def test_world_tick() -> None:
    """Time passes on its own, at a pace each campaign sets for itself.

    Default off: a campaign starts ageing when its GM decides, not because it
    exists. And two campaigns on one server must be able to run at completely
    different speeds, since the loop is a fixed-cadence scheduler and the
    *campaign* owns the rate.
    """
    slow, slow_store = _campaign(9601, "Slow")
    fast, fast_store = _campaign(9602, "Fast")
    NOW = 1_000_000.0

    check("tick: a campaign does not age until asked",
          minds.due_for_tick(slow, NOW) is False)
    check("tick: and tick() refuses rather than guessing",
          minds.tick(slow_store, slow, NOW, Random(1)) is None)

    def configure(campaign, store, hours, days, mode="automatic"):
        settings = {"tuning": {"time_mode": mode, "tick_hours": hours, "tick_days": days}}
        store.campaigns.save_settings(campaign.id, settings)
        campaign.settings = settings

    configure(slow, slow_store, hours=168.0, days=30.0)   # a month a week
    configure(fast, fast_store, hours=6.0, days=1.0)      # a day a night

    minds.spawn_npc(slow_store, name="A", world_time=0, rng=Random(3))
    minds.spawn_npc(fast_store, name="B", world_time=0, rng=Random(4))

    check("tick: both are due when they have never turned",
          minds.due_for_tick(slow, NOW) and minds.due_for_tick(fast, NOW))

    minds.tick(slow_store, slow, NOW, Random(1))
    minds.tick(fast_store, fast, NOW, Random(1))
    slow_days = slow_store.campaigns.get(slow.id).world_time / 1440
    fast_days = fast_store.campaigns.get(fast.id).world_time / 1440
    check("tick: EACH CAMPAIGN MOVES AT ITS OWN PACE",
          round(slow_days) == 30 and round(fast_days) == 1,
          f"slow {slow_days:.0f}d, fast {fast_days:.0f}d")

    # Cadence, not just size: the slow table is not due again for a week.
    later = NOW + 7 * 3600
    check("tick: a campaign that just turned waits its interval",
          minds.due_for_tick(slow_store.campaigns.get(slow.id), later) is False)
    check("tick: while the quicker one is ready again",
          minds.due_for_tick(fast_store.campaigns.get(fast.id), later) is True)

    # --- three modes, and a dungeon crawl needs the third ---------------- #
    timeless, tl_store = _campaign(9603, "Crawl")
    configure(timeless, tl_store, 6.0, 1.0, mode="timeless")
    minds.spawn_npc(tl_store, name="C", world_time=0, rng=Random(5))
    check("tick: a timeless campaign never turns on its own",
          minds.due_for_tick(timeless, NOW) is False)
    told = minds.advance(tl_store, timeless, 5.0, Random(1))
    check("tick: AND DECLINES TO AGE EVEN WHEN ASKED",
          told.get("timeless") is True
          and tl_store.campaigns.get(timeless.id).world_time == 0)
    check("tick: it says so rather than silently doing nothing",
          told["frozen"] is True)

    # A mode has to be settable by name, or it is not settable from Discord.
    from helpers.dnd import tuning as tuning_registry
    check("tick: modes are set by name",
          tuning_registry.coerce("time_mode", "TIMELESS") == "timeless")
    check("tick: and nonsense falls back to the default rather than wedging",
          tuning_registry.coerce("time_mode", "sideways") == "manual")

    # Manual and automatic must be the same code path, or the world ages
    # differently depending on whether anyone was looking.
    manual = minds.advance(fast_store, fast_store.campaigns.get(fast.id), 1.0, Random(9))
    check("tick: /gm advance and the tick share one body",
          set(manual) >= {"entities", "frozen"})


def test_scene_consolidation() -> None:
    """Closing a scene has to empty the working tier.

    `05-MEMORY.md` §1 calls working *"current scene, verbatim, evicted at scene
    end"*. `consolidate_scene` was written and called from nowhere, so nothing
    ever left it: a decade-old memory still sat in the tier meant to hold the
    last ten minutes, the per-tier budgets never applied, and the inspector
    filed everything under **Right now** forever.
    """
    campaign, store = _campaign(9501, "Scenes")
    marla = minds.spawn_npc(store, name="Marla", role="harbourmaster",
                            world_time=0, rng=Random(7))
    minds.remember(store, marla, "a knife fight outside the office", world_time=0,
                   rng=Random(1), valence=-0.9, details=["a green lantern"])
    minds.remember(store, marla, "someone shifted a crate", world_time=0,
                   rng=Random(2), valence=0.0)

    before = store.memories.tier_counts(marla.id)
    check("scene: memories start in the working tier", before.get("working", 0) >= 2)

    report = minds.close_scene(store, [marla], 0)
    after = store.memories.tier_counts(marla.id)
    check("scene: CLOSING IT EMPTIES THE WORKING TIER",
          after.get("working", 0) == 0, str(after))
    check("scene: what mattered was promoted, not deleted",
          after.get("mid", 0) >= 1 and report[marla.id][0] >= 1)

    # Below the working floor, a memory is let go rather than promoted — and
    # what goes leaves a trace, so a scene compresses instead of vanishing.
    trivial = [m for m in store.memories.for_entity(marla.id) if m.salience < 0.15]
    check("scene: nothing below the floor survived as itself",
          all(m.tier != "working" for m in trivial))

    idle = minds.close_scene(store, [marla], 0)
    check("scene: closing again with nothing working is a no-op", not idle)


def test_stakes() -> None:
    """The same act is a different event for each person in it.

    The merchant lord settles a stranger's debt with a wave of a finger. That
    must cost him nothing he notices while being the day the debtor's life did
    not end — and it must NOT follow from his rank alone, or the model has just
    hardcoded "the powerful never care", which is a cliche and not a rule.
    """
    campaign, store = _campaign(9401, "Stakes")
    lord = minds.spawn_npc(store, name="Vashen", role="merchant lord",
                           world_time=0, rng=Random(2), importance=0.95, standing=0.95)
    debtor = minds.spawn_npc(store, name="Teo", role="dock hand",
                             world_time=0, rng=Random(5), importance=0.15, standing=0.12)
    crowd = minds.spawn_npc(store, name="Fishwife", role="fishwife",
                            world_time=0, rng=Random(8), importance=0.3, standing=0.3)

    result = minds.interact(
        store, lord, debtor, "helped", world_time=0, rng=Random(1),
        description="paid off the whole debt without being asked",
        witnesses=[crowd],
    )
    lord_stake = result["stakes"][lord.id]
    debtor_stake = result["stakes"][debtor.id]

    check("stakes: the same act is worth wildly different amounts",
          debtor_stake.weight > lord_stake.weight * 5,
          f"lord {lord_stake.weight:.3f} vs debtor {debtor_stake.weight:.3f}")
    check("stakes: beneath noticing forms no memory",
          lord_stake.negligible and lord.id not in result["memories"])
    check("stakes: the one it happened to remembers it",
          debtor.id in result["memories"])
    check("stakes: a bystander forms an opinion of the actor",
          store.relations.between(crowd.id, lord.id).affinity > 0)

    # Significance must not travel through perception. It did, and a thing that
    # happened this morning rendered as "a while ago, maybe" because a low stake
    # blurred the `when` field at encoding.
    fresh = result["memories"][debtor.id]
    check("stakes: A FRESH MEMORY IS NOT BORN HAZY",
          fresh.fidelity["when"] == 1.0 and "recently" in fresh.describe(),
          f"when={fresh.fidelity['when']:.2f} :: {fresh.describe()[-24:]}")
    check("stakes: it happened TO them, not merely near them",
          debtor.id in fresh.participants and lord.id in fresh.participants)
    check("stakes: knowing someone follows what it was worth",
          store.relations.between(debtor.id, lord.id).familiarity
          > store.relations.between(lord.id, debtor.id).familiarity)

    # Which end of the act you were on decides which way it moves you. The
    # delta table is written from the point of view of the person it happened
    # TO; applying it unchanged to the actor had a lord come out "fond of them,
    # and is owed 4" while the man he saved came out indifferent.
    saver = minds.spawn_npc(store, name="Saver", role="lord", world_time=0,
                            rng=Random(21), standing=0.9)
    saved = minds.spawn_npc(store, name="Saved", role="hand", world_time=0,
                            rng=Random(22), standing=0.1)
    minds.interact(store, saver, saved, "saved", world_time=0, rng=Random(1),
                   description="cut the rope before the tide took him")
    theirs = store.relations.between(saved.id, saver.id)
    mine = store.relations.between(saver.id, saved.id)
    check("stakes: THE ONE WHO WAS SAVED OWES, not the one who saved",
          theirs.debt > 0 >= mine.debt, f"saved {theirs.debt}, saver {mine.debt}")
    check("stakes: and feels it far more than the actor does",
          theirs.affinity > mine.affinity,
          f"{theirs.affinity:+.3f} vs {mine.affinity:+.3f}")
    check("stakes: doing a kindness still warms you a little",
          rel_mod.actor_view("saved", 0.3)["affinity"] > 0)
    check("stakes: unless the echo is switched off",
          "affinity" not in rel_mod.actor_view("saved", 0.0)
          and rel_mod.actor_view("saved", 0.0)["debt"] < 0)

    # Standing is a ceiling: disposition may only ever cut insulation.
    from helpers.dnd.mind.traits import Traits
    cold = Traits(warmth=-0.6, honour=0.1, belonging=0.1)
    check("stakes: a cold nature cannot insulate past your station",
          stakes.capacity_of(0.5, cold) <= 0.5 + 1e-9,
          f"capacity {stakes.capacity_of(0.5, cold):.3f} against a 0.50 ceiling")

    # --- station must not decide character ------------------------------- #
    def as_lord(name, warmth, honour, belonging):
        entity = minds.spawn_npc(store, name=name, role="lord", world_time=0,
                                 rng=Random(3), importance=0.95, standing=0.95)
        doc = dict(entity.traits)
        doc.update(warmth=warmth, honour=honour, belonging=belonging)
        entity.traits = doc
        store.entities.save(entity)
        return entity

    cold = as_lord("Cold", -0.6, 0.2, 0.2)
    warm = as_lord("Warm", 0.8, 0.85, 0.8)
    servant = minds.spawn_npc(store, name="Nurse", role="servant", world_time=0,
                              rng=Random(6), importance=0.15, standing=0.12)
    cold_result = minds.interact(store, servant, cold, "helped", world_time=0,
                                 rng=Random(1), description="nursed them through a fever")
    warm_result = minds.interact(store, servant, warm, "helped", world_time=0,
                                 rng=Random(1), description="nursed them through a fever")
    check("stakes: A BENEVOLENT LORD REMEMBERS what was done for him",
          warm.id in warm_result["memories"])
    check("stakes: an indifferent one of equal rank does not",
          cold.id not in cold_result["memories"])

    # --- awareness is not mutual ----------------------------------------- #
    hidden = minds.interact(store, lord, debtor, "saved", world_time=0,
                            rng=Random(9), description="cut the rope before anyone saw",
                            subject_awareness=0.0)
    check("stakes: an unseen act still marks the person it happened to",
          hidden["stakes"][debtor.id].weight > 0)
    check("stakes: but it is worth less than one they can credit",
          hidden["stakes"][debtor.id].weight
          < stakes.stake_for(stakes.default_magnitude("saved"),
                             stakes.capacity_of(debtor.standing,
                                                minds.traits_of(debtor))).weight)

    # --- and all of it switches off -------------------------------------- #
    flat = stakes.StakesTuning(capacity_reach=0.0, disposition_reach=0.0)
    rich = stakes.stake_for(0.5, stakes.capacity_of(0.95), tuning=flat)
    poor = stakes.stake_for(0.5, stakes.capacity_of(0.15), tuning=flat)
    check("stakes: circumstances can be switched off entirely",
          abs(rich.weight - poor.weight) < 1e-9)

    # --- standing is not importance -------------------------------------- #
    # PCs are pinned at importance 1.0 because they are always fully simulated.
    # Reading that as insulation made capacity exactly 1 and every stake exactly
    # zero, so nothing that happened to a player character ever cost them
    # anything — a bug wearing the merchant lord's clothes.
    from helpers.dnd.world.entity import KIND_PC, Entity, Identity
    pc = store.entities.create(Entity(
        guild_id=store.guild_id, campaign_id=store.campaign_id, kind=KIND_PC,
        owner_id=42, identity=Identity(name="Player", role="thief"),
        importance=1.0,
    ))
    check("stakes: a PC keeps importance 1.0 for simulation depth",
          pc.importance == 1.0)
    check("stakes: but standing is its own, middling field", pc.standing == 0.5)
    hit = minds.interact(store, debtor, pc, "betrayed", world_time=0, rng=Random(2),
                         description="sold them to the Compact")
    check("stakes: SOMETHING CAN HAPPEN TO A PLAYER CHARACTER",
          not hit["stakes"][pc.id].negligible and pc.id in hit["memories"],
          f"stake {hit['stakes'][pc.id].weight:.3f}")

    pc.standing = 0.95
    store.entities.save(pc)
    rich_hit = minds.interact(store, debtor, pc, "betrayed", world_time=0, rng=Random(2),
                              description="sold them to the Compact")
    check("stakes: and standing alone decides how much",
          rich_hit["stakes"][pc.id].weight < hit["stakes"][pc.id].weight)


def test_roles_emerge() -> None:
    """A stereotype must be a distribution, not a rule printed on each person.

    Read forwards, the role table stamps low honour on anyone called a thief and
    every thief in the world is the same man twice. Read backwards it only
    *notices* — so with the priors switched off entirely, thieves should still
    come out less honourable on average, because dishonourable people are the
    ones who fall into thieving. That is the whole difference.
    """
    from helpers.dnd.tuning import GenerationTuning

    emergent = GenerationTuning(role_prior_weight=0.0, culture_prior_weight=0.0)
    rng = Random(11)
    people = [derive_traits(rng, tuning=emergent) for _ in range(400)]
    landed: dict[str, list[float]] = {}
    for person in people:
        role = traits_mod.suggest_role(person, rng, sharpness=emergent.role_fit_sharpness)
        landed.setdefault(role, []).append(person.honour)

    def mean(role: str) -> float:
        values = landed.get(role) or [0.5]
        return sum(values) / len(values)

    check("roles: NO prior applied at all", emergent.role_prior_weight == 0.0)
    check("roles: yet thieves are less honourable than priests",
          mean("thief") < mean("priest") - 0.1,
          f"thief {mean('thief'):.3f} vs priest {mean('priest'):.3f}")
    check("roles: the stereotype is a distribution, not a rule",
          any(h > 0.6 for h in landed.get("thief", [])),
          "no honest thief exists in 400 people")
    check("roles: several trades are represented", len(landed) >= 6)

    # Fit reads the same table backwards and must never flatten anyone.
    honest = Traits(honour=0.9)
    crooked = Traits(honour=0.1)
    check("roles: fit notices an odd thief",
          traits_mod.fit(honest, "thief") < traits_mod.fit(crooked, "thief"))
    check("roles: and says so in words",
          "thief" in traits_mod.describe_fit(traits_mod.fit(honest, "thief"), "thief"))

    # And the top-down path is still available for populating a world fast.
    stamped = GenerationTuning(role_prior_weight=1.0)
    rng2 = Random(5)
    typical = [derive_traits(rng2, role="thief", tuning=stamped).honour for _ in range(60)]
    free = [derive_traits(rng2, role="thief", tuning=emergent).honour for _ in range(60)]
    check("roles: archetype mode still available for fast worlds",
          sum(typical) / len(typical) < sum(free) / len(free))


def test_end_to_end() -> None:
    campaign, store = _campaign(9301, "Minds")

    marla = minds.spawn_npc(
        store, name="Marla Venn", role="harbourmaster", culture="tidewater",
        world_time=0, rng=Random(7),
    )
    check("e2e: an NPC is born with a personality", marla.traits is not None)
    check("e2e: and with a past", store.memories.count_for(marla.id) >= 1)
    check("e2e: and a body", marla.needs is not None)

    ondry = _npc(store, campaign, "Ondry", warmth=0.4)

    minds.remember(
        store, marla, "Ondry paid what he owed at the north dock",
        world_time=0, rng=Random(1), valence=0.6, participants=[marla.id, ondry.id],
        details=["a green lantern"],
    )
    check("e2e: memories persist", store.memories.count_for(marla.id) >= 2)

    hits = minds.recall_for(store, marla, ["lantern"], world_time=100, rng=Random(1))
    check("e2e: a cue reaches the memory", len(hits) >= 1)
    check("e2e: recalling it was recorded", hits[0].recall_count >= 1)

    minds.relate(store, marla, ondry, "helped", world_time=100)
    rel = store.relations.between(marla.id, ondry.id)
    check("e2e: the relationship moved", rel.affinity > 0)
    check("e2e: the reverse direction is untouched",
          store.relations.between(ondry.id, marla.id).affinity == 0)

    report = minds.advance(store, campaign, 400, Random(2))
    check("e2e: time advances the whole campaign", report["entities"] >= 2)
    check("e2e: world time moved", store.campaigns.get(campaign.id).world_time > 0)
    check("e2e: and it is not reported as frozen", report["frozen"] is False)

    aged = store.memories.for_entity(marla.id)
    check("e2e: memories aged", any(m.fidelity["when"] < 1.0 for m in aged))
    check("e2e: budget respected after ageing",
          len([m for m in aged if m.tier == TIER_MID])
          <= consolidate.budget_for(marla.importance, MEM)[TIER_MID])

    # Tenancy still holds for the new collections.
    other_campaign, other_store = _campaign(9302, "Elsewhere")
    check("e2e: memories do not cross campaigns",
          other_store.memories.count_for(marla.id) == 0)
    check("e2e: relationships do not cross campaigns",
          other_store.relations.between(marla.id, ondry.id).affinity == 0)


# --------------------------------------------------------------------------- #
#  18. The projection an NPC decides from
#
#  P3's decision engine is only worth building if "NPCs act on what they believe"
#  is true structurally. These tests are about what the engine *cannot* reach.
# --------------------------------------------------------------------------- #
def _walk(value, seen=None):
    """Every object reachable from a view, so a leak has nowhere to hide."""
    seen = seen if seen is not None else set()
    if id(value) in seen:
        return
    seen.add(id(value))
    yield value
    if isinstance(value, (str, bytes, int, float, bool)) or value is None:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk(key, seen)
            yield from _walk(item, seen)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _walk(item, seen)
        return
    for name in getattr(value, "__dataclass_fields__", ()):
        yield from _walk(getattr(value, name), seen)


def test_entity_view() -> None:
    campaign, store = _campaign(9311, "What Marla Knows")
    marla = _npc(store, campaign, "Marla", warmth=0.4, boldness=0.6, retention=0.5)
    ondry = _npc(store, campaign, "Ondry")
    hooded = _npc(store, campaign, "A hooded man")
    duchess = _npc(store, campaign, "The Duchess")
    rng = Random(11)
    now = 10_000

    # Marla knows Ondry, has never met the hooded man, and has only heard of the
    # Duchess — three kinds of acquaintance the view has to tell apart.
    minds.relate(store, marla, ondry, "helped", world_time=now, familiarity_bonus=0.4)
    store.beliefs.add(adopt("the duchess is poisoning the wells",
                            holder_id=marla.id, subject_id=duchess.id,
                            source_kind="told", at=now))
    store.beliefs.add(adopt("ondry owes the harbourmaster",
                            holder_id=marla.id, subject_id=ondry.id,
                            source_kind="witnessed", at=now))
    minds.remember(store, marla, "the fire on the north dock", world_time=now,
                   rng=rng, valence=-0.7, participants=[ondry.id],
                   details=["a green lantern"])

    view = minds.view_for(store, marla, world_time=now)

    # --- 1. The world is not reachable from the view ---------------------- #
    forbidden = (Entity, Memory, Belief, Relationship)
    leaks = [type(o).__name__ for o in _walk(view) if isinstance(o, forbidden)]
    check("view: THE ENGINE CANNOT REACH WORLD TRUTH", not leaks, str(sorted(set(leaks))))
    check("view: importance never reaches a decision", not hasattr(view, "importance"))

    # --- 2. The GM's truth flag does not travel --------------------------- #
    marked = store.beliefs.held_by(marla.id)[0]
    store.beliefs.set_truth(marked.id, False)
    lying = minds.view_for(store, marla, world_time=now)
    check("view: the GM's truth flag is not a field on a held belief",
          all(not hasattr(b, "truth") for b in lying.beliefs))
    check("view: and nothing else carries it either",
          not any(hasattr(o, "truth") for o in _walk(lying)))

    # --- 3. Nothing in a view can be written ------------------------------ #
    froze = True
    try:
        view.name = "someone else"
        froze = False
    except Exception:
        pass
    try:
        view.others[ondry.id] = None
        froze = False
    except Exception:
        pass
    check("view: a decision cannot rewrite the mind it is reading", froze)

    # --- 4. Three kinds of acquaintance ----------------------------------- #
    check("view: someone they know has a name", view.of(ondry.id).name == "Ondry")
    # Ondry helped Marla, so Marla likes him and is in his debt — from her side,
    # which is the only side a view ever has.
    check("view: and the feelings are the viewer's own",
          view.of(ondry.id).affinity > 0 and view.of(ondry.id).i_owe_them == 1)
    check("view: a debt is not readable backwards", view.of(ondry.id).they_owe_me == 0)
    check("view: someone never met is a stranger", view.of(hooded.id).stranger)
    check("view: a stranger has no name", view.of(hooded.id).name == "")
    check("view: someone only heard of is still in mind", duchess.id in view.others)
    check("view: and unnamed, because they have never met",
          view.of(duchess.id).name == "" and view.of(duchess.id).beliefs)

    # Somebody in the room is visible whether or not they are recognised.
    present = minds.view_for(store, marla, world_time=now, include=(hooded.id,))
    check("view: whoever is in the room is in the view", hooded.id in present.others)
    check("view: and is still a stranger", present.of(hooded.id).stranger)

    # --- 5. A memory arrives in the state decay left it in ---------------- #
    check("view: what is remembered comes through",
          any("north dock" in m.gist for m in view.memories))
    minds.age_entity(store, marla, 4000, world_time=now, rng=Random(3))
    faded = minds.view_for(store, marla, world_time=now)
    old = [m for m in faded.memories if "north dock" in m.gist]
    check("view: an old memory arrives faded, or does not arrive at all",
          not old or old[0].clarity < 1.0,
          f"{old[0].clarity:.2f}" if old else "dropped below the floor")
    check("view: a numb memory carries no feeling",
          all(m.valence == 0.0 for m in faded.memories if m.numb))

    # --- 6. Looking does not change anything ------------------------------ #
    before = [(m.id, m.recall_count, dict(m.fidelity))
              for m in store.memories.for_entity(marla.id)]
    twice = minds.view_for(store, marla, world_time=now)
    after = [(m.id, m.recall_count, dict(m.fidelity))
             for m in store.memories.for_entity(marla.id)]
    check("view: building one writes nothing", before == after)
    check("view: and is deterministic", twice == faded)

    # --- 7. Every limit is tunable, and every one switches off ------------ #
    for _ in range(6):
        minds.remember(store, ondry, f"a dull errand {_}", world_time=now, rng=rng)
    for i in range(6):
        store.beliefs.add(adopt(f"a thin rumour {i}", holder_id=ondry.id,
                                subject_id=marla.id, source_kind="assumed", at=now))

    capped = minds.view_for(store, ondry, world_time=now,
                            tuning=Tuning(campaign={"view_memory_limit": 2,
                                                    "view_belief_limit": 1}))
    check("view: the memory cap bites", len(capped.memories) == 2)
    check("view: the belief cap bites", len(capped.beliefs) == 1)

    uncapped = minds.view_for(store, ondry, world_time=now,
                              tuning=Tuning(campaign={"view_memory_limit": 0,
                                                      "view_belief_limit": 0,
                                                      "view_belief_floor": 0}))
    check("view: A CAP OF 0 IS NO CAP AT ALL",
          len(uncapped.memories) >= 6 and len(uncapped.beliefs) >= 6,
          f"{len(uncapped.memories)} memories, {len(uncapped.beliefs)} beliefs")

    # An assumed belief sits at 0.35; a floor above it keeps it out of decisions
    # without the holder ceasing to hold it.
    sure_only = minds.view_for(store, ondry, world_time=now,
                               tuning=Tuning(campaign={"view_belief_floor": 0.5}))
    check("view: too unsure to act on is left out of the decision",
          not sure_only.beliefs and store.beliefs.count_for(ondry.id) >= 6)

    # And the stranger floor: at 0 everyone is recognised on sight.
    village = minds.view_for(store, marla, world_time=now, include=(hooded.id,),
                             tuning=Tuning(campaign={"view_stranger_floor": 0}))
    check("view: a floor of 0 recognises everyone",
          village.of(duchess.id).name == "The Duchess")

    # --- 8. The tunables are registered and reach the panel ---------------- #
    keys = {s["key"] for s in TUNABLES}
    check("view: every perception knob is a registered tunable",
          {"view_memory_limit", "view_belief_limit", "view_relationship_limit",
           "view_belief_floor", "view_clarity_floor", "view_stranger_floor"} <= keys)
    check("view: they are grouped for the panel",
          all(s["group"] == "Perception" for s in TUNABLES if s["key"].startswith("view_")))
    check("view: and layered like everything else",
          Tuning(server={"view_memory_limit": 5},
                 campaign={"view_memory_limit": 9}).perception().memory_limit == 9)


# --------------------------------------------------------------------------- #
#  19. Affordances — what a scene physically permits
#
#  The other half of the decision engine's propose step: candidates are the
#  behaviour packs *intersected* with these, so what a scene forbids never even
#  gets scored.
# --------------------------------------------------------------------------- #
def test_affordances() -> None:
    ff = rules.get("freeform")
    srd = rules.get("srd5e")
    healthy = {"hp": {"current": 9, "max": 9}}
    company = (rs.Presence(entity_id="x", kind="npc", carrying=True),)

    # --- 1. Waiting is the floor, in every ruleset and every state -------- #
    for name, ruleset_impl, stats in (("freeform", ff, {}), ("srd5e", srd, healthy)):
        for situation in (
            rs.Situation(),
            rs.Situation(conditions=("unconscious",)),
            rs.Situation(others=company, carrying=True, lighting="dark"),
            rs.Situation(sealed=True, conditions=("restrained",)),
        ):
            allowed = ruleset_impl.affordances(stats, situation)
            check(f"affordances: {name} always leaves waiting on the table",
                  rs.WAIT in allowed)
            check(f"affordances: {name} answers only in the closed vocabulary",
                  allowed <= set(rs.AFFORDANCES), str(allowed - set(rs.AFFORDANCES)))

    # --- 2. An empty room offers nothing social --------------------------- #
    alone = ff.affordances({}, rs.Situation())
    check("affordances: nobody to talk to means no speaking", rs.SPEAK not in alone)
    check("affordances: and nobody to hit", rs.ATTACK not in alone)
    check("affordances: you can still leave", rs.FLEE in alone)
    check("affordances: a sealed room cannot be fled",
          rs.FLEE not in ff.affordances({}, rs.Situation(sealed=True)))

    # --- 3. Being unable to act removes everything but waiting ------------ #
    check("affordances: someone out cold has one option",
          ff.affordances({}, rs.Situation(others=company, conditions=("out cold",)))
          == frozenset({rs.WAIT}))
    check("affordances: 5e reads the same from its own condition list",
          srd.affordances(healthy, rs.Situation(others=company, conditions=("stunned",)))
          == frozenset({rs.WAIT}))
    # And 5e knows a thing the condition list does not say out loud.
    check("affordances: at 0 hit points you are not deciding anything",
          srd.affordances({"hp": {"current": 0}}, rs.Situation(others=company))
          == frozenset({rs.WAIT}))

    # --- 4. The two rulesets genuinely disagree --------------------------- #
    # A grappled 5e creature keeps its hands and loses its speed; freeform reads
    # the same word off a GM's free text and reaches the same place its own way.
    grappled = rs.Situation(others=company, conditions=("grappled",), carrying=True)
    five = srd.affordances(healthy, grappled)
    check("affordances: 5e speed 0 removes moving and fleeing",
          rs.MOVE not in five and rs.FLEE not in five)
    check("affordances: but not attacking or giving",
          rs.ATTACK in five and rs.GIVE in five)

    prone = rs.Situation(others=company, conditions=("prone",))
    check("affordances: a prone 5e creature still fights and still crawls",
          {rs.ATTACK, rs.MOVE} <= srd.affordances(healthy, prone))
    check("affordances: invisibility is the condition that adds an option",
          rs.HIDE in srd.affordances(healthy, rs.Situation(conditions=("invisible",))))
    check("affordances: freeform has no such rule",
          rs.HIDE not in ff.affordances({}, rs.Situation(conditions=("invisible",))))

    # Freeform reads what a GM actually types; 5e's closed list does not.
    tied = rs.Situation(others=company, conditions=("tied to a chair",))
    check("affordances: freeform understands 'tied to a chair'",
          rs.FLEE not in ff.affordances({}, tied))
    check("affordances: 5e does not, and says so by allowing it",
          rs.FLEE in srd.affordances(healthy, tied))

    # --- 5. Hiding wants somewhere to do it ------------------------------- #
    check("affordances: no hiding in a bare lit room",
          rs.HIDE not in ff.affordances({}, rs.Situation(lighting="bright")))
    check("affordances: the dark will do",
          rs.HIDE in ff.affordances({}, rs.Situation(lighting="dim and smoky")))
    check("affordances: so will something to get behind",
          rs.HIDE in ff.affordances({}, rs.Situation(features=("overturned cart",))))

    # --- 6. Giving and taking need something to give and take ------------- #
    empty_handed = rs.Situation(others=(rs.Presence(entity_id="y"),))
    check("affordances: you cannot give what you do not have",
          rs.GIVE not in ff.affordances({}, empty_handed))
    check("affordances: nor take from someone carrying nothing",
          rs.TAKE not in ff.affordances({}, empty_handed))
    check("affordances: a full pocket changes both",
          {rs.GIVE, rs.TAKE, rs.USE} <= ff.affordances({}, rs.Situation(
              others=company, carrying=True)))

    # --- 7. A campaign narrows what a ruleset offered --------------------- #
    campaign, store = _campaign(9312, "Lines and Veils")
    marla = _npc(store, campaign, "Marla")
    ondry = _npc(store, campaign, "Ondry")
    ondry.inventory = [{"name": "a purse"}]
    store.entities.save(ondry)
    scene = store.scenes.create(Scene(
        guild_id=campaign.guild_id, campaign_id=campaign.id, title="The tap room",
        present=[marla.id, ondry.id], lighting="dim",
    ))

    everything = minds.affordances_for(store, marla, scene)
    check("affordances: through the store, a scene offers real options",
          {rs.SPEAK, rs.ATTACK, rs.TAKE, rs.HIDE} <= everything, str(sorted(everything)))

    peaceful = minds.affordances_for(store, marla, scene, tuning=Tuning(
        campaign={"affordance_attack": False, "affordance_take": False}))
    check("affordances: A CAMPAIGN CAN SWITCH VIOLENCE OFF ENTIRELY",
          rs.ATTACK not in peaceful and rs.TAKE not in peaceful)
    check("affordances: without taking away everything else",
          {rs.SPEAK, rs.HIDE} <= peaceful)
    check("affordances: and waiting has no switch to find",
          rs.WAIT in minds.affordances_for(store, marla, scene, tuning=Tuning(
              campaign={f"affordance_{a}": False for a in rs.AFFORDANCES})))

    # The physics are not where a table's lines live: the ruleset still says
    # violence is possible, and the campaign is what declines it.
    situation = minds.situation_for(store, marla, scene)
    check("affordances: the ruleset itself is untouched by the campaign's choice",
          rs.ATTACK in rules.get(campaign.ruleset).affordances(marla.stats or {}, situation))

    # --- 8. The switches are real tunables with a panel control ----------- #
    keys = {s["key"]: s for s in TUNABLES}
    check("affordances: every switch but waiting is registered",
          all(f"affordance_{a}" in keys for a in rs.AFFORDANCES if a != rs.WAIT))
    check("affordances: waiting deliberately has none",
          "affordance_wait" not in keys)
    check("affordances: they are booleans, grouped for the panel",
          all(keys[f"affordance_{a}"]["type"] == "bool"
              and keys[f"affordance_{a}"]["group"] == "Actions"
              for a in rs.AFFORDANCES if a != rs.WAIT))
    check("affordances: and layered like everything else",
          Tuning(server={"affordance_hide": False}).affordances().permits("hide") is False)


# --------------------------------------------------------------------------- #
#  20. Goals — what somebody is after
#
#  P3's acceptance criterion is "an NPC pursues a goal". This is the half that
#  says what a goal is worth at a given moment; the scorer that acts on it is the
#  next increment.
# --------------------------------------------------------------------------- #
def test_goals() -> None:
    campaign, store = _campaign(9313, "Wanting Things")
    marla = _npc(store, campaign, "Marla")
    day = 1440

    # --- 1. A goal names the verbs that serve it -------------------------- #
    check("goals: every kind is served by something",
          all(goal_model.SERVED_BY.get(k) for k in goal_model.KINDS))
    verbs = {v for served in goal_model.SERVED_BY.values() for v in served}
    check("goals: AND EVERY VERB IS ONE A RULESET CAN ACTUALLY OFFER",
          verbs <= set(rs.AFFORDANCES), str(sorted(verbs - set(rs.AFFORDANCES))))
    acquire = goal_model.Goal(key="a-1", kind=goal_model.ACQUIRE, priority=1.0)
    check("goals: taking serves acquiring squarely", acquire.served_by("take") == 1.0)
    check("goals: attacking does not serve it at all", acquire.served_by("attack") == 0.0)

    # --- 2. Wanting fades, unless it is being pursued --------------------- #
    stale = goal_model.Goal(key="a-2", priority=0.8, touched_at=0)
    check("goals: a want nobody acts on fades",
          goal_math.faded(stale, 200 * day) < 0.3,
          f"{goal_math.faded(stale, 200 * day):.3f}")
    fresh = stale.with_progress(0.1, 200 * day)
    check("goals: pursuing it resets the clock",
          goal_math.faded(fresh, 200 * day) == 0.8)
    frozen = Tuning(campaign={"goal_decay": 0}).goals()
    check("goals: A VOW CAN BE MADE A VOW — decay switches off",
          goal_math.faded(stale, 3650 * day, frozen) == 0.8 and frozen.eternal)

    # --- 3. A deadline presses, convexly ---------------------------------- #
    tuning = Tuning().goals()
    dated = goal_model.Goal(key="a-3", priority=0.5, deadline=30 * day)
    far = goal_math.urgency(dated, 0, tuning)
    close = goal_math.urgency(dated, 29 * day, tuning)
    middling = goal_math.urgency(dated, 23 * day, tuning)
    check("goals: a distant deadline does not press at all", far == 0.0)
    check("goals: a close one presses hard", close > 0.8, f"{close:.2f}")
    check("goals: and the curve is convex, not a ramp",
          close - middling > middling - far, f"{middling:.2f}")
    check("goals: a deadline still expires when it stops pressing",
          goal_model.Goal(key="a-4", deadline=10).expired(11))
    # Switched off, a goal with a deadline one day out is worth exactly what the
    # same goal with no deadline is worth — compared at the same moment, or
    # ordinary fading would explain the gap instead.
    calm = Tuning(campaign={"goal_deadline_reach": 0}).goals()
    undated = goal_model.Goal(key="a-3", priority=0.5, deadline=None)
    check("goals: deadlines can be made not to hurry anyone",
          goal_math.pressure(dated, 29 * day, calm)
          == goal_math.pressure(undated, 29 * day, calm))
    check("goals: while they still press by default",
          goal_math.pressure(dated, 29 * day, tuning)
          > goal_math.pressure(undated, 29 * day, tuning))

    # --- 4. Nearly done is worth more than barely started ----------------- #
    started = goal_model.Goal(key="a-5", priority=0.5, progress=0.0)
    nearly = goal_model.Goal(key="a-6", priority=0.5, progress=0.9)
    check("goals: the goal gradient is real",
          goal_math.pressure(nearly, 0, tuning) > goal_math.pressure(started, 0, tuning))
    flat = Tuning(campaign={"goal_gradient": 0}).goals()
    check("goals: and can be switched off",
          goal_math.pressure(nearly, 0, flat) == goal_math.pressure(started, 0, flat))

    # --- 5. Everything the engine reads is bounded ------------------------ #
    extreme = goal_model.Goal(key="a-7", priority=1.0, progress=1.0, deadline=1)
    for t in (tuning, Tuning(campaign={"goal_gradient": 3, "goal_deadline_reach": 4}).goals()):
        check("goals: pressure never leaves 0..1",
              0.0 <= goal_math.pressure(extreme, 0, t) <= 1.0,
              f"{goal_math.pressure(extreme, 0, t):.3f}")
        check("goals: and neither does what a verb is worth",
              0.0 <= goal_math.value_of(extreme, "take", 0, t) <= 1.0)

    # --- 6. Through the store: authored, pursued, finished ---------------- #
    goal = minds.add_goal(store, marla, goal_model.ACQUIRE, world_time=0,
                          text="buy back her sister's indenture", priority=0.9)
    marla = store.entities.get(marla.id)
    check("goals: A GOAL SURVIVES BEING SAVED", [g.key for g in minds.goals_of(marla, 0)] == [goal.key])
    check("goals: and reaches the projection an NPC decides from",
          [g.text for g in minds.view_for(store, marla, world_time=0).goals]
          == ["buy back her sister's indenture"])

    minds.advance_goal(store, marla, goal.key, 0.5, world_time=day)
    marla = store.entities.get(marla.id)
    check("goals: progress is recorded", minds.all_goals_of(marla)[0].progress == 0.5)
    minds.advance_goal(store, marla, goal.key, 0.6, world_time=day)
    marla = store.entities.get(marla.id)
    done = minds.all_goals_of(marla)[0]
    check("goals: finishing one closes it", done.status == "done")
    check("goals: and it leaves the live list", not minds.goals_of(marla, day))
    check("goals: but stays on the record",
          len(minds.all_goals_of(marla)) == 1)

    # Giving up is recorded too — what somebody abandoned is a fact about them.
    second = minds.add_goal(store, marla, goal_model.HARM, world_time=day, text="see him ruined")
    marla = store.entities.get(marla.id)
    minds.drop_goal(store, marla, second.key)
    marla = store.entities.get(marla.id)
    check("goals: giving up is kept, not deleted",
          [g.status for g in minds.all_goals_of(marla) if g.key == second.key] == ["dropped"])

    # --- 7. The cap refuses rather than evicting -------------------------- #
    crowded, crowded_store = _campaign(9314, "Too Much Wanting")
    ondry = _npc(crowded_store, crowded, "Ondry")
    tight = Tuning(campaign={"goal_cap": 2})
    made = [minds.add_goal(crowded_store, crowded_store.entities.get(ondry.id),
                           goal_model.REACH, world_time=0, text=f"go {i}", tuning=tight)
            for i in range(3)]
    check("goals: the cap bites", made[2] is None and made[1] is not None)
    check("goals: AND REFUSES RATHER THAN QUIETLY DROPPING AN AMBITION",
          len(minds.all_goals_of(crowded_store.entities.get(ondry.id))) == 2)
    loose = Tuning(campaign={"goal_cap": 0})
    check("goals: a cap of 0 is no cap",
          minds.add_goal(crowded_store, crowded_store.entities.get(ondry.id),
                         goal_model.REACH, world_time=0, text="go 4", tuning=loose) is not None)

    # --- 8. Goals meet affordances ---------------------------------------- #
    scene = crowded_store.scenes.create(Scene(
        guild_id=crowded.guild_id, campaign_id=crowded.id, title="The road",
        present=[ondry.id], lighting="bright",
    ))
    ondry = crowded_store.entities.get(ondry.id)
    allowed = minds.affordances_for(crowded_store, ondry, scene, campaign=crowded)
    live = minds.goals_of(ondry, 0, loose)
    verb, worth = goal_math.best_verb(live, allowed, 0, loose.goals())
    check("goals: the best thing to do here serves what they want",
          verb == "move" and worth > 0, f"{verb} {worth:.2f}")
    # And a campaign that forbids the verb leaves the goal unserved, rather than
    # leaving the NPC to propose something the scene will not allow.
    pinned = minds.affordances_for(crowded_store, ondry, scene, campaign=crowded,
                                   tuning=Tuning(campaign={"affordance_move": False,
                                                           "affordance_flee": False}))
    check("goals: a forbidden verb serves nothing",
          goal_math.best_verb(live, pinned, 0, loose.goals())[1] == 0.0)

    # --- 9. Tunables and the panel ---------------------------------------- #
    keys = {s["key"] for s in TUNABLES}
    check("goals: every knob is registered",
          {"goal_cap", "goal_decay", "goal_abandon_below", "goal_deadline_reach",
           "goal_deadline_window", "goal_gradient", "goal_completion"} <= keys)
    check("goals: grouped for the panel",
          all(s["group"] == "Goals" for s in TUNABLES if s["key"].startswith("goal_")))
    check("goals: and layered like everything else",
          Tuning(server={"goal_cap": 9}, campaign={"goal_cap": 2}).goals().cap == 2)


def test_entity_round_trip() -> None:
    """Saving an entity must persist everything the entity carries.

    ``EntityRepo.save`` used to name the fields it wrote, and a list like that
    rots in silence: ``standing`` was added for stakes and never added there, so
    the inspector's control posted, the endpoint set it, the repository dropped
    it, and the panel said "Saved." This test is the guard, and it is written
    against ``to_doc`` rather than against a list so the *next* field is covered
    by it too.
    """
    campaign, store = _campaign(9315, "Round Trip")
    entity = _npc(store, campaign, "Kell")

    entity.standing = 0.93
    entity.importance = 0.31
    entity.conditions = ["bleeding"]
    entity.inventory = [{"name": "a brass key"}]
    entity.tier = "focus"
    entity.goals = [goal_model.Goal(key="acquire-1", text="the key").to_doc()]
    entity.identity.role = "harbourmaster"
    store.entities.save(entity)

    back = store.entities.get(entity.id)
    for field_name in ("standing", "importance", "conditions", "inventory", "tier"):
        check(f"entity: {field_name} survives a save",
              getattr(back, field_name) == getattr(entity, field_name),
              f"{getattr(back, field_name)!r}")
    check("entity: goals survive a save", (back.goals or [{}])[0].get("text") == "the key")
    check("entity: identity survives a save", back.identity.role == "harbourmaster")

    # Every field to_doc emits, except the ones the scope owns, must round trip.
    from helpers.dnd.store.entities import NOT_THE_CALLERS
    missed = [
        key for key in entity.to_doc()
        if key not in NOT_THE_CALLERS and key not in store.entities.by_id(entity.id)
    ]
    check("entity: NO FIELD IS SILENTLY DROPPED ON SAVE", not missed, str(missed))

    # And the tenancy keys are still not the caller's to move.
    stale = store.entities.get(entity.id)
    stale.guild_id, stale.campaign_id = 1, "elsewhere"
    store.entities.save(stale)
    fixed = store.entities.get(entity.id)
    check("entity: a save cannot reparent a record",
          fixed.guild_id == campaign.guild_id and fixed.campaign_id == campaign.id)


# --------------------------------------------------------------------------- #
#  21. Attention — the scarce thing, and what moves a priority
#
#  Anybody may want any number of things. What they cannot do is pursue them all
#  at once, and the two characters that falls out of — the relentless one and the
#  one who never finishes anything — are the point of the whole mechanic.
# --------------------------------------------------------------------------- #
def test_attention() -> None:
    tuning = Tuning().goals()

    def carrying(n, priority=0.6):
        return [goal_model.Goal(key=f"reach-{i}", kind=goal_model.REACH,
                                priority=priority) for i in range(n)]

    # --- 1. Carrying a goal costs something before any of it is spent ----- #
    one = goal_math.focus(carrying(1), 0, None, tuning)["reach-0"]
    six = goal_math.focus(carrying(6), 0, None, tuning)["reach-0"]
    twelve = goal_math.focus(carrying(12), 0, None, tuning)["reach-0"]
    check("attention: one goal gets nearly the whole person", one > 0.9, f"{one:.3f}")
    check("attention: six goals get much less than a sixth each",
          six < (one / 6), f"{six:.3f} vs {one / 6:.3f}")
    check("attention: TWELVE GOALS IS A PERSON WHO FINISHES NOTHING",
          twelve < 0.01, f"{twelve:.4f}")
    check("attention: and past that there is nothing left at all",
          goal_math.usable(13, None, tuning) == 0.0)
    check("attention: the shares never exceed the person",
          sum(goal_math.focus(carrying(6), 0, None, tuning).values()) <= 1.0)

    # The overhead is what makes a long list worse rather than merely slower.
    flat = Tuning(campaign={"goal_attention_overhead": 0}).goals()
    check("attention: OVERHEAD SWITCHES OFF INTO PLAIN DIVISION",
          abs(goal_math.focus(carrying(12), 0, None, flat)["reach-0"] - 1 / 12) < 1e-9
          and flat.divides_evenly)

    # --- 2. The split follows how much they care, not head count ---------- #
    mixed = [goal_model.Goal(key="harm-1", kind=goal_model.HARM, priority=1.0)]
    mixed += [goal_model.Goal(key=f"reach-{i}", kind=goal_model.REACH, priority=0.1)
              for i in range(5)]
    split = goal_math.focus(mixed, 0, None, tuning)
    check("attention: ONE REAL AMBITION KEEPS MOST OF THE PERSON",
          split["harm-1"] > 6 * split["reach-0"],
          f"{split['harm-1']:.3f} vs {split['reach-0']:.3f}")
    even = goal_math.focus(carrying(6), 0, None, tuning)
    check("attention: equal wanting splits equally",
          len(set(round(v, 6) for v in even.values())) == 1)

    # --- 3. Doggedness decides how much there is to spend ----------------- #
    dogged = goal_math.budget(Traits(diligence=1.0), tuning)
    feckless = goal_math.budget(Traits(diligence=-1.0), tuning)
    check("attention: a dogged person has more of it", dogged > feckless,
          f"{dogged:.2f} vs {feckless:.2f}")
    same = Tuning(campaign={"goal_attention_reach": 0}).goals()
    check("attention: and that can be switched off",
          goal_math.budget(Traits(diligence=1.0), same)
          == goal_math.budget(Traits(diligence=-1.0), same))

    # --- 4. Being spread thin costs progress, not just speed -------------- #
    goal = goal_model.Goal(key="reach-0", priority=0.6)
    focused = goal_math.progressed(goal, 0.4, 0, tuning, share=0.92)
    scattered = goal_math.progressed(goal, 0.4, 0, tuning, share=0.09)
    check("attention: the same effort gets less done when divided",
          focused.progress > 4 * scattered.progress,
          f"{focused.progress:.3f} vs {scattered.progress:.3f}")
    check("attention: but a GM saying it moved means it moved",
          goal_math.progressed(goal, 0.4, 0, tuning).progress == 0.4)

    # --- 5. Two people, same six goals ------------------------------------ #
    campaign, store = _campaign(9316, "Two Ways To Want")
    relentless = _npc(store, campaign, "Relentless", diligence=0.8)
    scattered_npc = _npc(store, campaign, "Scattered", diligence=-0.4)
    for i, priority in enumerate([1.0] + [0.1] * 5):
        minds.add_goal(store, store.entities.get(relentless.id), goal_model.REACH,
                       world_time=0, text=f"thing {i}", priority=priority)
    for i in range(6):
        minds.add_goal(store, store.entities.get(scattered_npc.id), goal_model.REACH,
                       world_time=0, text=f"thing {i}", priority=0.6)

    a = minds.attention_of(store.entities.get(relentless.id), 0)
    b = minds.attention_of(store.entities.get(scattered_npc.id), 0)
    check("attention: NOBODY WAS REFUSED A GOAL", a["carrying"] == 6 and b["carrying"] == 6)
    check("attention: the relentless one is still getting somewhere",
          max(a["shares"].values()) > 0.4, f"{max(a['shares'].values()):.3f}")
    check("attention: the scattered one is not",
          max(b["shares"].values()) < 0.1, f"{max(b['shares'].values()):.3f}")
    check("attention: and the panel can say why",
          b["overhead"] > 0 and b["usable"] < b["budget"])

    # --- 6. Priorities move with how they feel about people --------------- #
    hated = Relationship(affinity=-0.9, respect=-0.6, fear=0.3)
    liked = Relationship(affinity=0.8, trust=0.6)
    grudge = goal_model.Goal(key="harm-1", kind=goal_model.HARM,
                             subject_id="x", priority=0.5)
    check("attention: hating someone argues for wanting them ruined",
          goal_math.support(grudge, hated) > 0.5)
    check("attention: liking them argues against it",
          goal_math.support(grudge, liked) < 0)
    check("attention: a goal about nobody is moved by no feeling",
          goal_math.support(goal_model.Goal(key="a-1", kind=goal_model.ACQUIRE), hated) == 0)

    warmer = goal_math.reweighed(grudge, hated, tuning)
    cooler = goal_math.reweighed(grudge, liked, tuning)
    check("attention: a grudge grows where the feeling supports it",
          warmer.priority > grudge.priority)
    check("attention: AND COOLS WHERE IT DOES NOT", cooler.priority < grudge.priority)
    check("attention: it is a pull, never a jump",
          abs(warmer.priority - grudge.priority) < 0.2)
    check("attention: reweighing leaves the decay clock alone",
          warmer.touched_at == grudge.touched_at)
    frozen = Tuning(campaign={"goal_reweigh": 0}).goals()
    check("attention: PRIORITIES CAN BE FROZEN ENTIRELY",
          goal_math.reweighed(grudge, hated, frozen) == grudge)

    # --- 7. And it happens when the event happens ------------------------- #
    marla = _npc(store, campaign, "Marla")
    ondry = _npc(store, campaign, "Ondry")
    goal = minds.add_goal(store, store.entities.get(marla.id), goal_model.BEFRIEND,
                          world_time=0, text="win Ondry over", subject_id=ondry.id,
                          priority=0.5)
    marla = store.entities.get(marla.id)
    minds.relate(store, marla, ondry, "betrayed", world_time=10)
    after = [g for g in minds.all_goals_of(store.entities.get(marla.id))
             if g.key == goal.key][0]
    check("attention: BEING BETRAYED COOLS THE WISH TO BE CLOSER",
          after.priority < goal.priority, f"{goal.priority:.2f} → {after.priority:.2f}")

    # A GM still has the last word, and it reaches the split.
    minds.set_goal_priority(store, store.entities.get(marla.id), goal.key, 0.95)
    marla = store.entities.get(marla.id)
    check("attention: a GM can set what someone cares about",
          [g.priority for g in minds.all_goals_of(marla) if g.key == goal.key] == [0.95])

    # --- 8. Tunables ------------------------------------------------------- #
    keys = {s["key"] for s in TUNABLES}
    check("attention: every knob is registered",
          {"goal_attention", "goal_attention_overhead", "goal_attention_reach",
           "goal_reweigh"} <= keys)
    check("attention: the hard cap is off by default, since it is not the mechanism",
          Tuning().goals().cap == 0)


def main() -> int:
    for test in (
        test_traits,
        test_needs,
        test_witnesses_differ,
        test_curve_is_power_law,
        test_retention_is_personal,
        test_values_drive_forgetting,
        test_confabulation_and_imprints,
        test_recall,
        test_budgets,
        test_everything_tunable,
        test_relationships,
        test_rumours,
        test_clocks,
        test_world_tick,
        test_scene_consolidation,
        test_stakes,
        test_roles_emerge,
        test_entity_view,
        test_affordances,
        test_goals,
        test_entity_round_trip,
        test_attention,
        test_end_to_end,
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
