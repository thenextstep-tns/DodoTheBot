"""Render the DodoLand panel page end to end against stubs.

A page that parses is not a page that renders. Both of this project's outages
were things a syntax check would have called fine, so this actually builds the
HTML and looks at it.

It also pins the two rules that are easy to break by accident later: DodoLand
must not import anything from the tabletop engine, and it must only ever *read*
from trial ranks.
"""
import asyncio
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import discord  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import flourish, parameters as dodo_params  # noqa: E402
from helpers.dodoland.assets import AssetStore  # noqa: E402
from helpers.dodoland.buildings import BuildingStore  # noqa: E402
from helpers.dodoland.towns import TownStore  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import pages  # noqa: E402

GUILD_ID = 42
LIB, FASH = 900, 901


class Channel(discord.TextChannel):
    category = None

    def __init__(self, cid, name):
        self.id, self.name, self.position = cid, name, 0


class Member:
    bot = False

    def __init__(self, uid, name, handle=None):
        self.id = uid
        self.display_name = name
        self.name = handle or name.lower()


class Role:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class Guild:
    name, id = "ESO for Dodos", GUILD_ID

    def __init__(self):
        self.members = [Member(1, "Nik", "nikladushkin"), Member(2, "Fox", "foxxo"),
                        Member(3, "Rosa", "rosa_eso")]
        self.channels = [Channel(LIB, "help"), Channel(FASH, "fashion")]
        self.roles = [Role(70, "Godslayer"), Role(71, "Casual")]

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)


class Visibility:
    def feature_active(self, *args, **kwargs):
        return True


class TrialRanks:
    """Stands in for the real manager. A read-only surface only, on purpose."""

    def get(self, gid):
        return {"ranks": [{"role_id": 71, "min_points": 0, "name": "Casual"},
                          {"role_id": 70, "min_points": 100, "name": "Godslayer"}]}

    def standings(self, gid, limit=100):
        return [{"user_id": 1, "score": 250}, {"user_id": 2, "score": 5}]


class Bot:
    def __init__(self):
        self.dodoland_params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
        self.dodoland = ActivityStore(FakeCollection(), FakeCollection(), self.dodoland_params)
        self.dodoland_buildings = BuildingStore(FakeCollection())
        self.dodoland_assets = AssetStore(FakeCollection())
        self.dodoland_towns = TownStore(FakeCollection())
        self.visibility = Visibility()
        self.trial_ranks = TrialRanks()
        self._guild = None

    def get_guild(self, gid):
        return self._guild


guild, bot = Guild(), Bot()
bot._guild = guild

# Some real activity so the preview has rows and the thresholds have a shape.
for _ in range(12):
    bot.dodoland.record(GUILD_ID, 1, "message", channel_id=LIB)
bot.dodoland.record(GUILD_ID, 1, "image", channel_id=FASH)
bot.dodoland.record(GUILD_ID, 2, "message", channel_id=LIB)
bot.dodoland.record(GUILD_ID, 2, "mention_received", channel_id=LIB, partner_id=1)

bot.dodoland_buildings.save_buildings(GUILD_ID, [
    {"key": "library", "name": "The Grand Library", "icon": "\U0001F4DA",
     "channels": {LIB: 1.0}, "metric_weights": {},
     "tiers": [{"title": "Desk", "percentile": 20, "floor": 1},
               {"title": "Athenaeum", "percentile": 90, "floor": 5}]},
    {"key": "menagerie", "name": "The Menagerie", "icon": "\U0001F99C",
     "channels": {FASH: 1.0}, "metric_weights": {"image": 2.0},
     "tiers": [{"title": "Paddock", "percentile": 20, "floor": 1}]},
], guild=guild)


class Request(dict):
    def __init__(self, app):
        super().__init__()
        self.app = app


request = Request({"bot": bot})
request["guild"], request["scope"] = guild, "full"
response = asyncio.run(pages.dodoland_page(request))
body = response.text
assert response.status == 200
print(f"page            renders, {len(body):,} bytes")

for needle, why in (
    ("DodoLand", "the heading"),
    ("The Grand Library", "a building name"),
    ("#help", "a channel a building is fed by"),
    ("Athenaeum", "a tier title"),
    ("Town power", "the ranking column"),
    ("Nik", "a member in the preview"),
    ("Named by somebody", "a metric's label"),
    ("dodoland_w_message", "a metric's weight control"),
    ("dodoland_ch_image", "a metric's own channel list"),
    ("dodoland_pcap_mention_received", "a per-person cap control"),
    ("The map", "the map section"),
):
    assert needle in body, f"the page is missing {why} ({needle!r})"
