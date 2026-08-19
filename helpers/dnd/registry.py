"""
What belongs to Dodo Tabletop — the single source of truth.

The tabletop engine is kept **completely separate** from the rest of the bot:
its own strings (``lang_dnd.py``), its own parameters
(``helpers/dnd/parameters.py``), its own storage (the ``dnd_*`` collections), its
own dashboard section, its own panel access model (``web/dnd/access.py``).

Separation only stays true if there is one list saying what is separate. Shared
code that needs to exclude tabletop — the panel's cog inventory, the category
taxonomy — asks *this* module rather than hardcoding names, so adding a cog here
is the only edit needed to keep it out of the general surfaces.

--------------------------------------------------------------------------- #
MERGE NOTES — what this deliberately does NOT duplicate
--------------------------------------------------------------------------- #
Three systems are *enforcement*, not presentation, and tabletop keeps using them
rather than growing a parallel copy. Forking these would mean an admin could
disable a cog and have it stay on, which is a lie the panel must never tell.

* ``bot.visibility``   — who may run a command; whether a cog is on for a guild.
* ``bot.panel_access`` — who may open a guild's panel at all. The *campaign*
                         scope layered on top lives in ``web/dnd/access.py``.
* ``bot.state``        — resumable flows, once scenes become live (P3).

If tabletop is ever extracted into its own bot, those three are the seams to cut,
and each is one import.
"""

from __future__ import annotations

# Cogs owned by the tabletop engine. Excluded from the general dashboard; they
# get their own section on the DnD page instead.
DND_COGS: frozenset[str] = frozenset({
    "dnd",          # cogs/dnd/ — the engine
    "dnd_legacy",   # cogs/dnd_legacy.py — the old session manager, one release only
})

# Extension module names, for the panel's file-level inventory. ``cogs.dnd.cog``
# is the loadable entry point; the siblings are plain modules the cog loader
# skips (see cogs/dnd/__init__.py).
DND_EXTENSIONS: frozenset[str] = frozenset({
    "cog", "context", "embeds", "dnd_legacy", "knowledge",
})

# Collections in config/database.py that belong to tabletop. Listed so a future
# extraction (or a "wipe this server's tabletop data" tool) has one place to read.
DND_COLLECTIONS: tuple[str, ...] = (
    "dnd_campaigns", "dnd_entities", "dnd_scenes", "dnd_events", "dnd_knowledge",
    "dnd_memories", "dnd_beliefs", "dnd_relations", "dnd_clocks",
    "dnd_canon_queue", "dnd_snapshots",
)


def is_dnd_cog(name: str) -> bool:
    """Whether a cog qualified_name belongs to tabletop."""
    return name in DND_COGS


def is_dnd_extension(module_name: str) -> bool:
    """Whether a discovered cog *file* belongs to tabletop.

    The panel walks ``cogs/`` for filenames, so it sees ``cog``, ``context`` and
    ``embeds`` from inside ``cogs/dnd/`` — names generic enough that matching
    them by string alone would be fragile. Callers pass the full dotted path when
    they have it.
    """
    if module_name.startswith("cogs.dnd.") or module_name == "cogs.dnd_legacy":
        return True
    return module_name in DND_COGS


def strip_dnd(names):
    """Drop every tabletop cog from an iterable of cog names."""
    return [n for n in names if not is_dnd_cog(n)]
