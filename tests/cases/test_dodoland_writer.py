"""DodoLand: activity is written behind the bot's back, and scores the same.

The cog only queues acts; a background writer adds up the ones that differ
only in amount and records each sum once. What scores must be exactly what
scoring them one at a time gave - past the daily cap and the per-partner cap
included - and nothing queued may be lost on a flush.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import parameters as dp  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.dodoland.writer import ActivityWriter  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

G, NIK, FOX, ROSA, ROOM, HALL = 7, 1, 2, 3, 500, 501
DAY = "2026-10-16"


def store():
    params = ParamManager(FakeCollection(), dp.DODOLAND_PARAMETERS)
    params.set(G, dp.daily_cap_key("message"), 20)
    params.set(G, dp.partner_cap_key("mention_given"), 3)
    params.set(G, dp.daily_cap_key("mention_given"), 5)
    params.set(G, "dodoland_write_batch_seconds", 60.0)   # the thread waits; flush() writes
    return ActivityStore(FakeCollection(), FakeCollection(), params)


# The same burst both ways: 30 messages in one room (cap 20), 6 in another,
# 8 mentions of one person (pair cap 3), 4 of another (daily cap 5 overall),
# a mass ping that makes no pair row, and a voice session.
acts = ([(NIK, "message", ROOM, None, True, 1)] * 30 + [(NIK, "message", HALL, None, True, 1)] * 6 +
        [(NIK, "mention_given", ROOM, FOX, True, 1)] * 8 + [(NIK, "mention_given", ROOM, ROSA, True, 1)] * 4 +
        [(FOX, "mention_given", ROOM, NIK, False, 1)] * 2 + [(ROSA, "voice_minute", 0, None, True, 45)])

one = store()
for user, metric, room, partner, link, amount in acts:
    one.record(G, user, metric, channel_id=room, partner_id=partner, link=link, day=DAY, amount=amount)

two = store()
writer = ActivityWriter(two)
for user, metric, room, partner, link, amount in acts:
    writer.put(G, user, metric, channel_id=room, partner_id=partner, link=link, day=DAY, amount=amount)
assert writer.pending() == len(acts)
writer.flush()
assert writer.pending() == 0 and writer.written == len(acts), "a flush left acts behind"
print(f"writer          {len(acts)} acts queued and written in {writer.batches} batch")


def rows(st):
    out = {}
    for row in st.rows(G):
        out[row["user_id"]] = ({k: v for k, v in (row.get("scored") or {}).items()},
                              {k: v for k, v in (row.get("acts") or {}).items()},
                              {str(c): dict(m) for c, m in (row.get("channels") or {}).items()})
    return out


a, b = rows(one), rows(two)
assert a == b, f"batched scoring differs:\n one at a time {a}\n batched       {b}"
assert a[NIK][0]["message"] == 20, a[NIK]            # the daily cap, across both rooms
assert a[NIK][0]["mention_given"] == 3, a[NIK]       # 3 of Fox (pair cap); the daily cap of 5 counts every try, so Rosa is too late
pairs = lambda st: sorted((r["a"], r["b"], r.get("n")) for r in st._pairs.find({}))  # noqa: E731
assert pairs(one) == pairs(two), "the social graph differs"
print("writer          batched acts score exactly as one at a time, past both caps")

# The thread writes on its own, without a flush.
three = store()
three._params.set(G, "dodoland_write_batch_seconds", 0.0)
w3 = ActivityWriter(three)
w3.put(G, NIK, "message", channel_id=ROOM, day=DAY)
for _ in range(100):
    if w3.written:
        break
    time.sleep(0.02)
assert w3.written == 1 and rows(three)[NIK][0]["message"] == 1, "the background writer never wrote"
print("writer          the background thread writes by itself")

source = pathlib.Path("cogs/dodoland.py").read_text(encoding="utf-8")
assert "self.bot.dodoland.record(" not in source, "the cog still writes inside a Discord event"
assert source.count("writer_for(self.bot)") >= 2
print("cog             every act is queued, none written inside a Discord event")

print("PASS")
