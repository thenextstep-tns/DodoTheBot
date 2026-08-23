"""
Scoring, and choosing. The end of the pipeline.

Everything before this narrowed: affordances said what the room permits, packs
said what this person would think of. This weighs the survivors and picks one.

    U = Σ (weight × term), each term bounded −1…1 before its weight

Nine terms, and three rules that keep them authorable
(``06-DECISION-ENGINE.md`` §6):

1. **Every term is bounded to −1…1 before weighting.** Otherwise one term
   silently dominates and the weights stop being comparable to each other, which
   is the failure mode that makes a utility system unauthorable.
2. **Curves, not lines.** Needs are cubed, risk aversion rides an exponent on
   ``fear_of_death``, norms saturate. Linear utility produces NPCs who behave
   like spreadsheets.
3. **The trace comes back, always.** Every score carries the per-term breakdown
   that produced it. That dict is the explainability feature *and* the debugger,
   and it is why the panel can say **"fear 0.41, imprint 0.62, norm −0.25"**
   rather than "the model decided".

**Traits modulate the terms, never the weights.** Per-entity weights would be
untunable — with two hundred NPCs you would never find the one that is wrong —
so a bold character gets a different *risk term*, not a different risk weight.

The ninth term is a deliberate addition to the spec's eight: ``archetype``, the
leaning that ``mind/behaviour.py`` used to propose the candidate at all. It has
to enter the score somewhere, and a visible term is better than a silent
multiplier on the total — a number that moves a decision and never appears in
its trace is exactly what this file exists to avoid.

Selection is **softmax, not argmax**: the best action usually wins and sometimes
does not, and how often is a personality trait. Steady people are predictable;
volatile people surprise you.

Pure and seeded. The RNG is passed in, no wall clock is read, and the same
inputs give the same answer forever — which is what makes a campaign replayable
and is why decisions are never cached (``§11``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random
from typing import Any

from helpers.dnd.mind import goals as goal_math
from helpers.dnd.tuning import (
    DEFAULT_DECISION,
    DEFAULT_GOALS,
    DEFAULT_NEEDS,
    DecisionTuning,
    GoalTuning,
    NeedsTuning,
)

# The terms, in the order a trace reads best: what the body wants, what the
# person wants, what they feel, what it costs, who they are, what it would mean.
TERMS = ("need", "impulse", "goal", "relation", "risk", "trait", "imprint",
         "norm", "archetype")


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
#  The tables the terms read
#
#  Small, legible, and in one place on purpose: a scorer whose judgements are
#  scattered through nine functions cannot be reasoned about by the person who
#  has to explain an NPC's behaviour at the table.
# --------------------------------------------------------------------------- #
# Which needs an action plausibly answers.
NEEDS_SERVED = {
    "take":   ("hunger", "thirst"),
    "use":    ("hunger", "thirst", "pain", "warmth"),
    "flee":   ("safety",),
    "hide":   ("safety",),
    "move":   ("warmth", "safety"),
    "speak":  ("belonging", "desire"),
    "give":   ("belonging", "desire"),
    "attack": ("safety",),
    "wait":   ("fatigue",),
    "watch":  ("safety",),
}

# How much of a gamble each verb is, before anything about the person.
RISK = {
    "attack": 0.9, "take": 0.6, "flee": 0.35, "hide": 0.2, "use": 0.2,
    "move": 0.1, "speak": 0.1, "give": 0.1, "watch": 0.05, "wait": 0.0,
}

# Which way an action points socially. Used twice: to read a formative memory
# about somebody onto a choice about them, and to weigh what it would look like.
SOCIAL_SIGN = {
    "attack": -1.0, "take": -0.8, "hide": -0.3, "flee": -0.3,
    "speak": 0.8, "give": 1.0, "use": 0.0, "move": 0.0, "wait": 0.0,
    # Watching somebody is not friendly and not hostile. It is *appraisal*, and
    # giving it a social sign either way would make it read as a move against
    # them, which is precisely what it is not.
    "watch": 0.0,
}

# What a room thinks of it. Negative is "not done here".
NORM = {
    "attack": -0.85, "take": -0.6, "hide": -0.35, "flee": -0.25,
    "speak": 0.3, "give": 0.45, "use": 0.0, "move": 0.0, "wait": 0.05,
    # Nobody minds you looking. That is why it is the thing people do.
    "watch": 0.1,
}

# Which dispositions reach for which verb. **This is where `boldness` finally
# does something** — declared in P2, stored, displayed, and until now read by no
# code anywhere in the project.
TRAIT_AFFINITY = {
    "attack": {"boldness": 0.6, "warmth": -0.5, "volatility": 0.4},
    "flee":   {"boldness": -0.7, "fear_of_death": 0.5},
    "hide":   {"boldness": -0.5, "openness": -0.2, "honour": -0.2},
    "speak":  {"warmth": 0.5, "openness": 0.4, "belonging": 0.3},
    "give":   {"warmth": 0.6, "greed": -0.5, "honour": 0.3},
    "take":   {"greed": 0.7, "honour": -0.5, "boldness": 0.2},
    "use":    {"diligence": 0.4, "curiosity": 0.3},
    "move":   {"curiosity": 0.2},
    "wait":   {"diligence": 0.3, "volatility": -0.4, "boldness": -0.2},
    "watch":  {"diligence": 0.5, "curiosity": 0.5, "openness": 0.3,
               "volatility": -0.3},
}

# How the axes of a relationship argue for an action about that person.
RELATION_READS = {
    "attack": {"affinity": -0.6, "trust": -0.3, "fear": 0.3, "respect": -0.2},
    "take":   {"affinity": -0.4, "trust": -0.3, "respect": -0.3},
    # `desire` sits at 0 in every campaign that has not switched it on, so it
    # contributes exactly nothing there rather than needing a branch here.
    "speak":  {"affinity": 0.5, "familiarity": 0.3, "trust": 0.2, "desire": 0.4},
    "give":   {"affinity": 0.6, "trust": 0.3, "debt": 0.4, "desire": 0.3},
    "flee":   {"fear": 0.6, "trust": -0.2},
    "hide":   {"fear": 0.5},
    # You watch the people you have not made your mind up about: unfamiliar,
    # and not yet trusted.
    "watch":  {"familiarity": -0.4, "trust": -0.3, "fear": 0.2},
}

DEBT_SCALE = 5.0


# --------------------------------------------------------------------------- #
#  A decision, and its working
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Scored:
    """One candidate, weighed."""

    verb: str = "wait"
    target_id: Any = None
    utility: float = 0.0
    terms: dict = field(default_factory=dict)
    pack: str = ""

    def top_terms(self, count: int = 4) -> list[tuple[str, float]]:
        """The terms that actually decided it, largest pull first — the line the
        panel and the GM both want, rather than nine numbers."""
        live = [(name, value) for name, value in self.terms.items() if abs(value) >= 0.005]
        live.sort(key=lambda pair: -abs(pair[1]))
        return live[:count]

    def describe(self) -> str:
        where = f" → {self.target_id}" if self.target_id is not None else ""
        working = ", ".join(f"{name} {value:+.2f}" for name, value in self.top_terms())
        return f"{self.verb}{where} · U {self.utility:+.2f} ({working})"


@dataclass(frozen=True)
class Decision:
    """What somebody chose, everything they considered, and why.

    ``considered`` is kept rather than discarded because the interesting question
    at a table is almost never "what did she do" — it is "what else was she
    weighing, and how close was it".
    """

    chosen: Scored = field(default_factory=Scored)
    considered: tuple = ()
    temperature: float = 0.3
    entity_id: Any = None

    @property
    def runner_up(self) -> "Scored | None":
        rest = [s for s in self.considered if s is not self.chosen]
        return rest[0] if rest else None

    @property
    def margin(self) -> float:
        """How clear-cut it was. Near zero means the softmax was doing real work
        and this character could easily have done something else."""
        other = self.runner_up
        return self.chosen.utility - other.utility if other else self.chosen.utility

    def to_doc(self) -> dict:
        """The trace, as it is stored on the resulting ``WorldEvent``."""
        return {
            "verb": self.chosen.verb,
            "target_id": self.chosen.target_id,
            "utility": round(self.chosen.utility, 4),
            "terms": {k: round(v, 4) for k, v in self.chosen.terms.items()},
            "pack": self.chosen.pack,
            "temperature": round(self.temperature, 4),
            "margin": round(self.margin, 4),
            "considered": [
                {"verb": s.verb, "target_id": s.target_id,
                 "utility": round(s.utility, 4)}
                for s in self.considered[:8]
            ],
        }

    def describe(self) -> str:
        line = self.chosen.describe()
        other = self.runner_up
        if other is not None:
            line += f", over {other.verb} ({other.utility:+.2f}) at T {self.temperature:.2f}"
        return line


# --------------------------------------------------------------------------- #
#  The terms
# --------------------------------------------------------------------------- #
def need_term(view, verb: str, tuning: NeedsTuning = DEFAULT_NEEDS) -> float:
    """How much the body wants this. Cubed, so a need is ignorable until it
    very much is not — the one line that stops NPCs fidgeting about being
    slightly peckish."""
    best = 0.0
    for name in NEEDS_SERVED.get(verb, ()):
        best = max(best, clamp01(view.need(name)) ** max(0.1, tuning.urgency_power))
    return clamp01(best)


def impulse_term(view, verb: str, tuning: NeedsTuning = DEFAULT_NEEDS) -> float:
    """Whether a need has crossed from pressure into an *urge*.

    Distinct from :func:`need_term` on purpose: the need is how hard it presses
    at all, this is whether it has become the thing they keep thinking about.
    The gap between the two is where a disciplined character feels the urge to
    run and holds the line anyway.
    """
    threshold = clamp01(tuning.impulse_threshold)
    headroom = max(1e-6, 1.0 - threshold)
    best = 0.0
    for name in NEEDS_SERVED.get(verb, ()):
        value = clamp01(view.need(name))
        if value >= threshold:
            best = max(best, (value - threshold) / headroom)
    return clamp01(best)


def goal_term(view, verb: str, shares: dict,
              tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """How much this serves what they are actually after.

    A lookup and a multiply, which is the whole reason goals name their verbs
    rather than needing a planner searched over them.
    """
    return clamp01(max(
        (goal_math.value_of(goal, verb, view.world_time, tuning, shares.get(goal.key, 1.0))
         for goal in view.goals),
        default=0.0,
    ))


def relation_term(view, verb: str, target_id) -> float:
    """What they feel about the person this would be done to.

    Zero for an action aimed at nobody — not a mild opinion, genuinely no
    contribution, which is what keeps the trace honest about why something was
    chosen.
    """
    reads = RELATION_READS.get(verb)
    if not reads or target_id is None:
        return 0.0
    other = view.of(target_id)
    total = 0.0
    for axis, weight in reads.items():
        if axis == "debt":
            # Positive debt means the viewer owes them, which argues for giving.
            value = clamp(float(other.debt) / DEBT_SCALE)
        elif axis == "desire":
            # Wanting somebody is 0..1 — its absence is nothing, not the
            # opposite — and how much they strike this person raises it.
            value = clamp01(float(other.desire)) * (0.6 + 0.8 * clamp01(other.allure))
        else:
            value = clamp(float(getattr(other, axis, 0.0)))
        total += weight * value
    return clamp(total / max(1.0, sum(abs(w) for w in reads.values())))


def risk_term(view, verb: str, target_id, tuning: DecisionTuning = DEFAULT_DECISION) -> float:
    """What it might cost them, as *they* weigh cost. Always ≤ 0.

    Exponential in ``fear_of_death`` rather than linear: the difference between
    a fearless character and an average one should be much smaller than the
    difference between an average one and someone who cannot make themselves do
    it. That curve is the whole reason cowardice reads as cowardice.
    """
    danger = RISK.get(verb, 0.2)
    if target_id is not None and verb in ("attack", "take"):
        # Picking a fight with someone who frightens you is a worse idea.
        danger = clamp01(danger + 0.4 * clamp01(view.of(target_id).fear))
    # Kept inside 0..1 by construction rather than by clamping. A multiplier that
    # runs past 1 and is then clipped is not a curve, it is a curve with its top
    # sawn off — and the top is exactly where the difference between frightened
    # and unable-to-make-themselves is supposed to live.
    fear = clamp01(view.trait("fear_of_death", 0.5))
    caution = 0.25 + 0.75 * fear ** max(0.1, tuning.risk_curve)
    return -clamp01(danger * caution)


def trait_term(view, verb: str) -> float:
    """Whether this is the sort of thing they do.

    Where ``boldness`` starts mattering: declared in P2, rolled, stored,
    displayed, and read by nothing anywhere in the codebase until this line.
    """
    axes = TRAIT_AFFINITY.get(verb)
    if not axes:
        return 0.0
    total = 0.0
    for axis, weight in axes.items():
        value = view.trait(axis, 0.5 if axis in ("greed", "honour", "curiosity",
                                                 "fear_of_death", "belonging") else 0.0)
        # Drives sit 0..1 around a neutral 0.5; temperament is already centred.
        centred = (value - 0.5) * 2 if axis in ("greed", "honour", "curiosity",
                                                "fear_of_death", "belonging") else value
        total += weight * clamp(centred)
    return clamp(total / max(1.0, sum(abs(w) for w in axes.values())))


def imprint_term(view, verb: str, target_id) -> float:
    """What a formative memory of this person makes them want to do.

    An imprint about somebody is read onto a choice about them through the
    action's social direction: a fond one argues for speaking and against
    violence, a terrible one argues the other way round. This is the term that
    produces *"she drew her knife instead of answering"* and can say why.
    """
    sign = SOCIAL_SIGN.get(verb, 0.0)
    if not sign or target_id is None:
        return 0.0
    best = 0.0
    for memory in view.memories:
        if not memory.is_imprint or target_id not in memory.participants:
            continue
        pull = memory.valence * sign * clamp01(memory.salience)
        if abs(pull) > abs(best):
            best = pull
    return clamp(best)


def norm_term(view, verb: str, onlookers: int) -> float:
    """What it would look like, and how much they care what it looks like.

    Saturating in the number of people watching: the first witness changes
    everything and the ninth changes almost nothing. ``honour`` decides how much
    the whole term weighs on them at all, which is how the shameless end up
    doing in public what everyone else only considers.
    """
    baseline = NORM.get(verb, 0.0)
    if not baseline:
        return 0.0
    seen = 1.0 - math.exp(-max(0, onlookers) / 2.0)
    conscience = 0.4 + 1.2 * clamp01(view.trait("honour", 0.5))
    return clamp(baseline * seen * conscience)


def archetype_term(weight: float) -> float:
    """How much the person they are reached for this in the first place.

    A term rather than a multiplier on the total, so it shows up in the trace.
    A number that moves a decision and never appears in its working is the thing
    this whole file exists to prevent.
    """
    return clamp01(weight)


# --------------------------------------------------------------------------- #
#  Scoring one, then all of them
# --------------------------------------------------------------------------- #
def score(view, candidate, *, shares: dict, onlookers: int,
          tuning: DecisionTuning = DEFAULT_DECISION,
          goals: GoalTuning = DEFAULT_GOALS,
          needs: NeedsTuning = DEFAULT_NEEDS) -> Scored:
    """Weigh one candidate, and keep the working."""
    verb, target = candidate.verb, candidate.target_id
    raw = {
        "need": need_term(view, verb, needs),
        "impulse": impulse_term(view, verb, needs),
        "goal": goal_term(view, verb, shares, goals),
        "relation": relation_term(view, verb, target),
        "risk": risk_term(view, verb, target, tuning),
        "trait": trait_term(view, verb),
        "imprint": imprint_term(view, verb, target),
        "norm": norm_term(view, verb, onlookers),
        "archetype": archetype_term(candidate.weight),
    }
    weights = tuning.weights
    terms = {name: round(clamp(value) * weights.get(name, 0.0), 6)
             for name, value in raw.items()}
    return Scored(verb=verb, target_id=target, utility=sum(terms.values()),
                  terms=terms, pack=candidate.pack)


def temperature(view, tuning: DecisionTuning = DEFAULT_DECISION) -> float:
    """How much of a coin-toss this character's choices are.

    Volatility is the axis: a steady person does the sensible thing nearly every
    time, an explosive one is worth watching. Never zero — a temperature of zero
    is argmax, and argmax makes a world where nobody ever surprises you.
    """
    spread = tuning.temperature_spread * clamp01((view.trait("volatility") + 1.0) / 2.0)
    return max(0.01, tuning.temperature + spread)


def decide(view, candidates, rng: Random, *,
           onlookers: int | None = None,
           tuning: DecisionTuning = DEFAULT_DECISION,
           goals: GoalTuning = DEFAULT_GOALS,
           needs: NeedsTuning = DEFAULT_NEEDS) -> Decision:
    """Weigh everything on the table and choose one, softmax and seeded.

    Nothing is written and nothing is read but the view: this is a pure function
    of ``(EntityView, candidates, Random)``, which is what makes a campaign
    replay to the same state and why a decision is never cached.
    """
    pool = list(candidates or ())
    if not pool:
        return Decision(entity_id=getattr(view, "entity_id", None))

    if onlookers is None:
        onlookers = len(getattr(view, "others", {}) or {})
    shares = goal_math.focus(view.goals, view.world_time, view.traits, goals)

    scored = [score(view, c, shares=shares, onlookers=onlookers,
                    tuning=tuning, goals=goals, needs=needs) for c in pool]
    scored.sort(key=lambda s: (-s.utility, s.verb, str(s.target_id)))

    heat = temperature(view, tuning)
    top = scored[0].utility
    # Shifted by the best score before exponentiating: exp of a large positive
    # utility overflows, and exp of a large negative one underflows every weight
    # to zero and makes `choices` raise. Neither is a thing a GM should ever see.
    weights = [math.exp((s.utility - top) / heat) for s in scored]
    chosen = rng.choices(scored, weights=weights)[0]

    return Decision(chosen=chosen, considered=tuple(scored), temperature=heat,
                    entity_id=getattr(view, "entity_id", None))
