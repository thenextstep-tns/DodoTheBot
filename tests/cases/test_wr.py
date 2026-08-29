"""World-record bonus: points, medals, storage, and every surface agreeing."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import trial_ranks as tr
from helpers.trial_ranks import TrialRankManager


class Role:
    managed = False
    def __init__(s, i, n): s.id, s.name, s.position = i, n, 1
    def is_default(s): return False


class Guild:
    id = 42
    def __init__(s, r): s.roles = r
    def get_role(s, i): return next((x for x in s.roles if x.id == int(i)), None)


R = {n: Role(100 + i, n) for i, n in enumerate(["Low", "High", "vRG HM"])}
guild = Guild(list(R.values()))
rid = lambda n: R[n].id

# --- what a record is worth ---
assert tr.WR_POINTS == 15 and tr.FORMER_WR_POINTS == 5
cases = [({"current": 5, "former": 0}, 75), ({"current": 0, "former": 1}, 5),
         ({"current": 5, "former": 1}, 80), ({}, 0), (None, 0)]
for entry, expect in cases:
    got = tr.wr_points(entry)
    print(f"   {str(entry):32} -> {got}")
    assert got == expect, (entry, got, expect)

# --- medals, and the wall guard ---
assert tr.wr_medals({"current": 5}) == tr.WR_MEDAL * 5
assert tr.wr_medals({"former": 1}) == tr.FORMER_WR_MEDAL
mixed = tr.wr_medals({"current": 2, "former": 1})
print("   mixed:", mixed)
assert mixed == f"{tr.WR_MEDAL * 2} {tr.FORMER_WR_MEDAL}"
many = tr.wr_medals({"current": 30})
print("   thirty:", many)
assert many == f"{tr.WR_MEDAL}x30", "a long row collapses to a count"
assert tr.wr_medals(None) == ""

# --- the bonus counts towards the next rank ---
points = {str(rid("vRG HM")): 25}
ranks = tr.validate_ranks([{"role_id": rid("Low"), "min_points": 0},
                           {"role_id": rid("High"), "min_points": 40}], guild=guild)
held = {rid("vRG HM")}
plain = tr.missing_for_next(guild, held, points, ranks)
withwr = tr.missing_for_next(guild, held, points, ranks, bonus=tr.wr_points({"current": 1}))
print(f"\n   clears only: {plain['score']} -> {tr.rank_name(plain['current'], guild)}"
      f" (needs {plain['needed']})")
print(f"   +1 record:   {withwr['score']} -> {tr.rank_name(withwr['current'], guild)}"
      f" (needs {withwr['needed']})")
assert plain["score"] == 25 and withwr["score"] == 40
assert tr.rank_name(withwr["current"], guild) == "High", "the bonus can carry a rank"
assert withwr["needed"] == 0

# --- storage ---
class Col:
    def __init__(s): s.docs = []
    def _m(s, q, d): return all(d.get(k) == v for k, v in q.items())
    def find(s, q): return [d for d in s.docs if s._m(q, d)]
    def find_one(s, q): return next((d for d in s.docs if s._m(q, d)), None)
    def update_one(s, q, u, upsert=False):
        doc = s.find_one(q)
        if doc is None: doc = dict(q); s.docs.append(doc)
        doc.update(u.get("$set", {}))
    def delete_one(s, q):
        doc = s.find_one(q)
        if doc: s.docs.remove(doc)


col = Col()
m = TrialRankManager(Col(), Col(), wr_collection=col)
m.set_wr(42, 7, "Mobi", 5, 0)
m.set_wr(42, 8, "Ellander", 0, 1)
holders = m.wr_all(42)
print("\n   holders:", {v["name"]: tr.wr_points(v) for v in holders.values()})
assert tr.wr_points(holders[7]) == 75 and tr.wr_points(holders[8]) == 5
assert m.wr_for(42, 7)["current"] == 5
m.set_wr(42, 7, "Mobi", 6, 0)               # the 6th
assert m.wr_for(42, 7)["current"] == 6, "counts are editable"
m.set_wr(42, 8, "Ellander", 0, 0)           # zeroed
assert m.wr_for(42, 8) is None, "zeroing both removes them from the list"
assert 8 not in m.wr_all(42)
assert m.wr_all(99) == {}, "records are per guild"
print("PASS")
