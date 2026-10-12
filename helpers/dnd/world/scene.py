"""
Scenes — what is on screen right now.

A scene is where play happens and, on Discord, it is a thread. It holds the
small amount of state that makes narration feel grounded rather than generic:
who is present, where, when, and what the weather is doing.

At P0 a scene is presence plus a title: enough to bind a channel to a campaign,
promote the people in it to the ``focus`` tier, and give the event log somewhere
to hang. The affordance list and environmental state arrive with P1, and the
turn loop with P3 — the shape is here so those land as fills rather than
rewrites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"


@dataclass
class Scene:
    """One scene in a campaign."""

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None

    title: str = ""
    status: str = STATUS_OPEN
    channel_id: int = 0                  # the Discord thread or channel
    message_id: int | None = None        # the pinned scene card

    present: list = field(default_factory=list)   # entity ids in the scene
    location_id: Any = None

    # Environment. Written by the sim from P1; free-text so a GM can override
    # any of it without the engine needing a taxonomy of weather.
    time_of_day: str = ""
    weather: str = ""
    lighting: str = ""

    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None

    def to_doc(self) -> dict:
        doc = {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "title": self.title,
            "status": self.status,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "present": list(self.present),
            "location_id": self.location_id,
            "time_of_day": self.time_of_day,
            "weather": self.weather,
            "lighting": self.lighting,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Scene":
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            title=str(doc.get("title", "")),
            status=doc.get("status", STATUS_OPEN),
            channel_id=int(doc.get("channel_id", 0)),
            message_id=doc.get("message_id"),
            present=list(doc.get("present") or []),
            location_id=doc.get("location_id"),
            time_of_day=str(doc.get("time_of_day", "")),
            weather=str(doc.get("weather", "")),
            lighting=str(doc.get("lighting", "")),
            opened_at=doc.get("opened_at") or datetime.now(timezone.utc),
            closed_at=doc.get("closed_at"),
        )

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_OPEN
