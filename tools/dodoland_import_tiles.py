"""
Import the curated tile packs into the global tile library.

    py tools/dodoland_import_tiles.py item_imgs/tilesets --preview out.png   # nothing written
    py tools/dodoland_import_tiles.py item_imgs/tilesets                     # writes to the library

Reads the pack zips directly: no extraction, nothing from them is run, only
their PNGs are decoded. Every entry below was chosen by looking at the art, so
this is a manifest, not a heuristic: a ground tile is a cell that is the same
terrain on every side (a transition tile would draw a seam across a field), an
object is one island of opaque pixels cut by its own pixels rather than its
bounding box, because packed sheets overlap boxes and a box crop drags the
neighbour in.

**Re-runnable.** Each tile carries a ``source`` key; one that is already in the
library is left alone, so the owner's later renames, recategorising and ticks
survive a second run, and a removed tile can be brought back by running again.

Left out on purpose, and why:

* animated creatures and characters (cats, dogs, slimes, players) — they are
  walkers, and walkers come with step 7 and animation support;
* animation strips (campfire, flowers, doors), shadows, house interiors;
* autotile edge pieces, cliffs and the Fan-tasy building atlas — plain tiles
  first, as decided; transitions are a later step.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import sys
import zipfile
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# --------------------------------------------------------------------------- #
#  The packs
# --------------------------------------------------------------------------- #
PACKS = {
    # key: (zip name, folder inside, credit, grid)
    "fan": ("The Fan-tasy Tileset (Free) 1.5.9.zip", "The Fan-tasy Tileset (Free)/Art/",
            "The Fan-tasy Tileset (Free)", 16),
    "px": ("Pixel Art Top Down - Basic v1.2.3.zip", "Texture/", "Pixel Art Top Down - Basic", 32),
    "sp": ("summer_plains_v1.0_standard.zip", "summer_plains_v1.0_standard/",
           "Summer Plains by schwarnhild", 16),
    "vr": ("Valley Ruin Asset Pack V0.3.zip", "Valley Ruin Asset Pack V0.3/",
           "Valley Ruin Asset Pack", 16),
    "fl": ("FL_Houses_Demo_v1.0.zip", "Exterrior/", "FL Houses (demo)", 32),
    "dog": ("DogMegaPackFree.zip", "DogMegaPackFree/", "Dog Mega Pack (free)", 32),
}

ENV = ["environment:admin"]
OBJ = ["objects:admin", "objects:player"]
OBJ_ADMIN = ["objects:admin"]

# Category, its default uses. Order is palette order.
CATEGORIES = [
    ("Grass", ENV), ("Dirt & sand", ENV), ("Paths & paving", ENV), ("Water", ENV),
    ("Trees", OBJ), ("Logs & stumps", OBJ), ("Bushes", OBJ), ("Flowers & plants", OBJ),
    ("Grass tufts", OBJ), ("Mushrooms", OBJ), ("Rocks", OBJ), ("Houses", OBJ),
    ("House parts", OBJ_ADMIN), ("Walls & ruins", OBJ), ("Monuments & graves", OBJ),
    ("Fences & bridges", OBJ), ("Signs & lamps", OBJ), ("Camp & furniture", OBJ),
    ("Containers", OBJ), ("Items", OBJ),
]


def cells(sheet, size, ids):
    return ("cells", sheet, size, list(ids))


def cut(sheet, ids):
    return ("cut", sheet, list(ids))


def files(*paths):
    return ("files", list(paths))


# (category, name, pack, sources[, uses]) — uses default to the category's.
FAN_GROUND = "Ground Tileset/Tileset_Ground.png"
SP_TILES = "tiles.png"
SP_ASSETS = "assets.png"
VR_STONE = "Objects/stone and bush.png"
VR_FLOWER = "FlowerAndGrass.png"
VR_CHEST = "Objects/ChestSheet.png"
PX_PLANT = "TX Plant.png"
PX_PROPS = "TX Props.png"
PX_STRUCT = "TX Struct.png"
FL_HOUSES = "ready_to_use_houses.png"
FL_DECO = "floor_and_deoratives.png"
FL_PARTS = "walls_roofs_and_other.png"

MANIFEST = [
    # ---- Environment: plain ground, one terrain on every side ---------------
    ("Grass", "Meadow grass", "fan", [cells(FAN_GROUND, 16, [14, 96, 97, 98, 99, 100, 101, 108, 109, 110, 111, 112, 113])]),
    ("Grass", "Olive grass", "px", [cells("TX Tileset Grass.png", 32, [0, 1, 2, 3, 8, 9, 10, 11, 16, 17, 18, 19, 24, 25, 26, 27])]),
    ("Grass", "Olive grass with flowers", "px", [cells("TX Tileset Grass.png", 32, [4, 5, 6, 12, 13, 14, 20, 21, 22, 23, 29, 30, 31])]),
    ("Grass", "Summer grass", "sp", [cells(SP_TILES, 16, [21])]),
    ("Grass", "Summer grass, dark", "sp", [cells(SP_TILES, 16, [470])]),
    ("Grass", "Valley grass", "vr", [cells("Tiles Maps/GrassTile.png", 16, [12])]),
    ("Dirt & sand", "Dirt", "fan", [cells(FAN_GROUND, 16, [95])]),
    ("Dirt & sand", "Summer sand", "sp", [cells(SP_TILES, 16, [33, 34, 36, 59, 60, 61, 85, 88, 175, 176, 179, 203, 204, 221, 229, 246])]),
    ("Dirt & sand", "Valley sand", "vr", [cells("Tiles Maps/SandTile.png", 16, [12])]),
    ("Dirt & sand", "Valley dirt", "vr", [cells("Tiles Maps/DirtTile.png", 16, [0])]),
    ("Paths & paving", "Sandy path", "fan", [cells("Ground Tileset/Tileset_Road.png", 16, [8, 48, 49, 50, 54, 55, 56])]),
    ("Paths & paving", "Stone paving", "px", [cells("TX Tileset Stone Ground.png", 32, [9, 39, 46, 56, 58])]),
    ("Paths & paving", "Cobblestone", "fl", [cut(FL_DECO, [13])]),
    ("Paths & paving", "Stone patch", "fl", [cut(FL_DECO, [0])], OBJ),
    ("Water", "Lake water", "fan", [cells("Water and Sand/Tileset_Water.png", 16, [26, 192, 193, 194])]),
    ("Water", "Shallow water", "sp", [cells(SP_TILES, 16, [39])]),
    ("Water", "Deep water", "sp", [cells(SP_TILES, 16, [168])]),

    # ---- Trees --------------------------------------------------------------
    ("Trees", "Emerald tree", "fan", [files(*(f"Trees and Bushes/Tree_Emerald_{n}.png" for n in (1, 2, 3, 4)))]),
    ("Trees", "Birch", "px", [cut(PX_PLANT, [0, 1, 2])]),
    ("Trees", "Twisted oak", "sp", [cut(SP_ASSETS, [0])]),
    ("Trees", "Leafy oak", "sp", [cut(SP_ASSETS, [1, 2, 11])]),
    ("Trees", "Young tree", "sp", [cut(SP_ASSETS, [7])]),
    ("Trees", "Fruit sapling", "sp", [cut(SP_ASSETS, [8, 9, 10, 12, 13, 14])]),
    ("Trees", "Valley oak", "vr", [cut(VR_STONE, [9, 10, 11])]),
    ("Trees", "Dense oak", "vr", [cut(VR_STONE, [63, 64, 65])]),
    ("Trees", "Autumn tree", "vr", [cut(VR_STONE, [41, 42, 43])]),
    ("Trees", "Dead tree", "vr", [cut(VR_STONE, [21, 47, 81])]),
    ("Trees", "Giant tree", "vr", [cut("Objects/Giant_Tree.png", [0])]),

    # ---- Logs & stumps ------------------------------------------------------
    ("Logs & stumps", "Chopped tree", "fan", [files("Props/Chopped_Tree_1.png")]),
    ("Logs & stumps", "Log", "sp", [cut(SP_ASSETS, [3, 4])]),
    ("Logs & stumps", "Stump", "sp", [cut(SP_ASSETS, [5, 6])]),
    ("Logs & stumps", "Mossy root", "vr", [cut("Objects/Giant_Tree.png", [2, 3, 4, 5])]),
    ("Logs & stumps", "Firewood", "fl", [cut(FL_DECO, [11])]),
    ("Logs & stumps", "Timber stump", "fl", [cut(FL_DECO, [37])]),
    ("Logs & stumps", "Timber log", "fl", [cut(FL_DECO, [38, 39])]),

    # ---- Bushes -------------------------------------------------------------
    ("Bushes", "Emerald bush", "fan", [files(*(f"Trees and Bushes/Bush_Emerald_{n}.png" for n in range(1, 8)))]),
    ("Bushes", "Olive bush", "px", [cut(PX_PLANT, [3, 4, 5, 6, 7, 8])]),
    ("Bushes", "Summer bush", "sp", [cut(SP_ASSETS, [19, 20, 22, 36, 37, 38, 49, 57])]),
    ("Bushes", "Dark bush", "sp", [cut(SP_ASSETS, [21])]),
    ("Bushes", "Rust bush", "sp", [cut(SP_ASSETS, [39])]),
    ("Bushes", "Yellow bush", "sp", [cut(SP_ASSETS, [50, 51])]),
    ("Bushes", "Valley bush", "vr", [cut(VR_STONE, [44, 45, 49, 50])]),
    ("Bushes", "Autumn bush", "vr", [cut(VR_STONE, [46, 51])]),

    # ---- Flowers & plants ---------------------------------------------------
    ("Flowers & plants", "Fern", "sp", [cut(SP_ASSETS, [15, 16])]),
    ("Flowers & plants", "Flowering fern", "sp", [cut(SP_ASSETS, [17, 18])]),
    ("Flowers & plants", "Lily pad", "sp", [cut(SP_ASSETS, [26, 29, 34])]),
    ("Flowers & plants", "Puffball", "sp", [cut(SP_ASSETS, [28, 35])]),
    ("Flowers & plants", "Small plant", "fan", [files("Props/Plant_2.png")]),
    ("Flowers & plants", "Sprout", "vr", [cut(VR_STONE, [0, 1, 2])]),
    ("Flowers & plants", "Wildflower", "vr", [cut(VR_STONE, [4, 5, 6, 25])]),
    ("Flowers & plants", "Flower clump", "vr", [cut(VR_STONE, [15, 17, 18, 19])]),
    ("Flowers & plants", "Lupin", "vr", [cut(VR_STONE, [87, 88, 89, 90]), cut(VR_FLOWER, [9, 10])]),
    ("Flowers & plants", "Clover", "vr", [cut(VR_STONE, [93, 94])]),
    ("Flowers & plants", "Potted plant", "vr", [cut(VR_STONE, [85, 86, 91, 92]), cut(VR_FLOWER, [11, 12])]),
    ("Flowers & plants", "Sunflower", "vr", [cut(VR_FLOWER, [5, 6, 7])]),
    ("Flowers & plants", "Flower bed", "vr", [cut(VR_FLOWER, [8, 15, 16])]),
    ("Flowers & plants", "Bellflower", "vr", [cut(VR_FLOWER, [17, 18])]),
    ("Flowers & plants", "Leafy sprout", "vr", [cut(VR_FLOWER, [13, 14])]),
    ("Flowers & plants", "Ivy", "fl", [cut(FL_HOUSES, range(8, 21)), cut(FL_DECO, [2, 3])]),

    # ---- Grass tufts --------------------------------------------------------
    ("Grass tufts", "Olive grass tuft", "px", [cut(PX_PLANT, range(9, 24))]),
    ("Grass tufts", "Summer sprouts", "sp", [cut(SP_ASSETS, [44, 45, 56, 63, 64, 68])]),
    ("Grass tufts", "Tiny flowers", "sp", [cut(SP_ASSETS, [46, 47, 48, 60, 61, 62])]),
    ("Grass tufts", "Tall grass", "vr", [cut(VR_STONE, [16, 96, 97, 98, 99, 100, 101])]),
    ("Grass tufts", "Grass clump", "vr", [cut(VR_FLOWER, [0, 1, 2, 3, 4])]),
    ("Grass tufts", "Moss", "fl", [cut(FL_DECO, [14, 15, 18, 27])]),

    # ---- Mushrooms ----------------------------------------------------------
    ("Mushrooms", "Toadstools", "sp", [cut(SP_ASSETS, [27, 30])]),
    ("Mushrooms", "Valley mushrooms", "vr", [cut(VR_STONE, [12, 13, 14, 22, 23, 24])]),

    # ---- Rocks --------------------------------------------------------------
    ("Rocks", "Brown rock", "fan", [files(*(f"Rocks/Rock_Brown_{n}.png" for n in (1, 2, 4, 6, 9)))]),
    ("Rocks", "Grey rock", "px", [cut(PX_PROPS, [33, 34, 35, 36, 37, 38])]),
    ("Rocks", "Grey boulder", "px", [cut(PX_PROPS, [32])]),
    ("Rocks", "Pale rock", "sp", [cut(SP_ASSETS, [23, 24, 25, 41, 42])]),
    ("Rocks", "Sandstone rock", "sp", [cut(SP_ASSETS, [31, 32, 33, 52, 53])]),
    ("Rocks", "Pebbles", "sp", [cut(SP_ASSETS, [40, 43, 54, 55, 74, 75, 76, 77, 78])]),
    ("Rocks", "Rock in water", "sp", [cut(SP_ASSETS, [58, 59])]),
    ("Rocks", "Blue pebbles", "vr", [cut(VR_STONE, [7, 26, 27, 28, 95, 102, 103])]),
    ("Rocks", "Blue rock", "vr", [cut(VR_STONE, [20, 29, 32, 34, 30, 31, 33])]),
    ("Rocks", "Mossy rock", "vr", [cut(VR_STONE, [35, 36, 37, 38, 40])]),
    ("Rocks", "Boulder", "vr", [cut(VR_STONE, [39])]),
    ("Rocks", "Mossy boulder", "vr", [cut(VR_STONE, [48])]),
    ("Rocks", "Rubble", "fl", [cut(FL_DECO, [4, 16, 19, 32, 33, 34, 35, 36])]),

    # ---- Houses -------------------------------------------------------------
    ("Houses", "Hay cottage", "fan", [files("Buildings/House_Hay_1.png")]),
    ("Houses", "Hay house", "fan", [files("Buildings/House_Hay_2.png")]),
    ("Houses", "Hay farmhouse", "fan", [files("Buildings/House_Hay_3.png")]),
    ("Houses", "Purple hay house", "fan", [files("Buildings/House_Hay_4_Purple.png")]),
    *[("Houses", f"Timber house {n + 1}", "fl", [cut(FL_HOUSES, [i])])
      for n, i in enumerate([0, 1, 2, 3, 5, 6, 7])],
    ("Houses", "Timber manor", "fl", [cut(FL_HOUSES, [4])]),

    # ---- House parts (admin-only by default: building blocks, not decor) ----
    ("House parts", "Tower", "fl", [cut(FL_PARTS, [0])]),
    ("House parts", "Roof", "fl", [cut(FL_PARTS, [3, 7])]),
    ("House parts", "Wide roof", "fl", [cut(FL_PARTS, [4])]),
    ("House parts", "Thatched porch", "fl", [cut(FL_PARTS, [11, 13])]),
    ("House parts", "Door", "fl", [cut(FL_PARTS, [5, 6, 12, 24, 25])]),
    ("House parts", "Window", "fl", [cut(FL_PARTS, [14, 18, 22, 28, 30, 31, 35, 36])]),
    ("House parts", "Shutters", "fl", [cut(FL_PARTS, [15, 16, 19, 20])]),
    ("House parts", "Wall section", "fl", [cut(FL_PARTS, [26, 27])]),
    ("House parts", "Chimney", "fl", [cut(FL_PARTS, [21])]),
    ("House parts", "Dormer", "fl", [cut(FL_PARTS, [29])]),
    ("House parts", "Roof ridge", "fl", [cut(FL_PARTS, [32])]),
    ("House parts", "Planks", "fl", [cut(FL_PARTS, [1, 2, 9, 17, 34])]),
    ("House parts", "Straw", "fl", [cut(FL_PARTS, [8, 10])]),
    ("House parts", "Cross beam", "fl", [cut(FL_PARTS, [23])]),
    ("House parts", "Wooden door", "px", [cut(PX_PROPS, [11]), cut(PX_PROPS, [16, 17])]),

    # ---- Walls & ruins ------------------------------------------------------
    ("Walls & ruins", "City gate", "fan", [files("Buildings/CityWall_Gate_1.png")]),
    ("Walls & ruins", "Stone arch", "px", [cut(PX_STRUCT, [0, 4])]),
    ("Walls & ruins", "Stone wall", "px", [cut(PX_STRUCT, [1, 2, 3])]),
    ("Walls & ruins", "Mossy stone wall", "px", [cut(PX_STRUCT, [5, 6, 7])]),
    ("Walls & ruins", "Stone stairs", "px", [cut(PX_STRUCT, [8, 9, 10, 11])]),
    ("Walls & ruins", "Stone bricks", "px", [cut(PX_PROPS, [39, 40, 41])]),
    ("Walls & ruins", "Broken pillar", "px", [cut(PX_PROPS, [1, 12, 21])]),
    ("Walls & ruins", "Pillar", "px", [cut(PX_PROPS, [19])]),
    ("Walls & ruins", "Stone block", "px", [cut(PX_PROPS, [29])]),
    ("Walls & ruins", "Floor slab", "px", [cut(PX_PROPS, [2])]),
    ("Walls & ruins", "Stone pillar", "vr", [cut(VR_STONE, [52, 53, 54, 55, 56, 57, 58])]),
    ("Walls & ruins", "Mossy pillar", "vr", [cut(VR_STONE, [70, 71, 72, 73, 74, 75, 76])]),

    # ---- Monuments & graves -------------------------------------------------
    ("Monuments & graves", "Rune stone", "px", [cut(PX_PROPS, [0, 9])]),
    ("Monuments & graves", "Praying statue", "px", [cut(PX_PROPS, [6])]),
    ("Monuments & graves", "Sarcophagus", "px", [cut(PX_PROPS, [10])]),
    ("Monuments & graves", "Coffin", "px", [cut(PX_PROPS, [15])]),
    ("Monuments & graves", "Gravestone", "px", [cut(PX_PROPS, [20, 24, 25])]),
    ("Monuments & graves", "Stone cross", "px", [cut(PX_PROPS, [28])]),
    ("Monuments & graves", "Stone circle", "px", [cut(PX_PROPS, [26])]),
    ("Monuments & graves", "Ruined well", "px", [cut(PX_PROPS, [31])]),
    ("Monuments & graves", "Mossy monolith", "vr", [cut(VR_STONE, [8])]),
    ("Monuments & graves", "Grave tablets", "vr", [cut(VR_STONE, [83])]),
    ("Monuments & graves", "Stone head", "vr", [cut(VR_CHEST, [9, 10, 11])]),

    # ---- Fences & bridges ---------------------------------------------------
    ("Fences & bridges", "Wooden fence", "vr", [cut("Tiles Maps/fence.png", [0, 1])]),
    ("Fences & bridges", "Post", "sp", [cut(SP_ASSETS, [71, 72])]),
    ("Fences & bridges", "Rope fence", "sp", [cut(SP_ASSETS, [80])]),
    ("Fences & bridges", "Dock", "sp", [cut(SP_ASSETS, [79])]),
    ("Fences & bridges", "Pole", "fl", [cut(FL_DECO, [23, 24])]),
    ("Fences & bridges", "Plank fence", "fl", [cut(FL_PARTS, [33])]),
    ("Fences & bridges", "Loose planks", "fl", [cut(FL_DECO, [29, 30, 31])]),

    # ---- Signs & lamps ------------------------------------------------------
    ("Signs & lamps", "Sign", "fan", [files("Props/Sign_1.png", "Props/Sign_2.png")]),
    ("Signs & lamps", "Lamp post", "fan", [files("Props/LampPost_3.png")]),
    ("Signs & lamps", "Banner", "fan", [files("Props/Banner_Stick_1_Purple.png")]),
    ("Signs & lamps", "Bulletin board", "fan", [files("Props/BulletinBoard_1.png")]),
    ("Signs & lamps", "East-west signpost", "px", [cut(PX_PROPS, [18, 23])]),
    ("Signs & lamps", "Lantern pedestal", "px", [cut(PX_PROPS, [13])]),
    ("Signs & lamps", "Signpost", "sp", [cut(SP_ASSETS, [65, 66, 67])]),
    ("Signs & lamps", "Sign board", "sp", [cut(SP_ASSETS, [69, 70])]),
    ("Signs & lamps", "Notice board", "vr", [cut(VR_STONE, [3])]),

    # ---- Camp & furniture ---------------------------------------------------
    ("Camp & furniture", "Bench", "fan", [files("Props/Bench_1.png", "Props/Bench_3.png")]),
    ("Camp & furniture", "Table", "fan", [files("Props/Table_Medium_1.png")]),
    ("Camp & furniture", "Fireplace", "fan", [files("Props/Fireplace_1.png")]),
    ("Camp & furniture", "Hay stack", "fan", [files("Props/HayStack_2.png")]),
    ("Camp & furniture", "Hay-roof well", "fan", [files("Buildings/Well_Hay_1.png")]),
    ("Camp & furniture", "Stone bench", "px", [cut(PX_PROPS, [5])]),
    ("Camp & furniture", "Campfire", "sp", [cut(SP_ASSETS, [73])]),
    ("Camp & furniture", "Tent", "sp", [cut(SP_ASSETS, [81])]),
    ("Camp & furniture", "Training dummy", "vr", [cut(VR_CHEST, [8])]),
    ("Camp & furniture", "Well", "fl", [cut(FL_DECO, [6])]),
    ("Camp & furniture", "Hay bale", "fl", [cut(FL_DECO, [20])]),
    ("Camp & furniture", "Ladder", "fl", [cut(FL_DECO, [9])]),
    ("Camp & furniture", "Supplies", "fl", [cut(FL_DECO, [8, 25, 41])]),
    ("Camp & furniture", "Market stall bits", "fl", [cut(FL_DECO, [12, 28])]),

    # ---- Containers ---------------------------------------------------------
    ("Containers", "Small barrel", "fan", [files("Props/Barrel_Small_Empty.png")]),
    ("Containers", "Basket", "fan", [files("Props/Basket_Empty.png")]),
    ("Containers", "Crate", "fan", [files("Props/Crate_Large_Empty.png", "Props/Crate_Medium_Closed.png")]),
    ("Containers", "Water crate", "fan", [files("Props/Crate_Water_1.png")]),
    ("Containers", "Sack", "fan", [files("Props/Sack_3.png")]),
    ("Containers", "Iron-bound chest", "px", [cut(PX_PROPS, [3])]),
    ("Containers", "Wardrobe", "px", [cut(PX_PROPS, [7])]),
    ("Containers", "Wooden crate", "px", [cut(PX_PROPS, [4, 8])]),
    ("Containers", "Barrel", "px", [cut(PX_PROPS, [14])]),
    ("Containers", "Clay vase", "px", [cut(PX_PROPS, [22, 30])]),
    ("Containers", "Clay pot", "px", [cut(PX_PROPS, [27])]),
    ("Containers", "Urn", "vr", [cut(VR_STONE, [59, 60, 61, 62])]),
    ("Containers", "Small urn", "vr", [cut(VR_STONE, [66, 67, 68, 69])]),
    ("Containers", "Pot", "vr", [cut(VR_STONE, [77, 78, 79, 80])]),
    ("Containers", "Treasure chest", "vr", [cut(VR_CHEST, [0, 1, 2, 3])]),
    ("Containers", "Open treasure chest", "vr", [cut(VR_CHEST, [4, 5, 6, 7])]),
    ("Containers", "Wooden chest", "vr", [cut(VR_STONE, [82, 84])]),
    ("Containers", "Timber barrel", "fl", [cut(FL_DECO, [5])]),
    ("Containers", "Timber crate", "fl", [cut(FL_DECO, [10, 26])]),
    ("Containers", "Broken crate", "fl", [cut(FL_DECO, [7, 17])]),
    ("Containers", "Grain sack", "fl", [cut(FL_DECO, [21, 22])]),
    ("Containers", "Crate stack", "fl", [cut(FL_DECO, [40])]),

    # ---- Items --------------------------------------------------------------
    ("Items", "Gem", "vr", [cut("Objects/Items.png", [0, 1, 13, 14])]),
    ("Items", "Coin", "vr", [cut("Objects/Items.png", [2])]),
    ("Items", "Food", "vr", [cut("Objects/Items.png", [3, 4, 5, 6, 7, 11, 19])]),
    ("Items", "Stone", "vr", [cut("Objects/Items.png", [8])]),
    ("Items", "Bone", "vr", [cut("Objects/Items.png", [9])]),
    ("Items", "Stick", "vr", [cut("Objects/Items.png", [10, 16, 24, 25])]),
    ("Items", "Weapon", "vr", [cut("Objects/Items.png", [12, 22, 27])]),
    ("Items", "Tool", "vr", [cut("Objects/Items.png", [20, 21, 23, 31, 32, 33, 34])]),
    ("Items", "Potion", "vr", [cut("Objects/Items.png", [17, 18])]),
    ("Items", "Scroll", "vr", [cut("Objects/Items.png", [15, 26])]),
    ("Items", "Key", "vr", [cut("Objects/Items.png", [28, 29, 30])]),
    ("Items", "Dog bone", "dog", [cut("DogItems.png", [0, 1])]),
    ("Items", "Dog treat", "dog", [cut("DogItems.png", [2, 3, 4, 5, 7])]),
    ("Items", "Leash", "dog", [cut("DogItems.png", [6, 8])]),
]


# --------------------------------------------------------------------------- #
#  Cutting
# --------------------------------------------------------------------------- #
def _islands(alpha):
    h, w = alpha.shape
    label = np.zeros((h, w), dtype=np.int32)
    info = []
    current = 0
    for y0, x0 in zip(*np.nonzero(alpha)):
        if label[y0, x0]:
            continue
        current += 1
        queue = deque([(y0, x0)])
        label[y0, x0] = current
        xs, ys, n = [x0, x0], [y0, y0], 0
        while queue:
            y, x = queue.popleft()
            n += 1
            xs[0], xs[1] = min(xs[0], x), max(xs[1], x)
            ys[0], ys[1] = min(ys[0], y), max(ys[1], y)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not label[ny, nx]:
                        label[ny, nx] = current
                        queue.append((ny, nx))
        info.append({"id": current, "box": (int(xs[0]), int(ys[0]), int(xs[1]) + 1, int(ys[1]) + 1),
                     "area": n})
    return label, info


def cut_sprites(image: Image.Image, min_side: int = 6, speck_area: int = 24) -> list[Image.Image]:
    """Every sprite on a sheet, in reading order, each cut by its own pixels.

    Specks (a stray leaf, a sparkle) join the big island whose box holds them.
    """
    arr = np.asarray(image.convert("RGBA")).copy()
    label, info = _islands(arr[..., 3] > 16)
    big = [i for i in info if i["area"] > speck_area]
    owner = {}
    for small in (i for i in info if i["area"] <= speck_area):
        sx0, sy0, sx1, sy1 = small["box"]
        for b in big:
            x0, y0, x1, y1 = b["box"]
            if x0 <= sx0 and y0 <= sy0 and sx1 <= x1 and sy1 <= y1:
                owner[small["id"]] = b["id"]
                break
    pieces = []
    for b in big:
        x0, y0, x1, y1 = b["box"]
        if x1 - x0 < min_side or y1 - y0 < min_side:
            continue
        ids = [b["id"]] + [sid for sid, bid in owner.items() if bid == b["id"]]
        piece = arr[y0:y1, x0:x1].copy()
        piece[~np.isin(label[y0:y1, x0:x1], ids)] = 0
        pieces.append(((x0, y0), Image.fromarray(piece)))
    pieces.sort(key=lambda p: (p[0][1] // 16, p[0][0]))
    return [image for _, image in pieces]


class Packs:
    """Reads images straight out of the pack zips, caching sheets and cuts."""

    def __init__(self, folder: pathlib.Path) -> None:
        self.folder = folder
        self._zips: dict[str, zipfile.ZipFile] = {}
        self._sheets: dict[tuple, Image.Image] = {}
        self._cuts: dict[tuple, list[Image.Image]] = {}

    def image(self, pack: str, path: str) -> Image.Image:
        key = (pack, path)
        if key not in self._sheets:
            zip_name, inside, _, _ = PACKS[pack]
            if pack not in self._zips:
                self._zips[pack] = zipfile.ZipFile(self.folder / zip_name)
            data = self._zips[pack].read(inside + path)
            self._sheets[key] = Image.open(io.BytesIO(data)).convert("RGBA")
        return self._sheets[key]

    def variants(self, pack: str, source) -> list[Image.Image]:
        kind = source[0]
        if kind == "files":
            return [self.image(pack, path) for path in source[1]]
        if kind == "cells":
            _, sheet, size, ids = source
            image = self.image(pack, sheet)
            cols = image.width // size
            return [image.crop(((i % cols) * size, (i // cols) * size,
                                (i % cols) * size + size, (i // cols) * size + size)) for i in ids]
        if kind == "cut":
            _, sheet, ids = source
            key = (pack, sheet)
            if key not in self._cuts:
                self._cuts[key] = cut_sprites(self.image(pack, sheet))
            found = self._cuts[key]
            missing = [i for i in ids if i >= len(found)]
            if missing:
                raise SystemExit(f"{pack}:{sheet} has {len(found)} sprites; asked for {missing}")
            return [found[i] for i in ids]
        raise ValueError(kind)


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def build(folder: pathlib.Path) -> list[dict]:
    """Every tile in the manifest, as plain data, with its variants as PNG bytes."""
    packs = Packs(folder)
    defaults = dict(CATEGORIES)
    out = []
    for entry in MANIFEST:
        category, name, pack, sources = entry[:4]
        if category not in defaults:
            raise SystemExit(f"{name}: unknown category {category!r}")
        uses = entry[4] if len(entry) > 4 else defaults[category]
        images = [image for source in sources for image in packs.variants(pack, source)]
        out.append({"category": category, "name": name, "pack": PACKS[pack][2],
                    "cell_px": PACKS[pack][3], "uses": uses,
                    "source": f"{pack}:{name}", "images": images})
    return out


def preview(tiles: list[dict], path: str) -> None:
    """Everything the import would write, one row per tile, for looking at first."""
    row_h, label_w, width = 70, 300, 1500
    board = Image.new("RGBA", (width, row_h * len(tiles) + 10), (40, 40, 48, 255))
    draw = ImageDraw.Draw(board)
    for r, tile in enumerate(tiles):
        y = 5 + r * row_h
        draw.text((6, y + 4), f"{tile['category']} / {tile['name']}", fill=(255, 255, 0, 255))
        draw.text((6, y + 20), f"{tile['pack']} · {tile['cell_px']}px · {len(tile['images'])} var",
                  fill=(190, 190, 200, 255))
        draw.text((6, y + 36), ", ".join(tile["uses"]), fill=(150, 220, 150, 255))
        x = label_w
        for image in tile["images"]:
            k = min(64 / image.width, 64 / image.height)
            k = int(k) if k >= 1 else k
            small = image.resize((max(1, int(image.width * k)), max(1, int(image.height * k))),
                                 Image.NEAREST)
            if x + small.width > width:
                break
            board.alpha_composite(small, (x, y))
            x += small.width + 4
    board.save(path)


def write(tiles: list[dict]) -> None:
    from config import database
    from helpers.dodoland.tiles import TileLibrary

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                          database.dodoland_tile_art)
    have = {cat["name"]: cat["cat_id"] for cat in library.categories()}
    for name, _ in CATEGORIES:
        if name not in have:
            have[name] = library.add_category(name)["cat_id"]
    added = kept = 0
    for tile in tiles:
        if library.by_source(tile["source"]):
            kept += 1
            continue
        first, *rest = tile["images"]
        row = library.add_tile(name=tile["name"], cat_id=have[tile["category"]],
                               data=png(first), content_type="image/png",
                               uses=tile["uses"], cell_px=tile["cell_px"],
                               pack=tile["pack"], source=tile["source"])
        for image in rest:
            library.add_variant(row["tile_id"], data=png(image), content_type="image/png")
        added += 1
    print(f"added {added} tiles, {kept} were already there")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=pathlib.Path, help="the folder holding the pack zips")
    parser.add_argument("--preview", help="write a PNG of what would be imported, and stop")
    args = parser.parse_args()
    tiles = build(args.folder)
    print(f"{len(tiles)} tiles, {sum(len(t['images']) for t in tiles)} images, "
          f"{len(CATEGORIES)} categories")
    if args.preview:
        preview(tiles, args.preview)
        print("preview written to", args.preview)
        return
    write(tiles)


if __name__ == "__main__":
    main()
