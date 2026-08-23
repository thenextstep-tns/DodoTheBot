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

from helpers.dnd import narrate
from helpers.dnd import packs as pack_registry
from helpers.dnd import rules
from helpers.dnd.mind import behaviour
from helpers.dnd.mind import decide as decide_math
from helpers.dnd.mind import goals as goal_math
from helpers.dnd.mind import needs as needs_mod
from helpers.dnd.mind import relationships as rel_mod
from helpers.dnd.mind import rumour
from helpers.dnd.mind import stakes
from helpers.dnd.mind import traits as traits_mod
from helpers.dnd.mind.memory import consolidate, decay, encode, recall
from helpers.dnd.mind.memory import values as value_model
from helpers.dnd.tuning import DEFAULT_GOALS, Tuning
from helpers.dnd.world.entity import (
    KIND_NPC,
    TIER_ACTIVE,
    TIER_DORMANT,
    Entity,
    Identity,
)
from helpers.dnd.world import belief as belief_model
from helpers.dnd.world import clock as clock_model
from helpers.dnd.world import event as events
from helpers.dnd.world import goal as goal_model
from helpers.dnd.world import pack as pack_model
from helpers.dnd.world import view as view_model
from helpers.dnd.rules import ruleset as ruleset_model
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
    gist: str = "",
    *,
    gist_for=None,
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

    ``gist_for`` is that taken one step further: a callable ``(entity) -> str``,
    so the words differ too and not merely the fidelity. The person who did a
    thing remembers doing it; the people who watched remember watching them.
    Without it every witness gets ``gist`` verbatim, which is right for a GM's
    own description and wrong for anything the engine phrased itself.
    """
    tuning = tuning or tuning_for(store)
    formed = {}
    for entity, perception in witnesses:
        formed[entity.id] = remember(
            store,
            entity,
            gist_for(entity) if gist_for is not None else gist,
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
#  What an entity has to decide with
# --------------------------------------------------------------------------- #
def view_for(
    store,
    entity: Entity,
    *,
    world_time: int,
    cues=(),
    include=(),
    tuning: Tuning | None = None,
) -> view_model.EntityView:
    """Build the projection this entity decides from.

    The only supported way to get one. Everything the decision engine is allowed
    to see passes through here, so a term that wants world truth has nowhere to
    get it — see ``world/view.py`` for why that is structural rather than a
    matter of care.

    ``cues`` narrows the memories the way recall actually works: what is present
    drags things up, rather than the engine querying a life. Without cues the
    strongest memories come along, which is what an NPC deciding alone in a room
    has. ``include`` is who is in front of them — those people appear in the view
    whether or not it knows them, because you can see a stranger.

    Nothing is written. Recall here does **not** reconsolidate: a view is built
    for every NPC on every tick, and rewriting 200 memories four times an hour
    would be a world that drifts while nobody is playing in it.
    """
    tuning = tuning or tuning_for(store)
    perception = tuning.perception()

    memories = store.memories.for_entity(entity.id)
    if cues:
        limit = perception.memory_limit or len(memories)
        memories = recall.recall(memories, cues, world_time, limit=limit)

    beliefs = store.beliefs.held_by(entity.id)
    relations = store.relations.outgoing(entity.id)

    named = [r.to_id for r in relations]
    named += [b.subject_id for b in beliefs]
    named += list(include)
    identities = store.entities.identities_of(named)

    return view_model.project(
        entity,
        world_time=world_time,
        needs=needs_of(entity, world_time, tuning).to_doc(),
        traits=entity.traits,
        memories=memories,
        beliefs=beliefs,
        goals=tuple(goals_of(entity, world_time, tuning)),
        packs=tuple(packs_of(entity)),
        relations=relations,
        identities=identities,
        include=tuple(include),
        perception=perception,
    )


# --------------------------------------------------------------------------- #
#  Who somebody is, in terms of what they reach for
# --------------------------------------------------------------------------- #
def packs_for(store, campaign=None) -> pack_registry.Packs:
    """The archetypes this campaign can draw on: built-in, then server, then its
    own. Built once per command and handed down, like the tuning."""
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    return pack_registry.Packs.for_campaign(store.guild_id, campaign)


def packs_of(entity: Entity) -> list:
    """Which archetypes this entity carries, weighted."""
    return pack_model.assignments_from(entity.packs)


def assign_packs(store, entity: Entity, rng: Random, *, campaign=None,
                 tuning: Tuning | None = None, first=None) -> list:
    """Draw this entity's archetypes from who they already are, and store them.

    Called at generation. Separate from ``spawn_npc`` so a GM can re-roll
    somebody's archetypes without rebuilding the person, and so an entity that
    predates the feature can be given some.
    """
    tuning = tuning or tuning_for(store, campaign)
    available = packs_for(store, campaign).available().values()
    assignments = behaviour.assign(
        traits_of(entity), available, rng, tuning.behaviour(), first=first
    )
    entity.packs = pack_model.assignments_to(assignments) or None
    store.entities.save(entity)
    return assignments


def drift_packs(store, entity: Entity, *, world_time: int, verb: str = "",
                campaign=None, tuning: Tuning | None = None, available=None) -> list:
    """Move the mixture this entity is, one step.

    Called after events. ``verb`` is what they actually committed to, when there
    was one — that is the strongest pull, because people become what they do.
    Without it only what they are living through moves them, which is the slower
    half and still real.

    Returns the new assignments when they changed, or ``[]`` when nothing moved,
    so a caller can report a person turning into somebody else.
    """
    tuning = tuning or tuning_for(store, campaign)
    behaviour_tuning = tuning.behaviour()
    if behaviour_tuning.fixed or behaviour_tuning.off:
        return []

    if available is None:
        available = packs_for(store, campaign).available()
    before = packs_of(entity)
    after = behaviour.drifted(
        before, available, traits_of(entity),
        needs=needs_of(entity, world_time, tuning), verb=verb,
        tuning=behaviour_tuning,
    )
    if [(a.key, a.weight) for a in after] == [(b.key, b.weight) for b in before]:
        return []
    set_packs(store, entity, after)
    return after


def set_packs(store, entity: Entity, assignments) -> Entity:
    """Say what somebody is by hand. The definitions are configuration; which of
    them a given person is drawn from is a fact about that person."""
    entity.packs = pack_model.assignments_to(assignments) or None
    store.entities.save(entity)
    return entity


def candidates_for(
    store,
    entity: Entity,
    scene,
    *,
    world_time: int,
    campaign=None,
    tuning: Tuning | None = None,
    view=None,
    available=None,
    features=(),
    sealed: bool = False,
) -> list:
    """What this entity would think of doing here.

    The **propose** step end to end: what the scene physically permits, narrowed
    by what the campaign allows, crossed with what this person's archetypes reach
    for, fanned out over whoever they can see. Scoring them is the next stage and
    is not this function's business.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)
    if view is None:
        # Everyone on stage must be in the view even if this entity has never
        # met them and holds no belief about them: you can act on a stranger you
        # are standing next to, and without this the directed verbs — speak,
        # attack, give, take — quietly find nobody to aim at.
        present = tuple(getattr(scene, "present", ()) or ())
        view = view_for(store, entity, world_time=world_time, tuning=tuning,
                        include=present)

    allowed = affordances_for(store, entity, scene, campaign=campaign, tuning=tuning,
                              features=features, sealed=sealed)
    if available is None:
        available = packs_for(store, campaign).available()
    return behaviour.propose(
        view, allowed, packs_of(entity), available, tuning.behaviour(),
    )


