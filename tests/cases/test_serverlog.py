"""The server log: filters that find the right rows, and a page that renders them.

Two things here are load-bearing and neither is obvious.

The rows this reads have been written since long before anything could read
them, and the older ones carry no extracted ids. Filtering by person has to find
those too, or the page silently claims somebody did nothing for the first year
of their membership.

And every deleted message ever sent passes through the renderer. If it escaped
after substituting mentions instead of before, a message someone typed would
become markup on an admin's page.
"""
import asyncio
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from helpers import event_log
from web import routes


# --- extraction: who and where, read out of the rendered text --------------- #
row = event_log.subjects(
    "\U0001f464 **<@111111111111111111>** (`111111111111111111`) roles updated "
    "by <@222222222222222222> - <t:1756300000:f>",
    {"Roles added": "<@&333333333333333333>"})
print("extracted:", row)
# The subject first, then the actor. Both, because "everything about this person"
# has to include the kicks they handed out, not only the ones they received.
assert row["user_ids"] == [111111111111111111, 222222222222222222], row
# A role id is not a user id, even though the backtick pattern would take any
# number: it arrives as <@&…>, which the user pattern deliberately does not match.
assert 333333333333333333 not in row["user_ids"], row
assert row["channel_ids"] == [], row

edit = event_log.subjects(
    "✏️ **<@111111111111111111>** (`111111111111111111`) edited a message "
    "in <#444444444444444444> - <t:1756300000:f> [Jump](https://discord.com/x)")
assert edit["channel_ids"] == [444444444444444444], edit
print("channel picked out of a message edit")

# --- date bounds: the 'to' day is included whole ---------------------------- #
bounds = event_log.day_bounds("2026-08-01", "2026-08-27")
assert bounds["$gte"] == "2026-08-01T00:00:00", bounds
assert bounds["$lt"] == "2026-08-28T00:00:00", "'to the 27th' means the 27th"
assert event_log.valid_day("last tuesday") == "", "a date we can't read is dropped"
print("date bounds:", bounds)


# --- the query ------------------------------------------------------------- #
class Col:
    """Enough of a collection to prove what the query asks for."""
    def __init__(s): s.docs, s.queries = [], []
    def create_index(s, *a, **k): pass
    def aggregate(s, pipeline): return iter(())
    def count_documents(s, q): s.queries.append(q); return 0
    def find(s, q): s.queries.append(q); return _Cur([])


class _Cur(list):
    def sort(s, *a): return s
    def skip(s, n): return s
    def limit(s, n): return s


col = Col()
store = event_log.EventLogStore(col)
store.page(42, page=1, user_ids=[777888999000111222])
clause = col.queries[0]["$and"][0]["$or"]
# The indexed field is tried first; the text it came from is the fallback, and
# it only applies to rows that never had the field. Without the $exists guard a
# new row would be matched twice and an old one not at all.
assert clause[0] == {"user_ids": {"$in": [777888999000111222]}}, clause
assert clause[1]["user_ids"] == {"$exists": False}, clause
assert "777888999000111222" in clause[1]["description"]["$regex"], clause
print("a user filter reaches rows written before ids were extracted")

# Several people means any of them, not all of them: nobody picks two names to
# see only the events that name both.
col = Col()
store = event_log.EventLogStore(col)
store.page(42, user_ids=[111111111111111111, 222222222222222222],
           channel_ids=[444444444444444444])
both = col.queries[0]["$and"]
assert len(both) == 2, both
assert both[0]["$or"][0]["user_ids"]["$in"] == [111111111111111111, 222222222222222222]
pattern = both[0]["$or"][1]["description"]["$regex"]
assert "111111111111111111|222222222222222222" in pattern, pattern
assert re.search(pattern, "roles for <@222222222222222222> changed"), pattern
assert not re.search(pattern, "roles for <@555555555555555555> changed"), pattern
assert both[1]["$or"][0]["channel_ids"]["$in"] == [444444444444444444]
print("several ids match any of them, in the index and in the fallback")

