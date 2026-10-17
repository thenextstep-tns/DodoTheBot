"""DodoLand: pictures are read once, kept in memory, and served off the bot's loop.

A map asks for a couple of hundred tile and building pictures. Each used to be
one or two database round trips across the internet, made on the bot's own
loop, so the whole bot (Discord included) waited ~100 ms per picture. Now a
picture is read once and kept (it never changes under its id), a tile is
looked up in the library's in-memory listing, and the routes read off the loop.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import tiles as T  # noqa: E402


class Counting(FakeCollection):
    """A collection that counts its single-document reads."""

    def __init__(self):
        super().__init__()
        self.reads = 0

    def find_one(self, *args, **kwargs):
        self.reads += 1
        return super().find_one(*args, **kwargs)


tiles, art = Counting(), Counting()
lib = T.TileLibrary(tiles, FakeCollection(), art)
cat = lib.add_category("Houses")
house = lib.add_tile(name="House", cat_id=cat["cat_id"], data=b"one", content_type="image/png")
vid = lib.get(house["tile_id"])["variants"][0]
lib.add_variant(house["tile_id"], data=b"two", content_type="image/png")
mine = lib.add_tile(name="Ours", cat_id=cat["cat_id"], data=b"ours", content_type="image/png", guild_id=7)

before = art.reads
assert lib.art(vid)["data"] == b"one" and lib.art(vid)["data"] == b"one"
assert art.reads == before + 1, f"a picture read twice went to the database {art.reads - before} times"
print("pictures        a picture is read from the database once, then kept")

lib.tiles()   # the listing, read once
t_before, a_before = tiles.reads, art.reads
for _ in range(5):
    assert lib.picture(house["tile_id"], 99)["data"] == b"one"
assert tiles.reads == t_before and art.reads == a_before, "serving a kept picture still asked the database"
second = lib.get(house["tile_id"])["variants"][1]
assert lib.picture(house["tile_id"], 99, second)["data"] == b"two"
assert lib.picture(house["tile_id"], 99, "not-its-own")["data"] == b"one", "a picture that is not the tile's own was served"
assert lib.picture(mine["tile_id"], 99) is None and lib.picture(mine["tile_id"], 7)["data"] == b"ours", \
    "a server saw another server's tile"
print("pictures        a tile's own picture, from memory; another server's tile is not served")

lib.remove_variant(house["tile_id"], second)
assert lib.art(second) is None, "a removed picture is still served from memory"
lib.remove_tile(house["tile_id"])
assert lib.art(vid) is None, "a removed tile's picture is still served from memory"
print("pictures        a removed picture is forgotten")

lib.art_cache_mb = 0
small = lib.add_tile(name="Tiny", cat_id=cat["cat_id"], data=b"x", content_type="image/png")
v2 = lib.get(small["tile_id"])["variants"][0]
n = art.reads
lib.art(v2), lib.art(v2)
assert art.reads == n + 2, "with no room, pictures were still kept"
print("pictures        the room for kept pictures is a setting; 0 keeps none")

routes = {name: pathlib.Path(f"web/dodoland/{name}.py").read_text(encoding="utf-8")
          for name in ("assets_route", "tiles_ui", "decor_api")}
assert "run_in_executor(None, library.picture" in routes["assets_route"]
assert routes["tiles_ui"].count("await _off_loop(") >= 2
assert "picture_response(" in routes["decor_api"] and "dodoland_tiles.art(" not in routes["decor_api"]
print("routes          every picture route reads off the bot's loop, one way")

print("PASS")