def coarse_view_for(store, entity: Entity, *, world_time: int,
                    tuning: Tuning | None = None) -> view_model.EntityView:
    """A view built from the entity alone — **no queries at all**.

    No memories, no beliefs, no relationships, nobody else. That is the whole
    saving: the full view costs three round trips and a social projection, and a
    character nobody is watching needs none of it to know they are hungry and
    what they are trying to do.
    """
    tuning = tuning or tuning_for(store)
    return view_model.project(
        entity,
        world_time=world_time,
        needs=needs_of(entity, world_time, tuning).to_doc(),
        traits=entity.traits,
        goals=tuple(goals_of(entity, world_time, tuning)),
        packs=tuple(packs_of(entity)),
        perception=tuning.perception(),
    )


def decide_coarsely(store, entity: Entity, *, world_time: int, campaign=None,
                    tuning: Tuning | None = None, available=None):
    """What somebody off-screen does, without a scene and without an RNG.

    ``available`` is the campaign's resolved archetypes. Passed in by a caller
    running a whole turn, because resolving them costs a query and doing it once
    per NPC was the entire difference between this path making its budget and
    missing it.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)
    if available is None:
        available = packs_for(store, campaign).available()

    view = coarse_view_for(store, entity, world_time=world_time, tuning=tuning)
    candidates = behaviour.propose_coarse(
        view, packs_of(entity), available, tuning.behaviour(),
    )
    return decide_math.decide_coarse(
        view, candidates, tuning=tuning.decision(), goals=tuning.goals(),
        needs=tuning.needs(),
    )


def decide_for(
    store,
    entity: Entity,
    scene,
    *,
    world_time: int,
    rng: Random,
    campaign=None,
    tuning: Tuning | None = None,
    features=(),
    sealed: bool = False,
):
    """What this entity would do here, and the working behind it.

    The whole pipeline: what the scene permits, narrowed by what the campaign
    allows, crossed with what this person would think of, weighed by everything
    they are. Nothing is written — committing the choice is a separate step, so
    that a GM can ask what somebody *would* do without it happening.

    The engine only ever sees the :class:`EntityView`, so an NPC decides on what
    they believe rather than on what is true, at the type level rather than by
    anybody remembering to.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)

    # Somebody about to decide has to be up to date first. `view_for` stays
    # read-only — that is a promise the inspector depends on — so the arrears
    # are settled here, by a caller that is allowed to write.
    catch_up(store, entity, world_time, rng, tuning=tuning)

    present = tuple(getattr(scene, "present", ()) or ())
    view = view_for(store, entity, world_time=world_time, tuning=tuning,
                    include=present)
    candidates = candidates_for(
        store, entity, scene, world_time=world_time, campaign=campaign,
        tuning=tuning, view=view, features=features, sealed=sealed,
    )
    return decide_math.decide(
        view, candidates, rng,
        tuning=tuning.decision(), goals=tuning.goals(), needs=tuning.needs(),
    )


# --------------------------------------------------------------------------- #
#  Doing it
# --------------------------------------------------------------------------- #
# Which of the nine verbs is a thing done *to* somebody, and what a relationship
# calls it (``mind/relationships.py``). A verb absent here still happens and is
# still remembered — it simply does not move how two people stand.
ACT_AS_RELATION = {
    "attack": "attacked",
    "take": "stole",
    "give": "gifted",
    "speak": "talked",
}

# What an undirected act reads as, so something that nobody described still
# forms a memory somebody could tell back.
ACT_PHRASES = {
    "flee": "{name} got out",
    "hide": "{name} went to ground",
    "move": "{name} moved off",
    "use": "{name} used what they had",
    "wait": "{name} did nothing",
    "watch": "{name} hung back and watched",
}


