# Trial ranks — handoff

State of the trial-ranking system as of 27 Aug 2026, branch `refactor`.
Written for whoever (or whatever) picks this up next.

---

## What it does

Clears and achievements are worth points. Points earn a rank role. **Enrolment
is the only switch**: the automation touches nobody who has not opted in, and
there is deliberately no master on/off flag above that list — one existed, it
silently swallowed every role change for a day, and it was removed rather than
patched.

Two moments trigger a recalculation, and only two:

1. a scoring role changes on an enrolled member (`on_member_update`);
2. that member asks where they stand (`/rank`, or the announcement button).

**The panel can enrol the whole server at once** ("Turn trial ranks on for
everyone", under Users). It counts first and shows the numbers in a confirmation
before it touches anybody: how many have never answered, how many said no and
will be enrolled anyway, and how many sit above the bot and so can be enrolled
but not ranked. It is the only control that overrides a recorded "no", which is
why the confirmation names that count instead of asking "are you sure?". The
pass stops at `MAX_EDITS` role edits and leaves the people it never reached
*un-enrolled*, so pressing it again continues rather than leaving somebody
enrolled with a card promising a rank they were never given.

**New members are enrolled on join**, without being asked. The consent flow was
written for people who already had a rank set by hand; somebody joining today
has no such history. `on_member_join` never overwrites an existing enrolment
row, so anyone who left after saying no keeps that answer on return, and it
stays out of guilds with no ladder configured.

There is **no periodic sweep**. An hourly pass spent nearly all its work
confirming nothing had changed and left answers up to an hour stale when it
hadn't. `run_for_guild` still exists for the panel's **Recalculate now**.

---

## Files

| Path | Role |
|---|---|
| `helpers/trial_ranks.py` | Scoring, ranks, trials, interest, records, presets, the manager |
| `helpers/trial_image.py` | The shareable PNG chart |
| `helpers/share_tokens.py` | Capability links (hashed at rest) |
| `helpers/health.py` | Gateway sampling behind the dashboard status board |
| `cogs/trial_ranks.py` | Runtime: apply, listener, `/rank`, `/interest`, consent flow, the sweep |
| `web/routes.py` | Panel pages + the public board |
| `web/static/board.js` | The public leaderboard's behaviour |
| `web/static/panel.js` | Panel behaviour (trials, strings, dashboard) |

## Collections

```
TrialRanks         {_id: guild_id, points, ranks, trials, exclusive,
                    announce_channel_id, announce_message_id, log_channel_id,
                    board_url}
TrialStandings     {guild_id, user_id, score, rank}
TrialEnrollment    {guild_id, user_id, state, name, source, *_at}
TrialRankImages    {guild_id, role_id, data, content_type}
TrialInterest      {guild_id, user_id, name, role_ids, at}   TTL 60d
TrialPresets       {guild_id, name, points, ranks, trials, author_id}
TrialWorldRecords  {guild_id, user_id, name, current, former}
ShareTokens        {guild_id, kind, token_hash, expires_at}
BotHealth          {at, status, latency_ms, guilds, members}  TTL 90d
```

---

## Decisions worth not re-litigating

**Ranks are free-form.** A rank is a role + a threshold + optional description
and badge. Renaming the role renames the rank everywhere. The old fixed
`Casual…Myth` ladder is gone; legacy docs migrate on read in `_migrate_ranks`.

**Nothing reads the divider roles any more.** Scoring is keyed by role id, and
the editor is built from the trials mapping plus a standalone list. `sections()`
survives only for "Suggest from role names" at first setup. Moving a divider
must not change a single point — there is a test for exactly that.

**Points live on the trial slots.** Mapping a clear and pricing it are one job
in one place. The score box follows the picker, so re-mapping a slot can never
silently reprice the role that used to be there.

**World records are a person's, not a role's.** 15 points current, 5 former,
both permanent. Added in `apply()` and in the card so the card and the granted
role always agree. It changes *how many* next-step suggestions are listed
(smaller gap), never *which* — there is no WR-to-trial association anywhere.

**Prog interest is trial-only and self-clearing.** Achievements are excluded
(you don't form a group to earn one). Interest is pruned on every real
recalculation via `stale_interest`, using the same stronger-implies-weaker rule
as scoring. Pruning lives inside `apply()` and is skipped when `edit=False`, so
a preview cannot edit anyone's data.

**Failures are never swallowed.** Refused role edits report the reason (role
above the bot, missing permission, member outranks the bot, server owner). The
rule that actually bites: **a member whose top role is at or above the bot's
cannot have *any* role changed**, however low the target role sits.

**The public board's opened row is the `/rank` card.** Same call
(`missing_for_next`), so the two can never tell different stories: rung and star
row, the rank's description, the bar with `score → threshold`, what is still
needed for the next rung, the next steps with their marginal gains, then the
clears the total came from. Adding a field to the card means adding it in both
places or it will drift.

**The card shows where they stand, worked out live.** `standing_of` scores
every enrolled member on the spot rather than reading `TrialStandings`: the
stored row is only as fresh as that person's last recalculation, and "you are 4
behind Fox" has to be right about Fox too. Ties break on name, the same way the
board numbers its rows, so both call the same person the same number.

**The place goes on the rank line, the neighbours go in a field.** `#4 of 42`
sits next to the role mention at the top, because it is the first thing anyone
looks for. The two people ahead and the two behind live further down under
"Where you stand". Both gaps are magnitudes, never signed: which side of the
"you" row they are on already carries the direction, and a signed gap in a
minus template is how you get `(+-2)`.

**The board link is stored, not derived.** Only the token's hash is kept, so
nothing can rebuild the URL. `board_url` on the guild config holds it, filled in
automatically the moment a link is issued and cleared when one is revoked; the
panel also takes a paste, which is the only way to attach a link issued before
this existed. The consequence worth knowing: that row holds a working
capability link in plaintext, which the `ShareTokens` collection deliberately
does not. Validation refuses anything not containing `/r/<guild id>/`, because
the bot posts this link to members.

**A Discord embed footer is plain text.** No markdown, no links. The board link
therefore sits on the last line of the body, directly above the footer, which
is where it reads as one anyway. `set_footer` is unchanged.

**Strings resolve through a chain.** `bot.lang.get(key, guild=, locale=)` walks
guild+locale → guild+default → global+locale → global+default → `lang.py`.
`lang.KEY` still works and means the global/default layer. Per-guild and
per-locale storage exists; **the UI for both is not built yet**.

---

## Live state (ESO for Dodos, 783594413632520203)

60 priced roles · 14 trials · 7 ranks · 5 enrolled (Mido, Fox, Rosa, Tomtem,
Mr. Tea) · announcement posted to the moderators channel · public board link
issued.

---

## Not done / next up

1. **Strings: locales and per-guild wording.** Resolver and storage are ready;
   needs a locale picker and a Strings panel on the guild page. Migrating cogs
   off bare `lang.KEY` is incremental and optional.
2. **The "Clears" menu entry** — its setup moved into Trials Setup and the empty
   panel was removed. Nik was going to say what that entry should become.
3. **Per-embed capability tokens** for a "see the full rankings" button.
   `share_tokens.issue(guild, kind=KIND_USER, user_id=…, ttl_days=…)` already
   does the work; nothing in the module needs changing.
4. **Public leaderboard is enrolled-only by design.** Widening it to everyone
   publishes standings for people who never opted in — treat as a decision, not
   a tweak.
5. **`/interest` is visible to everyone.** It lists member names; the panel can
   set it to admin-level in one click if that becomes unwanted.
6. **Incident records** for the dashboard status board ("Related incidents" on
   the reference status page) — nothing writes them.

---

## Gotchas

- **The `enabled` flag is gone.** If you find a reference, it is stale.
- **Preset links and share links are shown once.** Only hashes are stored.
- **`$set` and `$setOnInsert` must never name the same field** — Mongo rejects
  it as a path conflict. This caused a 500 on preset overwrite; the test stub
  now raises the way Mongo does.
- **Test stubs must model the real thing.** Several bugs survived because a fake
  collection was more forgiving than Mongo, or a fake `Guild` lacked `.me`.
- **Check the database before theorising.** Two wrong diagnoses in a row were
  settled in one query.
- **Nine methods were pasted twice in `cogs/trial_ranks.py`** and sat that way
  for weeks. The later copy wins, so editing the earlier one changed nothing.
  Removed; `test_join` now checks every method in the class rather than a
  hand-written list of four, which is why it went unnoticed.
- Nik's style: no em dashes in user-facing copy, no filler, plain sentences.

## Testing

```bash
py -3 tests/run_tests.py        # 40 cases, no dependencies
py -3 tests/run_tests.py -v     # with what each one checked
```

See `tests/README.md`. The cases came out of this build and each one protects
something that actually broke: divider independence, the role-hierarchy
refusals, the preset write paths, the capability-token properties, and the
string resolver fallback chain. `test_massenrol` covers the sweep: that
counting enrols nobody, that "asked but never answered" is not a decline, that
an overridden decline is reported, and that hitting the edit cap leaves the
remainder un-enrolled rather than enrolled-but-unranked.
