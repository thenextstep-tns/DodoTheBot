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
]


# --------------------------------------------------------------------------- #
#  Type coercion
# --------------------------------------------------------------------------- #
def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "on", "yes")


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
    if param_type == "str":
        return str(raw)
    if param_type in ("role", "channel"):
        return int(raw or 0)
    if param_type in ("list_role", "list_channel"):
        return _to_id_list(raw)
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
        """Specs + current values, for the panel."""
        return [
            {**spec, "value": self.get(guild_id, spec["key"])}
            for spec in self._by_cog.get(cog, [])
        ]

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
