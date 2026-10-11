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
assert terrain_api.version(GUILD) != was, "a paint left the rendered map cached"
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

# --------------------------------------------------------------------------- #
#  The brush's randomisers, the selection and the pattern
# --------------------------------------------------------------------------- #
lake = T.index_of(T.base_kinds(T.TERRAIN), "lake")
# Density scatters: about that share of the disc, and the same stroke with the
# same seed lands on exactly the same cells — the server rolls the dice.
full = paint({"kind": lake, "radius": 12, "points": [[300, 300]]})["cells"]
half = paint({"kind": forest, "radius": 12, "points": [[300, 300]], "density": 0.5, "seed": 7})["cells"]
assert 0.35 * full < half < 0.65 * full, (half, full)
again = paint({"kind": forest, "radius": 12, "points": [[300, 300]], "density": 0.5, "seed": 7})["cells"]
assert again == half, "the same seeded stroke painted different cells"
print(f"randomiser      density 0.5 paints {half} of {full} cells, and a seed repeats exactly")

# A soft edge thins the rim and leaves the middle alone.
paint({"kind": lake, "radius": 12, "points": [[300, 300]]})
paint({"kind": forest, "radius": 12, "points": [[300, 300]], "soft": 1.0, "seed": 3})
assert brush.at(GUILD, 300, 300) == forest, "a soft brush missed its own centre"
rim = sum(1 for dx in range(-12, 13) for dy in range(-12, 13)
          if 10 * 10 <= dx * dx + dy * dy <= 12 * 12 and brush.at(GUILD, 300 + dx, 300 + dy) == forest)
assert rim < 30, f"a soft edge still painted {rim} rim cells"
print("randomiser      a soft edge thins the rim and keeps the centre")

# A selection fills exactly its rectangle, in either drag direction.
filled = paint({"mode": "rect", "kind": lake, "rect": [210, 220, 200, 215]})
assert filled["cells"] == 11 * 6, filled
assert brush.at(GUILD, 200, 215) == lake and brush.at(GUILD, 210, 220) == lake
assert brush.at(GUILD, 211, 220) != lake
print("select          a selection fills exactly its rectangle")

# A pattern is tiled from the world's own origin, so two strokes line up.
stamp = {"w": 2, "h": 1, "cells": [lake, forest]}
paint({"pattern": stamp, "radius": 3, "points": [[400, 400]]})
assert brush.at(GUILD, 400, 400) == lake and brush.at(GUILD, 401, 400) == forest
assert brush.at(GUILD, 402, 401) == lake
assert not paint({"pattern": {"w": 2, "h": 1, "cells": [lake, 999]}, "points": [[1, 1]]})["ok"]
print("pattern         a pattern tiles from the world origin and names only real ground")

# --------------------------------------------------------------------------- #
#  Ground drawn with library tiles
# --------------------------------------------------------------------------- #
from helpers.dodoland import terrainart  # noqa: E402

grass = {"tile_id": "g1", "name": "Meadow grass", "passable": True, "variants": ["a", "b"],
         "cell_px": 16}
water = {"tile_id": "w1", "name": "Deep water", "passable": False, "variants": ["c"],
         "cell_px": 32}
i = brush.kind_for_tile(GUILD, grass, "#46934f")
assert brush.kind_for_tile(GUILD, grass) == i, "a tile became two kinds"
j = brush.kind_for_tile(GUILD, water)
kinds = brush.world(GUILD)["kinds"]
assert j == i + 1 == len(kinds) - 1, "a tile kind must be appended, never inserted"
assert kinds[i]["move"] == 1 and kinds[i]["build"], kinds[i]
assert kinds[j]["move"] is None and kinds[j]["water"], "impassable water must block roads"
# A tile later marked impassable blocks roads without a repaint.
synced = T.sync_tile_kinds(kinds, {"g1": {**grass, "passable": False}, "w1": water})
assert synced[i]["move"] is None
print("tiles           painting a tile appends one kind, with costs that follow the tile")

