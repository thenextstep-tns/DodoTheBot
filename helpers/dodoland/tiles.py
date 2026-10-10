"""
The tile library — everything that can be put on the map.

One library for the ground people paint and the things they place on it. It
replaced the per-server asset library completely: a tile is an image (or a few
variants of one) plus the rules for using it.

**Two scopes.** A tile is either **global** (``guild_id`` 0) — curated by the
bot owner and offered to every server — or **one server's own**, uploaded by
that server's admins and seen nowhere else. That is what the asset library was
for, and why replacing it did not take anything away from server admins.

**What a tile says about itself**

* ``layer`` — where it goes: the environment (layer 1, painted ground), map
  objects (layer 3) or buildings (layer 4). Roads (layer 2) are the bot's.
* ``access`` — who may use it: server admins, players, both or neither. The bot
  owner is not a role; they can use everything.
* ``requires`` — what a *player* must have reached first: a building and the
  tier of it, the asset library's rule unchanged. **A lock is a tier index, not
  a point total**, because thresholds are derived from the live distribution
  and move. A server that has no building by that key has no such lock: a global
  tile must not be unreachable on a server that named its buildings differently.
* ``passable`` — whether a road may be drawn through it. Water and mountains are
  not; grass, paths and a scatter of flowers are; a bridge is.
* ``resizable`` with ``scale_min``/``scale_max`` — whether it can be drawn at
  other sizes. Drawn art resizes; pixel art is fixed, because pixel art scaled
  by 1.3 is smeared pixel art.
* ``cell_px`` — how many of the art's own pixels make one map cell.

**Three collections, because the bytes must never ride along.** A listing is
metadata only, with no projection to get wrong.

* ``categories`` — ``{cat_id, name, order}``; owned by the bot owner
* ``tiles``      — ``{tile_id, guild_id, name, cat_id, order, variants, layer,
  access, requires, passable, resizable, scale_min, scale_max, cell_px, pack,
  source}``
* ``art``        — ``{vid, tile_id, data, content_type, w, h}``

**A tile is one or more variants**, picked per cell or per placement, so ground
does not read as wallpaper. The last one cannot be removed.

**Order is a list position, renumbered on every move**, so two pages can never
disagree about it.
"""

from __future__ import annotations

import secrets
from typing import Any, Iterable, Optional

# Storage ceilings, not behaviour: they keep one upload from filling the
# database.
MAX_CATEGORIES = 100
MAX_TILES = 1500
# Sixteen, because a tuft of grass or a scatter of pebbles is one thing drawn
# a dozen ways, and those are exactly what variants are for.
MAX_VARIANTS = 16
MAX_NAME = 48
# Per image. Pixel tiles are a few KB; drawn map art at full resolution runs to
# a megabyte or so, and every image is its own row, so this only has to stop a
# photograph, not a drawing.
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_TYPES = ("image/png", "image/webp", "image/svg+xml", "image/gif")

GLOBAL = 0
# Tiles whose category was removed, or that were never given one. Shown last.
UNCATEGORISED = ""

# --------------------------------------------------------------------------- #
#  Layers, access, scale
# --------------------------------------------------------------------------- #
LAYERS: tuple[tuple[str, str], ...] = (
    ("environment", "Environment (layer 1)"),
    ("objects", "Map objects (layer 3)"),
    ("buildings", "Buildings (layer 4)"),
)
LAYER_KEYS = tuple(key for key, _ in LAYERS)
DEFAULT_LAYER = "objects"
# The bot owner is not a role: they can use every tile everywhere.
ROLES: tuple[tuple[str, str], ...] = (
    ("admin", "Server admins"),
    ("player", "Players"),
)
ROLE_KEYS = tuple(key for key, _ in ROLES)

# How many of the art's own pixels make one cell of the map. Pixel art comes
# on a 16px or a 32px grid; drawn art is whatever it was drawn at.
CELL_SIZES = (16, 32)          # the presets the editor offers
MIN_CELL, MAX_CELL = 4, 1024
DEFAULT_CELL = 16

