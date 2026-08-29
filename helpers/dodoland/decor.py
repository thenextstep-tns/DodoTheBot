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

**What may be placed is decided here, not in the browser.** ``assets.unlocked_for``
already says which assets somebody has earned; this refuses a placement that
does not pass it. A toolkit that dims the locked ones is a courtesy — the
refusal is the rule.

Nothing here scores anything. Decor is authored, like a town's name and its
colours: free, instant, reversible, and it moves no number. Standing is earned
and cannot be decorated into existence.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

SCOPE_WORLD = "world"
SCOPE_TOWN = "town"
SCOPES = (SCOPE_WORLD, SCOPE_TOWN)

# Per-scope ceilings. The world's is generous because one person curates it;
# a town's is mean on purpose — a plot with forty things on it is a junk pile,
# and scarcity is what makes any of them worth placing.
MAX_WORLD = 400
MAX_PER_TOWN = 24

MIN_SCALE, MAX_SCALE = 0.25, 6.0


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

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def place(self, guild_id: int, *, scope: str, asset_id: str, x: Any, y: Any,
              owner_id: int = 0, scale: Any = 1.0, flip: bool = False,
              allowed: Optional[set] = None) -> dict:
        """Put one thing down, and return the row that was written.

        ``allowed`` is the set of asset ids this person may place. Passing
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
            "scale": round(max(MIN_SCALE, min(MAX_SCALE, size)), 3),
            "flip": bool(flip),
        }
        self._col.insert_one(dict(row))
        return row

    def move(self, guild_id: int, piece_id: str, *, x: Any = None, y: Any = None,
             scale: Any = None, flip: Any = None,
             owner_id: Optional[int] = None) -> bool:
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
                changes["scale"] = round(
                    max(MIN_SCALE, min(MAX_SCALE, float(scale))), 3)
            except (TypeError, ValueError):
                raise DecorError("That size is not a number.") from None
        if flip is not None:
            changes["flip"] = bool(flip)
        if not changes:
            return False
        query = {"guild_id": int(guild_id), "piece_id": str(piece_id)}
        if owner_id is not None:
            query.update({"scope": SCOPE_TOWN, "owner_id": int(owner_id)})
        result = self._col.update_one(query, {"$set": changes})
        return bool(getattr(result, "modified_count", 0))

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