# A world may fix a kind's costs: the same stone paving is a road in one place
# and a mountain range in another, and the mountain must stay blocked.
mountain = {**kinds[i], "key": kinds[i]["key"] + "_mountains", "move": None, "grow": None,
            "build": False, "fixed": True}
assert T.sync_tile_kinds([mountain], {"g1": grass})[0]["move"] is None
print("tiles           a kind with fixed costs keeps them whatever its tile says")

defs = terrainart.pattern_defs(kinds, {"g1": grass, "w1": water}, "/art/",
                               {"a": (16, 16), "b": (16, 16), "c": (32, 32)})
assert defs.count("<pattern") == 2 and "/art/a" in defs and "/art/b" in defs
# A 32px tile still covers one cell: scale is the tile's own px per cell.
assert 'width="1" height="1"' in terrainart.tile_pattern("x", water, "/art/", {"c": (32, 32)})
grid = [i] * T.CELLS
assert f"url(#{terrainart.pattern_id(kinds[i]['key'])})" in terrainart.chunk_svg(grid, kinds, textured=True)
assert "#46934f" in terrainart.chunk_svg(grid, kinds), "far away a tile is its average colour"
assert not hasattr(terrainart, "MOTIFS"), "the generated motifs came back"
print("tiles           ground is a tile pattern up close and the tile's colour far away")

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

# A town's reach and a road are separate questions: shallow water stops a road
# and lets a town spread; deep sea stops both; unset, reach follows roads.
from helpers.dodoland import tiles as tile_rules  # noqa: E402

shallows = T.tile_kind({"tile_id": "s", "name": "Lake water", "passable": False, "spreads": True})
deep = T.tile_kind({"tile_id": "d", "name": "Deep water", "passable": False})
meadow = T.tile_kind({"tile_id": "m", "name": "Meadow", "passable": True})
assert shallows["move"] is None and shallows["grow"] == 1 and shallows["water"]
assert deep["move"] is None and deep["grow"] is None
assert meadow["move"] == 1 and meadow["grow"] == 1
assert tile_rules._complete({"tile_id": "x", "passable": False})["spreads"] is False
assert tile_rules._complete({"tile_id": "x", "passable": True})["spreads"] is True
print("influence       shallows stop a road but not a town; unset follows roads")

# A member paints only inside their own area, and their undo takes back only
# their own stroke — never what somebody else painted over it since.
import json as _json  # noqa: E402

water = T.index_of(T.base_kinds(T.TERRAIN), "lake")


def member(payload, area, uid=77, undo=None):
    req = _Req(bot, payload)
    req["uid"], req["player"] = uid, True
    req["paint_filter"] = area.__contains__
    call = terrain_api.api_player_terrain_undo if undo is not None else terrain_api.api_terrain_paint
    if undo is not None:
        req._payload = {"redo": undo}
    return _json.loads(asyncio.run(call(req)).body.decode())


sand = T.index_of(T.base_kinds(T.TERRAIN), "sand")
area = {(x, y) for x in range(440, 460) for y in range(440, 460)}
done = member({"kind": sand, "radius": 30, "points": [[450, 450]]}, area)
assert done["ok"] and done["cells"] == len(area), done
assert brush.at(GUILD, 439, 450) != sand and brush.at(GUILD, 450, 450) == sand,     "a member painted outside their own area"
refused = member({"kind": sand, "radius": 2, "points": [[100, 100]]}, area)
assert not refused["ok"], "a stroke wholly outside the member's area was accepted"
paint({"kind": water, "radius": 0, "points": [[445, 445]]})       # an admin paints over one cell
back = member({}, area, undo=False)
assert back["moved"] and brush.at(GUILD, 450, 450) != sand, "the member's undo did nothing"
assert brush.at(GUILD, 445, 445) == water, "a member's undo took back somebody else's painting"
again = member({}, area, undo=True)
assert again["moved"] and brush.at(GUILD, 450, 450) == sand and brush.at(GUILD, 445, 445) == water
assert member({}, area, uid=78, undo=False)["moved"] is False, "one member undid another's stroke"
print("members         paint inside their area; undo and redo are theirs and spare others' work")

print("PASS")
