"""
Generate an upload-ready tile bundle JSON for an approved category.

Usage:
    py tools/dodoland_mapart_bundle.py <category-slug> [--separate-category]
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import pathlib
import sys

DODOART_ROOT = pathlib.Path(r"C:\Users\Lenovo\Documents\DodoArt")
MAPART_DIR = DODOART_ROOT / "art_batches" / "mapart"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create upload bundle for approved category.")
    parser.add_argument("category_slug", help="Category slug to build bundle for")
    parser.add_argument("--separate-category", action="store_true",
                        help="Prefix category name with 'Pixel art · ' instead of original category")
    args = parser.parse_args()

    c_slug = args.category_slug
    manifest_p = MAPART_DIR / "manifest.json"
    sizes_p = MAPART_DIR / "sizes.csv"
    hires_dir = MAPART_DIR / "hires" / c_slug
    px_dir = MAPART_DIR / "px" / c_slug
    bundles_dir = MAPART_DIR / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    sizes_map = {}
    with sizes_p.open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sizes_map[r["name"]] = r

    cat_tiles = [t for t in manifest if t.get("category_slug") == c_slug]
    if not cat_tiles:
        raise SystemExit(f"No tiles found for category slug {c_slug}")

    bundle = []
    for t in cat_tiles:
        name = t["name"]
        t_slug = t["tile_slug"]
        img_p = hires_dir / f"{t_slug}.png"
        if not img_p.exists():
            img_p = px_dir / f"{t_slug}.png"
        if not img_p.exists():
            raise SystemExit(f"Missing art for {name}: {img_p}")

        img_b64 = base64.b64encode(img_p.read_bytes()).decode("ascii")

        orig_cat = t["category"]
        if args.separate_category:
            sub = orig_cat.split("·", 1)[-1].strip() if "·" in orig_cat else orig_cat
            cat_name = f"Pixel art · {sub}"
        else:
            cat_name = orig_cat

        s_info = sizes_map.get(name, {})
        cell_px = int(s_info.get("px_per_cell") or 16)

        layer = t.get("layer", "objects")
        access = t.get("access", ["admin"])
        uses = [f"{layer}:{role}" for role in access]

        entry = {
            "category": cat_name,
            "name": name,
            "pack": "DodoLand Map art, pixel",
            "source": f"pixel:{t['source']}",
            "cell_px": cell_px,
            "uses": uses,
            "images": [img_b64],
            "resizable": t.get("resizable", True),
            "passable": t.get("passable", True),
        }
        bundle.append(entry)

    out_bundle_path = bundles_dir / f"{c_slug}.json"
    out_bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Created upload bundle with {len(bundle)} tiles at {out_bundle_path}")


if __name__ == "__main__":
    main()
