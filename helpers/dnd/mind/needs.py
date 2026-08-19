"""
Physiological needs and the impulses they generate.

Seven needs, each 0..1 where 1 is desperate. They tick with world time and only
for entities the simulation is actually paying attention to — a dormant NPC's
needs are computed in closed form when someone looks (see :func:`advanced`),
which costs nothing until observed and gives the same answer as ticking would.

The one trick worth knowing:

    urgency = need ** 3

Linear needs produce NPCs who constantly fidget about being slightly peckish.
Cubed, hunger is invisible at 0.4 (0.06 urgency) and dominates at 0.9 (0.73).
That is how needs feel real without being annoying, and it is one line.

Impulses are **not** memory and not decisions. They are short-lived pressure that
the decision engine weighs against everything else in P3 — which is why a
disciplined NPC can feel the urge to run and hold the line anyway. That gap is
where character lives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from helpers.dnd.tuning import DEFAULT_NEEDS, NeedsTuning

NEEDS = ("hunger", "thirst", "fatigue", "pain", "warmth", "safety", "belonging")

NEED_LABELS = {
    "hunger": "Hunger", "thirst": "Thirst", "fatigue": "Fatigue", "pain": "Pain",
    "warmth": "Cold", "safety": "Fear for safety", "belonging": "Loneliness",
}

# Hours from satisfied to desperate, doing ordinary things. These are spans to
# *desperation*, not to discomfort — the cube means a need is barely felt for the
# first half of its span, so "hungry" arrives long before hour 48.
HOURS_TO_DESPERATE = {
    "hunger": 48,
    "thirst": 24,
    "fatigue": 20,      # a waking day
    "warmth": 72,
    "belonging": 120,
}
# Pain and safety are not on a clock — events set them and they ebb.
HOURS_TO_CALM = {"pain": 12, "safety": 6}

RATES = {name: 1 / (hours * 60) for name, hours in HOURS_TO_DESPERATE.items()}
RATES.update({name: -1 / (hours * 60) for name, hours in HOURS_TO_CALM.items()})

# Above this a need starts generating an impulse.
IMPULSE_THRESHOLD = 0.55

# need → the urge it produces.
NEED_IMPULSE = {
    "hunger": "eat", "thirst": "drink", "fatigue": "rest", "pain": "tend wound",
    "warmth": "get warm", "safety": "get to safety", "belonging": "seek company",
}


@dataclass
class Needs:
    """Where someone's body is, right now."""

    hunger: float = 0.2
    thirst: float = 0.2
    fatigue: float = 0.2
    pain: float = 0.0
    warmth: float = 0.2
    safety: float = 0.1
    belonging: float = 0.3
    ticked_at: int = 0      # world time this was last brought up to date

    def to_doc(self) -> dict:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Needs":
        doc = doc or {}
        return cls(
            **{n: float(doc.get(n, getattr(cls, n, 0.2))) for n in NEEDS},
            ticked_at=int(doc.get("ticked_at", 0)),
        )

    def value(self, name: str) -> float:
        return float(getattr(self, name, 0.0))

    def urgency(self, name: str, tuning: NeedsTuning = DEFAULT_NEEDS) -> float:
        """Cubed by default. Ignorable until it very much isn't."""
        return self.value(name) ** tuning.urgency_power

    def pressing(self, tuning: NeedsTuning = DEFAULT_NEEDS) -> list[tuple[str, float]]:
        """Needs over the impulse threshold, most urgent first."""
        out = [
            (n, self.urgency(n, tuning))
            for n in NEEDS
            if self.value(n) >= tuning.impulse_threshold
        ]
        out.sort(key=lambda pair: -pair[1])
        return out

    def describe(self, tuning: NeedsTuning = DEFAULT_NEEDS) -> str:
        pressing = self.pressing(tuning)
        if not pressing:
            return "comfortable"
        return ", ".join(NEED_LABELS[n].lower() for n, _ in pressing[:3])


def advanced(needs: Needs, world_time: int,
             tuning: NeedsTuning = DEFAULT_NEEDS) -> Needs:
    """Needs brought forward to ``world_time``, in closed form.

    Pure: returns a new :class:`Needs` and does not touch the input. This is the
    same function used for a live tick and for extrapolating a dormant entity
    when something finally looks at it, so the two can never disagree.
    """
    elapsed = max(0, int(world_time) - int(needs.ticked_at))
    if not elapsed:
        return needs

    values = {}
    for name in NEEDS:
        hours = tuning.hours.get(name)
        rate = (1 / (hours * 60)) if hours else RATES[name]
        moved = needs.value(name) + rate * elapsed
        values[name] = round(max(0.0, min(1.0, moved)), 4)
    return Needs(**values, ticked_at=int(world_time))


def satisfy(needs: Needs, name: str, amount: float = 1.0) -> Needs:
    """Meet a need — eating, sleeping, being tended to."""
    if name not in NEEDS:
        return needs
    setattr(needs, name, round(max(0.0, needs.value(name) - abs(amount)), 4))
    return needs


def aggravate(needs: Needs, name: str, amount: float = 0.3) -> Needs:
    """Push a need up — a wound, a fright, a cold night."""
    if name not in NEEDS:
        return needs
    setattr(needs, name, round(min(1.0, needs.value(name) + abs(amount)), 4))
    return needs


# --------------------------------------------------------------------------- #
#  Impulses
# --------------------------------------------------------------------------- #
@dataclass
class Impulse:
    """A short-lived urge. Pressure, not a decision."""

    kind: str
    strength: float
    source: str = "need"        # need | stimulus | imprint | trait
    target_id: object | None = None
    born_at: int = 0
    half_life: float = 120.0    # world minutes

    def at(self, world_time: int) -> float:
        """Strength now, after decay."""
        elapsed = max(0, int(world_time) - int(self.born_at))
        return self.strength * (0.5 ** (elapsed / max(1.0, self.half_life)))

    def to_doc(self) -> dict:
        return asdict(self)


def from_needs(needs: Needs, world_time: int,
               tuning: NeedsTuning = DEFAULT_NEEDS) -> list[Impulse]:
    """Impulses arising from the body alone.

    Strength is the *urgency*, not the raw need, so the cube governs here too —
    which is why a slightly hungry NPC generates an impulse so weak that anything
    else outweighs it.
    """
    return [
        Impulse(
            kind=NEED_IMPULSE[name],
            strength=round(urgency, 4),
            source="need",
            born_at=world_time,
        )
        for name, urgency in needs.pressing(tuning)
    ]


def live(impulses: list[Impulse], world_time: int, floor: float = 0.05) -> list[Impulse]:
    """Drop impulses that have decayed below noticing."""
    return [i for i in impulses if i.at(world_time) >= floor]
