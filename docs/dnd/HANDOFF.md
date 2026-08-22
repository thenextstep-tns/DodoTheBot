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
| P2 | ✅ live | Traits + inheritance, needs, memory that forgets like people do, relationships, NPCs, the entity inspector, **34 tunables in two layers** |
| P3 | next | Decisions, faction clocks, the world tick |

**305 tests** across five suites, all passing:

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
helpers/dnd/mind/       minds: traits, needs, memory, relationships   (pure, seeded)
helpers/dnd/world/      what exists: entity, memory, belief, event    (dataclasses)
helpers/dnd/rules/      dice and rulesets                             (pure, seeded)
helpers/dnd/store/      repositories — every query carries its tenant
```

Two rules hold it together: **the pure layers never do I/O and never read
configuration** (tuning is resolved at the orchestration edge and passed in as
typed dataclasses), and **every repository requires a `Scope`**, so an unscoped
query cannot be written.

## 6. What P3 is

From `12-ROADMAP.md`, with everything it depends on already built:

- **Appraisal and impulses** — `mind/needs.py` already generates impulses;
  P3 consumes them.
- **Utility scoring** — `U = Σ wᵢ · curveᵢ(state)`, softmax selection seeded per
  `(campaign, entity, tick)`, **with the term breakdown stored on the event** so
  the GM can be told *why* an NPC did something. `06-DECISION-ENGINE.md` is the
  spec and it is unchanged.
- **Simulation tiers** — `focus` / `active` / `dormant` are already on `Entity`
  and nothing uses them yet. Dormant entities are extrapolated in closed form;
  `needs.advanced()` is already written that way, so follow its shape.
- **World tick** — a `discord.ext.tasks` loop replacing the manual `/gm advance`,
  which stays as the GM's fast-forward.
- **Faction clocks** — fronts that advance whether or not players engage.
- **Rumour propagation** — beliefs travel the social graph and mutate. The
  belief model already has `mutations` and `shared_with` for exactly this.

Acceptance: leave a campaign alone for a simulated week and have clocks advance,
an NPC pursue a goal, a rumour about a PC reach someone who never met them —
with the tick under 25 ms for 200 active NPCs.

**Everything in P3 must be tunable and must have a panel control.** Expect to add
a Clocks page and a decision-trace view to the entity inspector.

Two slots of the 100-command budget are the safe margin, so P3's commands go
under `/gm` — not new top-level ones.

## 7. Known gaps, honestly

- **`/canon` is empty and stays empty until P4.** Nothing invents facts yet.
- **Nothing narrates.** Every message is mechanical output, by design.
- **The legacy cog is still loaded** as `dnd_legacy`. It goes one release after
  the migration has actually been run (`13-MIGRATION.md` §6).
- **Nothing ever writes  after creation.**  §3
  says temperament shifts on an imprint and drives drift with experience; the
  only trait access in the codebase is a read. The mechanic is specified in
  §3a and unbuilt — an NPC is the person they were rolled as, permanently.
- **Beliefs never decay.** Confidence is set from  and never moves
  again, so a rumour assumed once sits at 0.35 a decade later. Spec is
   §4; both land in P3.
- **Value keywords are English-only** (`mind/memory/values.py`). Fine for now;
  it would need attention before a non-English campaign.
- **`web/routes.py` is ~3300 lines.** Tabletop stays out of it; anything new goes
  in `web/dnd/`.
- **The user has not yet play-tested P1 or P2 in Discord.** The walkthroughs in
  the chat history are the scripts for that; nothing has been confirmed by a
  human at a table.

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
