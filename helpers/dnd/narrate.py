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

from helpers.dnd.mind import relationships as rel_mod
from helpers.dnd.tuning import DEFAULT_GIST, DEFAULT_REPORT, GistTuning, ReportTuning

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


# --------------------------------------------------------------------------- #
#  Episode gists — what a memory says happened
# --------------------------------------------------------------------------- #
# `08-LLM-LAYER.md` §5's `summarize_episode`, which was going to be an LLM task
# and is not: *"Structured gist from event kinds and participants… a template
# phrases it fine."* The gist is a memory's substance and the **longest-lived
# field there is** — `stability_gist` outlasts when, who, the details and even
# how it felt, which is the decay model saying you remember *that* something
# happened long after everything else about it has gone. So it is the sentence
# that has to survive being the only thing left.
#
# What makes these read like recollection rather than like a log is **whose
# memory it is**. `minds.interact` already works out each party's role — they
# did it, it was done to them, or they watched — and used to hand all three the
# same string. P2's headline is that two witnesses to one event hold measurably
# different memories, and that was true only of the *numbers*; the words were
# identical. Now:
#
#     Ondry saved me      the person it happened to
#     I saved Ondry       the person who did it
#     Ondry saved Marla   the bystander
#
# One table does all three, because English past tense does not conjugate
# between "I saved" and "Ondry saved" — the pronouns are the whole trick, and
# `mind/relationships.PHRASES` is reused rather than copied so a kind can never
# read one way in a relationship log and another in a memory.
#
# **There is deliberately no intensity band.** "Saved my life" for a high stake
# reads well and asserts something the simulation does not know; an attack
# becoming "tried to kill" is a different claim about what happened, and a
# memory is the wrong place to invent one. How much it mattered is `salience`,
# which is already per-person and already decays. If a later change wants
# gravity in the wording, it needs a fact to hang it on first.
ROLE_SUBJECT = "subject"   # it was done to them
ROLE_ACTOR = "actor"       # they did it
ROLE_WITNESS = "witness"   # they saw it happen to somebody else

# What an undirected act reads as. Written with ``{a}`` rather than ``{name}``
# so the actor's own memory can say *I* and a bystander's can say who it was.
ACT_GISTS = {
    "flee": "{a} got out",
    "hide": "{a} went to ground",
    "move": "{a} moved off",
    "use": "{a} used what {a_had}",
    "wait": "{a} did nothing",
    "watch": "{a} hung back and watched",
}

# (subject-position, object-position, possessive) for the person remembering,
# and for anybody else.
_ME = ("I", "me", "my")


def _speaker(name: str, first_person: bool) -> tuple[str, str, str]:
    return _ME if first_person else (name, name, f"{name}'s")


def episode_gist(kind: str, actor_name: str, subject_name: str, *,
                 role: str = ROLE_WITNESS,
                 tuning: GistTuning = DEFAULT_GIST) -> str:
    """What one person's memory of a directed act says.

    ``role`` is the **holder's** part in it, which is the only thing that varies
    — the act is the same act. With ``perspective`` switched off this returns
    the flat third-person phrasing every memory used to carry, which is also
    what a caller should use when it has no idea whose memory it is.
    """
    verb = rel_mod.PHRASES.get(kind, str(kind).replace("_", " "))
    if not tuning.perspective:
        return f"{actor_name} {verb} {subject_name}"
    actor = _speaker(actor_name, role == ROLE_ACTOR)
    subject = _speaker(subject_name, role == ROLE_SUBJECT)
    return f"{actor[0]} {verb} {subject[1]}"


def act_gist(verb: str, name: str, *, first_person: bool = False,
             tuning: GistTuning = DEFAULT_GIST) -> str:
    """What one person's memory of an *undirected* act says.

    The commonest memory anybody forms of themselves, because most of what a
    character does is not aimed at a person.
    """
    template = ACT_GISTS.get(verb, "{a} acted")
    who = _speaker(name, first_person and tuning.perspective)
    return template.format(a=who[0], a_poss=who[2],
                           a_had="they had" if who[0] != "I" else "I had")


# Kept as the old name and shape so anything still reaching for it — and the
# suites that assert on its wording — keeps working. New callers want
# :func:`act_gist`, which knows whose memory it is.
ACT_PHRASES = {
    verb: template.format(a="{name}", a_poss="{name}'s", a_had="they had")
    for verb, template in ACT_GISTS.items()
}


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


# --------------------------------------------------------------------------- #
#  Summary gists — the shape of a stretch nobody can call to mind any more
# --------------------------------------------------------------------------- #
# When memories are pruned they are folded into one low-salience summary rather
# than deleted, which is the difference between forgetting and amnesia
# (`05-MEMORY.md` §8). That summary used to read *"a stretch of 41 things that
# no longer come to mind clearly"* — a count, which is the one thing about a
# forgotten period nobody has ever retained. §8 asks for **"a hard winter at the
# docks"**, and every part of that is already in the memories being folded: how
# long it ran, how it felt on average, who kept turning up in it, and where.

# How long it went on, in the words a person would use. The thresholds are days.
_PERIODS = (
    (1.5, "day"), (10.0, "week"), (24.0, "fortnight"), (75.0, "month"),
    (200.0, "season"), (500.0, "year"),
)
_LONG_PERIOD = "few years"

# How it felt on the whole. All of these take "a", so the sentence composes.
_TONES = (
    (-0.35, "bad"), (-0.12, "hard"), (0.12, "quiet"), (0.40, "good"),
)
_BEST_TONE = "fine"


def _period(span_days: float) -> str:
    for limit, word in _PERIODS:
        if span_days < limit:
            return word
    return _LONG_PERIOD


def _tone(valence: float) -> str:
    for limit, word in _TONES:
        if valence < limit:
            return word
    return _BEST_TONE


def summary_gist(*, count: int, span_days: float, valence: float,
                 with_names: list | None = None, place: str = "",
                 tuning: GistTuning = DEFAULT_GIST) -> str:
    """One line for a stretch that has stopped being individual memories.

    Everything here is measured off the memories being folded, never invented.
    With ``summaries`` switched off this is the old count-based line, which is
    also the honest fallback when a caller has nothing but a count.
    """
    if not tuning.summaries:
        return (f"a stretch of {count} things that no longer come to mind clearly")

    line = f"a {_tone(valence)} {_period(span_days)}"
    names = [str(n) for n in (with_names or []) if n]
    if names:
        if len(names) == 1:
            company = names[0]
        elif len(names) == 2:
            company = f"{names[0]} and {names[1]}"
        else:
            company = f"{', '.join(names[:-1])} and {names[-1]}"
        line += f", mostly with {company}"
    if place:
        line += f" at {place}"
    return line


def dominant(values: list, *, exclude=(), limit: int = 2) -> list:
    """The things that keep turning up, commonest first.

    Used for both *who was in this stretch* and *where it happened*. Ties break
    on first appearance rather than arbitrarily, so a summary of the same
    memories is the same summary every time — replay depends on it.
    """
    order, counts = [], {}
    for value in values:
        if value is None or value in exclude:
            continue
        key = str(value)
        if key not in counts:
            counts[key] = [0, len(order)]
            order.append(value)
        counts[key][0] += 1
    ranked = sorted(order, key=lambda v: (-counts[str(v)][0], counts[str(v)][1]))
    return ranked[:limit] if limit else ranked


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