# The size range a resizable tile may be drawn at, as a multiple of its natural
# size. The bounds are the decor store's, so the two can never disagree about
# what "as large as it goes" means.
SCALE_FLOOR, SCALE_CEILING = 0.25, 6.0
DEFAULT_SCALE_MIN, DEFAULT_SCALE_MAX = 0.5, 3.0
# The fields an editor may change in place, and nothing else.
EDITABLE = ("name", "cat_id", "cell_px", "layer", "access", "requires",
            "passable", "resizable", "scale_min", "scale_max")


class TileError(ValueError):
    """A rejected library edit, with a message meant for the panel."""


def _clean_name(value: Any, what: str = "A tile") -> str:
    name = str(value or "").strip()
    if not name:
        raise TileError(f"{what} needs a name.")
    if len(name) > MAX_NAME:
        raise TileError(f"That name is too long (max {MAX_NAME} characters).")
    return name


def clean_layer(value: Any) -> str:
    layer = str(value or "")
    if layer not in LAYER_KEYS:
        raise TileError(f"Unknown layer {layer!r}.")
    return layer


def clean_access(values: Any) -> list[str]:
    """Known roles only, in canonical order. An unknown one is refused rather
    than dropped: a typo that silently removed a permission would be invisible."""
    given = [str(v) for v in (values or [])]
    unknown = [v for v in given if v not in ROLE_KEYS]
    if unknown:
        raise TileError(f"Unknown role(s): {', '.join(unknown)}.")
    return [role for role in ROLE_KEYS if role in given]


def clean_requires(value: Any) -> dict:
    """``{"building": key, "tier": n}``; tier 0 or no building means none."""
    value = value or {}
    if not isinstance(value, dict):
        raise TileError("Requirements must be a building and a tier.")
    building = str(value.get("building") or "").strip()[:40]
    try:
        tier = int(value.get("tier") or 0)
    except (TypeError, ValueError):
        raise TileError("The required tier must be a number.") from None
    if not 0 <= tier <= 12:
        raise TileError("The required tier must be between 0 and 12.")
    if not building or not tier:
        return {"building": "", "tier": 0}
    return {"building": building, "tier": tier}


def clean_cell(value: Any) -> int:
    try:
        cell = int(value)
    except (TypeError, ValueError):
        raise TileError("The grid size must be a number.") from None
    if not MIN_CELL <= cell <= MAX_CELL:
        raise TileError(f"The grid size must be between {MIN_CELL} and {MAX_CELL}px.")
    return cell


def clean_scale(value: Any, what: str) -> float:
    try:
        scale = round(float(value), 2)
    except (TypeError, ValueError):
        raise TileError(f"The {what} size must be a number.") from None
    if not SCALE_FLOOR <= scale <= SCALE_CEILING:
        raise TileError(f"Sizes go from {SCALE_FLOOR}x to {SCALE_CEILING}x.")
    return scale


def scale_range(tile: Optional[dict]) -> tuple[float, float]:
    """What a placement of this tile may be sized to. Fixed tiles are 1x only."""
    if not tile or not tile.get("resizable"):
        return 1.0, 1.0
    return float(tile["scale_min"]), float(tile["scale_max"])


def _size(data: bytes) -> tuple[int, int]:
    """Pixel size of an upload, or (0, 0) when it cannot be read (an SVG)."""
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001 - size is informative, never a reason to refuse
        return 0, 0


def check_image(data: bytes, content_type: str) -> None:
    if content_type not in ALLOWED_TYPES:
        raise TileError("A tile must be a PNG, WebP, GIF or SVG.")
    if not data:
        raise TileError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise TileError(f"A tile must be under {MAX_BYTES // 1024}KB.")


