"""
Cog categories ("meta-cogs").

Groups the many individual cogs into a handful of named categories so a server can
be managed in coarse, meaningful chunks from the control panel. This is a
presentation + bulk-toggle *layer* only: each category maps to a set of real cog
``qualified_name``s, and toggling a category just writes the per-cog enabled flag
(``cog_guild_state``) for each member. Enforcement is unchanged — it stays per-cog
in ``helpers/visibility.py`` and ``helpers/command_sync.py``.

Core cogs are never toggleable (disabling them would break the bot or the panel).
Any loaded cog not listed here is surfaced under "Other" so nothing is hidden.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Ordered categories. ``toggleable`` False marks the always-on core.
CATEGORIES: list[dict] = [
    {
        "key": "minigames",
        "label": "Minigames",
        "emoji": "🎮",
        "description": "Reaction / push-your-luck games and novelty fun.",
        "toggleable": True,
        "cogs": ["cheese", "pumpkin", "deathroll", "gilane", "quote", "throw", "pp", "fun", "economy"],
    },
    {
        "key": "universe",
        "label": "Dodo Universe",
        "emoji": "🐾",
        "description": "Pets and creatures: cats/dogs/waifus, fishing, gym, mouse racing.",
        "toggleable": True,
        "cogs": ["pet", "fishing", "gym", "racing", "racestats"],
    },
    {
        "key": "eso",
        "label": "ESO Raiding & Info",
        "emoji": "⚔️",
        "description": "Raid setups & schedule, parses, the parse tournament and PAT decoder.",
        "toggleable": True,
        "cogs": ["raid_setups", "scheduler", "parsing", "parse_tournament", "pat"],
    },
    {
        "key": "moderation",
        "label": "Moderation & Server Mgmt",
        "emoji": "🛡️",
        "description": "Moderation, anti-spam, audit log, event tracking, seasonal & server config.",
        "toggleable": True,
        "cogs": ["moderation", "spam", "log", "event_tracker", "server_config", "seasonal"],
    },
    {
        "key": "ai",
        "label": "AI & Conversation",
        "emoji": "🤖",
        "description": "LLM chat and Markov imitation.",
        "toggleable": True,
        "cogs": ["chat", "talkengine"],
    },
    {
        "key": "tabletop",
        "label": "Dodo Tabletop",
        "emoji": "🎲",
        "description": "The living-world tabletop engine: campaigns, characters, scenes and dice.",
        "toggleable": True,
        # dnd_legacy is the old session manager, kept loadable for one release
        # while campaigns migrate across (docs/dnd/13-MIGRATION.md).
        "cogs": ["dnd", "dnd_legacy"],
    },
    {
        "key": "core",
        "label": "Core",
        "emoji": "⚙️",
        "description": "Bot & panel essentials — always on.",
        "toggleable": False,
        "cogs": ["general", "owner", "control_panel"],
    },
]

OTHER_CATEGORY = {
    "key": "other",
    "label": "Other",
    "emoji": "📦",
    "description": "Loaded cogs not yet assigned to a category.",
    "toggleable": True,
    "cogs": [],
}

# Reverse map: cog qualified_name -> category key (built once).
_COG_TO_CATEGORY: dict[str, str] = {
    cog: category["key"] for category in CATEGORIES for cog in category["cogs"]
}
CORE: frozenset[str] = frozenset(
    cog for category in CATEGORIES if not category["toggleable"] for cog in category["cogs"]
)


# Passive-listener "features" — behaviors that run without a command being
# invoked, each individually toggleable per guild (for monetization flexibility).
# A feature is active only when its owning cog is enabled AND its own switch is on
# (see VisibilityManager.feature_active). Gated at the top of the relevant listener.
FEATURES: list[dict] = [
    {"key": "cheese_drop", "cog": "cheese", "label": "Cheese drops",
     "description": "Random 🧀 drops that start the co-op stretch game."},
    {"key": "spam_autoban", "cog": "spam", "label": "Anti-spam auto-ban",
     "description": "Auto-remove/ban users posting too fast, across too many channels, or cross-posting."},
    {"key": "mention_link_filter", "cog": "spam", "label": "Mention & link filter",
     "description": "Remove/ban messages with @everyone/@here or unauthorized invite links."},
    {"key": "audit_log", "cog": "log", "label": "Server audit logging",
     "description": "Log member/message/role/channel events to the log channel."},
    {"key": "event_tracking", "cog": "event_tracker", "label": "Event & behavior tracking",
     "description": "Track configured messages, uploads and reactions."},
    {"key": "pat_decode", "cog": "pat", "label": "PAT screenshot decoding",
     "description": "Auto-decode trial-clear (PAT) table screenshots posted in chat."},
    {"key": "tribes", "cog": "tribes", "label": "Tribe role rules",
     "description": "Hourly sweep that grants roles from the rules on the server's Tribes page."},
    {"key": "event_rules", "cog": "event_actions", "label": "Event rules",
     "description": "Run the 'when X happens, post this' rules built on the server's Events page."},
]

_FEATURES_BY_COG: dict[str, list[dict]] = {}
for _feat in FEATURES:
    _FEATURES_BY_COG.setdefault(_feat["cog"], []).append(_feat)


def features_for_cog(cog: str) -> list[dict]:
    """Passive-listener features owned by a cog (empty if none)."""
    return list(_FEATURES_BY_COG.get(cog, []))


def category_of(cog: str) -> str | None:
    """Category key a cog belongs to, or ``None`` if unmapped."""
    return _COG_TO_CATEGORY.get(cog)


def is_core(cog: str) -> bool:
    return cog in CORE


def member_cogs(category_key: str) -> list[str]:
    for category in CATEGORIES:
        if category["key"] == category_key:
            return list(category["cogs"])
    return []


def group_loaded_cogs(loaded_cog_names) -> list[dict]:
    """Bucket the loaded cog names into the ordered categories.

    Returns a shallow copy of each category with a ``present`` list of the
    currently-loaded member cogs (sorted). Unmapped loaded cogs are collected into
    an "Other" category so they always remain visible/manageable. Empty categories
    are omitted.
    """
    loaded = set(loaded_cog_names)
    result: list[dict] = []
    assigned: set[str] = set()
    for category in CATEGORIES:
        present = sorted(c for c in category["cogs"] if c in loaded)
        assigned.update(present)
        if present:
            result.append({**category, "present": present})
    leftover = sorted(loaded - assigned)
    if leftover:
        logger.warning(
            "Cogs missing from the category taxonomy (shown under 'Other'): %s", ", ".join(leftover)
        )
        result.append({**OTHER_CATEGORY, "present": leftover})
    return result
