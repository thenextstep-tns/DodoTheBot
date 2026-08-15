"""
The trial ranking, as a PNG people can read at a glance.

The panel explains the system to whoever configures it; this explains it to
everyone else. Roles are grouped by what they're worth — so the eye lands on
"these are worth 3" rather than on forty individual numbers — and the ranks are
listed with their thresholds, which is the other half of "what do I need next".

Drawn with Pillow (already a dependency) using the panel's palette.
"""

from __future__ import annotations

import datetime
import io
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from helpers import trial_ranks

# Panel palette.
INK = (34, 34, 34)
BODY = (63, 63, 63)
MUTED = (106, 106, 106)
HAIRLINE = (221, 221, 221)
SOFT = (247, 247, 247)
CANVAS = (255, 255, 255)
RAUSCH = (255, 56, 92)

WIDTH = 1240
MARGIN = 48
# Fonts Pillow can usually find; the last resort is its bitmap default, which
# is ugly but never crashes.
_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
_BOLD_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _font(size: int, bold: bool = False):
    for path in (_BOLD_PATHS if bold else _FONT_PATHS):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _display_name(name: str) -> str:
    """Most fonts have no superscript HM, so spell it out — with a space.

    Folding the characters alone reads as "vDSRHM"; the space is what makes it
    scannable at a glance, which is the whole point of the picture.
    """
    spelled = (name or "").replace("ᴴᴹ", " HM").replace("ʰᵐ", " hm")
    return spelled.translate(trial_ranks._SUPERSCRIPT).replace("  ", " ").strip()


def _wrap(draw, items: list[str], font, max_width: int, gap: int = 14) -> list[list[str]]:
    """Lay chips out into rows that fit the column."""
    rows, row, used = [], [], 0
    for item in items:
        width = draw.textlength(item, font=font) + gap * 2
        if row and used + width > max_width:
            rows.append(row)
            row, used = [], 0
        row.append(item)
        used += width + 8
    if row:
        rows.append(row)
    return rows


def build(guild, config: dict) -> bytes:
    """Render the current setup to PNG bytes."""
    points = config.get("points") or {}
    ranks = sorted(config.get("ranks") or [], key=lambda r: r["min_points"])

    # Effective value per role: what's stored, else the built-in suggestion —
    # the same thing the panel shows, so the picture matches the page.
    bands: dict[int, list[str]] = {}
    for role in trial_ranks.scoring_roles(guild):
        value = points.get(str(role.id)) or trial_ranks.default_points_for(role)
        if value:
            bands.setdefault(int(value), []).append(_display_name(role.name))
    for names in bands.values():
        names.sort(key=str.lower)

    title_font = _font(40, bold=True)
    band_font = _font(26, bold=True)
    chip_font = _font(21)
    rank_font = _font(24, bold=True)
    small_font = _font(19)

    # --- measure first, then draw on a canvas with room to spare ---
    # The canvas is deliberately over-tall and cropped to what was actually
    # drawn at the end: an estimate that drifts from the drawing code by a few
    # pixels per block used to land the footer on top of the last rank.
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    inner = WIDTH - MARGIN * 2
    layout, height = [], MARGIN + 60 + 34
    for value in sorted(bands, reverse=True):
        rows = _wrap(probe, bands[value], chip_font, inner - 150)
        layout.append((value, rows))
        height += max(48, len(rows) * 42 + 18) + 10
    height += 62 + len(ranks) * 44 + 120

    image = Image.new("RGB", (WIDTH, height), CANVAS)
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, WIDTH, 8], fill=RAUSCH)
    y = MARGIN
    draw.text((MARGIN, y), f"{guild.name} — trial ranks", font=title_font, fill=INK)
    y += 52
    draw.text((MARGIN, y), "What each clear is worth. Only your best role per trial counts.",
              font=small_font, fill=MUTED)
    y += 42

    # --- the point bands ---
    for value, rows in layout:
        block_height = max(48, len(rows) * 42 + 18)
        draw.rectangle([MARGIN, y, WIDTH - MARGIN, y + block_height], fill=SOFT)
        draw.rectangle([MARGIN, y, MARGIN + 6, y + block_height], fill=RAUSCH)
        label = f"{value} pt" if value == 1 else f"{value} pts"
        draw.text((MARGIN + 24, y + 14), label, font=band_font, fill=RAUSCH)
        chip_x0 = MARGIN + 150
        cy = y + 12
        for row in rows:
            cx = chip_x0
            for name in row:
                width = draw.textlength(name, font=chip_font) + 28
                draw.rounded_rectangle([cx, cy, cx + width, cy + 32], radius=16,
                                       fill=CANVAS, outline=HAIRLINE)
                draw.text((cx + 14, cy + 5), name, font=chip_font, fill=BODY)
                cx += width + 8
            cy += 42
        y += block_height + 10

    # --- the ladder ---
    if ranks:
        y += 22
        draw.text((MARGIN, y), "Ranks", font=band_font, fill=INK)
        y += 40
        for index, rank in enumerate(ranks):
            name = _display_name(trial_ranks.rank_name(rank, guild))
            nxt = ranks[index + 1]["min_points"] if index + 1 < len(ranks) else None
            span = f"{rank['min_points']}+" if nxt is None else f"{rank['min_points']}–{nxt - 1}"
            draw.rounded_rectangle([MARGIN, y, WIDTH - MARGIN, y + 36], radius=10,
                                   fill=SOFT if index % 2 == 0 else CANVAS, outline=HAIRLINE)
            draw.text((MARGIN + 18, y + 7), name, font=rank_font, fill=INK)
            draw.text((MARGIN + 320, y + 9), f"{span} points", font=small_font, fill=BODY)
            y += 44

    # The footer follows the content instead of sitting at a precomputed offset,
    # so it can never land on the last row of whatever came before it.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    y += 26
    draw.text((MARGIN, y),
              f"Add up your best clear per trial. Updated {stamp}.",
              font=small_font, fill=MUTED)
    y += 28

    image = image.crop((0, 0, WIDTH, min(height, y + MARGIN)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
