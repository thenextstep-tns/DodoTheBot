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


def _subpath(x: int, y: int, w: int, h: int, cell: float) -> str:
    return (f"M{x * cell:g} {y * cell:g}h{w * cell:g}v{h * cell:g}"
            f"h{-w * cell:g}z")


def chunk_svg(cells: list[int], kinds: list[dict], *,
              colours: Optional[dict] = None, cell: float = 1.0,
              width: int = T.CHUNK, height: int = T.CHUNK,
              offset: tuple[float, float] = (0.0, 0.0)) -> str:
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
        slot = kinds[value].get("colour") or "shadow"
        out.append(f'<path fill="{colours.get(slot, "#000")}" '
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
