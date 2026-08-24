# Handoff — the bot

**This file is about DodoTheBot as a whole.** The tabletop engine has its own,
and it is much longer: `docs/dnd/HANDOFF.md`. If you are picking up simulation
work, start there and come back here for the things that are true of the whole
repo — the shell, the deploy, the command cap, the test runners.

Split out of the tabletop handoff, which had grown to carry both and was
becoming the only place several repo-wide traps were written down. A trap that
lives in one subsystem's document is a trap the next person meets somewhere else.

---

## 1. What this is

A Discord bot for one community, run on a small VPS, with a web control panel.
**34 top-level cogs** plus the `cogs/dnd/` package, `helpers/` for the shared
machinery, `web/` for the panel.

It is not a framework and does not try to be reusable. It is a specific bot for
a specific server, and most decisions in it only make sense in that light.

## 2. The environment, and the four traps

These have each cost real time, twice in production.

| Trap | What happens | The rule |
| --- | --- | --- |
| **`python` is not `py`** on this machine | `ModuleNotFoundError: discord` | Always `py` |
| **Console encoding** | Suites die on clock glyphs and arrows rather than failing honestly | Prefix runs with `PYTHONIOENCODING=utf-8` |
| **Bash heredocs mangle this codebase's content** | A `\n` inside a patch script's replacement became a real newline, split a string literal, and **took the whole tabletop cog offline in production** | Use the **Edit tool** for any replacement containing an escape, a quote or a `"""`. Write patch scripts to a *file* and run them with `py` — never through a heredoc |
| **Discord caps an application at 100 top-level slash commands** | `CommandLimitReached` at load, and the **whole cog** goes offline | `tests/test_command_names.py` fails at 96. **Group new commands** — a group costs one slot however many subcommands it holds |

Two more that are not environment but behave like it:

- **A cog that loads fine in isolation can still fail in production.** Both
  outages this project has had were invisible to a single-cog smoke test.
- **Scope your `git add`.** A blanket `git add -A` once swept an unrelated
  in-progress edit into a deploy.

## 3. Deploying

**A push to `refactor` deploys to production in about 14 seconds.** There is no
staging. `.github/workflows/deploy.yml` SSHes to the VPS, hard-resets to
`origin/refactor`, syncs dependencies with `uv`, restarts `dodo`, and checks the
service came back.

- Host: `root@45.141.76.118`, service `dodo`, checkout at `/root/DodoTheBot`
- Panel: `https://dodobot.nextstep.team` (bound to `127.0.0.1:8080` behind a proxy)

`systemctl is-active dodo` returning `active` proves the **process** started. It
proves nothing about whether a cog loaded. After any push that adds or renames a
command:

```bash
ssh -i ~/.ssh/id_dodo_vps root@45.141.76.118 "journalctl -u dodo --since '-3min' --no-pager | grep -iE \"loaded cog|failed to load|Traceback\""
```

And to confirm *which* commit is live:

```bash
ssh -i ~/.ssh/id_dodo_vps root@45.141.76.118 "cd /root/DodoTheBot && git log --oneline -1"
```

## 4. Tests

Two separate worlds, for historical reasons that are fine:

**The bot's own suite** — `tests/cases/`, 34 scripts, stdlib only, run in
separate processes so one crash cannot take the rest with it:

```bash
py tests/run_tests.py
```

`tests/README.md` explains the shape and has a table of what each case protects.
`tests/test_all.py` exposes the same cases to pytest for anyone who has it.

**The tabletop suites** — six files run individually, listed in
`docs/dnd/HANDOFF.md` §2. They use `tests/fake_mongo.py` rather than the real
database.

**`tests/test_command_names.py` is the one that belongs to everybody.** It is
deliberately *static* — it `ast.parse`s the repo and imports nothing — and its
first check is simply *does every Python file in the project parse*. That check
exists because `lang_dnd.py` once shipped unparseable and nothing asked.

## 5. What is where

```
bot.py                  entry point, cog loading
lang.py                 the bot's strings          (lang_dnd.py is separate)
cogs/                   34 cogs, one per feature
cogs/dnd/               the tabletop engine — see docs/dnd/HANDOFF.md
helpers/                shared machinery, below
helpers/dnd/            tabletop's own, deliberately separate
web/                    the control panel; web/routes.py is ~3300 lines
web/dnd/                tabletop's panel pages, kept out of routes.py
docs/                   this file, plus one per subsystem
tests/cases/            the bot's suite
```

The shared machinery worth knowing about before touching anything:

| Module | What it is |
| --- | --- |
| `helpers/visibility.py` + `cog_categories.py` | Per-guild command and cog visibility. A cog can be switched off per server |
| `helpers/panel_access.py` | Panel scopes — `stats` / `full`. Every route is gated |
| `helpers/parameters.py` | The shared per-guild parameter registry. **Tabletop does not use it** |
| `helpers/state_machine.py` | `PersistentFlow` — resumable multi-step flows that survive a restart |
| `helpers/lang_manager.py` | Layered string resolution with a fallback chain |
| `helpers/command_sync.py` | Decides when Discord needs a command re-sync. Its hash once covered only top-level names, so adding a *parameter* never reached Discord |
| `helpers/audit_log.py` | `_record_change` — the panel's audit trail |

## 6. Subsystem docs

Each of these has its own document, and they are the real handoff for that area:

| Area | Document |
| --- | --- |
| **Tabletop / DnD** | `docs/dnd/HANDOFF.md`, plus sixteen design docs in `docs/dnd/` |
| Chat personality | `docs/CHAT_PERSONA.md` |
| Trial ranks | `docs/TRIAL_RANKS_HANDOFF.md` |
| Control panel setup | `docs/CONTROL_PANEL_SETUP.md` |
| Per-server parameters | `docs/PER_SERVER_PARAMETERS.md` |

## 7. Standing rules

These are the owner's, stated more than once, and they apply to the whole repo
rather than to tabletop alone:

- **Everything is a tweakable parameter visible to the bot owner.** No black
  boxes, no baked-in weights. If a number shapes behaviour it gets a control
  with a label, a description and a range — and it goes in a catalogue that can
  be read in one place. Tabletop enforces this with
  `helpers/dnd/catalogue.py` and `tests/test_dnd_catalogue.py`; **the rest of
  the bot has no equivalent yet, and should.**
- **The panel is the configuration surface, not Discord.** Slash commands are
  for playing, not for tuning. Long flat lists in the panel are a defect —
  group them.
- **Ship one complete, checkable thing at a time.** Not a phase, not a batch.
  Then stop, say plainly what to check and how, and wait for confirmation.
- **Verify at the level it will be used.** For anything with a UI that means
  clicking it and reading the browser console *before* reasoning about the
  source. "The tests pass" and "the cog loaded" are not evidence a feature works.
- **Push after every commit.** Commit messages describe the *effect*, not the
  mechanics — see `git log`.
- **Local inference only, if inference ever happens.** Ollama or nothing. No
  hosted API, no third-party model provider, in any tier, for any tenant.

## 8. Keeping this file honest

The same discipline the tabletop handoff learned the hard way:

- **Measure, do not increment.** Any count in this file — cogs, cases, commands
  — is to be re-counted, not adjusted. The tabletop handoff's test count drifted
  forty off by being incremented.
- **Grep for the claim you are invalidating**, not just the sentence you are
  editing.
- **Update it before the session ends**, as part of finishing rather than as an
  afterthought.
