# Dodo Tabletop — design docs

The plan for replacing `cogs/dnd.py` with a living-world tabletop engine.

**Status: design. Not built.** Nothing here describes existing code except where a
file is named explicitly.

---

## The one-paragraph version

Every "AI Dungeon Master" fails the same way: the LLM *is* the world state, so it
contradicts itself, forgets, and can be argued into anything. We invert it — **the
world is a deterministic simulation, and the LLM is a translator at two edges
(player text → intent, state-delta → prose). Nothing the model says is true until
the simulation says it is.** That makes small models viable, decisions
explainable, and the whole game playable with the LLM switched off. The
differentiator isn't "AI GM" — it's **minds that persist and a world that
continues while you're asleep**, and those are simulation problems, not prompting
problems.

**Picking this up in a new session? Read [HANDOFF.md](HANDOFF.md) first** — current state, the traps that have already caused outages, and what P3 is.

## Read in this order

| # | File | What it covers |
| --- | --- | --- |
| 00 | [PRODUCT](00-PRODUCT.md) | The thesis, what we're replacing, the full product, additions to the brief |
| 01 | [ARCHITECTURE](01-ARCHITECTURE.md) | Layers, invariants, module layout, turn loop, world tick, simulation tiers |
| 02 | [DATA-MODEL](02-DATA-MODEL.md) | Collections, schemas, indices, sizing |
| 03 | [KNOWLEDGE-BASE](03-KNOWLEDGE-BASE.md) | Four KB tiers, retrieval, beliefs vs facts, canon queue, bootstrap |
| 04 | [ENTITIES](04-ENTITIES.md) | One entity model, rulesets as data, traits, inheritance, needs, relationships |
| 05 | [MEMORY](05-MEMORY.md) | Tiers, salience, perception error, decay, confabulation, imprints, budgets |
| 06 | [DECISION-ENGINE](06-DECISION-ENGINE.md) | Utility AI, impulses, faction clocks, explainability |
| 07 | [NARRATIVE-ENGINE](07-NARRATIVE-ENGINE.md) | Drama manager, beats, suggester and autonomous GM |
| 08 | [LLM-LAYER](08-LLM-LAYER.md) | Backends, the hardware reality, five tasks, fallbacks, budgets |
| 09 | [SURFACES](09-SURFACES.md) | Discord play surface, web panel, access control, parameters |
| 10 | [MONETIZATION](10-MONETIZATION.md) | What's scarce, tiers, enforcement, import/export |
| 11 | [SAFETY](11-SAFETY.md) | Lines & veils, X-card, filtering, privacy |
| 12 | [ROADMAP](12-ROADMAP.md) | Six phases, each playable; risks; open questions |
| 13 | [MIGRATION](13-MIGRATION.md) | Carrying the existing `dodo_dnd` data across |
| 14 | [CONVENTIONS](14-CONVENTIONS.md) | **Instructions for Claude** — house style, invariants, what not to do |
| 15 | [SEPARATION](15-SEPARATION.md) | What is kept separate from the rest of the bot, what is shared, and every merge note |
| — | [HANDOFF](HANDOFF.md) | **Start here in a new session** — state, standing rules, known traps, what P3 is |

## The six ideas that matter

1. **The simulation owns truth.** (`00` §1) Everything else follows from this.
2. **Belief, not truth.** (`03` §4) Entities act on what they believe, with a
   source and a confidence. Lying NPCs, rumours, fog of war and dramatic irony all
   fall out of one design decision.
3. **Memory degrades, it doesn't delete.** (`05` §4) Fields rot in order — gist
   last, time and place first — and degraded slots get *confabulated*, so NPCs
   misremember characteristically.
4. **Witnesses perceive, they don't observe.** (`05` §3) Two witnesses to one
   event form two different memories. Every grudge and rumour in the game
   originates here rather than from a feature that generates them.
5. **The world runs on clocks.** (`06` §10) Faction agendas advance whether or not
   players engage — which is what "continuous world" actually means, and the
   headline feature for async play.
6. **Deterministic first, local always.** (`08` §5) Only two tasks call a model,
   and it runs on hardware we own. Async play and local inference turn out to be
   complementary: a play-by-post campaign needs a few renders a *day*, so the
   duty cycle on one laptop is tiny.

## Decisions taken at planning time

| | |
| --- | --- |
| Audience | Product for many servers — multi-tenant from the first commit |
| Rulesets | Freeform **and** SRD 5.1 in parallel; freeform playable first |
| Play mode | Both, async-first |
| LLM host | **Local only.** Ollama on the owner's laptop (Ryzen 7 8845H, 28 GB LPDDR5X-7500 ≈ 120 GB/s → ~20–28 tok/s on a 4B), reached over Tailscale. No hosted API in any tier. The VPS is closed as an option — see `08` §2 |
| AI surface | **Deterministic first.** Two tasks call a model, one calls it as a fallback, two never do — `08` §5 |

## Current state of the thing being replaced

`cogs/dnd.py`, 361 lines: character sheets are a hardcoded stat array identical for
every character; dice are cosmetic and feed nothing; memory is an unbounded
LLM-written string; there is no `guild_id` anywhere so it cannot serve two
servers; and it is wired to none of the bot's platform systems. It is a chat
wrapper with a session table. See `00` §2.