def commit_decision(
    store,
    entity: Entity,
    scene,
    decision,
    *,
    world_time: int,
    rng: Random,
    campaign=None,
    tuning: Tuning | None = None,
    caused_by: int | None = None,
    available=None,
) -> dict:
    """Make a decision *happen*: the only function here that writes a choice.

    The commit step of ``06-DECISION-ENGINE.md`` §8, and the line between a
    simulation that can be asked what it thinks and one that gets on with it.
    In order: the event is appended with its own reasoning attached, whoever it
    was done to has it done to them, everyone who saw it remembers it, what it
    served moves along, and doing it makes the actor a little more the sort of
    person who does it.

    **The trace rides on the event.** That is what makes an NPC's behaviour
    answerable weeks later, when nobody remembers the state that produced it —
    the event log is the only thing that still knows.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)

    chosen = decision.chosen
    verb, target_id = chosen.verb, chosen.target_id
    target = store.entities.get(target_id) if target_id is not None else None

    seq = store.campaigns.next_seq(campaign.id)
    seed = events.event_seed(campaign.seed, seq)
    event = store.events.append(
        events.ACTED,
        actor_id=entity.id,
        targets=(target_id,) if target_id is not None else (),
        payload={"name": entity.identity.name, "verb": verb,
                 "target": target.identity.name if target else "",
                 "trace": decision.to_doc()},
        seed=seed,
        seq=seq,
        caused_by=caused_by,
        world_time=world_time,
    )

    report = {"verb": verb, "target_id": target_id, "seq": seq,
              "utility": chosen.utility, "memories": 0, "goals": []}

    # --- who it was done to ------------------------------------------------ #
    onlookers = [
        other for other in _present_entities(store, scene)
        if other.id not in (entity.id, target_id)
    ]
    kind = ACT_AS_RELATION.get(verb)
    if target is not None and kind:
        outcome = interact(
            store, entity, target, kind,
            world_time=world_time, rng=rng, witnesses=onlookers,
            source_event_seq=seq, tuning=tuning,
        )
        report["memories"] = len(outcome["memories"])
        report["stakes"] = {str(k): v.weight for k, v in outcome["stakes"].items()}
    else:
        # Nobody had it done to them, but people saw it. An NPC slipping out of
        # a room is exactly the sort of thing a witness remembers and the person
        # who left never thinks about again.
        #
        # Unless nothing happened: waiting and watching, alone, off-screen, is
        # not an event anybody carries. Forming a memory of it would be noise
        # the budget prunes anyway, and it is the commonest thing a character
        # nobody is watching does — so it is also most of what the coarse path
        # would otherwise cost.
        idle = verb in ruleset_model.UNCOMMITTED and not onlookers
        if idle and not tuning.decision().remember_idle:
            report["memories"] = 0
            report["idle"] = True
            remembered = False
        else:
            remembered = True
        if remembered:
            gist_tuning = tuning.gists()
            formed = witness_event(
                store,
                [(entity, 1.0)] + [(other, 0.85) for other in onlookers],
                # The actor's own memory says *I*; everyone else's names them.
                # Undirected acts are most of what anybody does, so this is the
                # commonest memory a character holds about themselves.
                gist_for=lambda holder: narrate.act_gist(
                    verb, entity.identity.name,
                    first_person=holder.id == entity.id, tuning=gist_tuning,
                ),
                world_time=world_time, rng=rng,
                participants=[entity.id], source_event_seq=seq, tuning=tuning,
            )
            report["memories"] = sum(1 for m in formed.values() if m is not None)

    # --- what it served ---------------------------------------------------- #
    report["goals"] = advance_goals_by(
        store, entity, verb, world_time=world_time, tuning=tuning
    )
    report["relieved"] = relieve_needs(
        store, entity, verb, world_time=world_time, tuning=tuning
    )

    # --- and who it made them ---------------------------------------------- #
    entity = store.entities.get(entity.id) or entity
    # What they were leaning into *before* this, so a report can tell an actual
    # turn of character from the ordinary churn. The mixture's weights move on
    # nearly every action — that is what continuous drift means — so ``became``
    # alone marks almost every line and says nothing. The leading archetype
    # changing is rare, and is the thing worth being told.
    leading = packs_of(entity)
    drifted = drift_packs(store, entity, world_time=world_time, verb=verb,
                          campaign=campaign, tuning=tuning, available=available)
    report["was"] = leading[0].key if leading else ""
    report["became"] = [(a.key, a.weight) for a in drifted]
    report["event_seq"] = event.seq if event is not None else seq
    return report


def advance_goals_by(store, entity: Entity, verb: str, *, world_time: int,
                     tuning: Tuning | None = None) -> list:
    """Move every goal this action served, by what the actor could give it.

    Scaled by attention: a goal getting a ninth of somebody moves a ninth as
    far. This is where being spread thin stops being an abstraction and starts
    costing people the things they wanted.
    """
    tuning = tuning or tuning_for(store)
    goal_tuning = tuning.goals()
    step = tuning.decision().goal_progress
    if step <= 0:
        return []

    live = goals_of(entity, world_time, tuning)
    if not live:
        return []
    shares = goal_math.focus(live, world_time, traits_of(entity), goal_tuning)

    moved = []
    stored = goal_model.from_docs(entity.goals)
    out, changed = [], False
    for goal in stored:
        served = goal.served_by(verb) if goal.open else 0.0
        if served <= 0 or goal.key not in shares:
            out.append(goal)
            continue
        after = goal_math.progressed(goal, step * served, world_time, goal_tuning,
                                     share=shares.get(goal.key, 1.0))
        out.append(after)
        changed = True
        moved.append({"key": goal.key, "text": goal.text,
                      "progress": after.progress, "done": not after.open})
    if changed:
        save_goals(store, entity, out)
    return moved


def relieve_needs(store, entity: Entity, verb: str, *, world_time: int,
                  tuning: Tuning | None = None) -> dict:
    """Doing something about a need makes it press a little less.

    The interlock this closes is the one `04-ENTITIES.md` §5a warned about:
    deprivation could not be switched on while **nothing could satisfy a need**,
    because needs only ever rose and a world of NPCs would starve on a rail. Now
    that they can act, eating is a thing that can happen.

    Deliberately small and blunt — there is no item model yet, so this says
    "they did something about it", not "they ate a specific loaf". At 0 nothing
    anybody does relieves anything, which is the old behaviour exactly.
    """
    tuning = tuning or tuning_for(store)
    relief = tuning.decision().need_relief
    served = decide_math.NEEDS_SERVED.get(verb, ())
    if relief <= 0 or not served or entity.needs is None:
        return {}

    current = needs_of(entity, world_time, tuning)
    doc, eased = current.to_doc(), {}
    for name in served:
        was = float(doc.get(name, 0.0))
        now = max(0.0, was - relief)
        if now < was:
            doc[name] = now
            eased[name] = round(was - now, 4)
    if not eased:
        return {}
    doc["ticked_at"] = int(world_time)
    entity.needs = doc
    store.entities.save(entity)
    return eased


def _present_entities(store, scene) -> list:
    """Everyone on stage, as entities. Empty when there is no scene."""
    out = []
    for other_id in (getattr(scene, "present", ()) or ()):
        other = store.entities.get(other_id)
        if other is not None and not other.retired:
            out.append(other)
    return out


def act(
    store,
    entity: Entity,
    scene,
    *,
    world_time: int,
    rng: Random,
    campaign=None,
    tuning: Tuning | None = None,
) -> dict:
    """Decide, and then do it. The whole pipeline, end to end.

    Kept as two functions with this one on top, because *asking* what somebody
    would do and *making them do it* are different questions and the panel needs
    only the first.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)
    decision = decide_for(store, entity, scene, world_time=world_time, rng=rng,
                          campaign=campaign, tuning=tuning)
    if not decision.considered:
        return {"verb": "", "acted": False}
    report = commit_decision(store, entity, scene, decision, world_time=world_time,
                             rng=rng, campaign=campaign, tuning=tuning)
    report["acted"] = True
    return report


