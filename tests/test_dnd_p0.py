"""
Dodo Tabletop — P0 acceptance tests.

These check the four things ``docs/dnd/12-ROADMAP.md`` says P0 must deliver:

1. two campaigns on two servers with **no data leakage**,
2. a character sheet whose stats came from a **ruleset**, not a hardcoded array,
3. a roll that actually **changes an outcome**,
4. nothing lost across a restart (state is in Mongo, and replay is deterministic).

Run with ``py tests/test_dnd_p0.py``. No pytest, no mongomock — the collections
are swapped for the in-memory fake in ``tests/fake_mongo.py`` before the store
modules are imported, so nothing here can touch the real database.
"""

from __future__ import annotations

import os
import sys
from random import Random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fake_mongo import DuplicateKeyError, FakeCollection  # noqa: E402

# --------------------------------------------------------------------------- #
#  Swap the collections before anything in the store layer imports them.
#  config.database opens a MongoClient at import time; connection is lazy, so
#  importing it is safe, but every handle is replaced here regardless.
# --------------------------------------------------------------------------- #
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

pymongo.errors.DuplicateKeyError = DuplicateKeyError  # the fake raises ours

from helpers.dnd import rules  # noqa: E402
from helpers.dnd.rules import dice  # noqa: E402
from helpers.dnd.rules.ruleset import Action  # noqa: E402
from helpers.dnd.store import ScopeError, campaign_store, campaigns_for  # noqa: E402
from helpers.dnd.store import entities as entities_module  # noqa: E402
from helpers.dnd.store import campaigns as campaigns_module  # noqa: E402
from helpers.dnd.store import events as events_module  # noqa: E402
from helpers.dnd.store import scenes as scenes_module  # noqa: E402
from helpers.dnd.store.repo import Scope  # noqa: E402
from helpers.dnd.world import event as event_kinds  # noqa: E402
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.entity import KIND_PC, Entity, Identity  # noqa: E402
from helpers.dnd.world.event import event_seed  # noqa: E402

# The store modules bound the handles at import time, so re-point those too.
campaigns_module.CampaignRepo.collection = _FAKES["dnd_campaigns"]
entities_module.EntityRepo.collection = _FAKES["dnd_entities"]
events_module.EventRepo.collection = _FAKES["dnd_events"]
scenes_module.SceneRepo.collection = _FAKES["dnd_scenes"]
events_module.DuplicateKeyError = DuplicateKeyError

_FAKES["dnd_events"].create_index([("campaign_id", 1), ("seq", 1)], unique=True)


PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


# --------------------------------------------------------------------------- #
#  1. Dice
# --------------------------------------------------------------------------- #
def test_dice() -> None:
    check("dice: plain", str(dice.parse("2d6")) == "2d6")
    check("dice: modifier", dice.parse("1d20+5").modifier == 5)
    check("dice: chained modifiers", dice.parse("2d6+3-1").modifier == 2)
    check("dice: keep-highest", str(dice.parse("4d6kh3")) == "4d6kh3")
    check("dice: advantage is sugar", str(dice.parse("1d20adv")) == "2d20kh1")
    check("dice: disadvantage is sugar", str(dice.parse("1d20dis")) == "2d20kl1")
    check("dice: drop becomes keep", str(dice.parse("2d20dl1")) == "2d20kh1")
    check("dice: bare d20", dice.parse("d20").count == 1)
    check("dice: constant", dice.parse("7").constant is True)
    check("dice: gibberish is None", dice.parse("banana") is None)
    check("dice: empty is None", dice.parse("") is None)
    check("dice: drop-all rejected", dice.parse("2d6dl2") is None)

    try:
        dice.parse("5000d6", max_dice=100, max_sides=1000)
        check("dice: limit raises", False, "no DiceLimitError")
    except dice.DiceLimitError:
        check("dice: limit raises", True)

    # Keep/drop actually discards, and the total only counts survivors.
    roll = dice.roll(dice.parse("4d6kh3"), Random(42))
    check("dice: keeps 3 of 4", len(roll.kept) == 3 and len(roll.faces) == 4)
    check("dice: total is of kept", roll.total == sum(roll.kept))
    check("dice: one die dropped", len(roll.dropped) == 1)

    # Same seed, same roll — the property the whole replay design rests on.
    a = dice.roll_expression("10d20kh5+3", Random(7))
    b = dice.roll_expression("10d20kh5+3", Random(7))
    check("dice: deterministic under a seed", a.total == b.total and a.faces == b.faces)

    # Bounds hold over many rolls rather than one lucky one.
    rng = Random(1)
    faces = [f for _ in range(400) for f in dice.roll(dice.parse("3d6"), rng).faces]
    check("dice: faces within range", all(1 <= f <= 6 for f in faces))
    check("dice: uses the whole range", set(faces) == {1, 2, 3, 4, 5, 6})


