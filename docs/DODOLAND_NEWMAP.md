# DodoLand — the new map (branch `NewMap`)

Read `docs/DODOLAND.md` first. This is the redesign agreed with Nik on
10 Oct 2026, and the order it is being built in. Nothing here changes the
economy: `standing.py`, `intake.py`, the activity rows and flourish are untouched.

## The idea, as layers

| # | Layer | Who authors it | Built on |
|---|---|---|---|
| 1 | **Base map** — tiles painted on the grid | Owner curates the tile library; server admins paint | `terrain.py` grid, brush, undo, importer |
| 2 | **Roads** between connected towns | The bot (pathfinding) | `BUILT` layer, pair rows |
| 3 | **Decor** | Owner (global), server admins, players | `assets.py`, `decor.py` |
| 4 | **Buildings** inside a town's influence | The player | the per-server buildings and `townart.py` |

A town is a **town hall with its flag at the dot**, plus an **influence area**
that grows outward over the grid, around whatever is impassable (sea, map edge,
mountains). Inside it the player places their buildings and decor, and those
positions are saved. Buildings still climb tiers from standing exactly as now.
Walkers wander inside the influence area. More influence unlocks more assets.

## Decisions (Nik, 10 Oct 2026)

| Question | Answer |
|---|---|
| Two towns' influence meet | **Overlap allowed.** Each town's area is its own set of cells, not one shared ownership map. Shared ground is buildable by any town covering it; a cell holding a building is blocked for everyone else (Claude's default, not yet confirmed) |
| Which connections get a road | **Strongest few per town** (N is a setting); roads merge into a network |
| Tile format | **Plain tiles first**, with random variants. Corner autotiling (16-piece) is a later step |
| What sizes influence | **Town power**, on the square-root curve town width uses today |

## Order of work

Each step is one thing that can be clicked and checked, then stop.

1. ✅ **Tile library (owner, global).** Upload, name, categorise, order, variants. `helpers/dodoland/tiles.py`, `web/dodoland/tiles_ui.py`, `/dodoland/tiles`.
2. ✅ The base map draws library tiles (generated motifs **removed**); Brush / Select / Pattern tools.
3. "Rebuild roads": A* over `move` cost, written to `BUILT`, drawn. **Not built yet.**
4. ✅ Influence: per-town region grown from the town hall over `grow` cost, budget from town power; borders drawn (Influence layer).
5. Town hall + flag at the dot (behind a per-server switch; old town art stays the default).
6. Players place their buildings inside their region (layer 4).
7. Global owner decor, unlocks by influence, walkers confined to the region.

## Safety

All work is on `NewMap`, which does not auto-deploy (only `refactor` does). The
current town rendering stays the default until the new one covers it.

## Progress

**Step 1 done (10 Oct 2026).** `TileLibrary` in `helpers/dodoland/tiles.py`, three
collections (`DodoLandTileCats`, `DodoLandTiles`, `DodoLandTileArt` — bytes kept
apart so listings never carry them). Owner page at `/dodoland/tiles`, linked as
"🧱 Tiles" in the owner nav. Routes use a third gate, `owner = require_owner`;
both route-gating tests accept it and check it is the real owner gate.
`tests/cases/test_dodoland_tiles.py` covers ordering, refusals and cleanup.
The same editor is embedded as a **Tile library** section of every server's
DodoLand page, shown to the bot owner only (`test_dodoland_page` asserts a
server admin never sees it).

**Step 1b — the packs are in (10 Oct 2026).** `tools/dodoland_import_tiles.py`
reads the zips in `item_imgs/tilesets` (gitignored) directly and imported
**196 tiles / 567 images in 20 categories** into the live library. It is a
hand-checked manifest, not a heuristic, and it is re-runnable: each tile has a
`source` key and an existing one is left alone, so the owner's later edits
survive. `--preview out.png` renders everything it would write and writes nothing.

* **Ground** = cells that are one terrain on every side (Tiled wangsets for
  Fan-tasy; for the rest, every border pixel must be a colour from the tile's
  middle — a stray edge pixel repeats into a visible grid across a field).
* **Objects** = islands of opaque pixels cut by their own pixels, not their
  box: packed sheets overlap boxes and a box crop drags the neighbour in.
* Near-identical pieces (tufts, pebbles, ivy) are **one tile with variants**.

Each tile now carries:
* `uses` — `layer:role` pairs, layers `environment` / `objects` / `buildings`,
  roles `admin` / `player`. The owner is not a role (can use everything); roads
  are the bot's and not a use. Typos are refused, not dropped. Defaults from the
  import: ground → environment for admins; objects → map objects for admins and
  players; house parts → admins only. Editable per tile and per category.
* `cell_px` — 16 or 32, the grid the art was drawn on. **Pixel Art Top Down,
  FL Houses and the dog items are 32px; Fan-tasy, Summer Plains and Valley Ruin
  are 16px.** The renderer must scale by this or a 32px pack's tree is drawn
  twice the size of a 16px one.
* `pack` — for credits. **Summer Plains (schwarnhild) asks to be credited and
  forbids redistributing the files**; FL Houses forbids reselling them. Using
  them in the bot is fine; do not commit the art or publish the packs.

Left out, deliberately: animated cats, dogs, slimes and characters (walkers,
step 7), animation strips, shadows, house interiors, autotile edges, cliffs, the
Fan-tasy building atlas (transitions are a later step).

**Step 1c — the Miro board's art is in (10 Oct 2026).** Everything on the
DodoLand Miro board (`uXjVJYoeUCE=`) that is *not* on the map: **578 tiles / 803
images in 35 categories**, each named `Map art · <the board's section label>`,
pack `DodoLand Miro board`. Library total: 774 tiles, 55 categories.

How it was got, for next time (the board is locked — owner subscription lapsed
— and was read anonymously, comment-only):
* **Select all → Copy** puts `miro-data-v1` on the clipboard: base64, every byte
  shifted by +59, decoding to JSON with every item's resource id, **crop**
  rectangle (in source pixels), position, and grid cell. Many board images are
  crops of one shared sheet.
* `GET /api/v1/boards/{board}/resources/{id}/files/original?redirect=false`
  returns a signed `r.miro.com` URL for the original file. The page fetched each
  original once, cut the crops in a canvas and saved one JSON bundle.
* Off-map = outside the map rectangle (x −17.5k…36.8k, y −18.5k…7.3k board
  units; it matches the 958×453 terrain grid's aspect). Categories are the
  section label above each grid; 75 loose images were assigned by name.
* **Scale**: 353 of the images also appear on the map, and how big they were
  drawn there is their real scale — ~57 source px per terrain cell (56.7 board
  units per cell). Others take their section's median, clamped to 4× of it.
  So `cell_px` is now **any number 4–1024** (16/32 kept as presets).
* Scenery sections (hills, mountains, dunes, fields, flowers, rocks, waves,
  bushes, trees) are grouped into tiles with variants; everything else
  (monsters, crowds, castles, ships, weapons…) is one tile per drawing.
* Defaults: map objects for admins and players; Frames, Icons and Banners admins
  only. `MAX_BYTES` is 2 MB per image (drawn art is big), `MAX_CATEGORIES` 100.

`tools/dodoland_import_tile_bundle.py bundle.json [--dry-run]` is the generic
writer any future import can use: a curated JSON list in, re-runnable by `source`.

**Step 1d — the tile library replaces the asset library (10 Oct 2026).**
Each tile now has:

| Field | Meaning |
|---|---|
| `layer` | one of environment / objects / buildings (the old layer×role grid is gone) |
| `access` | `admin`, `player` — the bot owner can always use everything |
| `requires` | `{building, tier}`: a player's lock, the asset library's rule. A server without that building key has no such lock |
| `passable` | whether a road may be drawn through it |
| `resizable`, `scale_min`, `scale_max` | placement size range; fixed tiles are 1x, clamped **server-side** in `decor.py` |
| `guild_id` | 0 = global (owner's); otherwise that server's own tile |

* **Server admins (full scope)** get the Tile library section on their DodoLand
  page: global tiles read-only, their own server's tiles editable, uploads go to
  their server. Categories are the owner's. `/api/guild/{gid}/dodoland/tiles`
  enforces this; `test_dodoland_page` asserts the refusals.
* The **map toolkit** lists map objects/buildings admins have access to, one
  category at a time; the **town toolkit** lists map objects with player access,
  locked by `tiles.unlocked_for`. Decor rows keep the field name `asset_id`, which
  now holds a **tile id**; the image routes serve the tile's first variant.
* `helpers/dodoland/assets.py` and the Asset library section are **deleted**.
  `DodoLandAssets` is untouched (production on `refactor` still reads it); its 2
  rows were copied in as this server's tiles.
* `tools/dodoland_tiles_migrate.py` set layer/access from the old `uses`, judged
  `passable` (water, mountains, buildings, walls, monuments, solid props, rocks
  block roads; ground, plants, creatures, items, docks and planks do not — 386
  of 774 block) and made all 578 map-art tiles resizable 0.25–4x. It only fills
  unset fields, so re-running never overwrites panel edits.

Next: step 2 — draw environment tiles on the map as SVG patterns (the same
mechanism the motifs use), scaled by `cell_px`, the brush picking a tile from
`usable("environment", role)`.

**Step 2 + layers + buildings + influence (10 Oct 2026).**

*Ground.* A kind of ground is drawn with the tile it is bound to
(`kind["tile_id"]`): up close an SVG pattern of the tile's own images (4x4 block
of variants, sized by px-per-cell), far away its average colour. Painting a tile
appends a `tile_<id>` kind whose costs follow the tile's `passable` flag
(`terrain.sync_tile_kinds`). The imported kinds are bound to six tiles made from
the reference SVG's own colours (`tools/dodoland_terrain_bind.py`, category
**Map art · Ground**), so the map reads like the original.

*Tools* (terrain drawer): Brush with a random mix (shift-click), density and soft
edge, fresh server-side seed per stroke; Select (fill / clear / keep as pattern);
Pattern (tiled from the world origin). Endpoint: `api_terrain_paint` modes
`brush` / `rect`, plus `GET terrain/cells` for copying. Drawers share one style.

*Layers.* Tiles have `placement`: `paint` (environment ground only) or `place`.
Decor rows carry `layer`, `variant` and an import `source`. The map draws, bottom
to top: painted ground, influence, environment features, roads, map objects,
buildings and towns. **Layers** panel: show/hide each, choose the edited layer —
only its pieces are grabbable, the toolkit offers only its tiles. A piece is
drawn at its own variant's natural width (`vw`) times its size.

*The Miro map's terrain.* 2,443 features (forests, mountains, hills, fields,
dunes, flowers, ponds, rocks, caves, swamp, waves) placed as layer-1 features,
98 rivers painted as the `river` kind. Registration fitted from land/sea cues
(96% agree; scale 0.017873 cells per board unit, origin (-16850, -18250));
towns, creatures, ships, people and shrines deliberately left off.
`tools/dodoland_place_plan.py` (re-runnable, backs up ground before strokes),
`tools/dodoland_layers_migrate.py`. Each terrain tile's px-per-cell was re-read
from its own placements; sizes may run 0.25-12x.

