"""
The tile library — what the base map is painted with.

Until now the ground was drawn from generated motifs: a conifer here, a dune
there, chosen by the code. This is the other half of that: real tiles, curated
by the bot owner once and offered to **every server**, so a server's admins
paint their map from a toolkit rather than from whatever the code thought a
forest looks like.

**Global, not per guild.** The owner builds the toolkit; servers use it. A tile
uploaded once is available everywhere, which is the whole reason it is not a
column on ``DodoLandAssets`` (that library is per server and is decor).

**Three collections, because the bytes must never ride along.** The library is
listed on every page that offers a palette, and the images are the only large
thing in it. Keeping them in their own rows means a listing is metadata only,
with no projection to get wrong — the trap where an exclusion projection threw
away the fact that a picture existed is written up in ``docs/DODOLAND.md``.

* ``categories`` — ``{cat_id, name, order}``
* ``tiles``      — ``{tile_id, name, cat_id, order, variants: [vid, ...]}``
* ``art``        — ``{vid, tile_id, data, content_type}``

**A tile is one or more variants.** Plain ground repeated cell after cell reads
as wallpaper; two or three variants of the same grass picked per cell is what
makes it read as a field. Every tile has at least one, and the last cannot be
removed — remove the tile instead.

**Order is a list position, renumbered on every move.** Gaps and duplicates in
an ``order`` field are how a list ends up in a different order on two pages, so
a move rewrites the whole category as ``0..n-1``.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

# Storage ceilings, not behaviour: they keep one upload from filling the
# database. The same kind of limit ``assets.py`` keeps.
MAX_CATEGORIES = 40
MAX_TILES = 400
MAX_VARIANTS = 8
MAX_NAME = 48
# A tile is small and repeated. This is generous for a 64px pixel tile and
# mean for a photograph, which is the right way round.
MAX_BYTES = 256 * 1024
ALLOWED_TYPES = ("image/png", "image/webp", "image/svg+xml", "image/gif")

# Tiles whose category was removed, or that were never given one. Shown last.
UNCATEGORISED = ""


class TileError(ValueError):
    """A rejected library edit, with a message meant for the panel."""


def _clean_name(value: Any, what: str = "A tile") -> str:
    name = str(value or "").strip()
    if not name:
        raise TileError(f"{what} needs a name.")
    if len(name) > MAX_NAME:
        raise TileError(f"That name is too long (max {MAX_NAME} characters).")
    return name


def check_image(data: bytes, content_type: str) -> None:
    if content_type not in ALLOWED_TYPES:
        raise TileError("A tile must be a PNG, WebP, GIF or SVG.")
    if not data:
        raise TileError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise TileError(f"A tile must be under {MAX_BYTES // 1024}KB.")


def _moved(ids: list[str], target: str, delta: int) -> list[str]:
    """``ids`` with ``target`` moved ``delta`` places, clamped at the ends."""
    if target not in ids:
        return ids
    out = [item for item in ids if item != target]
    index = max(0, min(len(out), ids.index(target) + int(delta)))
    out.insert(index, target)
    return out


class TileLibrary:
    """The owner's tile toolkit, shared by every server. ``bot.dodoland_tiles``."""

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
            self._cats.create_index([("cat_id", 1)], unique=True)
            self._art.create_index([("vid", 1)], unique=True)
            self._art.create_index([("tile_id", 1)])
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    # ------------------------------------------------------------------ #
    #  Categories
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
        """Only an empty category can go. Silently uncategorising forty tiles
        is a decision nobody made."""
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
    #  Tiles
    # ------------------------------------------------------------------ #
    def tiles(self) -> list[dict]:
        """Every tile, metadata only, in palette order: by category, then by
        position inside it, uncategorised last."""
        self._ensure_indexes()
        rank = {row["cat_id"]: index for index, row in enumerate(self.categories())}
        rows = list(self._tiles.find({}, {"_id": 0}))
        rows.sort(key=lambda row: (rank.get(row.get("cat_id") or "", len(rank)),
                                   int(row.get("order", 0)),
                                   str(row.get("name", ""))))
        return rows

    def grouped(self) -> list[tuple[dict, list[dict]]]:
        """``(category, tiles)`` in palette order. The uncategorised group is
        included only when something is in it."""
        tiles = self.tiles()
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
        return row

    def _need(self, tile_id: str) -> dict:
        row = self.get(tile_id)
        if row is None:
            raise TileError("That tile no longer exists.")
        return row

    def _in_category(self, cat_id: str) -> list[dict]:
        rows = [row for row in self.tiles() if (row.get("cat_id") or "") == cat_id]
        return rows

    def _check_category(self, cat_id: Any) -> str:
        cat_id = str(cat_id or "")
        if cat_id and self._category(cat_id) is None:
            raise TileError("That category no longer exists.")
        return cat_id

    def add_tile(self, *, name: Any, cat_id: Any, data: bytes,
                 content_type: str) -> dict:
        """A new tile with its first variant, at the end of its category."""
        self._ensure_indexes()
        if self._tiles.count_documents({}) >= MAX_TILES:
            raise TileError(f"The library holds at most {MAX_TILES} tiles.")
        clean = _clean_name(name)
        cat_id = self._check_category(cat_id)
        check_image(data, content_type)
        tile_id = secrets.token_hex(8)
        vid = self._store_art(tile_id, data, content_type)
        row = {"tile_id": tile_id, "name": clean, "cat_id": cat_id,
               "order": len(self._in_category(cat_id)), "variants": [vid]}
        self._tiles.insert_one(dict(row))
        return row

    def update_tile(self, tile_id: str, *, name: Any = None,
                    cat_id: Any = None) -> None:
        """Rename a tile or move it to another category (it goes to the end)."""
        row = self._need(tile_id)
        changes: dict = {}
        if name is not None:
            changes["name"] = _clean_name(name)
        if cat_id is not None:
            target = self._check_category(cat_id)
            if target != (row.get("cat_id") or ""):
                changes["cat_id"] = target
                changes["order"] = len(self._in_category(target))
        if changes:
            self._tiles.update_one({"tile_id": str(tile_id)}, {"$set": changes})
            if "cat_id" in changes:
                self._renumber_tiles(row.get("cat_id") or "")

    def move_tile(self, tile_id: str, delta: int) -> None:
        row = self._need(tile_id)
        cat_id = row.get("cat_id") or ""
        ids = [t["tile_id"] for t in self._in_category(cat_id)]
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
        self._art.insert_one({"vid": vid, "tile_id": str(tile_id),
                              "data": data, "content_type": content_type})
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
