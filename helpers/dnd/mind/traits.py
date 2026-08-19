"""
Traits and inheritance — who someone is, before anything happens to them.

Numeric axes rather than tags, because the decision engine (P3) multiplies them.
Ten axes total, and that is a deliberate ceiling: enough for NPCs who feel
distinct, few enough that a GM can read a sheet and predict behaviour. More axes
make the utility weights unreadable and the NPCs mushier, not richer.

**Traits change rarely.** Temperament shifts only when an imprint forms; drives
drift slowly with reinforced experience. An NPC whose personality moves every
session has no personality.

Inheritance exists so generated NPCs are *coherent* rather than random. Culture
supplies a prior, parents pull toward their midpoint, and variance keeps siblings
apart — which hands you family and dynasty stories for the cost of a lerp.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from random import Random

from helpers.dnd.tuning import DEFAULT_GENERATION, GenerationTuning

# Stable disposition. -1..1.
TEMPERAMENT = ("warmth", "volatility", "boldness", "diligence", "openness")
# What they want. 0..1.
DRIVES = ("greed", "honour", "curiosity", "fear_of_death", "belonging")
# Faculties. 0..1, neutral at 0.5. NOT dispositions: these describe what a mind
# is *capable* of rather than what it wants, so they never feed the utility
# scorer the way drives do. Kept separate for that reason.
FACULTIES = ("retention",)

TRAIT_LABELS = {
    "warmth": "Warmth",             # cruel ↔ kind
    "volatility": "Volatility",     # steady ↔ explosive
    "boldness": "Boldness",         # timid ↔ reckless
    "diligence": "Diligence",       # feckless ↔ dogged
    "openness": "Openness",         # rigid ↔ curious
    "greed": "Greed",
    "honour": "Honour",
    "curiosity": "Curiosity",
    "fear_of_death": "Fear of death",
    "belonging": "Belonging",
    "retention": "Retention",
}

# How strongly parents pull a child toward their midpoint. The number to tune:
# high enough that "she has her mother's temper" reads as true, low enough that
# children are not copies.
# Defaults only — heritability and both variances are tunable per server and
# per campaign (helpers/dnd/tuning.py).
HERITABILITY = 0.4
SIBLING_VARIANCE = 0.25
RETENTION_VARIANCE = 0.32

# Culture priors. Deliberately small nudges, not stereotypes — a tidewater NPC
# is *slightly* more dogged on average, and any individual can be anything. The
# variance above is larger than most of these offsets, which is the point.
CULTURES: dict[str, dict] = {
    "tidewater": {"diligence": 0.3, "openness": -0.15, "belonging": 0.2},
    "highland": {"boldness": 0.25, "honour": 0.2, "warmth": -0.1},
    "city": {"openness": 0.3, "curiosity": 0.2, "belonging": -0.15},
    "wanderer": {"openness": 0.35, "belonging": -0.3, "curiosity": 0.25},
    "cloister": {"diligence": 0.35, "volatility": -0.3, "honour": 0.25},
    "": {},
}


@dataclass
class Traits:
    """Ten axes. Temperament is -1..1; drives are 0..1."""

    warmth: float = 0.0
    volatility: float = 0.0
    boldness: float = 0.0
    diligence: float = 0.0
    openness: float = 0.0

    greed: float = 0.5
    honour: float = 0.5
    curiosity: float = 0.5
    fear_of_death: float = 0.5
    belonging: float = 0.5

    # How well this mind holds on to things. 0.0 forgets names by next week;
    # 1.0 remembers nearly everything. Multiplies memory stability directly
    # (mind/memory/decay.py) and shifts the imprint threshold a little.
    retention: float = 0.5

    flaws: list[str] = field(default_factory=list)
    bonds: list[dict] = field(default_factory=list)
    ideals: list[str] = field(default_factory=list)

    def to_doc(self) -> dict:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Traits":
        doc = doc or {}
        known = {f: doc[f] for f in TEMPERAMENT + DRIVES + FACULTIES if f in doc}
        return cls(
            **known,
            flaws=list(doc.get("flaws") or []),
            bonds=list(doc.get("bonds") or []),
            ideals=list(doc.get("ideals") or []),
        )

    def axis(self, name: str) -> float:
        return float(getattr(self, name, 0.0))

    def strongest(self, count: int = 3) -> list[tuple[str, float]]:
        """The axes furthest from neutral — what you would notice about them.

        Drives are measured from 0.5 rather than 0, since 0.5 is their neutral;
        comparing a drive's raw value against a temperament's would make every
        NPC look greedy.
        """
        scored = [(a, abs(self.axis(a))) for a in TEMPERAMENT]
        scored += [(a, abs(self.axis(a) - 0.5) * 2) for a in DRIVES]
        scored.sort(key=lambda pair: -pair[1])
        return [(a, self.axis(a)) for a, _ in scored[:count]]

    def describe(self) -> str:
        """A one-line character read, for sheets and the inspector."""
        words = []
        for axis, value in self.strongest(3):
            words.append(_TRAIT_WORDS[axis][0] if value < (0.5 if axis in DRIVES else 0)
                         else _TRAIT_WORDS[axis][1])
        return ", ".join(words)


# Low end, high end. Used only for the human-readable read.
_TRAIT_WORDS = {
    "warmth": ("cold", "kind"),
    "volatility": ("steady", "volatile"),
    "boldness": ("cautious", "bold"),
    "diligence": ("careless", "dogged"),
    "openness": ("set in their ways", "curious"),
    "greed": ("unmaterial", "grasping"),
    "honour": ("unscrupulous", "honourable"),
    "curiosity": ("incurious", "inquisitive"),
    "fear_of_death": ("fearless", "self-preserving"),
    "belonging": ("solitary", "needs company"),
    "retention": ("forgetful", "never forgets"),
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def derive_traits(
    rng: Random,
    *,
    culture: str = "",
    parents: list[Traits] | None = None,
    role: str = "",
    tuning: GenerationTuning = DEFAULT_GENERATION,
) -> Traits:
    """Generate a coherent personality.

    Three sources, in order: the culture's prior, the parents' midpoint, then
    variance so no two siblings match.
    """
    values: dict[str, float] = {a: 0.0 for a in TEMPERAMENT}
    values.update({a: 0.5 for a in DRIVES})
    values.update({a: 0.5 for a in FACULTIES})

    for axis, offset in CULTURES.get(culture.lower().strip(), {}).items():
        values[axis] = values[axis] + offset

    for axis, offset in _ROLE_PRIORS.get(role.lower().strip(), {}).items():
        values[axis] = values[axis] + offset

    if parents:
        for axis in values:
            midpoint = sum(p.axis(axis) for p in parents) / len(parents)
            values[axis] = (
                values[axis] * (1 - tuning.heritability) + midpoint * tuning.heritability
            )

    for axis in values:
        # Retention varies more widely than disposition: the spread between a
        # person who remembers everything and one who remembers nothing is much
        # larger than the spread in how kind people are.
        spread = tuning.retention_variance if axis in FACULTIES else tuning.trait_variance
        values[axis] += rng.gauss(0, spread)
        low, high = (-1.0, 1.0) if axis in TEMPERAMENT else (0.0, 1.0)
        values[axis] = round(_clamp(values[axis], low, high), 3)

    return Traits(**values)


# A role nudges disposition too — a career shapes you, or selects for you. Same
# small magnitudes as culture, for the same reason.
_ROLE_PRIORS: dict[str, dict] = {
    "guard": {"diligence": 0.2, "boldness": 0.15},
    "soldier": {"boldness": 0.25, "honour": 0.15},
    "thief": {"honour": -0.25, "boldness": 0.2},
    "merchant": {"greed": 0.25, "warmth": 0.1},
    "priest": {"honour": 0.3, "warmth": 0.2},
    "scholar": {"curiosity": 0.3, "openness": 0.25, "retention": 0.2},
    "archivist": {"curiosity": 0.3, "diligence": 0.25, "retention": 0.25},
    "scribe": {"diligence": 0.3, "retention": 0.3},
    "harbourmaster": {"diligence": 0.3, "volatility": 0.1},
    "innkeeper": {"warmth": 0.25, "belonging": 0.2},
    "smuggler": {"honour": -0.2, "boldness": 0.25, "greed": 0.2},
    "noble": {"honour": 0.1, "greed": 0.15, "warmth": -0.1},
}


def shift_drive(traits: Traits, axis: str, amount: float) -> Traits:
    """Nudge a drive from lived experience. Drives move; temperament does not.

    Saturating rather than linear, so repeated experience deepens a disposition
    without ever pinning it at an extreme — nobody becomes perfectly greedy.
    """
    if axis not in DRIVES:
        return traits
    current = traits.axis(axis)
    target = 1.0 if amount > 0 else 0.0
    setattr(traits, axis, round(current + (target - current) * abs(amount), 3))
    return traits
