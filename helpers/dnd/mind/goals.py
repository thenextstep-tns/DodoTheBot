"""
What a goal is worth right now.

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


def pressure(goal: Goal, world_time: int, tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """What this goal is worth to them at this moment, 0..1.

    The number the decision engine multiplies a candidate's usefulness by. It is
    bounded like every other term the scorer sees, so no goal can outshout the
    rest of a personality by being given a priority of 40.
    """
    if not goal.open:
        return 0.0
    care = faded(goal, world_time, tuning)
    # Goal gradient: the closer to done, the more the next step is worth.
    near = 1.0 + tuning.gradient * clamp01(goal.progress)
    # And a closing deadline multiplies whatever is left of the caring. Both
    # reaches at 0 leave `care` exactly as it was, which is the switch.
    pressed = 1.0 + tuning.deadline_reach * urgency(goal, world_time, tuning)
    return clamp01(care * near * pressed)


def value_of(goal: Goal, verb: str, world_time: int,
             tuning: GoalTuning = DEFAULT_GOALS) -> float:
    """How much doing ``verb`` is worth to this goal, 0..1.

    The whole reason goals name their verbs: this is a table lookup and a
    multiply, where a planner would have been a search.
    """
    return clamp01(goal.served_by(verb) * pressure(goal, world_time, tuning))


# --------------------------------------------------------------------------- #
#  The set of them
# --------------------------------------------------------------------------- #
def active(goals, world_time: int, tuning: GoalTuning = DEFAULT_GOALS) -> list[Goal]:
    """The goals still in play, the one they care about most first.

    Drops what is finished, what was abandoned, what ran out of time, and what
    has faded below the point of caring. A cap of 0 or a floor of 0 switches the
    respective culling off.
    """
    live = []
    for goal in goals or ():
        if not goal.open or goal.expired(world_time):
            continue
        if tuning.abandon_below > 0 and faded(goal, world_time, tuning) < tuning.abandon_below:
            continue
        live.append(goal)

    live.sort(key=lambda g: (-pressure(g, world_time, tuning), g.key))
    return live if tuning.cap <= 0 else live[:tuning.cap]


def best_verb(goals, verbs, world_time: int,
              tuning: GoalTuning = DEFAULT_GOALS) -> tuple[str, float]:
    """The most goal-serving thing available, and what it is worth.

    A convenience for the tick and the inspector; the scorer proper will want the
    per-goal breakdown rather than the winner, because the trace is the product
    (``06-DECISION-ENGINE.md`` §6).
    """
    best, score = "", 0.0
    for verb in verbs or ():
        worth = max((value_of(g, verb, world_time, tuning) for g in goals or ()),
                    default=0.0)
        if worth > score:
            best, score = verb, worth
    return best, score


def progressed(goal: Goal, amount: float, world_time: int,
               tuning: GoalTuning = DEFAULT_GOALS) -> Goal:
    """Move a goal along, and close it if that finished it. Returns a new goal."""
    moved = goal.with_progress(goal.progress + amount, world_time)
    if moved.progress >= tuning.completion:
        return moved.with_status(STATUS_DONE)
    return moved


def abandoned(goal: Goal) -> Goal:
    return goal.with_status(STATUS_DROPPED)
