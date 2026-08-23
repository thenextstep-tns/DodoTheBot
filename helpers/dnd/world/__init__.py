"""
World layer — the things that exist and the log of what happened to them.

Pure dataclasses with explicit ``to_doc`` / ``from_doc``. No I/O lives here:
persistence is ``store/``'s job, and keeping the two apart is what lets the whole
simulation be exercised in memory, without a database, in a test.

This layer may import ``rules/`` and ``store/``; it must never import ``mind/``,
``narrative/`` or ``llm/`` (docs/dnd/01-ARCHITECTURE.md §1).
"""

from helpers.dnd.world.campaign import (  # noqa: F401
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_PAUSED,
    Campaign,
)
from helpers.dnd.world.entity import (  # noqa: F401
    KIND_CREATURE,
    KIND_FACTION,
    KIND_NPC,
    KIND_PC,
    KINDS,
    TIER_ACTIVE,
    TIER_DORMANT,
    TIER_FOCUS,
    TIERS,
    Entity,
    Identity,
    Position,
)
from helpers.dnd.world.event import WorldEvent, event_seed  # noqa: F401
from helpers.dnd.world.goal import (  # noqa: F401
    KINDS as GOAL_KINDS,
    Goal,
)
from helpers.dnd.world.scene import Scene  # noqa: F401
from helpers.dnd.world.view import (  # noqa: F401
    EntityView,
    HeldBelief,
    PerceivedEntity,
    Recollection,
    project,
)
