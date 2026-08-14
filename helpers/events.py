"""
Event-rule plumbing: "when X happens, post this in that channel".

Three parts:

* **The catalog** — every event discord.py dispatches, discovered by reading the
  installed library rather than hardcoding a list, so it tracks the version in
  use (~100 events). A few are filtered out: the socket firehose fires per
  websocket frame, and some events carry no guild at all, so a per-guild rule
  could never match them.
* **The context** — an event's arguments turned into ``{placeholders}`` an admin
  can use in a message. Names come from argument types (``{member}``,
  ``{channel}``, ``{before}``/``{after}`` for update events), so this works for
  events nobody wrote special handling for.
* **The store** — rules in Mongo, cached per guild, with a set of "events any
  rule mentions" that the runtime checks on every single dispatch.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Optional

from bson import ObjectId

import discord

# Fires for every websocket frame — a rule here would be a flood, not a feature.
EXCLUDED_EVENTS = {"socket_raw_receive", "socket_raw_send", "socket_event_type"}

# Dispatched with nothing guild-shaped in their arguments, so a per-guild rule
# can never match. Kept out of the picker with that reason shown.
NON_GUILD_EVENTS = {
    "connect", "disconnect", "ready", "resumed", "shard_connect", "shard_disconnect",
    "shard_ready", "shard_resumed", "user_update", "private_channel_update",
    "private_channel_pins_update", "entitlement_create", "entitlement_update",
    "entitlement_delete", "subscription_create", "subscription_update", "subscription_delete",
}

_DISPATCH_RE = re.compile(r"""dispatch\(\s*['"]([a-z_0-9]+)['"]""")
_catalog: Optional[list[str]] = None


# --------------------------------------------------------------------------- #
#  Catalog
# --------------------------------------------------------------------------- #
def discover_events() -> list[str]:
    """Every event name the installed discord.py dispatches, sorted.

    Read from the library source: the names only exist as string literals in
    ``dispatch(...)`` calls, so there is nothing to introspect at runtime. A
    handful of call sites build the name from a variable (shard/raw plumbing)
    and are missed — those are internal ones with no rule value.
    """
    global _catalog
    if _catalog is not None:
        return _catalog
    names: set[str] = set()
    root = os.path.dirname(discord.__file__)
    for dirpath, _dirs, files in os.walk(root):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, filename), encoding="utf-8") as handle:
                    names.update(_DISPATCH_RE.findall(handle.read()))
            except OSError:
                continue
    _catalog = sorted(names - EXCLUDED_EVENTS)
    return _catalog


def selectable_events() -> list[str]:
    """Catalog entries a per-guild rule can actually match."""
    return [name for name in discover_events() if name not in NON_GUILD_EVENTS]


def group_of(event: str) -> str:
    """Bucket for the picker, taken from the event's first word."""
    if event.startswith("raw_"):
        return "raw"
    for prefix in ("guild_channel", "guild_role", "guild", "member", "message", "reaction",
                   "thread", "voice", "scheduled_event", "automod", "stage_instance",
                   "soundboard", "integration", "invite", "poll", "app_command", "command"):
        if event.startswith(prefix):
            return prefix
    return "other"


def grouped_events() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for event in selectable_events():
        groups.setdefault(group_of(event), []).append(event)
    return dict(sorted(groups.items()))


# --------------------------------------------------------------------------- #
#  Context building
# --------------------------------------------------------------------------- #
# Checked in order — the first match names the argument. More specific types
# come first (a Member is also a User; a Thread is also a channel).
_TYPE_NAMES: tuple[tuple[type, str], ...] = (
    (discord.Message, "message"),
    (discord.Member, "member"),
    (discord.User, "user"),
    (discord.Guild, "guild"),
    (discord.Role, "role"),
    (discord.Thread, "thread"),
    (discord.Reaction, "reaction"),
    (discord.Invite, "invite"),
    (discord.VoiceState, "voice_state"),
    (discord.Emoji, "emoji"),
    (discord.PartialEmoji, "emoji"),
    (discord.ScheduledEvent, "event"),
    (discord.StageInstance, "stage"),
    (discord.Interaction, "interaction"),
    (discord.AuditLogEntry, "entry"),
    (discord.abc.GuildChannel, "channel"),
    (discord.abc.PrivateChannel, "channel"),
)


# Attributes worth pulling out of an argument: an on_message rule wants the
# author and channel, not just the message.
_RELATED_ATTRS = ("author", "user", "member", "channel", "target", "role", "message", "thread")


def _typed_name(value: Any) -> Optional[str]:
    """The placeholder name for a known discord type, or ``None`` for anything else."""
    for kind, name in _TYPE_NAMES:
        try:
            if isinstance(value, kind):
                return name
        except TypeError:  # pragma: no cover - runtime-checkable protocol quirks
            continue
    return None


def _base_name(value: Any) -> str:
    known = _typed_name(value)
    if known:
        return known
    return type(value).__name__.lower().replace("raw", "").replace("event", "") or "value"


def _flatten(context: dict, name: str, value: Any) -> None:
    """Store an object plus its handy string forms (``_name`` / ``_mention`` / ``_id``)."""
    context[name] = value
    for suffix, attribute in (("name", "display_name"), ("name", "name"), ("mention", "mention"), ("id", "id")):
        key = f"{name}_{suffix}"
        if key in context:
            continue
        attr = getattr(value, attribute, None)
        if attr is not None and not callable(attr):
            context[key] = attr


