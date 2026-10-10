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
