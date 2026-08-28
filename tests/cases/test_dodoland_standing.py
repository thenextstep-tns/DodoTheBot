"""DodoLand P1: buildings, derived thresholds, and town power.

The thresholds are the part worth guarding. Authored numbers fail visibly (a
tier nobody reaches); derived ones fail invisibly (a tier everybody reaches on a
quiet server), so every property that keeps them honest is asserted here.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import buildings as B  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland import standing  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

GUILD = 111
LIBRARY_CH, FASHION_CH, OFFTOPIC_CH = 900, 901, 902


def fresh():
    params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
    return ActivityStore(FakeCollection(), FakeCollection(), params), params


# --------------------------------------------------------------------------- #
#  Validation refuses what would break a page
# --------------------------------------------------------------------------- #
for bad, why in (
    ({"name": "", "tiers": []}, "an empty name"),
    ({"name": "X", "channels": {"nope": 1}}, "a non-numeric channel"),
    ({"name": "X", "channels": {5: 99}}, "a weight above the maximum"),
    ({"name": "X", "tiers": [{"title": "A", "percentile": 500}]}, "a percentile over 100"),
    ({"name": "X", "tiers": [{"title": "A", "percentile": 1},
                             {"title": "a", "percentile": 2}]}, "two tiers with one title"),
):
    try:
        B.validate_building(bad)
        raise AssertionError(f"accepted {why}")
    except B.DodoLandError:
        pass
print("validation      empty names, bad channels, silly percentiles and dupes refused")

try:
    B.validate_buildings([{"name": "Hall"}, {"name": "Hall"}])
    raise AssertionError("accepted two buildings with the same key")
except B.DodoLandError:
    pass
print("validation      two buildings cannot share a key")

# Tiers come back sorted easiest-first however they were entered.
tiers = B.validate_tiers([{"title": "Hard", "percentile": 90},
                          {"title": "Easy", "percentile": 10}])
assert [t["title"] for t in tiers] == ["Easy", "Hard"]
print("validation      tiers are stored in ladder order regardless of entry order")

# Defaults exist, are valid, and attach to no channels: a building that silently
# counted every room would be a building nobody configured.
defaults = B.validate_buildings(B.default_buildings())
assert len(defaults) >= 12, "a town needs more than a handful of buildings"
assert all(not b["channels"] for b in defaults), "a default building claimed a room"
assert all(len(b["tiers"]) == 6 for b in defaults)
assert all(b["hints"] for b in defaults), "a building has no words to match channels by"
print(f"defaults        {len(defaults)} buildings, six tiers each, no channels assumed")

# Suggestion is a starting guess: it fills empty buildings, never overwrites a
# choice, and never hands one room to two buildings.
class _Chan:
    def __init__(self, cid, name):
        self.id, self.name = cid, name


class _Guild:
    channels = [_Chan(1, "eso-help"), _Chan(2, "trials-lfg"), _Chan(3, "pet-pics"),
                _Chan(4, "general-chat")]


picked = B.suggest_channels(_Guild(), defaults)
attached = [cid for b in picked for cid in b["channels"]]
assert len(attached) == len(set(attached)), "one room was given to two buildings"
assert attached, "the suggester matched nothing at all"
held = [dict(b, channels={"99": 1.0}) if b["key"] == "library" else b for b in defaults]
again = B.suggest_channels(_Guild(), held)
kept = next(b for b in again if b["key"] == "library")
assert kept["channels"] == {"99": 1.0}, "suggesting overwrote a hand-tuned building"
print("defaults        suggestion fills empty buildings and never undoes a choice")


# --------------------------------------------------------------------------- #
#  Derived thresholds
# --------------------------------------------------------------------------- #
dist = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
assert standing.percentile_of(dist, 100) == 100
assert standing.percentile_of(dist, 50) == 50
assert standing.percentile_of([], 50) == 0
# Zeros are not part of the distribution: people who have not started should not
# drag every threshold to nothing.
assert standing.percentile_of([0, 0, 0, 100], 50) == 100
print("thresholds      percentiles read the scoring population, not the roster")

# On a young server the floor wins, so "top 2%" is not reachable with one message.
ladder = [{"title": "Foundations", "percentile": 20, "floor": 25},
          {"title": "Legendary", "percentile": 98, "floor": 5000}]
young = standing.resolve_tiers(ladder, [3, 5])
assert young[0]["threshold"] == 25 and young[0]["source"] == "floor"
assert young[1]["threshold"] == 5000
print("thresholds      the floor protects a young server from cheap top tiers")

# On a busy server the distribution wins and the ladder self-calibrates.
busy = standing.resolve_tiers(ladder, list(range(100, 20000, 100)))
assert busy[1]["threshold"] > 5000 and busy[1]["source"] == "percentile"
print("thresholds      on a busy server the live distribution takes over")

# Thresholds never decrease: a floor must not make an early rung harder than a
# later one, which would leave a tier that cannot be the highest reached.
weird = standing.resolve_tiers(
    [{"title": "A", "percentile": 10, "floor": 900}, {"title": "B", "percentile": 90, "floor": 0}],
    [100, 200, 300])
assert weird[0]["threshold"] <= weird[1]["threshold"]
print("thresholds      the ladder can never step backwards")

assert standing.tier_reached(0, busy) is None
assert standing.tier_reached(10 ** 9, busy) == 1
print("thresholds      below tier one is None, not tier zero")


# --------------------------------------------------------------------------- #
#  Scoring: a building is a place, so it scores from channels
# --------------------------------------------------------------------------- #
store, params = fresh()
NIK, FOX = 1, 2
for _ in range(5):
    store.record(GUILD, NIK, "message", channel_id=LIBRARY_CH)
store.record(GUILD, NIK, "image", channel_id=FASHION_CH)
for _ in range(3):
    store.record(GUILD, NIK, "message", channel_id=OFFTOPIC_CH)
store.record(GUILD, FOX, "message", channel_id=LIBRARY_CH)

library = {"key": "library", "name": "Library", "icon": "", "metric_weights": {},
           "channels": {LIBRARY_CH: 1.0},
           "tiers": [{"title": "Desk", "percentile": 10, "floor": 1}]}
menagerie = {"key": "menagerie", "name": "Menagerie", "icon": "",
             "metric_weights": {"image": 2.0}, "channels": {FASHION_CH: 1.0},
             "tiers": [{"title": "Paddock", "percentile": 10, "floor": 1}]}

result = standing.guild_standings(store, params, GUILD, [library, menagerie])
nik = result["people"][NIK]

# 5 messages x weight 1 in the library's only channel.
assert nik["buildings"]["library"]["points"] == 5, nik["buildings"]["library"]
# The off-topic channel feeds no building, so those three messages are not lost,
# they simply build nothing.
assert OFFTOPIC_CH not in nik["buildings"]["library"]["by_channel"]
# 1 image x weight 6 x the building's own 2.0 emphasis.
assert nik["buildings"]["menagerie"]["points"] == 12, nik["buildings"]["menagerie"]
print("scoring         channels decide which building a room builds")
print("scoring         a building's own emphasis multiplies without touching others")

# The breakdown adds up to the total, which is what makes the number arguable.
assert sum(nik["buildings"]["library"]["by_metric"].values()) == nik["buildings"]["library"]["points"]
print("scoring         every score carries the breakdown that produced it")

# Town power is buildings plus people reached, and places are ranked on it.
assert nik["power"] == 5 + 12 + nik["reach_points"]
assert nik["place"] == 1 and result["people"][FOX]["place"] == 2
print("scoring         town power is buildings plus reach, and it orders the board")

# Reach is channel-agnostic, so it belongs to the town and not to any building.
store2, params2 = fresh()
store2.record(GUILD, NIK, "mention_received", channel_id=LIBRARY_CH, partner_id=FOX)
res2 = standing.guild_standings(store2, params2, GUILD, [library])
assert res2["people"][NIK]["reached"] == 1 and res2["people"][FOX]["reached"] == 1
assert res2["people"][FOX]["power"] > 0, "a person with only ties still has a town"
print("scoring         reach sits on the town, and ties alone still make one")



# --------------------------------------------------------------------------- #
#  The suggest endpoint: the one click that makes any of this score
# --------------------------------------------------------------------------- #
import asyncio  # noqa: E402

from helpers.dodoland.buildings import BuildingStore  # noqa: E402
from web.dodoland import api as dodoland_api  # noqa: E402


class _Ch:
    def __init__(self, cid, name):
        self.id, self.name = cid, name


class _G:
    id, name = GUILD, "G"
    channels = [_Ch(901, "eso-help"), _Ch(902, "trials-lfg"), _Ch(903, "pet-pics")]

    def get_member(self, uid):
        return None


class _Audit:
    def record(self, *a, **k):
        pass


class _Bot:
    def __init__(self):
        self.dodoland_buildings = BuildingStore(FakeCollection())
        self.audit_log = self.audit_notify = _Audit()

    def get_guild(self, gid):
        return _G()


class _Req(dict):
    def __init__(self, app, body):
        super().__init__()
        self.app, self._b = app, body
        self.match_info = {"gid": str(GUILD)}

    async def json(self):
        return self._b


_bot = _Bot()
_req = _Req({"bot": _bot}, {})
_req["guild"], _req["scope"], _req["uid"] = _G(), "owner", 1

# Nothing scores until rooms are attached, so this endpoint is the one click
# that turns a configured server into a scoring one. It must actually persist.
assert not any(b["channels"] for b in _bot.dodoland_buildings.buildings(GUILD))
_resp = asyncio.run(dodoland_api.api_dodoland_suggest(_req))
assert _resp.status == 200, _resp.text
assert '"ok": true' in _resp.text, _resp.text
saved = _bot.dodoland_buildings.buildings(GUILD)
attached = {cid for b in saved for cid in b["channels"]}
assert attached == {'901', '902', '903'}, attached
assert _bot.dodoland_buildings.is_configured(GUILD), "suggesting did not persist"
print("suggest         one click attaches this server's real rooms, and it sticks")

# Running it again must not disturb what it already did.
asyncio.run(dodoland_api.api_dodoland_suggest(_req))
again = {cid for b in _bot.dodoland_buildings.buildings(GUILD) for cid in b["channels"]}
assert again == attached, "a second suggest moved rooms around"
print("suggest         pressing it twice changes nothing")



# --------------------------------------------------------------------------- #
#  Channels are offered in the order Discord draws them
# --------------------------------------------------------------------------- #
import discord  # noqa: E402

from web.dodoland import buildings_ui  # noqa: E402


class _Cat:
    def __init__(self, cid, name, position):
        self.id, self.name, self.position = cid, name, position


class _Room(discord.TextChannel):
    def __init__(self, cid, name, category, position):
        self.id, self.name, self.position = cid, name, position
        self._cat = category

    @property
    def category(self):
        return self._cat


_info, _admin, _social = _Cat(1, "Information", 0), _Cat(2, "Admin", 1), _Cat(3, "Social", 2)


class _Server:
    id = GUILD
    channels = [_Room(30, "general", _social, 1), _Room(10, "announcements", _info, 0),
                _Room(21, "moderators", _admin, 1), _Room(20, "raid-leading", _admin, 0),
                _Room(31, "big-walk", _social, 0), _Room(11, "wayshrine", _info, 1)]

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)


# With sixty-odd channels the only ordering anybody knows is their own sidebar.
order = [c.id for c in buildings_ui.ordered_channels(_Server())]
assert order == [10, 11, 20, 21, 31, 30], order
print("channels        offered in Discord's own category and channel order")

assert buildings_ui.channel_label(_Server().channels[0]) == "Social / general"
print("channels        labelled by category, so searching one finds its rooms")

# A hint may match a whole category, which is how servers are really organised.
picked = B.suggest_channels(_Server(), B.validate_buildings(B.default_buildings()))
tavern = next(b for b in picked if b["key"] == "tavern")
assert set(tavern["channels"]) == {"30", "31"}, tavern["channels"]
print("channels        a hint can claim a whole category, not one room at a time")



# --------------------------------------------------------------------------- #
#  A forum's posts are separate rooms; ordinary threads are not
# --------------------------------------------------------------------------- #
class _Forum(discord.ForumChannel):
    def __init__(self, cid, name, category, position):
        self.id, self.name, self.position = cid, name, position
        self._cat = category

    @property
    def category(self):
        return self._cat


class _Post:
    """A forum post. Only the attributes the picker and labeller read."""

    def __init__(self, tid, name, parent):
        self.id, self.name, self.parent = tid, name, parent


_feed = _Forum(40, "personal-feed", _social, 2)
_food = _Post(401, "Salvalicious food pics", _feed)
_safe = _Post(402, "Safe Space", _feed)


class _WithForum(_Server):
    channels = _Server.channels + [_feed]
    threads = [_safe, _food]


ids = [c.id for c in buildings_ui.ordered_channels(_WithForum())]
assert 40 in ids, "the forum itself is missing"
assert ids.index(401) > ids.index(40) and ids.index(402) > ids.index(40), ids
print("forums          each forum's posts are listed as rooms, under their forum")

label = buildings_ui.channel_label(_food)
assert label == "Social / personal-feed / Salvalicious food pics", label
print("forums          a post is labelled by its category and its forum")

# The listener charges a forum post to itself and an ordinary thread to its
# parent. Collapsing forum posts made the food feed, the safe space and the
# selfies thread one indistinguishable channel.
src = pathlib.Path("cogs/dodoland.py").read_text(encoding="utf-8")
assert "isinstance(parent, discord.ForumChannel)" in src,     "forum posts are being collapsed into their forum again"
print("forums          a post is its own room; a thread in a channel is not")

print("PASS")
