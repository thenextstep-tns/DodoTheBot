"""
Rebuild a server's terrain grid at a new resolution, from the reference map.

    py tools/dodoland_terrain_regrid.py GUILD --factor 4 --features f.json --preview p.png
    py tools/dodoland_terrain_regrid.py GUILD --factor 4 --features f.json --write --backup b.json

A grid of 958 cells across a whole continent makes a cell the size of a house,
so nothing on the map can be finer than that — not a river, not a coastline.
This redraws the world ``factor`` times finer from the **vector** reference map
the server uploaded (coastlines stay smooth: they are re-rasterised, not blown
up from old cells), then adds terrain on top:

* ``rivers`` — polylines in map fractions with a width (also a fraction), drawn
  at least ``--river-cells`` wide, as water;
* ``regions`` — ellipses in map fractions (``{"kind", "cx", "cy", "rx", "ry"}``)
  painted over land in order fields, dunes, forest, swamp, hills, mountains,
  ponds; scattered forest and swamp pieces are merged into continuous ground;
* the open sea — water more than ``--band`` cells from land and connected to the
  map's edge — becomes deep water; a light band stays along every coast.

Features are given in fractions of the map, so the same file works at any
resolution. Every cell is a library tile afterwards; mountains are their own
blocking kind so their stone stays a road surface elsewhere. Positions of towns
and placed pieces are percentages, so they do not move.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

LAND_COLOURS = {"#e8eff4"}
LAKE_COLOURS = {"#99b3e4"}
TILES = {"land": "fan:Meadow grass", "water": "fan:Lake water", "deep": "sp:Deep water",
         "fields": "sp:Summer grass", "dunes": "sp:Summer sand", "forest": "px:Olive grass",
         "swamp": "vr:Valley grass", "hills": "vr:Valley dirt", "mountains": "px:Stone paving",
         "ponds": "fan:Lake water"}
ORDER = ["fields", "dunes", "forest", "swamp", "hills", "mountains", "ponds"]
BLOCKING = {"mountains"}


# --------------------------------------------------------------------------- #
#  A small SVG path rasteriser: M m L l H h V v C c Z z, even-odd fill.
# --------------------------------------------------------------------------- #
def _tokens(d: str):
    for match in re.finditer(r"[MmLlHhVvCcZz]|-?\d*\.?\d+(?:e-?\d+)?", d):
        yield match.group(0)


def subpaths(d: str, steps: int = 10) -> list[list[tuple[float, float]]]:
    out, cur, x, y, start = [], [], 0.0, 0.0, (0.0, 0.0)
    tokens = list(_tokens(d))
    i, cmd = 0, ""

    def num():
        nonlocal i
        i += 1
        return float(tokens[i - 1])

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    out.append(cur)
                cur, (x, y) = [], start
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if cur:
                out.append(cur)
            cur, start = [(x, y)], (x, y)
            cmd = "l" if rel else "L"          # later pairs are line-tos
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            cur.append((x, y))
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            cur.append((x, y))
        elif c == "C":
            pts = [num() for _ in range(6)]
            if rel:
                pts = [pts[k] + (x if k % 2 == 0 else y) for k in range(6)]
            x1, y1, x2, y2, x3, y3 = pts
            for n in range(1, steps + 1):
                t = n / steps
                a, b, cc, dd = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                cur.append((a * x + b * x1 + cc * x2 + dd * x3, a * y + b * y1 + cc * y2 + dd * y3))
            x, y = x3, y3
        else:
            i += 1
    if cur:
        out.append(cur)
    return out


def rasterise(svg: str, width: int, height: int):
    """``(colours, grid)``: the fill colour index of every pixel, painted in order."""
    import numpy as np
    from PIL import Image, ImageDraw

    box = re.search(r'viewBox="([\d.\-\s]+)"', svg)
    vx, vy, vw, vh = (float(v) for v in box.group(1).split())
    sx, sy = width / vw, height / vh
    colours, grid = [], np.zeros((height, width), dtype=np.int16) - 1
    for group in re.finditer(r'<g[^>]*fill="(#[0-9a-fA-F]{6})"[^>]*>(.*?)</g>', svg, re.S):
        colour = group.group(1).lower()
        colours.append(colour)
        for d in re.findall(r'<path[^>]* d="([^"]*)"', group.group(2)):
            mask = np.zeros((height, width), dtype=bool)
            for poly in subpaths(d):
                if len(poly) < 3:
                    continue
                layer = Image.new("1", (width, height), 0)
                ImageDraw.Draw(layer).polygon([((px - vx) * sx, (py - vy) * sy) for px, py in poly], fill=1)
                mask ^= np.array(layer, dtype=bool)
            grid[mask] = len(colours) - 1
    return colours, grid, (vw, vh)


def grow(mask, times: int):
    from PIL import Image, ImageFilter
    import numpy as np
    image = Image.fromarray((mask * 255).astype("uint8"))
    for _ in range(times):
        image = image.filter(ImageFilter.MaxFilter(3))
    return np.array(image) > 0


def shrink(mask, times: int):
    from PIL import Image, ImageFilter
    import numpy as np
    image = Image.fromarray((mask * 255).astype("uint8"))
    for _ in range(times):
        image = image.filter(ImageFilter.MinFilter(3))
    return np.array(image) > 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("--factor", type=float, default=4.0)
    parser.add_argument("--features", type=pathlib.Path)
    parser.add_argument("--band", type=int, default=0, help="coastal band in cells (default 3 x factor)")
    parser.add_argument("--river-cells", type=float, default=3.0)
    parser.add_argument("--close", type=int, default=0, help="forest gap closing in cells (default 2 x factor)")
    parser.add_argument("--preview", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", type=pathlib.Path, default=pathlib.Path("dodoland_before_regrid.json"))
    args = parser.parse_args()

    import numpy as np
    from PIL import Image, ImageDraw

    from config import database
    from helpers.dodoland import terrain as T
    from helpers.dodoland.buildings import BuildingStore
    from helpers.dodoland.tiles import TileLibrary

    image = BuildingStore(database.dodoland_config).map_image(args.guild)
    if not image or "svg" not in str(image.get("content_type")):
        raise SystemExit("This server's reference map is not an SVG; nothing to redraw from.")
    svg = bytes(image["data"]).decode("utf-8", "replace")
    box = re.search(r'viewBox="([\d.\-\s]+)"', svg)
    vw, vh = (float(v) for v in box.group(1).split()[2:])
    W, H = int(round(vw * args.factor)), int(round(vh * args.factor))
    band = args.band or int(round(3 * args.factor))
    closing = args.close or int(round(2 * args.factor))
    print(f"grid {W} x {H} ({W * H:,} cells), coastal band {band}, forest closing {closing}")

    colours, grid, _ = rasterise(svg, W, H)
    land = np.isin(grid, [colours.index(c) for c in colours if c in LAND_COLOURS])
    lake = np.isin(grid, [colours.index(c) for c in colours if c in LAKE_COLOURS])
    water = ~land

    features = json.loads(args.features.read_text(encoding="utf-8")) if args.features else {}
    rivers = Image.new("1", (W, H), 0)
    draw = ImageDraw.Draw(rivers)
    for river in features.get("rivers", []):
        pts = [(x * W, y * H) for x, y in river["points"]]
        width = max(args.river_cells, float(river.get("width", 0)) * W)
        if len(pts) > 1:
            draw.line(pts, fill=1, width=int(round(width)), joint="curve")
        for x, y in pts:
            r = width / 2
            draw.ellipse([x - r, y - r, x + r, y + r], fill=1)
    river = np.array(rivers, dtype=bool) & land
    land = land & ~river

    kinds_mask = {}
    for kind in ORDER:
        layer = Image.new("1", (W, H), 0)
        dr = ImageDraw.Draw(layer)
        for r in features.get("regions", []):
            if r["kind"] == kind:
                cx, cy, rx, ry = r["cx"] * W, r["cy"] * H, r["rx"] * W, r["ry"] * H
                dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=1)
        mask = np.array(layer, dtype=bool)
        if kind in ("forest", "swamp"):
            mask = shrink(grow(mask, closing), closing) | mask
        kinds_mask[kind] = mask & land

    near = grow(land | river, band)
    far = water & ~near
    # A copy: an image made straight from an array shares its buffer and a
    # flood fill on it silently does nothing.
    reach = Image.fromarray((far * 255).astype("uint8")).copy()
    # Seeded a few cells in from the edge: a filled polygon can leave the very
    # last row and column of the raster unpainted, which reads as land.
    edge = 3
    seeds = ([(x, edge) for x in range(edge, W - edge, 20)] + [(x, H - 1 - edge) for x in range(edge, W - edge, 20)]
             + [(edge, y) for y in range(edge, H - edge, 20)] + [(W - 1 - edge, y) for y in range(edge, H - edge, 20)])
    for x, y in seeds:
        if reach.getpixel((x, y)) == 255:
            ImageDraw.floodfill(reach, (x, y), 128)
    deep = np.array(reach) == 128

    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)
    tiles = {k: library.by_source(s) for k, s in TILES.items()}
    missing = [TILES[k] for k, t in tiles.items() if not t]
    if missing:
        raise SystemExit(f"tiles not in the library: {missing}")

    def hex_of(tile):
        art = library.art(tile["variants"][0])
        with Image.open(io.BytesIO(bytes(art["data"]))) as im:
            rgb = im.convert("RGBA").resize((1, 1), Image.BOX).getpixel((0, 0))
        return "#%02x%02x%02x" % rgb[:3]

    kinds, index = [T.base_kinds()[0]], {}
    for name in ["land", "water", "deep"] + ORDER:
        tile = tiles[name]
        key = T.TILE_PREFIX + tile["tile_id"]
        if name in BLOCKING:
            kinds.append({**T.tile_kind(tile, hex_of(tile)), "key": f"{key}_{name}",
                          "label": name.capitalize(), "move": None, "grow": None,
                          "build": False, "fixed": True})
            index[name] = len(kinds) - 1
            continue
        found = next((i for i, k in enumerate(kinds) if k["key"] == key), None)
        if found is None:
            kinds.append(T.tile_kind(tile, hex_of(tile)))
            found = len(kinds) - 1
        index[name] = found

    out = np.zeros((H, W), dtype=np.int16)
    out[land] = index["land"]
    out[water | river] = index["water"]
    out[deep] = index["deep"]
    for kind in ORDER:
        out[kinds_mask[kind]] = index[kind]
    counts = {k["label"]: int((out == i).sum()) for i, k in enumerate(kinds) if (out == i).any()}
    print("cells:", counts)

    if args.preview:
        palette = np.array([[int(k.get("hex", "#141414")[j:j + 2], 16) for j in (1, 3, 5)] for k in kinds],
                           dtype=np.uint8)
        Image.fromarray(palette[out]).save(args.preview)
        print("preview:", args.preview)
    if not args.write:
        print("dry run; pass --write")
        return

    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)
    from bson import json_util
    before = {"world": database.dodoland_world.find_one({"_id": args.guild}),
              "chunks": list(database.dodoland_chunks.find({"guild_id": args.guild}))}
    args.backup.write_text(json_util.dumps(before), encoding="utf-8")
    store.wipe(args.guild, T.TERRAIN)
    store.set_world(args.guild, cells_w=W, cells_h=H, source_w=int(vw), source_h=int(vh), kinds=kinds)
    C = T.CHUNK
    for cy in range(-(-H // C)):
        for cx in range(-(-W // C)):
            block = np.zeros((C, C), dtype=np.int16)
            part = out[cy * C:(cy + 1) * C, cx * C:(cx + 1) * C]
            block[:part.shape[0], :part.shape[1]] = part
            store.write_chunk(args.guild, cx, cy, block.flatten().tolist())
    store.touch(args.guild)
    print(f"written: {W} x {H}, {-(-W // C) * -(-H // C)} chunks; backup {args.backup}")


if __name__ == "__main__":
    main()
