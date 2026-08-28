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

assert "font-awesome" in map_body, "Font Awesome is not loaded"
assert "dlframe" in map_body and "dlworld" in map_body
print("map             the map has the window, not a panel section")

# A town is drawn from what stands in it, so the buildings' icon classes have to
# reach the page.
assert "fa-book-open" in map_body or "fa-campground" in map_body,     "no building glyphs reached the map"
print("map             a town is drawn from the buildings that stand in it")

# Only what somebody placed appears. Nothing is scattered for you.
assert '"plot": {' in map_body.replace(" ", "") or '"plot":{' in map_body.replace(" ", "")
unplaced = map_body.count('"plot": null') + map_body.count('"plot":null')
assert unplaced >= 1, "every town was given a position without being placed"
print("map             unplaced towns stay off the map until put there")

# Markers must be counter-scaled or they become billboards at high zoom.
assert "--inv" in map_body, "town markers will scale with the map again"
print("map             markers keep their size however far the map is zoomed")

print("PASS")
