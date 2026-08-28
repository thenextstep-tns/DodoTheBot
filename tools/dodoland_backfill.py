"""
Run DodoLand's archive rebuild from the command line.

The panel has a button for this, but the button needs a browser and a session,
and the rebuild is a one-off administrative job that wants to be runnable on the
box. Same code path either way: this calls ``helpers.dodoland.backfill.run``,
so the panel and the shell cannot produce different history.

    py tools/dodoland_backfill.py <guild id> --preview   # report, write nothing
    py tools/dodoland_backfill.py <guild id>             # actually rebuild

**No Discord connection.** Opening a second gateway session with the live bot's
token to ask for a channel list would be a silly risk for a job that only needs
ids. The guild's channels are taken from the archive itself (rows carry a guild
id since the panel's stats work) plus anything the guild's buildings already
point at. Coverage is per channel rather than per row, so one recent message in
a channel brings that channel's whole history along with it.
"""

from __future__ import annotations

import argparse
import json
import sys

import config_py
from helpers.dodoland import backfill as backfill_rules
from helpers.dodoland import parameters as dodo_parameters
from helpers.dodoland.buildings import BuildingStore
from helpers.dodoland.store import ActivityStore


class _Channel:
    """Just enough of a channel for the backfill: it only ever reads ids."""

    def __init__(self, channel_id: int) -> None:
        self.id = int(channel_id)


class _Guild:
    def __init__(self, guild_id: int, channel_ids) -> None:
        self.id = int(guild_id)
        self.channels = [_Channel(c) for c in channel_ids]


class _Bot:
    """The two handles ``backfill.run`` actually uses."""

    def __init__(self) -> None:
        self.dodoland_params = dodo_parameters.manager()
        self.dodoland = ActivityStore(
            config_py.dodoland_activity, config_py.dodoland_pairs, self.dodoland_params
        )
        self.dodoland_buildings = BuildingStore(config_py.dodoland_config)


def channel_ids_for(bot: _Bot, guild_id: int) -> list[int]:
    """Every channel this guild is known to own.

    Two sources, unioned: channels the archive has seen carrying this guild id,
    and channels the guild's buildings already point at. The second matters
    because a room that has been quiet since the guild field was added would
    otherwise be invisible here.
    """
    found = {int(c) for c in config_py.messages.distinct("channel", {"guild": int(guild_id)})}
    for building in bot.dodoland_buildings.buildings(guild_id):
        found.update(int(c) for c in (building.get("channels") or {}))
    return sorted(found)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guild_id", type=int)
    parser.add_argument("--preview", action="store_true",
                        help="Report what would happen and write nothing.")
    args = parser.parse_args(argv)

    bot = _Bot()
    channels = channel_ids_for(bot, args.guild_id)
    if not channels:
        print("No channels found for that guild in the archive. Nothing to rebuild.")
        return 1
    print(f"{len(channels)} channels known for guild {args.guild_id}")

    guild = _Guild(args.guild_id, channels)
    result = backfill_rules.run(bot, guild, archive=config_py.messages,
                                dry_run=args.preview)
    print(json.dumps(result, indent=2, default=str))
    if args.preview:
        print("\nPreview only. Nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
