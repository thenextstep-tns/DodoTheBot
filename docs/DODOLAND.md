# DodoLand — handoff

The socialite tribe's town map. State as of 29 Aug 2026, branch `refactor`.

Trial ranks are the other half of this and have their own doc
(`docs/TRIAL_RANKS_HANDOFF.md`). Read it: DodoLand hangs its visual prestige off
that ladder and reads from it, one-directionally.

**Read `docs/HANDOFF.md` first** for the repo-wide traps: the `py` launcher, the
UTF-8 console, the heredoc trap (which bit this build four times), the
100-command cap, the 14-second deploy.

---

## 1. The one idea

**A town is a profile, not a ladder.** A socialite's reward is being seen by
other people, so everything optimises for the glance, the screenshot and the
neighbour, never for a number going up in private.

Three things follow, and every module obeys them:

**Reach, not volume.** What is counted is how many *different* people you
reached and who reached back. Volume crowns whoever talks most, which is not
what a socialite is. Message count exists, weighted at 1, so a quiet town is not
a dead one; it is not a way to earn.

**Every social act is capped per partner per day.** Past the cap the act still
happens and simply does not score, so a score cannot be inflated without
involving more people.

**Nothing is ever taken away.** No decay anywhere. Dormancy is a *view*: a town
is drawn lit or dim from its recent window. Adding decay would be a design
reversal, not a tweak.

## 2. The two axes

| Axis | Comes from | Who can get it |
|---|---|---|
| **Structure tier** — what you built | DodoLand standing, per channel | Anyone, by being sociable |
| **Flourish** — what you are known for | Trial rank | Only the trial ladder; cannot be ground for |

A chatty non-raider and a Godslayer can own the same building; only one has it
wreathed in light. `standing.py` contains **no reference to flourish** and a
test fails if it ever does. Rank buys visual effect, never a tier.

## 3. Where things are

```
helpers/dodoland/
  metrics.py     what counts and what it is worth (17 metrics)
  parameters.py  own registry, own collection (84 knobs; per-metric ones generated)
  intake.py      what a message is worth. The ONE place that decides
  store.py       the two activity collections, and the only reads of them
  standing.py    acts -> building points -> tier -> town power
  buildings.py   per-guild building definitions, validation, read-migration
  townart.py     drawing a town from primitives (9 shape families, 36 glyphs)
  towns.py       authored names, descriptions, pictures. Never scored
  assets.py      the decor library an admin uploads
  flourish.py    trial rank -> visual level. READ-ONLY; the only outside read
  mapview.py     graph-driven placement. Built, and NOT used by the map page
  backfill.py    rebuilding history from the message archive
  voice.py       voice session bookkeeping, clock-testable, no Discord types
  invites.py     who brought whom in, and when to refuse to say
web/dodoland/
  __init__.py       the route table. Every route is panel-scoped
  pages.py          the DodoLand panel page (7 sections)
  mappage.py        the map's own full-window page
  buildings_ui.py   the buildings editor
  api.py            the write endpoints
  assets_route.py   asset bytes, town pictures, town art on demand
cogs/dodoland.py               the listeners
tools/dodoland_backfill.py     the rebuild, from the shell
```

Collections: `DodoLandActivity`, `DodoLandPairs`, `DodoLandParams`,
`DodoLandConfig` (buildings, map image, plots), `DodoLandAssets`,
`DodoLandTowns`.

## 4. Live state (ESO for Dodos, 783594413632520203)

- Listener running since 28 Aug. **17 metrics**, three of them backfillable
  (`message`, `mention_given`, `mention_received`).
- History rebuilt: **21,797 activity rows, 3,710 pair rows, 672 people**,
  2024-09-26 to 2026-08-27, from 233,010 archived messages. Rows the rebuild
  wrote carry `source: "backfill"`; the listener's carry none.
- **15 buildings, 14 with rooms attached.** Map image uploaded. **Plots cleared
  on purpose** — the map starts empty and fills by hand.
- Nothing is visible to any member. There is no player-facing surface at all.