# What an action reads as when nothing narrates it. These now live in
# `helpers/dnd/narrate.py` — the deterministic, no-model half of P4
# (`08-LLM-LAYER.md` §5) — and are re-exported here because they were part of
# this module's surface first and the panel and cog both reach for them. The
# words themselves belong beside the rest of the report, not inside the
# orchestration layer: a pure module can be tested without a database, and two
# renderings of one event that disagree is how a GM stops trusting either.
ACTED_PHRASES = narrate.ACTED_PHRASES
describe_act = narrate.describe_act


def last_choice(store, entity: Entity):
    """The most recent thing this entity chose of their own accord, with its
    reasoning. ``None`` if they have never acted.

    Read back from the **event log** rather than from anything on the entity,
    which is the point of having put the trace there: weeks later, when nothing
    remembers the state that produced a decision, the log still does.
    """
    for event in store.events.recent(200):
        if event.kind == events.ACTED and event.actor_id == entity.id:
            return event
    return None


def run_turn(store, campaign, *, world_time: int, rng: Random,
             tuning: Tuning | None = None) -> dict:
    """Let the world's people take a turn.

    Everyone in an open scene first — those are the ones a table is watching —
    then whoever else is simulated closely enough to be worth running, up to the
    campaign's cap. The cap is what keeps a world of five hundred NPCs a fixed
    bill rather than an unbounded one.

    Called from ``advance``, not from the tick loop, for the reason that has held
    all of P3 together: a world that behaves differently when nobody is watching
    is a world with two rulesets.
    """
    tuning = tuning or tuning_for(store, campaign)
    limit = int(tuning.continuity().actors)
    if limit <= 0:
        return {"actors": 0, "acted": [], "off": True}

    scenes = {s.id: s for s in store.scenes.open_scenes()}
    on_stage, off_stage, seen = [], [], set()
    for scene in scenes.values():
        for entity in _present_entities(store, scene):
            if entity.kind == KIND_NPC and entity.id not in seen:
                seen.add(entity.id)
                on_stage.append((entity, scene))
    for entity in store.entities.list(kind=KIND_NPC, tier=TIER_ACTIVE):
        if entity.id not in seen:
            off_stage.append((entity, scenes.get(entity.position.scene_id)))

    # Resolved once for the whole turn rather than once per character: it is a
    # query, and the coarse path exists precisely to not be doing queries.
    available = packs_for(store, campaign).available()

    acted, coarse = [], 0
    for entity, scene in on_stage[:limit]:
        outcome = act(store, entity, scene, world_time=world_time, rng=rng,
                      campaign=campaign, tuning=tuning)
        if outcome.get("acted"):
            acted.append({"name": entity.identity.name, **outcome})

    # Everybody else runs the cheap path: no scene to perceive, no softmax, and
    # the social terms left out rather than scored against an empty room. This
    # is what the 200-NPC budget in §11 is for.
    for entity, _scene in off_stage[:max(0, limit - len(acted))]:
        decision = decide_coarsely(store, entity, world_time=world_time,
                                   campaign=campaign, tuning=tuning,
                                   available=available)
        if not decision.considered:
            continue
        report = commit_decision(store, entity, None, decision,
                                 world_time=world_time, rng=rng,
                                 campaign=campaign, tuning=tuning,
                                 available=available)
        coarse += 1
        acted.append({"name": entity.identity.name, "coarse": True, **report})

    return {"actors": len(acted), "acted": acted, "coarse": coarse}


# --------------------------------------------------------------------------- #
#  What somebody is after
# --------------------------------------------------------------------------- #
def goals_of(entity: Entity, world_time: int, tuning: Tuning | None = None) -> list:
    """This entity's live goals, the one they care about most first.

    No store: goals ride on the entity document, the same way needs and traits
    do. Finished, abandoned, expired and faded-past-caring goals are all left
    out — :func:`all_goals_of` is what the inspector uses to show those.
    """
    view = tuning.goals() if tuning else DEFAULT_GOALS
    return goal_math.active(goal_model.from_docs(entity.goals), world_time, view,
                            traits=traits_of(entity))


