# Architecture

Read `00-PRODUCT.md` first. This file is the system shape: layers, module layout,
data flow, and the invariants that must never be broken.

---

## 1. The layer cake

Strict dependency direction — **each layer may import only from layers below it.**
This is the rule that keeps the LLM from becoming load-bearing.

```
┌──────────────────────────────────────────────────────────────┐
│  SURFACES        cogs/dnd/*.py, web/dnd/*.py                  │
│                  Discord commands & views, panel pages        │
├──────────────────────────────────────────────────────────────┤
│  ORCHESTRATION   helpers/dnd/session.py, turn.py              │
│                  Turn loop, scene lifecycle, world tick       │
├──────────────────────────────────────────────────────────────┤
│  NARRATIVE       helpers/dnd/drama.py, beats.py, suggest.py   │
│                  Drama manager, beat selection, GM assist     │
├──────────────────────────────────────────────────────────────┤
│  MINDS           helpers/dnd/mind/ (decide, appraise,         │
│                  memory, needs, knowledge)                    │
├──────────────────────────────────────────────────────────────┤
│  WORLD           helpers/dnd/world/ (entity, scene, event,    │
│                  faction, clock, time)                        │
├──────────────────────────────────────────────────────────────┤
│  RULES           helpers/dnd/rules/ (ruleset, dice, resolve)  │
├──────────────────────────────────────────────────────────────┤
│  STORAGE         helpers/dnd/store/ (repositories, indices)   │
└──────────────────────────────────────────────────────────────┘

        ┌─────────────────────────────────────────────┐
        │  LLM  helpers/dnd/llm/                       │
        │  A leaf service. Called BY orchestration     │
        │  and narrative. Imports nothing above        │
        │  storage. Never imported by world/rules.     │
        └─────────────────────────────────────────────┘
```

**Invariant 1 — the LLM is a leaf.** `world/`, `rules/`, `mind/` and `store/` must
never import `llm/`. If a simulation module needs prose, it emits a *render
request* and someone above it decides whether to call a model. Enforced by a test
that greps imports (`14-CONVENTIONS.md` §5).

**Invariant 2 — truth flows up only.** The LLM's output is *never* written to
world state directly. It goes to the canon queue (`03-KNOWLEDGE-BASE.md` §5) or
it is display-only text.

**Invariant 3 — every layer below NARRATIVE is pure and synchronous.** No I/O, no
`await`, no clock reads, no `random` module. State in, state-delta out. That is
what makes the simulation testable and replayable.

---

## 2. Module layout

Mirrors the existing convention: logic in `helpers/`, Discord surface in `cogs/`,
web surface in `web/`. `web/routes.py` is already 3281 lines — DnD panel pages get
their own module and are mounted from `create_app`, never appended to it.

```
helpers/dnd/
├── __init__.py
├── store/
│   ├── repo.py           # base repository: guild+campaign scoping, projections
│   ├── entities.py       # entity CRUD, component loading
│   ├── campaigns.py
│   ├── knowledge.py      # KB facts, retrieval scoring
│   ├── events.py         # append-only event log
│   └── indices.py        # index definitions, applied at startup
├── rules/
│   ├── ruleset.py        # Ruleset protocol + registry
│   ├── dice.py           # dice grammar: 2d6+3, 4d6kh3, adv/dis, exploding
│   ├── resolve.py        # check / contest / save resolution
│   ├── freeform.py       # ruleset impl: narrative
│   └── srd5e.py          # ruleset impl: SRD 5.1 (CC-BY-4.0)
├── world/
│   ├── entity.py         # Entity + component dataclasses
│   ├── scene.py          # scene state, presence, affordances
│   ├── event.py          # WorldEvent, the one way state changes
│   ├── faction.py
│   ├── clock.py          # fronts/clocks, agenda advancement
│   └── time.py           # world time, tick scheduling, tiers
├── mind/
│   ├── needs.py
│   ├── traits.py         # traits, inheritance, derivation
│   ├── knowledge.py      # beliefs: source, confidence, propagation
│   ├── memory/
│   │   ├── tiers.py      # working / mid / long / imprint
│   │   ├── salience.py
│   │   ├── decay.py      # field-wise degradation + confabulation
│   │   ├── consolidate.py
│   │   └── recall.py     # cue matching, reconsolidation
│   ├── appraise.py       # stimulus → emotion delta
│   ├── impulse.py
│   └── decide.py         # utility scoring + softmax selection
├── narrative/
│   ├── drama.py          # tension, spotlight, pacing
│   ├── beats.py          # beat catalogue + selection
│   └── suggest.py        # GM-assist proposals
├── llm/
│   ├── backend.py        # Backend protocol
│   ├── ollama.py         # the ONLY inference backend (08 §1)
│   ├── null.py           # template-only; always available, always tested
│   ├── tasks.py          # render_scene, render_dialogue, parse_intent fallback
│   ├── queue.py          # priority queue; one host, serialized (08 §8)
│   ├── cache.py
│   └── budget.py         # per-guild/campaign call accounting
├── session.py            # scene lifecycle, PersistentFlow subclass
├── turn.py               # the turn loop (§4)
├── tick.py               # the world tick (§5)
└── entitlements.py       # tier gating (10-MONETIZATION.md)

cogs/dnd/
├── __init__.py           # the Cog; setup() registers everything
├── play.py               # player commands & views
├── gm.py                 # GM commands
└── sheet.py              # character sheet views

web/dnd/
├── __init__.py           # route table, mounted from web/routes.py:create_app
├── pages.py              # HTML rendering
└── api.py                # JSON endpoints
```