def _complete(row: dict) -> dict:
    """Fill fields a tile stored before they existed. Every new field goes here
    too, or older rows silently read as whatever ``None`` turns into.

    Rows from before layer/access were split carry ``uses`` ("layer:role"
    pairs); they read as their first layer and the union of its roles.
    """
    legacy = [u for u in (row.get("uses") or []) if ":" in str(u)]
    if row.get("layer") not in LAYER_KEYS:
        layers = [u.split(":")[0] for u in legacy if u.split(":")[0] in LAYER_KEYS]
        row["layer"] = layers[0] if layers else DEFAULT_LAYER
    if "access" not in row:
        row["access"] = [r for r in ROLE_KEYS if f"{row['layer']}:{r}" in legacy]
    row["access"] = [r for r in ROLE_KEYS if r in (row.get("access") or [])]
    try:
        row["requires"] = clean_requires(row.get("requires"))
    except TileError:
        row["requires"] = {"building": "", "tier": 0}
    row["passable"] = bool(row.get("passable", True))
    row["resizable"] = bool(row.get("resizable", False))
    for key, default in (("scale_min", DEFAULT_SCALE_MIN), ("scale_max", DEFAULT_SCALE_MAX)):
        try:
            value = float(row.get(key, default))
        except (TypeError, ValueError):
            value = default
        row[key] = min(max(value, SCALE_FLOOR), SCALE_CEILING)
    if row["scale_min"] > row["scale_max"]:
        row["scale_min"], row["scale_max"] = row["scale_max"], row["scale_min"]
    try:
        cell = int(row.get("cell_px"))
    except (TypeError, ValueError):
        cell = DEFAULT_CELL
    row["cell_px"] = cell if MIN_CELL <= cell <= MAX_CELL else DEFAULT_CELL
    row["guild_id"] = int(row.get("guild_id") or GLOBAL)
    row.setdefault("pack", "")
    row.setdefault("source", "")
    row.setdefault("variants", [])
    row.pop("uses", None)
    return row


def _moved(ids: list[str], target: str, delta: int) -> list[str]:
    """``ids`` with ``target`` moved ``delta`` places, clamped at the ends."""
    if target not in ids:
        return ids
    out = [item for item in ids if item != target]
    index = max(0, min(len(out), ids.index(target) + int(delta)))
    out.insert(index, target)
    return out


def unlocked_for(tiles: Iterable[dict], person: Optional[dict],
                 buildings: Iterable[dict]) -> set[str]:
    """Which tiles a player has reached the requirements of.

    ``buildings`` are this server's. A requirement naming a building the server
    does not have is no requirement here — a global tile cannot be allowed to
    be unreachable because a server named its buildings differently. A tile
    with no requirement is unlocked for everybody: that is the starter set, and
    a toolkit where nothing is available on day one gives nobody a reason to
    open the map twice.
    """
    present = {str(b.get("key")) for b in buildings}
    reached = {key: (score.get("tier") if score.get("tier") is not None else -1)
               for key, score in ((person or {}).get("buildings") or {}).items()}
    out = set()
    for tile in tiles:
        need = tile.get("requires") or {}
        building, tier = need.get("building") or "", int(need.get("tier") or 0)
        if not building or not tier or building not in present:
            out.add(tile["tile_id"])
        elif reached.get(building, -1) >= tier - 1:   # tier 1 is index 0
            out.add(tile["tile_id"])
    return out