print("page            buildings, tiers, metrics, caps, preview and map all present")

# Every section must have a menu entry. A panel with none renders hidden with
# nothing able to reveal it, which is how the rebuild button went missing: it
# was on the page the whole time and unreachable.
sections = set(re.findall(r'<section class="sidepanel" data-panel="(dl-[a-z]+)"', body))
menu = set(re.findall(r'class="sidenavitem[^"]*" href="#(dl-[a-z]+)"', body))
assert sections, "the page rendered no panels at all"
assert not (sections - menu), f"unreachable panels: {sorted(sections - menu)}"
assert not (menu - sections), f"menu entries pointing at nothing: {sorted(menu - sections)}"
print(f"page            all {len(sections)} panels are reachable from the menu")

# Wide content scrolls inside its own box. Fifteen buildings as fifteen columns
# pushed the entire panel sideways.
assert "dlscroll" in body, "the wide table has no scroll container"
# Scoped to the preview: other sections legitimately have their own tables, and
# what this guards is that the preview never goes back to a column per building.
_preview = body[body.index('data-panel="dl-preview"'):body.index('data-panel="dl-scratch"')]
assert _preview.count("<th>") < 8, "the preview is back to a column per building"
print("page            wide tables scroll inside themselves, not the page")

# Saving with no feedback is indistinguishable from not saving at all. panel.js's
# flash() writes into #status and silently gives up when there is none, which is
# exactly what happened here: every "saved" message went nowhere.
assert 'id="status"' in body, "the page has nowhere to show a save confirmation"
assert "function toast()" in body, "no fallback if the status element goes missing"
print("page            saves have somewhere to report to")

# The shared menu grid assumes its anchor fills the column; left to inherit, the
# items shrank to fit and centred themselves, drawing the menu as a staircase.
assert "sidenav dlnav" in body, "the menu is relying on inherited layout again"
print("page            the side menu is pinned to its own layout")

# Every control the page renders must be a real parameter, or it saves nothing.
keys = set(re.findall(r'data-key="(dodoland_[a-z_]+)"', body))
known = {spec["key"] for spec in dodo_params.DODOLAND_PARAMETERS}
assert keys and keys <= known, f"page renders unknown settings: {keys - known}"
print(f"page            all {len(keys)} rendered controls are real parameters")

# Snowflakes must reach JavaScript as strings; as a bare numeric literal a
# 64-bit id loses its last digits and every request 404s.
assert f'var GID = "{GUILD_ID}"' in body, "the guild id is not a string in JS"
print("page            the guild id reaches JavaScript as a string")

# Flourish comes from the trial ladder: the top rung gets the strongest effect.
glow = flourish.flourish_map(bot, GUILD_ID)
assert glow[1]["level"] == flourish.MAX_LEVEL, glow[1]
assert glow[2]["level"] == 1, glow[2]
assert glow[1]["rank_name"] == "Godslayer"
assert 3 not in glow, "somebody with no trial standing was given a flourish"
print("flourish        the top rung gets the strongest effect, the bottom one gets some")


# A guild with no ladder, or a broken one, means plain towns and never an error.
class NoLadder:
    def get(self, gid):
        return {"ranks": []}

    def standings(self, gid, limit=100):
        return []


class Broken:
    def get(self, gid):
        raise RuntimeError("trial ranks exploded")

    def standings(self, gid, limit=100):
        raise RuntimeError("nope")


bot.trial_ranks = NoLadder()
assert flourish.flourish_map(bot, GUILD_ID) == {}
bot.trial_ranks = Broken()
assert flourish.flourish_map(bot, GUILD_ID) == {}
print("flourish        no ladder and a broken ladder both mean plain towns")

# Flourish never changes a tier. The two axes stay separate.
scorer = pathlib.Path("helpers/dodoland/standing.py").read_text(encoding="utf-8")
assert "flourish" not in scorer, "the scorer has learned about flourish"
print("axes            scoring knows nothing about flourish: rank never buys a tier")

# DodoLand must not depend on the tabletop engine.
sources = (sorted(pathlib.Path("helpers/dodoland").glob("*.py"))
           + sorted(pathlib.Path("web/dodoland").glob("*.py"))
           + [pathlib.Path("cogs/dodoland.py")])
for path in sources:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "dnd" not in stripped, f"{path} imports tabletop: {stripped}"
print("isolation       nothing in DodoLand imports the tabletop engine")

