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

# Every setting an admin may override per guild, with the type the panel renders
# and a note on what actually reads it. Only flat scalars and lists live here;
# richer structures (reaction-role maps, trial/clear tables) stay in
# ``config.guild`` for now. ``used_by`` is "" for settings nothing reads yet —
# they are kept because they are part of the server's configuration surface.
#
# Types: channel · role · message (a message id) · text (multiline) · str ·
# emoji · list_role · list_channel.
SETTING_SPECS: tuple[dict[str, Any], ...] = (
    # ---------------------------------------------------------------- logging
    {"key": "LOG_CHANNEL", "type": "channel", "group": "Logging", "label": "Moderation log",
     "description": "Kicks, bans, nickname changes, purges and mass role changes are reported here.",
     "used_by": "moderation, seasonal"},
    {"key": "E4D_LOG", "type": "channel", "group": "Logging", "label": "Filter log",
     "description": "Where removed messages from the @everyone/link filter are reported.", "used_by": "spam"},
    {"key": "E4D_ROLE_LOG", "type": "channel", "group": "Logging", "label": "Role request log",
     "description": "Role self-assignment requests and their outcomes.", "used_by": "bot"},
    {"key": "MAIN_LOG", "type": "channel", "group": "Logging", "label": "Main log",
     "description": "General-purpose log channel.", "used_by": ""},
    {"key": "NEW_LOG_CHANNEL", "type": "channel", "group": "Logging", "label": "Secondary log",
     "description": "Alternate log channel kept from an older setup.", "used_by": ""},
    {"key": "roll_log", "type": "channel", "group": "Logging", "label": "Roll log",
     "description": "Dice rolls and pumpkin pulls are recorded here.", "used_by": "deathroll, pumpkin"},

    # -------------------------------------------------- welcome & onboarding
    {"key": "WELCOME_CHANNEL", "type": "channel", "group": "Welcome & onboarding", "label": "Welcome channel",
     "description": "Where the join message is posted. Leave unset to post nothing.", "used_by": "bot"},
    {"key": "WELCOME_MESSAGE", "type": "text", "group": "Welcome & onboarding", "label": "Welcome message",
     "description": "Posted when someone joins for the first time. Placeholders: {mention} {name} {guild} "
                    "{rank_req} {select_roles}.", "used_by": "bot"},
    {"key": "WELCOME_BACK_MESSAGE", "type": "text", "group": "Welcome & onboarding",
     "label": "Welcome-back message",
     "description": "Posted when a returning member's previous roles are restored. Same placeholders.",
     "used_by": "bot"},
    {"key": "starter_roles", "type": "list_role", "group": "Welcome & onboarding", "label": "Starter roles",
     "description": "Automatically granted to every new member on join.", "used_by": "bot"},
    {"key": "WAYSHRINE", "type": "channel", "group": "Welcome & onboarding", "label": "Wayshrine",
     "description": "Arrivals channel (the historical welcome destination).", "used_by": "bot"},
    {"key": "RANK_REQ", "type": "channel", "group": "Welcome & onboarding", "label": "Rank requests",
     "description": "Where members post clears to get ranked — referenced by the welcome message.",
     "used_by": "bot"},
    {"key": "SELECT_ROLES", "type": "channel", "group": "Welcome & onboarding", "label": "Role selection",
     "description": "Self-service role picking — referenced by the welcome message.", "used_by": "bot"},
    {"key": "base_roles_msg", "type": "message", "group": "Welcome & onboarding", "label": "Base roles message",
     "description": "Message id carrying the base reaction-role picker.", "used_by": ""},

    # ------------------------------------------------- moderation & safety
    {"key": "TRAP_ROLE_ID", "type": "role", "group": "Moderation & safety", "label": "Bot-trap role",
     "description": "Anyone who gains this role is treated as a bot account and banned.", "used_by": "bot"},
    {"key": "ALERT_CHANNEL_ID", "type": "channel", "group": "Moderation & safety", "label": "Alert channel",
     "description": "Auto-ban and anti-spam alerts, with the confirm/dismiss reactions.", "used_by": "bot, spam"},
    {"key": "allowed_roles", "type": "list_role", "group": "Moderation & safety", "label": "Filter-exempt roles",
     "description": "Members with any of these bypass the @everyone/link filter.", "used_by": "spam"},
    {"key": "BAN_EMOJI", "type": "emoji", "group": "Moderation & safety", "label": "Confirm-ban emoji",
     "description": "Reaction a moderator clicks to confirm an automatic ban.", "used_by": "bot"},
    {"key": "SALUTE_EMOJI", "type": "emoji", "group": "Moderation & safety", "label": "Salute emoji",
     "description": "Reaction used to acknowledge an alert.", "used_by": ""},
    {"key": "ADMIN", "type": "channel", "group": "Moderation & safety", "label": "Admin channel",
     "description": "Private admin discussion channel.", "used_by": ""},

    # ---------------------------------------------------- community channels
    {"key": "DODO_CHANNEL", "type": "channel", "group": "Community", "label": "Bot channel",
     "description": "Main channel for bot chatter.", "used_by": ""},
    {"key": "PET_CHANNEL", "type": "channel", "group": "Community", "label": "Pet channel",
     "description": "Where pet adoptions and pet events are posted.", "used_by": "bot, pet"},
    {"key": "PAT_DECODE_CHANNEL", "type": "channel", "group": "Community", "label": "Parse decode channel",
     "description": "Messages here are auto-decoded as parse links.", "used_by": "pat"},
    {"key": "ANNOUNCEMENT_CHANNEL", "type": "channel", "group": "Community", "label": "Announcements",
     "description": "Race announcements and other broadcasts.", "used_by": "racing"},
    {"key": "WEEKLY_CHANNEL", "type": "channel", "group": "Community", "label": "Weekly schedule channel",
     "description": "Holds the pinned weekly schedule message.", "used_by": "general"},
    {"key": "WEEKLY_MESSAGE", "type": "message", "group": "Community", "label": "Weekly schedule message",
     "description": "Message id of the schedule that /schedule123 DMs out.", "used_by": "general"},
    {"key": "META_CHANNEL", "type": "channel", "group": "Community", "label": "Meta channel",
     "description": "Channel holding the meta/build message.", "used_by": ""},
    {"key": "META_MESSAGE", "type": "message", "group": "Community", "label": "Meta message",
     "description": "Message id of the meta/build post.", "used_by": ""},
    {"key": "IMPROVING_DPS_CHANNEL", "type": "channel", "group": "Community", "label": "Improving DPS",
     "description": "Guide channel linked when advice is given.", "used_by": ""},
    {"key": "TIME_CHANNEL", "type": "channel", "group": "Community", "label": "Time channel",
     "description": "Channel used for time/timezone posts.", "used_by": ""},
    {"key": "public_channels", "type": "list_channel", "group": "Community", "label": "Public channels",
     "description": "Channels the quote game and imitation engine may quote from. Keep private "
                    "channels out of this list.", "used_by": "quote, talkengine"},

    # ------------------------------------------------------- games & events
    {"key": "OPEN_RAID_CHANNEL", "type": "channel", "group": "Games & events", "label": "Open raids",
     "description": "Forum/channel where scheduled raid posts are created.", "used_by": "scheduler"},
    {"key": "DND_FORUM_CHANNEL_ID", "type": "channel", "group": "Games & events", "label": "D&D forum",
     "description": "Forum channel the D&D cog opens threads in.", "used_by": "dnd"},
    {"key": "CONCLAVE_CHANNEL", "type": "channel", "group": "Games & events", "label": "Conclave channel",
     "description": "Where the conclave game runs.", "used_by": ""},
    {"key": "HUNT_CHANNEL", "type": "channel", "group": "Games & events", "label": "Hunt channel",
     "description": "Scavenger-hunt destination.", "used_by": ""},
    {"key": "ROLL_CHANNEL", "type": "channel", "group": "Games & events", "label": "Roll channel",
     "description": "Where dice games are played.", "used_by": ""},
    {"key": "FISHING_POND", "type": "channel", "group": "Games & events", "label": "Fishing pond",
     "description": "Channel fishing takes place in.", "used_by": ""},
    {"key": "FISHING_LOG", "type": "channel", "group": "Games & events", "label": "Fishing log",
     "description": "Where catches are recorded.", "used_by": ""},
    {"key": "DAILY_CHANNEL", "type": "channel", "group": "Games & events", "label": "Daily channel",
     "description": "Daily reward/streak posts.", "used_by": ""},
    {"key": "DOTY_CHANNEL", "type": "channel", "group": "Games & events", "label": "Dodo of the Year",
     "description": "Channel the DOTY voting threads are created in.", "used_by": "seasonal"},
    {"key": "VALENTINE_CHANNEL", "type": "channel", "group": "Games & events", "label": "Valentine channel",
     "description": "Where valentines are delivered.", "used_by": "seasonal"},
    {"key": "boss_spawn_channels", "type": "list_channel", "group": "Games & events", "label": "Boss spawn channels",
     "description": "Channels world bosses may spawn in.", "used_by": "server_config"},
    {"key": "lodestar_role", "type": "role", "group": "Games & events", "label": "Lodestar role",
     "description": "Role tied to the lodestar event.", "used_by": ""},
)

