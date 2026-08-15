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
#  Trial clear roles — one role per person per trial
# --------------------------------------------------------------------------- #
# A trial's roles are a ladder of their own, mapped by hand rather than guessed
# from names (names lie: "vKAᴴᴹ" and "vKA Vrolᴴᴹ" look alike and mean very
# different things). Each trial has up to six slots, weakest to strongest:
SLOTS = ("veteran", "partial1", "partial2", "full_hm", "trifecta", "extra")
SLOT_LABELS = {
    "veteran": "Veteran clear",
    "partial1": "Partial HM 1",
    "partial2": "Partial HM 2",
    "full_hm": "Full hardmode",
    "trifecta": "Trifecta",
    "extra": "Extra achievement",
}
SLOT_INDEX = {slot: index for index, slot in enumerate(SLOTS)}
# "Extra" sits outside the chain on purpose: it's worth points of its own but
# doesn't replace anything, and nothing replaces it. Everything else is a strict
# progression where the strongest held role is the only one kept.
SUPERSEDING_SLOTS = tuple(slot for slot in SLOTS if slot != "extra")

# Any slot may be empty — a trial without a second partial simply doesn't have
# one, and the rest keep their order. Holding a stronger role means the weaker
# ones are already implied, so exactly one of them is kept: the strongest.


def validate_trials(value, *, guild=None) -> list[dict]:
    """``[{name, slots: {slot: role_id}}]`` — the mapped lineups."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise TrialError("Trials must be a list.")
    if len(value) > 60:
        raise TrialError("Too many trials.")
    out, seen_roles = [], {}
    for item in value:
        if not isinstance(item, dict):
            raise TrialError("Each trial must be an object.")
        name = str(item.get("name") or "").strip()[:60]
        slots = {}
        raw_slots = item.get("slots") or {}
        if not isinstance(raw_slots, dict):
            raise TrialError("A trial's slots must be an object.")
        for slot, role_id in raw_slots.items():
            if slot not in SLOT_INDEX:
                raise TrialError(f"Unknown slot '{slot}'.")
            if not role_id:
                continue
            try:
                role_id = int(role_id)
            except (TypeError, ValueError):
                raise TrialError(f"The {SLOT_LABELS[slot]} role isn't a valid id.") from None
            if guild is not None and guild.get_role(role_id) is None:
                raise TrialError(f"The {SLOT_LABELS[slot]} role for '{name or 'a trial'}' "
                                 "isn't in this server.")
            # The same role may fill two slots of ONE trial (a server whose
            # trifecta role is also its extra achievement is common) — it still
            # scores once. Across two different trials it's a mistake, because
            # then "which trial does this clear belong to" has no answer.
            owner = seen_roles.get(role_id)
            if owner is not None and owner != (name or "a trial"):
                raise TrialError(f"A role is mapped to two different trials "
                                 f"('{owner}' and '{name or 'a trial'}').")
            seen_roles[role_id] = name or "a trial"
            slots[slot] = role_id
        if not slots:
            continue  # an empty lineup isn't a trial
        if not name:
            raise TrialError("Every mapped trial needs a name.")
        out.append({"name": name, "slots": slots})
    return out


def slot_of(trials: list[dict]) -> dict[int, tuple[int, int]]:
    """``role_id -> (trial index, slot index)`` for fast look-ups while scoring."""
    mapping = {}
    for trial_index, trial in enumerate(trials or []):
        for slot, role_id in (trial.get("slots") or {}).items():
            role_id = int(role_id)
            existing = mapping.get(role_id)
            # A role in two slots of one trial keeps its strongest SUPERSEDING
            # slot, so pointing trifecta and extra at the same role behaves as
            # the trifecta (and still scores once).
            if existing is None or (slot != "extra" and existing[1] == SLOT_INDEX["extra"]):
                mapping[role_id] = (trial_index, SLOT_INDEX[slot])
            elif slot != "extra" and SLOT_INDEX[slot] > existing[1]:
                mapping[role_id] = (trial_index, SLOT_INDEX[slot])
    return mapping


def superseded(role_ids: Iterable[int], trials: list[dict]) -> set[int]:
    """Roles a member holds that a stronger role in the same trial replaces.

    This is what "one role per person per trial" means in practice: hold the
    trifecta and the full hardmode, the partials and the veteran clear all fall
    away. Returns only roles the member actually has.
    """
    held = set(role_ids or ())
    mapping = slot_of(trials)
    extra_index = SLOT_INDEX["extra"]
    # An "extra" role is never dropped and never causes a drop — it's additional
    # credit, not a higher rung.
    extras = {role_id for role_id, (_t, slot) in mapping.items() if slot == extra_index}
    best: dict[int, int] = {}
    for role_id in held:
        found = mapping.get(role_id)
        if found and role_id not in extras:
            trial_index, slot_index = found
            best[trial_index] = max(best.get(trial_index, -1), slot_index)
    drop = set()
    for role_id in held:
        found = mapping.get(role_id)
        if found and role_id not in extras and found[1] < best[found[0]]:
            drop.add(role_id)
    return drop


def kept_roles(role_ids: Iterable[int], trials: list[dict]) -> set[int]:
    """What's left after the weaker roles of each trial are dropped."""
    held = set(role_ids or ())
    return held - superseded(held, trials)