def all_goals_of(entity: Entity) -> list:
    """Every goal on the record, finished and abandoned ones included. For the
    inspector, which has to be able to show what someone gave up on."""
    return goal_model.from_docs(entity.goals)


def attention_of(entity: Entity, world_time: int, tuning: Tuning | None = None) -> dict:
    """How this entity's attention is actually divided, plus the arithmetic.

    ``{shares: {key: 0..1}, budget, usable, overhead, carrying}`` — everything the
    inspector needs to show *why* somebody who wants nine things is getting none
    of them done, which is the whole reason the mechanic is worth having.
    """
    goal_tuning = tuning.goals() if tuning else DEFAULT_GOALS
    live = goals_of(entity, world_time, tuning)
    traits = traits_of(entity)
    total = goal_math.budget(traits, goal_tuning)
    return {
        "shares": goal_math.focus(live, world_time, traits, goal_tuning),
        "budget": total,
        "usable": goal_math.usable(len(live), traits, goal_tuning),
        "overhead": len(live) * max(0.0, goal_tuning.attention_overhead),
        "carrying": len(live),
    }


def set_goal_priority(store, entity: Entity, key: str, priority: float):
    """What a GM says this is worth to them. Returns the updated goal, or ``None``.

    Priority is the share of a person a goal gets, so this is the most
    consequential control on the page — it is how you say *this one matters and
    the rest are noise*, which is the difference between someone relentless and
    someone scattered.
    """
    goals, found = goal_model.from_docs(entity.goals), None
    out = []
    for goal in goals:
        if goal.key == key:
            found = goal.with_priority(priority)
            out.append(found)
        else:
            out.append(goal)
    if found is None:
        return None
    save_goals(store, entity, out)
    return found


def reweigh_goals(store, entity: Entity, *, subject_id=None, world_time: int = 0,
                  magnitude: float = 1.0, tuning: Tuning | None = None) -> list:
    """Let how they feel about people pull what they want about those people.

    Called after anything that moves a relationship, so a grudge that cools takes
    the wanting with it. ``subject_id`` narrows it to goals about one person,
    which is what an event between two entities wants; without it every goal they
    hold is re-weighed, which is what a tick wants.

    Returns the goals that actually moved, so a caller can report it.
    """
    tuning = tuning or tuning_for(store)
    goal_tuning = tuning.goals()
    if goal_tuning.reweigh <= 0:
        return []

    # How impulsive they are decides how far one event may swing them, so the
    # sudden reversal stays available to the people it looks like character on.
    volatility = traits_of(entity).volatility
    goals, out, moved = goal_model.from_docs(entity.goals), [], []
    for goal in goals:
        if not goal.open or goal.subject_id is None or (
            subject_id is not None and goal.subject_id != subject_id
        ):
            out.append(goal)
            continue
        relationship = store.relations.between(entity.id, goal.subject_id)
        shifted = goal_math.reweighed(
            goal, relationship, goal_tuning,
            world_time=world_time, magnitude=magnitude, volatility=volatility,
        )
        out.append(shifted)
        if shifted.priority != goal.priority:
            moved.append(shifted)

    if moved:
        save_goals(store, entity, out)
    return moved


def save_goals(store, entity: Entity, goals) -> Entity:
    """Write a goal list back. Sorted by key so a document never churns."""
    entity.goals = goal_model.to_docs(sorted(goals, key=lambda g: g.key)) or None
    store.entities.save(entity)
    return entity


def add_goal(
    store,
    entity: Entity,
    kind: str,
    *,
    world_time: int,
    text: str = "",
    subject_id: Any = None,
    priority: float = 0.5,
    deadline: int | None = None,
    origin: str = goal_model.ORIGIN_GM,
    tuning: Tuning | None = None,
):
    """Give somebody something to want.

    Returns the new goal, or ``None`` when they are already carrying as many as
    the campaign allows — refusing rather than silently evicting, because which
    ambition to drop is a decision with consequences and not one to make behind
    a GM's back.
    """
    tuning = tuning or tuning_for(store)
    goal_tuning = tuning.goals()
    existing = goal_model.from_docs(entity.goals)

    # Attention is what limits anyone: a long list is not refused, it is simply
    # unproductive, because carrying each goal costs something before any of it
    # is spent. The cap is off by default and is a blunt backstop for a table
    # that would rather have a flat rule.
    live = [g for g in existing if g.open and not g.expired(world_time)]
    if goal_tuning.cap > 0 and len(live) >= goal_tuning.cap:
        return None

    goal = goal_model.Goal(
        key=goal_model.next_key(existing, kind),
        kind=kind if kind in goal_model.KINDS else goal_model.ACQUIRE,
        text=text,
        subject_id=subject_id,
        priority=max(0.0, min(1.0, float(priority))),
        deadline=deadline,
        origin=origin if origin in goal_model.ORIGINS else goal_model.ORIGIN_GM,
        created_at=int(world_time),
        touched_at=int(world_time),
    )
    save_goals(store, entity, existing + [goal])
    return goal


def advance_goal(store, entity: Entity, key: str, amount: float, *,
                 world_time: int, tuning: Tuning | None = None):
    """Move one goal along. Returns the updated goal, or ``None`` if unknown."""
    tuning = tuning or tuning_for(store)
    goal_tuning = tuning.goals()

    goals, updated = goal_model.from_docs(entity.goals), None
    out = []
    for goal in goals:
        if goal.key == key:
            updated = goal_math.progressed(goal, amount, world_time, goal_tuning)
            out.append(updated)
        else:
            out.append(goal)
    if updated is None:
        return None
    save_goals(store, entity, out)
    return updated


