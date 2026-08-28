"""
Buildings — what a town is made of, and how a tier is earned.

A building is **per-guild data, not a constant**. Name, icon, the channels that
feed it and what each is worth there, its per-metric multipliers, and its tiers.
Free-form the way trial ranks are free-form: rename it, repoint it, delete it,
add a fourth. Nothing in the engine knows what a "library" is.

Thresholds are derived, not authored
------------------------------------

This is the decision that separates these tiers from the document they came
from, which asked one person for 125,000 acts when the server's entire history
is 306,927 messages. Authored numbers are wrong twice: wrong on day one when
nobody has any, and wrong again in a year when everybody does.

So a tier carries a **percentile** of the server's own live distribution. Tier 6
at percentile 95 means "the top 5% of people who have any score in this
building", and it means that on day one, in three years, on a 60-person server
and on a 600-person one. Nothing has to be re-tuned, and no tier is ever dead.

A tier also carries a small **floor** in absolute points, and the effective
threshold is whichever is higher. That exists for the young-server case: with
four scoring people a percentile is arithmetic rather than an achievement, and
"top 5%" should not be reachable with three messages. The floor stops that
without anybody having to maintain it.

Both numbers are visible in the panel next to what they currently resolve to,
because a threshold you cannot see resolve is exactly the black box the whole
design is trying to avoid.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from helpers.dodoland import metrics as metric_registry

MAX_BUILDINGS = 12
MAX_TIERS = 12
MAX_NAME = 60
MAX_TITLE = 60
MAX_ICON = 8
# A channel's weight is a multiplier, so this is "worth ten times a normal room".
MAX_WEIGHT = 10.0


class DodoLandError(ValueError):
    """A rejected DodoLand setting, with a message meant for the panel."""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return cleaned or "building"


def _clean_text(value: Any, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DodoLandError(f"{field} cannot be empty.")
    if len(text) > limit:
        raise DodoLandError(f"{field} is too long (max {limit} characters).")
    return text


def _weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DodoLandError("A channel weight must be a number.") from None
    if number < 0 or number > MAX_WEIGHT:
        raise DodoLandError(f"A channel weight must be between 0 and {MAX_WEIGHT}.")
    return round(number, 3)


def _percentile(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DodoLandError("A tier percentile must be a number.") from None
    if number < 0 or number > 100:
        raise DodoLandError("A tier percentile must be between 0 and 100.")
    return round(number, 2)


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
def validate_tiers(value: Any) -> list[dict]:
    """``[{title, percentile, floor}]``, kept sorted from easiest to hardest."""
    if not isinstance(value, list):
        raise DodoLandError("Tiers must be a list.")
    if len(value) > MAX_TIERS:
        raise DodoLandError(f"A building can have at most {MAX_TIERS} tiers.")
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise DodoLandError("Each tier must be an object.")
        floor = item.get("floor", 0)
        try:
            floor = max(0, int(floor))
        except (TypeError, ValueError):
            raise DodoLandError("A tier floor must be a whole number of points.") from None
        out.append({
            "title": _clean_text(item.get("title"), MAX_TITLE, "A tier title"),
            "percentile": _percentile(item.get("percentile", 0)),
            "floor": floor,
        })
    out.sort(key=lambda tier: (tier["percentile"], tier["floor"]))
    titles = [tier["title"].lower() for tier in out]
    if len(set(titles)) != len(titles):
        raise DodoLandError("Two tiers in the same building have the same title.")
    return out


def validate_channels(value: Any, *, guild=None) -> dict[int, float]:
    """``{channel_id: weight}`` — which rooms feed this building, and how much."""
    if isinstance(value, list):
        # The panel posts a list of rows; both shapes are accepted so the API
        # does not dictate the widget.
        value = {row.get("channel_id"): row.get("weight", 1) for row in value
                 if isinstance(row, dict)}
    if not isinstance(value, dict):
        raise DodoLandError("A building's channels must be a mapping.")
    out: dict[int, float] = {}
    known = {c.id for c in guild.channels} if guild is not None else None
    for raw_id, weight in value.items():
        try:
            channel_id = int(raw_id)
        except (TypeError, ValueError):
            raise DodoLandError("A channel id must be a number.") from None
        if known is not None and channel_id not in known:
            raise DodoLandError("A channel in this building is not in this server.")
        out[channel_id] = _weight(weight)
    return out


def validate_metric_weights(value: Any) -> dict[str, float]:
    """``{metric_key: multiplier}`` — this building's own emphasis.

    Absent means 1.0. A building that wants pictures to matter more sets
    ``image`` here rather than changing the server-wide weight, which would
    change every other building at the same time.
    """
    if not isinstance(value, dict):
        if value in (None, "", []):
            return {}
        raise DodoLandError("A building's metric weights must be a mapping.")
    out: dict[str, float] = {}
    for key, weight in value.items():
        metric_registry.get(str(key))  # raises KeyError on an unknown metric
        out[str(key)] = _weight(weight)
    return out


def validate_building(value: Any, *, guild=None) -> dict:
    """One building, fully checked, ready to store."""
    if not isinstance(value, dict):
        raise DodoLandError("A building must be an object.")
    name = _clean_text(value.get("name"), MAX_NAME, "A building name")
    icon = str(value.get("icon") or "").strip()[:MAX_ICON]
    return {
        "key": _slug(value.get("key") or name),
        "name": name,
        "icon": icon,
        "channels": validate_channels(value.get("channels") or {}, guild=guild),
        "metric_weights": validate_metric_weights(value.get("metric_weights") or {}),
        "tiers": validate_tiers(value.get("tiers") or []),
    }


def validate_buildings(value: Any, *, guild=None) -> list[dict]:
    """The whole set, with unique keys."""
    if not isinstance(value, list):
        raise DodoLandError("Buildings must be a list.")
    if len(value) > MAX_BUILDINGS:
        raise DodoLandError(f"A server can have at most {MAX_BUILDINGS} buildings.")
    out = [validate_building(item, guild=guild) for item in value]
    keys = [building["key"] for building in out]
    if len(set(keys)) != len(keys):
        raise DodoLandError("Two buildings have the same key. Rename one of them.")
    return out


# --------------------------------------------------------------------------- #
#  Defaults
# --------------------------------------------------------------------------- #
# Six tiers, not thirty. Every one of these will be reached by somebody, which
# is the entire argument: the document this replaces spent sixty of its ninety
# art states on tiers nobody could ever see.
_DEFAULT_TIERS = (
    ("Foundations", 20.0, 25),
    ("Established", 40.0, 100),
    ("Notable", 60.0, 300),
    ("Renowned", 80.0, 800),
    ("Storied", 92.0, 2000),
    ("Legendary", 98.0, 5000),
)


def _tier_set(titles: Iterable[str]) -> list[dict]:
    return [{"title": title, "percentile": pct, "floor": floor}
            for title, (_default, pct, floor) in zip(titles, _DEFAULT_TIERS)]


def default_buildings() -> list[dict]:
    """A starting set with no channels attached.

    Deliberately unattached: a building that silently counts every room is a
    building nobody configured, and the first thing an admin should do is say
    which rooms are which. The names are a suggestion and are meant to be
    rewritten.
    """
    return [
        {"key": "library", "name": "The Grand Library", "icon": "📚",
         "channels": {}, "metric_weights": {},
         "tiers": _tier_set(("Scholar's Desk", "Reading Nook", "Modest Archive",
                             "The Athenaeum", "Grand Library", "Citadel of Wisdom"))},
        {"key": "menagerie", "name": "The Menagerie", "icon": "🦜",
         "channels": {}, "metric_weights": {"image": 2.0},
         "tiers": _tier_set(("Mud Paddock", "Animal Pens", "The Stables",
                             "Exotic Menagerie", "The Aviary", "Gilded Sanctuary"))},
        {"key": "barracks", "name": "The Vanguard Barracks", "icon": "🛡️",
         "channels": {}, "metric_weights": {},
         "tiers": _tier_set(("Training Dummy", "Militia Camp", "The Armory",
                             "Guardhouse", "Vanguard Keep", "Paragon's Redoubt"))},
    ]


# --------------------------------------------------------------------------- #
#  Store
# --------------------------------------------------------------------------- #
class BuildingStore:
    """The per-guild DodoLand configuration document.

    One row per guild, holding the buildings and (later) the map. Reads are
    cached per guild and dropped on write, the same approach the rest of the
    bot's per-guild config uses.
    """

    def __init__(self, collection) -> None:
        self._col = collection
        self._cache: dict[int, dict] = {}

    def config(self, guild_id: int) -> dict:
        guild_id = int(guild_id)
        if guild_id not in self._cache:
            doc = self._col.find_one({"_id": guild_id}) or {}
            self._cache[guild_id] = doc
        return self._cache[guild_id]

    def buildings(self, guild_id: int) -> list[dict]:
        """This guild's buildings, or the unattached defaults if none are set."""
        stored = self.config(guild_id).get("buildings")
        return list(stored) if stored else default_buildings()

    def is_configured(self, guild_id: int) -> bool:
        """Whether anybody has saved buildings, as opposed to seeing defaults."""
        return bool(self.config(guild_id).get("buildings"))

    def invalidate(self, guild_id: Optional[int] = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(int(guild_id), None)

    def map_image(self, guild_id: int) -> Optional[dict]:
        """The uploaded base map, or ``None`` if this server has not set one."""
        return self.config(guild_id).get("map") or None

    def save_map(self, guild_id: int, image: Optional[dict]) -> None:
        """Store or clear the base map. ``None`` removes it."""
        guild_id = int(guild_id)
        if image is None:
            self._col.update_one({"_id": guild_id}, {"$unset": {"map": ""}}, upsert=True)
        else:
            self._col.update_one({"_id": guild_id}, {"$set": {"map": image}}, upsert=True)
        self.invalidate(guild_id)

    def plots(self, guild_id: int) -> dict[int, dict]:
        """``{user_id: {x, y}}`` — where people have settled, in map percentages.

        Percentages rather than pixels so replacing the base image with a
        redrawn one of a different size does not move everybody's town.
        """
        return {int(k): v for k, v in (self.config(guild_id).get("plots") or {}).items()}

    def settle(self, guild_id: int, user_id: int, x: float, y: float) -> dict:
        """Claim a plot. Re-settling moves the town rather than making a second."""
        spot = {"x": round(max(0.0, min(100.0, float(x))), 3),
                "y": round(max(0.0, min(100.0, float(y))), 3)}
        self._col.update_one({"_id": int(guild_id)},
                             {"$set": {f"plots.{int(user_id)}": spot}}, upsert=True)
        self.invalidate(guild_id)
        return spot

    def save_buildings(self, guild_id: int, value: Any, *, guild=None) -> list[dict]:
        buildings = validate_buildings(value, guild=guild)
        self._col.update_one({"_id": int(guild_id)},
                             {"$set": {"buildings": buildings}}, upsert=True)
        self.invalidate(guild_id)
        return buildings
