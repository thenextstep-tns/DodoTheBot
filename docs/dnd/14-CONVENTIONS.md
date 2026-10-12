# Working Conventions — instructions for Claude

Read this before writing any code in this module. It encodes how this codebase
works and the decisions that are already made, so they don't get re-litigated
each session.

---

## 1. Before you start a session on this module

1. Read `00-PRODUCT.md` §1 (the thesis) and `01-ARCHITECTURE.md` §1 (the layers).
   Everything else is reference — read the file for the subsystem you're touching.
2. Check `12-ROADMAP.md` for the current phase. **Do not build ahead of the
   phase.** Building P3 machinery during P1 is how this becomes a system that
   never ships.
3. Verify against the actual code before asserting anything about it. These
   documents describe a design; only some of it exists at any given time.

## 2. House style (match the existing codebase)

The bot has a strong, consistent voice. Match it — do not import a different one.

- **Module docstrings explain *why*, not what.** Look at
  `helpers/state_machine.py`, `helpers/visibility.py`, `helpers/parameters.py`:
  each opens by explaining the problem it solves and how it relates to its
  neighbours. Do the same.
- **Section banners** — `# ---- #` comment blocks separating logical regions.
- `from __future__ import annotations` in new helper modules.
- Type hints throughout; `Optional[...]`/`| None` consistently within a file.
- Comments explain non-obvious decisions, not syntax. Density matches the
  surrounding file.
- **User-facing strings go in `lang_dnd.py`** (not `lang.py` — see invariant 11)
  and are read as `lang_dnd.KEY`. No player-visible literal in a cog, ever.
- Logging via `self.bot.logger`; internal debug text stays in the code, not
  `lang.py`.

## 3. Commit conventions

Look at `git log`. Messages are lowercase-ish, specific, and describe the *effect*
on behaviour, not the mechanics of the change:

```
Trials: drop "Not run yet this session"
Log: don't merge one person's role edits into another's
Trial ranks: enrolment is the switch, so drop the one above it
```

Follow that. `Subsystem: what changed and why it matters.` Not "refactor memory
module" or "add feature".

**Push to origin after every commit** — the user's standing instruction, and the
`refactor` branch auto-deploys to production via GitHub Actions. Which means:

> **A push to `refactor` deploys to the live bot in ~14 seconds.** Never push
> something you have not at least imported and smoke-tested.

## 4. Non-negotiable invariants

Breaking any of these is a review failure, not a style preference.

1. **Nothing is baked in.** Every constant that shapes behaviour is a tunable in
   `helpers/dnd/tuning.py`, with a label, a description, a range and a group,
   resolved **default → server → campaign**. If something can be softened it must
   also be switchable off entirely (decay rate 0 = frozen memory). A magic number
   in a simulation file is a review failure. Standing project rule, not a
   tabletop one — see the `everything-tweakable` memory.

   **1a. And it goes in the catalogue.** `helpers/dnd/catalogue.py` is the one
   list of every parameter in the engine, rendered at **Tabletop → Admin → List
   of parameters**. Adding a parameter means adding it there, with what it
   does, what else it moves, its default, its range and where it can be set.
   `tests/test_dnd_catalogue.py` walks every module in `helpers/dnd` and **fails
   on any constant that shapes behaviour and is not in the catalogue** — either
   as a tunable, as a row in an editable data file, or listed in `BAKED_IN` with
   the reason it is not exposed yet.

   This is a test rather than a paragraph because the paragraph above it did not
   work: the rule was written down twice and quietly broken **eighty-two times**,
   including the whole per-verb weight table the decision engine scores with. It
   was invisible precisely because there was no list for it to be missing from.

   The catalogue never stores a copy of a value — it reads the live one out of
   the source. A first draft did store copies and the suite caught four of them
   transcribed wrong within minutes, which is the argument in miniature.
2. **The panel is the configuration surface, not Discord.** Every tunable and
   setting ships with a panel control **in the same phase as the feature**, with
   a description, a range, the current value, where it was inherited from, and a
   way to clear it. A slash command for configuration is a shortcut, never the
   API — commands are for *playing*: acting, rolling, looking. Long flat lists in
   the panel are a defect; group them. See the `webapp-first-config` memory.
3. **`llm/` is a leaf.** `world/`, `rules/`, `mind/` and `store/` never import it.
4. **LLM output is never world truth.** It goes to the canon queue, or it is
   display-only.
5. **Every document is scoped.** `guild_id` *and* `campaign_id`, always, and
   reads go through `store/repo.py`.
6. **Pure layers are pure.** No I/O, no `await`, no wall-clock reads, no bare
   `random` — the RNG is passed in, seeded.
7. **Bounded memory.** Nothing grows without a cap. The old cog's `history`
   string is the anti-pattern this module exists to correct.
