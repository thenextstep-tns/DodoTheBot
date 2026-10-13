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

print("PASS")
