"""Health sampling, day bucketing, and that gaps never render as green."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import health

now = datetime.datetime.now(datetime.timezone.utc)

assert health.classify(50, True) == health.STATUS_OK
assert health.classify(2500, True) == health.STATUS_DEGRADED, "slow but answering"
assert health.classify(None, True) == health.STATUS_DOWN, "unmeasured is not healthy"
assert health.classify(50, False) == health.STATUS_DOWN
print("classify:", [(x, health.classify(x, True)) for x in (50, 2500, None)])

def sample(days_ago, status, n=1):
    at = now - datetime.timedelta(days=days_ago)
    return [{"at": at, "status": status} for _ in range(n)]

samples = (sample(0, health.STATUS_OK, 12)
           + sample(1, health.STATUS_OK, 10) + sample(1, health.STATUS_DEGRADED, 2)
           + sample(2, health.STATUS_OK, 6) + sample(2, health.STATUS_DOWN, 6))
bars = health.day_bars(samples, days=5)
for b in bars:
    print(f"   {b['day']}  state={str(b['state']):9} uptime="
          f"{'—' if b['uptime'] is None else format(b['uptime'], '.1f')}  n={b['samples']}")

assert len(bars) == 5
assert bars[-1]["state"] == health.STATUS_OK and bars[-1]["uptime"] == 100
assert bars[-2]["state"] == health.STATUS_DEGRADED, "any degraded sample downgrades the day"
assert bars[-3]["state"] == health.STATUS_DOWN, "a down sample marks the day down"
assert abs(bars[-3]["uptime"] - 50) < 0.01
# Days before any data: blank, never green.
assert bars[0]["state"] is None and bars[0]["samples"] == 0
assert bars[0]["uptime"] is None, "a day nobody measured has no uptime to claim"

# Uptime averages only the measured days, so an empty history says so.
pct = health.uptime_percent(bars)
print("measured uptime:", round(pct, 2))
assert health.uptime_percent([{"samples": 0, "uptime": None}]) is None

# Outage durations come straight from the count of bad samples.
bad_day = health.day_bars(sample(0, health.STATUS_DOWN, 12)
                          + sample(0, health.STATUS_DEGRADED, 6), days=1)[0]
print("bad day:", bad_day["state"], bad_day["down_minutes"], "down /",
      bad_day["degraded_minutes"], "degraded")
assert bad_day["down_minutes"] == 12 * health.SAMPLE_MINUTES
assert bad_day["degraded_minutes"] == 6 * health.SAMPLE_MINUTES
assert health.human_minutes(243) == "4 hrs 3 mins", health.human_minutes(243)
assert health.human_minutes(60) == "1 hr"
assert health.human_minutes(1) == "1 min"
assert health.human_minutes(0) == "0 mins"
print("durations:", [health.human_minutes(x) for x in (0, 1, 60, 243)])

assert health.human_duration(90) == "1m"
assert health.human_duration(3 * 3600 + 25 * 60) == "3h 25m"
assert health.human_duration(50 * 3600) == "2d 2h"
print("durations:", [health.human_duration(x) for x in (90, 12300, 180000)])


class FakeCol:
    def __init__(self): self.docs = []
    def create_index(self, *a, **k): pass
    def insert_one(self, d): self.docs.append(d)
    def find(self, q):
        class C(list):
            def sort(self, *a, **k): return self
        return C(self.docs)


col = FakeCol()
mon = health.HealthMonitor(col)
mon.record(latency_ms=42.0, connected=True, guilds=3, members=900)
mon.record(latency_ms=None, connected=False, guilds=3, members=900)
print("recorded:", [(d["status"], d["latency_ms"]) for d in col.docs])
assert [d["status"] for d in col.docs] == [health.STATUS_OK, health.STATUS_DOWN]
assert mon.uptime_seconds() >= 0
print("PASS")
