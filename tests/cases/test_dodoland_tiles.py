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
tile_rules = T

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
#  Layer, access, requirements, roads, size
# --------------------------------------------------------------------------- #
tree = lib.add_tile(name="Oak", cat_id=water["cat_id"], data=b"t", content_type=PNG,
                    access=["player", "admin"], cell_px=32, pack="Summer Plains", source="sp:Oak")
got = lib.get(tree["tile_id"])
# Defaults: a map object, canonical role order, no lock, roads cross, fixed size.
assert got["layer"] == "objects" and got["access"] == ["admin", "player"], got
assert got["requires"] == {"building": "", "tier": 0} and got["passable"] and not got["resizable"]
assert tile_rules.scale_range(got) == (1.0, 1.0), "a fixed tile has one size"
assert lib.by_source("sp:Oak")["tile_id"] == tree["tile_id"]
assert lib.by_source("sp:nothing") is None and lib.by_source("") is None

lib.update_tile(tree["tile_id"], layer="buildings", passable=False, resizable=True,
                scale_min=0.5, scale_max=2, requires={"building": "gallery", "tier": 2})
got = lib.get(tree["tile_id"])
assert got["layer"] == "buildings" and not got["passable"]
assert tile_rules.scale_range(got) == (0.5, 2.0)
assert got["requires"] == {"building": "gallery", "tier": 2}
# A building with no tier, or a tier with no building, is no requirement.
lib.update_tile(tree["tile_id"], requires={"building": "gallery", "tier": 0})
assert lib.get(tree["tile_id"])["requires"] == {"building": "", "tier": 0}
print("fields          layer, access, requirement, roads and size are stored and read back")

# Refusals change nothing: a typo in a role must not silently drop a permission.
before = lib.get(tree["tile_id"])
assert "Unknown role" in refused(lib.update_tile, tree["tile_id"], access=["owner"])
assert "Unknown layer" in refused(lib.update_tile, tree["tile_id"], layer="roads")
assert "between" in refused(lib.update_tile, tree["tile_id"], requires={"building": "g", "tier": 99})
assert "larger" in refused(lib.update_tile, tree["tile_id"], scale_min=3, scale_max=1)
assert "Sizes go" in refused(lib.update_tile, tree["tile_id"], scale_max=50)
assert "grid" in refused(lib.update_tile, tree["tile_id"], cell_px=T.MIN_CELL - 1)
assert "Not editable" in refused(lib.update_tile, tree["tile_id"], guild_id=5)
assert lib.get(tree["tile_id"]) == before
lib.update_tile(tree["tile_id"], cell_px=57)
assert lib.get(tree["tile_id"])["cell_px"] == 57
print("fields          bad values are refused and change nothing; any scale in range")

# A whole category at once, optionally only one server's tiles in it.
assert lib.update_category(water["cat_id"], layer="environment", passable=False) == 2
assert all(t["layer"] == "environment" for c, ts in lib.grouped() if c["cat_id"] == water["cat_id"] for t in ts)
print("fields          a category can be set at once")

# --------------------------------------------------------------------------- #
#  Scope: global tiles and a server's own
# --------------------------------------------------------------------------- #
own = lib.add_tile(name="Our banner", cat_id="", data=b"o", content_type=PNG, guild_id=42,
                   access=["admin", "player"])
assert own["guild_id"] == 42
assert own["tile_id"] in {t["tile_id"] for t in lib.tiles(42)}
assert own["tile_id"] not in {t["tile_id"] for t in lib.tiles(7)}, "a server's tile leaked"
assert tree["tile_id"] in {t["tile_id"] for t in lib.tiles(7)}, "a global tile is everybody's"
assert lib.visible(own["tile_id"], 7) is None and lib.visible(own["tile_id"], 42)
# A category edit scoped to a server touches that server's tiles and nothing else.
assert lib.update_category("", guild_id=42, passable=False) == 1
assert lib.get(own["tile_id"])["passable"] is False
assert [t["name"] for t in lib.usable(42, "objects", "player")] == ["Our banner"]
print("scope           a server's own tiles are seen and edited by that server only")

# Rows stored before these fields existed read with safe defaults, and the old
# "layer:role" list becomes a layer and its roles.
lib._tiles.insert_one({"tile_id": "old", "name": "Old", "cat_id": "", "order": 9,
                       "variants": ["v"], "uses": ["environment:admin"]})
old = lib.get("old")
assert old["layer"] == "environment" and old["access"] == ["admin"], old
assert old["passable"] and not old["resizable"] and old["guild_id"] == 0 and "uses" not in old
print("legacy          older rows read with defaults; uses become layer and access")

print("PASS")
