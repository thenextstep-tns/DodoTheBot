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

**The ladder is whatever roles you point at it.** A rung is a role, a points
threshold, an optional description and an optional picture — no fixed names, no
fixed number of rungs. Rungs are ordered by the points they require, so "higher"
means "costs more" and a server can call its ranks anything it likes.
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
# A rung's description and picture are for the /rank embed, not for scoring.
MAX_DESCRIPTION = 400
# Rank pictures are meant to be small badges, not screenshots.
MAX_IMAGE_BYTES = 512 * 1024

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


def ordered_ranks(ranks: list[dict]) -> list[dict]:
    """The rungs cheapest-first. Points are the only ordering there is."""
    return sorted(ranks or (), key=lambda rank: int(rank.get("min_points") or 0))


def rank_for(score: int, ranks: list[dict]) -> Optional[dict]:
    """The best rung this score reaches — the most expensive one paid for."""
    reached = [rank for rank in ranks or () if score >= int(rank.get("min_points") or 0)]
    if not reached:
        return None
    return max(reached, key=lambda rank: int(rank.get("min_points") or 0))


def next_rank_for(score: int, ranks: list[dict]) -> Optional[dict]:
    """The cheapest rung still out of reach, or ``None`` at the top."""
    ahead = [rank for rank in ranks or () if score < int(rank.get("min_points") or 0)]
    if not ahead:
        return None
    return min(ahead, key=lambda rank: int(rank.get("min_points") or 0))


def progress_for(score: int, ranks: list[dict]) -> dict:
    """Where a score sits between the rung it holds and the next one.

    ``fraction`` is 1.0 at the top of the ladder — someone who has finished
    isn't 0% of the way to nothing.
    """
    current = rank_for(score, ranks)
    upcoming = next_rank_for(score, ranks)
    floor = int((current or {}).get("min_points") or 0)
    if upcoming is None:
        return {"current": current, "next": None, "floor": floor, "ceiling": None,
                "needed": 0, "fraction": 1.0}
    ceiling = int(upcoming["min_points"])
    span = max(1, ceiling - floor)
    return {
        "current": current,
        "next": upcoming,
        "floor": floor,
        "ceiling": ceiling,
        "needed": max(0, ceiling - score),
        "fraction": min(1.0, max(0.0, (score - floor) / span)),
    }


def _held_slot_state(role_ids: Iterable[int], points: dict, trials: list[dict]) -> tuple[dict, dict]:
    """``(best slot per trial, points of the role filling it)`` for what's held."""
    mapping = slot_of(trials or [])
    extra_index = SLOT_INDEX["extra"]
    best: dict[int, int] = {}
    value_at: dict[int, int] = {}
    for role_id in role_ids or ():
        found = mapping.get(int(role_id))
        if not found or found[1] == extra_index:
            continue
        trial_index, slot_index = found
        if slot_index >= best.get(trial_index, -1):
            best[trial_index] = slot_index
            value_at[trial_index] = int((points or {}).get(str(int(role_id))) or 0)
    return best, value_at


def missing_for_next(guild, role_ids: Iterable[int], points: dict, ranks: list[dict],
                     *, trials: list[dict] = None, limit: int = 12) -> dict:
    """What this member could still earn, cheapest first, to reach the next rung.

    Marginal, not nominal: a full hardmode when you already hold the veteran
    clear is worth the *difference*, because a trial only ever pays once. Roles
    a stronger clear already implies are left out entirely — telling someone to
    go and get a clear they've outgrown is worse than saying nothing.
    """
    held = {int(role_id) for role_id in role_ids or ()}
    score = score_for(held, points, trials=trials)
    state = progress_for(score, ranks)
    steps: list[dict] = []
    if state["next"] is not None:
        mapping = slot_of(trials or [])
        extra_index = SLOT_INDEX["extra"]
        best, value_at = _held_slot_state(held, points, trials or [])
        for role_id, value in (points or {}).items():
            role_id, value = int(role_id), int(value)
            if role_id in held:
                continue
            role = guild.get_role(role_id) if guild else None
            if role is None:
                continue
            gain, replaces = value, None
            found = mapping.get(role_id)
            if found and found[1] != extra_index:
                trial_index, slot_index = found
                current_slot = best.get(trial_index)
                if current_slot is not None:
                    if slot_index < current_slot:
                        continue  # already implied by a stronger clear
                    gain = value - value_at.get(trial_index, 0)
                    replaces = trial_index
            if gain <= 0:
                continue
            steps.append({"role_id": role_id, "name": role.name, "points": value,
                          "gain": gain, "upgrade": replaces is not None,
                          "trial": found[0] if found else None})
        # Cheapest first, which is also roughly easiest first: the whole point is
        # to answer "what do I do next", not to list the whole board.
        steps.sort(key=lambda step: (step["gain"], step["name"].lower()))
        # One suggestion per trial. Two rungs of the same trial can't both be
        # earned on top of each other — only the stronger one ever pays — so
        # listing both would promise points that don't add up.
        seen_trials, unique = set(), []
        for step in steps:
            if step["trial"] is not None:
                if step["trial"] in seen_trials:
                    continue
                seen_trials.add(step["trial"])
            unique.append(step)
        running, chosen = 0, []
        for step in unique:
            # Keep going a little past the finish line: the cheapest route isn't
            # always the one they can actually run this week.
            if running >= state["needed"] and len(chosen) >= 3:
                break
            running += step["gain"]
            chosen.append(step)
        steps = chosen[:limit]
    return {**state, "score": score, "steps": steps}


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


