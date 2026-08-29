# DodoLand — handoff

The socialite tribe's town map. State as of 29 Aug 2026, branch `refactor`, commit `b7e2ad0`.

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
  parameters.py  own registry, own collection (91 knobs; per-metric ones generated)
  intake.py      what a message is worth. The ONE place that decides
  store.py       the two activity collections, and the only reads of them
  standing.py    acts -> building points -> tier -> town power
  buildings.py   per-guild building definitions, validation, read-migration
  townart.py     drawing a town (9 shape families, 9 kinds of inhabitant)
  faicons.py     GENERATED. 72 Font Awesome paths; see tools/vendor_fa_icons.py
  towns.py       authored names, blurbs, pictures, building colours. Never scored
  assets.py      the decor library an admin uploads
  decor.py       what has been placed on the ground, in two scopes
  flourish.py    trial rank -> visual level. READ-ONLY; the only outside read
  mapview.py     graph-driven placement. Built, and NOT used by the map page
  backfill.py    rebuilding history from the message archive
  voice.py       voice session bookkeeping, clock-testable, no Discord types
  invites.py     who brought whom in, and when to refuse to say
web/dodoland/
  __init__.py       the route table. Every route is gated; two kinds of gate
  pages.py          the DodoLand panel page (9 sections)
  mappage.py        the map's own full-window page, and the admin toolkit
  buildings_ui.py   the buildings editor, including the shape and emblem pickers
  player.py         THE PLAYER FRONT END. Its own gate; never reads a user id
  theme.py          the palette, the chrome and the artwork's CSS, shared
  api.py            the admin write endpoints
  decor_api.py      placing things: admin on the world, a member on their town
  assets_route.py   asset bytes, town pictures, town art on demand
