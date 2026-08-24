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
from helpers.dnd.mind import decide as decide_math  # noqa: E402
from helpers.dnd.mind import relationships as rel_mod  # noqa: E402
from helpers.dnd.mind import stakes as stakes_math  # noqa: E402
from helpers.dnd import interactions as interaction_registry  # noqa: E402
from helpers.dnd.world import interaction as interaction_model  # noqa: E402
from helpers.dnd import tuning as tuning_registry  # noqa: E402
from helpers.dnd.tuning import GistTuning, TUNABLES, ReportTuning, Tuning  # noqa: E402
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
    # Not a naming convention — a behavioural one. Every tunable in the group
    # must actually move a field of the dataclass, and every field must be moved
    # by some tunable. Either half failing is a control wired to nothing, which
    # is this project's most expensive recurring bug.
    keys = [t["key"] for t in TUNABLES if t["group"] == "Reporting"]
    fields = set(ReportTuning().__dataclass_fields__)
    base = Tuning().report()
    moved = set()
    for key in keys:
        spec = next(t for t in TUNABLES if t["key"] == key)
        other = (not spec["default"]) if spec["type"] == "bool" else (
            float(spec["default"]) + 1 if spec["type"] != "bool" else 0)
        changed = {
            field for field in fields
            if getattr(Tuning(campaign={key: other}).report(), field)
            != getattr(base, field)
        }
        check(f"tuning: '{key}' reaches the report", bool(changed),
              detail="" if changed else "the control posts, nothing reads it")
        moved |= changed
    check("tuning: every Reporting field is reachable from the panel",
          moved == fields, detail=f"unreachable: {sorted(fields - moved)}")

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


# --------------------------------------------------------------------------- #
#  5. Episode gists — one event, three memories of it
# --------------------------------------------------------------------------- #
def test_episode_gists() -> None:
    """`08-LLM-LAYER.md` §5's `summarize_episode`, done with a template.

    The gist is the longest-lived field in the decay model, so it is what a
    memory eventually *is*. Wording it from the holder's side is what makes P2's
    "two witnesses differ" true of the words and not only of the numbers.
    """
    gist = narrate.episode_gist
    check("gist: it happened to them", gist("saved", "Ondry", "Marla",
                                            role=narrate.ROLE_SUBJECT)
          == "Ondry saved me")
    check("gist: THEY DID IT", gist("saved", "Ondry", "Marla",
                                    role=narrate.ROLE_ACTOR) == "I saved Marla")
    check("gist: they watched", gist("saved", "Ondry", "Marla",
                                     role=narrate.ROLE_WITNESS)
          == "Ondry saved Marla")

    check("gist: the three genuinely differ",
          len({gist("saved", "Ondry", "Marla", role=r)
               for r in (narrate.ROLE_SUBJECT, narrate.ROLE_ACTOR,
                         narrate.ROLE_WITNESS)}) == 3)

    flat = GistTuning(perspective=False)
    check("gist: perspective switches off",
          {gist("saved", "Ondry", "Marla", role=r, tuning=flat)
           for r in (narrate.ROLE_SUBJECT, narrate.ROLE_ACTOR,
                     narrate.ROLE_WITNESS)} == {"Ondry saved Marla"},
          detail="off must give exactly the flat third-person line it always did")

    # The table is `mind/relationships.PHRASES`, not a copy of it, so a kind can
    # never read one way in a relationship log and another in a memory.
    check("gist: the phrase table is the relationships one",
          narrate.rel_mod.PHRASES is rel_mod.PHRASES)
    for kind in rel_mod.PHRASES:
        line = gist(kind, "Ondry", "Marla", role=narrate.ROLE_SUBJECT)
        check(f"gist: '{kind}' reads as a sentence",
              line.startswith("Ondry ") and line.endswith(" me")
              and "_" not in line,
              detail=repr(line))

    check("gist: an unknown kind still reads",
          gist("bargained_with", "Ondry", "Marla") == "Ondry bargained with Marla")

    # Undirected acts — most of what anybody actually does.
    check("gist: their own undirected act says 'I'",
          narrate.act_gist("hide", "Marla", first_person=True)
          == "I went to ground")
    check("gist: and the room's version names them",
          narrate.act_gist("hide", "Marla") == "Marla went to ground")
    check("gist: person agreement holds inside the sentence",
          narrate.act_gist("use", "Marla", first_person=True) == "I used what I had"
          and narrate.act_gist("use", "Marla") == "Marla used what they had",
          detail="'I used what they had' is the failure this guards")
    check("gist: switched off, an actor is named like anyone else",
          narrate.act_gist("hide", "Marla", first_person=True, tuning=flat)
          == "Marla went to ground")
    # Every verb an NPC can actually commit to has to produce a real sentence
    # somewhere, by one of the two routes: a directed verb becomes a
    # relationship kind and takes the PHRASES table, an undirected one takes
    # ACT_GISTS. A verb in neither renders as its own key in somebody's memory.
    undirected = set(narrate.ACT_GISTS)
    directed = {
        verb: minds.ACT_AS_RELATION[verb]
        for verb in rs.AFFORDANCES if verb in minds.ACT_AS_RELATION
    }
    for verb in rs.AFFORDANCES:
        via = directed.get(verb)
        check(f"gist: '{verb}' has a sentence",
              verb in undirected or (via is not None and via in rel_mod.PHRASES),
              detail=f"neither in ACT_GISTS nor mapped to a known kind ({via!r})")


