"""
What a goal is worth right now, and how much of a person it is getting.

**Attention is the scarce thing, not slots.** Anybody may want any number of
things; what they cannot do is pursue them all at once. Each person has an
attention budget, it is divided across everything they are carrying, and a
goal's share decides both how often they act on it and how much they get done
when they do.

The part that makes this more than division is that **carrying a goal costs
something before any of it is spent** — an overhead per goal, for the keeping of
it in mind at all. So usable attention *falls* as goals accumulate:

    1 goal    0.92 to spend on it        relentless
    3 goals   0.25 each                  busy, still getting somewhere
    6 goals   0.09 each                  slow
    12 goals  0.003 each                 nothing is moving
    13 goals  nothing left at all        stuck in pure potentiality

Nobody wrote either of those characters. The single-minded one and the one who
never finishes anything both fall out of one subtraction, and the difference
between them is a choice a GM makes rather than a flag somebody set. Overhead at
0 turns it back into plain division, where twelve goals is merely twelve times
slower and never zero.

This also closes the loop that keeps goal lists from growing forever: a goal
with almost no attention never advances, a goal that never advances fades, and a
faded goal is eventually given up on. Spreading yourself thin costs you the
goals, not just the progress.

Three things happen to a goal that nobody touches, and between them they are why
a world full of goals does not silently become a world full of stale ones:

* **It fades.** Wanting something is not free, and a want nobody has acted on in
  months is not what it was. Decay measures from the last time the goal *moved*,
  not from when it was formed, so a goal being actively pursued never fades.
* **A deadline presses.** The same goal is worth more with a week left than with
  a year, and much more with a day. The curve is convex so the last stretch is
  where it starts dominating, rather than the pressure rising evenly and making
  every deadline feel the same.
* **Progress cuts both ways.** Being nearly there raises what the next step is
  worth — the classic goal-gradient — while completing it removes the goal from
  contention entirely.

Pure and tunable like the rest of ``mind/``: no I/O, no configuration reads, no
RNG. Every constant that shapes any of the above is a field on
:class:`~helpers.dnd.tuning.GoalTuning`, and every one of them switches off.
"""

from __future__ import annotations

from helpers.dnd.tuning import DEFAULT_GOALS, GoalTuning
from helpers.dnd.world.goal import STATUS_DONE, STATUS_DROPPED, Goal

