"""
Role-based, per-guild command & cog visibility.

Backs the multiserver control panel. Three levels apply to each command **per
guild**:

    "visible" — anyone may see/run it (default when nothing is stored)
    "admin"   — only guild admins (bot owners, the per-guild admin allowlist, or
                members with Discord's Manage Server permission)
    "owner"   — only bot owners

Independently, a whole cog can be **disabled for a guild**, which blocks every
command it owns in that guild regardless of level.

The authoritative enforcement lives here (used by the runtime checks in
``bot.py``); the live per-guild slash-picker sync (``helpers/command_sync.py``)
mirrors these decisions into Discord as closely as Discord allows.

Look-ups are cached per guild and the guild's cache entry is dropped whenever any
of its settings are written — the same approach as ``config/guild_config.py``.
"""

from __future__ import annotations

from typing import Iterable, Optional

LEVEL_VISIBLE = "visible"
LEVEL_ADMIN = "admin"
LEVEL_OWNER = "owner"
VALID_LEVELS = (LEVEL_VISIBLE, LEVEL_ADMIN, LEVEL_OWNER)


class VisibilityManager:
    """Reads/writes the per-guild visibility settings and answers the single
    ``can_run`` question the rest of the bot depends on. Instantiated once as
    ``bot.visibility``."""

    def __init__(self, *, visibility_col, cog_state_col, guild_admins_col, owners: Iterable[int], feature_col=None):
        self._vis_col = visibility_col
        self._cog_col = cog_state_col
        self._admin_col = guild_admins_col
        self._feature_col = feature_col
        self._owners = set(int(o) for o in owners)
        # Per-guild caches, each lazily populated and dropped on write.
        self._level_cache: dict[Optional[int], dict[str, str]] = {}
        self._cog_cache: dict[Optional[int], dict[str, bool]] = {}
        self._admin_cache: dict[Optional[int], set[int]] = {}
        self._feature_cache: dict[Optional[int], dict[str, bool]] = {}

    # ------------------------------------------------------------------ #
    #  Cache loaders
    # ------------------------------------------------------------------ #
    def _levels(self, guild_id: Optional[int]) -> dict[str, str]:
        if guild_id not in self._level_cache:
            self._level_cache[guild_id] = {
                doc["command"]: doc["level"]
                for doc in self._vis_col.find({"guild_id": guild_id})
                if doc.get("level") in VALID_LEVELS
            }
        return self._level_cache[guild_id]

    def _cogs(self, guild_id: Optional[int]) -> dict[str, bool]:
        if guild_id not in self._cog_cache:
            self._cog_cache[guild_id] = {
                doc["cog"]: bool(doc.get("enabled", True))
                for doc in self._cog_col.find({"guild_id": guild_id})
            }
        return self._cog_cache[guild_id]

    def _admins(self, guild_id: Optional[int]) -> set[int]:
        if guild_id not in self._admin_cache:
            doc = self._admin_col.find_one({"guild_id": guild_id})
            self._admin_cache[guild_id] = set(int(u) for u in doc.get("user_ids", [])) if doc else set()
        return self._admin_cache[guild_id]

    def _features(self, guild_id: Optional[int]) -> dict[str, bool]:
        if self._feature_col is None:
            return {}
        if guild_id not in self._feature_cache:
            self._feature_cache[guild_id] = {
                doc["feature"]: bool(doc.get("enabled", True))
                for doc in self._feature_col.find({"guild_id": guild_id})
            }
        return self._feature_cache[guild_id]

    def invalidate(self, guild_id: Optional[int]) -> None:
        """Drop every cached view for a guild (call after any write)."""
        self._level_cache.pop(guild_id, None)
        self._cog_cache.pop(guild_id, None)
        self._admin_cache.pop(guild_id, None)
        self._feature_cache.pop(guild_id, None)

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def is_owner(self, user_id: int) -> bool:
        return int(user_id) in self._owners

    def level(self, guild_id: Optional[int], command: str) -> str:
        """The stored level for a command in a guild (default ``visible``)."""
        return self._levels(guild_id).get(command, LEVEL_VISIBLE)

    def stored_level(self, guild_id: Optional[int], command: str) -> Optional[str]:
        """The explicitly-stored level, or ``None`` if the guild hasn't set one.

        Lets the picker sync distinguish "no override" (so it can fall back to a
        command's ``hidden`` flag → owner-level) from an explicit ``visible``.
        """
        return self._levels(guild_id).get(command)

    def cog_enabled(self, guild_id: Optional[int], cog: str) -> bool:
        """Whether a cog is enabled in a guild (default ``True``)."""
        return self._cogs(guild_id).get(cog, True)

    def feature_enabled(self, guild_id: Optional[int], feature: str) -> bool:
        """A passive-listener feature's *own* flag in a guild (default ``True``).

        This is the feature switch alone; use :meth:`feature_active` in listeners,
        which also honours the owning cog's enabled state.
        """
        return self._features(guild_id).get(feature, True)

    def stored_feature(self, guild_id: Optional[int], feature: str) -> Optional[bool]:
        """The explicitly-stored feature flag, or ``None`` if unset (for the panel)."""
        return self._features(guild_id).get(feature)

    def feature_active(self, guild_id: Optional[int], feature: str, cog: str) -> bool:
        """Whether a listener feature should actually run in a guild: its cog must
        be enabled **and** the feature's own switch must be on. This is the single
        call listeners make at the top of their handlers."""
        return self.cog_enabled(guild_id, cog) and self.feature_enabled(guild_id, feature)

    def guild_admin_ids(self, guild_id: Optional[int]) -> set[int]:
        return set(self._admins(guild_id))

    def is_guild_admin(self, guild_id: Optional[int], user_id: int, *, has_manage_guild: bool = False) -> bool:
        """Owner, on the per-guild admin allowlist, or holding Discord Manage Server."""
        return (
            self.is_owner(user_id)
            or has_manage_guild
            or int(user_id) in self._admins(guild_id)
        )

    def can_run(
        self,
        guild_id: Optional[int],
        user_id: int,
        command: str,
        cog: Optional[str],
        *,
        has_manage_guild: bool = False,
    ) -> bool:
        """The single allow/deny decision for a command invocation.

        A disabled cog is off **for the whole server, owners included** — if an
        admin switches something off it has to actually be off, or the setting
        is a lie. Owners keep the control panel as the way back: it is a web
        session, not a Discord command, so nothing here can lock them out of
        re-enabling it (and they are told when an admin changes something —
        see helpers/audit_notify.py).

        Levels still key off who you are: ``owner`` is owners-only, ``admin``
        is guild admins (owners included), ``visible`` is everyone.
        """
        if cog is not None and not self.cog_enabled(guild_id, cog):
            return False
        lvl = self.level(guild_id, command)
        if lvl == LEVEL_OWNER:
            return self.is_owner(user_id)
        if lvl == LEVEL_ADMIN:
            return self.is_guild_admin(guild_id, user_id, has_manage_guild=has_manage_guild)
        return True

    def visible_commands(
        self,
        guild_id: Optional[int],
        user_id: int,
        commands_meta: Iterable[tuple[str, Optional[str]]],
        *,
        has_manage_guild: bool = False,
    ) -> list[str]:
        """Filter ``(command, cog)`` pairs down to those the user may see/run."""
        return [
            command
            for command, cog in commands_meta
            if self.can_run(guild_id, user_id, command, cog, has_manage_guild=has_manage_guild)
        ]

    # ------------------------------------------------------------------ #
    #  Writes (each invalidates the affected guild's cache)
    # ------------------------------------------------------------------ #
    def set_level(self, guild_id: Optional[int], command: str, level: str) -> None:
        if level not in VALID_LEVELS:
            raise ValueError(f"Unknown visibility level: {level!r}")
        if level == LEVEL_VISIBLE:
            # Default — store nothing, just clear any override.
            self._vis_col.delete_one({"guild_id": guild_id, "command": command})
        else:
            self._vis_col.update_one(
                {"guild_id": guild_id, "command": command},
                {"$set": {"level": level}},
                upsert=True,
            )
        self.invalidate(guild_id)

    def set_cog_enabled(self, guild_id: Optional[int], cog: str, enabled: bool) -> None:
        if enabled:
            # Default — store nothing, just clear any override.
            self._cog_col.delete_one({"guild_id": guild_id, "cog": cog})
        else:
            self._cog_col.update_one(
                {"guild_id": guild_id, "cog": cog},
                {"$set": {"enabled": False}},
                upsert=True,
            )
        self.invalidate(guild_id)

    def set_feature_enabled(self, guild_id: Optional[int], feature: str, enabled: bool) -> None:
        if self._feature_col is None:
            return
        if enabled:
            self._feature_col.delete_one({"guild_id": guild_id, "feature": feature})
        else:
            self._feature_col.update_one(
                {"guild_id": guild_id, "feature": feature},
                {"$set": {"enabled": False}},
                upsert=True,
            )
        self.invalidate(guild_id)

    def add_guild_admin(self, guild_id: Optional[int], user_id: int) -> None:
        self._admin_col.update_one(
            {"guild_id": guild_id}, {"$addToSet": {"user_ids": int(user_id)}}, upsert=True
        )
        self.invalidate(guild_id)

    def remove_guild_admin(self, guild_id: Optional[int], user_id: int) -> None:
        self._admin_col.update_one({"guild_id": guild_id}, {"$pull": {"user_ids": int(user_id)}})
        self.invalidate(guild_id)
