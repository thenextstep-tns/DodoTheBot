"""
Breadth: how much of the server's living conversation a person takes part in.

Influence rewards it on top of town power. A **lively room** for somebody is a
channel where at least ``others`` *other* people wrote in the window, that the
person can write in, and that still exists. Their **breadth** is the share of
those rooms they wrote in themselves. Somebody who talks in every lively room
they can is woven through the whole server, which is what an area of influence
is meant to show; somebody with the same points from one channel is not.

Pure: day rows in, two callbacks for what only Discord knows (which room a
channel id belongs to, and whether a person may write there), shares out. The
settings are read by ``web/dodoland/influence_api.py``.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

# The act that is "wrote a message here". Every message (of any length the
# server counts) records one, replies and thread posts included.
WRITTEN = ("message",)


def talkers(rows: Iterable[dict], *, acts: Iterable[str] = WRITTEN,
            room: Callable[[int], Optional[int]] = lambda c: c) -> dict[int, dict[int, int]]:
    """``{room: {user: messages}}`` from day rows' per-channel split.

    ``room`` folds a channel id into the room it belongs to (a forum post into
    its forum) or ``None`` for one that no longer exists. A day's count is at
    least one wherever the act was recorded, capped or not: past a daily cap
    the act still happened, it just scored nothing.
    """
    wanted = tuple(acts)
    out: dict[int, dict[int, int]] = {}
    folded: dict[int, Optional[int]] = {}
    for row in rows:
        user = int(row.get("user_id") or 0)
        if not user:
            continue
        for cid, counts in (row.get("channels") or {}).items():
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            if cid not in folded:
                folded[cid] = room(cid)
            where = folded[cid]
            if where is None or not isinstance(counts, dict):
                continue
            n = sum(max(1, int(counts[a] or 0)) for a in wanted if a in counts)
            if n:
                people = out.setdefault(where, {})
                people[user] = people.get(user, 0) + n
    return out


def share(user_id: int, rooms: dict[int, dict[int, int]], *, others: int = 2,
          min_messages: int = 1, min_rooms: int = 3,
          may_write: Callable[[int, int], bool] = lambda u, r: True) -> dict:
    """One person's breadth: ``{joined, open, share}``.

    ``open`` is the lively rooms they could write in, ``joined`` how many of
    those they wrote at least ``min_messages`` in. Fewer than ``min_rooms``
    lively rooms is no breadth at all: on a server of two channels everybody
    would otherwise be "everywhere".
    """
    user_id = int(user_id)
    open_, joined = 0, 0
    for where, people in rooms.items():
        count = len(people) - (1 if user_id in people else 0)
        if count < max(0, others) or not may_write(user_id, where):
            continue
        open_ += 1
        if people.get(user_id, 0) >= max(1, min_messages):
            joined += 1
    value = joined / open_ if open_ >= max(1, min_rooms) else 0.0
    return {"joined": joined, "open": open_, "share": value}


def boost(value: float, bonus: float, curve: float = 1.0) -> float:
    """What town power is multiplied by, for reach, at a breadth of ``value``."""
    if bonus <= 0 or value <= 0:
        return 1.0
    return 1.0 + float(bonus) * min(1.0, float(value)) ** max(0.05, float(curve))
