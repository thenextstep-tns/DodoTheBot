"""DodoLand's player front end: your own town, and never anybody else's.

This is the surface ``docs/DODOLAND.md`` §6 held a place for, and the reason a
public map link and a per-player settle page were removed before it. What makes
this one safe is structural rather than careful: **a player handler never reads
a user id from the request.** Whose town it is comes from the signed session and
from nowhere else. Most of this file exists to keep that true.
"""
import asyncio
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import discord  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland.assets import AssetStore  # noqa: E402
from helpers.dodoland.buildings import BuildingStore  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.dodoland.decor import DecorStore  # noqa: E402
from helpers.dodoland.decor import DecorStore  # noqa: E402
from helpers.dodoland.towns import TownStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import player  # noqa: E402

GUILD_ID = 42
LIB, FASH, FORGE = 900, 901, 902
NIK, FOX, ROSA = 1, 2, 3


class Channel(discord.TextChannel):
    category = None

    def __init__(self, cid, name):
        self.id, self.name, self.position = cid, name, 0


class Member:
    bot = False

    def __init__(self, uid, name):
        self.id, self.display_name, self.name = uid, name, name.lower()


class Role:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class Guild:
    name, id = "ESO for Dodos", GUILD_ID
    icon = None

    def __init__(self):
        self.members = [Member(NIK, "Nik"), Member(FOX, "Fox"), Member(ROSA, "Rosa")]
        self.channels = [Channel(LIB, "help"), Channel(FASH, "fashion"),
                         Channel(FORGE, "crafting")]
        self.roles = [Role(70, "Godslayer"), Role(71, "Casual")]

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)


class Visibility:
    enabled = True

    def cog_enabled(self, gid, cog):
        return self.enabled

    def feature_active(self, *args, **kwargs):
        return True


class TrialRanks:
    def get(self, gid):
        return {"ranks": [{"role_id": 71, "min_points": 0, "name": "Casual"},
                          {"role_id": 70, "min_points": 100, "name": "Godslayer"}]}

    def standings(self, gid, limit=100):
        return [{"user_id": NIK, "score": 250}]


class Bot:
    def __init__(self, guild):
        self.dodoland_params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
        self.dodoland = ActivityStore(FakeCollection(), FakeCollection(), self.dodoland_params)
        self.dodoland_buildings = BuildingStore(FakeCollection())
        self.dodoland_assets = AssetStore(FakeCollection())
        self.dodoland_towns = TownStore(FakeCollection())
        self.dodoland_decor = DecorStore(FakeCollection())
        self.visibility = Visibility()
        self.trial_ranks = TrialRanks()
        self._guild = guild
        self.guilds = [guild]

    def get_guild(self, gid):
        return self._guild

    def get_user(self, uid):
        return None


guild = Guild()
bot = Bot(guild)

for _ in range(14):
    bot.dodoland.record(GUILD_ID, NIK, "message", channel_id=LIB)
bot.dodoland.record(GUILD_ID, NIK, "image", channel_id=FASH)
bot.dodoland.record(GUILD_ID, NIK, "mention_given", channel_id=LIB, partner_id=FOX)
bot.dodoland.record(GUILD_ID, FOX, "message", channel_id=LIB)
bot.dodoland.record(GUILD_ID, FOX, "mention_received", channel_id=LIB, partner_id=NIK)

bot.dodoland_buildings.save_buildings(GUILD_ID, [
    {"key": "library", "name": "The Grand Library", "icon": "\U0001F4DA",
     "channels": {LIB: 1.0}, "metric_weights": {},
     "tiers": [{"title": "Desk", "percentile": 20, "floor": 1},
               {"title": "Athenaeum", "percentile": 90, "floor": 500}]},
    {"key": "menagerie", "name": "The Menagerie", "icon": "\U0001F99C",
     "channels": {FASH: 1.0}, "metric_weights": {"image": 2.0},
     "tiers": [{"title": "Paddock", "percentile": 20, "floor": 1}]},
    # A building nobody has so much as started, so the page has to show one.
    {"key": "forge", "name": "The Forge", "icon": "🔥",
     "channels": {FORGE: 1.0}, "metric_weights": {},
     "tiers": [{"title": "Anvil", "percentile": 20, "floor": 1}]},
], guild=guild)


class Request(dict):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.match_info = {"gid": str(GUILD_ID)}


def build(uid=NIK):
    request = Request({"bot": bot})
    request["guild"], request["uid"] = guild, uid
    request["member"], request["scope"] = guild.get_member(uid), "none"
    # The gate is exercised separately; this calls the handler it wraps, which
    # is the part that renders.
    return asyncio.run(player.my_town_page.__wrapped__(request))