# ...and it must only ever read from trial ranks.
for path in sorted(pathlib.Path("helpers/dodoland").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    for bad in ("trial_ranks.save", "trial_ranks.apply", "trial_standings.update",
                "trial_standings.insert", "save_standing", "trial_ranks.set"):
        assert bad not in text, f"{path} writes to trial ranks via {bad}"
print("isolation       DodoLand only reads from trial ranks, never writes")



# --------------------------------------------------------------------------- #
#  Bots are never anybody's neighbour
# --------------------------------------------------------------------------- #
# Excluding bot authors was never enough. People mention the bot constantly, and
# every one of those was a mention received by it and a mention given by them,
# which put the bot second on the board with five figures of town power.
from helpers.dodoland import backfill as backfill_rules  # noqa: E402
from bson import ObjectId  # noqa: E402
import datetime as _dt  # noqa: E402

_when = _dt.datetime(2025, 5, 1, tzinfo=_dt.timezone.utc)
DODO = 999


def _row(author, text):
    return {"_id": ObjectId.from_datetime(_when), "author": author, "channel": LIB,
            "message": text, "bot": author == DODO}


_plan = backfill_rules.build_plan(
    iter([_row(1, "<@999> pumpkin"), _row(1, "<@999> pumpkin again"),
          _row(DODO, "a bot message here"), _row(1, "hello <@2> there")]),
    params=bot.dodoland_params, guild_id=GUILD_ID, channel_ids=[LIB],
    before="2099-01-01", bot_ids={DODO},
)
scored_users = {uid for uid, _day in _plan.activity}
assert DODO not in scored_users, "the bot scored a town"
assert not any(DODO in (a, b) for _d, a, b in _plan.pairs), "the bot is in the graph"
assert 1 in scored_users and 2 in scored_users, "real people stopped counting"
_nik = _plan.activity[(1, "2025-05-01")]["scored"]
assert _nik.get("mention_given") == 1, f"mentions of the bot still scored: {_nik}"
print("bots            never score, and mentioning one earns the mentioner nothing")

# The name column carries the handle, so two people called Dodo are tellable
# apart and somebody who left is named as such rather than as a bare number.
assert "(@" in body, "names carry no account handle"
print("names           nickname and handle, so duplicates are tellable apart")



# --------------------------------------------------------------------------- #
#  Attaching rooms to a building must actually save
# --------------------------------------------------------------------------- #
# panel.js's bindMultiSelect keeps its selection in a closure and never writes
# data-selected back to the option elements. The collector used to read those
# attributes, so it always saw the server-rendered state and every newly
# attached channel was silently dropped on save. The callback is the only place
# the live selection exists, so it records it on the element and the collector
# reads that.
assert "ms.dataset.chosen = ids.join(',')" in body,     "the channel picker no longer records what was chosen"
assert "picker.dataset.chosen" in body,     "the buildings collector is not reading the live selection"
assert "if (o.dataset.selected === '1') channels[o.dataset.id] = 1;" not in body,     "the collector is back to reading attributes that never change"
print("buildings       attaching rooms records the live selection, and saves it")



# --------------------------------------------------------------------------- #
#  The map has a page of its own
# --------------------------------------------------------------------------- #
from web.dodoland import mappage  # noqa: E402

bot.trial_ranks = TrialRanks()
bot.dodoland_buildings.settle(GUILD_ID, 1, 30.0, 40.0)
map_request = Request({"bot": bot})
map_request["guild"], map_request["scope"] = guild, "full"
map_body = asyncio.run(mappage.map_page(map_request)).text
print(f"map             renders, {len(map_body):,} bytes")

assert "dlframe" in map_body and "dlworld" in map_body
print("map             the map has the window, not a panel section")

# Artwork is fetched when a town comes close, never shipped with the page.
# Sending three hundred settlements and hiding most of them costs the whole
# payload for the handful anybody can see.
assert '"svg"' not in map_body, "the page is shipping pre-rendered town art again"
assert "/art'" in map_body, "nothing fetches a town's artwork"
assert "fa-solid" not in map_body, "the map is back to icon glyphs"
print("map             town art is fetched on approach, not shipped with the page")

# Only what is on screen exists in the DOM at all.
assert "frame.clientWidth + pad" in map_body, "towns off screen are never culled"
print("map             off-screen towns are not in the document")

# Every building kind is drawn differently, and every kind grows with its tier.
from helpers.dodoland import townart  # noqa: E402
seen = {}
for shape in townart.SHAPES:
    small, large = townart.one_svg(shape, 1), townart.one_svg(shape, 6)
    assert large != small, f"{shape} does not change with its tier"
    assert len(large) > len(small), f"{shape} does not grow with its tier"
    seen[shape] = small
assert len(set(seen.values())) == len(seen), "two building kinds draw the same thing"
print(f"art             {len(seen)} building kinds, each distinct, each growing by tier")

# Close-up flourishes exist and are gated, not always on.
assert 'class="fx"' in townart.one_svg("inn", 6), "no close-up detail at the top tier"
assert ".fx { display: none; }" in map_body, "close-up detail is not gated by zoom"
assert "detail_above" in map_body, "no threshold for showing close-up detail"
print("art             high tiers gain flourishes, shown only when zoomed close")

# Only what somebody placed appears. Nothing is scattered for you.
assert '"plot": {' in map_body.replace(" ", "") or '"plot":{' in map_body.replace(" ", "")
unplaced = map_body.count('"plot": null') + map_body.count('"plot":null')
assert unplaced >= 1, "every town was given a position without being placed"
print("map             unplaced towns stay off the map until put there")

# A town is sized in the map's own units and lives inside the scaled element, so
# it shrinks with the coastline. Pinning it to the screen made towns loom larger
# the further you zoomed out until the map was all roofs.
assert "levelOfDetail" in map_body, "towns never collapse to dots"
assert "dot_below" in map_body, "no threshold for collapsing a town to a dot"
assert "(person.w || D.sizes.town_pct) + '%'" in map_body,     "a town is sized absolutely again, so it depends on the map's resolution"
assert '"w":' in map_body, "towns no longer carry their own grown width"
print("map             a town's width grows from the base with its standing")
print("map             towns scale with the map and become dots when far away")

# The controls that decide how the world is drawn belong beside the map, not
# buried in a settings list: a town width means nothing except in relation to
# the map it is drawn on.
assert "dodoland_town_width_pct" in body, "town width cannot be set on the map page"
assert "dodoland_town_growth" in body, "how much a town grows cannot be set"
assert "How the world is drawn" in body
print("map             the world's scale is set per server, beside the map")

# Naming is authored and must never reach the scorer.
scorer = pathlib.Path("helpers/dodoland/standing.py").read_text(encoding="utf-8")
assert "town_rules" not in scorer and "building_names" not in scorer,     "naming a building has become able to move a number"
print("names           naming a town or a building moves no number at all")



# --------------------------------------------------------------------------- #
#  The map must stay vector at every zoom
# --------------------------------------------------------------------------- #
# Anything that promotes the world to its own composited layer, or filters an
# element inside it, makes the browser rasterise once and then scale that
# bitmap. An uploaded SVG map then stops being an SVG the moment anybody zooms,
# and every town blurs with it. This is the whole reason the zoom looked broken.
_world_css = map_body[map_body.index(".dlworld {"):map_body.index(".dlzoom {")]
assert "will-change" not in _world_css,     "the world is promoted to a layer again, so zooming will rasterise the map"
_scaled = map_body[map_body.index(".dltown {"):map_body.index(".dldrawer {")]
# Comments talk about filters on purpose; only real declarations matter.
_rules = re.sub(r"/\*.*?\*/", "", _scaled, flags=re.S)
assert "filter:" not in _rules,     "a filter inside the scaled world will rasterise whatever it touches"
print("map             nothing rasterises the world, so it stays vector when zoomed")

# Zooming out and back in must not leave the map somewhere absurd. The old rule
# took a min of one bound and a max of another that had crossed over.
assert "(w <= fw)" in map_body, "the clamp cannot handle a world smaller than the frame"
print("map             a world smaller than the frame is centred, not pinned")



# --------------------------------------------------------------------------- #
#  A save has to say what happened, where it happened
# --------------------------------------------------------------------------- #
# Refusals used to go to the hint bar in the far corner of the map, behind the
# card and often off screen, so a rejected save was indistinguishable from a
# button that did nothing at all.
assert "dlcardmsg" in map_body, "the card cannot report anything"
assert "cardmsg" in map_body and ".cardmsg.bad" in map_body
print("card            a save reports its result inside the card")

# The commonest refusal is a picture over the limit, so it is caught before the
# upload rather than after it.
assert "6 * 1024 * 1024" in map_body, "an oversized picture is not caught early"
print("card            an oversized picture is refused with its actual size")

# A dot is a town's only visible part when zoomed out, and it has to be
# clickable. Absolutely positioned, it left the town with no height at all.
_dot = map_body[map_body.index(".dldot {"):map_body.index(".dltown.dim")]
assert "position: absolute" not in _dot, "a dot is out of flow, so it cannot be clicked"
assert "margin: 0 auto" in _dot
print("card            a dot keeps a clickable body, so a far town still opens")

# The editor makes the card tall; a Save button nobody can reach does not work.
assert "max-height: calc(100vh" in map_body, "the card can grow past the screen"
print("card            the card scrolls rather than running off the screen")

print("PASS")
