# Handoff — Dodo Tabletop

**This file is about the tabletop engine only.** The bot as a whole — the shell,
the deploy, the command cap, the test runners, the repo-wide traps — is
`docs/HANDOFF.md`, and it is short. Read that one first if you have never
touched this repo; read this one if you are picking up simulation work.


Everything through **P3 is built, tested and live** — the whole simulation:
memory, belief, needs, goals, archetypes, decisions, and a world that moves when
nobody is watching. This file is what a fresh session needs to pick up **after**
that without re-deriving anything.

**`docs/dnd/PLAYTEST-P3.md` is written and unrun.** Nothing built in P3 has been
touched by a human, and neither has anything in P4. The owner's decision, taken
knowingly at the start of the P4 session, is to **build P4 first and then
playtest P3 and P4 together** — so this is deferred, not dropped, and §2b is
still the argument for why it matters. Whatever that playtest returns outranks
the roadmap.

---

## 1. Read this much, in this order

1. **`README.md`** — the thesis and the file index. Two minutes.
2. **`14-CONVENTIONS.md`** — how to work here. The twelve invariants are not
   suggestions; two of them exist because production broke.
3. **`12-ROADMAP.md`** — what is done, what P4 is, and the acceptance criteria.
4. The design file for whatever you are actually touching.

Do **not** read all sixteen documents. They are reference, not onboarding.

## 2. Where things stand

| Phase | State | What it gave us |
| --- | --- | --- |
| P0 | ✅ live | Campaigns, characters from a real ruleset, scenes, dice wired into resolution, event log, legacy importer |
| P1 | ✅ live | Four-tier knowledge with overrides, budgeted retrieval, beliefs, fog of war, canon queue — **plus full separation from the rest of the bot** |
| P2 | ✅ live | Traits + inheritance, needs, memory that forgets like people do, relationships, NPCs, the entity inspector, tunables in two layers |
| P2+ | ✅ live | **Stakes** — an act is worth different amounts to each person in it; emergent roles; scene consolidation. All of it came out of the playtest |
| P3 | ✅ **complete** | World tick, faction clocks, rumours — and the whole decision engine: what an NPC may see, what a scene permits, what they want, who they are, how they choose, what happens when they do, and the cheap paths for everybody nobody is watching |
| P4 | ◐ started | Voice. **Its first half needs no model at all**; two of its four pieces are built and live — the turn report (§8a) and episode gists (§8b). No model has been installed and none is needed yet |
| — | ✅ live | **Interaction kinds as data** (§8c) — off-roadmap, asked for directly. Four hand-maintained Python tables became one editable file |

**P0–P2 have now been played through by a human**, act by act, using
`PLAYTEST.md`. That run found **seven real bugs that all 305 tests missed**, and
the shape of them is the most useful thing in this file:

| What broke | Why no test caught it |
| --- | --- |
| The engine's on-switch had never worked — a 64-bit guild id became a JS number literal and every panel request 404'd | Tests assert on HTML strings; nothing executes a page's JS, and `FakeGuild.id` was `7777`, small enough to survive intact |
| Adding a command parameter never reached Discord | The sync-skip hash covered only top-level names |
| A memory formed this morning read as "a while ago, maybe" | Stake was driving *perception*; no test asserted a fresh memory is sharp |
| The man who was **saved** was recorded as the creditor | A test asserted the inverted sign — the bug had a guard holding it in place |
| Every PC was immune to every event | `importance` (a CPU knob, pinned at 1.0 for PCs) was read as standing |
| Disposition could insulate someone past their own station | Nothing asserted the documented ceiling |
| Nothing ever left the `working` memory tier | `consolidate_scene` was written and called from nowhere |
| **`standing` had never been persisted** — the inspector control posted, the endpoint set it, `EntityRepo.save` dropped it, the panel said "Saved." | `save()` named the fields it wrote, and `standing` was added for stakes without being added there. Nothing asserted a field survives a round trip |
| **`lang_dnd.py` shipped unparseable and took the whole tabletop cog offline** | `test_command_names.py` is deliberately *static* — it `ast.parse`s `cogs/` and imports nothing; the engine suites import `helpers/` and `web/`. **Nothing had ever asked whether the rest of the repo parses.** It does now, first check in that suite |
| A typo in any numeric tunable silently reset it to inherited, flashing "Saved." | The panel suite asserts on HTML; nothing types into a control. An unparseable number reads back as `""`, and `""` is this API's *clear the override* |

**The human verdict on P0–P2: the mechanics are there and it is not playable.**
Verbatim, so it does not get softened: *"the syntax is way too complicated, the
whole narrative structure is confusing and not explained — pretty much
impossible to play in any way, too convoluted for no payoff."* The simulation is
real and the game around it is not. That is a **surface** problem, not a model
one, and it is deferred by agreement until the mechanics are in place — but it
is the thing standing between this and a product, and no amount of P3 makes it
smaller. `00-PRODUCT.md`'s risk table called this exactly.

Two lessons are now conventions (`14-CONVENTIONS.md` §5a/5b): **click it and
read the console before reasoning about the source**, and **a green suite proves
whatever the fixture encodes** — three of those bugs had tests defending them.

**2,862 tests** across **seven** suites, all passing. `test_dnd_catalogue.py` is the newest: it is
mostly one assertion per parameter, which is why the number jumped. `test_dnd_p4.py`
is the Voice phase's, and is where the null-backend suite will go:

```bash
py tests/test_command_names.py && py tests/test_dnd_p0.py && py tests/test_dnd_p1.py && py tests/test_dnd_p2.py && py tests/test_dnd_panel.py && py tests/test_dnd_p4.py && py tests/test_dnd_catalogue.py
```

The count is 4 + 95 + 52 + 542 + 68 + 195 + 1906, **measured** — `test_command_names.py`
prints no total, so its four checks have to be counted by eye. See §9.

No pytest, no mongomock — `tests/fake_mongo.py` swaps the collections for an
in-memory fake, so nothing touches the real database.

## 2b. The next thing to do: play it

`docs/dnd/PLAYTEST-P3.md` is written and unrun. It covers what `PLAYTEST.md`
does not — people deciding things, and a human pushing on them: archetypes both
ways, stakes, attention split across goals, a turn that reports itself, `/npc
why`, a belief that is acted on after being marked false, and a week left alone.

**Nothing built in P3 has been touched by a human.** The first playtest found
seven bugs that 305 tests missed and produced the verdict that shaped six
increments. This session's own work is the same argument: clicking things found
that `standing` had never persisted, that `pack_count: 0` did not switch packs
off, that a renamed archetype forked instead of editing, and that the world went
inert after a day. None of those had a failing test.

Two things were built *for* that playtest, because without them it would have
been blind:

