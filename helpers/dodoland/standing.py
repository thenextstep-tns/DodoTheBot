"""
Scoring — from recorded acts to a building tier and a town's power.

Nothing here writes. It reads the day rows the listener produced and turns them
into the four numbers the panel asks for: what each building is worth, what tier
that reaches, what the whole town comes to, and where that puts somebody.

The arithmetic is deliberately shown rather than summarised. Every score comes
back with its own breakdown, because the one thing that makes a ladder trusted
is being able to point at where a number came from. That is why ``/rank`` is
believed and why an opaque "MMR" would not be.

    building points = sum over (channel, metric) of
        scored[channel][metric]
        x metric weight (server)
        x metric multiplier (this building)
        x channel weight (this building)

    town power = sum of building points
               + people reached x the partner weight

Buildings score from **channels**, because a building is a place. People reached
is channel-agnostic by nature (it is a property of who you talked to, not of
where), so it sits on the town rather than inside any one building.
"""

from __future__ import annotations

from typing import Iterable, Optional

from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import parameters as dodo_params


# --------------------------------------------------------------------------- #
#  One person, one building
# --------------------------------------------------------------------------- #
def building_score(channel_totals: dict, building: dict,
                   metric_weights: dict[str, int]) -> dict:
    """Points for one building, with the breakdown that produced them.

    ``channel_totals`` is ``{channel_id: {metric: scored count}}`` straight from
    the store. ``metric_weights`` is the server's weight per metric.
    """
    channels = {int(cid): float(weight)
                for cid, weight in (building.get("channels") or {}).items()}
    emphasis = building.get("metric_weights") or {}

    total = 0.0
    by_metric: dict[str, float] = {}
    by_channel: dict[int, float] = {}
    for channel_id, counts in (channel_totals or {}).items():
        channel_weight = channels.get(int(channel_id))
        if not channel_weight:
            continue  # this room does not feed this building
        for metric_key, count in (counts or {}).items():
            base = float(metric_weights.get(metric_key, 0))
            if not base:
                continue
            points = float(count) * base * float(emphasis.get(metric_key, 1.0)) * channel_weight
            if not points:
                continue
            total += points
            by_metric[metric_key] = by_metric.get(metric_key, 0.0) + points
            by_channel[int(channel_id)] = by_channel.get(int(channel_id), 0.0) + points

    return {
        "key": building.get("key"),
        "name": building.get("name"),
        "icon": building.get("icon"),
        "points": int(total),
        "by_metric": {k: int(v) for k, v in by_metric.items()},
        "by_channel": {k: int(v) for k, v in by_channel.items()},
    }


def metric_weights_for(params, guild_id: int) -> dict[str, int]:
    """The server's points-per-act for every metric, in one read."""
    return {metric.key: int(params.get(guild_id, dodo_params.weight_key(metric.key)))
            for metric in metric_registry.METRICS}


