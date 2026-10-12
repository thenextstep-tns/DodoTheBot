"""
Voice session bookkeeping — who was in a channel, with whom, and for how long.

Kept out of the cog and free of any Discord type so it can be tested against a
clock rather than against a gateway. The cog feeds it three facts (somebody
joined, somebody left, what time it is) and gets back the acts to record.

Two rules decide everything here:

**Alone earns nothing.** A voice channel with one person in it is not a social
act however many hours it lasts, and an idle mic overnight is the most obvious
farm available. A session only pays out if somebody else was actually in the
room at some point during it.

**Company is measured in overlap, not in presence.** Two people who were both
in a channel today but never at the same time did not share anything. Pairs are
credited from the intersection of their sessions, and only past a minimum, so
walking through a channel does not make you everybody's friend.

Sessions live in memory and are lost on restart. That is a deliberate trade:
persisting them would mean a write on every voice state change for a metric
weighted at one point a minute. A restart costs everybody the tail of their
current call and nothing else.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Session:
    """One person's stay in one channel.

    Co-presence is accumulated rather than inferred from a start time, because
    the same two people can overlap more than once in one stay and because the
    person who stays longest must not be credited for the time after everybody
    else left. ``shared`` is closed seconds; ``since`` is the currently open
    overlap, if any.
    """

    user_id: int
    channel_id: int
    joined_at: float
    shared: dict[int, float] = field(default_factory=dict)
    since: dict[int, float] = field(default_factory=dict)

    def open_with(self, other: int, at: float) -> None:
        self.since.setdefault(other, at)

    def close_with(self, other: int, at: float) -> None:
        started = self.since.pop(other, None)
        if started is not None and at > started:
            self.shared[other] = self.shared.get(other, 0.0) + (at - started)

    def close_all(self, at: float) -> None:
        for other in list(self.since):
            self.close_with(other, at)


@dataclass(frozen=True)
class VoiceCredit:
    """What one finished session earned. ``partners`` are the shared minutes."""

    user_id: int
    channel_id: int
    minutes: int
    partners: dict[int, int]


class VoiceTracker:
    """In-memory voice sessions for every guild the bot can see.

    One instance, hung off the cog. Not thread-safe and does not need to be:
    every call arrives on the event loop.
    """

    def __init__(self) -> None:
        # (guild_id, user_id) -> session
        self._sessions: dict[tuple[int, int], _Session] = {}
        # (guild_id, channel_id) -> {user_id}
        self._rooms: dict[tuple[int, int], set[int]] = {}

    # ------------------------------------------------------------------ #
    #  Movement
    # ------------------------------------------------------------------ #
    def join(self, guild_id: int, user_id: int, channel_id: int,
             now: Optional[float] = None) -> None:
        """Somebody entered a voice channel."""
        moment = now if now is not None else time.time()
        guild_id, user_id, channel_id = int(guild_id), int(user_id), int(channel_id)
        room = self._rooms.setdefault((guild_id, channel_id), set())

        session = _Session(user_id=user_id, channel_id=channel_id, joined_at=moment)
        # Everyone already here starts overlapping with the arrival now, and the
        # arrival with them. Opened on both sides so that whoever leaves first
        # closes it for both and neither is credited past the other's departure.
        for other in room:
            session.open_with(other, moment)
            existing = self._sessions.get((guild_id, other))
            if existing is not None:
                existing.open_with(user_id, moment)

        room.add(user_id)
        self._sessions[(guild_id, user_id)] = session

    def leave(self, guild_id: int, user_id: int,
              now: Optional[float] = None) -> Optional[VoiceCredit]:
        """Somebody left. Returns what the finished session earned, if anything."""
        moment = now if now is not None else time.time()
        guild_id, user_id = int(guild_id), int(user_id)
        session = self._sessions.pop((guild_id, user_id), None)
        if session is None:
            return None

        room = self._rooms.get((guild_id, session.channel_id))
        if room is not None:
            room.discard(user_id)
            if not room:
                self._rooms.pop((guild_id, session.channel_id), None)

        # Close this stay on both sides, so whoever is left behind stops
        # accruing shared time with somebody who has gone.
        session.close_all(moment)
        for other in room or ():
            existing = self._sessions.get((guild_id, other))
            if existing is not None:
                existing.close_with(user_id, moment)

        partners = {other: int(seconds // 60) for other, seconds in session.shared.items()}
        # Alone is worth nothing however long it lasts, so the minutes credited
        # are the longest stretch spent with somebody, not the time in the room.
        with_company = max(partners.values(), default=0)
        return VoiceCredit(
            user_id=user_id, channel_id=session.channel_id,
            minutes=with_company,
            partners={other: shared for other, shared in partners.items() if shared > 0},
        )

    # ------------------------------------------------------------------ #
    #  Housekeeping
    # ------------------------------------------------------------------ #
    def occupants(self, guild_id: int, channel_id: int) -> set[int]:
        return set(self._rooms.get((int(guild_id), int(channel_id)), ()))

    def active(self) -> int:
        """How many sessions are open. For the panel's diagnostics."""
        return len(self._sessions)

    def drop_guild(self, guild_id: int) -> None:
        """Forget a guild's sessions, e.g. on being removed from it."""
        guild_id = int(guild_id)
        for key in [k for k in self._sessions if k[0] == guild_id]:
            self._sessions.pop(key, None)
        for key in [k for k in self._rooms if k[0] == guild_id]:
            self._rooms.pop(key, None)