* **`/gm advance` now reports what people did** — `_turn_summary` in
  `cogs/dnd/cog.py`, deterministic and model-free. *(P4 grew this considerably
  and moved the substance into `helpers/dnd/narrate.py`; see §8a. The function
  in the cog is now the orchestration half — it resolves the tuning, the names
  and the archetype labels and wraps the lines in the strings.)* Before it, NPCs
  decided, acted, moved goals and changed who they were, and the message said
  "3 minds aged". A decision engine nobody can see the output of is, at the
  table, identical to no decision engine.
* **`/npc why <name>`** — the decision trace where the game is played rather
  than only in the panel. Reads it back from the **event log**, which is what
  putting the trace there was for.

## 3. Standing rules that are easy to violate

These live in the user's memory files and in `14-CONVENTIONS.md` §4. They were
each stated more than once, so treat them as settled:

- **Nothing is baked in.** Every constant is a tunable with a label, a
  description and a range, layered *default → server → campaign*. If something
  can be softened it must also be switchable off entirely.
- **The panel is the configuration surface, not Discord.** Every tunable ships
  with a panel control in the same phase as the feature. Slash commands are for
  *playing*. Long flat lists in the panel are a defect — group them.
- **Tabletop stays separate** from the rest of the bot: own strings, own
  parameters, own storage, own dashboard section (`15-SEPARATION.md`).
- **Local inference only.** Ollama or nothing. Never add a hosted-API backend.
- **Push to `refactor` deploys to production in ~14 seconds.**

## 4. Things that bit us — do not rediscover them

**The repo-wide traps are in `docs/HANDOFF.md` §2** and are not repeated here:
`py` rather than `python`, `PYTHONIOENCODING=utf-8`, bash heredocs mangling
patch scripts, and Discord's hard cap of 100 top-level slash commands. All four
have cost this project time and two of them caused outages. Go and read them.

What follows is the tabletop-specific half:

| Trap | What happens | Guard |
| --- | --- | --- |
| `cogs/dnd/__init__.py` can't hold `setup()` | `load_all_cogs` skips `__`-prefixed files | Entry point is `cogs/dnd/cog.py` |
| Command groups built in `__init__` | Subcommands report no cog, so the per-guild switch is bypassed | Groups are **class attributes** |
| `os.walk` yields `cogs.dnd`, not `cogs.dnd.` | DnD modules listed as cogs with dead Load buttons | `registry.is_dnd_extension` matches both |
| Duplicate top-level command name | `CommandAlreadyRegistered` — the *whole cog* goes offline | `tests/test_command_names.py` |
| Tabletop is near the command cap | Same outcome | **Group under `/gm`.** Currently 94 of 100 used across the whole bot |

The command cap is shared with every other cog, so it is a repo-wide budget that
tabletop happens to spend most of. Adding a top-level command here takes a slot
away from everything else.

## 5. The architecture, in one screen

```
cogs/dnd/, web/dnd/     surfaces
helpers/dnd/minds.py    orchestration — resolves tuning, calls the pure layer, writes back
helpers/dnd/tuning.py   121 tunables, resolved default → server → campaign
helpers/dnd/packs.py    behaviour archetypes, resolved built-in → server → campaign
helpers/dnd/interactions.py  what one person can do to another, same three layers
helpers/dnd/catalogue.py     every parameter there is, exposed or not
helpers/dnd/narrate.py  saying what happened — turn report and the words a
                        memory carries, no model anywhere     (pure, no RNG)
helpers/dnd/data/       what ships as data rather than as code
                        (packs.json, interactions.json)
helpers/dnd/mind/       traits, needs, memory, relationships, stakes,
                        goals, behaviour (propose), decide (score + select)
                                                             (pure, seeded)
helpers/dnd/world/      what exists: entity, memory, belief, goal, pack, event
                        — and view.py, the only thing a decision may see
helpers/dnd/rules/      dice, rulesets, affordances                   (pure, seeded)
helpers/dnd/store/      repositories — every query carries its tenant
```

Two rules hold it together: **the pure layers never do I/O and never read
configuration** (tuning is resolved at the orchestration edge and passed in as
typed dataclasses), and **every repository requires a `Scope`**, so an unscoped
query cannot be written.

## 6. P3 — complete

### Already built and live

| Piece | Where | What to know |
| --- | --- | --- |
| **World tick** | `minds.tick`, `due_for_tick`; the `world_tick` loop in `cogs/dnd/cog.py` | A 15-minute scheduler asks each campaign whether *it* is due. The campaign owns the pace: `tick_hours`, `tick_days`, both campaign-scoped |
| **Time modes** | `time_mode` tunable | `manual` (default) / `automatic` / `timeless`. Timeless is not "off": nothing ages on a tick *or* on command, for dungeon crawls. **Its panel control only started working in the affordance increment** — every tunable used to render as a number box, so the one setting deciding whether a campaign ages could not be changed from the panel at all |
| **Faction clocks** | `world/clock.py`, `store/clocks.py`, `minds.advance_clocks`; `/gm clock add|list|nudge` | Fronts fill on their own, fire `on_complete` as data, can start successors, and stop dead while `blocked_by` is non-empty |
| **Rumours** | `mind/rumour.py`, `minds.spread_rumours` | Claims walk the relationship graph, degrade by listener→teller trust, and drift one word per hop |

**The rule that held all three together: they run inside `advance()`, not inside
the tick loop**, so `/gm advance` moves them too. A world that ages differently
when nobody is watching is a world with two rulesets.

**Acceptance is met in full.** Left alone for a simulated week: clocks advance,
a rumour reaches someone who never met its subject, and an NPC carried a goal
from 0.00 to 0.46 through choices nobody made for them. `test_acting` is that
run. What P3 does *not* have is the four things below.

### The decision engine, as built

`06-DECISION-ENGINE.md` is the spec. It was built in six increments and this is
what each one settled — **read the notes before changing any of it**, because
most of them are decisions that cost something to reach:

1. **`EntityView`** — ✅ **built** (`world/view.py`, `minds.view_for`, panel group
   *Perception*). The projection an NPC decides from, and the only door between
   the world and the engine. What it buys, and what the next steps must not
   undo:
   * `Recollection` and `HeldBelief` are **projections, not records**. Decay is
     already applied, so a faded memory arrives faded; and `HeldBelief` has no
     `truth` field, so the GM's marking of whether a claim is *actually so* is
     not one attribute access away from every scoring term.
   * Everything is frozen and every mapping is a read-only proxy — a decision
     cannot rewrite the mind it is reading, which is what keeps replay honest.
   * `importance` is deliberately absent: it is a CPU knob, and reading it as
     standing made every PC immune to every event once already.
   * `view_for` **does not reconsolidate**. Thinking about something rewrites it,
     but a view is built for every NPC every tick, and 200 minds rewriting their
     own history four times an hour is a world that drifts while nobody plays in
     it. Reconsolidation belongs to step 5, where an NPC actually acts.
   * Six tunables under **Perception**, each switchable off (a cap of 0 is no
     cap; a floor of 0 lets everything through).
   The test to keep green is `test_entity_view` in `tests/test_dnd_p2.py`: it
   walks every object reachable from a view and fails if an `Entity`, `Memory`,
   `Belief` or `Relationship` is among them. **If a later step needs something
   the view does not carry, add it to the projection — do not pass the record.**
