"""
The ``freeform`` ruleset — narrative resolution, no system mastery required.

Four approaches rated −1…+3, one 2d6 ladder for everything:

    ≤ 6   fail        it goes wrong
    7-9   cost        you get it, but it costs you
    10-11 success     clean
    12+   triumph     and something extra

This exists to reach playable first. The differentiator of this product is the
minds — memory, belief, decision — and those need a body to inhabit long before
they need an action economy. A table can play a whole campaign on this ladder,
and it means P2 and P3 can be tested without waiting on a rules engine.

The "cost" band is what makes the ladder worth using: a system whose middle
result is *yes, but* generates story on its own, which is exactly what a
simulation with opinionated NPCs wants to be fed.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.rules import dice
from helpers.dnd.rules import ruleset
from helpers.dnd.rules.ruleset import (
    COST,
    FAIL,
    SUCCESS,
    TRIUMPH,
    Action,
    Outcome,
    register,
)

# The four approaches. Deliberately about *how* you act rather than what you are,
# so any concept can use any of them and no build is locked out of a scene.
APPROACHES = ("force", "finesse", "wits", "presence")

APPROACH_LABELS = {
    "force": "Force",
    "finesse": "Finesse",
    "wits": "Wits",
    "presence": "Presence",
}

# Rated −1…+3. One strength, one weakness, two middling — enough to feel like a
# character, few enough to pick in a modal without a wiki open.
STANDARD_SPREAD = (2, 1, 0, -1)

DEFAULT_DC = 7

# Conditions a GM might actually type, rather than a system's closed list. The
# first group takes everything away, the second only takes away leaving.
INCAPACITATED_WORDS = (
    "unconscious", "out cold", "asleep", "sleeping", "paralys", "paraly",
    "petrified", "stunned", "senseless", "comatose", "dead",
)
PINNED_WORDS = (
    "bound", "tied", "chained", "pinned", "grappled", "restrained", "trapped",
    "held fast", "stuck",
)

# Keywords that pull a concept toward an approach, so "a stubborn dockhand" and
# "a sly archivist" don't come out identical. Matched against the whole concept
# text; unmatched concepts fall back to a seeded shuffle, which is still
# differentiated because the seed differs per character.
_CONCEPT_HINTS = {
    "force": ("warrior", "fighter", "barbarian", "soldier", "knight", "brute", "dockhand",
              "smith", "guard", "wrestler", "orc", "dwarf"),
    "finesse": ("rogue", "thief", "ranger", "scout", "acrobat", "duelist", "assassin",
                "hunter", "sailor", "elf", "halfling"),
    "wits": ("wizard", "scholar", "archivist", "artificer", "alchemist", "detective",
             "engineer", "sage", "gnome", "librarian"),
    "presence": ("bard", "noble", "priest", "cleric", "paladin", "merchant", "diplomat",
                 "warlock", "sorcerer", "captain", "tiefling"),
}


class Freeform:
    """Narrative ruleset. Stateless — all methods are pure given their inputs."""

    key = "freeform"
    label = "Freeform (narrative)"

    def stat_schema(self) -> dict:
        return {
            "approaches": {
                "type": "object",
                "keys": list(APPROACHES),
                "value_range": [-1, 3],
            },
            "harm": {"type": "int", "range": [0, 4]},
        }

    def blank_sheet(self, concept: dict, rng: Random) -> dict:
        """Assign the spread, biased by the concept so two characters differ."""
        text = " ".join(
            str(concept.get(field, "")) for field in ("role", "species", "name", "text")
        ).lower()

        ranked = sorted(
            APPROACHES,
            key=lambda approach: (
                # Negative so hinted approaches sort first; the rng term breaks
                # ties and orders everything when nothing matched at all.
                -sum(1 for word in _CONCEPT_HINTS[approach] if word in text),
                rng.random(),
            ),
        )
        return {
            "approaches": {approach: STANDARD_SPREAD[i] for i, approach in enumerate(ranked)},
            "harm": 0,
        }

    def derive(self, stats: dict) -> dict:
        approaches = stats.get("approaches", {})
        # Harm is a condition track, not hit points: it subtracts from everything
        # you try, so being hurt makes you worse at the whole world rather than
        # just closer to a number that ends you.
        return {
            "best": max(approaches, key=lambda a: approaches.get(a, 0), default=""),
            "harm_penalty": -int(stats.get("harm", 0)),
        }

    def approaches(self, stats: dict) -> list[str]:
        return list(APPROACHES)

    def affordances(self, actor_stats: dict, situation) -> frozenset:
        """What the fiction allows. Permissive by temperament.

        Freeform has no condition list to consult, so it reads the words a GM
        actually types. ``"bound to a chair"`` stops you leaving; ``"out cold"``
        stops everything. The matching is deliberately generous — a ruleset whose
        whole promise is that you can write what you like should not require you
        to write it in its vocabulary.
        """
        if situation.has_condition(*INCAPACITATED_WORDS):
            return frozenset({ruleset.WAIT})

        allowed = {ruleset.WAIT}
        pinned = situation.has_condition(*PINNED_WORDS)

        if not pinned:
            allowed.add(ruleset.MOVE)
            if not situation.sealed:
                allowed.add(ruleset.FLEE)
            # Hiding wants somewhere to do it: the dark, or something to get
            # behind. Being watched by half the room is the scorer's problem.
            if situation.obscured or situation.features:
                allowed.add(ruleset.HIDE)

        if situation.others:
            allowed.add(ruleset.SPEAK)
        if situation.reachable:
            allowed.add(ruleset.ATTACK)
            if situation.carrying:
                allowed.add(ruleset.GIVE)
        if situation.anyone_carrying or situation.features:
            allowed.add(ruleset.TAKE)
        if situation.carrying or situation.features:
            allowed.add(ruleset.USE)

        return frozenset(allowed)

    def resolve(
        self, action: Action, actor_stats: dict, target_stats: dict | None, rng: Random
    ) -> Outcome:
        approach = action.approach if action.approach in APPROACHES else self.derive(actor_stats)["best"]
        rating = int(actor_stats.get("approaches", {}).get(approach, 0))
        penalty = self.derive(actor_stats)["harm_penalty"]
        dc = action.difficulty if action.difficulty is not None else DEFAULT_DC

        spec = dice.DiceSpec(count=2, sides=6, modifier=rating + penalty)
        result = dice.roll(spec, rng)

        if result.total <= dc - 1:
            degree = FAIL
        elif result.total <= dc + 2:
            degree = COST
        elif result.total <= dc + 4:
            degree = SUCCESS
        else:
            degree = TRIUMPH

        return Outcome(
            degree=degree,
            roll=result,
            dc=dc,
            summary=_SUMMARIES[degree].format(approach=APPROACH_LABELS.get(approach, approach)),
            detail={"approach": approach, "rating": rating, "harm_penalty": penalty},
        )

    def sheet_fields(self, stats: dict) -> list[tuple[str, str]]:
        approaches = stats.get("approaches", {})
        fields = [
            (APPROACH_LABELS[a], f"{approaches.get(a, 0):+d}") for a in APPROACHES
        ]
        harm = int(stats.get("harm", 0))
        fields.append(("Harm", "—" if harm == 0 else "▰" * harm + "▱" * (4 - harm)))
        return fields


# Deterministic narration for the null renderer. These are *mechanical*
# descriptions, not prose — a model dresses them up later, and until then they
# are still honest about what happened.
_SUMMARIES = {
    FAIL: "{approach} isn't enough — it goes wrong.",
    COST: "{approach} gets there, but it costs something.",
    SUCCESS: "{approach} carries it off cleanly.",
    TRIUMPH: "{approach} works better than anyone expected.",
}


freeform = register(Freeform())
