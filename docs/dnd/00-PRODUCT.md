# Dodo Tabletop — Product Definition

> The living-world tabletop engine. A Discord bot where the world keeps turning
> while you're asleep, the NPCs remember what you did to them, and the AI never
> gets to decide what's true.

Status: **design, not built**. Nothing in this directory describes existing code
except where it explicitly names a current file.

---

## 1. The thesis

Every "AI Dungeon Master" product on the market fails the same way: **the LLM is
the world state.** The model holds the story in its context window, so it
contradicts itself, forgets your brother's name, invents a castle that wasn't
there, and can be talked into giving you a +10 sword by a player who types
persuasively. The product feels magical for twenty minutes and hollow by hour
three.

Our inversion:

> **The world is a deterministic simulation. The LLM is a translator at two
> edges — player text → intent, and state-delta → prose. Nothing the model says
> is true until the simulation says it is.**

Consequences that fall straight out of this, all of them load-bearing:

| Because the sim owns truth… | We get |
| --- | --- |
| The model never has to remember | Small models work. A 4B is enough to *phrase* a fact it is handed. |
| The model never has to reason | No chain-of-thought latency, no reasoning-model pricing. |
| Every decision is Python | Sub-millisecond, reproducible, unit-testable, and **explainable to the GM**. |
| Prose is the last step | Mechanics resolve instantly; narration streams in after. Feels fast on any hardware. |
| The LLM is optional | The game is fully playable with the LLM disabled. That is an architectural requirement, not a nicety — see §6. |

The differentiator is not "AI dungeon master." Fifty products claim that. The
differentiator is **minds that persist and a world that continues** — and those
are simulation problems, not prompting problems.

---

## 2. What we are replacing

`cogs/dnd.py` today, honestly assessed:

- **Character sheets are decorative.** Every character created gets the same
  hardcoded block: `STR 15, DEX 14, CON 13, INT 12, WIS 10, CHA 8`, HP 10, AC 10.
  A `relationships: {}` field is written on creation and never read again.
- **Dice are cosmetic.** The "Roll Dice" button prints a number to the roller and
  feeds into nothing. Action resolution never consults a stat or a die. Initiative
  is typed in by hand.
- **Memory is an unbounded string.** Each action appends an LLM-written bullet
  summary to `session.history`, forever. The prompt grows without limit until it
  exceeds context and cost. There is no forgetting, no salience, no structure.
- **It is single-tenant.** No `guild_id` on any document; `DND_FORUM_CHANNEL_ID`
  is one global constant. Two servers cannot use it.
- **It is disconnected from the platform.** Not registered with `bot.state` (a
  restart drops everything), absent from `PARAMETERS` (nothing tunable per
  server), no control-panel presence.

It is a chat wrapper with a session table. Every capability this document
describes is a capability it does not have, which is why this is a rewrite and
not a refactor. See `13-MIGRATION.md` for how existing data gets carried across.

## 3. What we keep from the codebase

The bot around it is well built and the new module is a citizen of it, not a
kingdom beside it:

- **`bot.params`** (`helpers/parameters.py`) — typed per-guild registry; adding a
  spec renders a panel input for free.
- **`bot.visibility`** (`helpers/visibility.py`) — per-guild cog/command/feature
  gating. The source already notes features are individually toggleable "for
  monetization flexibility"; that is our enforcement point.
- **`bot.panel_access`** (`helpers/panel_access.py`) — scoped web access
  (`none/stats/config/full/owner`). Campaign GMs need a **new** scope concept —
  a GM is not a server admin. See `09-SURFACES.md`.
- **`bot.state`** (`helpers/state_machine.py`) — persistent resumable flows.
- **`bot.lang`** (`helpers/lang_manager.py`) — per-guild, per-locale overridable
  strings. All player-facing text goes through it.
- **`config_audit`** + `helpers/audit_log.py` — every panel change recorded.

And one idea worth generalizing: `cogs/chat.py`'s **rumour system** stores a fact
*about someone else*, *with a source attribution*. That is the seed of the
knowledge model in §4.3 — the best idea in the current codebase, currently used
for jokes.

