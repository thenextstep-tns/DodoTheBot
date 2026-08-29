"""
Input validation for the control panel.

Every panel write goes through here. Two jobs:

* **Types.** Values arrive as JSON from a browser, so an id can turn up as a
  string, a number, ``null`` or a dict. Anything that isn't coercible to the
  expected shape is rejected rather than stored — a dict reaching a Mongo query
  as a *value* is how ``{"$ne": ...}`` style operator injection happens.
* **Ownership.** A channel or role id is only acceptable if it belongs to *the
  guild being edited*. Without that check, an admin of one server could point
  another server's log channel at their own, or grant a role they don't own —
  the ids are just numbers, and the panel is per-guild by scope only.

Raises :class:`ValidationError`; callers turn it into a 200 with an error
message so the panel can show it inline.
"""

from __future__ import annotations

from typing import Iterable, Optional

import discord

# Discord's own limits, so we reject before the API does.
MAX_MESSAGE = 2000
MAX_NAME = 100
MAX_TEXT = 4000
# Snowflakes are 64-bit; anything outside this isn't an id.
_MIN_SNOWFLAKE = 10_000_000_000_000_00  # ~2015, when Discord ids start
_MAX_SNOWFLAKE = 2**63 - 1


class ValidationError(ValueError):
    """A rejected panel input, with a message meant for the user."""


def boolean(value, *, field: str = "value") -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1, "0", "1", "true", "false", "True", "False"):
        return value in (1, "1", "true", "True")
    raise ValidationError(f"{field} must be true or false.")


def integer(value, *, field: str = "value", minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    if isinstance(value, bool) or isinstance(value, (dict, list)):
        raise ValidationError(f"{field} must be a number.")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.") from None
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.")
    return number


def text(value, *, field: str = "value", max_length: int = MAX_TEXT, allow_empty: bool = True) -> str:
    if value is None:
        value = ""
    if isinstance(value, (dict, list, bool)):
        raise ValidationError(f"{field} must be text.")
    out = str(value)
    if not allow_empty and not out.strip():
        raise ValidationError(f"{field} can't be empty.")
    if len(out) > max_length:
        raise ValidationError(f"{field} is too long ({len(out)} characters, max {max_length}).")
    # Control characters other than tab/newline have no business in a stored
    # string and can garble both the panel and Discord.
    return "".join(ch for ch in out if ch in "\t\n" or ch.isprintable())


def choice(value, allowed: Iterable[str], *, field: str = "value") -> str:
    allowed = list(allowed)
    if value not in allowed:
        raise ValidationError(f"{field} must be one of: {', '.join(allowed)}.")
    return value


def snowflake(value, *, field: str = "id", allow_zero: bool = True) -> int:
    """A Discord id. ``0`` means "unset" and is allowed unless told otherwise."""
    if value in (None, "", "0", 0):
        if allow_zero:
            return 0
        raise ValidationError(f"{field} is required.")
    number = integer(value, field=field)
    if number and not (_MIN_SNOWFLAKE <= number <= _MAX_SNOWFLAKE):
        raise ValidationError(f"{field} doesn't look like a Discord id.")
    return number


def snowflake_list(value, *, field: str = "ids", max_items: int = 200) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = [part for part in value.replace(",", " ").split() if part]
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list of ids.")
    if len(value) > max_items:
        raise ValidationError(f"{field} has too many entries (max {max_items}).")
    out = []
    for item in value:
        got = snowflake(item, field=field, allow_zero=False)
        if got not in out:
            out.append(got)
    return out


# --------------------------------------------------------------------------- #
#  Ownership — the id must belong to the guild being edited
# --------------------------------------------------------------------------- #
def guild_channel(guild, value, *, field: str = "channel", allow_zero: bool = True) -> int:
    """A channel id that exists **in this guild** (0 clears it)."""
    channel_id = snowflake(value, field=field, allow_zero=allow_zero)
    if not channel_id:
        return 0
    if guild.get_channel_or_thread(channel_id) is None:
        raise ValidationError(f"That {field} isn't a channel in this server.")
    return channel_id


def guild_role(guild, value, *, field: str = "role", allow_zero: bool = True) -> int:
    """A role id that exists **in this guild** (0 clears it)."""
    role_id = snowflake(value, field=field, allow_zero=allow_zero)
    if not role_id:
        return 0
    if guild.get_role(role_id) is None:
        raise ValidationError(f"That {field} isn't a role in this server.")
    return role_id


def guild_channels(guild, value, *, field: str = "channels") -> list[int]:
    ids = snowflake_list(value, field=field)
    for channel_id in ids:
        if guild.get_channel_or_thread(channel_id) is None:
            raise ValidationError(f"One of the {field} isn't a channel in this server.")
    return ids


def guild_roles(guild, value, *, field: str = "roles") -> list[int]:
    ids = snowflake_list(value, field=field)
    for role_id in ids:
        if guild.get_role(role_id) is None:
            raise ValidationError(f"One of the {field} isn't a role in this server.")
    return ids


def assignable_role(guild, value, *, field: str = "role") -> int:
    """A role this guild's bot can actually hand out.

    Rejects @everyone, integration-managed roles, and anything at or above the
    bot's own top role — the three cases Discord would refuse anyway.
    """
    role_id = guild_role(guild, value, field=field, allow_zero=False)
    role = guild.get_role(role_id)
    me = guild.me
    if role.is_default():
        raise ValidationError("@everyone can't be assigned.")
    if role.managed:
        raise ValidationError(f"**{role.name}** is managed by an integration and can't be assigned.")
    if me is not None and role >= me.top_role:
        raise ValidationError(f"**{role.name}** sits above the bot's highest role, so it can't be assigned.")
    return role_id


def mention_safe(content: str) -> "discord.AllowedMentions":
    """Allowed mentions for admin-authored text: pings people and roles, never
    @everyone/@here, regardless of what the text contains."""
    return discord.AllowedMentions(users=True, roles=True, everyone=False, replied_user=False)
