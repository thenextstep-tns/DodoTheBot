"""The two automatic paths: gating, and that failures get reported (but not spammed)."""
import asyncio, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from cogs.trial_ranks import TrialRanks


class Guild:
    id, name = 42, "G"


class Vis:
    enabled = True
    def cog_enabled(self, gid, cog): return self.enabled


class Mgr:
    on = True
    def get(self, gid): return {"enabled": self.on}


class Bot:
    trial_ranks = Mgr()
    visibility = Vis()


cog = TrialRanks.__new__(TrialRanks)
cog.bot = Bot()
cog._reported = {}
logged = []


async def fake_log(guild, description, *, title="Trial ranks"):
    logged.append(description)


cog.log_event = fake_log
guild = Guild()

# --- gating: enrolment is the switch, so no feature flag may gate the runtime ---
assert cog.runs_here(guild) is True
Mgr.on = False
assert cog.runs_here(guild) is True, "a stored 'enabled' flag must not gate anything"
Mgr.on = True
Vis.enabled = False
assert cog.runs_here(guild) is False, "the cog being disabled for the guild still stops it"
assert "cog is disabled" in cog.why_not_running(guild)
Vis.enabled = True
assert cog.why_not_running(guild) == ""
print("gating OK: only the cog toggle gates; enrolment decides who is touched")

# --- reporting: said once, then held for an hour ---
async def run():
    await cog.report_problems(guild, ["Master sits above my highest role"], context="test")
    await cog.report_problems(guild, ["Master sits above my highest role"], context="test")
    await cog.report_problems(guild, ["Master sits above my highest role"], context="test")
    await cog.report_problems(guild, ["A different problem"], context="test")
    await cog.report_problems(guild, [], context="test")

asyncio.run(run())
print(f"\n{len(logged)} log entries from 5 calls:")
for entry in logged:
    print("   ", entry.splitlines()[0], "|", entry.splitlines()[-1])
assert len(logged) == 2, "repeats suppressed, a new problem still gets through"
assert "Master" in logged[0] and "different" in logged[1]

# An hour later the same problem is worth saying again.
cog._reported[42]["Master sits above my highest role"] -= 3601
asyncio.run(cog.report_problems(guild, ["Master sits above my highest role"], context="test"))
assert len(logged) == 3, "should speak up again after the hour"
print("\nthrottle OK — repeats held for an hour, new problems immediate")
print("PASS")
