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

**16 metrics, 71 parameters.** Three are backfillable (`message`,
`mention_given`, `mention_received`); the other thirteen count forward only.

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
- **A thread is charged to its parent channel.** A thread is a room inside a
  channel; otherwise every new thread silently escapes a building's definition.
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

## 4. Next: P1, the panel

Everything below is designed and unbuilt. The shape asked for:

1. **Building → channels → weight per channel.** A building is per-guild data,
   not a constant: name, icon, the channels that feed it and how much each is
   worth, its metric multipliers, and its tiers. Free-form the way trial ranks
   are free-form.
2. **Building → tiers**, each a title and a point threshold. Six or so, not
   thirty. Thresholds should be **derived from the server's own distribution**
   (tier N = a percentile band of the active population) rather than authored,
   so a tier means the same thing on day one and in three years, on a 60-person
   server and a 600-person one. The percentile band is the knob.
3. **Live preview, panel-only.** Computed for everybody, from real backfilled
   data, tweakable against the live system, and shown to nobody outside the
   panel until the numbers are right.
4. **Town power**: the total ranking. Buildings score from channels; town power
   adds the people-reached term, which is channel-agnostic by nature.

Then P2 the map (admin uploads the base image, players pick a plot), P3 the
Discord surface (`/town`, one grouped command), P4 neighbours and visiting.

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

`tests/fake_mongo.py` gained `$or` and `find_one_and_update(upsert=…)` for this,
because the stub was more forgiving than Mongo and the handoff is explicit that
this is how bugs survive.