# --------------------------------------------------------------------------- #
#  The switches
# --------------------------------------------------------------------------- #
# Everything here is off until a server turns it on. For its whole life DodoLand
# has ranked people who could not see it, so opening that up is a deliberate act
# by a server's owner and never something a deploy does on their behalf.
assert not player.town_pages_on(bot, GUILD_ID), "the player pages default to on"
assert not player.world_page_on(bot, GUILD_ID), "the world map defaults to on"
assert not player.self_settle_on(bot, GUILD_ID), "self-settling defaults to on"
print("switches        the whole player surface is off until a server opens it")

bot.dodoland_params.set(GUILD_ID, "dodoland_town_pages", True)
assert player.town_pages_on(bot, GUILD_ID)
assert not player.world_page_on(bot, GUILD_ID), "the world came on with the town page"
bot.dodoland_params.set(GUILD_ID, "dodoland_world_page", True)
assert player.world_page_on(bot, GUILD_ID)
assert not player.self_settle_on(bot, GUILD_ID), "settling came on with the world"
bot.dodoland_params.set(GUILD_ID, "dodoland_self_settle", True)
assert player.self_settle_on(bot, GUILD_ID)
print("switches        each of the three is its own decision, in order")

# Disabling the cog takes the whole surface with it, the same way it takes the
# listener: a server that has switched DodoLand off has switched it off.
bot.visibility.enabled = False
assert not player.town_pages_on(bot, GUILD_ID)
assert not player.world_page_on(bot, GUILD_ID)
assert not player.self_settle_on(bot, GUILD_ID)
bot.visibility.enabled = True
print("switches        turning the cog off closes the player pages too")


# --------------------------------------------------------------------------- #
#  The page
# --------------------------------------------------------------------------- #
response = build(NIK)
body = response.text
assert response.status == 200
print(f"page            renders, {len(body):,} bytes")

for needle, why in (
    ("The Grand Library", "a building"),
    ("The Menagerie", "a building nothing has been built in yet"),
    ("Desk", "the tier reached"),
    ("Athenaeum", "the tier above, which is the point of the page"),
    ("more to reach", "what the next rung costs"),
    ("#help", "which room the points came from"),
    ("town standing", "the standing tile"),
    ("people reached", "reach, which is what DodoLand counts"),
    ("Flourish", "what a trial rank does to a town"),
    ("Customise", "the part that belongs to its owner"),
):
    assert needle in body, f"the town page is missing {why} ({needle!r})"
print("page            standing, the climb, the next rung and the editor are all there")

# Every building the server has, not only the ones already standing: what is not
# in your town yet and what it would cost is the most useful row on the page.
assert "not yet" in body, "a building nobody has reached is hidden rather than shown"
print("page            unbuilt buildings are shown, with what they would take")

# The artwork is drawn into the page, not fetched. There is exactly one town
# here and it is what the page is for, so a second request for it is a flash of
# nothing for no reason.
assert "<svg viewBox=\"0 0 120 78\"" in body, "the town is not drawn on the page"
assert "/art" not in body, "the town page is fetching artwork it could have drawn"
# ...and it is wrapped in the pair of classes the shared artwork rules key off,
# or the inhabitants stand still and the flourishes never appear.
assert re.search(r'class="art dltown close', body), "the artwork is not marked close-up"
print("page            the town is drawn inline, close-up, with its life running")

# Snowflakes reach JavaScript as strings. As a bare numeric literal a 64-bit id
# loses its last digits and every request 404s. This has caused an outage.
assert f'var GID = "{GUILD_ID}"' in body, "the guild id is not a string in JS"
print("page            the guild id reaches JavaScript as a string")

# A save with no feedback is indistinguishable from no save.
assert 'id="tmsg"' in body and ".cardmsg.bad" in body,     "a refused save has nowhere to say so"
assert "6 * 1024 * 1024" in body, "an oversized picture is not caught before the upload"
print("page            saves report where the button was, oversized pictures early")

# Every animation the page references has to be defined, and every keyframe it
# defines has to be used. Twice a CSS block vanished from a patch and nothing
# noticed: the markup was right and simply nothing moved.
names = set(re.findall(r"animation:\s*([A-Za-z][\w-]*)", body)) - {"none"}
defined = set(re.findall(r"@keyframes\s+([A-Za-z][\w-]*)", body))
assert not (names - defined), f"animations with no keyframes: {sorted(names - defined)}"
assert not (defined - names), f"keyframes nothing uses: {sorted(defined - names)}"
print(f"page            all {len(names)} animations are both defined and used")

# Somebody with nothing counted still gets a page, and a tent rather than an
# error. Being new is not a failure state.
fresh = build(ROSA).text
assert "Nothing has been counted for you yet" in fresh
assert "The Grand Library" in fresh, "a newcomer is not shown what there is to build"
print("page            a newcomer gets a tent and the whole climb, not an error")


# --------------------------------------------------------------------------- #
#  Writes reach only your own town
# --------------------------------------------------------------------------- #
class JsonRequest(Request):
    def __init__(self, app, payload):
        super().__init__(app)
        self._payload = payload

    async def json(self):
        return self._payload


