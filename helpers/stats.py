"""
Per-server statistics for the control panel.

Everything here reads archives the bot already writes: ``Messages with Channels``
(one doc per message), ``Commands Usage`` (one doc per invocation) and ``Logs``
(the audit archive).

Two quirks of those archives shape this module:

* **No timestamp field.** Messages and command uses were never stored with one,
  so time ranges come from the ObjectId in ``_id``, which embeds its creation
  time. Filtering on an ``_id`` range keeps every historical document usable
  *and* rides the primary key index instead of scanning.
* **No guild field.** An archived message only recorded its channel, so a
  guild's stats are "activity in this guild's channels". New writes now carry
  the guild id too (see ``bot.py``), which command stats already prefer.

Times are UTC — the same clock the ObjectIds are minted from.

Every function here is a blocking pymongo call. The panel runs inside the bot's
event loop, so callers must push :func:`collect` to an executor rather than
awaiting it directly, or the bot stops responding while Mongo works.
"""

from __future__ import annotations

import datetime
from typing import Optional

from bson import ObjectId

import config_py

# Selectable ranges, in the order the panel offers them.
PERIODS: tuple[tuple[str, str, Optional[int]], ...] = (
    ("24h", "Last 24 hours", 1),
    ("7d", "Last 7 days", 7),
    ("30d", "Last 30 days", 30),
    ("90d", "Last 90 days", 90),
    ("1y", "Last year", 365),
    ("all", "All time", None),
)
DEFAULT_PERIOD = "30d"
PAGE_SIZE = 10
# Most days to plot; "all time" on an old server would otherwise draw thousands.
MAX_PLOT_DAYS = 120

_PERIOD_DAYS = {key: days for key, _label, days in PERIODS}
_PERIOD_LABELS = {key: label for key, label, _days in PERIODS}

_indexed = False


# --------------------------------------------------------------------------- #
#  Period helpers
# --------------------------------------------------------------------------- #
def normalise_period(period: Optional[str]) -> str:
    """Coerce a query-string period to a known key."""
    return period if period in _PERIOD_DAYS else DEFAULT_PERIOD


def period_label(period: str) -> str:
    return _PERIOD_LABELS[normalise_period(period)]


def cutoff(period: str) -> Optional[datetime.datetime]:
    """Start of the window, or ``None`` for all time."""
    days = _PERIOD_DAYS[normalise_period(period)]
    if days is None:
        return None
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def _id_range(period: str) -> dict:
    """An ``_id`` filter fragment covering the period (empty dict for all time)."""
    start = cutoff(period)
    return {"_id": {"$gte": ObjectId.from_datetime(start)}} if start else {}


# --------------------------------------------------------------------------- #
#  Scoping
# --------------------------------------------------------------------------- #
class Scope:
    """The guild facts the queries need, lifted off the gateway cache.

    Built on the event loop and passed into the worker thread, so nothing here
    reads a live ``discord.Guild`` while the bot may be mutating it.
    """

    __slots__ = ("guild_id", "guild_name", "channel_ids", "bot_ids")

    def __init__(self, guild) -> None:
        self.guild_id = guild.id
        self.guild_name = guild.name
        self.channel_ids = [channel.id for channel in guild.channels] + [thread.id for thread in guild.threads]
        self.bot_ids = [member.id for member in guild.members if member.bot]


def _message_match(scope: Scope, period: str, *, humans_only: bool = True) -> dict:
    # Historical docs only know their channel; newer ones carry the guild, which
    # also catches archived threads (they drop out of ``guild.threads``).
    match: dict = {"$or": [{"guild": scope.guild_id}, {"channel": {"$in": scope.channel_ids}}]}
    match.update(_id_range(period))
    if humans_only and scope.bot_ids:
        match["author"] = {"$nin": scope.bot_ids}
    return match


def _command_match(scope: Scope, period: str) -> dict:
    # Older docs recorded the guild by name only; newer ones carry the id.
    match: dict = {"$or": [{"Guild ID": scope.guild_id}, {"Guild": scope.guild_name}]}
    match.update(_id_range(period))
    return match


# --------------------------------------------------------------------------- #
#  Building blocks
# --------------------------------------------------------------------------- #
def ensure_indexes() -> None:
    """Create the indexes these queries lean on. Safe to call repeatedly."""
    global _indexed
    if _indexed:
        return
    try:
        config_py.messages.create_index([("channel", 1), ("_id", -1)], background=True)
        config_py.messages.create_index([("author", 1), ("_id", -1)], background=True)
        config_py.commands_use.create_index([("Guild ID", 1), ("_id", -1)], background=True)
        config_py.commands_use.create_index([("Guild", 1), ("_id", -1)], background=True)
        config_py.logs.create_index([("guild_id", 1), ("event_type", 1), ("timestamp", 1)], background=True)
    except Exception:  # noqa: BLE001 - stats must never take the panel down
        pass
    _indexed = True


