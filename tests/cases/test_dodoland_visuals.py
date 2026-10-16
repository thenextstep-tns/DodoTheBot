"""DodoLand: the cozy pass - muted ground and baked shadows.

Ground is pushed into the background the same way in the zoomed-out picture
(server colours) and the close-up textures (the page's groundMute): contrast
towards a mid-tone, saturation down, a little warm tint. Shadows are baked once
per picture behind what stands. Both are panel settings.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import parameters as dp  # noqa: E402
from helpers.dodoland import terrainart  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import mappage  # noqa: E402

off = {"contrast": 1.0, "saturation": 1.0, "mid": 0.45, "tint": [216, 185, 140], "tint_amount": 0.0}
assert terrainart.mute_hex("#4c8a2f", off) == "#4c8a2f", "muting at 1, 1, 0 changed a colour"
assert terrainart.mute_hex("shadow", dict(off, contrast=0.5)) == "shadow", "a palette name was rewritten"

flat = dict(off, contrast=0.5)
dark, light = terrainart.mute_rgb((10, 10, 10), flat), terrainart.mute_rgb((245, 245, 245), flat)
assert dark[0] > 10 and light[0] < 245, "lower contrast did not pull towards the mid-tone"
grey = terrainart.mute_rgb((200, 60, 40), dict(off, saturation=0.0))
assert max(grey) - min(grey) <= 1, f"no saturation still has colour: {grey}"
calm = terrainart.mute_rgb((200, 60, 40), dict(off, saturation=0.5))
assert (calm[0] - calm[2]) < (200 - 40), "lower saturation did not calm the colour"
print("ground          contrast pulls to the mid-tone, saturation calms, 1/1/0 is untouched")

params = ParamManager(FakeCollection(), dp.DODOLAND_PARAMETERS)
m = terrainart.mute_settings(params, 1)
assert (m["contrast"], m["saturation"], m["tint"], m["tint_amount"]) == (0.85, 0.92, [216, 185, 140], 0.06), m
params.set(1, "dodoland_ground_tint", "not a colour")
assert terrainart.mute_settings(params, 1)["tint"] == [216, 185, 140], "a bad tint broke the settings"
print("ground          the settings default to a gentle warm mute, and a bad tint falls back")

js = mappage._SCRIPT
assert "function groundMute(cv)" in js and "bake.blocks[key] = groundMute(cv)" in js \
    and "bake.autoImgs[key] = groundMute(cv)" in js, "a ground texture is not muted on the page"
assert "function shadowFor(src, flip, done)" in js and "if (stackOf(piece) !== 'flat') addShadow(" in js, \
    "standing pieces are not given their baked shadow"
assert "filter = 'blur(" in js[js.index("function shadowFor"):js.index("function addShadow")], \
    "the shadow is not blurred when it is baked"
assert "addShadow(el, svgPicture(box, body)" in js, "houses and walkers cast no shadow"
assert "forestShadow(t.a, !!t.f)" in js and "function forestRedrawAll()" in js, "forest trees cast no shadow"
print("page            textures muted once; pieces, towns, houses, walkers and forests all get a shadow")

# One sun for every shadow: morning to the left, evening to the right, short at
# midday, faint at night; and height is measured per column, so nothing floats.
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

node = shutil.which("node")
if node:
    fn = js[js.index("  function sunState()"):js.index("  // A picture's shadow, made once per picture")]
    probe = "var D = {sizes: {sun: {}}};\n" + fn + """
