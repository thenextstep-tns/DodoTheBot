"""DodoLand: the runaway horse, turning pieces, and a traveller's look.

The horse is the server's: a kick moves it away from where the click was (a
click on its left sends it off to the right), it stops at the map's edge, it
ends up in a zoo it runs past, and then it rests for hours. Pieces turn round
their foot and keep the turn. A traveller's look is checked, and only the
owner's own cats and dogs can follow them.
"""
import pathlib
import random
import sys
import time
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import decor as decor_rules  # noqa: E402
from helpers.dodoland import pets as pet_rules  # noqa: E402
from helpers.dodoland import towns as town_rules  # noqa: E402
from web.dodoland import horse_api  # noqa: E402

G = 7
PARAMS = {"dodoland_horse_on": True, "dodoland_horse_spread": 0, "dodoland_horse_bolt_min": 8,
          "dodoland_horse_bolt_max": 8, "dodoland_horse_catch": 1.0, "dodoland_zoo_building": "menagerie",
          "dodoland_horse_rest_min_hours": 3, "dodoland_horse_rest_max_hours": 6}


class Config:
    def __init__(self):
        self.doc, self._col = {}, self

    def config(self, gid):
        return self.doc

    def update_one(self, query, change, upsert=False):
        self.doc.update(change["$set"])

    def invalidate(self, gid):
        pass

    def plots(self, gid):
        return {1: {"x": 50, "y": 50}}


zoo_pieces = []
bot = types.SimpleNamespace(
    dodoland_params=types.SimpleNamespace(get=lambda gid, key: PARAMS[key]),
    dodoland_buildings=Config(),
    dodoland_terrain=types.SimpleNamespace(world=lambda gid: {"cells_w": 200, "cells_h": 200}),
    dodoland_tiles=types.SimpleNamespace(tiles=lambda gid: [{"tile_id": "zoo", "requires": {"building": "menagerie"}}]),
    dodoland_decor=types.SimpleNamespace(world=lambda gid: zoo_pieces))

random.seed(3)
state = horse_api.current(bot, G)
assert state["on"], "no horse came out"
bot.dodoland_buildings.doc["horse"] = {"on": True, "x": 50.0, "y": 50.0, "back_at": 0}
# Clicked on its left: it runs right, 8 cells, straight (no spread).
out = horse_api.kick(bot, G, 49.0, 50.0)
assert out["x"] > 50 and abs(out["y"] - 50) < 0.01 and abs((out["x"] - 50) / 100 * 200 - 8) < 0.01, out
out = horse_api.kick(bot, G, out["x"], 51.0)    # clicked below it: up it goes
assert out["y"] < 50, out
print("horse           it bolts away from the click: left of it sends it right, below it up")

bot.dodoland_buildings.doc["horse"] = {"on": True, "x": 99.2, "y": 50.0, "back_at": 0}
out = horse_api.kick(bot, G, 98.0, 50.0)
assert out["x"] < 99.5, f"the horse ran off the map: {out}"
print("horse           it stops at the map's edge")

# A zoo four cells to its right: a kick from the left runs it in.
bot.dodoland_buildings.doc["horse"] = {"on": True, "x": 50.0, "y": 50.0, "back_at": 0}
zoo_pieces.append({"piece_id": "z1", "asset_id": "zoo", "town": "1", "x": 52.0, "y": 50.0, "scale": 1.0})
out = horse_api.kick(bot, G, 49.0, 50.0)
assert out.get("caught") == {"zoo": "z1", "owner": "1"} and not out["on"], out
rest = bot.dodoland_buildings.doc["horse"]["back_at"] - time.time()
assert 3 * 3600 - 5 <= rest <= 6 * 3600, f"it comes back after {rest / 3600:.1f} hours"
assert not horse_api.current(bot, G)["on"] and horse_api.kick(bot, G, 0, 0) == {"on": False}
print("horse           run past a zoo it ends up in it, then rests for hours (no farming)")

# A town's horse, chased by the page into a zoo: checked, paid once, then the zoos rest.
bot.dodoland_buildings.doc["horse"] = {"on": False, "back_at": time.time() + 3600}
assert horse_api.catch(bot, G, "z1", {"x": 50, "y": 50}, {"x": 51, "y": 80}).get("refused") == "missed"
assert horse_api.catch(bot, G, "z1", {"x": 10, "y": 50}, {"x": 52, "y": 50}).get("refused") == "missed",     "a run longer than any bolt was paid"
assert horse_api.catch(bot, G, "nope", {"x": 50, "y": 50}, {"x": 52, "y": 50}).get("refused") == "no zoo"
got = horse_api.catch(bot, G, "z1", {"x": 49, "y": 50}, {"x": 52, "y": 50})
assert got.get("caught") == {"zoo": "z1", "owner": "1"}, got
assert horse_api.catch(bot, G, "z1", {"x": 49, "y": 50}, {"x": 52, "y": 50}).get("refused") == "full",     "the zoos took a second horse straight away"
print("herding         a town's horse run past a zoo is paid once; a run that misses or is too long is not")

# Turning a piece.
store = decor_rules.DecorStore(FakeCollection())
piece = store.place(G, scope=decor_rules.SCOPE_WORLD, asset_id="a", x=10, y=10)
store.move(G, piece["piece_id"], rot=-30)
assert store.piece(G, piece["piece_id"])["rot"] == 330.0
store.move(G, piece["piece_id"], x=11)
assert store.piece(G, piece["piece_id"])["rot"] == 330.0, "moving a piece lost its turn"
print("turning         a piece keeps its turn (degrees, any way round)")

# A traveller's look.
look = town_rules.clean_look({"head": "#AABBCC", "body": "", "horse": "#112233",
                              "pets": [{"k": "cat", "n": "Tom"}, {"k": "fish", "n": "Nemo"}]})
assert look == {"head": "#aabbcc", "horse": "#112233", "pets": [{"k": "cat", "n": "Tom"}]}, look
try:
    town_rules.clean_look({"head": "red"})
    raise AssertionError("a bad colour was kept")
except town_rules.TownError:
    pass
cats, dogs = FakeCollection(), FakeCollection()
for name in ("Tom", "Kit", "Ash", "Moe"):
    cats.insert_one({"owner": "5", "name": name})
cats.insert_one({"owner": "6", "name": "Not yours"})
dogs.insert_one({"owner": "5", "name": "Rex"})
pet_rules._collection = lambda kind: cats if kind == "cat" else dogs
kept = pet_rules.owned("5", [{"k": "cat", "n": n} for n in ("Tom", "Kit", "Ash", "Moe")] +
                       [{"k": "cat", "n": "Not yours"}, {"k": "dog", "n": "Rex"}])
assert kept == [{"k": "cat", "n": "Tom"}, {"k": "cat", "n": "Kit"}, {"k": "cat", "n": "Ash"},
                {"k": "dog", "n": "Rex"}], kept
print("look            colours checked; only the owner's own pets follow, three of each at most")

looks = pathlib.Path("web/dodoland/look_api.py").read_text(encoding="utf-8")
mine = looks[looks.index("async def api_my_pets"):looks.index("async def api_town_pets")]
assert 'request["uid"]' in mine and "user_id" not in mine, "a member's pet search reads a user id from the request"
print("look            a member searches only their own pets")

print("PASS")
