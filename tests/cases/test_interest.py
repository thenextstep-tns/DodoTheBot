"""Prog interest: bucketing, thresholds, registry upsert, and the panel section."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from helpers import trial_ranks as tr
from helpers.trial_ranks import TrialRankManager
from web import routes


class Role:
    managed = False
    def __init__(self, rid, name): self.id, self.name, self.position = rid, name, 1
    def is_default(self): return False


class Member:
    bot = False
    def __init__(self, uid, name): self.id, self.display_name, self.name = uid, name, name
    roles = []


class Guild:
    id, name = 42, "ESO for Dodos"
    channels = []
    def __init__(self, roles, members): self.roles, self.members = roles, members
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)
    def get_member(self, uid): return next((m for m in self.members if m.id == uid), None)
    def get_channel(self, cid): return None


NAMES = ["vKA", "vKA HM", "vKA trifecta", "vDSR", "vDSR HM", "Master Angler"]
ROLES = {n: Role(100 + i, n) for i, n in enumerate(NAMES)}
rid = lambda n: ROLES[n].id
members = [Member(1000 + i, f"player{i}") for i in range(14)]
guild = Guild(list(ROLES.values()), members)

CONFIG = {
    "trials": [
        {"name": "vKA", "slots": {"veteran": rid("vKA"), "full_hm": rid("vKA HM"),
                                  "trifecta": rid("vKA trifecta")}},
        {"name": "vDSR", "slots": {"veteran": rid("vDSR"), "full_hm": rid("vDSR HM")}},
    ],
    "points": {}, "ranks": [],
}

# --- thresholds ---
assert [tr.interest_level(n) for n in (0, 5)] == [tr.LEVEL_COLD] * 2
assert [tr.interest_level(n) for n in (6, 9)] == [tr.LEVEL_WARM] * 2
assert [tr.interest_level(n) for n in (10, 12, 20)] == [tr.LEVEL_READY] * 3
print("bands:", [(n, tr.interest_level(n)) for n in (0, 5, 6, 9, 10, 12)])

# --- bucketing: one person wanting a raid's HM *and* trifecta counts once ---
now = datetime.datetime.now(datetime.timezone.utc)
rows = [{"user_id": 1000, "name": "player0", "at": now,
         "role_ids": [rid("vKA HM"), rid("vKA trifecta"), rid("Master Angler")]}]
buckets = {b["name"]: b for b in tr.interest_buckets(guild, CONFIG, rows)}
assert buckets["vKA"]["count"] == 1, buckets["vKA"]["count"]
assert "Master Angler" not in buckets,     "a standalone achievement is not something a group progs for"
print("one person, two vKA roles ->", {k: v["count"] for k, v in buckets.items()})

# --- a realistic spread, busiest first ---
rows = []
for i, member in enumerate(members):
    wanted = [rid("vKA HM")] if i < 11 else []
    if i < 7:
        wanted.append(rid("vDSR HM"))
    if i < 3:
        wanted.append(rid("Master Angler"))
    if wanted:
        rows.append({"user_id": member.id, "name": member.display_name, "at": now,
                     "role_ids": wanted})
buckets = tr.interest_buckets(guild, CONFIG, rows)
print("spread:", [(b["name"], b["count"], b["level"]) for b in buckets])
assert [b["name"] for b in buckets] == ["vKA", "vDSR"],     "busiest first, and achievements are not raids"
assert buckets[0]["level"] == tr.LEVEL_READY and buckets[0]["count"] == 11
assert buckets[1]["level"] == tr.LEVEL_WARM and buckets[1]["count"] == 7
assert len(buckets) == 2

# --- registry: one row per person, latest press wins, first_at preserved ---
class FakeCol:
    def __init__(self): self.docs = []
    def create_index(self, key, **kw): pass
    def _m(self, q, d):
        for k, v in q.items():
            if isinstance(v, dict) and "$gte" in v:      # the TTL cutoff
                if d.get(k) is None or d[k] < v["$gte"]:
                    return False
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
        doc = self.find_one(q)
        if doc is None:
            doc = dict(q); doc.update(u.get("$setOnInsert", {})); self.docs.append(doc)
        doc.update(u.get("$set", {}))
    def delete_one(self, q):
        doc = self.find_one(q)
        if doc: self.docs.remove(doc)

col = FakeCol()
mgr = TrialRankManager(FakeCol(), FakeCol(), interest_collection=col)
mgr.record_interest(42, 1000, "player0", [rid("vKA HM")])
first = col.docs[0]["first_at"]
mgr.record_interest(42, 1000, "player0", [rid("vDSR HM")])
assert len(col.docs) == 1, "pressing twice is still one person"
assert col.docs[0]["role_ids"] == [rid("vDSR HM")], "latest press replaces stale wishes"
assert col.docs[0]["first_at"] == first, "but the date they first spoke up is kept"
assert len(mgr.interest_rows(42)) == 1
mgr.clear_interest(42, 1000)
assert mgr.interest_rows(42) == []
print("registry: upsert + first_at OK")

# --- the panel section ---
class Mgr:
    def get(self, gid): return CONFIG
    def interest_rows(self, gid, limit=1000): return rows
html = routes._interest_html(type("B", (), {"trial_ranks": Mgr()})(), guild, CONFIG)
for token in ("lvl-ready", "lvl-warm", "11/12", "7/12", "pip on"):
    assert token in html, token
# The only cold bucket was the achievement, which is no longer a raid at all.
assert "lvl-cold" not in html and "Master Angler" not in html
assert html.count('<span class="pip on"></span>') == 11 + 7, "pips match the counts"
assert "progclear" in html and "progneeds" in html, "per-clear breakdown rendered"
print("panel section OK")

empty = routes._interest_html(
    type("B", (), {"trial_ranks": type("M", (), {
        "get": lambda s, g: CONFIG, "interest_rows": lambda s, g, limit=1000: []})()})(),
    guild, CONFIG)
assert "Nobody has pressed" in empty
print("PASS")
