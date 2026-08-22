"""
What Dodo just did, and why — the part of the system you can otherwise only infer.

Everything interesting about the chat cog happens invisibly. A trigger matches
and she says nothing; a roll comes up short; a cooldown swallows a reply; the
daily cap stops a call. From outside, all of that looks identical to the feature
being switched off, which makes tuning the numbers guesswork — you change a
reply chance from 0.3 to 0.15 and have no way of telling whether it did anything.

So every decision is recorded here with the reason attached, and the panel shows
the last few hundred. Then "she interrupts too much" stops being a feeling and
becomes a row you can point at.

**In memory, per guild, and lost on restart.** The bot serves its own panel from
the same process, so a ring buffer is all this needs, and the alternative — a
database write on every message in every server — would cost more than the
feature it is describing.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

# What she did about a message. These are the router's routes plus the two
# outcomes only the cog knows about.
SPOKE = "spoke"            # a model reply went out
CANNED = "canned"          # a free line went out
SILENT = "silent"          # noticed, said nothing
JOINED = "joined"          # walked into a conversation uninvited
ABSTAINED = "abstained"    # joined in and then decided it had nothing to add
FAILED = "failed"          # the model call errored

# How each outcome reads in the panel, and the colour class it gets.
OUTCOMES = {
    SPOKE: ("replied", "ok"),
    CANNED: ("canned line", "ok"),
    SILENT: ("said nothing", "muted"),
    JOINED: ("joined in", "warn"),
    ABSTAINED: ("nothing to add", "muted"),
    FAILED: ("failed", "bad"),
}

MAX_TEXT = 140


class ChatActivity:
    """Recent chat decisions per guild. ``bot.chat_activity``."""

    def __init__(self, *, keep: int = 300) -> None:
        self._keep = keep
        self._log: dict[Optional[int], deque] = {}
        self._fires: dict[tuple, int] = {}

    def record(self, guild_id: Optional[int], *, channel: str, author: str, text: str,
               trigger: str = "", outcome: str = SILENT, reason: str = "",
               said: str = "", spice: Optional[int] = None,
               now: Optional[float] = None) -> None:
        """Note one decision. Called for anything that matched or spoke — a
        message that did neither is not evidence of anything."""
        ring = self._log.setdefault(guild_id, deque(maxlen=self._keep))
        ring.append({
            "at": now if now is not None else time.time(),
            "channel": channel,
            "author": author,
            "text": _clip(text),
            "trigger": trigger,
            "outcome": outcome,
            "reason": reason,
            "said": _clip(said),
            "spice": spice,
        })
        if trigger:
            key = (guild_id, trigger)
            self._fires[key] = self._fires.get(key, 0) + 1

    def recent(self, guild_id: Optional[int], limit: int = 100) -> list[dict]:
        """Newest first, because that is the one you are looking for."""
        ring = self._log.get(guild_id)
        return list(reversed(list(ring)[-limit:])) if ring else []

    def fires(self, guild_id: Optional[int]) -> dict[str, int]:
        """How many times each trigger has matched since the bot last started."""
        return {name: count for (gid, name), count in self._fires.items() if gid == guild_id}

    def counts(self, guild_id: Optional[int]) -> dict[str, int]:
        """How the decisions broke down, for the summary line."""
        totals: dict[str, int] = {}
        for entry in self._log.get(guild_id) or ():
            totals[entry["outcome"]] = totals.get(entry["outcome"], 0) + 1
        return totals


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text[:MAX_TEXT] + "…" if len(text) > MAX_TEXT else text
