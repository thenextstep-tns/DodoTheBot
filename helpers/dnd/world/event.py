"""
The event log — the spine of the simulation.

**Every** state change is a :class:`WorldEvent`, appended to a per-campaign log.
Entity state is a projection of that log. One design decision buys all of:

* **replay** — re-run from ``seq`` 0 and get identical state;
* **explainability** — ``caused_by`` chains render as "why did that happen";
* **witness encoding** — memory is written from events (P2), so perception
  filters apply uniformly instead of being sprinkled through call sites;
* **regression tests** — a recorded log is a fixture for the entire engine;
* **undo** — the GM's most-wanted feature, effectively free.

``seq`` is monotonic per campaign and carries a unique index, which doubles as
the optimistic-concurrency control: a duplicate key means someone else wrote
first, so re-read and retry.

Events are **immutable**. Nothing edits one after it is appended; a correction is
another event. That is what keeps replay honest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Event kinds. Kept as a flat vocabulary rather than a class hierarchy — the
# payload differs per kind, and a dict is easier to store, replay and extend
# than a polymorphic tree.
CAMPAIGN_CREATED = "campaign_created"
CHARACTER_CREATED = "character_created"
CHARACTER_RETIRED = "character_retired"
PLAYER_JOINED = "player_joined"
PLAYER_LEFT = "player_left"
SCENE_OPENED = "scene_opened"
SCENE_CLOSED = "scene_closed"
CHECK = "check"                 # an action resolved against a ruleset
ROLL = "roll"                   # a bare dice roll, no resolution attached
NPC_SPAWNED = "npc_spawned"     # an NPC entered the world with a mind (P2)
TIME_ADVANCED = "time_advanced"  # the GM let world time pass (P2)
RELATION = "relation"           # something happened between two entities (P2)
CLOCK_FILLED = "clock_filled"   # a front ran out of road (P3)
CLOCK_EFFECT = "clock_effect"   # and this is what it did (P3)
LEGACY_ACTION = "legacy_action"  # imported from the old cog (13-MIGRATION.md)


@dataclass(frozen=True)
class WorldEvent:
    """One thing that happened. Immutable."""

    guild_id: int
    campaign_id: Any
    seq: int
    kind: str
    world_time: int = 0                       # in-world minutes since campaign epoch
    actor_id: Any = None
    targets: tuple = ()
    payload: dict = field(default_factory=dict)
    seed: int = 0                             # the RNG seed used to resolve it
    caused_by: int | None = None              # seq of the triggering event
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "seq": self.seq,
            "kind": self.kind,
            "world_time": self.world_time,
            "actor_id": self.actor_id,
            "targets": list(self.targets),
            "payload": self.payload,
            "seed": self.seed,
            "caused_by": self.caused_by,
            "at": self.at,
        }

    @classmethod
    def from_doc(cls, doc: dict) -> "WorldEvent":
        return cls(
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            seq=int(doc.get("seq", 0)),
            kind=doc.get("kind", ""),
            world_time=int(doc.get("world_time", 0)),
            actor_id=doc.get("actor_id"),
            targets=tuple(doc.get("targets") or ()),
            payload=doc.get("payload") or {},
            seed=int(doc.get("seed", 0)),
            caused_by=doc.get("caused_by"),
            at=doc.get("at") or datetime.now(timezone.utc),
        )


def event_seed(campaign_seed: int, seq: int) -> int:
    """The RNG seed for resolving event ``seq`` in a campaign.

    Derived rather than random so a replay reproduces every roll exactly. The
    multiplier is a large odd constant, which spreads consecutive ``seq`` values
    across the seed space instead of handing out neighbours — consecutive seeds
    produce visibly correlated first draws in a Mersenne Twister, and players
    notice streaks long before they can explain them.
    """
    return (campaign_seed ^ (seq * 0x9E3779B1)) & 0xFFFFFFFF
