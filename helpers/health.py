"""
Bot health, sampled over time — what the dashboard's status board reads.

A status page is only worth looking at if it can say what *was* true, not just
what is true this second. Nothing was recording that, so this takes a small
sample every few minutes (is the gateway up, how far behind is it, how many
servers and members) and keeps ninety days of them.

Two consequences worth knowing:

* the board starts empty and fills in — it can't show history that was never
  recorded, and drawing a green bar for a day nobody measured would be a lie;
* samples expire on their own via a TTL index, so the collection stays a fixed
  size rather than growing forever.
"""

from __future__ import annotations

import datetime
from typing import Optional

# How often a sample is taken, and how long they're kept.
SAMPLE_MINUTES = 5
KEEP_DAYS = 90
# A gateway heartbeat slower than this is "degraded" rather than "down": the bot
# is answering, just badly, and conflating the two hides real outages.
DEGRADED_LATENCY_MS = 1000

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_DOWN = "down"


def classify(latency_ms: Optional[float], connected: bool) -> str:
    """One sample's verdict."""
    if not connected or latency_ms is None:
        return STATUS_DOWN
    return STATUS_DEGRADED if latency_ms >= DEGRADED_LATENCY_MS else STATUS_OK


def day_bars(samples: list[dict], days: int = KEEP_DAYS) -> list[dict]:
    """Collapse samples into one bar per day, oldest first.

    A day with no samples is returned as ``None`` state rather than green: the
    bot being off is exactly when nothing gets recorded, so "no data" must not
    render as "fine".
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    buckets: dict[datetime.date, list[dict]] = {}
    for sample in samples:
        at = sample.get("at")
        if not hasattr(at, "date"):
            continue
        buckets.setdefault(at.date(), []).append(sample)

    out = []
    for offset in range(days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        rows = buckets.get(day) or []
        if not rows:
            out.append({"day": day, "state": None, "uptime": None, "samples": 0})
            continue
        good = sum(1 for r in rows if r.get("status") == STATUS_OK)
        degraded = sum(1 for r in rows if r.get("status") == STATUS_DEGRADED)
        down = len(rows) - good - degraded
        uptime = (good + degraded) / len(rows) * 100
        if good == len(rows):
            state = STATUS_OK
        elif down == 0:
            state = STATUS_DEGRADED
        else:
            state = STATUS_DOWN
        # Each sample stands for the interval it was taken over, so a count of
        # bad samples converts straight into "how long was it bad".
        out.append({"day": day, "state": state, "uptime": uptime, "samples": len(rows),
                    "down_minutes": down * SAMPLE_MINUTES,
                    "degraded_minutes": degraded * SAMPLE_MINUTES,
                    "worst_latency": max((r.get("latency_ms") or 0) for r in rows)})
    return out


def human_minutes(minutes: int) -> str:
    """``4 hrs 3 mins`` — the phrasing a status page uses for an outage."""
    minutes = int(max(0, minutes))
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr" + ("s" if hours != 1 else ""))
    if mins or not hours:
        parts.append(f"{mins} min" + ("s" if mins != 1 else ""))
    return " ".join(parts)


def uptime_percent(bars: list[dict]) -> Optional[float]:
    """Uptime across the days that were actually measured."""
    measured = [bar for bar in bars if bar["samples"]]
    if not measured:
        return None
    return sum(bar["uptime"] for bar in measured) / len(measured)


def human_duration(seconds: float) -> str:
    """``3d 4h``, ``4h 12m``, ``12m`` — two units is enough to be useful."""
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class HealthMonitor:
    """Records samples and answers the dashboard's questions. ``bot.health``."""

    def __init__(self, collection, *, keep_days: int = KEEP_DAYS) -> None:
        self._col = collection
        self._keep_days = keep_days
        self._indexed = False
        self.started_at = datetime.datetime.now(datetime.timezone.utc)

    def _ensure_index(self) -> None:
        if self._col is None or self._indexed:
            return
        self._indexed = True
        try:
            self._col.create_index("at", expireAfterSeconds=self._keep_days * 86400,
                                   background=True)
        except Exception:  # noqa: BLE001 - housekeeping never breaks a sample
            pass

    def record(self, *, latency_ms: Optional[float], connected: bool,
               guilds: int, members: int) -> None:
        if self._col is None:
            return
        self._ensure_index()
        try:
            self._col.insert_one({
                "at": datetime.datetime.now(datetime.timezone.utc),
                "status": classify(latency_ms, connected),
                "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
                "guilds": int(guilds),
                "members": int(members),
            })
        except Exception:  # noqa: BLE001 - a lost sample is not worth an exception
            pass

    def samples(self, days: Optional[int] = None) -> list[dict]:
        if self._col is None:
            return []
        self._ensure_index()
        since = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=days or self._keep_days))
        try:
            return list(self._col.find({"at": {"$gte": since}}).sort("at", 1))
        except Exception:  # noqa: BLE001
            return []

    def uptime_seconds(self) -> float:
        return (datetime.datetime.now(datetime.timezone.utc) - self.started_at).total_seconds()
