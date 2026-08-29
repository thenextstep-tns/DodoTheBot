# Decision Engine

How an NPC decides what to do. Pure Python, sub-millisecond, seeded, explainable.
**No LLM is consulted at any point in this file.**

---

## 1. Why utility AI

- **Behaviour trees** don't scale with traits — every personality axis multiplies
  the branches, and the tree becomes unauthorable at about three axes.
- **GOAP** plans well but costs a search per decision, which one vCPU cannot spend
  on 8 focus NPCs per turn.
- **Utility AI** scores a flat candidate list against weighted curves. Traits
  become *weights*, so ten axes cost nothing extra, and every decision comes with
  a natural explanation: the scores themselves.

That last property is the one that matters. `07`'s explainability panel and the
GM's trust in the system both depend on being able to say *"fear 0.71, imprint
`the-fire`, debt to Marla 3"* — which utility AI hands you for free and the other
two do not.

## 2. The pipeline

```
        ┌──────────────┐
scene ─►│  1 PERCEIVE  │─► stimuli (filtered by senses, attention, traits)
        ├──────────────┤
        │  2 APPRAISE  │─► emotion delta, need updates, impulse generation
        ├──────────────┤
        │  3 PROPOSE   │─► candidate actions (behaviour packs × affordances)
        ├──────────────┤
        │  4 SCORE     │─► U per candidate, with a per-term trace
        ├──────────────┤
        │  5 SELECT    │─► softmax(U / temperature), seeded
        ├──────────────┤
        │  6 COMMIT    │─► WorldEvent → witnesses encode → relations shift
        └──────────────┘
```

Steps 1–5 are pure functions of `(EntityView, Scene, Random)`. Step 6 is the only
one that writes.

**The engine is never handed world state.** It receives an `EntityView` — a
projection built from that entity's beliefs, memories and perception
(`04-ENTITIES.md` §6). NPCs act on what they believe, enforced at the type level
rather than by discipline.

## 3. Perceive

```python
def perceive(view: EntityView, scene: Scene) -> list[Stimulus]:
    out = []
    for thing in scene.contents:
        if not in_sense_range(view, thing, scene):        # distance, light, cover
            continue
        p = notice_probability(view, thing)               # salience × attention
        if rng.random() < p:
            out.append(Stimulus(thing, clarity=clarity(view, thing, scene)))
    return out
```

`attention` is trait-modulated: high `diligence` notices detail, high `volatility`
fixates on threats, high `curiosity` notices the novel. An NPC missing something
obvious because they were arguing is correct behaviour, not a bug.

## 4. Appraise

Each stimulus is scored against needs, goals, beliefs and relationships to produce
an emotion delta:

```python
def appraise(view, stimulus) -> Appraisal:
    threat    = danger(stimulus, view) * (0.5 + view.traits.fear_of_death)
    desire    = need_satisfaction(stimulus, view.needs)
    social    = relationship_valence(view, stimulus.entity)
    novelty   = 1 - familiarity(view, stimulus)
    memory    = recall_valence(view, stimulus.cues)   # 05-MEMORY.md §7
    return Appraisal(
        valence = clamp(desire + social + 0.6 * memory - threat, -1, 1),
        arousal = clamp(threat + 0.4 * novelty + abs(memory), 0, 1),
    )
```

`recall_valence` is where imprints bite: a cue matching an imprint injects its
full valence into the appraisal, so the NPC who was burned reacts to fire before
reasoning about it.

Appraisal also **generates impulses** (`05-MEMORY.md` §6) and updates needs.

## 5. Propose

Candidates come from two sources, intersected:

- **Behaviour packs** — archetype action sets from the global KB (`coward`,
  `zealot`, `merchant`, `predator`, `loyalist`, `opportunist`). An entity has
  1–3, weighted.
- **Affordances** — what this scene physically permits, from
  `ruleset.affordances(actor, scene)`: attack, flee, speak, give, take, hide,
  wait, use, move.

```python
candidates = [
    a for pack in view.packs for a in pack.actions
    if a.spec in scene_affordances and a.preconditions_met(view, scene)
]
candidates.append(Action("wait"))     # always available; the null action matters
```

Typically 5–20 candidates. Capped at `CANDIDATE_CAP = 24` (lowest pack weight
dropped first) so the cost is bounded regardless of scene complexity.

## 6. Score

```python
def utility(view, action, scene) -> tuple[float, dict]:
    terms = {
        "need":       W_NEED       * need_gain(action, view.needs),          # urgency³
        "impulse":    W_IMPULSE    * impulse_match(action, view.impulses),
        "relation":   W_RELATION   * relationship_gain(action, view, scene),
        "goal":       W_GOAL       * goal_progress(action, view.goals),
        "risk":       W_RISK       * -risk(action, view) * (0.5 + view.traits.fear_of_death),
        "trait":      W_TRAIT      * trait_affinity(action, view.traits),
        "imprint":    W_IMPRINT    * imprint_pressure(action, view),
        "norm":       W_NORM       * social_acceptability(action, view, scene),
    }
    return sum(terms.values()), terms
```

