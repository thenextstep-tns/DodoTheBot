"""Presets keep their points, and their author keeps ownership."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers.trial_ranks import TrialRankManager


class FakeCol:
    def __init__(self): self.docs = []
    def create_index(self, *a, **k): pass
    def _m(self, q, d): return all(d.get(k) == v for k, v in q.items())
    def find(self, q, projection=None):
        class C(list):
            # Mongo really does sort; a no-op stub would let an ordering bug through.
            def sort(self, key, direction=1):
                return C(sorted(self, key=lambda d: d.get(key), reverse=direction < 0))
            def limit(self, n): return list(self)[:n]
        return C(d for d in self.docs if self._m(q, d))
    def find_one(self, q, p=None): return next((d for d in self.docs if self._m(q, d)), None)
    def update_one(self, q, u, upsert=False):
        clash = set(u.get("$set", {})) & set(u.get("$setOnInsert", {}))
        if clash:
            raise RuntimeError(
                "Updating the path " + sorted(clash)[0] + " would create a conflict")
        doc = self.find_one(q)
        if doc is None:
            doc = dict(q); doc.update(u.get("$setOnInsert", {})); self.docs.append(doc)
        doc.update(u.get("$set", {}))
    def delete_one(self, q):
        doc = self.find_one(q)
        if doc: self.docs.remove(doc)


col = FakeCol()
mgr = TrialRankManager(FakeCol(), FakeCol(), preset_collection=col)

RULESET = {"points": {"111": 25, "222": 5}, "ranks": [{"role_id": 9, "min_points": 10}],
           "trials": [{"name": "vRG", "slots": {"full_hm": 111}}]}
mgr.save_preset(42, "Season 1", RULESET, author_id=1000, author_name="Fox")
saved = mgr.preset(42, "Season 1")
print("stored keys:", sorted(saved))
# The reported bug: points must survive the round trip.
assert saved["points"] == {"111": 25, "222": 5}, saved["points"]
assert saved["ranks"] and saved["trials"], "ranks and trials stored too"
assert saved["author_id"] == 1000 and saved["author_name"] == "Fox"
created = saved["created_at"]

# Re-saving keeps the original author and creation date — authorship isn't
# reassigned by whoever edited last.
mgr.save_preset(42, "Season 1", {"points": {"111": 30}}, author_id=2000, author_name="Mido")
again = mgr.preset(42, "Season 1")
assert again["author_id"] == 1000, "author must not be reassigned on overwrite"
assert again["created_at"] == created
assert again["points"] == {"111": 30}, "content still updates"
print("author preserved across overwrite:", again["author_name"])

mgr.save_preset(42, "Experiment", RULESET, author_id=2000, author_name="Mido")
names = [p["name"] for p in mgr.presets(42)]
print("presets:", names)
assert names == ["Experiment", "Season 1"], "listed by name"
assert mgr.preset(42, "nope") is None
mgr.delete_preset(42, "Experiment")
assert [p["name"] for p in mgr.presets(42)] == ["Season 1"]
# A preset written before authorship existed belongs to nobody. The next person
# to save it takes it over — otherwise it would show owner controls to everyone,
# forever, which is exactly what went wrong on the live panel.
col.docs.append({"guild_id": 42, "name": "Legacy", "points": {"1": 1},
                 "ranks": [], "trials": []})
legacy = mgr.preset(42, "Legacy")
assert not legacy.get("author_id"), "starts unowned"
mgr.save_preset(42, "Legacy", RULESET, author_id=3000, author_name="Nik")
claimed = mgr.preset(42, "Legacy")
print("legacy preset claimed by:", claimed["author_name"], claimed["author_id"])
assert claimed["author_id"] == 3000 and claimed["author_name"] == "Nik"
# ...and once owned, it stays owned.
mgr.save_preset(42, "Legacy", RULESET, author_id=4000, author_name="Someone")
assert mgr.preset(42, "Legacy")["author_id"] == 3000, "ownership is not reassigned"
# Overwriting an *unowned* preset is the case that 500'd: the claim wrote
# author_id into $set while $setOnInsert still named it, which Mongo refuses.
# The stub above raises on that, so these three paths are the regression test.
seen = []
class Spy(FakeCol):
    def update_one(self, q, u, upsert=False):
        seen.append((set(u.get("$set", {})), set(u.get("$setOnInsert", {}))))
        return super().update_one(q, u, upsert)

spy = Spy()
m2 = TrialRankManager(FakeCol(), FakeCol(), preset_collection=spy)
m2.save_preset(7, "New", RULESET, author_id=1, author_name="A")          # insert
spy.docs.append({"guild_id": 7, "name": "Orphan", "points": {}})          # pre-authorship
m2.save_preset(7, "Orphan", RULESET, author_id=2, author_name="B")        # claim
m2.save_preset(7, "New", RULESET, author_id=1, author_name="A")           # plain overwrite
for setf, insf in seen:
    assert not (setf & insf), f"$set and $setOnInsert both name {setf & insf}"
print("no $set/$setOnInsert overlap on insert, claim or overwrite")
assert spy.find_one({"name": "Orphan"})["author_id"] == 2
print("PASS")
