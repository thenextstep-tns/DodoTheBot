"""
Stakes — what an event was worth to each person in it.

The same act is not the same event for everyone it touches. A merchant lord
settles a stranger's debt with a wave of a finger: it costs him nothing he will
notice, he does not trouble to learn the man's name, and by evening he has
forgotten. For the debtor it is the day his life did not end. He will remember
it in detail for thirty years, he will decide the lord is a good man, and he
will tell everyone who will listen — which is how a reputation gets built out of
one cheap afternoon, and why nobody believes it later when the same lord turns
out to be selling people's organs.

None of that works if an event has one magnitude. It needs a **stake per party**,
and three things decide it:

* **Capacity** — what they had to begin with. The same coin is nothing to one man
  and everything to another. This is Weber's law and it is the whole merchant
  lord.
* **Need pressure** — what it relieved. An act that answers a need already at the
  edge lands far harder than the same act offered to someone comfortable.
* **Awareness** — whether they even know. You can do someone a kindness they
  never learn of, and you can come to admire someone who has no idea you exist.
  **Familiarity is therefore not mutual**, and neither is anything built on it.

Pure and seeded like the rest of ``mind/``: no I/O, no configuration reads. The
orchestration edge resolves tuning and passes it in.
"""

from __future__ import annotations

from dataclasses import dataclass

from helpers.dnd.tuning import DEFAULT_STAKES, StakesTuning


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
#  What an event is worth to one person
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Stake:
    """One party's share of an event.

    ``weight`` is the number everything downstream multiplies by: how hard the
    relationship moves, how salient the memory is, how strong a belief it forms
    and how likely they are to repeat the story.
    """

    felt: float          # 0..1 — how large it loomed for them
    awareness: float     # 0..1 — how well they know who they were dealing with
    weight: float        # 0..1 — felt, gated by whether they know who to credit

    @property
    def negligible(self) -> bool:
        """Beneath noticing. They were there; it did not register as anything."""
        return self.weight < 0.05

    def describe(self) -> str:
        """One line a GM can read, because an asymmetry nobody can see is a bug."""
        if self.negligible:
            return "cost them nothing they noticed"
        if self.weight >= 0.75:
            return "the kind of thing a life turns on"
        if self.weight >= 0.4:
            return "mattered to them"
        return "registered, barely"


def felt_size(magnitude: float, capacity: float,
              *, need_pressure: float = 0.0,
              tuning: StakesTuning = DEFAULT_STAKES) -> float:
    """How large an event of this magnitude looms for someone with this capacity.

    ``capacity`` is what they have to absorb it with — standing, resources,
    security. High capacity leaves little room for an event to matter; low
    capacity leaves nothing but room. ``reach`` sets how sharply that bites, and
    at 0 it flattens back to "magnitude is magnitude", which is the behaviour
    this module replaced.

    ``need_pressure`` is the urgency of whatever the act relieved. It can only
    ever *raise* the stake, and it cannot take it above 1 — being desperate makes
    help matter more, not infinitely more.
    """
    magnitude = clamp01(magnitude)
    room = (1.0 - clamp01(capacity)) ** max(0.0, tuning.capacity_reach)
    base = magnitude * (room if tuning.capacity_reach > 0 else 1.0)
    relief = clamp01(need_pressure) * tuning.need_reach
    return clamp01(base + (1.0 - base) * base * relief)


def stake_for(magnitude: float, capacity: float,
              *, awareness: float = 1.0, need_pressure: float = 0.0,
              tuning: StakesTuning = DEFAULT_STAKES) -> Stake:
    """One party's stake in an event.

    Awareness gates the *weight* but not the *felt* size, deliberately: being
    saved by someone you never identify is still the day your life did not end,
    so the memory keeps its force. What you cannot do is direct any of it at a
    person — there is nobody to feel it toward.
    """
    felt = felt_size(magnitude, capacity, need_pressure=need_pressure, tuning=tuning)
    aware = clamp01(awareness)
    floor = clamp01(tuning.unknown_actor_floor)
    return Stake(
        felt=felt,
        awareness=aware,
        weight=clamp01(felt * (floor + (1.0 - floor) * aware)),
    )


