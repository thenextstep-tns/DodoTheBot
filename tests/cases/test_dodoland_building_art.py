"""DodoLand: uploaded building pictures sit beside the generated ones.

Each tier's painted picture is kept on its tile apart from the generated
drawing, so rebuilding the drawings never drops it, and the server's Building
artwork setting picks which the map draws. Uploaded pictures are sized per
building: the top tier about as big as the generated one, the lower tiers in
proportion, so the building still grows.
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import building_tiles  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland.tiles import TileLibrary  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import mappage  # noqa: E402

G = 7
library = TileLibrary(FakeCollection(), FakeCollection(), FakeCollection())
buildings = [{"key": "tavern", "name": "The Tavern", "shape": "inn", "symbol": "",
              "tiers": [{"title": f"T{i}"} for i in range(1, 7)]}]
building_tiles.sync(library, G, buildings)


def png(w, h):
    out = io.BytesIO()
    Image.new("RGBA", (w, h), (200, 100, 50, 255)).save(out, "PNG")
    return out.getvalue()


tiles = {t["requires"]["tier"]: t for t in library.tiles(G) if t["source"].startswith("building:")}
for tier, (w, h) in {1: (100, 80), 6: (400, 300)}.items():
    vid = library._store_art(tiles[tier]["tile_id"], png(w, h), "image/png")
    library._tiles.update_one({"tile_id": tiles[tier]["tile_id"]}, {"$set": {"uploaded": vid}})


class Bot:
    dodoland_tiles = library
    dodoland_params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)


class Guild:
    id = G


bot, guild = Bot(), Guild()
placeable = library.tiles(G)
assert mappage.uploaded_art(bot, guild, placeable, 10.0, (), 0.5) == {}, "uploaded art drawn while set to generated"
bot.dodoland_params.set(G, "dodoland_building_art", "uploaded")
art = mappage.uploaded_art(bot, guild, library.tiles(G), 10.0, (), 0.5)
t1, t6 = tiles[1]["tile_id"], tiles[6]["tile_id"]
assert set(art) == {t1, t6}, "a tier with no uploaded picture was given one"
# The top tier: the square root of its area is 60% of the generated box (10 x 0.5 cells).
assert abs(art[t6][1] - 400 / ((400 * 300) ** 0.5 / (0.6 * 5))) < 0.01, art[t6]
assert abs(art[t1][1] / art[t6][1] - 100 / 400) < 0.01, "the lower tier lost its size relative to the top one"
print("art             uploaded pictures only when chosen, sized from the top tier down")

bot.dodoland_params.set(G, "dodoland_uploaded_building_scale", 2.0)
bigger = mappage.uploaded_art(bot, guild, library.tiles(G), 10.0, (), 0.5)
assert abs(bigger[t6][1] - 2 * art[t6][1]) < 0.01
print("art             the size setting scales every uploaded picture")

# Rebuilding the generated drawings (a new colour) keeps the uploaded pictures.
buildings[0]["colour"] = "#123456"
building_tiles.sync(library, G, buildings)
again = {t["requires"]["tier"]: t for t in library.tiles(G) if t["source"].startswith("building:")}
assert again[6]["uploaded"] == library.get(t6)["uploaded"] != "", "a rebuild dropped the uploaded picture"
assert library.art(again[6]["uploaded"]) is not None, "the uploaded picture's bytes were removed"
assert again[6]["variants"] != [again[6]["uploaded"]], "the uploaded picture replaced the generated one"
print("art             rebuilding the generated drawings never touches the uploaded ones")

# One building bigger or smaller than the rest.
assert mappage.building_sizes("menagerie=0.6, tavern = 1.2; bad=x, =3") == {"menagerie": 0.6, "tavern": 1.2}
bot.dodoland_params.set(G, "dodoland_uploaded_building_scale", 1.0)
bot.dodoland_params.set(G, "dodoland_uploaded_building_sizes", "tavern=0.5")
half = mappage.uploaded_art(bot, guild, library.tiles(G), 10.0, (), 0.5)
assert abs(half[t6][1] - art[t6][1] / 2) < 0.01, "a building's own size was not applied"
print("art             a single building can be sized on its own")

# A town is drawn by a painted picture with its flag: its own painted building
# nearest its centre, within reach; otherwise the generated hall stays.
class _Terrain:
    def world(self, gid):
        return {"cells_w": 100, "cells_h": 100}


bot.dodoland_terrain = _Terrain()
upload = mappage.uploaded_art(bot, guild, library.tiles(G), 10.0, (), 0.5)
people = [{"id": "1", "plot": {"x": 50.0, "y": 50.0}, "built": []},
          {"id": "2", "plot": {"x": 10.0, "y": 10.0}, "built": []}]
world = [{"id": "far", "a": t6, "t": "1", "x": 58.0, "y": 50.0},
         {"id": "near", "a": t1, "t": "1", "x": 51.0, "y": 50.5},
         {"id": "other", "a": t6, "t": "9", "x": 50.0, "y": 50.0},
         {"id": "away", "a": t6, "t": "2", "x": 40.0, "y": 40.0}]
mappage.pictured_towns(bot, guild, people, world, library.tiles(G), upload)
assert people[0].get("hall_piece") == "near", people[0]
assert "hall_piece" not in people[1] and "hall_art" not in people[1], "a building out of reach drew the town"
mappage.pictured_towns(bot, guild, [dict(people[0])], world, library.tiles(G), {})
print("art             a town is drawn by its nearest own painted building, or keeps its hall")

print("PASS")
