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

    def __init__(self, uid, name):
        self.id, self.name, self.display_name = uid, name, name


class Role:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class Guild:
    name, id = "ESO for Dodos", GUILD_ID

    def __init__(self):
        self.members = [Member(1, "Nik"), Member(2, "Fox"), Member(3, "Rosa")]
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

print("PASS")
