"""
Tabletop panel rendering — a smoke test, not a UI test.

The panel pages are f-string HTML, so a typo is a runtime error on a page nobody
visits until a GM does. This renders both pages against the in-memory store and
asserts the two things that would be actively harmful if wrong:

* a **secret fact never appears in a player's HTML** — hiding it with CSS would
  still have shipped it to the browser;
* a player never gets the **engine settings** controls.

It does not check that anything looks right. That is the user's job, by design.

Run with ``py tests/test_dnd_panel.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fake_mongo import FakeCollection  # noqa: E402

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

from helpers import panel_access  # noqa: E402
from helpers.dnd.store import campaign_store, campaigns_for  # noqa: E402
from helpers.dnd.store import beliefs as beliefs_module  # noqa: E402
from helpers.dnd.store import campaigns as campaigns_module  # noqa: E402
from helpers.dnd.store import canon as canon_module  # noqa: E402
from helpers.dnd.store import entities as entities_module  # noqa: E402
from helpers.dnd.store import events as events_module  # noqa: E402
from helpers.dnd.store import knowledge as knowledge_module  # noqa: E402
from helpers.dnd.store import scenes as scenes_module  # noqa: E402
from helpers.dnd.world.campaign import Campaign  # noqa: E402
from helpers.dnd.world.entity import KIND_PC, Entity, Identity  # noqa: E402
from helpers.dnd.world.knowledge import Fact  # noqa: E402
from helpers.dnd.store import memories as memories_module  # noqa: E402
from helpers.dnd.store import relations as relations_module  # noqa: E402
from helpers.dnd import minds  # noqa: E402
from helpers.dnd import parameters as dnd_parameters  # noqa: E402
from web.dnd import access, pages  # noqa: E402

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

dnd_parameters.TUNING_COLLECTION = FakeCollection("DndTuning")

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


class FakeMember:
    def __init__(self, uid, name):
        self.id, self.display_name = uid, name


class FakeGuild:
    id = 7777
    name = "Test Server"

    def get_member(self, uid):
        return FakeMember(uid, f"Member{uid}")


class FakeVisibility:
    def cog_enabled(self, gid, cog):
        return True


class FakeBot:
    extensions = {"cogs.dnd.cog": 1}
    visibility = FakeVisibility()


SECRET_TEXT = "the harbourmaster is a Compact plant"


def build():
    guild = FakeGuild()
    campaign = campaigns_for(guild.id).create(
        Campaign(guild_id=guild.id, name="The Ashen Compact", ruleset="srd5e", gm_ids=[1],
                 player_ids=[2])
    )
    store = campaign_store(guild.id, campaign.id)
    store.entities.create(Entity(
        guild_id=guild.id, campaign_id=campaign.id, kind=KIND_PC, owner_id=2,
        identity=Identity(name="Kesh", role="rogue"),
        stats={"abilities": {"STR": 8, "DEX": 15, "CON": 13, "INT": 14, "WIS": 10, "CHA": 12},
               "hp": {"current": 9, "max": 9}, "ac": 12, "proficiency": 2},
    ))
    store.knowledge.add(Fact(kind="lore", title="The harbour", text="Smells of tar."))
    store.knowledge.add(Fact(kind="lore", title="The plant", text=SECRET_TEXT, secret=True))
    store.canon.propose(kind="person", title="Ondry", text="A ferryman.", confidence=0.7)
    return guild, campaign, store


def test_pages() -> None:
    guild, campaign, store = build()
    bot = FakeBot()

    # --- campaign list, as an admin and as a player ----------------------- #
    admin_html = pages.campaigns_html(bot, guild, panel_access.SCOPE_FULL, 1)
    player_html = pages.campaigns_html(bot, guild, panel_access.SCOPE_STATS, 2)
    check("panel: campaign list renders", "The Ashen Compact" in admin_html)
    check("panel: admin sees engine settings", "Engine" in admin_html)
    check("panel: player does not", "Engine" not in player_html)
    check("panel: player still sees their campaign", "The Ashen Compact" in player_html)
    check("panel: engine settings expose the cog switch",
          'data-cog="dnd"' in admin_html)
    check("panel: engine settings expose the params",
          'data-key="dnd_default_ruleset"' in admin_html)

    # Someone in the guild but in no campaign sees nothing of it.
    outsider = pages.campaigns_html(bot, guild, panel_access.SCOPE_STATS, 999)
    check("panel: an outsider sees no campaigns", "The Ashen Compact" not in outsider)

    # --- one campaign, as GM and as player -------------------------------- #
    gm_page = pages.campaign_html(bot, guild, campaign, access.CAMPAIGN_GM)
    player_page = pages.campaign_html(bot, guild, campaign, access.CAMPAIGN_PLAYER)

    check("panel: campaign page renders", "Kesh" in gm_page)
    check("panel: knowledge section renders", "World knowledge" in gm_page)
    check("panel: public lore shown to both",
          "The harbour" in gm_page and "The harbour" in player_page)

    # The important one: a secret must not be in the bytes sent to a player.
    check("panel: GM sees the secret", SECRET_TEXT in gm_page)
    check("panel: SECRET IS ABSENT from the player's HTML", SECRET_TEXT not in player_page)
    check("panel: secret title absent too", "The plant" not in player_page)

    check("panel: GM gets the add-fact form", 'id="lore-add"' in gm_page)
    check("panel: player does not", 'id="lore-add"' not in player_page)

    check("panel: GM sees the canon queue", "Proposed canon" in gm_page)
    check("panel: player does not", "Proposed canon" not in player_page)
    check("panel: canon proposal is listed", "Ondry" in gm_page)

    check("panel: script is scoped to the campaign", str(campaign.id) in gm_page)
    check("panel: SRD attribution is shown", "System Reference Document" in gm_page)


def test_inspector() -> None:
    """The entity inspector — the page that shows this is a simulation."""
    from random import Random

    guild, campaign, store = build()
    marla = minds.spawn_npc(
        store, name="Marla Venn", role="harbourmaster", culture="tidewater",
        world_time=0, rng=Random(7),
    )
    minds.remember(
        store, marla, "Ondry never paid what he owed at the north dock",
        world_time=0, rng=Random(1), valence=-0.6, details=["a green lantern"],
    )
    minds.advance(store, campaign, 900, Random(3))

    html = pages._inspector_html(FakeBot(), guild, campaign, marla, store)
    check("inspector: renders", "Marla Venn" in html)
    check("inspector: shows disposition", "Retention" in html and "Warmth" in html)
    check("inspector: shows the body", "Hunger" in html and "urgency" in html)
    check("inspector: shows memory", "Memory" in html)
    check("inspector: explains why memories stick",
          "holds onto" in html or "nothing in their values" in html)
    check("inspector: shows both relationship directions",
          "Feelings toward others" in html and "How others feel about them" in html)
    check("inspector: shows beliefs", "Beliefs" in html)

    # The inspector must be read-only — looking must not rewrite a memory.
    before = [(m.id, m.recall_count, m.salience) for m in store.memories.for_entity(marla.id)]
    pages._inspector_html(FakeBot(), guild, campaign, marla, store)
    after = [(m.id, m.recall_count, m.salience) for m in store.memories.for_entity(marla.id)]
    check("inspector: LOOKING DOES NOT CHANGE THE MIND", before == after)


def test_tuning_section() -> None:
    guild, campaign, store = build()
    tuning = minds.tuning_for(store, campaign)

    gm_html = pages._tuning_section(tuning, campaign, True)
    player_html = pages._tuning_section(tuning, campaign, False)
    check("tuning: GM sees the settings", "Forgetting speed" in gm_html)
    check("tuning: player sees none", player_html == "")
    check("tuning: the off switch is explained",
          "switches forgetting off entirely" in gm_html)
    check("tuning: each setting shows where it came from",
          "from default" in gm_html or "yours" in gm_html)
    check("tuning: ranges are shown", 'min="0.0"' in gm_html or "0.0–5.0" in gm_html)

    # --- the server layer, on the Tabletop index --------------------------- #
    server_html = pages._server_tuning_section(guild)
    check("tuning: server layer renders", "Simulation defaults" in server_html)
    check("tuning: server controls are distinct from campaign ones",
          'class="dndtune-server"' in server_html)
    check("tuning: server layer explains inheritance",
          "every campaign on this server" in server_html)

    admin_page = pages.campaigns_html(FakeBot(), guild, panel_access.SCOPE_FULL, 1)
    player_page = pages.campaigns_html(FakeBot(), guild, panel_access.SCOPE_STATS, 2)
    check("tuning: an admin gets the server defaults", "Simulation defaults" in admin_page)
    check("tuning: a player does not", "Simulation defaults" not in player_page)

    # A campaign override shows as the campaign's own.
    campaign.settings = {"tuning": {"memory_decay_rate": 0}}
    overridden = pages._tuning_section(
        minds.tuning_for(store, campaign), campaign, True
    )
    check("tuning: an override is badged as yours", "yours" in overridden)


def main() -> int:
    test_pages()
    test_inspector()
    test_tuning_section()
    for line in PASSED:
        print(f"  ok   {line}")
    for line in FAILED:
        print(f"  FAIL {line}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