cogs/dodoland.py               the listeners
tools/dodoland_backfill.py     the rebuild, from the shell
tools/vendor_fa_icons.py       re-fetch the emblem paths
tools/dodoland_art_preview.py  every shape, tier, emblem and flourish, offline
tools/dodoland_map_preview.py  the real map page, clickable, with stub data
```

Collections: `DodoLandActivity`, `DodoLandPairs`, `DodoLandParams`,
`DodoLandConfig` (buildings, map image, plots), `DodoLandAssets`,
`DodoLandTowns`, `DodoLandDecor`.

**Two preview tools, and they matter.** Nothing in the suite runs a page's
JavaScript and nothing renders artwork you can look at, so for most of this
subsystem's life the only place to see it was a live server behind an admin
login. Both tools import the same modules the real pages do — there is no second
copy of the drawing anywhere, which is the one thing that would make them worse
than useless. They write ignored HTML files at the repo root; serve them with
`py -m http.server` and open them.

## 4. Live state (ESO for Dodos, 783594413632520203)

- Listener running since 28 Aug. **17 metrics**, three of them backfillable
  (`message`, `mention_given`, `mention_received`).
- History rebuilt: **21,797 activity rows, 3,710 pair rows, 672 people**,
  2024-09-26 to 2026-08-27, from 233,010 archived messages. Rows the rebuild
  wrote carry `source: "backfill"`; the listener's carry none.
- **15 buildings, 14 with rooms attached.** Map image uploaded. **Plots cleared
  on purpose** — the map starts empty and fills by hand.
- All fifteen were stored with `shape: "inn"` and were repaired on 29 Aug; see
  the trap in §8. Four halls, three keeps, a chapel, a monument, an enclosure, a
  workshop, a playhouse, a gate and two inns now.
- The player front end exists and is **switched off**. Three parameters, all
  defaulting to off, decide whether anybody sees any of it: `dodoland_town_pages`,
  `dodoland_world_page`, `dodoland_self_settle`.

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
| Public surfaces | Built, and **off by default**. See §6 |
| What a player may change | Everything authored, nothing scored |
| Who may place scenery | Admins, via an asset marked admin-only |

## 6. The player front end

A public map link, a per-player settle page and a `/town` command were built and
**removed again**, because a half-finished thing behind a URL somebody can paste
is worse than no thing at all. What was wanted instead was "a Discord login and
an account that can manage its own town", and that is what `web/dodoland/player.py`
now is.

`/towns` lists the servers somebody has a town in; `/guild/{gid}/dodoland/me` is
their town: the artwork, their standing and place, every building with the tier
it has reached and what the next rung costs, who they reached, and the name,
blurb, picture, building names and colours that belong to them.

**Three rules hold it together, and breaking any of them re-opens the hole the
capability links were removed for.**

1. **A player handler never reads a user id from the request.** Not the path,
   the query or the body. Whose town it is comes from the signed session and
   nowhere else, so there is no id to tamper with. The panel's handlers *do*
   take an id, because an admin is legitimately acting on other people — which
   is exactly why these are separate handlers rather than a softer scope on the
   same ones.
2. **Membership is re-checked every request.** Somebody who leaves the server
   loses the page on their next request, not when their week-old session expires.
3. **The whole surface is off until a server turns it on**, in three separate
   steps: your own town, everybody's world, placing your own town.

Two tests hold this down. `test_dodoland_player.py` asserts the switches default
off, that a user id in the body is *ignored* rather than refused, that the gate
checks membership, and that no player handler reads an id. `test_dodoland_settle.py`
walks the route table — with newlines collapsed, so a route that outgrew one
line is still checked — and fails on any DodoLand route with neither a panel
scope nor the player gate, and if either capability-link path returns.

## 7. The map page

`/guild/{gid}/dodoland/map`. Its own full-window page, reached from a button in
the panel's map section. The panel no longer draws a map at all; it drew its own
markers once and consequently showed something different from every other
surface.

**Towns are made of buildings.** Nine shape families — inn, hall, keep, chapel,
enclosure, workshop, playhouse, monument, gate — each recognisable in outline
alone. **Shape says what a building is, tier says how far it has come, and an
emblem says what it is for.** A keep with a shield and a keep with a map are the
barracks and the war room, and no amount of masonry would have said which.
Colour alone was tried first: fifteen buildings in eight colours read as
confetti.

**Emblems are Font Awesome — as paths, never as a font.** The first attempt set
FA glyphs as SVG `<text>` with a `font-family`, and it never rendered: no
building had an emblem and the wanderers came out as whatever the fallback had
at those codepoints. A webfont inside an SVG fails silently, at a distance, in
exactly the part people are meant to look at, and fails outright in an `<img>`
and in a fetched fragment.

FA's *artwork* is not its font. Every icon is one `<path>`, and 72 of them are
vendored into `helpers/dodoland/faicons.py` by `tools/vendor_fa_icons.py` — no
network, no loading, no fallback, and it scales with the drawing. **The rule
stands exactly as written: no webfont, no `<text>`.** A test fails on
`font-family` or `<text>` in a town, and another checks every vendored emblem
draws a path.

An emblem hangs as a **medallion**: the icon knocked out of a disc in the
building's colour, ringed in the same dark line as the masonry. Tinted and seven
units across it was a smudge that took real effort to identify; punched out of a
coloured disc it reads at a fraction of the size, for the same reason road signs
are shapes with symbols cut out of them.

**A gate builds the wall it belongs to.** A gate standing alone in a field is a
doorway to nowhere, so the gate family raises a wall following the plate's own
ellipse, reaching further round as its tier climbs. It is the only building that
changes the *town* rather than adding to it.

**A town's own flag is its building's flag.** The banner is handed *into* the
family that flies it, which puts it on its own pole. Planting it from outside at
the building's overall height gave a tier-six inn two flags: its own pennant on
the roof and the banner nine units above it. A family is the only thing that
knows where its flag goes.

**The climb escalates.** This was the original PDF's best idea and was cut too
hard when its arithmetic was rejected — the numbers were unreachable, the
ambition was not wrong:

- tier 4 — the ground warms under it
- tier 5 — an aura settles over it, embers lift off the roof
- tier 6 — **it leaves the ground**: hovers over its own shadow, ring of light,
  orbiting motes, a beam standing over the settlement

**Life** wanders between the buildings, drawn from what actually stands there: a
menagerie brings animals, an inn brings drinkers, a chapel brings birds. Each
family contributes one inhabitant before any family gets a second, so a zoo
always puts an animal out. They walk somewhere, stand about, wander back and
stop again, turning to face the way they are going — **twelve routes**, assigned
by a hash of the town and the walker. With two, half a crowd stepped right in
unison and the other half stepped left, which read as choreography. **The waiting
is in the keyframes on purpose**: continuous motion reads as a mechanism, pauses
read as somebody deciding.

**A town shows how many people built it.** One ordinary house per
`dodoland_people_per_house` people reached, capped by `dodoland_max_houses`, on
generated rings outside the landmark band. **Linear in reach on purpose**: a
logarithm made sixty people and three hundred come out as fifteen houses and
eighteen, a difference nobody could see in the one quantity the whole system
exists to measure. Six kinds of house, told apart by outline and by paired roof
and wall colours — sixty copies of one house in seven shades of brown is a
housing estate, not a town.

**What moves around a building belongs to it.** A tavern has mugs and music, a
library has pages, a forge throws sparks and turns a gear, a menagerie has
butterflies. This replaced a single enormous turning sun drawn over every town on
the map regardless of what was in it — the same object above three hundred
different places, saying nothing about any of them. Rank frames a town from
underneath instead: warm ground, lanterns round the shore, a band of light.

**Opacity is for light and nothing else.** Glows, halos, embers. Wheels, cogs,
suns and orbits *rotate*; cloth *skews*; particles *drift*. A pond that blinks
reads as broken.

**A town's picture flies as a flag** from whatever it has built highest, clipped
to the cloth so any aspect ratio reads as a banner rather than a photograph
nailed to a stick. The town card shows the same cloth with the same wave, so it
is the town's banner in both places. Naming, describing and picturing a town are
all authored and move no number; `standing.py` never learns about any of it.

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

**A save must not decide what a building looks like.** All fifteen buildings on
the live server were stored with `shape: "inn"` — not falling back, *written*.
The editor had no shape control, so a save sent none and `validate_building` did
`shape or DEFAULT_SHAPE`. "Suggest rooms" saves too, so pressing that alone
flattened the map. The emblems escaped only because a blank symbol is filled in
from the defaults on read and `"inn"` is not blank. Nine shape families made no
visible difference for weeks because of it. Now: a missing shape falls back to
*that key's own* default, the editor has shape and emblem pickers that **draw
what they are choosing**, the collector sends both, and there is a
"Reset shapes to the suggested ones" button. A test asserts `library→hall`,
`warroom→keep`, `menagerie→pen`.

**A class in the artwork with no rule in the stylesheet is silent.** `lifted`,
`orbit`, `spark`, `bbeam` and `bring` were emitted for weeks with no CSS at all:
tier six was supposed to hover over its own shadow with motes going round it and
it sat flat on the ground next to a shadow that made no sense. `test_dodoland_page`
now collects every class the top tier emits, subtracts the ones that are
legitimately static, and fails if the stylesheet does not mention one.

**Anything inside a rotating group rotates with it.** An orbiting emblem tumbled
and spent half of every circuit upside down. Each one sits in its own group that
the stylesheet turns back at exactly the orbit's rate — the durations must match
or it drifts.

**A town has to fit the 120x78 it is given.** On the map those boxes sit side by
side, so anything that overflows is painted across the neighbours and over the
town's own name. The tier-six beam was 92 units tall; the ground and the flourish
ran off the bottom; an emblem on a tall building ran off the top and is clamped.

**The built area and the ground it stands on must be the same shape.** `_stand`
ran six units either side of the plate's centre while the plate ran ten, and
widened *linearly* with depth — a trapezoid on an ellipse. Between them a third
of every plate was bare, at the front and around the back corners. Both come
from the plate's ellipse now.

**Everything on the plate needs the same size reference.** Houses carried a 0.52
depth factor and the walkers carried none, so a townsperson stood two and a half
times the height of the house beside them. One mismatch like that makes the whole
picture read as a model.

**Two answers to one question is the bug this file keeps having.** The flag
position and `family_height`; the walk routes in CSS and the classes in Python;
the shape in the defaults and the shape in the store. Where it can be avoided it
is: which families fly their own flag is discovered by looking for the banner in
what was drawn, not by keeping a list.

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

**A patch that reports success can still have changed nothing.** Twice a CSS
block vanished from an edit and nothing noticed: the markup was right, the
classes were right, the page rendered perfectly, and no rule anywhere animated
anything. The render test now collects every animation the page *references* and
every `@keyframes` it *defines* and fails if either set has something the other
does not. **After any patch to this page, check the thing you changed is
actually in the file.**

**`town_art` must pass everything the artwork takes.** It sat for several
changes calling `town_svg` with an old argument list, so emblems, the rank
colour, the per-town gradient id and the flag were all silently dropped while
the drawing code supported every one. The towns looked plausible, so nothing
pointed at it. A test names each argument and what is lost without it.

**Never take pointer capture on `pointerdown`.** Capture routes every following
event to the capturing element, so a click on a town landed on the frame and
nothing opened. It is taken only once movement makes it a drag.

**The detail threshold is in screen pixels; a town's width is a percentage of
the base image.** Whether the two can ever meet depends on the uploaded image. A
400px map, a 3% town and a maximum zoom of 8 reach 96px against a threshold of
150 — unreachable at every zoom, with nothing to say so. The map section now
states what size towns actually reach and warns when the threshold is above it.

**A projection that excludes a whole field destroys the fact that it existed.**
`TownStore.all()` excluded `image`, so "this town has a picture" was permanently
false and an uploaded picture was invisible everywhere. It excludes `image.data`
instead: withhold the megabytes, keep the fact. `tests/fake_mongo.py` did not
model exclusion projections at all and so agreed with the bug; it does now,
dotted paths included.

**Errors must appear where the action was.** A refused save wrote to the hint bar
in the far corner of the map, behind the card and usually off screen, so it
looked exactly like a button with no handler.

**The panel reads its collections once per page load.** It did eight full scans
of a 32,000-row collection at one point, which was 5.6 seconds of database time.
`guild_standings` takes pre-fetched rows for exactly this.

## 9. Testing

```bash
py tests/run_tests.py dodoland      # this subsystem (8 cases)
py tests/run_tests.py               # the whole bot suite
py tests/test_dnd_panel.py          # after touching web/routes.py, which this does
py tools/dodoland_art_preview.py    # and then look at it
py tools/dodoland_map_preview.py    # the real map page, clickable
```

| Case | What it holds down |
|---|---|
| `test_dodoland` | Guild scoping, both caps, acts-vs-scored, voice overlap, invites |
| `test_dodoland_standing` | Validation, derived thresholds, suggestion, shape distinctness, tier escalation, town depth, **a save keeps its shape**, one banner per town |
| `test_dodoland_page` | Both pages render; **no tabletop import; no write to trial ranks**; nothing rasterises; panels reachable; **every effect class is styled**; twelve walks |
| `test_dodoland_player` | The three switches, the gate, and that **no player handler reads a user id** |
| `test_dodoland_decor` | Tier locks enforced on the server, ownership, limits, cleanup |
| `test_dodoland_backfill` | A rebuilt day equals a live day; repeatable; never crosses the boundary |
| `test_dodoland_map` | Graph placement, for `mapview.py` |
| `test_dodoland_settle` | The three bases, and that **every route is gated** |

**Run the previews.** Half the defects in §8 rendered, parsed and passed every
test; they were only ever visible by looking. "The tests pass" is not evidence
the artwork works.

## 10. What is not built

- **The colour picker.** A town's `building_colours` are stored, validated as
  `#rrggbb` and drawn; nothing lets an owner choose one. The plumbing is done
  and the control is missing.
