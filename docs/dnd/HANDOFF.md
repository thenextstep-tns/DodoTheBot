# Handoff — start here in a new session

Everything through **P2 is built, tested and live**. This file is what a fresh
session needs to pick up at P3 without re-deriving anything.

---

## 1. Read this much, in this order

1. **`README.md`** — the thesis and the file index. Two minutes.
2. **`14-CONVENTIONS.md`** — how to work here. The twelve invariants are not
   suggestions; two of them exist because production broke.
3. **`12-ROADMAP.md`** — what is done, what P3 is, and the acceptance criteria.
4. The design file for whatever you are actually touching.

Do **not** read all sixteen documents. They are reference, not onboarding.

## 2. Where things stand

| Phase | State | What it gave us |
| --- | --- | --- |
| P0 | ✅ live | Campaigns, characters from a real ruleset, scenes, dice wired into resolution, event log, legacy importer |
| P1 | ✅ live | Four-tier knowledge with overrides, budgeted retrieval, beliefs, fog of war, canon queue — **plus full separation from the rest of the bot** |
| P2 | ✅ live | Traits + inheritance, needs, memory that forgets like people do, relationships, NPCs, the entity inspector, tunables in two layers |
| P2+ | ✅ live | **Stakes** — an act is worth different amounts to each person in it; emergent roles; scene consolidation. All of it came out of the playtest |
| P3 | ◑ **three of four** | World tick ✅, faction clocks ✅, rumour propagation ✅. **The decision engine is all that remains** — steps 1–4 of 6 built |

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

**599 tests** across five suites, all passing:

```bash
py tests/test_command_names.py && py tests/test_dnd_p0.py && py tests/test_dnd_p1.py && py tests/test_dnd_p2.py && py tests/test_dnd_panel.py
```

No pytest, no mongomock — `tests/fake_mongo.py` swaps the collections for an
in-memory fake, so nothing touches the real database.

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

| Trap | What happens | Guard |
| --- | --- | --- |
| **100 slash commands** is a hard Discord cap | `CommandLimitReached` at load — the *whole cog* goes offline | `tests/test_command_names.py` fails at 96. Currently 95. **Group under `/gm`; a group costs one slot.** |
| Duplicate top-level command name | `CommandAlreadyRegistered`, same outcome | Same test |
| `cogs/dnd/__init__.py` can't hold `setup()` | `load_all_cogs` skips `__`-prefixed files | Entry point is `cogs/dnd/cog.py` |
| Command groups built in `__init__` | Subcommands report no cog, so the per-guild switch is bypassed | Groups are **class attributes** |
| `os.walk` yields `cogs.dnd`, not `cogs.dnd.` | DnD modules listed as cogs with dead Load buttons | `registry.is_dnd_extension` matches both |
| Bash heredocs choke on this codebase's content | Silent truncation or parse errors | Write a `.py` patch script to the scratchpad and run it with `py` |
| A `
` inside a patch script's replacement string | Becomes a real newline and splits the target's source string in two — cost three separate repairs in one session, and later **a production outage**: `lang_dnd.py` shipped unparseable and the cog would not load | **Use the Edit tool** for any replacement containing an escape or `"""`. This trap was already written down and got walked into anyway, which is why the guard is now a test rather than a paragraph |
| `python` ≠ `py` on this machine | `ModuleNotFoundError: discord` | Always use `py` |

**A cog that loads fine in isolation can still fail in production.** Both outages
this project has had were invisible to a single-cog smoke test. After any push
that adds a command, check:

```bash
ssh -i ~/.ssh/id_dodo_vps root@45.141.76.118 "journalctl -u dodo --since '-3min' --no-pager | grep -iE \"loaded cog 'cogs.dnd|failed to load\""
```

## 5. The architecture in six lines

```
cogs/dnd/, web/dnd/     surfaces
helpers/dnd/minds.py    orchestration — resolves tuning, calls the pure layer, writes back
helpers/dnd/mind/       minds: traits, needs, memory, relationships,
                        stakes — what an act was worth to each party
                                                             (pure, seeded)
helpers/dnd/world/      what exists: entity, memory, belief, event    (dataclasses)
                        — and view.py, the only thing a decision may see
helpers/dnd/rules/      dice and rulesets                             (pure, seeded)
helpers/dnd/store/      repositories — every query carries its tenant
```

Two rules hold it together: **the pure layers never do I/O and never read
configuration** (tuning is resolved at the orchestration edge and passed in as
typed dataclasses), and **every repository requires a `Scope`**, so an unscoped
query cannot be written.

## 6. P3 — three increments landed, one remains

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

