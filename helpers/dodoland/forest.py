"""
Forests as a painted layer, not as placed trees.

A forest costs nothing per tree. What is stored is **which cells are forest and
of which stand** — the terrain store's ``cover`` layer, the same 64 x 64 chunks
and run-length rows as the ground, so a continent of woodland is a few hundred
bytes per chunk whatever its tree count. The trees themselves are never stored:
the map works them out from the cells, from a seed, every time it draws them, so
the same spot always shows the same trees (``web/dodoland/forest_ui.py``).

A **stand** is what a stretch of forest is made of: the tiles in its mix, how
densely they grow, at what size and with how much spread. Stands are kept per
world, append-only, because the grid holds their *index*: index 0 is "no
forest", and an index, once given, never changes meaning. Painting with the same
mix and settings again reuses its stand rather than adding another.

Pure: specs in, specs out. The store and the endpoints are in
``helpers/dodoland/terrain.py`` and ``web/dodoland/forest_api.py``.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

NONE = 0
MAX_STANDS = 500
MAX_MIX = 12


class ForestError(ValueError):
    pass


def _number(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:   # NaN
        return default
    return max(low, min(high, number))


def stand_spec(*, mix: Iterable[str], density: Any = 0.75, scale: Any = 1.0,
               jitter: Any = 0.15, flip: Any = True) -> dict:
    """A stand from what the brush sends, cleaned and bounded.

    The mix keeps its order of first appearance and drops repeats; the seed
    follows from the rest, so the same stand always grows the same trees.
    """
    seen: list[str] = []
    for tile_id in mix or []:
        tile_id = str(tile_id or "").strip()
        if tile_id and tile_id not in seen:
            seen.append(tile_id)
    if not seen:
        raise ForestError("Pick at least one tree to paint a forest with.")
    if len(seen) > MAX_MIX:
        raise ForestError(f"A forest mixes at most {MAX_MIX} kinds of tree.")
    spec = {"mix": seen,
            "density": round(_number(density, 0.2, 1.0, 0.75), 3),
            "scale": round(_number(scale, 0.25, 6.0, 1.0), 3),
            "jitter": round(_number(jitter, 0.0, 0.5, 0.15), 3),
            "flip": bool(flip)}
    digest = hashlib.sha1(repr(sorted(spec.items())).encode("utf-8")).digest()
    spec["seed"] = int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
    return spec


def _same(a: dict, b: dict) -> bool:
    keys = ("mix", "density", "scale", "jitter", "flip")
    return all(a.get(k) == b.get(k) for k in keys)


def stand_index(stands: list[dict], spec: dict) -> tuple[int, list[dict]]:
    """The index painting ``spec`` writes, and the stand list (added to if the
    stand is new). Index 0 is no forest and is never a stand."""
    stands = list(stands or [{"key": "none"}])
    for index, stand in enumerate(stands):
        if index and _same(stand, spec):
            return index, stands
    if len(stands) > MAX_STANDS:
        raise ForestError("This world has too many kinds of forest.")
    stands.append(dict(spec))
    return len(stands) - 1, stands
