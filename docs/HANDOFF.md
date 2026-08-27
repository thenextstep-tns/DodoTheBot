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

**The bot's own suite** — one script per case in `tests/cases/`, stdlib only,
run in separate processes so one crash cannot take the rest with it. The runner
prints the count; do not write one down here, it drifts:

```bash
py tests/run_tests.py
```

`tests/README.md` explains the shape and has a table of what each case protects.
`tests/test_all.py` exposes the same cases to pytest for anyone who has it.

**The tabletop suites** — seven files run individually, listed with the exact
command in `docs/dnd/HANDOFF.md` §2. They use `tests/fake_mongo.py` rather than
the real database, so nothing touches production data.

The two do not overlap and neither runs the other. Run **both** before a push
that touches shared machinery — `helpers/`, `web/routes.py`, `lang.py`,
`bot.py` — because the tabletop suites import `helpers/` and `web/` and will
catch a break there that `tests/cases/` does not.

**`tests/test_command_names.py` is the one that belongs to everybody.** It is
deliberately *static* — it `ast.parse`s the repo and imports nothing — and its
first check is simply *does every Python file in the project parse*. That check
exists because `lang_dnd.py` once shipped unparseable and nothing asked.

## 5. What is where

```
bot.py                  entry point, cog loading
lang.py                 the bot's strings          (lang_dnd.py is separate)
config/database.py      87 Mongo collections, one module-level handle each
cogs/                   34 cogs, one per feature
cogs/dnd/               the tabletop engine - see docs/dnd/HANDOFF.md
helpers/                shared machinery
helpers/dnd/            tabletop's own, deliberately separate
web/routes.py           the control panel - ~3,900 lines, and the one file to
                        avoid adding to
web/dnd/                tabletop's panel pages, kept out of routes.py
web/static/panel.css    the panel's whole stylesheet
docs/                   this file, plus one per subsystem
tests/cases/            the bot's suite, one script per case
```

### The four ways a server is configured

These are separate on purpose and are the thing to get right before touching
anything. Putting a setting in the wrong one is the commonest mistake here.

| Store | What it holds | Read via |
| --- | --- | --- |
| `helpers/parameters.py` | **Behaviour tunables** per guild - thresholds, limits, reward sizes, role lists. Typed registry with defaults, backed by `command_params`. Types: int, float, bool, str, choice, role, channel, list_role | `bot.params.get(gid, "key")` |
| `GuildConfigManager` | **Channel and role ids** an admin points at things | per-guild config |
| `helpers/visibility.py` | **Who may see and run what** - per-cog, per-command, per-feature, per-role | `bot.visibility` |
| `helpers/cog_categories.py` | A presentation layer that bulk-toggles the above into named groups | panel only |

Adding a behaviour knob means appending a spec to `PARAMETERS` and reading it in
the cog; the panel renders a typed input for it automatically. **Tabletop does
not use any of this** - it has its own registry, its own parameters, its own
panel section (`15-SEPARATION.md`), and now its own catalogue.

### The cogs

Grouped by what they are rather than alphabetically, because that is how you
find the one you want. Line counts are a rough guide to where the weight is.

**Games and economy** - most of the bot by volume:

| Cog | Lines | What it is |
| --- | --- | --- |
| `pumpkin` | 1529 | The pumpkin economy plus a full team deathmatch minigame. The largest cog in the bot |
| `racing` | 744 | Skeevaton mouse racing: registration, classes, races, betting |
| `pet` | 413 | Cat/dog/waifu pets claimed from image APIs |
| `dnd_legacy` | 372 | **Superseded** by `cogs/dnd/`. Goes one release after the migration is run (`13-MIGRATION.md` §6) |
| `cheese` | 360 | Co-op push-your-luck cheese stretching |
| `fishing` | 327 | Fish with an eligible cat |
| `quote` | 309 | Guess the Quote, built on the message archive |
| `parse_tournament` | 247 | Reaction-based DPS parse championship |
| `gilane` | 234 | A 20-second reaction window event |
| `fun`, `pp`, `throw`, `deathroll`, `fighting_and_gym`, `parsing`, `racestats`, `economy` | 89-188 | Novelty commands, joke meters, duels, gym sessions, leaderboards, the Dodo Bank |

**Community and moderation:**

