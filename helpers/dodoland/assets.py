"""
The asset library — the things people can put on their own patch of the world.

An admin uploads images (a cart, a campfire, a banner, a statue) and says what a
person must have reached before they may place one. The map shows the whole
toolkit to everybody, with the locked ones dimmed, because a reward you cannot
see is not a reward: knowing the gilded banner exists at Renowned is the reason
to want Renowned.

Stored in their own collection rather than on the guild's config row. That row
is read on every page load and images are large; binaries in it would make every
read pay for every picture.

**A lock is a tier index, not a point total.** Thresholds are derived from the
server's live distribution and move as the server does, so a point total written
here would quietly mean something different every week. "Tier 3 of the Gallery"
keeps meaning the same thing.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

MAX_ASSETS = 200
MAX_NAME = 48
# Decor is drawn small on a map that may hold hundreds of towns. This is
# generous for a stylised icon and mean for a screenshot.
MAX_BYTES = 512 * 1024
ALLOWED_TYPES = ("image/png", "image/webp", "image/svg+xml", "image/gif")


class AssetError(ValueError):
    """A rejected asset, with a message meant for the panel."""


def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise AssetError("An asset needs a name.")
    if len(name) > MAX_NAME:
        raise AssetError(f"That name is too long (max {MAX_NAME} characters).")
    return name


class AssetStore:
    """Reads and writes a guild's asset library. ``bot.dodoland_assets``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._col.create_index([("guild_id", 1), ("asset_id", 1)], unique=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    def list(self, guild_id: int, *, with_data: bool = False) -> list[dict]:
        """Every asset for a guild, cheapest fields first.

        ``with_data`` is off by default: the toolkit needs names and locks far
        more often than it needs the bytes, and a list that always dragged the
        images along would make the panel pay for the whole library on every
        load.
        """
        self._ensure_indexes()
        fields = None if with_data else {"data": 0}
        rows = list(self._col.find({"guild_id": int(guild_id)}, fields))
        rows.sort(key=lambda row: (int(row.get("min_tier", 0)),
                                   str(row.get("name", "")).lower()))
        return rows

    def get(self, guild_id: int, asset_id: str) -> Optional[dict]:
        self._ensure_indexes()
        return self._col.find_one({"guild_id": int(guild_id),
                                   "asset_id": str(asset_id)})

    def add(self, guild_id: int, *, name: str, data: bytes, content_type: str,
            min_tier: int = 0, building: str = "") -> dict:
        """Store one asset. Returns the stored row without its bytes."""
        self._ensure_indexes()
        guild_id = int(guild_id)
        if self._col.count_documents({"guild_id": guild_id}) >= MAX_ASSETS:
            raise AssetError(f"A server can hold at most {MAX_ASSETS} assets.")
        if content_type not in ALLOWED_TYPES:
            raise AssetError("An asset must be a PNG, WebP, GIF or SVG.")
        if not data:
            raise AssetError("That file is empty.")
        if len(data) > MAX_BYTES:
            raise AssetError(f"An asset must be under {MAX_BYTES // 1024}KB.")

        row = {
            "guild_id": guild_id,
            "asset_id": secrets.token_hex(8),
            "name": _clean_name(name),
            "data": data,
            "content_type": content_type,
            # Which tier of which building unlocks it. Tier index, never points:
            # thresholds are derived and move, so a point total would quietly
            # mean something different every week.
            "min_tier": max(0, int(min_tier or 0)),
            "building": str(building or "").strip(),
        }
        self._col.insert_one(dict(row))
        row.pop("data", None)
        return row

    def remove(self, guild_id: int, asset_id: str) -> bool:
        self._ensure_indexes()
        result = self._col.delete_one({"guild_id": int(guild_id),
                                       "asset_id": str(asset_id)})
        return bool(getattr(result, "deleted_count", 0))

    def update(self, guild_id: int, asset_id: str, *, name: Optional[str] = None,
               min_tier: Optional[int] = None,
               building: Optional[str] = None) -> bool:
        """Rename an asset or change what unlocks it. Never touches the bytes."""
        self._ensure_indexes()
        changes: dict = {}
        if name is not None:
            changes["name"] = _clean_name(name)
        if min_tier is not None:
            changes["min_tier"] = max(0, int(min_tier))
        if building is not None:
            changes["building"] = str(building).strip()
        if not changes:
            return False
        result = self._col.update_one(
            {"guild_id": int(guild_id), "asset_id": str(asset_id)}, {"$set": changes})
        return bool(getattr(result, "modified_count", 0))


def unlocked_for(assets: list[dict], person: Optional[dict]) -> set[str]:
    """Which assets a person has earned the right to place.

    An asset with no building named is unlocked for everybody: that is the
    starter decor, and a library where nothing is available on day one gives
    nobody a reason to open the map twice.
    """
    if not person:
        return {row["asset_id"] for row in assets if not row.get("building")}
    reached = {key: (score.get("tier") if score.get("tier") is not None else -1)
               for key, score in (person.get("buildings") or {}).items()}
    out = set()
    for row in assets:
        building = row.get("building") or ""
        if not building:
            out.add(row["asset_id"])
            continue
        # min_tier 1 means "the first tier", so it is index 0.
        needed = max(0, int(row.get("min_tier", 0)) - 1)
        if reached.get(building, -1) >= needed:
            out.add(row["asset_id"])
    return out
