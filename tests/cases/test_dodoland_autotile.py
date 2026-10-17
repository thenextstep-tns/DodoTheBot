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
    fns = js[js.index("  // A corner's four cells, as bits"):js.index("  // The sixteen shapes of kind k")]
    probe = fns + r"""
function f(i, u, v) { return dualAt(i, u, v).f; }
var out = {
  // A lone corner of ground is a rounded quarter: in near its cell, out across the diagonal.
  tip_in: f(1, 0.2, 0.2) > 0.5, tip_out: f(1, 0.36, 0.36) < 0.5,
  // Three corners: the bare one is an inner curve, the mirror of the tip.
  inner_out: f(14, 0.2, 0.2) < 0.5, inner_in: f(14, 0.36, 0.36) > 0.5,
  // Two side by side: a straight edge on the cell line, its depth measured from it.
  edge: f(12, 0.5, 0.49) < 0.5 && f(12, 0.5, 0.51) > 0.5, depth: dualAt(12, 0.3, 0.8).d.toFixed(2),
  // Two diagonal: joined through the middle, so a road painted diagonally is one road.
  diag_mid: f(5, 0.5, 0.5) > 0.5, diag_off: f(5, 0.9, 0.1) < 0.5,
  // Along an edge the fringe's place runs 0 to 1 and meets the next tile's.
  t_tip: [dualAt(1, 0.5, 0.0001).t, dualAt(1, 0.0001, 0.5).t].map(function (x) { return x.toFixed(2); }).join(','),
  t_edge: dualAt(12, 0.25, 0.5).t.toFixed(2)
};
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(probe)
    run = subprocess.run([node, f.name], capture_output=True, text=True)
    got = json.loads(run.stdout or "{}") if run.returncode == 0 else {}
    assert got, (run.stdout, run.stderr)
    assert got["tip_in"] and got["tip_out"], f"a lone corner is not a rounded tip: {got}"
    assert got["inner_out"] and got["inner_in"], f"an inner corner is not curved: {got}"
    assert got["edge"] and got["depth"] == "0.30", f"a straight edge is not on the cell line: {got}"
    print("shapes          a lone corner is a rounded tip, three an inner curve, two a straight edge")
    assert got["diag_mid"] and got["diag_off"], f"two diagonal cells are not joined: {got}"
    print("shapes          two diagonal cells are joined, so a diagonal road is one road")
    assert got["t_tip"] == "0.00,1.00" and got["t_edge"] == "0.25", f"the fringe does not run on: {got}"
    print("shapes          the fringe's place along an edge runs on from tile to tile")
    bake = js[js.index("  // --- the close-up ground, baked"):js.index("  function bakeShow(key, res) {")]
    assert "blur(" not in bake and "bakeSmoothPath" not in bake, "the bake still blurs or traces outlines"
    print("bake            no blurs and no traced outlines: stamped corner shapes and one fill a ground")
else:
    print("shapes          (node not installed; the page's corner shapes were not run)")

server = pathlib.Path("web/dodoland/terrain_api.py").read_text(encoding="utf-8")
assert '"auto": {"center"' in server and 'tile = {**tile, "variants": list(auto.get("center")' in server, \
    "the map is not told which grounds are smart, or their plain texture uses their edges"
print("server          smart grounds are sent with their roles; their plain texture is centres only")

print("PASS")