---

## 3. The event log is the spine

**Every** state change is a `WorldEvent`, appended to a per-campaign log before
anything is mutated. Entity state is a *projection* of the log.

```python
@dataclass(frozen=True)
class WorldEvent:
    campaign_id: ObjectId
    seq: int                 # monotonic per campaign
    world_time: int          # in-world minutes since epoch
    kind: str                # "move" | "attack" | "speak" | "give" | ...
    actor_id: ObjectId | None
    targets: tuple[ObjectId, ...]
    payload: dict            # BSON-safe, kind-specific
    seed: int                # RNG seed used to resolve it
    caused_by: int | None    # seq of the event that triggered this
```

This buys, for one design decision:

- **Replay** — re-run a campaign from seq 0 and get byte-identical state.
- **Explainability** — `caused_by` chains render as "why did that happen".
- **Witness encoding** — memory is written from events, so perception filters
  apply uniformly (`05-MEMORY.md` §3).
- **Regression tests** — a recorded log is a test fixture for the whole sim.
- **Undo** — the GM's most-wanted feature, free.

Cost control: logs are **compacted** per arc. Events older than the current arc
collapse into a snapshot plus retained high-salience events. See
`02-DATA-MODEL.md` §7.

## 4. The turn loop

What happens when a player types an action. Timings are budgets, not guesses.

```
player input
   │
   ├─ 1. parse_intent            verb parser FIRST             <1 ms
   │      → Action | Clarify     Model only on genuine ambiguity (08 §5),
   │                              and even then, asking the player often beats
   │                              guessing. Never blocks step 2 on failure.
   ├─ 2. validate                 pure                          <1 ms
   │      affordances, reach, resources, entitlements
   ├─ 3. resolve                  pure, seeded                  <1 ms
   │      ruleset.resolve(action, actor, target) → outcome
   ├─ 4. emit WorldEvent          storage                       ~5 ms
   │      ◀── POST MECHANICAL OUTCOME TO DISCORD HERE ──▶
   │
   ├─ 5. propagate                pure                          <5 ms
   │      witnesses perceive → encode memory → relationship deltas
   │      → knowledge updates → impulse generation
   ├─ 6. react                    pure                          <1 ms/NPC
   │      focus NPCs decide (06-DECISION-ENGINE.md)
   ├─ 7. beat                     pure                          <1 ms
   │      drama manager picks the next beat
   └─ 8. render                   LLM, streamed                 ~1-10 s
          render_scene / render_dialogue
          Fallback: templated prose from the same state-delta.
```

**Steps 2–7 are the game.** Step 1 and step 8 are cosmetics that can degrade to
templates without the game stopping. That split is the whole architecture in one
diagram.

The user-visible latency budget is step 4 — under 50 ms to "you hit for 7,
the guard staggers." Prose arrives when it arrives.

## 5. The world tick