col = Col()
store = event_log.EventLogStore(col)
store.page(42, group="Messages")
assert col.queries[0]["event_type"]["$in"] == [
    "MESSAGE_EDIT", "MESSAGE_DELETE", "MESSAGE_BULK_DELETE"], col.queries[0]
assert col.queries[0]["guild_id"] == 42
print("a group filter expands to its types")

col = Col()
store = event_log.EventLogStore(col)
store.page(42, since="2026-08-01", until="2026-08-01")
assert col.queries[0]["timestamp"] == {"$gte": "2026-08-01T00:00:00",
                                       "$lt": "2026-08-02T00:00:00"}
print("a single day is a whole day")


# --- rendering -------------------------------------------------------------- #
class Role:
    def __init__(s, i, n): s.id, s.name = i, n


class Member:
    bot = False
    def __init__(s, i, n): s.id, s.display_name, s.name = i, n, n.lower()


class Channel:
    category, position = None, 0
    def __init__(s, i, n): s.id, s.name = i, n


MIDO = Member(111111111111111111, "Mido")
FOX = Member(222222222222222222, "Fox")
GENERAL = Channel(444444444444444444, "general")


class Guild:
    id, name = 42, "ESO for Dodos"
    # A real roster, because the filter options are built from it. An empty one
    # here would let the bug this replaced pass the test.
    members = [MIDO, FOX]
    channels = [GENERAL]
    threads = []
    def get_member(s, i): return {m.id: m for m in s.members}.get(int(i))
    def get_role(s, i): return {333333333333333333: Role(333333333333333333, "Legend")}.get(int(i))
    def get_channel_or_thread(s, i): return {GENERAL.id: GENERAL}.get(int(i))


guild = Guild()
out = routes._discord_markup(
    guild, "**<@111111111111111111>** (`111111111111111111`) edited a message in <#444444444444444444> - <t:1756300000:f>")
print("rendered:", out)
assert "@Mido" in out and "#general" in out, out
assert "<b>" in out and "<code>111111111111111111</code>" in out, out
assert "1756300000" not in out, "the row has a When column; the token is a repeat"

# Someone who has left, a role that is gone, a channel that is gone.
missing = routes._discord_markup(guild, "**<@999999999999999999>** in <#888888888888888888> got <@&777777777777777777>")
assert "999999999999999999" in missing and "deleted" in missing, missing
print("gone:", missing)

# THE ONE THAT MATTERS. Every deleted message passes through here.
nasty = routes._discord_markup(
    guild, '<img src=x onerror=alert(1)> and <script>alert(2)</script>')
assert "<img" not in nasty and "<script>" not in nasty, nasty
assert "&lt;img" in nasty and "&lt;script&gt;" in nasty, nasty
print("a message that is markup stays text")

# A mention typed by hand as literal text cannot smuggle a tag either, because
# the substitution only ever produces a span it built itself.
typed = routes._discord_markup(guild, "<@111111111111111111> said <b>hi</b>")
assert typed.count("<b>") == 0, typed
print("escaped first, matched second")


# --- the page --------------------------------------------------------------- #
DOCS = [
    {"_id": 2, "guild_id": 42, "event_type": "MESSAGE_DELETE",
     "timestamp": "2026-08-27T10:15:00+00:00",
     "description": "**<@111111111111111111>** (`111111111111111111`) message deleted in <#444444444444444444>",
     "fields": {"Content": "hello <@999999999999999999>"}, "user_ids": [111111111111111111], "channel_ids": [444444444444444444]},
    {"_id": 1, "guild_id": 42, "event_type": "THREAD_CREATE",
     "timestamp": "2026-08-26T09:00:00+00:00",
     "description": "**Thread Created:** <#444444444444444444> (`chat`)",
     "fields": {}, "user_ids": [], "channel_ids": [444444444444444444]},
]
# Two pages, so the pager renders: it is the only thing that carries the
# filters forward, and a single-page fixture cannot see it drop them.
data = {"rows": DOCS, "total": 2, "page": 1, "pages": 3}
options = {"types": {"MESSAGE_DELETE": 5, "THREAD_CREATE": 1},
           "people": [111111111111111111, 999999999999999999], "channels": [444444444444444444]}