Three rules that keep this authorable:

1. **Every term is bounded to −1…1** before weighting, so no single term can
   silently dominate and weights stay comparable.
2. **Curves, not lines.** Needs are cubed (`04-ENTITIES.md` §5); risk aversion is
   exponential in `fear_of_death`; social norms saturate. Linear utility produces
   NPCs who behave like spreadsheets.
3. **The trace is returned, always.** `terms` is stored on the resulting
   `WorldEvent`. That dict is the explainability feature and the debugger.

Weights are global constants tuned once; **traits modulate the terms, not the
weights.** Per-entity weights would be untunable — with 200 NPCs you would never
find the one that is wrong.

## 7. Select

```python
def select(scored, temperature) -> Action:
    T = 0.15 + 0.6 * view.traits.volatility      # steady NPCs are predictable
    weights = [exp(u / T) for u, _ in scored]
    return rng.choices([a for a, _ in scored], weights)[0]
```

Softmax rather than argmax: the best action usually wins, sometimes it doesn't,
and impulsive characters surprise you. `rng` is seeded from
`(campaign_seed, entity_id, tick)` so a replay reproduces it exactly.

## 8. Commit

```python
event = WorldEvent(kind=action.kind, actor_id=view.id, targets=action.targets,
                   payload=outcome.payload, seed=seed, caused_by=trigger_seq)
append(event)
for witness in scene.entities:
    draft = encode(event, witness, rng)     # 05-MEMORY.md §3 — perception applies
    if draft: store(draft)
apply_relationship_deltas(event)            # 04-ENTITIES.md §7
maybe_propagate_belief(event)               # 03-KNOWLEDGE-BASE.md §4
```

The engine emits an event. Whether anyone *narrates* it is a separate decision
made a layer up (`01-ARCHITECTURE.md` §1, Invariant 1).

## 9. Off-screen behaviour

`active`-tier NPCs run a **coarse** pipeline on the world tick: no perception (no
scene), candidates drawn from goals and needs only, no softmax (argmax, cheaper).
Roughly 0.1 ms each.

`dormant` NPCs do not run at all. When observed, their state is extrapolated in
closed form (`01-ARCHITECTURE.md` §6): needs advanced by elapsed time, memory
decayed, goal progress interpolated along their clock. Identical result, zero
ongoing cost.

## 10. Faction clocks

What makes the world *continue* — the headline feature for async play. Straight
from Apocalypse World's fronts, and entirely LLM-free.

```jsonc
{
  "_id": ObjectId, "campaign_id": …,
  "faction_id": ObjectId,
  "name": "The Compact seizes the north dock",
  "segments": 8, "filled": 3,
  "rate": 0.5,                       // segments per in-world day
  "status": "running",               // running | paused | complete | broken
  "blocked_by": [ObjectId],          // entities/events that stall it
  "on_complete": [{"kind": "spawn_event", "payload": {...}}]
}
```

Each tick: advance `filled` by `rate × elapsed`, unless blocked. On completion,
fire `on_complete` — which emits world events, spawns scenes, shifts faction
relations, and generates rumours that then propagate through the social graph.

Player action can **block, slow or accelerate** a clock. That is the entire
feedback loop between play and world: it means ignoring a problem has
consequences, which is what "continuous world" actually means.

## 11. Performance

| Path | Budget | Notes |
| --- | --- | --- |
| Full pipeline, one focus NPC | < 1 ms | ~20 candidates × 8 terms |
| Coarse pipeline, one active NPC | < 0.1 ms | no perception, argmax |
| Turn, 8 focus NPCs | < 10 ms | inside the 50 ms mechanical budget |
| World tick, 200 active NPCs | < 25 ms | batched, yields between batches |

If the full pipeline exceeds 1 ms, the fix is `CANDIDATE_CAP` or the term count —
never caching decisions, which would break determinism and replay.

## 12. Explaining a decision

Because `terms` is stored on every event, the GM panel can render:

> **Marla drew her knife instead of answering.**
> `imprint +0.62` — cue "green lantern" matched *the night at the north dock*
> `fear +0.41` — she believes you work for the Compact (confidence 0.6, told by Ondry)
> `relation −0.30` — trust −0.4, debt 0
> `norm −0.25` — drawing steel in the harbour office is not done
> `→ U 0.48`, chosen over *answer plainly* (0.31) at T = 0.51

No other product in this space can produce that paragraph, and it is what turns a
GM from suspicious of the AI into a collaborator with it.
