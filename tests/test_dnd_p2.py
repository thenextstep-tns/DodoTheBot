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
from helpers.dnd.store import entities as entities_module  # noqa: E402
from helpers.dnd.store import events as events_module  # noqa: E402
from helpers.dnd.store import knowledge as knowledge_module  # noqa: E402
from helpers.dnd.store import memories as memories_module  # noqa: E402
from helpers.dnd.store import relations as relations_module  # noqa: E402
from helpers.dnd.store import scenes as scenes_module  # noqa: E402
from helpers.dnd.tuning import TUNABLES, Tuning  # noqa: E402
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.entity import KIND_NPC, Entity, Identity  # noqa: E402
from helpers.dnd.world.memory import TIER_IMPRINT, TIER_MID, Memory  # noqa: E402

for _cls, _name in (
    (campaigns_module.CampaignRepo, "dnd_campaigns"),
    (entities_module.EntityRepo, "dnd_entities"),
    (events_module.EventRepo, "dnd_events"),
    (scenes_module.SceneRepo, "dnd_scenes"),
    (knowledge_module.KnowledgeRepo, "dnd_knowledge"),
    (beliefs_module.BeliefRepo, "dnd_beliefs"),
    (canon_module.CanonRepo, "dnd_canon_queue"),
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
    check("tuning: every tunable has a range",
          all(s["min"] <= s["default"] <= s["max"] for s in TUNABLES),
          str([s["key"] for s in TUNABLES if not s["min"] <= s["default"] <= s["max"]]))

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
    check("relations: help creates a debt", helped.debt == -1)

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
        test_stakes,
        test_roles_emerge,
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
