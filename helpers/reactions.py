"""
What each kind of cat does when you show it a thing.

The grid is ``emoji x class``: 1,401 catalogued objects against 13 classes, so
roughly eighteen thousand cells. That size is the point rather than a problem —
the game is finding out that showing a Loaf a pair of trousers is different from
showing them to a Zoom Gremlin, and you only find that out by trying it.

Three layers answer for any cell, nearest first:

1. what this server's admins wrote (``EmojiReactions`` with their ``guild_id``)
2. what was written for everyone (the same collection with ``guild_id`` 0)
3. :mod:`helpers.reaction_written`, the cells written one at a time
Nothing generates a line. An object nobody has written about does nothing when
it is shown, which is honest and also the point: the game reacts to the objects
that have had a person think about them, and no others.

Nothing is ever pre-written into the database, so a fresh server inherits the
whole grid and a server that edits one cell stores exactly one row. Because the
flavour layer answers everything, there are no blank cells to trip over in a
fight, and an admin editing one is always editing something rather than filling
in a form.
"""

from __future__ import annotations

import datetime

import config_py
from helpers import emoji_catalogue, reaction_written

GLOBAL = 0                      # the "for everyone" layer's guild_id
ATTRS = ("strength", "agility", "intellect", "charm")


def seed_pairs() -> int:
    """How many cells are written by hand, wherever they live."""
    return sum(len(v) for v in reaction_written.WRITTEN.values())


# --------------------------------------------------------------------------- #
#  Storage
# --------------------------------------------------------------------------- #
_INDEX: dict[str, dict] = {}


def _catalogue_index() -> dict[str, dict]:
    """Unicode rows keyed by character, built once.

    The flavour layer needs an object's *name* to write about it, and the
    resolver only ever gets the character, so the two are joined here rather
    than by handing every caller the catalogue.
    """
    global _INDEX
    if not _INDEX:
        _INDEX = {row["char"]: row for row in emoji_catalogue.load()}
    return _INDEX


def _collection():
    return config_py.emoji_reactions


def stored(guild_id: int, emojis: list[str] = None) -> dict[tuple[str, str], dict]:
    """Every stored row for a guild, keyed ``(emoji, class)``.

    One query for a whole page of the grid: a cell-at-a-time read would be a
    hundred round trips per screen.
    """
    query = {"guild_id": guild_id}
    if emojis:
        query["emoji"] = {"$in": list(emojis)}
    return {(row["emoji"], row["cls"]): row for row in _collection().find(query)}


def resolve(emoji: str, cls: str, guild_rows: dict, global_rows: dict) -> dict:
    """One cell, nearest layer first. ``source`` says which layer answered."""
    row = guild_rows.get((emoji, cls))
    if row is not None:
        return {"text": row.get("text", ""), "stats": row.get("stats", {}), "source": "guild"}
    row = global_rows.get((emoji, cls))
    if row is not None:
        return {"text": row.get("text", ""), "stats": row.get("stats", {}), "source": "global"}
    text, stats, source = reaction_written.line_for(emoji, cls)
    return {"text": text, "stats": stats, "source": source}


def grid(guild_id: int, emojis: list[str], classes: list[str]) -> dict:
    """A page of the grid, resolved: ``{emoji: {cls: cell}}``."""
    guild_rows = stored(guild_id, emojis)
    global_rows = stored(GLOBAL, emojis)
    return {emoji: {cls: resolve(emoji, cls, guild_rows, global_rows) for cls in classes}
            for emoji in emojis}


def save(guild_id: int, emoji: str, cls: str, text: str, stats: dict, actor_id: int = None) -> dict:
    """Write one cell for one guild, and return what the cell now resolves to.

    Returning the *resolved* cell rather than what was written is the whole
    point: clearing an override does not empty the cell, it uncovers the layer
    underneath, and a caller that assumed otherwise would paint "not decided"
    over a perfectly good default.

    A blank description deletes the override outright. Stat numbers with nothing
    written next to them are not a cell — the text is the content.
    """
    clean = {k: int(v) for k, v in (stats or {}).items() if k in ATTRS and v}
    text = (text or "").strip()
    cleared = not text
    if cleared:
        _collection().delete_one({"guild_id": guild_id, "emoji": emoji, "cls": cls})
    else:
        _collection().update_one(
            {"guild_id": guild_id, "emoji": emoji, "cls": cls},
            {"$set": {"text": text, "stats": clean, "updated_at": datetime.datetime.now(),
                      "updated_by": actor_id}},
            upsert=True,
        )
    now = resolve(emoji, cls, stored(guild_id, [emoji]), stored(GLOBAL, [emoji]))
    return {"cleared": cleared, **now}


def coverage(guild_id: int, total_emoji: int, total_classes: int) -> dict:
    """How many cells a person has written, out of how many exist.

    Every cell already answers, because the flavour layer answers all of them, so
    a percentage of *filled* cells would read 100% and mean nothing. What is
    worth showing is how much of the grid has been touched by hand.

    Counted from distinct ``(emoji, class)`` pairs rather than row counts, so a
    guild that overrides a seeded cell is not counted twice.
    """
    pairs = set()
    for gid in (GLOBAL, guild_id):
        pairs.update(stored(gid).keys())
    pairs.update((emoji, cls) for emoji, cells in reaction_written.WRITTEN.items()
                 for cls in cells)
    cells = total_emoji * total_classes
    return {"filled": len(pairs), "cells": cells,
            "percent": round(len(pairs) / cells * 100, 1) if cells else 0.0}


def guild_emoji_rows(guild) -> list[dict]:
    """This server's own custom emoji, in the same shape as the catalogue.

    They are worth having in the grid precisely because they are local: the
    joke a server already has is the one its members will try first.
    """
    rows = []
    for emoji in getattr(guild, "emojis", []) or []:
        rows.append({"char": str(emoji), "codepoint": f"guild:{emoji.id}",
                     "name": emoji.name.replace("_", " ").capitalize(),
                     "family": f"guild-{emoji.id}", "group": "This server",
                     "url": str(emoji.url), "custom": True})
    return rows


def catalogue(guild=None) -> list[dict]:
    """The server's own emoji first, then the Unicode catalogue."""
    return guild_emoji_rows(guild) + emoji_catalogue.by_usage()