def drop_goal(store, entity: Entity, key: str):
    """Give up on something. Kept on the record rather than deleted — what
    somebody abandoned is as much a fact about them as what they finished."""
    goals, found = goal_model.from_docs(entity.goals), None
    out = []
    for goal in goals:
        if goal.key == key:
            found = goal_math.abandoned(goal)
            out.append(found)
        else:
            out.append(goal)
    if found is None:
        return None
    save_goals(store, entity, out)
    return found


# --------------------------------------------------------------------------- #
#  What the scene physically permits
# --------------------------------------------------------------------------- #
def situation_for(
    store,
    entity: Entity,
    scene,
    *,
    features=(),
    sealed: bool = False,
) -> ruleset_model.Situation:
    """Flatten a scene into the handful of facts a ruleset can rule on.

    The rules layer sits below ``world/`` and must not import the entity model,
    so the occupants arrive as :class:`~helpers.dnd.rules.ruleset.Presence` —
    three facts each, which is all a physical possibility can turn on.

    ``features`` and ``sealed`` are arguments rather than scene fields because a
    scene does not carry objects or exits yet. Taking and using therefore ride on
    what people are *carrying*, which is real today; the seam is here so that
    when scenes gain contents this becomes a fill rather than a rewrite.
    """
    others = []
    for other_id in (scene.present if scene is not None else []):
        if other_id == entity.id:
            continue
        other = store.entities.get(other_id)
        if other is None or other.retired:
            continue
        others.append(ruleset_model.Presence(
            entity_id=other.id,
            kind=other.kind,
            carrying=bool(other.inventory),
            # Everyone on stage is within reach: no ruleset here models distance
            # yet, and pretending otherwise would silently disable half of this.
            reachable=True,
        ))

    return ruleset_model.Situation(
        others=tuple(others),
        conditions=tuple(str(c).lower() for c in entity.conditions),
        carrying=bool(entity.inventory),
        lighting=(scene.lighting if scene is not None else ""),
        features=tuple(features),
        sealed=bool(sealed),
    )


def affordances_for(
    store,
    entity: Entity,
    scene,
    *,
    campaign=None,
    tuning: Tuning | None = None,
    features=(),
    sealed: bool = False,
) -> frozenset:
    """What this entity could choose to do here, after the campaign has its say.

    Two questions, kept apart on purpose. The ruleset answers *what is physically
    possible*, knowing nothing about this table; the campaign then answers *what
    it is willing to have happen*, which is a lines-and-veils decision and has no
    business inside the physics. Waiting survives both.
    """
    if campaign is None:
        campaign = store.campaigns.get(store.campaign_id)
    tuning = tuning or tuning_for(store, campaign)

    situation = situation_for(store, entity, scene, features=features, sealed=sealed)
    allowed = rules.get(campaign.ruleset if campaign else "freeform").affordances(
        entity.stats or {}, situation
    )
    return tuning.affordances().filter(allowed)


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


def catch_up(store, entity: Entity, world_time: int, rng: Random,
             tuning: Tuning | None = None) -> dict:
    """Pay the arrears on an entity nobody has been simulating.

    A ``dormant`` character is skipped by every tick, so their memories are as
    old as the last time anything happened to them. This applies the whole gap
    in one pass, the moment somebody looks — the closed-form extrapolation
    ``06-DECISION-ENGINE.md`` §9 asks for, and the reason five hundred NPCs cost
    nothing to keep.

    Needs and goal pressure need no catching up at all: both are already
    functions of ``world_time`` rather than of having been ticked, so a dormant
    character's hunger is exactly right the instant it is read.

    **How faithful is one big step?** The forgetting curve is a function of
    total elapsed time, so the deterministic part lands where it would have. The
    *confabulation* draws do not: N days in one pass rolls once where N passes
    would roll N times, so a long-dormant character misremembers slightly less
    than a watched one. That is a real difference and the honest trade for the
    cost — noted here rather than claimed away.
    """
    tuning = tuning or tuning_for(store)
    behind = max(0, int(world_time) - int(entity.aged_at))
    if behind <= 0:
        return {"days": 0.0, "caught_up": False}

    days = behind / MINUTES_PER_DAY
    report = age_entity(store, entity, days, world_time=world_time, rng=rng,
                        tuning=tuning)
    entity.aged_at = int(world_time)
    store.entities.save(entity)
    return {**report, "days": days, "caught_up": True}


def days_behind(entity: Entity, world_time: int) -> float:
    """How far this entity's memories are from where the world is."""
    return max(0, int(world_time) - int(entity.aged_at)) / MINUTES_PER_DAY


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

    summary = _summarise(store, entity, pruned, world_time, tuning)
    store.memories.forget_many(pruned)
    if summary is not None:
        store.memories.add(summary)
    return len(pruned)


def _summarise(store, entity: Entity, pruned: list, world_time: int,
               tuning: Tuning):
    """``consolidate.summarise`` with the two lookups it may not do itself.

    A summary says who a forgotten stretch was mostly *with* and where it mostly
    *was*, and both of those are ids on the memories until somebody resolves
    them. This is the orchestration edge that does it — and it does no work at
    all when the wording is switched off, because then there is nothing to name.
    """
    gist_tuning = tuning.gists()
    if not pruned or not gist_tuning.summaries:
        return consolidate.summarise(pruned, entity.id, world_time,
                                     tuning=gist_tuning)

    company = narrate.dominant(
        [p for memory in pruned for p in memory.participants],
        exclude=(entity.id, str(entity.id)),
    )
    names = store.entities.identities_of(company) if company else {}
    # No `place=` yet, deliberately. `summary_gist` takes one and renders it —
    # "a hard winter **at the docks**" is `05-MEMORY.md` §8's own example — but
    # **nothing in the codebase ever writes `Memory.location_id`**, so passing
    # anything here would mean inventing a place or borrowing a field.
    #
    # The tempting shortcut is the scene id, and it is a trap: `Position` keeps
    # `location_id` and `scene_id` apart and `world/view.py` carries the former,
    # so filing scene ids under a memory's location would collide with the
    # location model the moment anybody builds one. When memories learn where
    # they happened, this call gains one argument and the sentence grows a tail.
    return consolidate.summarise(
        pruned, entity.id, world_time,
        names={key: (value or {}).get("name") or "" for key, value in names.items()},
        tuning=gist_tuning,
    )