2. **`ruleset.affordances`** — ✅ **built** (`rules/ruleset.py`,
   `minds.affordances_for`, panel group *Actions*). The nine verbs, plus:
   * The signature is **not** the one the spec sketched. `rules/` sits below
     `world/` and may not import the entity model, so it takes
     `(actor_stats, Situation)` — a flattened scene, occupants reduced to
     `Presence(entity_id, kind, carrying, reachable)`. `minds.situation_for`
     does the flattening.
   * `WAIT` is always returned and has **no switch**. It is the null action the
     engine falls back to; a campaign where nobody may do nothing has no floor.
   * The two rulesets deliberately disagree, which is the abstraction's whole
     proof: freeform reads the words a GM actually types (`"tied to a chair"`
     stops you leaving), srd5e reads the SRD condition list and knows 0 HP is
     unconsciousness whatever `conditions` says.
   * **Physics and lines are kept apart.** The ruleset says what is possible;
     the campaign's eight *Actions* switches say what it is willing to have
     happen, applied at the edge in `affordances_for`. Switching Attacking off
     means no NPC ever starts violence — players are unaffected, because a
     player's command goes through `resolve`, not through here.
   * **Scenes do not carry objects or exits yet**, so `features` and `sealed`
     are arguments to `situation_for` that nothing passes; taking and using ride
     on what people are carrying, which is real today. The seam is there so a
     scene contents model lands as a fill.
3a. **Goals** — ✅ **built** (`world/goal.py`, `mind/goals.py`, `minds.add_goal`
   and friends, panel group *Goals*, and an editor in the inspector under
   *What they want*).
   * **A goal names the verbs that serve it** (`SERVED_BY`). That table is the
     cheap half of GOAP and the reason §1 could rule search out: scoring a
     candidate against a goal is a lookup and a multiply. A test asserts every
     verb in it is one `rules.ruleset.AFFORDANCES` can actually grant, so a goal
     can never become unreachable.
   * Three things happen to an untouched goal, each switchable off: it **fades**
     (from when it last *moved*, so pursuit costs nothing), a **deadline
     presses** convexly inside its window, and **progress raises** what the next
     step is worth. `pressure()` is bounded 0..1 like every scorer term.
   * **Attention is the limit, not slots.** Anybody may hold any number of
     goals; each one costs `goal_attention_overhead` just to be carried, so
     usable attention *falls* as the list grows — 1 goal gets 0.92 of a person,
     6 get 0.09 each, 12 get 0.003, and 13 leaves nothing at all. The relentless
     character and the one who never finishes anything are the same subtraction
     with a different number in it; nobody scripted either. Overhead at 0 turns
     it back into plain division.
   * **The split follows priority, not head count**, so one real ambition beside
     a scatter of half-wants still gets somewhere. `priority` is therefore the
     load-bearing field: it is a share of a person, not a sort order.
   * **Priorities move.** `SUPPORTED_BY` maps relationship axes onto goal kinds,
     and `minds.relate` re-weighs any goal about the other party after every
     event — a grudge cools when the feeling behind it does. Always a pull,
     never a jump; `goal_reweigh = 0` freezes them. A GM still overrides.
   * `goal_cap` survives as a blunt backstop, **off by default**. It refuses
     rather than evicting — which ambition to drop is not a decision to make
     behind a GM's back.
   * Goals are embedded on the entity, not given a collection: bounded, and
     never read without the person. Finished and abandoned ones stay on the
     record; what somebody gave up on is a fact about them.
   * Goals are the one part of a mind the panel is *meant* to author — disposition
     is fenced behind a warning, plot is the GM's job.

3b. **Behaviour packs** — ✅ **built** (`helpers/dnd/data/packs.json`,
   `helpers/dnd/packs.py`, `world/pack.py`, `mind/behaviour.py`,
   `minds.candidates_for`, panel group *Behaviour* + an **Archetypes** section on
   the campaign page and a *What they reach for* section in the inspector).

   **The decision that was open, and how it went.** The roadmap said "from the
   global KB". The KB's `Fact` is prose + tags built for budgeted retrieval, so
   putting weight tables in `text` would have been a JSON blob in a field nothing
   validates. Instead the six ship as **data in `helpers/dnd/data/`** (the home
   `03-KNOWLEDGE-BASE.md` §7 names) and resolve **built-in → server → campaign**
   through the *same two override layers as the tunables* — server in the
   `DndTuning` document's `packs` map, campaign in `campaign.settings["packs"]`.
   No new collection, and a campaign carries its archetypes in its export bundle.
   **A GM can add a smuggler from the panel**, which is precisely what the role
   and culture tables still cannot do (§7).

   * **Both directions, by request.** Backwards is the default:
     `fit(traits, pack)` asks how predator-shaped this person already is, and
     assignment is weighted rather than argmax so the timid soldier still
     happens. Forwards is opt-in — `/npc create archetype:coward` or
     `spawn_npc(archetype=)` runs `shaped_by`, pulling the rolled disposition
     toward the archetype's priors before anything else. `04-ENTITIES.md`
     §3a-pre argues against forwards priors and is right *about generating a
     population*; naming one for one NPC is authoring, not generation, and the
     owner asked for both. `pack_shaping = 0` gives the label and whoever the
     dice produced.
   * **Nobody is one archetype and nobody stays the same mixture.** Everyone
     carries `pack_count` of them, weighted, and `leaning()` takes the strongest
     per verb rather than blending — so the part of someone that flees is not
     the part that bargains, and which archetype is in force depends on what is
     being considered. `behaviour.drifted` then moves the blend: fit is measured
     against `momentary(traits, needs)` (a frightened month makes somebody
     momentarily timid) and against **what they actually did**, so a coward who
     keeps having to fight becomes a predator over ~60 events and a predator
     having a terrible month becomes a coward. `minds.relate` drifts them on
     every event. `pack_drift = 0` freezes everyone.
     * The drift step keeps **one slot more** than `count`, because trimming to
       exactly `count` discards a newcomer's progress every step and the mixture
       can then only reshuffle what it started with.
     * The drift *target* is sharpened by `fit_sharpness` for the same reason a
       flat target is no target: six middling fits produce six near-equal shares
       and renormalising cancels the whole step.
   * **A pack weights verbs, it never adds one.** Candidates are archetypes
     ∩ affordances, so nothing can propose what the scene forbids and adding an
     archetype can never widen what is possible. Weights for unknown verbs are
     dropped on load.
   * **Editing:** a card sends its `key`, so renaming edits in place; the add
     form sends only a name and the server slugs it. Sending the name as the key
     from both would fork an archetype every time somebody renamed one.
   * `pack_count = 0` switches archetypes off **for people who already have
     them**, not merely for the next NPC generated — a setting that only affects
     future entities is a setting that looks broken.
   * `candidate_cap` is the documented performance lever (§11). Waiting always
     survives it.
   * **`candidates_for` builds the view with `include=scene.present`.** Without
     that the directed verbs — speak, attack, give, take — silently find nobody
     to aim at, because an unmet stranger is in no relationship and no belief.
     That is what `include` was added for in step 1; anything else building a
     view for a scene needs it too.
