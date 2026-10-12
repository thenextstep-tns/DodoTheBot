"""
Place a prepared plan on a server's map: world decor pieces and painted strokes.

    py tools/dodoland_place_plan.py GUILD plan.json                     # report
    py tools/dodoland_place_plan.py GUILD plan.json --write             # do it
    py tools/dodoland_place_plan.py GUILD --rollback backup.json        # undo the strokes

A plan is JSON::

    {"decor":   [{"tile_source", "variant": n, "x": %, "y": %, "width_cells", "source"}],
     "strokes": [{"radius", "points": [[x, y], ...] in cells, "source"}],
     "stroke_kind": "river"}

Decor positions are percentages of the base image, the way every piece is
stored. A piece's size is its wanted width in map cells over the tile's natural
width (its first image's width over its px-per-cell), clamped to the tile's own
range — so it lands the size it was drawn at.

**Re-runnable.** A piece carries its ``source``; one already on the map is left
alone. Strokes are painted with the named kind (default ``river``), and the
chunks they touch are saved to ``--backup`` first so ``--rollback`` can put the
ground back exactly.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("guild", type=int)
    parser.add_argument("plan", nargs="?", type=pathlib.Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", type=pathlib.Path, default=pathlib.Path("dodoland_terrain_backup.json"))
    parser.add_argument("--rollback", type=pathlib.Path)
    args = parser.parse_args()

    from config import database
    from helpers.dodoland import decor as decor_rules
    from helpers.dodoland import terrain as T
    from helpers.dodoland import tiles as tile_rules

    store = T.TerrainStore(database.dodoland_chunks, database.dodoland_world)
    if args.rollback:
        snap = {tuple(map(int, k.split(","))): v
                for k, v in json.loads(args.rollback.read_text(encoding="utf-8")).items()}
        print(f"restored {store.restore(args.guild, snap)} chunks")
        store.touch(args.guild)
        return

    library = tile_rules.TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats,
                                     database.dodoland_tile_art)
    decor = decor_rules.DecorStore(database.dodoland_decor)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))

    have = decor.sources(args.guild)
    tiles, sizes, todo, unknown = {}, {}, [], 0
    for piece in plan.get("decor", []):
        if piece["source"] in have:
            continue
        src = piece["tile_source"]
        if src not in tiles:
            tiles[src] = library.by_source(src)
        tile = tiles[src]
        if not tile or not tile["variants"]:
            unknown += 1
            continue
        todo.append((piece, tile))
    vids = {t["variants"][0] for t in tiles.values() if t and t["variants"]}
    sizes = library.art_sizes(vids)
    print(f"decor: {len(todo)} to place, {len(have)} already placed, {unknown} with no tile")

    world = store.world(args.guild)
    kind = T.index_of(world["kinds"], plan.get("stroke_kind", "river"))
    strokes = plan.get("strokes", [])
    edits = {}
    for stroke in strokes:
        r = int(stroke.get("radius") or 0)
        disc = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                if dx * dx + dy * dy <= r * r]
        pts = stroke["points"]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] or pts):
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for n in range(steps + 1):
                cx = round(x0 + (x1 - x0) * n / steps)
                cy = round(y0 + (y1 - y0) * n / steps)
                for dx, dy in disc:
                    x, y = cx + dx, cy + dy
                    if 0 <= x < world["cells_w"] and 0 <= y < world["cells_h"]:
                        edits[(x, y)] = kind
    print(f"strokes: {len(strokes)}, {len(edits)} cells as {world['kinds'][kind]['key']}")
    if not args.write:
        print("dry run; pass --write")
        return

    keys = sorted({(x // T.CHUNK, y // T.CHUNK) for x, y in edits})
    snap = store.snapshot(args.guild, keys)
    args.backup.write_text(json.dumps({f"{cx},{cy}": v for (cx, cy), v in snap.items()}),
                           encoding="utf-8")
    store.paint(args.guild, edits)
    store.touch(args.guild)
    print(f"painted {len(edits)} cells in {len(keys)} chunks (backup: {args.backup})")

    placed = 0
    for piece, tile in todo:
        w, _ = sizes.get(tile["variants"][0], (0, 0))
        natural = (w / tile["cell_px"]) if w else 1.0
        n = int(piece.get("variant") or 0)
        variant = tile["variants"][n] if n < len(tile["variants"]) else tile["variants"][0]
        decor.place(args.guild, scope=decor_rules.SCOPE_WORLD, asset_id=tile["tile_id"],
                    x=piece["x"], y=piece["y"], scale=piece["width_cells"] / natural,
                    scale_range=tile_rules.scale_range(tile), variant=variant,
                    source=piece["source"])
        placed += 1
    print(f"placed {placed} pieces")


if __name__ == "__main__":
    main()