*Town buildings.* `helpers/dodoland/building_tiles.py`: every (building, tier)
is a server tile in **Town buildings** — layer 4, players + admins, blocks roads,
requires that building at that tier. Re-synced on every buildings/shapes save.
The town toolkit offers objects and buildings.

*Influence.* `helpers/dodoland/influence.py` (pure Dijkstra over `grow` cost,
8-neighbour, budget = base + (top - base) * sqrt(power / strongest));
`web/dodoland/influence_api.py` adds blocking footprints of impassable placed
features and caches per guild. Params `dodoland_influence_base` (6),
`dodoland_influence_top` (40), `dodoland_influence_clear_forest` (off). Rivers
and water stop growth. **No towns are placed yet**, so the layer is empty until
one is.

Next: town hall + flag at the dot (step 5), roads (step 3), players placing
buildings inside their own area (step 6: enforce "inside your influence").

**Correction, same day: the map is terrain tiles only.** Nik rejected the Miro
art on the map (sizes were wrong under the old renderer, and it is not what the
base map is for). Done:

* all 2,443 placed map-art pieces **removed** (world decor is empty);
* the six generated "parchment / ink" tiles and their category **deleted**;
* the grid **repainted** by `tools/dodoland_terrain_rebuild.py`: water from the
  imported coastline (deep sea -> Summer Plains *Deep water*, everything else
  -> Fan-tasy *Lake water*), land -> *Meadow grass*, then regions read from where
  the Miro terrain drawings stand (`miro_regions`): fields *Summer grass*, dunes
  *Summer sand*, forest *Olive grass* (gaps closed so lines of trees become
  woods), swamp *Valley grass*, hills *Valley dirt*, mountains *Stone paving* as
  a **fixed blocking kind** (`kind["fixed"]`, so the tile stays a road surface
  elsewhere), ponds *Lake water*. The world's kinds are now only tiles.