8. **`backend=null` always works.** Every LLM task has a deterministic fallback,
   and the null suite is part of the test run.
9. **Mechanics before prose.** Post the outcome, then stream narration.
10. **No inference leaves hardware we own.** Ollama only. No hosted API, no
    third-party provider, no "just for the free tier", no API-key field. If you
    find yourself adding an HTTP client for a model vendor, stop.
11. **Stay separate.** Tabletop has its own strings (`lang_dnd.py`), parameters
    (`helpers/dnd/parameters.py`), tunables, storage, panel pages and dashboard
    section. Do not add a `dnd_*` key to the shared parameter registry, a `TT_*`
    string to `lang.py`, or a tabletop cog to `cog_categories.CATEGORIES`. The
    full map, including what *is* deliberately shared and why, is
    `15-SEPARATION.md`.
12. **Deterministic first.** If it can be computed in Python, it is computed in
    Python. A model is called only where prose quality is itself the product.
    Adding a call site means adding a row to the table in `08-LLM-LAYER.md` §5
    naming the deterministic alternative and why it is insufficient. "It would be
    nicer" is not a reason. This is what keeps the product from decaying into an
    LLM wrapper one convenient shortcut at a time.

## 5. Tests that must exist

- **Import-boundary test** — greps imports to enforce invariant 3. Cheap, catches
  the failure that would otherwise be invisible until it matters.
- **Command test** (`tests/test_command_names.py`) — two checks, each of which
  has taken the whole cog offline in production once. Top-level names must be
  unique across *all* cogs (`CommandAlreadyRegistered`), and the application must
  stay under Discord's **100 top-level slash commands** (`CommandLimitReached`).
  Neither shows up when a cog is loaded in isolation. Run it before any push that
  adds a command; the fix for the cap is always to group, since a group costs one
  slot however many subcommands it holds.
- **Null-backend suite** — the full turn loop with no model. Enforces invariant 8.
- **Golden replay** — a recorded event log replays to an identical state hash.
- **Tenant isolation** — two campaigns, same entity names, every repository method
  checked for leakage.
- **Property tests** — memory ≤ budget; salience monotonic in reinforcement;
  utility finite; decay never raises a fidelity.
- **Panel script wiring** (`tests/test_dnd_panel.py::test_script_wiring`) — no
  unquoted integer above 2⁵³ anywhere in the generated JavaScript, and the
  status element emitted before the script that looks it up. Both of those
  shipped at once and between them made **every control in the tabletop section
  do nothing at all**, silently, for days.

### 5a. What the panel tests do *not* cover

`tests/test_dnd_panel.py` asserts on **HTML strings**. Nothing in this repo
executes a page's JavaScript or calls a panel endpoint, so a control wired to
nothing passes every test in the suite. 305 green tests did not notice that the
switch which turns the whole engine on had never once worked.

So the rule is: **a panel control is not done until it has been clicked.**

```bash
py tests/render_panel.py && py -m http.server 8899 --directory .preview
```

Open it, click the thing you changed, and **read the browser console** — before
reasoning about the code, not after. On the bug above, the console named the
cause in one step; inference from reading the source did not, over many.

Two specific traps, both of which cost a real outage:

- **Discord ids are 64-bit.** `806174526383325225` as a bare JavaScript numeric
  literal parses as `…200` — a guild that does not exist — so every request 404s
  at the scope check. Interpolate snowflakes as **strings**, as `panel.js` says
  in its opening comment. Tabletop's script is separate by design
  (`15-SEPARATION.md`), which is exactly why it re-introduced this.
- **Test fixtures must use real-shaped ids.** The fake guild was `7777`, small
  enough to survive JavaScript intact, so the bug was invisible in tests and
  present for every real guild. `FakeGuild.id` is a genuine snowflake now.

### 5a-bis. Work in increments the user can check

**Do not build a phase and hand it over.** Build the smallest piece that is
complete enough to exercise, verify it yourself at the level it will be used,
then **stop and ask the user to check it** — naming the exact thing to do and
what they should see. Continue only once they confirm.

This is not a style preference. P0–P2 were delivered as three finished phases,
34 tunables and a panel section, all reported green — and the checkbox that
turns the engine on had never worked once. Every hour after that bug landed was
spent building on something nobody could switch on. A big delivery hides the
hole; a small one cannot.

Practically:

- One increment = one thing the user can click, run or type, end to end.
- Say what to check in a sentence, not a twelve-act script.
- If an increment turns out to be blocked, say so and stop — do not carry on
  into the next one to keep the momentum.
- The user's confirmation is the gate. Not the test suite, not the deploy log.

### 5a-ter. Update the handoff before you stop

