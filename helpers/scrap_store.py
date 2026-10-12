"""
Writing a finished scrap back to the pets.

The engine never touches the database — it hands back an ``outcome`` and this
applies it. Two things are permanent, and only two:

* the record, ``fightswon`` / ``fightslost``, which has existed on every pet
  since the beginning and has never once been incremented;
* the spoils, where each loser gives up a point of each of its two governing
  attributes and a winner takes those same two.

Everything an object did during the fight is temporary and is simply dropped.

The spoils are the only way a cat's *class* can move, since a class is its two
highest attributes: lose enough and the thing you were is taken off you. The gym
is the way back, which is what the gym is now for.
"""

from __future__ import annotations

import bson

import config_py
from helpers import scrap

COLLECTIONS = ("cat", "dog", "waifu")


def _collections():
    return {"cat": config_py.catcollection, "dog": config_py.dogcollection,
            "waifu": config_py.waifucollection}


def _find(ident):
    """The collection and document for a pet id, wherever it lives."""
    try:
        object_id = bson.ObjectId(ident)
    except (bson.errors.InvalidId, TypeError):
        return None, None
    for collection in _collections().values():
        doc = collection.find_one({"_id": object_id})
        if doc is not None:
            return collection, doc
    return None, None


def apply_outcome(outcome: dict, *, floor: int = None) -> dict:
    """Write a finished fight's records and spoils. Returns what it changed.

    Every write is clamped at the stat floor, so a cat that keeps losing gets
    weak but never reaches zero and never goes negative — a pet with a negative
    attribute would classify strangely and fight like nothing at all.
    """
    floor = int(scrap.TUNING["stat_floor"] if floor is None else floor)
    changed = {"records": 0, "transfers": 0, "missing": []}

    for record in outcome.get("records") or []:
        collection, doc = _find(record.get("ident"))
        if doc is None:
            changed["missing"].append(record.get("name"))
            continue
        field = "fightswon" if record["won"] else "fightslost"
        collection.update_one({"_id": doc["_id"]}, {"$inc": {field: 1}})
        changed["records"] += 1

    for transfer in outcome.get("transfers") or []:
        amount = int(transfer.get("amount", 1))
        attributes = [a for a in transfer.get("attributes", []) if a in scrap.ATTRIBUTES]
        if not attributes or amount <= 0:
            continue

        loser_col, loser = _find(transfer.get("from_ident"))
        winner_col, winner = _find(transfer.get("to_ident"))

        # One half may be absent when a borrowed cat was involved: it fights but
        # nothing is at stake for it, so the other side still settles up alone.
        borrowed = transfer.get("borrowed")
        if not borrowed and (loser is None or winner is None):
            changed["missing"].append(transfer.get("from") if loser is None else transfer.get("to"))
            continue
        if loser is None and winner is None:
            continue

        # Take only what the loser can actually give. A cat already at the floor
        # has nothing left to lose, and the winner must not be paid for it.
        if loser is not None:
            taken = {}
            for attribute in attributes:
                have = int(loser.get(attribute, 0) or 0)
                give = max(0, min(amount, have - floor))
                if give:
                    taken[attribute] = give
            if not taken:
                continue
        else:
            # Nobody lost anything, so the winner collects the flat amount.
            taken = {attribute: amount for attribute in attributes}

        if loser is not None:
            loser_col.update_one({"_id": loser["_id"]},
                                 {"$inc": {a: -v for a, v in taken.items()}})
        if winner is not None:
            winner_col.update_one({"_id": winner["_id"]}, {"$inc": dict(taken)})
        changed["transfers"] += 1

    return changed


def describe(outcome: dict) -> list[str]:
    """The spoils in words, for the end-of-fight embed."""
    lines = []
    for transfer in outcome.get("transfers") or []:
        attrs = ", ".join(scrap.ATTR_SHORT[a] for a in transfer["attributes"]
                          if a in scrap.ATTR_SHORT)
        if transfer.get("to"):
            lines.append(f"{transfer['to']} takes {attrs} off {transfer['from']}.")
        else:
            lines.append(f"{transfer['from']} loses {attrs} to nobody in particular.")
    return lines