* The tool refuses to run twice (it reads the imported water kinds); a backup of
  decor, chunks and kinds from before the clean-up is in the session scratchpad.

The built-in kind list (`terrain._BASE_KINDS`) still exists in code for the map
importer and as a new world's default; it is no longer in this world or any UI.

**The grid is 4x finer (3832 x 1812).** One cell per reference-map pixel made a
cell house-sized, so a river could not be thinner than a house.
`tools/dodoland_terrain_regrid.py GUILD --factor 4 --features f.json` redraws
the grid from the server's **vector** reference SVG (re-rasterised, not blown up
from old cells), draws rivers at least 3 cells wide, paints the region ellipses,
and floods the open sea (more than `--band` cells from land, joined to the edge)
as deep water. Dry run by default (`--preview p.png`); `--write --backup b.json`.
Features are map fractions, so the same file works at any factor. Every placed
position is a percentage, so nothing moved.

Cell-based settings were multiplied by 4 on this server so the world reads the
same size: influence base 24 / top 160, hall 10 cells, tile scale 1.25.
`influence.MAX_CELLS` 60k -> 400k (one big town now covers ~70k cells, ~0.2 s).
The overview step is a power of two (8 here) so it divides a 64-cell chunk.
Brush size up to 64 cells (default 12). Max zoom on this server is 50, about
12 px per cell, so tile textures show from about 1/5 of that.

**Overlay lines are screen pixels, and the influence follows its town.** Every
overlay inside the zoomed world was being scaled by the zoom: SVG
`non-scaling-stroke` only undoes the SVG's own viewBox, not the CSS transform on
`#dlworld`, and the browser rounds a sub-pixel CSS outline up to 1px before
scaling it. So at zoom 20-50 the influence border, brush ring and piece outline
were 20-80 px fat. Now: SVG overlay strokes use `.dltline` (width
`calc(Npx * var(--inv))`), and held/hovered pieces are marked by `.dlmark` boxes
on the frame (screen space), not outlines on the piece.
The brush cursor is the exact footprint (same disc test as the server, cell
edges, faint fill); size 0 is one cell. `cellAt` floors (the cell under the
pointer), so what is shown is what is painted. Arming a toolkit piece shows a
ghost of it at the cursor, at its placed size. Influence reloads after a town
is placed/moved/removed and after any decor change; its server cache key now
includes piece positions, not only the count.

**Terrain cache key survives restarts; no black screen while it loads.**
`terrain_api.version()` is now `"<boot>.<world rev>.<paints>"` (it was an
in-memory counter that restarted at 0, while the browser holds terrain responses
for 10 minutes — so after a restart, and after the regrid, `v=0` could serve the
old ground). The reference image stays visible until the first overview
arrives (about 5-7 s on a cold process: page 2.6 s, then world, overview and
influence 1.5-2.7 s each) instead of being hidden as soon as the world loads,
which left a black frame. Checked against real data through a read-only GET
harness (scratchpad `harness/serve.py`, port 8790, stopped afterwards).

## Backlog from Nik, 10 Oct 2026 (evening) — not started

Given as one list to work through after a break; take them one at a time.

1. **LoD / first impression.** Zoomed out, the blocky overview (average colours,
   step 8) looks bad and is the first thing a player sees. It should look pretty
   immediately — smoothing between levels of detail, nicer overview, optimise.
2. **Town buildings can't be placed** from the town's toolkit (the generated
   building tiles). Walls in particular should be built *around the town's
   influence area* rather than stamped.
3. **A loading screen** until everything is in (page ~2.6 s, then world/overview/
   influence ~1.5-2.7 s each on a cold process), and cut those times where possible.
4. **Click away from a town → its influence drawing goes.** Influence shows for
   the selected town only.
5. **Opening Toolkit or Terrain closes the other drawers** and deselects their
   armed tools.
