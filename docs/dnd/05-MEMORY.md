# Memory Model

The subsystem the product lives or dies on. Entirely non-AI: encoding, decay,
consolidation and recall are arithmetic over structured records. No model is
consulted to remember anything.

---

## 1. Tiers

| Tier | Holds | Lifetime | Decays |
| --- | --- | --- | --- |
| **working** | Current scene, verbatim | Evicted at scene end | — |
| **mid** (episodic) | This arc, compressed into episodes | Consolidated at arc end | Slowly |
| **long** (semantic) | Consolidated facts + valence | Campaign lifetime | Yes, field-wise |
| **imprint** | Formative events | Permanent | **Never** |
| *impulse* | Not memory — urges (§6) | Minutes | Rapid |

Flow:

```
event → perceive → encode(working)
                       │ scene end
                       ▼
                   consolidate → mid
                       │ arc end
                       ▼
                   consolidate → long ──► decay ──► degraded / confabulated
                       │
                       └─ salience ≥ IMPRINT_THRESHOLD ──► imprint (no decay)
```

## 2. Salience — the master value

Computed once at encoding, updated on reinforcement. It drives everything:
promotion to imprint, decay rate, recall probability, and what survives pruning.

```python
def salience(m: MemoryDraft, witness: Entity) -> float:
    emotional  = abs(m.valence) * m.arousal                  # intensity
    novelty    = 1.0 - similarity_to_existing(m, witness)    # surprise
    relevance  = personal_stake(m, witness)                  # was it about them
    social     = max(affinity_weight(witness, p) for p in m.participants)
    return clamp(
        0.35 * emotional + 0.25 * relevance +
        0.20 * novelty   + 0.20 * social,
        0.0, 1.0,
    )
```

Reinforcement (the same thing happening again) is multiplicative and saturating:

```python
salience = 1 - (1 - salience) * (1 - REINFORCE_GAIN)      # REINFORCE_GAIN ≈ 0.15
```

so repetition strengthens but never quite reaches certainty — and repeated small
slights genuinely accumulate into a grudge.

`IMPRINT_THRESHOLD = 0.85` at encoding, or `recall_count >= 8` with
`salience > 0.6` — trauma forms either from one overwhelming event or from
something returned to over and over. Both routes matter.

## 3. Encoding — witnesses perceive, they do not observe

**The most important function in the module.** Memory is written from
`WorldEvent`s, but each witness encodes *what they perceived*, not what happened.

```python
def encode(event: WorldEvent, witness: Entity, rng: Random) -> MemoryDraft | None:
    if not perceives(witness, event):        # senses, attention, distance, light
        return None

    clarity = perception_clarity(witness, event)   # 0..1: distance, light,
                                                   # distraction, conditions, traits
    draft = MemoryDraft.from_event(event)

    if clarity < 0.7:                              # partial perception
        draft.participants = drop_some(draft.participants, 1 - clarity, rng)
        draft.details      = drop_some(draft.details, 1 - clarity, rng)
    if clarity < 0.4:                              # misperception
        draft.gist = coarsen(draft.gist)           # "a fight" not "Marla stabbed Ondry"

    draft.valence = appraise(event, witness)       # THEIR feelings, not the event's
    draft.arousal = arousal(event, witness)
    draft.salience = salience(draft, witness)
    draft.cues = extract_cues(draft)               # objects, places, names, smells
    return draft
```

Two witnesses to one event produce **two different memories**, with different
valence, different detail, sometimes different participants. Every grudge, rumour,
false accusation and misunderstanding in the game originates here — not from a
"generate a misunderstanding" feature.

## 4. Decay — degradation, not deletion

Fields rot **independently and in order**. This is the mechanic that makes the
memory model feel like memory rather than a cache with a TTL.

```python
DECAY_RATE = {          # per world-day, scaled by (1 - salience)
    "gist":         0.002,   # survives longest
    "valence":      0.004,   # you remember how it felt after you forget what it was
    "participants": 0.010,
    "details":      0.025,
    "when":         0.040,   # time and place go first
}

def decay(m: Memory, days: float) -> None:
    if m.tier == "imprint":
        return
    for field, rate in DECAY_RATE.items():
        m.fidelity[field] *= exp(-rate * days * (1 - m.salience))
```

Rendering consults fidelity:

| Fidelity | Rendered as |
| --- | --- |
| `> 0.7` | The value, plainly |
| `0.3–0.7` | Hedged — "a woman, maybe the harbourmaster" |
| `< 0.3` | Dropped, **or confabulated** |

### Confabulation