| Cog | Lines | What it is |
| --- | --- | --- |
| `trial_ranks` | 1279 | Clears and achievements into points into a rank role. Has its own doc |
| `log` | 1033 | Server audit logger, per-guild log channels |
| `raid_setups` | 506 | Imports a raid gear plan from a Google Sheet |
| `moderation` | 345 | Kick/ban/nick/purge/pin, escalating warnings |
| `tribes` | 303 | "Who gets this role", as a rule built on the panel |
| `spam` | 262 | Auto-bans posting too fast or across too many channels |
| `scheduler` | 241 | Walks a raid leader through scheduling a trial |
| `general`, `seasonal`, `pat`, `event_tracker`, `server_config` | 71-217 | Bot info and reminders, thread-based seasonal events, screenshot decoding, behaviour logging, per-guild config |

**Dodo itself, and infrastructure:**

| Cog | Lines | What it is |
| --- | --- | --- |
| `chat` | 569 | Dodo talking, and mostly Dodo **not** talking. Has its own doc |
| `owner` | 255 | Owner-only bot management |
| `event_actions` | 155 | The "do this when that happens" runtime |
| `talkengine` | 84 | Markov chain over a user's messages |
| `control_panel` | 60 | Runs the aiohttp panel **inside the bot process** |

### The panel

One aiohttp app, served from inside the bot, at `dodobot.nextstep.team`. Pages:

```
/guild/{gid}            overview        /guild/{gid}/tribes     role rules
/guild/{gid}/stats      statistics      /guild/{gid}/trials     trial ranks
/guild/{gid}/settings   cogs & params   /guild/{gid}/tabletop   the engine
/guild/{gid}/events     event rules     /lang                   editable strings
/guild/{gid}/log        audit trail     /r/{gid}/{token}        capability link
```

**`web/routes.py` is ~3,900 lines and should not grow.** New surfaces get their
own package the way `web/dnd/` did.

Two panel rules worth knowing before writing any HTML:

- **Discord ids are 64-bit.** Interpolated as a bare JavaScript numeric literal,
  `806174526383325225` parses as `...200` and every request 404s. Interpolate
  snowflakes as **strings**. This has caused an outage.
- **Reuse the stylesheet.** `web/static/panel.css` already has the menu
  (`sidenavitem`), the settings row (`paramrow`/`tunerow`/`tunelabel`), chips,
  tables and panels. Inventing class names produces an unstyled page, which is
  exactly what happened to the tabletop parameters page. `tests/test_dnd_panel.py`
  now fails on any class that is neither styled nor selected by a script -
  **the rest of the panel has no such guard yet.**

### The shared machinery

| Module | What it is |
| --- | --- |
| `helpers/visibility.py` | Per-guild command and cog visibility. A cog can be off per server |
| `helpers/command_sync.py` | Decides when Discord needs a re-sync. Its hash once covered only top-level names, so adding a **parameter** never reached Discord |
| `helpers/panel_access.py` | Panel scopes - `stats` / `full`. Every route is gated |
| `helpers/state_machine.py` | `PersistentFlow` - multi-step flows that survive a restart |
| `helpers/lang_manager.py` | Layered string resolution with a fallback chain |
| `helpers/audit_log.py` | `_record_change` - the panel's audit trail. Call it from any endpoint that changes configuration |
| `helpers/event_log.py` | Reads the `Logs` collection the log cog writes, for the panel's **Server log** page. Read-only: the cog still owns the writing |
| `helpers/share_tokens.py` | Capability links: a URL that is itself the credential |
| `helpers/events.py` | "When X happens, post Y in Z" |
| `helpers/sheets.py` | Google Sheets ingestion for raid setups |
| `helpers/singleton.py` | Single-instance guard - two bots on one token is a bad afternoon |
| `helpers/scrap.py` | The cat-fight engine (**design in progress**, no command yet). Pure - no Discord, no Mongo - so the panel sandbox and the eventual command run the same code |

### Adding a command, end to end

1. Write it in the cog. **Group it** if the cog already has a group - the 100
   top-level cap is a shared budget across the whole bot (§2).
2. `py tests/test_command_names.py` - uniqueness and the cap.
3. Needs a knob? `helpers/parameters.py`, not a constant in the cog.
4. Says anything to a user? A string in `lang.py` (`lang_dnd.py` for tabletop).
5. Changes configuration? `_record_change` so it lands in the audit trail.
6. Push, then **check the journal** (§3) - a cog that loads in isolation can
   still fail in production.

## 6. Subsystem docs