def find_by_tag(guild, tag: str):
    """Resolve an exact Discord user tag to a member, or ``None``.

    Deliberately stricter than :func:`find_members`: enrolling somebody starts
    editing their roles, so a near-miss on a display name is not good enough.
    Only the account's own handle counts — ``name``, the legacy ``name#1234``,
    or a mention of it — never a nickname, and never a prefix.
    """
    query = str(tag or "").strip()
    if query.startswith("<@") and query.endswith(">"):
        query = query[2:-1].lstrip("!&")
    query = query.lstrip("@").strip()
    if not query:
        return None
    if query.isdigit() and len(query) >= 15:
        return guild.get_member(int(query))
    lowered = query.lower()
    for member in guild.members:
        if member.bot:
            continue
        if member.name.lower() == lowered:
            return member
        if f"{member.name}#{member.discriminator}".lower() == lowered:
            return member
        # Modern accounts report discriminator "0"; "name#0" shouldn't be the
        # only spelling that fails to match.
        if member.discriminator == "0" and lowered == f"{member.name.lower()}#0":
            return member
    return None


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


def rank_name(rank: dict, guild=None) -> str:
    """What to call a rung: the role's own name, falling back to a stored one.

    The role is the rank, so the server renames a rank by renaming the role and
    nothing here needs to know the word "Veteran".
    """
    role = guild.get_role(int(rank.get("role_id") or 0)) if guild else None
    return role.name if role is not None else (rank.get("name") or "Unmapped rank")


def validate_ranks(value, *, guild=None) -> list[dict]:
    """``[{role_id, min_points, description}]`` for the rungs actually mapped.

    A rung with no role is simply dropped. Two rungs may not want the same
    threshold — that would make "which rank does 40 points give" unanswerable —
    and the list is stored cheapest-first so ordering never depends on the
    caller. Names are deliberately *not* stored as the source of truth: the role
    is the rank, so renaming the role renames the rank.
    """
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
        if not item.get("role_id"):
            continue  # a row with no role picked yet isn't a rank
        try:
            role_id = int(item["role_id"])
            min_points = int(item.get("min_points") or 0)
        except (TypeError, ValueError):
            raise TrialError("A rank's threshold isn't a whole number.") from None
        role = guild.get_role(role_id) if guild is not None else None
        label = role.name if role is not None else str(role_id)
        if guild is not None and role is None:
            raise TrialError("A rank points at a role that isn't in this server.")
        if min_points < 0:
            raise TrialError(f"'{label}' can't have a negative threshold.")
        description = str(item.get("description") or "").strip()[:MAX_DESCRIPTION]
        out.append({"role_id": role_id, "min_points": min_points,
                    "name": label, "description": description})

    role_ids = [rank["role_id"] for rank in out]
    if len(set(role_ids)) != len(role_ids):
        raise TrialError("Two ranks point at the same role.")
    thresholds = [rank["min_points"] for rank in out]
    if len(set(thresholds)) != len(thresholds):
        duplicate = next(t for t in thresholds if thresholds.count(t) > 1)
        raise TrialError(f"Two ranks both start at {duplicate} points — "
                         "give them different thresholds.")
    return ordered_ranks(out)


def rank_rows(config: dict, guild=None) -> list[dict]:
    """The rungs as the panel renders them: cheapest first, names resolved."""
    return [
        {"role_id": int(rank.get("role_id") or 0),
         "min_points": int(rank.get("min_points") or 0),
         "description": rank.get("description") or "",
         "name": rank_name(rank, guild)}
        for rank in ordered_ranks(config.get("ranks") or [])
    ]


def _migrate_ranks(stored: list) -> list[dict]:
    """Read rungs saved before the ladder became free-form.

    Old documents carried a ``tier`` out of a fixed seven-name ladder. The role
    and the threshold were always the real content, so they're kept as-is and
    the tier is dropped — an existing server keeps working, and its ranks are
    now called whatever its roles are called.
    """
    out = []
    for rank in stored or []:
        if not isinstance(rank, dict) or not rank.get("role_id"):
            continue
        out.append({
            "role_id": int(rank["role_id"]),
            "min_points": int(rank.get("min_points") or 0),
            # The old tier name is a decent fallback label if the role is gone.
            "name": rank.get("name") or rank.get("tier") or "",
            "description": rank.get("description") or "",
        })
    return ordered_ranks(out)


# Where someone stands with the automated system, for the panel's conversion
# board. "prompted" is the passive state: they've seen the ask and not answered.
STATE_ENROLLED = "enrolled"
STATE_READ = "read"
STATE_DISMISSED = "dismissed"
STATE_PROMPTED = "prompted"


