"""
Import the second batch of tile packs (``item_imgs/tilesets/NewTileSets``) into
the global tile library, into the categories that already exist.

    py tools/dodoland_import_newsets.py item_imgs/tilesets/NewTileSets --preview out.png
    py tools/dodoland_import_newsets.py item_imgs/tilesets/NewTileSets

Same rules as ``dodoland_import_tiles.py``: a hand-checked manifest, the packs
read in place (zips, tarballs, loose PNGs — only images are decoded), objects
cut by their own pixels, ground only from cells that are one terrain on every
side. Differences, from what the library has become since:

* **One tile per drawing** (placed tiles are stamps): a manifest entry with
  several drawings becomes "Name", "Name 2"…, sources ``pack:Name`` and
  ``pack:Name#2`` — the split-stamps convention. Ground keeps its variants.
* **Scale**: every entry has a ``cell_px`` chosen against what its category
  already holds (``--preview`` draws each new tile beside an existing one at
  the same cells-per-pixel), so nothing lands gargantuan next to the old art.
  Within one pack the same scale is kept wherever its art agrees with itself.
* **Settings** (layer, placement, access, passable, spreads, resizable, size
  range) are copied from the category's existing tiles of the same kind
  (ground or object), so a new rock blocks roads like the old rocks do.
* ZRPG paints drop shadows into its sheets (black at alpha 92); they are
  stripped before cutting — no other art in the library has one.

Left out: the Pixel Art Top Down zip (byte-identical to the one imported in
step 1b), autotile edges and corners (cliff faces, castle wall runs, sand and
rock transitions), the underwater and night-tinted copies, palettes and
attribution sheets.

**Credits.** The LPC and ZRPG art is CC-BY-SA 3.0 / CC-BY 3.0 (credit the
artists; see the packs' CREDITS files); ``pack`` on each tile says which.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import io
import pathlib
import sys
import tarfile
import zipfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("first_import", ROOT / "tools" / "dodoland_import_tiles.py")
first = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(first)

# --------------------------------------------------------------------------- #
#  The packs: key -> (container, path inside or "", credit)
# --------------------------------------------------------------------------- #
PACKS = {
    "free": ("FreeEnvironment.zip", "FreeEnvironment/", "Free Environment pack"),
    "oga": ("", "", "16oga tiles"),
    "lpcc": ("", "", "[LPC] Cliffs"),
    "lpcb": ("lpc-beach-desert-v2.zip", "lpc-beach-desert/",
             "[LPC] Beach/Desert (bluecarrot16 et al., CC-BY-SA 3.0)"),
    "zb": ("ZRPG Beach.tar.gz", "ZRPG Beach/", "ZRPG Beach (Zabin, Jetrel, Sharm, Hyptosis et al.)"),
    "zt": ("ZRPG Tiles.tar.gz", "ZRPG Tiles/", "ZRPG Tiles (Jetrel, Zabin, Hyptosis, Sharm, OPP)"),
    "brick": ("Tileable Brick Ground Textures - Set 2.zip", "", "Tileable Brick Ground Textures - Set 2"),
}
# Packs whose sheets carry painted drop shadows.
SHADOWED = {"zb", "zt"}

ZB = "ZRPGBeach.png"
ZTREES, ZROCKS, ZCASTLE, ZHOUSES = "ZRPGtrees.png", "ZRPGRocks2.png", "ZRPGcastle.png", "houses.png"
JUNGLE = "tile_jungle_plants_objects.png"
FREE = "FreePack.png"
OGA = "16oga.png"
LPCB = "beach-desert.png"


def cells(sheet, size, ids):
    return ("cells", sheet, size, list(ids))


def cut(sheet, ids):
    return ("cut", sheet, list(ids))


def box(sheet, *rects):
    return ("box", sheet, list(rects))


def texture(path, side):
    return ("texture", path, side)


G = "ground"     # painted, one terrain on every side
O = "object"     # placed
# (category, name, kind, pack, cell_px, sources)
MANIFEST = [
    # ---- Ground --------------------------------------------------------------
    ("Grass", "Bright grass", G, "oga", 16, [cells(OGA, 16, [10, 20])]),
    ("Grass", "Lush grass", G, "zb", 32, [cells(ZB, 32, [522, 523, 554, 555])]),
    ("Grass", "Tall grass meadow", G, "zb", 32, [cells(ZB, 32, [618, 619, 626, 650, 651])]),
    ("Grass", "Soft green grass", G, "zt", 32, [cells(ZROCKS, 32, [918, 919, 950]), cells(ZTREES, 32, [560, 592, 625])]),
    ("Grass", "Deep green grass", G, "zt", 32, [cells(ZROCKS, 32, [673, 706]), cells(ZTREES, 32, [598])]),
    ("Dirt & sand", "Brown dirt", G, "oga", 16, [cells(OGA, 16, [11])]),
    ("Dirt & sand", "Packed earth", G, "lpcc", 32, [cells("LPC_cliffs_ddirt.png", 32, [18])]),
    ("Dirt & sand", "Gravel", G, "zb", 32, [cells(ZB, 32, [641, 647])]),
    ("Dirt & sand", "Stony ground", G, "zt", 32, [cells(ZROCKS, 32, [48, 49, 55, 56, 80, 81, 82, 87, 88, 89, 112, 113])]),
    ("Dirt & sand", "Pale sand", G, "zb", 32, [cells(ZB, 32, [801, 804])]),
    ("Dirt & sand", "Golden sand", G, "zb", 32, [cells(ZB, 32, [807, 810, 870, 871, 872])]),
    ("Dirt & sand", "Rippled sand", G, "zb", 32, [cells(ZB, 32, [864, 865, 866])]),
    ("Dirt & sand", "Dune sand", G, "lpcc", 32, [cells("LPC_cliffs_sand.png", 32, [18])]),
    # No snow category exists; snow is loose ground like sand.
    ("Dirt & sand", "Snow", G, "lpcc", 32, [cells("LPC_cliffs_snow.png", 32, [18])]),
    # Painted textures, 512px: shrunk to 256 and laid over 4 x 4 cells.
    ("Paths & paving", "Arc cobbles", G, "brick", 64, [texture("Brick_01.png", 256)]),
    ("Paths & paving", "Diamond flagstones", G, "brick", 64, [texture("Brick_02.png", 256)]),
    ("Paths & paving", "Square flagstones", G, "brick", 64, [texture("Brick_03.png", 256)]),
    ("Paths & paving", "Crazy paving", G, "brick", 64, [texture("Brick_04.png", 256)]),

    # ---- Trees ---------------------------------------------------------------
    ("Trees", "Broad oak", O, "zt", 40, [cut(ZTREES, [0, 1, 9, 10, 15])]),
    ("Trees", "Giant oak", O, "zt", 40, [cut(ZTREES, [3, 8])]),
    ("Trees", "Round oak", O, "zt", 40, [cut(ZTREES, [2, 4, 38])]),
    ("Trees", "Oak sapling", O, "zt", 40, [cut(ZTREES, [6])]),
    ("Trees", "Gnarled oak", O, "zt", 40, [cut(ZTREES, [7])]),
    ("Trees", "Teal tree", O, "zt", 40, [cut(ZTREES, [58, 64, 67])]),
    ("Trees", "Spruce", O, "zt", 40, [cut(ZTREES, [55, 65, 66, 68])]),
    ("Trees", "Pine", O, "free", 28, [cut(FREE, [11, 18, 19])]),
    ("Trees", "Snowy pine", O, "free", 28, [cut(FREE, [17])]),
    ("Trees", "Bare tree", O, "free", 28, [cut(FREE, [20])]),
    ("Trees", "Little pine", O, "oga", 16, [box(OGA, (80, 48, 96, 80))]),
    ("Trees", "Palm tree", O, "zb", 32, [cut(ZB, [12, 13, 84, 86, 142, 143, 56, 63])]),
    ("Trees", "Banana palm", O, "zb", 32, [cut(ZB, [49, 50, 62, 64, 85, 87])]),
    ("Trees", "Leaning palm", O, "zb", 32, [cut(ZB, [125, 147])]),
    ("Trees", "Windswept pine", O, "zb", 32, [cut(ZB, [58])]),
    ("Trees", "Bare desert tree", O, "zb", 32, [cut(ZB, [59, 60])]),
    ("Trees", "Desert olive", O, "zb", 32, [cut(ZB, [61])]),
    ("Trees", "Saguaro", O, "zb", 32, [cut(ZB, [9, 10, 11, 133])]),
    ("Trees", "Old saguaro", O, "free", 28, [cut(FREE, [0, 1])]),
    ("Trees", "Column cactus", O, "zb", 32, [cut(ZB, [30, 43])]),
    ("Trees", "Little saguaro", O, "zb", 32, [cut(ZB, [44, 45])]),

    # ---- Logs & stumps ---------------------------------------------------------
    ("Logs & stumps", "Dead stump", O, "zb", 32, [cut(ZB, [68])]),
    ("Logs & stumps", "Hollow log", O, "zt", 32, [cut(ZTREES, [56])]),
    ("Logs & stumps", "Mossy log", O, "zt", 32, [cut(JUNGLE, [35, 43])]),
    ("Logs & stumps", "Firewood pile", O, "zt", 32, [cut(JUNGLE, [28])]),
    ("Logs & stumps", "Dried palm frond", O, "lpcb", 32, [cut(LPCB, [6, 7, 8, 17])]),

    # ---- Bushes --------------------------------------------------------------
    ("Bushes", "Palm shrub", O, "zb", 32, [cut(ZB, [47, 48])]),
    ("Bushes", "Agave", O, "free", 40, [cut(FREE, [2, 3])]),
    ("Bushes", "Jungle bush", O, "zt", 32, [cut(ZTREES, [44, 45])]),
    ("Bushes", "Thorn shrub", O, "zt", 32, [cut(ZTREES, [61])]),
    ("Bushes", "Giant leaf", O, "zt", 40, [cut(JUNGLE, [29])]),

    # ---- Flowers & plants ----------------------------------------------------
    ("Flowers & plants", "Barrel cactus", O, "zb", 32, [cut(ZB, [7, 39, 40])]),
    ("Flowers & plants", "Prickly pear", O, "zb", 32, [cut(ZB, [46])]),
    ("Flowers & plants", "Cactus sprout", O, "zb", 32, [cut(ZB, [8, 57])]),
    ("Flowers & plants", "Flowering cactus", O, "free", 34, [cut(FREE, [4])]),
    ("Flowers & plants", "Pink coral", O, "zb", 32, [cut(ZB, [28])]),
    ("Flowers & plants", "Sea coral", O, "free", 40, [cut(FREE, [13, 14, 15])]),
    ("Flowers & plants", "Jungle fern", O, "zt", 32, [cut(ZTREES, [19, 23, 33, 35, 36, 37, 46, 47, 48, 50])]),
    ("Flowers & plants", "Forest sprout", O, "zt", 32, [cut(ZTREES, [20, 25, 34, 41])]),
    ("Flowers & plants", "Broadleaf plant", O, "zt", 32, [cut(ZTREES, [21])]),
    ("Flowers & plants", "Red flower", O, "zt", 32, [cut(ZTREES, [27])]),
    ("Flowers & plants", "Stump planter", O, "zt", 32, [cut(ZTREES, [22])]),
    ("Flowers & plants", "Marble planter", O, "zt", 32, [cut(ZTREES, [28])]),
    ("Flowers & plants", "Barrel planter", O, "zt", 32, [cut(ZTREES, [29, 30])]),
    ("Flowers & plants", "Potted fern", O, "zt", 32, [cut(ZTREES, [57, 59, 60])]),
    ("Flowers & plants", "Jungle leaves", O, "zt", 32, [cut(JUNGLE, [0, 5, 6, 7, 8, 9, 12, 15, 20, 21, 22, 23, 30, 33, 34])]),
    ("Flowers & plants", "Shadow fern", O, "zt", 32, [cut(JUNGLE, [16, 17, 19])]),
    ("Flowers & plants", "Night bloom", O, "zt", 32, [cut(JUNGLE, [1, 2, 3, 4, 37])]),
    ("Flowers & plants", "Torch plant", O, "zt", 32, [cut(JUNGLE, [10, 11, 13, 14])]),
    ("Flowers & plants", "Rafflesia", O, "zt", 32, [cut(JUNGLE, [25, 26])]),
    ("Flowers & plants", "Tall jungle flower", O, "zt", 32, [cut(JUNGLE, [24])]),
    ("Flowers & plants", "Bluebell", O, "zt", 32, [cut(JUNGLE, [41, 42])]),

    # ---- Grass tufts -----------------------------------------------------------
    ("Grass tufts", "Beach grass", O, "zb", 32, [cut(ZB, [5, 139, 140, 141, 132])]),
    ("Grass tufts", "Grass blades", O, "zt", 32, [cut(JUNGLE, [31, 32])]),
    ("Grass tufts", "Grass scatter", O, "zt", 32, [cut(ZROCKS, [46, 50, 51, 56, 57, 84, 85, 86])]),
    # Grass laid on top of the ground, like Paths & paving's "Stone patch".
    ("Grass", "Meadow patch", O, "zt", 32, [cut(ZTREES, [13, 14, 18, 24, 40, 62, 63])]),
    ("Grass", "Teal meadow patch", O, "zt", 32, [cut(ZROCKS, [43])]),

    # ---- Mushrooms ---------------------------------------------------------------
    ("Mushrooms", "Red toadstool", O, "zt", 32, [cut(JUNGLE, [36, 38])]),

    # ---- Rocks -----------------------------------------------------------------
    ("Rocks", "Craggy rock", O, "zt", 40, [cut(ZROCKS, [21, 22, 24])]),
    ("Rocks", "Mossy crag", O, "zt", 40, [cut(ZROCKS, [23])]),
    ("Rocks", "Rock stack", O, "zt", 40, [cut(ZROCKS, [26, 27, 28, 29, 30, 31, 32])]),
    ("Rocks", "Rock outcrop", O, "zt", 40, [cut(ZROCKS, [34, 35, 38, 39])]),
    ("Rocks", "Mossy outcrop", O, "zt", 40, [cut(ZROCKS, [36, 40])]),
    ("Rocks", "Rocky mesa", O, "zt", 40, [cut(ZROCKS, [2, 33])]),
    ("Rocks", "Rocky crater", O, "zt", 40, [cut(ZROCKS, [0])]),
    ("Rocks", "Ochre rock", O, "zt", 40, [cut(ZROCKS, [4, 5, 6, 8, 9, 13, 18, 19, 20])]),
    ("Rocks", "Sand pebbles", O, "zb", 32, [cut(ZB, [127, 128, 129, 130])]),
    ("Rocks", "Granite boulder", O, "free", 45, [cut(FREE, [12])]),
    ("Rocks", "Ice boulder", O, "free", 45, [cut(FREE, [16])]),
    ("Rocks", "Crystal rock", O, "zt", 32, [cut(JUNGLE, [46, 47, 48])]),
    ("Rocks", "Ember rock", O, "zt", 32, [cut(JUNGLE, [49])]),
    ("Rocks", "Thorn rock", O, "zt", 32, [cut(JUNGLE, [45])]),
    ("Rocks", "Grassy rock pillar", O, "lpcc", 32, [cut("LPC_cliffs_grass.png", [2])]),
    ("Rocks", "Earthen rock pillar", O, "lpcc", 32, [cut("LPC_cliffs_ddirt.png", [2])]),
    ("Rocks", "Sandy rock pillar", O, "lpcc", 32, [cut("LPC_cliffs_sand.png", [2])]),
    ("Rocks", "Snowy rock pillar", O, "lpcc", 32, [cut("LPC_cliffs_snow.png", [2])]),
    ("Rocks", "Rock spires", O, "lpcc", 32, [cut("LPC_cliffs_grass.png", [8, 9, 10])]),

    # ---- Sand and gravel laid on the ground --------------------------------------
    ("Dirt & sand", "Sand mound", O, "zb", 32, [cut(ZB, [135, 136, 137, 138])]),
    ("Dirt & sand", "Sand crater", O, "zb", 32, [cut(ZB, [144])]),
    ("Dirt & sand", "Sand drift", O, "zb", 32, [cut(ZB, [93, 96, 158, 159])]),
    ("Dirt & sand", "Gravel patch", O, "zb", 32, [cut(ZB, [98, 104])]),
    ("Dirt & sand", "Rubble patch", O, "zt", 32, [cut(ZROCKS, [52, 78, 102])]),
    ("Water", "Puddle", O, "lpcb", 32, [cut(LPCB, [99])]),

    # ---- Houses and their parts --------------------------------------------------
    ("Houses", "Gabled cottage", O, "zt", 36, [cut(ZHOUSES, [0])]),
    ("Houses", "Gabled townhouse", O, "zt", 36, [cut(ZHOUSES, [1])]),
    ("House parts", "Round stone tower", O, "oga", 16, [box(OGA, (112, 16, 160, 80))]),
    ("House parts", "Slate roof tile", O, "oga", 16, [cells(OGA, 16, [2, 7])]),
    ("House parts", "Stone wall block", O, "oga", 16, [cells(OGA, 16, [25])]),
    ("House parts", "Plank wall", O, "oga", 16, [box(OGA, (48, 16, 64, 64))]),
    ("House parts", "Portcullis gate", O, "zt", 40, [cut(ZCASTLE, [4])]),
    ("House parts", "Arched door", O, "zt", 40, [cut(ZCASTLE, [5])]),

    # ---- Walls, monuments ---------------------------------------------------------
    ("Walls & ruins", "Castle archway", O, "zt", 40, [cut(ZCASTLE, [0, 2])]),
    ("Monuments & graves", "Gargoyle statue", O, "zt", 32, [cut(ZCASTLE, [15, 16])]),
    ("Monuments & graves", "Giant ribcage", O, "zb", 40, [cut(ZB, [65, 69])]),
    ("Monuments & graves", "Horned skull", O, "zb", 40, [cut(ZB, [67])]),
    ("Monuments & graves", "Beast skull", O, "zb", 40, [cut(ZB, [77])]),
    ("Monuments & graves", "Giant jawbone", O, "zb", 40, [cut(ZB, [73])]),
    ("Monuments & graves", "Rib bone", O, "zb", 40, [cut(ZB, [78])]),
    ("Monuments & graves", "Tusks", O, "zb", 40, [cut(ZB, [80, 81])]),

    # ---- Fences, signs, camp, containers, items --------------------------------------
    ("Fences & bridges", "Iron railing", O, "oga", 16, [box(OGA, (48, 64, 64, 80))]),
    ("Signs & lamps", "Arrow signpost", O, "zt", 32, [cut(ZTREES, [43])]),
    ("Signs & lamps", "Wall torch", O, "zt", 32, [cut(ZCASTLE, [8])]),
    ("Signs & lamps", "Oil lantern", O, "zt", 32, [cut(JUNGLE, [40])]),
    ("Signs & lamps", "Skull banner", O, "zt", 32, [cut(JUNGLE, [39])]),
    ("Camp & furniture", "Canvas tent", O, "zt", 32, [cut(JUNGLE, [44])]),
    ("Camp & furniture", "Tall ladder", O, "lpcc", 40, [cut("LPC_cliffs_grass.png", [6])]),
    ("Camp & furniture", "Stone well", O, "oga", 16, [box(OGA, (96, 48, 112, 80))]),
    ("Containers", "Small cask", O, "oga", 16, [box(OGA, (64, 32, 80, 48))]),
    ("Containers", "Iron-banded chest", O, "oga", 16, [box(OGA, (96, 32, 112, 48))]),
    ("Containers", "Little keg", O, "zt", 20, [cut(ZCASTLE, [7])]),
    ("Items", "Seashell", O, "zb", 32, [cut(ZB, [0, 2, 3, 4, 16, 19, 22, 24, 34, 35])]),
    ("Items", "Starfish", O, "zb", 32, [cut(ZB, [1, 26, 29])]),
    ("Items", "Sand dollar", O, "zb", 32, [cut(ZB, [36, 37])]),
    ("Items", "Fish bones", O, "lpcb", 32, [cut(LPCB, [34])]),
    ("Items", "Beehive", O, "zt", 32, [cut(JUNGLE, [27])]),
    ("Items", "Apple", O, "free", 34, [cut(FREE, [5])]),
    ("Items", "Grapes", O, "free", 34, [cut(FREE, [6])]),
    ("Items", "Cauliflower", O, "free", 34, [cut(FREE, [7])]),
    ("Items", "Tomato", O, "free", 34, [cut(FREE, [8])]),
    ("Items", "Corn", O, "free", 34, [cut(FREE, [9])]),
    ("Items", "Carrot", O, "free", 34, [cut(FREE, [10])]),
]


# --------------------------------------------------------------------------- #
#  Reading the packs
# --------------------------------------------------------------------------- #
def _trim(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image


def _unshadow(image: Image.Image) -> Image.Image:
    a = np.asarray(image).copy()
    shade = (a[..., 0] < 8) & (a[..., 1] < 8) & (a[..., 2] < 8) & (a[..., 3] < 120)
    a[shade] = 0
    return Image.fromarray(a)


class Packs:
    def __init__(self, folder: pathlib.Path) -> None:
        self.folder = folder
        self._sheets: dict[tuple, Image.Image] = {}
        self._cuts: dict[tuple, list] = {}

    def _bytes(self, pack: str, path: str) -> bytes:
        container, inside, _ = PACKS[pack]
        if not container:
            return (self.folder / path).read_bytes()
        if container.endswith(".zip"):
            with zipfile.ZipFile(self.folder / container) as z:
                return z.read(inside + path)
        with tarfile.open(self.folder / container) as t:
            return t.extractfile(inside + path).read()

    def image(self, pack: str, path: str) -> Image.Image:
        key = (pack, path)
        if key not in self._sheets:
            image = Image.open(io.BytesIO(self._bytes(pack, path))).convert("RGBA")
            self._sheets[key] = _unshadow(image) if pack in SHADOWED else image
        return self._sheets[key]

    def drawings(self, pack: str, source) -> list[Image.Image]:
        kind = source[0]
        if kind == "cells":
            _, sheet, size, ids = source
            image = self.image(pack, sheet)
            cols = image.width // size
            return [image.crop(((i % cols) * size, (i // cols) * size,
                                (i % cols + 1) * size, (i // cols + 1) * size)) for i in ids]
        if kind == "box":
            _, sheet, rects = source
            return [_trim(self.image(pack, sheet).crop(r)) for r in rects]
        if kind == "texture":
            _, path, side = source
            return [self.image(pack, path).resize((side, side), Image.LANCZOS)]
        if kind == "cut":
            _, sheet, ids = source
            key = (pack, sheet)
            if key not in self._cuts:
                self._cuts[key] = first.cut_sprites(self.image(pack, sheet))
            found = self._cuts[key]
            missing = [i for i in ids if i >= len(found)]
            if missing:
                raise SystemExit(f"{pack}:{sheet} has {len(found)} sprites; asked for {missing}")
            return [found[i] for i in ids]
        raise ValueError(kind)


def build(folder: pathlib.Path) -> list[dict]:
    """Every tile to write: ground with its variants, objects one per drawing."""
    packs = Packs(folder)
    out = []
    for category, name, kind, pack, cell_px, sources in MANIFEST:
        images = [image for source in sources for image in packs.drawings(pack, source)]
        base = {"category": category, "kind": kind, "pack": PACKS[pack][2], "cell_px": cell_px}
        if kind == G:
            out.append({**base, "name": name, "source": f"{pack}:{name}", "images": images})
            continue
        for n, image in enumerate(images, start=1):
            label = name if n == 1 else f"{name} {n}"
            key = f"{pack}:{name}" if n == 1 else f"{pack}:{name}#{n}"
            out.append({**base, "name": label, "source": key, "images": [image]})
    return out


# --------------------------------------------------------------------------- #
#  Settings copied from the category
# --------------------------------------------------------------------------- #
SETTING_KEYS = ("layer", "placement", "access", "passable", "spreads", "resizable",
                "scale_min", "scale_max")


def category_settings(existing: list[dict]) -> dict:
    """``{(category id, "ground"|"object"): settings}``: the most common
    settings among a category's tiles of that kind."""
    votes: dict[tuple, collections.Counter] = collections.defaultdict(collections.Counter)
    for tile in existing:
        kind = G if tile.get("placement") == "paint" else O
        values = tuple((k, tuple(tile[k]) if isinstance(tile.get(k), list) else tile.get(k))
                       for k in SETTING_KEYS)
        votes[(tile["cat_id"], kind)][values] += 1
    return {key: {k: (list(v) if k == "access" else v) for k, v in counter.most_common(1)[0][0]}
            for key, counter in votes.items()}


