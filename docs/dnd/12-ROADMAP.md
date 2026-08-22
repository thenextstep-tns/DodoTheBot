# Roadmap

Spine-first. **Every phase ends playable** — no phase exists only to enable the
next one. Nothing is merged that leaves the module in a non-working state.

Phases are ordered by dependency, not by excitement. The temptation is to build
the memory model first because it is the interesting part; that would produce an
elaborate mind with nothing to think about.

---

## P0 — Foundations ✅ **done**
*Playable as: a competent sheet-and-dice bot with real, per-campaign data.*

Shipped: `helpers/dnd/{rules,world,store}`, `cogs/dnd/`, `web/dnd/`,
`helpers/dnd/migrate.py`, and `tests/test_dnd_p0.py` (95 checks, no pytest or
mongomock dependency — the collections are swapped for an in-memory fake).
Commands: `/campaign create|list|info|join|leave`, `/character create|sheet|retire`,
`/scene open|close`, `/dice`, `/check`, plus owner-only prefix `dndmigrate`.

`tests/test_command_names.py` guards two things that each took the whole cog
offline in production once: a **duplicate top-level name** (`/roll` collided with
the deathroll minigame) and **Discord's cap of 100 top-level slash commands**
(P2 pushed the bot from exactly 100 to 106). A group costs one slot however many
subcommands it holds, so GM tooling lives under `/gm`.

- `store/` — repositories, scope enforcement, indices
- `rules/` — ruleset protocol, dice grammar, resolution; **both** `freeform` and
  `srd5e` skeletons in parallel (the chosen approach — one implementation would
  let the abstraction quietly collapse)
- `world/entity.py`, `world/event.py` — entity model, event log
- Campaign create/join, character create, sheet, dice wired **into resolution**
- Discord: scene threads, action bar, the core commands
- Panel: campaign overview, entities list
- Migration of legacy data (`13-MIGRATION.md`)

**Acceptance — all four verified in `tests/test_dnd_p0.py`:**

| Criterion | How it is proved |
| --- | --- |
| Two campaigns on two servers, no data leakage | Identically-named campaigns and characters in two guilds; a foreign `_id` does not resolve, and a scoped delete spares the other server |
| Sheet stats come from a ruleset | A wizard and a barbarian get different ability arrays — the direct regression test for the old cog's identical block |
| A roll changes the outcome | Sweeping seeds at a fixed DC produces all four degrees; raising the DC lowers the success rate; a better ability raises it |
| A restart loses nothing | State reloads from a fresh store, and `save()` cannot reparent a record into another tenant |

**No LLM in this phase at all.**

## P1 — World & knowledge ✅ **done**
*Playable as: a GM tool with living notes and fog of war.*

Shipped: `world/knowledge.py` + `world/belief.py`, `store/knowledge.py` (budgeted
retrieval), `store/beliefs.py`, `store/canon.py`, `cogs/dnd/knowledge.py`, panel
knowledge + canon sections, and `tests/test_dnd_p1.py` (52 checks) plus
`tests/test_dnd_panel.py` (20). Commands: `/lore add|list|search|remove`,
`/look`, and under the GM group `/gm knows|believe|canon`.

P1 also **separated tabletop from the rest of the bot** — see `15-SEPARATION.md`.

- `dnd_knowledge`, four tiers, `overrides` semantics
- Retrieval scoring with token budgets
- Scene state, presence, affordances
- Beliefs — per entity, with source and confidence
- Canon queue (empty until P4, but the machinery and panel page exist)
- Panel: knowledge editor, canon queue
- Session-zero bootstrap, template path only

**Acceptance — verified in `tests/test_dnd_p1.py` and `tests/test_dnd_panel.py`:**

| Criterion | How it is proved |
| --- | --- |
| A player sees their character's beliefs, not world truth | One PC and one NPC hold different beliefs about the same dock; the PC's view contains only their own |
| An override visibly changes retrieval | A campaign rule with `overrides` set removes the global rule from both listing and retrieval |
| Secrets never reach a player | Retrieval with `for_player=True` drops them, and the rendered player HTML is asserted not to contain the secret's text |
| Canon needs an explicit ruling | A proposal is retrievable as low-weight soft canon but is not a fact until accepted; double-accept is refused |

## P2 — Minds ✅ **done**
*Playable as: NPCs that remember, feel, and can be inspected — before they act.*

Shipped: `mind/` (traits with inheritance, needs, memory, relationships),
`world/memory.py` + `world/relationship.py`, `store/memories.py` +
`store/relations.py`, `helpers/dnd/minds.py`, **`helpers/dnd/tuning.py`**, the
panel **entity inspector** and campaign tuning page, and `tests/test_dnd_p2.py`
(104 checks). Commands: `/npc create|list|mind` and `/gm remember|recall|relate|advance`,
plus `/gm tune show|set`.