def save(uid, payload):
    request = JsonRequest({"bot": bot}, payload)
    request["guild"], request["uid"] = guild, uid
    return asyncio.run(player.api_my_town.__wrapped__(request))


# A user id in the body is not an error and not a permission failure: it is
# simply not read. There is no id to tamper with, which is the whole design.
save(NIK, {"name": "Beanburg", "blurb": "Mostly soup.",
           "building_names": {"library": "The Drunken Archive"},
           "user_id": FOX, "target": FOX})
assert bot.dodoland_towns.get(GUILD_ID, NIK).get("name") == "Beanburg"
assert not bot.dodoland_towns.get(GUILD_ID, FOX).get("name"),     "a user id in the body reached somebody else's town"
print("writes          an id in the body is ignored; the session decides the town")

player.invalidate(GUILD_ID)
named = build(NIK).text
assert "Beanburg" in named and "The Drunken Archive" in named
assert "The Grand Library" in named, "the building's given name is no longer shown"
print("writes          a renamed town and a renamed building both show, beside the given name")

# Naming is authored and moves no number: the same standing before and after.
before = player.my_town(bot, guild, NIK)["person"]["power"]
save(NIK, {"name": "Beanburg the Second"})
player.invalidate(GUILD_ID)
after = player.my_town(bot, guild, NIK)["person"]["power"]
assert before == after, f"renaming a town moved a number: {before} -> {after}"
print("writes          renaming moves no number at all, which is the whole bargain")

# A refusal has to come back as a message, not a traceback.
too_long = save(NIK, {"name": "x" * 400})
assert too_long.status == 200
import json as _json  # noqa: E402

assert _json.loads(too_long.body.decode())["ok"] is False
print("writes          an over-long name is refused with something a page can show")


# --------------------------------------------------------------------------- #
#  Settling reaches only your own town, and only when allowed
# --------------------------------------------------------------------------- #
def settle(uid, payload):
    request = JsonRequest({"bot": bot}, payload)
    request["guild"], request["uid"] = guild, uid
    return asyncio.run(player.api_my_settle.__wrapped__(request))


settle(NIK, {"x": 30.0, "y": 40.0, "user_id": FOX})
plots = bot.dodoland_buildings.plots(GUILD_ID)
assert NIK in plots and FOX not in plots,     "settling with an id in the body placed somebody else's town"
print("settling        a member places their own town and nobody else's")


# --------------------------------------------------------------------------- #
#  The rules that keep this safe, checked in the source
# --------------------------------------------------------------------------- #
source = pathlib.Path("web/dodoland/player.py").read_text(encoding="utf-8")

# The gate is the only place a request is allowed to name a guild, and nothing
# anywhere is allowed to take a user id off a request.
gate = source[source.index("def require_town"):source.index("def _gone(")]
assert source.count("match_info") == gate.count("match_info") == 1,     "something outside the gate is reading the path"
for forbidden in ('body.get("user_id")', "body.get('user_id')", "query.get",
                  'match_info.get("uid")', 'match_info["uid"]'):
    assert forbidden not in source,     f"a player handler takes an id from the request: {forbidden}"
print("safety          no player handler reads a user id from the request")

# Membership is re-checked per request. A session lasts a week; leaving the
# server has to end the town page now, not next Tuesday.
assert "_member_of" in gate, "membership is not checked on the request"
print("safety          membership is checked per request, not at login")

# A refusal is 404 and never 403, the same bargain require_scope makes: the
# answer must not confirm that a server exists to somebody with no business
# there.
assert "status=403" not in source, "a refusal tells somebody the server exists"
assert "status=404" in source
print("safety          a refusal is 404, so it confirms nothing")

# Every route in the table is gated by one of exactly three things. Read with
# the newlines collapsed: a route whose handler no longer fits on one line is
# still a route, and a line-by-line scan quietly stopped covering it.
routes = pathlib.Path("web/dodoland/__init__.py").read_text(encoding="utf-8")
flat = " ".join(routes.split())
calls = re.findall(r"web\.(?:get|post|delete|put)\(.*?\)\),", flat)
assert len(calls) >= 15, f"only found {len(calls)} routes; the scan is broken"
for call in calls:
    assert ("configure(" in call or "full(" in call
            or "player." in call), f"an unscoped DodoLand route: {call}"
assert "/m/{gid}" not in routes and "/t/{gid}" not in routes,     "a capability-link route came back"
print(f"routes          all {len(calls)} routes are behind a panel scope or the player gate")

# Every player handler in the table actually carries the gate. A handler exposed
# without it would be a public page, which is the exact thing that was removed.
for call in calls:
    if "player." not in call:
        continue
    # Either a handler player.py already wrapped, or one it wraps at the route.
    gated = ("player.require_town(" in call
             or any(hasattr(getattr(player, n, None), "__wrapped__")
                    for n in re.findall(r"player\.(\w+)", call))
             or "player.towns_home" in call)
    assert gated, f"a player route with no gate on it: {call}"
print("routes          every player route carries the gate, none is bare")

print("PASS")