# --------------------------------------------------------------------------- #
#  2. Rulesets — sheets are generated, not hardcoded
# --------------------------------------------------------------------------- #
def test_rulesets() -> None:
    check("rules: both registered", rules.keys() == ["freeform", "srd5e"])
    check("rules: unknown key falls back", rules.get("nonsense").key == "freeform")

    srd = rules.get("srd5e")
    wizard = srd.blank_sheet({"role": "wizard"}, Random(1))
    barbarian = srd.blank_sheet({"role": "barbarian"}, Random(1))

    # THE regression test for the old cog, which gave every character
    # STR 15 DEX 14 CON 13 INT 12 WIS 10 CHA 8 regardless of concept.
    check(
        "srd5e: classes differ",
        wizard["abilities"] != barbarian["abilities"],
        f"{wizard['abilities']} vs {barbarian['abilities']}",
    )
    check("srd5e: wizard is smart", wizard["abilities"]["INT"] == 15)
    check("srd5e: barbarian is strong", barbarian["abilities"]["STR"] == 15)
    check("srd5e: hit dice differ", wizard["hp"]["max"] != barbarian["hp"]["max"])
    check("srd5e: standard array preserved",
          sorted(wizard["abilities"].values(), reverse=True) == [15, 14, 13, 12, 10, 8])

    free = rules.get("freeform")
    scholar = free.blank_sheet({"role": "archivist"}, Random(1))
    soldier = free.blank_sheet({"role": "soldier"}, Random(1))
    check("freeform: concepts differ", scholar["approaches"] != soldier["approaches"])
    check("freeform: scholar leans wits", scholar["approaches"]["wits"] == 2)
    check("freeform: soldier leans force", soldier["approaches"]["force"] == 2)

    # Sheets render for both rulesets without the caller knowing which.
    for ruleset, stats in ((srd, wizard), (free, scholar)):
        fields = ruleset.sheet_fields(stats)
        check(f"{ruleset.key}: sheet renders", bool(fields) and all(len(f) == 2 for f in fields))


# --------------------------------------------------------------------------- #
#  3. The roll changes the outcome
# --------------------------------------------------------------------------- #
def test_resolution() -> None:
    srd = rules.get("srd5e")
    stats = srd.blank_sheet({"role": "rogue"}, Random(1))

    # Sweep seeds at a fixed DC: a system where the die matters must produce
    # more than one degree. The old cog never consulted a die at all.
    degrees = {
        srd.resolve(Action(approach="DEX", difficulty=15), stats, None, Random(seed)).degree
        for seed in range(200)
    }
    check("srd5e: the die matters", len(degrees) > 1, f"degrees seen: {sorted(degrees)}")

    # A high DC should fail more often than a low one.
    def success_rate(dc: int) -> float:
        wins = sum(
            srd.resolve(Action(approach="DEX", difficulty=dc), stats, None, Random(s)).success
            for s in range(300)
        )
        return wins / 300

    easy, hard = success_rate(5), success_rate(25)
    check("srd5e: DC changes odds", easy > hard + 0.3, f"DC5={easy:.2f} DC25={hard:.2f}")

    # A better ability is genuinely better.
    strong = dict(stats, abilities=dict(stats["abilities"], DEX=20))
    weak = dict(stats, abilities=dict(stats["abilities"], DEX=4))
    strong_rate = sum(
        srd.resolve(Action(approach="DEX", difficulty=15), strong, None, Random(s)).success
        for s in range(300)
    )
    weak_rate = sum(
        srd.resolve(Action(approach="DEX", difficulty=15), weak, None, Random(s)).success
        for s in range(300)
    )
    check("srd5e: stats matter", strong_rate > weak_rate, f"{strong_rate} vs {weak_rate}")

    # Same seed → identical outcome, for both rulesets.
    for ruleset in rules.all_rulesets():
        sheet = ruleset.blank_sheet({"role": "fighter"}, Random(3))
        first = ruleset.resolve(Action(approach="STR"), sheet, None, Random(99))
        second = ruleset.resolve(Action(approach="STR"), sheet, None, Random(99))
        check(f"{ruleset.key}: resolution is deterministic",
              first.degree == second.degree and first.roll.total == second.roll.total)
        check(f"{ruleset.key}: outcome carries a summary", bool(first.summary))

    free = rules.get("freeform")
    sheet = free.blank_sheet({"role": "thief"}, Random(2))
    seen = {
        free.resolve(Action(approach="finesse"), sheet, None, Random(s)).degree
        for s in range(200)
    }
    check("freeform: reaches all four degrees", seen == {"fail", "cost", "success", "triumph"},
          f"saw {sorted(seen)}")


