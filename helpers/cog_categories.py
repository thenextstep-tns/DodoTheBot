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

**Dodo Tabletop is deliberately absent.** Its cogs are filtered out before they
reach this taxonomy (``helpers/dnd/registry.py``) and are managed from their own
DnD page instead, so the tabletop engine never appears among the bot's ordinary
features. MERGE NOTE: to fold it back in, drop the ``strip_dnd`` call in
``group_loaded_cogs`` and add a category listing ``dnd``/``dnd_legacy``.
"""

from __future__ import annotations

import logging

from helpers.dnd import registry as dnd_registry

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
        # "gym" is the cog's qualified_name; "fighting_and_gym" is the file it
        # lives in. The per-guild pages group by cog name and the bot-wide Cogs
        # list groups by file, so both spellings belong here.
        "cogs": ["pet", "fishing", "gym", "fighting_and_gym", "racing", "racestats"],
    },
    {
        "key": "eso",
        "label": "ESO Raiding & Info",
        "emoji": "⚔️",
        "description": "Raid setups & schedule, parses, the parse tournament, PAT decoder and trial ranks.",
        "toggleable": True,
        "cogs": ["raid_setups", "scheduler", "parsing", "parse_tournament", "pat", "trial_ranks"],
    },
    {
        "key": "moderation",
        "label": "Moderation & Server Mgmt",
        "emoji": "🛡️",
        "description": "Moderation, anti-spam, audit log, event tracking & rules, tribe roles, seasonal & server config.",
        "toggleable": True,
        "cogs": ["moderation", "spam", "log", "event_tracker", "event_actions", "tribes",
                 "server_config", "seasonal"],
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
    {"key": "chat_listeners", "cog": "chat", "label": "Chat string listeners",
     "description": "React to phrases in ordinary messages. The phrases themselves are edited on the Events page →",
     "link": ("events", "Chat triggers")},
    {"key": "chat_unprompted", "cog": "chat", "label": "Unprompted chat",
     "description": "Very rarely join a live conversation nobody addressed, using the last few messages as context."},
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
    # Tabletop is managed on its own page and must not appear here.
    loaded = set(dnd_registry.strip_dnd(loaded_cog_names))
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