6. **Some tiles flicker squished/normal on hover** over terrain (probably the
   non-square ones — the placement ghost's width/height, likely `pieceWidth`
   without the variant's own aspect, alternating with the real image).
7. **Objects place as if they had variations.** Only terrain tiles have variants;
   everything else is a stamp: one image, always the same (decor_api picks a
   random variant on place — stop that for non-paint tiles).
8. **Placing a tile in a fresh town sometimes selects the influence area**
   instead of placing/selecting (the influence overlay is catching clicks).
9. **Placed toolkit items must be selectable and owned**: stored with who placed
   them and where; the user can see, select and delete their own. Needs a small
   toolbox: **pointer** (select), **hand** (pan, or drag a selected piece),
   **pencil** (single-tile placement), **brush** with patterns — each with its
   own mechanic.
10. **Shallow water counts as influence** (grow cost for the light coastal water
    should let the area cover it; deep water still stops it).
11. **Low-resolution tiles**: some tiles are badly blurry (e.g. Olive grass tuft,
    Summer sprouts, Tiny flowers, Moss — upscaled tiny sprites). Fix (redraw at
    proper size / nearest-neighbour at an integer scale) or remove.

### Backlog progress — quick fixes done (4, 5, 6, 7, 8, 10)

* **5** One drawer at a time (`closeDrawers(keep)` in mappage): opening Towns,
  Toolkit or Terrain closes the others and puts their tools down (armed piece,
  held piece, brush, a town being moved). `terrClose()` is the terrain side.
* **4** Influence draws for the **open town only**; clicking empty map closes
  the town and its area. Layers → Influence cycles *selected → all → hidden*
  (`layerState.inflAll`, class `infl-all`).
* **8** While anything is armed, towns take no clicks (`.dlframe.placing
  .dltown { pointer-events: none }`) so a click in a town places; the frame is
  `user-select: none` (fast clicks were selecting the overlay).
* **7 + 6** Placed tiles are stamps. `tools/dodoland_split_stamps.py` split all
  127 multi-drawing placed tiles into one tile per drawing ("Olive bush 2"…,
  next free number, same settings, art rows moved, placed pieces repointed;
  867 -> 1407 tiles; `MAX_TILES` 1500 -> 3000). Placement now always uses
  `variants[0]`. The squish on hover was the same cause: a piece sized from one
  drawing while showing another of a different shape.
* **10** New tile flag **`spreads`** ("Influence spreads" in the tile editor and
  bulk bar), default = `passable`. Lake water: roads no, influence yes; deep
  water neither. `tile_kind` grow follows `spreads`; influence re-syncs kinds
  from the tiles on every compute and its cache key includes which tiles spread.
  New param `dodoland_influence_water_cost` (2): water costs that many cells of
  ground. Checked: the three placed towns now cover 1.9k-5.3k shallow cells and
  no deep ones.

Left: 1 (LoD / first impression), 2 (place town buildings; walls round the
area), 3 (loading screen + load times), 9 (owned pieces + pointer/hand/pencil/
brush toolbox), 11 (low-res tiles).

### Backlog 3 + 1 — loading and the first impression

* **Loading screen** (`#dlloading` in mappage): a card over the frame with three
  steps — map image, ground picture, towns' areas — and a bar; lifts when all
  three are in, or after 20 s regardless. Influence is requested as the script
  starts, in parallel with the world.
* **Load times.** Every map request was dominated by Atlas round trips (~60 ms
  each). Now: `TerrainStore` caches the world row (5 s trust) and every chunk's
  RLE (until `rev` moves; own writes update it in place); `TileLibrary` caches the
  listing (dropped on any write via `_Watched`, 30 s trust);
  `standing.recent_rows` shares one read of the activity window for
  `dodoland_rows_cache_s` (60) across the map, influence, town art and toolkit
  locks. The cog warms the overview picture and influence for every world at
  `on_ready`. Measured warm: page 0.5 s (was 2.6), picture 0 s, influence 0.06 s
  (was 2.7).
* **The zoomed-out map is a picture** (`helpers/dodoland/terrain_raster.py`,
  `GET …/terrain/picture?v=`, WebP ~650 KB at one pixel per cell, ~3 s to make,
  cached per terrain version in `terrain_api._PICTURES`): water darkens with
  depth, surf along shores, a darker coastline, relief on impassable land, broad
  variation and grain. Params `dodoland_overview_shading` (1) and
  `dodoland_overview_grain` (1). The browser scales it smoothly, so no
  staircase coast below tile zoom; the tile detail fades in from 2.5 to 4.5 px
  per cell instead of popping. The old SVG overview endpoint is kept but unused.

### Backlog 11 — low-resolution tiles

Nothing is upscaled on the map itself (at full zoom a 16 px/cell tile is drawn
at ~0.6x its pixels, Miro art at ~0.2x). The smudge was the **toolkit
thumbnail**: a 6x7 sprite smoothed up to 52 px. Pixel art (every
non-resizable tile) now renders with `image-rendering: pixelated` in the admin
kit, the player kit, the placement ghost and placed pieces (`px` flag in the
toolkit entries). The 30 sprites of 10 px or less (flowers, pebbles, mushrooms,
ivy) are genuine small details of 16 px packs, not broken cuts, so they stay.

### Backlog 9 — owned pieces and the toolbox

* **Ownership.** Every placed world piece now stores `by` (Discord id of the
  session), `by_name` and `at`; pieces from before read as unknown. The map
  payload carries them (`by`, `bn`, `at`).
* **Batch actions** on `POST /api/guild/{gid}/dodoland/decor`: `place_many`
  (≤400 items, each tile checked once, one `insert_many`), `move_many`,
  `remove_many` (world scope only). `DecorStore.place_many/remove_many`.
* **Toolbox** under the zoom buttons: **pointer** (V: click/shift-click select,
  drag a box on empty map — the edited layer only), **hand** (H: pan; click a
  piece to select; drag a selection to move it), **pencil** (P: click to stamp
  the picked tile), **brush** (B: drag to scatter; shift-click several tiles in
  the library for a mix; patterns Scatter / Line / Cluster, radius, spacing,
  size jitter, random mirror; previews while dragging, one request on release).
  Delete removes the selection, Escape lets go. Size / Mirror / Remove act on
  the whole selection. Selection boxes are screen-space, one per piece (≤400).
* **Placed tab** in the toolkit: *Placed by me* / *Everyone's*, newest first,
  name, cell coordinates, layer and placer; click a row to select it and fly to
  it (switching the edit layer if needed); × removes it.
* Verified end to end against a harness whose decor POST writes to an in-memory
  copy (scratchpad `harness/serve.py`): pencil → 1 piece with `by`; a brush
  stroke → 25 pieces in one request; box select → 25; Delete → removed 25;
  hand click-select, drag-move persisted, Escape.

### Backlog 2 — a town's buildings, and walls round its area

* **Build in this town** (town card): the server's building tiles the town has
  unlocked (its building at that tier or higher, from `p.built`), as cards.
  Picking one switches the edit layer to Buildings, arms the pencil and builds
  *for that town*: the place request carries `town`, and the server refuses a
  point outside that town's area (`influence_api.inside`, from the cells kept
  in `_CELLS` alongside the payload). The piece stores `town`.
