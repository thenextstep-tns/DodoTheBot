"""
Placing towns on the map, and deciding how each one is drawn.

Everything here is pure: coordinates in, coordinates out, no Discord and no
Mongo. That is what lets the placement be tested against a known graph rather
than eyeballed on a live server.

Why placement is graph-driven
-----------------------------

The obvious design is to let people click an empty coordinate, and that is still
what settling does. But on a server this size an empty continent stays empty:
towns land far apart, nobody is anybody's neighbour, and every mechanic that
depends on adjacency never fires. The original plan made this worse by growing
the canvas with the population, which pins density at "too sparse" forever.

So an unsettled town is **suggested next to the people its owner actually talks
to**, using the pair rows the listener already writes. The map then stops being
a scatter of dots and becomes a picture of the server: clusters are friend
groups, and the person bridging two clusters is visibly the person bridging two
friend groups. That is a screenshot somebody posts unprompted, which is the
entire point of a socialite feature.

A suggestion is never binding. Anybody who settles somewhere keeps that spot
forever, and the suggestion only ever fills in for people who have not chosen.

Coordinates are percentages of the base image, never pixels, so replacing the
map with a redrawn one of a different size does not move a single town.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

# Towns are kept off the very edge so a marker and its label stay on the image.
MARGIN = 6.0
# How close two towns may sit before one is nudged away, in percentage points.
MIN_GAP = 4.5
# Golden angle, for the fallback spiral. It is the standard way to scatter points
# that have no relationship without them landing in visible rows.
_GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _clamp(value: float) -> float:
    return max(MARGIN, min(100.0 - MARGIN, float(value)))


def _distance(one: tuple[float, float], two: tuple[float, float]) -> float:
    return math.hypot(one[0] - two[0], one[1] - two[1])


def _spiral(index: int) -> tuple[float, float]:
    """A point on a golden-angle spiral from the centre, for the unconnected."""
    radius = (40.0 - MARGIN) * math.sqrt((index + 0.5) / 60.0)
    angle = index * _GOLDEN
    return _clamp(50.0 + radius * math.cos(angle)), _clamp(50.0 + radius * math.sin(angle))


def _nudge(spot: tuple[float, float], taken: list[tuple[float, float]]) -> tuple[float, float]:
    """Push a point away from anything too close, outward from the centre."""
    x, y = spot
    for _attempt in range(24):
        clash = next((other for other in taken if _distance((x, y), other) < MIN_GAP), None)
        if clash is None:
            return _clamp(x), _clamp(y)
        away = math.atan2(y - clash[1], x - clash[0]) if (x, y) != clash else _GOLDEN
        x = _clamp(x + MIN_GAP * math.cos(away))
        y = _clamp(y + MIN_GAP * math.sin(away))
    return _clamp(x), _clamp(y)


def place(people: Iterable[dict], partners: dict[int, dict[int, int]],
          settled: dict[int, dict]) -> dict[int, dict]:
    """Work out where every town goes.

    ``people`` are the standings rows (each with ``user_id`` and ``power``),
    ``partners`` is ``{user: {other: strength}}`` from the pair rows, and
    ``settled`` is ``{user: {"x", "y"}}`` for anybody who has chosen.

    Returns ``{user_id: {"x", "y", "settled": bool}}``. Settled towns come back
    untouched; everybody else is suggested beside the people they talk to most,
    and only falls back to the spiral when none of their contacts are placed.
    """
    positions: dict[int, dict] = {}
    taken: list[tuple[float, float]] = []

    for user_id, spot in settled.items():
        point = (_clamp(spot.get("x", 50)), _clamp(spot.get("y", 50)))
        positions[int(user_id)] = {"x": point[0], "y": point[1], "settled": True}
        taken.append(point)

    # Strongest towns first: they anchor the clusters everybody else hangs off,
    # and the order has to be deterministic or the map moves between reads.
    pending = sorted(
        (person for person in people if int(person["user_id"]) not in positions),
        key=lambda person: (-int(person.get("power", 0)), int(person["user_id"])),
    )

    for index, person in enumerate(pending):
        user_id = int(person["user_id"])
        neighbours = partners.get(user_id) or {}
        anchors = [(positions[other], weight) for other, weight in neighbours.items()
                   if other in positions]
        if anchors:
            total = sum(weight for _spot, weight in anchors) or 1
            x = sum(spot["x"] * weight for spot, weight in anchors) / total
            y = sum(spot["y"] * weight for spot, weight in anchors) / total
            # Sitting exactly on the centroid would stack everybody who shares a
            # friend group, so each town is offset onto its own point around it.
            angle = (user_id % 360) * math.pi / 180.0
            point = (x + MIN_GAP * math.cos(angle), y + MIN_GAP * math.sin(angle))
        else:
            point = _spiral(index)
        point = _nudge(point, taken)
        positions[user_id] = {"x": point[0], "y": point[1], "settled": False}
        taken.append(point)
    return positions


def marker_size(power: int, biggest: int) -> float:
    """How large a town is drawn, 1.0 to 3.0, on a square-root scale.

    Linear scaling makes the busiest person's town swallow the map; the root
    keeps a newcomer's town visible next to somebody with a year's head start,
    which matters because the map is meant to invite people in.
    """
    if power <= 0 or biggest <= 0:
        return 1.0
    return 1.0 + 2.0 * math.sqrt(min(1.0, power / biggest))


def towns(people: Iterable[dict], *, partners: dict[int, dict[int, int]],
          settled: dict[int, dict], flourish: dict[int, dict],
          names: Optional[dict[int, str]] = None,
          lit: Optional[set[int]] = None) -> list[dict]:
    """Everything needed to draw the map, one entry per town.

    ``lit`` is whoever has been active inside the recent window. A town not in it
    is drawn dim. That is the **only** thing dormancy ever costs anybody: no
    score is reduced, nothing is removed, and coming back lights it again.
    """
    rows = list(people)
    positions = place(rows, partners, settled)
    biggest = max((int(p.get("power", 0)) for p in rows), default=0)
    lit = lit if lit is not None else set()

    out = []
    for person in rows:
        user_id = int(person["user_id"])
        spot = positions.get(user_id) or {"x": 50.0, "y": 50.0, "settled": False}
        glow = flourish.get(user_id) or {}
        out.append({
            "user_id": user_id,
            "name": (names or {}).get(user_id, f"User {user_id}"),
            "x": round(spot["x"], 3),
            "y": round(spot["y"], 3),
            "settled": spot["settled"],
            "power": int(person.get("power", 0)),
            "size": round(marker_size(int(person.get("power", 0)), biggest), 3),
            "flourish": int(glow.get("level", 0)),
            "flourish_label": glow.get("label") or "",
            "rank_name": glow.get("rank_name") or "",
            "lit": user_id in lit,
            "tiers": {key: score.get("tier_title")
                      for key, score in (person.get("buildings") or {}).items()
                      if score.get("tier") is not None},
        })
    # Drawn weakest first so the biggest towns land on top rather than under.
    out.sort(key=lambda town: (town["power"], town["user_id"]))
    return out
