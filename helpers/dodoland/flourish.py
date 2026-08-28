"""
Flourish — what a trial rank does to a town, and nothing else.

This is the second of DodoLand's two axes, and the only place the two meet:

* **Structure tier** is what you built. It comes from DodoLand standing, and
  every building is reachable by anyone through ordinary sociable activity.
  Nobody is locked out of a barracks for not raiding.
* **Flourish** is what you are known for. It comes from the trial ladder, it is
  cosmetic, and it cannot be ground for.

So a chatty non-raider and a Godslayer can own the same building, and only one
of them has it wreathed in fire. That split is the point: it makes the scarce
thing purely visual, which costs nothing to grant and cannot distort the
economy, while leaving the buildings themselves open to everybody.

**Strictly read-only, and trial ranks is the only outside thing DodoLand reads.**
Nothing here writes to `TrialRanks`, `TrialStandings` or anything else that
belongs to the ladder, and no DodoLand number is ever fed back into it. The
dependency is one-directional on purpose: the trial system has its own doc, its
own tests and its own rollout, and it must not acquire a second consumer that
can change its data.

The rank ladder is already free-form (a rung is a role, a threshold, an optional
description and a badge), so flourish is derived from a rung's **position** in
that ladder rather than from any hardcoded rank name. Rename the roles, add a
rung, delete one: the effects redistribute and nothing here needs editing.
"""

from __future__ import annotations

from typing import Optional

# Effect levels, weakest to strongest. Deliberately few: these are meant to read
# instantly at a glance on a map with forty towns on it, and eight levels of
# glow are indistinguishable from six.
LEVELS: tuple[dict, ...] = (
    {"key": "none", "label": "No flourish",
     "description": "An ordinary town. Most towns, most of the time."},
    {"key": "lantern", "label": "Lantern-lit",
     "description": "A warm light in the windows after dark."},
    {"key": "banner", "label": "Bannered",
     "description": "The rank's colours fly over the town centre."},
    {"key": "gilded", "label": "Gilded",
     "description": "Gold edging picks out every roofline."},
    {"key": "aura", "label": "Aura",
     "description": "A soft coloured glow rests over the whole settlement."},
    {"key": "radiant", "label": "Radiant",
     "description": "The glow pulses slowly, and the town is visible from across the map."},
    {"key": "ascendant", "label": "Ascendant",
     "description": "Light moves. The rarest thing on the map, and it should stay that way."},
)
BY_KEY = {level["key"]: level for level in LEVELS}
MAX_LEVEL = len(LEVELS) - 1


def level_for_rung(index: Optional[int], total: int) -> int:
    """Which effect level a rung of the trial ladder earns.

    ``index`` is the rung's position, cheapest first, or ``None`` for somebody
    who has not reached the first rung. Effects are spread across whatever
    ladder the server actually has, so the top rung always gets the strongest
    effect and the bottom one always gets something, however many rungs exist.

    Spreading rather than mapping by name is what keeps this free of the trial
    system's content: a server that renames its ranks, adds one or removes one
    gets a sensible redistribution and never a broken lookup.
    """
    if index is None or total <= 0:
        return 0
    if total == 1:
        return MAX_LEVEL
    # Rung 0 lands on level 1 (something), the last rung on MAX_LEVEL.
    span = MAX_LEVEL - 1
    return 1 + int(round(span * (min(index, total - 1) / (total - 1))))


BLANK: dict = {"level": 0, "rank_name": None, "role_id": 0, **BY_KEY["none"]}


def flourish_map(bot, guild_id: int) -> dict[int, dict]:
    """``{user_id: flourish}`` for everyone the trial ladder has ranked.

    Built from **one** read of the trial standings rather than a lookup per
    person, because the DodoLand page renders a whole server at once. Anybody
    absent from the result simply has no flourish, which is a plain town and a
    perfectly good one.

    The scores it reads are the trial system's *stored* standings, so they are
    as fresh as that person's last recalculation. That is deliberate: computing
    them live would mean reaching into the trial cog's scoring path, and this
    module is only allowed to read. A town whose glow is a day behind its owner's
    latest clear is a much smaller problem than DodoLand acquiring the ability to
    move somebody's rank.

    Any failure at all returns an empty map. A missing flourish must never be an
    error on a page.
    """
    try:
        from helpers import trial_ranks as trial_rules

        config = bot.trial_ranks.get(guild_id)
        ranks = trial_rules.ordered_ranks(config.get("ranks") or [])
        if not ranks:
            return {}

        guild = bot.get_guild(int(guild_id))
        positions = {int(rung.get("role_id") or 0): index
                     for index, rung in enumerate(ranks)}

        out: dict[int, dict] = {}
        for row in bot.trial_ranks.standings(guild_id, limit=10000) or ():
            user_id = int(row.get("user_id") or 0)
            if not user_id:
                continue
            current = trial_rules.rank_for(int(row.get("score") or 0), ranks)
            if current is None:
                continue
            role_id = int(current.get("role_id") or 0)
            level = level_for_rung(positions.get(role_id), len(ranks))
            role = guild.get_role(role_id) if guild and role_id else None
            out[user_id] = {
                "level": level,
                "rank_name": role.name if role else (current.get("name") or None),
                "role_id": role_id,
                **LEVELS[level],
            }
        return out
    except Exception:
        # Never let the trial system's shape, or its absence, break a town.
        return {}


def flourish_for(bot, guild_id: int, user_id: int) -> dict:
    """One person's flourish. Convenience over :func:`flourish_map`."""
    return flourish_map(bot, guild_id).get(int(user_id), dict(BLANK))
