"""Interest lapses after 60 days, and pressing again restarts the clock."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers.trial_ranks import TrialRankManager, INTEREST_TTL_DAYS

now = datetime.datetime.now(datetime.timezone.utc)


class FakeCol:
    def __init__(self): self.docs, self.indexes = [], []
    def create_index(self, key, **kw): self.indexes.append((key, kw))
    def _m(self, q, d):
        for k, v in q.items():
            if isinstance(v, dict) and "$gte" in v:
                if d.get(k) is None or d[k] < v["$gte"]: return False
            elif d.get(k) != v:
                return False
        return True
    def find(self, q, projection=None):
        class C(list):
            def sort(self, *a, **k): return self
            def limit(self, n): return list(self)[:n]
        return C(d for d in self.docs if self._m(q, d))
    def find_one(self, q, p=None): return next((d for d in self.docs if self._m(q, d)), None)
    def update_one(self, q, u, upsert=False):
        doc = next((d for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)
        if doc is None:
            doc = dict(q); doc.update(u.get("$setOnInsert", {})); self.docs.append(doc)
        doc.update(u.get("$set", {}))
    def delete_one(self, q): pass


col = FakeCol()
mgr = TrialRankManager(FakeCol(), FakeCol(), interest_collection=col)
mgr.record_interest(42, 1, "fresh", [100])
# A TTL index is requested so the collection doesn't grow forever.
assert col.indexes, "no TTL index requested"
key, kw = col.indexes[0]
assert key == "at" and kw["expireAfterSeconds"] == INTEREST_TTL_DAYS * 86400, col.indexes
print("TTL index:", col.indexes[0])

# Hand-age two rows either side of the window.
col.docs.append({"guild_id": 42, "user_id": 2, "name": "stale", "role_ids": [100],
                 "at": now - datetime.timedelta(days=INTEREST_TTL_DAYS + 1)})
col.docs.append({"guild_id": 42, "user_id": 3, "name": "justinside", "role_ids": [100],
                 "at": now - datetime.timedelta(days=INTEREST_TTL_DAYS - 1)})
live = {r["name"] for r in mgr.interest_rows(42)}
print("live:", live)
assert live == {"fresh", "justinside"}, live
assert "stale" not in live, "read filter must drop it even before the TTL sweep runs"

# Pressing again restarts the clock.
mgr.record_interest(42, 2, "stale", [100])
assert "stale" in {r["name"] for r in mgr.interest_rows(42)}, "re-press should revive"
print("after re-press:", {r["name"] for r in mgr.interest_rows(42)})

# The index is only requested once, not on every call.
before = len(col.indexes)
for _ in range(5):
    mgr.interest_rows(42)
assert len(col.indexes) == before, "index creation should be a one-off"
print("PASS")
