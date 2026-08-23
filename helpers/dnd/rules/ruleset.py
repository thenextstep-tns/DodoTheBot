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

# --------------------------------------------------------------------------- #
#  Affordances — what a scene physically permits
#
#  The decision engine proposes candidates by intersecting an entity's behaviour
#  packs with these (``docs/dnd/06-DECISION-ENGINE.md`` §5), which is what stops
#  a cornered NPC proposing to flee a sealed room or a bound one proposing to
#  walk away. The list is closed on purpose: a verb no ruleset can grant is a
#  pack that silently never fires, and that is the kind of bug that looks like
#  "the NPCs are boring" rather than like a bug.
#
#  Deliberately about *physical possibility*, not willingness or belief. Whether
#  an NPC would ever attack is the scorer's business; whether they could is this.
# --------------------------------------------------------------------------- #
ATTACK = "attack"
FLEE = "flee"
SPEAK = "speak"
GIVE = "give"
TAKE = "take"
HIDE = "hide"
WAIT = "wait"
USE = "use"
MOVE = "move"

AFFORDANCES = (ATTACK, FLEE, SPEAK, GIVE, TAKE, HIDE, WAIT, USE, MOVE)

AFFORDANCE_LABELS = {
    ATTACK: "Attack", FLEE: "Flee", SPEAK: "Speak", GIVE: "Give", TAKE: "Take",
    HIDE: "Hide", WAIT: "Wait", USE: "Use", MOVE: "Move",
}


@dataclass(frozen=True)
class Presence:
    """One other body in the scene, as the rules layer needs to see it.

    Not an entity: ``rules/`` sits below ``world/`` and must not import the
    entity model, so the caller flattens each occupant to the three facts a
    physical possibility can turn on.
    """

    entity_id: object = None
    kind: str = ""
    carrying: bool = False       # has anything on them worth taking
    reachable: bool = True       # close enough to touch, hit, or hand something to


@dataclass(frozen=True)
class Situation:
    """The scene as a body in it experiences it.

    Everything here is world truth rather than belief, and that is correct: you
    cannot walk through a wall by believing in a door. What an NPC *thinks* is
    in the room belongs to their ``EntityView``, and the two meet in the scorer.
    """

    others: tuple = ()                   # tuple[Presence, ...]
    conditions: tuple = ()               # the actor's own, lowercased by the caller
    carrying: bool = False               # the actor has something on them
    lighting: str = ""                   # free text, as scenes store it
    features: tuple = ()                 # things in the room worth using or taking
    sealed: bool = False                 # no way out at all — a cell, a sinking hold

    @property
    def reachable(self) -> tuple:
        return tuple(p for p in self.others if p.reachable)

    @property
    def alone(self) -> bool:
        return not self.others

    @property
    def anyone_carrying(self) -> bool:
        return any(p.carrying for p in self.reachable)

    def has_condition(self, *words: str) -> bool:
        """Whether any of ``words`` appears in the actor's conditions.

        Substring rather than equality because conditions are free text in one
        ruleset and a closed list in the other, and "badly wounded" should match
        a rule written about ``wounded``.
        """
        return any(word in condition for condition in self.conditions for word in words)

    @property
    def obscured(self) -> bool:
        """Whether the light is on the actor's side."""
        text = self.lighting.lower()
        return any(word in text for word in ("dark", "dim", "gloom", "shadow", "night", "smoke"))


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

    def affordances(self, actor_stats: dict, situation: Situation) -> frozenset:
        """Which of :data:`AFFORDANCES` this situation physically permits.

        Must always include :data:`WAIT`. Doing nothing is the null action the
        decision engine falls back to, and a ruleset that can return an empty set
        gives it nothing to choose from.
        """


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
