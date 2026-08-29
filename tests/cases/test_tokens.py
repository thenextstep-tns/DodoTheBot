"""Capability tokens: hashed at rest, rotatable, expirable, never guessable."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers.share_tokens import ShareTokenStore, KIND_PUBLIC, KIND_USER, TOKEN_BYTES


class Col:
    def __init__(self): self.docs = []
    def create_index(self, *a, **k): pass
    def insert_one(self, d): self.docs.append(dict(d))
    def find_one(self, q): return next((d for d in self.docs
                                        if all(d.get(k) == v for k, v in q.items())), None)
    def delete_many(self, q):
        keep = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
        n = len(self.docs) - len(keep)
        self.docs = keep
        return type("R", (), {"deleted_count": n})()


col = Col()
store = ShareTokenStore(col)
token = store.issue(42)
print("token length:", len(token))
assert len(token) >= 40, "needs real entropy"

# Nothing recoverable is stored.
stored = col.docs[0]
assert token not in str(stored), "the token itself must never be at rest"
assert len(stored["token_hash"]) == 64 and stored["token_hash"] != token
print("stored keys:", sorted(stored))

assert store.resolve(42, token) is not None, "the real token resolves"
assert store.resolve(42, token + "x") is None, "a near miss does not"
assert store.resolve(42, "") is None and store.resolve(42, None) is None
assert store.resolve(99, token) is None, "a token is bound to its guild"
assert store.resolve(42, token, kind=KIND_USER) is None, "and to its kind"

# Rotating kills the old link.
second = store.issue(42)
assert second != token
assert store.resolve(42, token) is None, "rotation must revoke the previous link"
assert store.resolve(42, second) is not None
assert len(col.docs) == 1, "rotation replaces rather than accumulates"

# Per-user tokens live alongside the public one, and revoke independently.
u1 = store.issue(42, kind=KIND_USER, user_id=7, replace=False)
u2 = store.issue(42, kind=KIND_USER, user_id=8, replace=False)
assert store.resolve(42, u1, kind=KIND_USER) and store.resolve(42, u2, kind=KIND_USER)
store.revoke_all(42, kind=KIND_USER, user_id=7)
assert store.resolve(42, u1) is None and store.resolve(42, u2) is not None, \
    "one recipient's link is revocable without touching anyone else's"
assert store.resolve(42, second) is not None, "and without touching the public one"
print("public + per-user tokens coexist and revoke independently")

# Expiry is enforced on read, not only by Mongo's sweeper.
past = store.issue(42, kind=KIND_USER, user_id=9, ttl_days=1, replace=False)
doc = next(d for d in col.docs if d.get("user_id") == 9)
doc["expires_at"] = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
assert store.resolve(42, past) is None, "an expired token must not be served"
naive = store.issue(42, kind=KIND_USER, user_id=10, ttl_days=1, replace=False)
d2 = next(d for d in col.docs if d.get("user_id") == 10)
d2["expires_at"] = d2["expires_at"].replace(tzinfo=None)   # Mongo hands back naive
assert store.resolve(42, naive) is not None, "a naive stored date must not crash the compare"
print("expiry honoured on read, tz-naive storage tolerated")

assert store.active(42) is not None
store.revoke_all(42, kind=KIND_PUBLIC)
assert store.active(42) is None and store.resolve(42, second) is None
print("PASS")
