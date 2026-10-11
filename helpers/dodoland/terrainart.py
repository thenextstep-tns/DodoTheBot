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
#  Texture: the ground is drawn with tiles from the library
# --------------------------------------------------------------------------- #
# A kind of ground bound to a library tile (``kind["tile_id"]``) is filled with
# an SVG ``<pattern>`` made of that tile's own images. A pattern costs nothing
# per region — it is defined once and a merged rectangle of any size is filled
# with it — so a forest the size of a county is still one path.
#
# The pattern is a block of PATTERN_CELLS x PATTERN_CELLS tiles with a variant
# picked per position, so a field of one grass reads as a field rather than as
# wallpaper. Its size comes from the tile's ``cell_px``: a 16px tile and a 32px
# tile both cover one map cell, at different detail.
#
# These replaced generated motifs that drew trees and dunes out of rectangles;
# the library is now the only source of ground art.
PATTERN_CELLS = 4


def pattern_id(key: str) -> str:
    return "tp_" + "".join(c for c in str(key) if c.isalnum())


def _pick(i: int, j: int, salt: int, count: int) -> int:
    value = (i * 73856093) ^ (j * 19349663) ^ salt
    value = (value * 1103515245 + 12345) & 0x7FFFFFFF
    return (value >> 8) % count


def tile_pattern(key: str, tile: dict, art_url: str, dims: Optional[dict] = None,
                 shrink: float = 1.0) -> str:
    """One ``<pattern>`` for a kind drawn with ``tile``.

    ``dims`` maps a variant id to its pixel ``(w, h)``; without it a variant is
    taken to be exactly one cell. ``art_url`` is prefixed to a variant id.
    """
    variants = list(tile.get("variants") or [])
    if not variants:
        return ""
    # ``shrink`` is the server's tile scale: art drawn that many times smaller.
    cell_px = float(tile.get("cell_px") or 16) * max(0.1, float(shrink))
    w, h = (dims or {}).get(variants[0], (cell_px, cell_px))
    size_w, size_h = max(w / cell_px, 0.02), max(h / cell_px, 0.02)
    salt = sum(ord(c) * (n + 7) for n, c in enumerate(str(key)))
    images = []
    for j in range(PATTERN_CELLS):
        for i in range(PATTERN_CELLS):
            vid = variants[_pick(i, j, salt, len(variants))]
            images.append(
                f'<image href="{art_url}{vid}" x="{i * size_w:g}" y="{j * size_h:g}" '
                f'width="{size_w:g}" height="{size_h:g}" preserveAspectRatio="none"/>')
    return (f'<pattern id="{pattern_id(key)}" patternUnits="userSpaceOnUse" '
            f'width="{PATTERN_CELLS * size_w:g}" height="{PATTERN_CELLS * size_h:g}" '
            f'style="image-rendering:pixelated">{"".join(images)}</pattern>')


def pattern_defs(kinds: list[dict], tiles: dict, art_url: str,
                 dims: Optional[dict] = None, shrink: float = 1.0) -> str:
    """``<defs>`` with one pattern per ground bound to a tile.

    Emitted **once** for the whole map rather than per chunk: a chunk is a
    fragment injected into one document, and repeating these in each of sixty
    would be sixty copies of every tile. ``tiles`` maps tile id -> tile.
    """
    out = [tile_pattern(str(kind.get("key")), tiles[kind["tile_id"]], art_url, dims, shrink)
           for kind in kinds if kind.get("tile_id") in tiles]
    out = [part for part in out if part]
    return f"<defs>{''.join(out)}</defs>" if out else ""


def kind_fill(kind: dict, colours: dict) -> str:
    """The flat colour a kind is drawn in when it is not textured: its tile's
    average colour if it has one, else its palette slot."""
    return kind.get("hex") or colours.get(kind.get("colour") or "shadow", "#000")


def _subpath(x: int, y: int, w: int, h: int, cell: float) -> str:
    return (f"M{x * cell:g} {y * cell:g}h{w * cell:g}v{h * cell:g}"
            f"h{-w * cell:g}z")


def _land(kind: Optional[dict]) -> bool:
    return bool(kind) and not kind.get("water") and str(kind.get("key") or "") != "unknown"


