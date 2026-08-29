"""
The entity model.

**One model for PCs, NPCs, creatures and factions.** The differences are which
components are attached, not which class was instantiated. Two models would
guarantee drift — the PC path grows features the NPC path never gets, and NPCs
stay puppets. An NPC has to be as real as a PC or the roleplay is cosmetic.

Components that are unbounded or independently queried — memory, beliefs,
relationships — live in their **own collections** rather than inside the entity
document. Embedding them would recreate the old cog's ever-growing ``history``
string and, on a long campaign, walk into the 16 MB document ceiling. Entities
stay small and hot; minds are paged in only for entities that are thinking.

Phase note: ``traits``, ``inheritance`` and ``needs`` are declared here and left
``None`` at P0. They are part of the shape from the start so P2 can fill them in
without a migration, but nothing writes them yet — an unpopulated field is
honest, a fabricated one is not.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# What an entity is. A faction is an entity with relationships and an agenda but
# no body — no stats, no needs, no position.
KIND_PC = "pc"
KIND_NPC = "npc"
KIND_CREATURE = "creature"
KIND_FACTION = "faction"
KINDS = (KIND_PC, KIND_NPC, KIND_CREATURE, KIND_FACTION)

# Simulation tiers (docs/dnd/01-ARCHITECTURE.md §6). Cost tracks the number of
# entities on screen, not the number in the world.
TIER_FOCUS = "focus"      # in the active scene — full pipeline every tick
TIER_ACTIVE = "active"    # same region or on a clock — coarse ticks
TIER_DORMANT = "dormant"  # never ticked; extrapolated on demand
TIERS = (TIER_FOCUS, TIER_ACTIVE, TIER_DORMANT)


@dataclass
class Identity:
    """Who they are to other people."""

    name: str
    # Explicit, and defaulted to they/them. A name does not tell you someone's
    # pronouns, and guessing misgenders a player's character in a way the
    # neutral default never does — this is also why the legacy importer defaults
    # rather than inferring (docs/dnd/13-MIGRATION.md §4).
    pronouns: str = "they/them"
    species: str = ""
    role: str = ""
    appearance: str = ""
    voice: str = ""

    def to_doc(self) -> dict:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Identity":
        doc = doc or {}
        return cls(
            name=str(doc.get("name", "Unnamed")),
            pronouns=str(doc.get("pronouns") or "they/them"),
            species=str(doc.get("species", "")),
            role=str(doc.get("role", "")),
            appearance=str(doc.get("appearance", "")),
            voice=str(doc.get("voice", "")),
        )


@dataclass
class Position:
    """Where they are. Both fields optional — an entity can exist off-stage."""

    location_id: Any = None
    scene_id: Any = None

    def to_doc(self) -> dict:
        return {"location_id": self.location_id, "scene_id": self.scene_id}

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Position":
        doc = doc or {}
        return cls(location_id=doc.get("location_id"), scene_id=doc.get("scene_id"))


@dataclass
class Entity:
    """A person, creature, or faction in a campaign.

    ``stats`` is deliberately an untyped dict: its shape belongs to the
    **ruleset**, which is what lets a freeform character and a 5e character live
    in one collection without either knowing about the other.
    """

    id: Any = None
    guild_id: int = 0
    campaign_id: Any = None

    kind: str = KIND_NPC
    tier: str = TIER_DORMANT
    owner_id: int | None = None          # discord user id, for kind=pc

    identity: Identity = field(default_factory=lambda: Identity(name="Unnamed"))
    stats: dict = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)
    inventory: list[dict] = field(default_factory=list)
    position: Position = field(default_factory=Position)

    # 0..1. Drives memory budget and tier promotion (docs/dnd/05-MEMORY.md §5).
    # A nameless guard and a named questgiver should not cost the same to run.
    # **This is a simulation-cost knob and nothing else.** PCs sit at 1.0 because
    # they are always fully simulated, which says nothing about their standing in
    # the world — see `standing` below, which is the field that used to be
    # missing and got substituted for, making every PC immune to every event.
    importance: float = 0.5

    # 0..1. What they have to absorb a shock with: money, rank, security, people
    # who owe them. A merchant lord shrugs off a debt that ends a dock hand's
    # life, and that difference is what `mind/stakes.py` reads. Deliberately
    # separate from `importance`: a beloved pauper matters enormously to the
    # story and can still be ruined by four marks.
    #
    # Middling by default, because most people are. Rulesets that model wealth
    # can derive it; until one does, it is set per entity.
    standing: float = 0.5

    # 0..1. How strongly people tend to be drawn to them — bearing, presence,
    # whatever the fiction wants it to be. Deliberately *not* a beauty score
    # handed down by the engine: it is one input to a **directed** attraction
    # that mostly turns on what the two of them are to each other, so a plain
    # person who is trusted and familiar can be wanted far more than a striking
    # stranger. Middling by default, set per entity like `standing`, and only
    # read at all when a campaign has switched desire on.
    allure: float = 0.5

    # Declared for P2; nothing writes them yet.
    traits: dict | None = None
    inheritance: dict | None = None
    needs: dict | None = None

    # What they are trying to bring about (``world/goal.py``). Embedded rather
    # than given a collection because goals are bounded by a tunable and are
    # never read without the person whose goals they are — the opposite of
    # memory and beliefs, which is why those got collections and this did not.
    goals: list | None = None

    # Which behaviour archetypes they are drawn from, weighted
    # (``world/pack.py``). Assigned at generation from their disposition, and
    # editable after: the definitions are campaign configuration, but *who is
    # what* is a fact about this person.
    packs: list | None = None

    # World time this entity's memories were last decayed. A ``dormant`` one is
    # not ticked at all (``06-DECISION-ENGINE.md`` §9), so it falls behind on
    # purpose and the arrears are paid when something finally looks at it —
    # which is what makes a world of five hundred people cost nothing to keep.
    aged_at: int = 0

    retired: bool = False
    legacy_id: Any = None                # set by the importer, for idempotency

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #
    def to_doc(self) -> dict:
        """A BSON-safe document. ``_id`` is omitted when unset so an insert lets
        Mongo assign one."""
        doc: dict = {
            "guild_id": self.guild_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind,
            "tier": self.tier,
            "owner_id": self.owner_id,
            "identity": self.identity.to_doc(),
            "stats": self.stats,
            "conditions": list(self.conditions),
            "inventory": list(self.inventory),
            "position": self.position.to_doc(),
            "importance": float(self.importance),
            "standing": float(self.standing),
            "allure": float(self.allure),
            "traits": self.traits,
            "inheritance": self.inheritance,
            "needs": self.needs,
            "goals": list(self.goals) if self.goals else [],
            "aged_at": int(self.aged_at),
            "packs": list(self.packs) if self.packs else [],
            "retired": bool(self.retired),
        }
        if self.legacy_id is not None:
            doc["legacy_id"] = self.legacy_id
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_doc(cls, doc: dict) -> "Entity":
        return cls(
            id=doc.get("_id"),
            guild_id=int(doc.get("guild_id", 0)),
            campaign_id=doc.get("campaign_id"),
            kind=doc.get("kind", KIND_NPC),
            tier=doc.get("tier", TIER_DORMANT),
            owner_id=doc.get("owner_id"),
            identity=Identity.from_doc(doc.get("identity")),
            stats=doc.get("stats") or {},
            conditions=list(doc.get("conditions") or []),
            inventory=list(doc.get("inventory") or []),
            position=Position.from_doc(doc.get("position")),
            importance=float(doc.get("importance", 0.5)),
            standing=float(doc.get("standing", 0.5)),
            allure=float(doc.get("allure", 0.5)),
            traits=doc.get("traits"),
            inheritance=doc.get("inheritance"),
            needs=doc.get("needs"),
            goals=list(doc.get("goals") or []) or None,
            aged_at=int(doc.get("aged_at", 0)),
            packs=list(doc.get("packs") or []) or None,
            retired=bool(doc.get("retired", False)),
            legacy_id=doc.get("legacy_id"),
        )

    # ------------------------------------------------------------------ #
    #  Convenience
    # ------------------------------------------------------------------ #
    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def is_pc(self) -> bool:
        return self.kind == KIND_PC