def _expand_related(context: dict, values: list) -> list:
    """Add the discord objects hanging off ``values`` (author, channel, …).

    Returns what it added, so the caller can walk one level further — a reaction
    carries a message, and the message carries the author and channel.
    """
    added = []
    for value in values:
        for attribute in _RELATED_ATTRS:
            try:
                related = getattr(value, attribute, None)
            except Exception:  # noqa: BLE001 - lazy properties can raise
                continue
            name = _typed_name(related) if related is not None else None
            if name is None or name in context:
                continue
            _flatten(context, name, related)
            added.append(related)
    return added


def guild_id_from(args: tuple) -> Optional[int]:
    """The guild an event belongs to, or ``None`` if it isn't guild-scoped."""
    for value in args:
        if isinstance(value, discord.Guild):
            return value.id
        guild = getattr(value, "guild", None)
        if isinstance(guild, discord.Guild):
            return guild.id
        guild_id = getattr(value, "guild_id", None)
        if isinstance(guild_id, int):
            return guild_id
    return None


def build_context(event: str, args: tuple) -> dict[str, Any]:
    """Placeholders for an event's arguments.

    Two arguments of the same type in an ``*_update`` event become ``{before}``
    and ``{after}``; otherwise repeats are numbered. Alongside each object the
    context carries flattened ``_name`` / ``_mention`` / ``_id`` strings, so a
    template rarely needs attribute access.
    """
    context: dict[str, Any] = {}
    used: dict[str, int] = {}
    is_update = event.endswith("_update") or event.endswith("_edit")

    names = [_base_name(value) for value in args]
    for index, (value, name) in enumerate(zip(args, names)):
        if is_update and names.count(name) == 2:
            name = "before" if names.index(name) == index else "after"
        else:
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name = f"{name}{used[name]}"
        _flatten(context, name, value)

    # Two levels of related objects: args -> (author, channel, …) -> theirs.
    _expand_related(context, _expand_related(context, list(args)))

    guild = next((value for value in args if isinstance(value, discord.Guild)), None)
    guild = guild or next((getattr(v, "guild", None) for v in args if getattr(v, "guild", None)), None)
    if guild is not None:
        context.setdefault("guild", guild)
        context.setdefault("guild_name", guild.name)
    message = next((value for value in args if isinstance(value, discord.Message)), None)
    if message is not None:
        context.setdefault("content", message.content)
        context.setdefault("jump_url", message.jump_url)
    return context


def placeholders_for(context: dict) -> list[str]:
    """The placeholder names in a context, for showing in the panel."""
    return sorted(key for key in context if not key.startswith("_"))


# --------------------------------------------------------------------------- #
#  Rule storage
# --------------------------------------------------------------------------- #
class EventRuleManager:
    """Per-guild event rules, cached. ``bot.event_rules``.

    ``active_events`` is the runtime's fast path: it is consulted on every
    dispatch, so it must stay a plain in-memory set.
    """

    def __init__(self, collection) -> None:
        self._col = collection
        self._cache: dict[int, list[dict]] = {}
        self._active: set[str] = set()
        self.refresh_active()

    # ---------------------------------------------------------------- reads
    def refresh_active(self) -> None:
        """Recompute which events any enabled rule anywhere listens for."""
        try:
            self._active = {
                event for event in self._col.distinct("event", {"enabled": True}) if isinstance(event, str)
            }
        except Exception:  # noqa: BLE001 - never break the gateway over this
            self._active = set()

    def listens_for(self, event: str) -> bool:
        return event in self._active

    def for_guild(self, guild_id: int) -> list[dict]:
        if guild_id not in self._cache:
            self._cache[guild_id] = list(self._col.find({"guild_id": guild_id}).sort("_id", 1))
        return self._cache[guild_id]

    def matching(self, guild_id: int, event: str) -> list[dict]:
        return [
            rule for rule in self.for_guild(guild_id)
            if rule.get("event") == event and rule.get("enabled", True)
        ]

    # --------------------------------------------------------------- writes
    def _invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)
        self.refresh_active()

    def create(self, guild_id: int, data: dict) -> dict:
        rule = {
            "guild_id": guild_id,
            "event": data["event"],
            "name": data.get("name") or data["event"],
            "channel_id": int(data.get("channel_id") or 0),
            "message": data.get("message") or "",
            "ping_user_ids": [int(uid) for uid in data.get("ping_user_ids") or []],
            "ping_role_ids": [int(rid) for rid in data.get("ping_role_ids") or []],
            "enabled": bool(data.get("enabled", True)),
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        result = self._col.insert_one(rule)
        rule["_id"] = result.inserted_id
        self._invalidate(guild_id)
        return rule

    def update(self, guild_id: int, rule_id: str, data: dict) -> None:
        fields = {}
        for key in ("event", "name", "message"):
            if key in data:
                fields[key] = data[key]
        if "channel_id" in data:
            fields["channel_id"] = int(data.get("channel_id") or 0)
        if "enabled" in data:
            fields["enabled"] = bool(data["enabled"])
        for key in ("ping_user_ids", "ping_role_ids"):
            if key in data:
                fields[key] = [int(value) for value in data[key] or []]
        if fields:
            self._col.update_one({"_id": ObjectId(rule_id), "guild_id": guild_id}, {"$set": fields})
            self._invalidate(guild_id)

    def delete(self, guild_id: int, rule_id: str) -> None:
        self._col.delete_one({"_id": ObjectId(rule_id), "guild_id": guild_id})
        self._invalidate(guild_id)