4. **`mind/decide.py`** — ✅ **built** (`minds.decide_for`, panel group *Deciding*,
   and a live trace in the inspector under *What they would do next*).
   * **Nine terms, not eight.** The spec's eight plus `archetype` — the leaning
     that put the candidate on the table has to enter the score somewhere, and a
     visible term beats a silent multiplier on the total. A number that moves a
     decision and never appears in its trace is the thing this file exists to
     prevent.
   * Every term is bounded −1…1 **before** weighting, the trace always comes
     back and sums exactly to the utility, and every weight is a tunable that
     switches off.
   * **Traits modulate the terms, never the weights.** Two hundred NPCs with
     their own weights would be untunable; a bold character gets a different
     risk *term*.
   * **`boldness` is finally read by code** — declared in P2, rolled, stored,
     displayed, and consulted by nothing until `TRAIT_AFFINITY`.
   * Softmax, not argmax, at `T = temperature + spread × volatility`. Steady
     people are predictable, volatile ones are not, and T is never 0.
   * **The risk curve is kept inside 0..1 by construction, not by clamping.**
     It was `(0.5 + fear) ** curve` and clipped at 1, which sawed the top off
     exactly where the difference between *frightened* and *cannot make
     themselves* is supposed to live — the frightened→terrified gap came out
     smaller than the brave→ordinary one.
   * The softmax exponentiates `(u - best)`, because `exp` of a large utility
     overflows and of a large negative one underflows every weight to zero and
     makes `rng.choices` raise.
   * **Nothing is written.** Asking what somebody would do must not make them do
     it; committing is step 5.
   * Measured at **0.06–0.18 ms** to score and select ~17 candidates, against a
     1 ms budget. The lever if that ever changes is `candidate_cap` or the term
     count — **never caching**, which would break replay.
5. **Commit** — ✅ **built** (`minds.commit_decision`, `minds.act`,
   `minds.run_turn`, an `acted` event kind, and NPC actions rendered with their
   reasoning in the campaign's event log).
   * **The P3 acceptance criterion is met.** Left alone for a simulated week a
     campaign now runs itself: clocks fill, rumours travel, and an NPC pursued a
     goal from 0.00 to 0.46 through their own choices, logging 28 events on the
     way. `tests/test_dnd_p2.py::test_acting` is that run, as a test.
   * `run_turn` is called from **`advance`**, not the tick loop — the rule that
     has held all of P3 together. A world that behaves differently when nobody
     is watching is a world with two rulesets.
   * `commit_decision` reuses **`interact`** for directed verbs rather than
     reimplementing it, so stakes, per-party memories, witness memories,
     relationship deltas, goal re-weighing and drift all come for free and
     cannot drift out of step with the rest of the engine.
   * **Acting relieves the need it answered** (`act_need_relief`). That closes
     the interlock `04-ENTITIES.md` §5a named: deprivation could not be switched
     on while nothing could satisfy a need, because needs only ever rose. Blunt
     on purpose — there is no item model, so it says *they did something about
     it*, not *they ate a specific loaf*.
   * **Deciding is still read-only.** `decide_for` writes nothing; only
     `commit_decision` does. A GM asking what somebody would do must not make
     them do it, and there is a test.
   * **Cost:** ~1.4 ms per NPC for the full pipeline *including* the writes
     (deciding alone is 0.18 ms). The default cap of 8 actors keeps one advance
     near 11 ms. The 25 ms / 200-NPC budget in §11 is for the **coarse** path,
     which is step 6 — do not read the current number against it.
6. **Coarse and dormant paths** — ✅ **built** (`minds.coarse_view_for`,
   `minds.decide_coarsely`, `decide.decide_coarse`, `behaviour.propose_coarse`,
   `minds.catch_up`).
   * **The coarse view does no queries at all.** No memories, no beliefs, no
     relationships, nobody else — built from the entity document alone. That is
     the whole saving; the full view costs three round trips and a social
     projection.
   * Candidates come from **goals and needs only**, directed verbs aimed at
     whoever the goal is about. Scoring uses `COARSE_TERMS` — the five an empty
     room can honestly answer. The social three are **absent, not zeroed**:
     scoring how somebody feels about nobody is not cheaper, it is wrong.
   * **Argmax, and no RNG in the signature.** The surprise a weighted draw buys
     is worth paying for on screen and worth nothing off it.
   * **Dormant characters are not ticked at all.** `advance` skips them and they
     carry `aged_at`; `catch_up` pays the arrears the moment anything looks.
     Needs and goal pressure need no catching up — both are closed-form in
     `world_time`, and there is a test that ten steps and one leap agree
     exactly. Memory decay's *deterministic* part lands the same; the
     confabulation **draws do not**, so a long-dormant character misremembers
     slightly less than a watched one. Real difference, honest trade, written
     down in `catch_up`'s docstring rather than claimed away.
   * **Waiting alone off-screen forms no memory** (`remember_idle`, off). It is
     the commonest thing an unwatched character does and therefore most of what
     a big world costs. Still logged — the world knows, nobody remembers.

### What the performance actually is, measured

| Path | Measured | §11 budget |
| --- | --- | --- |
| Coarse decide, one NPC | **0.08–0.11 ms** | ~0.1 ms ✅ |
| Full decide (score + select), ~17 candidates | **0.06–0.18 ms** | < 1 ms ✅ |
| Full decide **+ commit** | **~1.2–1.4 ms** | — |
| `run_turn`, default cap of 8 | **~4.6 ms** | — |
| `run_turn`, 200 NPCs | **61 ms** idle / **242 ms** acting | < 25 ms ❌ |

**The 25 ms figure is a budget for deciding, and it is met. It is not a budget
for writing, and writing is what the rest is.** Two hundred characters each
appending an event, forming memories and saving cannot be arithmetic-optimised
below the cost of the writes; `actors_per_advance` (default 8) is the lever, and
is why it exists. Note also that these numbers are taken against
`tests/fake_mongo.py`, whose collections are **linear scans** — a profile of the
200-NPC turn is dominated by `_matches` running 82,000 times. Against indexed
Mongo the memory reads are point lookups, so treat the absolute figures as an
upper bound and the *ratios* as the real signal.

### Two things the owner asked for during step 5, and where they live

* **A middle band between doing nothing and committing.** There is now a tenth
  affordance, `watch` — hanging back, listening, working out who these people
  are. `rules.ruleset.UNCOMMITTED` is the pair `(wait, watch)`, and both are
  granted to anyone who is not incapacitated, in *both* rulesets. Without it
  every NPC either froze or lunged, which is not what people do in a room.
  `wait` alone has no switch; `watch` has one like every other verb.
* **People change their minds incrementally.** `goal_reweigh_step` caps what one
  event may do to a priority, and the move itself scales by the event's
  **magnitude**, the person's **volatility** (the impulsive swing further — the
  exception that makes the rule readable) and `inertia()`, which resists change
  in proportion to how long a goal has been *carried*. A want formed today moves
  0.054 on a shattering event; the same want held a year moves 0.008. Forty
  events still take somebody from 0.26 to 0.85 — it travels, it never lurches.
  Inertia slows fading too, so old wants survive quiet stretches.