---

## 4. The product

### 4.1 Layered knowledge

Four tiers, resolved most-specific-first (the same shape as
`LangManager.get()`'s fallback chain, deliberately):

```
scene  →  campaign  →  server  →  global
```

- **Global** — curated by us. Rulesets, condition definitions, generic
  statblocks, behaviour archetypes, narrative primitives. Ships with the bot.
- **Server** — shared across a server's campaigns: house rules, default tone,
  content limits.
- **Campaign** — the GM's world: lore, factions, locations, NPCs, custom rules,
  GM style, arc plans. Editable on the web panel by campaign admins.
- **Scene** — what is *currently true and on screen*: who is present, lighting,
  weather, time of day, active effects. Cheap, and it is what makes replies feel
  grounded rather than generic.

**Retrieval, not stuffing.** Knowledge is chunked into tagged facts and the
prompt gets a *token budget* filled by relevance score. No embeddings needed at
v1 — tag + keyword + recency scoring runs in microseconds on one core.

**Canon queue.** Anything the LLM invents lands in a *proposed canon* queue, not
in canon. The GM promotes it (or an auto-accept threshold does). This single
mechanism is what prevents world drift, and it makes a great panel page.

Detail: `03-KNOWLEDGE-BASE.md`.

### 4.2 One entity model

PCs, NPCs, monsters and factions are **the same kind of object** with different
components attached. That is the whole point: an NPC has to be as real as a PC.

Components: `identity`, `stats` (schema comes from the ruleset, never hardcoded),
`traits`, `inheritance`, `needs`, `relationships`, `knowledge`, `memory`,
`inventory`, `conditions`, `position`.

- **Traits** — personal qualities on numeric axes (temperament plus drives:
  greed, honour, curiosity, cowardice), plus flaws/bonds/ideals.
- **Inheritance** — parentage, culture, bloodline. Traits are partly derived from
  lineage with variance, so generated NPCs are coherent instead of random, and
  family/dynasty stories come for free.
- **Needs** — hunger, thirst, fatigue, pain, warmth, safety, belonging. They tick
  with world time, and only for *active* entities (see §5).
- **Relationships** — per-pair and multi-axis: affinity, trust, fear, respect,
  debt. Toward PCs *and* toward each other. A faction is an entity with
  relationships and an agenda but no body; faction standing propagates to members
  as a prior that individuals can deviate from based on traits.

Detail: `04-ENTITIES.md`.

### 4.3 Belief, not truth

Every entity has a `knowledge` component: what it *believes*, each belief
carrying a **source** and a **confidence**. NPCs act on beliefs, never on world
truth.

This is the highest-leverage idea in the design. Once beliefs are per-entity and
separate from facts, you get — with no extra machinery —

- NPCs who are **wrong**, and act confidently on it;
- NPCs who **lie** (assert a belief they don't hold) as an ordinary action;
- **rumours** that propagate through a social graph, mutating as they go;
- **fog of war** for players, because a player sheet renders that character's
  beliefs, not the world;
- **dramatic irony**, which is most of what makes a table laugh.

Detail: `03-KNOWLEDGE-BASE.md` §4, `04-ENTITIES.md` §6.

### 4.4 Memory that degrades like memory

Five tiers, matching how memory actually behaves:

- **Working** — the current scene, verbatim, evicted on scene end.
- **Mid-term (episodic)** — this arc's events, compressed into salience-scored
  episodes.
- **Long-term (semantic)** — consolidated at session end: fact + confidence +
  emotional valence.
- **Imprints** — long-term entries that exceeded a salience threshold at encoding
  (betrayal, near-death, first love) or were reinforced N times. **Immune to
  decay.** Cue-triggered, which is how you get "he goes silent when he sees the
  sigil" without scripting it.
- **Impulses** — not memory. A short-lived urge queue generated from needs,
  traits and stimuli, decaying over world-seconds. This is what the decision
  engine consumes.

The part that matters: **decay is degradation, not deletion.** A memory's fields
rot independently, in order — *gist* survives longest, then *valence*, then
*participants*, then *details*, then *time and place*. An old memory becomes
"someone hurt me here, I think, years ago." Degraded slots may be
**confabulated** — filled with a plausible wrong value — so NPCs misremember,
which is both psychologically real and dramatically useful.

**Reconsolidation:** recalling a memory rewrites it, strengthening the gist and
sometimes importing present context as false detail. Cheap to implement, enormous
for flavour.

**Budgets** are what keep this lightweight: each entity gets K entries per tier
scaled by importance — a named questgiver gets 200, a nameless guard gets 12.
Consolidation prunes lowest-salience-first. Cost per entity is bounded, so 500
NPCs is a fixed, small bill.

Detail: `05-MEMORY.md`.

### 4.5 Decisions without AI

Utility AI, not behaviour trees (don't scale with traits) and not GOAP (too slow
to be worth it at v1). Per tick, for an active NPC:

1. **Perceive** — stimuli filtered by senses and attention, both trait-modulated.
2. **Appraise** — score each stimulus against needs, goals, beliefs and
   relationships → an emotion delta.
3. **Propose** — candidate actions from behaviour packs and the affordances of
   the current scene.
4. **Score** — `U = Σ wᵢ · curveᵢ(state)`, weights drawn from traits, needs,
   relationships and imprints.
5. **Select** — softmax, temperature from personality (impulsive NPCs pick more
   randomly), seeded per entity+tick so it is reproducible.
6. **Commit** — the action becomes a world event, witnesses encode it *as they
   perceived it*, relationships shift.

Only the *description* of step 6 touches the LLM. The decision itself is pure
Python and takes under a millisecond.

The subtle bit is step 6: **witnesses encode perception, not truth.** Perception
error is the origin of every grudge, rumour and misunderstanding in the game.

Detail: `06-DECISION-ENGINE.md`.

### 4.6 A world that continues

Faction **agendas advance on clocks** whether or not players engage — the
Apocalypse World "fronts" model, run on a scheduled tick with no LLM involved.
Off-screen NPCs are simulated coarsely (see §5). Come back after a week away and
the war moved, the merchant died, the rumour about you reached the capital.

This is the headline feature for async play-by-post, which is how Discord
tabletop actually works.

### 4.7 Narrative engine, two modes

Underneath both sits a **drama manager**: tension curve, spotlight distribution
(who hasn't acted lately), pacing beats, unresolved threads. It selects the next
*beat* deterministically; the LLM only renders it. Story structure is a state
machine, not a prompt.

- **Suggester** (ships first) — proposes hooks and complications derived from
  actual world state: unresolved goals, faction tension over threshold, imprints
  that could be triggered, dangling proposed-canon. The GM picks. Cheap, safe,
  immediately useful, and it makes the human GM better rather than replacing them.
- **Autonomous GM** — runs scenes, resolves actions, paces the arc. Same
  machinery, no human in the loop.

Detail: `07-NARRATIVE-ENGINE.md`.

---

## 5. Performance posture

Target hardware is unforgiving (1 vCPU, 898 MB), and "relatively lightweight" was
a stated requirement, so it is a design constraint rather than an optimization
pass:

- **Tiered simulation.** `focus` entities (in the active scene) tick fully.
  `active` (same region) tick on a coarse schedule. `dormant` entities do not
  tick at all — their state is *extrapolated on demand* when someone looks at
  them. Cost tracks the number of NPCs on screen, not in the world.
- **Bounded memory per entity** (§4.4) — no unbounded growth anywhere. The
  current cog's `history` string is the anti-pattern we are correcting.
- **Mechanics before prose.** Resolve and post the mechanical outcome in <50 ms,
  stream narration after. The table sees instant feedback regardless of model
  speed.
- **Every LLM call is small and narrow** (§6) — small prompts, JSON out, cached.
- **Seeded determinism** — same seed, same outcome. Enables replay, debugging,
  and cheap regression tests over the whole simulation.

## 6. The LLM layer

Two standing rules, set by the owner:

> **1. No inference leaves hardware we control.** No hosted APIs, no third-party
> providers, in any tier, for any tenant. Local only — Ollama on the owner's
> laptop today (Ryzen 7 8845H, 28 GB LPDDR5X-7500 ≈ 120 GB/s, ~20–28 tok/s on a
> 4B), a machine we own later if the product outgrows it.
>
> **2. Deterministic first.** If it can be computed in Python, it is. A model is
> called only where *prose quality is itself the product*.

Rule 2 is not a slogan — applying it cut the AI surface from five tasks to two:

| Task | |
| --- | --- |
| `summarize_episode` | **Non-AI.** Templated gist; only the engine reads it. |
| `propose_canon` | **Non-AI**, except one bootstrap batch per campaign. |
| `parse_intent` | **Non-AI first**; a model only on genuine ambiguity. |
| `render_scene` | **AI.** Prose quality is the product here. |
| `render_dialogue` | **AI.** Same, plus voice and mood. |

Adding a sixth call site requires justifying it against its deterministic
alternative in writing. The drift from "simulation with a renderer" to "LLM with
extra steps" happens one convenient call site at a time.

Small tasks mean small prompts, low latency, and viability on a 4B model. **Every
one has a deterministic fallback**, and `backend=null` stays a supported, tested
configuration — which is both the proof that the simulation owns the truth and
the reason a sleeping laptop is a non-event rather than an outage.

Detail: `08-LLM-LAYER.md`.

---

## 7. Additions to the original brief

Things not in the request that I think are required, with the reason:

1. **Safety and consent tooling** — lines & veils, an X-card equivalent, per-campaign
   content limits. Non-negotiable for a public roleplay product with LLM output,
   cheap to build as settings, and it protects the business. `11-SAFETY.md`.
2. **Zero-LLM playability as an architectural rule** — the honesty check on §1.
3. **Session-zero bootstrap** — a campaign KB must not require four hours of
   typing. Interview → generate → GM approves. Without this, nothing gets used.
4. **Async-first pacing** — matches how Discord tabletop is actually played and
   turns LLM latency from a liability into a non-issue.
5. **Determinism, replay, and an explainability panel** — seeded RNG plus an event
   log means you can replay a session and show a GM *why* an NPC acted: "fear
   0.71, imprint `the-fire`, debt to Marla 3." Nobody else has this. It is a
   debugging tool that happens to be a headline feature.
6. **Import/export as a JSON bundle** — kills lock-in objections, enables sharing
   and a future campaign marketplace.
7. **Cost caps and abuse limits** — per-guild and per-campaign token budgets, or
   one enthusiastic server bankrupts the operator.
8. **Ruleset as data** — dice grammar, ability schema and resolution rules are
   content, not code. Legal note: **SRD 5.1 is CC-BY-4.0** and safe to ship with
   attribution; copyrighted statblocks and published adventures are not.
9. **Per-entity fog of war on the player surface** — falls out of §4.3 for free
   and players will love it.

## 8. Non-goals for v1

Voice, maps and battle grids, image generation, a mobile app, real-time combat
with sub-second turns, and any ruleset beyond the two in `12-ROADMAP.md`.

---

## 9. Decisions taken

Confirmed by the owner at planning time:

| Decision | Choice | Consequence |
| --- | --- | --- |
| Audience | **Product for many servers** | Multi-tenant data model from day one; entitlements, safety and cost caps are in scope, not deferred. |
| Ruleset | **Both in parallel** | The abstraction is built against two implementations (freeform + SRD 5.1) so it can't quietly hardcode one. Freeform reaches playable first; SRD data fills in behind it. |
| Play mode | **Both, async-first** | Async is the default surface; live sessions are a mode that tightens pacing and enables combat rounds. |
| LLM host | **Local only — Ollama on the owner's laptop** | The VPS is closed as an option (`08-LLM-LAYER.md` §2). No hosted API in any tier: the laptop serves over a Tailscale tunnel, and if the product outgrows it the answer is a machine we own, or tenants pointing at their own Ollama. |
| AI surface | **Deterministic first** | Two tasks call a model, one calls it as a fallback, two never do. New call sites need written justification (`08-LLM-LAYER.md` §5). |

Open questions that do **not** block the build are tracked in `12-ROADMAP.md` §6.
