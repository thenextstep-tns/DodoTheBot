"""
The memory model.

The subsystem the product lives or dies on, and the reason this is a simulation
rather than a chat wrapper. Every part of it is arithmetic over structured
records — **no model is ever consulted to remember anything.**

Five tiers::

    working   the current scene, verbatim, evicted at scene end
    mid       this arc, compressed into salience-scored episodes
    long      consolidated facts: gist + valence + confidence
    imprint   formative events — immune to decay, triggered by cues
    (impulse) not memory; an urge queue, in mind/needs.py

The idea that makes it feel like memory rather than a cache with a TTL:

    **Decay is degradation, not deletion.**

A memory's fields rot *independently and in order* — the gist survives longest,
then how it felt, then who was there, then the details, and time and place go
first. An old memory becomes "someone hurt me here, I think, years ago". Below a
threshold a field may be **confabulated** — replaced with a plausible wrong value
drawn from the entity's other memories, so they misremember *characteristically*
rather than at random.

That is what produces an NPC who remembers the wrong person holding the knife,
and is certain about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Tiers, in the order a memory travels through them.
TIER_WORKING = "working"
TIER_MID = "mid"
TIER_LONG = "long"
TIER_IMPRINT = "imprint"
TIERS = (TIER_WORKING, TIER_MID, TIER_LONG, TIER_IMPRINT)

# How long each field holds together, in days, for a neutral memory held by a
# neutral person. These are *base stabilities*, not rates: the actual span is
# this multiplied by salience, the holder's retention faculty, and how well the
# memory aligns with their values (see mind/memory/decay.py).
#
# The ordering is the whole mechanic — gist outlasts how-it-felt outlasts
# who-was-there outlasts the details, and time-and-place goes first.
FIELD_STABILITY = {
    "gist": 240.0,
    "valence": 120.0,
    "participants": 45.0,
    "details": 14.0,
    "when": 7.0,
}
DECAYING_FIELDS = tuple(FIELD_STABILITY)

# Exponent of the Ebbinghaus retention curve R(t) = (1 + t/S) ** -SHAPE.
# Higher is a sharper initial drop and a flatter tail. ~0.5 matches the classic
# forgetting-curve data reasonably well.
SHAPE = 0.5

# Fidelity thresholds for how a field renders. These are the built-in defaults;
# every one of them is overridable per server and per campaign — see
# helpers/dnd/tuning.py. Nothing in this subsystem is baked in.
CLEAR_THRESHOLD = 0.7        # above: stated plainly
HEDGE_THRESHOLD = 0.3        # above: hedged ("a woman, maybe the harbourmaster")
CONFABULATE_THRESHOLD = 0.2  # below: dropped, or filled with a plausible wrong value

# Salience at encoding that makes a memory formative, or the number of recalls
# that does the same for something merely returned to over and over. Both routes
# matter: trauma forms from one overwhelming event *or* from rehearsal.
IMPRINT_THRESHOLD = 0.85
IMPRINT_RECALLS = 8
IMPRINT_RECALL_SALIENCE = 0.6

# How precisely an entity places a memory in time, as fidelity falls away.
WHEN_PRECISION = ("exact", "day", "season", "year", "sometime")


@dataclass
class Memory:
    """One remembered event, from one witness's point of view.

    Two witnesses to the same event produce two of these, with different valence,
    different detail, and sometimes different participants. That divergence is
    where every grudge and rumour in the game comes from.
    """

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None
    entity_id: Any = None

    tier: str = TIER_WORKING
    encoded_at: int = 0                 # world time, in minutes
    last_recalled_at: int = 0
    recall_count: int = 0

    # What is remembered.
    gist: str = ""                      # decays last
    valence: float = 0.0                # -1..1, how it felt to *this* witness
    arousal: float = 0.0                # 0..1, how strongly
    participants: list = field(default_factory=list)
    location_id: Any = None
    details: list[str] = field(default_factory=list)
    when_precision: str = "exact"

    salience: float = 0.0
    fidelity: dict = field(default_factory=lambda: {f: 1.0 for f in DECAYING_FIELDS})
    confabulated: list[str] = field(default_factory=list)

    source_event_seq: int | None = None
    cues: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #
    def to_doc(self) -> dict:
        doc = {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "entity_id": self.entity_id,
            "tier": self.tier,
            "encoded_at": int(self.encoded_at),
            "last_recalled_at": int(self.last_recalled_at),
            "recall_count": int(self.recall_count),
            "gist": self.gist,
            "valence": float(self.valence),
            "arousal": float(self.arousal),
            "participants": list(self.participants),
            "location_id": self.location_id,
            "details": list(self.details),
            "when_precision": self.when_precision,
            "salience": float(self.salience),
            "fidelity": dict(self.fidelity),
            "confabulated": list(self.confabulated),
            "source_event_seq": self.source_event_seq,
            "cues": [c.lower() for c in self.cues],
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Memory":
        fidelity = {f: 1.0 for f in DECAYING_FIELDS}
        fidelity.update(doc.get("fidelity") or {})
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            entity_id=doc.get("entity_id"),
            tier=doc.get("tier", TIER_WORKING),
            encoded_at=int(doc.get("encoded_at", 0)),
            last_recalled_at=int(doc.get("last_recalled_at", 0)),
            recall_count=int(doc.get("recall_count", 0)),
            gist=str(doc.get("gist", "")),
            valence=float(doc.get("valence", 0.0)),
            arousal=float(doc.get("arousal", 0.0)),
            participants=list(doc.get("participants") or []),
            location_id=doc.get("location_id"),
            details=list(doc.get("details") or []),
            when_precision=doc.get("when_precision", "exact"),
            salience=float(doc.get("salience", 0.0)),
            fidelity=fidelity,
            confabulated=list(doc.get("confabulated") or []),
            source_event_seq=doc.get("source_event_seq"),
            cues=[str(c).lower() for c in (doc.get("cues") or [])],
        )

    # ------------------------------------------------------------------ #
    #  Presentation
    # ------------------------------------------------------------------ #
    @property
    def is_imprint(self) -> bool:
        return self.tier == TIER_IMPRINT

    def clarity_of(self, field_name: str) -> str:
        """``clear`` / ``hazy`` / ``lost`` for one field."""
        value = self.fidelity.get(field_name, 1.0)
        if value >= CLEAR_THRESHOLD:
            return "clear"
        if value >= HEDGE_THRESHOLD:
            return "hazy"
        return "lost"

    @property
    def feels(self) -> str:
        """How the memory sits, in words. Valence decays too, so a very old
        memory reports ``numb`` — you remember that it happened, not how it felt."""
        if self.fidelity.get("valence", 1.0) < HEDGE_THRESHOLD:
            return "numb"
        if self.valence <= -0.6:
            return "bitter"
        if self.valence <= -0.2:
            return "sour"
        if self.valence >= 0.6:
            return "fond"
        if self.valence >= 0.2:
            return "warm"
        return "flat"

    def describe(self) -> str:
        """The memory as its owner would tell it, hedged by what has decayed.

        This is the null-renderer view: no model involved, and it still conveys
        that someone's recollection has holes in it.
        """
        gist = self.gist if self.clarity_of("gist") != "lost" else "something happened"
        parts = [gist]

        when = self.clarity_of("when")
        if when == "clear":
            parts.append("recently" if self.when_precision == "exact" else f"about a {self.when_precision} ago")
        elif when == "hazy":
            parts.append("a while ago, maybe")
        else:
            parts.append("a long time ago")

        if self.details and self.clarity_of("details") != "lost":
            hedge = "" if self.clarity_of("details") == "clear" else "something like "
            parts.append(f"({hedge}{', '.join(self.details[:3])})")

        return " — ".join(parts)
