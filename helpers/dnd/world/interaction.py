"""
Interaction kinds — what one person can do to another, and what it is worth.

An *interaction kind* is the unit the whole social simulation turns on. Every
time someone helps, betrays, saves or merely talks to someone else, four
questions get asked about it:

* **How big is it?** ``magnitude`` — before anybody's circumstances apply.
  Saving a life is a large thing however rich you are; talking is small however
  poor. ``mind/stakes.py`` scales this per person by capacity and need, which is
  how the same act is the end of a debtor's world and an afternoon the lord has
  already forgotten.
* **How does it move the two of them?** ``deltas``, per relationship axis,
  **written from the point of view of the person it happened to**. Debt is
  positive when *this* person owes the other. It read the other way once, and
  the man whose debt had just been cleared was recorded as the creditor.
* **How does it read?** ``phrase``, so a memory nobody wrote a gist for still
  says "Ondry kept their word to Marla" rather than "Ondry kept_word Marla".
* **May this campaign have it at all?** ``requires`` names an optional need
  (``mind/needs.OPTIONAL``) that must be switched on, which is how the romantic
  kinds stay out of a game that did not ask for them.

**These used to be four hand-maintained Python tables** — ``DELTAS``,
``PHRASES`` and ``ROMANTIC`` in ``mind/relationships.py``, ``KIND_MAGNITUDE`` in
``mind/stakes.py`` — keyed by the same strings and edited separately. They had
already drifted: the five romantic kinds were added to three of the four and
never given a magnitude, so ``lay_with`` silently fell back to the default and
was worth exactly as much as ``lied``. Nothing could have caught that, because
there was no single place the set of kinds was written down.

Now there is one, it is **data** (``helpers/dnd/data/interactions.json``), and it
resolves built-in → server → campaign like everything else configurable here. A
GM who wants *betrayed* to be the end of the world in their game changes a
number; a GM who wants an interaction the engine has never heard of adds one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helpers.dnd.world.relationship import AXES

# What a delta may name. The relationship axes, plus debt — which is a count
# people tally rather than a feeling they hold, and so is not an axis.
DELTA_FIELDS = AXES + ("debt",)

SOURCE_BUILTIN = "builtin"


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Interaction:
    """One kind of thing people do to each other."""

    key: str = ""
    label: str = ""
    phrase: str = ""
    description: str = ""
    magnitude: float = 0.4
    deltas: dict = field(default_factory=dict)
    # The optional need this kind belongs to, or "" for the ordinary ones. A
    # kind that requires something the campaign has not switched on is refused
    # rather than quietly recorded, so it cannot half-happen.
    requires: str = ""
    source: str = SOURCE_BUILTIN

    @property
    def optional(self) -> bool:
        return bool(self.requires)

    def to_doc(self) -> dict:
        return {
            "key": self.key, "label": self.label, "phrase": self.phrase,
            "description": self.description, "magnitude": self.magnitude,
            "deltas": dict(self.deltas), "requires": self.requires,
        }

    @classmethod
    def from_doc(cls, doc: dict, *, source: str = SOURCE_BUILTIN) -> "Interaction":
        doc = doc or {}
        key = str(doc.get("key") or "").strip().lower()
        # Unknown axes are dropped rather than carried, the same way a behaviour
        # pack drops weights for verbs no ruleset grants. A typo in a hand-edited
        # override must not become a field on a relationship.
        deltas = {}
        for axis, value in (doc.get("deltas") or {}).items():
            if axis not in DELTA_FIELDS:
                continue
            try:
                deltas[axis] = int(value) if axis == "debt" else _clamp(float(value))
            except (TypeError, ValueError):
                continue
        try:
            magnitude = max(0.0, min(1.0, float(doc.get("magnitude", 0.4))))
        except (TypeError, ValueError):
            magnitude = 0.4
        label = str(doc.get("label") or "").strip() or key.replace("_", " ").title()
        return cls(
            key=key,
            label=label,
            phrase=str(doc.get("phrase") or "").strip() or key.replace("_", " "),
            description=str(doc.get("description") or "").strip(),
            magnitude=magnitude,
            deltas=deltas,
            requires=str(doc.get("requires") or "").strip().lower(),
            source=source,
        )

    def felt_valence(self) -> float:
        """How an event of this kind feels, **derived from the deltas** rather
        than stored as a second number that could disagree with them.

        Affinity is the emotional axis so it leads; trust carries the kinds that
        are about reliability rather than warmth (``kept_word``, ``lied``), and
        familiarity covers the neutral ones. Doubled because the deltas are
        sized for a relationship axis and a memory's valence spans −1…1.
        """
        for axis in ("affinity", "trust", "familiarity"):
            if axis in self.deltas:
                return _clamp(float(self.deltas[axis]) * 2.0)
        return 0.0

    def actor_view(self, echo: float = 0.3) -> dict:
        """The same act, from the side of the person who *did* it.

        Two changes, and they are the whole asymmetry:

        * **Debt inverts.** If I helped you, you owe me. Same number, other sign.
        * **Feeling is an echo, not a mirror.** Doing someone a kindness warms
          you to them a little, and wronging them cools you — people devalue
          those they have harmed — but nothing like as much as being on the
          receiving end. At ``echo = 0`` the actor's feelings do not move at all.
        """
        out = {}
        for axis, base in self.deltas.items():
            if axis == "debt":
                out[axis] = -int(base)
            elif echo:
                out[axis] = base * echo
        return out


def as_deltas(catalogue: dict) -> dict[str, dict]:
    """``{kind: deltas}`` — the shape the pure relationship maths wants."""
    return {key: dict(kind.deltas) for key, kind in catalogue.items()}


def as_phrases(catalogue: dict) -> dict[str, str]:
    """``{kind: phrase}`` — the shape the gist templater wants."""
    return {key: kind.phrase for key, kind in catalogue.items()}


def as_magnitudes(catalogue: dict) -> dict[str, float]:
    """``{kind: magnitude}`` — the shape the stake maths wants."""
    return {key: kind.magnitude for key, kind in catalogue.items()}


def requiring(catalogue: dict, need: str) -> tuple:
    """Every kind gated behind one optional need."""
    return tuple(key for key, kind in catalogue.items() if kind.requires == need)
