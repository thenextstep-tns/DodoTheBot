"""
Minds, joined to storage.

``mind/`` is pure — functions of their arguments and an injected RNG, no I/O.
This module is the thin orchestration layer above it: load state, run the pure
functions, write the result back. Keeping the two apart is what lets the entire
memory model be tested without a database, and it is why nothing in ``mind/``
knows a repository exists.

Everything here takes an explicit ``world_time`` and ``rng``. Neither is read
from the environment, because a campaign has to replay identically.
"""

from __future__ import annotations

from random import Random
from typing import Any

from helpers.dnd.mind import needs as needs_mod
from helpers.dnd.mind import relationships as rel_mod
from helpers.dnd.mind import stakes
from helpers.dnd.mind import traits as traits_mod
from helpers.dnd.mind.memory import consolidate, decay, encode, recall
from helpers.dnd.mind.memory import values as value_model
from helpers.dnd.tuning import Tuning
from helpers.dnd.world.entity import (
    KIND_NPC,
    TIER_ACTIVE,
    Entity,
    Identity,
)
from helpers.dnd.world.memory import TIER_WORKING, Memory
from helpers.dnd.world.relationship import Relationship

MINUTES_PER_DAY = 1440


# --------------------------------------------------------------------------- #
#  Reading a mind
# --------------------------------------------------------------------------- #
def tuning_for(store, campaign=None) -> Tuning:
    """Resolved tunables for this campaign: defaults, then server, then campaign.

    Built once per command and handed down. Every function below accepts one, so
    a GM's settings reach the pure layer without any of it performing a lookup.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    return Tuning.for_campaign(store.guild_id, campaign)


def traits_of(entity: Entity) -> traits_mod.Traits:
    return traits_mod.Traits.from_doc(entity.traits)


def needs_of(entity: Entity, world_time: int, tuning: Tuning | None = None) -> needs_mod.Needs:
    """Needs brought up to date. Works for a dormant entity too — the closed-form
    advance is the same function a live tick uses."""
    current = needs_mod.Needs.from_doc(entity.needs)
    if tuning is None:
        return needs_mod.advanced(current, world_time)
    return needs_mod.advanced(current, world_time, tuning.needs())


def impulses_of(entity: Entity, world_time: int, tuning: Tuning | None = None) -> list:
    view = tuning.needs() if tuning else needs_mod.DEFAULT_NEEDS
    return needs_mod.from_needs(needs_of(entity, world_time, tuning), world_time, view)


def value_alignment(entity: Entity, memory: Memory) -> float:
    """How well a memory sits with this entity's values — for the inspector."""
    return value_model.alignment(memory, traits_of(entity))


def explain_retention(entity: Entity, memory: Memory) -> str:
    """Why this memory is sticking, or why it isn't. Shown per memory to the GM."""
    return value_model.explain(memory, traits_of(entity))


# --------------------------------------------------------------------------- #
#  Forming memories
# --------------------------------------------------------------------------- #
def remember(
    store,
    entity: Entity,
    gist: str,
    *,
    world_time: int,
    rng: Random,
    valence: float = 0.0,
    participants=None,
    details=None,
    perception: float = 1.0,
    salience_scale: float = 1.0,
    location_id: Any = None,
    source_event_seq: int | None = None,
    tuning: Tuning | None = None,
) -> Memory | None:
    """Form and store one entity's memory of something.

    Returns ``None`` when perception was too poor to register anything — they
    were there and they remember nothing, which is a legitimate outcome.
    """
    tuning = tuning or tuning_for(store)
    memory_tuning, salience_tuning = tuning.memory(), tuning.salience()

    affinities = rel_mod.affinity_map(store.relations.outgoing(entity.id))
    memory = encode.encode(
        witness_id=entity.id,
        gist=gist,
        world_time=world_time,
        rng=rng,
        valence=valence,
        participants=participants,
        details=details,
        location_id=location_id,
        traits=traits_of(entity),
        perception=perception,
        salience_scale=salience_scale,
        relationship_to_actor=_actor_affinity(affinities, participants, entity.id),
        existing_gists=store.memories.gists_of(entity.id),
        affinities=affinities,
        source_event_seq=source_event_seq,
        salience_tuning=salience_tuning,
        memory_tuning=memory_tuning,
    )
    if memory is None:
        return None

    # Something overwhelming imprints at once, without waiting for a decay pass.
    if decay.should_imprint(
        memory, retention=traits_of(entity).retention, tuning=memory_tuning
    ):
        decay.promote(memory)

    store.memories.add(memory)
    enforce_budget(store, entity, world_time, tuning=tuning)
    return memory


