"""
What Dodo holds about one person — and how it rots.

The shape is lifted from the D&D mind (``helpers/dnd/mind``) and then cut down
until it costs nothing: three feelings, a capped list of facts, a short list of
grudges, and a per-trigger fatigue counter. No scheduler, no background sweep —
**everything decays lazily at read time**, from a stored timestamp, so a user
who has not spoken in a month costs exactly one document read to catch up.

Why these four and not the D&D seven:

``affinity``
    The existing 0–1000 relationship score, kept under its old name in Mongo so
    nothing already stored is lost. Drifts back toward neutral over days, which
    is the "she forgives" knob and the reason a grudge cannot be permanent.
``familiarity``
    0–1, earned one message at a time. Drives how much shared history she is
    allowed to assume. This is what stops a stranger being greeted like a
    lifelong friend purely because they were polite once.
``grudges``
    Short half-life, high colour. The petty-grudge mechanic needs to *fade*,
    otherwise she is permanently angry at everyone who ever said "bad bot".
``facts``
    Replaces the old single ``memory`` blob. A capped list with hit counts, so
    recall is "the things that keep coming up" rather than "everything, forever" —
    and the model is never asked to echo it back (see :mod:`prompt`), which is
    what used to let one bad completion erase a user's whole history.

Old documents migrate on first read: the ``memory`` string becomes fact zero.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Field names as stored. Kept here so nothing else in the package spells a
# Mongo key by hand.
F_USER = "user_id"
F_LEGACY_MEMORY = "memory"
F_AFFINITY = "relationship"
F_AFFINITY_AT = "relationship_at"
F_FAMILIARITY = "familiarity"
F_FACTS = "facts"
F_GRUDGES = "grudges"
F_FATIGUE = "fatigue"
F_SEEN = "seen"
F_LAST_SEEN = "last_seen"
F_RUMOURS = "rumours_heard"

# Sub-keys inside the list entries.
K_TEXT = "text"
K_AT = "at"
K_HITS = "hits"
K_STRENGTH = "strength"

# Legacy placeholders the old prompt wrote into the memory blob. Migrating them
# into a fact would give every long-standing user a memory of having no memories.
_EMPTY_MEMORIES = ("", "none", "no memories yet.", "no memories yet")

_WHITESPACE = re.compile(r"\s+")


def _now() -> float:
    return time.time()


def _hours_since(stamp: float, now: float) -> float:
    return max(0.0, (now - stamp) / 3600.0)


@dataclass
class Tuning:
    """Every number this module uses, supplied by the caller.

    Built from per-server parameters in the cog; defaulted here only so the pure
    layer stays importable (and testable) without a database.
    """

    affinity_default: int = 500
    affinity_min: int = 0
    affinity_max: int = 1000
    sentiment_weight: float = 1.0
    affinity_drift_per_day: float = 4.0

    familiarity_per_message: float = 0.01
    familiarity_max: float = 1.0

    facts_max: int = 12
    facts_recall: int = 5
    fact_halflife_days: float = 45.0

    grudges_max: int = 3
    grudge_halflife_hours: float = 8.0
    grudge_floor: float = 0.15

    rumours_max: int = 6
    rumours_recall: int = 2

    fatigue_halflife_minutes: float = 45.0


@dataclass
class ChatState:
    """One person, as Dodo currently has them. Decay is already applied."""

    user_id: str
    affinity: int = 500
    familiarity: float = 0.0
    seen: int = 0
    facts: list[dict] = field(default_factory=list)
    grudges: list[dict] = field(default_factory=list)
    rumours: list[dict] = field(default_factory=list)
    fatigue: dict[str, dict] = field(default_factory=dict)
    last_seen: float = 0.0

    # ------------------------------------------------------------------ #
    #  Reading
    # ------------------------------------------------------------------ #
    @property
    def closeness(self) -> float:
        """Affinity as 0–1, for prompt lines and dial maths."""
        return round(self.affinity / 1000.0, 2)

    def recall_facts(self, tuning: Tuning) -> list[str]:
        """The facts worth spending tokens on: most-reinforced first, then newest."""
        ranked = sorted(self.facts, key=lambda f: (-f.get(K_HITS, 1), -f.get(K_AT, 0.0)))
        return [f[K_TEXT] for f in ranked[: max(0, tuning.facts_recall)]]

    def recall_rumours(self, tuning: Tuning) -> list[dict]:
        """The most recently heard rumours about this person."""
        if tuning.rumours_recall <= 0:
            return []
        return self.rumours[-tuning.rumours_recall:]

    def top_grudge(self) -> Optional[dict]:
        """The one she would actually bring up, or ``None`` if she is at peace."""
        return max(self.grudges, key=lambda g: g.get(K_STRENGTH, 0.0)) if self.grudges else None

    # ------------------------------------------------------------------ #
    #  Writing (in memory; the store persists)
    # ------------------------------------------------------------------ #
    def note_message(self, tuning: Tuning, *, now: Optional[float] = None) -> None:
        """One more message seen from this person."""
        self.seen += 1
        self.familiarity = min(tuning.familiarity_max,
                               self.familiarity + tuning.familiarity_per_message)
        self.last_seen = now if now is not None else _now()

    def apply_sentiment(self, tuning: Tuning, score: float) -> None:
        """Move affinity by a sentiment reading (or a trigger's flat delta)."""
        moved = self.affinity + score * tuning.sentiment_weight
        self.affinity = int(max(tuning.affinity_min, min(tuning.affinity_max, moved)))

    def add_fact(self, tuning: Tuning, text: str, *, now: Optional[float] = None) -> bool:
        """Record a durable fact. Re-stating a known one bumps its hit count
        instead of duplicating it. Returns whether anything changed."""
        text = _WHITESPACE.sub(" ", (text or "").strip())
        if not text:
            return False
        now = now if now is not None else _now()
        folded = text.lower()
        for fact in self.facts:
            if fact[K_TEXT].lower() == folded:
                fact[K_HITS] = fact.get(K_HITS, 1) + 1
                fact[K_AT] = now
                return True
        self.facts.append({K_TEXT: text, K_AT: now, K_HITS: 1})
        self._trim_facts(tuning, now)
        return True

    def add_grudge(self, tuning: Tuning, text: str, strength: float,
                   *, now: Optional[float] = None) -> None:
        """Take offence. Strength 0–1; the strongest live grudge is the one she
        actually mentions."""
        text = _WHITESPACE.sub(" ", (text or "").strip())
        if not text or strength <= 0:
            return
        now = now if now is not None else _now()
        folded = text.lower()
        for grudge in self.grudges:
            if grudge[K_TEXT].lower() == folded:
                grudge[K_STRENGTH] = min(1.0, grudge.get(K_STRENGTH, 0.0) + strength)
                grudge[K_AT] = now
                break
        else:
            self.grudges.append({K_TEXT: text, K_AT: now, K_STRENGTH: min(1.0, strength)})
        self.grudges.sort(key=lambda g: -g.get(K_STRENGTH, 0.0))
        del self.grudges[max(0, tuning.grudges_max):]

    def forgive(self) -> None:
        """Kindness clears the slate. That is the point of the grudges being
        petty: they are supposed to be cheap to end."""
        self.grudges.clear()

    def add_rumour(self, tuning: Tuning, rumour: str, source_id: str, source_name: str) -> None:
        """Store something somebody said about this person, oldest dropped first."""
        self.rumours.append({"rumour": rumour, "source_id": source_id, "source_name": source_name})
        del self.rumours[: max(0, len(self.rumours) - max(0, tuning.rumours_max))]

    def bump_fatigue(self, tuning: Tuning, key: str, *, now: Optional[float] = None) -> None:
        """Record that a trigger just fired for this person. The stored count is
        the *decayed* one plus one, so the entry never needs a sweep."""
        now = now if now is not None else _now()
        self.fatigue[key] = {K_HITS: self.fatigue_of(key, tuning, now=now) + 1.0, K_AT: now}

    def fatigue_of(self, key: str, tuning: Tuning, *, now: Optional[float] = None) -> float:
        """How many times this bit has been pulled recently, decayed. 0 = fresh."""
        entry = self.fatigue.get(key)
        if not entry:
            return 0.0
        now = now if now is not None else _now()
        halflife = max(1e-6, tuning.fatigue_halflife_minutes)
        elapsed = max(0.0, (now - entry.get(K_AT, now)) / 60.0)
        return entry.get(K_HITS, 0.0) * (0.5 ** (elapsed / halflife))

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #
    def _trim_facts(self, tuning: Tuning, now: float) -> None:
        """Drop the weakest facts when over the cap. Weight is hits against age,
        so a thing mentioned once a year ago loses to a thing mentioned thrice."""
        if len(self.facts) <= max(1, tuning.facts_max):
            return
        halflife_hours = max(1e-6, tuning.fact_halflife_days * 24.0)

        def weight(fact: dict) -> float:
            age = _hours_since(fact.get(K_AT, now), now)
            return fact.get(K_HITS, 1) * (0.5 ** (age / halflife_hours))

        self.facts.sort(key=weight, reverse=True)
        del self.facts[max(1, tuning.facts_max):]


# --------------------------------------------------------------------------- #
#  Decay — applied on load, never on a timer
# --------------------------------------------------------------------------- #
def _decay_affinity(affinity: int, since: float, tuning: Tuning, now: float) -> int:
    """Pull affinity toward neutral by ``affinity_drift_per_day``. Set the
    parameter to 0 to freeze relationships exactly where they are."""
    if tuning.affinity_drift_per_day <= 0 or since <= 0:
        return affinity
    days = max(0.0, (now - since) / 86400.0)
    pull = tuning.affinity_drift_per_day * days
    neutral = tuning.affinity_default
    if affinity > neutral:
        return int(max(neutral, affinity - pull))
    return int(min(neutral, affinity + pull))


def _decay_grudges(grudges: list[dict], tuning: Tuning, now: float) -> list[dict]:
    """Half-life decay; anything below the floor is genuinely forgotten."""
    halflife = max(1e-6, tuning.grudge_halflife_hours)
    alive = []
    for grudge in grudges:
        faded = _hours_since(grudge.get(K_AT, now), now) / halflife
        strength = grudge.get(K_STRENGTH, 0.0) * (0.5 ** faded)
        if strength >= tuning.grudge_floor:
            alive.append({**grudge, K_STRENGTH: round(strength, 4)})
    return alive


def from_document(document: Optional[dict], user_id: str, tuning: Tuning,
                  *, now: Optional[float] = None) -> ChatState:
    """Build a decayed :class:`ChatState` from a stored document (or nothing).

    Also performs the one-way migration off the legacy ``memory`` blob: whatever
    text was there becomes the first fact, so no history is lost the day this
    ships.
    """
    now = now if now is not None else _now()
    document = document or {}

    facts = [dict(f) for f in document.get(F_FACTS) or [] if f.get(K_TEXT)]
    if not facts:
        legacy = (document.get(F_LEGACY_MEMORY) or "").strip()
        if legacy.lower() not in _EMPTY_MEMORIES:
            facts = [{K_TEXT: legacy, K_AT: document.get(F_LAST_SEEN) or now, K_HITS: 1}]

    affinity = int(document.get(F_AFFINITY, tuning.affinity_default))
    affinity_at = float(document.get(F_AFFINITY_AT) or document.get(F_LAST_SEEN) or 0.0)

    return ChatState(
        user_id=user_id,
        affinity=_decay_affinity(affinity, affinity_at, tuning, now),
        familiarity=float(document.get(F_FAMILIARITY, 0.0)),
        seen=int(document.get(F_SEEN, 0)),
        facts=facts,
        grudges=_decay_grudges([dict(g) for g in document.get(F_GRUDGES) or []], tuning, now),
        rumours=[dict(r) for r in document.get(F_RUMOURS) or []],
        fatigue={str(k): dict(v) for k, v in (document.get(F_FATIGUE) or {}).items()},
        last_seen=float(document.get(F_LAST_SEEN) or 0.0),
    )


def to_document(state: ChatState, *, now: Optional[float] = None) -> dict[str, Any]:
    """The ``$set`` payload for a state. ``memory`` is written back as a joined
    summary purely so anything still reading the old field sees something sane."""
    now = now if now is not None else _now()
    return {
        F_AFFINITY: state.affinity,
        F_AFFINITY_AT: now,
        F_FAMILIARITY: round(state.familiarity, 4),
        F_SEEN: state.seen,
        F_FACTS: state.facts,
        F_GRUDGES: state.grudges,
        F_FATIGUE: state.fatigue,
        F_LAST_SEEN: state.last_seen or now,
        F_LEGACY_MEMORY: "; ".join(f[K_TEXT] for f in state.facts) or "No memories yet.",
    }
