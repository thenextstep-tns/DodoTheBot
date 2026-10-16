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
assert "c.filter = 'blur(" in js[js.index("function shadowFor"):js.index("function addShadow")], \
    "the shadow is not blurred when it is baked"
print("page            textures are muted once as prepared; what stands gets a baked shadow")

print("PASS")