chosen = {"type": "MESSAGE_DELETE", "group": "", "user": [111111111111111111],
          "channel": [], "from": "2026-08-01", "to": ""}
page = routes._server_log_html(None, guild, data, options, chosen)

assert "Server log" in page and "2 event(s)" in page
assert "Message deleted" in page and "Thread created" in page
# Only the types this guild has produced, and the group above its own types.
assert "Messages (all)" in page and "Threads (all)" in page
assert "Voice (all)" not in page, "a group with no events here is not offered"
assert 'value="MESSAGE_DELETE" selected' in page, "the chosen type comes back selected"
# The person filter is a chip, not a selected option, and it carries the name.
assert 'class="ms-chip" data-id="111111111111111111"' in page, "the choice comes back"
assert ">Mido<" in page, "and reads as a name rather than as a snowflake"
assert '<input type="date" name="from"\n      value="2026-08-01">' in page, page[:0] or "date kept"
# Every filter has to travel with the pager or page two silently drops the search.
assert "type=MESSAGE_DELETE" in page and "user=111111111111111111" in page and "from=2026-08-01" in page
# The field name and its value both render.
assert "Content" in page and "hello" in page
print("page renders with filters preserved")

# --- the options come from the server, not from what the log happens to hold - #
# The bug this replaced: options were aggregated from the ids extracted at write
# time, so a server of hundreds offered the two people who had triggered an
# event since that extraction started.
people = routes._log_people(guild, [999999999999999999])
assert [p["label"] for p in people] == ["Fox", "Mido", "999999999999999999"], people
assert people[-1]["sub"] == "left the server", people[-1]
assert all(p["id"] != str(999999999999999999) or p["label"] == "999999999999999999"
           for p in people)
print("people offered:", [p["label"] for p in people])

chans = routes._log_channels(guild, [888888888888888888])
assert [c["label"] for c in chans] == ["#general", "888888888888888888"], chans
assert chans[-1]["sub"] == "deleted or archived", chans[-1]
print("channels offered:", [c["label"] for c in chans])

# Nothing chosen is still a working control, and the placeholder is the "any"
# state rather than a value.
none_picked = dict(chosen, user=[], channel=[])
blank = routes._server_log_html(None, guild, data, options, none_picked)
assert 'placeholder="Anyone"' in blank and 'placeholder="Anywhere"' in blank
# The closing quote matters: the empty container is class="ms-chips", which a
# looser check matches happily.
assert 'class="ms-chip"' not in blank, "no chips when nothing is picked"
assert 'name="user"' in blank and 'name="channel"' in blank
print("empty pickers keep their placeholders")

# Two people at once: two chips, and both ids in the value the form submits.
two = dict(chosen, user=[MIDO.id, FOX.id])
page2 = routes._server_log_html(None, guild, data, options, two)
assert page2.count('class="ms-chip"') == 2, "one chip each"
assert f'value="{MIDO.id},{FOX.id}"' in page2, "and one field carrying both"
assert f"user={MIDO.id},{FOX.id}" in page2, "which the pager carries too"
print("two people picked at once")


# --- an empty page is a question, so it answers it -------------------------- #
class Vis:
    def __init__(s, on): s.on = on
    def feature_active(s, gid, feature, cog): return s.on


class LogCog:
    def __init__(s, wired): s.wired = wired
    def guild_log_channels(s, guild): return {"channel_id": 12345} if s.wired else {}


class Bot:
    def __init__(s, on, wired): s.visibility, s._cog = Vis(on), LogCog(wired)
    def get_cog(s, name): return s._cog


off = routes._server_log_html(Bot(False, True), guild, data, options, chosen)
assert "switched off" in off, "a page recording nothing has to say why"
nochannel = routes._server_log_html(Bot(True, False), guild, data, options, chosen)
assert "No log channel" in nochannel, nochannel
fine = routes._server_log_html(Bot(True, True), guild, data, options, chosen)
assert "warnline" not in fine, "and stay quiet when it is working"
print("empty-page warnings: off, no channel, healthy")
print("PASS")