def due_for_tick(campaign, now: float, tuning: Tuning | None = None) -> bool:
    """Whether enough real time has passed for this campaign to move on its own.

    Pure arithmetic over the campaign's own record, so the loop that calls it can
    stay a dumb scheduler and every campaign keeps its own cadence.
    """
    continuity = (tuning or Tuning.for_campaign(campaign.guild_id, campaign)).continuity()
    if not continuity.automatic:
        return False
    last = float(campaign.settings.get("ticked_at") or 0)
    return (now - last) >= continuity.hours * 3600.0


def tick(store, campaign, now: float, rng: Random,
         tuning: Tuning | None = None) -> dict | None:
    """One turn of the world, for one campaign.

    The manual `/gm advance` and this share the same body deliberately: a world
    that ages differently when nobody is watching is a world with two rulesets,
    and the difference would only ever surface as a bug nobody could reproduce.

    Returns the ageing report, or ``None`` when the campaign was not due.
    """
    tuning = tuning or tuning_for(store, campaign)
    if not due_for_tick(campaign, now, tuning):
        return None

    report = advance(store, campaign, tuning.continuity().days, rng)
    settings = dict(campaign.settings or {})
    settings["ticked_at"] = float(now)
    store.campaigns.save_settings(campaign.id, settings)
    campaign.settings = settings
    return report


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
            summary = _summarise(store, entity, dropped, world_time, tuning)
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
    # A timeless campaign does not age, whoever asked. A dungeon crawl has no
    # use for a harbourmaster forgetting a face between rooms, and switching off
    # every decay knob one at a time to get there is not a setting, it is a
    # chore. `timeless` is the one switch that means "time is not the point".
    if tuning.continuity().timeless:
        return {"days": days, "world_time": campaign.world_time, "entities": 0,
                "new_imprints": 0, "confabulated": 0, "pruned": 0,
                "frozen": True, "timeless": True}
    minutes = int(days * MINUTES_PER_DAY)
    world_time = store.campaigns.advance_time(campaign.id, minutes)

    report = {"days": days, "world_time": world_time, "entities": 0,
              "dormant": 0, "new_imprints": 0, "pruned": 0, "confabulated": 0,
              "frozen": tuning.memory().frozen}

    for entity in store.entities.list(include_retired=False):
        # Dormant characters are not ticked at all. They fall behind on purpose
        # and `catch_up` settles it the moment anything looks at them, which is
        # what turns a world of five hundred people from a recurring bill into
        # a one-off cost paid only for the ones who matter.
        if entity.tier == TIER_DORMANT:
            report["dormant"] = report.get("dormant", 0) + 1
            continue
        outcome = age_entity(
            store, entity, days, world_time=world_time, rng=rng, tuning=tuning
        )
        entity.aged_at = world_time
        report["entities"] += 1
        report["new_imprints"] += max(0, outcome["new_imprints"])
        report["pruned"] += outcome["pruned"]
        report["confabulated"] += outcome["confabulated"]

        # Needs advance for everyone; only their *storage* is lazy.
        if entity.needs is not None:
            entity.needs = needs_of(entity, world_time, tuning).to_doc()
            store.entities.save(entity)

    # Fronts fill whether or not anybody was watching. Done here rather than in
    # the tick loop so `/gm advance` moves them too — one body, as ever.
    report["clocks"] = advance_clocks(store, campaign, days, world_time)
    report["rumours"] = spread_rumours(store, world_time, rng, tuning)
    # And the people in it do something. Last, so they act on a world that has
    # already aged, filled its clocks and passed its rumours around.
    report["turn"] = run_turn(store, campaign, world_time=world_time, rng=rng,
                              tuning=tuning)
    return report


def spread_rumours(store, world_time: int, rng: Random,
                   tuning: Tuning | None = None) -> dict:
    """People who know each other talk, and what they pass on arrives worse.

    The mechanism behind reputation: run this on the tick and a claim about a PC
    reaches somebody who has never met them, weaker and slightly wrong. Nothing
    here is narrated and no model is involved — it is a walk over the
    relationship graph (`03-KNOWLEDGE-BASE.md` §4).

    Both parties also *remember the telling*, which matters more than it looks:
    a rumour you were told is an event that happened to you, so it decays, can
    be recalled by a cue, and can itself be misremembered later.
    """
    tuning = tuning or tuning_for(store)
    settings = tuning.rumours()
    if settings.exchanges <= 0:
        return {"told": 0, "drifted": 0}

    pairs = rumour.talkative_pairs(
        store.relations.familiar(settings.familiarity_floor), rng, settings
    )
    told, drifted = 0, 0
    for relation in pairs:
        teller = store.entities.get(relation.from_id)
        listener = store.entities.get(relation.to_id)
        if teller is None or listener is None:
            continue

        held = store.beliefs.held_by(teller.id)
        chosen = rumour.pick(held, listener.id, rng, max_hops=settings.max_hops)
        if chosen is None or not rumour.will_share(chosen, traits_of(teller), rng):
            continue
        # Do not tell someone what they already think. Without this, two people
        # trade the same claim back and forth forever — the original witness ends
        # up being told her own rumour, and the collection fills with echoes.
        if any(str(b.subject_id) == str(chosen.subject_id)
               for b in store.beliefs.held_by(listener.id)):
            store.beliefs.mark_shared(chosen.id, listener.id)
            continue

        # How much the *listener* trusts the teller decides what arrives — not
        # how much the teller likes them. You discount what you are told by who
        # told you.
        trust = max(0.0, store.relations.between(listener.id, teller.id).trust)
        claim, mutations, trust = rumour.travel(chosen, trust, rng, settings)
        if mutations > chosen.mutations:
            drifted += 1

        store.beliefs.add(belief_model.adopt(
            claim,
            holder_id=listener.id,
            subject_id=chosen.subject_id,
            source_kind=belief_model.SOURCE_TOLD,
            source_id=teller.id,
            at=world_time,
            trust=trust,
            mutations=mutations,
        ))
        store.beliefs.mark_shared(chosen.id, listener.id)
        told += 1

        gist = f"{teller.identity.name} said {claim}"
        for holder, other in ((listener, teller), (teller, listener)):
            remember(
                store, holder, gist,
                world_time=world_time, rng=rng,
                valence=0.0,
                participants=[teller.id, listener.id],
                salience_scale=0.5,     # hearing a thing is not living it
                tuning=tuning,
            )

    return {"told": told, "drifted": drifted}


