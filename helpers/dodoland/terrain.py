"""
What is actually where — the layer that turns a picture into a world.

Until now the map has been an image the bot could not read. Towns sat at
percentages *over* it and nothing could ask "what is here?", so nothing could be
impassable, nothing could grow around a lake, and a road could not avoid the
sea. This is the answer to that question, and everything else — city growth,
roads, walls — is a query against it.

**Two layers, and keeping them apart is the point.**

``TERRAIN`` is authored. An admin paints it, imports it from the map they drew,
and it changes rarely. ``BUILT`` is derived — roads, walls, the ground a town
has claimed — and it is rewritten by the growth and road passes constantly.
Mixing them would mean a growth pass could silently eat somebody's hand-painted
coastline, which is exactly the class of mistake that has cost this subsystem
the most time.

Cost composes across the layers rather than one winning::

    move_cost(cell)  = worst of (terrain, built)   # None anywhere = impassable
    build_cost(cell) = terrain must allow it, and nothing may already be built

**Stored in chunks, not as one grid.** A world of two million cells is not a
document, and an edit to one bay should not rewrite the continent. Each chunk is
64x64 cells, run-length encoded, in its own row. That is also how it is served:
the browser fetches the chunks it can see, which is the same bargain the towns
already make with their artwork.

**Run-length, and why a string.** Terrain comes in enormous uniform runs — an
ocean chunk is one run — so RLE is the natural fit, and a string survives being
looked at in a database GUI, which a packed binary does not. A chunk of open sea
is about a dozen bytes.
"""

from __future__ import annotations

from typing import Iterable, Optional

CHUNK = 64
CELLS = CHUNK * CHUNK

# Layers. Authored and derived, never the same row.
TERRAIN = "terrain"
BUILT = "built"
LAYERS = (TERRAIN, BUILT)

# Index 0 is "nothing has been said about this cell". A fresh world is entirely
# unknown rather than entirely grass, so an import that half-worked is visible
# as a half-painted map instead of a plausible wrong one.
UNKNOWN = 0


class TerrainError(ValueError):
    """A rejected terrain edit, with a message meant for the panel."""


# --------------------------------------------------------------------------- #
#  What a kind of ground is, and what it costs
# --------------------------------------------------------------------------- #
# ``move`` is what it costs a road to cross, ``grow`` what it costs a town to
# spread onto, and ``build`` whether a building may stand there. They are three
# different questions that look like one: water is unbuildable but bridgeable,
# forest is unbuildable but a road can be cut through it, and a town may be
# allowed to clear that forest or not depending on its own policy.
#
# ``None`` means "cannot, at any price".
_BASE_KINDS: tuple[dict, ...] = (
    {"key": "unknown", "label": "Not set", "colour": "shadow",
     "move": None, "grow": None, "build": False, "water": False},
    {"key": "deep", "label": "Deep sea", "colour": "deep",
     "move": None, "grow": None, "build": False, "water": True},
    {"key": "sea", "label": "Sea", "colour": "sea",
     "move": 90, "grow": None, "build": False, "water": True},
    {"key": "shallows", "label": "Shallows", "colour": "shallow",
     "move": 40, "grow": None, "build": False, "water": True},
    {"key": "lake", "label": "Lake", "colour": "river",
     "move": 50, "grow": None, "build": False, "water": True},
    {"key": "river", "label": "River", "colour": "river",
     "move": 25, "grow": None, "build": False, "water": True},
    {"key": "marsh", "label": "Marsh", "colour": "marsh",
     "move": 9, "grow": 14, "build": False, "water": False},
    {"key": "sand", "label": "Sand", "colour": "sand",
     "move": 2, "grow": 3, "build": True, "water": False},
    {"key": "plains", "label": "Plains", "colour": "grass_lt",
     "move": 1, "grow": 1, "build": True, "water": False},
    {"key": "grass", "label": "Grassland", "colour": "grass",
     "move": 1, "grow": 1, "build": True, "water": False},
    {"key": "forest", "label": "Forest", "colour": "grass_dark",
     # Crossable by a road, and only growable by a town that clears it.
     "move": 6, "grow": None, "build": False, "water": False, "clearable": True},
    {"key": "hills", "label": "Hills", "colour": "dirt",
     "move": 3, "grow": 4, "build": True, "water": False},
    {"key": "mountain", "label": "Mountain", "colour": "stone_dark",
     "move": None, "grow": None, "build": False, "water": False},
    {"key": "cliff", "label": "Cliff", "colour": "slate",
     "move": None, "grow": None, "build": False, "water": False},
)