MINUTES_PER_DAY = 1440


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
#  What time does to a goal
# --------------------------------------------------------------------------- #
def faded(goal: Goal, world_time: int, tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """How much they still care, after however long it has been.

    Exponential in days since the goal last moved. At ``decay = 0`` this returns
    the priority unchanged, which is the switch: goals that never fade, for a
    campaign where a vow is a vow.
    """
    if tuning.decay <= 0:
        return clamp01(goal.priority)
    days = max(0, int(world_time) - int(goal.touched_at)) / MINUTES_PER_DAY
    return clamp01(goal.priority * (1.0 - tuning.decay) ** days)


def urgency(goal: Goal, world_time: int, tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """How hard the deadline is pushing, 0..1.

    ``0`` for a goal with no deadline and for one whose deadline is still far
    off; rising convexly as it closes. A goal past its deadline returns 1.0 —
    it is not pressing any more, it is failing, and :func:`active` is what drops
    it.

    How much this *matters* is :attr:`GoalTuning.deadline_reach`, applied in
    :func:`pressure`. Keeping the two apart means the inspector can show how
    close a deadline is without that number changing when a GM retunes how much
    deadlines weigh.
    """
    if goal.deadline is None:
        return 0.0
    remaining = int(goal.deadline) - int(world_time)
    if remaining <= 0:
        return 1.0
    window = max(1.0, tuning.deadline_window * MINUTES_PER_DAY)
    if remaining >= window:
        return 0.0
    # Convex: the last tenth of the window is worth far more than the first.
    return clamp01(((window - remaining) / window) ** 2)


# --------------------------------------------------------------------------- #
#  Attention — the scarce thing
# --------------------------------------------------------------------------- #
def axis_of(traits, name: str, default: float = 0.0) -> float:
    """One trait axis, from a :class:`Traits` or from the plain mapping an
    ``EntityView`` carries. Both reach this module — the view deliberately holds
    inert data rather than a mind object — and a reader that only understood one
    of them would work everywhere except inside a decision."""
    if traits is None:
        return default
    if hasattr(traits, "axis"):
        return float(traits.axis(name))
    if isinstance(traits, dict):
        return float(traits.get(name, default))
    return float(getattr(traits, name, default))


def budget(traits=None, tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """How much attention this person has to spend at all.

    ``diligence`` is the axis, because it is the one that already means feckless
    ↔ dogged. A reach of 0 gives everybody the same budget, which is the switch
    for tables that would rather this not be a personality difference.
    """
    if traits is None or tuning.attention_reach <= 0:
        return max(0.0, tuning.attention)
    diligence = axis_of(traits, "diligence")
    return max(0.0, tuning.attention * (1.0 + tuning.attention_reach * diligence))


def usable(count: int, traits=None, tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """What is left to actually pursue things with, after the cost of carrying
    them. Falls to zero once somebody is holding more than they can hold."""
    if count <= 0:
        return 0.0
    return max(0.0, budget(traits, tuning) - count * max(0.0, tuning.attention_overhead))


def focus(goals, world_time: int, traits=None,
          tuning: GoalTuning = DEFAULT_GOALS) -> dict:
    """``{key: 0..1}`` — each goal's share, where 1.0 is somebody's whole budget.

    Split by how much they care rather than evenly: someone can carry one real
    ambition and a scatter of half-wants and still get the first one done, which
    is the difference between busy and lost.
    """
    live = [g for g in (goals or ()) if g.open]
    if not live:
        return {}

    total = budget(traits, tuning)
    spendable = usable(len(live), traits, tuning)
    if total <= 0 or spendable <= 0:
        return {g.key: 0.0 for g in live}

    weights = {g.key: max(0.0, faded(g, world_time, tuning)) for g in live}
    weighed = sum(weights.values())
    if weighed <= 0:
        # Nobody cares about any of them any more. Split what is left evenly
        # rather than dividing by zero.
        return {g.key: (spendable / len(live)) / total for g in live}
    return {key: (spendable * (weight / weighed)) / total
            for key, weight in weights.items()}


def pressure(goal: Goal, world_time: int, tuning: GoalTuning = DEFAULT_GOALS,
             share: float = 1.0) -> float:
    """What this goal is worth to them at this moment, 0..1.

    The number the decision engine multiplies a candidate's usefulness by. It is
    bounded like every other term the scorer sees, so no goal can outshout the
    rest of a personality by being given a priority of 40.

    ``share`` is this goal's slice of their attention, from :func:`focus`. It
    defaults to 1.0 — the whole of somebody — so that asking what a goal is
    worth *on its own* is still a sensible question, which is what the deadline
    and gradient tests want to ask.
    """
    if not goal.open:
        return 0.0
    care = faded(goal, world_time, tuning)
    # Goal gradient: the closer to done, the more the next step is worth.
    near = 1.0 + tuning.gradient * clamp01(goal.progress)
    # And a closing deadline multiplies whatever is left of the caring. Both
    # reaches at 0 leave `care` exactly as it was, which is the switch.
    pressed = 1.0 + tuning.deadline_reach * urgency(goal, world_time, tuning)
    return clamp01(care * near * pressed) * clamp01(share)


def value_of(goal: Goal, verb: str, world_time: int,
             tuning: GoalTuning = DEFAULT_GOALS, share: float = 1.0) -> float:
    """How much doing ``verb`` is worth to this goal, 0..1.

    The whole reason goals name their verbs: this is a table lookup and a
    multiply, where a planner would have been a search.
    """
    return clamp01(goal.served_by(verb) * pressure(goal, world_time, tuning, share))


# --------------------------------------------------------------------------- #
#  The set of them
# --------------------------------------------------------------------------- #
def active(goals, world_time: int, tuning: GoalTuning = DEFAULT_GOALS,
           traits=None) -> list[Goal]:
    """The goals still in play, the one getting the most of them first.

    Drops what is finished, what was abandoned, what ran out of time, and what
    has faded below the point of caring. Note what it does **not** drop: goals
    somebody is carrying but barely attending to. Those stay, because being
    stuck holding nine things you never get to is a state the simulation should
    be able to represent rather than tidy away.

    ``cap`` is off by default and is a blunt backstop, not the mechanism —
    attention is what actually limits anyone.
    """
    live = []
    for goal in goals or ():
        if not goal.open or goal.expired(world_time):
            continue
        if tuning.abandon_below > 0 and faded(goal, world_time, tuning) < tuning.abandon_below:
            continue
        live.append(goal)

    shares = focus(live, world_time, traits, tuning)
    live.sort(key=lambda g: (-pressure(g, world_time, tuning, shares.get(g.key, 1.0)), g.key))
    return live if tuning.cap <= 0 else live[:tuning.cap]


def best_verb(goals, verbs, world_time: int,
              tuning: GoalTuning = DEFAULT_GOALS, traits=None) -> tuple[str, float]:
    """The most goal-serving thing available, and what it is worth.

    Attention decides this as much as wanting does: the goal somebody is actually
    giving themselves to is the one that wins, which is why a person with nine
    ambitions does whatever is in front of them instead.

    A convenience for the tick and the inspector; the scorer proper will want the
    per-goal breakdown rather than the winner, because the trace is the product
    (``06-DECISION-ENGINE.md`` §6).
    """
    shares = focus(goals, world_time, traits, tuning)
    best, score = "", 0.0
    for verb in verbs or ():
        worth = max((value_of(g, verb, world_time, tuning, shares.get(g.key, 1.0))
                     for g in goals or ()), default=0.0)
        if worth > score:
            best, score = verb, worth
    return best, score


# --------------------------------------------------------------------------- #
#  Priorities move
# --------------------------------------------------------------------------- #
# Which relationship axes argue for a goal about that person, and how hard.
# Positive means the axis supports the goal; negative means it undermines it.
#
# This is what stops priorities being a number a GM sets once and forgets. A
# grudge that cools should take the wanting with it, and a person you have come
# to fear should make getting away from them matter more than it did — without
# anybody scripting either.
#
# Goals about a *thing* rather than a person (acquire, reach) are absent on
# purpose: no relationship speaks to them, so nothing moves them but the GM and
# the passage of time.
SUPPORTED_BY: dict[str, dict[str, float]] = {
    "harm":     {"affinity": -1.0, "respect": -0.4, "fear": 0.3},
    "protect":  {"affinity": 0.9, "debt": 0.5, "trust": 0.3},
    "befriend": {"affinity": 0.8, "familiarity": 0.3, "fear": -0.6},
    "avoid":    {"fear": 1.0, "affinity": -0.3, "trust": -0.3},
    "learn":    {"trust": -0.3, "familiarity": -0.2},
}

# Debt is a count, not an axis. Five favours deep is as lopsided as this model
# needs to care about.
DEBT_SCALE = 5.0


def support(goal: Goal, relationship=None) -> float:
    """How much how they feel about the subject argues for this goal, −1..1.

    ``0`` when the goal is not about a person, when they have no relationship
    with them, or when the kind is one no feeling speaks to.
    """
    axes = SUPPORTED_BY.get(goal.kind)
    if not axes or relationship is None or goal.subject_id is None:
        return 0.0

    total = 0.0
    for axis, weight in axes.items():
        if axis == "debt":
            # Positive debt means *they* owe the other person.
            value = max(-1.0, min(1.0, float(getattr(relationship, "debt", 0)) / DEBT_SCALE))
        else:
            value = float(getattr(relationship, axis, 0.0))
        total += weight * value
    return max(-1.0, min(1.0, total / max(1.0, sum(abs(w) for w in axes.values()))))


def reweighed(goal: Goal, relationship=None,
              tuning: GoalTuning = DEFAULT_GOALS) -> Goal:
    """Let how they feel about somebody pull what they want about them.

    A nudge toward where the relationship points, never a jump: priorities that
    snapped to the relationship would make goals a redundant view of it, and the
    interesting characters are the ones who still want something after the
    feeling behind it has gone. ``reweigh = 0`` freezes priorities entirely, so
    they only ever change when a GM says so.
    """
    if tuning.reweigh <= 0:
        return goal
    pull = support(goal, relationship)
    if pull == 0.0:
        return goal
    target = clamp01(0.5 + 0.5 * pull)
    moved = goal.priority + tuning.reweigh * (target - goal.priority)
    return goal.with_priority(moved)


def progressed(goal: Goal, amount: float, world_time: int,
               tuning: GoalTuning = DEFAULT_GOALS, share: float = 1.0) -> Goal:
    """Move a goal along, and close it if that finished it. Returns a new goal.

    ``share`` is how much of themselves they had to give it — a whole person's
    effort moves a goal by ``amount``, a ninth of one moves it by a ninth. It
    defaults to 1.0 because a **GM** saying a goal advanced means it advanced:
    the panel's control is a statement about the world, not an attempt by the
    character. The simulation's own pursuit passes the share from :func:`focus`,
    and that is where being spread thin actually costs somebody.
    """
    moved = goal.with_progress(goal.progress + amount * clamp01(share), world_time)
    if moved.progress >= tuning.completion:
        return moved.with_status(STATUS_DONE)
    return moved


def abandoned(goal: Goal) -> Goal:
    return goal.with_status(STATUS_DROPPED)