var out = {};
['morning', 'noon', 'evening', 'night'].forEach(function (m) { D.sizes.sun.mode = m; out[m] = sunState(); });
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(probe)
    run = subprocess.run([node, f.name], capture_output=True, text=True)
    sun = json.loads(run.stdout)
    assert sun["morning"]["x"] < 0 < sun["evening"]["x"], "the sun does not cross the sky"
    assert sun["noon"]["len"] < sun["morning"]["len"] and sun["noon"]["len"] < sun["evening"]["len"], \
        "midday shadows are not the shortest"
    assert all(sun[m]["y"] < 0 for m in sun), "a shadow falls in front of what casts it"
    assert sun["night"]["strength"] < sun["noon"]["strength"], "night shadows are not fainter"
    print("sun             morning left, evening right, shortest at noon, always behind, faint at night")
    # The night, from the same clock: none at noon, full at night, coming on at dusk.
    nfn = js[js.index("  function nightState()"):js.index("  // A soft round light, once per colour")]
    probe = "var D = {sizes: {sun: {rise: 6, set: 20}, night: {}}};\n" + nfn + """
var out = {};
['noon', 'evening', 'night', 'morning'].forEach(function (m) { D.sizes.sun.mode = m; out[m] = nightState(); });
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(probe)
    night = json.loads(subprocess.run([node, f.name], capture_output=True, text=True).stdout)
    assert night["noon"]["dark"] == 0 and night["morning"]["dark"] == 0, "it is dark by day"
    assert abs(night["night"]["dark"] - 0.62) < 0.01, night["night"]
    assert 0 < night["evening"]["dark"] < night["night"]["dark"], "dusk does not come on gradually"
    print("night           dark at night, none by day, coming on at dusk")
assert "function drawNight()" in js and "a.gl" in js and "L.intensity" in js and "pa.al === false" in js and "windowsOf(img.src)" in js, \
    "lights and lit windows are not drawn at night"
wfn = js[js.index("  function windowsOf(src)"):js.index("  var nightCv = document.createElement")]
assert "cells.length > maxArea" in wfn and "inner - ring < minContrast" in wfn, \
    "lights are found by colour alone (a thatched roof glows)"
assert "spots: keep" in wfn and "sp.r * o.w * spill" in js, "a picture's own lanterns and fires light nothing round them"
assert "wk.kind !== 'person'" in js and "nightSoon(true)" in js, "people out at night carry no lantern"
assert "'.dltown .dlname'" in js[js.index("function drawNight"):], "town names are hidden by the night"
print("night           lights (tiles with a light) and lit windows cut the night")
print("night           a light is small and brighter than around it, and lights its surroundings")
print("night           walkers carry lanterns; town names stay readable")

from helpers.dodoland import tiles as tile_rules  # noqa: E402
lib = tile_rules.TileLibrary(FakeCollection(), FakeCollection(), FakeCollection())
cat = lib.add_category("Lights")
lamp = lib.add_tile(name="Lamp", cat_id=cat["cat_id"], data=b"<svg/>", content_type="image/svg+xml")
lamp = lib.get(lamp["tile_id"])
assert lamp["light_radius"] == 0 and lamp["light_colour"] == tile_rules.DEFAULT_LIGHT_COLOUR
lamp = lib.update_tile(lamp["tile_id"], light_radius=6, light_colour="#FF9A3C")
assert lamp["light_radius"] == 6 and lamp["light_colour"] == "#ff9a3c"
for bad in ({"light_colour": "orange"}, {"light_radius": "far"}):
    try:
        lib.update_tile(lamp["tile_id"], **bad)
        raise AssertionError(f"a bad light setting was stored: {bad}")
    except tile_rules.TileError:
        pass
assert lib.update_tile(lamp["tile_id"], light_radius=999)["light_radius"] == tile_rules.MAX_LIGHT
print("lights          a tile's light reach and colour are its own settings, checked")
# The old single light reads as one point near the top of the picture.
old = lib.get(lamp["tile_id"])["lights"]
assert len(old) == 1 and old[0]["radius"] == tile_rules.MAX_LIGHT and old[0]["colour"] == "#ff9a3c", old
# Lights placed in the editor: clipped into range, the old reach let go.
lamp = lib.update_tile(lamp["tile_id"], lights=[
    {"x": 0.3, "y": 1.7, "colour": "#AABBCC", "radius": 99, "intensity": 5},
    {"x": -1, "y": 0.4, "radius": 2, "intensity": 0.5}], uploaded_lights=[{"x": 0.5, "y": 0.5}], auto_lights=False)
lamp = lib.get(lamp["tile_id"])
assert lamp["light_radius"] == 0 and lamp["auto_lights"] is False
assert lamp["lights"][0] == {"x": 0.3, "y": 1.0, "colour": "#aabbcc", "radius": tile_rules.MAX_LIGHT, "intensity": 2.0}
assert lamp["lights"][1]["x"] == 0.0 and lamp["lights"][1]["colour"] == tile_rules.DEFAULT_LIGHT_COLOUR
assert len(lamp["uploaded_lights"]) == 1
assert len(tile_rules.clean_lights([{"x": 0, "y": 0}] * 40)) == tile_rules.MAX_LIGHTS
for bad in ("lamp", [{"x": 0.5}], [{"x": 0, "y": 0, "colour": "red"}]):
    try:
        tile_rules.clean_lights(bad)
        raise AssertionError(f"bad lights were accepted: {bad}")
    except tile_rules.TileError:
        pass
print("lights          lights placed on a picture are clipped into range; the old reach becomes one")
editor = pathlib.Path("web/dodoland/lights_ui.py").read_text(encoding="utf-8")
routes = pathlib.Path("web/dodoland/__init__.py").read_text(encoding="utf-8")
assert 'web.get("/dodoland/lights", owner(lights_page))' in routes, "the lights editor is not the owner's"
assert "update_tile" in editor and "uploaded_lights" in editor and "dblclick" in editor
print("lights editor   owner-only, saves through the tile library")
shadow_fn = js[js.index("function shadowFor"):js.index("function shadowsOn")]
assert "low[c] - top[c]" in shadow_fn and "oy + low[c]" in shadow_fn, "height is not measured per column"
print("sun             a shadow starts at each column's own base, so nothing floats")

print("PASS")
