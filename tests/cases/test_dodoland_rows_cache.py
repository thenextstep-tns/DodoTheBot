"""DodoLand: the map's activity rows are read once, and nobody waits on a refresh.

A map asks for a dozen town drawings at once, and each needs the whole window of
activity (about 20,000 rows, over the internet from where the panel runs). With
nothing cached the callers that arrive together share one read; once the cache
is older than its freshness the old rows keep being served while one
background read replaces them.
"""
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from helpers.dodoland import standing  # noqa: E402


class Params:
    def __init__(self):
        self.values = {"dodoland_rows_cache_s": 60, "dodoland_rows_stale_s": 1800}

    def get(self, gid, key):
        return self.values[key]


class Store:
    def __init__(self):
        self.reads = 0
        self.gate = threading.Event()

    def rows(self, gid, since=None):
        self.reads += 1
        self.gate.wait(2)
        return [{"read": self.reads}]

    def pair_rows(self, gid, since=None):
        return []


params, store = Params(), Store()
standing._RECENT.clear()
got = []
threads = [threading.Thread(target=lambda: got.append(standing.recent_rows(store, params, 7, "d")))
           for _ in range(12)]
for t in threads:
    t.start()
time.sleep(0.2)
store.gate.set()
for t in threads:
    t.join()
assert store.reads == 1, f"{store.reads} reads for twelve callers arriving together"
assert len(got) == 12 and all(r[0][0]["read"] == 1 for r in got)
print("rows            twelve callers arriving together share one read")

# Older than its freshness: the old rows come back at once, one refresh runs.
key = (7, "d")
when, rows, pairs = standing._RECENT[key]
standing._RECENT[key] = (when - 120, rows, pairs)
store.gate.clear()
started = time.monotonic()
again = [standing.recent_rows(store, params, 7, "d") for _ in range(5)]
assert time.monotonic() - started < 0.5, "a caller waited on the refresh"
assert all(r[0][0]["read"] == 1 for r in again), "stale rows were not served"
store.gate.set()
for _ in range(50):
    if not standing._REFRESHING:
        break
    time.sleep(0.05)
assert store.reads == 2, f"{store.reads - 1} refreshes for five stale callers"
assert standing.recent_rows(store, params, 7, "d")[0][0]["read"] == 2, "the refresh did not land"
print("rows            stale rows are served at once while one refresh replaces them")

# Past the stale limit the caller waits for fresh rows, as it always did.
when, rows, pairs = standing._RECENT[key]
standing._RECENT[key] = (when - 4000, rows, pairs)
assert standing.recent_rows(store, params, 7, "d")[0][0]["read"] == 3
print("rows            past the stale limit the read is waited for")

# Map work is logged but does not message the server's owner.
src = pathlib.Path("web/dodoland/decor_api.py").read_text(encoding="utf-8") + \
    pathlib.Path("web/dodoland/terrain_api.py").read_text(encoding="utf-8") + \
    pathlib.Path("web/dodoland/forest_api.py").read_text(encoding="utf-8")
assert src.count("await _record_change(") == src.count("notify=False)"), \
    "placing on the map or painting it still sends a settings-changed message"
print("audit           placing and painting are logged, not messaged")

print("PASS")
