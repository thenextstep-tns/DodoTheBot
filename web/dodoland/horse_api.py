"""
The runaway horse.

One horse per server, loose somewhere near the towns. Click it and it bolts
(lang.py DODOLAND_HORSE_LINE, in the Strings menu) away from where you
clicked - click its left side and it runs off to the right - in a slightly
random direction. Run it into a zoo (a placed zoo building,
``dodoland_zoo_building``) and it turns into sweetrolls for that zoo's owner,
announced in the server's bot channel (its settings' Bot channel); then it is gone for a few hours, so it is a chase and
not a farm.

The server owns the horse: where it is, every bolt and every catch are worked
out here, so everybody sees the same horse and nobody can claim a catch the
horse never made. State lives on the server's DodoLand config row
(``horse``: {x, y, on, back_at}); positions are map percentages like
everything placed. Settings: ``dodoland_horse_*``.

Every other horse on the map (the ones walking the towns) can be chased too:
the page bolts it away from the click and, if its run passes a zoo, asks here
(POST {catch: {zoo, from, to}}); the run is checked (the zoo is real, the run
is no longer than a bolt and passes it) and paid like the runaway's. After any
catch the zoos take no more horses for the rest hours (``zoo_rest``), so the
towns' horses are not a farm either.

Endpoints: GET/POST ``/api/guild/{gid}/dodoland/horse`` (the panel's map) and
``.../dodoland/me/horse`` (a member's map); POST {x, y} is a kick from there.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from datetime import datetime

from aiohttp import web


def _p(bot, gid, key, default):
    try:
        return bot.dodoland_params.get(gid, key)
    except Exception:  # noqa: BLE001 - a setting added since startup
        return default


def _state(bot, gid) -> dict:
    return dict(bot.dodoland_buildings.config(gid).get("horse") or {})


def _save(bot, gid, state: dict) -> None:
    bot.dodoland_buildings._col.update_one({"_id": int(gid)}, {"$set": {"horse": state}}, upsert=True)
    bot.dodoland_buildings.invalidate(int(gid))


def _size(bot, gid) -> tuple[int, int]:
    world = bot.dodoland_terrain.world(gid)
    return max(1, int(world.get("cells_w") or 1)), max(1, int(world.get("cells_h") or 1))


def _wet(gid, cx: float, cy: float) -> bool:
    """Whether a cell is water, from the grid the town areas use (when built)."""
    from web.dodoland import influence_api

    grid = influence_api._WATER.get(int(gid))
    if grid is None:
        return False
    y, x = int(cy), int(cx)
    if y < 0 or x < 0 or y >= grid.shape[0] or x >= grid.shape[1]:
        return True
    return bool(grid[y, x])


def _spawn(bot, gid) -> dict | None:
    """A new horse, grazing a little way off a random town."""
    plots = list(bot.dodoland_buildings.plots(gid).values())
    if not plots:
        return None
    cw, ch = _size(bot, gid)
    for _ in range(40):
        town = random.choice(plots)
        a, d = random.uniform(0, 2 * math.pi), random.uniform(10, 26)
        cx = float(town["x"]) / 100 * cw + math.cos(a) * d
        cy = float(town["y"]) / 100 * ch + math.sin(a) * d
        if 2 <= cx < cw - 2 and 2 <= cy < ch - 2 and not _wet(gid, cx, cy):
            return {"x": round(cx / cw * 100, 4), "y": round(cy / ch * 100, 4), "on": True, "back_at": 0}
    return None


def _zoos(bot, gid) -> list[dict]:
    """Every placed zoo building: where it stands (cells), how big, whose."""
    key = str(_p(bot, gid, "dodoland_zoo_building", "menagerie"))
    cw, ch = _size(bot, gid)
    tiles = {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(gid)
             if (t.get("requires") or {}).get("building") == key}
    out = []
    for d in bot.dodoland_decor.world(gid):
        if d.get("asset_id") in tiles and d.get("town"):
            out.append({"id": d["piece_id"], "owner": str(d["town"]),
                        "x": float(d.get("x", 0)) / 100 * cw, "y": float(d.get("y", 0)) / 100 * ch,
                        "r": 5.0 * float(d.get("scale", 1.0))})
    return out


def _segment_gap(px, py, ax, ay, bx, by) -> float:
    """How near the run from a to b passes to p (cells)."""
    dx, dy = bx - ax, by - ay
    t = 0.0 if not (dx or dy) else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + dx * t - px, ay + dy * t - py)


def current(bot, gid) -> dict:
    """The horse as the page draws it; brought back once its rest is over."""
    if not bool(_p(bot, gid, "dodoland_horse_on", True)):
        return {"on": False}
    state = _state(bot, gid)
    if not state.get("on") and time.time() >= float(state.get("back_at") or 0):
        fresh = _spawn(bot, gid)
        if fresh:
            _save(bot, gid, fresh)
            state = fresh
    if not state.get("on"):
        return {"on": False, "back_in": max(0, int(float(state.get("back_at") or 0) - time.time()))}
    return {"on": True, "x": state["x"], "y": state["y"]}


def kick(bot, gid, fx: float, fy: float) -> dict:
    """The horse bolts away from (fx, fy), map percent. Blocking."""
    state = _state(bot, gid)
    if not state.get("on"):
        return {"on": False}
    cw, ch = _size(bot, gid)
    hx, hy = float(state["x"]) / 100 * cw, float(state["y"]) / 100 * ch
    px, py = float(fx) / 100 * cw, float(fy) / 100 * ch
    away = math.atan2(hy - py, hx - px) if (hx, hy) != (px, py) else random.uniform(0, 2 * math.pi)
    spread = math.radians(float(_p(bot, gid, "dodoland_horse_spread", 25)))
    lo = float(_p(bot, gid, "dodoland_horse_bolt_min", 6))
    hi = max(lo, float(_p(bot, gid, "dodoland_horse_bolt_max", 11)))
    # A few tries: the way it picks first may run into water or off the map.
    best = (hx, hy)
    for attempt in range(8):
        a = away + random.uniform(-spread, spread) * (1 + attempt * 0.4)
        dist, nx, ny = random.uniform(lo, hi), hx, hy
        for step in range(1, int(dist) + 1):
            tx, ty = hx + math.cos(a) * step, hy + math.sin(a) * step
            if not (1 <= tx < cw - 1 and 1 <= ty < ch - 1) or _wet(gid, tx, ty):
                break
            nx, ny = tx, ty
        if math.hypot(nx - hx, ny - hy) >= lo * 0.5:
            best = (nx, ny)
            break
        if math.hypot(nx - hx, ny - hy) > math.hypot(best[0] - hx, best[1] - hy):
            best = (nx, ny)
    nx, ny = best
    reach = float(_p(bot, gid, "dodoland_horse_catch", 2.0))
    caught = None
    resting = time.time() < float(state.get("zoo_rest") or 0)
    for zoo in ([] if resting else _zoos(bot, gid)):
        if _segment_gap(zoo["x"], zoo["y"], hx, hy, nx, ny) <= zoo["r"] + reach:
            caught = zoo
            nx, ny = zoo["x"], zoo["y"]
            break
    out = {"on": not caught, "x": round(nx / cw * 100, 4), "y": round(ny / ch * 100, 4),
           "from": {"x": state["x"], "y": state["y"]}}
    if caught:
        rest = random.uniform(float(_p(bot, gid, "dodoland_horse_rest_min_hours", 3)),
                              max(float(_p(bot, gid, "dodoland_horse_rest_min_hours", 3)),
                                  float(_p(bot, gid, "dodoland_horse_rest_max_hours", 6))))
        _save(bot, gid, {"on": False, "back_at": time.time() + rest * 3600, "zoo_rest": time.time() + rest * 3600})
        out["caught"] = {"zoo": caught["id"], "owner": caught["owner"]}
    else:
        _save(bot, gid, dict(state, on=True, x=out["x"], y=out["y"], back_at=0))
    return out


def catch(bot, gid, zoo_id: str, start: dict, end: dict) -> dict:
    """A town's horse run into a zoo by the page. Checked: the zoos are not
    resting, the zoo is a placed zoo, the run is no longer than a bolt can be
    and passes it. Blocking."""
    state = _state(bot, gid)
    if time.time() < float(state.get("zoo_rest") or 0):
        return {"refused": "full", "back_in": int(float(state["zoo_rest"]) - time.time())}
    zoo = next((z for z in _zoos(bot, gid) if z["id"] == str(zoo_id)), None)
    if zoo is None:
        return {"refused": "no zoo"}
    cw, ch = _size(bot, gid)
    try:
        ax, ay = float(start["x"]) / 100 * cw, float(start["y"]) / 100 * ch
        bx, by = float(end["x"]) / 100 * cw, float(end["y"]) / 100 * ch
    except (KeyError, TypeError, ValueError):
        return {"refused": "unreadable"}
    longest = float(_p(bot, gid, "dodoland_horse_bolt_max", 11)) * 1.6
    reach = float(_p(bot, gid, "dodoland_horse_catch", 2.0))
    if math.hypot(bx - ax, by - ay) > longest or _segment_gap(zoo["x"], zoo["y"], ax, ay, bx, by) > zoo["r"] + reach + 0.5:
        return {"refused": "missed"}
    lo = float(_p(bot, gid, "dodoland_horse_rest_min_hours", 3))
    rest = random.uniform(lo, max(lo, float(_p(bot, gid, "dodoland_horse_rest_max_hours", 6))))
    _save(bot, gid, dict(state, zoo_rest=time.time() + rest * 3600))
    return {"caught": {"zoo": zoo["id"], "owner": zoo["owner"]}}


def _pay(owner: int, catcher: int, count: int) -> None:
    """Sweetrolls, the way every other cog gives them: one row per roll."""
    import config_py

    now = datetime.now()
    if count > 0:
        config_py.sweetrolls.insert_many([{"gifted_to": int(owner), "gifter": int(catcher), "date": now,
                                           "source": "dodoland_horse"} for _ in range(count)])


async def _announce(bot, guild, catcher: int, owner: int, count: int) -> None:
    """The catch, in the server's bot channel (helpers/bot_channel.py), in the
    Strings menu's wording (lang.py DODOLAND_HORSE_CAUGHT)."""
    from helpers import bot_channel

    line = str(bot.lang.get("DODOLAND_HORSE_CAUGHT", guild=guild))
    await bot_channel.post(bot, guild, line.format(catcher=f"<@{int(catcher)}>", owner=f"<@{int(owner)}>", count=count))