def default_magnitude(kind: str, table: dict[str, float] | None = None) -> float:
    """How big an act of this kind is before anyone's circumstances apply."""
    return clamp01((table or KIND_MAGNITUDE).get(kind, 0.4))


# How much an act of each kind is intrinsically worth, before capacity and need
# scale it per person. Saving a life is a large thing however rich you are;
# talking is small however poor.
KIND_MAGNITUDE: dict[str, float] = {
    "saved": 1.0, "betrayed": 0.9, "attacked": 0.8, "healed": 0.7,
    "threatened": 0.6, "stole": 0.6, "helped": 0.5, "gifted": 0.5,
    "kept_word": 0.4, "lied": 0.4, "bested": 0.4, "insulted": 0.3,
    "praised": 0.3, "travelled": 0.3, "talked": 0.2, "met": 0.2,
}


# --------------------------------------------------------------------------- #
#  Capacity
# --------------------------------------------------------------------------- #
def capacity_of(standing: float, traits=None,
                *, tuning: StakesTuning = DEFAULT_STAKES) -> float:
    """How insulated someone is from an event — standing, tempered by character.

    **Standing alone must not decide this.** Deriving insulation from
    ``importance`` and nothing else would bake in "the powerful never notice
    what is done for them", which is a cliché, not a rule: a benevolent lord
    knows exactly what his household has done for him and remembers the names.
    A cold one two doors down does not know his own steward's face. They have
    identical standing.

    So standing sets how much someone *could* be insulated, and disposition
    decides how much of that they actually are. Warmth, honour and belonging all
    mean attending to people, and they cut insulation; their absence leaves it
    intact or worse. At ``disposition_reach: 0`` this collapses back to standing
    alone, for a table that wants the simple version.

    ``standing`` is what the world has given them to absorb a shock with. It is
    **not** ``importance``: that field is a simulation-cost knob, and PCs are
    pinned at 1.0 on it because they are always fully simulated. Reading it here
    made ``room`` exactly zero for every player character, so no event could
    cost a PC anything, ever — a bug that looked exactly like the intended
    merchant-lord behaviour and hid inside it.

    **Need pressure deliberately does not enter here.** It was tempting — a
    starving lord is less insulated than a fed one — but capacity is a standing
    measure and needs are an hourly one, and coupling them made a thirsty
    afternoon lower a man's station. It also fails badly against the current
    engine, where nothing can satisfy a need and every NPC's needs reach maximum
    within a day (`04-ENTITIES.md` §5a): capacity would collapse to zero for the
    entire world and the asymmetry this module exists for would vanish.

    Need *does* shape the stake — through ``need_pressure`` in :func:`felt_size`,
    which raises what an act is worth to the person it relieves. That is the
    right channel: being desperate makes help matter more; it does not make you
    less of a lord.
    """
    if traits is None or tuning.disposition_reach <= 0:
        return standing
    return clamp01(standing * (1.0 - tuning.disposition_reach * attentiveness(traits)))


def attentiveness(traits) -> float:
    """How much this person attends to others, −1…1.

    Positive means they notice what is done for and to them however high they
    sit; negative means they would not notice a kindness if it were itemised.
    Warmth is temperament (−1…1); honour and belonging are drives (0…1 around a
    neutral 0.5), so they are centred before averaging.
    """
    warmth = float(getattr(traits, "warmth", 0.0))
    honour = (float(getattr(traits, "honour", 0.5)) - 0.5) * 2.0
    belonging = (float(getattr(traits, "belonging", 0.5)) - 0.5) * 2.0
    return max(-1.0, min(1.0, (warmth + honour + belonging) / 3.0))
