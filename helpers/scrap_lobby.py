"""
Getting cats into a fight: the roster, and the minute before the bell.

A scrap opens with a sign-up window. Anyone may press **Send a cat to fight**,
and the only question that matters is whether they have one ready. Three answers
are possible and each one has to be useful:

* they have a roster, so a cat goes in and the button did what it said;
* they own cats but have never chosen any, so they are told how, *and* offered
  the obvious shortcut of letting the bot pick their best one;
* they own no cats at all, so they are told how to get one.

The second case is the one worth building carefully. Somebody who has just
watched a fight start and pressed a button is not in the mood to go away and
read about roster management, and a wall of instructions there is how a feature
dies. They get one sentence and a button.

Nothing here talks to Discord: it answers *what should happen*, and the cog
turns that into an ephemeral reply.
"""

from __future__ import annotations

import bson

import config_py
from helpers import scrap

# Why a join was refused, or what to offer instead.
READY = "ready"                 # a roster exists; these cats are going in
NO_ROSTER = "no_roster"         # owns cats, has chosen none
NO_CATS = "no_cats"             # owns nothing that can fight
ALREADY_IN = "already_in"       # this cat is already on the sand


def _collections() -> dict:
    """Cats only. It is a cat fight.

    Dogs used to be in here and "pick my best" happily reached into the dog
    collection, which is how a Working Dog ended up on a cat's roster. Dogs get
    thrown *into* a fight as an object; they do not enter one as a fighter.
    """
    return {"cat": config_py.catcollection}


def _roster_collection():
    return config_py.scrap_roster


def owned(owner_id: int) -> list[dict]:
    """Every pet this person could conceivably fight with."""
    pets = []
    for kind, collection in _collections().items():
        for pet in collection.find({"owner": owner_id}):
            pet["kind"] = kind
            pets.append(pet)
    return pets


def total_of(pet: dict) -> int:
    return sum(int(pet.get(attribute, 0) or 0) for attribute in scrap.ATTRIBUTES)


def best_of(pets: list[dict]) -> dict | None:
    """The strongest cat somebody owns, by total.

    Total rather than any single attribute, because the fight itself only reads
    the total — so "your best cat" here means exactly what it means in there.
    Ties break on the name so the answer never changes between two clicks.
    """
    if not pets:
        return None
    return sorted(pets, key=lambda p: (-total_of(p), str(p.get("name", ""))))[0]


def roster(owner_id: int, limit: int = None) -> list[dict]:
    """The cats this person has chosen to fight with, in the order chosen."""
    limit = int(scrap.TUNING["roster_max"] if limit is None else limit)
    row = _roster_collection().find_one({"owner": owner_id})
    idents = (row or {}).get("idents") or []
    by_id = {str(pet["_id"]): pet for pet in owned(owner_id)}
    # A cat that has been given away, deleted, or lost to a pink slip simply
    # falls out of the roster rather than breaking the join.
    return [by_id[i] for i in idents if i in by_id][:limit]


def enrol(owner_id: int, ident: str, limit: int = None) -> dict:
    """Put a cat on the roster, which is what summoning it now does."""
    limit = int(scrap.TUNING["roster_max"] if limit is None else limit)
    ident = str(ident)
    row = _roster_collection().find_one({"owner": owner_id}) or {}
    idents = [i for i in (row.get("idents") or []) if i != ident]
    idents.insert(0, ident)
    dropped = idents[limit:]
    idents = idents[:limit]
    _roster_collection().update_one({"owner": owner_id},
                                    {"$set": {"idents": idents}}, upsert=True)
    return {"idents": idents, "dropped": dropped, "full": len(idents) >= limit}


def release(owner_id: int, ident: str) -> None:
    row = _roster_collection().find_one({"owner": owner_id}) or {}
    idents = [i for i in (row.get("idents") or []) if i != str(ident)]
    _roster_collection().update_one({"owner": owner_id}, {"$set": {"idents": idents}}, upsert=True)


def join(owner_id: int, *, already: list = None, auto: bool = False) -> dict:
    """What happens when somebody presses "send a cat to fight".

    ``auto`` is the shortcut: they had no roster, were offered their best cat,
    and said yes. Returns a ``status`` the cog can turn into either a fighter or
    an ephemeral explanation, plus everything that explanation needs.
    """
    already = {str(i) for i in (already or [])}
    ready = [pet for pet in roster(owner_id) if str(pet["_id"]) not in already]
    if ready:
        return {"status": READY, "cats": ready}

    pets = owned(owner_id)
    if not pets:
        return {"status": NO_CATS, "cats": []}

    if roster(owner_id) and not ready:
        return {"status": ALREADY_IN, "cats": []}

    best = best_of(pets)
    if auto and best is not None:
        enrol(owner_id, str(best["_id"]))
        return {"status": READY, "cats": [best], "auto": True}
    return {"status": NO_ROSTER, "cats": [], "best": best, "owned": len(pets)}


def as_fighter(pet: dict) -> dict:
    """A pet document in the shape the engine wants."""
    fighter = {"name": pet.get("name") or "cat", "ident": str(pet.get("_id") or ""),
               "owner": pet.get("owner")}
    for attribute in scrap.ATTRIBUTES:
        fighter[attribute] = int(pet.get(attribute, 0) or 0)
    return fighter


def explain(result: dict) -> str:
    """The ephemeral reply, in one sentence, for whichever answer came back."""
    status = result["status"]
    if status == NO_CATS:
        return ("You have no cats to send. Claim one with `cat` first, then come back. "
                "The fight will still be going.")
    if status == ALREADY_IN:
        return "Every cat on your roster is already in this fight."
    if status == NO_ROSTER:
        best = result.get("best")
        if best is None:
            return "You have no cats to send."
        return (f"You have {result['owned']} cats and have not picked a fighter. "
                f"Summon one to put it on your roster, or send **{best['name']}**, "
                f"who is the best you have.")
    return "In they go."


def describe_roster(pets: list[dict], limit: int = None) -> str:
    """The roster as a line, for a summon reply or a profile."""
    limit = int(scrap.TUNING["roster_max"] if limit is None else limit)
    if not pets:
        return "Nobody on the roster yet."
    names = ", ".join(f"{pet.get('name')} ({total_of(pet)})" for pet in pets)
    return f"Fighting for you ({len(pets)}/{limit}): {names}"