# --------------------------------------------------------------------------- #
#  4. Scope enforcement — the tenant-isolation acceptance criterion
# --------------------------------------------------------------------------- #
def test_scope_rejects_unscoped() -> None:
    try:
        Scope(guild_id=0)
        check("scope: refuses empty guild", False)
    except ScopeError:
        check("scope: refuses empty guild", True)

    try:
        entities_module.EntityRepo(Scope(guild_id=1))
        check("scope: refuses missing campaign", False)
    except ScopeError:
        check("scope: refuses missing campaign", True)

    store = campaign_store(1, "C1")
    widened = store.entities._filter({"guild_id": 999, "campaign_id": "OTHER", "kind": "pc"})
    check("scope: caller cannot widen the filter",
          widened["guild_id"] == 1 and widened["campaign_id"] == "C1")
    stamped = store.entities._stamp({"guild_id": 999, "campaign_id": "OTHER"})
    check("scope: caller cannot mis-stamp a write",
          stamped["guild_id"] == 1 and stamped["campaign_id"] == "C1")


def test_two_servers_no_leakage() -> None:
    """Two guilds, identically-named campaigns and characters. Nothing crosses."""
    guild_a, guild_b = 1001, 2002

    campaign_a = campaigns_for(guild_a).create(
        Campaign(guild_id=guild_a, name="The Ashen Compact", ruleset="srd5e", gm_ids=[7])
    )
    campaign_b = campaigns_for(guild_b).create(
        Campaign(guild_id=guild_b, name="The Ashen Compact", ruleset="freeform", gm_ids=[8])
    )
    check("tenancy: same name on two servers is allowed", campaign_a.id != campaign_b.id)

    store_a = campaign_store(guild_a, campaign_a.id)
    store_b = campaign_store(guild_b, campaign_b.id)

    for store, campaign, owner in ((store_a, campaign_a, 7), (store_b, campaign_b, 8)):
        ruleset = rules.get(campaign.ruleset)
        store.entities.create(
            Entity(
                guild_id=campaign.guild_id, campaign_id=campaign.id, kind=KIND_PC,
                owner_id=owner, identity=Identity(name="Marla Venn"),
                stats=ruleset.blank_sheet({"role": "rogue"}, Random(1)),
            )
        )

    check("tenancy: each server sees one character",
          len(store_a.entities.characters()) == 1 and len(store_b.entities.characters()) == 1)
    check("tenancy: A cannot see B's player", store_a.entities.character_of(8) is None)
    check("tenancy: B cannot see A's player", store_b.entities.character_of(7) is None)

    # An id from the other campaign must not resolve, even though it is a valid
    # id in the same physical collection.
    foreign = store_b.entities.characters()[0]
    check("tenancy: foreign id does not resolve", store_a.entities.get(foreign.id) is None)

    # Guild-level listing is scoped too.
    check("tenancy: campaign lists are per guild",
          len(campaigns_for(guild_a).list()) == 1 and len(campaigns_for(guild_b).list()) == 1)

    # And name lookup does not cross servers.
    check("tenancy: by_name is scoped",
          campaigns_for(guild_a).by_name("The Ashen Compact").id == campaign_a.id)

    # Rulesets are per campaign, so the two sheets have different shapes.
    check("tenancy: rulesets stay separate",
          "abilities" in store_a.entities.characters()[0].stats
          and "approaches" in store_b.entities.characters()[0].stats)

    # Deleting everything in A leaves B untouched.
    store_a.entities.delete_many()
    check("tenancy: scoped delete spares the other server",
          len(store_a.entities.characters()) == 0 and len(store_b.entities.characters()) == 1)


