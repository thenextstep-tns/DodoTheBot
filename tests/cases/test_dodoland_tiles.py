"""DodoLand: the tile library the base map is painted with.

What this holds down: the library is one list in one order everywhere, a move
never leaves gaps or duplicates, a refusal changes nothing, and the bytes never
ride along with a listing.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import tiles as T  # noqa: E402

PNG = "image/png"
lib = T.TileLibrary(FakeCollection(), FakeCollection(), FakeCollection())


def refused(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except T.TileError as error:
        return str(error)
    raise AssertionError(f"{fn.__name__} should have been refused")


# --------------------------------------------------------------------------- #
#  Categories
# --------------------------------------------------------------------------- #
water = lib.add_category("Water")
ground = lib.add_category("Ground")
rock = lib.add_category("Rock")
assert [c["name"] for c in lib.categories()] == ["Water", "Ground", "Rock"]
assert "already" in refused(lib.add_category, "water")
assert "name" in refused(lib.add_category, "  ")

lib.move_category(rock["cat_id"], -2)
assert [c["name"] for c in lib.categories()] == ["Rock", "Water", "Ground"]
# Clamped at the ends rather than wrapping or refusing.
lib.move_category(rock["cat_id"], -5)
lib.move_category(ground["cat_id"], 9)
assert [c["name"] for c in lib.categories()] == ["Rock", "Water", "Ground"]
assert [c["order"] for c in lib.categories()] == [0, 1, 2]
lib.rename_category(rock["cat_id"], "Mountains")
assert lib.categories()[0]["name"] == "Mountains"
print("categories      add, reorder (clamped, renumbered), rename")

# --------------------------------------------------------------------------- #
#  Tiles
# --------------------------------------------------------------------------- #
deep = lib.add_tile(name="Deep sea", cat_id=water["cat_id"], data=b"a", content_type=PNG)
sea = lib.add_tile(name="Sea", cat_id=water["cat_id"], data=b"b", content_type=PNG)
grass = lib.add_tile(name="Grass", cat_id=ground["cat_id"], data=b"c", content_type=PNG)
loose = lib.add_tile(name="Odd", cat_id="", data=b"d", content_type=PNG)

# Palette order: by category order, then position, uncategorised last.
assert [t["name"] for t in lib.tiles()] == ["Deep sea", "Sea", "Grass", "Odd"]
groups = [(cat["name"], [t["name"] for t in tiles]) for cat, tiles in lib.grouped()]
assert groups == [("Mountains", []), ("Water", ["Deep sea", "Sea"]),
                  ("Ground", ["Grass"]), ("Uncategorised", ["Odd"])], groups

# A listing never carries the bytes.
assert all("data" not in t for t in lib.tiles())
assert lib.art(deep["variants"][0])["data"] == b"a"
print("tiles           palette order, uncategorised last, listings carry no bytes")

lib.move_tile(sea["tile_id"], -1)
assert [t["name"] for t in lib.tiles()][:2] == ["Sea", "Deep sea"]
# Moving to another category puts it at the end there and closes the gap behind.
lib.update_tile(sea["tile_id"], cat_id=ground["cat_id"])
water_tiles = [t for c, ts in lib.grouped() if c["name"] == "Water" for t in ts]
ground_tiles = [t for c, ts in lib.grouped() if c["name"] == "Ground" for t in ts]
assert [t["order"] for t in water_tiles] == [0]
assert [(t["name"], t["order"]) for t in ground_tiles] == [("Grass", 0), ("Sea", 1)]
lib.update_tile(sea["tile_id"], name="Open sea")
assert lib.get(sea["tile_id"])["name"] == "Open sea"
print("tiles           moves within and between categories leave no gaps")

# Refusals change nothing.
before = lib.tiles()
assert "PNG" in refused(lib.add_tile, name="X", cat_id="", data=b"x", content_type="text/html")
assert "empty" in refused(lib.add_tile, name="X", cat_id="", data=b"", content_type=PNG)
assert "under" in refused(lib.add_tile, name="X", cat_id="", data=b"x" * (T.MAX_BYTES + 1),
                          content_type=PNG)
assert "category" in refused(lib.add_tile, name="X", cat_id="nope", data=b"x", content_type=PNG)
assert lib.tiles() == before
print("tiles           a refused upload stores nothing")

# --------------------------------------------------------------------------- #
#  Variants
# --------------------------------------------------------------------------- #
second = lib.add_variant(grass["tile_id"], data=b"c2", content_type=PNG)
assert lib.get(grass["tile_id"])["variants"] == [grass["variants"][0], second]
lib.remove_variant(grass["tile_id"], grass["variants"][0])
assert lib.get(grass["tile_id"])["variants"] == [second]
assert lib.art(grass["variants"][0]) is None
assert "at least one" in refused(lib.remove_variant, grass["tile_id"], second)
for n in range(T.MAX_VARIANTS - 1):
    lib.add_variant(grass["tile_id"], data=b"v", content_type=PNG)
assert "at most" in refused(lib.add_variant, grass["tile_id"], data=b"v", content_type=PNG)
print("variants        add, remove, never the last one, capped")

# --------------------------------------------------------------------------- #
#  Removal
# --------------------------------------------------------------------------- #
assert "first" in refused(lib.remove_category, ground["cat_id"])
art_before = len(lib._art.docs)
held = len(lib.get(grass["tile_id"])["variants"])
lib.remove_tile(grass["tile_id"])
assert len(lib._art.docs) == art_before - held, "a removed tile left its images behind"
lib.remove_tile(sea["tile_id"])
lib.remove_category(ground["cat_id"])
assert [c["name"] for c in lib.categories()] == ["Mountains", "Water"]
assert [c["order"] for c in lib.categories()] == [0, 1]
assert lib.get(loose["tile_id"]) is not None
print("removal         a tile takes its images; only an empty category goes")

# --------------------------------------------------------------------------- #
#  Who may use a tile, and where
# --------------------------------------------------------------------------- #
# Six uses: three layers a person can place on, two user types. The owner is
# not a role, and the roads layer is the bot's.
assert len(T.USES) == 6 and "objects:player" in T.USES
assert not any(u.startswith("roads") or u.endswith(":owner") for u in T.USES)

tree = lib.add_tile(name="Oak", cat_id=water["cat_id"], data=b"t", content_type=PNG,
                    uses=["objects:player", "objects:admin"], cell_px=32,
                    pack="Summer Plains", source="sp:Oak")
# Stored in canonical order whatever order it was given in.
assert lib.get(tree["tile_id"])["uses"] == ["objects:admin", "objects:player"]
assert lib.get(tree["tile_id"])["cell_px"] == 32
assert lib.by_source("sp:Oak")["tile_id"] == tree["tile_id"]
assert lib.by_source("sp:nothing") is None and lib.by_source("") is None
assert [t["name"] for t in lib.usable("objects", "player")] == ["Oak"]
assert lib.usable("environment", "admin") == []

# A typo in a use is refused, never silently dropped: dropping it would remove
# a permission without anybody noticing.
assert "Unknown" in refused(lib.set_uses, tree["tile_id"], ["objects:owner"])
assert lib.get(tree["tile_id"])["uses"] == ["objects:admin", "objects:player"]
assert "grid" in refused(lib.update_tile, tree["tile_id"], cell_px=24)
lib.update_tile(tree["tile_id"], cell_px=16)
assert lib.get(tree["tile_id"])["cell_px"] == 16

# A whole category at once.
assert lib.set_category_uses(water["cat_id"], ["environment:admin"]) == 2
assert all(t["uses"] == ["environment:admin"] for c, ts in lib.grouped()
           if c["cat_id"] == water["cat_id"] for t in ts)
lib.set_uses(tree["tile_id"], [])
assert lib.get(tree["tile_id"])["uses"] == []
print("uses            per tile, per category, canonical, typos refused, grid 16/32")

# A row stored before these fields existed reads with safe defaults rather
# than as whatever None turns into.
lib._tiles.insert_one({"tile_id": "old", "name": "Old", "cat_id": "", "order": 9,
                       "variants": ["v"]})
old = lib.get("old")
assert old["uses"] == [] and old["cell_px"] == T.DEFAULT_CELL and old["pack"] == ""
print("uses            older rows read with defaults")

print("PASS")