Budget: < 1 ms per focus NPC, < 25 ms for a 200-NPC tick. If the full pipeline
is too slow the fix is `CANDIDATE_CAP` or fewer terms — **never** caching
decisions, which would break replay.

`boldness` is read by nothing today; step 4 is where it starts mattering.

### Optional needs, and the safety gate that came with them

`desire` is the first **optional need** (`mind/needs.OPTIONAL`) — off unless a
campaign asks for it, and the shape any future one should copy:

* **Two gates that must agree.** The `need_desire` tunable *and* the campaign's
  **lines** (`docs/dnd/11-SAFETY.md` §1). A fresh campaign already ships with
  `sexual content` on its lines, so switching the setting on alone does nothing
  — deliberately two acts, because a table agreeing to play something and a GM
  enabling the machinery are different decisions.
* That gate was invisible at first: the setting looked broken. Now the tuning
  row carries a `blocked` note saying which line overrules it, and there is a
  **Lines** section on the campaign page to clear one. `Tuning.entries()` is
  where the note is attached.
* **Off means off now.** `advanced()` pins an optional need to 0 every time it
  is read, so switching it off zeroes values entities were already carrying —
  the lesson from behaviour packs, where a setting that only affected new
  entities looked exactly like a setting that did not work.
* **It is not a scalar in a vacuum.** The body need is a general pressure; the
  *directed* pull is `Relationship.desire`, fed by `attraction()` from the
  target's `Entity.allure`, affinity, familiarity, trust and respect — weighted
  so a plain, trusted, familiar person is wanted **more** than a striking
  stranger (0.34 vs 0.32), and fear puts it out almost entirely. Standing
  pressure amplifies an existing pull and **cannot manufacture one**.
* **The negative half is repulsion**, not the absence of wanting — it briefly
  ran 0…1 here, which confused *neutral* with *repelled*. Repulsion **bleeds**
  into affinity and respect on every contact (`bleed()`, `desire_bleed`), so an
  acquaintance curdles the more you see of them. One direction only: letting
  attraction feed back would loop through affinity and infatuate the campaign.
* Five interactions carry it — `flirted`, `courted`, `rebuffed`, `lay_with`,
  `repelled` — and `minds.relate` **refuses all of them** in a campaign that did
  not opt in, so one cannot half-happen.

### Four things designed during the playtest, still unbuilt

Each has a spec section and no code. None blocks the decision engine, and all
four want the tick that now exists:

- **Deprivation effects** (`04-ENTITIES.md` §5a) — needs bend mood and apply
  ruleset conditions. Lethality default off. **The interlock that blocked this
  is now closed**: NPCs can act, acting relieves the need it answered
  (`act_need_relief`), and ordinary living holds needs at a baseline
  (`need_upkeep`) instead of climbing to desperation. Switching deprivation on
  no longer empties the world, and `need_upkeep = 0` is already the siege
  setting it wants. **This is the readiest of the four.**
- **Trait drift and rupture** (§3a, §3b) — an exposure ledger; sustained extreme
  exposure breaks one axis past the ceiling. Rupture is gated by the campaign's
  lines, not merely tunable.
- **Belief lifecycle** (`03-KNOWLEDGE-BASE.md` §4) — `fact`/`rumour`/`value`
  kinds; the first two erode, values harden and feed the ledger.
- **Standing and importance emerge** (§2b) — standing rides the same ledger;
  importance recomputed from story entanglement.

**Everything in P3 is tunable and has a panel control.** The decision-trace view
landed with the scorer (*What they would do next* in the inspector). **A Clocks
page never did** — clocks are still `/gm clock` only, which is the one place in
tabletop where Discord is the configuration surface and the panel is not. That
is a standing-rule violation looking for an owner.

## 7. Known gaps, honestly

- **`tests/fake_mongo.py` has no `$unset`**, so *clearing* a server-level tunable
  back to inherited is the one leg of the tuning round trip no test can exercise.
  The campaign layer clears fine (it rewrites the whole settings document).
- **`/canon` is empty and stays empty until P4.** Nothing invents facts yet.
- **Almost nothing narrates**, and what does, does it without a model. Scenes,
  checks and rolls are all mechanical output by design. The exceptions are
  `helpers/dnd/narrate.py` (the turn report §8a, and the words every memory
  carries §8b) and `/npc why` — every one of them a deterministic template over
  state that already exists, which is the argument for doing the non-AI half of
  P4 first. **What a player reads during play still does not narrate at all**;
  that is `render_scene`, and it is the half that needs a model.
- **The legacy cog is still loaded** as `dnd_legacy`. It goes one release after
  the migration has actually been run (`13-MIGRATION.md` §6).
- **Nothing ever writes `entity.traits` after creation.** *(Note: `entity.packs`
  now does drift — who somebody is, in archetype terms, moves with what happens
  to them. Disposition itself still does not.)* `04-ENTITIES.md` §3
  says temperament shifts on an imprint and drives drift with experience; the
  only trait access in the codebase is a read. The mechanic is specified in
  `04-ENTITIES.md` §3a and unbuilt — an NPC is the person they were rolled as,
  permanently.
- **Needs settle at a baseline, they do not accumulate.** Found while preparing
  the playtest: a day of world time added +0.8 fatigue, so every NPC in the
  campaign chose to rest and **the world went inert after one advance**. Ordinary
  living now covers ordinary needs (`need_upkeep`, 0.85) and a need approaches
  `1 - upkeep` exponentially instead of climbing to 1. `HOURS_TO_DESPERATE` is
  therefore the span for somebody getting *nothing*, which is what deprivation
  will take away. At `need_upkeep = 0` a besieged character still starves on the
  documented schedule — hunger 0.51 by day one, 0.82 by day three.
- **Beliefs never decay.** Confidence is set from `source_kind` and never moves
  again, so a rumour assumed once sits at 0.35 a decade later. Spec is
  `03-KNOWLEDGE-BASE.md` §4. **It did not land in P3** — the decision engine
  reads beliefs but nothing ages them.
- **Value keywords are English-only** (`mind/memory/values.py`). Fine for now;
  it would need attention before a non-English campaign.
