"""The chat cog end to end, with a fake Discord and a fake model.

The mind is covered by ``test_chat``; what this protects is the wiring around it.
Four things have to hold or the feature is either silent or ruinous: she answers
a ping, she answers a role ping, she never answers a bot, and a phrase she
notices but does not reply to still costs zero API calls while changing how she
feels.
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.fake_mongo import FakeCollection
import config_py
from helpers import parameters
from helpers.chat import router as router_model
from helpers.chat import state as state_model
from helpers.chat import triggers as trigger_model

# The cog reads and writes through the module-level handle, so swap it for a
# fake before importing the cog.
memories = FakeCollection()
config_py.memory = memories

import cogs.chat as chat_cog  # noqa: E402

chat_cog.config_py.memory = memories

GUILD_ID = 424242424242424242
CALLS = []


class FakeCompletion:
    def __init__(self, payload):
        message = type("M", (), {"content": json.dumps(payload)})()
        self.choices = [type("C", (), {"message": message})()]


class FakeClient:
    """Records every call and answers with a fixed JSON payload."""

    def __init__(self, payload):
        self.payload = payload
        outer = self

        class Completions:
            def create(self, **kwargs):
                CALLS.append(kwargs)
                return FakeCompletion(outer.payload)

        self.chat = type("Chat", (), {"completions": Completions()})()


class Role:
    def __init__(self, rid): self.id = rid


class User:
    def __init__(self, uid, name, bot=False):
        self.id, self.display_name, self.bot = uid, name, bot
        self.mention = f"<@{uid}>"


class Channel:
    def __init__(self, cid=7):
        self.id = cid
        self.sent = []

    async def send(self, content, **kwargs):
        self.sent.append(content)

    def typing(self):
        class Ctx:
            async def __aenter__(self): return None
            async def __aexit__(self, *a): return False
        return Ctx()


class Guild:
    def __init__(self, me):
        self.id, self.me, self.owner_id = GUILD_ID, me, 1


class Message:
    def __init__(self, author, content, *, guild, channel, mentions=(), roles=()):
        self.author, self.content, self.guild, self.channel = author, content, guild, channel
        self.mentions, self.role_mentions, self.reference = list(mentions), list(roles), None


class Vis:
    enabled = True
    def cog_enabled(self, gid, cog): return True
    def feature_active(self, gid, feature, cog): return self.enabled


class Bot:
    def __init__(self):
        self.user = User(999, "Dodo", bot=True)
        self.params = parameters.ParamManager(FakeCollection())
        self.visibility = Vis()
        self.chat_triggers = trigger_model.ChatTriggerManager(FakeCollection())
        self.config = {"owners": [1]}
        self.logger = type("L", (), {"debug": lambda *a: None, "warning": lambda *a: None})()


def build(payload=None, **params):
    """A cog with a fake model and the given per-server parameter overrides."""
    CALLS.clear()
    memories.docs.clear()
    bot = Bot()
    for key, value in params.items():
        bot.params.set(GUILD_ID, key, value)
    cog = chat_cog.Chat(bot)
    cog._client_for = lambda guild, author: FakeClient(
        payload or {"say": "hello", "felt": 0, "learned": None, "rumour": None})
    dodo_role = Role(555)
    bot.user.roles = [dodo_role]
    guild = Guild(bot.user)
    return cog, bot, guild, Channel(), dodo_role


run = asyncio.run
NOTHING = {"say": "", "felt": 0, "learned": None, "rumour": None}


# --------------------------------------------------------------------------- #
#  Being addressed
# --------------------------------------------------------------------------- #
cog, bot, guild, channel, dodo_role = build()
ada = User(1, "Ada")
run(cog.handle_message(Message(ada, "hi there", guild=guild, channel=channel,
                               mentions=[bot.user])))
assert channel.sent == ["hello"], f"a direct mention went unanswered: {channel.sent}"
assert len(CALLS) == 1, "a direct mention should cost exactly one call"
print("cog             a direct mention is answered")

cog, bot, guild, channel, dodo_role = build()
run(cog.handle_message(Message(ada, "hey birds", guild=guild, channel=channel,
                               roles=[dodo_role])))
assert channel.sent == ["hello"], "a ping of her role went unanswered"
print("cog             a ping of a role she wears is answered")

cog, bot, guild, channel, dodo_role = build(chat_respond_to_role_ping=False)
run(cog.handle_message(Message(ada, "hey birds", guild=guild, channel=channel,
                               roles=[dodo_role])))
assert channel.sent == [], "role pings should be ignorable per server"
print("cog             role pings can be switched off per server")

cog, bot, guild, channel, dodo_role = build()
other_bot = User(2, "Robot", bot=True)
run(cog.handle_message(Message(other_bot, "hi", guild=guild, channel=channel,
                               mentions=[bot.user])))
assert channel.sent == [] and CALLS == [], "answering another bot is how a loop starts"
print("cog             she never answers another bot")

cog, bot, guild, channel, dodo_role = build()
bot.params.set(GUILD_ID, "chat_ignored_channels", [channel.id])
run(cog.handle_message(Message(ada, "hi", guild=guild, channel=channel, mentions=[bot.user])))
assert channel.sent == [], "an ignored channel must stay quiet even for a direct ping"
print("cog             ignored channels are honoured")

# Answering a ping in isolation is the difference between a conversation and a
# series of unrelated statements.
cog, bot, guild, channel, dodo_role = build(chat_user_cooldown_seconds=0)
bo = User(3, "Bo")
run(cog.handle_message(Message(ada, "we should raid tonight", guild=guild, channel=channel)))
run(cog.handle_message(Message(bo, "i can heal", guild=guild, channel=channel)))
run(cog.handle_message(Message(ada, "what do you think?", guild=guild, channel=channel,
                               mentions=[bot.user])))
system = CALLS[-1]["messages"][0]["content"]
assert "Ada: we should raid tonight" in system and "Bo: i can heal" in system, \
    f"she answered the ping without reading the room:\n{system}"
assert system.count("what do you think?") == 0, \
    "the message she is answering should not also be pasted in as context"
print("cog             an ordinary reply sees the conversation it is part of")


# --------------------------------------------------------------------------- #
#  Noticing without speaking
# --------------------------------------------------------------------------- #
cog, bot, guild, channel, dodo_role = build()
bot.chat_triggers.create(GUILD_ID, {
    trigger_model.K_NAME: "insult", trigger_model.K_PATTERNS: ["bad bot"],
    trigger_model.K_AFFINITY: -8, trigger_model.K_GRUDGE: 0.6, trigger_model.K_CHANCE: 0.0,
})
# Her arbitrary opinion of a stranger is the baseline here, not plain neutral.
tuning = cog._state_tuning(guild)
before = state_model.from_document(None, "1", tuning).affinity
run(cog.handle_message(Message(ada, "bad bot", guild=guild, channel=channel)))
assert channel.sent == [] and CALLS == [], "chance 0 must not speak or spend"
stored = state_model.from_document(memories.find_one({"user_id": "1"}), "1", tuning)
assert stored.affinity < before, f"the insult should still land ({stored.affinity} vs {before})"
assert stored.top_grudge() is not None, "she should be holding it against them"
print("cog             a noticed phrase costs nothing and still changes how she feels")

# ...and it shows up in the next reply she does make.
run(cog.handle_message(Message(ada, "hello again", guild=guild, channel=channel,
                               mentions=[bot.user])))
assert len(CALLS) == 1
system = CALLS[0]["messages"][0]["content"]
assert "holding against them" in system, f"the grudge never reached the prompt:\n{system}"
print("cog             the grudge surfaces in the next reply she gives")


# --------------------------------------------------------------------------- #
#  Canned replies and the daily cap
# --------------------------------------------------------------------------- #
cog, bot, guild, channel, dodo_role = build()
bot.chat_triggers.create(GUILD_ID, {
    trigger_model.K_NAME: "banter", trigger_model.K_PATTERNS: ["no u"],
    trigger_model.K_CHANCE: 1.0, trigger_model.K_REFLEX: ["NO U TIMES INFINITY"],
    trigger_model.K_REFLEX_CHANCE: 1.0,
})
run(cog.handle_message(Message(ada, "no u", guild=guild, channel=channel)))
assert channel.sent == ["NO U TIMES INFINITY"], channel.sent
assert CALLS == [], "a canned line must not reach the model"
print("cog             a canned trigger line answers without an API call")

cog, bot, guild, channel, dodo_role = build(chat_daily_call_cap=1)
run(cog.handle_message(Message(ada, "one", guild=guild, channel=channel, mentions=[bot.user])))
run(cog.handle_message(Message(ada, "two", guild=guild, channel=channel, mentions=[bot.user])))
assert len(CALLS) == 1, f"the daily cap did not hold: {len(CALLS)} calls"
print("cog             the daily call cap holds")


# --------------------------------------------------------------------------- #
#  Joining a conversation uninvited
# --------------------------------------------------------------------------- #
cog, bot, guild, channel, dodo_role = build(
    chat_spontaneous_chance=1.0, chat_spontaneous_min_messages=2,
    chat_spontaneous_min_speakers=2, chat_ambient_cooldown_seconds=0)
bo = User(3, "Bo")
run(cog.handle_message(Message(ada, "did you see the thing", guild=guild, channel=channel)))
run(cog.handle_message(Message(bo, "which thing", guild=guild, channel=channel)))
assert channel.sent == ["hello"], f"she never joined in: {channel.sent}"
system = CALLS[-1]["messages"][0]["content"]
assert "Nobody addressed you" in system, "the uninvited turn lost its instruction"
assert "Ada: did you see the thing" in system, "she joined in without reading the room"
print("cog             she joins a live conversation with the last few messages as context")

cog, bot, guild, channel, dodo_role = build(
    payload=NOTHING, chat_spontaneous_chance=1.0, chat_spontaneous_min_messages=2,
    chat_spontaneous_min_speakers=2, chat_ambient_cooldown_seconds=0)
run(cog.handle_message(Message(ada, "a", guild=guild, channel=channel)))
run(cog.handle_message(Message(bo, "b", guild=guild, channel=channel)))
assert CALLS and channel.sent == [], "an empty answer means she decided to stay quiet"
print("cog             having nothing to add, she says nothing")

cog, bot, guild, channel, dodo_role = build(
    chat_spontaneous_chance=1.0, chat_spontaneous_min_messages=2,
    chat_spontaneous_min_speakers=2, chat_ambient_cooldown_seconds=0)
bot.visibility.enabled = False
run(cog.handle_message(Message(ada, "a", guild=guild, channel=channel)))
run(cog.handle_message(Message(bo, "b", guild=guild, channel=channel)))
assert channel.sent == [] and CALLS == [], "the unprompted feature switch must work"
print("cog             the unprompted feature can be switched off")


# --------------------------------------------------------------------------- #
#  Memory is a delta, not an echo
# --------------------------------------------------------------------------- #
cog, bot, guild, channel, dodo_role = build(
    payload={"say": "noted", "felt": 5, "learned": "plays healer", "rumour": None})
before = state_model.from_document(None, "1", cog._state_tuning(guild)).affinity
run(cog.handle_message(Message(ada, "i play healer", guild=guild, channel=channel,
                               mentions=[bot.user])))
saved = memories.find_one({"user_id": "1"})
assert [f["text"] for f in saved["facts"]] == ["plays healer"], saved["facts"]
assert saved["relationship"] == before + 5, f"sentiment did not apply: {saved['relationship']}"
print("cog             a learned fact is appended and the sentiment lands")

# A model that answers with rubbish must not destroy anything.
cog._client_for = lambda guild, author: FakeClient({"nonsense": True})
run(cog.handle_message(Message(ada, "again", guild=guild, channel=channel,
                               mentions=[bot.user])))
saved = memories.find_one({"user_id": "1"})
assert [f["text"] for f in saved["facts"]] == ["plays healer"], \
    "a junk completion wiped the memory — the exact bug the delta contract removes"
print("cog             a junk completion cannot erase what she knows")

print("PASS")