**Forgetting is a power law, not a decay timer.** Three things shape how long a
memory holds together, and all three are tunable (including to zero):

* how much it mattered at the time (salience),
* **whose head it is in** — `retention` is a per-character faculty, so some
  people remember nearly everything and some lose names by the next week,
* **whether their value system is holding on to it** — a grasping NPC keeps every
  debt and loses every kindness; a sworn one does the reverse. Values also shape
  what they *notice* in the first place, so attention and retention compound.

- Traits, inheritance, derivation from culture
- Needs with cubed urgency
- Memory: tiers, salience, encoding with perception error, field-wise decay,
  confabulation, imprints, budgets, consolidation, recall, reconsolidation
- Relationships, multi-axis, event-driven
- Panel: **the entity inspector** (`09-SURFACES.md` §5)

**Acceptance — verified in `tests/test_dnd_p2.py` and `tests/test_dnd_panel.py`:**

| Criterion | How it is proved |
| --- | --- |
| Two witnesses differ | The distant witness keeps fewer details, sees only "a fight", and scores it lower — from one event |
| Memory degrades and confabulates | Over simulated years a faint memory loses fields in order and either blanks or is filled with a wrong value drawn from that character's *other* memories |
| Imprints survive everything | Promoted, then aged a century at zero retention: byte-identical, half-life infinite |
| Budgets hold | Pruning always lands inside the cap, lowest salience first, imprints exempt, and what goes leaves a summary |
| Curve is a power law | More is lost in the first week than in the fifth year; 100 one-day steps equal one 100-day step |
| Forgetting can be switched off | `memory_decay_rate: 0` leaves fidelity byte-identical after a century |
| Looking doesn't change the mind | The inspector renders twice with identical recall counts and salience |

This phase is where the product becomes itself, and the inspector is the demo
that proves it worked.

## P3 — Decisions & continuity
*Playable as: a world that keeps turning while you sleep.*

- Appraisal, impulses
- **Deprivation effects** (`04-ENTITIES.md` §5a) — needs bend mood and apply
  ruleset conditions, not just rank actions. Optional lethality, **default off**
  and interlocked: it stays off until NPCs can act to feed themselves, or a
  campaign left alone empties itself in a week.
- **Belief lifecycle** (`03-KNOWLEDGE-BASE.md` §4) — `fact`/`rumour`/`value`
  kinds; the first two erode on a power law, values harden instead. Today a
  rumour assumed once is held at identical confidence a decade later.
- **Trait drift** (`04-ENTITIES.md` §3a) — an exposure ledger fed by events,
  imprints and long-held beliefs moves the baseline in bounded, legible steps,
  extrapolated in closed form for dormant entities. Nothing writes traits after
  creation today, so §3's "temperament shifts when an imprint forms" is
  specified and unbuilt.
- **Rupture** (`04-ENTITIES.md` §3b) — sustained extreme exposure breaks one axis
  past the drift ceiling, permanently and narrowly. Default off and gated by the
  campaign's lines (`11-SAFETY.md`), not merely tunable.
- **Beliefs bend memory** (`05-MEMORY.md` §4) — confirming a belief reinforces
  the memory, contradicting it either sticks or is suppressed depending on
  `openness`. Only the drive half of that is built.
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

- Backend interface; `null` first, then `ollama`. **No hosted-API backend, ever.**
- The non-AI paths first: verb parser, templated episode gists, name tables — most
  of `08-LLM-LAYER.md` §5 lands before a model is installed at all
- The two AI tasks (`render_scene`, `render_dialogue`) with schemas, retries and
  template fallbacks
- Laptop setup and the §12 measurement checklist, results recorded in `08`
- Tailscale tunnel; verify the unreachable-host path degrades to `null` cleanly
- Priority queue, response cache, load accounting
- Streaming, mechanics-first posting
- Canon queue fed by LLM output; soft canon
- Safety filtering (`11-SAFETY.md`)

**Acceptance:** the null-backend suite passes the entire turn loop; an NPC never
speaks a fact it does not believe; **closing the laptop mid-scene degrades to
templates without interrupting play**; measured tok/s recorded in `08` §3.

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
| **Inference host is one laptop.** Must be awake; live sessions burst. | Async play needs a few renders a *day*, so the duty cycle is tiny (`08` §8). Bursts fall back to templates rather than queueing anyone. If it outgrows this, the answer is a machine we own — not a hosted API. |
| **A 4B model may write dull prose.** | Measure at P4 before deciding; an 8B is a config change costing ~half the speed. And the sim, not the prose, is what makes it interesting — testable at P2/P3 with no model at all. |
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