* **Town buildings no longer block their own town.** Blocked cells now follow
  the tile's `spreads` flag, not `passable` (a road goes round a house; the
  town does not stop at its own door). Building tiles get `spreads=True`
  (existing 90 updated; `add_tile(spreads=)`), and the influence cache key only
  counts pieces that actually block, so placing a building is ~120 ms instead of
  a full recompute.
* **Walls** are a town style, not pieces: `TownStore.save(walls=)` with
  `WALLS = ("", "palisade", "stone")`, set from the card (None / Palisade /
  Stone) via `POST /api/guild/{gid}/dodoland/town {walls}`. Drawn by
  `drawWalls()` (terrain_ui) along the area's **smoothed border** in cell units,
  with towers every 42 (stone) / 54 (palisade) cells; part of the Buildings
  layer; they grow with the area.
* **Smoothed borders.** `influence.loops` (cell-edge loops, holes included,
  corners only) + `ring_path` (two Chaikin passes, loops under 12 corners
  dropped) — ~40 KB per big town. Also used for the influence line instead of
  the stair-step.

All eleven backlog items are done. Still open from the original plan: roads
(step 3), the player-facing building flow on the player page (players placing
their own town's buildings inside their area from `/me`), walkers.

### Step 3 — roads (11 Oct 2026)

`helpers/dodoland/roads.py` (pure) + `web/dodoland/roads_api.py`
(`GET /guild/{gid}/dodoland/roads`, cached per guild, rebuilt when terrain,
plots, road-blocking pieces or settings change and at least daily; warmed at
`on_ready`). Links: pair rows over the standing window between placed towns,
each town's `dodoland_roads_per_town` (3) strongest with at least
`dodoland_roads_min` (3) interactions. A* on a `dodoland_roads_step` (2)
coarser grid: `move` cost, shallows/rivers crossable at `dodoland_roads_bridge`
(6) per step and drawn as plank bridges, deep sea / mountains / road-blocking
pieces (`passable` False — buildings too) impassable, existing road ground at
`dodoland_roads_reuse` (0.35) so roads merge. Strongest links routed first. A
Pillow flood fill refuses towns no road could join before searching. Paths are
string-pulled (80-point window) and Chaikin-rounded. Drawn in `#dltroads`
(Roads layer), `dodoland_roads_width` (2.4 cells). Roads reload when a town is
placed/moved/removed. Live data: one road (40 interactions) across the
continent with 3 bridges, ~3.5 s to compute, cached.

### Earned buildings only, at the current tier (Nik, 11 Oct)

A town builds **only what it has earned, at the tier it has reached, one of
each**: the Build section lists exactly those; a building it already has is
marked *built* and clicking it finds and selects it. The server enforces the
same (`decor_api._town_may_build`). A placed town building is **drawn at the
town's current tier** (`currentTile`), so it upgrades as the town progresses.

### Selecting on the live map (Nik, 11 Oct)

Tested on Nik's own Chrome against the live bot: selecting objects failed
because the edit layer had been left on *Buildings* (by Build-in-this-town),
and every other layer was `pointer-events: none`. Now any visible piece can be
selected (selecting one moves editing to its layer), and a click picks the
nearest piece within 10 screen px — zoomed out, a flower is a pixel.

### Nik's round of 11 Oct (morning)

1. **Map cleared to land and water** for hand drawing: every land kind other
   than Meadow grass (fields, dunes, forest, swamp, hills, mountains) repainted
   Meadow grass (521,768 cells in 413 chunks), and all placed pieces removed (4).
   Backup in the scratchpad `backup_before_flatten.json` (world, chunks, decor).
2. **Ground's Edit opens the Terrain drawer** (Ground is painted, not placed).
   The "bushes on the ground" were four placed objects, now removed; the
   Meadow grass tile itself is clean.
3. **Buildings only from a town's card.** The toolkit never offers buildings
   (Buildings layer edit disabled; a saved edit layer of buildings falls back to
   objects). Each earned building's row in the card has ✎ (rename in place,
   saved through `building_names`) and **Build** — the current tier of that
   town's building, no choice of tier; once placed it says **Built** and finds
   it. Clicking a placed building opens its town's card. Clicking inside the
   open town's own area no longer closes it (`inOpenArea`: the area's fill
   path, `isPointInFill`); only clicking outside does.
4. **Roads off**: `dodoland_roads_on` defaults to False and is not warmed.
5. **The stretching, found on Nik's machine**: the world was laid out at the
   reference image's 958 px and zoomed up to 50x, so a 0.8 px tree had its
   edges rounded to whole layout pixels (0 or 1 px) before the zoom. The world
   is now laid out `WS = 16` times larger and zoomed 16 times less (`kMin/kMax`,
   `--ws` for the few fixed sizes inside it: the town dot), so pieces and halls
   are many layout pixels and the rounding is invisible.

### Town card actions, forest brush, people and animals (11 Oct)