- **The world page for members** (`dodoland_world_page`) gates the switch and
  the map is shared, but a member-facing map route is not wired: the switch
  currently only gates settling.
- **Reactions** as a metric. Forward-only; would arrive as entries in `METRICS`
  and nothing else.
- **Rank-granted social function** (hosting beacons, decor slots, naming
  rights). Candidates only. The constraint: rank grants *social* capability,
  never economic advantage, or the two axes collapse into one.
- **`mapview.py`'s graph placement** is built, tested, and unused by the map
  page. It is the neighbours-from-the-social-graph idea, and it is the seed of
  "regions of influence" if that is ever wanted.
- **Regions and kingdoms.** Discussed, not designed. Terrain was asked for and
  is deliberately *not* new machinery: a forest is an admin-only asset placed
  with the toolkit.
- **The wall's gate does not line up with the gate building.** The gap is at
  the front-centre of the plate; the wayshrine stands wherever its tier puts it.

## 11. Where to pick up

The economy is configured, the history is real, the artwork is worth looking at
and the front end exists. What is missing is anybody having been shown it.

1. **Place towns on the map.** 672 people have standing and placement is by hand
   from the drawer beside the map. This is still the gate on everything else.
2. **Tune the tier thresholds against the preview**, which is what the two
   previews (with history / from scratch) exist for.
3. **Turn on `dodoland_town_pages`** and look at your own town as a member would
   before telling anybody. The panel section links straight to it.
4. Then the colour picker, then the member-facing world map, then reactions,
   then rank-granted function.
