"""
Reusable command checks.

These decorate commands to gate access. The predicates read ``context.author``,
which exists on both prefix ``Context`` and slash ``ApplicationCommandInteraction``,
so the same checks work as we migrate commands to slash.
"""

import json
from typing import Callable, TypeVar

from disnake.ext import commands

from exceptions import UserBlacklisted, UserNotOwner

T = TypeVar("T")


def is_owner() -> Callable[[T], T]:
    """Allow only bot owners (listed in ``config.json``) to run the command."""

    async def predicate(context: commands.Context) -> bool:
        with open("config.json", encoding="utf-8") as file:
            config = json.load(file)
        if context.author.id not in config["owners"]:
            raise UserNotOwner()
        return True

    return commands.check(predicate)


def not_blacklisted() -> Callable[[T], T]:
    """Block users whose IDs are in ``blacklist.json`` from running the command."""

    async def predicate(context: commands.Context) -> bool:
        with open("blacklist.json", encoding="utf-8") as file:
            blacklist = json.load(file)
        if context.author.id in blacklist["ids"]:
            raise UserBlacklisted()
        return True

    return commands.check(predicate)
