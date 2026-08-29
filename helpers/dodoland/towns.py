"""
What a person calls their town, and what they say about it.

Standing is earned and cannot be typed in. This is the opposite: everything here
is authored, and none of it changes a single number. A town's name, its
description, its picture and the names of its individual buildings are the part
of the map that belongs to its owner rather than to the scoring.

That separation is deliberate and worth keeping. Naming your library "The
Drunken Archive" should be free, instant and reversible; earning the tier that
made it a library should not be either. Mixing the two would mean a rename could
be an exploit, and it would make the panel afraid of letting people type.

Stored per (guild, user) in a collection of its own. The blurb and the picture
are the only large fields DodoLand keeps per person, and they have no business
on the guild's config row, which is read on every page load.
"""

from __future__ import annotations

from typing import Any, Optional

import re

MAX_NAME = 48
MAX_BLURB = 600
MAX_BUILDING_NAME = 48
# A colour an owner painted one of their buildings. Six-digit hex only: it goes
# straight into an SVG ``fill``, so anything that is not provably a colour is a
# place for markup to get in, and "rgb(...)" and "url(#...)" are both valid CSS.
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# A town's picture. Room for a real drawing or a short loop, and still far
# inside Mongo's 16MB document ceiling with the rest of the row. Two megabytes
# was mean enough that an ordinary PNG export was refused. GIFs are allowed on
# purpose: a town that waves is exactly the sort of thing people put effort
# into.
MAX_IMAGE_BYTES = 6 * 1024 * 1024
ALLOWED_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")


class TownError(ValueError):
    """A rejected town edit, with a message meant for the panel."""


def _text(value: Any, limit: int, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise TownError(f"{field} cannot be empty.")
        return ""
    if len(text) > limit:
        raise TownError(f"{field} is too long (max {limit} characters).")
    return text


class TownStore:
    """Per-person town details. ``bot.dodoland_towns``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        try:
            self._col.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    def get(self, guild_id: int, user_id: int) -> dict:
        self._ensure_indexes()
        return self._col.find_one({"guild_id": int(guild_id),
                                   "user_id": int(user_id)}) or {}

    def all(self, guild_id: int, *, with_images: bool = False) -> dict[int, dict]:
        """``{user_id: details}`` for a guild.

        The image *bytes* are left out by default, but the field itself is
        kept: the map needs to know which towns have a picture without paying
        for the gallery on every load. Excluding the whole ``image`` field
        instead — which is what this did — made "has a picture" permanently
        false, so an uploaded picture saved correctly and then never appeared
        anywhere.
        """
        self._ensure_indexes()
        fields = None if with_images else {"image.data": 0}
        return {int(row["user_id"]): row
                for row in self._col.find({"guild_id": int(guild_id)}, fields)}

    def save(self, guild_id: int, user_id: int, *, name: Optional[str] = None,
             blurb: Optional[str] = None,
             building_names: Optional[dict] = None,
             building_colours: Optional[dict] = None) -> dict:
        """Set any of the authored fields. Absent ones are left alone."""
        self._ensure_indexes()
        changes: dict = {}
        if name is not None:
            changes["name"] = _text(name, MAX_NAME, "A town name")
        if blurb is not None:
            changes["blurb"] = _text(blurb, MAX_BLURB, "A description")
        if building_names is not None:
            if not isinstance(building_names, dict):
                raise TownError("Building names must be a mapping.")
            cleaned = {}
            for key, value in building_names.items():
                label = _text(value, MAX_BUILDING_NAME, "A building name")
                if label:
                    cleaned[str(key)[:40]] = label
            changes["building_names"] = cleaned
        if building_colours is not None:
            if not isinstance(building_colours, dict):
                raise TownError("Building colours must be a mapping.")
            painted = {}
            for key, value in building_colours.items():
                text = str(value or "").strip()
                if not text:
                    continue  # cleared: fall back to the stable hashed colour
                if not _HEX.match(text):
                    raise TownError(f"{text!r} is not a colour. Use #rrggbb.")
                painted[str(key)[:40]] = text.lower()
            changes["building_colours"] = painted
        if not changes:
            return self.get(guild_id, user_id)
        self._col.update_one(
            {"guild_id": int(guild_id), "user_id": int(user_id)},
            {"$set": changes}, upsert=True,
        )
        return self.get(guild_id, user_id)

    def save_image(self, guild_id: int, user_id: int,
                   image: Optional[dict]) -> None:
        """Store or clear a town's picture. ``None`` removes it."""
        self._ensure_indexes()
        query = {"guild_id": int(guild_id), "user_id": int(user_id)}
        if image is None:
            self._col.update_one(query, {"$unset": {"image": ""}}, upsert=True)
            return
        content_type = str(image.get("content_type") or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise TownError("A town picture must be a PNG, JPEG, GIF or WebP.")
        data = image.get("data") or b""
        if not data:
            raise TownError("That file is empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise TownError(f"A picture must be under "
                            f"{MAX_IMAGE_BYTES // (1024 * 1024)}MB.")
        self._col.update_one(
            query, {"$set": {"image": {"data": data, "content_type": content_type}}},
            upsert=True,
        )


def display_name(details: dict, fallback: str) -> str:
    """What to call a town: what its owner named it, or after its owner."""
    return str((details or {}).get("name") or "").strip() or fallback


def building_label(details: dict, key: str, fallback: str) -> str:
    """What to call one building: its owner's name for it, or the tier's."""
    named = ((details or {}).get("building_names") or {}).get(str(key))
    return str(named or "").strip() or fallback


def building_colour(details: dict, key: str, fallback: str = "") -> str:
    """What colour its owner painted one building, or nothing.

    Empty means "not painted", and the artwork falls back to the stable hashed
    colour per building key. Painting is authored the same way naming is: free,
    instant, reversible, and it moves no number.
    """
    painted = ((details or {}).get("building_colours") or {}).get(str(key))
    text = str(painted or "").strip()
    return text if _HEX.match(text) else fallback