- **`web/routes.py` is ~3300 lines.** Tabletop stays out of it; anything new goes
  in `web/dnd/`.
- **Seeded backstories are stamped "recently".** `_seed_history` dates them
  `max(0, world_time - randint(200, 20000))` minutes, which clamps to 0 in a
  fresh campaign and is only ~14 days even when it does not — so a formative
  childhood event reads as last week. They also carry no cue (`details=[]`), so
  they can never be recalled *and* can never contaminate a confabulation.
- **Arc consolidation (mid → long) is still called from nowhere.** Scene-level
  runs on `/scene close`. The arc level now has a tick to hang from and still
  is not wired — a cheap next job.
- **`PYTHONIOENCODING=utf-8` is needed** to run the suites in this shell, or the
  clock faces and arrows crash the Windows console rather than the code.
- **The role and culture prior tables are still Python** — the last of them.
  Behaviour archetypes went to data first (§6 step 3b) and **interaction kinds
  followed** (§8c), so the machinery, the layering, the panel shape and the
  rename-edits-in-place rule are all established and proven twice.
  `04-ENTITIES.md` §9 step 1 wants exactly the same treatment here.
  `role_prior_weight` makes them switchable but not *editable* — a GM still
  cannot add a trade. **This is the next item the owner has queued** (§8, item 4).
- **Rulesets do not model wealth**, so `standing` is set by hand. Deriving it
  from the sheet is the natural next step (`04-ENTITIES.md` §2b).

## 8. P4 — what is actually next

`12-ROADMAP.md` calls it *Voice*, and the roadmap's own ordering is the
important part: **the non-AI paths land first**, and a good deal of P4 is
reachable with no model installed at all.

The playtest is deferred by the owner's decision, not skipped — see the header
and §2b. Anything it returns outranks this list.

### The half that needs no model

1. ~~**More of `_turn_summary`.**~~ ✅ **built** — see §8a.
2. ~~**Templated episode gists.**~~ ✅ **built** — see §8b. *(Left below for the
   shape of the original ask.)* Memory used to store
   the GM's words or a phrase from `mind/relationships.PHRASES`. A richer
   deterministic templater makes recall read like recollection.
3. **The verb parser.** `/check` takes an approach and free text; P4 wants
   *"I put myself between Rook and Ondry"* to resolve to an action. Deterministic
   first, and the ten affordance verbs are the vocabulary it maps onto.
4. **Name and culture tables as data** — the same treatment archetypes got
   (`helpers/dnd/data/`, layered through `campaign.settings`). This is the
   long-standing "a GM cannot add a trade" gap and the machinery now exists.

### The half that needs one

Backend interface with `null` first, then Ollama. **No hosted API, ever** —
invariant 10, and it is not negotiable. `render_scene` and `render_dialogue`
only, each with a schema, retries and a template fallback, and the null suite is
part of every run.

**Acceptance (`12-ROADMAP.md`):** the null-backend suite passes the whole turn
loop; an NPC never speaks a fact it does not believe; closing the laptop
mid-scene degrades to templates without interrupting play.

### Before you start P4, two housekeeping items

* **Six command slots left** (94/100). Discord's cap is hard and hitting it takes
  the *whole cog* offline — it has happened twice. P4 wants commands. Group new
  ones under `/gm` or an existing group, where a whole group costs one slot.
* **121 tunables in 16 groups.** Every one is justified and "everything
  tweakable" is settled — this is not a case for removing any. But the panel
  could fold the ones nobody should ever touch behind an *advanced* disclosure,
  the way the trait override already is, before the number doubles.

## 8a. P4, increment 1 — the turn report ✅ built

**`helpers/dnd/narrate.py`**, a new tuning group *Reporting* (8 tunables), and
`tests/test_dnd_p4.py` (63 checks). `/gm advance` now says what people did, in
the detail the campaign asks for.

Before: `**2 day(s)** pass. 5 mind(s) aged…` plus, at most, a line per actor
with a goal clause. After, with everything switched on:

```
**While that happened:**
· **Marla** went for **Ondry** — closer to *settle the debt*; that settled
  their nerves a little; it was everything to **Ondry**; 3 will remember it;
  and turned from *Coward* toward *Predator*

**Elsewhere:**
· **Sella** took from **Bram** — and got what they wanted: *not go hungry*
```

Five bands, each its own switch, each reading data P3 already produced and threw
away: goals, needs relieved, stakes, witnesses, archetype drift. Plus a line cap
(`report_lines`, and **0 switches the whole report off**), whether people who did
nothing are listed, and whether off-screen actors appear at all.

**What the increment settled, and what not to undo:**

* **The room and the world are kept apart.** *The world got on with it* and *the
  person across the table moved* are different pieces of news; one merged list
  cannot tell you which is which. The cap is shared across both, so off-screen
  drifting can never push the scene off the bottom.
* **Waiting and watching are not reported by default.** They are real choices —
  `wait` is the floor every decision falls back to — but a turn where six people
  held still reads as quiet, not as six lines of *did nothing*. `report_idle`
  brings them back. This is the one place the increment **changes existing
  behaviour**; everything else only adds.
* **Drift had to be narrowed to be worth anything.** `became` is the whole
  mixture and arrives whenever any weight in it moved — which is nearly every
  action, because drift is continuous. Reported as-is it marked *every line* and
  said nothing. `commit_decision` now also records `was`, the leading archetype
  before the step, and the band fires only when the lead actually changes. If a
  later change drops `was`, the band goes quiet rather than guessing.
* **Defaults are quiet on purpose.** Goals and needs on; stakes, witnesses and
  drift off. The human verdict on P0–P2 was *"too convoluted for no payoff"*, and
  a turn answering with forty lines of trailing clauses is that verdict in a new
  place. Switching one on costs a GM one click.
* **`describe_act` and `ACTED_PHRASES` moved** from `minds` into `narrate`;
  `minds` re-exports both, so nothing that imported them from there broke.
  `report["actor_id"]` was added during the work and removed again when the
  design stopped needing it — do not re-add it without a caller.

**The bug this increment produced and caught, which is the useful part:**
`_stake_note` shipped reading its map with `int(key)`. **Entity ids are not
integers** — `ObjectId` in production, `str` in the fake — so every key raised,
every raise was caught and skipped, and the band rendered nothing at all while
its switch, its label and its description were all perfectly correct. That is
`14-CONVENTIONS.md` §5a's failure mode arriving in a Discord message instead of
on a page, and no test would have found it, because a test asserting "the band
renders" with integer fixture ids would have passed. It was found by **running a
real advance against a real store and reading the output** — the same move that
found the four bugs in P3. `test_ids_are_not_integers` is the regression, and its
fixture ids are strings for the same reason `FakeGuild.id` is a real snowflake.

