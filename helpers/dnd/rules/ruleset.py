"""
Ruleset protocol and registry.

A ruleset is **data plus a small resolver**, not code scattered through the
engine. The old cog hardcoded one stat array (``STR 15, DEX 14, CON 13, …``) for
every character anyone ever made; that block was identical whether you rolled a
barbarian or a wizard, which is the mistake this layer exists to prevent.

Rulesets deal in **stat dictionaries, not entities.** ``rules/`` sits below
``world/`` in the layering (``docs/dnd/01-ARCHITECTURE.md`` §1), so it must not
import the entity model — it receives the ``stats`` blob and the small amount of
context a resolution needs. That constraint is what lets two rulesets coexist in
one collection without either knowing about the other.

Add a ruleset by implementing :class:`Ruleset` and calling :func:`register`. If
that ever requires touching a file outside this package, the abstraction has
failed and the fix belongs here rather than at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Protocol, runtime_checkable

from helpers.dnd.rules.dice import Roll

# Degrees of success, coarsest first. Every ruleset maps its own resolution onto
# these four so the layers above can reason about outcomes without knowing which
# ruleset produced them.
FAIL = "fail"
COST = "cost"          # succeeded, but it cost something
SUCCESS = "success"
TRIUMPH = "triumph"

DEGREES = (FAIL, COST, SUCCESS, TRIUMPH)


@dataclass(frozen=True)
class Action:
    """What someone is trying to do. Produced by the intent parser (P4) or by a
    command argument (P0), validated before it reaches a resolver."""

    kind: str = "check"              # check | attack | save | contest
    approach: str = ""               # which stat/skill/approach is being used
    text: str = ""                   # the player's own words, kept for the log
    target_id: object | None = None
    difficulty: int | None = None    # None → the ruleset's default DC


@dataclass(frozen=True)
class Outcome:
    """The result of resolving an action. Carries its working so the event log
    can explain itself and the null renderer has something to say."""

    degree: str
    roll: Roll | None
    dc: int
    summary: str                     # deterministic one-liner — the P0 narration
    detail: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.degree in (COST, SUCCESS, TRIUMPH)


@runtime_checkable
class Ruleset(Protocol):
    """What every ruleset must provide."""

    key: str
    label: str

    def stat_schema(self) -> dict:
        """Describes the shape of ``entity.stats`` for validation and the panel."""

    def blank_sheet(self, concept: dict, rng: Random) -> dict:
        """A fresh, *differentiated* stat block from a character concept.

        ``concept`` carries whatever the player supplied — ``name``, ``role``,
        ``species``, free text. Two different concepts must not produce the same
        numbers; that was the old cog's defining bug.
        """

    def derive(self, stats: dict) -> dict:
        """Values computed from the stats: modifiers, defences, initiative."""

    def approaches(self, stats: dict) -> list[str]:
        """The stat/skill names a check may be made with, for command choices."""

    def resolve(self, action: Action, actor_stats: dict, target_stats: dict | None, rng: Random) -> Outcome:
        """Resolve an action. Pure and seeded — same inputs, same outcome."""

    def sheet_fields(self, stats: dict) -> list[tuple[str, str]]:
        """``(label, value)`` pairs for rendering a character sheet."""


# --------------------------------------------------------------------------- #
#  Registry
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, Ruleset] = {}


def register(ruleset: Ruleset) -> Ruleset:
    """Register a ruleset under its key. Last registration wins, so reloading a
    module cleanly re-points the key at the new implementation."""
    _REGISTRY[ruleset.key] = ruleset
    return ruleset


def get(key: str) -> Ruleset:
    """The ruleset for a key, falling back to freeform.

    A campaign whose ruleset key has gone missing (a bad import, a ruleset
    removed between releases) must stay *playable* rather than raising on every
    interaction — freeform can resolve anything, so it is the safe floor.
    """
    if key in _REGISTRY:
        return _REGISTRY[key]
    return _REGISTRY["freeform"]


def keys() -> list[str]:
    return sorted(_REGISTRY)


def all_rulesets() -> list[Ruleset]:
    return [_REGISTRY[k] for k in keys()]
