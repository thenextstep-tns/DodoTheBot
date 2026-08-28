"""
Where DodoLand activity is written, and the only place it is read from.

Two collections, both keyed by day so nothing grows without bound and any
window is a range scan rather than a recount:

``DodoLandActivity``  one row per (guild, user, day)
    ``acts``      what happened, uncapped. The honest record.
    ``scored``    what counted after the caps. What standing is built from.
    ``channels``  scored counts split by channel, which is what lets a building
                  be defined as "these channels, these metrics" without a
                  second pass over anything.

``DodoLandPairs``     one row per (guild, day, a, b), ``a < b`` so a pair is
    undirected and two people always land on the same row. This is where the
    per-partner caps are enforced, and it is *also* the social graph the map
    places neighbours from later. The anti-farm data and the fun data are the
    same data, which is why neither can rot without the other noticing.

**acts and scored are separate on purpose.** A capped act is still recorded, so
the panel can say "200 reactions, 80 scored" rather than quietly discarding the
rest. A cap that is invisible reads as a bug to the person it happens to.

**Every call demands a guild.** DodoLand is multiserver from its first write, so
an unscoped query raises here rather than returning another server's rows. There
is no code path that reads across guilds, by construction.
"""

from __future__ import annotations

import datetime
from typing import Iterable, Optional

from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import parameters as dodo_params

# pymongo's ReturnDocument, imported lazily so the tests can run this module
# against a fake collection with no driver installed.
try:  # pragma: no cover - trivial import guard
    from pymongo import ReturnDocument

    _AFTER = ReturnDocument.AFTER
except Exception:  # pragma: no cover
    _AFTER = True


def today(now: Optional[datetime.datetime] = None) -> str:
    """The day key, UTC. Same clock the message archive's ObjectIds use."""
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d")


def days_back(count: int, now: Optional[datetime.datetime] = None) -> str:
    """The day key ``count`` days ago, for window queries."""
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    return (moment - datetime.timedelta(days=max(0, count))).strftime("%Y-%m-%d")


# Which history a read covers. Rebuilt rows are stamped ``source: "backfill"``;
# rows the listener wrote carry no source at all, which is what "live" means.
BASIS_ALL = "all"
BASIS_LIVE = "live"
BASIS_BACKFILL = "backfill"
BASES = (BASIS_ALL, BASIS_LIVE, BASIS_BACKFILL)
BASIS_LABELS = {
    BASIS_ALL: "With history",
    BASIS_LIVE: "From scratch",
    BASIS_BACKFILL: "Rebuilt history only",
}


def _basis_filter(basis: str) -> dict:
    """The query fragment selecting one history."""
    if basis == BASIS_LIVE:
        return {"source": {"$ne": BASIS_BACKFILL}}
    if basis == BASIS_BACKFILL:
        return {"source": BASIS_BACKFILL}
    return {}


def allowance(done_before: int, amount: int, cap: int) -> int:
    """How much of ``amount`` scores, given what already happened and the cap.

    Extracted so the live listener and the archive backfill cannot drift: one
    writes against Mongo's current count and the other against an in-memory
    tally, but the decision itself is made in exactly one place. A backfilled
    day and a live day have to be worth the same, or the history is a second
    economy wearing the same name.

    Clips rather than falls off: a bulk amount that crosses the cap still scores
    the part that was under it.
    """
    if cap <= 0:
        return max(0, amount)
    return max(0, min(amount, cap - done_before))