A scheduled job (`discord.ext.tasks`, default every 10 in-world minutes /
configurable real interval) that advances the world with **no LLM involvement at
all**:

1. Advance world time.
2. Tick needs for `focus` + `active` entities.
3. Decay memory, run consolidation for entities due (staggered, not all at once).
4. Advance faction clocks; fire agenda events whose clock filled.
5. Propagate rumours along the social graph.
6. Run `active`-tier NPC decisions at coarse granularity.
7. Compact logs if due.

Cost is bounded by tier population, not world population — see §6.

## 6. Simulation tiers

The single most important performance decision.

| Tier | Who | Ticks | Memory tiers active | Cost |
| --- | --- | --- | --- | --- |
| `focus` | In the active scene | Every tick, full pipeline | all | ~1 ms/entity |
| `active` | Same region, or on a clock | Coarse (every N ticks), no perception | mid, long, imprint | ~0.1 ms/entity |
| `dormant` | Everyone else | **Never** | long, imprint only | 0 |

A `dormant` entity's state is **extrapolated on demand** when something looks at
it: needs advanced by elapsed time in closed form, memory decayed by elapsed
time, clock positions computed. It is a pure function of `(stored_state, Δt)`, so
it costs nothing until observed and produces the same answer as if it had ticked.

Promotion `dormant → active → focus` happens when a scene includes them, a clock
targets them, or a player asks about them.

## 7. Multi-tenancy

Chosen at planning time: **product for many servers.** Therefore, from the first
commit:

- Every document carries `guild_id` **and** `campaign_id`. No exceptions, no
  "we'll add it later" — the current cog's missing `guild_id` is exactly the
  mistake being corrected.
- All repository reads go through `store/repo.py`, which **requires** a scope
  object and injects the filter. Raw collection access outside `store/` is a
  review failure.
- Cross-campaign reads are impossible by construction, not by discipline.
- Global-tier KB is the only unscoped collection, and it is read-only at runtime.

## 8. Concurrency

One bot process, one event loop, `pymongo` (synchronous) as the rest of the
codebase uses. Therefore:

- **Simulation code must never block the loop for long.** The pure layers are
  sub-millisecond by design; the world tick processes entities in bounded batches
  and yields between them.
- **Per-campaign serialization.** All mutations for a campaign go through a
  single asyncio lock keyed by `campaign_id`, so two players acting at once can't
  interleave a half-applied event. Cheap and it removes an entire class of bug.
- **Optimistic concurrency** on the event log via the `seq` unique index — a
  duplicate-key error means someone else wrote first; re-read and retry.
- Long LLM calls happen **outside** the lock. Resolve first, release, then render.

## 9. Integration points with the existing bot

| Existing system | How DnD uses it |
| --- | --- |
| `bot.params` | Per-guild tunables: tick interval, inference host URL and model, daily render cap, default ruleset, NPC simulation cap. Adding specs gives free panel inputs. |
| `bot.visibility` | Cog gate `dnd`; features `dnd_world_tick`, `dnd_autonomous_gm`, `dnd_npc_chatter` toggle independently per guild. |
| `bot.panel_access` | Server-level scopes as today, **plus** a new per-campaign GM grant — see `09-SURFACES.md` §4. |
| `bot.state` | `session.py` subclasses `PersistentFlow` (`kind = "dnd_scene"`) so live scenes survive restarts. |
| `bot.lang` | Every player-facing string. New `DND_*` keys replace the 21 existing ones. |
| `config_audit` | Campaign KB edits and GM overrides are audited like any panel change. |
| `helpers/health.py` | Tick duration, LLM latency and token spend become health samples. |

## 10. Testing strategy

The determinism is what makes this cheap:

- **Golden replays** — a recorded event log replays to an identical state hash.
  One fixture covers the entire simulation.
- **Property tests** — memory never exceeds budget; salience is monotonic in
  reinforcement; utility scores are finite; decay never resurrects a field.
- **Import-boundary test** — `llm/` is not imported by `world/`, `rules/`,
  `mind/` or `store/`.
- **Null-backend suite** — the full turn loop, end to end, with `backend=null`.
  If this suite fails, Invariant 1 has been violated somewhere.
- **Tenant isolation test** — two campaigns, identical entity names; every
  repository method is checked for leakage.