## 5. Decisions the owner settled

| Question | Answer |
|---|---|
| Bot commands vs ignored bot channels | Commands count **wherever** they happen |
| Can a room feed two buildings? | **Yes**, at different weights |
| Who gets a town? | **Only people with activity** |
| Does voice build anything? | **No** — town power only, for now |
| Forum posts | **Their own rooms**; ordinary threads collapse to their parent |
| Thresholds | **Derived** from the live distribution, with a floor |
| Placement | **Manual only.** Nothing is auto-scattered |
| Public surfaces | **None yet.** See §6 |

## 6. Nothing is public, deliberately

A public map link, a per-player settle page and a `/town` command were all built
and **removed again**. None of DodoLand is ready to be seen by the people it
ranks, and a half-finished thing behind a URL somebody can paste is worse than
no thing at all. It comes back with a proper front end: a Discord login and an
account that can manage its own town, not a capability link.

`tests/cases/test_dodoland_settle.py` walks the route table and fails on any
DodoLand route without a panel scope, and if either capability-link path returns.

## 7. The map page

`/guild/{gid}/dodoland/map`. Its own full-window page, reached from a button in
the panel's map section. The panel no longer draws a map at all; it drew its own
markers once and consequently showed something different from every other
surface.

**Towns are made of buildings.** Nine shape families — inn, hall, keep, chapel,
enclosure, workshop, playhouse, monument, gate — each recognisable in outline
alone. **Shape says what a building is, tier says how far it has come, and a
Font Awesome emblem says what it is for.** A keep with a shield and a keep with
a map are the barracks and the war room, and no amount of masonry would have
said which. Colour alone was tried first: fifteen buildings in eight colours
read as confetti.

**The climb escalates.** This was the original PDF's best idea and was cut too
hard when its arithmetic was rejected — the numbers were unreachable, the
ambition was not wrong:

- tier 4 — the ground warms under it
- tier 5 — an aura settles over it, embers lift off the roof
- tier 6 — **it leaves the ground**: hovers over its own shadow, ring of light,
  orbiting motes, a beam standing over the settlement

**Life** wanders between the buildings, drawn from what actually stands there: a
menagerie brings animals, an inn brings drinkers, a chapel brings birds.

### How a town relates to the map

Town width is a **percentage of the map's width**, never pixels, for the same
reason positions are percentages: re-uploading a redrawn map at another
resolution must change neither where a town sits nor how big it looks. A pixel
size made the same setting a twentieth of a large map and a third of a small one
— one town covered an entire island.

Towns **grow with standing**, from a base width up to a multiple of it, on a
square-root curve. Linear growth would let one prolific person's settlement
swallow the map. Both settings live on the map section rather than in the
general settings list: a town width means nothing except beside the map it
applies to.

### Level of detail

Three levels, and it is real rather than claimed:

1. **Off screen** — no DOM node at all, culled to the visible rectangle.
2. **A dot** — below the dot threshold. No artwork is fetched.
3. **Full, then close-up** — artwork is fetched from
   `/guild/{gid}/dodoland/town/{uid}/art` the first time a town comes close
   enough, once, then kept. Flourishes appear above the detail threshold.

The page once shipped all 343 settlements pre-rendered and hid the far ones with
CSS, paying the whole payload and parse for the handful anybody sees. This is
why detail per building can now be as rich as you like: what is on screen at
high zoom is a few towns, not the server.

## 8. Traps. Read this before touching the map

**Never put `will-change` on `.dlworld`, and never a CSS `filter` on anything
inside it.** Either promotes the world to a composited layer which the browser
rasterises once and then scales, so an uploaded SVG map stops being vector the
moment anybody zooms and every town blurs with it. Effects use **opacity,
transform and SVG gradients** only. `test_dodoland_page.py` strips comments and
fails on any `filter:` in that block, or on `will-change` returning.

**`bindMultiSelect` never writes its selection back to the DOM.** It keeps the
chosen ids in a closure and hands them to its `save` callback, and nothing else.
Reading `data-selected` off the options returns the server-rendered state
forever, which is why attaching channels to a building silently did nothing.

