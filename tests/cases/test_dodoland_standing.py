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
held = [dict(b, channels={99: 1.0}) if b["key"] == "library" else b for b in defaults]
again = B.suggest_channels(_Guild(), held)
kept = next(b for b in again if b["key"] == "library")
assert kept["channels"] == {99: 1.0}, "suggesting overwrote a hand-tuned building"
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

print("PASS")
