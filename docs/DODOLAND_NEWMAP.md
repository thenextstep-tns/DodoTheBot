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

### Forest brush planted nothing
`forestDab` lays a staggered grid whose rows are `0.8 x gap` apart, but chose
which rows to look at in `gap` units, so the rows it looked at drifted off the
brush by `0.2 x y`: fine at the top of the map, nothing below row ~50 (the map
is 1,812 rows). Rows are now found in row units (and one extra column for the
half-step rows). `test_dodoland_page` runs `forestDab` in node at rows 50, 900
and 1,790.

### Painted forests, step 1 (paint, erase, see the trees)
Every brushed tree was a placed piece (a decor row, a DOM element, part of
every map payload). A forest is now **painted, not placed**:
* **Storage** — the terrain store's new `cover` layer (`T.COVER`): which stand
  grows on each cell, 0 = none, same 64x64 RLE chunks as the ground. Stands
  (`helpers/dodoland/forest.py`: mix of tile ids, density, scale, jitter, flip,
  seed from the rest) live in the world row as `stands`, append-only like
  `kinds`; the same settings reuse their stand. A forest across the whole test
  map is 35 chunk rows. Nothing per tree exists anywhere.
* **Endpoints** (`web/dodoland/forest_api.py`): `POST /api/.../forest/paint`
  (full scope; `points`/`radius` rasterised by `terrain_api.stroke_reach`, now
  shared with the ground brush; `erase: true` or the stand; mix tiles checked
  with `decor_api._admin_tile`); `GET .../forest/chunks?r=` (+ member alias
  `/me/w/forest/chunks`) returns the stands and only non-empty chunks.
* **Drawing** (`web/dodoland/forest_ui.py`, spliced into the map script): per
  visible chunk, trees are grown from the cells on a staggered grid spaced by
  the stand's tree width (the old forest dab's formula), tile/size/mirror/nudge
  from a hash of the grid point and seed, then drawn nearest-last onto one
  canvas per chunk (z 3: above ground, below objects and towns). A few chunks
  per frame; the furthest are let go past `dodoland_forest_chunks_max` (200).
* **Settings**: `dodoland_lod_forest` (1.0 px/cell: not drawn further out),
  `dodoland_forest_detail_max` (12 px/cell sharpest), `dodoland_forest_full_at`
  (4: below it only that share of trees is drawn, seed-picked, so zooming in
  only adds trees), `dodoland_forest_chunks_max`.
* The Forest brush pattern now paints this layer (Paint / Erase switch); the
  old tree-by-tree `forestDab` is gone. Scatter / Line / Cluster still place pieces.
Next steps: undo for forest strokes; canopy in the zoomed-out picture; depth
strips so a tree south of a house draws in front of it; turning existing
brushed trees into painted forest; members painting in their area.
* Density re-scaled (Nik): spacing in tree widths runs linearly from
  `dodoland_forest_spacing_zero` (1.95) at 0% to `dodoland_forest_spacing_full`
  (0.95) at 100% — the old 20% is now 100%, the old 0% is 80%. Applies to
  forests already painted (their stored density is read through it).