**`panel.js` only binds controls inside a `.cogcard`.** This page has none, so it
binds its own, on `DOMContentLoaded` — `panel.js` loads *after* an inline script.

**A save with no feedback is indistinguishable from no save.** `flash()` writes
into `#status` and silently gives up when there is none.

**A panel with no menu entry is unreachable.** The rebuild button sat hidden on
the page for hours. The render test now fails on any panel without an entry, and
on any entry pointing at nothing.

**Mongo keys must be strings.** `validate_channels` returned int keys once and
every building save 500'd.

**Missing fields are filled in from the defaults on read** (`buildings()`).
Every building on this server predates the icon, shape and symbol fields. Add a
field to a building and add it there too, or existing servers silently get the
fallback for it.

**Gradient ids must be unique per town**, or every town takes the colour of
whichever drew last.

**A rebuild clears its own previous output before writing.** Upserting alone
cannot remove a row the plan stopped producing, so a rules change left old rows
beside new ones and the bot kept a town it should never have had.

**Bots are excluded on both sides of every act.** Excluding bot *authors* was not
enough: people mention the bot constantly, and it built a 10,560-point town out
of being talked to.

**aiohttp refuses a request body over 1MiB by default**, and does it by
resetting the connection mid-read, so the handler never runs and the browser
gets no answer at all. Every upload this panel offers is larger than that.
`create_app` sets `client_max_size`; the per-file limits live in the handlers,
where a refusal can say what was wrong. This was blamed on DodoLand twice.

**The panel reads its collections once per page load.** It did eight full scans
of a 32,000-row collection at one point, which was 5.6 seconds of database time.
`guild_standings` takes pre-fetched rows for exactly this.

## 9. Testing

```bash
py tests/run_tests.py dodoland      # this subsystem
py tests/run_tests.py               # the whole bot suite (47 cases)
py tests/test_dnd_panel.py          # after touching web/routes.py, which this does
```

| Case | What it holds down |
|---|---|
| `test_dodoland` | Guild scoping, both caps, acts-vs-scored, voice overlap, invites |
| `test_dodoland_standing` | Validation, derived thresholds, suggestion, shape distinctness, tier escalation, town depth |
| `test_dodoland_page` | Both pages render; **no tabletop import; no write to trial ranks**; nothing rasterises; panels reachable |
| `test_dodoland_backfill` | A rebuilt day equals a live day; repeatable; never crosses the boundary |
| `test_dodoland_map` | Graph placement, for `mapview.py` |
| `test_dodoland_settle` | The three bases, and that **every route is scoped** |

## 10. What is not built

- **Any player-facing surface.** All of §6. This is the big one.
- **Placing decor.** The library, the tier locks and the toolkit strip exist;
  nothing lets anybody put an asset on their plot.
- **Reactions** as a metric. Forward-only; would arrive as entries in `METRICS`
  and nothing else.
- **Rank-granted social function** (hosting beacons, decor slots, naming
  rights). Candidates only. The constraint: rank grants *social* capability,
  never economic advantage, or the two axes collapse into one.
- **`mapview.py`'s graph placement** is built, tested, and unused by the map
  page. It is the neighbours-from-the-social-graph idea, kept for whenever
  auto-placement is wanted again.
- **Font Awesome is a CDN dependency**, on the map page only, for the emblems
  and the wanderers. If it is blocked those glyphs do not draw and nothing else
  is affected. Vendoring it locally is small and nobody has asked yet.

## 11. Where to pick up

The economy is configured and the history is real. What is missing is anybody
being able to see it. In rough order:

1. **Place towns on the map.** 672 people have standing and the map is empty by
   design; placement is by hand from the drawer beside it.
2. **Tune the tier thresholds against the preview**, which is exactly what the
   two previews (with history / from scratch) exist for.
3. **Build the player front end** — Discord login, your own town, customise it.
   Everything else has been waiting on this.
4. Then decor placement, then reactions, then rank-granted function.