**The last act of any session that changed state is updating `HANDOFF.md`.** Not
an offer, not a nicety — part of finishing. Context is summarised rather than
preserved and a summary is lossy; that file is the only thing that survives
intact into the next session.

It must say what shipped, what is now fixed or stale, what broke and why nothing
caught it, and **the next increment with the shape it should take**. Correct
anything that has stopped being true. A handoff naming an already-built thing as
"start here" is worse than no handoff, because it will be believed: one line in
this file once told a session not to verify through the UI, and a switch that
had never worked got reported as verified twice on the strength of it.

Keep it readable. It is onboarding, not reference — the reference is the
sixteen documents next to it.

### 5b. "Deployed" is not "works"

Grepping the journal for `Loaded cog 'cogs.dnd` proves the process started. It
proves nothing about whether the feature functions. Do not report a panel change
as verified on the strength of a log line — either exercise it, or say plainly
that it is deployed but untested.

## 6. Integration checklist for anything new

Every feature added to this module should ask:

- [ ] **Did it introduce a number?** → then it is a parameter, and it needs a
      spec in `helpers/dnd/tuning.py`, a control on the campaign page, **and a
      row in `helpers/dnd/catalogue.py`** (invariant 1a). If it genuinely cannot
      be exposed yet, it still goes in `catalogue.BAKED_IN` with the reason and
      where it should end up. The suite will not let it through otherwise. This
      is the first question, not the last, because it is the one that has been
      skipped most.
- [ ] Does it need a per-guild tunable? → add a spec to
      `helpers/dnd/parameters.py` (**not** the shared registry) and render it in
      the Engine section of the DnD panel page.
- [ ] Is it a passive behaviour? → gate it with `bot.visibility.feature_active`.
      Features are shared enforcement, so they stay in `cog_categories.FEATURES`
      even though the cogs themselves do not (`15-SEPARATION.md` §2).
- [ ] Does it hold state across a restart? → `PersistentFlow` from
      `helpers/state_machine.py`.
- [ ] Does it say anything to a user? → `lang_dnd.py` key.
- [ ] Does it change server configuration? → audit into `config_audit`.
- [ ] Is it tier-limited? → `entitlements.check(...)`, degrade never destroy.
- [ ] New collection? → declare it in `config/database.py` with a comment, and add
      its indices to `store/indices.py`.

## 7. Things not to do

- **Don't append DnD pages to `web/routes.py`.** It is 3281 lines. New pages go in
  `web/dnd/` and mount from `create_app`.
- **Don't hardcode a ruleset.** If 5e assumptions leak outside `rules/srd5e.py`,
  the abstraction has failed.
- **Don't add a "just ask the LLM" shortcut** when a deterministic path is
  awkward. That shortcut is how every competitor's product ended up mush. If the
  deterministic path is genuinely wrong, change the design and say so — don't
  route around it quietly.
- **Don't infer pronouns from names**, in code or in generation. Entities carry an
  explicit field; the default is `they/them`.
- **Don't install Ollama on the VPS.** Settled and closed — 468 MB free, and the
  bot lives there. Inference happens on the laptop.
- **Don't add a hosted-API backend**, even as a convenience for testing. See
  invariant 8.
- **Don't build ahead of the roadmap phase.**

## 8. Decisions already made — do not re-open without new information

| Decision | Where |
| --- | --- |
| Simulation owns truth; LLM translates at the edges | `00-PRODUCT.md` §1 |
| Multi-tenant from the first commit | `01-ARCHITECTURE.md` §7 |
| Both rulesets built in parallel, freeform playable first | `04-ENTITIES.md` §2 |
| Async-first, live sessions as a tightening of the same loop | `12-ROADMAP.md` |
| Local inference only; Ollama on the owner's laptop; **no hosted API ever** | `08-LLM-LAYER.md` §2 |
| Qwen3 4B Q4_K_M as the starting model, `num_ctx=4096` | `08-LLM-LAYER.md` §3–4 |
| Two AI tasks, one AI fallback, two non-AI | `08-LLM-LAYER.md` §5 |
| Utility AI, not behaviour trees or GOAP | `06-DECISION-ENGINE.md` §1 |
| Memory decays field-wise and confabulates | `05-MEMORY.md` §4 |
| Canon queue with soft canon | `03-KNOWLEDGE-BASE.md` §5 |
| Suggester mode before autonomous GM | `07-NARRATIVE-ENGINE.md` §1 |
| Campaign scope resolver separate from `PanelAccessManager` | `09-SURFACES.md` §4 |

## 9. When the design is wrong

It will be, somewhere. When you find it:

1. Say so plainly, with the specific case that breaks it.
2. Propose the change and its cost.
3. **Update the relevant doc in the same commit as the code.** A design document
   that has drifted from the code is worse than none, because the next session
   will trust it.