class TrialRankManager:
    """One trial-ranking setup per guild. ``bot.trial_ranks``."""

    def __init__(self, collection, standings_collection, *,
                 enrollment_collection=None, image_collection=None) -> None:
        self._col = collection
        self._standings = standings_collection
        self._enrollment = enrollment_collection
        self._images = image_collection
        self._cache: dict[int, dict] = {}
        self._enrolled_cache: dict[int, set[int]] = {}

    def get(self, guild_id: int) -> dict:
        guild_id = int(guild_id)
        if guild_id not in self._cache:
            doc = self._col.find_one({"_id": guild_id}) or {}
            self._cache[guild_id] = {
                "enabled": doc.get("enabled", False),
                "points": doc.get("points") or {},
                "ranks": _migrate_ranks(doc.get("ranks")),
                "trials": doc.get("trials") or [],
                "exclusive": doc.get("exclusive", True),
                "announce_channel_id": int(doc.get("announce_channel_id") or 0),
                "announce_message_id": int(doc.get("announce_message_id") or 0),
            }
        return self._cache[guild_id]

    def save(self, guild_id: int, data: dict) -> None:
        fields = {key: data[key] for key in
                  ("points", "ranks", "trials", "enabled", "exclusive",
                   "announce_channel_id", "announce_message_id") if key in data}
        if not fields:
            return
        fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
        self._col.update_one({"_id": int(guild_id)}, {"$set": fields}, upsert=True)
        self._cache.pop(int(guild_id), None)

    # ------------------------------------------------------------------ #
    #  Who the automation is allowed to touch
    # ------------------------------------------------------------------ #
    # Nobody is automated until they say so (or an admin enrols them by hand).
    # That's the whole safety story for the rollout: switching the feature on
    # cannot rewrite a single role by itself.
    def enrolled_ids(self, guild_id: int) -> set[int]:
        guild_id = int(guild_id)
        if guild_id not in self._enrolled_cache:
            if self._enrollment is None:
                self._enrolled_cache[guild_id] = set()
            else:
                self._enrolled_cache[guild_id] = {
                    int(doc["user_id"])
                    for doc in self._enrollment.find(
                        {"guild_id": guild_id, "state": STATE_ENROLLED}, {"user_id": 1})
                }
        return self._enrolled_cache[guild_id]

    def is_enrolled(self, guild_id: int, user_id: int) -> bool:
        return int(user_id) in self.enrolled_ids(guild_id)

    def set_state(self, guild_id: int, user_id: int, state: str, *,
                  name: str = "", source: str = "") -> None:
        """Record where someone is in the conversion, newest wins.

        Every stage is stamped separately rather than overwritten, so the board
        can say "23 read the explanation" even after those 23 went on to enrol.
        """
        if self._enrollment is None:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        fields = {"state": state, "at": now}
        if name:
            fields["name"] = name
        if source:
            fields["source"] = source
        fields[f"{state}_at"] = now
        self._enrollment.update_one(
            {"guild_id": int(guild_id), "user_id": int(user_id)},
            {"$set": fields, "$setOnInsert": {"first_seen": now}},
            upsert=True,
        )
        self._enrolled_cache.pop(int(guild_id), None)

    def forget(self, guild_id: int, user_id: int) -> None:
        """Take someone back off the automated system entirely."""
        if self._enrollment is None:
            return
        self._enrollment.delete_one({"guild_id": int(guild_id), "user_id": int(user_id)})
        self._enrolled_cache.pop(int(guild_id), None)

    def roster(self, guild_id: int, limit: int = 500) -> list[dict]:
        """Everyone the conversion has touched, whatever stage they reached."""
        if self._enrollment is None:
            return []
        return list(self._enrollment.find({"guild_id": int(guild_id)})
                    .sort("at", -1).limit(limit))

    # ------------------------------------------------------------------ #
    #  Rank pictures
    # ------------------------------------------------------------------ #
    def set_image(self, guild_id: int, role_id: int, data: bytes, content_type: str) -> None:
        if self._images is None:
            return
        self._images.update_one(
            {"guild_id": int(guild_id), "role_id": int(role_id)},
            {"$set": {"data": data, "content_type": content_type,
                      "at": datetime.datetime.now(datetime.timezone.utc)}},
            upsert=True,
        )

    def image(self, guild_id: int, role_id: int) -> Optional[dict]:
        if self._images is None:
            return None
        return self._images.find_one({"guild_id": int(guild_id), "role_id": int(role_id)})

    def image_role_ids(self, guild_id: int) -> set[int]:
        """Which rungs have a picture — enough to render the panel without
        pulling every blob out of the database on page load."""
        if self._images is None:
            return set()
        return {int(doc["role_id"]) for doc in
                self._images.find({"guild_id": int(guild_id)}, {"role_id": 1})}

    def clear_image(self, guild_id: int, role_id: int) -> None:
        if self._images is None:
            return
        self._images.delete_one({"guild_id": int(guild_id), "role_id": int(role_id)})

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