# What a town has put on the ground. Derived, never painted by hand.
_BUILT_KINDS: tuple[dict, ...] = (
    {"key": "clear", "label": "Nothing", "colour": "shadow",
     "move": 0, "grow": 0, "build": True, "water": False},
    {"key": "road", "label": "Road", "colour": "dirt",
     # Cheap on purpose: a later road snaps onto an earlier one rather than
     # running beside it, which is what makes a network instead of a hairball.
     "move": 0, "grow": 0, "build": False, "water": False, "cheap": 0.3},
    {"key": "claimed", "label": "Town ground", "colour": "cream",
     "move": 2, "grow": 0, "build": True, "water": False},
    {"key": "building", "label": "Building", "colour": "roof_red",
     "move": None, "grow": None, "build": False, "water": False},
    {"key": "wall", "label": "Wall", "colour": "stone",
     "move": None, "grow": None, "build": False, "water": False},
    {"key": "gate", "label": "Gate", "colour": "wood",
     # The whole reason a wall is worth building: a road has to come through it.
     "move": 1, "grow": None, "build": False, "water": False},
)


def base_kinds(layer: str = TERRAIN) -> list[dict]:
    """The built-in kinds for a layer, as fresh dicts."""
    source = _BASE_KINDS if layer == TERRAIN else _BUILT_KINDS
    return [dict(kind) for kind in source]


def index_of(kinds: list[dict], key: str) -> int:
    """The stored index of a kind. Indices are what the grid holds."""
    for index, kind in enumerate(kinds):
        if kind.get("key") == key:
            return index
    raise TerrainError(f"There is no {key!r} terrain.")


def passable(kind: dict, *, clears_forest: bool = False) -> bool:
    """Whether a town may spread onto this kind of ground."""
    if kind.get("grow") is not None:
        return True
    return bool(clears_forest and kind.get("clearable"))


def grow_cost(kind: dict, *, clears_forest: bool = False) -> Optional[int]:
    """What it costs a town to spread onto one cell, or ``None`` for never.

    A town that clears forest pays for it. That is the whole mechanic: growing
    through woodland is slower than growing around it, so two towns with the
    same standing and different policies end up different shapes.
    """
    cost = kind.get("grow")
    if cost is not None:
        return int(cost)
    if clears_forest and kind.get("clearable"):
        return int(kind.get("move") or 6) * 2
    return None


# --------------------------------------------------------------------------- #
#  Run-length coding
# --------------------------------------------------------------------------- #
def encode(cells: Iterable[int]) -> str:
    """``[0,0,0,3,3]`` -> ``"3x0 2x3"``.

    Readable on purpose: this is the one field somebody will stare at in a
    database GUI wondering why a bay is the wrong shape, and a packed binary
    would make that impossible.
    """
    out: list[str] = []
    run_value: Optional[int] = None
    run = 0
    for value in cells:
        value = int(value)
        if value == run_value:
            run += 1
            continue
        if run_value is not None:
            out.append(f"{run}x{run_value}")
        run_value, run = value, 1
    if run_value is not None:
        out.append(f"{run}x{run_value}")
    return " ".join(out)


