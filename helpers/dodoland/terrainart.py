"""
Drawing the world — a chunk of terrain as vector, at any zoom.

The map has to stay crisp however far in anybody goes, so terrain is emitted as
SVG rather than rasterised. The naive way to do that is one ``<rect>`` per cell,
which for a 64x64 chunk is four thousand nodes and for a screen full of chunks is
a hundred thousand. No browser is happy about that.

So cells are merged into the largest rectangles that share a value, and all the
rectangles of one kind become a **single ``<path>``** with one subpath each. A
chunk of open sea — the commonest chunk on any map with a coast — comes out as
one path with one subpath. A chunk of coastline comes out as a handful.

The merge is greedy and in two passes: runs along a row, then those runs
extended downward while the row beneath matches. It is not the optimal
rectangle decomposition, which is a much harder problem and worth nothing here:
greedy already turns the pathological case into a few hundred subpaths and the
ordinary case into single digits.
"""

from __future__ import annotations

from typing import Iterable, Optional

from helpers.dodoland import palette as palette_rules
from helpers.dodoland import terrain as T


def rects(cells: list[int], width: int = T.CHUNK,
          height: int = T.CHUNK, *, skip: Iterable[int] = (T.UNKNOWN,)
          ) -> list[tuple[int, int, int, int, int]]:
    """``(x, y, w, h, value)`` covering every cell, largest rectangles first.

    ``skip`` is what not to emit at all — by default the unknown cell, because
    an unpainted world should be a hole you can see through to whatever is
    behind it rather than a field of grey rectangles.
    """
    skipped = set(skip)
    taken = bytearray(width * height)
    out: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        x = 0
        while x < width:
            index = y * width + x
            value = cells[index]
            if taken[index] or value in skipped:
                x += 1
                continue
            # How far this run goes along the row.
            run = 1
            while (x + run < width and cells[index + run] == value
                   and not taken[index + run]):
                run += 1
            # ...and how many rows below match it for that whole width.
            depth = 1
            while y + depth < height:
                base = (y + depth) * width + x
                if any(cells[base + i] != value or taken[base + i]
                       for i in range(run)):
                    break
                depth += 1
            for dy in range(depth):
                base = (y + dy) * width + x
                for dx in range(run):
                    taken[base + dx] = 1
            out.append((x, y, run, depth, value))
            x += run
    return out


# --------------------------------------------------------------------------- #
#  Texture
# --------------------------------------------------------------------------- #
# Flat colour is not terrain. Forest should have trees in it, sand should have
# grains, water should have a swell — but a motif *per cell* would be millions
# of nodes, which is the whole thing the rectangle merge exists to avoid.
#
# An SVG ``<pattern>`` costs nothing per region: it is defined once and a
# merged rectangle of any size is filled with it. So a forest the size of a
# county is still one path, and it has trees in it.
#
# Each motif is drawn on an 8x8 cell tile from three colours — the ground's own,
# one step darker and one step lighter — so every texture sits in the same
# thirty-two colour world and nothing has to be hand-picked per kind.
TILE = 8

# (shape, how many) per kind. The shape is what the ground *is*: a forest reads
# as canopy, a marsh as reeds, a cliff as striations. Kinds not named here stay
# flat, which is right for anything that should recede.
MOTIFS: dict[str, tuple[str, int]] = {
    "forest": ("trees", 5),
    "grass": ("tufts", 6),
    "plains": ("tufts", 3),
    "marsh": ("reeds", 7),
    "sand": ("grains", 9),
    "hills": ("bumps", 4),
    "mountain": ("peaks", 3),
    "cliff": ("striations", 4),
    "deep": ("swell", 3),
    "sea": ("swell", 4),
    "shallows": ("swell", 5),
    "lake": ("swell", 4),
    "river": ("swell", 5),
}


def _spots(count: int, seed: int) -> list[tuple[int, int]]:
    """Scattered but fixed positions on the tile.

    Deterministic from the kind's name: a texture that moved between page loads
    would shimmer, and one that was truly regular would read as wallpaper.
    """
    out, value = [], seed or 1
    while len(out) < count:
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        spot = ((value >> 7) % TILE, (value >> 17) % TILE)
        if spot not in out:
            out.append(spot)
    return out