def _paged_counts(collection, match: dict, field: str, page: int) -> dict:
    """Group by ``field``, order by count, and return one page plus the total.

    ``$facet`` gets the page and the number of distinct values in a single pass,
    so paging doesn't re-run the grouping for every page view.
    """
    skip = max(0, (page - 1) * PAGE_SIZE)
    pipeline = [
        {"$match": match},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {
            "$facet": {
                "rows": [{"$sort": {"count": -1, "_id": 1}}, {"$skip": skip}, {"$limit": PAGE_SIZE}],
                "total": [{"$count": "n"}],
            }
        },
    ]
    result = next(collection.aggregate(pipeline, allowDiskUse=True), {})
    rows = [{"id": row["_id"], "count": row["count"]} for row in result.get("rows", [])]
    total = (result.get("total") or [{}])[0].get("n", 0)
    return {"rows": rows, "total": total, "page": page, "pages": max(1, -(-total // PAGE_SIZE))}


def _per_day(match: dict) -> list[dict]:
    """Daily message counts, oldest first, capped at ``MAX_PLOT_DAYS``."""
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": {"$toDate": "$_id"}}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": -1}},
        {"$limit": MAX_PLOT_DAYS},
    ]
    days = [{"day": row["_id"], "count": row["count"]} for row in config_py.messages.aggregate(pipeline, allowDiskUse=True)]
    return list(reversed(days))


def _per_hour(match: dict) -> list[int]:
    """Message counts bucketed by UTC hour (24 slots, always full-length)."""
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"$hour": {"$toDate": "$_id"}}, "count": {"$sum": 1}}},
    ]
    hours = [0] * 24
    for row in config_py.messages.aggregate(pipeline, allowDiskUse=True):
        if isinstance(row["_id"], int) and 0 <= row["_id"] < 24:
            hours[row["_id"]] = row["count"]
    return hours


def _command_log(scope: Scope, period: str, page: int) -> dict:
    """Recent command invocations, newest first."""
    match = _command_match(scope, period)
    skip = max(0, (page - 1) * PAGE_SIZE)
    total = config_py.commands_use.count_documents(match)
    rows = []
    for doc in config_py.commands_use.find(match).sort("_id", -1).skip(skip).limit(PAGE_SIZE):
        rows.append(
            {
                "command": doc.get("Command", "?"),
                "name": doc.get("Name", ""),
                "user_id": doc.get("User ID"),
                "when": doc["_id"].generation_time if isinstance(doc.get("_id"), ObjectId) else None,
            }
        )
    return {"rows": rows, "total": total, "page": page, "pages": max(1, -(-total // PAGE_SIZE))}


def _history_days(scope: Scope) -> int:
    """Days between the oldest archived message for this guild and now — the
    denominator for an all-time daily average (the plotted range is capped)."""
    oldest = config_py.messages.find_one({"channel": {"$in": scope.channel_ids}}, sort=[("_id", 1)])
    if not oldest or not isinstance(oldest.get("_id"), ObjectId):
        return 1
    age = datetime.datetime.now(datetime.timezone.utc) - oldest["_id"].generation_time
    return max(1, age.days)


def _log_event_count(scope: Scope, period: str, event_type: str) -> int:
    """How many audit events of one type landed in the window."""
    match: dict = {"guild_id": scope.guild_id, "event_type": event_type}
    start = cutoff(period)
    if start:
        # Timestamps are stored as ISO strings; same format and offset throughout,
        # so a lexicographic comparison is a chronological one.
        match["timestamp"] = {"$gte": start.isoformat()}
    try:
        return config_py.logs.count_documents(match)
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
def collect(scope: Scope, period: str, *, user_page: int = 1, channel_page: int = 1, command_page: int = 1) -> dict:
    """Every figure the stats page shows, in one blocking pass.

    Ids come back unresolved: turning them into names can need an API call, which
    belongs on the event loop rather than in this worker thread (see
    ``helpers/names.py``).
    """
    ensure_indexes()
    period = normalise_period(period)
    human_match = _message_match(scope, period)

    users = _paged_counts(config_py.messages, human_match, "author", user_page)
    channels = _paged_counts(config_py.messages, human_match, "channel", channel_page)
    per_day = _per_day(human_match)
    per_hour = _per_hour(human_match)
    commands = _command_log(scope, period, command_page)
    top_commands = _paged_counts(config_py.commands_use, _command_match(scope, period), "Command", 1)

    total_messages = config_py.messages.count_documents(human_match)
    busiest_day = max(per_day, key=lambda d: d["count"], default=None)
    busiest_hour = max(range(24), key=lambda h: per_hour[h]) if any(per_hour) else None
    span_days = _PERIOD_DAYS[period] or _history_days(scope)

    return {
        "period": period,
        "period_label": period_label(period),
        "users": users,
        "channels": channels,
        "per_day": per_day,
        "per_hour": per_hour,
        "commands": commands,
        "top_commands": top_commands["rows"],
        "summary": {
            "messages": total_messages,
            "active_users": users["total"],
            "active_channels": channels["total"],
            "per_day_avg": round(total_messages / span_days, 1) if total_messages else 0,
            "busiest_day": busiest_day,
            "busiest_hour": busiest_hour,
            "commands": commands["total"],
            "joins": _log_event_count(scope, period, "MEMBER_JOIN"),
            "leaves": _log_event_count(scope, period, "MEMBER_LEAVE"),
            "kicks": _log_event_count(scope, period, "MEMBER_KICK"),
        },
    }