Verified before shipping: all six suites; the *Reporting* group rendered and
**clicked** in `tests/render_panel.py`'s preview (8 controls, right types, right
defaults, guild id intact as a string in the POST, console clean but for the
static server's 501 on POST); and `tuning.coerce` round-tripped `"1"` → `True`
and `"3"` → `3` into a resolved `ReportTuning`.

**Next in this half:** episode gists (§8 item 2) — built, §8b.

## 8b. P4, increment 2 — episode gists ✅ built

`08-LLM-LAYER.md` §5's `summarize_episode`, which was going to be an LLM task
and is now a template. Two halves, one new tuning group *Remembering*, and 57
more checks in `test_dnd_p4.py`.

### One event, three memories of it

`minds.interact` already worked out each party's **role** — they did it, it was
done to them, or they watched — and used it for the relationship deltas. It then
handed all three **the same gist string**. P2's headline acceptance criterion is
that two witnesses to one event hold measurably different memories, and that was
true only of the *numbers*: fidelity, salience, which fields rot first. The words
were identical. Now:

```
Ondry saved me      Marla, who it happened to
I saved Marla       Ondry, who did it
Ondry saved Marla   Cass, who watched
```

* **One table, reused not copied.** `mind/relationships.PHRASES` does all three,
  because English past tense does not conjugate between *I saved* and *Ondry
  saved* — the pronouns are the whole trick. A test asserts `narrate` holds the
  same object, so a kind can never read one way in a relationship log and
  another in a memory.
* **Undirected acts too**, via `ACT_GISTS` — *I went to ground* against *Marla
  went to ground*. These are most of what anybody does, so it is the commonest
  memory a character holds about themselves. `witness_event` grew a `gist_for`
  callable for it; passing a flat `gist` still works and is right for a GM's own
  description.
* **The GM's words are never re-personed.** If a description was typed, everyone
  gets it verbatim. Authored text is not ours to rewrite into first person.
* **There is deliberately no intensity band.** *"Saved my life"* at a high stake
  reads well and asserts something the simulation does not know; an attack
  becoming *"tried to kill"* is a different claim about what happened. How much
  it mattered is `salience`, which is already per-person and already decays. If
  a later change wants gravity in the wording it needs a fact to hang it on
  first — this was considered and rejected, not overlooked.

### What a forgotten stretch reduces to

`consolidate.summarise` folds pruned memories into one hazy summary instead of
deleting them — the difference between forgetting and amnesia. It said *"a
stretch of 41 things that no longer come to mind clearly"*: a **count**, which
is the one thing about a forgotten period nobody has ever retained. §8 of
`05-MEMORY.md` asks for *"a hard winter at the docks"*, and it now says things
like **"a quiet month, mostly with Ondry"** — span, mean valence and dominant
company, all measured off the memories being folded, none invented.

`narrate.dominant` breaks ties on first appearance rather than arbitrarily,
because the same memories must fold the same way every time or replay drifts.

**`place` is the one part not wired, on purpose.** `summary_gist` takes it and
renders it, and `_summarise` passes nothing, because **nothing in the codebase
ever writes `Memory.location_id`** — every memory has `None` there. The tempting
shortcut is the scene id and it is a trap: `Position` keeps `location_id` and
`scene_id` apart and `world/view.py` carries the former, so filing scene ids
under a memory's location would collide with the location model the moment
anybody builds one. When memories learn where they happened, that call gains one
argument. **Do not "fix" this by passing a scene id.**

### What clicking found this time

The *Remembering* group shipped **with no icon** — `_GROUP_EMOJI` in
`web/dnd/pages.py` is a hand-maintained map and a missing key renders a bare
heading and a bullet where every other group has a face. Invisible to all 875
assertions, and found in the preview. `test_dnd_panel.py` now asserts every
group in `tuning_registry.GROUPS` has one, so the next group cannot ship bare.

Also worth knowing: **the 542-test P2 suite asserted nothing about gist wording
at all.** Changing what every memory in the system says broke no test. The
mechanics were covered thoroughly and the words were not covered at all, which
is `14-CONVENTIONS.md` §5a's lesson in a different costume.

`tests/render_panel.py` now runs one real `interact`, so the inspector preview
shows a gist the engine phrased rather than only ones typed by hand. Verified by
clicking: it renders as *"Ondry Kass saved me — a long time ago"* under **Right
now**, and the *Remembering* controls post with the guild id intact as a string.

**Next in this half:** the verb parser (§8 item 3) — `/check`'s free text
resolving to one of the ten affordance verbs, deterministic first. It is the one
remaining no-model item that touches the *"too convoluted to play"* verdict
directly, and the vocabulary it maps onto is already fixed by `rules/ruleset.py`.
Item 4, name and culture tables as data, is the other and is pure plumbing —
the archetype machinery in `helpers/dnd/packs.py` is the pattern to copy.

## 8c. Interaction kinds as data ✅ built

**Not a roadmap item — the owner asked for it directly**: *"I need those stakes
written down and editable somewhere, make sure that is the case."* They were
not. Now they are `helpers/dnd/data/interactions.json`, resolved built-in →
server → campaign, with a **What people do to each other** section on the
campaign page.

### What was actually wrong

The set of interaction kinds was written down **four times**, all keyed by the
same strings and all maintained by hand:

| Table | Where | What it held |
| --- | --- | --- |
| `DELTAS` | `mind/relationships.py` | how each kind moves the two people |
| `PHRASES` | `mind/relationships.py` | how it reads in a memory |
| `ROMANTIC` | `mind/relationships.py` | which are gated behind an optional need |
| `KIND_MAGNITUDE` | `mind/stakes.py` | how big it is before circumstances |

They had already drifted. The five romantic kinds were added to three of the
four and **never given a magnitude**, so they fell through to the 0.4 default:
`lay_with` was worth exactly as much as `lied`. No test could have caught it,
because there was nowhere the set of kinds was defined as one thing. The shipped
file now gives them real numbers (`lay_with` 0.7, `courted` 0.5, `repelled` 0.5,
`rebuffed` 0.4, `flirted` 0.25), and a test asserts every kind has its own.

### How it is put together

* **`world/interaction.py`** is the model, and it owns the two derivations that
  used to be loose functions — `felt_valence()` (how an act feels, taken *from*
  the deltas rather than stored as a second number that could disagree) and
  `actor_view()` (debt inverts, feeling is an echo not a mirror).
* **`interactions.py`** is the registry: `built_in()`, `Interactions`,
  `validate`, exactly mirroring `packs.py`. It also exposes `deltas()`,
  `phrases()` and `magnitudes()` — the shapes each pure module wants, built at
  the edge and passed in, because `mind/` never reaches for a registry itself.
* **The old module-level tables still exist and now *derive* from the file**, so
  the many callers that only ever wanted the shipped numbers are untouched and
  there is still exactly one place a number is written. Tests assert the
  equality, so the derivation cannot rot into a copy.
