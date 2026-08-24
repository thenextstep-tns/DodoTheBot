"""
What each kind of cat does when you show it a thing.

The grid is ``emoji x class``: 1,401 catalogued objects against 13 classes, so
roughly eighteen thousand cells. That size is the point rather than a problem —
the game is finding out that showing a Loaf a pair of trousers is different from
showing them to a Zoom Gremlin, and you only find that out by trying it.

Three layers answer for any cell, nearest first:

1. what this server's admins wrote (``EmojiReactions`` with their ``guild_id``)
2. what was written for everyone (the same collection with ``guild_id`` 0)
3. :data:`SEED` below, for the handful written cell by cell
4. :mod:`helpers.reaction_flavour`, which answers every remaining cell

Nothing is ever pre-written into the database, so a fresh server inherits the
whole grid and a server that edits one cell stores exactly one row. Because the
flavour layer answers everything, there are no blank cells to trip over in a
fight, and an admin editing one is always editing something rather than filling
in a form.
"""

from __future__ import annotations

import datetime

import config_py
from helpers import emoji_catalogue, reaction_flavour

GLOBAL = 0                      # the "for everyone" layer's guild_id
ATTRS = ("strength", "agility", "intellect", "charm")


# --------------------------------------------------------------------------- #
#  Seed content
# --------------------------------------------------------------------------- #
# Written by hand, keyed emoji -> class -> (what happens, stat change). Kept
# short on purpose: one thing happens, it is funny, it is over. Anything longer
# than a line does not fit in the cell or in a fight log.
def _(text: str, **stats: int) -> dict:
    return {"text": text, "stats": {k: v for k, v in stats.items() if v}}