# --------------------------------------------------------------------------- #
#  5. The event log
# --------------------------------------------------------------------------- #
def test_event_log() -> None:
    guild = 3003
    campaign = campaigns_for(guild).create(Campaign(guild_id=guild, name="Log Test", seed=12345))
    store = campaign_store(guild, campaign.id)

    first = store.events.append(event_kinds.CAMPAIGN_CREATED, payload={"n": 1})
    second = store.events.append(event_kinds.CHECK, payload={"n": 2})
    check("events: sequence increments", first.seq == 1 and second.seq == 2)
    check("events: scoped to the campaign", first.campaign_id == campaign.id)

    # The unique (campaign_id, seq) index is the concurrency control; a collision
    # must be retried onto a fresh number, never dropped.
    _FAKES["dnd_events"].insert_one(
        {"guild_id": guild, "campaign_id": campaign.id, "seq": 3, "kind": "squatter"}
    )
    third = store.events.append(event_kinds.ROLL, payload={"n": 3})
    check("events: retries past a taken seq", third is not None and third.seq == 4,
          f"got seq {third.seq if third else None}")

    recent = store.events.recent(10)
    check("events: recent is newest first", recent[0].seq >= recent[-1].seq)
    replayed = list(store.events.since(0))
    check("events: replay is ordered", [e.seq for e in replayed] == sorted(e.seq for e in replayed))

    # Derived seeds: stable for a given (campaign seed, seq), distinct between
    # neighbouring events.
    check("events: seed is derived, not random",
          event_seed(12345, 1) == event_seed(12345, 1))
    check("events: neighbouring seeds differ", event_seed(12345, 1) != event_seed(12345, 2))

    # A campaign that no longer exists must not be resurrected by an append.
    gone = campaign_store(guild, "does-not-exist")
    check("events: refuses to write to a missing campaign",
          gone.events.append(event_kinds.ROLL) is None)

    # A resolution derives its seed from a sequence number *before* it can roll,
    # so it hands that number back to append. The event's seq must be the one the
    # seed came from, and no number may be burned along the way.
    before = store.campaigns.get(campaign.id).seq
    allocated = store.campaigns.next_seq(campaign.id)
    resolved = store.events.append(
        event_kinds.CHECK, seq=allocated, seed=event_seed(campaign.seed, allocated)
    )
    after = store.campaigns.get(campaign.id).seq
    check("events: pre-allocated seq is used as given", resolved.seq == allocated)
    check("events: seed matches the event's own seq",
          resolved.seed == event_seed(campaign.seed, resolved.seq))
    check("events: no sequence number burned", after == before + 1,
          f"{before} -> {after}")

    # If that number turns out to be taken, the event is renumbered rather than
    # dropped — losing an event is worse than moving it.
    taken = store.campaigns.next_seq(campaign.id)
    _FAKES["dnd_events"].insert_one(
        {"guild_id": guild, "campaign_id": campaign.id, "seq": taken, "kind": "squatter"}
    )
    renumbered = store.events.append(event_kinds.CHECK, seq=taken, seed=999)
    check("events: collided pre-allocation is renumbered, not dropped",
          renumbered is not None and renumbered.seq != taken)
    check("events: renumbered event keeps its resolved seed", renumbered.seed == 999)


# --------------------------------------------------------------------------- #
#  6. Persistence survives a "restart"
# --------------------------------------------------------------------------- #
def test_survives_restart() -> None:
    guild = 4004
    campaign = campaigns_for(guild).create(
        Campaign(guild_id=guild, name="Persistence", ruleset="srd5e", gm_ids=[1])
    )
    store = campaign_store(guild, campaign.id)
    ruleset = rules.get(campaign.ruleset)
    entity = store.entities.create(
        Entity(
            guild_id=guild, campaign_id=campaign.id, kind=KIND_PC, owner_id=42,
            identity=Identity(name="Ondry", pronouns="he/him", role="ferryman"),
            stats=ruleset.blank_sheet({"role": "ranger"}, Random(5)),
        )
    )
    entity.conditions = ["exhausted:1"]
    entity.inventory = [{"item": "green lantern", "qty": 1}]
    store.entities.save(entity)

    # Everything is in the database, so a fresh store is a fresh process.
    reborn = campaign_store(guild, campaign.id)
    loaded = reborn.entities.character_of(42)
    check("restart: character survives", loaded is not None and loaded.name == "Ondry")
    check("restart: pronouns survive", loaded.identity.pronouns == "he/him")
    check("restart: conditions survive", loaded.conditions == ["exhausted:1"])
    check("restart: inventory survives", loaded.inventory[0]["item"] == "green lantern")
    check("restart: stats survive", loaded.stats["abilities"] == entity.stats["abilities"])
    check("restart: campaign seed survives", reborn.campaigns.get(campaign.id).seed == campaign.seed)

    # save() must not let a stale copy reparent a record into another tenant.
    loaded.guild_id, loaded.campaign_id = 9999, "ELSEWHERE"
    reborn.entities.save(loaded)
    still = campaign_store(guild, campaign.id).entities.character_of(42)
    check("restart: save cannot reparent a record", still is not None)


