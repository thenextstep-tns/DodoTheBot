# DodoLand — handoff

The socialite tribe's town map. State as of 28 Aug 2026, branch `refactor`.

Trial ranks are the other half of this and have their own doc
(`docs/TRIAL_RANKS_HANDOFF.md`). Read it: DodoLand borrows its shape
deliberately and hangs its visual prestige off its ladder.

---

## 1. The one idea

**A town is a profile, not a ladder.** A socialite's reward is being seen by
other people, so everything optimises for the glance, the screenshot and the
neighbour, never for a number going up in private.

Three things follow, and every module here obeys them:

**Reach, not volume.** What is counted is how many *different* people you
reached and who reached back. Volume metrics crown whoever talks most, and that
is not what a socialite is. Message count is present, weighted at 1, so a quiet
town is not a dead one; it is not a way to earn.

**Every social act is capped per partner per day.** Two friends boosting each
other all evening is the obvious exploit and the only defence that works is
refusing to score the repetition. Past the cap the act still happens and simply
does not score. You cannot inflate a score without involving more people, which
is precisely the behaviour the tribe exists to reward.

**Nothing is ever taken away.** There is no decay anywhere in this package, and
adding one would be a design reversal rather than a tweak. Dormancy is a *view*:
a town is drawn lit or dim from its recent window. A fortnight away costs
brightness and never progress. The people this tribe is courting are exactly the
people a decay mechanic drives off.

## 2. The two axes

This is the decision that separates DodoLand from the document it came from, and
it is worth not re-litigating.

| Axis | Comes from | Who can get it |
|---|---|---|
| **Structure tier** — what you built | DodoLand standing (messages, mentions, per channel) | Anyone, by being present and sociable |
| **Flourish** — what you are known for | Trial rank (`TrialStandings`, the existing ladder) | Only the trial ladder, and it cannot be ground for |

So a chatty non-raider and a Godslayer can both own a Titan's Bastion, and only
one of them has it wreathed in fire. Nobody is locked out of a *building* for
not raiding, and the raiders get a visual signature nobody can farm.

The higher the rank, the more impressive the effect. Flourish is cosmetic first;
rank may also unlock **social function** (hosting beacons, extra decor slots,
naming rights on a road or region). Candidates only, none built. The constraint
they must respect: rank grants *social* capability, never economic advantage. A
rank that multiplies standing collapses the two axes back into one.

## 3. What is built (P0, live)

The listener and its store. No commands, no panel, no map: it ships, it gathers,
and it shows nobody anything. That order is deliberate, because data has a lead
time nothing else does.

```
helpers/dodoland/metrics.py     what counts, and what it is worth
helpers/dodoland/parameters.py  own registry, own collection, knobs generated
helpers/dodoland/intake.py      what a message is worth. The one place that decides
helpers/dodoland/voice.py       voice session bookkeeping, clock-testable, no Discord types
helpers/dodoland/invites.py     who brought whom in, and when to refuse to say
helpers/dodoland/store.py       the two collections, and the only reads of them
cogs/dodoland.py                the listeners
tests/cases/test_dodoland.py    scoping, caps, acts-vs-scored, voice overlap, invites
```

**17 metrics, 75 parameters, 15 buildings.** Three metrics are backfillable
(`message`, `mention_given`, `mention_received`); the rest count forward only.

### Collections

```
DodoLandActivity  {guild_id, user_id, day, acts, scored, channels}
DodoLandPairs     {guild_id, day, a, b, acts, n}      a < b, undirected
DodoLandParams    {guild_id, key, value}
```

`acts` is what happened, `scored` is what counted after the caps. **Both are
kept.** A cap that silently eats data reads as a bug to the person it happens
to, and the panel can say "200 mentions, 80 scored" instead of shrugging.

`channels` holds *scored* counts split by channel. That is what makes a building
definable as "these channels, these metrics" later without a second pass over
anything, and it is why the split exists before anything reads it.

