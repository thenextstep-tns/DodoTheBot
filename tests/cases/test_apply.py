"""A refused role edit must be reported, never silently swallowed."""
import asyncio, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from cogs.trial_ranks import TrialRanks
from helpers import trial_ranks as tr


class Role:
    managed = False
    def __init__(self, rid, name, position):
        self.id, self.name, self.position = rid, name, position
    def is_default(self): return False
    def __ge__(self, other): return self.position >= other.position
    def __lt__(self, other): return self.position < other.position


class Perms:
    def __init__(self, manage): self.manage_roles = manage


class Me:
    def __init__(self, top, manage=True):
        self.top_role, self.guild_permissions = top, Perms(manage)


class Guild:
    id = 42
    owner_id = 999
    def __init__(self, roles, me, members=()):
        self.roles, self.me, self.members = roles, me, list(members)
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)


class Member:
    bot = False
    id = 7
    display_name = "Fox"
    def __init__(self, guild, roles, *, forbid=False):
        self.guild, self.roles, self.forbid = guild, roles, forbid
        self.added, self.removed = [], []
    @property
    def top_role(self): return max(self.roles, key=lambda r: r.position)
    async def add_roles(self, *roles, reason=None):
        if self.forbid: raise discord.Forbidden(_Resp(), "Missing Permissions")
        self.added += list(roles)
    async def remove_roles(self, *roles, reason=None):
        if self.forbid: raise discord.Forbidden(_Resp(), "Missing Permissions")
        self.removed += list(roles)


class _Resp:
    status, reason = 403, "Forbidden"


LEGEND = Role(1, "Legend", 50)
MASTER = Role(2, "Master", 60)
CLEAR = Role(3, "vRG HM", 10)
BOT_LOW = Role(9, "Dodo", 55)      # under Master, over Legend
BOT_HIGH = Role(9, "Dodo", 99)

CONFIG = {
    "enabled": True, "exclusive": True,
    "points": {str(CLEAR.id): 300},
    "ranks": [{"role_id": LEGEND.id, "min_points": 100, "name": "Legend"},
              {"role_id": MASTER.id, "min_points": 250, "name": "Master"}],
    "trials": [],
}
cog = TrialRanks.__new__(TrialRanks)
cog.bot = type("B", (), {"trial_ranks": type("M", (), {
    "get": lambda s, g: CONFIG,
    "wr_for": lambda s, g, u: None,   # no records in these cases
    "interest_rows": lambda s, g, limit=1000: [],
    "drop_interest_roles": lambda s, g, u, r: 0,
})()})()

# 1. Happy path — the bot outranks everything.
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_HIGH))
m = Member(guild, [LEGEND, CLEAR])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("healthy:", out["rank_name"], "granted", out["granted"], "removed", out["removed"],
      "errors", out["errors"])
assert out["rank_name"] == "Master"
assert [r.name for r in m.added] == ["Master"], m.added
assert [r.name for r in m.removed] == ["Legend"], m.removed
assert not out["errors"]

# 2. THE BUG: Master sits above the bot. Card said Master, roles never moved.
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_LOW))
m = Member(guild, [LEGEND, CLEAR])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\nrank role too high:", out["rank_name"], "granted", out["granted"])
for e in out["errors"]: print("   !", e)
assert out["rank_name"] == "Master", "still computes the right rank"
assert out["granted"] == 0 and not m.added, "and correctly fails to apply it"
assert out["errors"], "but it must SAY SO — this is what was swallowed"
assert "above my highest role" in out["errors"][0]
assert "Master" in out["errors"][0]
# Legend is below the bot, so removing it still works.
assert [r.name for r in m.removed] == ["Legend"], m.removed

# 3. No Manage Roles at all.
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_HIGH, manage=False))
m = Member(guild, [LEGEND, CLEAR])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\nno permission:", out["errors"])
assert "Manage Roles" in out["errors"][0]
assert not m.added and not m.removed

# 4. Discord refuses at the API even though the hierarchy looked fine.
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_HIGH))
m = Member(guild, [LEGEND, CLEAR], forbid=True)
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\n403 from Discord:", out["errors"])
assert out["errors"] and "refused" in out["errors"][0]

# 5. The panel warns before anyone is enrolled.
from web import routes
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_LOW))
warns = routes._rank_role_warnings(guild, CONFIG)
print("\npanel warning:", warns)
assert warns and "Master" in warns[0]
assert not routes._rank_role_warnings(Guild([LEGEND, MASTER, CLEAR], Me(BOT_HIGH)), CONFIG)
print("\nPASS")

# ---------------------------------------------------------------------------
# 6. THE REAL ONE: the member outranks the bot, so Discord refuses to touch
#    them at all — even though Legend and Master both sit BELOW the bot.
STAFF = Role(4, "Moderator", 80)          # above the bot
BOT_MID = Role(9, "Dodo", 70)             # above Legend(50) and Master(60)


guild = Guild([LEGEND, MASTER, CLEAR, STAFF], Me(BOT_MID))
guild.owner_id = 999
m = Member(guild, [LEGEND, CLEAR, STAFF])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\nmember outranks bot:", out["rank_name"], "granted", out["granted"])
for e in out["errors"]: print("   !", e)
assert out["rank_name"] == "Master"
assert out["granted"] == 0 and not m.added and not m.removed, "nothing may be attempted"
assert out["errors"] and "above mine" in out["errors"][0], out["errors"]
assert "Moderator" in out["errors"][0], "must name the blocking role"
# The rank roles themselves are fine — the message must not blame them.
assert "Master** sits above" not in out["errors"][0]

# 7. The server owner is untouchable regardless of hierarchy.
guild = Guild([LEGEND, MASTER, CLEAR], Me(BOT_HIGH))
guild.owner_id = 7
m = Member(guild, [LEGEND, CLEAR])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\nserver owner:", out["errors"])
assert "owner" in out["errors"][0].lower() and not m.added

# 8. A normal member below the bot is unaffected by any of this.
guild = Guild([LEGEND, MASTER, CLEAR, STAFF], Me(BOT_MID))
guild.owner_id = 999
m = Member(guild, [LEGEND, CLEAR])
out = asyncio.run(TrialRanks.apply(cog, m, CONFIG))
print("\nordinary member:", [r.name for r in m.added], [r.name for r in m.removed],
      out["errors"])
assert [r.name for r in m.added] == ["Master"] and not out["errors"]
print("\nPASS (hierarchy)")