def _actor_affinity(affinities: dict, participants, witness_id) -> float:
    """How the witness feels about whoever else was involved."""
    for person in participants or []:
        if person != witness_id and person in affinities:
            return affinities[person]
    return 0.0


def witness_event(
    store,
    witnesses: list[tuple[Entity, float]],
    gist: str,
    *,
    world_time: int,
    rng: Random,
    valence: float = 0.0,
    participants=None,
    details=None,
    location_id: Any = None,
    source_event_seq: int | None = None,
    tuning: Tuning | None = None,
) -> dict:
    """One event, several witnesses, one memory each — and they will differ.

    ``witnesses`` is ``[(entity, perception)]``. This is the function that makes
    the world generative: nobody agrees on what happened, because nobody saw the
    same thing.
    """
    tuning = tuning or tuning_for(store)
    formed = {}
    for entity, perception in witnesses:
        formed[entity.id] = remember(
            store,
            entity,
            gist,
            world_time=world_time,
            rng=rng,
            valence=valence,
            participants=participants,
            details=details,
            perception=perception,
            location_id=location_id,
            source_event_seq=source_event_seq,
            tuning=tuning,
        )
    return formed


# --------------------------------------------------------------------------- #
#  Recall
# --------------------------------------------------------------------------- #
def recall_for(
    store,
    entity: Entity,
    cues,
    *,
    world_time: int,
    rng: Random,
    limit: int = 5,
    present_details=None,
    reconsolidate: bool = True,
    tuning: Tuning | None = None,
) -> list[Memory]:
    """What these cues bring to mind — and, by default, rewrite in the bringing.

    ``reconsolidate=False`` is for the GM inspector, which must be able to look
    without changing what it is looking at.
    """
    tuning = tuning or tuning_for(store)
    memory_tuning = tuning.memory()
    retention = traits_of(entity).retention

    memories = store.memories.for_entity(entity.id)
    hits = recall.recall(memories, cues, world_time, limit=limit)
    if not reconsolidate:
        return hits

    for memory in hits:
        recall.reconsolidate(memory, world_time, rng, present_details=present_details)
        if decay.should_imprint(memory, retention=retention, tuning=memory_tuning):
            decay.promote(memory)
        store.memories.save(memory)
    return hits


def imprint_triggered(store, entity: Entity, cues, world_time: int) -> Memory | None:
    """Whether a scene has just set off one of this entity's imprints.

    A dramatic event rather than a lookup — the moment the NPC goes quiet.
    """
    return recall.triggered_by(store.memories.imprints(entity.id), cues, world_time)


# --------------------------------------------------------------------------- #
#  The passage of time
# --------------------------------------------------------------------------- #
def age_entity(store, entity: Entity, days: float, *, world_time: int, rng: Random,
               tuning: Tuning | None = None) -> dict:
    """Decay one entity's memories, promote imprints, enforce the budget.

    Returns a small report so a GM-facing command can say what actually changed
    rather than claiming success silently.
    """
    tuning = tuning or tuning_for(store)
    memory_tuning = tuning.memory()
    entity_traits = traits_of(entity)

    memories = store.memories.for_entity(entity.id)
    before_imprints = sum(1 for m in memories if m.is_imprint)

    decay.age_all(memories, days, rng, traits=entity_traits, tuning=memory_tuning)

    # Fill confabulated fields from this entity's *other* memories, so the
    # mistake is characteristically theirs.
    pool = store.memories.detail_pool(entity.id)
    for memory in memories:
        if memory.confabulated:
            decay.substitute(memory, pool, rng)
    store.memories.save_all(memories)

    pruned = enforce_budget(store, entity, world_time, tuning=tuning)
    after = store.memories.for_entity(entity.id)
    return {
        "aged": len(memories),
        "new_imprints": sum(1 for m in after if m.is_imprint) - before_imprints,
        "confabulated": sum(1 for m in after if m.confabulated),
        "pruned": pruned,
        "frozen": memory_tuning.frozen,
    }


def enforce_budget(store, entity: Entity, world_time: int,
                   tuning: Tuning | None = None) -> int:
    """Bring an entity back inside its memory budget. Returns how many went.

    The bounded-cost guarantee: an entity's memory has a ceiling proportional to
    how much it matters, so a world of 500 NPCs is a fixed bill.
    """
    tuning = tuning or tuning_for(store)
    memories = store.memories.for_entity(entity.id)
    surviving, pruned = consolidate.prune(
        memories, entity.importance, world_time, tuning.memory()
    )
    if not pruned:
        return 0

    summary = consolidate.summarise(pruned, entity.id, world_time)
    store.memories.forget_many(pruned)
    if summary is not None:
        store.memories.add(summary)
    return len(pruned)