`DodoLandPairs` does double duty on purpose: it enforces the per-partner caps
**and** it is the relation graph the map will place neighbours from. The
anti-farm data and the fun data are the same data, so neither can rot without
the other noticing.

### Metrics

**Backfillable** (`message`, `mention_given`, `mention_received`) come out of
`Messages with Channels` (author, channel, guild, and raw text that still
carries its `<@id>`). That is why they were built first: DodoLand can launch
with towns made of the server's real history rather than an empty continent
nobody opens twice. The archive is **306,927 messages**.

**Forward-only** is everything else, because nothing ever stored an image, a
reply target, a thread parent, a voice session, an RSVP or an invite use:
`image`, `reply_given/received`, `thread_start`,
`thread_reply_given/received`, `voice_minute`, `voice_together`,
`event_hosted`, `event_rsvp`, `event_interest_received`, `newcomer_welcomed`,
`member_recruited`.

Every intent these need is already on: `voice_states`,
`guild_scheduled_events` and `invites` come with `Intents.default()`, and
`members` + `message_content` are enabled explicitly in `_build_intents()`.

Reactions remain deliberately absent, and will arrive as entries in `METRICS`
and nothing else.

### Rules specific to the forward-only ones

- **Voice alone is worth nothing**, however long it lasts. Minutes credited are
  the longest stretch spent *with somebody*, and co-presence is accumulated on
  both sides so the person who stays last is not credited for the empty room.
  This was a real bug, caught by the test that asserts both sides agree.
- **Sessions live in memory** and are lost on restart. Persisting them would
  mean a write per voice state change for a metric worth one point a minute; a
  restart costs everyone the tail of their current call and nothing else.
- **An unattributed join beats a misattributed one.** `member_recruited` is the
  most heavily weighted act here, so a tie between two invites, a vanity URL, a
  missing Manage Guild permission or a self-invite all credit *nobody*.
- **Welcoming scores once per newcomer**, not once per mechanism: reaching the
  same new person by mention and reply in one message is one welcome.

### Every metric has a complete setup

Four generated knobs each: **weight**, **daily cap**, **per-partner cap**
(social only) and **channels it counts in** (empty = wherever DodoLand tracks).
`parameters.metric_setup()` resolves all of them in one call, so the panel, the
scorer and any future surface cannot disagree about a metric's configuration.

### The rules worth knowing

- **Mentions are parsed from raw text, not `Message.mentions`.** The archive only
  stored text, so text is the common denominator. Using the resolved list live
  and a regex in the backfill is exactly the silent divergence `intake.py`
  exists to prevent.
- **Role pings reach nobody.** `<@&id>` and `@everyone` are excluded. If they
  scored, one ping of @Members would outweigh a year of conversation.
- **A thread is charged to its parent channel, but a forum post is charged to
  itself.** A thread in an ordinary channel is a conversation inside it, and
  charging it elsewhere would make building definitions go stale as fast as
  people start conversations. A forum is a container of separate rooms rather
  than a room, so collapsing its posts destroyed the distinction the map exists
  to show. See §4c.
- **Length is measured on raw text**, so a message that is only a ping is not a
  free point.
- **Failures in the listener are logged, never raised.** It runs inside
  `on_message` for every message on the server. A Mongo hiccup must cost a
  point, never a conversation.

### Multiserver

Every document carries `guild_id` and `store.py` **raises** on an unscoped read
rather than returning everything. There is no code path that reads across
guilds. Continents do not join up, and nothing publishes which other servers a
person is in — that last one is a privacy decision, not an unbuilt feature.

### Parameters

`helpers/dodoland/parameters.py`, own collection, rendered on DodoLand's own
page (never among the general cog settings). The per-metric knobs are
**generated** from `METRICS`: weight, daily cap, and per-partner cap for social
acts. A metric cannot be added without its knobs appearing, because there is no
second place to forget to add them. The corollary is enforced by the same
mechanism: nothing is listed in `METRICS` until something counts it, since a
knob that changes nothing is worse than a missing one.