### Shade where grounds meet
Close up, a thin soft line now runs wherever two different kinds of land meet
(grass on grass, grass on road) — the coast's shading was the only edge before.
`terrainart.edge_path` finds the cell edges between two different non-water,
known kinds (inside the chunk and across its right/bottom borders, so lines run
on over chunk lines); `chunk_svg` draws them as a dark core
(`dodoland_tile_edge_width` 0.12 cells, `dodoland_tile_edge_strength` 0.3) in a
halo twice as wide at half strength. Vector, so thin at any zoom (the coast
shade is a 1px-per-cell picture). Both settings are in the chunk cache key;
`invalidate` also drops the left and upper neighbours of a painted chunk.
0.8 ms per chunk on the live map.
* **Replaced the same day** (Nik: "it should blend one into another, not be a
  hard boundary"): no line any more. `terrainart.blend_edges` groups the border
  edges by the kind that spills (the higher index — never both ways, two
  textures crossed both ways cancel out); `blend_svg` lays that kind's own
  pattern over its neighbour in `dodoland_tile_blend_steps` (8) nested strokes
  out to `dodoland_tile_blend_width` (1.2 cells), opacities chosen so cover
  rises in even steps to `dodoland_tile_blend_strength` (0.9) at the border.
  One path per kind, so corners are not painted twice. The chunks endpoint now
  sends every chunk's fill first and every blend after, so a fade over a chunk
  line is not buried under the next chunk. Checked by rendering real tiles in
  headless Chrome: 1.0-1.5 cells rounds the cell staircase into a slope.
  `dodoland_tile_edge_*` are gone.

### Close-up ground is baked, not vector
The vector chunks (one SVG path per kind, filled with `<pattern>`s, and then
the stroked blend on top) made panning jittery: the browser re-rasterises
vector work on every move. Now (`terrain_ui.py`, "the close-up ground, baked"):
* `GET .../terrain/rle?r=cx0,cy0,cx1,cy1` (+ member alias) sends each chunk's
  RLE and, per kind, `{fill, layout, land}`; `terrainart.pattern_layout` is the
  old `tile_pattern`'s 4x4 variant block (same `_pick`), so textures sit where
  they always did.
* The page bakes each visible chunk into a canvas: per kind, a world-aligned
  `CanvasPattern` of its block fills its cells. Blend: for each land kind that
  outranks a land kind in the chunk (the higher spills, as before), its shape
  over the chunk plus a margin of neighbours' cells, grown by `width` and
  blurred once (`ctx.filter`), masked to the lower land kinds, filled with its
  texture, drawn at `blend_strength`. No canvas filter (old Safari): hard edges.
* Shown as an SVG `<image>` (blob URL) in `#dltdetail`, so it stays under
  shading, influence, roads and walls; 64.04 cells wide so there is no seam.
  3 chunks baked per frame; detail tiers 2/4/8/16 px per cell
  (`dodoland_ground_detail_max` 16); `dodoland_ground_chunks_max` (300) kept.
* A stroke/undo's `touched` chunks are re-read and they and their 8 neighbours
  re-baked (`bakeTouched`); nothing else is.
* Gone: `terrain/chunks`, `terrain/defs` (+ member aliases), `pattern_defs`,
  `tile_pattern`, `pattern_id`, `chunk_svg(textured=)`, `blend_edges`,
  `blend_svg`, `dodoland_tile_blend_steps`. Blend defaults a touch less washy:
  width 1.2 -> 0.9 cells, strength 0.9 -> 0.85. Checked in headless Chrome
  with the real bake code on real tiles.

### Next up (agreed 11 Oct 2026, not started)
**Smooth borders in the bake**, two checkable steps; the grid stays the truth,
only the picture is smoothed.
1. Smoothed outlines: per chunk (with neighbour margin), marching squares on
   each kind's region -> polygon with diagonal corner cuts -> a couple of
   Chaikin rounds (as `influence.ring_path`). Draw in rank order: lowest kind
   fills the chunk; each higher kind k fills smooth(cells with kind >= k), so a
   rounded-off corner shows the neighbour, not a leftover stair (three-way
   corners approximate). Blend fades along the smoothed edge. One panel setting
   for strength, 0 = today's square cells. Land grounds and roads first; coasts
   left as they are.
2. Smoothing per stroke: the terrain brush gets a Smoothing slider (0 sharp ..
   full) written into a new small grid layer next to the ground; outline
   vertices next to sharp cells are not cut, so plazas/markers keep corners
   while roads curve. A "smoothing only" brush mode changes it without
   repainting ground. Undo/redo (admin snapshots and members' cell history)
   carry it. Unset cells use a panel default ("smooth").
**Still to check on the live bot after a restart**: painted forests (paint /
erase, sparser density), the baked ground and its blend (jitter gone?).
Painted-forest follow-ups: undo, canopy in the overview, depth strips,
converting existing brushed trees, members painting in their area.

### Painted forests stack with walkers (depth strips)
Walkers walked over every painted tree: a forest chunk was one canvas at z 3.
Now each chunk's trees are drawn in strips `dodoland_forest_strip_cells` (2)
deep by trunk position, each strip a canvas with `z-index: depth(lowest trunk)`
like pieces and walkers; `.dlforest` is `display: contents` so the strips stack
among them (far-out hiding is the `.far` class, so the Layers switch still
works). A walker is at most one strip wrong.

### Smooth borders, step 1 (done)
In the bake (`terrain_ui.py`, `bakeChunk`), with a margin of at least 3 cells of
neighbours so curves carry over chunk lines: non-land kinds fill exact cells;
land kinds go lowest rank first — the lowest fills all land, each higher kind k
fills the smoothed outline of (land kinds >= k), clipped to land (coasts stay
square); each kind's blend is grown and blurred from the edge it was drawn
with and kept to land. Outline: `bakeHalf` (half-cell grid, bridges where two
cells touch only at a corner, so a diagonal road is one shape) ->
`bakeLoops` -> `bakeSimplify` (Douglas–Peucker, `dodoland_ground_straighten`
1.5 cells x strength: regular stairs run straight; at 1.8 a 2-over-6-down
staircase is one straight edge) -> `bakeRound` (corners rounded by a fixed
distance, never more than half a side, so a big plaza keeps its sides).
`dodoland_ground_smoothing` (1; 0 = the square cells exactly as before).
2-4 ms per bordered chunk in Chrome (0.4 ms plain), once per chunk.
Step 2 (per-stroke smoothing, sharp corners on demand) is next.
* **Smoothing covers every kind** (Nik): water and coasts too. Leaving water
  out showed its bug on a lake island: the lowest *land* kind (grass) filled
  under all land, so the island's rounded corners showed grass. Now every
  known kind ranks and fills smooth(kinds >= k), so a rounded corner shows the
  ground actually under it; both rank orders checked in Chrome. Blends stay
  land into land, kept off the water by the smoothed land outline.
* **Coast shading follows the smooth shore** (Nik: "the shader is still
  pixelated"). The close-up overlay's coast terms (dark land edge, surf) were
  one cell wide, so they kept the old stairs. `terrain_raster.render_shade`
  takes `coast=False` for the overlay (`shade_bytes`; depth and rock relief
  stay; the zoomed-out picture keeps everything), and the bake draws both from
  the smoothed water and land shapes as blurred masks (`coast_width`,
  `dodoland_coast_shade_width` 1 cell; strength = detail x overview shading).
  Masks come from actual water / land cells, not "not land", so the map edge
  and unread neighbours get no rim.
* **Second pass** (Nik: "something is off"): (1) a pale crescent under a lake
  island — the fills, the blend and the coast each smoothed their own outline,
  so one shore came out as several slightly different curves. Now each chunk
  bakes on a canvas `m` cells larger than itself; per kind one shape; a land
  mask is drawn by replaying the very same fills (land white, water cleared),
  and blends and coast shading use that mask, so they meet the fills exactly;
  the chunk is cut out at the end. A blend spills only from land (`isLand &&
  v >= k`), never from a lake's shore. (2) Douglas–Peucker made islands into
  faceted polygons; Taubin smoothing kept stairs (it preserves low
  frequencies). Now `bakeResample` (half-cell spacing) + `bakeGauss` (Gaussian
  along the outline, sigma = `dodoland_ground_straighten` cells x strength,
  relabelled "smoothing reach"): organic shapes stay organic, a 1-over-1-down
  stair is within 0.00 cells of straight, a plaza keeps 96% of its size.

### Placed things are clickable only where painted
Like the town hall (inline SVG, `visiblePainted`), but for every placed piece,
whose `<img>` took clicks over its whole rectangle (transparent corners,
glows, soft shadows). `mappage.paintedAt` reads each picture once into a
256px alpha map (`alphaMaps`, keyed by src) and asks the pixel under the
pointer; below `dodoland_hit_alpha` (96 of 255; 0 = the whole rectangle, as
before) the press is not the piece's. `pieceHit` walks
`document.elementsFromPoint` past it: the first painted piece beneath takes
it, a town or house gets it re-dispatched (`passOn`), otherwise it bubbles on
to the map (pan, tools). Hover outline and cursor follow the same test.
Checked in headless Chrome with overlapping pieces, a glow and a town.

### The entrance page is a three-step welcome (12 Oct 2026)
`/guild/{gid}/dodoland/me` (`player.my_town_page`) was the whole old member
page: standing tiles, the climb of every building, flourish, the decoration
catalogue with its size slider, who-you-reached, a customise form. Now it is
only: 1. name your town, 2. pick a picture (previewed as the flag at once,
oversized refused before upload), 3. one building shown growing (`_example`:
`dodoland_entrance_building`, blank = the town hall, else the most tiers;
`dodoland_entrance_stages` evenly spread tiers, always first and top, drawn
inline with `townart.building_svg` in one shared crop `_crop` from the
measured `_TIER_REACH`), then one big button. The button: **Place my town!**
→ `/me/map?place=1` (map arms the member's own placement) when members may
settle and the town has no plot; **Go to my town** → `?mine=1` (map centres
on it after `fit()` and opens its card) when it has one; **Open the map**
plus a note when an admin places towns; **Save my town** when the map is
closed. It saves only what changed, then navigates. The page no longer reads
the standings snapshot at all (no `snapshot()`, no town drawing), so it is
cheap. Every text is in `helpers/dodoland/page_texts.py` (old keys replaced),
edited in the panel under *What members can see → Texts on the entrance
page*. The decor toolkit API (`/me/toolkit`, `/me/decor`) still exists; only
the page's catalogue went. `player.my_town()` stays (tests use it).

### Members: founding rule, toolkit, picture limits, population (12 Oct 2026)
* **Founded on open ground.** `player.api_my_settle` refuses a spot inside any
  other town's area (`influence_api.claimed_by(..., but=uid)`); its own area
  is fine, and it may grow into neighbours later. The map shows the refusal as
  a notice and stays armed. Admin placement is not restricted.
* **Member toolkit.** The Toolkit button shows for members. Their kit is every
  placed tile with *player* access (`assets[].pl`), dimmed with a reason where
  not unlocked (`lk`, `why`, from `tile_rules.unlocked_for` on the viewer's
  standing). `player_map.build` takes `place` / `place_many` of non-building
  tiles through `_decorate`: player access, unlocked (`_unlocked`, cached 60s),
  inside their own area (a brush stroke keeps what landed inside), and under
  `dodoland_member_pieces` (default 150, counting their buildings;
  `DecorStore.town_count`). Pieces are stored with `town = uid`, so the
  existing move/remove/lock rules and town moves carry them. On the page
  `mayTouch(p)` stops members selecting anything but their own unlocked pieces;
  the Landmark button, the who-placed filter and the Forest brush are admin-only.
* **The toolkit showing behind a card** was CSS: `body.dlcardopen` moved the
  drawers right by 372px, which un-hid a *closed* drawer narrower than that.
  Now only an open drawer moves, and a closed one is `visibility: hidden`.
* **Pictures.** `towns.sniff_image` reads the type from the bytes (PNG, JPEG,
  GIF, WebP) and stores that, not the claimed type; `dodoland_picture_max_kb`
  (default 1024) via `towns.picture_limit`, on both the member and admin save
  paths; the pages check type, extension and size before uploading.
* **Population** on a town card: the tiles its area covers (`influence` towns
  `cells`) × `dodoland_population_per_cell` (default 1); filled in when the
  areas arrive (`refreshPop`).

### Slowness after the tunnel: the activity read (12 Oct 2026)
The panel now runs on the laptop, so every read of the activity window (~20,000
rows from Atlas) crosses the internet, ~4s. The profile of `/me/w/town/{id}/art`
was all pymongo. `standing.recent_rows` cached it for 60s, but on expiry the
next caller waited for the read, and a map asking for a dozen town drawings at
once made a dozen reads. Now: single-flight per key (`_lock_for`), and past
`dodoland_rows_cache_s` the old rows are served for up to
`dodoland_rows_stale_s` (default 1800) while one background thread re-reads
(`_refresh_rows`). The map page (`_collect`), the member snapshot and the
influence layer now use `recent_standings` (shared, read-only) instead of
re-scoring with `guild_standings`. Test: `test_dodoland_rows_cache.py`.

Map work no longer DMs the owner: `_record_change(..., notify=False)` for decor,
terrain and forest edits (still in the audit log).

### Hidden for now (12 Oct 2026)
* Town walls on the card: behind `dodoland_walls_option` (default off,
  `D.sizes.walls`); walls already chosen are kept and still drawn.
* The terrain palette's Eraser card is gone (the internal erase used by a
  selection's Clear stays).
* Terrain's Select and Pattern tools are hidden for everyone; with only the
  brush left, the tool row (`#dlttools`) is hidden. The code is still there.

### Walls back: shared, open at the shore, drawn raised (12 Oct 2026)
* `dodoland_walls_option` is on again (the card's None / Palisade / Stone).
* Where walls stand is worked out on the server with the areas
  (`influence_api.walls`, cached on `id(_CELLS)` + the choices, sent as
  `walls` in the influence layer): every walled town's **land** is one
  territory, each cell owned by the biggest walled town covering it, and
  `influence.wall_runs` walks its border keeping the edges whose outside is
  not water or off the map. So walled towns that overlap share one outer wall
  and none runs through the overlap (which is inside both areas, so both
  build and paint there), and a wall stops at the shore. Runs are open paths
  in cell units, Chaikin-smoothed with their ends kept; the style changes
  where the owning town does. The water grid is `_WATER`, built in `compute`.
* Drawn raised like the map art (`terrain_ui` `drawWalls`): shadow, the path
  repeated upward as the face (stone courses / wooden stakes), the top, then
  battlements or pointed tips; towers (`towerSvg`: round stone with merlons,
  square wooden with a roof) along each run and at its ends, none within six
  cells of another, nearer ones drawn last. Walls sit in the terrain SVG
  under placed pieces; they are not depth-sorted against buildings yet.
* Choosing walls on the card re-reads the influence layer.

### Gates, stacking, unbroken areas, members customise (13 Oct 2026)
* **Areas ignore placed things** unless `dodoland_influence_pieces_block` is on
  (default off): `compute` passes no blocked cells, so a cottage or pond no
  longer punches a hole in a town's area. Roads still go round pieces.
* **Gates.** The card's walls section has *Add a gate* / *Remove a gate*; the
  next map click (`gating`, `gateAt`) posts `gate_add` / `gate_remove` to the
  town endpoint (admin `api.py`, member `player.api_my_town`), which calls
  `influence_api.gate_edit`: snapped to the nearest point of the town's own
  wall (`_raw_walls`, within 5 cells), at most `towns.MAX_GATES` (12), not on
  top of another; stored as `gates: [[x%, y%]]` (`TownStore.set_gates`).
  `walls()` = `_raw_walls` then `cut_gates` (radius `dodoland_gate_width` / 2,
  default 4 cells), which also returns each opening's ends; the page draws a
  gateway (arch or plank doors, raised) and always two towers, set back 1.3
  cells along the wall. The response now has `walls` and `gates`.
* **Stacking per piece** (`stack`: flat / stand / top, "" = layer default:
  environment flat, else standing): `DecorStore.set_stack`, action `stack` on
  the admin decor endpoint and the member build endpoint (own pieces only).
  Toolkit foot: *Flat · Standing · On top* for the selection; `stackZ` is the
  one z-order rule (flat 2, standing `depth(y)`, top 10200 + depth). Fixes a
  pond drawn over a tree. A per-tile default is not built yet.
* **Members customise** their own town from its card (*Customise your town*,
  the same editor, saving through their own route), and get the pencil/brush
  shortcuts now they have the toolkit.

### Redrawn art replaces a category's pictures (13 Oct 2026)
`tools/dodoland_replace_tile_art.py "<category>" <folder> [--write]`: each PNG
(named after the tile, `castles-1.png` = "Castles 1") becomes the tile's only
picture, as a new variant (new address, so no stale cache); placed pieces are
moved to it; `cell_px` is scaled so it is drawn the same width as before
(`--cell-px N` overrides); old pictures go to `logs/tile_art_backup/<cat>-<time>/`.
The tile keeps id, category, layer, access, resizing. Done for
**Map art · Castles** (7 hi-res pixel castles from `DodoArt/art_batches/mapart/
hires/castles`; nothing was placed yet). The toolkit's thumbnails now carry
`?v=<first variant>` for the same reason.

### Smart ground: tilesets that pick their own edges (13 Oct 2026)
* **Import:** `tools/dodoland_import_autotiles.py <folder> [--write]` takes every
  `*_tileset` folder (its `128x128` files: 01-09 the 3x3, 10-13 extra centres,
  14 the single tile) and makes one paintable environment tile per set in the
  **Smart ground** category (new: these draw differently from every other
  ground). Pictures are stored centre first; the tile row's `autotile` field
  (`{center: [vids], edges: {top_left...bottom_right}, single}`) says which is
  which. Re-running replaces a set's pictures on the same tile. Lake water and
  shallow sea water are closed ground that towns spread over (water: walls stop
  there); lava and the abyss are closed; the rest open. 21 sets imported from
  `DodoArt/art_batches/tilesets`.
* **Drawing** (`terrain_ui`, in `bakeChunk`): `terrain_rle` sends `auto` per
  smart kind (and a plain layout from its centres only). The ordinary bake sees
  under a smart cell the ordinary ground beside it (`autoUnder`), so it runs on
  under the edge tiles' clear margins; then `autoDraw` draws smart grounds
  lowest kind first, each carried one cell under a higher one's border.
  `autoTile(n, e, s, w)` per cell: centre (or a variation, per N x N block,
  `dodoland_autotile_variation` 0.25), edge or corner from the 3x3, the single
  tile alone; strips and their ends from the outer bands of both edges. A tile
  spans `dodoland_autotile_cells` (2) cells: inside follows the world N-grid,
  a border shows the outer 1/N band of its edge tile. `dodoland_autotile_inset`
  (0.03) trims the pictures' own frame, which otherwise reads as a grid. No
  smoothing or blending for smart ground. Test: `test_dodoland_autotile.py`.
* Which smart ground is on top where two meet is the kind order (the one first
  painted in this world is lowest). Not tweakable yet.
* **Blended, no grid (13 Oct, later):** `autoDraw` now draws each smart ground
  in three layers: its tiles (`autoProc`: trimmed and made seamless along their
  axis by the half-shift blend: centres both ways, top/bottom edges along x,
  side edges along y), a seamless texture from its centre laid from the world
  origin with variations faded in per N x N block (`autoSoft`), and a mask,
  whole inside, blurred across the border cells by `dodoland_autotile_blend`
  (0.5 cells). The texture goes over the tiles through the mask, only where the
  tiles are opaque. A lower ground under a higher one's border is now drawn as
  plain inside, so its own fringe no longer shows through the higher's clear
  edge (the "grass did not change when wheat went next to it" bug). Bake margin
  at least 4 cells so the blend carries over chunk lines.

### Uploaded building art beside the generated (13 Oct 2026)
* `tools/dodoland_import_building_art.py <guild> <folder> [--write] [--map folder=key]`
  stores each `tier_<n>_*.png` (full resolution; `64x64` ignored) on that
  building tier's tile as `uploaded` (its own art row, not in `variants`, so
  `building_tiles.sync` rebuilding the generated drawing never drops it).
  `FOLDERS` maps the DodoArt/buildings folders to building keys. 78 uploaded for
  ESO For Dodos (13 buildings x 6). `museum` matches no building (left out);
  Town Hall (moot) and The Wayshrine have none and keep generated art.
* **Building artwork** (`dodoland_building_art`: generated / uploaded, in *What
  members can see*) picks what the map draws. `mappage.uploaded_art` gives each
  uploaded tile `(vid, width in cells)`: per building, the top tier's sqrt(area)
  = 60% of its generated box x `dodoland_uploaded_building_scale` (1.0), lower
  tiers in proportion. In uploaded mode the asset's `vw`/`wc` and every placed
  piece's `v` use the uploaded picture (`pieceVariant` covers pieces placed
  during the session). The tile image routes serve `uploaded` as one of the
  tile's own pictures (admin `?v=`, member `/me/asset/<tile>/<vid>`: the
  member side reads no query). The entrance page's growing building uses the
  uploaded tiers when every stage shown has one.
* **Towns drawn by painted pictures (13 Oct, later):** with uploaded art,
  `mappage.pictured_towns` gives each town `hall_art` (the town hall
  building's uploaded picture at the town's tier) or else `hall_piece` (its own
  painted building nearest its plot, within `dodoland_uploaded_hall_reach`, 6
  cells); the page then draws no generated hall (`.dltown.pictured/.bypiece`)
  and flies the town's flag (`flagHtml`, `.dlflag`) from the top of that
  picture. Neither: the generated hall stays. Town Hall has no uploaded art on
  ESO For Dodos, so towns take their nearest painted building.
  `dodoland_uploaded_building_sizes` ("menagerie=0.6, tavern=1.2") sizes single
  buildings on top of the overall size; each placed piece still has its own
  Size slider.

### Admin side locked to the bot owner (13 Oct 2026)
`web/dodoland/__init__.py` `OWNER_ONLY = True`: every `configure`/`full`
DodoLand route (the page, the map, every reader and every write: settings,
buildings, terrain, forest, decor, towns, settle, backfill) takes the bot
owner's scope, so a server's owner and its admins get 404; the DodoLand menu
item follows it (`routes._dodoland_scope`). The tile library was already the
owner's. Members' own pages (`/dodoland/me…`, `/towns`) are unchanged. There
are no DodoLand Discord commands. To give the panel scopes back, set it False.
Test: `test_dodoland_owner_only.py` (all 28 admin routes, through the real gate).

### Stutter: the ground bake (16 Oct 2026)
Measured with real chunks round Beanburg in headless Chrome (the page's own
`bakeChunk`): 30-65 ms a chunk on average, up to ~350 ms, three chunks a frame,
and smart ground 85-95% of it. Now: smart ground's scratch canvases are reused
(`autoScratch`) instead of made per kind per chunk; its blend mask is drawn and
blurred at 4 px a cell and scaled up; its inside is one pattern fill of a path
(only border cells draw tiles one by one); the texture block is cached. Result:
5-25 ms a chunk typical. `terrDetail` bakes nearest the view's middle first,
within `dodoland_bake_budget_ms` (8) a frame, at least one chunk. Next if it
still hitches: bake in a worker (OffscreenCanvas). The benchmark is a scratch
tool (bake_bench.py), not in the repo.
* **No more pictures for chunks (16 Oct, later):** the 1-second freeze at a
  change of detail was every visible chunk being re-encoded (`toBlob` PNG),
  decoded and swapped into the one big terrain `<svg>`, which redrew with each.
  Now the terrain layer is two svgs with `#dltdetail` between them as an HTML
  div: each baked chunk's canvas is shown directly (`bakeShow` positions it in
  percent of the world and `replaceWith`s the old one, so no flash). Memory is
  bounded by `dodoland_ground_memory_mb` (256) as well as the chunk count;
  on-screen chunks are never dropped. Measured: encoding alone was 110-160 ms
  worst frame for 30 chunks, so the svg redraw/decoding was the rest.

### Cozy pass: muted ground and baked shadows (16 Oct 2026)
* **Muted ground** (`dodoland_ground_contrast` 0.85, `_saturation` 0.92,
  `_midtone` 0.45, `_tint` #d8b98c at `_tint_amount` 0.06):
  `terrainart.mute_rgb` / `mute_settings`. Server side it mutes the palette
  (`terrain_api._colours`) and every kind's flat colour (`_muted_kinds`) for
  the zoomed-out picture, the overview and the rle `fill`s (the picture's cache
  key includes the settings). The page's `groundMute` applies the same per
  pixel, once, to each texture as it is prepared (`bakeBlock`, `autoProc`).
* **Baked shadows** (`dodoland_shadow_strength` 0.38, `_contact` 0.4, `_lean`
  0.6, `_length` 0.42, `_blur` 0.035): `shadowFor` makes, once per picture (and
  mirror), a small blurred, sheared, flattened silhouette plus a contact
  ellipse at its lowest painted row, as a WebP blob; `addShadow` puts it behind
  the picture (`img.dlshadow`, z-index -1). Every standing piece (not flat) and
  a town drawn by its hall's painted picture get one. Nothing per frame.
  Forest-brush trees and generated SVG towns have none yet.
* **One sun, and nothing floats (16 Oct, later):** `sunState()` (page) from
  `dodoland_time_of_day` (auto = each viewer's clock; or morning / noon /
  afternoon / evening / night), sunrise/sunset hours: shadow direction swings
  left (morning) to right (evening), always behind (`y < 0`), longest near
  sunrise/sunset (`_shadow_length` at noon up to `_shadow_longest`), softer at
  dawn/dusk, a faint moon at night (`_shadow_night`); half-hour steps, and a
  minute's check redoes every shadow when it moves (`shadowed`, forests via
  `forestRedrawAll`). `shadowFor` now measures height per column from that
  column's lowest painted pixel (a paved yard casts nothing; the old global
  base made iso buildings float), draws a line per column away from the sun,
  blurs it, and adds a thin contact rim (no ellipse). Shadows now on placed
  pieces, painted halls, generated town art (`svgPicture` of its SVG), houses
  and walkers (`standing`), and forest trees (drawn onto their strip canvases
  first). `dodoland_shadow_lean` is gone (the sun decides).

