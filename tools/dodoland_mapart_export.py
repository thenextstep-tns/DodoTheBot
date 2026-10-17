"""
Export original black-and-white Map art engravings from the tile library.

Usage:
    py tools/dodoland_mapart_export.py [--out-dir PATH] [--scale FLOAT]
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config import database
from helpers.dodoland.tiles import TileLibrary


def slugify(text: str) -> str:
    """Turn a name or label into a clean filesystem slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "tile"


def category_slug(cat_name: str) -> str:
    """Slug for a Map art category, stripping the 'Map art · ' prefix."""
    sub = cat_name.split("·", 1)[-1].strip() if "·" in cat_name else cat_name
    return slugify(sub)


def get_clamp_range(category: str) -> tuple[int, int]:
    """Return (min_cells, max_cells) for a category."""
    cat = category.lower()
    if any(k in cat for k in ("castle",)):
        return (4, 10)
    if any(k in cat for k in ("boat", "settlement")):
        return (3, 8)
    if any(k in cat for k in ("mountain", "hill", "field", "dune", "moronobu")):
        return (4, 12)
    if any(k in cat for k in ("dude", "crowd", "animal", "monster", "angel", "death", "bella")):
        return (1, 3)
    return (1, 4)


def clamp_width(size_cells: float, category: str) -> int:
    min_c, max_c = get_clamp_range(category)
    rounded = round(size_cells)
    return max(min_c, min(max_c, rounded))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export original Map art tiles.")
    parser.add_argument("--out-dir", type=pathlib.Path, default=REPO_ROOT / "art_batches" / "mapart",
                        help="Output directory for mapart batches")
    parser.add_argument("--scale", type=float, default=None,
                        help="Tile scale override (default: from dodoland_params or 1.25)")
    parser.add_argument("--force-sizes", action="store_true",
                        help="Overwrite sizes.csv even if it exists")
    args = parser.parse_args()

    out_dir = args.out_dir
    originals_dir = out_dir / "originals"
    originals_dir.mkdir(parents=True, exist_ok=True)

    tile_scale = args.scale
    if tile_scale is None:
        param = database.dodoland_params.find_one({"key": "dodoland_tile_scale"})
        tile_scale = float(param["value"]) if param and "value" in param else 1.25

    print(f"Connecting to tile library (tile scale: {tile_scale})...")
    library = TileLibrary(database.dodoland_tiles, database.dodoland_tile_cats, database.dodoland_tile_art)

    cat_map = {c["cat_id"]: c["name"] for c in library.categories()}

    all_tiles = library.tiles()
    mapart_tiles = []
    for t in all_tiles:
        cat_name = cat_map.get(t["cat_id"], "")
        if "map art" in cat_name.lower() and cat_name.lower() != "map art · ground":
            mapart_tiles.append((cat_name, t))

    mapart_tiles.sort(key=lambda item: (item[0], item[1].get("order", 0), item[1]["name"]))

    print(f"Found {len(mapart_tiles)} Map art tiles across categories.")

    manifest = []
    sizes_rows = []
    category_counts = {}

    for cat_name, tile in mapart_tiles:
        c_slug = category_slug(cat_name)
        t_slug = slugify(tile["name"])
        cat_dir = originals_dir / c_slug
        cat_dir.mkdir(parents=True, exist_ok=True)

        img_path = cat_dir / f"{t_slug}.png"
        rel_img_path = f"originals/{c_slug}/{t_slug}.png"

        variant_ids = tile.get("variants") or []
        if not variant_ids:
            print(f"Warning: Tile {tile['name']} ({tile['tile_id']}) has no variants!")
            continue

        art = library.art(variant_ids[0])
        if not art or not art.get("data"):
            print(f"Warning: No art data for tile {tile['name']} variant {variant_ids[0]}")
            continue

        img_path.write_bytes(art["data"])

        art_w = art.get("w") or 0
        art_h = art.get("h") or 0
        cell_px = tile.get("cell_px") or 16
        size_cells = round(art_w / cell_px / tile_scale, 3)

        manifest_entry = {
            "tile_id": tile["tile_id"],
            "source": tile.get("source", ""),
            "category": cat_name,
            "category_slug": c_slug,
            "name": tile["name"],
            "tile_slug": t_slug,
            "layer": tile.get("layer", "objects"),
            "access": tile.get("access", ["admin"]),
            "passable": tile.get("passable", True),
            "resizable": tile.get("resizable", False),
            "cell_px": cell_px,
            "art_w": art_w,
            "art_h": art_h,
            "size_cells": size_cells,
            "image_path": rel_img_path,
        }
        manifest.append(manifest_entry)

        clamped_w = clamp_width(size_cells, cat_name)
        sizes_rows.append({
            "category": cat_name,
            "name": tile["name"],
            "source": tile.get("source", ""),
            "width_cells": clamped_w,
            "height_cells": "",
            "px_per_cell": 16,
        })

        category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

    manifest_file = out_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote manifest with {len(manifest)} tiles to {manifest_file}")

    sizes_file = out_dir / "sizes.csv"
    if args.force_sizes or not sizes_file.exists():
        with sizes_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["category", "name", "source", "width_cells", "height_cells", "px_per_cell"])
            writer.writeheader()
            writer.writerows(sizes_rows)
        print(f"Wrote sizes.csv with {len(sizes_rows)} entries to {sizes_file}")
    else:
        print(f"sizes.csv already exists at {sizes_file} (use --force-sizes to overwrite)")

    print("\n--- Map art counts per category ---")
    for cat, count in sorted(category_counts.items()):
        print(f"{cat}: {count}")
    print(f"\nTotal: {sum(category_counts.values())} tiles in {len(category_counts)} categories")


if __name__ == "__main__":
    main()
