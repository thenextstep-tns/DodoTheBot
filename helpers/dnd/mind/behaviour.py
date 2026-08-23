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

# Verbs that are done *to* somebody. A candidate for one of these without a
# target is not an action, it is a category — so these fan out over whoever the
# actor can actually see, and the rest get a single target-less candidate.
DIRECTED = ("attack", "give", "take", "speak")

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
           tuning: BehaviourTuning = DEFAULT_BEHAVIOUR) -> list[Assignment]:
    """Which archetypes this person carries, and how much of them each accounts for.

    Weighted by fit rather than argmax, so the population sorts itself without
    any individual being forced into type. ``count`` of 0 returns nothing, which
    is packs switched off — the engine then proposes every affordance evenly.
    """
    candidates = [p for p in (packs or ()) if p.key]
    count = min(int(tuning.count), len(candidates))
    if count <= 0 or not candidates:
        return []

    pool = list(candidates)
    chosen: list[BehaviourPack] = []
    for _ in range(count):
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