### Night, lights and lit windows (16 Oct 2026)
* **Night** (`nightState`, same clock as the sun): dusk from 45 min before
  sunset to an hour after, dawn from an hour before sunrise to 30 min after;
  `dodoland_night_darkness` (0.62), `_night_colour`, `_dusk_colour`.
  `drawNight` paints one half-resolution canvas over the frame (`.dlnight`,
  z 6): the night, `destination-out` light pools and lit windows, then a warm
  `source-over` glow. Only at night, at most once a frame (`nightSoon`, from
  `apply()` and every minute).
* **Lights are a tile setting**: `light_radius` (cells, 0 = none, up to
  `MAX_LIGHT` 40) and `light_colour` on every tile, in `EDITABLE`, validated in
  `_props`, defaulted in `_complete`, edited in the tile library ("Light").
  The map gets `lr`/`lc` per asset. `tools/dodoland_lights_category.py` made the
  **Lights** category and moved Lamp post, Lantern pedestal, Oil lantern (warm
  #ffc46b), Wall torch, Fireplace, Campfire (fire #ff9a3c) into it, lit.
  `dodoland_light_glow` (0.35) is how warmly they tint what they light.
* **Lit windows**: `windowsOf(src)` finds a picture's warm bright pixels once
  (`dodoland_window_min_red` 205, `_min_green` 130, `_warmth` 75) as a mask
  and a blurred halo; at night they are cut out and glow
  (`dodoland_window_glow` 0.8) on placed pieces, painted halls, generated
  towns and houses, but **only in towns that are lit** (active lately), so a
  dark window is a quiet town. Walkers carry no light yet.
* **Lights are lights (16 Oct, later):** `windowsOf` now groups warm pixels
  into patches and keeps one only if it is small (`dodoland_window_max_size`,
  0.6% of the picture) and brighter than its surroundings by
  `dodoland_window_contrast` (45): a thatched roof or straw no longer glows,
  while lanterns, fires and windows do; the colour range reaches deeper orange
  (min red 200, green 100, warmth 80). Every kept light also throws its own
  pool (`dodoland_window_spill`, 6x its size), like a placed lamp. People out
  walking carry a lantern (`dodoland_walker_light`, 1.6 cells; animals none),
  redrawn each frame from a per-view cache (`nightCache`, `nightSoon(true)`),
  and the night is lifted off town name labels.

### Activity written behind the bot's back (16 Oct 2026)
Every counted act was up to three Atlas round trips made inside the Discord
event (from the laptop, 100-300 ms of the bot's event loop per message). Now
`cogs/dodoland.py` only queues (`helpers/dodoland/writer.py`,
`writer_for(bot)` -> `bot.dodoland_writer`, made once, survives a cog reload);
one daemon thread wakes every `dodoland_write_batch_seconds` (2), drains the
queue, sums acts that differ only in amount (same guild, person, metric, room,
partner, link, day) and calls `ActivityStore.record(amount=...)` once per sum;
`flush()` on exit (`atexit`). Exactness: the per-pair cap now clips like the
daily cap (`_bump_pair` returns how many are under it; `record` scores
`min(pair allowance, daily allowance)`), so batches score exactly as acts one at
a time (single acts unchanged). Test: `test_dodoland_writer.py` replays a burst
past both caps both ways and compares every row and pair. Days are stamped at
queue time, so a batch spanning midnight is right. Needs a full restart (store.py
is a startup helper).

### Lights editor (16 Oct 2026)
`/dodoland/lights` (owner-only, linked from the tile library; `?tile=<id>`
preselects): `web/dodoland/lights_ui.py`. Pick a tile from a searchable,
category-filtered grid; its picture is shown large with the map's own night
over it. Double-click adds a light, drag moves it, click selects it; per light:
colour, radius (map cells, previewed at true scale from the tile's width in
cells, `mappage._tile_cells` / `uploaded_sizes`) and intensity (0-2), Delete
removes it. Drawn and painted (uploaded) pictures have their own lights.
"Also find lit windows automatically" is per tile. Autosaves (debounced) via
`update_tile`. Model (`helpers/dodoland/tiles.py`): `lights`, `uploaded_lights`
(`[{x, y, colour, radius, intensity}]`, x/y as fractions of the picture,
`clean_lights`, max `MAX_LIGHTS` = 16), `auto_lights` (default on). The old
single `light_radius`/`light_colour` reads as one light at (0.5, 0.25);
saving points sets `light_radius` to 0. The map sends `gl` (the points for the
picture it draws) and `al: false`; `drawNight` places each point on the piece's
picture, mirrored with a flipped piece and scaled with it.

### Night fixes, twilight colours, editor shows found lights (16 Oct 2026)
- Shared JS `web/dodoland/nightlights.py` (`findLights`, `skyAt`, `hexRgb`,
  `PIECE_FOOT`), included by the map and the lights editor: both find and draw
  lights the same way.
- "Daytime rectangles" were town name labels cutting their box out of the night
  while invisible (opacity 0 until hovered). Names are cut only while showing
  (computed opacity), redrawn on hover and on the names button.
- Pools of hand-placed lights fall on the ground at the piece's foot (0.85 of
  its height; a town lot's ground line), as the old single light did; the core
  stays where the light was put.
- Lights found inside pictures fade with the picture's on-screen width
  (`dodoland_night_detail_from`/`_to`, 12-40 px); lit far-off town dots glow.
- findLights merges lights closer than `dodoland_window_merge` (0.08 of width)
  and keeps the strongest `dodoland_window_most` (6): a painting had 67.
- Dusk/dawn: `dodoland_dusk_colours` (pink, purple, violet, night blue),
  `dodoland_dawn_colours` (night, violet, warm orange), `dodoland_twilight_tint`,
  `_spread` (sun's side lags: west pinker at dusk, east oranger at dawn, as a
  horizontal gradient), `_hours`. Replaces `dodoland_dusk_colour`.
- Drawn towns: each `.lot[data-building]` takes its tier tile's lights through
  `getScreenCTM` (tile picture coords -> lot coords: x*120-60, y*78-64); a tier
  with auto off cuts its lot's box out of the town's found-light mask. Assets
  carry `gd`/`wd` (drawn lights/width) for tiers shown as paintings. Pictured
  halls take the hall tile's `gl`.
- Editor: panel colours (readable list in both themes, grouped by category,
  Town buildings first), dragging works (the pressed dot is no longer rebuilt
  under the pointer), found lights shown as dashed rings with "Light them on
  the map" (= auto_lights) and "Make them mine" (turns them into own lights,
  auto off; clicking a ring does the same), Night/Dusk/Dawn/Day previews.

### Lights editor is a dialog on each tile card (16 Oct 2026)
The standalone `/dodoland/lights` page with its tile grid is gone. Each placed
tile's card in the owner's tile library has a Light row: "💡 Edit lights" and a
summary (`lights_ui.light_summary`); the old light_radius/colour inputs are
gone (the model keeps them for old rows). The button opens `#lxdlg`
(`lights_ui.dialog_html`, included only on the owner's page), which loads the
tile from `GET /api/dodoland/lights/{tile_id}` (`api_tile_lights`, owner) and
saves through `update_tile`. A light's pool is centred on the point again
(y + 0.15 r), on the map and in the editor; the foot anchoring is removed.

### Ground bake rewritten: dual grid, smooth and cheaper (17 Oct 2026)
The close-up bake (terrain_ui.py) no longer traces and Gaussian-smooths
outlines, blurs blends and coasts, or lays smart ground cell by cell. Every
ground is laid at the cell corners (dual grid): a corner's four cells give an
index 0-15 (bits 1 up-left, 2 up-right, 4 down-right, 8 down-left, of cells
holding this ground or one drawn after it) and the corner gets that one of 16
shapes (`dualAt`: bilinear between the four cells, threshold 0.5 - a lone
corner is a rounded tip, three an inner curve; diagonal pairs joined by a band
so diagonal roads stay one road). `dualTiles(k, res)` makes the 16 masks
(edge feathered by `dodoland_ground_feather`) and, for smart grounds, 16 fringe
tiles sampled from one cell of the top edge tile's outer band (made seamless)
by depth from the edge and position along it (`dodoland_ground_fringe` deep,
max 0.5 cell). `bakeChunk`: grounds ordered plain-then-smart by rank; the
first fills the chunk directly; each other works in its own box on a scratch
layer: interior corners as rect runs, edge corners stamped, `bakeFill` (texture
source-in; smart ground's seamless centre `autoBlock` + variations only where
it is), fringe source-atop, composited. Margin is 1 cell. Removed settings:
ground smoothing/straighten, tile blend width/strength, coast shade width,
autotile blend (shore surf now comes from the tilesets' own fringe).
`bakeWarm` runs during loading (new card step "Preparing the ground"): fetches
the kinds via `rle?r=0,0,0,0`, loads every ground's pictures and makes every
ground's textures, blocks and dual tiles at every detail level in budgeted
slices. Same test chunk, headless CPU, warm: old 53/29/22 ms (res 16/8/4),
new ~21/11/8 ms; the ~70 ms first-meeting cost is moved into loading.

### Pictures kept in memory, read off the loop (17 Oct 2026)
Profiling the live map (Nik's log, /guild/.../dodoland/map): ~240 picture
requests each did one or two blocking Atlas round trips (~70-125 ms) on the
bot's event loop - 21 of them froze the bot 2.6 s; the full load took 25 s.
`TileLibrary.art` now keeps picture rows in an LRU (`art_cache_mb`, set from
`dodoland_art_cache_mb`, default 128; a picture never changes under its vid;
removed ones are forgotten); `peek(tile_id)` reads the in-memory listing (used
by `visible`, so a picture request needs no tile round trip); `picture(tile,
guild, want)` is the one way to pick a tile's picture. Routes read off the loop:
`assets_route.picture_response` (panel and member asset routes), tiles_ui
`_off_loop` (tile library art). `first_art` removed. Test:
test_dodoland_pictures.py. Also measured: the map page itself is ~0.5 s warm /
2.9 s cold to build (DB round trips in _collect), and terrain/world 0.3-2.4 s.

### Life on the map: horse, travellers, pets, honours, turning, Placing bar (17 Oct 2026)
- **Placing bar** (mappage `busyStart/busyEnd` in `decorPost`): place/move
  requests show "Placing…/Moving…" with a bar filled over this browser's
  running average (localStorage `dlbusy-*`).
- **Turning**: decor rows carry `rot` (degrees; `DecorStore.move(rot=)`,
  move/move_many in both endpoints); payload `r`; `.dlpiece` rotates round its
  foot (`--rot`, origin 50% 85%). A handle (`.dlturn`) over a lone selected
  piece; Shift = 15° steps; double-click = straight.
- **Runaway horse** (`web/dodoland/horse_api.py`, server-authoritative; state
  on the guild config row `horse`): GET/POST `/api/guild/{gid}/dodoland/horse`
  and `/me/horse`. A kick bolts it away from the click (± `dodoland_horse_spread`,
  `bolt_min/max` cells, stops at water/edge); running past a placed zoo
  (`dodoland_zoo_building` pieces) catches it: `dodoland_horse_sweetrolls`
  rows in `sweetrolls` (gifted_to zoo owner, gifter = catcher, source
  dodoland_horse), announced in `dodoland_horse_channel` (named, not pinged),
  rest `rest_min/max_hours`. Line: `dodoland_horse_line`.
- **Travellers**: on the `dodoland_travellers` busiest roads (roads_api roads,
  kept as `terr.roads`), one of the two owners walks to the other's town and
  back; normal NPC size, bright colours, gold ring, avatar over head (`av`,
  Discord display_avatar), torch (night light); on horseback outside every
  town area (`inTown` via #dltinfl fills); their horse says
  `dodoland_horse_busy_line`. Click: card with avatar.
- **Look** (town card editor "Your traveller"): head/body/horse colours and up
  to 3 cats + 3 dogs following (`towns.clean_look`, `helpers/dodoland/pets.py`
  owned/search/details; pet owners are numbers or text in the pet cog — match
  both). Search: `/pets?user_id=` (panel) and `/me/pets` (member, own only).
- **Pets in towns**: `dodoland_pets_per_town` of each settled owner's cats and
  dogs walk their town (`_pets_of`, $firstN, cached 30 min); click shows photo.
- **Trophies & banners**: `_honours_of` - vet/hm clear roles held
  (config vet_clears/hm_clears) and best parse (`parses`); banner = trial rank
  in its colour (`rank_colour`); drawn over each town (`.dlhonours`) and on
  its card (`honoursCard`).
- Kept figures (`.dlkeep`) survive `buildLife`'s clear-out.
- Fixes (17 Oct): figures were unclickable (`.dlstand` pointer-events:none came
  later in the CSS) - now `.dlstand.dlhorse/.dltraveller/.dlpet`. Travellers come
  from who talks to whom (`_travel`: top `dodoland_travellers` pairs among
  settled people from the pair rows, plus always the viewer's own - their top
  partner or the nearest town), walking the road between the two if there is
  one, else a gentle curve across country; spawned from `buildLife` and again
  when roads load. Pets follow the traveller (chosen, else the first few) and no
  longer wander towns. "Find my traveller": town card button and the 🐎 map
  button (flashes the ring). Zoo catch radius 5 cells x scale. Honours (banner,
  cups, parse) removed for now.
- Forest LOD (17 Oct): below `dodoland_forest_merge` screen px per cell
  (default 6) a forest chunk is one flat canvas (`forestRenderFlat`: trees back
  to front, no shadows, z at the chunk's top) instead of depth strips with
  per-tree shadows; crossing the threshold re-renders (`d.flat`).
- Travellers v3 (17 Oct): `web/dodoland/travel_api.py`, GET `.../travel` (and
  the member reader `/me/w/travel`). One traveller per person (`who_travels`:
  viewer first, then top pairs sending whoever is not out yet). Routes: the
  roads' coarse grid (`roads.coarse_costs`, water cost
  `dodoland_travel_water_cost` 150, sea impassable) with path/road ground
  (`dodoland_travel_path_words` in the kind's key/label) costing
  `dodoland_travel_path_cost` (0.3) by share of the block; endpoints snapped to
  the nearest open block; `roads.astar(greed=2.5)` (new param, weighted
  heuristic; roads keep 1.0), retried in reverse when the search limit is hit.
  Cached hourly / on plots, settings, day - not per paint stroke (~8 s cold).
  The page fetches it once (`travelLoad`). Ring is an SVG ellipse under the
  feet (was an absolutely positioned element covering the body); torches show
  only while `.dldark` (set by drawNight at dusk, night, dawn).
- Travellers v4 (17 Oct): tours. `travel_api.tours`: one traveller per settled
  person (busiest first, `dodoland_travellers`), stops = home + their top
  `dodoland_travel_stops` talk partners (else nearest towns). `travel()` returns
  `{tours: [{w, stops}], routes: {"lo|hi": path}}`; a tour walks out through the
  stops and back (`tourLegs`), resting 3-8 s at each town. `current()` serves
  the last answer while recomputing in a background thread (cold ~24 s).
  Only chosen pets (`follow`) exist, following their traveller; town pets and
  `_pets_of`/`dodoland_pets_per_town` removed. Clicks: the frame asks
  `figureAt` (horse, travellers, their pets, by screen rect) before anything
  else; figures carry no listeners of their own.
- Figure clicks (17 Oct): the runaway horse spawned inside a town, where
  pieces and towns (z up to 30000 hovered) stacked over it and their own
  pointerdown handlers kept the press. `figureAt` now runs in capture-phase
  listeners on the frame (pointerdown + click, stopPropagation), horse z 40000.
  Cards open centred above the figure (`cardOver`), below when no room.
- Every horse (17 Oct): towns' walker horses (not zoo ones) are clickable via
  `figureAt` -> `herd()`: shout, bolt away from the click client-side (round
  water via `wetAt` on the baked cells, `D.sizes.horse` settings), become
  free (zone 'free'); a run passing a placed zoo POSTs `{catch: {zoo, from,
  to}}` -> `horse_api.catch` (zoo real, run <= 1.6x bolt_max, passes within
  r + reach; refused while `zoo_rest`), paid and announced like the runaway.
  Any catch sets `zoo_rest` (rest hours) for all horses.
- Strings (17 Oct): every text the horses, travellers, traveller editor, Placing
  bar and turn handle say is a `DODOLAND_*` constant in lang.py (the Strings
  menu, per server via `bot.lang.get`). The page gets them as `D.str`
  (`mappage.PAGE_STRINGS`, `_page_strings`) and says them with `txt(key, fill)`;
  the announcement uses `DODOLAND_HORSE_CAUGHT` and goes to the server's Bot
  channel (guild config `DODO_CHANNEL`). The horse's text settings are gone.
