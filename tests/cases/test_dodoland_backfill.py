"""DodoLand: rebuilding history from the message archive.

Three properties matter more than the arithmetic, and all three fail silently
if they break, so each is asserted directly:

* a rebuilt day is worth exactly what a live day is worth;
* running it twice does not double anything;
* it never writes over a day the listener owns.
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bson import ObjectId  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import backfill  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland.store import ActivityStore, allowance  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

GUILD = 42
NIK, FOX, ROSA = 1, 2, 3
LIB, SPAM = 900, 901


def fresh():
    params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
    return ActivityStore(FakeCollection(), FakeCollection(), params), params


def archived(author, text, channel, when):
    """An archive row, dated the way the real ones are: through the ObjectId."""
    return {"_id": ObjectId.from_datetime(when), "author": author,
            "channel": channel, "message": text, "bot": False}


DAY_ONE = datetime.datetime(2025, 3, 4, 12, 0, tzinfo=datetime.timezone.utc)
DAY_TWO = DAY_ONE + datetime.timedelta(days=1)


# --------------------------------------------------------------------------- #
#  The shared capping decision
# --------------------------------------------------------------------------- #
assert allowance(0, 1, 0) == 1, "a zero cap means uncapped"
assert allowance(38, 5, 40) == 2, "a bulk amount clips at the cap"
assert allowance(40, 5, 40) == 0
print("caps            the live path and the rebuild share one capping function")


# --------------------------------------------------------------------------- #
#  A rebuilt day is worth what a live day is worth
# --------------------------------------------------------------------------- #
docs = [archived(NIK, "hello <@2> how are you", LIB, DAY_ONE),
        archived(NIK, "a second message here", LIB, DAY_ONE),
        archived(FOX, "replying to <@1> now", LIB, DAY_ONE)]

store, params = fresh()
plan = backfill.build_plan(iter(docs), params=params, guild_id=GUILD,
                           channel_ids=[LIB, SPAM], before="2099-01-01")
store.replace_days(GUILD, plan.activity_rows(), plan.pair_rows())
rebuilt = store.totals(GUILD, NIK)

# The same three messages, played through the live listener's own path.
live, _ = fresh()
for doc in docs:
    from helpers.dodoland import intake
    for act in intake.acts_from_message(doc["author"], doc["message"],
                                        channel_id=doc["channel"]):
        live.record(GUILD, act.user_id, act.metric, channel_id=act.channel_id,
                    partner_id=act.partner_id, day="2025-03-04")

assert rebuilt == live.totals(GUILD, NIK), (rebuilt, live.totals(GUILD, NIK))
assert store.channel_totals(GUILD, NIK) == live.channel_totals(GUILD, NIK)
assert store.partners(GUILD, NIK) == live.partners(GUILD, NIK)
print("parity          a rebuilt day scores identically to the same day counted live")


# --------------------------------------------------------------------------- #
#  Repeatable: twice is not double
# --------------------------------------------------------------------------- #
once = store.totals(GUILD, NIK)
plan_again = backfill.build_plan(iter(docs), params=params, guild_id=GUILD,
                                 channel_ids=[LIB, SPAM], before="2099-01-01")
store.replace_days(GUILD, plan_again.activity_rows(), plan_again.pair_rows())
assert store.totals(GUILD, NIK) == once, "running the rebuild twice doubled it"
assert len(store.rows(GUILD)) == 2, "the rebuild grew extra rows on a repeat"
print("repeatable      rebuilding twice writes the same numbers, never double")


# --------------------------------------------------------------------------- #
#  It never overwrites a day the listener owns
# --------------------------------------------------------------------------- #
store, params = fresh()
store.record(GUILD, NIK, "message", channel_id=LIB, day="2025-03-05")
boundary = store.first_day(GUILD)
assert boundary == "2025-03-05"

plan = backfill.build_plan(
    iter([archived(NIK, "old message here", LIB, DAY_ONE),
          archived(NIK, "same day as live", LIB, DAY_TWO)]),
    params=params, guild_id=GUILD, channel_ids=[LIB], before=boundary)
assert plan.messages == 1, "the rebuild reached into the listener's own days"
assert plan.last_day == "2025-03-04"
print("boundary        the rebuild stops before the listener's earliest day")


# --------------------------------------------------------------------------- #
#  It respects every setting the live path respects
# --------------------------------------------------------------------------- #
store, params = fresh()
params.set(GUILD, "dodoland_ignored_channels", [SPAM])
plan = backfill.build_plan(
    iter([archived(NIK, "a real message", LIB, DAY_ONE),
          archived(NIK, "bot spam channel", SPAM, DAY_ONE)]),
    params=params, guild_id=GUILD, channel_ids=[LIB, SPAM], before="2099-01-01")
assert plan.messages == 1 and plan.skipped == 1
print("settings        an ignored channel is skipped by the rebuild too")

# A channel that is not this guild's is somebody else's history.
plan = backfill.build_plan(
    iter([archived(NIK, "another server entirely", 55555, DAY_ONE)]),
    params=params, guild_id=GUILD, channel_ids=[LIB], before="2099-01-01")
assert plan.messages == 0 and not plan.activity
print("scoping         a channel outside this guild is never rebuilt into it")

# Per-metric channel lists apply as well.
store, params = fresh()
params.set(GUILD, "dodoland_ch_message", [SPAM])
plan = backfill.build_plan(
    iter([archived(NIK, "hello <@2> there", LIB, DAY_ONE)]),
    params=params, guild_id=GUILD, channel_ids=[LIB, SPAM], before="2099-01-01")
scored = plan.activity[(NIK, "2025-03-04")]["scored"]
assert "message" not in scored, scored
assert scored.get("mention_given") == 1
print("settings        a metric's own channel list is honoured by the rebuild")

# Caps hold across a day's worth of archive, per person and per partner.
store, params = fresh()
params.set(GUILD, "dodoland_pcap_mention_received", 2)
plan = backfill.build_plan(
    iter([archived(NIK, f"poke <@2> number {n}", LIB, DAY_ONE) for n in range(9)]),
    params=params, guild_id=GUILD, channel_ids=[LIB], before="2099-01-01")
fox = plan.activity[(FOX, "2025-03-04")]
assert fox["acts"]["mention_received"] == 9
assert fox["scored"]["mention_received"] == 2, fox["scored"]
print("caps            nine pokes from one person rebuild as nine acts, two scored")

# Only the three archivable metrics are ever produced. Nothing in the archive
# can imply a picture, a reply target or a voice session.
store, params = fresh()
plan = backfill.build_plan(
    iter([archived(NIK, "hello <@2> there", LIB, DAY_ONE)]),
    params=params, guild_id=GUILD, channel_ids=[LIB], before="2099-01-01")
produced = {metric for values in plan.activity.values() for metric in values["acts"]}
assert produced <= set(backfill.REBUILDABLE), produced
print("honesty         the rebuild invents nothing the archive never stored")

print("PASS")
