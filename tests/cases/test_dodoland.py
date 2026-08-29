"""DodoLand P0: intake rules, guild scoping, and the caps that stop farming.

Every assertion here protects something that would be invisible if it broke.
A cap that silently stops working looks exactly like a popular person, and a
guild filter that silently stops working looks exactly like a busy server.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import intake, metrics  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

GUILD, OTHER_GUILD = 111, 222
NIK, FOX, ROSA = 1, 2, 3
CHANNEL = 900


def store_with(**overrides):
    params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
    for key, value in overrides.items():
        params.set(GUILD, key, value)
    return ActivityStore(FakeCollection(), FakeCollection(), params), params


# --------------------------------------------------------------------------- #
#  Every metric's knobs exist, because they are generated rather than written
# --------------------------------------------------------------------------- #
keys = {spec["key"] for spec in dodo_params.DODOLAND_PARAMETERS}
for metric in metrics.METRICS:
    assert dodo_params.weight_key(metric.key) in keys, f"{metric.key} has no weight knob"
    assert dodo_params.daily_cap_key(metric.key) in keys, f"{metric.key} has no daily cap"
    assert dodo_params.channels_key(metric.key) in keys, f"{metric.key} has no channel list"
    if metric.is_social:
        assert dodo_params.partner_cap_key(metric.key) in keys, \
            f"social metric {metric.key} has no per-person cap"
assert len(keys) == len(dodo_params.DODOLAND_PARAMETERS), "duplicate parameter key"
print(f"parameters      {len(metrics.METRICS)} metrics, every knob generated, no duplicates")

# Every metric resolves to a complete, renderable setup: nothing half-configured
# can reach the panel, because the panel builds its blocks from this call.
_probe = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
for metric in metrics.METRICS:
    setup = dodo_params.metric_setup(_probe, GUILD, metric.key)
    assert set(setup) >= {"key", "label", "description", "kind", "weight",
                          "daily_cap", "partner_cap", "channels", "backfill"}, setup
    assert (setup["partner_cap"] is None) != metric.is_social
print("parameters      every metric resolves to a complete setup for the panel")


# --------------------------------------------------------------------------- #
#  Intake: what a message is worth
# --------------------------------------------------------------------------- #
acts = intake.acts_from_message(NIK, "hey <@2> look at this", channel_id=CHANNEL)
kinds = sorted((a.metric, a.user_id, a.partner_id) for a in acts)
assert kinds == [("mention_given", NIK, FOX), ("mention_received", FOX, NIK),
                 ("message", NIK, None)], kinds
print("intake          a message naming one person credits both sides")

# A role ping is not a person. If it scored, one @Members would outweigh a year.
assert intake.mentioned_ids("<@&940276564925513818> raid tonight") == []
assert intake.mentioned_ids("@everyone") == []
print("intake          role pings and @everyone reach nobody")

# The same person twice in one message is one mention.
assert intake.mentioned_ids("<@2> and <@!2> again") == [FOX]
print("intake          repeating a name in one message is one mention")

# Short messages are not currency, and a message that is only a ping is not a
# free point: length is measured on the raw text.
assert not any(a.metric == "message" for a in
               intake.acts_from_message(NIK, "k", channel_id=CHANNEL))
print("intake          'k' is not currency")

# Naming yourself is the cheapest farm there is.
selfnamed = intake.acts_from_message(NIK, "<@1> hello me", channel_id=CHANNEL)
assert [a.metric for a in selfnamed] == ["message"]
assert len(intake.acts_from_message(NIK, "<@1> hello me", channel_id=CHANNEL,
                                    count_self=True)) == 3
print("intake          self-mentions score only when explicitly allowed")

# The mention ceiling is a cost ceiling and it holds.
crowd = " ".join(f"<@{i}>" for i in range(10, 40))
assert len([a for a in intake.acts_from_message(NIK, crowd, channel_id=CHANNEL)
            if a.metric == "mention_given"]) == 5
print("intake          one message can credit at most the configured mentions")

# Channel policy: empty tracked list means everywhere, ignored always wins.
assert intake.counts_channel(CHANNEL, tracked=[], ignored=[])
assert not intake.counts_channel(CHANNEL, tracked=[], ignored=[CHANNEL])
assert not intake.counts_channel(CHANNEL, tracked=[123], ignored=[])
assert not intake.counts_channel(CHANNEL, tracked=[CHANNEL], ignored=[CHANNEL])
print("intake          empty tracked list means everywhere; ignored always wins")


# --------------------------------------------------------------------------- #
#  The per-person cap is the anti-farm design
# --------------------------------------------------------------------------- #
store, _ = store_with(dodoland_pcap_mention_received=3)
scored = [store.record(GUILD, NIK, "mention_received", channel_id=CHANNEL, partner_id=FOX)
          for _ in range(10)]
assert scored[:3] == [True, True, True], scored
assert not any(scored[3:]), "the per-person cap stopped holding"
print("caps            one friend can score you three times a day, not ten")

# ...and it is per person, so the fourth from somebody *else* still counts.
assert store.record(GUILD, NIK, "mention_received", channel_id=CHANNEL, partner_id=ROSA)
print("caps            a different person still scores: farming needs more people")

# A capped act is still on the record. A cap that silently eats data reads as a
# bug to the person it happens to.
row = store.rows(GUILD, user_id=NIK)[0]
assert row["acts"]["mention_received"] == 11, row["acts"]
assert row["scored"]["mention_received"] == 4, row["scored"]
print("caps            11 happened, 4 scored, and both are on the record")

# The pair row counts the whole evening, capped or not: it is the social graph.
assert store.partners(GUILD, NIK) == {FOX: 10, ROSA: 1}
print("graph           pair rows keep every exchange, so the map sees real ties")

# The daily cap is independent of the per-person one.
store, _ = store_with(dodoland_cap_message=3)
assert [store.record(GUILD, NIK, "message", channel_id=CHANNEL) for _ in range(5)] \
    == [True, True, True, False, False]
print("caps            the daily cap holds independently of the per-person cap")


# --------------------------------------------------------------------------- #
#  Multiserver: no read is ever unscoped
# --------------------------------------------------------------------------- #
store, _ = store_with()
store.record(GUILD, NIK, "message", channel_id=CHANNEL)
store.record(OTHER_GUILD, NIK, "message", channel_id=CHANNEL)
assert store.totals(GUILD, NIK) == {"message": 1}
assert store.totals(OTHER_GUILD, NIK) == {"message": 1}
assert len(store.rows(GUILD)) == 1, "a guild read saw another server's rows"
print("scoping         two servers, one person, two separate towns")

for call in (lambda: store.totals(0, NIK),
             lambda: store.rows(None),
             lambda: store.partners("", NIK)):
    try:
        call()
    except ValueError:
        continue
    raise AssertionError("an unscoped DodoLand read was allowed")
print("scoping         an unscoped read raises rather than returning everything")

# Channels are recorded per metric, which is what lets a building be defined as
# "these channels" later without a second pass over anything.
store, _ = store_with()
store.record(GUILD, NIK, "message", channel_id=CHANNEL)
store.record(GUILD, NIK, "mention_received", channel_id=777, partner_id=FOX)
assert store.channel_totals(GUILD, NIK) == {CHANNEL: {"message": 1},
                                            777: {"mention_received": 1}}
print("buildings       scored acts are split by channel, ready for per-building feeds")

# A social act with no partner is a programming error, not a silent zero.
try:
    store.record(GUILD, NIK, "mention_received", channel_id=CHANNEL)
    raise AssertionError("a social act without a partner was accepted")
except ValueError:
    pass
try:
    store.record(GUILD, NIK, "no_such_metric", channel_id=CHANNEL)
    raise AssertionError("an unknown metric was accepted")
except KeyError:
    pass
print("safety          missing partners and unknown metrics raise, never pass quietly")



# --------------------------------------------------------------------------- #
#  Forward-only metrics: what a richer message is worth
# --------------------------------------------------------------------------- #
from helpers.dodoland import invites as invite_rules  # noqa: E402
from helpers.dodoland.voice import VoiceTracker  # noqa: E402

rich = intake.acts_from_message(
    NIK, "look at this <@3>", channel_id=CHANNEL,
    has_image=True, reply_to=FOX, thread_owner=ROSA,
)
got = {(a.metric, a.user_id, a.partner_id) for a in rich}
assert ("image", NIK, None) in got
assert ("reply_given", NIK, FOX) in got and ("reply_received", FOX, NIK) in got
assert ("thread_reply_given", NIK, ROSA) in got
assert ("thread_reply_received", ROSA, NIK) in got
print("intake          image, reply and thread-owner credit both sides")

# The backfill passes none of that context and must produce exactly the three
# archivable acts, or the rebuilt history is a different economy.
old = intake.acts_from_message(NIK, "hey <@2> there", channel_id=CHANNEL)
assert {a.metric for a in old} == {"message", "mention_given", "mention_received"}
print("intake          the backfill path yields only the archivable acts")

# Replying to yourself or posting in your own thread is not a social act.
solo = intake.acts_from_message(NIK, "still me", channel_id=CHANNEL,
                                reply_to=NIK, thread_owner=NIK)
assert {a.metric for a in solo} == {"message"}
print("intake          answering yourself in your own thread reaches nobody")

# Welcoming is credited once against whoever did it, for people it reached.
welcome = intake.acts_from_message(NIK, "hi <@2> welcome!", channel_id=CHANNEL,
                                   newcomers={FOX})
assert [a for a in welcome if a.metric == "newcomer_welcomed"][0].partner_id == FOX
assert len([a for a in welcome if a.metric == "newcomer_welcomed"]) == 1
# Reaching the same newcomer by mention *and* reply is still one welcome.
both = intake.acts_from_message(NIK, "hi <@2>", channel_id=CHANNEL,
                                reply_to=FOX, newcomers={FOX})
assert len([a for a in both if a.metric == "newcomer_welcomed"]) == 1
print("intake          welcoming scores once per newcomer, not once per mechanism")


# --------------------------------------------------------------------------- #
#  Bulk amounts clip at the cap instead of falling off it
# --------------------------------------------------------------------------- #
store, _ = store_with(dodoland_cap_voice_minute=60)
assert store.record(GUILD, NIK, "voice_minute", channel_id=CHANNEL, amount=45) == 45
assert store.record(GUILD, NIK, "voice_minute", channel_id=CHANNEL, amount=30) == 15
assert store.record(GUILD, NIK, "voice_minute", channel_id=CHANNEL, amount=10) == 0
row = store.rows(GUILD, user_id=NIK)[0]
assert row["acts"]["voice_minute"] == 85 and row["scored"]["voice_minute"] == 60
print("amounts         a session crossing the cap still scores the part under it")


# --------------------------------------------------------------------------- #
#  Voice: alone earns nothing, company is measured in overlap
# --------------------------------------------------------------------------- #
voice = VoiceTracker()
voice.join(GUILD, NIK, 500, now=0)
credit = voice.leave(GUILD, NIK, now=3600)
assert credit.minutes == 0 and credit.partners == {}
print("voice           an hour alone in a channel is worth nothing")

voice = VoiceTracker()
voice.join(GUILD, NIK, 500, now=0)
voice.join(GUILD, FOX, 500, now=600)        # arrives ten minutes later
nik = voice.leave(GUILD, NIK, now=1800)     # leaves at thirty
assert nik.minutes == 20, nik.minutes       # only the shared twenty count
assert nik.partners == {FOX: 20}
fox = voice.leave(GUILD, FOX, now=2400)
assert fox.partners == {NIK: 20}, fox.partners
print("voice           minutes are the time with company, and both sides agree")

# Two people in a channel at different times shared nothing.
voice = VoiceTracker()
voice.join(GUILD, NIK, 500, now=0)
voice.leave(GUILD, NIK, now=600)
voice.join(GUILD, FOX, 500, now=1200)
assert voice.leave(GUILD, FOX, now=1800).partners == {}
print("voice           passing through the same room is not sharing it")


# --------------------------------------------------------------------------- #
#  Invites: an unattributed join beats a misattributed one
# --------------------------------------------------------------------------- #
owners = {"aaa": NIK, "bbb": FOX}
assert invite_rules.recruiter_for({"aaa": 4, "bbb": 1}, {"aaa": 5, "bbb": 1}, owners, ROSA) == NIK
print("invites         the invite whose count moved names the recruiter")

# Two moved at once: naming one of them would credit the wrong person for the
# most heavily weighted act in the system.
assert invite_rules.recruiter_for({"aaa": 4, "bbb": 1}, {"aaa": 5, "bbb": 2}, owners, ROSA) is None
# An invite that did not exist before (vanity URL, or created between fetches).
assert invite_rules.recruiter_for({}, {"ccc": 1}, {"ccc": NIK}, ROSA) is None
# Nothing moved at all.
assert invite_rules.recruiter_for({"aaa": 4}, {"aaa": 4}, owners, ROSA) is None
# Inviting yourself back is what an alt account looks like.
assert invite_rules.recruiter_for({"aaa": 4}, {"aaa": 5}, owners, NIK) is None
print("invites         ties, vanity links and self-invites credit nobody")


print("PASS")
