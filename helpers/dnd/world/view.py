"""
The projection an NPC decides from.

    **NPC decisions read beliefs. Never world truth.**

That rule has held so far by discipline: every function that touches a mind
*happened* to be handed the right things. Discipline does not survive a decision
engine with six stages and eight scoring terms, so this module makes the rule
structural. :func:`project` is the only door between the world and
``mind/decide.py``, and what comes out the other side is an :class:`EntityView` —
one entity's beliefs, memories, needs and traits, and nothing else.

Three things the engine therefore *cannot* do, however carelessly it is written:

* **read a fact it does not believe** — the view holds beliefs, not knowledge;
* **read the GM's ``truth`` flag** on a belief. It is not a field on
  :class:`HeldBelief`. An NPC who knew their own belief was false would not be
  holding a belief, they would be lying, which is a different act entirely;
* **read a memory as it was encoded** — a :class:`Recollection` has already had
  decay applied, so a faded memory arrives faded. The engine sees what they
  remember, not what happened.

It also cannot *write*: every dataclass here is frozen and every mapping is a
read-only proxy. A decision that mutated the mind it was reading would break
replay, and replay is how a campaign is debugged.

Pure, like the rest of this layer: no I/O, no configuration reads, no RNG.
``helpers/dnd/minds.py`` loads the records and calls :func:`project`; the limits
below arrive as an argument, resolved at that edge.

Building a view deliberately does **not** reconsolidate the memories it draws
on. Thinking about something does rewrite it (``mind/memory/recall.py``), but a
view is built for every NPC on every tick, and a world where 200 minds rewrite
their own history in the background four times an hour is a write storm and a
world that drifts while nobody is playing in it. Reconsolidation belongs to the
commit step, where an NPC has actually acted on the memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

from helpers.dnd.world.belief import Belief
from helpers.dnd.world.entity import Entity
from helpers.dnd.world.memory import Memory
from helpers.dnd.world.relationship import AXES, Relationship

if TYPE_CHECKING:  # pragma: no cover - types only
    # Imported for annotation only. At runtime ``helpers.dnd.tuning`` imports
    # this layer, so importing it back here would be a cycle.
    from helpers.dnd.tuning import PerceptionTuning


# --------------------------------------------------------------------------- #
#  Defaults
#
#  The source of truth for these numbers, the way memory.FIELD_STABILITY is for
#  forgetting. `helpers/dnd/tuning.py` reads them as the defaults of the
#  tunables that override them, so there is one number, in one place.
# --------------------------------------------------------------------------- #
# How much of a mind reaches one decision. Caps rather than truths: a person has
# more memories than they bring to bear on whether to run.
MEMORY_LIMIT = 12
BELIEF_LIMIT = 20
RELATIONSHIP_LIMIT = 40

# Below this confidence a belief is a half-remembered thing someone said once,
# and does not sway a choice.
BELIEF_FLOOR = 0.15
# Below this clarity a memory does not come to mind at all. Above it, it comes
# to mind in whatever state decay has left it in.
CLARITY_FLOOR = 0.15
# Familiarity below which someone is a stranger: a face, no name. Nobody knows
# the name of the man who just walked in, and that is most of a first meeting.
STRANGER_FLOOR = 0.05

# What an unnamed person is to the viewer. Not a display string — the null
# renderer decides how to phrase it; this is the absence of a name.
UNKNOWN_NAME = ""

# Display only: which needs :meth:`EntityView.describe` bothers to mention. It
# mirrors the needs impulse threshold rather than reading it, because this layer
# may not import ``mind/`` — and because nothing behavioural hangs on it. What an
# NPC *does* about a need is the decision engine's business, and tunable there.
PRESSING = 0.55


def _empty_map() -> Mapping:
    return MappingProxyType({})


# --------------------------------------------------------------------------- #
#  A memory, as it comes back
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Recollection:
    """One memory as its owner has it *now*, decay already applied.

    Fields that have faded past legibility are simply absent — an empty ``gist``
    is a memory of something they cannot place, a zero ``valence`` on a numb
    recollection is genuinely no feeling left, and lost ``participants`` means
    they could not tell you who was there. The engine never learns what was
    originally encoded, because it is never given it.
    """

    memory_id: Any = None
    gist: str = ""
    valence: float = 0.0
    arousal: float = 0.0
    salience: float = 0.0
    clarity: float = 1.0
    participants: tuple = ()
    details: tuple[str, ...] = ()
    location_id: Any = None
    when: str = "unknown"
    encoded_at: int = 0
    is_imprint: bool = False
    numb: bool = False

    @property
    def lost(self) -> bool:
        """Nothing usable left. Kept out of a view by the clarity floor, but a
        floor of 0 lets these through, which is a legitimate setting."""
        return not self.gist

    @property
    def weight(self) -> float:
        """How loudly this one speaks up. Salience is what it was worth; clarity
        is how much of it survived."""
        return max(0.0, self.salience) * max(0.0, self.clarity)


def recollect(memory: Memory) -> Recollection:
    """Project one stored memory into what its owner can actually retrieve."""
    gist_lost = memory.clarity_of("gist") == "lost"
    numb = memory.feels == "numb"
    when_clarity = memory.clarity_of("when")
    if when_clarity == "clear":
        when = memory.when_precision
    elif when_clarity == "hazy":
        when = "vague"
    else:
        when = "unknown"

    return Recollection(
        memory_id=memory.id,
        gist="" if gist_lost else memory.gist,
        valence=0.0 if numb else float(memory.valence),
        arousal=float(memory.arousal),
        salience=float(memory.salience),
        clarity=float(memory.fidelity.get("gist", 1.0)),
        # Faces go before details, and time and place go first of all — so a
        # memory can arrive as "someone hurt me, I think, a while ago".
        participants=() if memory.clarity_of("participants") == "lost"
        else tuple(memory.participants),
        details=() if memory.clarity_of("details") == "lost" else tuple(memory.details),
        location_id=None if when == "unknown" else memory.location_id,
        when=when,
        encoded_at=int(memory.encoded_at),
        is_imprint=memory.is_imprint,
        numb=numb,
    )


# --------------------------------------------------------------------------- #
#  A belief, as it is held
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HeldBelief:
    """Something the viewer takes to be true, and how sure they are.

    Deliberately **not** a :class:`~helpers.dnd.world.belief.Belief`: that record
    carries ``truth``, which is the GM's marking of whether the claim is actually
    so. Passing the record through would put world truth one attribute access
    away from every scoring term in the engine, and eventually somebody reads it.
    """

    subject_id: Any = None
    claim: str = ""
    confidence: float = 0.0
    certainty: str = "unsure"
    source_kind: str = ""
    source_id: Any = None
    at: int = 0
    mutations: int = 0

    @property
    def secondhand(self) -> bool:
        """They were told this, or it has changed hands since. Worth knowing when
        deciding whether to act on it in front of the person it is about."""
        return self.source_kind != "witnessed" or self.mutations > 0


def held(belief: Belief) -> HeldBelief:
    """Project one stored belief into what its holder has of it."""
    return HeldBelief(
        subject_id=belief.subject_id,
        claim=belief.claim,
        confidence=float(belief.confidence),
        certainty=belief.certainty,
        source_kind=belief.source_kind,
        source_id=belief.source_id,
        at=int(belief.at),
        mutations=int(belief.mutations),
    )


# --------------------------------------------------------------------------- #
#  Another person, as this one knows them
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PerceivedEntity:
    """Somebody else, through one pair of eyes.

    The regard axes are the viewer's own ``A → B`` relationship and nobody
    else's, which is why a decision can turn on fearing someone who has never
    given you a thought.
    """

    entity_id: Any = None
    name: str = UNKNOWN_NAME
    kind: str = ""
    known: bool = False

    affinity: float = 0.0
    trust: float = 0.0
    fear: float = 0.0
    respect: float = 0.0
    familiarity: float = 0.0
    debt: int = 0

    beliefs: tuple[HeldBelief, ...] = ()

    @property
    def stranger(self) -> bool:
        return not self.known

    # Two named properties rather than one signed number, because the sign has
    # been read backwards here once already and the fix cost a playtest
    # (``mind/relationships.py``). ``debt`` is positive when the *viewer* is the
    # one who owes.
    @property
    def i_owe_them(self) -> int:
        return max(0, self.debt)

    @property
    def they_owe_me(self) -> int:
        return max(0, -self.debt)

    @property
    def prominence(self) -> float:
        """How much this person figures in the viewer's life at all. Used to
        decide who is worth carrying into a decision when the cap bites."""
        return max(
            abs(self.affinity), abs(self.trust), abs(self.fear),
            abs(self.respect), abs(self.familiarity),
            min(1.0, abs(self.debt) / 5.0),
            0.34 if self.beliefs else 0.0,
        )


def _perceive(relationship: Relationship | None, entity_id: Any,
              identity: Mapping | None, beliefs: tuple[HeldBelief, ...],
              stranger_floor: float) -> PerceivedEntity:
    """One row of ``others``. Never sees the subject's own record — only what the
    viewer stands toward them and what the viewer believes about them."""
    identity = identity or {}
    axes = {axis: float(getattr(relationship, axis, 0.0)) for axis in AXES} if relationship \
        else {axis: 0.0 for axis in AXES}
    known = axes["familiarity"] >= stranger_floor
    return PerceivedEntity(
        entity_id=entity_id,
        name=str(identity.get("name") or UNKNOWN_NAME) if known else UNKNOWN_NAME,
        kind=str(identity.get("kind") or ""),
        known=known,
        debt=int(getattr(relationship, "debt", 0) or 0),
        beliefs=beliefs,
        **axes,
    )


# --------------------------------------------------------------------------- #
#  The view itself
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EntityView:
    """Everything one entity has to decide with, and nothing else.

    ``traits`` and ``needs`` are read-only mappings rather than the ``mind/``
    dataclasses, because this layer must not import ``mind/`` — and because a
    projection should be inert data, not an object with behaviour the engine can
    call into.
    """

    entity_id: Any = None
    name: str = ""
    kind: str = ""
    role: str = ""
    world_time: int = 0

    # Self-knowledge. You know your own station, your own wounds, where you are.
    # ``importance`` is deliberately absent: it is a simulation-cost knob, not a
    # fact about the person, and reading it as one made every PC immune to every
    # event once already.
    standing: float = 0.5
    conditions: tuple[str, ...] = ()
    location_id: Any = None
    scene_id: Any = None

    traits: Mapping[str, float] = field(default_factory=_empty_map)
    ideals: tuple[str, ...] = ()
    flaws: tuple[str, ...] = ()

    needs: Mapping[str, float] = field(default_factory=_empty_map)

    beliefs: tuple[HeldBelief, ...] = ()
    memories: tuple[Recollection, ...] = ()
    others: Mapping[Any, PerceivedEntity] = field(default_factory=_empty_map)

    # ------------------------------------------------------------------ #
    #  Reading a view
    # ------------------------------------------------------------------ #
    def trait(self, name: str, default: float = 0.0) -> float:
        return float(self.traits.get(name, default))

    def need(self, name: str, default: float = 0.0) -> float:
        return float(self.needs.get(name, default))

    def of(self, entity_id: Any) -> PerceivedEntity:
        """How the viewer stands toward somebody. A person they have never met
        and never heard of comes back as a stranger rather than as ``None``, so
        the engine has no null path to forget about."""
        found = self.others.get(entity_id)
        if found is not None:
            return found
        return PerceivedEntity(entity_id=entity_id)

    def confidence_in(self, claim: str) -> float:
        """How sure they are of a claim. ``0`` means they have never heard it —
        which is not the same as disbelieving it, and the engine should treat the
        two differently."""
        wanted = claim.strip().lower()
        for belief in self.beliefs:
            if belief.claim.strip().lower() == wanted:
                return belief.confidence
        return 0.0

    def believes(self, claim: str, at_least: float = 0.0) -> bool:
        """Whether they hold a claim firmly enough to act on it. The default is
        0 rather than :data:`BELIEF_FLOOR` on purpose: anything still in the view
        has already cleared the campaign's floor, and a second gate here would
        quietly disagree with a GM who moved it."""
        return self.confidence_in(claim) > 0 and self.confidence_in(claim) >= at_least

    def beliefs_about(self, subject_id: Any) -> tuple[HeldBelief, ...]:
        return self.of(subject_id).beliefs

    def recalls(self, cue: str) -> tuple[Recollection, ...]:
        """Recollections whose gist mentions something. A convenience for the
        inspector and for tests; the engine gets its memories cue-selected at the
        edge, the way recall actually works."""
        needle = cue.strip().lower()
        return tuple(m for m in self.memories if needle and needle in m.gist.lower())

    @property
    def strongest_memory(self) -> Recollection | None:
        return self.memories[0] if self.memories else None

    def describe(self, pressing_above: float = PRESSING) -> str:
        """One line, for the inspector and for a decision trace's header."""
        who = self.name or "someone"
        pressing = [n for n, v in sorted(self.needs.items(), key=lambda p: -p[1])
                    if v >= pressing_above][:2]
        body = ", ".join(pressing) if pressing else "comfortable"
        return (f"{who} — {body}; {len(self.beliefs)} belief(s), "
                f"{len(self.memories)} recollection(s), knows {len(self.others)}")


