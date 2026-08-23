"""
Dodo Tabletop — P4 acceptance tests: Voice, the half that needs no model.

`12-ROADMAP.md` orders P4 so that **the non-AI paths land first**, and
`08-LLM-LAYER.md` §5 is why: of five candidate LLM tasks, three turned out not
to need a model. This suite covers the first of them to be built — the turn
report — and it is the suite the null backend will be added to, because
invariant 8 says `backend=null` always works and the null suite is part of every
run.

What is actually being asserted, beyond "it renders":

* **Every band switches off, and the whole report switches off** (invariant 1).
* **Ids are not integers.** Entity ids are `ObjectId`s in production and strings
  in the fake. The stake band shipped coercing the map's keys with `int()`, which
  matches nothing and left the band silently dead while looking wired — the
  panel-control failure mode from `14-CONVENTIONS.md` §5a, in a message instead
  of a page. `test_ids_are_not_integers` is that regression.
* **Drift is continuous, so "the mixture moved" is not news.** The band fires
  only when the *leading* archetype changes.
* **The pure module and the cog agree**, because the cog is where the tuning,
  the names and the archetype labels are resolved and the pure layer cannot look
  any of them up for itself.

Run with ``py tests/test_dnd_p4.py``.
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
from helpers.dnd import narrate  # noqa: E402
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
from helpers.dnd.rules import ruleset as rs  # noqa: E402
from helpers.dnd import tuning as tuning_registry  # noqa: E402
from helpers.dnd.tuning import TUNABLES, ReportTuning, Tuning  # noqa: E402
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.scene import Scene  # noqa: E402

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

from helpers.dnd import parameters as dnd_parameters  # noqa: E402

dnd_parameters.TUNING_COLLECTION = FakeCollection("DndTuning")

# Imported last: the cog pulls in discord.py, and everything above has to have
# swapped the collections out before any of it runs.
from cogs.dnd.cog import _turn_summary  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


def _campaign(guild: int, name: str):
    campaign = campaigns_for(guild).create(
        Campaign(guild_id=guild, name=name, ruleset="freeform", gm_ids=[1])
    )
    return campaign, campaign_store(guild, campaign.id)


# A turn built by hand, so a band can be asserted without steering the whole
# simulation into producing one. Ids are **strings**, deliberately: that is what
# they are, and an int here would hide the bug this suite exists to catch.
def _turn():
    return {
        "actors": 3,
        "coarse": 1,
        "acted": [
            {
                "name": "Marla", "verb": "attack", "target_id": "id7",
                "memories": 3,
                "goals": [{"key": "debt", "text": "settle the debt",
                           "progress": 0.4, "done": False}],
                "relieved": {"safety": 0.2, "hunger": 0.05},
                "stakes": {"id2": 0.31, "id7": 0.82},
                "was": "coward",
                "became": [("predator", 0.61), ("coward", 0.30)],
            },
            {
                "name": "Bram", "verb": "wait", "target_id": None,
                "memories": 0, "goals": [], "relieved": {"fatigue": 0.2},
                "was": "loyalist", "became": [("loyalist", 0.7)],
            },
            {
                "name": "Sella", "verb": "give", "target_id": "id7",
                "coarse": True, "memories": 1,
                "goals": [{"key": "eat", "text": "not go hungry",
                           "progress": 1.0, "done": True}],
                "relieved": {"hunger": 0.3},
                "stakes": {"id7": 0.05},
                "was": "zealot", "became": [("zealot", 0.8)],
            },
        ],
    }


NAMES = {"id7": {"name": "Ondry", "kind": "npc"},
         "id2": {"name": "Marla", "kind": "npc"}}
PACKS = {"predator": "Predator", "coward": "Coward",
         "loyalist": "Loyalist", "zealot": "Zealot"}


def _lines(**kwargs):
    return narrate.turn_lines(_turn(), names=NAMES, packs=PACKS,
                              tuning=ReportTuning(**kwargs))


# --------------------------------------------------------------------------- #
#  1. The report, band by band
# --------------------------------------------------------------------------- #
def test_bands() -> None:
    default = _lines()
    here = "\n".join(default["here"])

    check("report: the act itself is named", "**Marla** went for **Ondry**" in here)
    check("report: what it got them", "closer to *settle the debt*" in here)
    check("report: what it settled",
          "that settled their nerves" in here,
          detail="reports the need that moved most, not all of them")
    check("report: and not the ones it moved less", "their hunger" not in here)

    check("report: stakes are off by default",
          "mattered" not in here and "barely noticed" not in here)
    check("report: witnesses are off by default", "remember it" not in here)
    check("report: drift is off by default", "turned from" not in here)

    loud = "\n".join(_lines(stakes=True, witnesses=True, drift=True)["here"])
    check("report: WHO IT MATTERED TO", "it was everything to **Ondry**" in loud)
    check("report: who will remember it", "3 will remember it" in loud)
    check("report: WHO THEY TURNED INTO",
          "turned from *Coward* toward *Predator*" in loud)

    # Each band off on its own, not merely all-off. Every band is given
    # something to say by the fixture, so reading the same with the switch on
    # and off means exactly one thing: it is wired to nothing.
    for band in ("goals", "needs", "stakes", "witnesses", "drift"):
        bare = {"goals": False, "needs": False}
        on = "\n".join(_lines(**{**bare, band: True})["here"])
        off = "\n".join(_lines(**{**bare, band: False})["here"])
        check(f"report: '{band}' switches off on its own", on != off,
              detail=f"identical with the switch both ways: {on!r}")


def test_switched_off() -> None:
    """Invariant 1: it must be possible to have none of this at all."""
    off = _lines(lines=0)
    check("report: 0 lines switches the whole report off",
          not off["here"] and not off["elsewhere"] and off["acted"] == 0)
    check("report: and says so", ReportTuning(lines=0).off)
    check("report: a normal setting does not", not ReportTuning().off)


def test_idle_and_cap() -> None:
    quiet = _lines()
    check("report: doing nothing is not reported",
          not any("Bram" in line for line in quiet["here"] + quiet["elsewhere"]))
    check("report: and is not counted against the cap", quiet["acted"] == 2)

    loud = _lines(idle=True)
    check("report: unless you ask for it",
          any("Bram" in line for line in loud["here"]) and loud["acted"] == 3)

    check("report: 'wait' and 'watch' are what idle means",
          tuple(narrate.UNCOMMITTED) == tuple(rs.UNCOMMITTED),
          detail="named in narrate and in the ruleset; they must not drift apart")

    capped = _lines(lines=1)
    shown = len(capped["here"]) + len(capped["elsewhere"])
    check("report: the cap holds", shown == 1)
    check("report: and the rest are counted, not dropped silently",
          capped["hidden"] == 1)


def test_here_and_elsewhere() -> None:
    split = _lines()
    check("report: the room and the world are kept apart",
          any("Marla" in line for line in split["here"])
          and any("Sella" in line for line in split["elsewhere"]))
    check("report: off-screen can be switched off",
          not _lines(offscreen=False)["elsewhere"])
    check("report: and the room is untouched by that",
          _lines(offscreen=False)["here"] == split["here"])
    check("report: the cap is shared between the two",
          _lines(lines=2)["hidden"] == 0 and _lines(lines=1)["hidden"] == 1,
          detail="off-screen drifting must not push the scene off the bottom")


# --------------------------------------------------------------------------- #
#  2. The two bugs this cost, as regressions
# --------------------------------------------------------------------------- #
def test_ids_are_not_integers() -> None:
    """Entity ids are ``ObjectId``s, never ints.

    The stake band shipped reading its map with ``int(key)``, which raises on
    every real id and was caught and skipped — so the band rendered nothing at
    all while its switch, its label and its description all looked correct. This
    is `14-CONVENTIONS.md` §5a's failure mode arriving in a message rather than
    on a page, and the reason the fixture ids here are strings.
    """
    line = _lines(stakes=True)["here"][0]
    check("ids: A STRING ID STILL RESOLVES A STAKE", "**Ondry**" in line
          and ("everything to" in line or "mattered to" in line))

    # And the bands themselves, which are what make it a report rather than a
    # readout of a float.
    def band(weight):
        act = dict(_turn()["acted"][0], stakes={"id7": weight})
        return narrate.notes_for(act, names=NAMES,
                                 tuning=ReportTuning(goals=False, needs=False,
                                                     stakes=True))[0]

    check("ids: a high stake reads as one", "everything to" in band(0.9))
    check("ids: a middling one reads as one", "mattered to" in band(0.5))
    check("ids: and an act nobody cared about says so",
          "barely noticed" in band(0.02),
          detail="silence would read as 'this had no stakes', which is a different claim")

    check("ids: an act aimed at nobody has no stake line",
          not narrate.notes_for(_turn()["acted"][1], names=NAMES,
                                tuning=ReportTuning(goals=False, needs=False,
                                                    stakes=True)))


def test_drift_is_only_news_when_it_turns() -> None:
    """Drift is continuous: ``became`` arrives on nearly every action.

    Reporting it as-is marked every line in the report and said nothing. Only a
    change in the **leading** archetype is a sentence about a person.
    """
    turned, held = _turn()["acted"][0], _turn()["acted"][1]
    tune = ReportTuning(goals=False, needs=False, drift=True)

    check("drift: a turn of character is reported",
          "turned from *Coward* toward *Predator*"
          in narrate.notes_for(turned, packs=PACKS, tuning=tune)[0])
    check("drift: THE ORDINARY CHURN IS NOT",
          not narrate.notes_for(held, packs=PACKS, tuning=tune),
          detail="Bram's mixture moved; who he leads with did not")

    fresh = dict(turned, was="")
    check("drift: somebody's first archetype reads as one",
          "*Predator* now" in narrate.notes_for(fresh, packs=PACKS, tuning=tune)[0])

    unknown = dict(turned, was="smuggler", became=[("harrier", 0.5)])
    check("drift: an archetype with no definition still names itself",
          "*Harrier*" in narrate.notes_for(unknown, packs=PACKS, tuning=tune)[0],
          detail="archetypes layer built-in -> server -> campaign; a key can outlive its label")

    stale = {k: v for k, v in turned.items() if k != "was"}
    check("drift: a report that cannot say stays quiet",
          not narrate.notes_for(stale, packs=PACKS, tuning=tune))


# --------------------------------------------------------------------------- #
#  3. Tuning: nothing baked in, and the panel can reach all of it
# --------------------------------------------------------------------------- #
def test_tunables() -> None:
    keys = {t["key"] for t in TUNABLES if t["group"] == "Reporting"}
    fields = set(ReportTuning().__dataclass_fields__)
    check("tuning: every Reporting field has a tunable",
          {f"report_{f}" for f in fields} == keys,
          detail=f"{sorted(keys)} vs {sorted(fields)}")

    # Invariant 2: a tunable ships with a panel control in the same phase as the
    # feature, and a control with no label or no range is not one.
    for spec in (t for t in TUNABLES if t["group"] == "Reporting"):
        check(f"tuning: '{spec['key']}' is described for the panel",
              bool(spec["label"]) and len(spec["description"]) > 40
              and spec["type"] in ("bool", "int", "float", "choice")
              and spec["group"] in tuning_registry.GROUPS)

    default = Tuning().report()
    check("tuning: the defaults are the dataclass's", default == ReportTuning())

    tuned = Tuning(campaign={"report_lines": 3, "report_stakes": True,
                             "report_goals": False})
    view = tuned.report()
    check("tuning: A CAMPAIGN OVERRIDE REACHES THE REPORT",
          view.lines == 3 and view.stakes is True and view.goals is False)
    check("tuning: and the rest still inherit",
          view.needs is True and view.offscreen is True)

    layered = Tuning(server={"report_lines": 2, "report_witnesses": True},
                     campaign={"report_lines": 5})
    check("tuning: campaign beats server, server beats default",
          layered.report().lines == 5 and layered.report().witnesses is True)


# --------------------------------------------------------------------------- #
#  4. End to end — the words a GM actually gets back
# --------------------------------------------------------------------------- #
def test_end_to_end() -> None:
    """Through ``_turn_summary``, with a real store behind it.

    The pure module can be right and the message still be empty: the cog is
    where the tuning is resolved, the names are looked up and the archetype
    labels are fetched, and every one of those is a thing the pure layer is
    forbidden from doing for itself.
    """
    campaign, store = _campaign(9401, "Report")
    people = [
        minds.spawn_npc(store, name=name, role=role, culture="city",
                        world_time=0, rng=Random(20 + i))
        for i, (name, role) in enumerate(
            [("Marla", "thief"), ("Ondry", "guard"), ("Bram", "smith")])
    ]
    store.scenes.create(Scene(
        guild_id=campaign.guild_id, campaign_id=campaign.id, channel_id=1,
        title="The tap room", present=[p.id for p in people], lighting="dim",
    ))
    marla = store.entities.get(people[0].id)
    minds.add_goal(store, marla, kind="acquire", text="settle the debt",
                   subject_id=people[1].id, priority=0.8, world_time=0)

    def advance():
        seq = store.campaigns.next_seq(campaign.id)
        return minds.advance(store, campaign, 2.0, Random(seq)).get("turn") or {}

    def retune(**overrides):
        campaign.settings["tuning"] = dict(overrides)
        campaigns_for(campaign.guild_id).save_settings(campaign.id, campaign.settings)

    turn = advance()
    check("e2e: the world moved", (turn.get("actors") or 0) > 0)

    message = _turn_summary(store, campaign, turn)
    check("e2e: THE TURN REPORTS ITSELF", "While that happened" in message)
    check("e2e: with somebody named", any(p.identity.name in message for p in people))

    retune(report_lines=0)
    check("e2e: and can be switched off entirely",
          _turn_summary(store, campaign, advance()) == "")

    retune(report_stakes=True, report_witnesses=True, report_drift=True)
    loud = _turn_summary(store, campaign, advance())
    check("e2e: a live stake resolves through a real id",
          "noticed" in loud or "mattered to" in loud or "everything to" in loud,
          detail=loud[:160])
    check("e2e: witnesses are counted", "remember it" in loud)

    retune()
    check("e2e: a turn where nobody acts is not silence",
          _turn_summary(store, campaign, {"actors": 0, "acted": []})
          == "\n\nNobody did anything worth reporting.")
    check("e2e: and a turn that never ran says nothing at all",
          _turn_summary(store, campaign, {}) == "")

    # Everyone acted, everyone off-screen, off-screen switched off: the world
    # moved and the report must not silently claim otherwise.
    retune(report_offscreen=False)
    only_off = {"actors": 1, "acted": [
        {"name": "Sella", "verb": "give", "target_id": None, "coarse": True,
         "memories": 1, "goals": [], "relieved": {}}]}
    check("e2e: a wholly off-screen turn still reports as quiet",
          _turn_summary(store, campaign, only_off)
          == "\n\nNobody did anything worth reporting.")


def test_reexports() -> None:
    """``describe_act`` moved into ``narrate``; ``minds`` still answers for it."""
    check("moved: minds.describe_act is narrate's",
          minds.describe_act is narrate.describe_act)
    check("moved: and the phrase table came with it",
          minds.ACTED_PHRASES is narrate.ACTED_PHRASES)
    check("moved: every affordance has a phrase",
          set(rs.AFFORDANCES) <= set(narrate.ACTED_PHRASES),
          detail="a verb with no phrase renders as its own key")


def main() -> int:
    for test in (
        test_bands,
        test_switched_off,
        test_idle_and_cap,
        test_here_and_elsewhere,
        test_ids_are_not_integers,
        test_drift_is_only_news_when_it_turns,
        test_tunables,
        test_end_to_end,
        test_reexports,
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