def suggest_trials(guild) -> list[dict]:
    """A starting point built from role names, for review — never applied blind.

    Names are a decent hint even though they're a bad rule, so this fills the
    veteran / partial / full-hardmode slots and leaves you to correct it.
    Trifectas can't be guessed (nothing in "Dawnbringer" says Kyne's Aegis), so
    those slots stay empty.
    """
    grouped: dict[str, dict] = {}
    for role in sections(guild)["clears"]:
        folded = role.name.translate(_SUPERSCRIPT).strip()
        # Take the hardmode marker off FIRST: otherwise "vKAHM" reads as a trial
        # called "KAHM" instead of Kyne's Aegis on hardmode.
        is_hm = bool(re.search(r"\(?\s*hm\s*\)?\s*$", folded, re.I))
        without_hm = re.sub(r"\(?\s*hm\s*\)?\s*$", "", folded, flags=re.I).strip()
        match = re.match(r"^v\s*([A-Za-z]{2,4})(.*)$", without_hm)
        if not match:
            continue
        code = match.group(1).upper()
        rest = match.group(2).strip(" +()-")
        entry = grouped.setdefault(code, {"name": f"v{code}", "slots": {}, "_partials": []})
        if is_hm and not rest:
            entry["slots"]["full_hm"] = role.id          # vKAᴴᴹ
        elif not is_hm and (not rest or rest == "0"):
            entry["slots"]["veteran"] = role.id          # vKA, vAS+0
        else:
            entry["_partials"].append(role.id)           # vKA Vrolᴴᴹ, vCR+1
    out = []
    for entry in grouped.values():
        partials = entry.pop("_partials")
        for slot, role_id in zip(("partial1", "partial2"), partials):
            entry["slots"][slot] = role_id
        if entry["slots"]:
            out.append(entry)
    return sorted(out, key=lambda trial: trial["name"])


# --------------------------------------------------------------------------- #
#  Scoring
# --------------------------------------------------------------------------- #
def score_for(role_ids: Iterable[int], points: dict, *, trials: list[dict] = None, guild=None) -> int:
    """Sum the points of the scoring roles a member holds.

    With ``trials`` mapped, each trial contributes once — its strongest held
    role — so a trifecta doesn't also pay for the hardmode and partials it
    already implies.
    """
    return sum(row["points"] for row in _counted(role_ids, points, trials=trials))


def _counted(role_ids: Iterable[int], points: dict, *, trials: list[dict] = None) -> list[dict]:
    """The rows that actually score, after each trial is reduced to one role."""
    held = kept_roles(role_ids, trials) if trials else set(role_ids or ())
    rows = []
    for role_id, value in (points or {}).items():
        role_id = int(role_id)
        if role_id in held:
            rows.append({"role_id": role_id, "points": int(value)})
    return rows


def rank_for(score: int, ranks: list[dict]) -> Optional[dict]:
    """The best rung this score reaches — by ladder position, not by threshold.

    Ordering off the ladder rather than the numbers means Myth beats Legend
    because it *is* higher, not because someone typed a bigger threshold.
    """
    reached = [rank for rank in ranks or () if score >= rank["min_points"]]
    if not reached:
        return None
    return max(reached, key=lambda rank: LADDER_INDEX.get(rank.get("tier"), -1))


def breakdown_for(guild, role_ids: Iterable[int], points: dict, trials: list[dict] = None) -> list[dict]:
    """Which roles produced a score, and which a stronger clear replaced.

    Replaced rows are returned too (``counted: False``) so a preview can explain
    a total rather than assert it.
    """
    held = set(role_ids or ())
    counted = {row["role_id"] for row in _counted(held, points, trials=trials)}
    rows = []
    for role_id, value in (points or {}).items():
        role_id = int(role_id)
        if role_id not in held:
            continue
        role = guild.get_role(role_id)
        rows.append({"role_id": role_id, "name": role.name if role else str(role_id),
                     "points": int(value), "counted": role_id in counted})
    rows.sort(key=lambda row: (not row["counted"], -row["points"], row["name"]))
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
                "trials": doc.get("trials") or [],
                "exclusive": doc.get("exclusive", True),
            }
        return self._cache[guild_id]

    def save(self, guild_id: int, data: dict) -> None:
        fields = {key: data[key]
                  for key in ("points", "ranks", "trials", "enabled", "exclusive") if key in data}
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
