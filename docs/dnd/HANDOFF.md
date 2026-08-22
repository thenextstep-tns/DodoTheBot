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
| P3 | ◑ **three of four** | World tick ✅, faction clocks ✅, rumour propagation ✅. **The decision engine is all that remains** — step 1 of 6 (`EntityView`) is built |

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

**385 tests** across five suites, all passing:

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
` inside a patch script's replacement string | Becomes a real newline and splits the target's source string in two — cost three separate repairs in one session | Escape it (`\n`), or use the Edit tool for anything containing escapes or `"""` |
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
| **Time modes** | `time_mode` tunable | `manual` (default) / `automatic` / `timeless`. Timeless is not "off": nothing ages on a tick *or* on command, for dungeon crawls |
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
2. **`ruleset.affordances(actor, scene)`** — add to the protocol and both
   rulesets. What a scene physically permits: attack, flee, speak, give, take,
   hide, wait, use, move. `04-ENTITIES.md` §2 says it was deferred until a Scene
   existed; it exists.
3. **Goals on `Entity`** plus **behaviour packs**. The roadmap says packs come
   from the global KB — note that the prior tables are still Python
   (§7), so decide deliberately whether packs repeat that mistake.
4. **`mind/decide.py`** — perceive → appraise → propose → score → select, pure
   and seeded. Eight utility terms, each bounded to −1…1 before weighting.
   **Traits modulate the terms, never the weights** (§6 of the spec) — per-entity
   weights would be untunable across 200 NPCs.
5. **Commit + traces** — the term breakdown stored on the `WorldEvent`, and a
   decision-trace view in the panel inspector. This is the explainability
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

- **`time_mode` has no working panel control.** It is the one `choice` tunable,
  and `_tune_row` in `web/dnd/pages.py` renders every tunable as
  `<input type="number" min="0.0" max="1.0">` — so the row shows an empty number
  box and a GM cannot select `automatic` or `timeless` from the panel at all.
  `_dnd_param_input` a few hundred lines above already knows how to render a
  choice; `_tune_row` needs the same three lines. Found while adding the
  Perception group; left alone to keep that increment clean.
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
- **`boldness` is read by nothing.** Declared, rolled, stored, displayed, and
  consulted by no code anywhere. P3's risk term is where it starts mattering.
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
- **Prior tables are still Python.** `04-ENTITIES.md` §9 step 1 says culture and
  role come from the campaign KB. `role_prior_weight` makes them switchable but
  not yet *editable* — a GM cannot add a trade.
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