def _motif(shape: str, count: int, light: str, dark: str, seed: int) -> str:
    """One tile's worth of marks, in cell units."""
    out = []
    for i, (x, y) in enumerate(_spots(count, seed)):
        tone = dark if i % 2 else light
        if shape == "trees":
            # A canopy blob with a trunk pixel under it.
            out.append(f'<rect x="{x}" y="{y}" width="2" height="1" fill="{dark}"/>')
            out.append(f'<rect x="{x}" y="{y - 1}" width="1" height="1" fill="{light}"/>')
        elif shape == "tufts":
            out.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{tone}"/>')
        elif shape == "reeds":
            out.append(f'<rect x="{x}" y="{y}" width="1" height="2" fill="{dark}"/>')
        elif shape == "grains":
            out.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{tone}"/>')
        elif shape == "bumps":
            out.append(f'<rect x="{x}" y="{y}" width="3" height="1" fill="{dark}"/>')
            out.append(f'<rect x="{x + 1}" y="{y - 1}" width="1" height="1" fill="{light}"/>')
        elif shape == "peaks":
            out.append(f'<path d="M{x} {y + 3}L{x + 2} {y}L{x + 4} {y + 3}z" fill="{dark}"/>')
            out.append(f'<path d="M{x + 1} {y + 2}L{x + 2} {y}L{x + 3} {y + 2}z" fill="{light}"/>')
        elif shape == "striations":
            out.append(f'<rect x="{x}" y="{y}" width="1" height="4" fill="{dark}"/>')
        elif shape == "swell":
            # A dash and a shorter one below it: the universal shorthand for
            # moving water, and it survives being two pixels tall.
            out.append(f'<rect x="{x}" y="{y}" width="3" height="1" fill="{light}"/>')
            out.append(f'<rect x="{x + 1}" y="{y + 1}" width="2" height="1" fill="{dark}"/>')
    return "".join(out)


def pattern_id(key: str) -> str:
    return "tp_" + "".join(c for c in str(key) if c.isalnum())


def pattern_defs(kinds: list[dict], colours: Optional[dict] = None,
                 cell: float = 1.0) -> str:
    """``<defs>`` with one pattern per textured ground.

    Emitted **once** for the whole map rather than per chunk: a chunk is a
    fragment injected into one document, and repeating these in each of sixty
    would be sixty copies of every tile.
    """
    colours = colours or palette_rules.PALETTE
    out = []
    for kind in kinds:
        key = str(kind.get("key") or "")
        motif = MOTIFS.get(key)
        if not motif:
            continue
        slot = kind.get("colour") or "shadow"
        base = colours.get(slot, "#000")
        dark = colours.get(palette_rules.shade(slot), base)
        light = colours.get(palette_rules.lighten(slot), base)
        shape, count = motif
        seed = sum(ord(c) * (i + 3) for i, c in enumerate(key))
        out.append(
            f'<pattern id="{pattern_id(key)}" patternUnits="userSpaceOnUse" '
            f'width="{TILE * cell:g}" height="{TILE * cell:g}">'
            f'<rect width="{TILE * cell:g}" height="{TILE * cell:g}" fill="{base}"/>'
            f'<g transform="scale({cell:g})" shape-rendering="crispEdges">'
            f'{_motif(shape, count, light, dark, seed)}</g></pattern>')
    return f"<defs>{''.join(out)}</defs>" if out else ""


def _subpath(x: int, y: int, w: int, h: int, cell: float) -> str:
    return (f"M{x * cell:g} {y * cell:g}h{w * cell:g}v{h * cell:g}"
            f"h{-w * cell:g}z")


def chunk_svg(cells: list[int], kinds: list[dict], *,
              colours: Optional[dict] = None, cell: float = 1.0,
              width: int = T.CHUNK, height: int = T.CHUNK,
              offset: tuple[float, float] = (0.0, 0.0),
              textured: bool = False) -> str:
    """One chunk as SVG: a single ``<path>`` per kind of ground present.

    ``shape-rendering="crispEdges"`` is not decoration. Adjacent rectangles that
    share an edge are antialiased against each other otherwise, and a tiled map
    comes out covered in pale hairlines where nothing is actually there.
    """
    colours = colours or palette_rules.PALETTE
    by_value: dict[int, list[str]] = {}
    for x, y, w, h, value in rects(cells, width, height):
        by_value.setdefault(value, []).append(_subpath(x, y, w, h, cell))
    out = []
    dx, dy = offset
    for value, parts in sorted(by_value.items()):
        if value >= len(kinds):
            continue
        kind = kinds[value]
        slot = kind.get("colour") or "shadow"
        key = str(kind.get("key") or "")
        # Texture only up close. At map scale a motif is noise on a coastline,
        # and the overview is drawn at one pixel per several cells, where the
        # pattern would alias into a shimmer rather than resolve into trees.
        fill = (f"url(#{pattern_id(key)})" if textured and key in MOTIFS
                else colours.get(slot, "#000"))
        out.append(f'<path fill="{fill}" '
                   f'shape-rendering="crispEdges" d="{"".join(parts)}"/>')
    body = "".join(out)
    if dx or dy:
        return f'<g transform="translate({dx:g},{dy:g})">{body}</g>'
    return body


def downsample(cells: list[int], width: int, height: int, step: int
               ) -> tuple[list[int], int, int]:
    """Every ``step``-th cell, for a zoomed-out view.

    Nearest rather than a majority vote on purpose: a coastline sampled by
    majority dissolves at distance, while nearest keeps the shape of the land
    and only loses detail inside it — and the shape is the whole point of a map
    seen from far away.
    """
    out_w, out_h = -(-width // step), -(-height // step)
    out = [T.UNKNOWN] * (out_w * out_h)
    for y in range(out_h):
        row = min(y * step, height - 1) * width
        for x in range(out_w):
            out[y * out_w + x] = cells[row + min(x * step, width - 1)]
    return out, out_w, out_h
