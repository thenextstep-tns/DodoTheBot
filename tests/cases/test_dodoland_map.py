"""DodoLand: where towns go on the map.

Placement is graph-driven, which is the whole reason the map is worth looking
at: clusters are friend groups. These assert the properties that make that true,
plus the ones that stop it being annoying (nothing off the edge, nothing
stacked, nothing that moves between two reads).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from helpers.dodoland import mapview  # noqa: E402


def person(uid, power=100):
    return {"user_id": uid, "power": power, "buildings": {}}


def spread(positions):
    return [(round(p["x"], 2), round(p["y"], 2)) for p in positions.values()]


# --------------------------------------------------------------------------- #
#  A settled town is never moved
# --------------------------------------------------------------------------- #
placed = mapview.place([person(1), person(2)], {}, {1: {"x": 12, "y": 80}})
assert placed[1]["x"] == 12 and placed[1]["y"] == 80 and placed[1]["settled"]
assert not placed[2]["settled"]
print("settling        a chosen spot is kept exactly, and marked as chosen")

# Re-settling moves rather than duplicating: one person, one town.
again = mapview.place([person(1)], {}, {1: {"x": 30, "y": 30}})
assert len(again) == 1 and again[1]["x"] == 30
print("settling        a person has one town, and moving it moves that town")


# --------------------------------------------------------------------------- #
#  Suggestions follow the relation graph
# --------------------------------------------------------------------------- #
# Two clusters: 1-2-3 talk to each other, 10-11 talk to each other, and the two
# groups never interact. The clusters must come out apart.
partners = {1: {2: 50, 3: 40}, 2: {1: 50, 3: 30}, 3: {1: 40, 2: 30},
            10: {11: 60}, 11: {10: 60}}
people = [person(u) for u in (1, 2, 3, 10, 11)]
settled = {1: {"x": 20, "y": 20}, 10: {"x": 80, "y": 80}}
positions = mapview.place(people, partners, settled)


def near(a, b):
    return ((positions[a]["x"] - positions[b]["x"]) ** 2
            + (positions[a]["y"] - positions[b]["y"]) ** 2) ** 0.5


assert near(2, 1) < near(2, 10), "a town landed nearer a stranger than a friend"
assert near(3, 1) < near(3, 10)
assert near(11, 10) < near(11, 1)
print("placement       towns land beside the people they actually talk to")
print("placement       two friend groups come out as two clusters")

# Somebody who talks to nobody still gets a spot, on the fallback spiral.
lonely = mapview.place([person(99)], {}, {})
assert 99 in lonely and mapview.MARGIN <= lonely[99]["x"] <= 100 - mapview.MARGIN
print("placement       somebody who talks to nobody still gets a place to live")


# --------------------------------------------------------------------------- #
#  Nothing off the edge, nothing stacked, nothing that drifts
# --------------------------------------------------------------------------- #
crowd = [person(u, power=u * 3) for u in range(1, 41)]
web = {u: {v: 5 for v in range(1, 41) if v != u} for u in range(1, 41)}
big = mapview.place(crowd, web, {})
for uid, spot in big.items():
    assert mapview.MARGIN <= spot["x"] <= 100 - mapview.MARGIN, spot
    assert mapview.MARGIN <= spot["y"] <= 100 - mapview.MARGIN, spot
print("placement       forty towns all stay on the image")

points = spread(big)
assert len(set(points)) == len(points), "two towns were placed on the same spot"
print("placement       no two towns share a pixel")

assert spread(mapview.place(crowd, web, {})) == points, "the map moved between reads"
print("placement       the same data always produces the same map")


# --------------------------------------------------------------------------- #
#  How a town is drawn
# --------------------------------------------------------------------------- #
# Square-root scaling, so the busiest town does not swallow the map and a
# newcomer stays visible next to somebody with a year's head start.
assert mapview.marker_size(0, 1000) == 1.0
assert mapview.marker_size(1000, 1000) == 3.0
assert mapview.marker_size(250, 1000) == 2.0, mapview.marker_size(250, 1000)
assert mapview.marker_size(10, 1000) > 1.15, "a small town is invisible"
print("drawing         town size is on a root scale, so newcomers stay visible")

rendered = mapview.towns(
    [person(1, 500), person(2, 10)], partners={1: {2: 3}, 2: {1: 3}},
    settled={1: {"x": 40, "y": 40}},
    flourish={1: {"level": 6, "label": "Ascendant", "rank_name": "Godslayer"}},
    names={1: "Nik", 2: "Fox"}, lit={1},
)
by_id = {town["user_id"]: town for town in rendered}
assert by_id[1]["flourish"] == 6 and by_id[1]["rank_name"] == "Godslayer"
assert by_id[2]["flourish"] == 0, "a town got a flourish nobody earned"
print("drawing         flourish comes from trial rank, and only from there")

assert by_id[1]["lit"] and not by_id[2]["lit"]
assert by_id[2]["power"] == 10, "a dim town lost points for being quiet"
print("drawing         a quiet town is dim and loses nothing: no decay anywhere")

# Biggest last, so the largest towns draw on top rather than under.
assert [town["user_id"] for town in rendered] == [2, 1]
print("drawing         towns draw weakest first so the big ones are not buried")

print("PASS")