def blend_edges(cells: list[int], kinds: list[dict], *, right: Optional[list[int]] = None,
                below: Optional[list[int]] = None, size: int = T.CHUNK) -> dict[int, str]:
    """Where two different kinds of land meet, as cell edges grouped by the
    kind that spills over the border: ``{kind index: path}``.

    One kind per border spills into the other (the higher index), never both:
    two textures laid over each other both ways cancel out. Inside the chunk,
    and across its right and bottom borders when those neighbours are given, so
    a border on a chunk line is blended once. Water is left out: the coast has
    its own shading.
    """
    land = [_land(k) for k in kinds]

    def spill(a: int, b: int) -> Optional[int]:
        if a == b or not (0 <= a < len(land) and 0 <= b < len(land)) or not (land[a] and land[b]):
            return None
        return max(a, b)

    horizontal: dict[int, dict[int, list[int]]] = {}   # kind -> y of the edge -> xs
    vertical: dict[int, dict[int, list[int]]] = {}
    for y in range(size):
        row = y * size
        for x in range(size):
            here = cells[row + x]
            east = cells[row + x + 1] if x + 1 < size else (right[row] if right else None)
            south = cells[row + size + x] if y + 1 < size else (below[x] if below else None)
            if east is not None:
                kind = spill(here, east)
                if kind is not None:
                    vertical.setdefault(kind, {}).setdefault(x + 1, []).append(y)
            if south is not None:
                kind = spill(here, south)
                if kind is not None:
                    horizontal.setdefault(kind, {}).setdefault(y + 1, []).append(x)

    def runs(values: list[int]):
        values = sorted(values)
        start = prev = values[0]
        for v in values[1:]:
            if v != prev + 1:
                yield start, prev - start + 1
                start = v
            prev = v
        yield start, prev - start + 1

    out: dict[int, str] = {}
    for kind in set(horizontal) | set(vertical):
        parts = []
        for y, xs in (horizontal.get(kind) or {}).items():
            parts.extend(f"M{x} {y}h{n}" for x, n in runs(xs))
        for x, ys in (vertical.get(kind) or {}).items():
            parts.extend(f"M{x} {y}v{n}" for y, n in runs(ys))
        out[kind] = "".join(parts)
    return out


def blend_svg(edges: dict[int, str], kinds: list[dict], *, width: float, steps: int,
              strength: float = 0.9, colours: Optional[dict] = None,
              offset: tuple[float, float] = (0.0, 0.0)) -> str:
    """The cross-fade along those borders: the spilling kind's own texture laid
    over its neighbour in ``steps`` nested strokes, ``width`` cells out at the
    widest, so it fades from ``strength`` at the border to nothing.

    The strokes' opacities are chosen so the cover rises in even steps (each
    stroke adds the same share), and every stroke of a kind is one path, so
    where its border turns a corner the overlap is painted once, not twice.
    """
    if not edges or width <= 0 or steps < 1 or strength <= 0:
        return ""
    colours = colours or palette_rules.PALETTE
    steps = max(1, min(12, int(steps)))
    strength = min(0.99, float(strength))
    # Cover after the k widest strokes: strength * k / steps. Opacity of stroke
    # k is what takes the cover from step k-1 to step k.
    alphas, before = [], 0.0
    for k in range(1, steps + 1):
        after = strength * k / steps
        alphas.append(1 - (1 - after) / (1 - before))
        before = after
    out = []
    for kind_index in sorted(edges):
        kind = kinds[kind_index] if 0 <= kind_index < len(kinds) else None
        if not kind or not edges[kind_index]:
            continue
        paint = (f"url(#{pattern_id(str(kind.get('key') or ''))})" if kind.get("tile_id")
                 else kind_fill(kind, colours))
        for k, alpha in enumerate(alphas):
            half = width * (steps - k) / steps
            out.append(f'<path d="{edges[kind_index]}" fill="none" stroke="{paint}" '
                       f'stroke-opacity="{alpha:.3g}" stroke-width="{half * 2:.3g}" '
                       f'stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>')
    body = "".join(out)
    dx, dy = offset
    return f'<g transform="translate({dx:g},{dy:g})">{body}</g>' if (dx or dy) and body else body


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
        key = str(kind.get("key") or "")
        # Texture only up close. The overview is drawn at one pixel per several
        # cells, where a tile pattern would alias into a shimmer, so far away a
        # ground is its tile's average colour.
        fill = (f"url(#{pattern_id(key)})" if textured and kind.get("tile_id")
                else kind_fill(kind, colours))
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