## 4. P1, the panel (built)

`/guild/{gid}/dodoland`, admin-scoped, in `web/dodoland/` (its own package, so
`web/routes.py` does not grow). Five sections behind the shared side menu:

| Section | What it is |
|---|---|
| **Preview** | Everybody's town power, place, per-building tier and flourish, live from real data. Visible **only** here |
| **Buildings** | Each building, the channels that feed it and their weights, its own metric emphasis, and its tiers with what each currently costs |
| **What counts** | All 16 metrics, each with its four knobs, editable |
| **The map** | Upload the base image, see who has settled |
| **Settings** | Intake and window tunables |

`helpers/dodoland/buildings.py` holds the per-guild building definitions and
their validation; `helpers/dodoland/standing.py` does the scoring. Neither
writes anything a player sees.

### Thresholds are derived

A tier carries a **percentile** of the server's own live distribution plus a
small absolute **floor**, and the effective threshold is whichever is higher.
"Top 5%" means the same thing on day one and in three years, at 60 members and
at 600, so nothing needs re-tuning and no tier is ever dead. The floor stops a
top tier being cheap while only four people have scored at all. Thresholds are
forced non-decreasing, or a floor could make an early rung harder than a later
one. The panel shows the percentile, the floor, the live value and which of them
decided, because a threshold you cannot watch resolve is the black box this
whole design exists to avoid.

### Flourish, and the two axes

`helpers/dodoland/flourish.py`. Seven levels, spread across whatever rungs the
trial ladder actually has, so renaming or adding a rank redistributes them and
never breaks a lookup. Nothing is hardcoded to a rank name.

**`standing.py` contains no reference to flourish, and there is a test that
fails if it ever does.** Rank buys visual effect and never a tier. That is what
keeps every building reachable by anyone through ordinary sociable activity
while the scarce thing stays unfarmable and free to grant.

### Isolation, enforced by test

`tests/cases/test_dodoland_page.py` fails if any file under `helpers/dodoland/`,
`web/dodoland/` or `cogs/dodoland.py` imports the tabletop engine, and if any of
them writes to trial ranks. **Trial ranks is the only thing DodoLand reads from
outside itself, and it is read-only.** The dependency is one-directional so the
ladder never acquires a consumer that can change its data.

Flourish reads the trial system's *stored* standings, so a person's glow is as
fresh as their last recalculation. That is deliberate: computing live would mean
reaching into the trial cog's scoring path.

## 4a. P2, the map (built)

The world is an **image an admin uploads**, not one the bot generates. That
decision removed the vector editor, the procedural coastlines and the elevation
polygons from the build entirely, and it is why there is a handcrafted world at
all rather than one permanently scheduled.

Positions are **percentages of the image**, never pixels, so replacing the map
with a redrawn one of another size does not move a single town.

### Placement is graph-driven, and that is the whole point

Letting people click an empty coordinate is still what settling does. But on a
server this size an empty continent stays empty: towns land far apart, nobody is
anybody's neighbour, and every mechanic that depends on adjacency never fires.
The document this replaces made it worse by growing the canvas with the
population, pinning density at "too sparse" permanently.

So an unsettled town is **suggested beside the people its owner actually talks
to**, from the pair rows the listener already writes. Clusters on the map are
friend groups, and whoever sits between two clusters is visibly the person who
bridges them. A suggestion is never binding: anybody who settles keeps that spot
and the suggestion only fills in for people who have not chosen.

`helpers/dodoland/mapview.py` is pure (coordinates in, coordinates out, no
Discord and no Mongo), so placement is tested against a known graph rather than
eyeballed on a live server.

### Drawing

- **Size is on a square-root scale.** Linear makes the busiest town swallow the
  map; the root keeps a newcomer visible beside somebody with a year's head
  start, which matters for a map meant to invite people in.