def close_scene(store, entities: list[Entity], world_time: int,
                tuning: Tuning | None = None) -> dict:
    """End of scene: working memories are promoted or let go.

    ``05-MEMORY.md`` §1 defines the working tier as *"current scene, verbatim,
    evicted at scene end"*, and §8 says consolidation runs at scene end. Both
    ``consolidate_scene`` and ``consolidate_arc`` were written and then called
    from nowhere, so nothing ever left the working tier: a decade-old memory
    still sat in the tier that is supposed to hold the last ten minutes, the
    per-tier budgets never applied, and the inspector filed everything under
    **Right now** forever.

    What survives moves to ``mid``. What does not is dropped, and what is
    dropped leaves a summary, so a scene compresses to its substance rather
    than vanishing.

    Returns ``{entity_id: (promoted, dropped)}`` so the GM can be told.
    """
    tuning = tuning or tuning_for(store)
    report = {}
    for entity in entities:
        working = store.memories.for_entity(entity.id, tier=TIER_WORKING)
        if not working:
            continue
        kept, dropped = consolidate.consolidate_scene(working)
        if kept:
            store.memories.save_all(kept)
        if dropped:
            summary = consolidate.summarise(dropped, entity.id, world_time)
            store.memories.forget_many(dropped)
            if summary is not None:
                store.memories.add(summary)
        # Promotion can push a tier past its cap, so the budget runs after.
        enforce_budget(store, entity, world_time, tuning=tuning)
        report[entity.id] = (len(kept), len(dropped))
    return report


def advance(store, campaign, days: float, rng: Random) -> dict:
    """Move the whole campaign forward, ageing every mind in it.

    P2's manual stand-in for the world tick that arrives in P3 — the same
    functions, driven by a GM command instead of a schedule.
    """
    tuning = tuning_for(store, campaign)
    minutes = int(days * MINUTES_PER_DAY)
    world_time = store.campaigns.advance_time(campaign.id, minutes)

    report = {"days": days, "world_time": world_time, "entities": 0,
              "new_imprints": 0, "pruned": 0, "confabulated": 0,
              "frozen": tuning.memory().frozen}

    for entity in store.entities.list(include_retired=False):
        outcome = age_entity(
            store, entity, days, world_time=world_time, rng=rng, tuning=tuning
        )
        report["entities"] += 1
        report["new_imprints"] += max(0, outcome["new_imprints"])
        report["pruned"] += outcome["pruned"]
        report["confabulated"] += outcome["confabulated"]

        # Needs advance for everyone; only their *storage* is lazy.
        if entity.needs is not None:
            entity.needs = needs_of(entity, world_time, tuning).to_doc()
            store.entities.save(entity)

    return report


# --------------------------------------------------------------------------- #
#  Relationships
# --------------------------------------------------------------------------- #
def relate(
    store,
    from_entity: Entity,
    to_entity: Entity,
    kind: str,
    *,
    world_time: int,
    intensity: float = 1.0,
    familiarity_bonus: float = 0.0,
    deltas: dict | None = None,
    tuning: Tuning | None = None,
    description: str = "",
    rng: Random | None = None,
    source_event_seq: int | None = None,
) -> Relationship:
    """Record that something happened between two entities.

    The relationship shift is only one third of what an event does
    (``06-DECISION-ENGINE.md`` §8): both parties should also *remember* it. Until
    they did, a GM could move Marla's trust in Ondry and leave nothing in her
    head about why — a feeling with no event behind it.

    ``description`` is what actually happened, in the GM's words. Without one a
    line is templated from the kind, so an undescribed event still leaves a
    memory rather than none at all. Pass ``rng`` to form those memories; without
    it only the relationship moves, which is what the pure-arithmetic tests want.
    """
    tuning = tuning or tuning_for(store)
    relationship = store.relations.between(from_entity.id, to_entity.id)
    rel_mod.apply(
        relationship,
        kind,
        traits=traits_of(from_entity),
        intensity=intensity,
        world_time=world_time,
        deltas=deltas,
        tuning=tuning.relationships(),
    )
    if familiarity_bonus:
        rel_mod.deepen(relationship, familiarity_bonus)
    saved = store.relations.save(relationship)
    return saved


def need_pressure(entity: Entity, world_time: int, tuning: Tuning | None = None) -> float:
    """The worst thing their body is currently telling them, 0..1."""
    current = needs_of(entity, world_time, tuning)
    return max((current.value(name) for name in needs_mod.NEEDS), default=0.0)


