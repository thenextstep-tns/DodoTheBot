"""
Behaviour packs at work: who is what, and what that makes them consider.

This is the **propose** step of ``06-DECISION-ENGINE.md`` §5 — the third stage,
and the one that turns "everything the room physically permits" into "the
handful of things *this person* would think of". Scoring them is the next stage
and lives elsewhere; nothing here decides anything.

Three ideas hold it up:

**Archetypes are noticed, not assigned.** :func:`fit` reads a pack's priors
backwards — given who this person already is, how predator-shaped are they? —
exactly as ``mind/traits.py`` reads role priors. Generation then draws weighted
rather than picking the best, so the timid soldier and the gentle thug still
happen at the rate they should.

**A pack weights verbs, it never adds one.** Candidates are the intersection of
what an archetype reaches for and what the scene affords, so no archetype can
propose something impossible and adding one can never widen what is possible.
Waiting is always a candidate, because the null action is what a decision falls
back to when everything else scores badly.

**Packs are a lens, not a cage.** With packs switched off every affordance is
proposed evenly and the engine still works — it just has nothing to say about
why this person reached for that. Which is the honest description of what the
feature buys.

Pure and seeded like the rest of ``mind/``: no I/O, no configuration reads. The
archetype definitions arrive as arguments, resolved at the orchestration edge by
``helpers/dnd/packs.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

from helpers.dnd.mind.traits import DRIVES, FACULTIES, Traits
from helpers.dnd.tuning import DEFAULT_BEHAVIOUR, BehaviourTuning
from helpers.dnd.world.pack import Assignment, BehaviourPack

# Which verbs serve which goal, and which answer which need. Imported rather
# than restated: the coarse path has to reach the same conclusions as the full
# one about what a goal is for, or an NPC would want different things off-screen
# than on it.
from helpers.dnd.world.goal import SERVED_BY as SERVED  # noqa: E402
from helpers.dnd import verbs as verb_data  # noqa: E402
from helpers.dnd.world import verb as verb_model  # noqa: E402

NEEDS_ANSWERED_BY: dict[str, tuple] = {}


def _index_needs() -> None:
    """Invert the scorer's needs table once, at import.

    ``mind/decide`` maps verb → needs; the coarse proposer wants need → verbs.
    Built from the same table rather than written out again, so the two can
    never disagree about what eating is.
    """
    from helpers.dnd.mind import decide as decide_math

    for verb, names in decide_math.NEEDS_SERVED.items():
        for name in names:
            NEEDS_ANSWERED_BY.setdefault(name, ())
            NEEDS_ANSWERED_BY[name] = NEEDS_ANSWERED_BY[name] + (verb,)


# Verbs that are done *to* somebody. A candidate for one of these without a
# target is not an action, it is a category — so these fan out over whoever the
# actor can actually see, and the rest get a single target-less candidate.
# **Derived from the verb data.** This was a fourth hardcoded tuple, and the
# one that caught out the six verbs added when verbs became data: `help` was
# proposed with no target, so it never reached `interact`, moved no
# relationship, and formed a memory of somebody helping nobody. A verb that is
# `directed` in `verbs.json` is aimed at a person, everywhere.
DIRECTED = verb_model.directed(verb_data.built_in())

# Always available, always proposed, never weighted away entirely.
WAIT = "wait"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
#  Who is what
# --------------------------------------------------------------------------- #
def fit(traits: Traits, pack: BehaviourPack) -> float:
    """How well this person suits that archetype, −1…1. **Priors read backwards.**

    Forwards, ``priors`` would stamp a disposition onto anyone labelled a coward.
    Backwards it asks the better question and never flattens anybody: a predator
    who fits at −0.3 is a reluctant one, and that person existing is the whole
    argument for reading the table this way round.
    """
    if not pack.priors:
        return 0.0
    total = 0.0
    for axis, offset in pack.priors.items():
        value = traits.axis(axis)
        # Drives sit 0..1 around a neutral 0.5; temperament is already centred.
        centred = (value - 0.5) * 2 if axis in DRIVES or axis in FACULTIES else value
        total += centred * (1.0 if offset > 0 else -1.0) * min(1.0, abs(offset) / 0.3)
    return max(-1.0, min(1.0, total / max(1, len(pack.priors))))


def describe_fit(value: float, label: str) -> str:
    """One line for the GM, because an emergent oddity nobody sees is wasted."""
    if value >= 0.45:
        return f"{label.lower()} to the bone"
    if value >= 0.15:
        return f"has the makings of {label.lower()}"
    if value > -0.15:
        return f"{label.lower()} in name only"
    if value > -0.45:
        return f"an odd sort of {label.lower()}"
    return f"nothing like {label.lower()}"


def assign(traits: Traits, packs, rng: Random,
           tuning: BehaviourTuning = DEFAULT_BEHAVIOUR, first=None) -> list[Assignment]:
    """Which archetypes this person carries, and how much of them each accounts for.

    Weighted by fit rather than argmax, so the population sorts itself without
    any individual being forced into type. ``count`` of 0 returns nothing, which
    is packs switched off — the engine then proposes every affordance evenly.

    ``first`` is the archetype a GM asked for: it takes the leading share and the
    rest are drawn around it, so *give me a coward* gives you somebody who is
    mostly a coward and still their own person.
    """
    candidates = [p for p in (packs or ()) if p.key]
    count = min(int(tuning.count), len(candidates))
    if count <= 0 or not candidates:
        return []

    pool = list(candidates)
    chosen: list[BehaviourPack] = []
    if first is not None:
        named = next((p for p in pool if p.key == first.key), None)
        if named is not None:
            chosen.append(named)
            pool.remove(named)

    for _ in range(count - len(chosen)):
        if not pool:
            break
        weights = [
            max(0.001, (fit(traits, pack) + 1.0) / 2.0) ** max(0.0, tuning.fit_sharpness)
            for pack in pool
        ]
        pick = rng.choices(pool, weights=weights)[0]
        chosen.append(pick)
        pool.remove(pick)

    # The first one drawn is the one they mostly are; the rest are shades of it.
    # Normalised so a two-pack NPC is not twice the person a one-pack NPC is.
    raw = [tuning.falloff ** index for index in range(len(chosen))]
    total = sum(raw) or 1.0
    return [Assignment(key=pack.key, weight=round(share / total, 4))
            for pack, share in zip(chosen, raw)]


def shaped_by(traits: Traits, pack: BehaviourPack,
              tuning: BehaviourTuning = DEFAULT_BEHAVIOUR) -> Traits:
    """The table read **forwards**, on purpose and only when asked.

    Everything else here reads priors backwards, because generating a population
    top-down flattens it. But a GM saying *give me a coward* is not generating a
    population, they are authoring one person, and refusing them the shortcut on
    statistical grounds would be pedantry. So: asked for explicitly, applied
    once, at creation.

    A pull rather than a stamp — ``shaping`` of the way toward the archetype's
    priors — so two cowards are still two people. At 0 asking for an archetype
    gets you the label and whoever the dice produced.
    """
    if pack is None or not pack.priors or tuning.shaping <= 0:
        return traits

    doc = traits.to_doc()
    for axis, offset in pack.priors.items():
        if axis not in doc or not isinstance(doc[axis], (int, float)):
            continue
        drive = axis in DRIVES or axis in FACULTIES
        # Priors are written on a −1..1 scale; drives live 0..1 around 0.5.
        target = (0.5 + offset / 2.0) if drive else offset
        low = 0.0 if drive else -1.0
        moved = doc[axis] + tuning.shaping * (target - doc[axis])
        doc[axis] = max(low, min(1.0, moved))
    return Traits.from_doc(doc)


def momentary(traits: Traits, needs=None) -> Traits:
    """Who somebody is *right now*, as opposed to who they are.

    A person who has been frightened and hurt for a month is a more cautious
    person that month, and drift measured against their settled disposition
    would never notice. Only the two axes that state plausibly bends are moved,
    and the record itself is untouched — this is a lens, not a write.
    """
    if needs is None:
        return traits
    pressure = clamp01(max(float(getattr(needs, "safety", 0.0)),
                           float(getattr(needs, "pain", 0.0))))
    if pressure <= 0:
        return traits
    doc = traits.to_doc()
    doc["boldness"] = max(-1.0, min(1.0, doc.get("boldness", 0.0) - pressure))
    doc["fear_of_death"] = clamp01(doc.get("fear_of_death", 0.5) + pressure * 0.5)
    return Traits.from_doc(doc)


def drifted(assignments, packs: dict, traits: Traits, *, needs=None, verb: str = "",
            tuning: BehaviourTuning = DEFAULT_BEHAVIOUR) -> list[Assignment]:
    """Who somebody is becoming, one small step at a time.

    Nobody is one archetype and nobody stays the same mixture. Two things move
    the balance:

    * **What they are living through.** Fit is measured against
      :func:`momentary` rather than their settled disposition, so a stretch of
      being frightened pulls them toward the archetypes that answer fear.
    * **What they actually did.** Pass the ``verb`` they committed to and the
      archetype that most reaches for it gains ground. Behaviour becomes
      identity, slowly, which is the loop that makes a long campaign feel like
      it happened to somebody.

    Archetypes they do not currently carry are in the running too, so a person
    can *become* an opportunist rather than only becoming more of one. The set
    is trimmed back to ``count`` afterwards, so the mixture stays legible.

    ``drift = 0`` freezes it: who someone is never changes, which is the right
    setting for a one-shot.
    """
    live = {a.key: a.weight for a in (assignments or ())}
    if tuning.drift <= 0 or not packs:
        return [Assignment(key=k, weight=w) for k, w in live.items()]

    self_now = momentary(traits, needs)
    target: dict[str, float] = {}
    for key, pack in packs.items():
        # Sharpened the same way assignment is. A flat target is no target: six
        # archetypes fitting middlingly well produce six near-equal shares, and
        # renormalising afterwards then cancels the entire step — which is what
        # this did until somebody watched a frightened month change nothing.
        suits = max(0.0, (fit(self_now, pack) + 1.0) / 2.0) ** max(0.0, tuning.fit_sharpness)
        target[key] = suits
        if verb:
            target[key] += pack.weight_for(verb) * tuning.drift_from_action

    total = sum(target.values())
    if total <= 0:
        return [Assignment(key=k, weight=w) for k, w in live.items()]
    target = {k: v / total for k, v in target.items()}

    moved = {
        key: live.get(key, 0.0) + tuning.drift * (target.get(key, 0.0) - live.get(key, 0.0))
        for key in set(live) | set(target)
    }
    kept = sorted(moved.items(), key=lambda p: (-p[1], p[0]))
    # One slot more than they are "made of", so an archetype that is growing has
    # somewhere to grow. Trimming to exactly ``count`` each step discards the
    # newcomer's progress every time, and the mixture then cannot change at all
    # — it only shuffles the two you started with, which is not what anybody
    # means by becoming something.
    count = int(tuning.count) or len(kept)
    kept = [(k, w) for k, w in kept[:count + 1] if w > 0.001]
    share = sum(w for _, w in kept) or 1.0
    return [Assignment(key=k, weight=round(w / share, 4)) for k, w in kept]


# --------------------------------------------------------------------------- #
#  What that makes them consider
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Candidate:
    """One thing an entity might do, before anything has scored it."""

    verb: str = WAIT
    target_id: Any = None
    weight: float = 0.0      # 0..1, how much their archetypes reach for this
    pack: str = ""           # which archetype put it on the table, for the trace

    @property
    def directed(self) -> bool:
        return self.verb in DIRECTED

    def describe(self) -> str:
        where = f" → {self.target_id}" if self.target_id is not None else ""
        return f"{self.verb}{where} ({self.weight:.2f}{' via ' + self.pack if self.pack else ''})"


def leaning(assignments, packs: dict, verb: str) -> tuple[float, str]:
    """How much somebody reaches for a verb, and which of their archetypes it is.

    The strongest single archetype rather than a blend: a person who is mostly a
    coward and a little a predator still has a predator's reach for violence when
    it comes to it, and averaging that away produces NPCs who are all the same
    mild soup.
    """
    best, source = 0.0, ""
    for assignment in assignments or ():
        pack = packs.get(assignment.key)
        if pack is None:
            continue
        value = pack.weight_for(verb) * clamp01(assignment.weight)
        if value > best:
            best, source = value, pack.key
    return best, source


def propose_coarse(view, assignments, packs: dict,
                   tuning: BehaviourTuning = DEFAULT_BEHAVIOUR) -> list[Candidate]:
    """What somebody off-screen would think of doing, cheaply.

    ``06-DECISION-ENGINE.md`` §9: an ``active``-tier character is not in a scene,
    so there is no room to read affordances from and nobody present to aim at.
    Candidates come from **what they want and what their body wants** — the
    verbs their live goals are served by, aimed at whoever the goal is about, and
    the verbs that answer a pressing need.

    That is the whole saving, and it is a large one: no scene, no perception, no
    social projection, and a candidate list of three or four instead of twenty.
    """
    wanted: dict = {}

    for goal in getattr(view, "goals", ()):
        for verb, served in SERVED.get(goal.kind, {}).items():
            if served <= 0:
                continue
            # Off-screen, a directed verb aims at whoever the goal is about —
            # seeking somebody out is exactly what pursuing a goal about them
            # looks like when nobody is watching.
            key = (verb, goal.subject_id if verb in DIRECTED else None)
            wanted[key] = max(wanted.get(key, 0.0), served)

    for need, value in getattr(view, "needs", {}).items():
        if value < tuning.coarse_need_floor:
            continue
        for verb in NEEDS_ANSWERED_BY.get(need, ()):
            if verb in DIRECTED:
                continue
            key = (verb, None)
            wanted[key] = max(wanted.get(key, 0.0), clamp01(value))

    shaped = bool(assignments) and not tuning.off
    out = []
    for (verb, target), pull in wanted.items():
        weight, source = leaning(assignments, packs, verb)
        if not shaped:
            weight, source = 1.0, ""
        elif weight <= 0:
            continue
        out.append(Candidate(verb=verb, target_id=target, weight=weight, pack=source))

    out.sort(key=lambda c: (-c.weight, c.verb, str(c.target_id)))
    cap = int(tuning.candidate_cap)
    if cap > 0:
        out = out[:max(0, cap - 1)]

    wait_weight, wait_source = leaning(assignments, packs, WAIT)
    out.append(Candidate(verb=WAIT, target_id=None,
                         weight=wait_weight if shaped else 1.0,
                         pack=wait_source if shaped else ""))
    return out


def propose(view, affordances, assignments, packs: dict,
            tuning: BehaviourTuning = DEFAULT_BEHAVIOUR) -> list[Candidate]:
    """The things this person would think of doing here.

    ``affordances`` is what the scene permits (``rules/ruleset.py``) after the
    campaign has had its say; ``assignments`` and ``packs`` are who they are.
    The intersection is the candidate list, fanned out over whoever they can see
    for the verbs that need somebody to do them to.

    Capped, lowest leaning dropped first, so a crowded room cannot make one
    decision cost more than a quiet one. The cap is the documented lever for
    when the pipeline is too slow (``06-DECISION-ENGINE.md`` §11) — never
    caching, which would break replay.
    """
    allowed = [v for v in (affordances or ()) if v != WAIT]
    others = list(getattr(view, "others", {}) or {})

    # Switching archetypes off has to mean off *now*, not merely "stop handing
    # them out": entities generated earlier still carry theirs, and a setting
    # that only affects people created after it was changed is a setting that
    # appears not to work.
    shaped = bool(assignments) and not tuning.off

    out: list[Candidate] = []
    for verb in sorted(allowed):
        weight, source = leaning(assignments, packs, verb)
        if not shaped:
            # Everything the scene allows is equally worth considering, and the
            # scorer does all of the work of telling people apart.
            weight, source = 1.0, ""
        elif weight <= 0:
            continue

        if verb in DIRECTED and others:
            for target in others:
                out.append(Candidate(verb=verb, target_id=target,
                                     weight=weight, pack=source))
        elif verb not in DIRECTED:
            out.append(Candidate(verb=verb, target_id=None,
                                 weight=weight, pack=source))

    out.sort(key=lambda c: (-c.weight, c.verb, str(c.target_id)))
    cap = int(tuning.candidate_cap)
    if cap > 0:
        out = out[:max(0, cap - 1)]          # room kept for waiting

    # The null action, last and always. An NPC with nothing good to do should
    # do nothing, and a candidate list that cannot express that will always
    # produce somebody flailing.
    wait_weight, wait_source = leaning(assignments, packs, WAIT)
    out.append(Candidate(verb=WAIT, target_id=None,
                         weight=wait_weight if shaped else 1.0,
                         pack=wait_source if shaped else ""))
    return out


_index_needs()