- **Flourish is a CSS class per level**, so effects live in the stylesheet and a
  town with no rank costs nothing to render. Levels 5 and 6 animate, and the
  animation is dropped under `prefers-reduced-motion`: forty animated towns is a
  phone's whole frame budget.
- **A quiet town is dim and loses nothing.** There is a test that a dim town
  still has all its points, so no decay can be introduced by accident later.
- Towns draw weakest first, so the biggest are not buried under the smallest.

### Rebuilding history from the archive

`helpers/dodoland/backfill.py`, driven from the panel with a preview that writes
nothing. Three properties, each of which would fail silently, each asserted:

1. **A rebuilt day is worth what a live day is worth.** Both go through
   `intake.acts_from_message` and cap through `store.allowance`, which exists
   for exactly this reason. The test replays the same messages down both paths
   and demands the totals, channel splits and relation graph all match.
2. **It is repeatable.** In-memory aggregation written with `$set`, so twice is
   not double. One act at a time with `$inc` would have been 600,000 round trips
   and a landmine.
3. **It never touches a live day.** It stops strictly before the listener's
   earliest row; a rebuilt day overwriting a real one would be unrecoverable.

Two archive quirks, inherited from `helpers/stats.py`: there is no timestamp
field, so the day comes from the ObjectId's generation time; and older rows
carry no guild, so a guild's history is activity in that guild's channels.

### The order to switch this on

Placement reads the relation graph, which the backfill creates, so:

1. **Attach channels to buildings.** Nothing scores until this is done; the
   defaults ship unattached because a building that silently counts every room
   is one nobody configured.
2. **Preview, then run the backfill.**
3. **Upload the map.** Uploading earlier is fine for checking the image renders,
   but do not settle anybody before step 2 or you are placing towns against a
   layout that is about to change under them.

## 4b. Not built

- **The player-facing surface.** No `/town` command, no public link. Everything
  is still admin-only, which is deliberate: nothing is shown to the people it
  ranks until the numbers are right.
- **The buildings editor is a validated JSON textarea.** It refuses bad input
  rather than half-applying, but it is not the widget the rest of the panel has.
  Worth upgrading once the building shapes settle, since building it twice is
  the waste.
- **Reactions**, and the rank-granted *social functions* (hosting beacons, decor
  slots, naming rights). Candidates only. The constraint they must respect: rank
  grants social capability, never economic advantage, or the two axes collapse
  into one.

## 4c. What went wrong in the first days, and what now guards it

Every one of these was found by the owner on the live panel, not by a test. They
are listed because each is a class of mistake this subsystem is prone to.

**Controls that render but are not wired.** `panel.js` binds parameters and
multiselects only inside a `.cogcard`, and this page has none, so every channel
picker on it was a list of dead divs. Bind on `DOMContentLoaded` (that file
loads *after* an inline script) and bind this page's controls explicitly.

**`bindMultiSelect` never writes its selection back to the DOM.** It keeps the
chosen ids in a closure and hands them to its `save` callback, and nothing else.
Reading `data-selected` off the options gives the server-rendered state forever,
which is why attaching channels to a building silently did nothing. The callback
is the only place the live selection exists; it records it on the element and
the collector reads that. Tested in both directions.

**A save with no feedback is indistinguishable from no save.** `flash()` writes
into `#status` and silently gives up when there is none. The page renders one
and the script creates one if it ever goes missing.

**A panel with no menu entry is unreachable.** The rebuild button sat on the
page, hidden, with nothing able to reveal it. The render test now fails on any
panel without an entry and any entry pointing at nothing.

**A column per building does not scale.** Fifteen buildings became fifteen
columns and pushed the whole page sideways. The preview lists what a town has
actually built, in one cell. Wide content lives in `.dlscroll`.

**The page read the same collection eight times.** Two previews, each separately
counting distinct days, plus the map fetching rows and pairs again: about
100,000 documents per page load once the archive rebuild made the collection
real. Now one read, split by basis in memory. Measured on the live server: 5.6s
of database time became 0.70s, and the Python scoring is 0.06s of it. The
Python was never the cost.

