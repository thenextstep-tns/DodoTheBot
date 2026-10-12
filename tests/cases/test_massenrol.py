"""Turning it on for the whole server: who it takes, and who it refuses to lose.

The sweep is the one path that overrides an answer somebody already gave, so
what it counts before it runs matters as much as what it does. It also has to
stop cleanly: enrolling somebody the pass never got round to ranking produces
the failure that looks like success, a card promising a rank nobody was given.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import cogs.trial_ranks as cog_module
from cogs.trial_ranks import TrialRanks, MAX_EDITS

# The pause between role edits is there to stay under Discord's rate limit, and
# there is no Discord here. Left in, the capped case alone would sit for over a
# minute proving nothing about the cap.
cog_module.EDIT_PAUSE = 0
from helpers.trial_ranks import (TrialRankManager, STATE_DISMISSED, STATE_ENROLLED,
                                 STATE_PROMPTED)


class Cur(list):
    """Just enough cursor: the manager sorts and limits what it reads."""
    def sort(s, key, direction=1):
        return Cur(sorted(s, key=lambda d: d.get(key), reverse=direction < 0))
    def limit(s, n): return Cur(s[:n])


class Col:
    def __init__(s): s.docs = []
    def _m(s, q, d): return all(d.get(k) == v for k, v in q.items())
    def create_index(s, *a, **k): pass
    def find(s, q, p=None): return Cur(d for d in s.docs if s._m(q, d))
    def find_one(s, q, p=None): return next((d for d in s.docs if s._m(q, d)), None)
    def update_one(s, q, u, upsert=False):
        d = s.find_one(q)
        if d is None:
            d = dict(q); d.update(u.get("$setOnInsert", {})); s.docs.append(d)
        d.update(u.get("$set", {}))
    def delete_one(s, q):
        d = s.find_one(q)
        if d: s.docs.remove(d)


class Role:
    managed = False
    def __init__(s, rid, name, position): s.id, s.name, s.position = rid, name, position
    def is_default(s): return False
    def __ge__(s, other): return s.position >= other.position
    def __lt__(s, other): return s.position < other.position


class Perms:
    manage_roles = True


class Me:
    guild_permissions = Perms()
    def __init__(s, top): s.top_role = top


class Member:
    bot = False
    def __init__(s, guild, uid, name, roles):
        s.guild, s.id, s.display_name, s.name, s.roles = guild, uid, name, name, list(roles)
        s.added, s.removed = [], []
    @property
    def top_role(s): return max(s.roles, key=lambda r: r.position)
    async def add_roles(s, *roles, reason=None): s.added += list(roles); s.roles += list(roles)
    async def remove_roles(s, *roles, reason=None):
        s.removed += list(roles)
        s.roles = [r for r in s.roles if r not in roles]


class Guild:
    id, owner_id = 42, 999
    def __init__(s, roles, me): s.roles, s.me, s.members = roles, me, []
    def get_role(s, rid): return next((r for r in s.roles if r.id == int(rid)), None)
    def get_channel(s, cid): return None


EVERYONE = Role(0, "@everyone", 0)   # Discord gives it to everybody, so the fake does too
LEGEND = Role(1, "Legend", 50)
CLEAR = Role(3, "vRG HM", 10)
BOT = Role(9, "Dodo", 99)
STAFF = Role(8, "Officer", 120)          # above the bot: untouchable by Discord's rule
CONFIG = {"exclusive": True, "trials": [],
          "points": {str(CLEAR.id): 300},
          "ranks": [{"role_id": LEGEND.id, "min_points": 100, "name": "Legend"}]}


def build(people):
    """A guild, a manager backed by fakes, and a cog wired to both."""
    guild = Guild([EVERYONE, LEGEND, CLEAR, BOT, STAFF], Me(BOT))
    guild.members = [Member(guild, uid, name, [EVERYONE, *roles])
                     for uid, name, roles in people]
    manager = TrialRankManager(Col(), Col(), enrollment_collection=Col(),
                               interest_collection=Col(), wr_collection=Col())
    manager._cache[42] = CONFIG
    cog = TrialRanks.__new__(TrialRanks)
    loop = asyncio.get_event_loop_policy().new_event_loop()
    cog.bot = type("B", (), {
        "trial_ranks": manager,
        "loop": type("L", (), {"run_in_executor": staticmethod(
            lambda ex, fn, *a: asyncio.sleep(0, result=fn(*a)))})(),
        "guild_config": type("G", (), {"get": staticmethod(lambda g, k: 0)})(),
        "logger": type("Lg", (), {"error": staticmethod(lambda *a: None)})(),
    })()
    loop.close()
    return guild, manager, cog


BOTLIKE = type("Bot", (Member,), {"bot": True})

# --- the plan: counted before anything is touched -------------------------- #
guild, manager, cog = build([
    (1, "Mido", [CLEAR]),        # never asked
    (2, "Fox", [CLEAR]),         # said no
    (3, "Rosa", [CLEAR]),        # already on
    (4, "Tea", []),              # never asked, nothing to score
    (5, "Boss", [STAFF]),        # never asked, out of the bot's reach
])
manager.set_state(42, 2, STATE_DISMISSED, name="Fox", source="button")
manager.set_state(42, 3, STATE_ENROLLED, name="Rosa", source="panel")
manager.set_state(42, 4, STATE_PROMPTED, name="Tea", source="command")

plan = cog.enrol_plan(guild)
print("plan:", {k: [m.display_name for m in v] for k, v in plan.items()})
assert [m.display_name for m in plan["already"]] == ["Rosa"]
assert [m.display_name for m in plan["declined"]] == ["Fox"], \
    "only a recorded no counts as a decline"
assert [m.display_name for m in plan["fresh"]] == ["Mido", "Tea", "Boss"], \
    "asked-but-unanswered is not a decline"
assert [m.display_name for m in plan["unreachable"]] == ["Boss"], \
    "the panel has to be able to warn before it enrols somebody untouchable"
# Nothing has happened yet: a plan that enrolled anybody would be a trap.
assert manager.enrolled_ids(42) == {3}, "counting must not enrol"

# --- the sweep ------------------------------------------------------------- #
summary = asyncio.run(cog.enrol_everyone(guild))
print("swept:", {k: v for k, v in summary.items() if k != "errors"})
assert summary["enrolled"] == 4, summary        # everyone but Rosa, who was on
assert summary["overruled"] == 1, "the decline it overrode is reported, not hidden"
assert manager.enrolled_ids(42) == {1, 2, 3, 4, 5}
assert summary["granted"] == 2, "Mido and Fox earn Legend; Tea and Boss do not"
assert [r.name for r in guild.members[0].added] == ["Legend"]
assert not guild.members[3].added, "no clears, no rank"
# Boss is above the bot, so Discord blocks every role change on them. The rank
# is still worked out; the refusal is what must not be swallowed.
assert summary["errors"] and "above mine" in summary["errors"][0], summary["errors"]
assert not guild.members[4].added

# Running it again is a no-op rather than a second round of role edits.
again = asyncio.run(cog.enrol_everyone(guild))
assert again["enrolled"] == 0 and again["targets"] == 0, again
print("a second press changes nothing")

# --- a recorded no can be kept ---------------------------------------------- #
guild, manager, cog = build([(1, "Mido", [CLEAR]), (2, "Fox", [CLEAR])])
manager.set_state(42, 2, STATE_DISMISSED, name="Fox", source="button")
summary = asyncio.run(cog.enrol_everyone(guild, include_declined=False))
print("declines kept:", summary["enrolled"], "enrolled,", summary["declined"], "left alone")
assert summary["enrolled"] == 1 and summary["overruled"] == 0
assert manager.enrolled_ids(42) == {1}, "the no was honoured"

# --- stopping leaves nobody enrolled-but-unranked --------------------------- #
guild, manager, cog = build(
    [(i, f"P{i}", [CLEAR]) for i in range(1, MAX_EDITS + 6)])
summary = asyncio.run(cog.enrol_everyone(guild))
print("capped at", MAX_EDITS, "edits:", summary["enrolled"], "enrolled,",
      summary["remaining"], "left for the next press")
assert summary["enrolled"] == MAX_EDITS, summary
assert summary["remaining"] == 5, summary
# The five it never reached are still un-enrolled, so pressing again picks them
# up. Enrolling them and skipping the roles would leave a card promising a rank
# they were never given.
assert len(manager.enrolled_ids(42)) == MAX_EDITS
rest = asyncio.run(cog.enrol_everyone(guild))
assert rest["enrolled"] == 5 and rest["remaining"] == 0, rest
print("PASS")
