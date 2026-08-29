"""
Campaigns — the unit of tenancy.

Everything in Dodo Tabletop is scoped to a campaign, which is scoped to a guild.
That is not decoration: the cog this replaces had no ``guild_id`` on any document
and one global forum-channel constant, so it structurally could not serve two
servers. Here, ``(guild_id, campaign_id)`` is on every record from the first
commit and the repositories refuse to query without it.

A campaign owns its own RNG root (``seed``) and its own event counter (``seq``),
which together make replay possible: the same seed and the same event sequence
reproduce the same campaign exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_ARCHIVED = "archived"

# Defaults for a fresh campaign. Kept here rather than scattered so the panel,
# the create command and the importer all agree on what "new" means.
DEFAULT_SETTINGS: dict = {
    "tone": "",
    "gm_style": "",
    "tick_minutes": 10,          # world minutes per tick (P3)
    "tick_real_seconds": 900,
    "autonomous_gm": False,      # P5
    "canon_auto_accept": 0.0,    # P4 — 0.0 means the GM approves everything
    "npc_focus_cap": 8,
    "safety": {                  # P4/P11 — conservative until a GM says otherwise
        "lines": ["sexual content", "harm to children"],
        "veils": [],
        "intensity": "moderate",
        "x_card_enabled": True,
    },
}


@dataclass
class Campaign:
    """One campaign on one server."""

    id: Any = None
    guild_id: int = 0
    name: str = ""
    ruleset: str = "freeform"
    status: str = STATUS_ACTIVE

    gm_ids: list = field(default_factory=list)
    player_ids: list = field(default_factory=list)
    channel_id: int = 0              # forum/text channel scenes are opened in

    world_time: int = 0              # in-world minutes since the campaign epoch
    seq: int = 0                     # last event sequence number
    seed: int = 0                    # RNG root; set at creation, never changed

    settings: dict = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    legacy_id: Any = None            # set by the importer, for idempotency

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> dict:
        doc = {
            "guild_id": self.guild_id,
            "name": self.name,
            "ruleset": self.ruleset,
            "status": self.status,
            "gm_ids": list(self.gm_ids),
            "player_ids": list(self.player_ids),
            "channel_id": self.channel_id,
            "world_time": self.world_time,
            "seq": self.seq,
            "seed": self.seed,
            "settings": self.settings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.legacy_id is not None:
            doc["legacy_id"] = self.legacy_id
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Campaign":
        settings = dict(DEFAULT_SETTINGS)
        settings.update(doc.get("settings") or {})
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            name=str(doc.get("name", "")),
            ruleset=str(doc.get("ruleset", "freeform")),
            status=doc.get("status", STATUS_ACTIVE),
            gm_ids=[int(x) for x in (doc.get("gm_ids") or [])],
            player_ids=[int(x) for x in (doc.get("player_ids") or [])],
            channel_id=int(doc.get("channel_id", 0)),
            world_time=int(doc.get("world_time", 0)),
            seq=int(doc.get("seq", 0)),
            seed=int(doc.get("seed", 0)),
            settings=settings,
            legacy_id=doc.get("legacy_id"),
            created_at=doc.get("created_at") or datetime.now(timezone.utc),
            updated_at=doc.get("updated_at") or datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------ #
    #  Membership
    # ------------------------------------------------------------------ #
    def is_gm(self, user_id: int) -> bool:
        return int(user_id) in self.gm_ids

    def is_player(self, user_id: int) -> bool:
        return int(user_id) in self.player_ids

    def is_member(self, user_id: int) -> bool:
        return self.is_gm(user_id) or self.is_player(user_id)
