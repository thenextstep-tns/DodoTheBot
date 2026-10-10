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