# --------------------------------------------------------------------------- #
#  7. Pronouns are never inferred
# --------------------------------------------------------------------------- #
def test_pronoun_default() -> None:
    check("identity: defaults to they/them", Identity(name="Alex").pronouns == "they/them")
    check("identity: blank falls back", Identity.from_doc({"name": "Alex", "pronouns": ""}).pronouns
          == "they/them")
    check("identity: explicit is kept",
          Identity.from_doc({"name": "Marla", "pronouns": "she/her"}).pronouns == "she/her")


# --------------------------------------------------------------------------- #
#  8. Legacy migration
# --------------------------------------------------------------------------- #
def test_migration() -> None:
    from helpers.dnd import migrate

    # Stand in for the legacy database with the shape the old cog actually
    # wrote — including the stat block that was identical for everybody.
    legacy_stats = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}
    sessions = FakeCollection("sessions")
    characters = FakeCollection("characters")
    actions = FakeCollection("actions")
    sessions.insert_one({
        "session_id": 1700000000, "title": "The Sunken Bell",
        "description": "A bell tolls under the harbour.",
        "players": [11, 22], "history": "- They found the bell.\n- It rang back.",
        "status": "active",
    })
    for name, klass, race, player in (("Ilas", "wizard", "elf", 11), ("Bron", "fighter", "orc", 22)):
        characters.insert_one({
            "session_id": 1700000000, "player_id": player, "name": name,
            "class": klass, "race": race, "stats": dict(legacy_stats), "hp": 10, "ac": 10,
            "equipment": ["rope"], "relationships": {}, "history": "- Did a thing.",
        })
    actions.insert_one({
        "session_id": 1700000000, "player_id": 11,
        "action_description": "I ring it.", "gm_narrative": "It answers.", "summary": "- Rang.",
    })

    migrate.legacy_sessions = sessions
    migrate.legacy_characters = characters
    migrate.legacy_actions = actions

    guild = 5005

    # Dry run must write nothing.
    before = len(_FAKES["dnd_campaigns"].docs)
    planned = migrate.plan(guild)
    check("migrate: dry run counts the work", planned.campaigns == 1 and planned.characters == 2)
    check("migrate: dry run writes nothing", len(_FAKES["dnd_campaigns"].docs) == before)
    check("migrate: dry run is flagged", planned.dry_run is True)

    done = migrate.execute(guild)
    check("migrate: imports the campaign", done.campaigns == 1)
    check("migrate: imports characters", done.characters == 2)

    campaign = campaigns_for(guild).by_legacy_id(1700000000)
    check("migrate: campaign is findable", campaign is not None and campaign.name == "The Sunken Bell")
    check("migrate: players carried across", sorted(campaign.player_ids) == [11, 22])

    store = campaign_store(guild, campaign.id)
    imported = store.entities.characters()
    check("migrate: both characters exist", len(imported) == 2)

    # The headline correction: the identical legacy block is gone, and a wizard
    # and a fighter no longer have the same numbers.
    by_name = {e.name: e for e in imported}
    check("migrate: legacy stat block discarded",
          by_name["Ilas"].stats.get("abilities") != legacy_stats)
    check("migrate: classes now differ",
          by_name["Ilas"].stats["abilities"] != by_name["Bron"].stats["abilities"])
    check("migrate: wizard is smart again", by_name["Ilas"].stats["abilities"]["INT"] == 15)
    check("migrate: equipment carried", by_name["Bron"].inventory[0]["item"] == "rope")
    check("migrate: pronouns defaulted, not guessed",
          all(e.identity.pronouns == "they/them" for e in imported))
    check("migrate: report names the defaults", len(done.defaulted_pronouns) == 2)

    # Prose history became lore events, not fabricated episodic memory.
    kinds = {e.payload.get("kind") for e in store.events.recent(50)}
    check("migrate: premise imported as lore", "premise" in kinds)
    check("migrate: session history imported as lore", "previous_chapters" in kinds)
    check("migrate: actions imported as events", "action" in kinds)

    # Re-running must not duplicate anything.
    again = migrate.execute(guild)
    check("migrate: is idempotent", again.campaigns == 0 and again.skipped == 1)
    check("migrate: no duplicate campaign",
          len([c for c in campaigns_for(guild).list(include_archived=True)]) == 1)

    # The source database is untouched — it is the rollback.
    check("migrate: source left alone",
          len(sessions.docs) == 1 and len(characters.docs) == 2 and len(actions.docs) == 1)


def main() -> int:
    for test in (
        test_dice,
        test_rulesets,
        test_resolution,
        test_scope_rejects_unscoped,
        test_two_servers_no_leakage,
        test_event_log,
        test_survives_restart,
        test_pronoun_default,
        test_migration,
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
