"""DodoLand: gates in walls, how pieces stack, and areas placed things cannot break.

A gate is an opening in a town's own wall: the wall is cut there and a gateway
stands in the gap. A piece lies flat, stands by where it stands, or sits on top
of everything, so a pond can go under the tree beside it. And a town's area
follows the painted ground: nothing placed on the map punches a hole in it
unless the server asks for that.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import decor as decor_rules  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland import towns as town_rules  # noqa: E402
from helpers.dodoland.decor import DecorStore  # noqa: E402
from helpers.dodoland.towns import TownStore  # noqa: E402
from web.dodoland import influence_api  # noqa: E402

# A straight wall along y = 10 from x = 0 to x = 40, with a gate in the middle.
W, H = 100, 100
run = {"style": "stone", "town": "7", "pts": [(float(x), 10.0) for x in range(0, 41)]}
runs, gates = influence_api.cut_gates([run], {"7": [[20.0, 10.0]]}, W, H, 4.0)
assert len(runs) == 2 and len(gates) == 1, (runs, gates)
gate = gates[0]
assert gate["a"][0] < 20 < gate["b"][0] and gate["b"][0] - gate["a"][0] >= 4, gate
assert gate["style"] == "stone" and gate["town"] == "7"
# Somebody else's gate does not cut this town's wall.
untouched, none = influence_api.cut_gates([run], {"8": [[20.0, 10.0]]}, W, H, 4.0)
assert len(untouched) == 1 and not none
print("gates           a gate cuts its own town's wall and leaves the opening's ends")

towns = TownStore(FakeCollection())
assert towns.set_gates(1, 7, [[20, 10], [30.5, 10]]) == [[20.0, 10.0], [30.5, 10.0]]
assert towns.get(1, 7)["gates"] == [[20.0, 10.0], [30.5, 10.0]]
assert len(towns.set_gates(1, 7, [[1, 1]] * 40)) == town_rules.MAX_GATES, "no cap on gates"
try:
    towns.set_gates(1, 7, [[150, 10]])
    raise AssertionError("a gate off the map was kept")
except town_rules.TownError:
    pass
print("gates           a town keeps its gates, on the map, a dozen at most")

store = DecorStore(FakeCollection())
mine = store.place(1, scope=decor_rules.SCOPE_WORLD, asset_id="pond", x=10, y=10, town="7")
theirs = store.place(1, scope=decor_rules.SCOPE_WORLD, asset_id="pond", x=12, y=10, town="8")
assert store.set_stack(1, [mine["piece_id"], theirs["piece_id"]], "flat", town="7") == 1, \
    "a member restacked somebody else's piece"
assert store.piece(1, mine["piece_id"])["stack"] == "flat"
assert store.set_stack(1, [theirs["piece_id"]], "top") == 1   # an admin, anything
try:
    store.set_stack(1, [mine["piece_id"]], "sideways")
    raise AssertionError("an unknown stacking was stored")
except decor_rules.DecorError:
    pass
print("stacking        flat, standing or on top; a member only their own")

spec = next(p for p in dodo_params.DODOLAND_PARAMETERS if p["key"] == "dodoland_influence_pieces_block")
assert spec["default"] is False, "placed things break towns' areas by default"
source = pathlib.Path("web/dodoland/influence_api.py").read_text(encoding="utf-8")
assert 'params.get(guild.id, "dodoland_influence_pieces_block") else set()' in source
print("areas           nothing placed on the map breaks a town's area unless the server asks")

print("PASS")
