---
description: Redraw the "Map art" engravings as coloured pixel art, in batches, ready to upload as placeable tiles
---

# Redraw the Map art as pixel art

The tile library holds 815 **Map art** tiles in 35 categories ("Map art · Castles",
"Map art · Monsters", …, pack "DodoLand Miro board"). They are black-and-white
old-map engravings, 39 to 1,800 px wide. This workflow redraws each one as
coloured pixel art in the style of the pixel packs the map already uses, at a size
you choose, and writes upload-ready batches. It never writes to the database:
importing a batch is a separate step you run.

Read `docs/DODOLAND_NEWMAP.md` first. Tile rules: `helpers/dodoland/tiles.py`.
Importer and bundle format: `tools/dodoland_import_tile_bundle.py`.

Rules for the whole run:
- Work one category at a time, and stop after each category's contact sheet until
  the user approves it.
- Keep what each object *is* (its silhouette, pose, parts, how many figures);
  change only the medium: ink engraving to coloured pixel art.
- No gargantuan objects: the sizes come from `sizes.csv`, which the user edits.
- Everything goes under `art_batches/mapart/` (git-ignored). Nothing is uploaded
  by this workflow.

## 1. Export the originals (read-only)

Write `tools/dodoland_mapart_export.py`. It reads the library through
`TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
database.dodoland_tile_art)`, for every tile whose category starts with `Map art`
except `Map art · Ground` (painted ground, not objects). For each one it writes:
- `art_batches/mapart/originals/<category-slug>/<tile-slug>.png` (first variant);
- a row in `art_batches/mapart/manifest.json`: tile_id, source, category, name,
  layer, access, passable, resizable, cell_px, and the size it is drawn at now, in
  map cells (art width / cell_px / `dodoland_tile_scale`).

// turbo
Run it, then print the counts per category.

## 2. Sizes, editable

Write `art_batches/mapart/sizes.csv` with one row per tile:
`category, name, source, width_cells, height_cells, px_per_cell`.
- `width_cells` starts at the size it is drawn at now, rounded and clamped by
  category: figures, crowds and animals 1-3; props, fountains, shrines and weapons
  1-4; boats and settlements 3-8; castles 4-10; mountains, hills, fields and
  dunes 4-12.
- `height_cells` is blank (keeps the original's aspect ratio).
- `px_per_cell` is 16, the existing pixel packs' grid.

Ask the user to edit the sizes (one row, or a whole category) and wait. Every
later step reads the file, so changing a size and re-running steps 3-5 for that
tile is all a resize takes.

## 3. Style reference

Make `art_batches/mapart/style/reference.png`: a sheet of about 30 tiles from the
pixel packs already in the library (pack names other than "DodoLand Miro board":
houses, trees, rocks, figures), each at 1:1. Extract its palette (about 32 colours)
to `style/palette.png`. That palette is the only set of colours the batches may
use, so every redrawn object sits on the same map.

## 4. Redraw, one category at a time

For each tile in the category, use the agent's image generation with two
reference images (the original engraving, and `style/reference.png`) and this
prompt, filled in from the manifest and `sizes.csv`:

> Redraw the object in the first image as top-down 3/4-view pixel art in the style
> of the second image: same palette, hard pixel edges, no anti-aliasing, a 1 px dark
> outline, light from the top left. Keep exactly what it shows: the same object,
> silhouette, pose and number of parts. Colour it naturally (stone grey, wood
> brown, foliage green, water blue, cloth in muted reds and blues; monsters and
> magic may be bolder). Transparent background, nothing else in the frame, no
> ground shadow beyond a 1-2 px contact shadow. Category: {category}. Object:
> {name}. Final size {width_px} x {height_px} px.

Save the raw result to `art_batches/mapart/raw/<category-slug>/<tile-slug>.png`.

Then clean every result the same way with Pillow (write
`tools/dodoland_mapart_pixelate.py`):
1. remove any background colour that is not transparent;
2. trim to the drawn area;
3. resize to exactly width_cells x px_per_cell wide (height from the aspect or
   `height_cells`) with nearest neighbour;
4. hard alpha: opaque at alpha 128 or more, transparent below;
5. snap every pixel to the nearest colour of `style/palette.png`;
6. add or repair the 1 px dark outline;
7. save to `art_batches/mapart/px/<category-slug>/<tile-slug>.png`.

## 5. Review and stop

Write `art_batches/mapart/review/<category-slug>.png`: for each tile, the original,
the pixel version at 1:1, and the pixel version at 4x, with its name and size.
Show it to the user and **wait**. Redraw only the ones they reject (with their
notes added to the prompt) and show the sheet again. Move to the next category
when they approve this one.

## 6. Write the upload batch

For each approved category, write `art_batches/mapart/bundles/<category-slug>.json`
in the format `tools/dodoland_import_tile_bundle.py` reads:
- `category`: the original category (the pixel tiles sit beside the engravings), or
  `Pixel art · <name>` if the user prefers them apart. Ask once, at the first
  category;
- `name`: the original name; `pack`: "DodoLand Map art, pixel";
- `source`: `pixel:<original source>`, so a later import recognises it;
- `cell_px`: px_per_cell; `uses`: the original layer with the original access, e.g.
  `["objects:admin", "objects:player"]`;
- `images`: the base64 PNG.

Add `resizable: false` and the original's `passable` to each entry; the importer
writes both through.

## 7. Upload (the user runs this)

Tell the user the commands for each approved category:

```
py tools/dodoland_import_tile_bundle.py art_batches/mapart/bundles/<category-slug>.json --dry-run
py tools/dodoland_import_tile_bundle.py art_batches/mapart/bundles/<category-slug>.json
```

The importer skips any tile whose `source` is already in the library. To replace a
redrawn tile, delete it in the panel first, or extend the importer with an
`--update` flag that adds a new variant.

## 8. Check and finish

// turbo
Run `py -X utf8 tests/run_tests.py`.

The user restarts the bot and checks on the live local panel
(http://localhost:8080): the tiles show in the toolkit, place at the chosen sizes,
stay crisp when zoomed, and members can place the player-access ones. Do not start
other servers.

Add a progress-log entry to `docs/DODOLAND_NEWMAP.md` (categories done, counts,
where the batches are, how to re-run one tile). Commit the tools and the doc (not
`art_batches/`) and push NewMap.
