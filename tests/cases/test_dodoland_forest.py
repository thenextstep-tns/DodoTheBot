"""DodoLand: forests painted as a layer, not placed tree by tree.

A stroke writes a stand's index into the terrain store's cover layer (0 to
erase); the stand list is append-only and reused for the same settings; the
ground underneath is untouched; nothing per tree is stored. The trees are grown
in the browser from the cells, deterministically, all over the map.
"""
import asyncio
import json
import math
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import forest as F  # noqa: E402
from helpers.dodoland import terrain as T  # noqa: E402
from web.dodoland import forest_api  # noqa: E402

GUILD = 42

# ---- stands -------------------------------------------------------------------
a = F.stand_spec(mix=["oak", "pine", "oak"], density=0.75, scale=1, jitter=0.15)
b = F.stand_spec(mix=["oak", "pine"], density="0.75", scale=1.0, jitter=0.15)
assert a == b and a["mix"] == ["oak", "pine"], "the same stand was described two ways"
assert F.stand_spec(mix=["oak"], density=9)["density"] == 1.0, "density was not bounded"
assert F.stand_spec(mix=["oak"], scale=-3)["scale"] == 0.25
try:
    F.stand_spec(mix=[])
    raise AssertionError("a forest of nothing was accepted")
except F.ForestError:
    pass
first, stands = F.stand_index([{"key": "none"}], a)
again, stands2 = F.stand_index(stands, b)
assert first == 1 and again == 1 and len(stands2) == 2, "painting the same stand again added another"
other, stands3 = F.stand_index(stands2, F.stand_spec(mix=["oak"], density=0.5))
assert other == 2 and stands3[1] == stands2[1], "a new stand moved an old one"
print("stands          the same settings reuse their stand; a new one is appended, never inserted")


# ---- the endpoints ----------------------------------------------------------------
class _Audit:
    def record(self, *a, **k):
        pass


class _Tiles:
    def visible(self, tile_id, guild_id):
        if tile_id in ("oak", "pine"):
            return {"tile_id": tile_id, "placement": "place", "access": ["admin"]}
        if tile_id == "grass":
            return {"tile_id": tile_id, "placement": "paint", "access": ["admin"]}
        return None


class _Bot:
    def __init__(self, store):
        self.dodoland_terrain = store
        self.dodoland_tiles = _Tiles()
        self.audit_log = _Audit()


class _Guild:
    id, name = GUILD, "Test"


class _Req(dict):
    def __init__(self, bot, payload=None, query=None):
        super().__init__()
        self.app = {"bot": bot}
        self.match_info = {"gid": str(GUILD)}
        self.query = query or {}
        self._payload = payload
        self["guild"], self["scope"], self["uid"] = _Guild(), "owner", 1

    async def json(self):
        return self._payload


store = T.TerrainStore(FakeCollection(), FakeCollection())
store.set_world(GUILD, cells_w=512, cells_h=512)
grass = T.index_of(T.base_kinds(T.TERRAIN), "grass")
store.paint(GUILD, {(x, y): grass for x in range(90, 111) for y in range(390, 411)})
bot = _Bot(store)


def call(handler, payload=None, query=None):
    return json.loads(asyncio.run(handler(_Req(bot, payload, query))).body.decode())


done = call(forest_api.api_forest_paint, {"points": [[100, 400]], "radius": 6, "mix": ["oak", "pine"]})
assert done["ok"] and done["stand"] == 1 and 100 < done["cells"] < 125, done
assert store.at(GUILD, 100, 400, T.COVER) == 1 and store.at(GUILD, 108, 400, T.COVER) == 0
assert store.at(GUILD, 100, 400) == grass, "painting forest changed the ground under it"
assert store.world(GUILD)["stands"][1]["mix"] == ["oak", "pine"]
again = call(forest_api.api_forest_paint, {"points": [[300, 300]], "radius": 3, "mix": ["pine", "oak", "pine"]})
assert again["stand"] == 2, "a different mix order is a different stand"
erased = call(forest_api.api_forest_paint, {"points": [[100, 400]], "radius": 2, "erase": True})
assert erased["ok"] and store.at(GUILD, 100, 400, T.COVER) == 0 and store.at(GUILD, 104, 400, T.COVER) == 1
print("painting        a stroke writes its stand, erase writes nothing, the ground is untouched")