# --------------------------------------------------------------------------- #
#  Building one
# --------------------------------------------------------------------------- #
def _limits(perception: "PerceptionTuning | None") -> tuple:
    """The six caps and floors, defaulted. Duck-typed rather than imported —
    see the note at the top of the file."""
    if perception is None:
        return (MEMORY_LIMIT, BELIEF_LIMIT, RELATIONSHIP_LIMIT,
                BELIEF_FLOOR, CLARITY_FLOOR, STRANGER_FLOOR)
    return (
        int(getattr(perception, "memory_limit", MEMORY_LIMIT)),
        int(getattr(perception, "belief_limit", BELIEF_LIMIT)),
        int(getattr(perception, "relationship_limit", RELATIONSHIP_LIMIT)),
        float(getattr(perception, "belief_floor", BELIEF_FLOOR)),
        float(getattr(perception, "clarity_floor", CLARITY_FLOOR)),
        float(getattr(perception, "stranger_floor", STRANGER_FLOOR)),
    )


def _capped(items: list, limit: int) -> list:
    """A cap of 0 means no cap — that is how every limit here switches off."""
    return items if limit <= 0 else items[:limit]


def project(
    entity: Entity,
    *,
    world_time: int,
    needs: Mapping[str, float] | None = None,
    traits: Mapping[str, Any] | None = None,
    memories: list[Memory] | tuple = (),
    beliefs: list[Belief] | tuple = (),
    relations: list[Relationship] | tuple = (),
    identities: Mapping[Any, Mapping] | None = None,
    include: tuple = (),
    perception: "PerceptionTuning | None" = None,
) -> EntityView:
    """Build the view one entity decides from.

    ``needs`` and ``traits`` are the plain dicts an entity stores them as,
    already brought up to ``world_time`` by the caller — this layer may not
    import ``mind/``, and would have no business advancing them anyway.

    ``identities`` maps entity id → ``{"name", "kind"}`` for the people the
    viewer might name; anyone missing from it, and anyone too unfamiliar to
    recognise, arrives nameless. ``include`` names ids that must appear in
    ``others`` whether or not the viewer knows them — the strangers who just
    walked into the scene.
    """
    memory_limit, belief_limit, relation_limit, \
        belief_floor, clarity_floor, stranger_floor = _limits(perception)
    identities = identities or {}

    # --- what they believe --------------------------------------------- #
    convictions = [held(b) for b in beliefs if b.confidence >= belief_floor]
    convictions.sort(key=lambda b: (-b.confidence, -b.at, b.claim))
    convictions = _capped(convictions, belief_limit)

    by_subject: dict = {}
    for conviction in convictions:
        if conviction.subject_id is not None:
            by_subject.setdefault(conviction.subject_id, []).append(conviction)

    # --- what they remember -------------------------------------------- #
    recalled = [recollect(m) for m in memories]
    recalled = [r for r in recalled if r.clarity >= clarity_floor]
    recalled.sort(key=lambda r: (-r.weight, -r.encoded_at, str(r.memory_id)))
    recalled = _capped(recalled, memory_limit)

    # --- who they know -------------------------------------------------- #
    # Everyone the viewer has a relationship with, everyone they hold a belief
    # about, and everyone the caller insists on. Someone can be in the second
    # group and not the first: you can have heard of a person you have never met.
    seen: dict = {}
    for relationship in relations:
        other_id = relationship.to_id
        if other_id is None or other_id == entity.id:
            continue
        seen[other_id] = _perceive(
            relationship, other_id, identities.get(other_id),
            tuple(by_subject.get(other_id, ())), stranger_floor,
        )
    for subject_id in by_subject:
        if subject_id not in seen and subject_id != entity.id:
            seen[subject_id] = _perceive(
                None, subject_id, identities.get(subject_id),
                tuple(by_subject[subject_id]), stranger_floor,
            )

    ranked = sorted(seen.values(), key=lambda p: (-p.prominence, str(p.entity_id)))
    ranked = _capped(ranked, relation_limit)
    others = {p.entity_id: p for p in ranked}

    # Anyone present must be visible to the engine even if the cap dropped them
    # and even if they are a total stranger — you can see the man you do not know.
    for other_id in include:
        if other_id is not None and other_id != entity.id and other_id not in others:
            others[other_id] = seen.get(other_id) or _perceive(
                None, other_id, identities.get(other_id), (), stranger_floor,
            )

    trait_doc = dict(traits or entity.traits or {})
    numeric = {k: float(v) for k, v in trait_doc.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
    need_doc = {k: float(v) for k, v in dict(needs or entity.needs or {}).items()
                if k != "ticked_at" and isinstance(v, (int, float))}

    return EntityView(
        entity_id=entity.id,
        name=entity.identity.name,
        kind=entity.kind,
        role=entity.identity.role,
        world_time=int(world_time),
        standing=float(entity.standing),
        conditions=tuple(entity.conditions),
        location_id=entity.position.location_id,
        scene_id=entity.position.scene_id,
        traits=MappingProxyType(numeric),
        ideals=tuple(trait_doc.get("ideals") or ()),
        flaws=tuple(trait_doc.get("flaws") or ()),
        needs=MappingProxyType(need_doc),
        beliefs=tuple(convictions),
        memories=tuple(recalled),
        others=MappingProxyType(others),
    )
