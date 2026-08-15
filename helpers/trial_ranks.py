"""
Trial ranking — clears and achievements earn points, points earn a rank role.

Deliberately separate from tribes: this is one concrete ladder, not a rule
engine, and it reads the structure the server already has.

**Sections come from the divider roles.** A role list like

    ============ RANKS & ROLES ========
    Legend / 170k / Tank / Healer / DD
    ======== ACHIEVEMENTS ========
    Master Angler / Godslayer / …
    ============ CLEARS ============
    vHRC(HM) / vAA(HM) / …
    ============ GROUPS ============

already says which role is what. Walking the roles top-down (Discord's own
hierarchy order), every role belongs to the last divider seen, so:

* **ranks**        — the ladder's rungs; each gets a points threshold
* **achievements** — worth points
* **clears**       — worth points, into the same total
* **groups** and anything after — ignored

That means adding a new trial to the server puts it in front of you here
automatically, flagged as "no points set", instead of needing to be registered
by hand.
"""

from __future__ import annotations

import datetime
import re
from typing import Iterable, Optional

# A divider is a role whose name is mostly separator characters around a word.
_DIVIDER_CHARS = re.compile(r"[=\-–—_~*•·\s]")
_SECTION_WORDS = (
    ("ranks", ("RANK",)),
    ("achievements", ("ACHIEV",)),
    ("clears", ("CLEAR",)),
    ("groups", ("GROUP",)),
)
SCORING_SECTIONS = ("clears", "achievements")
SECTION_LABELS = {
    "ranks": "Ranks & roles",
    "achievements": "Achievements",
    "clears": "Clears",
    "groups": "Groups",
    "other": "Everything else",
}


class TrialError(ValueError):
    """A rejected trial-ranking setting, with a message for the panel."""


def divider_section(role_name: str) -> Optional[str]:
    """Which section a divider role opens, or ``None`` if it isn't a divider.

    Requires actual separator characters, so a normal role called "Clears"
    doesn't accidentally split the list.
    """
    name = role_name or ""
    if name.count("=") < 2 and name.count("-") < 3 and name.count("—") < 2:
        return None
    letters = _DIVIDER_CHARS.sub("", name).upper()
    if not letters:
        return None
    for section, words in _SECTION_WORDS:
        if any(word in letters for word in words):
            return section
    return None


def sections(guild) -> dict[str, list]:
    """Group a guild's roles by the divider above them, hierarchy order."""
    out: dict[str, list] = {key: [] for key in ("ranks", "achievements", "clears", "groups", "other")}
    current = "other"
    for role in sorted(guild.roles, key=lambda r: -r.position):
        if role.is_default():
            continue
        found = divider_section(role.name)
        if found:
            current = found
            continue
        if role.managed:
            continue  # bot/integration roles are never part of the ladder
        out[current].append(role)
    return out


def scoring_roles(guild) -> list:
    """Every role that may carry points — clears and achievements."""
    grouped = sections(guild)
    return [role for key in SCORING_SECTIONS for role in grouped[key]]


# --------------------------------------------------------------------------- #
#  Scoring
# --------------------------------------------------------------------------- #
def score_for(role_ids: Iterable[int], points: dict) -> int:
    """Sum the point value of every scoring role the member holds.

    Clears and achievements go into the same total, so a decorated player and a
    prolific clearer can arrive at the same rank by different routes.
    """
    held = set(role_ids or ())
    total = 0
    for role_id, value in (points or {}).items():
        if int(role_id) in held:
            total += int(value)
    return total


def rank_for(score: int, ranks: list[dict]) -> Optional[dict]:
    """The highest rank whose threshold this score reaches."""
    reached = [rank for rank in ranks or () if score >= rank["min_points"]]
    return max(reached, key=lambda rank: rank["min_points"]) if reached else None


