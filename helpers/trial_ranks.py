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
# The ladder is fixed and ordered — worst to best. Ranks aren't whatever roles
# happen to sit under a divider (that section also holds Tank/Healer/DD and
# other non-rank roles); they're these seven rungs, each mapped to a role of
# your choosing. Order is what lets "keep only the coolest rank" mean anything.
LADDER = ("Casual", "Raider", "Veteran", "Expert", "Master", "Legend", "Myth")
LADDER_INDEX = {name: index for index, name in enumerate(LADDER)}

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
#  Default point values
# --------------------------------------------------------------------------- #
# The values ESO for Dodos arrived at, keyed by role name so they apply to any
# server using the same trial names. Matching ignores case, spacing, punctuation
# and superscript HM, so "vRG Bahsei(HM)", "vRG Bahseiᴴᴹ" and "vrg bahsei hm"
# all land on the same entry. These only ever pre-fill an empty box — a value
# you have set is never overwritten.
DEFAULT_POINTS_BY_NAME: dict[str, int] = {
    # --- clears: base ---
    "vAA": 1, "vHRC": 2, "vSO": 3, "vMoL": 4, "vHoF": 5, "vAS+0": 2, "vCR+0": 4,
    "vSS": 4, "vKA": 4, "vRG": 5, "vDSR": 6, "vSE": 5, "vLC": 5, "vOC": 6,
    # --- clears: hardmode / partial ---
    "vAA HM": 2, "vHRC HM": 4, "vSO HM": 4, "vMoL HM": 6, "vHoF HM": 6,
    "vAS+Llothis": 3, "vAS+Felms": 3, "vAS+2": 15,
    "vCR+1": 5, "vCR+2": 8, "vCR+3": 15,
    "vSS Lokke HM": 7, "vSS Yolna HM": 5, "vSS HM": 15,
    "vKA Yandir HM": 5, "vKA Vrol HM": 5, "vKA HM": 15,
    "vRG Oaxiltso HM": 8, "vRG Bahsei HM": 15, "vRG HM": 25,
    "vDSR Turlassil & Lylanar HM": 12, "vDSR Reef Guardian HM": 12, "vDSR HM": 27,
    "vSE Yaseyla HM": 10, "vSE Chimera HM": 10, "vSE HM": 25,
    "vLC Count HM": 10, "vLC Orphic HM": 10, "vLC HM": 25,
    "vOC Shapers of Flesh HM": 10, "vOC Jynorah & Skorkhif HM": 15, "vOC HM": 30,
    # --- achievements ---
    "Master Angler": 20, "Opulent Ordeal ND": 25, "Misery's Master": 55,
    "Unstoppable": 50, "Mindmender": 45, "Soul of the Squall": 50,
    "Planesbreaker": 40, "Dawnbringer": 25, "Godslayer": 30, "Gryphon Heart": 20,
    "Immortal Redeemer": 20, "Tick-Tock Tormentor": 15, "The Unchained": 30,
    "Dro-m'Athra Destroyer": 10,
}

# Superscript letters Discord role names use for the HM suffix.
_SUPERSCRIPT = str.maketrans({"\u1d34": "H", "\u1d39": "M", "\u02b0": "h", "\u1d50": "m"})


def normalise_role_name(name: str) -> str:
    """Fold a role name to a comparable key: no case, spacing or punctuation."""
    folded = (name or "").translate(_SUPERSCRIPT).lower()
    return "".join(ch for ch in folded if ch.isalnum())


DEFAULT_POINTS: dict[str, int] = {
    normalise_role_name(name): points for name, points in DEFAULT_POINTS_BY_NAME.items()
}


def default_points_for(role) -> int:
    """The suggested value for a role, or 0 if we have no opinion about it."""
    return DEFAULT_POINTS.get(normalise_role_name(getattr(role, "name", "")), 0)


def with_defaults(guild, points: dict) -> dict:
    """Stored points, with suggestions filled in for roles that have none.

    Returns ``{role_id: (value, is_default)}`` so the panel can show a
    suggestion differently from a decision.
    """
    out = {}
    for role in scoring_roles(guild):
        stored = (points or {}).get(str(role.id))
        if stored:
            out[role.id] = (int(stored), False)
        else:
            suggested = default_points_for(role)
            if suggested:
                out[role.id] = (suggested, True)
    return out


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
    """The best rung this score reaches — by ladder position, not by threshold.

    Ordering off the ladder rather than the numbers means Myth beats Legend
    because it *is* higher, not because someone typed a bigger threshold.
    """
    reached = [rank for rank in ranks or () if score >= rank["min_points"]]
    if not reached:
        return None
    return max(reached, key=lambda rank: LADDER_INDEX.get(rank.get("tier"), -1))