MANAGED_KEYS: tuple[str, ...] = tuple(spec["key"] for spec in SETTING_SPECS)
SPECS_BY_KEY: dict[str, dict] = {spec["key"]: spec for spec in SETTING_SPECS}
# Panel display order.
GROUPS: tuple[str, ...] = tuple(dict.fromkeys(spec["group"] for spec in SETTING_SPECS))

# Built-in defaults pulled from config.guild, resolved once at import.
DEFAULTS: dict[str, Any] = {key: getattr(_defaults, key) for key in MANAGED_KEYS}


def coerce(key: str, raw: Any) -> Any:
    """Turn a panel-submitted value into what the setting stores.

    Ids arrive as strings from HTML controls; 0 (or blank) means "unset", which
    is how the existing readers already treat a missing channel or role.
    """
    spec = SPECS_BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"'{key}' is not a managed guild setting.")
    kind = spec["type"]
    if kind in ("channel", "role", "message"):
        if raw in (None, "", "0", 0):
            return 0
        return int(raw)
    if kind in ("list_role", "list_channel"):
        if isinstance(raw, str):
            raw = [part for part in raw.replace(",", " ").split() if part]
        return [int(item) for item in raw or []]
    if kind in ("text", "str", "emoji"):
        return "" if raw is None else str(raw)
    return raw


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

    # Annotation quoted: this class defines a method named ``set``, which shadows
    # the builtin inside the class body.
    def overridden_keys(self, guild_id: int) -> "set[str]":
        """Every key this guild has stored, in one query.

        The panel needs this for all ~40 settings at once; asking per key would
        be one round-trip each, on the event loop.
        """
        stored = self._col.find_one({"_id": guild_id}) or {}
        return {key for key in stored if key != "_id"}

    def invalidate(self, guild_id: int | None = None) -> None:
        """Drop cached settings for one guild, or all guilds when ``None``."""
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(guild_id, None)