def unpriced(guild, points: dict) -> list:
    """Scoring roles with no points set yet — surfaced so nothing is forgotten."""
    priced = {int(role_id) for role_id, value in (points or {}).items()}
    return [role for role in scoring_roles(guild) if role.id not in priced]


# --------------------------------------------------------------------------- #
#  Validation + storage
# --------------------------------------------------------------------------- #
def validate_points(value, *, guild=None) -> dict:
    """``{role_id: points}``, keyed by string id (Mongo can't take int keys)."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise TrialError("Points must be a mapping of role to value.")
    if len(value) > 500:
        raise TrialError("Too many scoring roles.")
    out = {}
    for role_id, points in value.items():
        try:
            role_id = int(role_id)
            points = int(points)
        except (TypeError, ValueError):
            raise TrialError("Points must be whole numbers.") from None
        if not -100_000 <= points <= 100_000:
            raise TrialError("Points are out of range.")
        if guild is not None and guild.get_role(role_id) is None:
            raise TrialError("A scoring role isn't in this server.")
        if points:  # zero means "not scored" — don't store it
            out[str(role_id)] = points
    return out


def validate_ranks(value, *, guild=None) -> list[dict]:
    """``[{role_id, min_points}]``, sorted, thresholds unique."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise TrialError("Ranks must be a list.")
    if len(value) > 40:
        raise TrialError("Too many ranks.")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise TrialError("Each rank must be an object.")
        try:
            role_id = int(item.get("role_id"))
            min_points = int(item.get("min_points"))
        except (TypeError, ValueError):
            raise TrialError("A rank threshold isn't a whole number.") from None
        if min_points < 0:
            raise TrialError("Rank thresholds can't be negative.")
        role = guild.get_role(role_id) if guild is not None else None
        if guild is not None and role is None:
            raise TrialError("A rank role isn't in this server.")
        out.append({"role_id": role_id, "min_points": min_points,
                    "name": item.get("name") or (role.name if role else str(role_id))})
    out.sort(key=lambda rank: rank["min_points"])
    thresholds = [rank["min_points"] for rank in out]
    if len(set(thresholds)) != len(thresholds):
        raise TrialError("Two ranks share the same threshold — the ladder would be ambiguous.")
    role_ids = [rank["role_id"] for rank in out]
    if len(set(role_ids)) != len(role_ids):
        raise TrialError("The same role is used for two ranks.")
    return out


class TrialRankManager:
    """One trial-ranking setup per guild. ``bot.trial_ranks``."""

    def __init__(self, collection, standings_collection) -> None:
        self._col = collection
        self._standings = standings_collection
        self._cache: dict[int, dict] = {}

    def get(self, guild_id: int) -> dict:
        guild_id = int(guild_id)
        if guild_id not in self._cache:
            doc = self._col.find_one({"_id": guild_id}) or {}
            self._cache[guild_id] = {
                "enabled": doc.get("enabled", False),
                "points": doc.get("points") or {},
                "ranks": doc.get("ranks") or [],
                "exclusive": doc.get("exclusive", True),
            }
        return self._cache[guild_id]

    def save(self, guild_id: int, data: dict) -> None:
        fields = {key: data[key] for key in ("points", "ranks", "enabled", "exclusive") if key in data}
        if not fields:
            return
        fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
        self._col.update_one({"_id": int(guild_id)}, {"$set": fields}, upsert=True)
        self._cache.pop(int(guild_id), None)

    # ---- standings, for the stats view ----
    def save_standing(self, guild_id: int, user_id: int, name: str, score: int, rank: Optional[str]) -> None:
        self._standings.update_one(
            {"guild_id": int(guild_id), "user_id": int(user_id)},
            {"$set": {"name": name, "score": int(score), "rank": rank,
                      "at": datetime.datetime.now(datetime.timezone.utc)}},
            upsert=True,
        )

    def standings(self, guild_id: int, limit: int = 100) -> list[dict]:
        return list(
            self._standings.find({"guild_id": int(guild_id)}).sort("score", -1).limit(limit)
        )