def decode(rle: str, size: int = CELLS) -> list[int]:
    """The inverse, padded or trimmed to exactly ``size`` cells.

    Padding rather than raising: a chunk written by an older, smaller grid is a
    chunk that should come back as mostly unknown, not an exception on a page.
    """
    cells: list[int] = []
    for token in str(rle or "").split():
        count, _, value = token.partition("x")
        try:
            cells.extend([int(value)] * int(count))
        except ValueError:
            continue
        if len(cells) >= size:
            break
    if len(cells) < size:
        cells.extend([UNKNOWN] * (size - len(cells)))
    return cells[:size]


# --------------------------------------------------------------------------- #
#  The store
# --------------------------------------------------------------------------- #
class TerrainStore:
    """A guild's world, in chunks. ``bot.dodoland_terrain``."""

    def __init__(self, chunks, config) -> None:
        self._chunks = chunks
        self._config = config
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._chunks.create_index(
                [("guild_id", 1), ("layer", 1), ("cx", 1), ("cy", 1)], unique=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    # ------------------------------------------------------------------ #
    #  Shape of the world
    # ------------------------------------------------------------------ #
    def world(self, guild_id: int) -> dict:
        """This guild's grid size and terrain vocabulary.

        The kind list is stored per guild rather than read from the constants,
        because the grid holds **indices** into it: if the built-in list were
        reordered under a server that had already painted, every cell would
        silently change meaning.
        """
        self._ensure_indexes()
        row = self._config.find_one({"_id": int(guild_id)}) or {}
        return {
            "cells_w": int(row.get("cells_w") or 0),
            "cells_h": int(row.get("cells_h") or 0),
            "kinds": row.get("kinds") or base_kinds(TERRAIN),
            "built_kinds": row.get("built_kinds") or base_kinds(BUILT),
            "source_w": int(row.get("source_w") or 0),
            "source_h": int(row.get("source_h") or 0),
        }

    def set_world(self, guild_id: int, *, cells_w: int, cells_h: int,
                  source_w: int = 0, source_h: int = 0,
                  kinds: Optional[list] = None) -> dict:
        """Set the grid's size. **Does not clear what is painted** — see
        :meth:`wipe`, which is the deliberate way to start again."""
        if not 16 <= int(cells_w) <= 8192 or not 16 <= int(cells_h) <= 8192:
            raise TerrainError("A world is between 16 and 8192 cells on a side.")
        self._ensure_indexes()
        changes = {"cells_w": int(cells_w), "cells_h": int(cells_h),
                   "source_w": int(source_w), "source_h": int(source_h)}
        if kinds is not None:
            changes["kinds"] = kinds
        self._config.update_one({"_id": int(guild_id)}, {"$set": changes}, upsert=True)
        return self.world(guild_id)

    def chunk_counts(self, guild_id: int) -> tuple[int, int]:
        world = self.world(guild_id)
        return (-(-world["cells_w"] // CHUNK), -(-world["cells_h"] // CHUNK))

    # ------------------------------------------------------------------ #
    #  Reading
    # ------------------------------------------------------------------ #
    def chunk(self, guild_id: int, cx: int, cy: int,
              layer: str = TERRAIN) -> list[int]:
        """One chunk's cells, row-major. Unwritten chunks are all unknown."""
        self._ensure_indexes()
        row = self._chunks.find_one({"guild_id": int(guild_id), "layer": layer,
                                     "cx": int(cx), "cy": int(cy)})
        return decode(row.get("rle", "") if row else "")

    def chunks(self, guild_id: int, boxes: Iterable[tuple[int, int]],
               layer: str = TERRAIN) -> dict[tuple[int, int], list[int]]:
        """Several chunks in one read — what the viewport asks for.

        One query for everything on screen rather than one per chunk: the panel
        once did eight full scans of a collection per page load and it took
        5.6 seconds, which is the mistake this signature exists to prevent.
        """
        self._ensure_indexes()
        wanted = [(int(cx), int(cy)) for cx, cy in boxes]
        if not wanted:
            return {}
        rows = self._chunks.find({
            "guild_id": int(guild_id), "layer": layer,
            "$or": [{"cx": cx, "cy": cy} for cx, cy in wanted],
        })
        found = {(int(r["cx"]), int(r["cy"])): decode(r.get("rle", "")) for r in rows}
        return {key: found.get(key) or [UNKNOWN] * CELLS for key in wanted}

    def at(self, guild_id: int, x: int, y: int, layer: str = TERRAIN) -> int:
        """One cell. Convenience; never use it in a loop over a region."""
        cells = self.chunk(guild_id, x // CHUNK, y // CHUNK, layer)
        return cells[(y % CHUNK) * CHUNK + (x % CHUNK)]

    # ------------------------------------------------------------------ #
    #  Writing
    # ------------------------------------------------------------------ #
    def write_chunk(self, guild_id: int, cx: int, cy: int, cells: list[int],
                    layer: str = TERRAIN) -> None:
        if len(cells) != CELLS:
            raise TerrainError(f"A chunk is {CELLS} cells, not {len(cells)}.")
        self._ensure_indexes()
        self._chunks.update_one(
            {"guild_id": int(guild_id), "layer": layer, "cx": int(cx), "cy": int(cy)},
            {"$set": {"rle": encode(cells)}}, upsert=True)

    def paint(self, guild_id: int, edits: dict, layer: str = TERRAIN) -> int:
        """Apply ``{(x, y): kind_index}`` across however many chunks it touches.

        Grouped by chunk so a brush stroke across a chunk border is two writes
        rather than one per cell. Returns how many chunks were rewritten.
        """
        self._ensure_indexes()
        by_chunk: dict[tuple[int, int], dict[int, int]] = {}
        for (x, y), value in edits.items():
            key = (int(x) // CHUNK, int(y) // CHUNK)
            offset = (int(y) % CHUNK) * CHUNK + (int(x) % CHUNK)
            by_chunk.setdefault(key, {})[offset] = int(value)
        for (cx, cy), cells in by_chunk.items():
            current = self.chunk(guild_id, cx, cy, layer)
            for offset, value in cells.items():
                current[offset] = value
            self.write_chunk(guild_id, cx, cy, current, layer)
        return len(by_chunk)

    def snapshot(self, guild_id: int, keys: Iterable[tuple[int, int]],
                 layer: str = TERRAIN) -> dict[tuple[int, int], str]:
        """The raw RLE of some chunks, for undo.

        Chunks rather than cells: a brush stroke covers tens of thousands of
        cells but only a handful of chunks, and a chunk's whole encoded state is
        a few hundred bytes. Recording what changed cell by cell would be
        megabytes for the same information.
        """
        self._ensure_indexes()
        out: dict[tuple[int, int], str] = {}
        for cx, cy in keys:
            row = self._chunks.find_one({"guild_id": int(guild_id), "layer": layer,
                                         "cx": int(cx), "cy": int(cy)})
            out[(int(cx), int(cy))] = str(row.get("rle", "")) if row else ""
        return out

    def restore(self, guild_id: int, snapshot: dict, layer: str = TERRAIN) -> int:
        """Put chunks back exactly as they were. The other half of undo."""
        self._ensure_indexes()
        for (cx, cy), rle in snapshot.items():
            self._chunks.update_one(
                {"guild_id": int(guild_id), "layer": layer,
                 "cx": int(cx), "cy": int(cy)},
                {"$set": {"rle": str(rle)}}, upsert=True)
        return len(snapshot)

    def wipe(self, guild_id: int, layer: Optional[str] = None) -> int:
        """Throw a layer away. The deliberate way to start an import again."""
        self._ensure_indexes()
        query: dict = {"guild_id": int(guild_id)}
        if layer is not None:
            query["layer"] = layer
        result = self._chunks.delete_many(query)
        return int(getattr(result, "deleted_count", 0))

    def painted(self, guild_id: int, layer: str = TERRAIN) -> int:
        """How many chunks have anything in them. What the panel reports."""
        self._ensure_indexes()
        return int(self._chunks.count_documents({"guild_id": int(guild_id),
                                                 "layer": layer}))