def interact(
    store,
    actor: Entity,
    subject: Entity,
    kind: str,
    *,
    world_time: int,
    rng: Random,
    description: str = "",
    magnitude: float | None = None,
    actor_awareness: float = 1.0,
    subject_awareness: float = 1.0,
    witnesses: list[Entity] | None = None,
    source_event_seq: int | None = None,
    tuning: Tuning | None = None,
) -> dict:
    """One act, and what it was worth to each person it touched.

    ``actor`` did the thing; ``subject`` had it done to them. The same act is not
    the same event for the two of them, and the difference is not a flourish —
    it is the mechanism that lets a reputation be bought cheaply:

    > A merchant lord settles a stranger's debt with a wave of a finger. It costs
    > him nothing he will notice and he does not trouble to learn the man's name.
    > For the debtor it is the day his life did not end, and he will tell
    > everyone. The lord's standing rises on an afternoon he has already
    > forgotten.

    Each party's stake (``mind/stakes.py``) scales *both* how far their
    relationship moves and how firmly they remember it — and a stake beneath
    noticing forms **no memory at all**, which is how the lord forgets.

    Awareness is per-direction and never assumed mutual. You can do someone a
    kindness they never trace to you, and they can be changed by it while having
    nobody to thank.

    Returns ``{"stakes": {entity_id: Stake}, "memories": {entity_id: Memory}}``.
    """
    tuning = tuning or tuning_for(store)
    stake_tuning = tuning.stakes()

    size = stakes.default_magnitude(kind) if magnitude is None else magnitude
    gist = description.strip() or rel_mod.phrase(
        kind, actor.identity.name, subject.identity.name
    )
    base_valence = rel_mod.felt_valence(kind)

    # Who was touched, how aware each is, and how much of the event was theirs.
    # Who it happened *to*. Salience weighs being a participant far above having
    # merely watched (`05-MEMORY.md` §2) — "a story you tell" against "a story
    # that happened to you" — so the two principals must appear in their own
    # memory's participant list. Listing only the other person had a man's debt
    # being cleared score as something he saw somebody else go through.
    principals = [actor.id, subject.id]
    # (holder, other, awareness, share of the event, their role in it)
    parties: list[tuple[Entity, Entity, float, float, str]] = [
        (subject, actor, subject_awareness, 1.0, "subject"),
        (actor, subject, actor_awareness, 1.0, "actor"),
    ]
    for witness in witnesses or []:
        if witness.id in (actor.id, subject.id):
            continue
        # It did not happen to them; they only saw it happen to someone else.
        parties.append((witness, actor, 1.0, stake_tuning.witness_reach, "witness"))

    out_stakes, out_memories = {}, {}
    for holder, other, awareness, share, role in parties:
        pressure = need_pressure(holder, world_time, tuning)
        stake = stakes.stake_for(
            size * share,
            stakes.capacity_of(holder.standing, traits_of(holder), tuning=stake_tuning),
            awareness=awareness,
            need_pressure=pressure,
            tuning=stake_tuning,
        )
        out_stakes[holder.id] = stake

        # A relationship only moves toward someone you know was involved, and
        # which way it moves depends on which end of the act you were on.
        if awareness > 0 and not stake.negligible:
            if role == "subject":
                deltas = None                      # the table as written
            elif role == "actor":
                deltas = rel_mod.actor_view(kind, stake_tuning.actor_echo)
            else:
                # A bystander thinks better or worse of whoever did it, but
                # nobody owes anybody anything for a thing they merely watched.
                deltas = {
                    axis: base * stake_tuning.actor_echo
                    for axis, base in (rel_mod.DELTAS.get(kind) or {}).items()
                    if axis != "debt"
                }
            relate(
                store, holder, other, kind,
                world_time=world_time,
                intensity=stake.weight,
                deltas=deltas,
                # Knowing someone is not a flat +0.02 whatever happened. The
                # night a man saved your life you know him far better than after
                # a conversation, so how far you close the distance follows what
                # it was worth to you.
                familiarity_bonus=stake_tuning.familiarity_reach * stake.weight,
                tuning=tuning,
            )

        # Beneath noticing is beneath remembering. This is the line the lord
        # falls on the wrong side of, and it is the point of the whole model.
        if stake.negligible:
            continue
        memory = remember(
            store,
            holder,
            gist,
            world_time=world_time,
            rng=rng,
            valence=base_valence * stake.felt,
            participants=list(principals),
            # They were there, so they saw it clearly. Perception is sensory
            # access — distance, light, distraction — and it is NOT how much the
            # thing mattered. Feeding stake in here made a trivial event arrive
            # already blurred, so something that happened this morning read as
            # "a while ago, maybe".
            perception=1.0,
            # Significance goes where it belongs: how firmly it is held. A
            # trivial event is now remembered accurately and briefly.
            salience_scale=0.25 + 0.75 * stake.felt,
            source_event_seq=source_event_seq,
            tuning=tuning,
        )
        if memory is not None:
            out_memories[holder.id] = memory

    return {"stakes": out_stakes, "memories": out_memories}


