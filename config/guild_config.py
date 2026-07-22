"""
Per-guild settings, backed by MongoDB with an in-memory cache.

Historically every channel/role ID was a module-level constant in
``config.guild`` — fine for the single ESO for Dodos server, but it made the bot
impossible to reuse elsewhere. This layer stores the same settings per guild in
a ``GuildConfig`` collection and merges them over the ``config.guild`` values,
which now act as the built-in defaults.

Reading a setting for a guild with no stored document returns the default, so
existing behaviour is unchanged until an admin overrides something with the
``/serverconfig`` commands. Look-ups are cached per guild and the cache entry is
dropped whenever that guild's settings are written.
"""

from typing import Any

from config import guild as _defaults
from config.database import db

guild_config_col = db["GuildConfig"]

# The settings an admin may override per guild, with the value used when a guild
# has not set its own. Only flat scalars and lists live here; richer structures
# (reaction-role maps, trial/clear tables) stay in ``config.guild`` for now.
MANAGED_KEYS: tuple[str, ...] = (
    # Channels
    "E4D_LOG", "E4D_ROLE_LOG", "LOG_CHANNEL", "MAIN_LOG", "WAYSHRINE", "SELECT_ROLES",
    "RANK_REQ", "ADMIN", "DODO_CHANNEL", "PET_CHANNEL", "ROLL_CHANNEL", "HUNT_CHANNEL",
    "VALENTINE_CHANNEL", "WEEKLY_CHANNEL", "WEEKLY_MESSAGE", "META_CHANNEL", "META_MESSAGE",
    "IMPROVING_DPS_CHANNEL", "TIME_CHANNEL", "FISHING_LOG", "FISHING_POND", "DAILY_CHANNEL",
    "DOTY_CHANNEL", "ANNOUNCEMENT_CHANNEL", "OPEN_RAID_CHANNEL", "DND_FORUM_CHANNEL_ID",
    "CONCLAVE_CHANNEL", "NEW_LOG_CHANNEL", "PAT_DECODE_CHANNEL", "roll_log", "ALERT_CHANNEL_ID",
    # Roles / messages
    "TRAP_ROLE_ID", "lodestar_role", "base_roles_msg",
    # Lists
    "starter_roles", "allowed_roles", "public_channels", "boss_spawn_channels",
    # Emoji
    "BAN_EMOJI", "SALUTE_EMOJI",
)

# Built-in defaults pulled from config.guild, resolved once at import.
DEFAULTS: dict[str, Any] = {key: getattr(_defaults, key) for key in MANAGED_KEYS}


class GuildConfigManager:
    """Cached read/write access to per-guild settings, layered over ``DEFAULTS``."""

    def __init__(self, collection=guild_config_col, defaults: dict | None = None) -> None:
        self._col = collection
        self._defaults = defaults if defaults is not None else DEFAULTS
        self._cache: dict[int, dict[str, Any]] = {}

    def get_all(self, guild_id: int | None) -> dict[str, Any]:
        """Return the merged (defaults + stored overrides) settings for a guild.

        ``guild_id`` may be ``None`` (e.g. a DM context), in which case the bare
        defaults are returned.
        """
        if guild_id is None:
            return dict(self._defaults)
        if guild_id not in self._cache:
            stored = self._col.find_one({"_id": guild_id}) or {}
            merged = dict(self._defaults)
            merged.update({k: v for k, v in stored.items() if k != "_id"})
            self._cache[guild_id] = merged
        return self._cache[guild_id]

    def get(self, guild_id: int | None, key: str, default: Any = None) -> Any:
        """Return a single setting for a guild, falling back to its default."""
        return self.get_all(guild_id).get(key, default)

    def set(self, guild_id: int, key: str, value: Any) -> None:
        """Persist an override for one setting and invalidate the guild's cache."""
        if key not in MANAGED_KEYS:
            raise KeyError(f"'{key}' is not a managed guild setting.")
        self._col.update_one({"_id": guild_id}, {"$set": {key: value}}, upsert=True)
        self._cache.pop(guild_id, None)

    def reset(self, guild_id: int, key: str) -> None:
        """Drop a stored override so the setting reverts to its default."""
        self._col.update_one({"_id": guild_id}, {"$unset": {key: ""}})
        self._cache.pop(guild_id, None)

    def is_overridden(self, guild_id: int, key: str) -> bool:
        """Whether a guild has stored its own value for ``key``."""
        stored = self._col.find_one({"_id": guild_id}, {key: 1}) or {}
        return key in stored

    def invalidate(self, guild_id: int | None = None) -> None:
        """Drop cached settings for one guild, or all guilds when ``None``."""
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(guild_id, None)
