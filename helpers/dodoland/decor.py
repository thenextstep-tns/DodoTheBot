"""
Putting a thing from the library on the ground.

The asset library, the tier locks and the toolkit strip have all existed for a
while and nothing has ever placed one. This is that missing half, and it serves
two people who want different things from it:

* **An admin dressing the world.** Forests, rivers, mountains, ruins, a
  lighthouse on a headland — decor that belongs to the *map* and that everybody
  sees in the same place. It sits at a percentage of the base image, exactly
  the way a town does, so re-uploading a redrawn map at another resolution
  moves nothing.

* **A player dressing their own town.** A cart outside the tavern, a bonfire, a
  standing stone on the hill behind. It sits at a percentage of **their town's
  own box**, so it travels with the town when the town is moved or resized, and
  it can never end up on somebody else's land.

Those are the only two scopes, and the difference is not cosmetic: world decor
is configuration and town decor is a possession. They are stored in one
collection with a ``scope`` because they are the same shape and the same
toolkit places both, and separated by an ``owner_id`` that is ``0`` for the
world and a user id for a town.

**What may be placed is decided here, not in the browser.** ``tiles.unlocked_for``
says which tiles somebody has reached the requirements of; this refuses a
placement that does not pass it, and clamps its size to what the tile allows.
``asset_id`` on a row holds a **tile id** since the tile library replaced the
asset library. A toolkit that dims the locked ones is a courtesy — the
refusal is the rule.

Nothing here scores anything. Decor is authored, like a town's name and its
colours: free, instant, reversible, and it moves no number. Standing is earned
and cannot be decorated into existence.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Optional

SCOPE_WORLD = "world"
SCOPE_TOWN = "town"
SCOPES = (SCOPE_WORLD, SCOPE_TOWN)

# Per-scope ceilings. The world's is generous because one person curates it;
# a town's is mean on purpose — a plot with forty things on it is a junk pile,
# and scarcity is what makes any of them worth placing.
MAX_WORLD = 20000
# How a piece stacks against the others ("" is its layer's own way).
STACKS = ("", "flat", "stand", "top")
MAX_PER_TOWN = 24

MIN_SCALE, MAX_SCALE = 0.25, 12.0


def _clamp_scale(size: float, scale_range: tuple) -> float:
    low, high = (max(MIN_SCALE, float(scale_range[0])), min(MAX_SCALE, float(scale_range[1])))
    return round(max(low, min(high, size)), 3)


class DecorError(ValueError):
    """A rejected placement, with a message meant for the panel."""


def _coord(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DecorError(f"{field} must be a number.") from None
    # A little slack past the edges: a forest may legitimately run off the
    # coast, and a town's decor may sit just outside its own box.
    if not -20.0 <= number <= 120.0:
        raise DecorError(f"{field} is off the map.")
    return round(number, 3)


class DecorStore:
    """Everything placed on the ground. ``bot.dodoland_decor``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._col.create_index([("guild_id", 1), ("scope", 1), ("owner_id", 1)])
            self._col.create_index([("guild_id", 1), ("piece_id", 1)], unique=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def world(self, guild_id: int) -> list[dict]:
        """Everything an admin has put on the map itself."""
        self._ensure_indexes()
        rows = list(self._col.find({"guild_id": int(guild_id),
                                    "scope": SCOPE_WORLD}))
        rows.sort(key=lambda row: (float(row.get("y", 0)), str(row.get("piece_id"))))
        return rows

    def town(self, guild_id: int, owner_id: int) -> list[dict]:
        """Everything one person has put in and around their own town."""
        self._ensure_indexes()
        rows = list(self._col.find({"guild_id": int(guild_id), "scope": SCOPE_TOWN,
                                    "owner_id": int(owner_id)}))
        rows.sort(key=lambda row: (float(row.get("y", 0)), str(row.get("piece_id"))))
        return rows

    def towns(self, guild_id: int) -> dict[int, list[dict]]:
        """``{owner_id: pieces}`` for a whole guild, in one read.

        The map draws every placed town at once, so asking per person would be
        one query per settlement — the same mistake that once put eight full
        scans in front of every panel load.
        """
        self._ensure_indexes()
        out: dict[int, list[dict]] = {}
        for row in self._col.find({"guild_id": int(guild_id), "scope": SCOPE_TOWN}):
            out.setdefault(int(row.get("owner_id", 0)), []).append(row)
        for pieces in out.values():
            pieces.sort(key=lambda row: (float(row.get("y", 0)),
                                         str(row.get("piece_id"))))
        return out

    def count(self, guild_id: int, scope: str, owner_id: int = 0) -> int:
        self._ensure_indexes()
        return int(self._col.count_documents({
            "guild_id": int(guild_id), "scope": str(scope),
            **({"owner_id": int(owner_id)} if scope == SCOPE_TOWN else {}),
        }))

    def town_count(self, guild_id: int, town: str) -> int:
        """How many world pieces belong to one town: its buildings and what its
        owner has put around it."""
        self._ensure_indexes()
        return int(self._col.count_documents({
            "guild_id": int(guild_id), "scope": SCOPE_WORLD, "town": str(town)[:24]}))

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def place(self, guild_id: int, *, scope: str, asset_id: str, x: Any, y: Any,
              owner_id: int = 0, scale: Any = 1.0, flip: bool = False,
              allowed: Optional[set] = None,
              scale_range: tuple = (MIN_SCALE, MAX_SCALE),
              variant: str = "", source: str = "", layer: str = "objects",
              placed_by: int = 0, placed_by_name: str = "", town: str = "",
              locked: bool = False) -> dict:
        """Put one thing down, and return the row that was written.

        ``scale_range`` is what the tile may be sized to — ``(1, 1)`` for a
        tile that is not resizable — and a size outside it is clamped, here,
        not in the browser.

        ``allowed`` is the set of tile ids this person may place. Passing
        ``None`` means the caller is an administrator acting on the world and
        the locks do not apply to them; passing a set means they do, and this
        is the only place that check is enforced.
        """
        self._ensure_indexes()
        guild_id, owner_id = int(guild_id), int(owner_id)
        if scope not in SCOPES:
            raise DecorError(f"Unknown scope: {scope!r}")
        asset_id = str(asset_id or "").strip()
        if not asset_id:
            raise DecorError("Nothing was chosen to place.")
        if allowed is not None and asset_id not in allowed:
            raise DecorError("That one is not unlocked yet.")

        limit = MAX_WORLD if scope == SCOPE_WORLD else MAX_PER_TOWN
        if self.count(guild_id, scope, owner_id) >= limit:
            raise DecorError(
                f"That is the most that can be placed here ({limit}). Remove "
                "something first." if scope == SCOPE_TOWN else
                f"The map already holds {limit} pieces of decor.")

        row = self._row(guild_id, scope=scope, asset_id=asset_id, x=x, y=y,
                        owner_id=owner_id, scale=scale, flip=flip,
                        scale_range=scale_range, variant=variant, source=source,
                        layer=layer, placed_by=placed_by, placed_by_name=placed_by_name)
        if town:
            # Which town it was built for, if it was: the town's own buildings.
            row["town"] = str(town)[:24]
        if locked:
            row["locked"] = True   # placed in landmark mode
        self._col.insert_one(dict(row))
        return row

    def place_many(self, guild_id: int, items: list[dict], *, placed_by: int = 0,
                   placed_by_name: str = "", locked: bool = False,
                   town: str = "") -> list[dict]:
        """Many world pieces in one write — a brush stroke.

        Each item is ``{asset_id, x, y, scale, flip, variant, layer,
        scale_range}``, already checked by the caller. One ``insert_many``
        rather than one round trip per piece: a stroke of a hundred trees was a
        hundred requests to the database.
        """
        self._ensure_indexes()
        guild_id = int(guild_id)
        if not items:
            return []
        if self.count(guild_id, SCOPE_WORLD) + len(items) > MAX_WORLD:
            raise DecorError(f"The map holds at most {MAX_WORLD} pieces of decor.")
        rows = [self._row(guild_id, scope=SCOPE_WORLD, asset_id=item["asset_id"],
                          x=item.get("x"), y=item.get("y"), scale=item.get("scale", 1.0),
                          flip=bool(item.get("flip")),
                          scale_range=item.get("scale_range") or (MIN_SCALE, MAX_SCALE),
                          variant=item.get("variant") or "", layer=item.get("layer") or "objects",
                          placed_by=placed_by, placed_by_name=placed_by_name)
                for item in items]
        for row in rows:
            if locked:
                row["locked"] = True
            if town:
                row["town"] = str(town)[:24]   # a member's own, around their town
        self._col.insert_many([dict(row) for row in rows])
        return rows

    def _row(self, guild_id: int, *, scope: str, asset_id: str, x: Any, y: Any,
             owner_id: int = 0, scale: Any = 1.0, flip: bool = False,
             scale_range: tuple = (MIN_SCALE, MAX_SCALE), variant: str = "",
             source: str = "", layer: str = "objects", placed_by: int = 0,
             placed_by_name: str = "") -> dict:
        try:
            size = float(scale)
        except (TypeError, ValueError):
            size = 1.0
        row = {
            "guild_id": guild_id,
            "piece_id": secrets.token_hex(8),
            "scope": scope,
            # 0 for the world. A town's decor belongs to exactly one person and
            # the endpoints never take this from a request body.
            "owner_id": owner_id if scope == SCOPE_TOWN else 0,
            "asset_id": asset_id,
            "x": _coord(x, "A position"),
            "y": _coord(y, "A position"),
            "scale": _clamp_scale(size, scale_range),
            "flip": bool(flip),
            # Which of the tile's images this piece shows. A scattered range
            # of mountains is many drawings of one tile, and each piece keeps
            # its own; empty means the tile's first.
            "variant": str(variant or ""),
            # The map layer it belongs to, from its tile, so the map can draw,
            # show, hide and lock layers separately.
            "layer": str(layer or "objects"),
            # Who put it there and when, so a person can find and take back
            # what they placed. 0 for pieces from before this was recorded, and
            # for imports.
            "by": int(placed_by or 0),
            "by_name": str(placed_by_name or "")[:64],
            "at": int(time.time()),
        }
        if source:
            # Where an imported piece came from, so an import can be re-run.
            row["source"] = str(source)[:120]
        return row

    def sources(self, guild_id: int) -> set:
        """The ``source`` keys already placed on this guild's map."""
        self._ensure_indexes()
        return {row["source"] for row in self._col.find(
            {"guild_id": int(guild_id), "scope": SCOPE_WORLD}, {"source": 1})
            if row.get("source")}

    def set_stack(self, guild_id: int, piece_ids: list, stack: str, *, town: str = "") -> int:
        """How pieces stack: ``flat`` (under everything standing), ``stand``
        (in front of what stands behind it, by where it stands), ``top`` (over
        everything), or ``""`` for its layer's own way. ``town`` narrows it to
        that town's pieces (a member's own). Returns how many changed."""
        if stack not in STACKS:
            raise DecorError("Stacking is flat, standing or on top.")
        self._ensure_indexes()
        query = {"guild_id": int(guild_id), "piece_id": {"$in": [str(i) for i in piece_ids][:2000]}}
        if town:
            query["town"] = str(town)[:24]
        result = self._col.update_many(query, {"$set": {"stack": stack}})
        return int(getattr(result, "modified_count", 0))

    def move(self, guild_id: int, piece_id: str, *, x: Any = None, y: Any = None,
             scale: Any = None, flip: Any = None, rot: Any = None, yaw: Any = None,
             owner_id: Optional[int] = None,
             scale_range: tuple = (MIN_SCALE, MAX_SCALE)) -> bool:
        """Move, resize or mirror one piece.

        ``owner_id`` narrows the query rather than being checked afterwards, so
        a player's request cannot touch a piece that is not theirs even if they
        know its id. That is the whole reason it is a query term.
        """
        self._ensure_indexes()
        changes: dict = {}
        if x is not None:
            changes["x"] = _coord(x, "A position")
        if y is not None:
            changes["y"] = _coord(y, "A position")
        if scale is not None:
            try:
                changes["scale"] = _clamp_scale(float(scale), scale_range)
            except (TypeError, ValueError):
                raise DecorError("That size is not a number.") from None
        if flip is not None:
            changes["flip"] = bool(flip)
        if rot is not None:
            try:
                changes["rot"] = round(float(rot) % 360.0, 1)
            except (TypeError, ValueError):
                raise DecorError("That turn is not a number.") from None
        if yaw is not None:
            # Turned on the ground (a fence running off into the distance).
            try:
                changes["yaw"] = round(float(yaw) % 360.0, 1)
            except (TypeError, ValueError):
                raise DecorError("That turn is not a number.") from None
        if not changes:
            return False
        query = {"guild_id": int(guild_id), "piece_id": str(piece_id)}
        if owner_id is not None:
            query.update({"scope": SCOPE_TOWN, "owner_id": int(owner_id)})
        result = self._col.update_one(query, {"$set": changes})
        return bool(getattr(result, "modified_count", 0))

    def set_landmark(self, guild_id: int, piece_ids: list, locked: bool) -> int:
        """Make world pieces landmarks, or ordinary pieces again.

        A landmark is the map as its admins set it up: nobody moves or removes
        it (an admin unlocks it first), no town carries it off when it moves,
        and no member paints the ground under it.
        """
        self._ensure_indexes()
        ids = [str(p) for p in piece_ids or []][:2000]
        if not ids:
            return 0
        # Unlocking takes off a member's own lock too: an admin's one button
        # frees anything, whoever locked it.
        changes = {"locked": True} if locked else {"locked": False, "pinned": False}
        result = self._col.update_many({"guild_id": int(guild_id), "scope": SCOPE_WORLD,
                                        "piece_id": {"$in": ids}}, {"$set": changes})
        return int(getattr(result, "modified_count", 0))

    def set_pinned(self, guild_id: int, piece_ids: list, pinned: bool, town=None) -> int:
        """A member's own lock: their building stays put until they (or an
        admin) unlock it, so it is not dragged or deleted by accident. Unlike a
        landmark it is still the town's — it moves with the town, and the
        ground under it can be painted. Never touches an admin's landmark.
        ``town`` narrows it to that town's own pieces."""
        self._ensure_indexes()
        ids = [str(p) for p in piece_ids or []][:2000]
        if not ids:
            return 0
        query = {"guild_id": int(guild_id), "scope": SCOPE_WORLD,
                 "piece_id": {"$in": ids}, "locked": {"$ne": True}}
        if town is not None:
            query["town"] = str(town)
        result = self._col.update_many(query, {"$set": {"pinned": bool(pinned)}})
        return int(getattr(result, "modified_count", 0))

    def held(self, guild_id: int, piece_ids) -> dict:
        """Which of these pieces may not be moved or removed, and why:
        ``{piece_id: "landmark" | "pinned"}``."""
        ids = [str(p) for p in piece_ids or []]
        if not ids:
            return {}
        return {row["piece_id"]: ("landmark" if row.get("locked") else "pinned")
                for row in self._col.find(
                    {"guild_id": int(guild_id), "piece_id": {"$in": ids},
                     "$or": [{"locked": True}, {"pinned": True}]},
                    {"piece_id": 1, "locked": 1})}

    def landmarks(self, guild_id: int, piece_ids) -> set:
        """Which of these pieces are landmarks."""
        ids = [str(p) for p in piece_ids or []]
        if not ids:
            return set()
        return {row["piece_id"] for row in self._col.find(
            {"guild_id": int(guild_id), "piece_id": {"$in": ids}, "locked": True}, {"piece_id": 1})}

    def remove_town_buildings(self, guild_id: int, town_id) -> int:
        """Every piece built for one town, gone: what Remove Town takes with it."""
        self._ensure_indexes()
        result = self._col.delete_many({"guild_id": int(guild_id), "scope": SCOPE_WORLD,
                                        "town": str(town_id)})
        return int(getattr(result, "deleted_count", 0))

    def remove_many(self, guild_id: int, piece_ids: list) -> int:
        """World pieces by id, in one write. Town pieces are never touched."""
        self._ensure_indexes()
        ids = [str(p) for p in piece_ids or []][:2000]
        if not ids:
            return 0
        result = self._col.delete_many({"guild_id": int(guild_id), "scope": SCOPE_WORLD,
                                        "piece_id": {"$in": ids}})
        return int(getattr(result, "deleted_count", 0))

    def remove(self, guild_id: int, piece_id: str,
               owner_id: Optional[int] = None) -> bool:
        self._ensure_indexes()
        query = {"guild_id": int(guild_id), "piece_id": str(piece_id)}
        if owner_id is not None:
            query.update({"scope": SCOPE_TOWN, "owner_id": int(owner_id)})
        result = self._col.delete_one(query)
        return bool(getattr(result, "deleted_count", 0))

    def clear_town(self, guild_id: int, owner_id: int) -> int:
        """Everything one person placed, gone. Used when a town is unsettled."""
        self._ensure_indexes()
        result = self._col.delete_many({"guild_id": int(guild_id),
                                        "scope": SCOPE_TOWN,
                                        "owner_id": int(owner_id)})
        return int(getattr(result, "deleted_count", 0))

    def piece(self, guild_id: int, piece_id: str) -> Optional[dict]:
        self._ensure_indexes()
        return self._col.find_one({"guild_id": int(guild_id), "piece_id": str(piece_id)})

    def forget_tile(self, tile_id: str) -> int:
        """Every placement of a tile that no longer exists, on every server —
        a global tile can be placed anywhere. ``asset_id`` holds the tile id
        since the tile library replaced the asset library."""
        self._ensure_indexes()
        result = self._col.delete_many({"asset_id": str(tile_id)})
        return int(getattr(result, "deleted_count", 0))

    def forget_asset(self, guild_id: int, asset_id: str) -> int:
        """Remove every placement of an asset that no longer exists.

        Called when the library drops one. Without it a deleted asset leaves
        pieces behind that render as a broken image on somebody's town, which
        looks like their town is broken rather than like an admin tidied up.
        """
        self._ensure_indexes()
        result = self._col.delete_many({"guild_id": int(guild_id),
                                        "asset_id": str(asset_id)})
        return int(getattr(result, "deleted_count", 0))