def test_summary_gists() -> None:
    """What a stretch nobody can call to mind any more reduces to.

    `05-MEMORY.md` §8 asks for *"a hard winter at the docks"*; the old line was
    a count of how many things went, which is the one thing about a forgotten
    period nobody has ever retained.
    """
    line = narrate.summary_gist(count=41, span_days=18.0, valence=-0.5,
                                with_names=["Ondry"], place="the docks")
    check("summary: IT DESCRIBES THE STRETCH",
          line == "a bad fortnight, mostly with Ondry at the docks", detail=line)

    check("summary: how long it ran comes from the span",
          [narrate.summary_gist(count=2, span_days=d, valence=0.0)
           for d in (0.2, 5.0, 18.0, 40.0, 120.0, 300.0, 900.0)]
          == ["a quiet day", "a quiet week", "a quiet fortnight", "a quiet month",
              "a quiet season", "a quiet year", "a quiet few years"])

    tones = [narrate.summary_gist(count=2, span_days=5.0, valence=v)
             for v in (-0.9, -0.2, 0.0, 0.3, 0.9)]
    check("summary: and how it felt comes from the valence",
          tones == ["a bad week", "a hard week", "a quiet week", "a good week",
                    "a fine week"], detail=str(tones))

    check("summary: company reads as a list",
          narrate.summary_gist(count=2, span_days=5.0, valence=0.0,
                               with_names=["A", "B", "C"])
          == "a quiet week, mostly with A, B and C")
    check("summary: an empty name is not company",
          narrate.summary_gist(count=2, span_days=5.0, valence=0.0,
                               with_names=[None, ""]) == "a quiet week",
          detail="an unresolved id must not render as 'mostly with None'")

    check("summary: it switches off to the old count",
          narrate.summary_gist(count=41, span_days=18.0, valence=-0.5,
                               with_names=["Ondry"],
                               tuning=GistTuning(summaries=False))
          == "a stretch of 41 things that no longer come to mind clearly")

    # Replay depends on the same memories folding the same way every time.
    people = ["b", "a", "b", "c", "a", "b"]
    check("summary: who dominates is stable, not arbitrary",
          narrate.dominant(people) == narrate.dominant(list(people)) == ["b", "a"])
    check("summary: and the holder is never their own company",
          narrate.dominant(people, exclude=("b",)) == ["a", "c"])