def advance_clocks(store, campaign, days: float, world_time: int) -> dict:
    """Move every running front, and fire what the filled ones were aimed at.

    This is what makes ignoring a problem cost something, which is most of the
    difference between a world and a set of rooms.
    """
    moved, completed = 0, []
    for clock in store.clocks.ticking():
        if not clock.running:
            continue                      # blocked: somebody is holding it shut
        filled = clock_model.advance(clock, days, world_time=world_time)
        store.clocks.save(clock)
        moved += 1
        if filled:
            completed.append(clock)

    for clock in completed:
        store.events.append(
            events.CLOCK_FILLED,
            actor_id=clock.faction_id or 0,
            payload={
                "clock": clock.name,
                "clock_id": str(clock.id),
                "segments": clock.segments,
            },
        )
        # Consequences are data, so a front can be authored without code and a
        # completed one replays identically.
        for effect in clock.on_complete:
            kind = str(effect.get("kind", ""))
            payload = dict(effect.get("payload") or {})
            if kind == "start_clock":
                store.clocks.create(clock_model.Clock(
                    name=str(payload.get("name", f"After {clock.name}")),
                    segments=int(payload.get("segments", 8)),
                    rate=float(payload.get("rate", clock.rate)),
                    faction_id=clock.faction_id,
                    created_at=world_time,
                ))
            elif kind in ("announce", "spawn_event"):
                store.events.append(
                    events.CLOCK_EFFECT,
                    actor_id=clock.faction_id or 0,
                    payload={"clock": clock.name, **payload},
                )

    return {"moved": moved, "filled": [c.name for c in completed]}


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
    # A table that did not switch desire on cannot have a romance recorded
    # between its characters, by a command or by the engine. Refusing here
    # rather than filtering the deltas means it never half-happens.
    if kind in rel_mod.ROMANTIC and not romance_allowed(tuning):
        return store.relations.between(from_entity.id, to_entity.id)

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

    # What they want about this person follows how they now feel about them.
    # Here rather than in the pure layer because it needs the stored goals, and
    # here rather than on the tick because a grudge should cool when the thing
    # that cooled it happened, not on the next quarter hour.
    reweigh_goals(store, from_entity, subject_id=to_entity.id,
                  world_time=world_time, magnitude=intensity, tuning=tuning)
    # And who they are follows what they live through. Nobody is one archetype
    # and nobody stays the same mixture.
    drift_packs(store, from_entity, world_time=world_time, tuning=tuning)
    return saved


def romance_allowed(tuning: Tuning | None = None) -> bool:
    """Whether this campaign has opted into desire at all.

    One question, asked in one place, so the need, the relationship axis, the
    interactions and the panel can never disagree about whether a table said
    yes — and so that adding the next optional need is one entry rather than a
    hunt through four modules.
    """
    view = tuning.needs() if tuning else needs_mod.DEFAULT_NEEDS
    return "desire" in view.optional


def attraction_of(store, entity: Entity, other_id, *, world_time: int,
                  tuning: Tuning | None = None) -> float:
    """How drawn this entity is to that one, 0..1. Zero unless asked for."""
    tuning = tuning or tuning_for(store)
    if not romance_allowed(tuning):
        return 0.0
    other = store.entities.get(other_id)
    return rel_mod.attraction(
        store.relations.between(entity.id, other_id),
        allure=other.allure if other else 0.5,
        pressure=needs_of(entity, world_time, tuning).value("desire"),
    )


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
    # The GM's own words, if they wrote any, go to everyone unchanged — authored
    # text is not ours to re-person. Otherwise each party's memory is worded from
    # their own side of it, below, in the loop that already knows their role.
    told = description.strip()
    gist_tuning = tuning.gists()
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
            told or narrate.episode_gist(
                kind, actor.identity.name, subject.identity.name,
                role=role, tuning=gist_tuning,
            ),
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
    archetype: str = "",
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

    # Both directions, as asked. Left alone, an archetype is *noticed* in whoever
    # the dice produced. Named, it pulls them toward it first — the quick way to
    # get a coward when a coward is what the scene needs, and the one place in
    # this engine where a prior is read forwards.
    wanted = packs_for(store).get(archetype) if archetype else None
    if wanted is not None:
        entity_traits = behaviour.shaped_by(
            entity_traits, wanted, tuning.behaviour()
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

    # Archetypes drawn from who they turned out to be, not from the label on
    # them — the same backwards read as the role, one line later so it can see
    # the finished disposition.
    assign_packs(store, entity, rng, campaign=None, tuning=tuning, first=wanted)

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
