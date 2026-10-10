"""DodoLand: a server's town buildings as tiles players unlock and place.

Each (building, tier) becomes one of the server's own tiles on layer 4, locked
behind that building at that tier. They are derived from the building
definitions, so a re-sync must change nothing, a renamed building must rename
its tiles, and a removed building must take its tiles with it.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import building_tiles, tiles as T  # noqa: E402

GUILD = 42
lib = T.TileLibrary(FakeCollection(), FakeCollection(), FakeCollection())
tiers = [{"title": "Shed"}, {"title": "Hall"}, {"title": "Palace"}]
buildings = [{"key": "moot", "name": "Town Hall", "shape": "hall", "symbol": "scales", "tiers": tiers},
             {"key": "menagerie", "name": "Zoo", "shape": "pen", "symbol": "paw", "tiers": tiers[:2]}]

assert building_tiles.sync(lib, GUILD, buildings) == {"added": 5, "updated": 0, "removed": 0, "total": 5}
assert building_tiles.sync(lib, GUILD, buildings)["added"] == 0, "a re-sync added tiles again"
hall = lib.by_source(f"building:{GUILD}:moot:2")
assert hall["name"] == "Town Hall · Hall" and hall["guild_id"] == GUILD
assert hall["layer"] == "buildings" and hall["placement"] == "place"
assert hall["access"] == ["admin", "player"] and not hall["passable"]
assert hall["requires"] == {"building": "moot", "tier": 2}
assert lib.art_sizes(hall["variants"])[hall["variants"][0]] == (120, 78), "an SVG's size must be read"
assert lib.visible(hall["tile_id"], 7) is None, "a server's buildings leaked to another server"
print("buildings       every building and tier is a layer-4 tile, locked behind itself")

# Locked until that building reaches that tier.
usable = lib.usable(GUILD, "buildings", "player")
unlocked = T.unlocked_for(usable, {"buildings": {"moot": {"tier": 0}}}, buildings)
assert lib.by_source(f"building:{GUILD}:moot:1")["tile_id"] in unlocked
assert hall["tile_id"] not in unlocked
print("buildings       a tier's tile unlocks when the building reaches that tier")

# Derived: renames follow, removals clean up.
buildings[0]["name"] = "The Moot"
buildings = buildings[:1]
result = building_tiles.sync(lib, GUILD, buildings)
assert result["removed"] == 2 and lib.by_source(f"building:{GUILD}:menagerie:1") is None, result
assert lib.by_source(f"building:{GUILD}:moot:1")["name"] == "The Moot · Shed"
print("buildings       renames follow the building and a removed building takes its tiles")

# A town drawn as a hall always flies exactly one flag: the town's picture when
# it has one, a pennant in its colour when it does not — whatever the shape.
from helpers.dodoland import townart  # noqa: E402

for shape in townart.SHAPES:
    plain = townart.hall_svg(shape, 3, "#c0392b")
    pictured = townart.hall_svg(shape, 3, "#c0392b", flag_url="/p.png", uid="9")
    assert plain.count('class="banner"') == 1, f"{shape} hall without a picture flies no pennant"
    assert pictured.count("townflag") == 1 and 'class="banner"' not in pictured,         f"{shape} hall flies two flags or none"
print("halls           every hall flies one flag, its picture or its own pennant")

print("PASS")
