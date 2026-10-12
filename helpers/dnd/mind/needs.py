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

import math
from dataclasses import asdict, dataclass

from helpers.dnd.tuning import DEFAULT_NEEDS, NeedsTuning

NEEDS = ("hunger", "thirst", "fatigue", "pain", "warmth", "safety", "belonging",
         "desire")

# Needs that are **off unless a campaign asks for them**. Not a judgement about
# what a table should play — an adult drive belongs in an adult game and this
# engine has no opinion about that — but a default. A need that shapes behaviour
# has to be opted into, because a GM who did not choose it should never have to
# work out why their NPCs are behaving unexpectedly.
#
# Gated in two places, and both must agree (see :func:`enabled`):
#   * the ``need_desire`` tunable, per server and per campaign;
#   * the campaign's **lines** (``docs/dnd/11-SAFETY.md`` §1), which start with
#     sexual content on them for a fresh campaign. A line is not a preference a
#     tunable may override.
OPTIONAL = ("desire",)

NEED_LABELS = {
    "hunger": "Hunger", "thirst": "Thirst", "fatigue": "Fatigue", "pain": "Pain",
    "warmth": "Cold", "safety": "Fear for safety", "belonging": "Loneliness",
    "desire": "Desire",
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
    # Slow, and slower than loneliness. Cubed like the rest, so it is invisible
    # for most of its span and only ever one pressure among eight.
    "desire": 168,
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
    "desire": "seek intimacy",
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
    desire: float = 0.0     # off unless the campaign asks for it; see OPTIONAL
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

    def without(self, names) -> "Needs":
        """A copy with some needs pinned to nothing.

        How an optional need is switched off *for people who already have one* —
        the lesson from behaviour packs, where a setting that only affected
        entities created afterwards looked exactly like a setting that did not
        work. Turning desire off must mean off now, not off for the next NPC.
        """
        blanked = {name: 0.0 for name in names if hasattr(self, name)}
        if not blanked:
            return self
        return Needs(**{**self.to_doc(), **blanked})

    def urgency(self, name: str, tuning: NeedsTuning = DEFAULT_NEEDS) -> float:
        """Cubed by default. Ignorable until it very much isn't."""
        if not enabled(name, tuning):
            return 0.0
        return self.value(name) ** tuning.urgency_power

    def pressing(self, tuning: NeedsTuning = DEFAULT_NEEDS) -> list[tuple[str, float]]:
        """Needs over the impulse threshold, most urgent first."""
        out = [
            (n, self.urgency(n, tuning))
            for n in NEEDS
            if enabled(n, tuning) and self.value(n) >= tuning.impulse_threshold
        ]
        out.sort(key=lambda pair: -pair[1])
        return out

    def describe(self, tuning: NeedsTuning = DEFAULT_NEEDS) -> str:
        pressing = self.pressing(tuning)
        if not pressing:
            return "comfortable"
        return ", ".join(NEED_LABELS[n].lower() for n, _ in pressing[:3])


def enabled(name: str, tuning: NeedsTuning = DEFAULT_NEEDS) -> bool:
    """Whether this need is in play at all.

    Everything but :data:`OPTIONAL` always is. An optional one needs the
    campaign to have asked for it *and* the campaign's lines to permit it, and
    the caller resolving those two into one flag is
    ``helpers/dnd/tuning.py``.
    """
    return name not in OPTIONAL or name in tuning.optional


def advanced(needs: Needs, world_time: int,
             tuning: NeedsTuning = DEFAULT_NEEDS) -> Needs:
    """Needs brought forward to ``world_time``, in closed form.

    Pure: returns a new :class:`Needs` and does not touch the input. This is the
    same function used for a live tick and for extrapolating a dormant entity
    when something finally looks at it, so the two can never disagree.
    """
    # A need the campaign has not asked for is pinned to nothing every time
    # anybody looks, rather than merely stopped from rising. Switching it off
    # has to mean off *now*, including for entities that were carrying a value
    # while it was on.
    off = tuple(name for name in OPTIONAL if not enabled(name, tuning))

    elapsed = max(0, int(world_time) - int(needs.ticked_at))
    if not elapsed:
        return needs.without(off)

    values = {}
    for name in NEEDS:
        if name in off:
            values[name] = 0.0
            continue
        hours = tuning.hours.get(name)
        rate = (1 / (hours * 60)) if hours else RATES[name]
        # **Ordinary living covers ordinary needs.** People eat and sleep between
        # the moments a campaign cares about, and a model where they do not makes
        # everybody permanently starving and exhausted — which in practice means
        # every NPC rests forever and the world goes inert. `HOURS_TO_DESPERATE`
        # is therefore the span for somebody who is getting *nothing*, and upkeep
        # is how much of that ordinary life normally answers. Deprivation
        # (`04-ENTITIES.md` §5a) is what will take it away again.
        #
        # Only the needs that rise: pain and fear ebb on their own and are not
        # something upkeep helps with.
        if rate > 0:
            # Needs settle toward a baseline rather than climbing forever. A
            # person getting on with ordinary life is *slightly* hungry
            # perpetually and never starving; take that living away and the
            # baseline goes to 1 and they climb to it at the documented rate.
            #
            # Monotonic accumulation was the alternative and it does not work:
            # a week of world time maxed everybody out, so every NPC in the
            # campaign chose to rest and the world went inert. Nobody is
            # exhausted by ordinary weeks. Deprivation is what exhausts people.
            target = max(0.0, 1.0 - tuning.upkeep)
            moved = target + (needs.value(name) - target) * math.exp(-rate * elapsed)
        else:
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
