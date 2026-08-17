"""Prog interest drops away as it is earned."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import trial_ranks as tr
from helpers.trial_ranks import TrialRankManager

# vRG: veteran -> Bahsei HM (partial) -> full HM -> trifecta
V, P, F, T, OTHER, ACH = 1, 2, 3, 4, 5, 6
TRIALS = [{"name": "vRG", "slots": {"veteran": V, "partial1": P, "full_hm": F, "trifecta": T}},
          {"name": "vDSR", "slots": {"veteran": OTHER}}]

cases = [
    ("holds the very thing they wanted", [F], [F], {F}),
    ("wanted the HM, came back with the trifecta", [F], [T], {F}),
    ("wanted the partial, got the full HM", [P], [F], {P}),
    ("wanted the trifecta, only has the HM", [T], [F], set()),
    ("wants another trial entirely", [OTHER], [T], set()),
    ("several at once", [P, F, OTHER], [T], {P, F}),
    ("an achievement they now hold", [ACH], [ACH], {ACH}),
    ("an achievement they don't", [ACH], [T], set()),
]
for label, wanted, held, expect in cases:
    got = tr.stale_interest(wanted, held, TRIALS)
    print(f"   {label:42} -> drop {sorted(got) or '-'}")
    assert got == expect, (label, got, expect)

# The row shrinks, and disappears once nothing is left.
class Col:
    def __init__(s): s.docs = []
    def create_index(s, *a, **k): pass
    def _m(s, q, d): return all(d.get(k) == v for k, v in q.items()
                                if not isinstance(v, dict))
    def find(s, q, p=None):
        class C(list):
            def sort(s2, *a, **k): return s2
            def limit(s2, n): return list(s2)[:n]
        return C(d for d in s.docs if s._m(q, d))
    def find_one(s, q): return next((d for d in s.docs if s._m(q, d)), None)
    def update_one(s, q, u, upsert=False):
        d = s.find_one(q)
        if d is None:
            d = dict(q); d.update(u.get("$setOnInsert", {})); s.docs.append(d)
        d.update(u.get("$set", {}))
    def delete_one(s, q):
        d = s.find_one(q)
        if d: s.docs.remove(d)

col = Col()
m = TrialRankManager(Col(), Col(), interest_collection=col)
m.record_interest(42, 7, "Fox", [P, F, OTHER])
assert m.drop_interest_roles(42, 7, {P, F}) == 2
assert col.docs[0]["role_ids"] == [OTHER], col.docs[0]["role_ids"]
print("\n   row shrinks to:", col.docs[0]["role_ids"])
assert m.drop_interest_roles(42, 7, {P}) == 0, "dropping what is already gone is a no-op"
assert m.drop_interest_roles(42, 7, {OTHER}) == 1
assert col.docs == [], "the row goes with the last want"
assert m.drop_interest_roles(42, 999, {F}) == 0, "somebody with no row is fine"
assert m.drop_interest_roles(42, 7, []) == 0
print("   row removed once nothing is left")
print("PASS")
