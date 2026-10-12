"""
Behaviour packs — the shape of what somebody reaches for.

An archetype is a set of leanings across the verbs a scene can offer: a coward
reaches for the door, a merchant reaches for a conversation, a predator reaches
for you. Give an entity one to three of these, weighted, and the decision engine
has a candidate list to score instead of a flat menu of everything physically
possible (``06-DECISION-ENGINE.md`` §5).

Two things keep this from being a personality system bolted on beside the one
that already exists:

**Priors are read backwards.** ``priors`` describes the disposition an archetype
implies, and :func:`helpers.dnd.mind.behaviour.fit` asks the *reverse* question —
given who this person already is, how coward-shaped are they? Forwards it would
stamp a temperament onto anyone labelled a coward and flatten the interesting
cases; backwards it only notices. Same table, opposite causality, exactly as
``mind/traits.py`` handles roles.

**Packs weight verbs, they do not add them.** A pack can only ever reach for
something a ruleset already affords, so no archetype can propose an action the
scene will not allow, and adding an archetype can never widen what is possible.

The definitions themselves are **data** — ``helpers/dnd/data/packs.json``,
resolved built-in → server → campaign by ``helpers/dnd/packs.py``. That is the
whole point: a GM who needs a *smuggler* adds one, rather than filing an issue
about a table buried in a Python module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BehaviourPack:
    """One archetype: what it reaches for, and who tends to be it."""

    key: str = ""
    label: str = ""
    description: str = ""
    # verb → 0..1. Keys are ``rules.ruleset.AFFORDANCES``; anything else is
    # dropped on load, because a weight for a verb no ruleset grants is a
    # leaning that can never show up in play.
    weights: dict = field(default_factory=dict)
    # trait axis → −1..1, the disposition this archetype implies.
    priors: dict = field(default_factory=dict)
    # Where the definition came from, for the panel: builtin | server | campaign.
    source: str = "builtin"

    def to_doc(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "weights": {k: round(float(v), 4) for k, v in self.weights.items()},
            "priors": {k: round(float(v), 4) for k, v in self.priors.items()},
        }

    @classmethod
    def from_doc(cls, doc: dict, *, source: str = "builtin") -> "BehaviourPack":
        doc = doc or {}
        key = str(doc.get("key", "")).strip().lower()
        return cls(
            key=key,
            label=str(doc.get("label") or key.title()),
            description=str(doc.get("description", "")),
            weights=_numbers(doc.get("weights")),
            priors=_numbers(doc.get("priors"), low=-1.0),
            source=source,
        )

    def weight_for(self, verb: str) -> float:
        """How much this archetype reaches for that verb. Unlisted is zero —
        not a leaning against it, just no leaning toward it."""
        return float(self.weights.get(verb, 0.0))

    @property
    def reaches_for(self) -> list[str]:
        """The verbs this archetype is actually about, strongest first. What the
        panel shows instead of nine numbers."""
        return [v for v, _ in sorted(self.weights.items(), key=lambda p: -p[1])][:3]


def _numbers(raw, low: float = 0.0, high: float = 1.0) -> dict:
    """Clean a weight or prior map: numbers only, clamped, keys lowercased."""
    out: dict = {}
    for key, value in (raw or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        out[str(key).strip().lower()] = max(low, min(high, number))
    return out


def restricted_to(pack: BehaviourPack, verbs) -> BehaviourPack:
    """The same pack with any verb the rules do not know dropped.

    Applied on load rather than on read: a bad weight should be gone once, not
    filtered on every decision for the rest of the campaign.
    """
    allowed = set(verbs or ())
    kept = {k: v for k, v in pack.weights.items() if k in allowed}
    if kept == pack.weights:
        return pack
    return BehaviourPack(
        key=pack.key, label=pack.label, description=pack.description,
        weights=kept, priors=pack.priors, source=pack.source,
    )


@dataclass(frozen=True)
class Assignment:
    """One pack an entity carries, and how much of them it accounts for."""

    key: str = ""
    weight: float = 1.0

    def to_doc(self) -> dict:
        return {"key": self.key, "weight": round(float(self.weight), 4)}

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Assignment":
        doc = doc or {}
        return cls(key=str(doc.get("key", "")),
                   weight=max(0.0, min(1.0, float(doc.get("weight", 1.0)))))


def assignments_from(docs) -> list[Assignment]:
    return [Assignment.from_doc(d) for d in (docs or [])]


def assignments_to(items) -> list[dict]:
    return [a.to_doc() for a in (items or [])]
