"""
Per-guild tunables for Dodo Tabletop — **separate from ``helpers/parameters.py``.**

Same idea as the bot's parameter registry, same typed-spec shape, but its own
list and its own collection so tabletop settings never appear among the general
cog settings on the dashboard. The DnD panel page renders these itself.

Only parameters something actually reads are registered. The rest arrive with the
phase that consumes them, so the panel never shows a setting that does nothing —
a dead toggle is worse than a missing one, because someone will change it and
expect an effect.

--------------------------------------------------------------------------- #
MERGE NOTE
--------------------------------------------------------------------------- #
This reuses ``ParamManager`` and ``coerce`` from ``helpers/parameters.py`` rather
than reimplementing typed coercion — that is machinery, not surface, and forking
it would mean fixing every coercion bug twice. What is separate is the **spec
list** and the **collection**.

To merge later: append ``DND_PARAMETERS`` to ``PARAMETERS`` and point at the
shared ``command_params`` collection; the panel would then render them under a
``dnd`` cog like any other. Deliberately not done — the whole point of the
current arrangement is that tabletop has no presence in the general settings UI.
"""

from __future__ import annotations

from typing import Any, Optional

from config.database import db
from helpers.parameters import ParamManager

# Tabletop's own store, so a general "reset this server's settings" never
# silently rewrites a campaign's rules, and vice versa.
dnd_params_col = db["DndParams"]

# Same spec shape as helpers/parameters.PARAMETERS: key, cog, label, description,
# type, default, and choices for type="choice".
DND_PARAMETERS: list[dict] = [
    # --- rules ---
    {"key": "dnd_default_ruleset", "cog": "dnd", "type": "choice", "default": "freeform",
     "choices": ["freeform", "srd5e"],
     "label": "Default ruleset",
     "description": "Ruleset a new campaign starts with. Freeform is narrative; srd5e is D&D 5e SRD 5.1."},
    {"key": "dnd_max_dice", "cog": "dnd", "type": "int", "default": 100,
     "label": "Max dice per roll",
     "description": "Largest number of dice a single roll expression may throw."},
    {"key": "dnd_max_sides", "cog": "dnd", "type": "int", "default": 1000,
     "label": "Max die size",
     "description": "Largest die a roll expression may use."},

    # --- knowledge (P1) ---
    {"key": "dnd_kb_budget", "cog": "dnd", "type": "int", "default": 1200,
     "label": "Knowledge budget (tokens)",
     "description": "How much campaign knowledge a scene render may draw on. Higher is richer and slower."},
    {"key": "dnd_kb_max_facts", "cog": "dnd", "type": "int", "default": 40,
     "label": "Max facts retrieved",
     "description": "Hard cap on facts pulled per retrieval, whatever the token budget allows."},
    {"key": "dnd_canon_auto_accept", "cog": "dnd", "type": "float", "default": 0.0,
     "label": "Canon auto-accept",
     "description": "Confidence above which invented facts become canon without GM review. 0 = the GM approves everything."},
]


class DndParamManager(ParamManager):
    """Tabletop's parameter manager, over its own collection and spec list.

    Subclasses the shared manager for its typed coercion and per-guild cache —
    that part is plumbing, and a second copy would just be a second place for the
    same bug.
    """

    def __init__(self, collection=dnd_params_col, specs: list[dict] = DND_PARAMETERS):
        super().__init__(collection, specs)


# One instance, imported directly by tabletop code. Not hung on the bot object:
# `bot.params` is the general registry, and two similarly-named attributes on the
# bot is exactly the intertwining this separation exists to avoid.
params = DndParamManager()


def get(guild_id: Optional[int], key: str) -> Any:
    """Read a tabletop parameter for a guild."""
    return params.get(guild_id, key)


def entries(guild_id: Optional[int]) -> list[dict]:
    """Specs + current values, for the DnD panel page."""
    return params.entries_for_cog(guild_id, "dnd")


# --------------------------------------------------------------------------- #
#  Simulation tunables, server layer
# --------------------------------------------------------------------------- #
# The tunables in helpers/dnd/tuning.py have two override layers: the server
# (here) and the campaign (campaign.settings["tuning"]). They are kept out of
# DND_PARAMETERS above because there are dozens of them, they are grouped and
# ranged differently, and the DnD panel renders them in their own section.
TUNING_COLLECTION = db["DndTuning"]


def tuning_overrides(guild_id: Optional[int]) -> dict:
    """Every server-level tunable override for a guild."""
    doc = TUNING_COLLECTION.find_one({"guild_id": guild_id})
    return (doc or {}).get("values", {})


def pack_overrides(guild_id: Optional[int]) -> dict:
    """Every server-level behaviour archetype for a guild.

    Same document as the tunables, different field: archetypes are configuration
    layered the same way, and a second collection would be a second thing to
    scope, index and export for no gain.
    """
    doc = TUNING_COLLECTION.find_one({"guild_id": guild_id})
    return (doc or {}).get("packs", {})


def set_packs(guild_id: Optional[int], packs: dict) -> None:
    """Replace a guild's server-level archetypes wholesale.

    The whole map rather than one key, so removing one is an ordinary write. The
    per-key ``$unset`` the tunables use is the reason clearing a server tunable
    is the one path no test covers (``tests/fake_mongo.py`` has no ``$unset``).
    """
    TUNING_COLLECTION.update_one(
        {"guild_id": guild_id}, {"$set": {"packs": dict(packs or {})}}, upsert=True
    )


def set_tuning(guild_id: Optional[int], key: str, value) -> None:
    """Set one server-level tunable. ``None`` clears it back to the default."""
    if value is None:
        TUNING_COLLECTION.update_one(
            {"guild_id": guild_id}, {"$unset": {f"values.{key}": ""}}, upsert=True
        )
        return
    TUNING_COLLECTION.update_one(
        {"guild_id": guild_id}, {"$set": {f"values.{key}": value}}, upsert=True
    )