def breakdown_for(guild, role_ids: Iterable[int], points: dict) -> list[dict]:
    """Which roles produced a member's score, biggest contribution first.

    This is what makes a weighting decision inspectable: not "142 points" but
    "vDSR 40 + vSE 40 + vKA 25 …".
    """
    held = set(role_ids or ())
    rows = []
    for role_id, value in (points or {}).items():
        role_id = int(role_id)
        if role_id not in held:
            continue
        role = guild.get_role(role_id)
        rows.append({"role_id": role_id, "name": role.name if role else str(role_id),
                     "points": int(value)})
    rows.sort(key=lambda row: (-row["points"], row["name"]))
    return rows


def find_members(guild, names: Iterable[str], *, limit: int = 10) -> list[dict]:
    """Resolve typed names to members: id, mention, exact, prefix, then substring.

    Returns one row per input so an unmatched name is reported rather than
    silently dropped — a typo shouldn't look like "this player scores zero".
    """
    members = [m for m in guild.members if not m.bot]
    out = []
    for raw in list(names)[:limit]:
        query = str(raw).strip()
        # People paste mentions and @names; treat them as the name they contain.
        if query.startswith("<@") and query.endswith(">"):
            query = query[2:-1].lstrip("!&")
        query = query.lstrip("@").strip()
        if not query:
            continue
        digits = "".join(ch for ch in query if ch.isdigit())
        member = None
        if digits and len(digits) >= 15:
            member = guild.get_member(int(digits))
        if member is None:
            lowered = query.lower()
            candidates = [
                next((m for m in members if m.display_name.lower() == lowered
                      or m.name.lower() == lowered), None),
                next((m for m in members if m.display_name.lower().startswith(lowered)
                      or m.name.lower().startswith(lowered)), None),
                next((m for m in members if lowered in m.display_name.lower()
                      or lowered in m.name.lower()), None),
            ]
            member = next((c for c in candidates if c is not None), None)
        out.append({"query": query, "member": member})
    return out


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
    """``[{tier, role_id, min_points}]`` for the rungs that are actually mapped.

    A rung with no role is simply unused. Thresholds must climb with the ladder:
    a Veteran who needs fewer points than a Raider is a setup mistake, not a
    preference, so it's rejected rather than silently producing a rank nobody
    can ever hold.
    """
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise TrialError("Ranks must be a list.")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise TrialError("Each rank must be an object.")
        tier = item.get("tier") or item.get("name")
        if tier not in LADDER_INDEX:
            raise TrialError(f"Unknown rank '{tier}'. The ladder is: {', '.join(LADDER)}.")
        if not item.get("role_id"):
            continue  # rung left unmapped — fine, it just isn't used
        try:
            role_id = int(item["role_id"])
            min_points = int(item.get("min_points") or 0)
        except (TypeError, ValueError):
            raise TrialError(f"The threshold for {tier} isn't a whole number.") from None
        if min_points < 0:
            raise TrialError(f"{tier} can't have a negative threshold.")
        if guild is not None and guild.get_role(role_id) is None:
            raise TrialError(f"The role for {tier} isn't in this server.")
        out.append({"tier": tier, "name": tier, "role_id": role_id, "min_points": min_points})

    seen_tiers = [rank["tier"] for rank in out]
    if len(set(seen_tiers)) != len(seen_tiers):
        raise TrialError("The same rank is listed twice.")
    role_ids = [rank["role_id"] for rank in out]
    if len(set(role_ids)) != len(role_ids):
        raise TrialError("Two ranks point at the same role.")

    out.sort(key=lambda rank: LADDER_INDEX[rank["tier"]])
    previous = None
    for rank in out:
        if previous is not None and rank["min_points"] <= previous["min_points"]:
            raise TrialError(
                f"{rank['tier']} needs more points than {previous['tier']} "
                f"({rank['min_points']} is not above {previous['min_points']})."
            )
        previous = rank
    return out


def ladder_rows(config: dict) -> list[dict]:
    """Every rung in ladder order, mapped or not — what the panel renders."""
    by_tier = {rank.get("tier"): rank for rank in config.get("ranks") or []}
    return [
        {"tier": tier,
         "role_id": (by_tier.get(tier) or {}).get("role_id", 0),
         "min_points": (by_tier.get(tier) or {}).get("min_points")}
        for tier in LADDER
    ]


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
