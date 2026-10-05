"""DodoLand: the layer that turns a picture into a world.

Until this existed the map was an image the bot could not read — nothing could
be impassable, nothing could grow round a lake, no road could avoid the sea.
What this file holds down is the part everything else will be a query against:
that a cell means what it says, that an edit only rewrites what it touched, and
that the authored layer and the derived one can never overwrite each other.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import palette  # noqa: E402
from helpers.dodoland import terrain as T  # noqa: E402

GUILD = 42
store = T.TerrainStore(FakeCollection(), FakeCollection())


# --------------------------------------------------------------------------- #
#  Run-length coding
# --------------------------------------------------------------------------- #
assert T.encode([0, 0, 0, 3, 3]) == "3x0 2x3"
assert T.decode("3x0 2x3", 5) == [0, 0, 0, 3, 3]
# A whole chunk of open sea is a dozen bytes, which is the entire reason the
# grid is affordable at two million cells.
ocean = T.encode([2] * T.CELLS)
assert len(ocean) <= 16, ocean
assert T.decode(ocean) == [2] * T.CELLS
print(f"rle             a chunk of open sea stores as {len(ocean)} bytes")

# Round-trips whatever it is given, including the pathological case.
stripes = [i % 7 for i in range(T.CELLS)]
assert T.decode(T.encode(stripes)) == stripes
# Short or damaged input comes back as unknown rather than as an exception on a
# page: a chunk written by an older, smaller grid must not break a map.
assert T.decode("2x5", 6) == [5, 5, 0, 0, 0, 0]
assert T.decode("nonsense 3x1", 5) == [1, 1, 1, 0, 0]
assert T.decode("", 4) == [0, 0, 0, 0]
print("rle             round-trips, and damaged input degrades to unknown")


# --------------------------------------------------------------------------- #
#  Three questions that look like one
# --------------------------------------------------------------------------- #
kinds = {k["key"]: k for k in T.base_kinds(T.TERRAIN)}

# Water cannot be built on or grown onto, but a road may cross it at a price.
assert kinds["sea"]["build"] is False
assert T.grow_cost(kinds["sea"]) is None
assert kinds["sea"]["move"] is not None, "no road may ever bridge anything"
# Deep sea is the exception: nothing crosses it at any price.
assert kinds["deep"]["move"] is None
print("costs           water is unbuildable, bridgeable, and deep sea is not")

# Forest: a road can be cut through it, a town may only grow onto it if that
# town has chosen to clear forest. That is the whole policy mechanic.
assert kinds["forest"]["move"] is not None, "a road cannot cross a forest"
assert T.grow_cost(kinds["forest"]) is None
assert T.grow_cost(kinds["forest"], clears_forest=True) is not None
assert T.grow_cost(kinds["forest"], clears_forest=True) > T.grow_cost(kinds["plains"]), \
    "clearing forest has to cost more than walking onto grass, or nobody goes round"
assert not T.passable(kinds["forest"])
assert T.passable(kinds["forest"], clears_forest=True)
print("costs           a town that clears forest pays for it; one that does not, cannot")

# Mountain is nobody's, whatever their policy.
assert T.grow_cost(kinds["mountain"], clears_forest=True) is None
assert kinds["mountain"]["move"] is None
print("costs           mountain refuses everybody, policy or not")

# A gate is the only thing in a wall a road can use. That is what makes a wall
# worth building rather than a thing that merely looks defensive.
built = {k["key"]: k for k in T.base_kinds(T.BUILT)}
assert built["wall"]["move"] is None and built["gate"]["move"] is not None
print("costs           a wall stops a road and a gate lets it through")


# --------------------------------------------------------------------------- #
#  The store
# --------------------------------------------------------------------------- #
store.set_world(GUILD, cells_w=1916, cells_h=906, source_w=958, source_h=453)
world = store.world(GUILD)
assert (world["cells_w"], world["cells_h"]) == (1916, 906)
assert store.chunk_counts(GUILD) == (30, 15), store.chunk_counts(GUILD)
print(f"world           1916x906 cells is {30 * 15} chunks, not one document")

for bad in ((8, 100), (100, 9000)):
    try:
        store.set_world(GUILD, cells_w=bad[0], cells_h=bad[1])
    except T.TerrainError:
        pass
    else:
        raise AssertionError(f"accepted a world of {bad}")
print("world           an absurd grid size is refused")

# An unwritten chunk is unknown, not grass. A half-finished import has to look
# half-finished rather than plausible and wrong.
assert store.chunk(GUILD, 0, 0) == [T.UNKNOWN] * T.CELLS
print("world           an unpainted world is unknown, never a default terrain")

# Painting groups by chunk: a stroke across a border is two writes, not one per
# cell, and only the chunks it touched are rewritten.
sea = T.index_of(world["kinds"], "sea")
grass = T.index_of(world["kinds"], "grass")
store.paint(GUILD, {(1, 1): sea, (2, 1): sea, (65, 1): grass})
assert store.painted(GUILD) == 2, store.painted(GUILD)
assert store.at(GUILD, 1, 1) == sea
assert store.at(GUILD, 2, 1) == sea
assert store.at(GUILD, 65, 1) == grass
assert store.at(GUILD, 3, 1) == T.UNKNOWN, "painting spread to a cell nobody asked for"
print("world           a stroke writes only the chunks it crosses")

touched = store.paint(GUILD, {(x, 5): grass for x in range(0, 200)})
assert touched == 4, f"a 200-cell stroke rewrote {touched} chunks"
print("world           a 200-cell stroke is four writes, not two hundred")


# --------------------------------------------------------------------------- #
#  The authored layer and the derived one never touch
# --------------------------------------------------------------------------- #
# This is the one that matters most. A growth pass rewrites `built` constantly;
# if it could reach `terrain` it would eventually eat a hand-painted coastline,
# and nobody would know which pass did it.
road = T.index_of(world["built_kinds"], "road")
store.paint(GUILD, {(1, 1): road}, layer=T.BUILT)
assert store.at(GUILD, 1, 1, layer=T.BUILT) == road
assert store.at(GUILD, 1, 1) == sea, "the derived layer wrote over painted terrain"

assert store.wipe(GUILD, layer=T.BUILT) >= 1
assert store.at(GUILD, 1, 1) == sea, "wiping the derived layer took the terrain with it"
assert store.painted(GUILD, layer=T.BUILT) == 0
print("layers          rebuilding what is derived never touches what was painted")


# --------------------------------------------------------------------------- #
#  Guild scoping, which every DodoLand store owes
# --------------------------------------------------------------------------- #
assert store.chunk(99, 0, 0) == [T.UNKNOWN] * T.CELLS
assert store.painted(99) == 0, "another guild's world leaked"
print("scoping         one server never sees another's world")


# --------------------------------------------------------------------------- #
#  The palette
# --------------------------------------------------------------------------- #
assert len(palette.PALETTE) == 32, f"{len(palette.PALETTE)} colours, not 32"
assert len(set(palette.PALETTE.values())) == 32, "two slots share a colour"
assert all(len(v) == 7 and v.startswith("#") for v in palette.PALETTE.values())
print(f"palette         {len(palette.PALETTE)} distinct colours, every one a real hex")

# Every terrain and built kind draws from a slot that exists, or it renders as
# nothing and the map has a hole in it that no test would otherwise catch.
for layer in T.LAYERS:
    for kind in T.base_kinds(layer):
        assert kind["colour"] in palette.PALETTE, \
            f"{kind['key']} is drawn in {kind['colour']!r}, which is not a colour"
print("palette         every kind of ground names a colour that exists")

# A town may repaint its roofs. A town may not repaint the sea — otherwise a
# town can hide itself from the map it exists to be seen on.
mine = palette.resolve(town={"roof_red": "#123456"})
assert mine["roof_red"] == "#123456"
assert palette.resolve(town={"deep": "#ff0000"})["deep"] == palette.PALETTE["deep"]
try:
    palette.validate_overrides({"deep": "#ff0000"}, town=True)
except palette.PaletteError as error:
    assert "may change" in str(error), error
else:
    raise AssertionError("a town was allowed to repaint the sea")
print("palette         a town repaints its roofs and never the world")

# The server may change anything, and nonsense is refused rather than stored.
assert palette.validate_overrides({"deep": "#102030"})["deep"] == "#102030"
# Blank is not an error, it is how an override is removed — otherwise clearing a
# colour back to the default needs a second control to do it with.
assert palette.validate_overrides({"deep": ""}) == {}
assert palette.validate_overrides({"deep": None}) == {}
for bad in ("red", "#12345", "#gggggg", "rgb(1,2,3)", "url(#x)"):
    try:
        palette.validate_overrides({"deep": bad})
    except palette.PaletteError:
        pass
    else:
        raise AssertionError(f"accepted {bad!r} as a colour")
print("palette         the server may change any slot; nonsense is refused")

print("PASS")
