"""
The server log: what Discord did, as opposed to what the panel did.

``helpers/audit_log.py`` is the other log and answers a different question: who
changed a *setting*. This one reads what the ``log`` cog has been watching all
along — roles, edits, deletes, threads, joins, bans, invites, voice — which has
been written to the ``Logs`` collection since long before anything could read it
back. Nothing here writes; the cog still owns that.

Three things shape the queries:

* **Ordering is by ``_id``, not by time.** An ObjectId's leading bytes are the
  insertion timestamp, so it sorts the same way while being the primary key and
  needing no second index. ``audit_log`` settled on this for the same reason.
* **Date bounds compare the ``timestamp`` string.** It is ISO-8601 in UTC for
  every row ever written, so a lexicographic compare is a chronological one, and
  it works on rows that predate every field added since.
* **Ids are matched against a list, not a single value.** A kick names two
  people, the one kicked and the one who did it, and both are answers to "show
  me everything about this person".

Rows written before the cog started extracting ids have neither ``user_ids`` nor
``channel_ids``. They are still findable: every filter falls back to a regex
over the description, which is where the mention has always been. That fallback
is a collection scan within one guild, so it is kept behind the indexed path
with ``$or`` rather than replacing it.
"""

from __future__ import annotations

import datetime
import re
from typing import Optional

PAGE_SIZE = 50

# How many distinct people or channels a filter dropdown will offer. Past this
# it stops being a list you can read and becomes one you have to search.
MAX_FILTER_OPTIONS = 200

# What the log cog records, grouped so a dropdown reads as a menu rather than as
# thirty-seven shouted constants. Order is the order they are offered in.
EVENT_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Messages", ("MESSAGE_EDIT", "MESSAGE_DELETE", "MESSAGE_BULK_DELETE")),
    ("Members", ("MEMBER_JOIN", "MEMBER_LEAVE", "MEMBER_KICK", "MEMBER_BAN",
                 "MEMBER_UNBAN", "MEMBER_ROLE_UPDATE", "MEMBER_NICK_UPDATE",
                 "MEMBER_TIMEOUT_ADD", "MEMBER_TIMEOUT_REMOVE")),
    ("Threads", ("THREAD_CREATE", "THREAD_DELETE", "THREAD_UPDATE")),
    ("Channels", ("CHANNEL_CREATE", "CHANNEL_DELETE", "CHANNEL_UPDATE")),
    ("Roles", ("ROLE_CREATE", "ROLE_DELETE", "ROLE_UPDATE")),
    ("Voice", ("VOICE_JOIN", "VOICE_LEAVE", "VOICE_MOVE")),
    ("Invites", ("INVITE_CREATE", "INVITE_DELETE")),
    ("Events", ("EVENT_CREATE", "EVENT_DELETE", "EVENT_UPDATE")),
    ("Emoji & stickers", ("EMOJI_CREATE", "EMOJI_DELETE", "EMOJI_UPDATE",
                          "STICKER_CREATE", "STICKER_DELETE", "STICKER_UPDATE")),
    ("Server", ("GUILD_UPDATE", "AUTOMOD_ACTION")),
]

