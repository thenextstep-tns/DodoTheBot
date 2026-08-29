"""
Index definitions, applied once at startup.

Two of these are doing more than speeding up a query:

* ``dnd_events (campaign_id, seq)`` is **unique**, which is the optimistic
  concurrency control for the append-only log — a duplicate key is how a writer
  learns someone else took its sequence number.
* ``dnd_entities (campaign_id, tier)`` is what keeps the world tick's cost
  proportional to the entities on screen rather than the entities in existence.

``create_index`` is idempotent, so this is safe to run on every boot. Failures
are logged and swallowed: a missing index makes the bot slower, but refusing to
start makes it useless.
"""

from __future__ import annotations

import logging

from config.database import (
    dnd_beliefs,
    dnd_campaigns,
    dnd_canon_queue,
    dnd_clocks,
    dnd_entities,
    dnd_events,
    dnd_knowledge,
    dnd_memories,
    dnd_relations,
    dnd_scenes,
)

logger = logging.getLogger(__name__)

# (collection, keys, kwargs)
_INDICES = [
    (dnd_campaigns, [("guild_id", 1), ("name", 1)], {}),
    (dnd_campaigns, [("guild_id", 1), ("channel_id", 1)], {}),

    (dnd_entities, [("campaign_id", 1), ("tier", 1)], {}),
    (dnd_entities, [("campaign_id", 1), ("kind", 1)], {}),
    (dnd_entities, [("campaign_id", 1), ("owner_id", 1)], {}),

    # Unique: this is concurrency control, not just a lookup (see the docstring).
    (dnd_events, [("campaign_id", 1), ("seq", 1)], {"unique": True}),
    (dnd_events, [("campaign_id", 1), ("world_time", 1)], {}),

    (dnd_scenes, [("campaign_id", 1), ("status", 1)], {}),
    (dnd_scenes, [("channel_id", 1), ("status", 1)], {}),

    # Declared now so the phases that fill these collections don't have to
    # remember to come back for them.
    (dnd_knowledge, [("scope", 1), ("scope_id", 1)], {}),
    (dnd_knowledge, [("scope_id", 1), ("tags", 1)], {}),
    (dnd_memories, [("entity_id", 1), ("tier", 1), ("salience", -1)], {}),
    (dnd_memories, [("entity_id", 1), ("cues", 1)], {}),
    (dnd_beliefs, [("campaign_id", 1), ("holder_id", 1)], {}),
    (dnd_beliefs, [("campaign_id", 1), ("subject_id", 1)], {}),
    (dnd_relations, [("campaign_id", 1), ("from_id", 1), ("to_id", 1)], {"unique": True}),
    (dnd_clocks, [("campaign_id", 1), ("status", 1)], {}),
    (dnd_canon_queue, [("campaign_id", 1), ("status", 1)], {}),
]


def ensure_indices() -> int:
    """Create every index that doesn't exist. Returns how many succeeded."""
    created = 0
    for collection, keys, kwargs in _INDICES:
        try:
            collection.create_index(keys, **kwargs)
            created += 1
        except Exception as error:  # noqa: BLE001 — a slow bot beats a dead one
            logger.warning(
                "Could not create index %s on %s: %s", keys, collection.name, error
            )
    return created