class ActivityStore:
    """Reads and writes DodoLand's two activity collections.

    Instantiated once and hung off the bot as ``bot.dodoland``. ``params`` is a
    :class:`helpers.parameters.ParamManager` over DodoLand's own specs.
    """

    def __init__(self, activity_col, pairs_col, params) -> None:
        self._activity = activity_col
        self._pairs = pairs_col
        self._params = params

    # ------------------------------------------------------------------ #
    #  Indexes
    # ------------------------------------------------------------------ #
    def ensure_indexes(self) -> None:
        """The two unique keys, plus the range index every window read uses."""
        self._activity.create_index([("guild_id", 1), ("user_id", 1), ("day", 1)], unique=True)
        self._activity.create_index([("guild_id", 1), ("day", 1)])
        self._pairs.create_index([("guild_id", 1), ("day", 1), ("a", 1), ("b", 1)], unique=True)
        self._pairs.create_index([("guild_id", 1), ("a", 1)])
        self._pairs.create_index([("guild_id", 1), ("b", 1)])

    # ------------------------------------------------------------------ #
    #  Parameter reads
    # ------------------------------------------------------------------ #
    def weight(self, guild_id: int, metric_key: str) -> int:
        return int(self._params.get(guild_id, dodo_params.weight_key(metric_key)))

    def daily_cap(self, guild_id: int, metric_key: str) -> int:
        return int(self._params.get(guild_id, dodo_params.daily_cap_key(metric_key)))

    def partner_cap(self, guild_id: int, metric_key: str) -> int:
        return int(self._params.get(guild_id, dodo_params.partner_cap_key(metric_key)))

    # ------------------------------------------------------------------ #
    #  Writing
    # ------------------------------------------------------------------ #
    def record(self, guild_id: int, user_id: int, metric_key: str, *,
               channel_id: int = 0, partner_id: Optional[int] = None,
               day: Optional[str] = None, amount: int = 1) -> int:
        """Record ``amount`` of an act. Returns how much of it scored.

        The act is always written to ``acts`` in full. It reaches ``scored``
        (and the per-channel split) only up to the person's daily cap for that
        metric, and only if it is under the per-partner cap for the day.

        ``amount`` exists for the metrics that arrive in bulk rather than one
        at a time — a voice session is forty minutes, not forty events — and it
        clips at the cap rather than falling off it, so a session that crosses
        the daily ceiling still scores the part that was under it.

        The return is an int rather than a bool so callers can tell "all of it"
        from "some of it"; ``0`` is falsey, so ``if store.record(...)`` still
        reads the way it did.
        """
        guild_id = _require_guild(guild_id)
        metric = metric_registry.get(metric_key)
        stamp = day or today()
        amount = int(amount)
        if amount <= 0:
            return 0

        if metric.is_social:
            if partner_id is None:
                raise ValueError(f"{metric_key!r} is a social act and needs a partner_id")
            if int(partner_id) == int(user_id):
                # A self-act never reaches here from the cog, but a backfill or a
                # future caller might; refusing centrally is cheaper than trusting.
                return 0
            within_partner_cap = self._bump_pair(
                guild_id, int(user_id), int(partner_id), metric_key, stamp, amount
            )
        else:
            within_partner_cap = True

        after = self._activity.find_one_and_update(
            {"guild_id": guild_id, "user_id": int(user_id), "day": stamp},
            {"$inc": {f"acts.{metric_key}": amount}},
            upsert=True, return_document=_AFTER,
        ) or {}
        done = int((after.get("acts") or {}).get(metric_key, amount))

        if not within_partner_cap:
            return 0
        allowed = allowance(done - amount, amount, self.daily_cap(guild_id, metric_key))
        if allowed <= 0:
            return 0

        bump = {f"scored.{metric_key}": allowed}
        if channel_id:
            bump[f"channels.{int(channel_id)}.{metric_key}"] = allowed
        self._activity.update_one(
            {"guild_id": guild_id, "user_id": int(user_id), "day": stamp}, {"$inc": bump}
        )
        return allowed

    def _bump_pair(self, guild_id: int, user_id: int, partner_id: int,
                   metric_key: str, stamp: str, amount: int = 1) -> bool:
        """Count this act on the undirected pair row; True if it is under the cap.

        The row is bumped whether or not the act scores, because the pair count
        is the social graph and a capped evening of chatting is still two people
        who talked.
        """
        low, high = sorted((int(user_id), int(partner_id)))
        after = self._pairs.find_one_and_update(
            {"guild_id": guild_id, "day": stamp, "a": low, "b": high},
            {"$inc": {f"acts.{metric_key}": amount, "n": amount}},
            upsert=True, return_document=_AFTER,
        ) or {}
        done = int((after.get("acts") or {}).get(metric_key, amount))
        cap = self.partner_cap(guild_id, metric_key)
        return cap <= 0 or done <= cap

    # ------------------------------------------------------------------ #
    #  Reading
    # ------------------------------------------------------------------ #
    def rows(self, guild_id: int, *, user_id: Optional[int] = None,
             since: Optional[str] = None, basis: str = BASIS_ALL) -> list[dict]:
        """Daily rows for a guild, optionally one person's, from a day onward.

        ``basis`` picks which history to read. It is what lets the panel show
        two honest previews side by side: everything, and only what has been
        counted since tracking started. Both are real answers to different
        questions, and being able to see them together is the difference between
        "these numbers look odd" and "these numbers look odd *because of the
        rebuild*".
        """
        query: dict = {"guild_id": _require_guild(guild_id)}
        if user_id is not None:
            query["user_id"] = int(user_id)
        if since:
            query["day"] = {"$gte": since}
        query.update(_basis_filter(basis))
        return list(self._activity.find(query))

    def pair_rows(self, guild_id: int, *, since: Optional[str] = None,
                  basis: str = BASIS_ALL) -> list[dict]:
        """Every pair row for a guild. The relation graph, whole."""
        query: dict = {"guild_id": _require_guild(guild_id)}
        if since:
            query["day"] = {"$gte": since}
        query.update(_basis_filter(basis))
        return list(self._pairs.find(query))

    def totals(self, guild_id: int, user_id: int, *, since: Optional[str] = None,
               basis: str = BASIS_ALL) -> dict[str, int]:
        """Scored acts per metric for one person over a window."""
        out: dict[str, int] = {}
        for row in self.rows(guild_id, user_id=user_id, since=since, basis=basis):
            for key, count in (row.get("scored") or {}).items():
                out[key] = out.get(key, 0) + int(count)
        return out

    def channel_totals(self, guild_id: int, user_id: int, *,
                       since: Optional[str] = None,
                       basis: str = BASIS_ALL) -> dict[int, dict[str, int]]:
        """Scored acts per metric, split by channel. What buildings score from."""
        out: dict[int, dict[str, int]] = {}
        for row in self.rows(guild_id, user_id=user_id, since=since, basis=basis):
            for channel, counts in (row.get("channels") or {}).items():
                bucket = out.setdefault(int(channel), {})
                for key, count in (counts or {}).items():
                    bucket[key] = bucket.get(key, 0) + int(count)
        return out

    def partner_days(self, guild_id: int, user_id: int, *, since: Optional[str] = None) -> int:
        """How many (person, day) pairs this person reached. The unfarmable number."""
        query: dict = {
            "guild_id": _require_guild(guild_id),
            "$or": [{"a": int(user_id)}, {"b": int(user_id)}],
        }
        if since:
            query["day"] = {"$gte": since}
        return sum(1 for _ in self._pairs.find(query))

    def partners(self, guild_id: int, user_id: int, *,
                 since: Optional[str] = None) -> dict[int, int]:
        """``{other_user_id: acts exchanged}`` — the social graph, one person's slice.

        The map places neighbours from this: a town belongs next to the people
        its owner actually talks to.
        """
        query: dict = {
            "guild_id": _require_guild(guild_id),
            "$or": [{"a": int(user_id)}, {"b": int(user_id)}],
        }
        if since:
            query["day"] = {"$gte": since}
        out: dict[int, int] = {}
        for row in self._pairs.find(query):
            other = row["b"] if int(row["a"]) == int(user_id) else row["a"]
            out[int(other)] = out.get(int(other), 0) + int(row.get("n", 0))
        return out

    def first_day(self, guild_id: int, *, basis: str = BASIS_LIVE) -> Optional[str]:
        """The earliest day this guild has a row for, or ``None``.

        Defaults to the **live** history, because the caller that matters is the
        backfill: everything it writes must stop strictly before the first day
        the listener recorded, so a rebuilt day can never overwrite a real one.
        Reading all rows here would make the boundary move every time the
        rebuild ran, which would then refuse to rebuild anything at all.
        """
        rows = self.rows(_require_guild(guild_id), basis=basis)
        days = sorted(row.get("day") for row in rows if row.get("day"))
        return days[0] if days else None

    # ------------------------------------------------------------------ #
    #  Bulk writing (the archive backfill)
    # ------------------------------------------------------------------ #
    def replace_days(self, guild_id: int, activity: list[dict], pairs: list[dict]) -> int:
        """Overwrite whole days outright. Returns how many rows were written.

        ``$set`` rather than ``$inc``, which is what makes the backfill safely
        **repeatable**: running it twice writes the same numbers rather than
        doubling them. That is only sound because the caller restricts itself to
        days before the listener started, where there is nothing live to lose.

        Sent as bulk batches. A rebuild of this server is roughly 32,000 rows,
        and one round trip each took long enough that the first real run was
        killed part-way through, leaving the activity rows written and the
        relation graph almost entirely missing. Batching is the difference
        between a job that finishes and a job that gets interrupted.
        """
        guild_id = _require_guild(guild_id)
        activity_ops = [
            (
                {"guild_id": guild_id, "user_id": int(row["user_id"]), "day": row["day"]},
                {"$set": {"acts": row.get("acts") or {},
                          "scored": row.get("scored") or {},
                          "channels": row.get("channels") or {},
                          "source": "backfill"}},
            )
            for row in activity or ()
        ]
        pair_ops = [
            (
                {"guild_id": guild_id, "day": row["day"],
                 "a": int(row["a"]), "b": int(row["b"])},
                {"$set": {"acts": row.get("acts") or {}, "n": int(row.get("n", 0)),
                          "source": "backfill"}},
            )
            for row in pairs or ()
        ]
        return (self._bulk(self._activity, activity_ops)
                + self._bulk(self._pairs, pair_ops))

    @staticmethod
    def _bulk(collection, operations, batch: int = 1000) -> int:
        """Upsert many rows, in batches, falling back to one at a time.

        The fallback is for the test stub, which models a collection rather than
        a driver and has no ``bulk_write``. It must stay: a stub that quietly
        did nothing here would let a broken rebuild pass its tests.
        """
        if not operations:
            return 0
        try:
            from pymongo import UpdateOne
        except Exception:  # pragma: no cover - no driver, as in the tests
            UpdateOne = None

        written = 0
        if UpdateOne is not None and hasattr(collection, "bulk_write"):
            for start in range(0, len(operations), batch):
                chunk = operations[start:start + batch]
                collection.bulk_write(
                    [UpdateOne(query, update, upsert=True) for query, update in chunk],
                    ordered=False,
                )
                written += len(chunk)
            return written
        for query, update in operations:
            collection.update_one(query, update, upsert=True)
            written += 1
        return written

    # ------------------------------------------------------------------ #
    #  Retention
    # ------------------------------------------------------------------ #
    def prune(self, guild_id: int, *, keep_days: Optional[int] = None) -> int:
        """Drop rows older than the keep window. Returns how many were removed.

        Deliberately not a TTL index: the window is a per-guild parameter, and a
        TTL index would apply one number to every server on the bot.
        """
        guild_id = _require_guild(guild_id)
        keep = keep_days if keep_days is not None else int(
            self._params.get(guild_id, "dodoland_keep_days")
        )
        cutoff = days_back(keep)
        removed = self._activity.delete_many({"guild_id": guild_id, "day": {"$lt": cutoff}})
        self._pairs.delete_many({"guild_id": guild_id, "day": {"$lt": cutoff}})
        return int(getattr(removed, "deleted_count", 0) or 0)


def _require_guild(guild_id) -> int:
    """DodoLand has no unscoped reads. A missing guild is a bug, not a wildcard."""
    try:
        value = int(guild_id)
    except (TypeError, ValueError):
        value = 0
    if not value:
        raise ValueError("DodoLand queries are always guild-scoped; got no guild id")
    return value