EVENT_LABELS = {
    "MESSAGE_EDIT": "Message edited",
    "MESSAGE_DELETE": "Message deleted",
    "MESSAGE_BULK_DELETE": "Messages purged",
    "MEMBER_JOIN": "Joined",
    "MEMBER_LEAVE": "Left",
    "MEMBER_KICK": "Kicked",
    "MEMBER_BAN": "Banned",
    "MEMBER_UNBAN": "Unbanned",
    "MEMBER_ROLE_UPDATE": "Roles changed",
    "MEMBER_NICK_UPDATE": "Nickname changed",
    "MEMBER_TIMEOUT_ADD": "Timed out",
    "MEMBER_TIMEOUT_REMOVE": "Timeout lifted",
    "THREAD_CREATE": "Thread created",
    "THREAD_DELETE": "Thread deleted",
    "THREAD_UPDATE": "Thread changed",
    "CHANNEL_CREATE": "Channel created",
    "CHANNEL_DELETE": "Channel deleted",
    "CHANNEL_UPDATE": "Channel changed",
    "ROLE_CREATE": "Role created",
    "ROLE_DELETE": "Role deleted",
    "ROLE_UPDATE": "Role changed",
    "VOICE_JOIN": "Joined voice",
    "VOICE_LEAVE": "Left voice",
    "VOICE_MOVE": "Moved voice channel",
    "INVITE_CREATE": "Invite created",
    "INVITE_DELETE": "Invite deleted",
    "EVENT_CREATE": "Scheduled event created",
    "EVENT_DELETE": "Scheduled event deleted",
    "EVENT_UPDATE": "Scheduled event changed",
    "EMOJI_CREATE": "Emoji added",
    "EMOJI_DELETE": "Emoji removed",
    "EMOJI_UPDATE": "Emoji renamed",
    "STICKER_CREATE": "Sticker added",
    "STICKER_DELETE": "Sticker removed",
    "STICKER_UPDATE": "Sticker renamed",
    "GUILD_UPDATE": "Server settings changed",
    "AUTOMOD_ACTION": "AutoMod acted",
}

# Which group a type belongs to, so a row can be labelled without a linear scan.
GROUP_OF = {name: group for group, names in EVENT_GROUPS for name in names}

_USER_MENTION = re.compile(r"<@!?(\d{15,25})>")
_CHANNEL_MENTION = re.compile(r"<#(\d{15,25})>")
# The templates put the subject's raw id in backticks right after their mention,
# which is the one id present even when the mention fails to resolve.
_BARE_ID = re.compile(r"`(\d{15,25})`")


def subjects(description: str, fields: dict = None) -> dict:
    """Every user and channel a log entry names, in the order they appear.

    Read out of the rendered text rather than passed in by each listener: there
    are thirty-odd listeners and one of this, so this is the version that cannot
    be half-done. The first user mentioned is the subject by construction, since
    every template in ``lang.py`` opens with it.
    """
    blob = str(description or "")
    for value in (fields or {}).values():
        blob += "\n" + str(value)
    users, channels = [], []
    for match in _USER_MENTION.finditer(blob):
        value = int(match.group(1))
        if value not in users:
            users.append(value)
    for match in _BARE_ID.finditer(blob):
        value = int(match.group(1))
        if value not in users:
            users.append(value)
    for match in _CHANNEL_MENTION.finditer(blob):
        value = int(match.group(1))
        if value not in channels:
            channels.append(value)
    return {"user_ids": users, "channel_ids": channels}


def day_bounds(since: str, until: str) -> dict:
    """Turn two ``YYYY-MM-DD`` strings into a query on the timestamp string.

    ``until`` is inclusive of its whole day, because somebody asking for events
    "to the 27th" means the 27th, not midnight at the start of it.
    """
    bounds = {}
    if since:
        bounds["$gte"] = f"{since}T00:00:00"
    if until:
        try:
            end = datetime.date.fromisoformat(until) + datetime.timedelta(days=1)
        except ValueError:
            return bounds
        bounds["$lt"] = f"{end.isoformat()}T00:00:00"
    return bounds


