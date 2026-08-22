"""
Whether to answer at all — and whether answering needs the model.

Four outcomes, in descending order of how much they cost:

``ENGAGE``
    A real API call. Always the answer when somebody actually addressed her:
    a mention, a ping of a role she has, or a reply to one of her messages.
``SPONTANEOUS``
    An API call nobody asked for. She reads the last few messages and joins a
    live conversation the way a person would. Rare by design and rate-limited
    twice (a probability *and* a cooldown), because the difference between
    charming and infuriating here is entirely frequency.
``REFLEX``
    A canned line from the matched trigger. No API call, no tokens. This is what
    keeps string listeners affordable: a bare "no u" never deserved a model.
``IGNORE``
    Nothing is said. Note that a trigger can match and still land here — the
    caller has already applied its feelings by then, so she noticed, and it
    surfaces in whatever she says next. Silence with a memory is most of what
    makes the character read as a character.

Everything here is arithmetic on in-memory dicts. The router runs on every
message in every guild, so it must never touch the database.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from random import Random
from typing import Optional

from helpers.chat.triggers import Trigger

ENGAGE = "engage"
SPONTANEOUS = "spontaneous"
REFLEX = "reflex"
IGNORE = "ignore"

# Why a message went the way it did, for the debug log. Not user-facing.
R_ADDRESSED = "addressed"
R_TRIGGER = "trigger"
R_NO_MATCH = "no match"
R_CHANCE = "chance"
R_COOLDOWN = "cooldown"
R_CAPPED = "daily cap"
R_QUIET = "channel too quiet"


@dataclass
class RouterTuning:
    """Per-server frequency controls. Every one of these is a panel parameter."""

    ambient_multiplier: float = 1.0
    ambient_cooldown_seconds: float = 90.0
    user_cooldown_seconds: float = 4.0
    daily_cap: int = 0                       # 0 = uncapped

    spontaneous_chance: float = 0.002
    spontaneous_cooldown_seconds: float = 5400.0
    spontaneous_min_messages: int = 5
    spontaneous_min_speakers: int = 2
    context_messages: int = 8


@dataclass
class Decision:
    """What to do about one message."""

    route: str = IGNORE
    trigger: Optional[Trigger] = None
    reason: str = R_NO_MATCH

    @property
    def speaks(self) -> bool:
        return self.route != IGNORE

    @property
    def costs_tokens(self) -> bool:
        return self.route in (ENGAGE, SPONTANEOUS)


class Router:
    """Routing decisions plus the short-term memory they need.

    Holds a per-channel ring of recent messages (for spontaneous context) and the
    cooldown clocks. All of it is deliberately in-process and lost on restart —
    a bot that has forgotten it spoke ten minutes ago is a much smaller problem
    than a database write on every message in every server.
    """

    def __init__(self, *, history: int = 24) -> None:
        self._history = history
        self._recent: dict[int, deque] = {}
        self._channel_spoke: dict[int, float] = {}
        self._channel_unprompted: dict[int, float] = {}
        self._user_spoke: dict[int, float] = {}
        self._calls: dict[tuple, int] = {}

    # ------------------------------------------------------------------ #
    #  Short-term channel memory
    # ------------------------------------------------------------------ #
    def observe(self, channel_id: int, author: str, content: str) -> None:
        """Remember that somebody said something here."""
        if not content:
            return
        ring = self._recent.setdefault(channel_id, deque(maxlen=self._history))
        ring.append((author, content))

    def recent(self, channel_id: int, count: int) -> list[str]:
        """The last ``count`` messages as ``name: text`` lines."""
        ring = self._recent.get(channel_id)
        if not ring or count <= 0:
            return []
        return [f"{author}: {content}" for author, content in list(ring)[-count:]]

    def _speakers(self, channel_id: int, count: int) -> int:
        ring = self._recent.get(channel_id)
        if not ring:
            return 0
        return len({author for author, _ in list(ring)[-count:]})

    def _depth(self, channel_id: int) -> int:
        return len(self._recent.get(channel_id) or ())

    # ------------------------------------------------------------------ #
    #  Budget bookkeeping
    # ------------------------------------------------------------------ #
    def note_spoke(self, channel_id: int, user_id: int, *, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self._channel_spoke[channel_id] = now
        self._user_spoke[user_id] = now

    def note_unprompted(self, channel_id: int, *, now: Optional[float] = None) -> None:
        self._channel_unprompted[channel_id] = now if now is not None else time.time()

    def note_call(self, guild_id: Optional[int], *, now: Optional[float] = None) -> None:
        """Count an API call against today's cap for this guild."""
        self._calls[self._day_key(guild_id, now)] = self.calls_today(guild_id, now=now) + 1

    def calls_today(self, guild_id: Optional[int], *, now: Optional[float] = None) -> int:
        return self._calls.get(self._day_key(guild_id, now), 0)

    @staticmethod
    def _day_key(guild_id: Optional[int], now: Optional[float]) -> tuple:
        now = now if now is not None else time.time()
        return (guild_id, int(now // 86400))

    def _capped(self, guild_id: Optional[int], tuning: RouterTuning, now: float) -> bool:
        return tuning.daily_cap > 0 and self.calls_today(guild_id, now=now) >= tuning.daily_cap

    def _cooling(self, clock: dict, key: int, seconds: float, now: float) -> bool:
        return seconds > 0 and (now - clock.get(key, 0.0)) < seconds

    # ------------------------------------------------------------------ #
    #  The decision
    # ------------------------------------------------------------------ #
    def decide(self, *, addressed: bool, trigger: Optional[Trigger], guild_id: Optional[int],
               channel_id: int, user_id: int, tuning: RouterTuning,
               rng: Optional[Random] = None, now: Optional[float] = None) -> Decision:
        """Route one message. The caller applies the trigger's feelings either
        way — this only decides whether anything is *said*."""
        rng = rng or Random()
        now = now if now is not None else time.time()

        if addressed:
            if self._capped(guild_id, tuning, now):
                return Decision(IGNORE, trigger, R_CAPPED)
            if self._cooling(self._user_spoke, user_id, tuning.user_cooldown_seconds, now):
                return Decision(IGNORE, trigger, R_COOLDOWN)
            return Decision(ENGAGE, trigger, R_ADDRESSED)

        if trigger is not None:
            return self._decide_ambient(trigger, guild_id, channel_id, tuning, rng, now)
        return self._decide_unprompted(guild_id, channel_id, tuning, rng, now)

    def _decide_ambient(self, trigger: Trigger, guild_id: Optional[int], channel_id: int,
                        tuning: RouterTuning, rng: Random, now: float) -> Decision:
        """A string she reacts to, in a message that was not aimed at her."""
        if rng.random() >= trigger.chance * tuning.ambient_multiplier:
            return Decision(IGNORE, trigger, R_CHANCE)
        if self._cooling(self._channel_spoke, channel_id, tuning.ambient_cooldown_seconds, now):
            return Decision(IGNORE, trigger, R_COOLDOWN)
        # A canned line is free, so it is still allowed when the day's budget is
        # gone — that is the whole point of having reflexes.
        if trigger.reflex and rng.random() < trigger.reflex_chance:
            return Decision(REFLEX, trigger, R_TRIGGER)
        if self._capped(guild_id, tuning, now):
            return Decision(REFLEX if trigger.reflex else IGNORE, trigger, R_CAPPED)
        return Decision(ENGAGE, trigger, R_TRIGGER)

    def _decide_unprompted(self, guild_id: Optional[int], channel_id: int,
                           tuning: RouterTuning, rng: Random, now: float) -> Decision:
        """The rare one: joining a conversation nobody invited her to.

        Gated on the channel actually having a conversation in it — several
        recent messages from more than one person — so she interrupts a chat
        rather than talking at somebody thinking out loud alone.
        """
        if tuning.spontaneous_chance <= 0 or rng.random() >= tuning.spontaneous_chance:
            return Decision(IGNORE, None, R_CHANCE)
        if self._depth(channel_id) < tuning.spontaneous_min_messages:
            return Decision(IGNORE, None, R_QUIET)
        if self._speakers(channel_id, tuning.context_messages) < tuning.spontaneous_min_speakers:
            return Decision(IGNORE, None, R_QUIET)
        if self._cooling(self._channel_unprompted, channel_id,
                         tuning.spontaneous_cooldown_seconds, now):
            return Decision(IGNORE, None, R_COOLDOWN)
        if self._cooling(self._channel_spoke, channel_id, tuning.ambient_cooldown_seconds, now):
            return Decision(IGNORE, None, R_COOLDOWN)
        if self._capped(guild_id, tuning, now):
            return Decision(IGNORE, None, R_CAPPED)
        return Decision(SPONTANEOUS, None, R_CHANCE)
