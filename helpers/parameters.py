"""
Per-server command parameters.

Gameplay/behaviour tunables that should differ per guild (thresholds, limits,
reward sizes, role lists, …) live here as a typed registry with built-in
defaults, backed by the ``command_params`` collection. Cogs read them via
``bot.params.get(guild_id, "key")``; the control panel renders a typed input per
parameter under each cog.

This is deliberately separate from:
  - ``GuildConfigManager`` (per-guild **channel/role IDs** an admin sets — the
    existing store; cogs should read channels from there, per-guild), and
  - ``VisibilityManager`` (who can see/run commands and which cogs/features are on).

Add a parameter by appending a spec to ``PARAMETERS`` (grouped by cog) and reading
it in the cog. Types: int, float, bool, str, choice, role, channel, list_role.
Role/channel values are stored as integer IDs (0 = unset); the panel renders a
dropdown populated from the guild.
"""

from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
#  Parameter registry (grow this cog-by-cog)
# --------------------------------------------------------------------------- #
# Each spec: key, cog, label, description, type, default, and choices (for
# type="choice"). Keep keys globally unique and snake_case.
PARAMETERS: list[dict] = [
    # --- moderation ---
    {"key": "purge_max", "cog": "moderation", "type": "int", "default": 50,
     "label": "Max purge", "description": "Largest number of messages /purge will delete at once."},
    {"key": "pin_allowed_roles", "cog": "moderation", "type": "list_role",
     "default": [852793776064692264, 1055862512689623181],
     "label": "Pin roles", "description": "Roles allowed to use the reply-to-pin command."},
    {"key": "unpin_role", "cog": "moderation", "type": "role", "default": 852793776064692264,
     "label": "Unpin role", "description": "Role allowed to unpin messages."},
    # --- spam (anti-spam auto-ban feature) ---
    {"key": "spam_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Rate threshold", "description": "Messages within the rate window before a ban triggers."},
    {"key": "spam_time_window", "cog": "spam", "type": "float", "default": 2.0,
     "label": "Rate window (s)", "description": "Seconds the rate threshold is measured over."},
    {"key": "multi_channel_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Multi-channel threshold", "description": "Distinct channels posted in before a ban triggers."},
    {"key": "multi_channel_window", "cog": "spam", "type": "float", "default": 1.0,
     "label": "Multi-channel window (s)", "description": "Seconds the multi-channel spread is measured over."},
    {"key": "duplicate_channel_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Cross-post threshold", "description": "Distinct channels the same message may appear in before a ban."},
    {"key": "duplicate_window", "cog": "spam", "type": "int", "default": 30,
     "label": "Cross-post window (s)", "description": "Seconds over which identical messages across channels are tracked."},
    {"key": "duplicate_min_len", "cog": "spam", "type": "int", "default": 8,
     "label": "Cross-post min text", "description": "Minimum text length for a text-only message to count (attachments always count)."},
    # --- spam: @everyone/@here + unauthorized-link filter (mention_link_filter feature) ---
    {"key": "restricted_strings", "cog": "spam", "type": "list_str",
     "default": ["discord.gg", "@everyone", "@here"],
     "label": "Restricted strings", "description": "A message containing any of these (and no allowed link/role) is removed."},
    {"key": "allowed_links", "cog": "spam", "type": "list_str",
     "default": [
         "discord.gg/8ewt2Fe", "discord.gg/esou", "discord.gg/uesp", "discord.gg/ZaPwNHKQBg",
         "discord.gg/35FMqVQJgY", "discord.gg/enterthedominion", "discord.gg/FAU9A2pBY7",
         "discord.gg/5NaETqTjDD", "discord.gg/fmrgcr4Dc5", "dodos.fun", "discord.gg/e4d",
         "discord.gg/tBdB6KZzmf", "discord.gg/jEXVVgBTUP", "discord.gg/7xjfDDx6cX",
         "discord.gg/78xRCj4QVa", "discord.gg/fQXqfWDmWa", "discord.gg/pXV23eZZ86",
         "discord.gg/MuwsNJcqEw", "discord.gg/healershaven", "discord.gg/mindcleaver",
         "discord.gg/dpsnerds", "discord.gg/B6cyn3uMr", "discord.gg/68PsPTmk3P",
     ],
     "label": "Allowed links", "description": "Links/invites that are never removed (substring match)."},
    {"key": "allowed_guild_ids", "cog": "spam", "type": "list_int", "default": [],
     "label": "Allowed invite guilds", "description": "Guild IDs whose invites are allowed (invites are resolved and checked)."},
    # --- economy ---
    {"key": "starting_balance", "cog": "economy", "type": "int", "default": 0,
     "label": "Starting balance", "description": "Coins a brand-new wallet is created with."},
    # --- gym ---
    {"key": "gym_session_hours", "cog": "gym", "type": "int", "default": 24,
     "label": "Gym session (hours)", "description": "How long a cat trains before its attribute goes up."},
    {"key": "gym_stat_gain", "cog": "gym", "type": "int", "default": 1,
     "label": "Gym stat gain", "description": "How many points the trained attribute gains per session."},
    # --- fishing ---
    {"key": "fishing_cost", "cog": "fishing", "type": "int", "default": 10,
     "label": "Fishing cost", "description": "Coins deducted per fishing attempt."},
    {"key": "fishing_bag_max", "cog": "fishing", "type": "int", "default": 24,
     "label": "Goodies bag size", "description": "Max items a user can keep stashed."},
    # --- cheese (co-op cheese-stretch minigame; listener feature) ---
    {"key": "cheese_drop_threshold", "cog": "cheese", "type": "int", "default": 985,
     "label": "Drop threshold", "description": "0–1000 roll; a 🧀 drops when the roll is above this (higher = rarer)."},
    {"key": "cheese_event_timeout", "cog": "cheese", "type": "int", "default": 25,
     "label": "Stretch timeout (s)", "description": "Seconds of inactivity before the cheese fizzles."},
    {"key": "cheese_steal_divisor", "cog": "cheese", "type": "int", "default": 5,
     "label": "Steal divisor", "description": "A thief grabs ceil(total stretch / this) for themselves."},
    {"key": "cheese_mouse_chance", "cog": "cheese", "type": "float", "default": 0.02,
     "label": "Mouse peek chance", "description": "Per-pull chance an adopted mouse peeks out (0–1)."},
    {"key": "cheese_mouse_sweetrolls", "cog": "cheese", "type": "int", "default": 5,
     "label": "Mouse sweetrolls", "description": "Sweetrolls each puller gets if the mouse eats the cheese."},
    {"key": "mouse_adoption_rank", "cog": "cheese", "type": "int", "default": 250,
     "label": "Adoption rank", "description": "Relationship points with a mouse before adoption is offered (shared with racing)."},
    # --- racing (skeevaton races) ---
    {"key": "race_reaction_window", "cog": "racing", "type": "float", "default": 2.0,
     "label": "Reaction window (s)", "description": "Seconds players get to click a cheese/wine/bomb/starry-eyes/map event mid-race."},
    # --- pumpkin (pull minigame in bot.py + team deathmatch) ---
    {"key": "pumpkin_role_id", "cog": "pumpkin", "type": "role", "default": 1430471888412475413,
     "label": "Pumpkin role", "description": "The 'covered in guts' / collector role."},
    {"key": "pumpkin_role_threshold", "cog": "pumpkin", "type": "int", "default": 50,
     "label": "Role threshold", "description": "Pumpkins collected before the pumpkin role is granted."},
    {"key": "pumpkin_weight_min", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Giant pumpkin min kg", "description": "Lightest a spawned giant pumpkin can be."},
    {"key": "pumpkin_weight_max", "cog": "pumpkin", "type": "int", "default": 800,
     "label": "Giant pumpkin max kg", "description": "Heaviest a spawned giant pumpkin can be."},
    {"key": "pumpkin_strength_start", "cog": "pumpkin", "type": "int", "default": 50,
     "label": "Base pull strength", "description": "Starting pull strength for a new puller."},
    {"key": "pumpkin_strength_gain", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Pull strength gain", "description": "Strength gained each time you join a pull."},
    {"key": "fight_join_cost", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Fight join cost", "description": "Pumpkins to join a deathmatch."},
    # --- chat (LLM) ---
    {"key": "chat_api_key", "cog": "chat", "type": "secret", "default": "",
     "label": "Chat API key", "description": "This server's own LLM API key (proxyapi.ru). Required — only the owner's own server falls back to the bot's default key."},
    {"key": "chat_personality", "cog": "chat", "type": "text",
     "default": ('You are Dodo, a bird from "ESO for Dodos". You give out concise wise and profound '
                 "things, but also sometimes randomly unhinged and stupid."),
     "label": "Bot personality", "description": "The base persona injected into the chat system prompt for this server."},
    # --- dnd (Dodo Tabletop — see docs/dnd/) ---
    # Only parameters something actually reads today live here; the rest arrive
    # with the phase that needs them, so the panel never shows a dead setting.
    {"key": "dnd_default_ruleset", "cog": "dnd", "type": "choice", "default": "freeform",
     "choices": ["freeform", "srd5e"],
     "label": "Default ruleset", "description": "Ruleset a new campaign starts with. Freeform is narrative; srd5e is D&D 5e SRD 5.1."},
    {"key": "dnd_max_dice", "cog": "dnd", "type": "int", "default": 100,
     "label": "Max dice per roll", "description": "Largest number of dice a single roll expression may throw."},
    {"key": "dnd_max_sides", "cog": "dnd", "type": "int", "default": 1000,
     "label": "Max die size", "description": "Largest die a roll expression may use."},
    # --- general (server-wide) ---
    {"key": "command_prefix", "cog": "general", "type": "str", "default": "",
     "label": "Command prefix", "description": "Text prefix for commands on this server. Blank = the bot default."},
]


# --------------------------------------------------------------------------- #
#  Type coercion
# --------------------------------------------------------------------------- #
def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "on", "yes")


def _to_str_list(raw: Any) -> list[str]:
    """One string per line (or a list); blanks dropped."""
    if isinstance(raw, list):
        items = [str(x) for x in raw]
    elif raw in (None, ""):
        items = []
    else:
        items = str(raw).replace("\r\n", "\n").split("\n")
    return [s.strip() for s in items if s.strip()]


def _to_id_list(raw: Any) -> list[int]:
    if isinstance(raw, list):
        items = raw
    elif raw in (None, ""):
        items = []
    else:
        items = str(raw).replace(",", " ").split()
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def coerce(param_type: str, raw: Any, *, choices: Optional[list] = None) -> Any:
    """Coerce a raw (JSON/string) value to the parameter's native type. Raises
    ``ValueError`` on invalid input so the API can report it."""
    if param_type == "int":
        return int(raw)
    if param_type == "float":
        return float(raw)
    if param_type == "bool":
        return _to_bool(raw)
    if param_type in ("str", "secret", "text"):
        return str(raw)
    if param_type in ("role", "channel"):
        return int(raw or 0)
    if param_type in ("list_role", "list_channel", "list_int"):
        return _to_id_list(raw)
    if param_type == "list_str":
        return _to_str_list(raw)
    if param_type == "choice":
        value = str(raw)
        if choices and value not in choices:
            raise ValueError(f"{value!r} is not one of {choices}")
        return value
    raise ValueError(f"Unknown parameter type: {param_type!r}")


class ParamManager:
    """Reads/writes per-guild command parameters with typed coercion + a per-guild
    cache. Instantiated once as ``bot.params``."""

    def __init__(self, collection, specs: list[dict] = PARAMETERS):
        self._col = collection
        self._by_key = {spec["key"]: spec for spec in specs}
        self._by_cog: dict[str, list[dict]] = {}
        for spec in specs:
            self._by_cog.setdefault(spec["cog"], []).append(spec)
        self._cache: dict[Optional[int], dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def _stored(self, guild_id: Optional[int]) -> dict[str, Any]:
        if guild_id not in self._cache:
            self._cache[guild_id] = {
                doc["key"]: doc["value"]
                for doc in self._col.find({"guild_id": guild_id})
                if doc.get("key") in self._by_key
            }
        return self._cache[guild_id]

    def get(self, guild_id: Optional[int], key: str) -> Any:
        """The value for a parameter in a guild, or its built-in default."""
        spec = self._by_key.get(key)
        if spec is None:
            raise KeyError(f"Unknown parameter: {key!r}")
        return self._stored(guild_id).get(key, spec["default"])

    def specs_for_cog(self, cog: str) -> list[dict]:
        return list(self._by_cog.get(cog, []))

    def entries_for_cog(self, guild_id: Optional[int], cog: str) -> list[dict]:
        """Specs + current values, for the panel. ``secret`` values are never sent
        to the client — only whether one is set."""
        entries = []
        for spec in self._by_cog.get(cog, []):
            value = self.get(guild_id, spec["key"])
            if spec["type"] == "secret":
                entries.append({**spec, "value": "", "is_set": bool(value)})
            else:
                entries.append({**spec, "value": value})
        return entries

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def invalidate(self, guild_id: Optional[int]) -> None:
        self._cache.pop(guild_id, None)

    def set(self, guild_id: Optional[int], key: str, raw: Any) -> Any:
        """Coerce + store a parameter override. Returns the stored value; raises
        ``KeyError`` for an unknown key or ``ValueError`` for a bad value."""
        spec = self._by_key.get(key)
        if spec is None:
            raise KeyError(f"Unknown parameter: {key!r}")
        value = coerce(spec["type"], raw, choices=spec.get("choices"))
        if value == spec["default"]:
            self._col.delete_one({"guild_id": guild_id, "key": key})
        else:
            self._col.update_one(
                {"guild_id": guild_id, "key": key}, {"$set": {"value": value}}, upsert=True
            )
        self.invalidate(guild_id)
        return value
