"""
Live per-guild application-command sync driven by the visibility settings.

Instead of one global command set, each guild gets its own slash-command tree
computed from :class:`helpers.visibility.VisibilityManager`:

    - a command whose cog is **disabled** for the guild is omitted;
    - an **owner**-level command (explicitly set, or a ``hidden`` owner-tooling
      command with no override) is omitted from the guild picker entirely — the
      owner still runs it via prefix or the control panel;
    - an **admin**-level command is included but stamped with
      ``default_member_permissions = Manage Server`` so Discord hides it from
      non-admins (the closest native match to our runtime rule);
    - everything else is **visible**.

Discord can't hide a command from a single user id, so this is a best-effort
mirror of the authoritative runtime checks in ``bot.py``.

Syncs are per-guild: a single guild is re-synced (debounced) when its config
changes, and every guild is synced once on startup — but only when its computed
tree actually differs from the last sync (a stored hash guard), to stay well
within Discord's per-guild command-sync rate limits.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Optional

import discord
from discord import app_commands

from helpers.visibility import LEVEL_ADMIN, LEVEL_OWNER, LEVEL_VISIBLE

_ADMIN_PERMS = discord.Permissions(manage_guild=True)
_DEBOUNCE_SECONDS = 2.0


class CommandSyncer:
    """Computes and applies per-guild command trees. Lives on ``bot.command_syncer``."""

    def __init__(self, bot, *, hash_col):
        self.bot = bot
        self._hash_col = hash_col
        self._locks: dict[int, asyncio.Lock] = {}
        self._pending: dict[int, asyncio.Task] = {}

    # ------------------------------------------------------------------ #
    #  Level resolution
    # ------------------------------------------------------------------ #
    def _is_hidden(self, command) -> bool:
        """Whether a command is owner-tooling. ``hidden`` lives on the ext
        (hybrid/prefix) command, not on the app-command object, so resolve it by
        name via the prefix registry."""
        ext = self.bot.get_command(command.name)
        return bool(getattr(ext, "hidden", False))

    def _effective_level(self, guild_id: int, command) -> str:
        """Stored override, else ``owner`` for hidden owner-tooling, else ``visible``."""
        stored = self.bot.visibility.stored_level(guild_id, command.name)
        if stored is not None:
            return stored
        return LEVEL_OWNER if self._is_hidden(command) else LEVEL_VISIBLE

    @staticmethod
    def _cog_name(command) -> Optional[str]:
        binding = getattr(command, "binding", None)
        return binding.qualified_name if binding is not None else None

    @staticmethod
    def _clone(command):
        """A detached per-guild copy so we can re-permission it without touching the
        shared global command object. Falls back to the original if a type can't be
        copied (e.g. a group) — it's then included as-is."""
        try:
            return command._copy_with(parent=None, binding=command.binding)
        except Exception:
            return command

    # ------------------------------------------------------------------ #
    #  Tree building
    # ------------------------------------------------------------------ #
    def build_guild_commands(self, guild_id: int) -> list:
        """The list of app commands that should appear in ``guild_id``'s picker."""
        result = []
        for command in self.bot.tree.get_commands():
            cog = self._cog_name(command)
            if cog is not None and not self.bot.visibility.cog_enabled(guild_id, cog):
                continue
            level = self._effective_level(guild_id, command)
            if level == LEVEL_OWNER:
                continue
            if level == LEVEL_ADMIN:
                clone = self._clone(command)
                clone.default_permissions = _ADMIN_PERMS
                result.append(clone)
            else:
                result.append(command)
        return result

    def _signature(self, guild_id: int) -> str:
        """A stable hash of the computed tree, used to skip unchanged startup syncs."""
        entries = sorted(
            (c.name, self._effective_level(guild_id, c), self._cog_name(c) or "")
            for c in self.bot.tree.get_commands()
        )
        # Fold in the guild's cog-disabled set (affects which entries are dropped).
        payload = {
            "entries": [
                (name, lvl, cog)
                for (name, lvl, cog) in entries
                if lvl != LEVEL_OWNER and (not cog or self.bot.visibility.cog_enabled(guild_id, cog))
            ]
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    # ------------------------------------------------------------------ #
    #  Syncing
    # ------------------------------------------------------------------ #
    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def sync_guild(self, guild_id: int, *, force: bool = False) -> Optional[int]:
        """Recompute and push ``guild_id``'s command tree. Returns the command count
        synced, or ``None`` when skipped because nothing changed."""
        async with self._lock(guild_id):
            signature = self._signature(guild_id)
            if not force:
                stored = self._hash_col.find_one({"guild_id": guild_id})
                if stored and stored.get("hash") == signature:
                    return None
            guild_obj = discord.Object(id=guild_id)
            self.bot.tree.clear_commands(guild=guild_obj)
            for command in self.build_guild_commands(guild_id):
                self.bot.tree.add_command(command, guild=guild_obj, override=True)
            try:
                synced = await self.bot.tree.sync(guild=guild_obj)
            except discord.HTTPException as error:
                self.bot.logger.error(f"Failed to sync commands for guild {guild_id}: {error}")
                return None
            self._hash_col.update_one(
                {"guild_id": guild_id}, {"$set": {"hash": signature}}, upsert=True
            )
            self.bot.logger.info(f"Synced {len(synced)} command(s) to guild {guild_id}.")
            return len(synced)

    async def sync_all(self, *, force: bool = False) -> None:
        """Sync every guild the bot is in (startup + manual ``/sync``)."""
        for guild in self.bot.guilds:
            await self.sync_guild(guild.id, force=force)

    def request_sync(self, guild_id: int) -> None:
        """Debounced live resync for a guild after a config change (fire-and-forget)."""
        existing = self._pending.get(guild_id)
        if existing and not existing.done():
            existing.cancel()

        async def _debounced():
            try:
                await asyncio.sleep(_DEBOUNCE_SECONDS)
                await self.sync_guild(guild_id, force=True)
            except asyncio.CancelledError:
                pass
            finally:
                self._pending.pop(guild_id, None)

        self._pending[guild_id] = self.bot.loop.create_task(_debounced())
