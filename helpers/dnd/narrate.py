"""
Saying what happened — the deterministic half of Voice (P4).

`08-LLM-LAYER.md` §5 cut the AI surface from five tasks to two, and this module
is where most of the other three land: **no model is consulted, the words come
from the verb**. It is the null backend's fallback before there is a backend to
fall back from, and when `llm/` arrives `render_scene`'s template path renders
through here rather than growing a second vocabulary that disagrees with this
one.

Why it exists at all, restated because it is easy to mistake for polish: a
decision engine nobody can see the output of is, at the table, exactly the same
as no decision engine. P3 built minds that choose, act, move their goals, settle
their needs and change who they are, and for most of that phase the message a GM
got back said *"3 minds aged"*. Everything below is already structured data with
a trace attached — the templating is the cheap part and the visibility is the
whole payoff.

**Pure** (`14-CONVENTIONS.md` §4, invariant 6): no I/O, no wall clock, no bare
RNG, and no configuration read. Names, archetype labels and tuning all arrive as
arguments; the orchestration edge resolves them. That is what lets the whole
report be tested without a database and rendered identically by the cog and the
panel — two renderings of one event that disagree is how a GM stops trusting
either.

**Every band switches off** (invariant 1) and the switches live in the panel's
*Reporting* group (invariant 2). The defaults are deliberately quiet: the human
verdict on P0–P2 was that the game is *"too convoluted for no payoff"*, and a
turn that answers with forty lines of trailing clauses is that verdict again in
a new place. Goals and needs are on because they read as consequence; stakes,
witnesses and drift are opt-in because they read as instrumentation.
"""

from __future__ import annotations

from helpers.dnd.tuning import DEFAULT_REPORT, ReportTuning

# What an action reads as when nothing narrates it. Moved here from ``minds`` in
# P4, where it was already doing this module's job from inside the orchestration
# layer; ``minds`` re-exports it so nothing that imported it from there breaks.
ACTED_PHRASES = {
    "attack": "went for", "take": "took from", "give": "gave something to",
    "speak": "spoke to", "flee": "got out", "hide": "went to ground",
    "move": "moved off", "use": "used what they had", "wait": "did nothing",
    "watch": "hung back and watched",
}

# The verbs that are not really *doing* anything — `rules.ruleset.UNCOMMITTED`.
# Named here rather than imported so the pure layer keeps its single dependency,
# and asserted equal to the ruleset's pair in the suite so they cannot drift.
UNCOMMITTED = ("wait", "watch")

# What a relieved need is called in a sentence. Blunt on purpose, exactly as
# blunt as ``minds.relieve_needs`` itself: there is no item model, so this says
# *they did something about it*, never *they ate a specific loaf*.
NEED_EASED = {
    "hunger": "their hunger",
    "thirst": "their thirst",
    "fatigue": "how tired they were",
    "pain": "the pain",
    "warmth": "the cold",
    "safety": "their nerves",
    "belonging": "how alone they felt",
    "desire": "what they were wanting",
}

# How much an act was worth to somebody else, in words rather than a weight.
# Bands, not a number: "0.62" is instrumentation and "it mattered to Ondry" is a
# report. The low band says *barely noticed* rather than saying nothing, because
# an act landing on somebody who does not care is itself a fact about the room.
STAKE_BANDS = (
    (0.70, "it was everything to {who}"),
    (0.40, "it mattered to {who}"),
    (0.15, "{who} took note"),
    (0.00, "{who} barely noticed"),
)


def describe_act(report: dict, names: dict | None = None) -> tuple[str, str, str]:
    """One committed action as ``(name, verb, target)``, ready for a message."""
    names = names or {}
    verb = ACTED_PHRASES.get(report.get("verb", ""), report.get("verb") or "acted")
    target_id = report.get("target_id")
    target = ""
    if target_id is not None:
        who = (names.get(target_id) or {}).get("name") or ""
        target = f" **{who}**" if who else ""
    return report.get("name", ""), verb, target


def _goal_note(report: dict) -> str:
    """What the act got them. The first band, and the one that makes a turn read
    as consequence rather than as a list of gestures."""
    moved = report.get("goals") or []
    finished = [goal for goal in moved if goal.get("done")]
    if finished:
        return f"and got what they wanted: *{finished[0].get('text') or 'it'}*"
    if moved:
        return f"closer to *{moved[0].get('text') or 'something'}*"
    return ""


def _need_note(report: dict) -> str:
    """What it settled. Reports the need that moved **most**, not every one —
    ``use`` eases four at once and listing all four buries the line."""
    eased = report.get("relieved") or {}
    if not eased:
        return ""
    name = max(eased, key=lambda key: eased.get(key) or 0.0)
    return f"that settled {NEED_EASED.get(name, 'something')} a little"


def _label_for(key, packs: dict | None) -> str:
    """What a campaign calls one archetype, falling back to its key.

    The fallback matters: archetypes resolve built-in → server → campaign, so a
    key can outlive the definition a GM deleted, and a line reading *more of a
    smuggler* is better than a line that vanishes.
    """
    return (packs or {}).get(key) or str(key).replace("_", " ").title()


def _drift_note(report: dict, packs: dict | None) -> str:
    """Who they turned into — and only then.

    ``became`` is the **whole new mixture**, and it arrives whenever any weight
    in it moved. Drift is continuous, so that is very nearly every action: used
    as-is it marks every line in the report and tells you nothing. What is
    actually news is the **leading** archetype changing — the part of somebody
    that answers first is now a different part — which is rare, and is a
    sentence about a person rather than about the engine.
    """
    became = report.get("became") or []
    if not became:
        return ""
    first = became[0]
    key = first[0] if isinstance(first, (list, tuple)) else first
    was = report.get("was")
    if was is None or was == key:
        # Either they lead with what they always led with, or the report predates
        # ``was`` and cannot say. Both are silence rather than a guess.
        return ""
    now = _label_for(key, packs)
    if not was:
        return f"and is *{now}* now, where they were nothing in particular"
    return f"and turned from *{_label_for(was, packs)}* toward *{now}*"


