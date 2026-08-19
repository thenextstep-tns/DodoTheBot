"""
Relationships — directed, and multi-axis.

``A → B`` is not ``B → A``, and that asymmetry is most of the drama: the guard
who fears you while you barely remember him is a scene; mutual dislike is a
statistic.

Five axes rather than one "friendliness" number, because they come apart in ways
that matter. Someone can trust you and not like you (a competent rival), fear you
and respect you (a beaten duellist), or like you while owing you nothing. Collapse
them and every NPC reduces to the same slider.

Updated **only from events**, never by a language model — see
``helpers/dnd/mind/relationships.py`` for the deltas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The axes. All -1..1 except debt, which is a count.
AXES = ("affinity", "trust", "fear", "respect", "familiarity")

AXIS_LABELS = {
    "affinity": "Affinity",       # dislike ↔ like
    "trust": "Trust",             # suspect ↔ rely on
    "fear": "Fear",               # unafraid ↔ afraid
    "respect": "Respect",         # contempt ↔ regard
    "familiarity": "Familiarity",  # stranger ↔ well known
}


@dataclass
class Relationship:
    """How one entity stands toward another."""

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None

    from_id: Any = None
    to_id: Any = None

    affinity: float = 0.0
    trust: float = 0.0
    fear: float = 0.0
    respect: float = 0.0
    familiarity: float = 0.0
    # Negative means *they* owe *you*. Kept as a count rather than a -1..1 axis
    # because a debt is a discrete thing people tally, not a feeling they have.
    debt: int = 0

    updated_at: int = 0     # world time

    def to_doc(self) -> dict:
        doc = {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "debt": int(self.debt),
            "updated_at": int(self.updated_at),
        }
        for axis in AXES:
            doc[axis] = round(float(getattr(self, axis)), 4)
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Relationship":
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            from_id=doc.get("from_id"),
            to_id=doc.get("to_id"),
            affinity=float(doc.get("affinity", 0.0)),
            trust=float(doc.get("trust", 0.0)),
            fear=float(doc.get("fear", 0.0)),
            respect=float(doc.get("respect", 0.0)),
            familiarity=float(doc.get("familiarity", 0.0)),
            debt=int(doc.get("debt", 0)),
            updated_at=int(doc.get("updated_at", 0)),
        )

    # ------------------------------------------------------------------ #
    #  Presentation
    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        """How this reads in a sentence — the strongest thing they feel.

        Checked strongest-first rather than by a fixed axis order, so an NPC who
        both likes and fears you reads as afraid, which is what would actually
        govern their behaviour in the room.
        """
        if self.familiarity < 0.1 and abs(self.affinity) < 0.15 and self.fear < 0.15:
            return "a stranger"

        candidates = [
            (abs(self.fear), "afraid of them" if self.fear > 0 else ""),
            (abs(self.affinity), "fond of them" if self.affinity > 0 else "dislikes them"),
            (abs(self.trust), "trusts them" if self.trust > 0 else "suspicious of them"),
            (abs(self.respect), "respects them" if self.respect > 0 else "contemptuous of them"),
        ]
        strength, phrase = max(candidates, key=lambda pair: pair[0])
        if strength < 0.15:
            return "indifferent"
        if self.debt > 0:
            phrase += f", and owes them {self.debt}"
        elif self.debt < 0:
            phrase += f", and is owed {abs(self.debt)}"
        return phrase

    def as_dict(self) -> dict:
        return {axis: getattr(self, axis) for axis in AXES} | {"debt": self.debt}
