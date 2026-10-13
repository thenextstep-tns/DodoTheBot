"""DodoLand: smart ground picks its own tile from its neighbours.

A smart ground is a 3 x 3 border set, extra centres and a single tile
(tools/dodoland_import_autotiles.py). The map draws each cell with the tile its
four neighbours call for: the centre inside, an edge or a corner at a border,
the single tile on its own, and a strip one cell wide from the outer bands of
both its edges. These are the page's own functions, run in node.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools import dodoland_import_autotiles as importer  # noqa: E402
from web.dodoland import terrain_ui  # noqa: E402

# The importer finds every role in a set's folder, and says what is missing.
with tempfile.TemporaryDirectory() as tmp:
    folder = pathlib.Path(tmp)
    names = ["01_top_left", "02_top_center", "03_top_right", "04_mid_left", "05_center_seamless",
             "06_mid_right", "07_bottom_left", "08_bottom_center", "09_bottom_right",
             "10_variation_a", "11_variation_b", "14_single_standalone"]
    for n in names:
        (folder / f"{n}.png").write_bytes(b"x")
    got = importer.roles(folder)
    assert [p.name for p in got["center"]] == ["05_center_seamless.png", "10_variation_a.png", "11_variation_b.png"]
    assert got["edges"]["bottom_center"].name == "08_bottom_center.png" and got["single"].name.startswith("14_")
    (folder / "06_mid_right.png").unlink()
    try:
        importer.roles(folder)
        raise AssertionError("a set with an edge missing was accepted")
    except ValueError as error:
        assert "mid_right" in str(error)
print("import          every role is found in a set, and a missing one is named")

node = shutil.which("node")
if node:
    js = terrain_ui.SCRIPT
    fns = js[js.index("  function autoHash(x, y)"):js.index("  // What the rest of the bake sees")]
    probe = fns + r"""
var set = {center: ['C', 'V1', 'V2'], single: 'S', edges: {top_left: 'TL', top_center: 'TC', top_right: 'TR',
  mid_left: 'ML', mid_right: 'MR', bottom_left: 'BL', bottom_center: 'BC', bottom_right: 'BR'}};
function pick(n, e, s, w, N, share) {
  return autoTile(n, e, s, w, 5, 9, set, share || 0, N || 1).map(function (p) { return p.v; }).join('+');
}
var out = {
  inside: pick(1, 1, 1, 1), single: pick(0, 0, 0, 0),
  north: pick(0, 1, 1, 1), east: pick(1, 0, 1, 1), south: pick(1, 1, 0, 1), west: pick(1, 1, 1, 0),
  nw: pick(0, 1, 1, 0), ne: pick(0, 0, 1, 1), sw: pick(1, 1, 0, 0), se: pick(1, 0, 0, 1),
  strip_h: pick(0, 1, 0, 1), strip_v: pick(1, 0, 1, 0), end_w: pick(0, 1, 0, 0),
  varied: pick(1, 1, 1, 1, 1, 1)
};
// With tiles two cells across, a north border shows the top band of the edge
// tile, and inside the band follows the world grid.
var band = autoTile(0, 1, 1, 1, 4, 9, set, 0, 2)[0], inner = autoTile(1, 1, 1, 1, 5, 9, set, 0, 2)[0];
out.band = [band.sy, band.sh, inner.sx, inner.sy].join(',');
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(probe)
    run = subprocess.run([node, f.name], capture_output=True, text=True)
    got = json.loads(run.stdout or "{}") if run.returncode == 0 else {}
    assert got, (run.stdout, run.stderr)
    assert got["inside"] == "C" and got["single"] == "S", got
    assert (got["north"], got["east"], got["south"], got["west"]) == ("TC", "MR", "BC", "ML"), got
    assert (got["nw"], got["ne"], got["sw"], got["se"]) == ("TL", "TR", "BL", "BR"), got
    print("tiles           inside, single, each edge and each corner get their own tile")
    assert got["strip_h"] == "TC+BC" and got["strip_v"] == "ML+MR", got
    assert got["end_w"] == "TL+BL", f"a strip's west end is not its two west corners: {got['end_w']}"
    print("tiles           a strip one cell wide is the outer bands of both its edges")
    assert got["varied"] in ("V1", "V2"), "a variation share of 1 left the plain centre"
    assert got["band"] == "0,0.5,0.5,0.5", got["band"]
    print("tiles           a tile spans N cells: a border shows its edge band, inside follows the grid")
else:
    print("tiles           (node not installed; the page's tile picking was not run)")

server = pathlib.Path("web/dodoland/terrain_api.py").read_text(encoding="utf-8")
assert '"auto": {"center"' in server and 'tile = {**tile, "variants": list(auto.get("center")' in server, \
    "the map is not told which grounds are smart, or their plain texture uses their edges"
print("server          smart grounds are sent with their roles; their plain texture is centres only")

print("PASS")