def valid_day(value: str) -> str:
    """``YYYY-MM-DD`` or ``""``. Anything else is dropped rather than guessed."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


class EventLogStore:
    """Reads the ``Logs`` collection the log cog writes. ``bot.event_log``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._col is None or self._indexed:
            return
        self._indexed = True
        try:
            # Every query is scoped to one guild, so the guild leads all of them.
            self._col.create_index([("guild_id", 1), ("_id", -1)], background=True)
            self._col.create_index([("guild_id", 1), ("event_type", 1), ("_id", -1)],
                                   background=True)
            self._col.create_index([("guild_id", 1), ("user_ids", 1), ("_id", -1)],
                                   background=True)
            self._col.create_index([("guild_id", 1), ("channel_ids", 1), ("_id", -1)],
                                   background=True)
            self._col.create_index([("guild_id", 1), ("timestamp", -1)], background=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a page load
            pass

    @staticmethod
    def _id_clause(field: str, ids: list, pattern) -> dict:
        """Match any of ``ids`` on the indexed field, or in the text it came from.

        Several ids mean "any of these", not "all of them": nobody picks two
        people to see the events involving both at once.

        The fallback is guarded on the field being absent so that a row is only
        ever matched one way. Without the guard, a row written today matches
        twice and one written last year not at all.
        """
        return {"$or": [
            {field: {"$in": ids}},
            {field: {"$exists": False},
             "description": {"$regex": pattern(ids)}},
        ]}

    def _query(self, guild_id: int, *, event_type: str = "", group: str = "",
               user_ids: list = None, channel_ids: list = None,
               since: str = "", until: str = "") -> dict:
        query: dict = {"guild_id": int(guild_id)}
        if event_type:
            query["event_type"] = event_type
        elif group:
            names = dict(EVENT_GROUPS).get(group)
            if names:
                query["event_type"] = {"$in": list(names)}
        clauses = []
        users = [int(value) for value in (user_ids or ()) if value]
        if users:
            clauses.append(self._id_clause(
                "user_ids", users,
                lambda ids: "[<`]@?!?(?:" + "|".join(str(i) for i in ids) + ")[>`]"))
        channels = [int(value) for value in (channel_ids or ()) if value]
        if channels:
            clauses.append(self._id_clause(
                "channel_ids", channels,
                lambda ids: "<#(?:" + "|".join(str(i) for i in ids) + ")>"))
        if clauses:
            query["$and"] = clauses
        bounds = day_bounds(since, until)
        if bounds:
            query["timestamp"] = bounds
        return query

    def page(self, guild_id: int, *, page: int = 1, **filters) -> dict:
        """One page of events for a guild, newest first."""
        self._ensure_indexes()
        query = self._query(guild_id, **filters)
        try:
            total = self._col.count_documents(query)
            skip = max(0, (page - 1) * PAGE_SIZE)
            rows = list(self._col.find(query).sort("_id", -1).skip(skip).limit(PAGE_SIZE))
        except Exception:  # noqa: BLE001 - an unreadable log is an empty one, not a 500
            total, rows = 0, []
        return {"rows": rows, "total": total, "page": page,
                "pages": max(1, -(-total // PAGE_SIZE))}

    def types(self, guild_id: int) -> list[dict]:
        """Which event types this guild has actually produced, commonest first.

        Built from the data rather than from ``EVENT_LABELS`` so the dropdown
        offers what is there. A server with no scheduled events should not have
        to scroll past three kinds of them.
        """
        return self._distinct(guild_id, "$event_type")

    def people(self, guild_id: int) -> list[int]:
        """User ids that appear in this guild's log, commonest first."""
        return [int(row["value"]) for row in self._distinct(guild_id, "$user_ids",
                                                            unwind="$user_ids")]

    def channels(self, guild_id: int) -> list[int]:
        """Channel ids that appear in this guild's log, commonest first."""
        return [int(row["value"]) for row in self._distinct(guild_id, "$channel_ids",
                                                            unwind="$channel_ids")]

    def _distinct(self, guild_id: int, expression: str, *,
                  unwind: str = "") -> list[dict]:
        pipeline: list[dict] = [{"$match": {"guild_id": int(guild_id)}}]
        if unwind:
            pipeline.append({"$unwind": unwind})
        pipeline += [
            {"$group": {"_id": expression, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": MAX_FILTER_OPTIONS},
        ]
        try:
            return [{"value": row["_id"], "count": row["count"]}
                    for row in self._col.aggregate(pipeline) if row["_id"] is not None]
        except Exception:  # noqa: BLE001 - a filter that can't be built is left empty
            return []
