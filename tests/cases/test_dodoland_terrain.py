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

# --------------------------------------------------------------------------- #
#  The brush
# --------------------------------------------------------------------------- #
# The stroke is rasterised on the server so a radius means one thing. Two
# clients that each decided for themselves would paint different shapes from
# the same drag, and the map would quietly depend on which browser did it.
import asyncio  # noqa: E402

from web.dodoland import terrain_api  # noqa: E402


class _Audit:
    def record(self, *a, **k):
        pass


class _Bot:
    def __init__(self, store):
        self.dodoland_terrain = store
        self.audit_log = _Audit()


class _Guild:
    id, name = GUILD, "Test"


class _Req(dict):
    def __init__(self, bot, payload):
        super().__init__()
        self.app = {"bot": bot}
        self.match_info = {"gid": str(GUILD)}
        self._payload = payload
        self["guild"], self["scope"], self["uid"] = _Guild(), "owner", 1

    async def json(self):
        return self._payload


brush = T.TerrainStore(FakeCollection(), FakeCollection())
brush.set_world(GUILD, cells_w=512, cells_h=512)
bot = _Bot(brush)
forest = T.index_of(T.base_kinds(T.TERRAIN), "forest")


def paint(payload):
    import json as _json
    response = asyncio.run(terrain_api.api_terrain_paint(_Req(bot, payload)))
    return _json.loads(response.body.decode())


# A round brush, not a square one: square corners read as deliberate when they
# are not, and a coastline painted with them looks like tetris.
result = paint({"kind": forest, "radius": 5, "points": [[100, 100]]})
assert result["ok"], result
area = result["cells"]
assert 60 <= area <= 95, f"a radius-5 round brush painted {area} cells"
assert brush.at(GUILD, 100, 100) == forest
assert brush.at(GUILD, 104, 100) == forest, "the brush is narrower than its radius"
assert brush.at(GUILD, 104, 104) == T.UNKNOWN, "the brush painted its corners"
print(f"brush           radius 5 covers {area} cells, round rather than square")

# A radius of zero is one cell, not nothing.
assert paint({"kind": forest, "radius": 0, "points": [[7, 7]]})["cells"] == 1
print("brush           a radius of zero is a single cell")

# Painting off the edge clips rather than wrapping or erroring: a stroke that
# runs off the coast is the commonest stroke there is.
edge = paint({"kind": forest, "radius": 4, "points": [[0, 0]]})
assert edge["ok"] and 0 < edge["cells"] < 60, edge
assert brush.at(GUILD, 0, 0) == forest
print("brush           a stroke over the edge is clipped, not refused")

for payload, why in (
    ({"kind": 99, "radius": 1, "points": [[1, 1]]}, "a terrain that does not exist"),
    ({"kind": forest, "radius": 1, "points": []}, "a stroke with no points"),
    ({"kind": None, "radius": 1, "points": [[1, 1]]}, "no terrain at all"),
    ({"kind": forest, "radius": 1, "points": [[9999, 9999]]}, "a stroke off the world"),
):
    assert paint(payload)["ok"] is False, f"accepted {why}"
print("brush           nonsense is refused with something a page can show")

# A stroke longer than the cap is refused rather than silently truncated — the
# client thins its own points and a stroke that long means something is wrong.
assert paint({"kind": forest, "radius": 1,
              "points": [[1, 1]] * 5000})["ok"] is False
print("brush           an implausibly long stroke is refused, not truncated")

# Every paint bumps the version every render cache is keyed on, so nothing
# stale can outlive a stroke. This is what stands in for a rebuild.
was = terrain_api.version(GUILD)
paint({"kind": forest, "radius": 1, "points": [[200, 200]]})
assert terrain_api.version(GUILD) > was, "a paint left the rendered map cached"
print("brush           a stroke invalidates what it changed, with no job to run")

# A drag is sampled about sixty times a second and moves further than that
# between samples — at a low zoom one pixel of mouse movement is several cells.
# Stamping only where the pointer happened to be sampled left a trail of
# disconnected blobs, which is exactly what a stroke looked like.
gap = paint({"kind": forest, "radius": 2, "points": [[300, 300], [340, 300]]})
assert gap["ok"], gap
missing = [x for x in range(300, 341) if brush.at(GUILD, x, 300) != forest]
assert not missing, f"the stroke has {len(missing)} holes in it: {missing[:8]}"
print("brush           two samples forty cells apart paint a line, not two blobs")

# ...diagonally too. The property is continuity, not which exact cells a line
# algorithm picks: every column the stroke crosses must be painted, and the
# painted row must never jump by more than one between neighbouring columns.
paint({"kind": forest, "radius": 0, "points": [[20, 400], [60, 430]]})
rows = []
for x in range(20, 61):
    hit = [y for y in range(395, 436) if brush.at(GUILD, x, y) == forest]
    assert hit, f"column {x} of the diagonal stroke was not painted at all"
    rows.append(hit)
jumps = [x for i, x in enumerate(range(21, 61))
         if min(abs(a - b) for a in rows[i + 1] for b in rows[i]) > 1]
assert not jumps, f"the diagonal stroke jumps a row at columns {jumps[:6]}"
print("brush           a diagonal stroke is continuous, column by column")

# Every texture has to be drawn from colours that differ, or the motif is
# invisible. Two grounds shipped flat because a slot was its own neighbour.
from helpers.dodoland import terrainart  # noqa: E402

for kind in T.base_kinds(T.TERRAIN):
    slot = kind.get("colour")
    if kind.get("key") not in terrainart.MOTIFS:
        continue
    light = palette.lighten(slot)
    dark = palette.shade(slot)
    assert palette.PALETTE[light] != palette.PALETTE[slot],         f"{kind['key']} has no lighter colour, so its texture is invisible"
    assert palette.PALETTE[dark] != palette.PALETTE[slot],         f"{kind['key']} has no darker colour, so its texture is invisible"
print("texture         every motif is drawn from three colours that differ")

# ...and the ramps have to actually run dark to light, or "darker" returns
# something lighter and the shading inverts.
def _lum(hex_colour):
    r = int(hex_colour[1:3], 16); g = int(hex_colour[3:5], 16)
    b = int(hex_colour[5:7], 16)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

for ramp in palette._RAMPS:
    levels = [_lum(palette.PALETTE[slot]) for slot in ramp]
    assert levels == sorted(levels), f"{ramp} is not ordered dark to light"
print(f"texture         all {len(palette._RAMPS)} colour ramps run dark to light")

print("PASS")
