"""Actually load the cog into a real Bot — this is what the gateway does."""
import asyncio, sys, traceback
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from discord.ext import commands


class FakeMgr:
    def get(self, gid): return {"enabled": False, "points": {}, "ranks": [], "trials": []}
    def enrolled_ids(self, gid): return set()
    def is_enrolled(self, gid, uid): return False
    def interest_rows(self, gid, limit=1000): return []


async def main():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.trial_ranks = FakeMgr()
    bot.logger = type("L", (), {"error": staticmethod(print)})()
    from cogs.trial_ranks import setup
    try:
        await setup(bot)
    except Exception:
        traceback.print_exc()
        print("\n>>> COG FAILED TO LOAD — every command in it is dead <<<")
        return 1
    cog = bot.get_cog("trial_ranks")
    print("cog loaded:", cog is not None)
    names = sorted(c.qualified_name for c in bot.commands)
    print("prefix commands:", names)
    app = sorted(c.name for c in bot.tree.get_commands())
    print("app commands:   ", app)
    assert "rank" in names and "interest" in names, names
    await bot.close()
    print("PASS")
    return 0


sys.exit(asyncio.run(main()))
