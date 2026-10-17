"""
A member's own cats and dogs (the pet cog's collections), for DodoLand.

Their traveller on the roads can be followed by up to :data:`MAX_FOLLOW` of
each, chosen on their town's card. People have up to thousands of pets, so the
card searches them by name (:func:`search`) rather than listing them, and a
choice is only kept if the pet really is theirs (:func:`owned`).
"""

from __future__ import annotations

import re

MAX_FOLLOW = 3
KINDS = ("cat", "dog")


def _whose(owner) -> dict:
    """The pet cog stores an owner as a number in some rows and as text in
    others: match either."""
    text = str(owner)
    return {"$in": [text, int(text)]} if text.isdigit() else text


def _collection(kind: str):
    import config_py

    return config_py.catcollection if kind == "cat" else config_py.dogcollection


def search(owner, q: str = "", limit: int = 24) -> list[dict]:
    """``[{k, n, t, u}]``: the owner's cats and dogs whose name contains ``q``."""
    query: dict = {"owner": _whose(owner)}
    q = str(q or "").strip()[:40]
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    out = []
    for kind in KINDS:
        for row in _collection(kind).find(query, {"name": 1, "type": 1, "url": 1}).limit(limit):
            out.append({"k": kind, "n": str(row.get("name") or ""), "t": str(row.get("type") or ""),
                        "u": str(row.get("url") or "")})
    return out[:limit * 2]


def owned(owner, chosen: list[dict]) -> list[dict]:
    """The chosen ``[{k, n}]`` that really are the owner's, at most
    :data:`MAX_FOLLOW` of each kind, in order."""
    out, count = [], {kind: 0 for kind in KINDS}
    for pet in chosen or []:
        kind, name = pet.get("k"), str(pet.get("n") or "")
        if kind not in KINDS or not name or count[kind] >= MAX_FOLLOW:
            continue
        if _collection(kind).find_one({"owner": _whose(owner), "name": name}) is not None:
            out.append({"k": kind, "n": name})
            count[kind] += 1
    return out


def details(choices: dict) -> dict:
    """``{owner: [{k, n, t, u}]}`` for ``{owner: [{k, n}]}``, one query a kind."""
    out: dict = {}
    for kind in KINDS:
        terms = [{"owner": _whose(owner), "name": {"$in": [p["n"] for p in pets if p.get("k") == kind]}}
                 for owner, pets in choices.items() if any(p.get("k") == kind for p in pets)]
        if not terms:
            continue
        found = {}
        for row in _collection(kind).find({"$or": terms}, {"owner": 1, "name": 1, "type": 1, "url": 1}):
            found.setdefault((str(row.get("owner")), str(row.get("name"))),
                             {"k": kind, "n": str(row.get("name") or ""), "t": str(row.get("type") or ""),
                              "u": str(row.get("url") or "")})
        for owner, pets in choices.items():
            for pet in pets:
                hit = pet.get("k") == kind and found.get((str(owner), pet.get("n")))
                if hit:
                    out.setdefault(str(owner), []).append(hit)
    return out