# --------------------------------------------------------------------------- #
#  Derived thresholds
# --------------------------------------------------------------------------- #
def percentile_of(values: list[int], percentile: float) -> int:
    """The value at a percentile of a sorted distribution.

    Nearest-rank, which is the definition that does not invent a threshold
    nobody actually scored. An empty distribution has no threshold at all, and
    the caller falls back to the tier's floor.
    """
    scores = sorted(int(v) for v in values if int(v) > 0)
    if not scores:
        return 0
    if percentile <= 0:
        return scores[0]
    if percentile >= 100:
        return scores[-1]
    rank = max(1, min(len(scores), int(-(-len(scores) * percentile // 100))))
    return scores[rank - 1]


def resolve_tiers(tiers: list[dict], distribution: list[int]) -> list[dict]:
    """Turn percentile tiers into the point thresholds they mean right now.

    Each tier's threshold is the higher of its percentile of the live
    distribution and its absolute floor. The floor is what keeps "top 5%" from
    being reachable with three messages on a server where four people have
    scored at all.

    Thresholds are then forced to be non-decreasing: a floor can otherwise lift
    an early tier above a later one on a young server, which would leave a rung
    that is harder than the rung above it.
    """
    out: list[dict] = []
    highest = 0
    for tier in tiers or ():
        derived = percentile_of(distribution, float(tier.get("percentile", 0)))
        threshold = max(int(derived), int(tier.get("floor", 0)), highest)
        highest = threshold
        out.append({
            "title": tier.get("title"),
            "percentile": tier.get("percentile"),
            "floor": int(tier.get("floor", 0)),
            "derived": int(derived),
            "threshold": threshold,
            # Which of the two decided it, so the panel can say so rather than
            # leaving somebody to work out why a number is not moving.
            "source": "floor" if int(tier.get("floor", 0)) >= int(derived) else "percentile",
        })
    return out


def tier_reached(points: int, resolved: list[dict]) -> Optional[int]:
    """Index of the highest tier a score reaches, or ``None`` for below tier 1."""
    reached = None
    for index, tier in enumerate(resolved or ()):
        if points >= tier["threshold"]:
            reached = index
    return reached


# --------------------------------------------------------------------------- #
#  A whole guild
# --------------------------------------------------------------------------- #
def matches_basis(row: dict, basis: str) -> bool:
    """Whether a row belongs to the history ``basis`` names.

    The same rule :func:`helpers.dodoland.store._basis_filter` expresses as a
    query, applied in memory. It exists so a caller can fetch every row once and
    then split it, rather than asking the database the same question twice.
    """
    source = row.get("source")
    if basis == "live":
        return source != "backfill"
    if basis == "backfill":
        return source == "backfill"
    return True


def guild_standings(store, params, guild_id: int, buildings: list[dict], *,
                    user_ids: Optional[Iterable[int]] = None,
                    since: Optional[str] = None, basis: str = "all",
                    rows: Optional[list[dict]] = None,
                    pair_rows: Optional[list[dict]] = None) -> dict:
    """Every scoring person's buildings, town power and place, in one pass.

    Aggregates in memory rather than querying per person: a ranking only exists
    relative to everybody else, so it has to be computed as a set. This is the
    same reasoning that shapes the tribe sweep.

    ``rows`` and ``pair_rows`` let a caller hand in day rows it has already
    fetched. The panel shows two bases of the same data and also draws a map
    from it; fetching per view meant eight scans of a 32,000-row collection on
    every page load, which is what made the page take seconds to open. Passing
    them in makes it one scan, split in memory.
    """
    weights = metric_weights_for(params, guild_id)
    partner_weight = int(params.get(guild_id, "dodoland_partner_weight"))
    partner_cap = int(params.get(guild_id, "dodoland_partner_daily_cap"))

    # {user: {channel: {metric: count}}}, built from one scan of the day rows.
    per_user: dict[int, dict[int, dict[str, int]]] = {}
    wanted = {int(u) for u in user_ids} if user_ids is not None else None
    day_rows = (rows if rows is not None
                else store.rows(guild_id, since=since, basis=basis))
    day_rows = [row for row in day_rows if matches_basis(row, basis)]
    for row in day_rows:
        user_id = int(row.get("user_id", 0))
        if not user_id or (wanted is not None and user_id not in wanted):
            continue
        bucket = per_user.setdefault(user_id, {})
        for channel_id, counts in (row.get("channels") or {}).items():
            target = bucket.setdefault(int(channel_id), {})
            for metric_key, count in (counts or {}).items():
                target[metric_key] = target.get(metric_key, 0) + int(count)

    # People reached, counted per day and capped the same way an act is.
    reach: dict[int, int] = {}
    pairs = (pair_rows if pair_rows is not None
             else store.pair_rows(guild_id, since=since, basis=basis))
    pairs = [row for row in pairs if matches_basis(row, basis)]
    for row in pairs:
        for user_id in (int(row.get("a", 0)), int(row.get("b", 0))):
            if user_id and (wanted is None or user_id in wanted):
                reach[user_id] = reach.get(user_id, 0) + 1
    if partner_cap > 0:
        # The cap is per day; the store cannot apply it because it does not know
        # the day's shape until the whole window is read.
        span = max(1, len({row.get("day") for row in day_rows}))
        reach = {user: min(count, partner_cap * span)
                 for user, count in reach.items()}

    people: dict[int, dict] = {}
    for user_id, channel_totals in per_user.items():
        scores = [building_score(channel_totals, building, weights)
                  for building in buildings]
        reached = reach.get(user_id, 0)
        reach_points = reached * partner_weight
        people[user_id] = {
            "user_id": user_id,
            "buildings": {score["key"]: score for score in scores},
            "reached": reached,
            "reach_points": reach_points,
            "power": sum(score["points"] for score in scores) + reach_points,
        }

    # Anybody with pair rows but no channel-attributed acts still has a town.
    for user_id, reached in reach.items():
        if user_id in people:
            continue
        reach_points = reached * partner_weight
        people[user_id] = {
            "user_id": user_id,
            "buildings": {b["key"]: building_score({}, b, weights) for b in buildings},
            "reached": reached, "reach_points": reach_points, "power": reach_points,
        }

    # Tiers, resolved per building from that building's live distribution.
    resolved: dict[str, list[dict]] = {}
    for building in buildings:
        key = building["key"]
        distribution = [person["buildings"][key]["points"] for person in people.values()]
        resolved[key] = resolve_tiers(building.get("tiers") or [], distribution)

    for person in people.values():
        for key, score in person["buildings"].items():
            score["tier"] = tier_reached(score["points"], resolved.get(key, []))
            score["tier_title"] = (
                resolved[key][score["tier"]]["title"]
                if score["tier"] is not None and resolved.get(key) else None
            )

    # Ties break on user id so a place is stable between two reads that saw the
    # same numbers, the same way the trial board numbers its rows.
    order = sorted(people.values(), key=lambda p: (-p["power"], p["user_id"]))
    for place, person in enumerate(order, start=1):
        person["place"] = place

    return {
        "basis": basis,
        "people": people,
        "order": order,
        "tiers": resolved,
        "weights": weights,
        "partner_weight": partner_weight,
    }
