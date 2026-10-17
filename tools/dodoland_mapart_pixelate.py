"""
Post-processing pipeline for redrawn Map art pixel tiles.

Cleans raw generated images:
1. Removes non-transparent background;
2. Trims to the drawn area;
3. Resizes to exactly width_cells x px_per_cell (height from aspect or height_cells) with nearest neighbour;
4. Enforces hard alpha (opaque >= 128, transparent below);
5. Snaps every pixel to the nearest colour in style/palette.png;
6. Adds/repairs 1 px dark outline;
7. Saves to art_batches/mapart/px/<category-slug>/<tile-slug>.png.

Also generates contact sheet review images in art_batches/mapart/review/<category-slug>.png.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys
from collections import deque
from PIL import Image, ImageDraw, ImageFont

DODOART_ROOT = pathlib.Path(r"C:\Users\Lenovo\Documents\DodoArt")
MAPART_DIR = DODOART_ROOT / "art_batches" / "mapart"


def load_palette(palette_path: pathlib.Path) -> list[tuple[int, int, int]]:
    pal_img = Image.open(palette_path).convert("RGB")
    colors = list(dict.fromkeys(pal_img.getdata()))
    if not colors:
        raise ValueError(f"No colors found in palette {palette_path}")
    return colors


def remove_background(img: Image.Image) -> Image.Image:
    """Detect and remove checkerboard or solid uniform background."""
    img = img.convert("RGBA")
    w, h = img.size
    data = img.load()

    # If image already has genuine transparency across > 5% of pixels, keep alpha >= 128
    trans_count = sum(1 for y in range(h) for x in range(w) if data[x, y][3] < 128)
    if trans_count > (w * h * 0.05):
        out = Image.new("RGBA", (w, h))
        out_data = out.load()
        for y in range(h):
            for x in range(w):
                r, g, b, a = data[x, y]
                out_data[x, y] = (r, g, b, 255) if a >= 128 else (0, 0, 0, 0)
        return out

    # Border flood-fill to eliminate checkerboard (light grey/white) or solid background
    visited = bytearray(w * h)
    queue = deque()
    for x in range(w):
        queue.append((x, 0)); visited[0 * w + x] = 1
        queue.append((x, h - 1)); visited[(h - 1) * w + x] = 1
    for y in range(h):
        queue.append((0, y)); visited[y * w + 0] = 1
        queue.append((w - 1, y)); visited[y * w + (w - 1)] = 1

    # Sample corners to determine background characteristics
    corners = [data[0, 0][:3], data[w - 1, 0][:3], data[0, h - 1][:3], data[w - 1, h - 1][:3]]
    is_light_bg = any(sum(c) / 3 > 170 for c in corners)

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if not visited[idx]:
                    r, g, b, _ = data[nx, ny]
                    match = False
                    if is_light_bg:
                        # Light checkerboard or white: grey/white pixels where max difference is small
                        if min(r, g, b) > 165 and (max(r, g, b) - min(r, g, b)) < 30:
                            match = True
                    else:
                        # Solid dark or custom background
                        if any(math.sqrt((r - cr)**2 + (g - cg)**2 + (b - cb)**2) < 25 for cr, cg, cb in corners):
                            match = True
                    if match:
                        visited[idx] = 1
                        queue.append((nx, ny))

    out = Image.new("RGBA", (w, h))
    out_data = out.load()
    for y in range(h):
        for x in range(w):
            if not visited[y * w + x]:
                out_data[x, y] = (*data[x, y][:3], 255)
    return out


def trim_to_drawn(img: Image.Image) -> Image.Image:
    """Crop image to bounding box of opaque pixels."""
    bbox = img.getbbox()
    if bbox:
        return img.crop(bbox)
    return img


def snap_to_palette(img: Image.Image, palette: list[tuple[int, int, int]]) -> Image.Image:
    """Snap every opaque pixel to the nearest RGB in the palette."""
    w, h = img.size
    out = Image.new("RGBA", (w, h))
    in_data = img.load()
    out_data = out.load()

    def nearest_palette(rgb):
        r, g, b = rgb
        best_col = palette[0]
        best_dist = float("inf")
        for pr, pg, pb in palette:
            d = (r - pr)**2 + (g - pg)**2 + (b - pb)**2
            if d < best_dist:
                best_dist = d
                best_col = (pr, pg, pb)
        return best_col

    for y in range(h):
        for x in range(w):
            r, g, b, a = in_data[x, y]
            if a >= 128:
                nr, ng, nb = nearest_palette((r, g, b))
                out_data[x, y] = (nr, ng, nb, 255)
            else:
                out_data[x, y] = (0, 0, 0, 0)

    return out


def repair_outline(img: Image.Image, dark_color: tuple[int, int, int]) -> Image.Image:
    """Ensure a 1 px dark outline on all silhouette edges."""
    w, h = img.size
    data = img.load()
    out = img.copy()
    out_data = out.load()

    for y in range(h):
        for x in range(w):
            if data[x, y][3] >= 128:
                # Check if this opaque pixel touches any transparent pixel (4-connected)
                is_edge = False
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if nx < 0 or nx >= w or ny < 0 or ny >= h or data[nx, ny][3] < 128:
                        is_edge = True
                        break
                if is_edge:
                    # If this boundary pixel is light or not sufficiently dark, darken it
                    r, g, b, _ = data[x, y]
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    if lum > 60:
                        out_data[x, y] = (dark_color[0], dark_color[1], dark_color[2], 255)

    return out


def clean_tile(raw_path: pathlib.Path, target_w: int, target_h: int | None,
               palette: list[tuple[int, int, int]]) -> Image.Image:
    img = Image.open(raw_path)
    # 1. Remove background
    img = remove_background(img)
    # 2. Trim to drawn area
    img = trim_to_drawn(img)

    orig_w, orig_h = img.size
    if orig_w == 0 or orig_h == 0:
        return Image.new("RGBA", (target_w, target_h or target_w), (0, 0, 0, 0))

    if target_h is None or target_h <= 0:
        target_h = max(1, round(target_w * (orig_h / orig_w)))

    # 3. Resize with nearest neighbor
    img = img.resize((target_w, target_h), Image.Resampling.NEAREST)

    # 4. Hard alpha
    w, h = img.size
    data = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            data[x, y] = (r, g, b, 255) if a >= 128 else (0, 0, 0, 0)

    # 5. Snap to palette
    img = snap_to_palette(img, palette)

    # 6. Outline repair using darkest color in palette
    darkest = min(palette, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    img = repair_outline(img, darkest)

    return img


def generate_review_sheet(category_slug: str) -> pathlib.Path:
    """Generate contact sheet in art_batches/mapart/review/<category-slug>.png."""
    manifest_path = MAPART_DIR / "manifest.json"
    sizes_path = MAPART_DIR / "sizes.csv"
    review_dir = MAPART_DIR / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sizes_map = {}
    if sizes_path.exists():
        with sizes_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sizes_map[row["name"]] = row

    cat_tiles = [t for t in manifest if t.get("category_slug") == category_slug]
    if not cat_tiles:
        raise ValueError(f"No tiles found for category slug {category_slug}")

    rows = []
    for t in cat_tiles:
        name = t["name"]
        t_slug = t["tile_slug"]
        orig_p = MAPART_DIR / "originals" / category_slug / f"{t_slug}.png"
        px_p = MAPART_DIR / "px" / category_slug / f"{t_slug}.png"

        orig_img = Image.open(orig_p).convert("RGBA") if orig_p.exists() else Image.new("RGBA", (64, 64), (50, 50, 50, 255))
        px_img = Image.open(px_p).convert("RGBA") if px_p.exists() else Image.new("RGBA", (16, 16), (200, 50, 50, 255))

        # 4x version of pixel image
        px_4x = px_img.resize((px_img.width * 4, px_img.height * 4), Image.Resampling.NEAREST)

        # Thumbnail of original (max 96x96 maintaining aspect)
        orig_thumb = orig_img.copy()
        orig_thumb.thumbnail((96, 96), Image.Resampling.BILINEAR)

        s_info = sizes_map.get(name, {})
        w_cells = s_info.get("width_cells", "?")
        label = f"{name}\nSize: {w_cells} cells ({px_img.width}x{px_img.height} px)\nOrig: {orig_img.width}x{orig_img.height}"

        rows.append((orig_thumb, px_img, px_4x, label))

    # Calculate layout
    row_gap = 16
    col_orig_w = 110
    col_1x_w = 140
    col_4x_w = 320
    col_text_w = 260
    total_w = col_orig_w + col_1x_w + col_4x_w + col_text_w + 32

    # Calculate total height
    total_h = 40  # Header
    row_heights = []
    for orig_thumb, px_img, px_4x, label in rows:
        rh = max(orig_thumb.height, px_img.height, px_4x.height, 60) + row_gap
        row_heights.append(rh)
        total_h += rh

    sheet = Image.new("RGBA", (total_w, total_h), (34, 37, 43, 255))
    draw = ImageDraw.Draw(sheet)

    # Header
    cat_title = cat_tiles[0].get("category", category_slug)
    draw.text((16, 12), f"Review: {cat_title} ({len(cat_tiles)} tiles)", fill=(230, 235, 245, 255))

    cur_y = 40
    for idx, (orig_thumb, px_img, px_4x, label) in enumerate(rows):
        # Draw background divider
        draw.line([(16, cur_y), (total_w - 16, cur_y)], fill=(50, 54, 62, 255), width=1)
        y_content = cur_y + 8

        # 1. Original
        sheet.paste(orig_thumb, (24, y_content), orig_thumb)

        # 2. Pixel 1:1
        x_1x = col_orig_w + 24
        sheet.paste(px_img, (x_1x, y_content), px_img)

        # 3. Pixel 4x
        x_4x = x_1x + col_1x_w
        sheet.paste(px_4x, (x_4x, y_content), px_4x)

        # 4. Text
        x_text = x_4x + col_4x_w
        draw.text((x_text, y_content + 4), label, fill=(210, 215, 220, 255))

        cur_y += row_heights[idx]

    out_path = review_dir / f"{category_slug}.png"
    sheet.save(out_path, "PNG")
    print(f"Generated review sheet: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw redrawn pixel tiles.")
    parser.add_argument("category_slug", help="Category slug to process (e.g. castles, monsters)")
    parser.add_argument("--tile", default=None, help="Process single tile slug only")
    parser.add_argument("--review-only", action="store_true", help="Only rebuild the review contact sheet")
    args = parser.parse_args()

    c_slug = args.category_slug
    if args.review_only:
        generate_review_sheet(c_slug)
        return

    palette = load_palette(MAPART_DIR / "style" / "palette.png")
    manifest = json.loads((MAPART_DIR / "manifest.json").read_text(encoding="utf-8"))

    sizes_map = {}
    with (MAPART_DIR / "sizes.csv").open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sizes_map[r["name"]] = r

    tiles = [t for t in manifest if t.get("category_slug") == c_slug]
    if args.tile:
        tiles = [t for t in tiles if t.get("tile_slug") == args.tile]

    out_px_dir = MAPART_DIR / "px" / c_slug
    out_px_dir.mkdir(parents=True, exist_ok=True)

    for t in tiles:
        t_slug = t["tile_slug"]
        raw_p = MAPART_DIR / "raw" / c_slug / f"{t_slug}.png"
        if not raw_p.exists():
            print(f"Skip {t['name']}: no raw image at {raw_p}")
            continue

        s = sizes_map.get(t["name"], {})
        w_cells = int(s.get("width_cells") or 1)
        h_cells_str = s.get("height_cells", "").strip()
        h_cells = int(h_cells_str) if h_cells_str else None
        px_per_cell = int(s.get("px_per_cell") or 16)

        target_w = w_cells * px_per_cell
        target_h = h_cells * px_per_cell if h_cells else None

        cleaned = clean_tile(raw_p, target_w, target_h, palette)
        out_p = out_px_dir / f"{t_slug}.png"
        cleaned.save(out_p, "PNG")
        print(f"Cleaned {t['name']} -> {out_p} ({cleaned.size})")

    generate_review_sheet(c_slug)


if __name__ == "__main__":
    main()
