"""
The change log: who changed what, when, and what it was before.

Every write the control panel makes is recorded here — owner and admin alike,
so the log is a full history rather than a record of other people's edits. The
DM notifier (``helpers/audit_notify.py``) is separate and only fires for
non-owners; this is the durable record behind it.

Entries are kept indefinitely by choice, so the collection only grows with
actual configuration activity. Old values are stored alongside new ones, which
is what makes "put it back" answerable.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

# What kind of thing changed, for filtering and for rendering a readable label.
KIND_COG = "cog"
KIND_COG_LEVEL = "cog_level"
KIND_COMMAND = "command"
KIND_CATEGORY = "category"
KIND_FEATURE = "feature"
KIND_PARAM = "param"
KIND_SETTING = "setting"
KIND_EVENT_RULE = "event_rule"
KIND_ACCESS = "panel_access"
KIND_LANG = "lang"
KIND_TRIBE = "tribe"
KIND_TRIAL = "trial_rank"

KIND_LABELS = {
    KIND_COG: "Cog",
    KIND_COG_LEVEL: "Cog visibility",
    KIND_COMMAND: "Command level",
    KIND_CATEGORY: "Category",
    KIND_FEATURE: "Feature",
    KIND_PARAM: "Parameter",
    KIND_SETTING: "Setting",
    KIND_EVENT_RULE: "Event rule",
    KIND_ACCESS: "Panel access",
    KIND_LANG: "String",
    KIND_TRIBE: "Tribe",
    KIND_TRIAL: "Trial ranking",
}

PAGE_SIZE = 25
# Values are stored for display, not for replay; long text is truncated.
MAX_VALUE_CHARS = 300


def _short(value: Any) -> Any:
    """Store something displayable: long text truncated, everything else as-is."""
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + "…"
    if isinstance(value, list) and len(value) > 30:
        return value[:30] + ["…"]
    return value


class AuditLog:
    """Append-only record of panel changes. ``bot.audit_log``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        try:
            self._col.create_index([("guild_id", 1), ("_id", -1)], background=True)
            self._col.create_index([("guild_id", 1), ("kind", 1), ("_id", -1)], background=True)
        except Exception:  # noqa: BLE001 - logging must never break a save
            pass
        self._indexed = True

    def record(
        self,
        guild_id: int,
        actor_id: Optional[int],
        actor_name: str,
        kind: str,
        target: str,
        old: Any = None,
        new: Any = None,
        *,
        is_owner: bool = False,
    ) -> None:
        """Append one change. Never raises — the write it describes already happened."""
        try:
            self._ensure_indexes()
            self._col.insert_one(
                {
                    "guild_id": int(guild_id),
                    "actor_id": int(actor_id) if actor_id else None,
                    "actor_name": str(actor_name)[:100],
                    "actor_is_owner": bool(is_owner),
                    "kind": kind,
                    "target": str(target)[:200],
                    "old": _short(old),
                    "new": _short(new),
                    "at": datetime.datetime.now(datetime.timezone.utc),
                }
            )
        except Exception:  # noqa: BLE001
            pass

    def page(self, guild_id: int, *, page: int = 1, kind: Optional[str] = None,
             actor_id: Optional[int] = None) -> dict:
        """One page of history for a guild, newest first."""
        self._ensure_indexes()
        query: dict = {"guild_id": int(guild_id)}
        if kind:
            query["kind"] = kind
        if actor_id:
            query["actor_id"] = int(actor_id)
        try:
            total = self._col.count_documents(query)
            skip = max(0, (page - 1) * PAGE_SIZE)
            rows = list(self._col.find(query).sort("_id", -1).skip(skip).limit(PAGE_SIZE))
        except Exception:  # noqa: BLE001
            total, rows = 0, []
        return {
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, -(-total // PAGE_SIZE)),
        }

    def actors(self, guild_id: int) -> list[dict]:
        """Distinct people who have changed this guild, for the filter dropdown."""
        try:
            pipeline = [
                {"$match": {"guild_id": int(guild_id), "actor_id": {"$ne": None}}},
                {"$group": {"_id": "$actor_id", "name": {"$last": "$actor_name"}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 50},
            ]
            return [{"id": row["_id"], "name": row.get("name") or str(row["_id"]), "count": row["count"]}
                    for row in self._col.aggregate(pipeline)]
        except Exception:  # noqa: BLE001
            return []