def test_gists_end_to_end() -> None:
    """Through ``interact`` and ``commit_decision``, with a real store."""
    campaign, store = _campaign(9402, "Gists")
    ondry = minds.spawn_npc(store, name="Ondry", role="guard", world_time=0,
                            rng=Random(3))
    marla = minds.spawn_npc(store, name="Marla", role="thief", world_time=0,
                            rng=Random(7))
    cass = minds.spawn_npc(store, name="Cass", role="scribe", world_time=0,
                           rng=Random(9))
    scene = store.scenes.create(Scene(
        guild_id=campaign.guild_id, campaign_id=campaign.id, channel_id=1,
        title="the tap room", present=[ondry.id, marla.id, cass.id],
    ))

    def retune(**overrides):
        campaign.settings["tuning"] = dict(overrides)
        campaigns_for(campaign.guild_id).save_settings(campaign.id, campaign.settings)

    out = minds.interact(store, ondry, marla, "saved", world_time=100,
                         rng=Random(4), witnesses=[cass],
                         tuning=minds.tuning_for(store, campaign))
    said = {eid: memory.gist for eid, memory in out["memories"].items()}
    check("e2e gist: ONE EVENT, THREE DIFFERENT MEMORIES",
          said.get(marla.id) == "Ondry saved me"
          and said.get(ondry.id) == "I saved Marla"
          and said.get(cass.id) == "Ondry saved Marla", detail=str(said))

    told = minds.interact(
        store, ondry, marla, "saved", world_time=300, rng=Random(6),
        witnesses=[cass], description="the beam came down and Ondry took it",
        tuning=minds.tuning_for(store, campaign),
    )
    check("e2e gist: THE GM'S OWN WORDS ARE NEVER RE-PERSONED",
          {m.gist for m in told["memories"].values()}
          == {"the beam came down and Ondry took it"},
          detail="authored text is not ours to rewrite into first person")

    retune(gist_perspective=False)
    flat = minds.interact(store, ondry, marla, "helped", world_time=200,
                          rng=Random(5), witnesses=[cass],
                          tuning=minds.tuning_for(store, campaign))
    check("e2e gist: and it switches off for the whole campaign",
          {m.gist for m in flat["memories"].values()} == {"Ondry helped Marla"})

    # An undirected act: the actor's own memory against the room's.
    retune()
    marla = store.entities.get(marla.id)
    hiding = decide_math.Decision(
        chosen=decide_math.Scored(verb="hide", target_id=None, utility=1.0,
                                  terms={"trait": 1.0}),
        considered=(decide_math.Scored(verb="hide", target_id=None),),
    )
    minds.commit_decision(store, marla, scene, hiding, world_time=400,
                          rng=Random(8), campaign=campaign)

    def newest(entity_id):
        held = sorted(store.memories.for_entity(entity_id),
                      key=lambda m: -m.encoded_at)
        return held[0].gist if held else ""

    check("e2e gist: they remember doing it, the room remembers watching",
          newest(marla.id) == "I went to ground"
          and newest(cass.id) == "Marla went to ground",
          detail=f"{newest(marla.id)!r} / {newest(cass.id)!r}")

    # And the forgotten stretch. Scene close is where working memories go.
    for day in range(40):
        minds.interact(store, ondry, marla, "talked",
                       world_time=500 + day * 1440, rng=Random(day),
                       tuning=minds.tuning_for(store, campaign))
    end = 500 + 40 * 1440
    report = minds.close_scene(store, [store.entities.get(marla.id)], end)
    _kept, dropped = report.get(marla.id, (0, 0))
    check("e2e gist: a scene's trivia is let go", dropped > 0)

    summaries = [m.gist for m in store.memories.for_entity(marla.id)
                 if m.when_precision == "sometime"]
    check("e2e gist: AND FOLDS INTO SOMETHING THAT READS LIKE A MEMORY",
          any(s.startswith("a ") and "mostly with Ondry" in s for s in summaries),
          detail=str(summaries))
    check("e2e gist: the summary is not a count of what went",
          not any("things that no longer" in s for s in summaries))