async def api_horse(request: web.Request):
    """GET: where the horse is. POST {x, y}: a kick from there (map percent)."""
    bot, guild = request.app["bot"], request["guild"]
    loop = asyncio.get_running_loop()
    if request.method == "GET":
        return web.json_response({"ok": True, **await loop.run_in_executor(None, current, bot, guild.id)})
    try:
        body = await request.json()
        if body.get("catch"):
            c = body["catch"]
            out = await loop.run_in_executor(None, catch, bot, guild.id, str(c.get("zoo") or ""),
                                             c.get("from") or {}, c.get("to") or {})
        else:
            out = await loop.run_in_executor(None, kick, bot, guild.id, float(body.get("x")), float(body.get("y")))
    except (TypeError, ValueError, AttributeError):
        return web.json_response({"ok": False, "error": "Where was it kicked from?"}, status=400)
    caught = out.get("caught")
    if caught:
        catcher = int(request.get("uid") or 0)
        owner = int(caught["owner"]) if str(caught["owner"]).isdigit() else 0
        count = max(0, int(_p(bot, guild.id, "dodoland_horse_sweetrolls", 5)))
        if owner:
            await loop.run_in_executor(None, _pay, owner, catcher or owner, count)
            await _announce(bot, guild, catcher or owner, owner, count)
        out["sweetrolls"] = count
    return web.json_response({"ok": True, **out})