* **Card rows**: an unbuilt earned building has **Build**; a placed one has
  **Move** (the next click inside the town's area moves it) and **Delete**.
  **Remove Town** asks first (naming how many buildings go with it) and the
  server now deletes every piece built for that town
  (`DecorStore.remove_town_buildings`) besides its town-scope decor.
* **Buildings stay inside their area on every move**: `move` and `move_many`
  refuse a town's piece outside its area (`decor_api._outside_area`); a refused
  drag snaps back on the page (`decorPost(..., fail)`).
* **Forest brush** (default pattern): the picked tiles (shift-click several)
  count as one; the brush disc is filled with a staggered, jittered grid spaced
  by their own width times `(1.15 - density)` (Density slider, 75%), each grid
  point taken once per stroke so going over it again does not pile up; strokes
  up to 1,600 pieces, sent in batches of 400. Pieces are drawn back to front
  (sorted by y) so the lower tree stands in front. `MAX_WORLD` 6000 -> 20000.
* **People & animals** (new layer, `.dllife` SVG in map cells above the
  buildings): people walk between random spots inside each placed town's area
  and pause; their kinds come from the town's buildings (`townart.LIFE` by
  building shape) using the town art's own figures; the crowd is 2 to
  `dodoland_life_max` (12) on a square-root of power. A placed zoo
  (`dodoland_zoo_building`, menagerie) holds `dodoland_zoo_animals` (2) per
  tier, wandering inside it. Animated only when a cell is at least 1.2 px and
  the tab is visible. `dodoland_life_on` switches it off.

### Zoo would not build; buildings a quarter size; the hall row (11 Oct)

Found on Nik's Chrome: **Build on the zoo was refused** ("a town builds at the
tier it has reached") because the server scored the town *alone*
(`user_ids=[uid]` with only its rows), and tiers are percentiles of everybody:
alone Beanburg's zoo was tier 6, among everyone tier 3 (what the card shows).
All one-person scoring (town art, toolkit unlocks, the build check) now reads
`standing.recent_standings` — everybody, cached with the shared rows. The town
art's per-town tiers had the same flaw before today.
**Buildings were drawn at a quarter of the hall's scale** (tile box 120 px /
12 px per cell = 8 cells, while the hall's box is 10 x 120/34 = 35 cells), so
their tier growth and smoke were a few pixels. Town building tiles are now
drawn at the hall's scale (`mappage._tile_cells`). The **town hall's row**
shows "Town hall" instead of Build: the placed town is the hall.

**Escape / right click put everything down** (`putDown()` in mappage,
`terrPutDown()` in terrain_ui): armed kit tile and brush mix, Build-for-town,
Move-a-building, moving a town, the terrain brush / eraser / selection, the
piece selection, a half-drawn box or brush stroke — then back to the hand.
Escape works from inside a drawer's field too (it blurs it); the rename field
keeps its own Escape (cancel the rename).

### Effects, flourish on the hall, wheel pan, shallow coast (11 Oct)

* **Placed buildings had never had their tier effects**: the building tiles were
  made from `townart.one_svg`, the bare masonry. New `townart.building_svg`
  composes a building exactly as a town does (tier effects behind and in front,
  topical things, emblem, lifted at tier 6); tiles re-synced (90 updated). The
  town hall uses it too.
* **Nothing rotates any more** (Nik: "those rotating rings were horrible"):
  topical icons that orbited a building now hang beside it and bob (`fxbob`,
  `dlbob`); the tier-6 ring with orbiting motes is replaced by a breathing crown
  of light (`bcrown`); the outer flourish band no longer spins.
* **Flourish on the town hall**: `hall_svg(flourish=, glow=)` draws the owner's
  trial-rank frame (warm ground, lanterns, light bands, motes) sized to the hall.
* **Middle button held pans** from anywhere, with any tool; no autoscroll.
  The hint box is bottom centre (it was under the drawers).
* **The coast is Shallow water** (Summer Plains tile), not Lake water: lake
  cells joined to the open sea and within 16 cells of deep water repainted
  (267,025 cells, 357 chunks); inland lakes and rivers stay Lake water. Backup
  `backup_before_shallow.json` in the scratchpad. Note: the Deep water tile is
  currently set to let influence spread (not set by Claude) — towns can grow
  over the open sea until that is unticked.

### Members on the map: paint in their own area, their own undo (11 Oct)

`web/dodoland/player_map.py`: `GET /guild/{gid}/dodoland/me/map` (player gate,
world page on) serves the same map page with `request["player"]`; every read
it needs has a `/me/w/...` alias (terrain world/defs/picture/chunks/cells,
influence, roads, tile art, assets, town art/picture) through `reader()`, which
sets `dl_base` so URLs the server hands back point at the member's routes.
The page takes its URLs from `D.ep` (base, paint, undo, decor, town, settle).
* **Paint**: `POST /api/.../me/terrain/paint` — the admin stroke, with tiles
  limited to player access (`_env_tiles`) and edits filtered to the member's
  own town's area (`paint_filter` from `influence_api._CELLS`).
* **Undo/redo**: `POST /api/.../me/terrain/undo` — the member's own strokes
  only (`_PUNDO/_PREDO` per guild+user), recorded cell by cell; a cell is only
  put back if it still holds what their stroke left, so an admin's later work
  in the same place is never taken back.
* **Build**: `POST /api/.../me/build` — place / move / move_many / remove /
  remove_many, narrowed to pieces with `town == uid`, same tier/one-of-each/
  inside-the-area rules. Rename and walls go through `/me/town`.
* The page hides the Toolkit, pencil and brush, layer editing (except Ground,
  which opens Terrain), town placing and other towns' controls.
* All 16 painted ground tiles now have Players access (owner can untick).
* The member's town page links to "The map" when the world page is on.

### Moving a town moves what is in it (11 Oct)

`web/dodoland/town_move.move_town` (both the admin settle and the member's own
settle use it): it collects the town's buildings (`town == uid`) and anything
its owner placed inside its old area (`by == uid`), settles the hall, and puts
each piece at the same offset from the new hall. A piece landing where nothing
stands (a kind with no `move`: water, mountains) goes to the nearest open cell
in the new area; one outside the new area goes to the nearest open cell inside
it; the hall dropped in the sea goes to the nearest open ground. Each such
adjustment comes back as a plain sentence (`notes`), shown in a dismissable
notice at the top of the map; the page applies `moved` positions at once.
Checked on a copy of the live data: a small move keeps every offset exactly;
a drop into the sea puts the hall on the nearest shore with both notices.
Members removing their own town now also take its buildings with it.