**Excluding bot *authors* is not excluding bots.** People mention the bot
constantly, and each of those was a mention received by it and a mention given
by them, so Dodo sat second on the board with 10,560 town power. Bots are
dropped on both sides of every act, and the rebuild learns which accounts are
bots from the archive so departed ones are caught too.

**A rebuild that only upserts cannot shrink.** When the rules changed the plan
got smaller and the old rows stayed, so the bot kept its town and the preview
counted 1,261 people where the rules produce 671. The rebuild clears every row
it previously wrote before writing the new ones. Live rows carry no `source` and
are never touched.

**A forum is not a room.** It is a container of rooms. Collapsing its posts into
it made the food feed, the safe space and the selfies thread one
indistinguishable channel. A forum post is charged to itself; a thread in an
ordinary text channel is still charged to its parent, or building definitions
would go stale as fast as people start conversations. Only *active* posts can be
listed in the picker: Discord will not hand over archived threads without a
request per forum.

## 4d. Settled decisions

| Question | Answer |
|---|---|
| Bot commands vs ignored bot channels | Commands count **wherever** they happen, ignoring channel rules. Otherwise the Dodo Statue is unbuildable, since bot channels are the first thing anybody ignores |
| Can a room feed two buildings? | **Yes**, at different weights. A busy general channel really is both the tavern and somewhere else. The suggester still gives each room to one building, because a guess that quietly double-counted would be a bad guess |
| Who gets a town? | **Only people with activity.** No empty plots for lurkers |
| Does voice build anything? | **No, not yet.** It counts toward town power only. Voice minutes arrive in far larger numbers than messages and would dominate whichever building they landed in. Attaching them is a one-line change |
| Forum posts | **Their own rooms.** Ordinary threads still collapse into their channel |
| Thresholds | **Derived** from the server's live distribution, with a floor |

## 5. Constraints this has to live inside

- **95 of 100 slash commands are used.** `/town` must be one grouped command.
- **`web/routes.py` is ~4,600 lines and must not grow.** DodoLand gets
  `web/dodoland/`, the way tabletop got `web/dnd/`.
- **The panel runs inside the bot process** on a small VPS. Map rendering is
  precomputed and cached, never per-request.
- **Discord ids are 64-bit.** Interpolate snowflakes into JavaScript as strings
  or every request 404s. This has caused an outage.
- **Reuse `web/static/panel.css`.** Inventing class names produces an unstyled
  page.

## 6. Testing

```bash
py tests/run_tests.py dodoland      # this subsystem
py tests/run_tests.py               # the whole bot suite
```

Five cases, each protecting something that would fail invisibly:

| Case | What it holds down |
|---|---|
| `test_dodoland` | Guild scoping, both caps, acts-vs-scored, voice overlap, invite attribution |
| `test_dodoland_standing` | Validation, derived thresholds, the floor, per-channel scoring |
| `test_dodoland_page` | The page actually renders; **no tabletop import; no write to trial ranks** |
| `test_dodoland_backfill` | A rebuilt day equals a live day; repeatable; never crosses the boundary |
| `test_dodoland_map` | Clusters come out as clusters; nothing off the edge, stacked, or drifting |

Run the tabletop suites too after touching `web/routes.py`, which DodoLand does:

```bash
py tests/test_dnd_panel.py
```

`tests/fake_mongo.py` gained `$or` and `find_one_and_update(upsert=…)` for this,
because the stub was more forgiving than Mongo and the handoff is explicit that
this is how bugs survive.

**Two traps this subsystem hit, both now guarded:**

- The page script is full of literal `%` (positions are percentages), so it is
  substituted with `.replace()` and never `%`-formatted. `%`-format tried to
  read every percent sign as a conversion.
- A test case must `print("PASS")` or the runner counts it as a failure however
  many assertions passed.