* `interact` and `relate` take `campaign=` / `available_kinds=`; `minds`
  resolves the catalogue once per call and hands it down.
* **`requires` replaced `ROMANTIC`.** A kind names the optional need it belongs
  to, so a campaign inventing an act of its own says for itself which need gates
  it, and the gate now reads `tuning.permits_need(...)` — the canonical two-gate
  check (setting *and* line) rather than a second path to the same question.
* **`requires` is deliberately not editable from the panel.** A control that can
  clear it is a control that walks round the safety gate; an override inherits it
  from the shipped kind.

### The stake bands, the other half of the ask

The four phrases the turn report uses (*it was everything to them* … *barely
noticed*) had their thresholds hardcoded in `narrate.py` — something I shipped
in §8a and which was an invariant-1 violation the moment it landed. The three
lines are now tunables (`stake_everything`, `stake_mattered`, `stake_noted`, in
*Reporting*). The **wording** is not tunable: four phrases is a vocabulary, not
three numbers, and a campaign that wants its own is asking for something bigger.

### The test that changed shape

`test_tunables` asserted every `ReportTuning` field had a tunable named
`report_<field>` — a **naming** convention, which the stake bands promptly broke
by being named sensibly. It now asserts the **behavioural** thing: every tunable
in the group must actually move a field, and every field must be moved by some
tunable. Either half failing is a control wired to nothing, which is this
project's most expensive recurring bug. Prefer this shape.

Verified by clicking: 21 cards render, `saved` shows its real deltas and a
magnitude of 1.00, the five gated kinds carry a note naming the need holding
them, and Save posts `{key, label, phrase, magnitude, deltas}` with the guild id
intact as a string and zero-valued axes omitted. Server side exercised
separately — validate, layer, resolve, and a brand-new kind
(`swore_an_oath_to`) resolving like any other.

## 8d. The parameter catalogue ✅ built

**Asked for directly, and it started as a complaint:** *"I don't like that you
are deviating from my initial sacred dogma of EVERYTHING IS A TWEAKABLE
PARAMETER VISIBLE TO THE BOT OWNER. I absolutely don't need a black box system
with some baked in weights."*

That was fair, and the scale of it was worse than it looked. An AST walk over
`helpers/dnd` found **82 constants that shape behaviour with no control of any
kind** — including `RISK`, `NORM`, `SOCIAL_SIGN`, `TRAIT_AFFINITY`,
`RELATION_READS` and `NEEDS_SERVED`, which between them are *the entire per-verb
weighting the decision engine scores with*. The rule had been kept for anything
anybody thought to call a tunable and quietly broken everywhere else, and it was
invisible because **there was no list for a constant to be missing from**.

### What shipped

* **`helpers/dnd/catalogue.py`** — one entry per parameter, 205 in total: 121
  tunables, 2 editable data files, 82 baked in. Each row carries a label, a
  description, its default, its range, which layer it can be set at, which
  module reads it, what it combines with, and what else moves when it moves.
* **Tabletop → Admin → List of parameters** (`/guild/{gid}/tabletop/parameters`,
  admin-scoped) renders it, grouped, one section at a time.
* **`tests/test_dnd_catalogue.py`** — 1,906 checks, and the point of the whole
  exercise.

### Three decisions worth keeping

1. **It lists what is *not* exposed, on the same page, flagged.** A defect
   nobody can see is one nobody fixes, so the baked-in rows name the file, the
   live value and where it should end up. The page is the work queue.
2. **It never stores a copy of a value.** `live_values()` reads them out of the
   source at render time. The first draft did store copies and the suite caught
   four transcribed wrong within minutes — a catalogue with its own copy of a
   number is just one more hand-maintained table that can drift.
3. **Cross-relations are derived where possible.** Which typed view a tunable
   arrives in is read out of `tuning.py`'s own AST rather than maintained by
   hand; only the relations that reach *across* a boundary are authored, in
   `AFFECTS`. It would be absurd for this file to be the parallel list it exists
   to prevent.

### The rule is now a test

`14-CONVENTIONS.md` invariant **1a** and the first line of the §6 checklist.
The suite walks every module and fails on any behaviour-shaping constant that is
not a tunable, not a row in a data file, and not in `BAKED_IN`. It also fails if
a listed constant has moved, been deleted, or become a tunable without being
reclassified — so the queue cannot silently contain finished work.

**Adding a parameter now means adding it to the catalogue.** That is not a
convention any more, it is a failing test.

### The queue, in priority order

The 82 are not equal. In the order they should be done:

1. **`data/verbs.json`** — the decision engine's six per-verb tables plus the
   goal map. The biggest black box, and **a prerequisite for adding verbs**:
   every new verb needs an entry in all six, so doing this first turns *adding a
   verb* into a data edit. The owner has asked for five new ones (help/aid,
   follow, search/examine, wait-for/listen, threaten), which is the next
   increment after this.
2. **`data/priors.json`** — role and culture tables. The long-standing "a GM
   cannot add a trade" gap, now the oldest thing on the list.
3. **`data/axes.json`**, **`data/needs.json`**, **`data/values.json`** — trait
   modifiers, attraction weights, need schedules, and the wording tables.
4. **`data/rulesets.json`** — SRD class tables and both default DCs. Lowest
   value: it is the part a GM is least likely to want to change, and the SRD
   numbers are the SRD's.
5. The loose scalars, which can simply become tunables in their existing groups.

## 9. Keeping this file honest

It was updated in **twelve separate commits** on the day P3 was built, once per
increment, and it still drifted — because each update patched the paragraph it
was touching and left the surrounding text disagreeing with it. By the end the
header said a fresh session was picking up P3, the phase table said P3 was
complete *and* that the decision engine was all that remained, a heading read
"What remains" above six things that were built, and the architecture diagram
was missing four modules that had been added that day.

Worst of it: **the test count was wrong by forty**, because it was being
incremented rather than measured. A number nobody checked, in the one document
whose whole job is to be trusted without checking.

So, when updating this file:

* **Measure, do not increment.** The count is
  `py tests/test_command_names.py` plus the four suite totals. Run them.
* **Read §1, §2 and §5 after changing anything.** They describe the whole, so
  they go stale when a part changes, and nothing about editing §6 makes you look
  at them.
* **Grep for the claim you are invalidating**, not just the sentence you are
  rewriting: "all that remains", "still unbuilt", "read by nothing", "P3".

## 10. Working preferences

**Moved to `docs/HANDOFF.md` §7**, because they are how the owner wants the
whole repo worked on rather than anything to do with simulation: one complete
checkable increment at a time, verify at the level it will be used, click it and
read the console, push after every commit, scope your `git add`, and everything
is a tweakable parameter.

Two that are tabletop's own:

- **Do not spawn subagents or run deep research** unless asked.
- **Read `14-CONVENTIONS.md` §4 before changing anything in `helpers/dnd/`.**
  The twelve invariants are review gates, and two of them exist because
  production broke.