### Houses back, and a town hall with a square (11 Oct)

* **Ordinary houses** return on the map: each placed town gets the classic
  town's count (`reached // dodoland_people_per_house`, capped by
  `dodoland_max_houses`), drawn with the town art's cottages (6 shapes x house
  colours) at the hall's scale, scattered through its area, thickest round the
  hall, clear of the hall and its placed buildings, seeded by the town's id so
  the layout is stable. They live in the life SVG under the walkers, belong to
  the Buildings layer and stay visible zoomed out.
* **The town hall's square** (`townart._hall_dress`): a paved plaza that widens
  with tier; braziers with flickering flames from tier 2; banners in the town's
  colour from tier 3 (`hbanner`, waving); sparks from tier 5 — on top of its
  tier effects and the owner's flourish. The hall no longer carries an emblem
  medallion (it sat on its flag).

**Square brush** (11 Oct): the terrain brush has a Round / Square switch (above
Size; remembered per viewer). The server rasterises `shape: "square"` as the
full square with the soft edge measured to its rim (Chebyshev distance); the
cursor outline follows the shape. For roads and anything with straight edges.

### Movable houses, drawers beside the card, whose pieces a town takes (11 Oct)

* **Houses can be moved** (never removed): drag one with the pointer or the hand.
  Each house is a number with its own look (seeded by town + number); moved
  ones are stored on the town record (`TownStore.move_house`, `houses.{i}: [x, y]`,
  map %) through `POST …/dodoland/town {house: {i, x, y}}` (admin, any town) or
  `/me/town` (a member, their own), refused outside the town's area; a refusal
  snaps it back. Unmoved houses keep laying themselves out round the moved ones.
  Moving the town shifts moved houses with it; any that would land outside the
  new area or in water return to the town's own layout (and the notice says so).
* **Drawers beside the town card**: with a card open (`body.dlcardopen`) the
  Terrain and Toolkit drawers open at `left: 372px`, beside it, not under it.
* **A moving town takes only its own**: `town_move.carried` — its buildings
  (`town == uid`) and what *its owner* placed (`by == uid`) inside its old area.
  An admin's or another member's piece inside that area stays put, whoever is
  doing the moving. Tested (`test_dodoland_settle`) and checked on a copy of the
  live data.

### Landmarks and Landmark mode (11 Oct)

A **landmark** is a world piece with `locked: true` — the map as its admins set
it up:
* nobody moves or removes it: the admin decor endpoint refuses move/remove of a
  locked piece ("Unlock it first"), the page refuses to drag or delete it, and
  the member build endpoint never touches one, even one built for their town;
