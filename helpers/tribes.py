"""
Tribes — "who gets this role", as a rule you build rather than a script.

A tribe is a **condition tree** plus the role(s) it grants. Conditions nest, so
arbitrary logic is expressible:

    all(
        has_role(A), has_role(B),
        any( has_role(C), all(has_role(D), has_role(E)), has_role_any(F, G) )
    )

Node types:

* ``all`` / ``any`` / ``not`` — groups, with ``children``
* ``has_role``    — holds all (or any) of ``role_ids``
* ``member_for``  — joined the server more than ``days`` ago
* ``account_for`` — Discord account older than ``days``
* ``metric_min``  — at least ``min`` messages/threads, optionally limited to ``channel_ids``
* ``metric_top``  — inside the top ``n`` by that metric for those channels

Evaluation never touches Discord or Mongo: a sweep builds a
:class:`MemberFacts` table for the whole guild once, then every member is
checked against every tribe in memory. That is what makes ranking conditions
("top 10 in #general") answerable at all — a rank only exists relative to
everyone else, so it has to be computed as a set.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from bson import ObjectId

GROUP_TYPES = ("all", "any", "not")
LEAF_TYPES = ("has_role", "member_for", "account_for", "metric_min", "metric_top")
METRICS = ("messages", "threads")
ROLE_MODES = ("all", "any")

MAX_DEPTH = 6
MAX_NODES = 60

# Human labels for the panel.
NODE_LABELS = {
    "all": "ALL of these must match",
    "any": "ANY of these must match",
    "not": "NONE of these may match",
    "has_role": "Has role(s)",
    "member_for": "On the server for at least",
    "account_for": "Account older than",
    "metric_min": "At least N messages/threads",
    "metric_top": "In the top N by messages/threads",
}
METRIC_LABELS = {"messages": "messages sent", "threads": "threads created"}


class RuleError(ValueError):
    """A malformed condition tree, with a message meant for the panel."""


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
def validate_node(node: Any, *, guild=None, depth: int = 0, counter: Optional[list] = None) -> dict:
    """Type-check one condition node (recursively) and return it normalised.

    ``guild`` (optional) additionally checks that role/channel ids belong to it,
    the same ownership rule the rest of the panel applies.
    """
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise RuleError(f"Rule is too large (max {MAX_NODES} conditions).")
    if depth > MAX_DEPTH:
        raise RuleError(f"Rule is nested too deeply (max {MAX_DEPTH} levels).")
    if not isinstance(node, dict):
        raise RuleError("Each condition must be an object.")

    kind = node.get("type")
    if kind in GROUP_TYPES:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            raise RuleError(f"'{kind}' needs at least one condition inside it.")
        return {
            "type": kind,
            "children": [validate_node(child, guild=guild, depth=depth + 1, counter=counter)
                         for child in children],
        }

    if kind == "has_role":
        ids = _ids(node.get("role_ids"), "role_ids")
        if not ids:
            raise RuleError("Pick at least one role.")
        if guild is not None:
            for role_id in ids:
                if guild.get_role(role_id) is None:
                    raise RuleError("A role in this rule isn't in this server.")
        mode = node.get("mode", "all")
        if mode not in ROLE_MODES:
            raise RuleError("Role match mode must be 'all' or 'any'.")
        return {"type": kind, "role_ids": ids, "mode": mode}

    if kind in ("member_for", "account_for"):
        return {"type": kind, "days": _positive_int(node.get("days"), "days")}

    if kind in ("metric_min", "metric_top"):
        metric = node.get("metric", "messages")
        if metric not in METRICS:
            raise RuleError("Metric must be messages or threads.")
        channel_ids = _ids(node.get("channel_ids"), "channel_ids")
        if guild is not None:
            for channel_id in channel_ids:
                if guild.get_channel_or_thread(channel_id) is None:
                    raise RuleError("A channel in this rule isn't in this server.")
        out = {"type": kind, "metric": metric, "channel_ids": channel_ids}
        if kind == "metric_min":
            out["min"] = _positive_int(node.get("min"), "minimum")
        else:
            out["n"] = _positive_int(node.get("n"), "top N")
        return out

    raise RuleError(f"Unknown condition type: {kind!r}")


def _ids(value, field: str) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise RuleError(f"{field} must be a list.")
    out = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            raise RuleError(f"{field} must contain ids.") from None
        if number not in out:
            out.append(number)
    return out


def _positive_int(value, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise RuleError(f"{field} must be a whole number.") from None
    if number < 0:
        raise RuleError(f"{field} can't be negative.")
    return number


def describe(node: dict, guild=None) -> str:
    """A one-line, human-readable rendering of a condition tree."""
    kind = node.get("type")
    if kind in GROUP_TYPES:
        joiner = {"all": " AND ", "any": " OR ", "not": ", "}[kind]
        inner = joiner.join(describe(child, guild) for child in node.get("children", []))
        return f"NOT ({inner})" if kind == "not" else f"({inner})"
    if kind == "has_role":
        names = []
        for role_id in node["role_ids"]:
            role = guild.get_role(role_id) if guild else None
            names.append(f"@{role.name}" if role else f"role {role_id}")
        return (" & " if node.get("mode") == "all" else " / ").join(names)
    if kind == "member_for":
        return f"member for {node['days']}d"
    if kind == "account_for":
        return f"account older than {node['days']}d"
    scope = ""
    if node.get("channel_ids"):
        names = []
        for channel_id in node["channel_ids"]:
            channel = guild.get_channel_or_thread(channel_id) if guild else None
            names.append(f"#{channel.name}" if channel else str(channel_id))
        scope = " in " + ", ".join(names)
    metric = METRIC_LABELS.get(node.get("metric", "messages"), "messages")
    if kind == "metric_min":
        return f"≥{node['min']} {metric}{scope}"
    return f"top {node['n']} by {metric}{scope}"


# --------------------------------------------------------------------------- #
#  Facts + evaluation
# --------------------------------------------------------------------------- #
class MemberFacts:
    """Everything the rules need about one guild, computed once per sweep.

    ``messages`` / ``threads`` map ``user_id -> {channel_id: count}``; totals and
    rankings are derived from them for whatever channel set a condition names,
    so any combination of channels can be answered without another query.
    """

    def __init__(self, messages: dict, threads: dict, joined: dict, created: dict, roles: dict, now=None):
        self.messages = messages
        self.threads = threads
        self.joined = joined
        self.created = created
        self.roles = roles
        self.now = now or datetime.datetime.now(datetime.timezone.utc)
        self._rank_cache: dict[tuple, dict[int, int]] = {}

    def _table(self, metric: str) -> dict:
        return self.threads if metric == "threads" else self.messages

    def count(self, user_id: int, metric: str, channel_ids: Iterable[int]) -> int:
        per_channel = self._table(metric).get(user_id) or {}
        channel_ids = list(channel_ids or [])
        if not channel_ids:
            return sum(per_channel.values())
        return sum(per_channel.get(channel_id, 0) for channel_id in channel_ids)

    def ranking(self, metric: str, channel_ids: Iterable[int]) -> dict[int, int]:
        """``user_id -> 1-based rank`` for this metric over these channels."""
        key = (metric, tuple(sorted(channel_ids or ())))
        if key not in self._rank_cache:
            totals = {
                user_id: self.count(user_id, metric, key[1])
                for user_id in self._table(metric)
            }
            ordered = sorted(
                ((uid, total) for uid, total in totals.items() if total > 0),
                key=lambda item: (-item[1], item[0]),
            )
            self._rank_cache[key] = {uid: index for index, (uid, _t) in enumerate(ordered, start=1)}
        return self._rank_cache[key]

    def days_since(self, when) -> float:
        if when is None:
            return 0.0
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        return (self.now - when).total_seconds() / 86400


def evaluate(node: dict, user_id: int, facts: MemberFacts) -> bool:
    """Does this member satisfy the condition tree?"""
    kind = node.get("type")
    if kind == "all":
        return all(evaluate(child, user_id, facts) for child in node["children"])
    if kind == "any":
        return any(evaluate(child, user_id, facts) for child in node["children"])
    if kind == "not":
        return not any(evaluate(child, user_id, facts) for child in node["children"])
    if kind == "has_role":
        held = facts.roles.get(user_id) or set()
        wanted = set(node["role_ids"])
        return wanted <= held if node.get("mode", "all") == "all" else bool(wanted & held)
    if kind == "member_for":
        return facts.days_since(facts.joined.get(user_id)) >= node["days"]
    if kind == "account_for":
        return facts.days_since(facts.created.get(user_id)) >= node["days"]
    if kind == "metric_min":
        return facts.count(user_id, node["metric"], node["channel_ids"]) >= node["min"]
    if kind == "metric_top":
        rank = facts.ranking(node["metric"], node["channel_ids"]).get(user_id)
        return rank is not None and rank <= node["n"]
    return False


def rank_of(node: dict, user_id: int, facts: MemberFacts) -> Optional[int]:
    """Where this member sits for the first ranking/counting condition in a tree.

    Used for the tribe leaderboards: a tribe defined by "top N in #general" has
    an obvious ordering, and one defined by a message count can borrow the same
    ordering from that count.
    """
    kind = node.get("type")
    if kind in GROUP_TYPES:
        for child in node.get("children", []):
            found = rank_of(child, user_id, facts)
            if found is not None:
                return found
        return None
    if kind in ("metric_top", "metric_min"):
        return facts.ranking(node["metric"], node["channel_ids"]).get(user_id)
    return None


# --------------------------------------------------------------------------- #
#  Storage
# --------------------------------------------------------------------------- #
class TribeManager:
    """Per-guild tribe definitions, cached. ``bot.tribes``."""

    def __init__(self, collection, members_collection) -> None:
        self._col = collection
        self._members = members_collection
        self._cache: dict[int, list[dict]] = {}

    def for_guild(self, guild_id: int) -> list[dict]:
        if guild_id not in self._cache:
            self._cache[guild_id] = list(self._col.find({"guild_id": int(guild_id)}).sort("_id", 1))
        return self._cache[guild_id]

    def enabled_for(self, guild_id: int) -> list[dict]:
        return [t for t in self.for_guild(guild_id) if t.get("enabled", True)]

    def invalidate(self, guild_id: Optional[int] = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(guild_id, None)

    def create(self, guild_id: int, data: dict) -> dict:
        doc = {
            "guild_id": int(guild_id),
            "name": data.get("name") or "New tribe",
            "enabled": bool(data.get("enabled", True)),
            "role_ids": [int(r) for r in data.get("role_ids") or []],
            "remove_when_unmatched": bool(data.get("remove_when_unmatched", False)),
            "condition": data.get("condition") or {"type": "all", "children": []},
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        doc["_id"] = self._col.insert_one(doc).inserted_id
        self.invalidate(guild_id)
        return doc

    def update(self, guild_id: int, tribe_id: str, data: dict) -> None:
        fields = {}
        for key in ("name", "condition"):
            if key in data:
                fields[key] = data[key]
        if "role_ids" in data:
            fields["role_ids"] = [int(r) for r in data["role_ids"] or []]
        for flag in ("enabled", "remove_when_unmatched"):
            if flag in data:
                fields[flag] = bool(data[flag])
        if fields:
            fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
            self._col.update_one({"_id": ObjectId(tribe_id), "guild_id": int(guild_id)}, {"$set": fields})
            self.invalidate(guild_id)

    def delete(self, guild_id: int, tribe_id: str) -> None:
        self._col.delete_one({"_id": ObjectId(tribe_id), "guild_id": int(guild_id)})
        self._members.delete_many({"guild_id": int(guild_id), "tribe_id": str(tribe_id)})
        self.invalidate(guild_id)

    # ------------------------------------------------------------------ #
    #  Membership snapshots (what the stats page reads)
    # ------------------------------------------------------------------ #
    def save_membership(self, guild_id: int, tribe_id: str, rows: list[dict]) -> None:
        """Replace a tribe's membership with this sweep's result."""
        key = {"guild_id": int(guild_id), "tribe_id": str(tribe_id)}
        self._members.delete_many(key)
        if rows:
            self._members.insert_many([{**key, **row} for row in rows])

    def membership(self, guild_id: int, tribe_id: str) -> list[dict]:
        return list(
            self._members.find({"guild_id": int(guild_id), "tribe_id": str(tribe_id)}).sort("rank", 1)
        )

    def tribes_of(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self._members.find({"guild_id": int(guild_id), "user_id": int(user_id)}))