SEED: dict[str, dict[str, dict]] = {
    "👖": {
        "loaf": _("Sits on them. They are warm now, and they are his.", strength=1, intellect=1),
        "pouncer": _("Waits inside one leg for eleven minutes. Something will walk past.", agility=2),
        "chonk": _("Gets into them. Gets stuck in them. Refuses all help.", strength=2, agility=-1),
        "ricochet": _("Wears them briefly at full speed, off three walls.", agility=2, strength=-1),
        "ghost": _("Is inside the trousers. Nobody saw it get in.", agility=1, intellect=1),
        "gremlin": _("Shreds them to threads in nine seconds and is delighted.", strength=2, charm=-1),
        "barger": _("Works out the pockets. Removes everything in them.", intellect=2),
        "stalker": _("Drags them onto the wardrobe. They live up there now.", intellect=1, agility=1),
        "purrsuader": _("Lies on them so you cannot leave the house.", intellect=2, charm=1),
        "tyrant": _("Sits on them while you are still wearing them.", charm=2, strength=1),
        "weaver": _("Winds through both legs and comes out fully dressed.", charm=2, agility=1),
        "dinner": _("Cries into the trousers until fed.", charm=2),
        "alley": _("Has slept in worse. Sleeps in these.", strength=1, charm=1),
    },
    "🥒": {
        "loaf": _("Does not turn around. Whatever it is, it can wait.", intellect=2),
        "pouncer": _("Leaves the ground entirely and lands on a shelf.", agility=2, strength=-1),
        "chonk": _("Attempts the ceiling. Achieves about a foot.", agility=1, strength=-1),
        "ricochet": _("Was already gone before it hit the floor.", agility=2),
        "ghost": _("Vanishes. The cucumber is now alone.", agility=2, intellect=1),
        "gremlin": _("Screams, launches, returns, and bites it.", agility=2, charm=-1),
        "barger": _("Sniffs it. Concludes it is a vegetable. Leaves.", intellect=3),
        "stalker": _("Observes it from above for an hour. Never blinks.", intellect=2),
        "purrsuader": _("Is insulted. You will be paying for this.", intellect=1, charm=1),
        "tyrant": _("Does not accept that this happened.", charm=2, strength=-1),
        "weaver": _("Trips you on the way out. Not an accident.", charm=1, agility=2),
        "dinner": _("Assumes it is food. Is wrong. Is furious.", charm=1, intellect=-1),
        "alley": _("Has been startled by better. Keeps eating.", strength=1),
    },
    "📦": {
        "loaf": _("Fits. Somehow fits. Will not be leaving.", strength=2, intellect=1),
        "pouncer": _("Uses it as a hide. Everything that passes is prey.", agility=2, strength=1),
        "chonk": _("Does not fit and gets in anyway. Box is now a hat.", strength=2, agility=-2),
        "ricochet": _("Enters at speed. Box travels four feet.", agility=2),
        "ghost": _("The box is empty. The box is not empty.", agility=1, intellect=2),
        "gremlin": _("Destroys the box, then mourns the box.", strength=1, charm=-1),
        "barger": _("Opens the flaps from inside. Learns a door.", intellect=3),
        "stalker": _("Stacks it and gains one metre of altitude.", intellect=2, agility=1),
        "purrsuader": _("Sits in it and looks at you until photographed.", charm=2, intellect=1),
        "tyrant": _("Claims it. It was always going to be theirs.", charm=2, strength=1),
        "weaver": _("Around, through, out, and around again.", agility=2, charm=1),
        "dinner": _("Cries from inside the box. Acoustics are excellent.", charm=3),
        "alley": _("A box is a house. Finally, a house.", strength=1, charm=1),
    },
    "🧹": {
        "loaf": _("Watches it approach. Does not move. Is swept.", intellect=1, strength=1),
        "pouncer": _("Ambushes the bristles. Wins. Is very proud.", strength=2),
        "chonk": _("Is swept around like a rug with opinions.", strength=1, agility=-1),
        "ricochet": _("Rides it, falls off, blames the broom.", agility=1, strength=-1),
        "ghost": _("Left the room when the cupboard opened.", agility=2, intellect=2),
        "gremlin": _("Attacks it. Loses. Attacks it again.", strength=1, agility=1, charm=-1),
        "barger": _("Understands the broom. Fears it correctly.", intellect=2, charm=-1),
        "stalker": _("Is above the broom. The broom cannot reach.", intellect=2, agility=1),
        "purrsuader": _("Makes the sweeping stop by being adorable at it.", charm=3),
        "tyrant": _("Sits on the pile. Sweeping is over.", charm=2, strength=1),
        "weaver": _("Between the bristles, under the handle, gone.", agility=3),
        "dinner": _("Screams. Is given food to stop screaming. Wins.", charm=2, intellect=1),
        "alley": _("Knows this one. Leaves before it starts.", agility=1, intellect=1),
    },
    "💀": {
        "loaf": _("Sits beside it companionably. No comment.", intellect=2),
        "pouncer": _("Pounces on it. It rolls. Now it is a game.", agility=1, strength=1),
        "chonk": _("Knocks it off the table. Watches it go. Satisfied.", strength=2),
        "ricochet": _("Bats it round the room at high speed.", agility=2, strength=1),
        "ghost": _("Kinship. Immediate, unsettling kinship.", intellect=2, agility=1),
        "gremlin": _("Wears it. Refuses to explain.", charm=1, strength=1),
        "barger": _("Examines the jaw hinge with real interest.", intellect=3),
        "stalker": _("Places it on the shelf, facing your bed.", intellect=2, charm=-1),
        "purrsuader": _("Poses with it until you feel something.", charm=2, intellect=1),
        "tyrant": _("Sits in it. It is a throne now.", charm=2, strength=1),
        "weaver": _("Threads through both eye sockets. Twice.", agility=3),
        "dinner": _("Cries at it. It does not feed her. Cries harder.", charm=2, intellect=-1),
        "alley": _("Has seen a skull. Has seen several.", strength=1, intellect=1),
    },
    "🐟": {
        "loaf": _("Would like the fish brought closer, please.", strength=1, charm=1),
        "pouncer": _("Takes it out of the air. This is what it is for.", strength=2, agility=1),
        "chonk": _("Eats it whole and looks for the second one.", strength=3, agility=-1),
        "ricochet": _("Catches it on the rebound off the fridge.", agility=2, strength=1),
        "ghost": _("The fish is gone. Nobody saw the fish go.", agility=2, intellect=1),
        "gremlin": _("Kills an already dead fish. Thoroughly.", strength=2, charm=-1),
        "barger": _("Works out which cupboard the fish came from.", intellect=3, strength=1),
        "stalker": _("Takes it up high to eat where you cannot judge.", intellect=1, agility=2),
        "purrsuader": _("Gets a second fish out of you without moving.", charm=3, intellect=1),
        "tyrant": _("The fish was always hers. You were holding it.", charm=2, strength=1),
        "weaver": _("Figure-eights your ankles until the fish falls.", charm=2, agility=1),
        "dinner": _("Eats it, then reports never having been fed.", charm=3, intellect=1),
        "alley": _("Eats fast, watching the door. Old habit.", strength=2, agility=1),
    },
    "🕯️": {
        "loaf": _("Sits close. Is warm. Is slightly on fire. Unbothered.", strength=1, intellect=-1),
        "pouncer": _("Stalks the flame. The flame does not move. Confusing.", agility=1, intellect=-1),
        "chonk": _("Blocks all the light. Room goes dark.", strength=2),
        "ricochet": _("Knocks it over twice at speed. House survives.", agility=2, intellect=-2),
        "ghost": _("Is lit from below and looks appalling.", intellect=1, charm=-1),
        "gremlin": _("Bats the flame. Learns. Bats it again. Learns nothing.", agility=1, intellect=-2),
        "barger": _("Works out heat before touching it. Rare and smug.", intellect=3),
        "stalker": _("Watches from above, planning something with wax.", intellect=2),
        "purrsuader": _("Arranges herself in the candlelight. Devastating.", charm=3),
        "tyrant": _("Sits between you and the candle. Deal with it.", charm=2, strength=1),
        "weaver": _("Winds past it four times without singeing a hair.", agility=3),
        "dinner": _("Cries at a candle. It is not food. She insists.", charm=2, intellect=-1),
        "alley": _("Fire means people. People mean food. Approaches.", intellect=1, charm=1),
    },
    "🎃": {
        "loaf": _("Two round heavy things, sitting. Nothing happens. Perfect.", strength=2, intellect=1),
        "pouncer": _("Ambushes it from inside. Nobody expected a cat.", agility=2, strength=1),
        "chonk": _("Is mistaken for the pumpkin. Does not correct anyone.", strength=2, charm=1),
        "ricochet": _("Rolls it down the hall at genuinely alarming speed.", agility=2, strength=1),
        "ghost": _("Occupies it. The pumpkin now has opinions.", agility=1, intellect=2),
        "gremlin": _("Hollows it further, uninvited, at 3am.", strength=2, agility=1),
        "barger": _("Gets in through the mouth. Studies the inside.", intellect=2, strength=1),
        "stalker": _("Puts it somewhere high, where it will eventually fall.", intellect=2, agility=1),
        "purrsuader": _("Sits behind it and becomes a seasonal photograph.", charm=3),
        "tyrant": _("Sits on it. It is a plinth. She is a monument.", charm=2, strength=1),
        "weaver": _("In one eye, out the other, no pause.", agility=3),
        "dinner": _("Assumes it is a very large dinner. Is not discouraged.", charm=2, strength=1),
        "alley": _("Sleeps in it. It is warm and nobody wants it back.", strength=1, charm=1),
    },
}


def seed_pairs() -> int:
    """How many cells the shipped seed fills."""
    return sum(len(v) for v in SEED.values())


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
    row = SEED.get(emoji, {}).get(cls)
    if row is not None:
        return {"text": row["text"], "stats": dict(row["stats"]), "source": "seed"}
    entry = _catalogue_index().get(emoji)
    if entry is not None:
        written = reaction_flavour.for_cell(entry, cls)
        if written["text"]:
            return {**written, "source": "written"}
    return {"text": "", "stats": {}, "source": "empty"}


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
    pairs.update((emoji, cls) for emoji, cells in SEED.items() for cls in cells)
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
    return guild_emoji_rows(guild) + emoji_catalogue.load()