* no moving town carries it (`town_move.carried` skips locked pieces, even the
  owner's own);
* members cannot paint the ground under it (`player_map.paint` subtracts the
  landmarks' footprints, `influence_api._blocked(landmarks=True)`);
* generated houses keep clear of it.
Admins lock / unlock the selection with **🔒 Landmark** in the toolkit
(`action: lock|unlock`); landmarks show a blue box with a lock, and 🔒 in the
Placed list. **Landmark mode** (a switch in the toolkit, shown only to the bot
owner and the server's owner): while on, everything placed with the pencil or
the brush is a landmark from the moment it lands (`landmark: true` on place /
place_many). Remembered per viewer.

**Top bar** (11 Oct): Terrain and Toolkit on the left (beside the drawers they
open), the server's name centred, Layers and Towns list on the right. The back
link and the counts are gone.

### Depth: lower on the map is in front (11 Oct)

Every piece (objects and buildings), town hall, house and walker takes its
z-index from where it stands: `depth(y%) = 100 + y% * 100`, so what stands lower
on the map is drawn in front, whatever its layer (Nik: buildings must follow the
same logic as tiles). Flat environment features stay underneath. Houses and
walkers are no longer drawn in one overlay SVG: each is its own element
(`.dlstand`, an SVG in town-art units placed at its ground point by
`standing()` / `stand()`), so they pass behind and in front of buildings
properly; walkers restack every frame as they move. A hovered or open town
lifts above its neighbours so its name stays readable.

**A town catches the mouse only where it is drawn** (11 Oct): `.dltown` is
`pointer-events: none` and only its art's painted shapes (and the zoomed-out dot)
take clicks; glows, auras, beams and sparks let clicks through, and while
placing or painting the whole town does. Checked on Nik's live map: of 12
houses overlapping Beanburg's box, 12 were blocked before and 10 reachable
after (the other 2 are behind the hall's own drawing).

### People reached = individual connections (11 Oct)

Nik: "people reached" ballooned with every raid ping. It counted **pair rows**,
one per person per day, and a ping made one. Now (`standing.guild_standings`):
* `dodoland_reach_counts` "people" (default): each person once over the window;
  "days" restores the old person-days count.
* `dodoland_reach_mentions_alone` (off): a person only ever pinged — no reply,
  thread or voice together — is not reached. Cleans up existing history too.
* `dodoland_mass_ping_at` (4): from now on a message naming that many people
  scores for the room's buildings as before, but its acts carry `link=False`, so
  `store.record` makes no pair row: it connects nobody.
Building points are untouched; only town power's reach part and the reached
count change. On live data the top town goes 1,288 -> 153 people reached (place
unchanged); a few towns move several places. Houses are `reached //
dodoland_people_per_house` (10), so they drop too — Nik to retune (2 keeps
about the old density).

### Shading kept up close
Far out the ground is the overview picture, whose shading (water darkening with
depth, surf, the coast's darker edge, mountain relief) vanished once real tiles
faded in. `terrain_raster.render_shade` draws that shading alone as RGBA (no
variation/grain); `terrain_api.shade_bytes` caches it per terrain version
(`_SHADES`, ~4 s, ~360 KB on live data, warmed at start). Served at
`/terrain/shade` and `/me/w/terrain/shade`; the client lays it in `#dltshade`
above the tiles with the same fade-in opacity as the tiles, so the look is
continuous. `dodoland_detail_shading` (1.0) scales it; 0 turns it off.

### Influence at large reaches
Nik set the strongest town's reach 40 -> 500 and the map crawled: a recompute
took 40 s (search 19 s, fill/line/ring 18 s, 1.26 MB payload), and it ran
inside whatever request came next — every 5 minutes (`_TTL`) and on every
change. Now, with identical areas (checked cell for cell on live data):
* `influence.grow_grid` — the same Dijkstra over a flat cost list built once per
  compute (`influence_api._cost_grid`, `inf` = never) instead of a cost
  callback; about 2x faster.
* `fill_path` and `loops` find runs/border edges in numpy; only the border is
  walked in Python. ~10x faster.
* The stepped `line` is only built when there is no `ring` (the page only uses
  it as a fallback).
* `current()`: when nothing it was made from changed and only the TTL ran out,
  the old areas are served and the new ones made on a thread (`_refresh`, one
  per guild, `_LOCKS`). A real change still recomputes before answering.
Live (top reach 340, 15 towns): 8.3 s total, ~3.5 s of it standings, 760 KB.

### Two kinds of lock
* **Landmark** (`locked`, admin): the toolkit's 🔒 Landmark button / Landmark
  mode. Unchanged: nobody moves or removes it, no town carries it, members
  cannot paint under it.
* **Locked in place** (`pinned`, member level): the 🔓/🔒 button on each placed
  building's row in the town card. Stops a move/drag/delete/mirror until
  unlocked, but it is still the town's: `town_move.carried` takes it along and
  the ground under it can be painted. `decor.set_pinned` never touches a
  landmark and, for members, only their own town's pieces.
* Admins use the same row button: on a locked building it unlocks either kind
  (`set_landmark(False)` clears both); on an unlocked one it pins (`action:
  "pin"`), so an admin can lock a town building without making it a map
  landmark. The toolkit button also unlocks either kind. Members cannot unlock
  a landmark (button disabled, server refuses).
* Refusals: `decor.held()` -> `{id: "landmark"|"pinned"}`, checked by both the
  admin and member endpoints; the page shows pinned selections in amber.

### Breadth: influence for taking part across the server
Nik's idea: reward taking part in as many lively channels as one can.
`helpers/dodoland/breadth.py` (pure) + `influence_api._breadth`:
* A **lively room** for a person: a channel where >= `dodoland_breadth_others`
  (2) *other* people wrote in the last `dodoland_breadth_days` (30), that they
  can write in (`permissions_for(member).send_messages`), and that still exists.
  Built from day rows' `channels.{cid}.message` (a capped day still counts
  as written). Forum posts fold into their forum; uncached/archived posts and
  deleted channels drop out.
* **Breadth** = rooms they wrote >= `dodoland_breadth_min_messages` (1) in /
  their lively rooms; 0 if they have fewer than `dodoland_breadth_min_rooms` (3).
* For **reach only**: power x (1 + `dodoland_breadth_bonus` (1.0) x
  breadth ^ `dodoland_breadth_curve` (1.0)). The largest boosted power sets
  the scale, so the strongest still reaches `influence_top` and no further:
  it reorders who gets large areas, never makes them larger (or slower).
* The town card shows "Talks in N of M lively rooms · reach +X%" from the
  influence payload (`towns[].breadth`).
Live estimate (no permission filter): the top town is also the broadest (40/61,
x1.66) so keeps the top; narrow towns lose most (6/64: 158 -> 129 cells).

Ideas not built (for Nik): bridge-building (talking with people from groups
that do not talk to each other), steadiness (days active of the last 30 over
bursts), reviving a quiet room (first post after N quiet days that draws
replies from 2+ people), back-and-forth (conversations where both sides
reply), welcoming newcomers who then stay a week.

### Second tile batch (NewTileSets, 11 Oct 2026)
`tools/dodoland_import_newsets.py <folder> [--preview out.png]`: 298 tiles
from 7 packs into the **existing** categories (none created; snow went to
Dirt & sand, sand/grass/gravel patches laid on the ground went to their ground
category as objects, like "Stone patch"). Library 1315 -> 1613 tiles.
* Packs: ZRPG Tiles + ZRPG Beach, [LPC] Beach/Desert (only what ZRPG Beach
  lacks: same art), [LPC] Cliffs (pillars, spires, ladder, plain ground only;
  the faces are autotile edges), FreePack, 16oga (packed edge to edge, so cut
  by rectangles), four painted brick textures (shrunk 512 -> 256, cell_px 64:
  each texture spans 4x4 cells; one variant tiles seamlessly in the pattern).
  The "Pixel Art Top Down (1)" zip is byte-identical to step 1b's: skipped.
* One tile per drawing (split-stamp names/sources); ground keeps variants.
* **Scale** chosen per entry against the category's existing art, checked in
  the preview (new beside old at the same px per cell): ZRPG trees/rocks/
  castle 40, ZRPG beach/jungle/LPC 32, ZRPG houses 36, FreePack trees 28
  (oversized fruit/boulders/agave/coral have their own). Broad oak ~4 cells
  wide like Emerald tree; giant oak ~7 (Summer Plains oaks are ~9).
* Settings copied from the category's existing tiles of the same kind.
* ZRPG's painted drop shadows (black, alpha 92) are stripped before cutting.
* Credits: LPC/ZRPG are CC-BY-SA 3.0 / CC-BY 3.0, named in each tile's `pack`.
  `item_imgs/tilesets/` is now actually in .gitignore (it was only untracked).
