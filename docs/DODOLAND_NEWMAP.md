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
2. The base map draws library tiles instead of the procedural motifs; the brush paints a chosen tile. Old motifs remain the fallback.
3. "Rebuild roads": A* over `move` cost, written to `BUILT`, drawn.
4. Influence: per-town region grown from the town hall over `grow` cost, budget from town power; borders drawn.
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
`py tools/dodoland_tiles_preview.py` (or the `dodoland-tiles` launch config)
serves the real page on :8778 against an in-memory library.

Next: step 2 — bind tiles to ground kinds and draw them on the map as SVG
patterns (the same mechanism the motifs use), the brush picking a tile.