Each of these is the real handoff for its area:

| Area | Document |
| --- | --- |
| **Tabletop / DnD** | `docs/dnd/HANDOFF.md`, plus sixteen design docs in `docs/dnd/` |
| Chat personality | `docs/CHAT_PERSONA.md` |
| Trial ranks | `docs/TRIAL_RANKS_HANDOFF.md` |
| Control panel setup | `docs/CONTROL_PANEL_SETUP.md` |
| Per-server parameters | `docs/PER_SERVER_PARAMETERS.md` |
| The test suite | `tests/README.md` - has a table of what each case protects |
| Cat fights (in design) | `docs/SCRAP_DESIGN.md` |

**What has no document:** the games and economy cogs, which are most of the bot
by volume. `pumpkin` alone is 1,529 lines with no design note anywhere. If you
are about to do substantial work in one of them, writing the doc first is
probably the cheaper path.

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

---

## The two logs

They answer different questions and live on different pages, which is why there
are two.

| Page | What it shows | Written by | Read by |
| --- | --- | --- | --- |
| **📜 Server log** (`/guild/<id>/serverlog`) | What Discord did: role changes, message edits and deletions, threads, joins, bans, invites, voice | `cogs/log.py` into `Logs` | `helpers/event_log.py` |
| **📝 Change log** (`/guild/<id>/log`) | What this panel did: every setting anybody changed, with its old value | `_record_change` into `ConfigAudit` | `helpers/audit_log.py` |

Things worth knowing before touching the server log:

- **The events were always being stored.** `send_log` has written every event to
  `Logs` since long before anything could read them. The page is a reader, not a
  new pipeline, and it shows history going back as far as the collection does.
- **Ids are extracted from the rendered text**, in `send_log`, via
  `event_log.subjects`. There are thirty-odd listeners and one `send_log`, so
  this is the only version of it that cannot be half-done. It works because
  every `LOG_*` template in `lang.py` opens with the subject's mention.
- **Rows written before that extraction have no `user_ids`.** Every id filter is
  an `$or`: the indexed field, or a description regex for rows that never had
  the field. Drop the `$exists: False` guard and new rows match twice while old
  ones stop matching at all.
- **Date filters compare the `timestamp` string**, which is ISO-8601 UTC on
  every row ever written, so a lexicographic compare is a chronological one.
  Ordering is by `_id`, whose leading bytes are the insertion time.
- **Escape before substituting, never after.** Every deleted message on the
  server passes through `_discord_markup`. It escapes first and then matches
  `&lt;@123&gt;`, so there is no path from something typed in Discord to markup
  on an admin's page. There is a test that tries.
- **Subject and actor are different questions and different filters.** "Done
  to" matches `subject_id`, "Done by" matches `actor_id`. One combined person
  filter looked reasonable and was not: picking a moderator returned every role
  change they had ever handed out to somebody else.
- **The actor is the mention that follows the word "by".** Every `LOG_*`
  template writes it that way, whether the word comes from the template ("was
  kicked by {actor}") or from the listener (`f" by {entry.user.mention}"`); the
  subject is then the first user named who is not the actor. That is a
  dependency on wording, so `test_serverlog` formats twelve real templates and
  fails if any of them stops saying it. The same rule is what the fallback
  regexes use, so old rows answer the two questions the same way.
- **Filter names must not collide.** "Done to" and the date "to" were briefly
  both `to`, which a form resolves by silently discarding one. The person
  filters are `subject` and `actor`; the dates keep `from` and `to`. There is a
  test asserting every filter has its own name.
- **The person and channel filters are built from the guild, not from the log.**
  They were built by aggregating the extracted ids once, which was wrong in a
  way that looked like working code: a server of hundreds offered the two people
  who had happened to trigger an event since the extraction shipped. Ids found
  in the log and no longer in the guild are appended as "left the server" or
  "deleted or archived", because that is half of what the page is for.
- **Both are multi-choice.** `.mspick` in `panel.js` is the widget, sourced from
  a JSON blob in the page so the same control serves people and channels. The
  hidden field carries a comma separated list and is the only thing that
  submits; a half-typed name is never a choice. Several ids mean *any* of them.
  `tests/render_serverlog.py` exists to click it, since nothing in the suite
  runs a page's JavaScript.
- **Nothing is recorded with the feature off or no log channel set.** Both
  produce an empty page, so the page says which one is true rather than leaving
  somebody to find it in the source.