refused = call(forest_api.api_forest_paint, {"points": [[10, 10]], "radius": 2, "mix": ["grass"]})
assert not refused["ok"], "a ground tile was planted as a tree"
refused = call(forest_api.api_forest_paint, {"points": [[10, 10]], "radius": 2, "mix": ["nothing"]})
assert not refused["ok"], "a tile this server does not have was planted"
assert not call(forest_api.api_forest_paint, {"points": [[10, 10]], "radius": 2})["ok"]
print("painting        only what an admin could place grows in a forest")

got = call(forest_api.forest_chunks, query={"r": "0,0,7,7"})
assert got["ok"] and set(got["chunks"]) == {"1,6", "4,4"}, got["chunks"].keys()
assert len(got["stands"]) == 3 and got["version"]
print("reading         only chunks with forest in them are sent, with the stands")

# Nothing per tree: a forest of tens of thousands of cells is a few chunk rows.
call(forest_api.api_forest_paint, {"points": [[64, 64], [448, 448]], "radius": 60, "mix": ["oak"]})
rows = list(store._chunks.find({"layer": T.COVER}))
assert len(rows) <= 64 and sum(len(r["rle"]) for r in rows) < 40_000, len(rows)
print(f"storage         a forest across the map is {len(rows)} chunk rows, nothing per tree")

# ---- growing the trees (the browser) ---------------------------------------------------
from web.dodoland import forest_ui  # noqa: E402

node = shutil.which("node")
if node:
    probe = r"""
var D = {cells_w: 3832};
var assets = {oak: {id: 'oak', wc: 3, lo: 0.5, hi: 3}, pine: {id: 'pine', wc: 2, lo: 0.5, hi: 3}};
function assetById(id) { return assets[id] || null; }
var FOREST = {stands: [{key: 'none'}, {mix: ['oak', 'pine'], density: 0.75, scale: 1, jitter: 0.15, flip: true, seed: 12345}]};
""" + forest_ui.SCRIPT[forest_ui.SCRIPT.index("  function forestRand"):forest_ui.SCRIPT.index("  function forestImg")] + r"""
var out = [];
[[1, 1], [7, 14], [40, 27]].forEach(function (c) {
  var cells = new Uint16Array(4096);
  for (var i = 0; i < 4096; i++) if ((i % 64) < 32) cells[i] = 1;   // the left half only
  var a = forestTrees(c[0], c[1], cells), b = forestTrees(c[0], c[1], cells);
  var same = JSON.stringify(a.map(function (t) { return [t.x, t.y, t.a.id, t.w]; })) ===
             JSON.stringify(b.map(function (t) { return [t.x, t.y, t.a.id, t.w]; }));
  var inside = a.every(function (t) { return t.x - c[0] * 64 < 34 && t.x - c[0] * 64 > -2; });
  var sorted = a.every(function (t, i) { return !i || a[i - 1].y <= t.y; });
  out.push([a.length, same, inside, sorted].join(':'));
});
console.log(out.join(' '));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(probe)
    result = subprocess.run([node, f.name], capture_output=True, text=True)
    parts = result.stdout.split()
    assert len(parts) == 3, (result.stdout, result.stderr)
    for part in parts:
        count, same, inside, ordered = part.split(":")
        assert int(count) > 100, f"a half-painted chunk grew only {count} trees"
        assert same == "true", "the same forest grew different trees twice"
        assert inside == "true", "trees grew on cells that are not forest"
        assert ordered == "true", "trees are not drawn nearest last"
    print(f"growing         the same trees every time, only on forest, all down the map: {' '.join(p.split(':')[0] for p in parts)}")

print("PASS")
