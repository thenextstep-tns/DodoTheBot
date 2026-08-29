"""
Tell the bot owner when someone else changes their server's configuration.

Guild admins can switch cogs off, change command levels and edit settings, and
those changes now apply to everyone — the owner included. So the owner has to
hear about it, and be able to put it back.

Changes are **batched**: an admin working through a settings page produces one
DM a few seconds after they stop, not one per field. Each DM says who changed
what, in which server, and links straight to the page to change it back.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Optional

import discord

# How long to keep collecting an actor's changes before sending the summary.
BATCH_DELAY = 20.0
# Most lines to list before summarising the remainder.
MAX_LINES = 25


class OwnerNotifier:
    """Batches config changes per (guild, actor) and DMs the bot owners.

    Instantiated once as ``bot.audit_notify``; the panel calls :meth:`record`
    after a successful write by a non-owner.
    """

    def __init__(self, bot, owners, *, panel_url: str = "", delay: float = BATCH_DELAY) -> None:
        self.bot = bot
        self._owners = [int(o) for o in owners]
        self._panel_url = panel_url.rstrip("/")
        self._delay = delay
        self._pending: dict[tuple[int, int], dict] = {}
        self._tasks: dict[tuple[int, int], asyncio.Task] = {}

    def record(self, guild, actor, line: str) -> None:
        """Note one change. Safe to call from a request handler; never raises."""
        try:
            if actor is None or int(actor.id) in self._owners:
                return  # the owner's own changes aren't news
            key = (int(guild.id), int(actor.id))
            entry = self._pending.setdefault(
                key,
                {
                    "guild_name": guild.name,
                    "actor": getattr(actor, "display_name", None) or getattr(actor, "name", str(actor.id)),
                    "actor_id": int(actor.id),
                    "lines": [],
                    "first_at": datetime.datetime.now(datetime.timezone.utc),
                },
            )
            entry["lines"].append(line)
            task = self._tasks.get(key)
            if task and not task.done():
                task.cancel()  # restart the window; they're still working
            self._tasks[key] = self.bot.loop.create_task(self._flush_later(key))
        except Exception as error:  # noqa: BLE001 - notification must never break a save
            self._log(f"Failed to record config change: {error}")

    async def _flush_later(self, key) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        entry = self._pending.pop(key, None)
        self._tasks.pop(key, None)
        if not entry:
            return
        try:
            await self._send(key[0], entry)
        except Exception as error:  # noqa: BLE001
            self._log(f"Failed to DM owners about config changes: {error}")

    async def _send(self, guild_id: int, entry: dict) -> None:
        lines = entry["lines"]
        shown = lines[:MAX_LINES]
        if len(lines) > MAX_LINES:
            shown.append(f"…and {len(lines) - MAX_LINES} more change(s).")
        embed = discord.Embed(
            title="Server settings changed",
            description=(
                f"**{entry['actor']}** (`{entry['actor_id']}`) changed the configuration of "
                f"**{entry['guild_name']}**:\n\n" + "\n".join(f"• {line}" for line in shown)
            ),
            color=0xFF385C,
            timestamp=entry["first_at"],
        )
        if self._panel_url:
            embed.add_field(
                name="Change it back",
                value=f"{self._panel_url}/guild/{guild_id}",
                inline=False,
            )
        embed.set_footer(text="You get this because they are not a bot owner.")
        for owner_id in self._owners:
            try:
                user = self.bot.get_user(owner_id) or await self.bot.fetch_user(owner_id)
                await user.send(embed=embed)
            except (discord.HTTPException, AttributeError) as error:
                self._log(f"Could not DM owner {owner_id}: {error}")

    def _log(self, message: str) -> None:
        logger = getattr(self.bot, "logger", None)
        if logger:
            logger.error(message)
