"""The chat triggers must actually render on the Events page — and be wired.

No test in this repo executes the panel's JavaScript, so the failure mode is a
card that renders perfectly and does nothing, because a class name drifted apart
from the selector that binds it. This case reads both sides and checks they still
agree, then walks the store through the same create/edit/reset the panel does.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.fake_mongo import FakeCollection
from web import routes
from helpers import cog_categories
from helpers.chat import activity as activity_model
from helpers.chat import triggers as trigger_model


class Vis:
    def feature_enabled(self, gid, key): return True


class Guild:
    id, name, icon = 424242424242424242, "Test Guild", None
    roles, channels = [], []


class Rules:
    def for_guild(self, gid): return []


class Bot:
    def __init__(self, collection):
        self.visibility, self.event_rules = Vis(), Rules()
        self.chat_triggers = trigger_model.ChatTriggerManager(collection)
        self.chat_activity = activity_model.ChatActivity()


collection = FakeCollection()
bot, guild = Bot(collection), Guild()

# A guild nobody has configured still gets a personality, stored and editable.
html = routes._events_html(bot, guild)
assert html.count('class="rulecard trigcard') == len(trigger_model.DEFAULT_TRIGGERS), \
    "a fresh guild should be seeded with the default triggers"
assert collection.count_documents({trigger_model.K_GUILD: guild.id}) == len(
    trigger_model.DEFAULT_TRIGGERS), "seeding must persist, not just render"
print(f"page            a fresh server seeds {len(trigger_model.DEFAULT_TRIGGERS)} editable triggers")

for phrase in ("xynode", "no u", "good bot"):
    assert phrase in html, f"default trigger phrase missing from the page: {phrase}"
print("page            the shipped phrases are visible and editable")

# A section nobody can find is a section that does not exist. It sits under a
# long list of event rules, so the top of the page has to point at it.
assert 'id="chat-triggers"' in html and 'href="#chat-triggers"' in html, \
    "nothing at the top of the Events page points to the chat triggers"
assert "the words Dodo reacts to" in html, \
    "the heading should say what it is in the words someone would search for"
feature = next(f for f in cog_categories.FEATURES if f["key"] == "chat_listeners")
assert feature.get("link") == ("events", "Chat triggers"), \
    "the chat cog's listener switch must link to the page holding its phrases"
rendered = routes._feature_rows([{**feature, "enabled": True}], guild)
assert f'href="/guild/{guild.id}/events"' in rendered, \
    "the feature row rendered without its link"
print("page            the chat cog links to the triggers, and the page signposts them")

# Every control the JS looks for has to exist, and vice versa.
script = pathlib.Path("web/static/panel.js").read_text(encoding="utf-8")
for selector in (".trigname", ".trigpatterns", ".trignote", ".trigreflex", ".trigspice",
                 ".trigaffinity", ".triggrudge", ".trigchance", ".trigreflexchance",
                 ".trigforgives", ".trigsave", ".trigtoggle", ".trigdelete"):
    assert f'class="{selector[1:]}' in html or selector[1:] in html, \
        f"the page never renders {selector}"
    assert selector in script, f"nothing in panel.js binds {selector}"
for element in ("addtrigger", "resettriggers", "synctriggers"):
    assert f'id="{element}"' in html, f"the page is missing #{element}"
    assert f'"{element}"' in script, f"nothing in panel.js binds #{element}"
assert 'querySelector(".trigpage")' in script, "the trigger block never binds at all"
assert "chat-trigger" in script and "chat-trigger" in pathlib.Path(
    "web/routes.py").read_text(encoding="utf-8"), "the JS and the route disagree on the endpoint"
print("page            every control on the card is bound to the API")

# The store survives the round trip the panel performs.
first = collection.find_one({trigger_model.K_GUILD: guild.id})
bot.chat_triggers.update(guild.id, str(first["_id"]), {trigger_model.K_PATTERNS: "wombat\nemu"})
reloaded = next(t for t in bot.chat_triggers.for_guild(guild.id)
                if t.id == str(first["_id"]))
assert reloaded.matches("look, an emu"), "an edited pattern should match immediately"
assert not reloaded.matches("xynode"), "the old patterns should be gone"
print("page            editing patterns recompiles them straight away")

made = bot.chat_triggers.create(guild.id, {
    trigger_model.K_NAME: "custom", trigger_model.K_PATTERNS: ["pineapple"],
    trigger_model.K_CHANCE: 1.0,
})
assert bot.chat_triggers.match(guild.id, "I like pineapple").name == "custom"
bot.chat_triggers.delete(guild.id, str(made[trigger_model.K_ID]))
assert bot.chat_triggers.match(guild.id, "I like pineapple") is None
print("page            triggers can be added and removed per server")

# A server keeps the triggers it was first given, so a default shipped later
# never arrives — the live server sat on the first-ever wording for days because
# of exactly this. Syncing adds the missing ones and touches nothing else.
stale = FakeCollection()
aged = trigger_model.ChatTriggerManager(stale)
aged.for_guild(guild.id)
newcomer = trigger_model.DEFAULT_TRIGGERS[-1][trigger_model.K_NAME]
stale.delete_one({trigger_model.K_NAME: newcomer})
edited = stale.find_one({trigger_model.K_GUILD: guild.id})
aged.update(guild.id, str(edited["_id"]), {trigger_model.K_NOTE: "my own wording"})
aged._invalidate(guild.id)

added = aged.sync_defaults(guild.id)
assert added == [newcomer], f"sync should add exactly the missing default, got {added}"
assert stale.find_one({trigger_model.K_ID: edited["_id"]})[trigger_model.K_NOTE] == \
    "my own wording", "syncing new defaults trampled an edit"
assert aged.sync_defaults(guild.id) == [], "syncing twice should add nothing the second time"
print("page            new default triggers can arrive without discarding edits")

bot.chat_triggers.reset(guild.id)
assert bot.chat_triggers.match(guild.id, "xynode is here") is not None, \
    "reset should bring the defaults back"
assert collection.count_documents({trigger_model.K_GUILD: guild.id}) == len(
    trigger_model.DEFAULT_TRIGGERS), "reset should not leave the edited rows behind"
print("page            reset restores the defaults and drops the edits")

# One server's triggers are not another's.
other = Guild()
other.id = 999999999999999999
bot.chat_triggers.create(other.id, {trigger_model.K_NAME: "elsewhere",
                                    trigger_model.K_PATTERNS: ["pineapple"],
                                    trigger_model.K_CHANCE: 1.0})
assert bot.chat_triggers.match(other.id, "pineapple").name == "elsewhere"
assert bot.chat_triggers.match(guild.id, "pineapple") is None, "triggers leaked across servers"
print("page            triggers are per server")

# Disabled features are said out loud rather than failing silently.
bot.visibility = type("Off", (), {"feature_enabled": lambda self, gid, key: False})()
off_html = routes._events_html(bot, guild)
assert "String listeners are off" in off_html and "Unprompted chat is off" in off_html
print("page            a server with the listeners off is told so")

# The activity log is the whole point of the page: without it a trigger that
# matched and stayed silent is indistinguishable from the feature being off.
bot.visibility = Vis()
empty = routes._events_html(bot, guild)
assert "Nothing yet" in empty, "an empty log should explain itself rather than render blank"

bot.chat_activity.record(guild.id, channel="general", author="Ada", text="no u",
                         trigger="banter", outcome=activity_model.SILENT, reason="chance")
bot.chat_activity.record(guild.id, channel="general", author="Bo", text="good bot",
                         trigger="praise", outcome=activity_model.CANNED, reason="trigger",
                         said="say it again")
live = routes._events_html(bot, guild)
for expected in ("Ada", "no u", "said nothing", "chance", "canned line", "say it again"):
    assert expected in live, f"the activity log never showed {expected!r}"
assert bot.chat_activity.fires(guild.id) == {"banter": 1, "praise": 1},     bot.chat_activity.fires(guild.id)
assert "banter" in live and "praise" in live
print("page            silent matches are visible, with the reason they stayed silent")

print("PASS")
