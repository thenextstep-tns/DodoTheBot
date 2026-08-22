"""
Faction clocks — what makes the world *continue*.

Straight from Apocalypse World's fronts, and entirely free of any model
(``06-DECISION-ENGINE.md`` §10). A clock is a thing that is going to happen
unless somebody stops it: *The Compact seizes the north dock*, eight segments,
half a segment a day. Nobody has to be present for it to fill.

That is the whole of async play. A campaign where nothing moves between sessions
is a diorama, and the difference between a world and a set of rooms is whether
ignoring a problem makes it worse. Clocks are how ignoring a problem makes it
worse.

**Players can block, slow or accelerate a clock**, which is the entire feedback
loop between play and world: the fiction moves the clock, the clock moves the
fiction. Blocking is deliberately not "stopped" — a blocked clock is one someone
is actively holding shut, and it resumes the moment they stop.

Pure: this module advances arithmetic and decides nothing about storage. The
repository writes it back and the tick supplies the elapsed time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A clock's life. `broken` is for a front the fiction has overtaken — the dock
# burned down, so the Compact seizing it is no longer a thing that can happen.
RUNNING = "running"
PAUSED = "paused"
COMPLETE = "complete"
BROKEN = "broken"
STATUSES = (RUNNING, PAUSED, COMPLETE, BROKEN)

# What a clock does when it fills. Kept as data rather than code so a GM can
# author consequences without one, and so a completed clock is replayable.
ON_COMPLETE_KINDS = ("announce", "spawn_event", "start_clock")


@dataclass
class Clock:
    """A front, ticking toward something."""

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None

    name: str = ""
    faction_id: Any = None          # optional: whose front this is

    segments: int = 8               # how many steps until it happens
    filled: float = 0.0             # how many are done, fractional between ticks
    rate: float = 0.5               # segments per in-world day

    status: str = RUNNING
    blocked_by: list = field(default_factory=list)   # entities holding it shut
    on_complete: list = field(default_factory=list)  # [{kind, payload}]

    created_at: int = 0             # world time
    completed_at: int | None = None

    # ------------------------------------------------------------------ #
    #  Reading
    # ------------------------------------------------------------------ #
    @property
    def blocked(self) -> bool:
        return bool(self.blocked_by)

    @property
    def running(self) -> bool:
        """Whether time actually moves this clock right now."""
        return self.status == RUNNING and not self.blocked

    @property
    def progress(self) -> float:
        if self.segments <= 0:
            return 1.0
        return max(0.0, min(1.0, self.filled / self.segments))

    def days_remaining(self) -> float | None:
        """In-world days until it fills at the current rate, or ``None``.

        ``None`` means never — it is stopped, blocked, or its rate is zero, and
        a GM should be told "not while you hold it" rather than a made-up date.
        """
        if not self.running or self.rate <= 0:
            return None
        return max(0.0, (self.segments - self.filled) / self.rate)

    def render(self) -> str:
        """The clock face. Filled segments, then empty ones."""
        done = int(min(self.segments, max(0, round(self.filled))))
        return "●" * done + "○" * max(0, self.segments - done)

    def describe(self) -> str:
        """One line a GM can read at a glance."""
        if self.status == COMPLETE:
            return f"{self.render()} **filled**"
        if self.status == BROKEN:
            return f"{self.render()} broken — overtaken by events"
        if self.status == PAUSED:
            return f"{self.render()} paused"
        if self.blocked:
            return f"{self.render()} held shut by {len(self.blocked_by)}"
        left = self.days_remaining()
        if left is None:
            return f"{self.render()} not moving"
        return f"{self.render()} {self.filled:.1f}/{self.segments} · ~{left:.0f}d left"

    # ------------------------------------------------------------------ #
    #  Storage
    # ------------------------------------------------------------------ #
    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "guild_id": int(self.guild_id),
            "campaign_id": self.campaign_id,
            "name": self.name,
            "faction_id": self.faction_id,
            "segments": int(self.segments),
            "filled": float(self.filled),
            "rate": float(self.rate),
            "status": self.status,
            "blocked_by": list(self.blocked_by),
            "on_complete": list(self.on_complete),
            "created_at": int(self.created_at),
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_doc(cls, doc: dict) -> "Clock":
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            name=doc.get("name", ""),
            faction_id=doc.get("faction_id"),
            segments=int(doc.get("segments", 8)),
            filled=float(doc.get("filled", 0.0)),
            rate=float(doc.get("rate", 0.5)),
            status=doc.get("status", RUNNING),
            blocked_by=list(doc.get("blocked_by") or []),
            on_complete=list(doc.get("on_complete") or []),
            created_at=int(doc.get("created_at", 0)),
            completed_at=doc.get("completed_at"),
        )


# --------------------------------------------------------------------------- #
#  Advancing
# --------------------------------------------------------------------------- #
def advance(clock: Clock, days: float, *, world_time: int = 0) -> bool:
    """Move a clock forward by ``days`` of in-world time.

    Returns whether it *completed on this step* — once only, so a caller can
    fire its consequences without having to remember whether it already did.
    Mutates the clock; storage is somebody else's job.
    """
    if not clock.running or days <= 0:
        return False

    clock.filled += clock.rate * days
    if clock.filled < clock.segments:
        return False

    clock.filled = float(clock.segments)
    clock.status = COMPLETE
    clock.completed_at = int(world_time)
    return True


def nudge(clock: Clock, segments: float) -> Clock:
    """Push a clock forward or drag it back by hand.

    The GM's direct hand on a front, and the shape a player's action takes when
    it does not warrant its own mechanism: burning the ledgers is `-2`.
    Completing this way is deliberate and counts.
    """
    clock.filled = max(0.0, min(float(clock.segments), clock.filled + segments))
    if clock.filled >= clock.segments and clock.status == RUNNING:
        clock.status = COMPLETE
    elif clock.status == COMPLETE and clock.filled < clock.segments:
        # Dragged back below the line: it is a live front again.
        clock.status = RUNNING
        clock.completed_at = None
    return clock
