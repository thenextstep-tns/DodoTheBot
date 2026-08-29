"""
Dice grammar and rolling.

The old DnD cog matched ``(\\d+)d(\\d+)`` and printed the result to whoever
pressed the button; nothing ever consumed it. Here a roll is a value object that
resolution actually depends on, so it has to carry its parts (every die face, the
ones that were dropped, the modifier) and it has to be **seeded** — the whole
simulation is replayable, and a roll that reached for the global ``random`` module
would be the one thing that isn't.

Grammar::

    2d6            two six-sided dice
    1d20+5         with a flat modifier (+ and - may be chained: 2d6+1-2)
    4d6kh3         keep the highest 3          (kl3 keeps the lowest)
    2d20dh1        drop the highest 1          (dl1 drops the lowest)
    1d20adv        advantage    — sugar for 2d20kh1
    1d20dis        disadvantage — sugar for 2d20kl1
    d20            count defaults to 1
    6              a bare number is a constant

Parsing never raises on bad input: it returns ``None`` so the caller can say
something friendly. It raises only for limits (``DiceLimitError``), because
"20000d1000" is a different kind of wrong from "banana" and deserves a different
message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random

# Dice notation, whole-string. Kept as one expression because the parts are
# positional: count, sides, an optional keep/drop clause, adv/dis sugar, then any
# number of flat modifiers.
_DICE_RE = re.compile(
    r"""
    ^\s*
    (?P<count>\d*)                      # 2   (blank = 1)
    d
    (?P<sides>\d+)                      # 20
    (?:(?P<kd>kh|kl|dh|dl)(?P<kdn>\d+))?   # kh3 / dl1
    (?P<vantage>adv|dis)?               # advantage sugar
    (?P<mods>(?:\s*[+-]\s*\d+)*)        # +5 -1 +2
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

_CONST_RE = re.compile(r"^\s*(?P<sign>[+-]?)\s*(?P<value>\d+)\s*$")
_MOD_RE = re.compile(r"([+-])\s*(\d+)")

# Ceilings that apply before any per-guild limit, so a parse can never allocate
# an absurd list even if a guild sets its parameters foolishly.
HARD_MAX_DICE = 1000
HARD_MAX_SIDES = 10_000


class DiceLimitError(ValueError):
    """A syntactically valid roll that asks for more dice than is allowed."""

    def __init__(self, max_dice: int, max_sides: int) -> None:
        super().__init__(f"roll exceeds {max_dice}d{max_sides}")
        self.max_dice = max_dice
        self.max_sides = max_sides


@dataclass(frozen=True)
class DiceSpec:
    """A parsed roll expression. Pure data — rolling it needs an RNG."""

    count: int
    sides: int
    modifier: int = 0
    keep: int | None = None          # how many dice survive
    keep_high: bool = True           # …taken from the top or the bottom
    constant: bool = False           # a bare number, no dice at all

    def __str__(self) -> str:
        if self.constant:
            return str(self.modifier)
        text = f"{self.count}d{self.sides}"
        if self.keep is not None and self.keep != self.count:
            text += f"{'kh' if self.keep_high else 'kl'}{self.keep}"
        if self.modifier:
            text += f"{self.modifier:+d}"
        return text


@dataclass(frozen=True)
class Roll:
    """The outcome of rolling a :class:`DiceSpec`, with its working shown."""

    spec: DiceSpec
    faces: tuple[int, ...] = ()      # every die, in the order thrown
    kept: tuple[int, ...] = ()       # those that counted
    total: int = 0

    @property
    def dropped(self) -> tuple[int, ...]:
        """Faces that were rolled but discarded by a keep/drop clause."""
        remaining = list(self.kept)
        out: list[int] = []
        for face in self.faces:
            if face in remaining:
                remaining.remove(face)
            else:
                out.append(face)
        return tuple(out)

    def breakdown(self) -> str:
        """Human-readable working, e.g. ``[5, ~~2~~, 6] +3``."""
        if self.spec.constant:
            return str(self.total)
        dropped = list(self.dropped)
        parts: list[str] = []
        for face in self.faces:
            if face in dropped:
                dropped.remove(face)
                parts.append(f"~~{face}~~")
            else:
                parts.append(str(face))
        text = f"[{', '.join(parts)}]"
        if self.spec.modifier:
            text += f" {self.spec.modifier:+d}"
        return text


def parse(expression: str, *, max_dice: int = HARD_MAX_DICE, max_sides: int = HARD_MAX_SIDES) -> DiceSpec | None:
    """Parse a roll expression.

    Returns ``None`` for anything unreadable, so callers can offer help rather
    than swallow a traceback. Raises :class:`DiceLimitError` when the expression
    parses but asks for too much.
    """
    if not expression:
        return None

    constant = _CONST_RE.match(expression)
    if constant:
        value = int(constant.group("value"))
        if constant.group("sign") == "-":
            value = -value
        return DiceSpec(count=0, sides=0, modifier=value, constant=True)

    match = _DICE_RE.match(expression)
    if not match:
        return None

    count = int(match.group("count") or 1)
    sides = int(match.group("sides"))
    if count < 1 or sides < 1:
        return None

    keep: int | None = None
    keep_high = True

    # adv/dis is sugar, and it is applied first so an explicit kh/kl in the same
    # expression wins — "1d20adv kh1" is contradictory, and the explicit clause
    # is the more deliberate of the two.
    vantage = (match.group("vantage") or "").lower()
    if vantage:
        count = max(count, 2)
        keep, keep_high = 1, vantage == "adv"

    clause = (match.group("kd") or "").lower()
    if clause:
        number = int(match.group("kdn"))
        if number < 1:
            return None
        if clause in ("kh", "kl"):
            keep, keep_high = min(number, count), clause == "kh"
        else:  # dh / dl — expressed as "keep the rest from the other end"
            if number >= count:
                return None
            keep, keep_high = count - number, clause == "dl"

    modifier = sum(int(f"{sign}{value}") for sign, value in _MOD_RE.findall(match.group("mods") or ""))

    effective_max_dice = min(max_dice, HARD_MAX_DICE)
    effective_max_sides = min(max_sides, HARD_MAX_SIDES)
    if count > effective_max_dice or sides > effective_max_sides:
        raise DiceLimitError(effective_max_dice, effective_max_sides)

    return DiceSpec(count=count, sides=sides, modifier=modifier, keep=keep, keep_high=keep_high)


def roll(spec: DiceSpec, rng: Random) -> Roll:
    """Roll a parsed spec with an explicit RNG.

    The RNG is a parameter, never module-level state: replaying a campaign has to
    reproduce every roll exactly (``docs/dnd/01-ARCHITECTURE.md`` §3).
    """
    if spec.constant:
        return Roll(spec=spec, total=spec.modifier)

    faces = tuple(rng.randint(1, spec.sides) for _ in range(spec.count))
    if spec.keep is None or spec.keep >= spec.count:
        kept = faces
    else:
        ordered = sorted(faces, reverse=spec.keep_high)
        kept = tuple(ordered[: spec.keep])
    return Roll(spec=spec, faces=faces, kept=kept, total=sum(kept) + spec.modifier)


def roll_expression(
    expression: str, rng: Random, *, max_dice: int = HARD_MAX_DICE, max_sides: int = HARD_MAX_SIDES
) -> Roll | None:
    """Parse and roll in one step. ``None`` when the expression is unreadable."""
    spec = parse(expression, max_dice=max_dice, max_sides=max_sides)
    return None if spec is None else roll(spec, rng)