class TileLibrary:
    """Every tile, global and per server. ``bot.dodoland_tiles``."""

    def __init__(self, tiles, categories, art) -> None:
        self._tiles = tiles
        self._cats = categories
        self._art = art
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._tiles.create_index([("tile_id", 1)], unique=True)
            self._tiles.create_index([("guild_id", 1)])
            self._cats.create_index([("cat_id", 1)], unique=True)
            self._art.create_index([("vid", 1)], unique=True)
            self._art.create_index([("tile_id", 1)])
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    # ------------------------------------------------------------------ #
    #  Categories (the bot owner's)
    # ------------------------------------------------------------------ #
    def categories(self) -> list[dict]:
        self._ensure_indexes()
        rows = list(self._cats.find({}, {"_id": 0}))
        rows.sort(key=lambda row: (int(row.get("order", 0)), str(row.get("name", ""))))
        return rows

    def _category(self, cat_id: str) -> Optional[dict]:
        return self._cats.find_one({"cat_id": str(cat_id)})

    def add_category(self, name: Any) -> dict:
        self._ensure_indexes()
        existing = self.categories()
        if len(existing) >= MAX_CATEGORIES:
            raise TileError(f"The library holds at most {MAX_CATEGORIES} categories.")
        clean = _clean_name(name, "A category")
        if any(row["name"].lower() == clean.lower() for row in existing):
            raise TileError(f"There is already a category called {clean!r}.")
        row = {"cat_id": secrets.token_hex(6), "name": clean, "order": len(existing)}
        self._cats.insert_one(dict(row))
        return row

    def rename_category(self, cat_id: str, name: Any) -> None:
        if self._category(cat_id) is None:
            raise TileError("That category no longer exists.")
        self._cats.update_one({"cat_id": str(cat_id)},
                              {"$set": {"name": _clean_name(name, "A category")}})

    def remove_category(self, cat_id: str) -> None:
        """Only an empty category can go — on every server. Silently
        uncategorising forty tiles is a decision nobody made."""
        if self._category(cat_id) is None:
            raise TileError("That category no longer exists.")
        held = self._tiles.count_documents({"cat_id": str(cat_id)})
        if held:
            raise TileError(f"Move or remove its {held} tile(s) first.")
        self._cats.delete_one({"cat_id": str(cat_id)})
        self._renumber_categories([row["cat_id"] for row in self.categories()])

    def move_category(self, cat_id: str, delta: int) -> None:
        ids = [row["cat_id"] for row in self.categories()]
        if str(cat_id) not in ids:
            raise TileError("That category no longer exists.")
        self._renumber_categories(_moved(ids, str(cat_id), delta))

    def _renumber_categories(self, ids: list[str]) -> None:
        for order, cat_id in enumerate(ids):
            self._cats.update_one({"cat_id": cat_id}, {"$set": {"order": order}})

    # ------------------------------------------------------------------ #
    #  Reading tiles
    # ------------------------------------------------------------------ #
    def tiles(self, guild_id: Optional[int] = None) -> list[dict]:
        """Tiles in palette order, metadata only.

        ``guild_id=None`` is every tile everywhere (the owner's view); a guild
        id is what that server sees: the global ones and its own.
        """
        self._ensure_indexes()
        rank = {row["cat_id"]: index for index, row in enumerate(self.categories())}
        # Filtered here rather than in the query: rows written before tiles had
        # a scope have no guild_id at all, a query cannot match a missing field
        # as 0, and the whole library is a few hundred small rows.
        rows = [_complete(row) for row in self._tiles.find({}, {"_id": 0})]
        if guild_id is not None:
            rows = [row for row in rows if row["guild_id"] in (GLOBAL, int(guild_id))]
        rows.sort(key=lambda row: (rank.get(row.get("cat_id") or "", len(rank)),
                                   int(row.get("order", 0)),
                                   str(row.get("name", ""))))
        return rows

    def grouped(self, guild_id: Optional[int] = None) -> list[tuple[dict, list[dict]]]:
        """``(category, tiles)`` in palette order; uncategorised last, and only
        when something is in it."""
        tiles = self.tiles(guild_id)
        out = []
        for cat in self.categories():
            out.append((cat, [t for t in tiles if t.get("cat_id") == cat["cat_id"]]))
        known = {cat["cat_id"] for cat, _ in out}
        loose = [t for t in tiles if (t.get("cat_id") or "") not in known]
        if loose:
            out.append(({"cat_id": UNCATEGORISED, "name": "Uncategorised"}, loose))
        return out

    def get(self, tile_id: str) -> Optional[dict]:
        self._ensure_indexes()
        row = self._tiles.find_one({"tile_id": str(tile_id)})
        if row:
            row.pop("_id", None)
            _complete(row)
        return row

    def visible(self, tile_id: str, guild_id: int) -> Optional[dict]:
        """The tile, if this server may see it at all."""
        row = self.get(tile_id)
        if row and row["guild_id"] in (GLOBAL, int(guild_id)):
            return row
        return None

    def usable(self, guild_id: int, layer: str, role: str) -> list[dict]:
        """What ``role`` may use on ``layer`` on this server, locked or not."""
        layer, role = clean_layer(layer), str(role)
        if role not in ROLE_KEYS:
            raise TileError(f"Unknown role {role!r}.")
        return [row for row in self.tiles(guild_id)
                if row["layer"] == layer and role in row["access"]]

    def by_source(self, source: str) -> Optional[dict]:
        """The tile an import added under this key, if it is still there."""
        self._ensure_indexes()
        row = self._tiles.find_one({"source": str(source)}) if source else None
        if row:
            row.pop("_id", None)
            _complete(row)
        return row

    def _need(self, tile_id: str) -> dict:
        row = self.get(tile_id)
        if row is None:
            raise TileError("That tile no longer exists.")
        return row

    def _in_category(self, cat_id: str) -> list[dict]:
        return [row for row in self.tiles() if (row.get("cat_id") or "") == cat_id]

    def _check_category(self, cat_id: Any) -> str:
        cat_id = str(cat_id or "")
        if cat_id and self._category(cat_id) is None:
            raise TileError("That category no longer exists.")
        return cat_id

    # ------------------------------------------------------------------ #
    #  Writing tiles
    # ------------------------------------------------------------------ #
    def _props(self, given: dict, current: Optional[dict] = None) -> dict:
        """Validate the editable fields in ``given`` against what is stored."""
        out: dict = {}
        if "name" in given:
            out["name"] = _clean_name(given["name"])
        if "cell_px" in given:
            out["cell_px"] = clean_cell(given["cell_px"])
        if "layer" in given:
            out["layer"] = clean_layer(given["layer"])
        if "access" in given:
            out["access"] = clean_access(given["access"])
        if "requires" in given:
            out["requires"] = clean_requires(given["requires"])
        if "passable" in given:
            out["passable"] = bool(given["passable"])
        if "resizable" in given:
            out["resizable"] = bool(given["resizable"])
        for key, what in (("scale_min", "smallest"), ("scale_max", "largest")):
            if key in given:
                out[key] = clean_scale(given[key], what)
        low = out.get("scale_min", (current or {}).get("scale_min", DEFAULT_SCALE_MIN))
        high = out.get("scale_max", (current or {}).get("scale_max", DEFAULT_SCALE_MAX))
        if low > high:
            raise TileError("The smallest size cannot be larger than the largest.")
        return out

    def add_tile(self, *, name: Any, cat_id: Any, data: bytes, content_type: str,
                 guild_id: int = GLOBAL, layer: Any = DEFAULT_LAYER,
                 access: Any = ("admin",), requires: Any = None,
                 passable: bool = True, resizable: bool = False,
                 scale_min: Any = DEFAULT_SCALE_MIN, scale_max: Any = DEFAULT_SCALE_MAX,
                 cell_px: Any = DEFAULT_CELL, pack: str = "", source: str = "") -> dict:
        """A new tile with its first variant, at the end of its category.

        ``pack`` is where the art came from, kept for credits. ``source`` is a
        stable key for an imported tile, so re-running an import finds what it
        already added instead of adding it twice.
        """
        self._ensure_indexes()
        if self._tiles.count_documents({}) >= MAX_TILES:
            raise TileError(f"The library holds at most {MAX_TILES} tiles.")
        props = self._props({"name": name, "layer": layer, "access": list(access or []),
                             "requires": requires, "passable": passable,
                             "resizable": resizable, "scale_min": scale_min,
                             "scale_max": scale_max, "cell_px": cell_px})
        cat_id = self._check_category(cat_id)
        check_image(data, content_type)
        tile_id = secrets.token_hex(8)
        vid = self._store_art(tile_id, data, content_type)
        row = {"tile_id": tile_id, "guild_id": int(guild_id or GLOBAL), "cat_id": cat_id,
               "order": len(self._in_category(cat_id)), "variants": [vid],
               "pack": str(pack or "")[:80], "source": str(source or "")[:200], **props}
        self._tiles.insert_one(dict(row))
        return row

    def update_tile(self, tile_id: str, **given: Any) -> dict:
        """Change any of :data:`EDITABLE`. Moving category puts it at the end
        there. Returns the tile as stored."""
        unknown = set(given) - set(EDITABLE)
        if unknown:
            raise TileError(f"Not editable: {', '.join(sorted(unknown))}.")
        row = self._need(tile_id)
        given = {k: v for k, v in given.items() if v is not None}
        changes = self._props(given, row)
        old_cat = row.get("cat_id") or ""
        if "cat_id" in given:
            target = self._check_category(given["cat_id"])
            if target != old_cat:
                changes["cat_id"] = target
                changes["order"] = len(self._in_category(target))
        if changes:
            self._tiles.update_one({"tile_id": str(tile_id)},
                                   {"$set": changes})
            if "cat_id" in changes:
                self._renumber_tiles(old_cat)
        return self._need(tile_id)

    def update_category(self, cat_id: str, guild_id: Optional[int] = None,
                        **given: Any) -> int:
        """The same settings for every tile in a category that ``guild_id`` may
        edit (``None``: all of them). Returns how many changed."""
        cat_id = self._check_category(cat_id)
        given = {k: v for k, v in given.items() if k != "name" and k != "cat_id" and v is not None}
        if not given:
            return 0
        rows = [r for r in self._in_category(cat_id)
                if guild_id is None or r["guild_id"] == int(guild_id)]
        for row in rows:
            changes = self._props(given, row)
            self._tiles.update_one({"tile_id": row["tile_id"]},
                                   {"$set": changes})
        return len(rows)

    def move_tile(self, tile_id: str, delta: int) -> None:
        row = self._need(tile_id)
        ids = [t["tile_id"] for t in self._in_category(row.get("cat_id") or "")]
        self._write_tile_order(_moved(ids, str(tile_id), delta))

    def _renumber_tiles(self, cat_id: str) -> None:
        self._write_tile_order([t["tile_id"] for t in self._in_category(cat_id)])

    def _write_tile_order(self, ids: list[str]) -> None:
        for order, tile_id in enumerate(ids):
            self._tiles.update_one({"tile_id": tile_id}, {"$set": {"order": order}})

    def remove_tile(self, tile_id: str) -> None:
        row = self._need(tile_id)
        self._tiles.delete_one({"tile_id": str(tile_id)})
        self._art.delete_many({"tile_id": str(tile_id)})
        self._renumber_tiles(row.get("cat_id") or "")

    # ------------------------------------------------------------------ #
    #  Variants
    # ------------------------------------------------------------------ #
    def _store_art(self, tile_id: str, data: bytes, content_type: str) -> str:
        vid = secrets.token_hex(8)
        width, height = _size(data)
        self._art.insert_one({"vid": vid, "tile_id": str(tile_id),
                              "data": data, "content_type": content_type,
                              "w": width, "h": height})
        return vid

    def add_variant(self, tile_id: str, *, data: bytes, content_type: str) -> str:
        row = self._need(tile_id)
        variants = list(row.get("variants") or [])
        if len(variants) >= MAX_VARIANTS:
            raise TileError(f"A tile holds at most {MAX_VARIANTS} variants.")
        check_image(data, content_type)
        vid = self._store_art(tile_id, data, content_type)
        self._tiles.update_one({"tile_id": str(tile_id)},
                               {"$set": {"variants": variants + [vid]}})
        return vid

    def remove_variant(self, tile_id: str, vid: str) -> None:
        row = self._need(tile_id)
        variants = list(row.get("variants") or [])
        if str(vid) not in variants:
            raise TileError("That variant no longer exists.")
        if len(variants) == 1:
            raise TileError("A tile needs at least one image. Remove the tile instead.")
        variants.remove(str(vid))
        self._tiles.update_one({"tile_id": str(tile_id)}, {"$set": {"variants": variants}})
        self._art.delete_one({"vid": str(vid)})

    def art(self, vid: str) -> Optional[dict]:
        """One variant's bytes. The only read that carries them."""
        self._ensure_indexes()
        return self._art.find_one({"vid": str(vid)})

    def first_art(self, tile_id: str) -> Optional[dict]:
        """A tile's first variant's bytes — what a toolkit button shows."""
        row = self.get(tile_id)
        if not row or not row["variants"]:
            return None
        return self.art(row["variants"][0])