# --------------------------------------------------------------------------- #
#  6. Interaction kinds as data — what an act is worth, written down once
# --------------------------------------------------------------------------- #
# Here rather than in the P2 suite because the failure being guarded against is
# this suite's subject: a number that shapes the world with nowhere to read or
# change it. Stakes are P2 mechanics; *the stakes being editable* is P4 work.
def test_one_table_not_four() -> None:
    """The set of interaction kinds is defined in exactly one place.

    It used to be four — ``DELTAS``, ``PHRASES`` and ``ROMANTIC`` in
    ``mind/relationships.py`` and ``KIND_MAGNITUDE`` in ``mind/stakes.py`` — all
    keyed by the same strings and edited by hand. They had already drifted: the
    five romantic kinds went into three of the four and were never given a
    magnitude, so ``lay_with`` fell through to the 0.4 default and was worth
    exactly as much as ``lied``.
    """
    shipped = interaction_registry.built_in()
    check("kinds: the shipped file parses and is not empty", len(shipped) >= 21,
          detail=f"{len(shipped)} kinds")

    check("kinds: EVERY KIND HAS A MAGNITUDE OF ITS OWN",
          all(key in stakes_math.KIND_MAGNITUDE for key in shipped),
          detail="the drift that started this")
    check("kinds: including the romance-gated ones",
          stakes_math.default_magnitude("lay_with")
          != stakes_math.default_magnitude("lied"),
          detail=f"lay_with {stakes_math.default_magnitude('lay_with')} vs "
                 f"lied {stakes_math.default_magnitude('lied')}")

    # The old module-level tables now *derive* from the file, so there is still
    # exactly one place the numbers live and old callers still work.
    check("kinds: the deltas table is the file",
          rel_mod.DELTAS == interaction_model.as_deltas(shipped))
    check("kinds: so is the phrase table",
          rel_mod.PHRASES == interaction_model.as_phrases(shipped))
    check("kinds: and so is the list of gated ones",
          set(rel_mod.ROMANTIC)
          == set(interaction_model.requiring(shipped, "desire")))

    for key, kind in shipped.items():
        check(f"kinds: '{key}' is complete",
              bool(kind.label and kind.phrase and kind.description) and kind.deltas,
              detail="a kind with no phrase renders as its key in a memory")
        check(f"kinds: '{key}' only names real axes",
              set(kind.deltas) <= set(interaction_model.DELTA_FIELDS),
              detail=str(sorted(set(kind.deltas) - set(interaction_model.DELTA_FIELDS))))


def test_kinds_are_editable() -> None:
    """Built-in → server → campaign, and a GM may add one the engine never had."""
    shipped = interaction_registry.built_in()

    plain = interaction_registry.Interactions()
    check("kinds: with no overrides you get the shipped set",
          plain.available().keys() == shipped.keys()
          and plain.source_of("saved") == "builtin")

    tweaked = dict(shipped["saved"].to_doc(), magnitude=0.5)
    layered = interaction_registry.Interactions(
        server={"saved": tweaked},
        campaign={"saved": dict(tweaked, magnitude=0.2)},
    )
    check("kinds: CAMPAIGN BEATS SERVER BEATS SHIPPED",
          layered.get("saved").magnitude == 0.2
          and interaction_registry.Interactions(server={"saved": tweaked})
          .get("saved").magnitude == 0.5
          and shipped["saved"].magnitude == 1.0)
    check("kinds: and the panel can say which layer won",
          layered.source_of("saved") == "campaign"
          and layered.source_of("betrayed") == "builtin")

    invented, problem = interaction_registry.validate(
        {"label": "Swore an oath to", "deltas": {"trust": 0.4}, "magnitude": 0.6}
    )
    check("kinds: A GM CAN ADD ONE THAT DID NOT EXIST",
          invented is not None and invented["key"] == "swore_an_oath_to",
          detail=problem)
    with_new = interaction_registry.Interactions(campaign={invented["key"]: invented})
    check("kinds: and it resolves like any other",
          with_new.get("swore_an_oath_to").magnitude == 0.6
          and "swore_an_oath_to" in with_new.keys())

    # Renaming must edit, not fork — the bug archetypes shipped with.
    renamed, _ = interaction_registry.validate(
        {"key": "saved", "label": "Pulled them out of it", "deltas": {"trust": 0.3}}
    )
    check("kinds: renaming edits in place", renamed["key"] == "saved",
          detail="a rename that forks leaves the original in force")

    check("kinds: an act that changes nothing is refused",
          interaction_registry.validate({"label": "Nodded at", "deltas": {}})[0] is None)
    check("kinds: an unnamed one is refused",
          interaction_registry.validate({"deltas": {"trust": 0.2}})[0] is None)
    check("kinds: a typo'd axis is dropped, not carried",
          "trsut" not in interaction_registry.validate(
              {"label": "X", "deltas": {"trust": 0.2, "trsut": 0.9}})[0]["deltas"])


