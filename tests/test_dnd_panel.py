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
from helpers.dnd import tuning as tuning_registry  # noqa: E402
from helpers.dnd import interactions as interaction_registry  # noqa: E402
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
    # A real-shaped snowflake, not a small integer. The id used to be 7777,
    # which survives a trip through JavaScript intact — so a page embedding it
    # as a numeric literal looked fine here and 404'd against every real guild.
    id = 806174526383325225
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


def test_script_wiring() -> None:
    """The panel script's two silent killers, both of which shipped.

    Neither is visible in rendered HTML, which is all the other checks look at,
    and both made every control on the page do nothing at all:

    * a snowflake embedded as a **numeric literal** loses precision above 2^53,
      so the request goes to a guild that does not exist and 404s at the scope
      check;
    * the status element emitted *after* the script means ``getElementById``
      returns null, so nothing can ever report the failure.
    """
    import re

    guild = FakeGuild()
    script = pages._dnd_script(guild.id, "abc123")

    check("script: the guild id is a string, not a numeric literal",
          f'const gid = "{guild.id}"' in script,
          "a bare 64-bit literal silently becomes a different id")

    # Belt and braces: no unquoted integer anywhere in the script may exceed
    # JavaScript's safe range, whoever writes the next line of it. Comments are
    # stripped first — the one explaining this trap quotes the offending id.
    code = re.sub(r"//[^\n]*", "", script)
    unsafe = [
        found for found in re.findall(r"(?<![\"'\w.])(\d{16,})(?![\"'\w])", code)
        if int(found) > 2**53
    ]
    check("script: no unsafe integer literals at all", not unsafe, str(unsafe[:3]))

    body = script.find("</script>")
    check("script: the status element exists before the script runs",
          0 <= script.find('id="status"') < body,
          "emitted after the script, so getElementById returns null")

    # A third one, found by typing into the panel rather than by reading it.
    # A checkbox's .value is "on" whether ticked or not, and a number input that
    # cannot parse what was typed reports "" — which this API reads as *clear
    # the override*. Posting el.value directly therefore made every switch
    # permanently on, and turned a typo into a silent reset to inherited.
    # Scoped to the tuning endpoints on purpose: they are the ones where "" is
    # *meaningful*. The trait editor posts a raw value to an endpoint that
    # rejects a non-number outright, which is a worse message and not a silent
    # loss.
    tune_posts = [line for line in script.splitlines() if "dnd/tune" in line]
    check("script: both tuning endpoints are reachable from the page",
          len(tune_posts) == 4, str(len(tune_posts)))
    check("script: tuning controls are never posted as a raw .value",
          all("el.value" not in line for line in script.splitlines()
              if "key: el.dataset.key" in line),
          "a checkbox posts \"on\" and a bad number posts \"\" — which means clear")
    check("script: unparseable numbers are refused rather than sent",
          "el.validity.badInput" in script and "unusable(el)" in script)
    check("script: a switch posts its state",
          'el.checked ? "1" : "0"' in script)


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

    # --- what people do to each other, and what it is worth ---------------- #
    kinds_html = pages._interactions_section(
        guild, campaign, minds.tuning_for(store, campaign), True
    )
    check("kinds: the section renders", "How big it is" in kinds_html)
    check("kinds: every shipped kind has a card",
          all(f'data-key="{key}"' in kinds_html
              for key in interaction_registry.built_in()))
    check("kinds: a delta slider spans the negative half",
          'min="-1" max="1" data-axis="affinity"' in kinds_html,
          detail="an act that costs trust is not an act that fails to build it")
    check("kinds: debt gets a whole-number box, not a slider",
          'data-axis="debt"' in kinds_html and 'step="1"' in kinds_html)
    check("kinds: a gated kind says which need is holding it",
          "has not switched on" in kinds_html,
          detail="sliders on an act nothing can record read as broken controls")
    check("kinds: a player sees none of it",
          pages._interactions_section(guild, campaign,
                                      minds.tuning_for(store, campaign), False) == "")

    # Every group needs an icon, or it renders with a bare heading in the panel
    # and a bullet in the side menu while every other group has a face. Cosmetic,
    # and invisible to every other assertion here — `Remembering` shipped without
    # one and it took clicking the page to notice.
    for group in tuning_registry.GROUPS:
        check(f"tuning: the '{group}' group has an icon",
              bool(pages._GROUP_EMOJI.get(group)),
              detail="add it to web/dnd/pages.py::_GROUP_EMOJI")

    # A campaign override shows as the campaign's own.
    campaign.settings = {"tuning": {"memory_decay_rate": 0}}
    overridden = pages._tuning_section(
        minds.tuning_for(store, campaign), campaign, True
    )
    check("tuning: an override is badged as yours", "yours" in overridden)


def main() -> int:
    test_pages()
    test_inspector()
    test_script_wiring()
    test_tuning_section()
    for line in PASSED:
        print(f"  ok   {line}")
    for line in FAILED:
        print(f"  FAIL {line}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
