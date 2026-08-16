# Roadmap

Spine-first. **Every phase ends playable** — no phase exists only to enable the
next one. Nothing is merged that leaves the module in a non-working state.

Phases are ordered by dependency, not by excitement. The temptation is to build
the memory model first because it is the interesting part; that would produce an
elaborate mind with nothing to think about.

---

## P0 — Foundations
*Playable as: a competent sheet-and-dice bot with real, per-campaign data.*

- `store/` — repositories, scope enforcement, indices
- `rules/` — ruleset protocol, dice grammar, resolution; **both** `freeform` and
  `srd5e` skeletons in parallel (the chosen approach — one implementation would
  let the abstraction quietly collapse)
- `world/entity.py`, `world/event.py` — entity model, event log
- Campaign create/join, character create, sheet, dice wired **into resolution**
- Discord: scene threads, action bar, the core commands
- Panel: campaign overview, entities list
- Migration of legacy data (`13-MIGRATION.md`)

**Acceptance:** two campaigns on two servers, no data leakage; a character sheet
whose stats came from a ruleset rather than a hardcoded array; a roll that changes
an outcome; a restart that loses nothing.

**No LLM in this phase at all.**

## P1 — World & knowledge
*Playable as: a GM tool with living notes and fog of war.*

- `dnd_knowledge`, four tiers, `overrides` semantics
- Retrieval scoring with token budgets
- Scene state, presence, affordances
- Beliefs — per entity, with source and confidence
- Canon queue (empty until P4, but the machinery and panel page exist)
- Panel: knowledge editor, canon queue
- Session-zero bootstrap, template path only

**Acceptance:** `Look` shows a player *their character's* beliefs, not world
truth; a campaign fact overriding a global rule visibly changes resolution.

## P2 — Minds
*Playable as: NPCs that remember, feel, and can be inspected — before they act.*

- Traits, inheritance, derivation from culture
- Needs with cubed urgency
- Memory: tiers, salience, encoding with perception error, field-wise decay,
  confabulation, imprints, budgets, consolidation, recall, reconsolidation
- Relationships, multi-axis, event-driven
- Panel: **the entity inspector** (`09-SURFACES.md` §5)

**Acceptance:** two witnesses to one event hold measurably different memories; a
memory degrades over simulated months and confabulates a detail; an imprint
survives everything; memory never exceeds budget under a property test.

This phase is where the product becomes itself. Ship the inspector with it — the
demo is what convinces you the phase worked.

## P3 — Decisions & continuity
*Playable as: a world that keeps turning while you sleep.*

- Appraisal, impulses
- Utility scoring, softmax selection, decision traces
- Behaviour packs in the global KB
- Simulation tiers, dormant extrapolation
- World tick, staggered consolidation
- Faction clocks, agenda advancement, rumour propagation
- Panel: clocks, decision traces

**Acceptance:** leave a campaign alone for a simulated week — clocks advance, an
NPC pursues a goal, a rumour about a PC reaches someone who never met them, and
the tick stays under 25 ms for 200 active NPCs.

## P4 — Voice
*Playable as: NPCs that talk, and a world that phrases itself.*

- Backend interface; `null` first, then `openai_compat`, then `ollama`
- The five tasks with schemas, retries and fallbacks
- Response cache, budget accounting, degrade-on-exceed
- Streaming, mechanics-first posting
- Canon queue fed by LLM output; soft canon
- Safety filtering (`11-SAFETY.md`)
- The `08-LLM-LAYER.md` §3 benchmark, run and recorded

**Acceptance:** the null-backend suite passes the entire turn loop; an NPC never
speaks a fact it does not believe; exceeding budget degrades without interrupting
play.

## P5 — Narrative
*Playable as: a co-GM, then an autonomous one.*

- **5a** — drama state, beat catalogue, selection, binding, **suggester mode**
- **5b** — autonomous GM: pacing governor, response windows, escalation guard,
  safety gate, GM override

**Acceptance (5a):** every suggestion cites real state; dismissals visibly change
later suggestions. **(5b):** an unattended campaign runs a full arc without
escalating out of control or ignoring a player for more than N beats.

## P6 — Product
*Sellable.*

- Entitlements, tiers, limits, degrade-not-destroy
- Import/export bundles
- Billing integration
- Owner administration, cross-guild health and spend
- Polish, onboarding, docs

---

## Sequencing notes

**Both rulesets in parallel** (the chosen approach) does not mean equal depth at
equal times. `freeform` reaches playable first because it needs no data; `srd5e`
grows behind it as the global KB fills in. The abstraction is validated
continuously by both existing, which is the point — but P0 does not block on a
complete 5e implementation.

**Both play modes, async-first**: async is the default everywhere. Live-session
mode is a *tightening* of the same loop — shorter response windows, initiative
order, combat rounds — and lands with P3 (when turn order matters) rather than
needing its own phase.

## Risks

| Risk | Mitigation |
| --- | --- |
| **Scope.** This is a large system. | Every phase ships playable; the module is useful from P0 and can stop at any phase boundary without being a half-thing. |
| **Fun is unproven.** The simulation could be technically excellent and dull. | P2's inspector and P3's continuity are testable for fun *before* any LLM work. If the world isn't interesting without prose, prose won't save it. |
| **1 vCPU.** | Tiers, budgets and bounded costs are designed in from P0, and the perf numbers in `06` are acceptance criteria, not aspirations. |
| **Local LLM may stay impossible.** | `08-LLM-LAYER.md` §2 — pluggable backends mean this never blocks anything. |
| **`web/routes.py` is 3281 lines.** | `web/dnd/` is a separate module from the first commit. |
| **Legal.** | SRD 5.1 only, CC-BY-4.0, attributed. No published statblocks or adventures. |
| **The old cog has live data.** | `13-MIGRATION.md`; the legacy cog stays loadable for one release. |

## Open questions (non-blocking)

Defaults are assumed where noted; raise them at the phase that needs them.

1. **Campaign ↔ channel binding** — one forum channel per campaign, or one shared
   with tagged threads? *Assumed: per campaign, configurable.* (P0)
2. **Do PCs get simulated minds?** A PC has a player, but memory and relationships
   for PCs would let NPCs react to reputation. *Assumed: yes, memory and
   relationships tracked; decisions never automated.* (P2)
3. **Retired characters** — become NPCs, or archive? *Assumed: convert to NPC,
   which is a nice touch and nearly free.* (P2)
4. **Cross-campaign entities** — a shared server pantheon? *Assumed: no in v1;
   server-tier knowledge covers most of the want.* (P1)
5. **Language.** `bot.lang` is per-locale; is non-English play a v1 target? Affects
   model choice and name tables. *Assumed: English v1, structure stays
   locale-ready.* (P4)
6. **Voice/TTS** — explicitly a non-goal now; revisit after P6.