FALLBACK = {
    G: {"layer": "environment", "placement": "paint", "access": ["admin", "player"],
        "passable": True, "spreads": True, "resizable": False, "scale_min": 0.5, "scale_max": 3.0},
    O: {"layer": "objects", "placement": "place", "access": ["admin", "player"],
        "passable": True, "spreads": True, "resizable": False, "scale_min": 0.5, "scale_max": 3.0},
}


# --------------------------------------------------------------------------- #
#  Preview: each new tile beside an existing one, at the same scale
# --------------------------------------------------------------------------- #
def preview(tiles: list[dict], path: str, px_per_cell: int = 14) -> None:
    from config import database
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                          database.dodoland_tile_art)
    cats = {c["name"]: c["cat_id"] for c in library.categories()}
    refs: dict[str, list] = collections.defaultdict(list)
    for tile in library.tiles(0):
        if tile["variants"] and "Miro" not in tile.get("pack", ""):
            refs[tile["cat_id"]].append(tile)

    def ref_image(cat_id: str, kind: str):
        pool = [t for t in refs.get(cat_id, []) if (t["placement"] == "paint") == (kind == G)]
        if not pool:
            return None, None
        pool.sort(key=lambda t: t["name"])
        tile = pool[len(pool) // 2]
        row = library.art(tile["variants"][0])
        if not row or not row.get("data"):
            return None, None
        return Image.open(io.BytesIO(bytes(row["data"]))).convert("RGBA"), tile

    def at_scale(image, cell_px):
        k = px_per_cell / float(cell_px)
        return image.resize((max(1, round(image.width * k)), max(1, round(image.height * k))), Image.NEAREST)

    groups: dict[tuple, list] = collections.defaultdict(list)
    for tile in tiles:
        groups[(tile["category"], tile["kind"])].append(tile)
    rows = []
    for (category, kind), members in groups.items():
        ref, ref_tile = ref_image(cats.get(category, ""), kind)
        rows.append((category, kind, members, ref, ref_tile))
    width = 1600
    boards = []
    for category, kind, members, ref, ref_tile in rows:
        items = []
        if ref is not None:
            items.append((f"[old] {ref_tile['name']}", at_scale(ref, ref_tile["cell_px"])))
        for tile in members:
            items.append((tile["name"], at_scale(tile["images"][0], tile["cell_px"])))
        x, y, line_h, placed = 0, 18, 0, []
        for label, image in items:
            w = max(image.width, 60)
            if x + w > width:
                x, y, line_h = 0, y + line_h + 26, 0
            placed.append((x, y, label, image))
            x += w + 12
            line_h = max(line_h, image.height)
        board = Image.new("RGBA", (width, y + line_h + 30), (46, 52, 46, 255))
        draw = ImageDraw.Draw(board)
        draw.text((4, 2), f"{category} ({kind}) — {px_per_cell}px per map cell", fill=(255, 220, 90, 255))
        for x, y, label, image in placed:
            board.alpha_composite(image, (x, y + 12))
            draw.text((x, y), label[:18], fill=(255, 140, 140, 255) if label.startswith("[old]") else (230, 230, 230, 255))
        boards.append(board)
    total = Image.new("RGBA", (width, sum(b.height for b in boards)), (0, 0, 0, 255))
    y = 0
    for board in boards:
        total.alpha_composite(board, (0, y))
        y += board.height
    total.save(path)


# --------------------------------------------------------------------------- #
#  Writing
# --------------------------------------------------------------------------- #
def write(tiles: list[dict]) -> None:
    from config import database
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                          database.dodoland_tile_art)
    cats = {c["name"]: c["cat_id"] for c in library.categories()}
    missing = sorted({t["category"] for t in tiles} - set(cats))
    if missing:
        raise SystemExit(f"These categories do not exist: {missing}")
    settings = category_settings(library.tiles(0))
    added = kept = 0
    for tile in tiles:
        if library.by_source(tile["source"]):
            kept += 1
            continue
        cat_id = cats[tile["category"]]
        props = settings.get((cat_id, tile["kind"])) or FALLBACK[tile["kind"]]
        first_image, *rest = tile["images"]
        row = library.add_tile(name=tile["name"], cat_id=cat_id, data=first.png(first_image),
                               content_type="image/png", layer=props["layer"],
                               placement=props["placement"], access=props["access"],
                               passable=props["passable"], resizable=props["resizable"],
                               scale_min=props["scale_min"], scale_max=props["scale_max"],
                               cell_px=tile["cell_px"], pack=tile["pack"], source=tile["source"],
                               spreads=props["spreads"])
        for image in rest:
            library.add_variant(row["tile_id"], data=first.png(image), content_type="image/png")
        added += 1
    print(f"added {added} tiles, {kept} were already there")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=pathlib.Path, help="the NewTileSets folder")
    parser.add_argument("--preview", help="write a PNG of what would be imported, and stop")
    args = parser.parse_args()
    tiles = build(args.folder)
    print(f"{len(tiles)} tiles, {sum(len(t['images']) for t in tiles)} images, "
          f"{len({t['category'] for t in tiles})} categories (all existing)")
    if args.preview:
        preview(tiles, args.preview)
        print("preview written to", args.preview)
        return
    write(tiles)


if __name__ == "__main__":
    main()
