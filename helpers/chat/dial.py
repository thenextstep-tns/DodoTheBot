"""
How much Dodo is allowed to be Dodo, this one time.

The failure mode of a character prompt is that adjectives are absolute. Tell a
model "be unhinged" and every reply is maximally unhinged, because there is no
scale in the word. So the prompt never receives an adjective from this module —
it receives a **budget**: how many flourishes she may spend and how many
sentences she gets. Models obey "one flourish, two sentences" almost perfectly
and obey "be zany but not too zany" not at all.

The budget is arithmetic over things that already exist:

* the base allowance for the server (a parameter)
* what the matched trigger is worth
* how close she is to this person — she is louder around friends
* how worn out the current bit is (:mod:`triggers` fatigue)
* whether this is a utility question, which zeroes it: a link is a link

Plus one **rotating obsession** per server, so what is on her mind today is the
same all day and different tomorrow. That is where the sense of an inner life
comes from, and it costs one modulo.

Note there is no sleepiness axis. The old prompt rolled drowsiness per message,
which meant two replies five seconds apart could be "sharp and tired" and then
"very sleepy and rambling" — the single most character-destroying line in the
file. Variation now comes from state, which is continuous, and from the trigger,
which has a reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random
from typing import Optional

from helpers.chat.state import ChatState
from helpers.chat.triggers import Trigger

# A link is never worth a joke on top.
_URL = re.compile(r"https?://", re.IGNORECASE)


@dataclass
class DialTuning:
    """Panel-set numbers for the budget. All per server."""

    spice_base: float = 1.0
    spice_max: int = 3
    spice_jitter: float = 0.25
    close_bonus_at: float = 0.75
    distant_penalty_at: float = 0.25
    fatigue_bite: float = 1.0
    sentences_max: int = 3
    chars_max: int = 240
    obsession_chance: float = 0.2


@dataclass
class Dial:
    """The per-reply budget, and the short lines that express it."""

    spice: int = 1
    sentences: int = 1
    chars: int = 240
    utility: bool = False
    worn: float = 0.0
    obsession: str = ""
    note: str = ""

    def line(self) -> str:
        """The one-line ``dial:`` block that reaches the model.

        The character cap is here because sentence counts alone do not hold — a
        model told "2 sentences" will happily write two very long ones. A number
        of characters is unambiguous and it obeys that.
        """
        parts = [f"{self.spice} flourish{'es' if self.spice != 1 else ''}",
                 f"{self.sentences} sentence{'s' if self.sentences != 1 else ''} max",
                 f"under {self.chars} characters"]
        if self.utility:
            parts.append("this one is a real question: answer it exactly, flourish after")
        if self.worn >= 2:
            parts.append(f"this bit has been pulled {int(self.worn) + 1} times lately and you know it")
        return " | ".join(parts)


def is_utility(text: str, patterns: list[str]) -> bool:
    """Whether this reads as a lookup rather than a conversation.

    Links are always utility. Everything else comes from a per-server list, so a
    server whose members ask about builds and one whose members ask about recipes
    can each teach her what a real question looks like.
    """
    if not text:
        return False
    if _URL.search(text):
        return True
    folded = text.lower()
    return any(pattern.lower() in folded for pattern in patterns if pattern.strip())


def obsession_of(obsessions: list[str], guild_id: Optional[int], rotate_hours: float,
                 now: float) -> str:
    """What is on her mind today on this server.

    Deterministic from the clock, so it holds steady through a conversation and
    has moved by tomorrow — the cheapest possible version of having a day.
    """
    live = [item for item in obsessions if item.strip()]
    if not live or rotate_hours <= 0:
        return ""
    bucket = int(now // (rotate_hours * 3600.0))
    return live[(bucket + (guild_id or 0)) % len(live)]


def compute(state: ChatState, trigger: Optional[Trigger], tuning: DialTuning, *,
            text: str = "", utility_patterns: Optional[list[str]] = None,
            obsessions: Optional[list[str]] = None, obsession_rotate_hours: float = 8.0,
            guild_id: Optional[int] = None, now: float = 0.0,
            rng: Optional[Random] = None, fatigue: float = 0.0) -> Dial:
    """Work out what this reply is allowed to be."""
    rng = rng or Random()
    utility = is_utility(text, utility_patterns or [])

    spice = tuning.spice_base
    if trigger is not None:
        spice += trigger.spice
    if state.closeness >= tuning.close_bonus_at:
        spice += 1
    elif state.closeness <= tuning.distant_penalty_at:
        spice -= 1

    # Wear erodes the *trigger's* bonus and stops there. A bit that has been
    # pulled five times should get a bird who is bored of it — not a bird with no
    # personality at all, which is what happens if fatigue is allowed to eat into
    # the base allowance as well.
    if trigger is not None:
        spice -= min(fatigue * tuning.fatigue_bite, trigger.spice)

    # A little jitter so two identical messages are not two identical replies.
    if tuning.spice_jitter and rng.random() < tuning.spice_jitter:
        spice += rng.choice((-1, 1))

    if utility:
        spice = min(spice, 1)

    spice = int(max(0, min(tuning.spice_max, round(spice))))

    # One sentence is her *normal*. Length is earned by the situation — a
    # tantrum or someone in real trouble gets more room, an ordinary remark does
    # not. The old mapping (1 + spice) made three sentences the common case,
    # which is how you get a paragraph in reply to "what is happening".
    sentences = 1 + (spice >= 2) + (spice >= 3)
    sentences = int(max(1, min(tuning.sentences_max, sentences)))
    chars = int(max(40, tuning.chars_max * sentences / max(1, tuning.sentences_max)))

    obsession = ""
    if not utility and rng.random() < tuning.obsession_chance:
        obsession = obsession_of(obsessions or [], guild_id, obsession_rotate_hours, now)

    return Dial(
        spice=spice,
        sentences=sentences,
        chars=chars,
        utility=utility,
        worn=fatigue,
        obsession=obsession,
        note=trigger.note if trigger is not None else "",
    )