Below `CONFABULATE_THRESHOLD = 0.2`, a field may be **filled with a plausible
wrong value** instead of dropped — drawn from the entity's other memories and
beliefs, so it is wrong in a *characteristic* way. The field is recorded in
`confabulated` so the GM panel can show it.

An NPC who remembers the wrong person holding the knife — confidently — is worth
more than any amount of prompt engineering.

## 5. Budgets — how this stays lightweight

Each entity has a hard cap per tier, scaled by `importance`:

```python
budget = {
    "mid":     int(12 + 60 * importance),     # 12 … 72
    "long":    int(20 + 200 * importance),    # 20 … 220
    "imprint": int(3 + 12 * importance),      # 3 … 15
}
```

A nameless guard: 12 mid, 20 long, 3 imprints. A named questgiver: ~70/220/15.

When a tier exceeds budget, prune **lowest salience first**, but never an imprint
and never anything recalled within the last N days. Pruned mid-term memories are
merged into a single low-salience summary rather than vanishing, so the gist
survives even when the episodes do not.

This is the bounded-cost guarantee. 500 NPCs is a fixed, known bill — the exact
opposite of the current cog's unbounded `history` string.

## 6. Impulses

Not memory. A short-lived urge queue, and the decision engine's direct input.

```python
@dataclass
class Impulse:
    kind: str            # "flee" | "eat" | "confront" | "boast" | "hide" | ...
    strength: float      # 0..1
    target_id: ObjectId | None
    born_at: int         # world time
    half_life: float     # world minutes
```

Generated by:
- **Needs** over threshold — `hunger > 0.7` → `eat`
- **Stimuli** — a threat appears → `flee` or `confront`, split by `boldness`
- **Cue-triggered imprints** (§7) — a strong urge with the imprint's valence
- **Trait pressure** — high `curiosity` in an unexplored place → `investigate`

Decay: `strength * 0.5 ** (elapsed / half_life)`, dropped below 0.05. Impulses are
*pressure*, not commands — the utility scorer weighs them against everything else,
so a disciplined NPC feels the urge to run and holds the line. That gap between
impulse and action is where character lives.

## 7. Recall & reconsolidation

Recall is **cue-driven**, not query-driven:

```python
def recall(entity, cues: list[str], limit: int) -> list[Memory]:
    scored = [
        (m, cue_overlap(m.cues, cues) * m.salience * recency_boost(m))
        for m in memories_of(entity)
    ]
    return top_n(scored, limit)
```

Indexed on `(entity_id, cues)` (`02-DATA-MODEL.md` §8), so a walk into the harbour
in the rain surfaces the harbour-in-the-rain memories without scanning.

**Reconsolidation** — recalling rewrites:

```python
m.recall_count += 1
m.salience = reinforce(m.salience)
m.fidelity["gist"] = min(1.0, m.fidelity["gist"] + 0.05)   # gist strengthens
if rng.random() < 0.1:                                      # …and detail corrupts
    import_current_context_as_detail(m, current_scene)
```

The NPC who has told the story a hundred times remembers it vividly — and wrongly,
with details borrowed from the tellings rather than the event. Cheap to implement,
and it is exactly how human memory behaves.

## 8. Consolidation

Runs at scene end (working → mid) and arc end (mid → long), staggered across
entities on the world tick so no single tick is expensive.

- **working → mid**: group by episode, compute episode salience, drop below
  `0.15`, keep gist + valence + participants.
- **mid → long**: extract the *semantic* content — "Marla betrayed me" survives
  as a fact even after the episode decays. Contradictions with existing long-term
  memory raise confidence in whichever has higher salience rather than storing
  both.
- Anything crossing `IMPRINT_THRESHOLD` is promoted, not consolidated.

**Consolidation calls no model at all** (`08-LLM-LAYER.md` §5). The grouping,
scoring and selection were always deterministic; the gist is a template built from
event kinds and participants. Only the engine reads these — no player ever sees a
raw gist — so prose quality buys nothing here, and paying a model for it would be
exactly the drift the deterministic-first rule exists to prevent.

## 9. What the GM sees

A memory inspector on the panel, per entity — the debugging tool that doubles as
a headline feature:

- Each tier, sorted by salience, with fidelity bars per field
- Confabulated fields flagged in red, with the true value beside them
- Imprints and their cues
- Live impulse queue with decay curves
- Recall trace: "this NPC just recalled X because you said 'lantern'"

Anyone can claim their NPCs have memory. Showing the GM a decaying, misremembered,
cue-triggered memory with the true value next to it is the demo that sells the
product.