Acceptance is half-met: clocks advance and a rumour reaches someone who never
met its subject. What is missing is *an NPC pursuing a goal*.

### What remains: the decision engine

`06-DECISION-ENGINE.md` is the spec and is unchanged. This is the largest single
piece in P3 — do **not** attempt it in one increment. Suggested split, each
checkable on its own:

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
5. **Commit** — what remains of this step is the *writing*: emit the
   `WorldEvent` with `Decision.to_doc()` on it (already shaped for that),
   witnesses encode, relationship deltas apply, beliefs propagate
   (§8). The trace **view** landed with step 4. This is the explainability
   feature and the debugger; it is not optional polish.
6. **Coarse and dormant paths** — `active` NPCs run argmax with no perception;
   `dormant` are extrapolated in closed form. Follow the shape of
   `needs.advanced()`, which is already written that way.

Budget: < 1 ms per focus NPC, < 25 ms for a 200-NPC tick. If the full pipeline
is too slow the fix is `CANDIDATE_CAP` or fewer terms — **never** caching
decisions, which would break replay.

`boldness` is read by nothing today; step 4 is where it starts mattering.

### Four things designed during the playtest, still unbuilt

Each has a spec section and no code. None blocks the decision engine, and all
four want the tick that now exists:

- **Deprivation effects** (`04-ENTITIES.md` §5a) — needs bend mood and apply
  ruleset conditions. Lethality default off and **interlocked**: nothing can
  satisfy a need until NPCs can act, so switching it on now empties the world.
- **Trait drift and rupture** (§3a, §3b) — an exposure ledger; sustained extreme
  exposure breaks one axis past the ceiling. Rupture is gated by the campaign's
  lines, not merely tunable.
- **Belief lifecycle** (`03-KNOWLEDGE-BASE.md` §4) — `fact`/`rumour`/`value`
  kinds; the first two erode, values harden and feed the ledger.
- **Standing and importance emerge** (§2b) — standing rides the same ledger;
  importance recomputed from story entanglement.

**Everything in P3 must be tunable and must have a panel control.** Expect a
Clocks page and the decision-trace view.

## 7. Known gaps, honestly

- **`tests/fake_mongo.py` has no `$unset`**, so *clearing* a server-level tunable
  back to inherited is the one leg of the tuning round trip no test can exercise.
  The campaign layer clears fine (it rewrites the whole settings document).
- **`/canon` is empty and stays empty until P4.** Nothing invents facts yet.
- **Nothing narrates.** Every message is mechanical output, by design.
- **The legacy cog is still loaded** as `dnd_legacy`. It goes one release after
  the migration has actually been run (`13-MIGRATION.md` §6).
- **Nothing ever writes `entity.traits` after creation.** `04-ENTITIES.md` §3
  says temperament shifts on an imprint and drives drift with experience; the
  only trait access in the codebase is a read. The mechanic is specified in
  `04-ENTITIES.md` §3a and unbuilt — an NPC is the person they were rolled as,
  permanently.
- **Beliefs never decay.** Confidence is set from `source_kind` and never moves
  again, so a rumour assumed once sits at 0.35 a decade later. Spec is
  `03-KNOWLEDGE-BASE.md` §4; both land in P3.
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
- **Prior tables are still Python** — the role and culture ones, at least.
  Behaviour archetypes are now data a GM can edit (§6 step 3b), and the same
  treatment is what `04-ENTITIES.md` §9 step 1 wants for these: they could
  move into `helpers/dnd/data/` and layer through `campaign.settings` with
  the machinery packs already built.
  `role_prior_weight` makes them switchable but not *editable* — a GM still
  cannot add a trade.
- **Rulesets do not model wealth**, so `standing` is set by hand. Deriving it
  from the sheet is the natural next step (`04-ENTITIES.md` §2b).

## 8. Working preferences

- **Ship one complete, checkable thing at a time.** Not a phase, not a batch —
  the smallest increment the user can actually exercise. Then stop, say plainly
  what to check and how, and *wait for them to confirm* before continuing. A
  phase delivered whole is a phase where every part can be broken at once, and
  the user pays for the whole thing before finding out.
- **Verify the increment yourself first**, at the level it will be used. For a
  panel control that means clicking it (`14-CONVENTIONS.md` §5a). "The tests
  pass" and "the cog loaded" are not evidence that a feature works — an earlier
  version of this list said they were, and on the strength of it a switch that
  had never once functioned was reported as verified twice.
- Do not spawn subagents or run deep research unless asked.
- Commit messages describe the *effect*, not the mechanics. See `git log`.
- Push after every commit.
- **Scope your `git add`.** A blanket `git add -A` once swept an unrelated
  in-progress edit of the user's into a deploy.