def test_kinds_reach_the_simulation() -> None:
    """The proof that editable means *takes effect*, not merely *stored*."""
    campaign, store = _campaign(9403, "Kinds")

    def retune(**settings):
        campaign.settings.update(settings)
        campaigns_for(campaign.guild_id).save_settings(campaign.id, campaign.settings)

    def run(guild_seed):
        a = minds.spawn_npc(store, name=f"A{guild_seed}", world_time=0,
                            rng=Random(30 + guild_seed))
        b = minds.spawn_npc(store, name=f"B{guild_seed}", world_time=0,
                            rng=Random(60 + guild_seed))
        out = minds.interact(store, a, b, "saved", world_time=100, rng=Random(2),
                             campaign=campaign,
                             tuning=minds.tuning_for(store, campaign))
        return out, a, b

    retune(interactions={})
    shipped_out, _a, shipped_b = run(1)

    # Halve what being saved is worth, and the person it happened to should feel
    # it correspondingly less.
    lighter = dict(interaction_registry.built_in()["saved"].to_doc(), magnitude=0.3)
    retune(interactions={"saved": lighter})
    light_out, _a2, light_b = run(2)

    check("kinds: A CAMPAIGN'S OWN MAGNITUDE CHANGES THE STAKE",
          light_out["stakes"][light_b.id].weight
          < shipped_out["stakes"][shipped_b.id].weight,
          detail=f"{light_out['stakes'][light_b.id].weight:.3f} vs "
                 f"{shipped_out['stakes'][shipped_b.id].weight:.3f}")

    # Reword it, and the memory of it is reworded too.
    reworded = dict(interaction_registry.built_in()["saved"].to_doc(),
                    phrase="pulled")
    retune(interactions={"saved": reworded})
    worded_out, _a3, worded_b = run(3)
    check("kinds: AND ITS WORDING CHANGES THE MEMORY",
          "pulled me" in worded_out["memories"][worded_b.id].gist,
          detail=worded_out["memories"][worded_b.id].gist)

    # Change the deltas, and the relationship moves differently.
    colder = dict(interaction_registry.built_in()["saved"].to_doc(),
                  deltas={"affinity": -0.4, "debt": 1})
    retune(interactions={"saved": colder})
    _cold_out, cold_a, cold_b = run(4)
    check("kinds: and its deltas move the relationship",
          store.relations.between(cold_b.id, cold_a.id).affinity < 0,
          detail="being saved now costs affinity, because this campaign says so")

    # The safety gate is data too, and it still refuses.
    retune(interactions={})
    gated_a = minds.spawn_npc(store, name="G1", world_time=0, rng=Random(91))
    gated_b = minds.spawn_npc(store, name="G2", world_time=0, rng=Random(92))
    minds.relate(store, gated_a, gated_b, "lay_with", world_time=100,
                 campaign=campaign, tuning=minds.tuning_for(store, campaign))
    check("kinds: a gated act is still refused when the need is off",
          store.relations.between(gated_a.id, gated_b.id).familiarity == 0.0,
          detail="`requires` is per-kind data now and must still hold the line")


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
        test_episode_gists,
        test_summary_gists,
        test_gists_end_to_end,
        test_one_table_not_four,
        test_kinds_are_editable,
        test_kinds_reach_the_simulation,
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
