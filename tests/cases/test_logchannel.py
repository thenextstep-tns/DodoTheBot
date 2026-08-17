"""The trial-rank log channel resolves to its own setting, then sensible fallbacks."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from cogs.trial_ranks import TrialRanks


class Channel:
    def __init__(self, cid, name): self.id, self.name = cid, name


CHANNELS = {10: Channel(10, "trial-ranks"), 20: Channel(20, "role-requests"),
            30: Channel(30, "dodo-log")}


class Guild:
    id = 42
    def get_channel(self, cid): return CHANNELS.get(int(cid))


class Mgr:
    config = {}
    def get(self, gid): return self.config


class GuildConfig:
    values = {}
    def get(self, gid, key): return self.values.get(key)


class Bot:
    trial_ranks = Mgr()
    guild_config = GuildConfig()


cog = TrialRanks.__new__(TrialRanks)
cog.bot = Bot()
guild = Guild()

def name_of():
    channel = cog.log_channel(guild)
    return channel.name if channel else None

# Nothing configured anywhere.
assert name_of() is None, "no channels, no logging — and no crash"

# Only the moderation log exists: last resort, still logs somewhere.
Bot.guild_config.values = {"LOG_CHANNEL": 30}
assert name_of() == "dodo-log", name_of()

# The role-request log wins over the moderation log without any extra setup.
Bot.guild_config.values = {"LOG_CHANNEL": 30, "E4D_ROLE_LOG": 20}
assert name_of() == "role-requests", name_of()

# An explicit choice beats both.
Mgr.config = {"log_channel_id": 10}
assert name_of() == "trial-ranks", name_of()

# A channel that has since been deleted falls through instead of going silent.
Mgr.config = {"log_channel_id": 999}
assert name_of() == "role-requests", name_of()

# Junk in the guild config doesn't take the logging down with it.
Mgr.config = {}
Bot.guild_config.values = {"E4D_ROLE_LOG": "not-a-number", "LOG_CHANNEL": 30}
assert name_of() == "dodo-log", name_of()
print("PASS")