def _stake_note(report: dict, names: dict | None) -> str:
    """What the act was worth to the person it was done to.

    Deliberately the **target**, not a scan for whoever scored highest. Two
    reasons, and the first one is a bug this had already:

    * ``stakes`` is keyed by ``str(entity_id)``, because it is stored on an event
      and Mongo keys are strings. Entity ids are not integers — they are
      ``ObjectId``\\ s in production and strings in the fake — so anything that
      coerces a key back to an id silently matches nothing and the whole band
      goes quiet while looking perfectly wired.
    * The map also holds witnesses, whose ids nothing has looked up, so a scan
      would keep picking people it cannot name and reporting nobody.

    The target is who the label promises anyway. The actor's own echo
    (``stakes_actor_echo``) is excluded by construction rather than by filtering.
    """
    target_id = report.get("target_id")
    if target_id is None:
        return ""
    stakes = report.get("stakes") or {}
    if str(target_id) not in stakes:
        return ""
    weight = float(stakes[str(target_id)] or 0.0)
    who = ((names or {}).get(target_id) or {}).get("name") or ""
    if not who:
        return ""
    for floor, phrase in STAKE_BANDS:
        if weight >= floor:
            return phrase.format(who=f"**{who}**")
    return ""


def _witness_note(report: dict) -> str:
    """How much of the world is carrying this now. ``memories`` counts everyone
    who formed one, the actor included, which is why one is *only they*."""
    formed = int(report.get("memories") or 0)
    if formed <= 0:
        return "nobody will remember it"
    if formed == 1:
        return "only they will remember it"
    return f"{formed} will remember it"


def notes_for(report: dict, *, names: dict | None = None,
              packs: dict | None = None,
              tuning: ReportTuning = DEFAULT_REPORT) -> list[str]:
    """Every switched-on band that has something to say about one act.

    Order is fixed and is the order a line reads best in: what it got them, what
    it settled, who it landed on, who is carrying it, and who it made them —
    consequence first, instrumentation last.
    """
    out = []
    if tuning.goals:
        out.append(_goal_note(report))
    if tuning.needs:
        out.append(_need_note(report))
    if tuning.stakes:
        out.append(_stake_note(report, names))
    if tuning.witnesses:
        out.append(_witness_note(report))
    if tuning.drift:
        out.append(_drift_note(report, packs))
    return [note for note in out if note]


def act_line(report: dict, *, names: dict | None = None,
             packs: dict | None = None,
             tuning: ReportTuning = DEFAULT_REPORT) -> str:
    """One act as one line of report, notes and all."""
    name, verb, target = describe_act(report, names)
    notes = notes_for(report, names=names, packs=packs, tuning=tuning)
    tail = f" — {'; '.join(notes)}" if notes else ""
    return f"**{name}** {verb}{target}{tail}"


def is_idle(report: dict) -> bool:
    """Whether this was somebody declining to do anything.

    ``wait`` is the null action the engine falls back to and ``watch`` is the
    middle band between doing nothing and committing — both are real choices the
    simulation needs and neither is an event. A turn where six people hung back
    reports as quiet, not as six lines of *did nothing*.
    """
    return (report.get("verb") or "") in UNCOMMITTED


def turn_lines(turn: dict, *, names: dict | None = None,
               packs: dict | None = None,
               tuning: ReportTuning = DEFAULT_REPORT) -> dict:
    """A whole turn, split into what happened here and what happened elsewhere.

    Returns ``{here, elsewhere, hidden, acted}``:

    * ``here`` — people in an open scene, the ones a table is watching
    * ``elsewhere`` — the coarse path, everybody nobody is looking at. Kept
      apart rather than interleaved because *the world got on with it* and *the
      person across the table moved* are different pieces of news, and a GM
      reading one list cannot tell which is which.
    * ``hidden`` — how many fell past the line cap, so the caller can say so
    * ``acted`` — how many were reportable at all, idle ones already dropped

    The cap is applied to the two lists **together**, oldest first, so a turn
    full of off-screen drifting cannot push the scene off the bottom.
    """
    if tuning.lines == 0:
        return {"here": [], "elsewhere": [], "hidden": 0, "acted": 0}

    reports = [
        act for act in (turn.get("acted") or [])
        if act.get("verb") and (tuning.idle or not is_idle(act))
    ]
    budget = len(reports) if tuning.lines < 0 else min(len(reports), tuning.lines)

    here, elsewhere = [], []
    for act in reports[:budget]:
        line = act_line(act, names=names, packs=packs, tuning=tuning)
        if act.get("coarse"):
            if tuning.offscreen:
                elsewhere.append(line)
        else:
            here.append(line)
    return {
        "here": here,
        "elsewhere": elsewhere,
        "hidden": len(reports) - budget,
        "acted": len(reports),
    }


def target_ids(turn: dict) -> list:
    """Everybody an act in this turn was aimed at, for one identity lookup.

    Here rather than at the call site so the report and its name resolution
    cannot fall out of step — a line naming nobody because the caller forgot to
    ask for that id is the failure this prevents.

    Only ``target_id``: it is a real id, and the stake band reads the target's
    weight out of the map rather than trying to turn the map's string keys back
    into ids, which cannot be done.
    """
    return [
        act.get("target_id")
        for act in (turn.get("acted") or [])
        if act.get("target_id") is not None
    ]
