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
- **User-facing strings go in `lang_dnd.py`** (not `lang.py` — see invariant 9)
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

1. **`llm/` is a leaf.** `world/`, `rules/`, `mind/` and `store/` never import it.
2. **LLM output is never world truth.** It goes to the canon queue or it is
   display-only.
3. **Every document is scoped.** `guild_id` *and* `campaign_id`, always, and
   reads go through `store/repo.py`.
4. **Pure layers are pure.** No I/O, no `await`, no wall-clock reads, no bare
   `random` — RNG is passed in, seeded.
5. **Bounded memory.** Nothing grows without a cap. The old cog's `history` string
   is the anti-pattern this module exists to correct.
6. **`backend=null` always works.** Every LLM task has a deterministic fallback,
   and the null suite is part of the test run.
7. **Mechanics before prose.** Post the outcome, then stream narration.
8. **No inference leaves hardware we own.** Ollama only. No hosted API, no
   third-party provider, no "just for the free tier", no API-key field. If you
   find yourself adding an HTTP client for a model vendor, stop.
9. **Stay separate.** Tabletop has its own strings (`lang_dnd.py`), parameters
   (`helpers/dnd/parameters.py`), storage, panel pages and dashboard section. Do
   not add a `dnd_*` key to the shared parameter registry, a `TT_*` string to
   `lang.py`, or a tabletop cog to `cog_categories.CATEGORIES`. The full map,
   including what *is* deliberately shared and why, is `15-SEPARATION.md`.
10. **Deterministic first.** If it can be computed in Python, it is computed in
   Python. A model is called only where prose quality is itself the product.
   Adding a call site means adding a row to the table in `08-LLM-LAYER.md` §5
   naming the deterministic alternative and why it is insufficient. "It would be
   nicer" is not a reason. This is the invariant that keeps the product from
   decaying into an LLM wrapper one convenient shortcut at a time.

## 5. Tests that must exist

- **Import-boundary test** — greps imports to enforce invariant 1. Cheap, catches
  the failure that would otherwise be invisible until it matters.
- **Command-name collision test** (`tests/test_command_names.py`) — top-level
  command names must be unique across *all* cogs. Discord raises
  `CommandAlreadyRegistered` at load time, so one duplicate takes a whole cog
  offline, and a cog loaded in isolation will never show it. Run it before any
  push that adds a command.
- **Null-backend suite** — the full turn loop with no model. Enforces invariant 6.
- **Golden replay** — a recorded event log replays to an identical state hash.
- **Tenant isolation** — two campaigns, same entity names, every repository method
  checked for leakage.
- **Property tests** — memory ≤ budget; salience monotonic in reinforcement;
  utility finite; decay never raises a fidelity.

## 6. Integration checklist for anything new

Every feature added to this module should ask:

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