# --------------------------------------------------------------------------- #
#  NPC generation
# --------------------------------------------------------------------------- #
def spawn_npc(
    store,
    *,
    name: str,
    role: str = "",
    species: str = "",
    culture: str = "",
    pronouns: str = "they/them",
    importance: float | None = None,
    standing: float | None = None,
    world_time: int = 0,
    rng: Random,
    ruleset=None,
    parents: list[Entity] | None = None,
    tuning: Tuning | None = None,
) -> Entity:
    """Create an NPC with a personality, a body, and a past.

    The past is the part that matters. A generator that produces a statblock with
    a name attached gives you a prop; seeding one or two memories — occasionally
    a formative one — gives you someone who reacts to things on first contact,
    before the simulation has had any time to happen to them.
    """
    tuning = tuning or tuning_for(store)
    generation = tuning.generation()
    if importance is None:
        importance = generation.importance

    parent_traits = [traits_of(p) for p in (parents or [])] or None
    entity_traits = traits_mod.derive_traits(
        rng, culture=culture, parents=parent_traits, role=role, tuning=generation
    )
    # No role given: roll the person first and ask what someone like that became.
    # This is the bottom-up path — over a population the trades sort themselves
    # by disposition, so the stereotype emerges as a distribution instead of
    # being stamped on each individual at birth.
    if not role.strip():
        role = traits_mod.suggest_role(
            entity_traits, rng, sharpness=generation.role_fit_sharpness
        )

    stats = {}
    if ruleset is not None:
        stats = ruleset.blank_sheet({"name": name, "role": role, "species": species}, rng)

    entity = store.entities.create(
        Entity(
            guild_id=store.guild_id,
            campaign_id=store.campaign_id,
            kind=KIND_NPC,
            tier=TIER_ACTIVE,
            identity=Identity(
                name=name, pronouns=pronouns, species=species, role=role
            ),
            stats=stats,
            traits=entity_traits.to_doc(),
            needs=needs_mod.Needs(ticked_at=world_time).to_doc(),
            inheritance={
                "parents": [p.id for p in (parents or [])],
                "culture": culture,
                "bloodline": None,
                "derived": True,
            },
            importance=max(0.0, min(1.0, importance)),
            standing=0.5 if standing is None else max(0.0, min(1.0, standing)),
        )
    )

    for gist, valence, arousal in _seed_history(entity_traits, role, culture, rng):
        remember(
            store,
            entity,
            gist,
            world_time=max(0, world_time - rng.randint(200, 20000)),
            rng=rng,
            valence=valence,
            details=[],
            tuning=tuning,
        )
    return entity


# Small pools of formative-sounding backstory beats, chosen by disposition rather
# than at random so an NPC's past is consistent with who they are. Kept short and
# generic on purpose: they are seeds a GM overwrites, not authored fiction.
_SEEDS = {
    "hard": [
        ("lost someone on the water", -0.8, 0.9),
        ("went hungry through a bad winter", -0.6, 0.6),
        ("was cheated and could do nothing about it", -0.7, 0.7),
    ],
    "warm": [
        ("was taken in by strangers who owed them nothing", 0.8, 0.7),
        ("learned the trade from someone patient", 0.5, 0.4),
        ("was trusted with something that mattered", 0.6, 0.5),
    ],
    "plain": [
        ("has worked the same round for years", 0.1, 0.2),
        ("knows every face on this street", 0.2, 0.2),
        ("came here from somewhere quieter", 0.0, 0.3),
    ],
}


def _seed_history(entity_traits: traits_mod.Traits, role: str, culture: str, rng: Random):
    """One or two starting memories, weighted by disposition."""
    pool = list(_SEEDS["plain"])
    if entity_traits.axis("warmth") > 0.1:
        pool += _SEEDS["warm"]
    if entity_traits.axis("warmth") < -0.1 or entity_traits.axis("volatility") > 0.2:
        pool += _SEEDS["hard"]

    count = rng.choice([1, 1, 2])
    chosen = rng.sample(pool, min(count, len(pool)))
    # One in four gets something that will imprint, so a handful of NPCs in any
    # town are carrying something.
    if rng.random() < 0.25:
        chosen.append(rng.choice(_SEEDS["hard"]))
    return chosen
