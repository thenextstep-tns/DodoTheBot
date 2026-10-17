"""
The map view: the map, and almost nothing else.

A map squeezed into a panel section between a settings form and a table is not a
map, it is a thumbnail. This page gives it the screen: the world fills the
window, and everything else is a drawer over the top of it.

Three decisions this page is built around.

**Only placed towns appear.** Nothing is auto-scattered here. A town exists on
the map because somebody put it there, so the map starts empty and fills up
deliberately. The graph-driven suggestion still exists in
``helpers/dodoland/mapview.py`` and is not used by this page; a map that placed
three hundred towns for you is a map you cannot curate, and curating it is the
point of building one by hand.

**A town is drawn from what stands in it.** Not a dot: the buildings that person
has actually reached a tier in, each drawn as its own kind — an inn, a hall, a
keep, a chapel — and each grown by its tier. A settlement with a library, a
bakery and a forge looks like a different place from one with barracks and a war
room, which is the whole reason buildings were worth having.

**Clicking a town opens it.** Standing, place, flourish, every building and its
tier, and the coordinates. A map you cannot interrogate is wallpaper.

**Detail arrives with the zoom.** Only towns inside the visible rectangle get a
DOM node at all, and their artwork is fetched the first time they are close
enough to be worth drawing. Shipping three hundred pre-rendered settlements and
hiding most of them with CSS costs the whole payload and the whole parse for the
handful anybody can actually see. Because of that this can afford as much
detail per building as it likes: what is on screen at high zoom is a few towns,
not the server.

Nothing is loaded from anywhere else. The towns are shapes this repository draws
and the few controls are ordinary characters, so the page renders identically on
a machine with no network at all. An icon font was tried first and dropped: it
could not express a tier, and pulling in a CDN for four buttons was not a trade
worth making.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json

from aiohttp import web

from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import standing
from helpers.dodoland import tiles as tile_rules
from helpers.dodoland import terrainart
from helpers.dodoland import townart
from helpers.dodoland import towns as town_rules
from helpers.dodoland import store as store_module
from web.dodoland import forest_ui, nightlights, terrain_ui, theme


def _e(value) -> str:
    return html.escape(str(value))


def _name_of(guild, bot, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    if member is not None:
        return member.display_name
    user = bot.get_user(int(user_id))
    return user.name if user is not None else f"User {user_id}"


def _grown(power: int, biggest: int) -> float:
    """How far up the size curve a town sits, 0 to 1."""
    if power <= 0 or biggest <= 0:
        return 0.0
    return min(1.0, (power / biggest) ** 0.5)


def _avatar_of(guild, user_id) -> str:
    """A member's own picture (Discord's, small), or ""."""
    member = guild.get_member(int(user_id)) if str(user_id).isdigit() else None
    try:
        return str(member.display_avatar.with_size(64).url) if member is not None else ""
    except Exception:  # noqa: BLE001
        return ""






def _rooms_of(guild, building: dict) -> list[str]:
    """The channels that build one building, named the way Discord names them."""
    out = []
    for channel_id in (building.get("channels") or {}):
        channel = guild.get_channel(int(channel_id))
        if channel is None and hasattr(guild, "get_thread"):
            channel = guild.get_thread(int(channel_id))
        out.append(f"#{channel.name}" if channel is not None
                   else f"#{channel_id}")
    return sorted(out)


def _collect(bot, guild) -> dict:
    """Everything the page needs, in one pass. Blocking; call in an executor."""
    buildings = bot.dodoland_buildings.buildings(guild.id)
    rooms = {b["key"]: _rooms_of(guild, b) for b in buildings}
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)
    lit_since = store_module.days_back(
        int(bot.dodoland_params.get(guild.id, "dodoland_lit_days")))

    rows, pairs = standing.recent_rows(bot.dodoland, bot.dodoland_params, guild.id, since)
    # Shared with every other reader of the same rows (cached, read-only).
    result = standing.recent_standings(bot.dodoland, bot.dodoland_params, guild.id,
                                       buildings, since)
    glow = flourish_rules.flourish_map(bot, guild.id)
    plots = bot.dodoland_buildings.plots(guild.id)
    lit = {int(row.get("user_id", 0)) for row in rows
           if str(row.get("day") or "") >= lit_since}

    details = bot.dodoland_towns.all(guild.id)
    # The toolkit's output: what an admin has put on the map, and what each
    # person has put around their own town. One read each rather than one per
    # settlement.
    world_decor = bot.dodoland_decor.world(guild.id)
    town_decor = bot.dodoland_decor.towns(guild.id)
    base_pct = float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct"))
    growth = max(1.0, float(bot.dodoland_params.get(guild.id, "dodoland_town_growth")))
    biggest = max((p["power"] for p in result["order"]), default=0)
    # Drawn as halls, every town is one small building at the same size, and
    # the influence layer is what grows; drawn classic, the town itself grows.
    halls = str(bot.dodoland_params.get(guild.id, "dodoland_town_style")) == "hall"
    hall_cells = float(bot.dodoland_params.get(guild.id, "dodoland_hall_cells"))
    cells_w = max(1, bot.dodoland_terrain.world(guild.id)["cells_w"] or 1)
    from helpers.dodoland import townart as _townart
    hall_pct = round(hall_cells * _townart.WIDTH / _townart.HALL_SPAN / cells_w * 100, 4)
    per_house = int(bot.dodoland_params.get(guild.id, "dodoland_people_per_house"))
    house_cap = max(0, int(bot.dodoland_params.get(guild.id, "dodoland_max_houses")))
    people = []
    for person in result["order"]:
        uid = person["user_id"]
        mine = details.get(uid, {})
        built = []
        for key, score in person["buildings"].items():
            if score.get("tier") is None:
                continue
            built.append({
                "key": key,
                # What its owner calls it, falling back to what the server calls
                # it. Naming is free and changes nothing; the tier behind it is
                # neither.
                "name": town_rules.building_label(mine, key, score["name"]),
                "given": score["name"],
                "tier": int(score["tier"]) + 1,
                "title": score["tier_title"],
                "points": score["points"],
                # What actually builds it. The map makes somebody ask why a
                # building is there, and this is the answer.
                "rooms": rooms.get(key, []),
            })
        built.sort(key=lambda b: -b["tier"])
        shine = glow.get(uid) or flourish_rules.BLANK
        owner = _name_of(guild, bot, uid)
        people.append({
            "id": str(uid),
            "owner": owner,
            "name": town_rules.display_name(mine, owner),
            "blurb": str(mine.get("blurb") or ""),
            "walls": str(mine.get("walls") or ""),
            "gates": len(mine.get("gates") or []),
            # Houses moved by hand, by their number: {"3": [x, y]}.
            "house_at": {str(k): v for k, v in (mine.get("houses") or {}).items()},
            "has_image": bool(mine.get("image")),
            "power": person["power"],
            "place": person["place"],
            "reached": person["reached"],
            # Ordinary houses around the hall, one per so many people reached:
            # the classic town's rule, linear in reach on purpose.
            "houses": (min(house_cap, int(person["reached"]) // per_house) if per_house > 0 else 0),
            "built": built,
            "flourish": int(shine.get("level", 0)),
            "flourish_label": shine.get("label") or "",
            "rank": shine.get("rank_name") or "",
            "lit": uid in lit,
            "plot": plots.get(uid),
            # A town grows from the base width by its standing, on a square-root
            # curve. Linear growth would let one prolific person's settlement
            # swallow the map while everybody else stayed a speck, which is the
            # same reason the old marker sizing used a root.
            "w": hall_pct if halls else
                 round(base_pct * (1 + (growth - 1) * _grown(person["power"], biggest)), 4),
            # Placed relative to the town's own box, so it travels with the
            # town when the town is moved or grows.
            "decor": [{"id": d["piece_id"], "a": d["asset_id"],
                       "x": float(d.get("x", 50)), "y": float(d.get("y", 50)),
                       "s": float(d.get("scale", 1.0)),
                       "f": bool(d.get("flip"))}
                      for d in town_decor.get(uid, ())],
        })
    cats = {c["cat_id"]: c["name"] for c in bot.dodoland_tiles.categories()}
    # What admins may place: any tile that is placed rather than painted, on
    # whatever layer it belongs to. Painted ground lives in the terrain drawer.
    placeable = [t for t in bot.dodoland_tiles.tiles(guild.id)
                 if t["placement"] == "place" and "admin" in t["access"]]
    dims = bot.dodoland_tiles.art_sizes(v for t in placeable for v in t["variants"])
    shrink = max(0.1, float(bot.dodoland_params.get(guild.id, "dodoland_tile_scale")))
    # A town's buildings are drawn at its hall's scale: the hall's 120-unit box
    # spans hall_cells x 120 / HALL_SPAN cells, and so does every building's.
    hall_box = (float(bot.dodoland_params.get(guild.id, "dodoland_hall_cells"))
                * townart.WIDTH / townart.HALL_SPAN)
    landmarks = (str(bot.dodoland_params.get(guild.id, "dodoland_town_hall")),
                 str(bot.dodoland_params.get(guild.id, "dodoland_zoo_building")))
    bscale = max(0.1, float(bot.dodoland_params.get(guild.id, "dodoland_building_scale")))
    # Uploaded building pictures, when the server draws with them: each tier's
    # own picture in place of its generated drawing, wherever one was uploaded.
    upload = uploaded_art(bot, guild, placeable, hall_box, landmarks, bscale)
    # Settled people: their picture (travellers wear it), look and chosen pets.
    settled = [p for p in people if p.get("plot")]
    looks = {p["id"]: (details.get(int(p["id"])) or details.get(p["id"]) or {}).get("look") or {} for p in settled}
    from helpers.dodoland import pets as pet_rules
    follow = pet_rules.details({uid: lk.get("pets") for uid, lk in looks.items() if lk.get("pets")})
    for p in settled:
        p["av"] = _avatar_of(guild, p["id"])
        if looks.get(p["id"]):
            p["look"] = looks[p["id"]]
        if follow.get(p["id"]):
            p["follow"] = follow[p["id"]]
    world_decor = [dict(d, variant=upload[d["asset_id"]][0]) if d.get("asset_id") in upload else d
                   for d in world_decor]
    return {"people": people, "buildings": buildings,
            "total": len(result["people"]),
            "cells_w": bot.dodoland_terrain.world(guild.id)["cells_w"],
            "world": [{"id": d["piece_id"], "a": d["asset_id"], "v": d.get("variant") or "",
                       "l": d.get("layer") or "objects",
                       "x": float(d.get("x", 50)), "y": float(d.get("y", 50)),
                       "s": float(d.get("scale", 1.0)),
                       "f": bool(d.get("flip")),
                       # Turned this many degrees round its foot (the turn handle).
                       **({"r": float(d.get("rot"))} if d.get("rot") else {}),
                       # Who placed it, for the toolkit's Placed list.
                       "by": str(d.get("by") or ""), "bn": str(d.get("by_name") or ""),
                       "t": str(d.get("town") or ""),
                       "k": bool(d.get("locked")),
                       # Locked in place by its owner (or from its card).
                       "pk": bool(d.get("pinned")),
                       # How it stacks: flat, stand, top, or its layer's way.
                       "st": str(d.get("stack") or ""),
                       "at": int(d.get("at") or 0)} for d in world_decor],
            # The toolkit is the tile library's map objects and buildings that
            # admins have access to here. Ground is painted, not placed.
            "assets": [{"id": t["tile_id"], "name": t["name"], "cat": cats.get(t["cat_id"], ""),
                        "layer": t["layer"],
                        # Each variant's own width in map cells: drawings in one
                        # tile are not all the same size.
                        "vw": ({upload[t["tile_id"]][0]: upload[t["tile_id"]][1]} if t["tile_id"] in upload else
                               {v: _tile_cells(t, dims.get(v, (0, 0))[0], shrink, hall_box, landmarks, bscale)
                                for v in t["variants"]}),
                        # Natural width in map cells: the art's own width over
                        # its px-per-cell. A piece is drawn at this times its size.
                        "wc": (upload[t["tile_id"]][1] if t["tile_id"] in upload else
                               _tile_cells(t, dims.get(t["variants"][0], (0, 0))[0], shrink, hall_box,
                                           landmarks, bscale) if t["variants"] else 0),
                        # Pixel art (the fixed-size packs) is drawn with hard
                        # pixels: a 6-pixel sprouts sprite smoothed up to a
                        # thumbnail was a smudge, which read as "low resolution".
                        "px": not t["resizable"],
                        "building": t["requires"]["building"], "tier": t["requires"]["tier"],
                        # Members may place it (when they have unlocked it).
                        "pl": "player" in t["access"],
                        # A light: how far it lights at night (cells) and in what colour.
                        # Its lights (set in the lights editor), for the picture the map
                        # draws: the uploaded painting's own, or its own pictures'.
                        **({"gl": t["uploaded_lights"] if t["tile_id"] in upload else t["lights"]}
                           if (t["uploaded_lights"] if t["tile_id"] in upload else t["lights"]) else {}),
                        # Shown as its uploaded painting, a tier keeps the lights
                        # of its drawing too (gd) and its drawn width (wd), for
                        # where a town draws it.
                        **({"wd": _tile_cells(t, dims.get(t["variants"][0], (0, 0))[0], shrink, hall_box,
                                              landmarks, bscale) if t["variants"] else 0,
                            **({"gd": t["lights"]} if t["lights"] else {})}
                           if t["tile_id"] in upload and t["requires"]["building"] else {}),
                        # Whether lit windows are also found in it by colour.
                        **({} if t.get("auto_lights", True) else {"al": False}),
                        "lo": tile_rules.scale_range(t)[0], "hi": tile_rules.scale_range(t)[1]}
                       for t in placeable],
            # Not sent to the page: what a member's toolkit is unlocked from.
            "standings": result["people"], "defs": buildings, "upload": upload}


def _night_settings(bot, gid) -> dict:
    """How dark the night is, its colours, and how lights and windows glow."""
    p = bot.dodoland_params

    def num(key, lo, hi):
        return max(lo, min(hi, float(p.get(gid, key))))

    def hexed(key, fallback):
        v = str(p.get(gid, key) or "").strip()
        return v if len(v) == 7 and v.startswith("#") else fallback
    return {"darkness": num("dodoland_night_darkness", 0, 1),
            "colour": hexed("dodoland_night_colour", "#0b1430"),
            "dusk_colours": nightlights.colours(p.get(gid, "dodoland_dusk_colours"), nightlights.DUSK),
            "dawn_colours": nightlights.colours(p.get(gid, "dodoland_dawn_colours"), nightlights.DAWN),
            "tint": num("dodoland_twilight_tint", 0, 1), "spread": num("dodoland_twilight_spread", 0, 1),
            "twilight": num("dodoland_twilight_hours", 0.25, 6),
            "detail_from": num("dodoland_night_detail_from", 0, 400),
            "detail_to": num("dodoland_night_detail_to", 1, 800),
            "light_glow": num("dodoland_light_glow", 0, 1), "window_glow": num("dodoland_window_glow", 0, 1),
            "min_red": num("dodoland_window_min_red", 0, 255), "min_green": num("dodoland_window_min_green", 0, 255),
            "warmth": num("dodoland_window_warmth", 0, 255),
            "max_size": num("dodoland_window_max_size", 0.0001, 0.2),
            "contrast": num("dodoland_window_contrast", 0, 255),
            "spill": num("dodoland_window_spill", 0, 30),
            "most": num("dodoland_window_most", 0, 64), "merge": num("dodoland_window_merge", 0, 1),
            "walker_light": num("dodoland_walker_light", 0, 10)}


def _sun_settings(bot, gid) -> dict:
    """The sun the page casts every shadow from: the time of day (``auto``
    follows each viewer's own clock) and the shadow settings."""
    p = bot.dodoland_params

    def num(key, lo, hi):
        return max(lo, min(hi, float(p.get(gid, key))))
    mode = str(p.get(gid, "dodoland_time_of_day") or "auto")
    return {"mode": mode if mode in ("auto", "morning", "noon", "afternoon", "evening", "night") else "auto",
            "rise": num("dodoland_sunrise_hour", 0, 23), "set": num("dodoland_sunset_hour", 1, 24),
            "strength": num("dodoland_shadow_strength", 0, 1), "contact": num("dodoland_shadow_contact", 0, 1),
            "length": num("dodoland_shadow_length", 0.05, 1.5), "longest": num("dodoland_shadow_longest", 0.1, 3),
            "swing": num("dodoland_shadow_swing", 0, 2), "night": num("dodoland_shadow_night", 0, 1),
            "blur": num("dodoland_shadow_blur", 0, 0.2)}


def uploaded_art(bot, guild, tiles: list, hall_box: float, landmarks: tuple, bscale: float) -> dict:
    """``{tile_id: (uploaded picture id, width in map cells)}`` for the town
    building tiles that have an uploaded picture, when the server draws its
    buildings with them (``dodoland_building_art``); empty otherwise.

    Sized per building: its highest uploaded tier is as big (by the square root
    of its area) as about 60% of its generated drawing's box, which is how much
    of that box a top-tier generated building fills, times
    ``dodoland_uploaded_building_scale``; every lower tier keeps its size
    relative to it, so the building still grows tier by tier."""
    params = bot.dodoland_params
    if str(params.get(guild.id, "dodoland_building_art") or "") != "uploaded":
        return {}
    return uploaded_sizes(bot, guild, tiles, hall_box, landmarks, bscale)


def uploaded_sizes(bot, guild, tiles: list, hall_box: float, landmarks: tuple, bscale: float) -> dict:
    """``{tile_id: (uploaded picture id, width in map cells)}`` for every town
    building tile with an uploaded picture, whatever the server draws with
    (:func:`uploaded_art` is this when the server draws with them)."""
    params = bot.dodoland_params
    mine = [t for t in tiles if t.get("uploaded") and str(t.get("source") or "").startswith("building:")]
    if not mine:
        return {}
    sizes = bot.dodoland_tiles.art_sizes(t["uploaded"] for t in mine)
    grow = max(0.1, float(params.get(guild.id, "dodoland_uploaded_building_scale")))
    each = building_sizes(params.get(guild.id, "dodoland_uploaded_building_sizes"))
    by_key: dict = {}
    for t in mine:
        by_key.setdefault(t["requires"]["building"], []).append(t)
    out = {}
    for key, group in by_key.items():
        top = max(group, key=lambda t: int(t["requires"]["tier"] or 0))
        w, h = sizes.get(top["uploaded"], (0, 0))
        if not w or not h:
            continue
        box = hall_box * (1.0 if key in landmarks else bscale)
        px_per_cell = (w * h) ** 0.5 / (0.6 * box * grow * each.get(key, 1.0))
        for t in group:
            tw = sizes.get(t["uploaded"], (0, 0))[0]
            if tw:
                out[t["tile_id"]] = (t["uploaded"], round(tw / px_per_cell, 3))
    return out


def building_sizes(text) -> dict:
    """``"menagerie=0.6, tavern=1.2"`` -> ``{"menagerie": 0.6, "tavern": 1.2}``;
    anything unreadable is left out."""
    out = {}
    for part in str(text or "").replace(";", ",").split(","):
        key, _, value = part.partition("=")
        try:
            size = float(value)
        except ValueError:
            continue
        if key.strip() and size > 0:
            out[key.strip()] = min(10.0, size)
    return out


def pictured_towns(bot, guild, people: list, world: list, tiles: list, upload: dict) -> None:
    """With uploaded building art: what draws each town instead of its
    generated hall, set on the person as ``hall_art`` (the town hall's own
    uploaded picture, at the tier the town has reached) or ``hall_piece`` (its
    own painted building placed nearest its centre, within
    ``dodoland_uploaded_hall_reach`` cells). Neither: the generated hall stays."""
    if not upload:
        return
    from helpers.dodoland import building_tiles

    params = bot.dodoland_params
    hall_key = str(params.get(guild.id, "dodoland_town_hall") or "")
    reach = max(0.0, float(params.get(guild.id, "dodoland_uploaded_hall_reach")))
    size = bot.dodoland_terrain.world(guild.id)
    cw, ch = max(1, size["cells_w"] or 1), max(1, size["cells_h"] or 1)
    by_source = {t.get("source"): t for t in tiles}
    for person in people:
        plot = person.get("plot")
        if not plot:
            continue
        tier = next((b["tier"] for b in person["built"] if b["key"] == hall_key), 1)
        hall = by_source.get(building_tiles._source(guild.id, hall_key, tier))
        if hall and hall["tile_id"] in upload:
            vid, cells = upload[hall["tile_id"]]
            person["hall_art"] = {"a": hall["tile_id"], "v": vid, "wc": cells}
            continue
        best = None
        for piece in world:
            if piece.get("t") != person["id"] or piece.get("a") not in upload:
                continue
            d = (((piece["x"] - plot["x"]) / 100 * cw) ** 2 + ((piece["y"] - plot["y"]) / 100 * ch) ** 2) ** 0.5
            if d <= reach and (best is None or d < best[0]):
                best = (d, piece["id"])
        if best:
            person["hall_piece"] = best[1]


def _tile_cells(tile: dict, art_w: float, shrink: float, hall_box: float,
                landmarks: tuple = (), scale: float = 1.0) -> float:
    """How many map cells wide a tile is drawn at size 1.

    A tile's own art over its px-per-cell — except a town's generated buildings,
    which are drawn at the town hall's scale. They were 120 px over 12 px per
    cell, eight cells, while the hall beside them spanned thirty-five: every
    building a quarter of its true size, its tier's growth and its smoke a few
    pixels.
    """
    source = str(tile.get("source") or "")
    if source.startswith("building:"):
        # building:<guild>:<key>:<tier>. The hall and the zoo are landmarks and
        # keep the hall's scale; the rest are drawn at a fraction of it.
        key = source.split(":")[2] if source.count(":") >= 3 else ""
        return round(hall_box * (1.0 if key in landmarks else scale), 3)
    return round(art_w / tile["cell_px"] / shrink, 3)


async def map_page(request: web.Request):
    """The map, given the whole window."""
    from web.routes import _page  # noqa: F401  (kept for the nav's sake)

    bot, guild = request.app["bot"], request["guild"]
    viewer = str(request.get("uid") or "")
    data = await asyncio.get_running_loop().run_in_executor(None, _collect, bot, guild)
    # With uploaded building art, a painted picture with the flag stands for
    # the town instead of its generated hall.
    pictured_towns(bot, guild, data["people"], data["world"],
                   bot.dodoland_tiles.tiles(guild.id), data.get("upload") or {})
    # The same page for a member (web/dodoland/player_map.py): it reads and
    # writes through their own routes and offers only their own town.
    player = bool(request.get("player"))
    if player:
        # Only the towns on the map, and their own: not the standing of every
        # member of the server (which nobody browsing the map should be handed,
        # and which was most of the page). Only the tiles the map draws —
        # what is placed, and the town buildings at any tier — not the
        # admins' toolkit library.
        data = dict(data)
        data["people"] = [p for p in data["people"] if p["plot"] or p["id"] == viewer]
        used = {d["a"] for d in data["world"]}
        # Their toolkit: what members may place, dimmed where they have not
        # unlocked it yet (a reward you cannot see is not a reward).
        person = data["standings"].get(int(viewer)) if viewer.isdigit() else None
        unlocked = tile_rules.unlocked_for(
            [{"tile_id": a["id"], "requires": {"building": a["building"], "tier": a["tier"]}}
             for a in data["assets"] if a["pl"]], person, data["defs"])
        names = {b["key"]: b.get("name") or b["key"] for b in data["defs"]}

        def why(a):
            return f"Unlocks at tier {a['tier']} of {names.get(a['building'], a['building'])}"
        data["assets"] = [dict(a, lk=a["id"] not in unlocked,
                               **({"why": why(a)} if a["id"] not in unlocked else {}))
                          if a["pl"] else a
                          for a in data["assets"]
                          if a.get("building") or a["id"] in used or a["pl"]]
        from web.dodoland import player as player_rules
        may_settle = player_rules.self_settle_on(bot, guild.id)
    else:
        may_settle = True
    base = request.get("dl_base") or f"/guild/{guild.id}/dodoland"
    api = (f"/api/guild/{guild.id}/dodoland/me" if player else f"/api/guild/{guild.id}/dodoland")
    # Landmark mode is the map's own setting-up tool: for the bot owner and the
    # server's owner, nobody else sees it.
    from helpers import panel_access
    landmark_mode = (not player) and (request.get("scope") == panel_access.SCOPE_OWNER or
                                      str(getattr(guild, "owner_id", "") or "") == viewer)
    endpoints = {"base": base, "player": player, "landmark_mode": landmark_mode,
                 "paint": api + "/terrain/paint", "undo": api + "/terrain/undo",
                 # Members read the forest; only admins paint it (no member route).
                 "forest": base + "/forest/chunks",
                 "forest_paint": "" if player else api + "/forest/paint",
                 "decor": api + ("/build" if player else "/decor"),
                 "town": api + "/town",
                 # The runaway horse (horse_api.py): where it is, and kicks.
                 "horse": api + "/horse",
                 # A town owner's cats and dogs, for the ones following them.
                 "pets": api + "/pets",
                 # A member places and moves their own town when the server lets them.
                 "settle": api + "/settle" if may_settle else ""}

    image = bot.dodoland_buildings.map_image(guild.id)
    if image:
        raw = image.get("data")
        blob = bytes(raw) if raw is not None else b""
        src = (f"data:{_e(image.get('content_type'))};base64,"
               f"{base64.b64encode(blob).decode('ascii')}")
        world = f'<img id="dlbase" alt="The map of {_e(guild.name)}" src="{src}">'
    else:
        world = ('<div class="dlnomap">No map uploaded yet. Upload one on the '
                 'DodoLand page first.</div>')

    placed = [p for p in data["people"] if p["plot"]]
    unplaced = [p for p in data["people"] if not p["plot"]]
    # How large a piece of decor is drawn at 100% zoom, before its own scale.
    decor_size = int(bot.dodoland_params.get(guild.id, "dodoland_asset_size"))
    # People and animals: the town art's own figures, drawn with a colour
    # token the page fills in, and its rule for who each building brings.
    life = {
        "on": bool(bot.dodoland_params.get(guild.id, "dodoland_life_on")),
        "max": int(bot.dodoland_params.get(guild.id, "dodoland_life_max")),
        "zoo": str(bot.dodoland_params.get(guild.id, "dodoland_zoo_building")),
        "per_tier": int(bot.dodoland_params.get(guild.id, "dodoland_zoo_animals")),
        "sprites": {name: (draw("@C@") if name not in ("person",) else draw("@C@", hat=0))
                    for name, draw in townart.WANDERERS.items()},
        "hats": [townart._person("@C@", hat=h) for h in (0, 1, 2)],
        "pools": {k: list(v) for k, v in townart.LIFE.items()},
        "default": list(townart.DEFAULT_LIFE),
        "shapes": {b["key"]: (b.get("shape") or "") for b in data["buildings"]},
        "colours": list(townart.WALKER_COLOURS),
        "zoo_kinds": ["cat", "dog", "horse", "kiwi", "bird", "dove"],
        # Every cottage shape in every house colour, at the town art's size;
        # the page scales them by the hall's units per cell.
        "cottages": [townart._cottage(0.0, 0.0, 7.6, roof, variant=v, wall=wall)
                     for v in range(6) for roof, wall in townart.HOUSE_COLOURS],
        # A real member: head and coat in their own colours (@H@, @B@).
        "member": townart.member_figure("@H@", "@B@"),
        "units_per_cell": round(townart.HALL_SPAN / float(bot.dodoland_params.get(guild.id, "dodoland_hall_cells")), 4),
    }
    if "dove" not in life["sprites"]:
        life["sprites"]["dove"] = townart._fa_walker("dove", 5.0)("@C@")
    sizes = {
        # A proportion of the map's width, not a pixel count. Positions are
        # percentages for the same reason: re-uploading the map at another
        # resolution must change neither where a town sits nor how big it looks.
        "town_pct": float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct")),
        "dot_below": int(bot.dodoland_params.get(guild.id, "dodoland_town_dot_below")),
        "detail_above": int(bot.dodoland_params.get(guild.id, "dodoland_detail_above")),
        "ratio": townart.HEIGHT / townart.WIDTH,
        # The building the town itself is drawn as, when towns are halls.
        "hall_key": (str(bot.dodoland_params.get(guild.id, "dodoland_town_hall"))
                     if str(bot.dodoland_params.get(guild.id, "dodoland_town_style")) == "hall" else ""),
        "min_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_min_zoom")),
        "max_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_max_zoom")),
        # Per layer: the screen pixels a map cell must be before it shows.
        "lod": {key: float(bot.dodoland_params.get(guild.id, f"dodoland_lod_{key}"))
                for key in ("tiles", "environment", "objects", "buildings", "houses",
                            "life", "influence", "walls", "forest")},
        # How finely forests are drawn, and how many chunks of them at once.
        "forest_detail": float(bot.dodoland_params.get(guild.id, "dodoland_forest_detail_max")),
        "forest_chunks": int(bot.dodoland_params.get(guild.id, "dodoland_forest_chunks_max")),
        "forest_full": float(bot.dodoland_params.get(guild.id, "dodoland_forest_full_at")),
        "forest_strip": float(bot.dodoland_params.get(guild.id, "dodoland_forest_strip_cells")),
        # The close-up ground, baked per chunk: how finely, how many kept, and
        # how soft its curved edges are and how deep a smart ground's fringe.
        "ground_feather": max(0.001, min(0.5, float(bot.dodoland_params.get(guild.id, "dodoland_ground_feather")))),
        "ground_fringe": max(0.0, min(0.5, float(bot.dodoland_params.get(guild.id, "dodoland_ground_fringe")))),
        "ground_detail": float(bot.dodoland_params.get(guild.id, "dodoland_ground_detail_max")),
        "ground_chunks": int(bot.dodoland_params.get(guild.id, "dodoland_ground_chunks_max")),
        "ground_memory_mb": max(32, int(bot.dodoland_params.get(guild.id, "dodoland_ground_memory_mb"))),
        "hit_alpha": max(0, min(255, int(bot.dodoland_params.get(guild.id, "dodoland_hit_alpha")))),
        # Smart ground: how many cells one tile spans, and how often a variation shows.
        "autotile_cells": max(1, min(8, int(bot.dodoland_params.get(guild.id, "dodoland_autotile_cells")))),
        "autotile_inset": max(0.0, min(0.2, float(bot.dodoland_params.get(guild.id, "dodoland_autotile_inset")))),
        "bake_budget_ms": max(1, min(50, int(bot.dodoland_params.get(guild.id, "dodoland_bake_budget_ms")))),
        # Ground muting, the same the server applies to the zoomed-out picture.
        "ground_mute": terrainart.mute_settings(bot.dodoland_params, guild.id),
        # The sun every shadow comes from (dodoland_time_of_day, dodoland_shadow_*).
        "sun": _sun_settings(bot, guild.id),
        # The night, from the same clock (dodoland_night_*, dodoland_window_*).
        "night": _night_settings(bot, guild.id),
        # Real members travelling the busiest roads (0: none), and what a
        # traveller's horse says when somebody tries to herd it.
        "travellers": max(0, int(bot.dodoland_params.get(guild.id, "dodoland_travellers"))),
        "horse_busy": str(bot.dodoland_params.get(guild.id, "dodoland_horse_busy_line")),
        "autotile_variation": max(0.0, min(1.0, float(bot.dodoland_params.get(guild.id, "dodoland_autotile_variation")))),
        # The walls choice on a town's card (dodoland_walls_option).
        "walls": bool(bot.dodoland_params.get(guild.id, "dodoland_walls_option")),
        # A town's picture: the server's own limit, in bytes.
        "picture_max": town_rules.picture_limit(bot.dodoland_params, guild.id),
        # Population on a town's card: the tiles its area covers, times this.
        "pop_per_cell": max(0.0, float(bot.dodoland_params.get(guild.id, "dodoland_population_per_cell"))),
        "forest_gap_full": float(bot.dodoland_params.get(guild.id, "dodoland_forest_spacing_full")),
        # Below this, px per cell, a forest chunk is one flat picture, not trees.
        "forest_merge": max(0.0, float(bot.dodoland_params.get(guild.id, "dodoland_forest_merge"))),
        "forest_gap_zero": float(bot.dodoland_params.get(guild.id, "dodoland_forest_spacing_zero")),
    }

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Map · {_e(guild.name)}</title>
<style>{_CSS}</style>
</head><body>
<div class="dlbar">
  <!-- The making tools on the left, side by side, beside the drawers they
       open; the server's name in the middle; looking-around on the right. -->
  <div class="dlbarside">
    <button id="dlterr" class="dlghost">🗺 Terrain</button>
    <button id="dlkit" class="dlghost">🧰 Toolkit</button>
    <button id="dlsettle" class="dlghost own" hidden>🏠 Place my town</button>
  </div>
  <b class="dltitle">{_e(guild.name)}</b>
  <div class="dlbarside right">
    <button id="dllayers" class="dlghost">▤ Layers</button>
    <button id="dltoggle" class="dlghost">Towns list</button>
  </div>
</div>

<div class="dllayerpanel" id="dllayerpanel" hidden>
  <div class="dlhrow"><b>Layers</b><span class="muted">show · edit</span></div>
  <div id="dllayerrows"></div>
  <p class="dlkithint">Only the layer you edit can be picked up, and the toolkit
  offers that layer's tiles. Ground is painted in the Terrain drawer.</p>
</div>

<div class="dlframe" id="dlframe">
  <div class="dlworld" id="dlworld">{world}</div>
  <div class="dlzoom">
    <button type="button" id="dlin" title="Zoom in">+</button>
    <button type="button" id="dlout" title="Zoom out">&minus;</button>
    <button type="button" id="dlfit" title="Fit the whole map">&#9634;</button>
    <button type="button" id="dlnames" title="Show every name">A</button>
    <button type="button" id="dlfindme" title="Find your traveller on the roads">&#128014;</button>
    <span class="dlzsep"></span>
    <button type="button" data-tool="pointer" title="Select (V): click a piece, shift-click to add, drag a box"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M5 3l14 8-6 1.5L10 19z" fill="currentColor"/></svg></button>
    <button type="button" data-tool="hand" title="Hand (H): drag to move around; drag a selected piece to move it"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M8 11V5.5a1.5 1.5 0 013 0V10m0-5.5a1.5 1.5 0 013 0V10m0-4a1.5 1.5 0 013 0v7c0 4-2.5 7-6.5 7S5 17 4 14l-1.5-3.5a1.4 1.4 0 012.4-1.4L8 13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <button type="button" data-tool="pencil" title="Pencil (P): click to place the picked tile, one per click"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M4 20l1-5L16 4l4 4L9 19zM14 6l4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg></button>
    <button type="button" data-tool="brush" title="Brush (B): drag to scatter the picked tiles"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 3c-4 2-8 6-10 10l2 2c4-2 8-6 10-10zM9 14c-3 0-4 2-4 4s-1 2-2 3c3 0 7 0 7-4z" fill="currentColor"/></svg></button>
  </div>
  <div class="dlbox" id="dlbox"></div>
  <div class="dlbrushcur" id="dlbrushcur"></div>
  <div class="dlhint" id="dlhint">Drag to move, scroll to zoom</div>
  <div class="dlloading" id="dlloading" role="status" aria-live="polite">
    <div class="dlloadcard">
      <div class="dlloadtitle">{_e(guild.name)}</div>
      <div class="dlloadbar"><i id="dlloadfill"></i></div>
      <ul class="dlloadsteps">
        <li data-step="map">Unrolling the map</li>
        <li data-step="ground">Painting the land and sea</li>
        <li data-step="reach">Measuring every town's reach</li>
        <li data-step="textures">Preparing the ground</li>
      </ul>
    </div>
  </div>
</div>

<aside class="dldrawer" id="dldrawer">
  <div class="dldhead">
    <b>Towns</b>
    <button class="dlghost" id="dlclose">&times;</button>
  </div>
  <input class="dlsearch" id="dlsearch" placeholder="Search a name...">
  <div class="dllist" id="dllist"></div>
</aside>

{terrain_ui.DRAWER}
<aside class="dldrawer dlkitdrawer" id="dlkitdrawer">
  <div class="dldhead">
    <b>Toolkit</b>
    <button class="dlghost" id="dlkitclose">&times;</button>
  </div>
  <div class="dlseg dlkittabs"><button data-tab="lib" class="on">Library</button><button data-tab="placed">Placed</button></div>
  <label class="dllandmode" id="dllandmode" hidden title="Everything you place while this is on is a landmark: nobody moves or removes it until an admin unlocks it, no town carries it off, and members cannot paint the ground under it">
    <input type="checkbox" id="dllandmodebox"><b>&#128274; Landmark mode</b><span>Everything I place stays put</span></label>
  <div class="dlkitpane" id="dlkitlib">
    <p class="dlkithint" id="dlkithint">Pick something, then use the pencil to put it
    down one at a time or the brush to scatter it. Shift-click several to brush a mix.</p>
    <div class="dlbrushopts" id="dlbrushopts" hidden>
      <div class="dlseg" id="dlbrushpat">{'' if player else '<button data-pat="forest" class="on">Forest</button>'}<button data-pat="scatter"{' class="on"' if player else ''}>Scatter</button><button data-pat="line">Line</button><button data-pat="cluster">Cluster</button></div>{'' if player else forest_ui.MODE}
      <label title="Forest: how tightly the trees pack. 100% stands them about crown to crown; lower lets ground show between them. The spacing at each end is set in the panel.">Density <input type="range" id="dlbden" min="20" max="100" step="5" value="75"><output id="dlbdenn">75%</output></label>
      <label>Radius <input type="range" id="dlbrad" min="1" max="60" value="8"><output id="dlbradn">8</output></label>
      <label>Spacing <input type="range" id="dlbsp" min="1" max="40" value="6"><output id="dlbspn">6</output></label>
      <label>Size jitter <input type="range" id="dlbjit" min="0" max="60" step="5" value="15"><output id="dlbjitn">15%</output></label>
      <label class="dlcheck"><input type="checkbox" id="dlbflip" checked> Random mirror</label>
    </div>
    <select id="dlkitcat" class="dlsel"></select>
    <div class="dlkitgrid" id="dlkitgrid"></div>
  </div>
  <div class="dlkitpane" id="dlkitplaced" hidden>
    <div class="dlplacedhead">
      <select id="dlplacedwho" class="dlsel"{' hidden' if player else ''}><option value="me">Placed by me</option><option value="all">Everyone's</option></select>
      <span id="dlplacedn" class="muted"></span>
    </div>
    <div class="dlplacedlist" id="dlplacedlist"></div>
  </div>
  <div class="dlkitfoot">
    <label>Size <input type="range" id="dlkitscale" min="0.25" max="6"
      step="0.05" value="1"></label>
    <button class="dlghost" id="dlkitflip">Mirror</button>
    <span class="dlstack" id="dlstack" title="How the selection draws against what is around it"><button data-st="flat" title="Under everything that stands: ponds, paths, rugs">Flat</button><button data-st="stand" title="In front of what stands behind it">Standing</button><button data-st="top" title="Over everything">On top</button></span>
    <button class="dlghost" id="dlkitlock"{' hidden' if player else ''} title="A landmark: nobody moves or removes it until an admin unlocks it, no town carries it off, and members cannot paint the ground under it. On something already locked (a landmark, or a building its owner locked in place) it unlocks it.">&#128274; Landmark</button>
    <button class="dlghost" id="dlkitdel">Remove</button>
  </div>
  <p class="dlkitmsg" id="dlkitmsg"></p>
</aside>

<aside class="dlcard" id="dlcard" hidden></aside>

<script>window.DL = {json.dumps({"people": data["people"], "sizes": sizes,
                                 "gid": str(guild.id), "me": viewer,
                                 "world": data["world"],
                                 "assets": data["assets"],
                                 "cells_w": data["cells_w"],
                                 "decorsize": decor_size, "life": life,
                                 "ep": endpoints})};</script>
<script>{_SCRIPT}</script>
</body></html>"""
    return web.Response(text=body, content_type="text/html")


# The palette is shared with the player pages (``web/dodoland/theme.py``) — it
# was copied into them once, and two copies of a colour scheme become two colour
# schemes the moment either is edited.
_CSS = theme.PALETTE + """
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--deep); color: var(--ink); overflow: hidden;
  font: 15px/1.5 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }

.dlbar { position: fixed; inset: 0 0 auto 0; height: 52px; z-index: 30;
  display: flex; align-items: center; gap: 14px; padding: 0 16px;
  background: var(--bar); color: #f4e6cf; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
.dlbarside { display: flex; gap: 10px; flex: 1 1 0; min-width: 0; }
.dlbarside.right { justify-content: flex-end; }
.dltitle { flex: 0 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-size: 17px; text-align: center; }
.dlback { color: #f0c98a; text-decoration: none; }
.dlback:hover { text-decoration: underline; }
.dlcount { font-size: 13px; opacity: .8; }
.dlspacer { flex: 1 1 auto; }
.dlghost { background: none; border: 1px solid rgba(255,255,255,.25);
  color: inherit; border-radius: 8px; padding: 6px 12px; cursor: pointer;
  font: inherit; font-size: 13px; }
.dlghost:hover { background: rgba(255,255,255,.1); }

/* The map gets the window. Everything else floats over it. */
.dlframe { position: fixed; inset: 52px 0 0 0; overflow: hidden;
  cursor: grab; touch-action: none; background: var(--deep); }
.dlframe.dragging { cursor: grabbing; }
.dlframe.placing { cursor: crosshair; }
/* Until the map, the ground and the towns' areas are in: a card over the frame
   rather than a black screen that fills in piece by piece. */
.dlloading { position: absolute; inset: 0; z-index: 40; display: flex;
  align-items: center; justify-content: center; background: var(--night, #15110e);
  transition: opacity .45s ease; }
.dlloading.done { opacity: 0; pointer-events: none; }
.dlloadcard { min-width: 260px; max-width: 80vw; text-align: center; }
.dlloadtitle { font-size: 22px; font-weight: 700; margin-bottom: 14px; color: #f3e6cf; }
.dlloadbar { height: 4px; border-radius: 2px; background: rgba(255,255,255,.12); overflow: hidden; }
.dlloadbar i { display: block; height: 100%; width: 8%; background: var(--lantern);
  transition: width .35s ease; }
.dlloadsteps { list-style: none; margin: 14px 0 0; padding: 0; font-size: 13px;
  color: rgba(243,230,207,.55); text-align: left; display: inline-block; }
.dlloadsteps li::before { content: "○"; display: inline-block; width: 1.4em; }
.dlloadsteps li.ok { color: rgba(243,230,207,.95); }
.dlloadsteps li.ok::before { content: "●"; color: var(--lantern); }
/* Clicking fast to place things is a double-click to the browser, which then
   selects whatever is under it — the influence overlay lit up blue. */
.dlframe { user-select: none; -webkit-user-select: none; }
/* While something is armed, a town is ground like any other: the click places
   rather than opening the town. */
.dlframe.placing .dltown, .dlframe.painting .dltown,
.dlframe.placing .dltown *, .dlframe.painting .dltown * { pointer-events: none !important; }
/* Only the open town's area, unless the Layers panel asks for every one. */
#dltinfl > g { display: none; }
#dltinfl > g.on, .dlworld.infl-all #dltinfl > g { display: inline; }
/* No will-change here, and it must stay that way. Promoting this to its own
   composited layer makes the browser rasterise it once at whatever size it
   happened to be and then scale that bitmap, so an SVG map stops being vector
   the moment anybody zooms and every town blurs with it. The transform is
   cheap enough without the hint. */
.dlworld { position: absolute; top: 0; left: 0; transform-origin: 0 0; }
.dlworld img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }
.dlnomap { padding: 40px; color: var(--soft); }

/* Above the drawers, and out from under the open one. These sat at z-index 12
   under a 340px drawer that opens by default, so the whole control column was
   invisible and every press landed on the drawer instead — which looks exactly
   like four buttons with no handlers. */
.dlzoom { position: fixed; right: 16px; top: 68px; display: flex;
  flex-direction: column; gap: 6px; z-index: 26;
  transition: right .18s ease; }
.dlzoom.shifted { right: 356px; }
.dlzoom button { width: 38px; height: 38px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--edge); background: var(--paper); color: var(--ink);
  box-shadow: 0 2px 10px rgba(0,0,0,.35); }
.dlzoom button.on { background: var(--lantern); color: #fff; }
/* Bottom centre: on the left it sat under the Terrain and Toolkit drawers. */
.dlhint { position: absolute; left: 50%; bottom: 16px; z-index: 12;
  transform: translateX(-50%); max-width: calc(100% - 32px); text-align: center;
  padding: 6px 12px; border-radius: 9px; font-size: 13px;
  background: rgba(0,0,0,.55); color: #fff3e0; }

/* A town is placed and sized in the map's own units and sits inside the element
   the zoom scales, so it shrinks and grows with the coastline exactly as a
   village on a paper map does. It is deliberately NOT counter-scaled: an
   earlier version pinned towns to a fixed screen size, which made them loom
   larger the further you zoomed out until the map was all roofs. */
.dltown { position: absolute; transform: translate(-50%, -100%);
  cursor: pointer; z-index: 5; }
.dlart { width: 100%; }
/* Uploaded art: the town drawn by a painted picture, or by one of its own
   painted buildings (then nothing of its own is drawn but its name). */
.dltown.pictured .dlart { position: relative; }
.dltown.pictured .dlart img { display: block; width: 100%; height: auto; pointer-events: auto; }
.dltown.bypiece .dlart { display: none; }
/* The town's flag, flying from the top of the picture it is on. */
.dlflag { position: absolute; left: 50%; top: 0; width: 22%; aspect-ratio: 1 / 1.35;
  transform: translate(-3%, -62%); pointer-events: none; }
.dlflag i { position: absolute; left: 0; bottom: 0; width: 5%; min-width: 1px; height: 100%;
  background: #3b2a1c; border-radius: 1px; }
.dlflag i::before { content: ""; position: absolute; left: -60%; top: -4%; width: 220%;
  aspect-ratio: 1; border-radius: 50%; background: #c99a3a; }
.dlflag img { position: absolute; left: 5%; top: 4%; width: 95%; height: auto;
  border: 1px solid #2b1d12; box-shadow: 1px 1px 0 rgba(0,0,0,.25); }
.dltown svg { display: block; width: 100%; height: auto; overflow: visible; }
/* A town catches the mouse only on what is drawn — the hall, its square, its
   flag — not on the empty rectangle around it, which covered the houses
   standing behind it. Light (glows, auras, beams, sparks) lets clicks through. */
.dltown { pointer-events: none; }
.dltown .dlart svg * { pointer-events: visiblePainted; }
.dltown .dldot { pointer-events: auto; }
.dltown .fx, .dltown .fx *, .dltown .flwash, .dltown .flring, .dltown .flring2,
.dltown .flunder, .dltown .halo, .dltown .glow, .dltown .bglow, .dltown .baura,
.dltown .bshadow, .dltown .bbeam, .dltown .bcrown { pointer-events: none; }
/* Below a few dozen pixels a settlement is an illegible smudge, so it becomes a
   dot, which is what every map does as you pull away from it. */
.dltown.tiny .dlart, .dltown.tiny .dlname { display: none; }
.dltown.tiny .dldot { display: block; }
/* In flow, not absolute: when a town is a dot this is its only visible child,
   and an absolutely positioned one left the town with no height and therefore
   nothing to click. A dot you cannot open is not a town on a map. */
/* Sizes inside the world are in world pixels, which are --ws to a pixel of
   the reference image. */
.dldot { display: none; width: calc(11px * var(--ws, 1)); height: calc(11px * var(--ws, 1));
  border-radius: 50%; margin: 0 auto; background: #f0c98a;
  border: calc(2px * var(--ws, 1)) solid #4a3524;
  box-shadow: 0 calc(1px * var(--ws, 1)) calc(3px * var(--ws, 1)) rgba(0,0,0,.5); }
.dltown.tiny { min-width: calc(14px * var(--ws, 1)); }
.dltown.dim { opacity: .5; }
/* A filter on anything inside the scaled world rasterises it, so the selected
   town is marked with an outline on its ground plate rather than a glow. Same
   reason will-change is banned above: keep the vectors vectors. */
.dltown.on .dlart { outline: none; }
.dltown.on ellipse:first-of-type { stroke: var(--lantern); stroke-width: 3; }
.dltown.on .dldot { box-shadow: 0 0 0 calc(3px * var(--ws, 1)) var(--lantern); }
/* The name is drawn at a constant screen size, because a label that shrinks
   with the map stops being a label. It is the one thing here that is
   counter-scaled, and only ever the text. */
.dlname { position: absolute; left: 50%; top: 100%; margin-top: calc(4px * var(--inv, 1));
  transform: translateX(-50%) scale(var(--inv, 1)); transform-origin: top center;
  padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: #fff6e4; background: rgba(20,14,8,.82); white-space: nowrap;
  opacity: 0; transition: opacity .12s ease; pointer-events: none; }
.dltown:hover, .dltown.on { z-index: 30000 !important; }
.dltown:hover .dlname, .dlworld.named .dlname, .dltown.on .dlname { opacity: 1; }
""" + theme.TOWN_ART_CSS + """
/* Drawers float over the map rather than stealing its width. */
.dldrawer { position: fixed; top: 52px; bottom: 0; right: 0; width: 340px;
  z-index: 20; display: flex; flex-direction: column; background: var(--paper);
  border-left: 1px solid var(--edge); box-shadow: -6px 0 24px rgba(0,0,0,.28);
  transform: translateX(100%); transition: transform .18s ease; }
.dldrawer.open { transform: none; }
/* In a drawer only the lists scroll and give up height; everything else —
   headers, tabs, switches, sliders, footers — keeps its own. Without this the
   column squeezed the Library / Placed tabs until their labels were cut off. */
.dldrawer > :not(.dlkitpane):not(.dlkitgrid):not(.dllist),
.dlkitpane > :not(.dlkitgrid):not(.dlplacedlist) { flex-shrink: 0; }
.dldhead { display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--edge); }
.dldhead .dlghost { border-color: var(--edge); }
.dlsearch { margin: 10px 14px; padding: 8px 10px; font: inherit; font-size: 14px;
  border: 1px solid var(--edge); border-radius: 8px; background: var(--deep);
  color: var(--ink); }
.dllist { flex: 1 1 auto; overflow-y: auto; padding: 0 8px 16px; }
.dlgroup { padding: 10px 6px 4px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .12em; color: var(--soft); }
.dlrow { display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 8px 8px; border: 0; border-radius: 8px; background: none;
  color: inherit; font: inherit; text-align: left; cursor: pointer; }
.dlrow:hover { background: var(--deep); }
.dlrow.armed { background: var(--lantern); color: #fff; }
.dlrow .n { flex: 1 1 auto; min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.dlrow .p { font-size: 12px; opacity: .75; }

.dlcard { position: fixed; left: 16px; bottom: 16px; width: 340px; z-index: 25;
  padding: 16px 18px; border-radius: 12px; background: var(--paper);
  border: 1px solid var(--edge); box-shadow: 0 10px 34px rgba(0,0,0,.35);
  /* The editor makes this tall enough to run off the top of the screen, and a
     Save button nobody can reach is a Save button that does not work. */
  max-height: calc(100vh - 84px); overflow-y: auto; }
.cardmsg { margin: 10px 0 0; font-size: 13px; color: var(--soft); }
.cardmsg.bad { color: #c0392b; font-weight: 600; }
.dlcard h3 { margin: 0 0 2px; font-size: 19px; }
.dlcard .sub { color: var(--soft); font-size: 13px; margin-bottom: 10px; }
.dlcard ul { list-style: none; margin: 8px 0 0; padding: 0; }
.dlcard li { display: flex; align-items: center; gap: 8px; padding: 3px 0;
  font-size: 14px; }
/* A building's own line, and the rooms that build it once it is the one being
   asked about. Every building's channels at once is a wall of names; the
   question is only ever asked about the one somebody just clicked. */
.dlcard li.bline { display: block; padding: 4px 0; }
.dlcard .btop { display: flex; align-items: center; gap: 8px; }
.dlcard li.bline.focus { background: var(--deep); border-radius: 8px;
  padding: 6px 8px; margin: 2px -8px; }
.brooms { font-size: 12px; color: var(--soft); margin-top: 3px;
  word-break: break-word; }
/* The lot under the pointer says it can be opened, and the one that is open is
   picked out by its ground plate rather than by a filter — a filter inside the
   scaled world rasterises whatever it touches. */
.lot.named { cursor: pointer; }
.dlcard li i { width: 20px; text-align: center; color: var(--lantern); }
.dlcard .acts { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.dlcard button.own { background: var(--lantern); color: #fff;
  border-color: var(--lantern); }
.yours { font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
  padding: 2px 7px; border-radius: 999px; vertical-align: middle;
  background: var(--lantern); color: #fff; }
.dlcard .blurb { margin: 8px 0 0; font-size: 14px; color: var(--soft);
  white-space: pre-wrap; }
.dledit { margin-top: 12px; display: none; }
.dledit.open { display: block; }
.dledit label { display: block; font-size: 12px; color: var(--soft);
  margin: 8px 0 3px; }
.dledit input, .dledit textarea { width: 100%; padding: 7px 9px; font: inherit;
  font-size: 14px; border: 1px solid var(--edge); border-radius: 8px;
  background: var(--deep); color: var(--ink); }
.dledit textarea { min-height: 70px; resize: vertical; }
.dlcard button { flex: 1 1 auto; padding: 7px 10px; border-radius: 8px;
  border: 1px solid var(--edge); background: var(--deep); color: var(--ink);
  font: inherit; font-size: 13px; cursor: pointer; }
.dlcard button:hover { background: var(--edge); }

/* ---- the toolkit -------------------------------------------------------- */
/* Decor sits inside `.dlworld`, so it scales and pans with the coastline
   exactly as a town does. It is placed at a percentage of the base image for
   the same reason towns are: re-uploading a redrawn map at another resolution
   must move nothing. */
/* Turned round its foot: the point it stands on stays where it stands. */
.dlpiece { position: absolute; transform: translate(-50%, -85%) rotate(var(--rot, 0deg));
  transform-origin: 50% 85%;
  z-index: 4; cursor: pointer; }
.dlpiece img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }
.dlpiece.flip img { transform: scaleX(-1); }
/* A baked shadow behind its picture (made already mirrored for a mirrored piece). */
.dltown .dlart { position: relative; }
/* The night: one canvas over the map, lights cut out of it (see drawNight). */
.dlnight { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none;
  z-index: 6; display: none; }
.dlpiece img.dlshadow, .dltown .dlart img.dlshadow, .dlstand img.dlshadow { position: absolute; z-index: -1;
  max-width: none; pointer-events: none; transform: none; image-rendering: auto; display: block; }
/* Held and hovered pieces are marked by boxes on the frame, in screen pixels,
   not by outlines on the pieces. Anything drawn inside the zoomed world is
   scaled by the zoom, and a browser rounds an outline thinner than one pixel up
   to one before it scales — so a "1px" line was fifty pixels at full zoom. */
.dlmark { position: absolute; pointer-events: none; z-index: 20; display: none;
  border: 1.5px solid var(--lantern); border-radius: 3px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, .45); }
.dlmark.hover { border: 1px dashed rgba(240, 166, 79, .85); box-shadow: none; }
/* A landmark's box: steady blue, with a lock. */
.dlmark.locked { border-color: #7fb2ff; }
.dlmark.locked::after, .dlmark.pinned::after { content: "🔒"; position: absolute; top: -18px; left: 50%;
  transform: translateX(-50%); font-size: 12px; }
/* Locked in place by its owner: amber, the same lock. */
.dlmark.pinned { border-color: #f0c34f; }
.bico.block.on { color: #f0c34f; }
.bline button[disabled] { opacity: .45; cursor: not-allowed; }
/* Where the armed piece will land, at the size it will land at. */
.dlpiece.ghost { opacity: .6; pointer-events: none; display: none; z-index: 40000; }
.dlframe.placing .dlpiece.ghost.live { display: block; }
/* Grabbable, and grabbed. touch-action stops the browser treating a drag on a
   piece as a scroll of the page underneath it. */
.dlpiece { touch-action: none; cursor: grab; }
.dlpiece.dragging { cursor: grabbing; opacity: .85; }
/* Town decor belongs to a town and sits under its buildings, so a cart parked
   outside the tavern is outside the tavern rather than on its roof. */
.dlpiece.town { z-index: 3; }
/* The layers, bottom to top: painted ground (the terrain svg, z 1), the
   environment's placed features, roads, map objects, buildings and towns. */
.dlpiece.L-environment { z-index: 2; }
/* Objects, buildings and towns take their depth from where they stand (the
   page's depth()); only flat ground features are a layer of their own. */
.dlworld.hide-influence #dltinfl,
.dlworld.hide-ground #dltover, .dlworld.hide-ground #dltdetail,
.dlworld.hide-environment .dlpiece.L-environment,
.dlworld.hide-objects .dlpiece.L-objects,
.dlworld.hide-buildings .dlpiece.L-buildings,
.dlworld.hide-buildings .dltown { display: none; }
/* Any piece that can be seen can be picked up; the layer being edited only
   decides what the toolkit offers. Locking the other layers silently made
   trees unclickable for anyone whose last edit was a building. */
.dllayerpanel { position: fixed; top: 60px; right: 16px; width: 290px; z-index: 28;
  background: var(--paper); border: 1px solid var(--edge); border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,.3); padding: 10px 0 2px; }
.dllayerpanel[hidden] { display: none; }
.dlhrow { display: flex; justify-content: space-between; align-items: center;
  padding: 0 14px 8px; font-size: 13px; }
.dllayer { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center;
  padding: 7px 14px; border-top: 1px solid var(--edge); font-size: 13px; }
.dllayer.editing { background: var(--deep); box-shadow: inset 3px 0 0 var(--lantern); }
.dllayer small { display: block; color: var(--soft); font-size: 11px; }
.dllayer button { background: none; border: 1px solid var(--edge); border-radius: 6px;
  color: inherit; font: inherit; font-size: 12px; padding: 2px 7px; cursor: pointer; }
.dllayer button.off { opacity: .45; }
.dllayer button.on { border-color: var(--lantern); color: var(--lantern); }
.dllayer button:disabled { visibility: hidden; }

.dlkitdrawer { left: 0; right: auto; border-left: 0;
  border-right: 1px solid var(--edge); transform: translateX(-100%);
  box-shadow: 6px 0 24px rgba(0,0,0,.28); }
.dlkitdrawer.open { transform: translateX(0); }
/* With a town's card open, the left-hand drawers open beside it, not under it.
   Only an open one: a closed drawer is tucked away by translateX(-100%), which
   is its own width, and moved 372px right a closed drawer narrower than that
   still showed beside the card. */
body.dlcardopen .dlkitdrawer.open, body.dlcardopen .dlterrdrawer.open { left: 372px; border-left: 1px solid var(--edge); }
/* Closed is gone, not merely slid aside: nothing of it can show or be clicked. */
.dlkitdrawer:not(.open), .dlterrdrawer:not(.open) { visibility: hidden;
  transition: transform .2s, visibility 0s .2s; }
.dlkithint { margin: 10px 0 0; padding: 0 14px 8px; font-size: 12px; color: var(--soft);
  line-height: 1.45; }
/* One look for every palette in a drawer — the toolkit's and the terrain's —
   so the two cannot drift apart. Cards are a fixed size: a grid that stretches
   its rows to fill the drawer turned two mushrooms into two pillars. */
.dlkitgrid { flex: 1 1 auto; overflow-y: auto; display: grid; gap: 6px;
  grid-template-columns: repeat(auto-fill, minmax(74px, 1fr)); grid-auto-rows: 84px;
  align-content: start; padding: 2px 14px 12px; }
.dlkititem { border: 1px solid transparent; border-radius: 8px; padding: 5px 4px 4px;
  background: var(--deep); cursor: pointer; display: flex; flex-direction: column;
  align-items: center; justify-content: space-between; gap: 3px; font: inherit;
  color: inherit; min-width: 0; transition: border-color .12s, background .12s; }
.dlkititem:hover { border-color: var(--edge); background: var(--paper); }
.dlkititem img { width: 100%; height: 52px; object-fit: contain; }
/* Pixel art keeps its pixels, in the kit and on the map. */
.dlkititem.px img, .dlpiece.px img { image-rendering: pixelated; }
.dlstack { display: inline-flex; border: 1px solid var(--edge); border-radius: 8px; overflow: hidden; }
.dlstack button { background: var(--deep); color: var(--soft); border: 0; border-right: 1px solid var(--edge);
  padding: 5px 8px; font: inherit; font-size: 12px; cursor: pointer; }
.dlstack button:last-child { border-right: 0; }
.dlstack button.on { background: var(--paper); color: var(--ink); box-shadow: inset 0 -2px 0 var(--lantern); }
.dlkititem span { font-size: 10px; text-align: center; line-height: 1.2; color: var(--soft);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
/* Selected: a thin ring, not a slab — the picture is the point. */
.dlkititem.armed { border-color: var(--lantern); background: var(--paper); }
.dlkititem.armed span { color: var(--ink); }
.dlsel, .dlkitcat { display: block; margin: 0 14px 10px; width: calc(100% - 28px);
  padding: 7px 10px; font: inherit; font-size: 13px; color: var(--ink);
  background: var(--deep); border: 1px solid var(--edge); border-radius: 8px;
  color-scheme: dark light; }
.dlsel:focus, .dlkitcat:focus { outline: 1px solid var(--lantern); outline-offset: 1px; }
.dlseg { display: flex; margin: 10px 14px 0; border: 1px solid var(--edge); border-radius: 8px;
  overflow: hidden; }
.dlseg button { flex: 1; background: var(--deep); color: var(--soft); border: 0;
  border-right: 1px solid var(--edge); padding: 7px 0; font: inherit; font-size: 13px;
  cursor: pointer; }
.dlseg button:last-child { border-right: 0; }
.dlseg button.on { background: var(--paper); color: var(--ink); box-shadow: inset 0 -2px 0 var(--lantern); }
/* A locked thing is shown, not hidden. Knowing the gilded banner exists at the
   third tier of the Gallery is the reason to want the third tier. */
.dlkititem.locked { opacity: .42; cursor: not-allowed; }
.dlkititem.locked span::after { content: " 🔒"; }
.dlkitfoot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 10px 14px; border-top: 1px solid var(--edge); }
.dlkitfoot label { font-size: 12px; color: var(--soft); display: flex;
  align-items: center; gap: 6px; flex: 1 1 120px; }
.dlkitfoot input[type=range] { flex: 1 1 auto; min-width: 60px; }
.dlkitmsg { margin: 0; padding: 0 14px 12px; font-size: 12px; color: var(--soft); }
.dlkitmsg.bad { color: #c0392b; font-weight: 600; }
.dlbuild { margin-top: 12px; border-top: 1px solid var(--edge); padding-top: 10px; }
.dlcard .btop { display: flex; align-items: center; gap: 6px; }
.dlcard .btop .bpts { margin-left: auto; opacity: .7; }
.dlcard .btop button { flex: 0 0 auto; padding: 2px 8px; font-size: 12px; border-radius: 6px; }
.dlcard .btop .bico { padding: 2px 5px; background: none; border-color: transparent; opacity: .55; }
.dlcard .btop .bico:hover { opacity: 1; border-color: var(--edge); }
.dlcard .btop .bbuild { background: var(--lantern); border-color: var(--lantern); color: #fff; }
.dlcard .btop .bmove, .dlcard .btop .bdel { background: none; color: inherit; border-color: var(--edge); }
.dlcard .btop .bhall { font-size: 11px; color: var(--soft); border: 1px dashed var(--edge);
  border-radius: 6px; padding: 2px 7px; }
.dlcard .btop .bdel:hover { border-color: #c0392b; color: #e06a5a; }
.dlcard .brename { flex: 1 1 auto; min-width: 0; font: inherit; padding: 2px 6px; }
.dlbuildgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); gap: 6px;
  margin: 8px 0; max-height: 210px; overflow-y: auto; }
.dlbuildtile { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 4px;
  border: 1px solid var(--edge); border-radius: 8px; background: none; color: inherit; cursor: pointer; }
.dlbuildtile:hover { border-color: var(--lantern); }
.dlbuildtile img { width: 100%; height: 40px; object-fit: contain; }
.dlbuildtile.px img { image-rendering: pixelated; }
.dlbuildtile span { font-size: 10px; line-height: 1.15; text-align: center; }
.dlbuildtile.placed { border-style: dashed; opacity: .75; }
.dlbuildtile small { font-size: 9px; color: var(--soft); }
.dlwallrow { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.dlzsep { display: block; height: 1px; margin: 4px 6px; background: var(--edge); }
.dlzoom button svg { display: block; margin: auto; }
.dlkittabs { margin: 10px 14px 0; }
.dllandmode { display: grid; grid-template-columns: auto 1fr; column-gap: 8px; align-items: center;
  margin: 8px 14px 0; padding: 6px 10px; border: 1px dashed var(--edge); border-radius: 8px;
  font-size: 12px; cursor: pointer; }
.dllandmode input { grid-row: span 2; margin: 0; }
.dllandmode b { font-weight: 600; white-space: nowrap; }
.dllandmode span { color: var(--soft); }
.dllandmode.on { border-style: solid; border-color: #7fb2ff; background: rgba(127, 178, 255, .1); }
.dllandmode[hidden] { display: none; }
.dlkitpane { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
.dlkitpane[hidden] { display: none; }
.dlbrushopts { padding: 4px 14px 8px; display: grid; gap: 6px; font-size: 12px; color: var(--soft); }
.dlbrushopts label { display: grid; grid-template-columns: 76px 1fr 36px; align-items: center; gap: 6px; }
.dlbrushopts label.dlcheck { display: flex; }
.dlbrushopts[hidden] { display: none; }
.dlbrushopts .dlseg { margin: 0 0 4px; }
.dlplacedhead { display: flex; gap: 8px; align-items: center; padding: 8px 14px 6px; font-size: 12px; }
.dlplacedhead .dlsel { margin: 0; flex: 1 1 auto; }
.dlplacedlist { flex: 1 1 auto; overflow-y: auto; padding: 0 8px 10px; }
.dlplaced { display: grid; grid-template-columns: 34px 1fr auto; gap: 8px; align-items: center;
  padding: 5px 6px; border-radius: 8px; cursor: pointer; font-size: 12px; }
.dlplaced:hover { background: var(--deep); }
.dlplaced.on { background: var(--deep); box-shadow: inset 3px 0 0 var(--lantern); }
.dlplaced img { width: 34px; height: 30px; object-fit: contain; }
.dlplaced.px img { image-rendering: pixelated; }
.dlplaced small { display: block; color: var(--soft); }
.dlplaced button { background: none; border: 1px solid var(--edge); border-radius: 6px; color: inherit;
  cursor: pointer; font-size: 12px; padding: 2px 7px; }
/* Real members on the roads: a gold ring at their feet, their picture over
   their heads (drawn at screen size), a flickering torch; on a horse outside
   the towns. Pets and travellers take clicks. */
.dlstand.dltraveller, .dlstand.dlpet, .dlstand.dlhorse { pointer-events: auto; cursor: pointer; }
.dlstand.dltraveller.found .dltring { animation: dlfound .5s ease-in-out 6 alternate; }
@keyframes dlfound { to { transform: scale(2.4); opacity: .4; } }
.dllook { display: flex; gap: 10px; flex-wrap: wrap; }
.dllook label { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; }
.dlpets { display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0; }
.dlpets button { font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.dlpets.found { max-height: 120px; overflow-y: auto; }
.dltraveller svg { overflow: visible; }
.dltraveller .tr { display: none; }
.dltraveller.riding .tw { display: none; }
.dltraveller.riding .tr { display: inline; }
.dltring { transform-box: fill-box; transform-origin: center; }
.dlworld:not(.dldark) .dltorch { display: none; }
.dltface { position: absolute; left: 50%; bottom: 112%; width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid #ffd257; transform: translateX(-50%) scale(var(--inv, 1)); transform-origin: bottom center;
  box-shadow: 0 1px 4px rgba(0,0,0,.5); background: #2a1d12; }
.dlflame { animation: dlflicker .35s ease-in-out infinite alternate; }
@keyframes dlflicker { from { opacity: .75; } to { opacity: 1; } }
.dltcard { position: absolute; z-index: 45; display: none; width: 200px; padding: 12px; border-radius: 14px;
  background: var(--paper, #fff8ec); color: var(--ink, #2b2118); box-shadow: 0 8px 24px rgba(0,0,0,.35); text-align: center; }
.dltcard.on { display: block; }
.dltcard img { width: 96px; height: 96px; border-radius: 50%; object-fit: cover; display: block; margin: 0 auto 8px;
  border: 3px solid #ffd257; }
.dltcard img.pet { border-radius: 12px; width: 176px; height: 140px; }
.dltcard b { display: block; font-size: 15px; }
.dltcard span { display: block; font-size: 13px; margin-top: 2px; }
.dltcard small { display: block; font-size: 11px; opacity: .7; margin-top: 6px; }
/* The runaway horse: it takes clicks; what it says is drawn at screen size. */
/* Over everything, a town pointed at included (30000): it grazes among them. */
.dlstand.dlhorse { z-index: 40000 !important; }
.dlhorse svg { transition: transform .15s; }
.dlhorse.running svg { animation: dlgallop .22s linear infinite; }
@keyframes dlgallop { 50% { translate: 0 -6%; } }
.dlhorse.gone { transition: opacity 1.2s 1.6s; opacity: 0; }
.dlhorsesay { position: absolute; left: 50%; bottom: 100%; transform: translateX(-50%) scale(var(--inv, 1));
  transform-origin: bottom center; white-space: nowrap; padding: 5px 10px; border-radius: 10px;
  background: #fff8ec; color: #3a2414; font-size: 13px; font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,.35);
  opacity: 0; transition: opacity .2s; pointer-events: none; margin-bottom: 4px; }
.dlhorsesay.on { opacity: 1; }
/* The turn handle: above a lone selected piece; drag it round to turn the
   piece (Shift: in 15 degree steps), double-click to stand it straight. */
.dlturn { position: absolute; z-index: 22; display: none; width: 22px; height: 22px; margin: -11px 0 0 -11px;
  border-radius: 50%; background: var(--lantern, #f0a64f); color: #1b130a; font-size: 14px; line-height: 22px;
  text-align: center; cursor: grab; box-shadow: 0 1px 4px rgba(0,0,0,.45); touch-action: none; user-select: none; }
.dlturn.on { display: block; }
.dlturn::after { content: ""; position: absolute; left: 50%; top: 22px; width: 1px; height: 14px; background: rgba(240,166,79,.7); }
/* "Placing..." while a place or move is saved: a bar that fills over about
   as long as saving usually takes here, so nobody pulls things about meanwhile. */
.dlbusy { position: fixed; left: 50%; bottom: 64px; transform: translateX(-50%); z-index: 40;
  display: none; min-width: 180px; padding: 8px 14px 10px; border-radius: 12px;
  background: rgba(20, 14, 8, .88); color: #f3e6cf; font-size: 13px; font-weight: 600;
  box-shadow: 0 6px 18px rgba(0, 0, 0, .35); pointer-events: none; text-align: center; }
.dlbusy.on { display: block; }
.dlbusy i { display: block; height: 4px; margin-top: 7px; border-radius: 2px; background: rgba(243, 230, 207, .18); overflow: hidden; }
.dlbusy b { display: block; height: 100%; width: 0; background: var(--lantern, #f0a64f); border-radius: 2px; }
.dlframe.busy, .dlframe.busy * { cursor: progress !important; }
/* The pointer's selection box and the brush's reach, on screen. */
.dlbox { position: absolute; display: none; pointer-events: none; z-index: 21;
  border: 1px dashed var(--lantern); background: rgba(240, 166, 79, .1); }
.dlbrushcur { position: absolute; display: none; pointer-events: none; z-index: 21;
  border: 1px solid rgba(255, 255, 255, .9); border-radius: 50%;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, .45); transform: translate(-50%, -50%); }
.dlframe[data-tool="pointer"] { cursor: default; }
.dlframe[data-tool="hand"] { cursor: grab; }
.dlframe.placing[data-tool="brush"] { cursor: none; }
/* Armed, everything placed is ground to stamp on rather than something to grab. */
.dlframe.placing .dlpiece { pointer-events: none; }
.dlpiece.preview { opacity: .55; pointer-events: none; }
/* Layers too far out for their detail setting. */
.dlworld.lodoff-environment .dlpiece.L-environment,
.dlworld.lodoff-objects .dlpiece.L-objects,
.dlworld.lodoff-buildings .dlpiece.L-buildings,
.dlworld.lodoff-houses .dlhouse,
.dlworld.lodoff-influence #dltinfl,
.dlworld.lodoff-walls #dltwalls { display: none; }
.dlnotice { position: absolute; top: 14px; left: 50%; transform: translateX(-50%); z-index: 45;
  display: none; max-width: min(560px, calc(100% - 32px)); padding: 10px 38px 10px 14px;
  border-radius: 10px; background: rgba(40, 28, 14, .96); color: #fbecd2;
  border: 1px solid var(--lantern); box-shadow: 0 6px 24px rgba(0,0,0,.45); font-size: 13px; }
.dlnotice.on { display: block; }
.dlnotice p { margin: 2px 0; }
.dlnotice button { position: absolute; top: 6px; right: 8px; background: none; border: 0;
  color: inherit; font-size: 18px; cursor: pointer; }
/* A building's pop-up, above it, on screen. */
.dlpop { position: absolute; display: none; z-index: 30; transform: translate(-50%, -100%);
  min-width: 180px; max-width: 300px; padding: 9px 12px 10px; border-radius: 10px;
  background: rgba(24, 18, 13, .94); color: #f6ead6; border: 1px solid var(--edge);
  box-shadow: 0 6px 22px rgba(0,0,0,.4); font-size: 13px; line-height: 1.35; text-align: left; }
.dlpop::after { content: ""; position: absolute; left: 50%; bottom: -6px; width: 10px; height: 10px;
  background: rgba(24, 18, 13, .94); border-right: 1px solid var(--edge); border-bottom: 1px solid var(--edge);
  transform: translateX(-50%) rotate(45deg); }
.dlpop b { display: block; font-size: 14px; }
.dlpop .dlpopsub { display: block; color: var(--soft); font-size: 12px; margin-top: 2px; }
.dlpop .dlpopfed { display: block; font-size: 12px; margin-top: 6px; }
.dlpop button { margin-top: 8px; background: none; border: 1px solid var(--edge); border-radius: 6px;
  color: inherit; font: inherit; font-size: 12px; padding: 2px 8px; cursor: pointer; }
/* Houses and walkers stand on the map like pieces, each at its ground point. */
.dlstand { position: absolute; pointer-events: none; }
.dlstand svg { display: block; width: 100%; height: auto; overflow: visible; }
.dlhouse.flip svg { transform: scaleX(-1); }
.dlworld.hide-life .dlwalker, .dlworld.lifefar .dlwalker { display: none; }
.dlworld.hide-buildings .dlhouse { display: none; }
/* Houses can be picked up and moved, by whoever may edit that town. */
.dlhouse.movable { pointer-events: auto; cursor: grab; }
.dlhouse.dragging { cursor: grabbing; opacity: .85; }
.dlframe.placing .dlhouse, .dlframe.painting .dlhouse { pointer-events: none !important; }
/* The life layer itself stays: the houses are in it, and they show from afar. */
.dlkitempty { padding: 0 14px; color: var(--soft); font-size: 13px; }

""" + terrain_ui.CSS + forest_ui.CSS + """
@media (max-width: 720px) {
  .dldrawer { width: 100%; }
  .dlcard { left: 8px; right: 8px; width: auto; }
}
"""

_SCRIPT = r"""
(function () {
  var D = window.DL, frame = document.getElementById('dlframe'),
      world = document.getElementById('dlworld'),
      base = document.getElementById('dlbase'),
      hint = document.getElementById('dlhint'),
      list = document.getElementById('dllist'),
      drawer = document.getElementById('dldrawer'),
      card = document.getElementById('dlcard');
  var byId = {};
  D.people.forEach(function (p) { byId[p.id] = p; });

  // --- the viewport ---------------------------------------------------- //
  // --- loading ---------------------------------------------------------- //
  // Three things make the first picture: the base image (the map's size), the
  // ground, and the towns' areas. The card lifts when all three are in, or
  // after a while regardless — a slow area must not hold the map hostage.
  var waitingFor = {map: 1, ground: 1, reach: 1, textures: 1}, steps = Object.keys(waitingFor).length;
  function loaded(step) {
    if (!waitingFor[step]) return;
    delete waitingFor[step];
    var li = document.querySelector('.dlloadsteps [data-step="' + step + '"]');
    if (li) li.classList.add('ok');
    var left = Object.keys(waitingFor).length;
    var fill = document.getElementById('dlloadfill');
    if (fill) fill.style.width = Math.round((steps - left) / steps * 100) + '%';
    if (!left) liftLoading();
  }
  function liftLoading() {
    var card = document.getElementById('dlloading');
    if (card) setTimeout(function () { card.classList.add('done'); }, 150);
  }
  setTimeout(liftLoading, 20000);

  var view = {x: 0, y: 0, k: 1}, nat = {w: 0, h: 0};
  // The world is laid out WS times larger than the reference image and zoomed
  // WS times less, which looks the same. It is not cosmetic: the browser
  // rounds a box's edges to whole layout pixels before the zoom is applied,
  // and at 958 px across a tree was 0.8 px wide — rounded to 0 or 1 depending
  // on where it stood, then magnified fifty times. That was the stretching.
  // Laid out large, a tree is a dozen pixels and the rounding cannot be seen.
  var WS = 16;
  // Depth: what stands lower on the map stands nearer, so it is drawn in front.
  // One rule for every piece, town hall, house and walker, from where it stands
  // (its y, in percent of the map). Flat ground features stay underneath.
  function depth(yPct) { return 100 + Math.round(Math.max(0, Math.min(100, yPct)) * 100); }
  // How a piece stacks: flat under everything standing (the environment
  // layer's way), standing by where it stands (everything else's), or on top
  // of all of it. A piece can be set to any of the three (Flat / Standing /
  // On top in the toolkit), which is how a pond goes under a tree beside it.
  function stackOf(p) { return p.st || ((p.l || 'objects') === 'environment' ? 'flat' : 'stand'); }
  function stackZ(el, p) {
    var st = stackOf(p);
    el.style.zIndex = st === 'flat' ? '2' : st === 'top' ? String(10200 + depth(p.y)) : String(depth(p.y));
  }
  world.style.setProperty('--ws', WS);
  function kMin() { return D.sizes.min_zoom / WS; }
  function kMax() { return D.sizes.max_zoom / WS; }
  function apply() {
    world.style.transform = 'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.k + ')';
    // Towns live in map space but are drawn at screen size, so each is scaled
    // back by 1/k. Without this a town becomes a billboard at 4x.
    // Only labels are counter-scaled: a name that shrinks with the map stops
    // being a name. The towns themselves scale with the world on purpose.
    world.style.setProperty('--inv', (1 / view.k).toFixed(4));
    levelOfDetail();
    if (typeof placePop === 'function') placePop();
    if (typeof placeMarks === 'function') placeMarks();
    if (typeof nightSoon === 'function') nightSoon();
  }
  function clamp() {
    // Two different jobs depending on which is bigger. When the world is larger
    // than the frame, stop it being dragged past its own edges. When it is
    // smaller, centre it instead: the old rule took a min of one bound and a
    // max of another that had crossed over, which pinned the map to a nonsense
    // position and is what made zooming out and back in leave a mess.
    var w = nat.w * view.k, h = nat.h * view.k;
    var fw = frame.clientWidth, fh = frame.clientHeight;
    view.x = (w <= fw) ? (fw - w) / 2 : Math.min(0, Math.max(fw - w, view.x));
    view.y = (h <= fh) ? (fh - h) / 2 : Math.min(0, Math.max(fh - h, view.y));
  }
  function fit() {
    if (!nat.w || !nat.h) return;
    // Re-read: a resize or a replaced image can change these underneath us.
    if (base && base.naturalWidth) { nat.w = base.naturalWidth * WS; nat.h = base.naturalHeight * WS; }
    // Measured after layout: called too early the frame has no height yet and
    // the map ends up stranded in the middle of a black screen, which is what
    // it did. A little air so the coastline is not flush against the edges.
    var fw = frame.clientWidth, fh = frame.clientHeight;
    if (!fw || !fh) { requestAnimationFrame(fit); return; }
    var pad = 24;
    view.k = Math.min((fw - pad * 2) / nat.w, (fh - pad * 2) / nat.h);
    view.k = Math.min(kMax(), Math.max(kMin(), view.k));
    clamp();
    apply();
    // Something waiting for the map's real size (arriving at one's own town).
    fit.done = true;
    if (fit.then) { var then = fit.then; fit.then = null; then(); }
  }
  function zoom(f, cx, cy) {
    var n = Math.min(kMax(), Math.max(kMin(), view.k * f));
    if (n === view.k) return;
    view.x = cx - (cx - view.x) * (n / view.k);
    view.y = cy - (cy - view.y) * (n / view.k);
    view.k = n; clamp(); apply();
  }
  function measure() {
    if (!base) return;
    // An SVG with no intrinsic size reports 0, so fall back to what it actually
    // laid out at rather than to a number that makes fit() meaningless.
    var box = base.getBoundingClientRect();
    nat.w = (base.naturalWidth || Math.round(box.width) || frame.clientWidth) * WS;
    nat.h = (base.naturalHeight || Math.round(box.height) || frame.clientHeight) * WS;
    // Width only: the image carries its own aspect, and pinning a height too
    // means any disagreement between the two shows as the world drifting away
    // from the coastline drawn on it.
    world.style.width = nat.w + 'px';
    requestAnimationFrame(fit);
    loaded('map');
  }
  if (base) { if (base.complete && base.naturalWidth) measure();
              else base.addEventListener('load', measure);
              base.addEventListener('error', function () { loaded('map'); }); }
  else loaded('map');
  window.addEventListener('resize', function () { clamp(); apply(); });

  frame.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var b = frame.getBoundingClientRect();
    zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX - b.left, ev.clientY - b.top);
  }, {passive: false});

  // Pointer capture is taken only once a drag has actually started. Taking it
  // on pointerdown routes every following event to the frame, so a plain click
  // on a town never reaches the town and nothing opens. That is why towns and
  // dots were unclickable.
  var down = false, captured = false, moved = 0, last = null, pid = null, figPress = null;
  var painting = false;
  frame.addEventListener('pointerdown', function (ev) {
    // A brush stroke is a drag and so is a pan. Whichever is armed wins, and
    // only one ever can be.
    if (ev.button === 0 && typeof terr !== 'undefined' && terr.armed !== null && strokeStart(ev)) {
      painting = true;
      try { frame.setPointerCapture(ev.pointerId); } catch (e) {}
      return;
    }
    // The wheel held down moves the map, always: over a piece, over a town,
    // with any tool or brush in hand (the terrain brush above is left-button).
    if (ev.button === 1) {
      ev.preventDefault();
      down = true; captured = false; moved = 0; pid = ev.pointerId;
      last = {x: ev.clientX, y: ev.clientY};
      return;
    }
    if (ev.target.closest && ev.target.closest('.dlzoom')) return;

    if (typeof toolDown === 'function' && toolDown(ev)) return;
    down = true; captured = false; moved = 0; pid = ev.pointerId;
    last = {x: ev.clientX, y: ev.clientY};
  });
  frame.addEventListener('pointermove', function (ev) {
    if (painting) { strokeMove(ev); return; }
    if (gesture) { toolMove(ev); return; }
    if (!down) return;
    var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
    moved += Math.abs(dx) + Math.abs(dy);
    if (!captured && moved > 4) {
      // Now it is a drag rather than a click, so hold on to the pointer.
      captured = true;
      frame.classList.add('dragging');
      try { frame.setPointerCapture(pid); } catch (e) {}
    }
    if (!captured) return;
    view.x += dx; view.y += dy; last = {x: ev.clientX, y: ev.clientY};
    clamp(); apply();
  });
  ['pointerup', 'pointercancel'].forEach(function (e) {
    frame.addEventListener(e, function (ev) {
      if (painting) { painting = false; strokeEnd(); }
      if (gesture) toolUp(ev);
      down = false; captured = false; frame.classList.remove('dragging');
    });
  });
  document.getElementById('dlin').onclick = function () {
    zoom(1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlout').onclick = function () {
    zoom(1 / 1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlfit').onclick = fit;
  // Your own traveller: the view goes to them and their ring flashes.
  function findTraveller() {
    var t = (typeof travellers !== 'undefined' ? travellers : []).filter(function (q) { return String(q.who.id) === String(D.me); })[0];
    if (!t || t.x == null) { hint.textContent = 'Your traveller is not on the roads (settle a town and talk to people).'; return; }
    view.k = Math.max(view.k, Math.min(kMax(), 10 / WS));
    view.x = frame.clientWidth / 2 - t.x / terr.world.cells_w * nat.w * view.k;
    view.y = frame.clientHeight / 2 - t.y / terr.world.cells_h * nat.h * view.k;
    clamp(); apply();
    t.el.classList.add('found');
    setTimeout(function () { t.el.classList.remove('found'); }, 3000);
  }
  document.getElementById('dlfindme').onclick = findTraveller;
  var namesBtn = document.getElementById('dlnames');
  namesBtn.onclick = function () {
    var on = world.classList.toggle('named');
    namesBtn.classList.toggle('on', on);
    if (typeof nightSoon === 'function') nightSoon(true);
  };

  // --- towns ------------------------------------------------------------ //
  // --- level of detail -------------------------------------------------- //
  // Three questions, asked on every pan and zoom: is this town on screen at
  // all, is it big enough to be more than a dot, and is it close enough for its
  // flourishes. Only the first decides whether it exists in the DOM.
  var nodes = {}, art = {};

  function draw(person) {
    var el = document.createElement('div');
    el.className = 'dltown fl' + person.flourish + (person.lit ? '' : ' dim');
    el.dataset.id = person.id;
    el.style.left = person.plot.x + '%';
    el.style.top = person.plot.y + '%';
    el.style.zIndex = depth(person.plot.y);
    // A percentage of the world, which is the base image's own width, so a town
    // is a fixed fraction of the map whatever resolution that image happens to
    // be. It sits inside the element the zoom scales, so it shrinks and grows
    // with the coastline.
    el.style.width = (person.w || D.sizes.town_pct) + '%';
    el.innerHTML = '<span class="dldot"></span>' +
      '<div class="dlart"></div>' +
      '<div class="dlname">' + escapeHtml(person.name) + '</div>';
    // Uploaded art: the town is its hall's painted picture (hall_art), or one
    // of its own painted buildings carries its flag (hall_piece); no generated hall.
    if (person.hall_art) {
      el.classList.add('pictured');
      if (D.cells_w) el.style.width = (person.hall_art.wc / D.cells_w * 100) + '%';
      el.querySelector('.dlart').innerHTML = '<img alt="" src="' + assetUrl(person.hall_art.a) +
        '?v=' + person.hall_art.v + '">' + flagHtml(person);
      addShadow(el.querySelector('.dlart'), assetUrl(person.hall_art.a) + '?v=' + person.hall_art.v, false);
    } else if (person.hall_piece) {
      el.classList.add('pictured', 'bypiece');
    }
    el.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (moved > 6) return;
      // Which building was clicked, if any. A town is a pile of overlapping
      // silhouettes and the one you want is often behind another, so clicking
      // it brings it out and opens the card on it.
      var lot = ev.target.closest && ev.target.closest('.lot.named');
      var key = lot && lot.getAttribute('data-building');
      if (lot) {
        // Paint order is document order in SVG, so moving the group to the end
        // of its parent is what "bring to the front" means here.
        lot.parentNode.appendChild(lot);
      }
      open(person.id, key || null);
    });
    world.appendChild(el);
    nodes[person.id] = el;
    return el;
  }

  // A town's flag on a picture: a pole and the town's own picture as cloth.
  function flagHtml(person) {
    if (!person || !person.has_image) return '';
    return '<div class="dlflag"><i></i><img alt="" src="' + D.ep.base + '/town/' + person.id +
      '/picture?w=320"></div>';
  }
  var hallPieces = {};
  D.people.forEach(function (p) { if (p.hall_piece) hallPieces[p.hall_piece] = p; });
  function needArt(person, el) {
    if (person.hall_art || person.hall_piece) return;
    // Fetched once per town, then kept. A town that is never approached is
    // never drawn, which is what lets a building be as detailed as it likes.
    if (art[person.id] === undefined) {
      art[person.id] = null;  // in flight; do not ask twice
      fetch(D.ep.base + '/town/' + person.id + '/art')
        .then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (svg) {
          art[person.id] = svg;
          var host = nodes[person.id];
          if (host && svg) {
            host.querySelector('.dlart').innerHTML =
              '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
              svg + '</svg>';
            addShadow(host.querySelector('.dlart'), svgPicture([0, 0, 120, 78], svg), false);
          }
        }).catch(function () { art[person.id] = ''; });
    } else if (art[person.id]) {
      var host = el.querySelector('.dlart');
      if (!host.firstChild) {
        host.innerHTML = '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
          art[person.id] + '</svg>';
        addShadow(host, svgPicture([0, 0, 120, 78], art[person.id]), false);
      }
    }
  }

  // Each layer shows from its own zoom (D.sizes.lod, px per map cell; set per
  // server in the panel). A class on the world per layer that is too far out.
  function layerDetail() {
    if (!D.cells_w || !nat.w) return;
    var perCell = nat.w * view.k / D.cells_w, lod = D.sizes.lod || {};
    ['environment', 'objects', 'buildings', 'houses', 'influence', 'walls'].forEach(function (k) {
      world.classList.toggle('lodoff-' + k, perCell < (lod[k] || 0));
    });
  }
  function levelOfDetail() {
    if (!nat.w) return;
    layerDetail();
    // Sizes differ per town now, so the thresholds are asked per town rather
    // than once for the map. A large settlement keeps its buildings and its
    // smoke further out than a hamlet does, which is what you would expect.
    var mapPx = nat.w * view.k / 100;

    // The visible rectangle, in map percentages, with a margin so a town does
    // not pop in at the very edge of the frame.
    var pad = nat.w * (D.sizes.town_pct / 100) * view.k * 3;
    var x0 = ((-view.x - pad) / (nat.w * view.k)) * 100;
    var x1 = ((-view.x + frame.clientWidth + pad) / (nat.w * view.k)) * 100;
    var y0 = ((-view.y - pad) / (nat.h * view.k)) * 100;
    var y1 = ((-view.y + frame.clientHeight + pad) / (nat.h * view.k)) * 100;

    D.people.forEach(function (p) {
      if (!p.plot) return;
      var on = p.plot.x >= x0 && p.plot.x <= x1 && p.plot.y >= y0 && p.plot.y <= y1;
      var el = nodes[p.id];
      if (!on) {
        if (el) { el.remove(); delete nodes[p.id]; }
        return;
      }
      if (!el) el = draw(p);
      var shown = (p.w || D.sizes.town_pct) * mapPx;
      var tiny = shown < D.sizes.dot_below;
      el.classList.toggle('tiny', tiny);
      el.classList.toggle('close', shown > D.sizes.detail_above);
      // A dot needs no artwork, which is most of the saving on a wide view.
      if (!tiny) needArt(p, el);
    });
    // Decor is sized against the base image, which is 0 until it has loaded.
    if (typeof resizeDecor === 'function') resizeDecor();
    if (typeof terrDetail === 'function') terrDetail();
    if (typeof forestView === 'function') forestView();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function redraw() {
    world.querySelectorAll('.dltown').forEach(function (n) { n.remove(); });
    nodes = {};
    levelOfDetail();
    // The counts left the top bar; nothing to update there any more.
  }

  // --- the town card ----------------------------------------------------- //
  var openId = null;
  function open(id, focusKey) {
    var p = byId[id];
    if (!p) return;
    openId = id;
    // What this viewer may do to this town: an admin anything, a member their
    // own. Decided before the rows are drawn — decided after, it was still
    // unset when they were, and every row lost its rename, Build, Move and Delete.
    var mayEdit = !D.ep.player || (D.me && String(p.id) === String(D.me));
    // One thing open at a time: a town's card puts the toolkit and the
    // terrain drawer away (the towns list stays; towns are opened from it).
    if (kitDrawer.classList.contains('open')) closeKit();
    if (typeof terrClose === 'function') terrClose();
    world.querySelectorAll('.dltown').forEach(function (n) {
      n.classList.toggle('on', n.dataset.id === id);
    });
    markInfluence();
    var rows = p.built.map(function (b) {
      // The rooms that build it, on the one that was clicked. Every building
      // at once is a wall of channel names; the question is only ever asked
      // about the building somebody just pointed at.
      var on = focusKey && b.key === focusKey;
      var rooms = (b.rooms && b.rooms.length)
        ? b.rooms.map(escapeHtml).join(' ')
        : 'No rooms are attached to it yet.';
      // On the building's own row: rename it, and build it — at the tier
      // this town has reached, which is the only tier it can be built at.
      // The town hall is the town: it stands where the town is placed.
      var isHall = D.sizes.hall_key && b.key === D.sizes.hall_key;
      var tile = p.plot && !isHall && mayEdit ? currentTile(p, b.key) : null;
      var placed = tile && townPiece(p, b.key);
      return '<li class="bline' + (on ? ' focus' : '') + '"' +
        ' data-key="' + escapeHtml(b.key) + '">' +
        '<div class="btop"><span class="bnm">' + escapeHtml(b.name) + ' — <b>' +
        escapeHtml(b.title) + '</b></span>' +
        (mayEdit ? '<button class="bico" data-rename="' + escapeHtml(b.key) + '" title="Rename it">&#9998;</button>' : '') +
        '<span class="bpts">' + b.points.toLocaleString() + '</span>' +
        (isHall && p.plot ? '<span class="bhall" title="The town is drawn as its hall; Move moves the town">Town hall</span>' : '') +
        (tile && !placed ? '<button class="bbuild" data-build="' + escapeHtml(b.key) +
          '" title="Put it on the map, inside this town">Build</button>' : '') +
        (placed ? lockButton(placed, b.key) +
          '<button class="bmove" data-movebld="' + escapeHtml(b.key) + '"' +
          (placed.k || placed.pk ? ' disabled title="Locked in place. Unlock it first."'
                                 : ' title="Click inside the town to move it there"') + '>Move</button>' +
          '<button class="bdel" data-delbld="' + escapeHtml(b.key) + '"' +
          (placed.k || placed.pk ? ' disabled title="Locked in place. Unlock it first."'
                                 : ' title="Take it off the map"') + '>Delete</button>' : '') +
        '</div>' +
        (on ? '<div class="brooms">Built by ' + rooms + '</div>' : '') +
        '</li>';
    }).join('') || '<li style="opacity:.7">Nothing built yet.</li>';

    // Every building can be renamed, which is why they are inputs rather than
    // text once the editor is open. Naming is free and moves no number.
    var nameFields = p.built.map(function (b) {
      return '<label>' + escapeHtml(b.given) + '</label>' +
        '<input class="bname" data-key="' + escapeHtml(b.key) + '" maxlength="48" value="' +
        escapeHtml(b.name) + '">';
    }).join('');

    // Whose town this is decides what the card offers. Editing somebody
    // else's is an administrative act and says so, rather than quietly looking
    // like editing your own.
    var mine = D.me && String(p.id) === String(D.me);
    card.innerHTML =
      '<h3>' + escapeHtml(p.name) +
        (mine ? ' <span class="yours">yours</span>' : '') + '</h3>' +
      '<div class="sub">' + escapeHtml(p.owner) + ' · #' + p.place + ' · ' +
        p.power.toLocaleString() + ' standing · ' + p.reached.toLocaleString() +
        ' people reached' +
        '<span id="dlpopn">' + popText(p) + '</span>' +
        (p.rank ? ' · ' + escapeHtml(p.flourish_label) + ' (' + escapeHtml(p.rank) + ')' : '') +
        '</div>' +
      breadthLine(p) +
      (p.blurb ? '<p class="blurb">' + escapeHtml(p.blurb) + '</p>' : '') +
      (p.has_image
        // Through this page's own base (a member's map reads its own routes),
        // and a card-sized copy rather than the original upload.
        ? '<div class="cardflag"><img alt="" decoding="async" src="' + D.ep.base +
          '/town/' + p.id + '/picture?w=640"></div>'
        : '') +
      '<ul>' + rows + '</ul>' +
      (p.plot ? '<div class="sub" style="margin-top:10px">At ' +
        p.plot.x.toFixed(1) + ', ' + p.plot.y.toFixed(1) + '</div>' : '') +
      (p.plot && mayEdit && D.sizes.walls ? wallSection(p) : '') +
      '<div class="acts">' +
        (D.ep.player ? (mine ? '<button data-act="edit" class="own">Customise your town</button>' : '') +
          (mine && D.ep.settle ? '<button data-act="move">Move my town</button>' : '') : (mine
          ? '<button data-act="edit" class="own">Customise your town</button><button data-act="findme">Find my traveller</button>'
          : '<button data-act="edit">Admin edit</button>') +
        '<button data-act="move">Move</button>' +
        '<button data-act="remove">Remove Town</button>') +
        '<button data-act="close">Close</button></div>' +
      '<div class="dledit">' +
        '<label>Town name</label>' +
        '<input id="tname" maxlength="48" value="' + escapeHtml(p.name) + '">' +
        '<label>Description</label>' +
        '<textarea id="tblurb" maxlength="600">' + escapeHtml(p.blurb) + '</textarea>' +
        '<label>Picture or GIF</label>' +
        '<input id="tpic" type="file" accept="image/png,image/jpeg,image/gif,image/webp">' +
        '<label style="margin-top:12px"><b>Your traveller on the roads</b></label>' +
        '<div class="dllook"><label>Head <input type="color" id="lhead" value="' + escapeHtml((p.look || {}).head || '#f2c9a0') + '"></label>' +
        '<label>Body <input type="color" id="lbody" value="' + escapeHtml((p.look || {}).body || '#ff3b3b') + '"></label>' +
        '<label>Horse <input type="color" id="lhorse" value="' + escapeHtml((p.look || {}).horse || '#7a4e2c') + '"></label></div>' +
        '<label>Pets following you (up to 3 cats and 3 dogs)</label>' +
        '<div id="lpets" class="dlpets"></div>' +
        '<input id="lpetq" placeholder="Search your cats and dogs by name\u2026">' +
        '<div id="lpetfound" class="dlpets found"></div>' +
        (nameFields ? '<label style="margin-top:12px"><b>Building names</b></label>' +
          nameFields : '') +
        '<div class="acts"><button data-act="save" class="own">Save</button>' +
        '<button data-act="clearpic">Remove picture</button></div>' +
        '<p class="cardmsg" id="dlcardmsg"></p>' +
      '</div>';
    card.hidden = false;
    document.body.classList.add('dlcardopen');
    var editor = card.querySelector('.dledit');
    var look = wireLook(card, p, id);
    card.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        var act = b.dataset.act;
        if (b.dataset.build) { buildFor(p, b.dataset.build); return; }
        if (b.dataset.rename) { renameBuilding(p, b.dataset.rename, b); return; }
        if (b.dataset.movebld) { moveBuilding(p, b.dataset.movebld); return; }
        if (b.dataset.delbld) { deleteBuilding(p, b.dataset.delbld); return; }
        if (b.dataset.lockbld) { lockBuilding(p, b.dataset.lockbld); return; }
        if (b.dataset.walls !== undefined) { setWalls(p, b.dataset.walls); return; }
        if (b.dataset.gate) {
          gating = {id: id, op: b.dataset.gate};
          frame.classList.add('placing');
          hint.textContent = b.dataset.gate === 'add'
            ? 'Click the wall where the gate should go. Escape to stop.'
            : 'Click the gate to take out. Escape to stop.';
          return;
        }
        if (act === 'close') { closeCard(); }
        else if (act === 'findme') { closeCard(); findTraveller(); }
        else if (act === 'move') { arm(id); closeCard(); }
        else if (act === 'remove') {
          var own = D.world.filter(function (q) { return q.t === String(id); }).length;
          var ask = 'Remove ' + p.name + ' from the map?' +
            (own ? '\n\nIts ' + own + (own === 1 ? ' building' : ' buildings') + ' will be removed too.' : '') +
            '\n\nWhat the town has earned is kept.';
          if (!window.confirm(ask)) return;
          place(id, null); closeCard();
        }
        else if (act === 'edit') { editor.classList.toggle('open'); }
        else if (act === 'clearpic') { saveTown(id, {clear_image: true}); }
        else if (act === 'save') {
          var names = {};
          card.querySelectorAll('.bname').forEach(function (i) {
            names[i.dataset.key] = i.value;
          });
          var pic = card.querySelector('#tpic');
          var chosen = pic && pic.files && pic.files[0];
          var payload = {
            name: card.querySelector('#tname').value,
            blurb: card.querySelector('#tblurb').value,
            building_names: names,
            look: look()
          };
          if (!chosen) { saveTown(id, payload); return; }
          var box = document.getElementById('dlcardmsg');
          if (['image/png', 'image/jpeg', 'image/gif', 'image/webp'].indexOf(chosen.type) < 0 ||
              !/\.(png|jpe?g|gif|webp)$/i.test(chosen.name)) {
            if (box) { box.classList.add('bad'); box.textContent = 'That is not a picture this takes. Use a PNG, JPG, GIF or WebP.'; }
            return;
          }
          if (chosen.size > D.sizes.picture_max) {
            if (box) {
              box.classList.add('bad');
              box.textContent = 'That picture is ' + Math.round(chosen.size / 1024) +
                'KB. The limit is ' + Math.round(D.sizes.picture_max / 1024) + 'KB, so ' +
                'nothing was saved. Pick a smaller one, or clear it and save the rest.';
            }
            return;
          }
          var reader = new FileReader();
          reader.onload = function () {
            payload.image = String(reader.result).split(',').pop();
            payload.content_type = chosen.type;
            saveTown(id, payload);
          };
          reader.readAsDataURL(chosen);
        }
      };
    });
  }

  // The traveller's look on the town card: three colours and the pets that
  // follow, searched among the owner's own cats and dogs. Returns a function
  // giving the look to save.
  function wireLook(card, p, id) {
    var chosen = ((p.look || {}).pets || []).slice(), box = card.querySelector('#lpets');
    var q = card.querySelector('#lpetq'), found = card.querySelector('#lpetfound'), timer = null;
    function count(k) { return chosen.filter(function (c) { return c.k === k; }).length; }
    function draw() {
      if (!box) return;
      box.innerHTML = chosen.map(function (c, i) {
        return '<button type="button" data-i="' + i + '">' + (c.k === 'dog' ? '\ud83d\udc36 ' : '\ud83d\udc31 ') +
          escapeHtml(c.n) + ' \u00d7</button>';
      }).join('') || '<small>None yet.</small>';
      box.querySelectorAll('button').forEach(function (b) {
        b.onclick = function () { chosen.splice(+b.dataset.i, 1); draw(); };
      });
    }
    function search() {
      if (!D.ep.pets) return;
      fetch(D.ep.pets + '?q=' + encodeURIComponent(q.value) + (D.ep.player ? '' : '&user_id=' + encodeURIComponent(id)))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          found.innerHTML = (res.pets || []).map(function (pet, i) {
            return '<button type="button" data-i="' + i + '">' + (pet.k === 'dog' ? '\ud83d\udc36 ' : '\ud83d\udc31 ') +
              escapeHtml(pet.n) + (pet.t ? ' <small>' + escapeHtml(pet.t) + '</small>' : '') + '</button>';
          }).join('') || '<small>No cats or dogs by that name.</small>';
          found.querySelectorAll('button').forEach(function (b) {
            b.onclick = function () {
              var pet = res.pets[+b.dataset.i];
              if (count(pet.k) >= (res.most || 3) || chosen.some(function (c) { return c.k === pet.k && c.n === pet.n; })) return;
              chosen.push({k: pet.k, n: pet.n}); draw();
            };
          });
        });
    }
    if (q) q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(search, 250); });
    if (q) q.addEventListener('focus', function () { if (!found.innerHTML) search(); });
    draw();
    return function () {
      return {head: card.querySelector('#lhead').value, body: card.querySelector('#lbody').value,
              horse: card.querySelector('#lhorse').value, pets: chosen};
    };
  }
  function saveTown(id, payload) {
    // Anything this says has to appear in the card. It used to go to the hint
    // bar in the far corner of the map, behind the card and often off screen,
    // so a refused save looked exactly like a button that did nothing.
    var say = function (text, bad) {
      var box = document.getElementById('dlcardmsg');
      if (box) { box.textContent = text; box.classList.toggle('bad', !!bad); }
      hint.textContent = text;
    };
    payload.user_id = id;
    say('Saving...');
    fetch(D.ep.town, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { say(res.error || 'That did not work.', true); return; }
      say('Saved. Reloading...');
      setTimeout(function () { window.location.reload(); }, 400);
    }).catch(function (err) { say(String(err), true); });
  }
  // --- building a town ---------------------------------------------------- //
  // A town's own buildings are the tiles its buildings have unlocked, at the
  // tier each has reached; picking one arms the pencil for that town, and the
  // server only takes it inside that town's area. Walls are not placed at all:
  // they are a style the town has, drawn along its area's edge.
  var building = null;   // town id the pencil is building for
  function townTier(p, key) {
    for (var i = 0; i < p.built.length; i++) if (p.built[i].key === key) return p.built[i].tier;
    return 0;
  }
  // A town builds each building it has earned at the tier it has reached in
  // it — never the tiers below: its buildings show where it is.
  // The tile showing `building` at the tier town `p` has reached now.
  function currentTile(p, building) {
    var tier = townTier(p, building);
    for (var i = 0; i < D.assets.length; i++) {
      var a = D.assets[i];
      if (a.layer === 'buildings' && a.building === building && a.tier === tier) return a;
    }
    return null;
  }
  // The piece a town already has for a building, if it has placed one.
  function townPiece(p, building) {
    for (var i = 0; i < D.world.length; i++) {
      var piece = D.world[i], a = piece.t === String(p.id) && assetById(piece.a);
      if (a && a.building === building) return piece;
    }
    return null;
  }
  // Moving a building: the next click inside the town's area puts it there.
  var relocating = null;   // {piece, town}
  function moveBuilding(p, key) {
    var piece = townPiece(p, key);
    if (!piece) return;
    relocating = {piece: piece, town: p};
    armedAsset = null; building = null;
    setTool('hand', true);
    selectOnly([piece.id]);
    hint.textContent = 'Click inside ' + p.name + '’s area to move it there. Escape to stop.';
  }
  function relocateTo(at) {
    var r = relocating;
    relocating = null;
    decorPost({action: 'move', piece_id: r.piece.id, x: Math.round(at.x * 1000) / 1000,
               y: Math.round(at.y * 1000) / 1000}, function () {
      r.piece.x = at.x; r.piece.y = at.y;
      redrawDecor();
      hint.textContent = 'Moved.';
      open(r.town.id);
    });
  }
  // Locking a building in place, from its row. A member locks and unlocks
  // their own; an admin's landmark is beyond them. An admin unlocks anything
  // with the same button, whoever locked it.
  // How widely the owner takes part, from the influence layer: the rooms
  // that are lively for them, how many of those they wrote in, and what that
  // does to the town's reach.
  // Population: the tiles the town's area covers, so it grows with its reach.
  function population(p) {
    var t = (D.influence || []).filter(function (x) { return String(x.id) === String(p.id); })[0];
    return t && t.cells ? Math.round(t.cells * (D.sizes.pop_per_cell || 0)) : 0;
  }
  function popText(p) {
    var n = population(p);
    return n ? ' · population <b>' + n.toLocaleString() + '</b>' : '';
  }
  // The areas arrive after the page (and after a card opened from ?mine=1).
  function refreshPop() {
    var el = document.getElementById('dlpopn');
    if (el && openId && byId[openId]) el.innerHTML = popText(byId[openId]);
  }
  function breadthLine(p) {
    var t = (D.influence || []).filter(function (x) { return String(x.id) === String(p.id); })[0];
    var b = t && t.breadth;
    if (!b || !b.open) return '';
    var plus = Math.round((b.boost - 1) * 100);
    return '<div class="sub" title="Lively rooms: channels where other people talked recently and this town’s owner can write. Taking part in more of them makes the town’s area reach further.">' +
      'Talks in ' + b.joined + ' of ' + b.open + ' lively rooms' +
      (plus > 0 ? ' · reach +' + plus + '%' : '') + '</div>';
  }
  function lockButton(piece, key) {
    var landmark = piece.k, held = piece.k || piece.pk;
    var title = landmark
      ? (D.ep.player ? 'A landmark the server’s admins set. Only they can unlock it.'
                     : 'A landmark. Click to unlock it.')
      : held ? 'Locked in place. Click to unlock it.'
             : 'Lock it in place, so it is not moved or deleted by accident. It still moves with the town.';
    return '<button class="bico block' + (held ? ' on' : '') + '" data-lockbld="' + escapeHtml(key) + '"' +
      (landmark && D.ep.player ? ' disabled' : '') + ' title="' + title + '">' +
      (held ? '&#128274;' : '&#128275;') + '</button>';
  }
  function lockBuilding(p, key) {
    var piece = townPiece(p, key);
    if (!piece) return;
    if (piece.k && D.ep.player) {
      hint.textContent = 'That is a landmark the server’s admins set. Only they can unlock it.';
      return;
    }
    var unlock = piece.k || piece.pk;
    decorPost({action: unlock ? 'unlock' : (D.ep.player ? 'lock' : 'pin'), piece_ids: [piece.id]},
      function () {
        if (unlock) { piece.k = false; piece.pk = false; } else { piece.pk = true; }
        redrawDecor(); placeMarks();
        hint.textContent = unlock ? 'Unlocked.' : 'Locked in place.';
        open(p.id);
      });
  }
  function deleteBuilding(p, key) {
    var piece = townPiece(p, key);
    if (!piece) return;
    decorPost({action: 'remove_many', piece_ids: [piece.id]}, function () {
      D.world = D.world.filter(function (q) { return q.id !== piece.id; });
      delete sel[piece.id];
      redrawDecor(); selChanged();
      hint.textContent = 'Taken off the map.';
      open(p.id);
    });
  }
  function wallSection(p) {
    var walls = [['', 'None'], ['palisade', 'Palisade'], ['stone', 'Stone']].map(function (w) {
      return '<button data-walls="' + w[0] + '" class="' + ((p.walls || '') === w[0] ? 'own' : '') + '">' + w[1] + '</button>';
    }).join('');
    var gates = p.walls
      ? '<div class="acts"><button data-gate="add" title="Then click the wall where the gate goes">Add a gate</button>' +
        (p.gates ? '<button data-gate="remove" title="Then click the gate to take out">Remove a gate</button>' : '') +
        '</div>' + (p.gates ? '<span class="sub">' + p.gates + (p.gates === 1 ? ' gate' : ' gates') + '</span>' : '')
      : '';
    return '<div class="dlbuild"><div class="dlwallrow"><span class="sub">Walls round its area</span>' +
      '<div class="acts">' + walls + '</div>' + gates + '</div></div>';
  }
  // Renaming in place: the row's name becomes a field; Enter or leaving it
  // saves, Escape puts it back. Naming is free and moves no number.
  function renameBuilding(p, key, button) {
    var row = button.closest('.bline'), label = row && row.querySelector('.bnm');
    var b = p.built.filter(function (x) { return x.key === key; })[0];
    if (!label || !b) return;
    var field = document.createElement('input');
    field.className = 'brename'; field.maxLength = 48; field.value = b.name;
    label.replaceWith(field);
    field.focus(); field.select();
    var done = false;
    function finish(save) {
      if (done) return;
      done = true;
      if (!save || field.value.trim() === b.name) { open(p.id); return; }
      var names = {};
      p.built.forEach(function (x) {
        var v = x.key === key ? field.value.trim() : x.name;
        if (v && v !== x.given) names[x.key] = v;
      });
      fetch(D.ep.town, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: p.id, building_names: names})
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (res.ok) b.name = field.value.trim() || b.given;
        else hint.textContent = res.error || 'That name was not saved.';
        open(p.id);
      });
    }
    field.addEventListener('keydown', function (ev) {
      ev.stopPropagation();
      if (ev.key === 'Enter') finish(true);
      if (ev.key === 'Escape') finish(false);
    });
    field.addEventListener('blur', function () { finish(true); });
  }
  function buildFor(p, key) {
    var tileId = (currentTile(p, key) || {}).id;
    if (!tileId) { hint.textContent = 'There is no drawing of that building at this tier yet.'; return; }
    if (layerState.edit !== 'buildings') { layerState.edit = 'buildings'; applyLayers(); }
    // One of each: a town that has its tavern already is shown it, not given
    // a second one.
    var a = assetById(tileId), placed = a && townPiece(p, a.building);
    if (placed) {
      setTool('hand'); selectOnly([placed.id]);
      view.x = frame.clientWidth / 2 - placed.x / 100 * nat.w * view.k;
      view.y = frame.clientHeight / 2 - placed.y / 100 * nat.h * view.k;
      clamp(); apply();
      kitSay(p.name + ' has this already. Drag it to move it.');
      return;
    }
    armedAsset = tileId; mix = [tileId];
    building = p.id;
    setTool('pencil', true);
    frame.classList.add('placing');
    hint.textContent = 'Building ' + a.name.split(' · ')[0] + ' for ' + p.name +
      ': click inside its area. Escape to stop.';
  }
  // A gate in a town's wall: the click is snapped to the town's own wall on
  // the server, which cuts the wall there and draws a gateway.
  var gating = null;
  function gateAt(g, at) {
    var body = {user_id: g.id};
    body[g.op === 'add' ? 'gate_add' : 'gate_remove'] = at;
    fetch(D.ep.town, {method: 'POST', headers: {'Content-Type': 'application/json'},
                      body: JSON.stringify(body)})
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) { hint.textContent = res.error || 'That did not work.'; notify([res.error || 'That did not work.']); return; }
        var p = byId[g.id];
        if (p) p.gates = Math.max(0, (p.gates || 0) + (g.op === 'add' ? 1 : -1));
        gating = null;
        frame.classList.remove('placing');
        hint.textContent = g.op === 'add' ? 'Gate built.' : 'Gate taken out.';
        if (p && openId === g.id) open(g.id);
        if (typeof loadInfluence === 'function') loadInfluence();
      })
      .catch(function (err) { hint.textContent = String(err); });
  }
  function setWalls(p, style) {
    fetch(D.ep.town, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: p.id, walls: style})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { hint.textContent = res.error || 'That did not work.'; return; }
      p.walls = style;
      card.querySelectorAll('[data-walls]').forEach(function (b) {
        b.classList.toggle('own', b.dataset.walls === style);
      });
      // Walls are worked out with the areas (shared where walled towns meet).
      if (typeof loadInfluence === 'function') loadInfluence();
    });
  }

  function inOpenArea(clientX, clientY) {
    var g = openId && document.querySelector('#dltinfl > g[data-town="' + openId + '"]');
    var fill = g && g.querySelector('path');
    var svg = fill && fill.ownerSVGElement;
    if (!svg || typeof terr === 'undefined' || !terr.world) return false;
    var b = frame.getBoundingClientRect();
    var pt = svg.createSVGPoint();
    pt.x = (clientX - b.left - view.x) / (nat.w * view.k) * terr.world.cells_w;
    pt.y = (clientY - b.top - view.y) / (nat.h * view.k) * terr.world.cells_h;
    try { return fill.isPointInFill(pt); } catch (e) { return false; }
  }

  // The open town's area of influence is the one drawn; closing the town, or
  // clicking away from it, takes its area with it.
  function markInfluence() {
    world.querySelectorAll('#dltinfl > g').forEach(function (g) {
      g.classList.toggle('on', !!openId && g.dataset.town === String(openId));
    });
  }
  function closeCard() {
    card.hidden = true; openId = null;
    document.body.classList.remove('dlcardopen');
    markInfluence();
    world.querySelectorAll('.dltown.on').forEach(function (n) {
      n.classList.remove('on');
    });
  }

  // --- placing ----------------------------------------------------------- //
  var armed = null;
  function arm(id) {
    armed = id;
    frame.classList.add('placing');
    hint.textContent = 'Click the map to place ' + byId[id].name;
    renderList();
  }
  // A member's own town: placed or moved from the top bar, when the server
  // lets members choose where their town stands.
  var settleBtn = document.getElementById('dlsettle');
  function settleLabel() {
    var me = D.me && byId[D.me];
    settleBtn.hidden = !(D.ep.player && D.ep.settle && me);
    if (me) settleBtn.textContent = me.plot ? '🏠 Move my town' : '🏠 Place my town';
  }
  settleBtn.onclick = function () {
    if (!D.me || !byId[D.me]) return;
    if (armed === D.me) { putDown(); return; }
    closeDrawers();
    arm(D.me);
    hint.textContent = (byId[D.me].plot ? 'Click where your town should move to' : 'Click where your town should stand') +
      '. Escape to stop.';
  };
  // A notice the map cannot hide: top centre, above the drawers, until it is
  // dismissed or a while has passed.
  var notice = document.createElement('div');
  notice.className = 'dlnotice';
  frame.appendChild(notice);
  function notify(lines) {
    notice.innerHTML = lines.map(function (l) { return '<p>' + escapeHtml(l) + '</p>'; }).join('') +
      '<button title="Dismiss">&times;</button>';
    notice.querySelector('button').onclick = function () { notice.classList.remove('on'); };
    notice.classList.add('on');
    clearTimeout(notify.t);
    notify.t = setTimeout(function () { notice.classList.remove('on'); }, 14000);
  }
  function place(id, point) {
    if (!D.ep.settle) return;
    fetch(D.ep.settle, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(point
        ? {user_id: id, x: point.x, y: point.y}
        : {user_id: id, remove: true})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) {
        // Said where it is seen, and still armed: the next click tries again.
        hint.textContent = res.error || 'That did not work.';
        notify([res.error || 'That did not work.']);
        return;
      }
      byId[id].plot = point ? {x: res.x, y: res.y} : null;
      armed = null;
      frame.classList.remove('placing');
      hint.textContent = point ? 'Placed.' : 'Removed from the map.';
      if (point && res.moved && res.moved.length) {
        // Everything in the town came with it, at the same offset from the hall.
        var at = {};
        res.moved.forEach(function (m) { at[m.piece_id] = m; });
        D.world.forEach(function (q) { if (at[q.id]) { q.x = at[q.id].x; q.y = at[q.id].y; } });
        redrawDecor();
        hint.textContent = 'Moved, with ' + res.moved.length +
          (res.moved.length === 1 ? ' thing' : ' things') + ' that belong to it.';
      }
      if (res.notes && res.notes.length) notify(res.notes);
      if (!point) {
        // Its buildings went with it, on the server; and on the page.
        D.world = D.world.filter(function (q) { return q.t !== String(id); });
        redrawDecor();
      }
      redraw(); renderList(); settleLabel();
      // A town's area is its own overlay, worked out from where the town is:
      // moved or removed, the old area has to go with it — and its roads.
      if (typeof loadInfluence === 'function') loadInfluence();
      if (typeof loadRoads === 'function') loadRoads();
    });
  }
  frame.addEventListener('click', function (ev) {
    if (swallowClick) { swallowClick = false; return; }
    if (moved > 6 || !nat.w) return;
    if (typeof hidePop === 'function') hidePop();
    var b = frame.getBoundingClientRect();
    if (relocating) {
      relocateTo({x: ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100,
                  y: ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100});
      return;
    }
    if (gating) {
      gateAt(gating, {x: ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100,
                      y: ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100});
      return;
    }
    var at = {
      x: ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100,
      y: ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100
    };
    // Settling a town and placing decor are the same gesture on the same
    // surface, so only one of them may ever be armed at a time.
    if (armed) { place(armed, at); return; }
    if (armedAsset && tool === 'pencil') { placeDecor(at); return; }
    if (armedAsset && tool === 'brush') return;
    if (typeof terr !== 'undefined' && terr.armed) return;
    // The map's own buttons sit inside the frame; pressing one is not
    // clicking the map.
    if (ev.target.closest && ev.target.closest('.dlzoom, .dlhint')) return;
    // Nothing armed and nothing under the pointer: let go — of a held piece
    // and of the open town, whose area goes with it.
    var near = tool === 'hand' && nearestPiece(ev.clientX, ev.clientY, 10);
    if (near) { selectOnly([near.id]); showTownOf(near); return; }
    if (selIds().length) selectOnly([]);
    // Inside the open town's own area is still that town; only outside it
    // is clicking away.
    if (openId && !inOpenArea(ev.clientX, ev.clientY)) { closeCard(); }
  });

  // --- the list ---------------------------------------------------------- //
  var search = document.getElementById('dlsearch');
  function renderList() {
    var q = (search.value || '').toLowerCase();
    var hit = D.people.filter(function (p) {
      return !q || p.name.toLowerCase().indexOf(q) >= 0;
    });
    // Who is not on the map is the admins' business (they place towns from
    // it); a member's list is the towns there are to visit.
    var waiting = D.ep.player ? [] : hit.filter(function (p) { return !p.plot; });
    var placed = hit.filter(function (p) { return p.plot; });
    function group(title, rows) {
      if (!rows.length) return '';
      return '<div class="dlgroup">' + title + ' (' + rows.length + ')</div>' +
        rows.map(function (p) {
          return '<button class="dlrow' + (armed === p.id ? ' armed' : '') +
            '" data-id="' + p.id + '"><span class="n">' + escapeHtml(p.name) +
            '</span><span class="p">' + p.power.toLocaleString() + '</span></button>';
        }).join('');
    }
    list.innerHTML = group('Not on the map', waiting) + group('Placed', placed);
    list.querySelectorAll('.dlrow').forEach(function (row) {
      row.onclick = function () {
        var p = byId[row.dataset.id];
        if (p.plot) { open(p.id); }
        else if (!D.ep.player) { arm(p.id); }
      };
    });
  }
  search.addEventListener('input', renderList);
  // The zoom controls have to stay reachable whichever drawer is open, so
  // they step aside rather than hide behind it.
  var zoombar = document.querySelector('.dlzoom');
  function placeZoom() {
    zoombar.classList.toggle('shifted', drawer.classList.contains('open'));
  }
  // One drawer at a time. Closing a drawer puts its tools down too: a brush
  // still armed under the toolkit painted wherever a piece was being placed.
  function closeDrawers(keep) {
    if (keep !== 'list') drawer.classList.remove('open');
    if (keep !== 'kit' && kitDrawer.classList.contains('open')) closeKit();
    if (keep !== 'terr' && typeof terrClose === 'function') terrClose();
    if (keep !== 'list' && armed) {
      armed = null; frame.classList.remove('placing');
      hint.textContent = 'Drag to move, scroll to zoom'; renderList();
    }
    placeZoom();
  }
  document.getElementById('dltoggle').onclick = function () {
    var opening = !drawer.classList.contains('open');
    if (opening) closeDrawers('list');
    drawer.classList.toggle('open', opening);
    placeZoom();
  };
  document.getElementById('dlclose').onclick = function () {
    drawer.classList.remove('open');
    placeZoom();
  };


  // --- the toolkit ------------------------------------------------------- //
  // Two things it does, and they are one gesture each: pick something from the
  // library and click the ground to put it there, or click a piece already on
  // the ground to take hold of it. Everything else — size, mirror, remove —
  // acts on whatever is held.
  //
  // Positions are percentages of the base image, exactly like a town's, so a
  // redrawn map at another resolution moves nothing that has been placed.
  var kitDrawer = document.getElementById('dlkitdrawer'),
      kitGrid = document.getElementById('dlkitgrid'),
      kitMsg = document.getElementById('dlkitmsg'),
      kitScale = document.getElementById('dlkitscale');
  var armedAsset = null, heldPiece = null, pieces = {};

  function kitSay(text, bad) {
    if (!kitMsg) return;
    kitMsg.textContent = text || '';
    kitMsg.classList.toggle('bad', !!bad);
  }

  function assetUrl(id) {
    return D.ep.base + '/asset/' + id;
  }

  // Hundreds of tiles in one grid is a wall, so the kit shows one category at
  // a time; which one survives a reload as a per-viewer convenience.
  var kitCat = document.getElementById('dlkitcat');
  function editLayer() { return world.dataset.edit || 'objects'; }
  // Buildings are never in the toolkit: a town builds its own, from its card,
  // at the tier it has earned. The toolkit is for dressing the world.
  function kitAssets() {
    // A member decorates with what members may place, on any layer; their
    // buildings go up from their town's card.
    if (D.ep.player) return D.assets.filter(function (a) { return a.pl && a.layer !== 'buildings'; });
    var layer = editLayer() === 'buildings' ? 'objects' : editLayer();
    return D.assets.filter(function (a) { return a.layer === layer; });
  }
  // What this viewer may pick up: an admin anything, a member their own town's
  // things that nobody has locked.
  function mayTouch(p) {
    return !D.ep.player || (!!p && String(p.t || '') === String(D.me) && !p.k);
  }
  function fillKitCats() {
    if (!kitCat) return;
    var cats = [];
    kitAssets().forEach(function (a) { if (cats.indexOf(a.cat) < 0) cats.push(a.cat); });
    kitCat.innerHTML = cats.map(function (c) {
      return '<option>' + escapeHtml(c || 'Uncategorised') + '</option>';
    }).join('');
    try { var keptCat = window.localStorage.getItem('dl-kit-cat-' + editLayer());
          if (keptCat && cats.indexOf(keptCat) >= 0) kitCat.value = keptCat; } catch (e) {}
  }
  if (kitCat) kitCat.onchange = function () {
    try { window.localStorage.setItem('dl-kit-cat-' + editLayer(), kitCat.value); } catch (e) {}
    renderKit();
  };
  function assetById(id) {
    for (var i = 0; i < D.assets.length; i++) if (D.assets[i].id === id) return D.assets[i];
    return null;
  }
  // The slider offers what the tile allows; a fixed-size tile gets no slider.
  // The server clamps whatever arrives, so this is a courtesy, not the rule.
  function fitSlider(assetId) {
    var a = assetById(assetId);
    if (!kitScale) return;
    var lo = a ? a.lo : 1, hi = a ? a.hi : 1;
    kitScale.min = lo; kitScale.max = hi;
    kitScale.disabled = lo === hi;
    var v = parseFloat(kitScale.value) || 1;
    kitScale.value = Math.min(hi, Math.max(lo, v));
  }

  function renderKit() {
    if (!kitAssets().length) {
      kitGrid.innerHTML = '<p class="dlkitempty">Nothing on this layer that admins ' +
        'can place yet.</p>';
      return;
    }
    var shown = kitCat ? kitCat.value : null;
    kitGrid.innerHTML = kitAssets().filter(function (a) {
      return shown === null || (a.cat || 'Uncategorised') === shown;
    }).map(function (a) {
      return '<button class="dlkititem' + (a.px ? ' px' : '') + (a.lk ? ' locked' : '') +
        (mix.indexOf(a.id) >= 0 || armedAsset === a.id ? ' armed' : '') + '" data-asset="' + a.id + '"' +
        (a.lk ? ' title="' + escapeHtml(a.why || 'Not unlocked yet') + '"' : '') + '>' +
        // With its first picture's id: a redrawn tile gets a new address, so
        // no browser keeps the old picture it cached for a week.
        '<img alt="" loading="lazy" src="' + assetUrl(a.id) + (a.vw && Object.keys(a.vw)[0] ? '?v=' + Object.keys(a.vw)[0] : '') + '">' +
        '<span>' + escapeHtml(a.name) + '</span></button>';
    }).join('');
    kitGrid.querySelectorAll('.dlkititem').forEach(function (el) {
      el.onclick = function (ev) {
        var id = el.dataset.asset;
        if (el.classList.contains('locked')) { kitSay(el.title + '.'); return; }
        building = null;
        if (ev.shiftKey && armedAsset) {
          // A mix for the brush: every stroke picks among these at random.
          var at = mix.indexOf(id);
          if (at >= 0 && mix.length > 1) mix.splice(at, 1); else if (at < 0) mix.push(id);
          if (tool !== 'brush') setTool('brush');
        } else if (armedAsset === id && mix.length <= 1) {
          armedAsset = null; mix = [];
        } else {
          armedAsset = id; mix = [id];
          if (tool !== 'pencil' && tool !== 'brush') setTool('pencil');
        }
        if (armedAsset && mix.indexOf(armedAsset) < 0) armedAsset = mix[0] || null;
        sel = {}; selChanged();
        fitSlider(armedAsset);
        frame.classList.toggle('placing', !!armedAsset && (tool === 'pencil' || tool === 'brush'));
        kitSay(!armedAsset ? '' : tool === 'brush'
          ? (mix.length > 1 ? 'Brushing a mix of ' + mix.length + '. Drag on the map.' : 'Drag on the map to brush it.')
          : 'Click the map to place it.');
        renderKit();
      };
    });
  }

  // The picture a piece shows: its own, unless its tile now offers only one
  // other (a building drawn with its uploaded picture, placed before or just now).
  function pieceVariant(piece) {
    var a = typeof assetById === 'function' ? assetById(piece.a) : null, keys = a && a.vw ? Object.keys(a.vw) : [];
    // A tile drawn with one picture is drawn with it whatever the piece asks
    // for - and asking for none (a town's building moved up to the tier it has
    // reached now, a toolkit preview) is not "its first variant": a town
    // building shown as its uploaded painting has that as its only picture,
    // and the first variant is the generated drawing it stands in for.
    return (keys.length === 1 && (!piece.v || !(piece.v in a.vw))) ? keys[0] : piece.v;
  }
  function pieceWidth(piece) {
    // A percentage of the base image, so decor shrinks with the coastline the
    // same way a town does. `nat.w` is 0 until the map image has loaded, and
    // dividing by 1 then made every piece twenty-eight times the width of the
    // world — so a piece drawn before the image arrives is redrawn after it.
    if (!nat.w) return null;
    // A tile with a known natural size is drawn at it: its own width in map
    // cells, times the piece's size. That is what px-per-cell is for — a 32px
    // pack's tree and a 16px pack's tree come out the same size. Anything else
    // falls back to the old fixed size.
    var a = typeof assetById === 'function' ? assetById(piece.a) : null;
    var wc = a ? ((a.vw && a.vw[piece.v]) || a.wc) : 0;
    if (wc && D.cells_w) return (wc * piece.s / D.cells_w * 100) + '%';
    return (D.decorsize * WS * piece.s / nat.w * 100) + '%';
  }


  // --- the sun, and baked shadows ----------------------------------------- //
  // One sun for the whole map, from the viewer's own clock (or a time of day
  // set in the panel, dodoland_time_of_day): it rises in the east, so morning
  // shadows fall to the left and long, at midday short and behind, in the
  // evening to the right; at night a faint moon. Every shadow comes from it.
  function sunState() {
    var S = D.sizes.sun || {}, mode = S.mode || 'auto', h;
    if (mode === 'auto') { var now = new Date(); h = now.getHours() + now.getMinutes() / 60; }
    else h = {morning: 8, noon: 13, afternoon: 16, evening: 19, night: 23}[mode] || 13;
    h = Math.round(h * 2) / 2;   // a new sun every half hour, not every frame
    var rise = S.rise == null ? 6 : S.rise, set = S.set == null ? 20 : S.set;
    var base = S.strength == null ? 0.38 : S.strength, noon = S.length == null ? 0.35 : S.length;
    var out;
    if (h > rise && h < set) {
      var p = (h - rise) / (set - rise), elev = Math.sin(Math.PI * p);
      var len = Math.min(S.longest == null ? 1.3 : S.longest, noon / Math.max(elev, 0.12));
      out = {x: -Math.cos(Math.PI * p) * (S.swing == null ? 1 : S.swing), y: -(0.35 + 0.65 * elev) * 0.6,
             len: len, strength: base * (0.6 + 0.4 * Math.min(1, elev * 2)), night: false};
    } else {
      out = {x: -0.3, y: -0.45, len: 0.5, strength: base * (S.night == null ? 0.3 : S.night), night: true};
    }
    out.contact = (S.contact == null ? 0.35 : S.contact) * (out.night ? 0.7 : 1);
    out.blur = S.blur == null ? 0.03 : S.blur;
    out.key = mode + '|' + h;
    return out;
  }
  // A picture's shadow, made once per picture (and mirror) per sun. Height is
  // measured per column from that column's lowest painted pixel, so whatever
  // lies on the ground (a paved yard, a plinth's step) casts nothing, and only
  // what rises casts, behind it and away from the sun - never out in front,
  // which is what made things float. A soft rim darkens the ground right at
  // the base. Small (it is blurred), as a WebP blob, behind the picture.
  var shadows = {}, shadowed = [];
  function shadowFor(src, flip, done) {
    var sun = sunState(), key = src + (flip ? '|f' : '') + '|' + sun.key, hit = shadows[key];
    if (hit && hit.url) { done(hit); return; }
    if (hit) { hit.wait.push(done); return; }
    hit = shadows[key] = {wait: [done]};
    var im = new Image();
    im.decoding = 'async';
    im.onload = function () {
      try {
        var sc = Math.min(1, 220 / Math.max(im.naturalWidth || 1, im.naturalHeight || 1));
        var w = Math.max(1, Math.round((im.naturalWidth || 100) * sc)), h = Math.max(1, Math.round((im.naturalHeight || 100) * sc));
        var sil = document.createElement('canvas'); sil.width = w; sil.height = h;
        var sx = sil.getContext('2d');
        if (flip) { sx.translate(w, 0); sx.scale(-1, 1); }
        sx.drawImage(im, 0, 0, w, h);
        var px = sx.getImageData(0, 0, w, h).data, low = [], top = [];
        for (var x = 0; x < w; x++) {
          low[x] = -1; top[x] = -1;
          for (var y = h - 1; y >= 0; y--) if (px[(y * w + x) * 4 + 3] > 96) { low[x] = y; break; }
          for (var y2 = 0; y2 < h; y2++) if (px[(y2 * w + x) * 4 + 3] > 96) { top[x] = y2; break; }
        }
        var dx = sun.x * sun.len, dy = sun.y * sun.len;
        var blur = Math.max(0.6, sun.blur * h), pad = Math.ceil(blur * 3) + 2;
        var reachL = Math.ceil(Math.max(0, -dx) * h) + 1, reachR = Math.ceil(Math.max(0, dx) * h) + 1;
        var cv = document.createElement('canvas');
        cv.width = w + reachL + reachR + pad * 2; cv.height = h + pad * 2;
        var ox = pad + reachL, oy = pad;
        var shape = document.createElement('canvas'); shape.width = cv.width; shape.height = cv.height;
        var sc2 = shape.getContext('2d');
        sc2.strokeStyle = '#000'; sc2.lineWidth = 1.6; sc2.lineCap = 'round';
        sc2.beginPath();
        for (var c = 0; c < w; c++) {
          if (low[c] < 0) continue;
          var z = low[c] - top[c];
          sc2.moveTo(ox + c + 0.5, oy + low[c] + 0.5);
          sc2.lineTo(ox + c + 0.5 + dx * z, oy + low[c] + 0.5 + dy * z);
        }
        sc2.stroke();
        var ctx = cv.getContext('2d');
        ctx.filter = 'blur(' + blur.toFixed(1) + 'px)';
        ctx.globalAlpha = sun.strength;
        ctx.drawImage(shape, 0, 0);
        // The rim where it meets the ground.
        if (sun.contact > 0) {
          var rim = document.createElement('canvas'); rim.width = cv.width; rim.height = cv.height;
          var rc = rim.getContext('2d');
          rc.fillStyle = '#000';
          for (var c2 = 0; c2 < w; c2++) if (low[c2] >= 0) rc.fillRect(ox + c2 - 0.5, oy + low[c2] - 1, 2, 3);
          ctx.filter = 'blur(' + Math.max(0.6, blur * 0.6).toFixed(1) + 'px)';
          ctx.globalAlpha = sun.contact;
          ctx.drawImage(rim, 0, 0);
        }
        cv.toBlob(function (blob) {
          if (!blob) return;
          hit.url = URL.createObjectURL(blob);
          // Where it sits against the picture's own box, in percent of it.
          hit.left = -ox / w * 100; hit.top = -oy / h * 100;
          hit.width = cv.width / w * 100; hit.height = cv.height / h * 100;
          var wait = hit.wait; hit.wait = [];
          wait.forEach(function (f) { f(hit); });
        }, 'image/webp', 0.9);
      } catch (e) { hit.failed = true; }
    };
    im.src = src;
  }
  function shadowsOn() {
    var S = D.sizes.sun || {};
    return (S.strength == null ? 0.38 : S.strength) > 0 || (S.contact == null ? 0.35 : S.contact) > 0;
  }
  // Put a picture's shadow behind it in el; remembered, so a new sun can redo it.
  function addShadow(el, src, flip) {
    if (!shadowsOn() || !el) return;
    el._shadow = {src: src, flip: !!flip};
    if (shadowed.indexOf(el) < 0) shadowed.push(el);
    shadowFor(src, flip, function (s) {
      var old = el.querySelector(':scope > img.dlshadow');
      var sh = old || document.createElement('img');
      sh.className = 'dlshadow'; sh.alt = ''; sh.src = s.url;
      sh.style.left = s.left + '%'; sh.style.top = s.top + '%';
      sh.style.width = s.width + '%'; sh.style.height = s.height + '%';
      if (!old) el.appendChild(sh);
    });
  }
  // An inline drawing's shadow (a generated town, a house, a walker): the
  // drawing as an svg picture, shadowed like any other, one per drawing.
  var svgPictures = {};
  function svgPicture(box, body) {
    var key = box.join(',') + '|' + body;
    if (!svgPictures[key]) {
      var w = Math.round(box[2] * 12), h = Math.round(box[3] * 12);
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + box.join(' ') + '" width="' + w +
        '" height="' + h + '">' + body + '</svg>';
      svgPictures[key] = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    }
    return svgPictures[key];
  }
  // A new sun: every shadow redone (and the forests, whose trees carry theirs).
  var sunKey = sunState().key;
  setInterval(function () {
    var now = sunState().key;
    if (now === sunKey) return;
    sunKey = now;
    Object.keys(shadows).forEach(function (k) { if (shadows[k].url) URL.revokeObjectURL(shadows[k].url); });
    shadows = {};
    shadowed = shadowed.filter(function (el) { return el.isConnected; });
    shadowed.forEach(function (el) { addShadow(el, el._shadow.src, el._shadow.flip); });
    if (typeof forestRedrawAll === 'function') forestRedrawAll();
  }, 60000);


  // --- night --------------------------------------------------------------- //
  // From the same clock as the sun: dusk comes on around sunset, full night,
  // then dawn. One canvas over the map at half the screen's resolution: filled
  // with the night, then lights cut out of it (lamps, lanterns, campfires -
  // any tile with a light - and the lit windows of towns that were active
  // lately), then a warm glow laid over what they light. Drawn only at night,
  // once per frame at most, as the view moves; by day it does nothing.
  function nightState() {
    var S = D.sizes.sun || {}, N = D.sizes.night || {}, mode = S.mode || 'auto', h;
    var set = S.set == null ? 20 : S.set;
    if (mode === 'auto') { var now = new Date(); h = now.getHours() + now.getMinutes() / 60; }
    else h = {morning: 8, noon: 13, afternoon: 16, evening: set - 0.1, night: 23}[mode] || 13;
    // Dusk through pink, purple and violet into the night's blue, dawn from
    // it into a warm orange (nightlights.py, skyAt).
    return skyAt(S, N, h);
  }
  function mixHex(a, b, t) {
    var pa = [1, 3, 5].map(function (i) { return parseInt(a.slice(i, i + 2), 16); });
    var pb = [1, 3, 5].map(function (i) { return parseInt(b.slice(i, i + 2), 16); });
    return pa.map(function (v, i) { return Math.round(v + (pb[i] - v) * t); });
  }
  // A soft round light, once per colour: white for cutting the dark, the
  // light's own colour for its glow.
  var stamps = {};
  function stamp(rgb) {
    var key = rgb.join(',');
    if (stamps[key]) return stamps[key];
    var c = document.createElement('canvas'); c.width = c.height = 256;
    var x = c.getContext('2d'), g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
    g.addColorStop(0, 'rgba(' + key + ',1)'); g.addColorStop(0.35, 'rgba(' + key + ',.7)');
    g.addColorStop(0.7, 'rgba(' + key + ',.22)'); g.addColorStop(1, 'rgba(' + key + ',0)');
    x.fillStyle = g; x.fillRect(0, 0, 256, 256);
    return (stamps[key] = c);
  }
  // A picture's own lights (lit windows, lanterns, fires), found once per
  // picture by findLights (nightlights.py) - the same finder the lights editor
  // shows, so what a tile lights by itself is what its editor said. Null if
  // it has none.
  var windowMaps = {};
  function windowsOf(src) {
    if (windowMaps[src] !== undefined) return windowMaps[src];
    windowMaps[src] = null;
    var im = new Image();
    im.onload = function () {
      try {
        windowMaps[src] = findLights(im, D.sizes.night || {});
        if (windowMaps[src]) nightSoon();
      } catch (e) { windowMaps[src] = null; }
    };
    im.src = src;
    return null;
  }
  var nightCv = document.createElement('canvas'), nightQueued = false;
  nightCv.className = 'dlnight';
  frame.appendChild(nightCv);
  // keep: only the walkers moved (or a name came or went), so the rest of the
  // night is as it was.
  function nightSoon(keep) {
    if (!keep) nightCache = null;
    if (nightQueued) return;
    nightQueued = true;
    requestAnimationFrame(function () { nightQueued = false; drawNight(); });
  }
  // A town's name shows while it is pointed at, and is lifted out of the
  // night only while it shows: redrawn once it has faded in or out.
  var nameHover = null;
  world.addEventListener('pointerover', function (ev) {
    if (!nightOn) return;
    var t = ev.target && ev.target.closest ? ev.target.closest('.dltown') : null;
    if (t === nameHover) return;
    nameHover = t;
    setTimeout(function () { nightSoon(true); }, 140);
  });
  // The tiers of the town buildings, for the lights put on their drawings.
  function tierAsset(key, tier) {
    for (var i = 0; i < D.assets.length; i++) {
      var a = D.assets[i];
      if (a.building === key && +a.tier === +tier) return a;
    }
    return null;
  }
  var nightOn = false, nightCache = null;
  function drawNight() {
    var st = nightState();
    nightOn = Math.max(st.at(0).a, st.at(1).a) >= 0.01;
    world.classList.toggle('dldark', nightOn);
    if (!nightOn || !nat.w) { nightCv.style.display = 'none'; return; }
    nightCv.style.display = 'block';
    var R = 0.5, W = frame.clientWidth, H = frame.clientHeight;
    var w = Math.max(1, Math.round(W * R)), h = Math.max(1, Math.round(H * R));
    if (nightCv.width !== w || nightCv.height !== h) { nightCv.width = w; nightCv.height = h; }
    var c = nightCv.getContext('2d'), N = D.sizes.night || {};
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
    c.clearRect(0, 0, w, h);
    // The sky: across the screen from the sun's side, which is a little
    // behind the far side - pinker at dusk in the west, oranger at dawn in the east.
    var sky = c.createLinearGradient(st.sunLeft ? 0 : w, 0, st.sunLeft ? w : 0, 0);
    for (var gi = 0; gi <= 4; gi++) {
      var at = st.at(gi / 4);
      sky.addColorStop(gi / 4, 'rgba(' + at.rgb.join(',') + ',' + at.a.toFixed(3) + ')');
    }
    c.fillStyle = sky;
    c.fillRect(0, 0, w, h);
    c.setTransform(R, 0, 0, R, 0, 0);
    var fr = frame.getBoundingClientRect(), cellPx = nat.w * view.k / D.cells_w;
    // The lights inside a picture fade out as it gets small on screen
    // (dodoland_night_detail_from/_to, its width in pixels): from afar a town
    // is one soft glow, not a scatter of blobs.
    var dFrom = N.detail_from == null ? 12 : N.detail_from;
    var dTo = Math.max(dFrom + 1, N.detail_to == null ? 40 : N.detail_to);
    function detail(px) { var t = Math.max(0, Math.min(1, (px - dFrom) / (dTo - dFrom))); return t * t * (3 - 2 * t); }
    var viewKey = [view.x, view.y, view.k, W, H, D.world.length, Object.keys(pieces).length].join('|');
    var cached = nightCache && nightCache.key === viewKey;
    var lights = cached ? nightCache.lights.slice() : [], windows = cached ? nightCache.windows : [];
    // A list of lights put on a picture (the lights editor), x and y as
    // fractions of its box b; each glows where it was put.
    function pushLights(list, b, flip, perCell) {
      list.forEach(function (L) {
        var r = L.radius * perCell;
        var lx = b.left - fr.left + (flip ? 1 - L.x : L.x) * b.width, ly = b.top - fr.top + L.y * b.height;
        if (r <= 0 || lx < -r || ly < -r || lx > W + r || ly > H + r) return;
        lights.push({x: lx, y: ly + r * 0.15, top: ly, r: r, k: L.intensity, rgb: hexRgb(L.colour)});
      });
    }
    function seen(b) { return b.width && !(b.right < fr.left || b.bottom < fr.top || b.left > fr.right || b.top > fr.bottom); }
    if (!cached) {
    // Lights: every placed piece whose tile has lights, each where it was
    // put on the picture, mirrored and sized with the piece.
    D.world.forEach(function (p) {
      var a = assetById(p.a), el = pieces[p.id];
      if (!a || !a.gl || !a.gl.length || !el) return;
      var img = el.querySelector('img');
      if (!img) return;
      var b = img.getBoundingClientRect();
      pushLights(a.gl, b, el.classList.contains('flip'), cellPx * (p.s || 1));
    });
    // Windows: what has warm lit windows in its picture, in towns active lately.
    function lit(townId) { return !townId || (byId[townId] && byId[townId].lit); }
    Object.keys(pieces).forEach(function (id) {
      var el = pieces[id], p = el && el._piece, img = el && el.querySelector('img');
      if (!img || !lit(p && p.t)) return;
      var pa = p && assetById(p.a);
      if (pa && pa.al === false) return;   // its lights are only the ones put on it by hand
      var wm = windowsOf(img.src);
      if (!wm) return;
      var b = img.getBoundingClientRect(), f = detail(b.width);
      if (!seen(b) || f <= 0.01) return;
      windows.push({m: wm, x: b.left - fr.left, y: b.top - fr.top, w: b.width, h: b.height, f: f,
                    flip: el.classList.contains('flip')});
    });
    world.querySelectorAll('.dltown .dlart > img:first-child, .dltown .dlart > svg, .dlhouse > svg').forEach(function (art) {
      var town = art.closest('.dltown'), house = art.closest('.dlhouse');
      var id = town ? town.dataset.id : house ? house.dataset.town : '';
      if (!lit(id)) return;
      var b = art.getBoundingClientRect();
      if (!seen(b)) return;
      var person = town && byId[id], holes = null, own = true;
      // A town drawn as its hall's painting: that tier's lights on it.
      if (town && art.tagName === 'IMG' && person && person.hall_art) {
        var ha = assetById(person.hall_art.a);
        if (ha && ha.gl) pushLights(ha.gl, b, false, cellPx);
        if (ha && ha.al === false) own = false;
      }
      // A drawn town: each building in it at its tier, with the lights put
      // on that tier's drawing, placed through the building's own transform;
      // and where a tier finds none by itself, none are found on it.
      if (town && art.tagName === 'svg' && person && person.built) {
        art.querySelectorAll('.lot[data-building]').forEach(function (lot) {
          var key = lot.getAttribute('data-building'), tier = 0;
          person.built.forEach(function (bt) { if (bt.key === key) tier = bt.tier; });
          var a = tier && tierAsset(key, tier);
          if (!a) return;
          var list = a.wd != null ? (a.gd || []) : (a.gl || []), wc = a.wd != null ? a.wd : a.wc;
          var m = lot.getScreenCTM();
          if (!m) return;
          if (list.length && wc > 0) {
            var perCell = 120 * Math.abs(m.a) / wc;
            list.forEach(function (L) {
              var ux = L.x * 120 - 60, uy = L.y * 78 - 64;
              var lx = m.a * ux + m.c * uy + m.e - fr.left, ly = m.b * ux + m.d * uy + m.f - fr.top;
              var r = L.radius * perCell;
              if (r <= 0 || lx < -r || ly < -r || lx > W + r || ly > H + r) return;
              lights.push({x: lx, y: ly + r * 0.15, top: ly, r: r, k: L.intensity, rgb: hexRgb(L.colour)});
            });
          }
          if (a.al === false) {
            var lb = lot.getBoundingClientRect();
            (holes = holes || []).push({x: lb.left - fr.left, y: lb.top - fr.top, w: lb.width, h: lb.height});
          }
        });
      }
      if (!own) return;
      var sh = art.parentNode._shadow;
      var src = art.tagName === 'IMG' ? art.src : sh && sh.src;
      if (!src) return;
      var wm = windowsOf(src), f = detail(b.width);
      if (!wm || f <= 0.01) return;
      windows.push({m: wm, x: b.left - fr.left, y: b.top - fr.top, w: b.width, h: b.height, f: f, holes: holes,
                    flip: !!(house && house.classList.contains('flip'))});
    });
    // From afar a lively town is a dot: it glows, a beacon rather than a hole.
    world.querySelectorAll('.dltown.tiny .dldot').forEach(function (dot) {
      var town = dot.closest('.dltown');
      if (!lit(town.dataset.id)) return;
      var b = dot.getBoundingClientRect();
      if (!seen(b)) return;
      var r = Math.max(6, b.width * 1.6);
      lights.push({x: b.left - fr.left + b.width / 2, y: b.top - fr.top + b.height / 2,
                   top: b.top - fr.top + b.height / 2, r: r, k: 0.9, rgb: [255, 196, 110]});
    });
    // A picture's own lights light the ground round them too, a pool the
    // size of the light times dodoland_window_spill.
    var spill = N.spill == null ? 6 : N.spill;
    windows.forEach(function (o) {
      (o.m.spots || []).forEach(function (sp) {
        var r = Math.max(1, sp.r * o.w * spill), fx = o.flip ? 1 - sp.cx : sp.cx;
        var lx = o.x + fx * o.w, ly = o.y + sp.cy * o.h;
        if (o.holes && o.holes.some(function (hr) { return lx >= hr.x && lx <= hr.x + hr.w && ly >= hr.y && ly <= hr.y + hr.h; })) return;
        lights.push({x: lx, y: ly + r * 0.25, top: ly, r: r, k: o.f, rgb: [255, 190, 100], spot: true});
      });
    });
    nightCache = {key: viewKey, lights: lights.slice(), windows: windows};
    }
    // Town names stay readable, but only the ones showing: a hidden label
    // lifted the night off a whole box of ground.
    var names = [];
    world.querySelectorAll(world.classList.contains('named') ? '.dltown .dlname'
                           : '.dltown:hover .dlname, .dltown.on .dlname').forEach(function (n) {
      var b = n.getBoundingClientRect();
      if (!seen(b) || +getComputedStyle(n).opacity < 0.5) return;
      names.push({x: b.left - fr.left, y: b.top - fr.top, w: b.width, h: b.height});
    });
    // People out walking carry a small lantern (dodoland_walker_light, cells).
    var wl = N.walker_light == null ? 1.6 : N.walker_light;
    if (wl > 0 && typeof walkers !== 'undefined' && !world.classList.contains('lifefar')) {
      walkers.forEach(function (wk) {
        if (wk.kind !== 'person' && wk.kind !== 'child') return;
        var sx = view.x + wk.x / D.cells_w * nat.w * view.k, sy = view.y + wk.y / cellsH() * nat.h * view.k;
        var r = wl * cellPx;
        if (sx < -r || sy < -r || sx > W + r || sy > H + r) return;
        lights.push({x: sx, y: sy, top: sy - r * 0.45, r: r, rgb: [255, 180, 80]});
      });
      // Real members on the roads carry torches: brighter, further.
      (typeof travellers !== 'undefined' ? travellers : []).forEach(function (t) {
        if (t.x == null) return;
        var sx = view.x + t.x / D.cells_w * nat.w * view.k, sy = view.y + t.y / cellsH() * nat.h * view.k;
        var r = wl * 1.6 * cellPx;
        if (sx < -r || sy < -r || sx > W + r || sy > H + r) return;
        lights.push({x: sx, y: sy, top: sy - r * 0.5, r: r, k: 1.2, rgb: [255, 170, 70]});
      });
    }
    function put(img, x, y, w2, h2, flip) {
      if (!flip) { c.drawImage(img, x, y, w2, h2); return; }
      c.save(); c.translate(x + w2, y); c.scale(-1, 1); c.drawImage(img, 0, 0, w2, h2); c.restore();
    }
    // A picture's own glow, faded with its size on screen and kept off the
    // buildings in it that find no lights by themselves.
    function putWindow(o, img, alpha, fn) {
      c.globalAlpha = Math.min(1, alpha * o.f);
      if (!o.holes) { fn ? fn() : put(img, o.x, o.y, o.w, o.h, o.flip); return; }
      c.save();
      c.beginPath(); c.rect(-W, -H, W * 3, H * 3);
      o.holes.forEach(function (hr) { c.rect(hr.x, hr.y, hr.w, hr.h); });
      c.clip('evenodd');
      fn ? fn() : put(img, o.x, o.y, o.w, o.h, o.flip);
      c.restore();
    }
    // Cut the night where things are lit.
    c.globalCompositeOperation = 'destination-out';
    var white = stamp([255, 255, 255]);
    lights.forEach(function (l) {
      var k = l.k == null ? 1 : l.k;
      c.globalAlpha = Math.min(1, 0.85 * k); c.drawImage(white, l.x - l.r, l.y - l.r * 0.7, l.r * 2, l.r * 1.4);
      c.globalAlpha = Math.min(1, k); c.drawImage(white, l.x - l.r * 0.22, l.top - l.r * 0.22, l.r * 0.44, l.r * 0.44);
    });
    windows.forEach(function (o) {
      putWindow(o, o.m.mask, 1);
      putWindow(o, o.m.halo, 0.7);
    });
    c.globalAlpha = 0.9; c.fillStyle = '#000';
    names.forEach(function (nm) { c.fillRect(nm.x, nm.y, nm.w, nm.h); });
    // And warm what they light.
    c.globalCompositeOperation = 'source-over';
    var glow = (N.light_glow == null ? 0.35 : N.light_glow) * st.k;
    lights.forEach(function (l) {
      var s = stamp(l.rgb), k = l.k == null ? 1 : l.k;
      c.globalAlpha = Math.min(1, glow * k); c.drawImage(s, l.x - l.r, l.y - l.r * 0.7, l.r * 2, l.r * 1.4);
      c.globalAlpha = Math.min(1, glow * 2 * k); c.drawImage(s, l.x - l.r * 0.18, l.top - l.r * 0.18, l.r * 0.36, l.r * 0.36);
    });
    var wg = (N.window_glow == null ? 0.8 : N.window_glow) * st.k, amber = stamp([255, 190, 90]);
    windows.forEach(function (o) {
      putWindow(o, o.m.halo, wg * 0.55);
      if (wg > 0) putWindow(o, null, wg * 0.18, function () {
        c.drawImage(amber, o.x + o.w * 0.1, o.y + o.h * 0.55, o.w * 0.8, o.h * 0.5);
      });
    });
    c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
  }
  setInterval(nightSoon, 60000);

  // Which pixels of a piece's picture are painted, read once per picture
  // into a small alpha map (pictures are ours, so the canvas is not tainted).
  var alphaMaps = {};
  function paintedAt(el, clientX, clientY) {
    var need = D.sizes.hit_alpha === undefined ? 96 : D.sizes.hit_alpha;
    if (need <= 0) return true;   // the whole picture takes clicks, as it used to
    var img = el.querySelector('img');
    if (!img || !img.complete || !img.naturalWidth) return true;   // not known yet: solid
    var key = img.currentSrc || img.src, map = alphaMaps[key];
    if (map === undefined) {
      try {
        var w = Math.min(256, img.naturalWidth), h = Math.max(1, Math.round(img.naturalHeight * w / img.naturalWidth));
        var c = document.createElement('canvas');
        c.width = w; c.height = h;
        var x = c.getContext('2d');
        x.drawImage(img, 0, 0, w, h);
        map = alphaMaps[key] = {w: w, h: h, a: x.getImageData(0, 0, w, h).data};
      } catch (e) { map = alphaMaps[key] = null; }
    }
    if (!map) return true;
    var r = img.getBoundingClientRect();
    var fx = (clientX - r.left) / r.width, fy = (clientY - r.top) / r.height;
    if (!(fx >= 0 && fx < 1 && fy >= 0 && fy < 1)) return false;
    if (el.classList.contains('flip')) fx = 1 - fx;
    // A faint glow or shadow is not the building: well over half opaque.
    return map.a[(Math.floor(fy * map.h) * map.w + Math.floor(fx * map.w)) * 4 + 3] >= need;
  }
  // What a press on ``el`` really lands on: the piece if it is painted there,
  // else the first painted piece or other thing of the map beneath it, else
  // the map itself (``{}``).
  function pieceHit(ev, el) {
    if (paintedAt(el, ev.clientX, ev.clientY)) return {piece: el._piece, el: el};
    var stack = document.elementsFromPoint(ev.clientX, ev.clientY), past = false;
    for (var i = 0; i < stack.length; i++) {
      var e = stack[i];
      if (!past) { if (e === el || el.contains(e)) past = true; continue; }
      var p = e.closest && e.closest('.dlpiece');
      if (p && p !== el && p._piece) {
        if (paintedAt(p, ev.clientX, ev.clientY)) return {piece: p._piece, el: p};
        continue;
      }
      if (e === world || e === frame || !frame.contains(e)) return {};
      if (e.closest && (e.closest('.dltown') || e.closest('.dlhouse'))) return {other: e};
    }
    return {};
  }
  // Hand the press to what is beneath, as if it had been pressed there.
  function passOn(ev, target, type) {
    ev.stopPropagation();
    var init = {bubbles: true, cancelable: true, clientX: ev.clientX, clientY: ev.clientY,
                button: ev.button, buttons: ev.buttons, shiftKey: ev.shiftKey};
    target.dispatchEvent(type === 'click' ? new MouseEvent('click', init)
      : new PointerEvent(type, Object.assign(init, {pointerId: ev.pointerId, isPrimary: ev.isPrimary,
                                                    pointerType: ev.pointerType})));
  }

  function drawPiece(piece) {
    var el = document.createElement('div');
    var meta = typeof assetById === 'function' ? assetById(piece.a) : null;
    // A town's building grows with the town: drawn at the tier reached now,
    // whatever tier it was when it was put down.
    if (piece.t && meta && meta.building && byId[piece.t]) {
      var now = currentTile(byId[piece.t], meta.building);
      if (now && now.id !== piece.a) { piece = Object.assign({}, piece, {a: now.id, v: ''}); meta = now; }
    }
    el.className = 'dlpiece L-' + (piece.l || 'objects') + (piece.f ? ' flip' : '') +
      (meta && meta.px ? ' px' : '');
    if (piece.r) el.style.setProperty('--rot', piece.r + 'deg');
    el.dataset.id = piece.id;
    el.style.left = piece.x + '%';
    el.style.top = piece.y + '%';
    stackZ(el, piece);
    var w = pieceWidth(piece);
    if (w) el.style.width = w;
    var picture = assetUrl(piece.a) + (pieceVariant(piece) ? '?v=' + pieceVariant(piece) : '');
    el.innerHTML = '<img alt="" loading="lazy" decoding="async" src="' + picture + '">' +
      (hallPieces[piece.id] ? flagHtml(hallPieces[piece.id]) : '');
    // Its shadow, behind it, for everything that stands (not flat ground).
    if (stackOf(piece) !== 'flat') addShadow(el, picture, !!piece.f);

    // Dragging, and clicking, from one gesture. The frame owns panning and
    // takes pointer capture as soon as a drag starts, so a piece that only
    // listened for `click` could be selected and never moved: every attempt to
    // drag one panned the map underneath it instead. Stopping the event here
    // is what keeps the map still while a piece is being moved.
    // A piece answers only where it is painted: its picture's empty corners
    // and faint glow pass the press, the click and the hover on to whatever
    // is underneath — another piece, a house, a town, or the map.
    el._piece = piece;
    el.addEventListener('pointerdown', function (ev) {
      var hit = pieceHit(ev, el);
      if (hit.piece) pieceDown(ev, hit.piece, hit.el);
      else if (hit.other) passOn(ev, hit.other, 'pointerdown');
    });
    el.addEventListener('click', function (ev) {
      var hit = pieceHit(ev, el);
      if (hit.piece) pieceClick(ev, hit.piece);
      else if (hit.other) passOn(ev, hit.other, 'click');
    });
    el.addEventListener('pointermove', function (ev) {
      var solid = paintedAt(el, ev.clientX, ev.clientY);
      el.style.cursor = solid ? '' : 'inherit';
      var want = solid ? piece.id : (hovered === piece.id ? null : hovered);
      if (want !== hovered) { hovered = want; placeMarks(); }
    });
    el.addEventListener('pointerleave', function () {
      if (hovered === piece.id) { hovered = null; placeMarks(); }
    });
    world.appendChild(el);
    pieces[piece.id] = el;
    return el;
  }

  // --- marks: what is held, what is under the pointer ------------------- //
  var hovered = null, markPool = [];
  var hoverMark = document.createElement('div');
  hoverMark.className = 'dlmark hover';
  frame.appendChild(hoverMark);
  function markAt(mark, el) {
    if (!el) { mark.style.display = 'none'; return; }
    var r = el.getBoundingClientRect(), f = frame.getBoundingClientRect(), pad = 2;
    mark.style.left = (r.left - f.left - pad) + 'px';
    mark.style.top = (r.top - f.top - pad) + 'px';
    mark.style.width = (r.width + pad * 2) + 'px';
    mark.style.height = (r.height + pad * 2) + 'px';
    mark.style.display = 'block';
  }
  function placeMarks() {
    // A box per selected piece, on screen; a few hundred at most, because a
    // box selection over a forest is a lot of boxes to move on every pan.
    var ids = selIds().filter(function (id) { return pieces[id]; }).slice(0, 400);
    while (markPool.length < ids.length) {
      var m = document.createElement('div');
      m.className = 'dlmark';
      frame.appendChild(m);
      markPool.push(m);
    }
    markPool.forEach(function (m, i) {
      markAt(m, i < ids.length ? pieces[ids[i]] : null);
      var p = i < ids.length && pieceById(ids[i]);
      m.classList.toggle('locked', !!(p && p.k));
      m.classList.toggle('pinned', !!(p && p.pk && !p.k));
    });
    markAt(hoverMark, hovered && !sel[hovered] && !frame.classList.contains('placing') && pieces[hovered]);
    placeTurn(ids.length === 1 ? ids[0] : null);
  }
  // Turning a piece: a handle above it when it is the only one selected. The
  // turn is round the piece's foot, as the angle from the foot to the pointer.
  var turn = document.createElement('div');
  turn.className = 'dlturn'; turn.textContent = '\u21bb';
  turn.title = 'Drag round to turn (Shift: 15\u00b0 steps). Double-click: straight.';
  frame.appendChild(turn);
  function turnFoot(el) {
    var r = el.getBoundingClientRect(), f = frame.getBoundingClientRect();
    // The foot (50%, 85% of the unturned box) is where the piece stands.
    var p = pieceById(el.dataset.id), w = el.offsetWidth * view.k, h = el.offsetHeight * view.k;
    var cx = r.left + r.width / 2 - f.left, cy = r.top + r.height / 2 - f.top;
    var a = (p && p.r || 0) * Math.PI / 180, dy = h * 0.35;
    return {x: cx - Math.sin(a) * dy, y: cy + Math.cos(a) * dy, h: h, w: w};
  }
  function placeTurn(id) {
    var p = id && pieceById(id), el = id && pieces[id];
    var may = p && el && !p.k && (!D.ep.player || String(p.by || '') === String(D.me) || p.t === String(D.me));
    turn.classList.toggle('on', !!may);
    if (!may) { turn.dataset.id = ''; return; }
    var foot = turnFoot(el), a = (p.r || 0) * Math.PI / 180, reach = foot.h * 0.85 + 26;
    turn.dataset.id = id;
    turn.style.left = (foot.x + Math.sin(a) * reach) + 'px';
    turn.style.top = (foot.y - Math.cos(a) * reach) + 'px';
    turn.style.transform = 'rotate(' + (p.r || 0) + 'deg)';
  }
  function setTurn(id, deg, save) {
    var p = pieceById(id), el = pieces[id];
    if (!p || !el) return;
    deg = ((Math.round(deg * 10) / 10) % 360 + 360) % 360;
    p.r = deg;
    el.style.setProperty('--rot', deg + 'deg');
    placeTurn(id);
    if (save) decorPost(D.ep.player ? {action: 'move', piece_id: id, rot: deg}
                                    : {action: 'move_many', moves: [{piece_id: id, rot: deg}]}, function () {});
  }
  turn.addEventListener('pointerdown', function (ev) {
    var id = turn.dataset.id, el = id && pieces[id];
    if (!el) return;
    ev.preventDefault(); ev.stopPropagation();
    try { turn.setPointerCapture(ev.pointerId); } catch (e) {}
    var foot = turnFoot(el), f = frame.getBoundingClientRect(), turned = false;
    function move(m) {
      var deg = Math.atan2(m.clientX - f.left - foot.x, -(m.clientY - f.top - foot.y)) * 180 / Math.PI;
      if (m.shiftKey) deg = Math.round(deg / 15) * 15;
      turned = true;
      setTurn(id, deg, false);
    }
    function up() {
      turn.removeEventListener('pointermove', move); turn.removeEventListener('pointerup', up);
      if (turned) setTurn(id, pieceById(id).r || 0, true);
    }
    turn.addEventListener('pointermove', move); turn.addEventListener('pointerup', up);
  });
  turn.addEventListener('dblclick', function (ev) {
    ev.stopPropagation();
    if (turn.dataset.id) setTurn(turn.dataset.id, 0, true);
  });

  // The armed piece, following the pointer at the size it will be placed at,
  // anchored the same way a placed one is.
  var ghost = document.createElement('div');
  ghost.className = 'dlpiece ghost';
  ghost.innerHTML = '<img alt="">';
  world.appendChild(ghost);
  function aimGhost(ev) {
    if (!armedAsset || !nat.w || tool !== 'pencil') { ghost.classList.remove('live'); return; }
    var b = frame.getBoundingClientRect();
    var probe = {a: armedAsset, v: '', s: parseFloat(kitScale.value) || 1};
    var w = pieceWidth(probe);
    if (w) ghost.style.width = w;
    var meta = assetById(armedAsset);
    ghost.classList.toggle('px', !!(meta && meta.px));
    var src = assetUrl(armedAsset);
    var img = ghost.firstChild;
    if (img.getAttribute('src') !== src) img.setAttribute('src', src);
    ghost.style.left = ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100 + '%';
    ghost.style.top = ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100 + '%';
    ghost.classList.add('live');
  }
  frame.addEventListener('pointermove', aimGhost);
  frame.addEventListener('pointerleave', function () { ghost.classList.remove('live'); });

  // --- layers ------------------------------------------------------------ //
  var LAYERS = [
    {key: 'ground', label: 'Ground', sub: 'layer 1 · painted in the Terrain drawer', edit: true},
    {key: 'environment', label: 'Environment features', sub: 'layer 1 · placed', edit: true},
    {key: 'influence', label: 'Influence', sub: 'each town’s area', edit: false},
    {key: 'roads', label: 'Roads', sub: 'layer 2 · drawn by the bot', edit: false},
    {key: 'objects', label: 'Map objects', sub: 'layer 3', edit: true},
    {key: 'buildings', label: 'Buildings & towns', sub: 'layer 4 · built from a town’s card', edit: false},
    {key: 'life', label: 'People & animals', sub: 'walking in each town', edit: false}
  ];
  var layerState = {hidden: [], edit: 'objects'};
  try { layerState = JSON.parse(window.localStorage.getItem('dl-layers')) || layerState; } catch (e) {}
  // Nothing in the toolkit edits buildings any more; a saved choice of it
  // would leave the kit empty.
  if (layerState.edit === 'buildings' || layerState.edit === 'ground') layerState.edit = 'objects';
  function applyLayers() {
    LAYERS.forEach(function (l) {
      world.classList.toggle('hide-' + l.key, layerState.hidden.indexOf(l.key) >= 0);
    });
    world.dataset.edit = layerState.edit;
    world.classList.toggle('infl-all', !!layerState.inflAll);
    try { window.localStorage.setItem('dl-layers', JSON.stringify(layerState)); } catch (e) {}
    var rows = document.getElementById('dllayerrows');
    if (rows) {
      rows.innerHTML = LAYERS.map(function (l) {
        var hidden = layerState.hidden.indexOf(l.key) >= 0;
        var n = l.key === 'influence' ? (D.influence || []).length
              : l.key === 'roads' ? (D.roads || []).length
              : D.world.filter(function (p) { return (p.l || 'objects') === l.key; }).length;
        var says = hidden ? 'hidden' : 'shown';
        if (l.key === 'influence' && !hidden) says = layerState.inflAll ? 'all' : 'selected';
        return '<div class="dllayer' + (layerState.edit === l.key ? ' editing' : '') + '">' +
          '<span>' + l.label + (n ? ' <span class="muted">· ' + n + '</span>' : '') +
          '<small>' + l.sub + '</small></span>' +
          '<button data-eye="' + l.key + '" class="' + (hidden ? 'off' : '') + '" title="' +
          (l.key === 'influence' ? 'The open town only, every town, or none' : 'Show or hide') + '">' +
          says + '</button>' +
          '<button data-edit="' + l.key + '" class="' + (layerState.edit === l.key ? 'on' : '') + '"' +
          (l.edit && (!D.ep.player || l.key === 'ground') ? '' : ' disabled') + '>edit</button></div>';
      }).join('');
      rows.querySelectorAll('[data-eye]').forEach(function (b) {
        b.onclick = function () {
          var k = b.dataset.eye, at = layerState.hidden.indexOf(k);
          if (k === 'influence') {
            // selected -> all -> hidden -> selected
            if (at >= 0) { layerState.hidden.splice(at, 1); layerState.inflAll = false; }
            else if (!layerState.inflAll) { layerState.inflAll = true; }
            else { layerState.hidden.push(k); layerState.inflAll = false; }
          } else if (at >= 0) layerState.hidden.splice(at, 1); else layerState.hidden.push(k);
          applyLayers();
        };
      });
      rows.querySelectorAll('[data-edit]').forEach(function (b) {
        b.onclick = function () {
          // Ground is painted, so editing it is the Terrain drawer.
          if (b.dataset.edit === 'ground') {
            if (!document.getElementById('dlterrdrawer').classList.contains('open')) {
              document.getElementById('dlterr').click();
            }
            return;
          }
          layerState.edit = b.dataset.edit;
          armedAsset = null; mix = []; sel = {}; heldPiece = null;
          frame.classList.remove('placing');
          applyLayers(); fillKitCats(); renderKit(); selChanged();
        };
      });
    }
  }
  document.getElementById('dllayers').onclick = function () {
    var panel = document.getElementById('dllayerpanel');
    panel.hidden = !panel.hidden;
  };

  function redrawDecor() {
    world.querySelectorAll('.dlpiece:not(.ghost)').forEach(function (n) { n.remove(); });
    pieces = {};
    // Back to front: of two overlapping trees the lower one stands in front,
    // which is what makes a dense stand read as a wood.
    D.world.sort(function (a, b) { return a.y - b.y; });
    D.world.forEach(drawPiece);
    // A zoo put down or taken away changes who walks where.
    if (typeof buildLife === 'function' && typeof terr !== 'undefined' && terr.world) {
      clearTimeout(redrawDecor.life);
      redrawDecor.life = setTimeout(buildLife, 300);
    }
    Object.keys(sel).forEach(function (id) {
      if (pieces[id]) pieces[id].classList.add('on'); else delete sel[id];
    });
    placeMarks();
    if (typeof renderPlaced === 'function') renderPlaced();
  }

  function resizeDecor() {
    // Only the widths, so this can run on every zoom without rebuilding the
    // nodes — and without throwing away a piece mid-drag.
    D.world.forEach(function (piece) {
      var el = pieces[piece.id], w = pieceWidth(piece);
      if (el && w) el.style.width = w;
    });
  }

  function pieceById(id) {
    for (var i = 0; i < D.world.length; i++) {
      if (D.world[i].id === id) return D.world[i];
    }
    return null;
  }

  // Selecting one piece, kept for the callers that think in one held piece.
  function hold(id, keep) {
    if (keep) { if (!sel[id]) selectOnly([id]); return; }
    if (sel[id] && selIds().length === 1) selectOnly([]); else selectOnly([id]);
  }

  // "Placing..." / "Moving..." while a place or move is saved: the bar fills
  // over this browser's running average of how long that takes (eased so it
  // nears the end without reaching it), then completes and fades.
  var busy = {n: 0, el: null};
  function busyStart(action) {
    var kind = /move/.test(action) ? 'move' : /place/.test(action) ? 'place' : '';
    if (!kind) return null;
    if (!busy.el) {
      busy.el = document.createElement('div'); busy.el.className = 'dlbusy';
      busy.el.innerHTML = '<span></span><i><b></b></i>';
      document.body.appendChild(busy.el);
    }
    var avg = 700;
    try { avg = +localStorage.getItem('dlbusy-' + kind) || avg; } catch (e) {}
    busy.n++;
    busy.el.querySelector('span').textContent = kind === 'move' ? 'Moving…' : 'Placing…';
    var bar = busy.el.querySelector('b');
    bar.style.transition = 'none'; bar.style.width = '0';
    busy.el.classList.add('on'); frame.classList.add('busy');
    void bar.offsetWidth;
    bar.style.transition = 'width ' + Math.round(avg * 1.15) + 'ms cubic-bezier(.2,.7,.3,1)';
    bar.style.width = '92%';
    return {kind: kind, t0: performance.now()};
  }
  function busyEnd(b) {
    if (!b) return;
    var took = performance.now() - b.t0;
    try {
      var old = +localStorage.getItem('dlbusy-' + b.kind) || took;
      localStorage.setItem('dlbusy-' + b.kind, String(Math.round(old * 0.7 + took * 0.3)));
    } catch (e) {}
    if (--busy.n > 0) return;
    var bar = busy.el.querySelector('b');
    bar.style.transition = 'width 120ms linear'; bar.style.width = '100%';
    setTimeout(function () { if (busy.n <= 0) { busy.el.classList.remove('on'); frame.classList.remove('busy'); } }, 220);
  }
  function decorPost(payload, then, fail) {
    var b = busyStart(payload.action || '');
    fetch(D.ep.decor, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      busyEnd(b);
      if (!res.ok) {
        kitSay(res.error || 'That did not work.', true);
        hint.textContent = res.error || 'That did not work.';
        if (fail) fail(res);
        return;
      }
      then(res);
      // A placed piece can block a town's growth, so its area may have changed.
      if (typeof loadInfluence === 'function') loadInfluence();
    }).catch(function (err) { busyEnd(b); kitSay(String(err), true); });
  }

  function placeDecor(point) {
    decorPost({action: 'place', asset_id: armedAsset, x: point.x, y: point.y,
               scale: parseFloat(kitScale.value) || 1, town: building || '',
               landmark: !building && landmarkMode},
      function (res) {
        D.world.push({id: res.piece.piece_id, a: res.piece.asset_id, v: res.piece.variant || '',
                      l: res.piece.layer || 'objects',
                      x: res.piece.x, y: res.piece.y, s: res.piece.scale,
                      f: !!res.piece.flip, by: String(res.piece.by || ''),
                      bn: res.piece.by_name || '', at: res.piece.at || 0,
                      t: res.piece.town || '', k: !!res.piece.locked});
        redrawDecor();
        if (building) {
          // One of each: once it stands, the pencil is put down and the card
          // says Built.
          var town = byId[building];
          armedAsset = null; mix = []; building = null;
          frame.classList.remove('placing');
          setTool('hand');
          hint.textContent = 'Built.';
          if (town) open(town.id);
          return;
        }
        kitSay('Placed. Click again to place another.');
      });
  }

  function selectedPieces() {
    return selIds().map(pieceById).filter(function (p) { return p; });
  }
  if (kitScale) kitScale.oninput = function () {
    var chosen = selectedPieces();
    // With nothing selected the slider is the size the pencil and brush use.
    if (!chosen.length) return;
    var v = parseFloat(kitScale.value) || 1;
    chosen.forEach(function (p) {
      var a = assetById(p.a);
      p.s = a ? Math.min(a.hi, Math.max(a.lo, v)) : v;
    });
    // Just the widths. Rebuilding every node on each step of a slider threw
    // the element out from under the pointer.
    resizeDecor(); placeMarks();
  };
  if (kitScale) kitScale.onchange = function () {
    var chosen = selectedPieces();
    if (!chosen.length) return;
    decorPost({action: 'move_many', moves: chosen.map(function (p) {
      return {piece_id: p.id, scale: p.s}; })}, function () { kitSay('Resized.'); });
  };
  // Whether the selection holds something locked; says so if it does.
  function heldSay(verb) {
    var chosen = selectedPieces();
    var text = chosen.some(function (p) { return p.k; })
      ? 'That is a landmark. Unlock it first to ' + verb + ' it.'
      : chosen.some(function (p) { return p.pk; })
        ? 'That is locked in place. Unlock it first to ' + verb + ' it.' : '';
    if (text) { kitSay(text, true); hint.textContent = text; }
    return !!text;
  }
  document.getElementById('dlkitflip').onclick = function () {
    var chosen = selectedPieces();
    if (!chosen.length) { kitSay('Select a placed piece first.', true); return; }
    if (heldSay('mirror')) return;
    chosen.forEach(function (p) { p.f = !p.f; });
    redrawDecor();
    decorPost({action: 'move_many', moves: chosen.map(function (p) {
      return {piece_id: p.id, flip: p.f}; })}, function () { kitSay('Mirrored.'); });
  };
  function removeSelection() {
    var ids = selIds();
    if (!ids.length) { kitSay('Select a placed piece first.', true); return; }
    if (heldSay('remove')) return;
    decorPost({action: 'remove_many', piece_ids: ids}, function (res) {
      D.world = D.world.filter(function (q) { return !sel[q.id]; });
      sel = {};
      redrawDecor(); selChanged();
      kitSay(res.removed === 1 ? 'Removed.' : 'Removed ' + res.removed + '.');
    });
  }
  document.getElementById('dlkitdel').onclick = removeSelection;
  // Landmark mode: only offered to the bot owner and the server's owner; while
  // on, everything they place is a landmark from the moment it lands.
  var landmarkMode = false;
  (function () {
    var row = document.getElementById('dllandmode'), box = document.getElementById('dllandmodebox');
    if (!D.ep.landmark_mode || !row) return;
    row.hidden = false;
    try { landmarkMode = window.localStorage.getItem('dl-landmark-mode') === '1'; } catch (e) {}
    box.checked = landmarkMode;
    row.classList.toggle('on', landmarkMode);
    box.onchange = function () {
      landmarkMode = box.checked;
      row.classList.toggle('on', landmarkMode);
      try { window.localStorage.setItem('dl-landmark-mode', landmarkMode ? '1' : '0'); } catch (e) {}
      kitSay(landmarkMode ? 'Landmark mode: what you place now stays put.' : 'Landmark mode off.');
    };
  })();
  // Landmarks: the selection locked, or unlocked if all of it already is.
  document.getElementById('dlkitlock').onclick = function () {
    var chosen = selectedPieces();
    if (!chosen.length) { kitSay('Select a placed piece first.', true); return; }
    var lock = !chosen.every(function (p) { return p.k || p.pk; });
    decorPost({action: lock ? 'lock' : 'unlock', piece_ids: chosen.map(function (p) { return p.id; })},
      function () {
        chosen.forEach(function (p) { p.k = lock; if (!lock) p.pk = false; });
        redrawDecor(); selChanged();
        kitSay(lock ? (chosen.length === 1 ? 'Now a landmark.' : chosen.length + ' landmarks.')
                    : (chosen.length === 1 ? 'No longer a landmark.' : chosen.length + ' unlocked.'));
      });
  };
  function closeKit() {
    kitDrawer.classList.remove('open');
    armedAsset = null; mix = [];
    if (selIds().length) selectOnly([]);
    frame.classList.remove('placing');
    // The pencil and the brush need the kit; without it the hand is back.
    if (tool === 'pencil' || tool === 'brush') setTool('hand');
    renderKit();
  }
  function openKit() {
    closeDrawers('kit');
    kitDrawer.classList.add('open');
    renderPlaced();
  }
  document.getElementById('dlkit').onclick = function () {
    if (kitDrawer.classList.contains('open')) { closeKit(); return; }
    openKit();
  };
  document.getElementById('dlkitclose').onclick = closeKit;
  // Flat / Standing / On top, for everything selected.
  function stackButtons() {
    var ids = selIds(), first = ids.length && pieceById(ids[0]);
    document.querySelectorAll('#dlstack button').forEach(function (b) {
      b.classList.toggle('on', !!first && stackOf(first) === b.dataset.st);
      b.disabled = !ids.length;
    });
  }
  document.querySelectorAll('#dlstack button').forEach(function (b) {
    b.onclick = function () {
      var ids = selIds();
      if (!ids.length) { kitSay('Select something first.', true); return; }
      decorPost({action: 'stack', piece_ids: ids, stack: b.dataset.st}, function () {
        ids.forEach(function (id) {
          var p = pieceById(id);
          if (p) { p.st = b.dataset.st; var node = pieces[id]; if (node) stackZ(node, p); }
        });
        stackButtons();
        kitSay({flat: 'Lies flat now.', stand: 'Stands by where it is.', top: 'On top of everything.'}[b.dataset.st]);
      });
    };
  });

  // --- the toolbox ------------------------------------------------------- //
  // Four tools, one mechanic each:
  //   pointer (V)  click a piece to select it, shift-click to add or drop one,
  //                drag the empty map to select everything in a box; drag a
  //                selected piece to move the whole selection
  //   hand    (H)  drag the map to move around; click a piece to select it;
  //                drag a selected piece to move the selection
  //   pencil  (P)  click to put the picked tile down, once per click
  //   brush   (B)  drag to scatter the picked tiles (shift-click several in the
  //                library for a mix) as a scatter, a line or clusters
  // Delete removes the selection; Escape lets go of everything.
  var tool = 'hand', sel = {}, mix = [], gesture = null, swallowClick = false;
  try { tool = window.localStorage.getItem('dl-tool') || 'hand'; } catch (e) {}
  if (['pointer', 'hand', 'pencil', 'brush'].indexOf(tool) < 0 || !D.assets.length) tool = 'hand';
  if (tool === 'pencil' || tool === 'brush') tool = 'hand';   // nothing is picked on a fresh page
  var HINT = {
    pointer: 'Select: click a piece, shift-click to add, drag a box over the map.',
    hand: 'Hand: drag to move around; click a piece to select it, drag it to move it.',
    pencil: 'Pencil: pick a tile, then click the map to put it down.',
    brush: 'Brush: pick tiles (shift-click for a mix), then drag on the map.'
  };
  function setTool(t, quiet) {
    tool = t;
    try { window.localStorage.setItem('dl-tool', t); } catch (e) {}
    document.querySelectorAll('.dlzoom [data-tool]').forEach(function (b) {
      b.classList.toggle('on', b.dataset.tool === t);
    });
    frame.dataset.tool = t;
    var placing = t === 'pencil' || t === 'brush';
    if (t !== 'pencil') building = null;
    if (placing && !quiet && !kitDrawer.classList.contains('open')) openKit();
    document.getElementById('dlbrushopts').hidden = t !== 'brush';
    frame.classList.toggle('placing', placing && !!armedAsset);
    if (!placing) { ghost.classList.remove('live'); }
    brushCursor(null);
    if (!quiet) kitSay(HINT[t]);
  }
  document.querySelectorAll('.dlzoom [data-tool]').forEach(function (b) {
    b.onclick = function (ev) { ev.stopPropagation(); setTool(b.dataset.tool); };
  });

  function selIds() { return Object.keys(sel); }
  function selectOnly(ids) { sel = {}; ids.forEach(function (id) { sel[id] = true; }); selChanged(); }
  function selChanged() {
    // A member selects only their own things; the rest of the map is to look at.
    if (D.ep.player) Object.keys(sel).forEach(function (id) { if (!mayTouch(pieceById(id))) delete sel[id]; });
    if (typeof stackButtons === 'function') stackButtons();
    var ids = selIds();
    heldPiece = ids.length ? ids[ids.length - 1] : null;
    world.querySelectorAll('.dlpiece:not(.ghost)').forEach(function (n) {
      n.classList.toggle('on', !!sel[n.dataset.id]);
    });
    var p = heldPiece && pieceById(heldPiece);
    if (p) { fitSlider(p.a); kitScale.value = p.s; }
    if (p && ids.length === 1 && (p.l || 'objects') !== editLayer()) {
      layerState.edit = p.l || 'objects';
      applyLayers(); fillKitCats(); renderKit();
    }
    if (ids.length) kitSay(ids.length === 1
      ? 'Selected. Drag it to move it; size, mirror or remove it below.'
      : ids.length + ' selected. Drag one to move them all; Delete removes them.');
    placeMarks();
    renderPlaced();
  }

  function toMap(clientX, clientY) {
    var b = frame.getBoundingClientRect();
    return {x: ((clientX - b.left - view.x) / (nat.w * view.k)) * 100,
            y: ((clientY - b.top - view.y) / (nat.h * view.k)) * 100};
  }

  // A press on a placed piece. Armed, pieces take no pointer at all (CSS), so
  // this is only ever the pointer or the hand.
  function pieceDown(ev, piece, el) {
    if (ev.button !== 0) return;   // the wheel pans; it passes through to the map
    var selected = !!sel[piece.id];
    // The hand on a piece that is not selected is still the hand: the map pans,
    // and a click without a drag selects it (pieceClick).
    if (tool === 'hand' && !selected) return;
    if (!mayTouch(piece)) return;   // somebody else's: the map pans as usual
    ev.stopPropagation(); ev.preventDefault();
    if (tool === 'pointer') {
      if (ev.shiftKey) {
        if (selected) { delete sel[piece.id]; selChanged(); return; }
        sel[piece.id] = true; selChanged();
      } else if (!selected) {
        selectOnly([piece.id]);
      }
    }
    dragSelection(ev, el);
  }
  function pieceClick(ev, piece) {
    ev.stopPropagation();
    if (moved > 6 && tool === 'hand') return;
    if (tool === 'hand' && !sel[piece.id]) selectOnly([piece.id]);
    showTownOf(piece);
  }
  // A building belongs to a town: clicking it is asking about that town.
  function showTownOf(piece) {
    if (!piece || !piece.t || !byId[piece.t]) return;
    var a = assetById(piece.a);
    if (a && a.building) { showPop(piece); return; }
    open(piece.t);
  }

  // A building's pop-up: what it is, whose it is and what builds it, floating
  // above the building, on screen. It follows the map as it moves and goes on
  // the next click elsewhere, Escape or a right click.
  var pop = document.createElement('div');
  pop.className = 'dlpop';
  frame.appendChild(pop);
  var popFor = null;
  function showPop(piece) {
    var town = byId[piece.t], a = assetById(piece.a);
    var b = town && a && town.built.filter(function (x) { return x.key === a.building; })[0];
    if (!b) { pop.style.display = 'none'; popFor = null; return; }
    var rooms = (b.rooms && b.rooms.length)
      ? b.rooms.map(escapeHtml).join(', ') : 'No channels feed it yet.';
    pop.innerHTML =
      '<b>' + escapeHtml(b.name) + ' of ' + escapeHtml(town.name) + '</b>' +
      '<span class="dlpopsub">' + escapeHtml(b.given) + ' · ' + escapeHtml(b.title) +
      ' · tier ' + b.tier + ' · ' + b.points.toLocaleString() + ' points</span>' +
      '<span class="dlpopfed">Fed by ' + rooms + '</span>' +
      '<button data-poptown="' + town.id + '">' + escapeHtml(town.name) + ' &rsaquo;</button>';
    pop.querySelector('button').onclick = function (ev) {
      ev.stopPropagation(); hidePop(); open(town.id);
    };
    popFor = piece.id;
    pop.style.display = 'block';
    placePop();
  }
  function hidePop() { popFor = null; pop.style.display = 'none'; }
  function placePop() {
    var el = popFor && pieces[popFor];
    if (!el) { if (popFor) hidePop(); return; }
    var r = el.getBoundingClientRect(), f = frame.getBoundingClientRect();
    pop.style.left = (r.left + r.width / 2 - f.left) + 'px';
    pop.style.top = (r.top - f.top - 8) + 'px';
  }
  function shownLayer(layer) { return layerState.hidden.indexOf(layer || 'objects') < 0; }
  // The piece a click meant: the one under it, or failing that the nearest
  // within a few screen pixels. Zoomed out a flower is a pixel across, and a
  // pixel cannot be clicked.
  function nearestPiece(clientX, clientY, reach) {
    var best = null, bestD = reach;
    D.world.forEach(function (p) {
      var el = pieces[p.id];
      if (!el || !shownLayer(p.l)) return;
      var r = el.getBoundingClientRect();
      var dx = Math.max(r.left - clientX, 0, clientX - r.right);
      var dy = Math.max(r.top - clientY, 0, clientY - r.bottom);
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d <= bestD) { bestD = d; best = p; }
    });
    return best;
  }
  // Everything selected moves together, by the pointer's travel in map units.
  function dragSelection(ev, el) {
    if (heldSay('move')) return;
    var start = {x: ev.clientX, y: ev.clientY}, travelled = 0;
    var group = selectedPieces().map(function (p) { return {p: p, x: p.x, y: p.y}; });
    try { el.setPointerCapture(ev.pointerId); } catch (e) {}
    el.classList.add('dragging');
    function onMove(move) {
      var dx = move.clientX - start.x, dy = move.clientY - start.y;
      travelled = Math.abs(dx) + Math.abs(dy);
      if (travelled <= 3 || !nat.w) return;
      group.forEach(function (g) {
        g.p.x = g.x + (dx / view.k / nat.w) * 100;
        g.p.y = g.y + (dy / view.k / nat.h) * 100;
        var node = pieces[g.p.id];
        if (node) {
          node.style.left = g.p.x + '%'; node.style.top = g.p.y + '%';
          stackZ(node, g.p);
        }
      });
      placeMarks();
    }
    function onUp() {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
      el.classList.remove('dragging');
      try { el.releasePointerCapture(ev.pointerId); } catch (e) {}
      if (travelled <= 3) return;
      decorPost({action: 'move_many', moves: group.map(function (g) {
        return {piece_id: g.p.id, x: Math.round(g.p.x * 1000) / 1000,
                y: Math.round(g.p.y * 1000) / 1000};
      })}, function () { kitSay(group.length === 1 ? 'Moved.' : 'Moved ' + group.length + '.'); renderPlaced(); },
      function () {
        // Refused (a building dragged out of its town's area): back it goes.
        group.forEach(function (g) {
          g.p.x = g.x; g.p.y = g.y;
          var node = pieces[g.p.id];
          if (node) { node.style.left = g.x + '%'; node.style.top = g.y + '%'; }
        });
        placeMarks();
      });
    }
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);
  }

  // The frame asks the tool first. True means the tool took the gesture.
  var g0 = null, boxEl = document.getElementById('dlbox');
  function toolDown(ev) {
    if (ev.button !== 0 || !nat.w) return false;
    // A town being moved is placed by a plain click; a town is opened by one.
    if (armed || (ev.target.closest && ev.target.closest('.dltown'))) return false;
    if (tool === 'brush' && (armedAsset || forestErasing())) { brushStart(ev); return true; }
    if (tool === 'pointer') {
      // The pointer is only captured once this is a drag: captured at once,
      // the click that follows lands on the frame and nothing under it opens.
      gesture = 'box';
      g0 = {x: ev.clientX, y: ev.clientY, add: ev.shiftKey, id: ev.pointerId, held: false};
      return true;
    }
    return false;
  }
  function toolMove(ev) {
    if (gesture === 'brush') { brushMove(ev); return; }
    if (gesture === 'forest') { brushCursor(ev); forestStrokeMove(ev); return; }
    if (gesture === 'box') {
      if (!g0.held && Math.abs(ev.clientX - g0.x) + Math.abs(ev.clientY - g0.y) > 4) {
        g0.held = true;
        try { frame.setPointerCapture(g0.id); } catch (e) {}
      }
      var f = frame.getBoundingClientRect();
      boxEl.style.left = (Math.min(g0.x, ev.clientX) - f.left) + 'px';
      boxEl.style.top = (Math.min(g0.y, ev.clientY) - f.top) + 'px';
      boxEl.style.width = Math.abs(ev.clientX - g0.x) + 'px';
      boxEl.style.height = Math.abs(ev.clientY - g0.y) + 'px';
      boxEl.style.display = 'block';
    }
  }
  function toolUp(ev) {
    var was = gesture;
    gesture = null;
    swallowClick = true;
    setTimeout(function () { swallowClick = false; }, 0);
    if (was === 'brush') { brushEnd(); return; }
    if (was === 'forest') { forestStrokeEnd(); return; }
    if (was === 'box') {
      boxEl.style.display = 'none';
      var travel = Math.abs(ev.clientX - g0.x) + Math.abs(ev.clientY - g0.y);
      if (travel < 4) {
        // A click: the piece it meant, if one is near enough; else let go of
        // everything and close a town.
        var near = nearestPiece(ev.clientX, ev.clientY, 10);
        if (near) {
          if (g0.add) { if (sel[near.id]) delete sel[near.id]; else sel[near.id] = true; selChanged(); }
          else selectOnly([near.id]);
          showTownOf(near);
          return;
        }
        if (!g0.add) selectOnly([]);
        hidePop();
        if (openId && !inOpenArea(ev.clientX, ev.clientY)) closeCard();
        return;
      }
      var a = toMap(Math.min(g0.x, ev.clientX), Math.min(g0.y, ev.clientY));
      var b = toMap(Math.max(g0.x, ev.clientX), Math.max(g0.y, ev.clientY));
      var hit = D.world.filter(function (p) {
        return shownLayer(p.l) && p.x >= a.x && p.x <= b.x && p.y >= a.y && p.y <= b.y;
      }).map(function (p) { return p.id; });
      if (!g0.add) sel = {};
      hit.forEach(function (id) { sel[id] = true; });
      selChanged();
      if (!hit.length) kitSay('Nothing placed in that box.');
    }
  }

  // --- the brush ---------------------------------------------------------- //
  // Members scatter; painting forests is an admin's (no member route).
  var brush = {pat: D.ep.forest_paint ? 'forest' : 'scatter', r: 8, sp: 6, jit: 0.15, flip: true, den: 0.75};
  var STROKE_MAX = 1600;
  var stroke2 = null;   // {items, last, carry, previews}
  function cellsH() {
    return (typeof terr !== 'undefined' && terr.world) ? terr.world.cells_h
      : D.cells_w * (nat.h / nat.w);
  }
  function pxPerCell() { return nat.w * view.k / Math.max(1, D.cells_w); }
  function brushCursor(ev) {
    var cur = document.getElementById('dlbrushcur');
    if (!ev || tool !== 'brush' || !(armedAsset || forestErasing())) { cur.style.display = 'none'; return; }
    var f = frame.getBoundingClientRect(), d = Math.max(6, brush.r * 2 * pxPerCell());
    cur.style.left = (ev.clientX - f.left) + 'px';
    cur.style.top = (ev.clientY - f.top) + 'px';
    cur.style.width = cur.style.height = d + 'px';
    cur.style.display = 'block';
  }
  frame.addEventListener('pointermove', brushCursor);
  frame.addEventListener('pointerleave', function () { brushCursor(null); });
  function toCell(ev) {
    var m = toMap(ev.clientX, ev.clientY);
    return {x: m.x / 100 * D.cells_w, y: m.y / 100 * cellsH()};
  }
  // Forest is painted as a layer of its own (forest_ui.py), not dabbed as pieces.
  function dab(cx, cy) {
    var out = [], n = brush.pat === 'cluster' ? 3 + Math.floor(Math.random() * 3) : 1;
    var reach = brush.pat === 'line' ? brush.r * 0.15 : brush.pat === 'cluster' ? brush.r * 0.5 : brush.r;
    for (var i = 0; i < n; i++) {
      // Uniform over the disc, not bunched at its centre.
      var t = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * reach;
      out.push({x: cx + Math.cos(t) * d, y: cy + Math.sin(t) * d});
    }
    placeAt(out);
  }
  function placeAt(out) {
    out.forEach(function (c) {
      if (stroke2.items.length >= STROKE_MAX) return;
      var id = mix[Math.floor(Math.random() * mix.length)] || armedAsset;
      var a = assetById(id);
      var base = parseFloat(kitScale.value) || 1;
      var s = base * (1 + (Math.random() * 2 - 1) * brush.jit);
      s = a ? Math.min(a.hi, Math.max(a.lo, s)) : s;
      var item = {asset_id: id, x: c.x / D.cells_w * 100, y: c.y / cellsH() * 100,
                  scale: Math.round(s * 100) / 100, flip: brush.flip && Math.random() < 0.5};
      stroke2.items.push(item);
      // A preview where it will land, until the server has it.
      var el = drawPiece({id: 'preview' + stroke2.items.length, a: id, v: '', l: a ? a.layer : 'objects',
                          x: item.x, y: item.y, s: item.scale, f: item.flip});
      el.classList.add('preview');
      delete pieces['preview' + stroke2.items.length];
      stroke2.previews.push(el);
    });
  }
  function brushStart(ev) {
    if (brush.pat === 'forest') {
      // A painted forest: no pieces, one request when the stroke ends.
      gesture = 'forest';
      try { frame.setPointerCapture(ev.pointerId); } catch (e) {}
      forestStrokeStart(ev);
      return;
    }
    gesture = 'brush';
    try { frame.setPointerCapture(ev.pointerId); } catch (e) {}
    var c = toCell(ev);
    stroke2 = {items: [], last: c, carry: 0, previews: []};
    dab(c.x, c.y);
  }
  function brushMove(ev) {
    brushCursor(ev);
    var c = toCell(ev), from = stroke2.last;
    var dx = c.x - from.x, dy = c.y - from.y, len = Math.sqrt(dx * dx + dy * dy);
    if (!len) return;
    // One dab every `spacing` cells of travel, carried across moves so a slow
    // drag and a fast one leave the same trail.
    var step = Math.max(0.5, brush.sp);
    var t = step - stroke2.carry;
    while (t <= len) {
      dab(from.x + dx * t / len, from.y + dy * t / len);
      t += step;
    }
    stroke2.carry = len - (t - step);
    stroke2.last = c;
  }
  function brushEnd() {
    var s = stroke2;
    stroke2 = null;
    if (!s || !s.items.length) return;
    kitSay('Placing ' + s.items.length + '…');
    var batches = [];
    for (var i = 0; i < s.items.length; i += 400) batches.push(s.items.slice(i, i + 400));
    var placed = 0;
    (function next() {
      var batch = batches.shift();
      if (!batch) {
        s.previews.forEach(function (el) { el.remove(); });
        redrawDecor();
        kitSay('Placed ' + placed + '.');
        return;
      }
      decorPost({action: 'place_many', items: batch, landmark: landmarkMode}, function (res) {
        res.pieces.forEach(function (row) {
          D.world.push({id: row.piece_id, a: row.asset_id, v: row.variant || '', l: row.layer || 'objects',
                        x: row.x, y: row.y, s: row.scale, f: !!row.flip,
                        by: String(row.by || ''), bn: row.by_name || '', at: row.at || 0,
                        t: row.town || '', k: !!row.locked});
        });
        placed += res.pieces.length;
        next();
      }, function () { s.previews.forEach(function (el) { el.remove(); }); redrawDecor(); });
    })();
    // A refused stroke must not leave its previews behind.
    setTimeout(function () { s.previews.forEach(function (el) { if (el.parentNode) el.remove(); }); }, 15000);
  }
  document.querySelectorAll('#dlbrushpat button').forEach(function (b) {
    b.onclick = function () {
      brush.pat = b.dataset.pat;
      document.querySelectorAll('#dlbrushpat button').forEach(function (o) { o.classList.toggle('on', o === b); });
      var fm = document.getElementById('dlforestmode'); if (fm) fm.hidden = brush.pat !== 'forest';
    };
  });
  function brushSlider(id, show, set) {
    var el = document.getElementById(id), out = document.getElementById(id + 'n');
    el.oninput = function () { var v = parseFloat(el.value) || 0; set(v); out.textContent = show(v); };
  }
  brushSlider('dlbrad', String, function (v) { brush.r = v; });
  brushSlider('dlbsp', String, function (v) { brush.sp = v; });
  brushSlider('dlbjit', function (v) { return v + '%'; }, function (v) { brush.jit = v / 100; });
  brushSlider('dlbden', function (v) { return v + '%'; }, function (v) { brush.den = v / 100; });
  document.getElementById('dlbflip').onchange = function () { brush.flip = this.checked; };

  // --- what you placed ---------------------------------------------------- //
  var placedWho = document.getElementById('dlplacedwho');
  function renderPlaced() {
    var pane = document.getElementById('dlkitplaced');
    if (!pane || pane.hidden) return;
    var mine = placedWho.value === 'me';
    var rows = D.world.filter(function (p) {
      return D.ep.player ? mayTouch(p) : (!mine || (p.by && p.by === D.me));
    });
    rows.sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
    document.getElementById('dlplacedn').textContent = rows.length + (rows.length === 1 ? ' piece' : ' pieces');
    var shown = rows.slice(0, 300);
    var list = document.getElementById('dlplacedlist');
    list.innerHTML = shown.map(function (p) {
      var a = assetById(p.a);
      var who = mine ? '' : ' · ' + escapeHtml(p.bn || (p.by ? 'someone' : 'from before names were kept'));
      return '<div class="dlplaced' + (sel[p.id] ? ' on' : '') + (a && a.px ? ' px' : '') + '" data-id="' + p.id + '">' +
        '<img alt="" loading="lazy" src="' + assetUrl(p.a) + '">' +
        '<div>' + (p.k ? '&#128274; ' : '') + escapeHtml(a ? a.name : 'A removed tile') +
        '<small>' + Math.round(p.x / 100 * D.cells_w) + ', ' + Math.round(p.y / 100 * cellsH()) +
        ' · ' + escapeHtml(p.l || 'objects') + who + '</small></div>' +
        '<button data-del="' + p.id + '" title="Remove it">×</button></div>';
    }).join('') + (rows.length > shown.length
      ? '<p class="dlkithint">And ' + (rows.length - shown.length) + ' more.</p>' : '') +
      (!rows.length ? '<p class="dlkithint">' + (mine ? 'Nothing placed by you yet.' : 'Nothing placed yet.') + '</p>' : '');
    list.querySelectorAll('.dlplaced').forEach(function (row) {
      row.onclick = function (ev) {
        var id = row.dataset.id, p = pieceById(id);
        if (ev.target.dataset.del) {
          sel = {}; sel[id] = true; removeSelection(); return;
        }
        if (!p) return;
        // Off its layer it cannot be grabbed, so editing moves to its layer.
        if ((p.l || 'objects') !== editLayer()) { layerState.edit = p.l || 'objects'; applyLayers(); fillKitCats(); renderKit(); }
        selectOnly([id]);
        // Centred on it, at a zoom where it can be seen.
        if (view.k < 8 / WS) view.k = Math.min(kMax(), 8 / WS);
        view.x = frame.clientWidth / 2 - p.x / 100 * nat.w * view.k;
        view.y = frame.clientHeight / 2 - p.y / 100 * nat.h * view.k;
        clamp(); apply();
      };
    });
  }
  placedWho.onchange = renderPlaced;
  document.querySelectorAll('.dlkittabs button').forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll('.dlkittabs button').forEach(function (o) { o.classList.toggle('on', o === b); });
      document.getElementById('dlkitlib').hidden = b.dataset.tab !== 'lib';
      document.getElementById('dlkitplaced').hidden = b.dataset.tab !== 'placed';
      renderPlaced();
    };
  });

  window.addEventListener('keydown', function (ev) {
    var t = ev.target, tag = t && t.tagName;
    var key = (ev.key || '').toLowerCase();
    // Escape puts down whatever is in hand, even from a field in a drawer.
    if (key === 'escape') {
      if (t && t.blur && tag !== 'BODY') t.blur();
      putDown();
      return;
    }
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var pick = {v: 'pointer', h: 'hand', p: 'pencil', b: 'brush'}[key];
    if (pick && D.assets.length) { setTool(pick); ev.preventDefault(); return; }
    if ((key === 'delete' || key === 'backspace') && selIds().length) { ev.preventDefault(); removeSelection(); return; }
  });

  // Put down whatever is in hand — Escape, or a right click on the map. A tile
  // armed in the kit, a brush mix, a building from a town's card, a building
  // being moved, a town being moved, the terrain brush, a selection, a stroke
  // or a box half drawn: all of it, and back to the hand.
  function putDown() {
    hidePop();
    armedAsset = null; mix = []; building = null; relocating = null; gating = null;
    if (gesture === 'brush' && stroke2) {
      stroke2.previews.forEach(function (el) { el.remove(); });
      stroke2 = null;
    }
    if (gesture === 'forest') forestStrokeCancel();
    gesture = null;
    boxEl.style.display = 'none';
    if (armed) { armed = null; renderList(); }
    frame.classList.remove('placing');
    ghost.classList.remove('live');
    if (typeof terrPutDown === 'function') terrPutDown();
    if (selIds().length) selectOnly([]);
    setTool('hand', true);
    renderKit();
    hint.textContent = 'Drag to move, scroll to zoom';
    kitSay('');
  }
  // Holding the wheel would otherwise start the browser's autoscroll.
  frame.addEventListener('mousedown', function (ev) { if (ev.button === 1) ev.preventDefault(); });
  frame.addEventListener('auxclick', function (ev) { if (ev.button === 1) ev.preventDefault(); });
  frame.addEventListener('contextmenu', function (ev) {
    ev.preventDefault();
    putDown();
  });

  if (D.ep.player) {
    document.querySelectorAll('.dlzoom [data-tool="pencil"], .dlzoom [data-tool="brush"]').forEach(function (b) {
      b.hidden = true;
    });
    if (tool === 'pencil' || tool === 'brush') tool = 'hand';
  }
  // The tool remembered from last time, without opening the toolkit: a page
  // that opens with a drawer nobody asked for looks like the click did it.
  setTool(tool, true);
  kitSay('');
  // --- life: people and animals ------------------------------------------ //
  // People walk inside their town's area of influence, going from one spot in
  // it to another and stopping a while; animals do the same inside a zoo that
  // stands on the map. Who walks is the town's buildings (townart.LIFE): an
  // inn brings drinkers and a dog, a keep a horse. Each walker, like each
  // house, is its own element standing at its ground point, so it takes its
  // depth from where it stands (see `depth`) and passes behind a building that
  // is lower on the map. Only animated while close enough to see and while the
  // tab is visible.
  var LIFE = D.life || {}, walkers = [], lifeLast = 0, lifeRaf = null;
  function sprite(name, colour, hat) {
    var body = name === 'person' ? (LIFE.hats || [])[hat || 0] : (LIFE.sprites || {})[name];
    return String(body || '').split('@C@').join(colour);
  }
  // Spots inside an area, found once: random points kept if the area's fill
  // contains them.
  function spotsIn(fill, count) {
    var svg = fill.ownerSVGElement, out = [], box = fill.getBBox(), tries = 0;
    var pt = svg.createSVGPoint();
    while (out.length < count && tries < count * 40) {
      tries++;
      pt.x = box.x + Math.random() * box.width;
      pt.y = box.y + Math.random() * box.height;
      try { if (fill.isPointInFill(pt)) out.push({x: pt.x, y: pt.y}); } catch (e) { return out; }
    }
    return out;
  }
  // Something standing on the map, drawn in town-art units: an element whose
  // ground point (the art's own 0, groundY) is placed at a spot in cells.
  // `box` is the art's extent [x, y, w, h] in its own units.
  // ``bare``: no shadow (a figure that changes shape as it goes).
  function standing(cls, body, box, groundY, cellsPerUnit, bare) {
    var el = document.createElement('div');
    el.className = 'dlstand ' + cls;
    el.innerHTML = '<svg viewBox="' + box.join(' ') + '" preserveAspectRatio="xMidYMax meet">' + body + '</svg>';
    if (!bare) addShadow(el, svgPicture(box, body), cls.indexOf(' flip') >= 0);
    el.style.width = (box[2] * cellsPerUnit / terr.world.cells_w * 100) + '%';
    var fx = -box[0] / box[2] * 100, fy = (groundY - box[1]) / box[3] * 100;
    el.style.transform = 'translate(' + (-fx).toFixed(2) + '%,' + (-fy).toFixed(2) + '%)';
    world.appendChild(el);
    return el;
  }
  function stand(el, x, y) {
    var px = x / terr.world.cells_w * 100, py = y / terr.world.cells_h * 100;
    el.style.left = px + '%'; el.style.top = py + '%';
    el.style.zIndex = depth(py);
  }
  var WALKER_BOX = [-5, -9, 10, 12];
  function addWalker(kind, colour, hat, zone, at) {
    var animal = kind !== 'person' && kind !== 'child';
    var scale = kind === 'horse' ? 0.30 : kind === 'child' ? 0.17 : 0.21;
    // People are drawn standing on y = 2.6, animals on y = 0.
    var el = standing('dlwalker', sprite(kind, colour, hat), WALKER_BOX, animal ? 0 : 2.6, scale);
    var w = {el: el, art: el.firstChild, x: at.x, y: at.y, tx: at.x, ty: at.y, kind: kind,
             wait: Math.random() * 3, face: 1, zone: zone,
             speed: (animal ? 1.6 : 1.1) * (0.75 + Math.random() * 0.5)};
    walkers.push(w);
    stand(el, at.x, at.y);
    return w;
  }
  // --- the runaway horse (web/dodoland/horse_api.py) ---------------------- //
  // The server says where it is; a click is a kick from where the pointer is,
  // and the server says where it bolted to (away from the click, a little
  // randomly) and whether it ran into a zoo. Everybody sees the same horse:
  // it is asked for again every so often and gallops to where it is now.
  var horse = {el: null, x: 0, y: 0, busy: false, line: ''};
  function horseCells(st) {
    return {x: st.x / 100 * terr.world.cells_w, y: st.y / 100 * terr.world.cells_h};
  }
  function horseSay(text, ms) {
    if (!horse.el) return;
    var b = horse.el.querySelector('.dlhorsesay');
    if (!b) { b = document.createElement('div'); b.className = 'dlhorsesay'; horse.el.appendChild(b); }
    b.textContent = text; b.classList.add('on');
    clearTimeout(horse.sayT);
    horse.sayT = setTimeout(function () { b.classList.remove('on'); }, ms || 2600);
  }
  function horseDraw(st) {
    if (!st.on) { if (horse.el) { horse.el.remove(); horse.el = null; } return; }
    var at = horseCells(st);
    if (!horse.el) {
      horse.el = standing('dlhorse dlkeep', sprite('horse', '#8a5a34'), WALKER_BOX, 0, 0.42);
      horse.el.title = 'A horse. It does not look like it wants to go back to the zoo.';
      horse.x = at.x; horse.y = at.y;
      stand(horse.el, at.x, at.y);
      return;
    }
    if (!horse.busy && (Math.abs(at.x - horse.x) > 0.3 || Math.abs(at.y - horse.y) > 0.3)) horseRun(at, null);
  }
  // Gallops from where it is to ``to`` (cells), facing the way it goes.
  function horseRun(to, done) {
    var from = {x: horse.x, y: horse.y}, dist = Math.hypot(to.x - from.x, to.y - from.y);
    var ms = Math.max(350, dist * 85), t0 = performance.now();
    horse.busy = true;
    horse.el.classList.add('running');
    var art = horse.el.querySelector('svg');
    if (art) art.style.transform = to.x < from.x ? 'scaleX(-1)' : '';
    (function step(now) {
      var t = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - t, 2);
      horse.x = from.x + (to.x - from.x) * e; horse.y = from.y + (to.y - from.y) * e;
      stand(horse.el, horse.x, horse.y);
      if (t < 1) { requestAnimationFrame(step); return; }
      horse.busy = false;
      horse.el.classList.remove('running');
      if (done) done();
    })(t0);
  }
  function horseKick(ev) {
    ev.stopPropagation(); ev.preventDefault();
    if (horse.busy || !D.ep.horse) return;
    var f = frame.getBoundingClientRect();
    var fx = (ev.clientX - f.left - view.x) / (nat.w * view.k) * 100;
    var fy = (ev.clientY - f.top - view.y) / (nat.h * view.k) * 100;
    horseSay(horse.line || 'NO!! I am not coming back to the zoo!!! Nay-nay-nay!!!');
    fetch(D.ep.horse, {method: 'POST', headers: {'Content-Type': 'application/json'},
                       body: JSON.stringify({x: fx, y: fy})})
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok || !horse.el) return;
        horseRun(horseCells(res), function () {
          if (!res.caught) return;
          var owner = byId[res.caught.owner];
          horseSay('🍬 × ' + (res.sweetrolls || 0) + ' for ' + (owner ? owner.name : 'the zoo') + '!', 3200);
          horse.el.classList.add('gone');
          setTimeout(function () { horseDraw({on: false}); }, 3400);
        });
      })
      .catch(function () {});
  }
  function horsePoll() {
    if (!D.ep.horse || !terr.world || !nat.w) { setTimeout(horsePoll, 2000); return; }
    fetch(D.ep.horse).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) return;
      horse.line = res.line || horse.line;
      horseDraw(res);
      setTimeout(horsePoll, res.on ? 20000 : Math.min(600000, Math.max(20000, (res.back_in || 600) * 1000)));
    }).catch(function () { setTimeout(horsePoll, 60000); });
  }
  setTimeout(horsePoll, 1500);
  // --- real members on the roads ------------------------------------------- //
  // One traveller per person (travel_api.py), touring the towns of the
  // people they talk to most: home, one town, the next, and back the same
  // way, round and round, on ways worked out over the terrain (round the
  // water, along the paths). As big as anybody, in their own colours (the
  // town card's "Your traveller"), a gold ring at their feet, their picture
  // over their heads, a torch from dusk to dawn; on horseback outside the
  // towns. Only the pets they chose follow them.
  var travellers = [], travelRaf = null, travelLast = 0, TRAVEL = null;
  function roadPoints(d) {
    var nums = String(d || '').match(/-?\d+(\.\d+)?/g) || [], out = [];
    for (var i = 0; i + 1 < nums.length; i += 2) out.push({x: +nums[i], y: +nums[i + 1]});
    return out;
  }
  function travelLoad() {
    if (TRAVEL !== null || !D.ep.base) return;
    TRAVEL = {tours: [], routes: {}};
    fetch(D.ep.base + '/travel').then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (res) { TRAVEL = {tours: res.tours || [], routes: res.routes || {}}; travellersReset(); })
      .catch(function () {});
  }
  // The legs of a tour in the order walked: out through the stops, then back.
  function tourLegs(stops) {
    var out = [];
    function leg(a, b) {
      var lo = a < b ? a : b, hi = a < b ? b : a, pts = roadPoints(TRAVEL.routes[lo + '|' + hi]);
      if (pts.length < 2) return null;
      if (a !== lo) pts = pts.slice().reverse();
      var len = [0];
      for (var j = 1; j < pts.length; j++) len.push(len[j - 1] + Math.hypot(pts[j].x - pts[j - 1].x, pts[j].y - pts[j - 1].y));
      return {pts: pts, len: len, to: b};
    }
    for (var i = 0; i + 1 < stops.length; i++) { var f = leg(stops[i], stops[i + 1]); if (f) out.push(f); }
    for (var k = stops.length - 1; k > 0; k--) { var g = leg(stops[k], stops[k - 1]); if (g) out.push(g); }
    return out;
  }
  function travellersReset() {
    travellers.forEach(function (t) { t.el.remove(); (t.pets || []).forEach(function (q) { q.el.remove(); }); });
    travellers = [];
    if (!terr.world) return;
    if (TRAVEL === null) { travelLoad(); return; }
    TRAVEL.tours.forEach(function (tour, n) {
      var walker = byId[tour.w], legs = tourLegs(tour.stops || []);
      if (!walker || !legs.length) return;
      var look = walker.look || {}, colour = ['#ff3b3b', '#ffb000', '#00b7ff', '#ff4fd8', '#2fe36b', '#ffe14d'][n % 6];
      // The torch is lit from dusk to dawn (.dldark on the world, drawNight).
      var torch = '<g class="dltorch"><line x1="2.6" y1="0" x2="3.4" y2="-5" stroke="#6b4423" stroke-width="0.55"/>' +
                  '<circle class="dlflame" cx="3.5" cy="-5.6" r="0.95" fill="#ffb84d"/></g>';
      var ring = '<ellipse class="dltring" cx="0" cy="2.6" rx="3.2" ry="0.95" fill="none" stroke="#ffd257" stroke-width="0.45"/>';
      var me = String(LIFE.member || '').split('@H@').join(look.head || '#f2c9a0').split('@B@').join(look.body || colour) + torch;
      var ride = '<g transform="translate(0 2.6) scale(1.35)">' + sprite('horse', look.horse || '#7a4e2c') + '</g>' +
                 '<g transform="translate(0 -3.2) scale(0.9)">' + me + '</g>';
      var el = standing('dlwalker dltraveller dlkeep',
                        ring + '<g class="tw">' + me + '</g><g class="tr">' + ride + '</g>', WALKER_BOX, 2.6, 0.21, true);
      if (walker.av) el.insertAdjacentHTML('beforeend', '<img class="dltface" alt="" src="' + walker.av + '">');
      // Spread out: each starts somewhere along their round.
      var start = Math.floor(Math.random() * legs.length);
      var t = {el: el, who: walker, legs: legs, leg: start, at: Math.random() * legs[start].len[legs[start].len.length - 1],
               rest: 0, speed: 1.1 + Math.random() * 0.4};
      t.pets = (walker.follow || []).map(function (pet, j) {
        var furs = ['#8a6a4a', '#d9a066', '#5a5050', '#e8dcc8', '#c47a3a', '#2f2a28'];
        var pel = standing('dlwalker dlpet dlkeep', sprite(pet.k === 'dog' ? 'dog' : 'cat', furs[(pet.n.length + j) % furs.length]),
                           WALKER_BOX, 0, 0.21, true);
        pel.title = pet.n + (pet.t ? ' (' + pet.t + ')' : '');
        return {el: pel, lag: 1.1 * (j + 1), pet: pet};
      });
      travellers.push(t);
      travellerPlace(t);
    });
    if (travellers.length && !travelRaf) travelRaf = requestAnimationFrame(travelStep);
  }
  function legAt(leg, s) {
    s = Math.max(0, Math.min(s, leg.len[leg.len.length - 1]));
    var i = 1;
    while (i < leg.len.length - 1 && leg.len[i] < s) i++;
    var a = leg.pts[i - 1], b = leg.pts[i], f = (s - leg.len[i - 1]) / ((leg.len[i] - leg.len[i - 1]) || 1);
    return {x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, dx: b.x - a.x};
  }
  function travellerPlace(t) {
    var leg = t.legs[t.leg], p = legAt(leg, t.at);
    var face = p.dx < 0 ? -1 : 1;
    if (face !== t.face) { t.face = face; var art = t.el.querySelector('svg'); if (art) art.style.transform = face < 0 ? 'scaleX(-1)' : ''; }
    t.x = p.x; t.y = p.y;
    stand(t.el, p.x, p.y);
    (t.pets || []).forEach(function (q) { var at = legAt(leg, t.at - q.lag); stand(q.el, at.x, at.y); });
    // Inside a town's area on foot, outside it on horseback; asked twice a second.
    var now = performance.now();
    if (!t.asked || now - t.asked > 500) {
      t.asked = now;
      var riding = !inTown(p.x, p.y);
      if (riding !== t.riding) { t.riding = riding; t.el.classList.toggle('riding', riding); }
    }
  }
  var inflPt = null;
  function inTown(x, y) {
    var g = document.getElementById('dltinfl');
    if (!g) return true;
    var svg = g.ownerSVGElement;
    inflPt = inflPt || (svg && svg.createSVGPoint());
    if (!inflPt) return true;
    inflPt.x = x; inflPt.y = y;
    var paths = g.querySelectorAll('g[data-town] path');
    for (var i = 0; i < paths.length; i++) {
      try { if (paths[i].isPointInFill(inflPt)) return true; } catch (e) { return true; }
    }
    return false;
  }
  function travelStep(now) {
    travelRaf = null;
    var dt = Math.min(0.1, (now - (travelLast || now)) / 1000);
    travelLast = now;
    if (!travellers.length) return;
    if (!world.classList.contains('lifefar') && !document.hidden) {
      travellers.forEach(function (t) {
        if (t.rest > 0) { t.rest -= dt; return; }
        t.at += t.speed * dt;
        var leg = t.legs[t.leg], end = leg.len[leg.len.length - 1];
        // At each town a rest, then on to the next.
        if (t.at >= end) { t.leg = (t.leg + 1) % t.legs.length; t.at = 0; t.rest = 3 + Math.random() * 5; }
        travellerPlace(t);
      });
    }
    travelRaf = requestAnimationFrame(travelStep);
  }
  function travellerSay(t, text) {
    var b = t.el.querySelector('.dlhorsesay');
    if (!b) { b = document.createElement('div'); b.className = 'dlhorsesay'; t.el.appendChild(b); }
    b.textContent = text; b.classList.add('on');
    clearTimeout(t.sayT);
    t.sayT = setTimeout(function () { b.classList.remove('on'); }, 2600);
  }
  var travelCard = document.createElement('div');
  travelCard.className = 'dltcard';
  frame.appendChild(travelCard);
  function travellerCard(t, ev) {
    var f = frame.getBoundingClientRect(), going = byId[t.legs[t.leg].to] || {name: 'the next town'};
    travelCard.innerHTML = (t.who.av ? '<img alt="" src="' + t.who.av.replace(/size=\d+/, 'size=256') + '">' : '') +
      '<b>' + escapeHtml(t.who.owner || t.who.name) + '</b>' +
      '<span>' + (t.rest > 0 ? 'resting before ' : 'on the road to ') + escapeHtml(going.name) + '</span>' +
      '<small>visiting the towns of the people they talk to most</small>';
    cardOver(t.el);
  }
  frame.addEventListener('pointerdown', function () { travelCard.classList.remove('on'); });
  // What a press lands on, among the things that move: checked before the
  // map's own handling, so whatever lies over them (a forest, the ground
  // layers) never takes the click. Topmost first: the horse, then travellers,
  // then their pets.
  function figureAt(x, y) {
    function hit(el, pad) {
      if (!el || !el.isConnected) return false;
      var r = el.getBoundingClientRect();
      return r.width > 0 && x >= r.left - pad && x <= r.right + pad && y >= r.top - pad && y <= r.bottom + pad;
    }
    if (horse.el && !horse.el.classList.contains('gone') && hit(horse.el, 6)) return {act: horseKick};
    for (var i = 0; i < travellers.length; i++) {
      var t = travellers[i];
      if (getComputedStyle(t.el).display === 'none') continue;
      if (hit(t.el, 4)) return {act: function (ev) {
        if (t.riding) travellerSay(t, D.sizes.horse_busy || "Nay, I'm on a business trip right now");
        travellerCard(t, ev);
      }};
      for (var j = 0; j < (t.pets || []).length; j++) {
        if (hit(t.pets[j].el, 3)) {
          var q = t.pets[j];
          return {act: function (ev) { petCard({pet: q.pet, owner: t.who, el: q.el}, ev); }};
        }
      }
    }
    return null;
  }
  // Asked in the capture phase, before anything under the pointer (a town, a
  // building - which keep their presses to themselves) sees the press.
  frame.addEventListener('pointerdown', function (ev) {
    figPress = null;
    if (ev.button !== 0 || (typeof terr !== 'undefined' && terr.armed !== null)) return;
    var fig = figureAt(ev.clientX, ev.clientY);
    if (fig) { figPress = fig; ev.stopPropagation(); ev.preventDefault(); }
  }, true);
  frame.addEventListener('click', function (ev) {
    if (!figPress) return;
    var fig = figPress;
    figPress = null;
    ev.stopPropagation(); ev.preventDefault();
    fig.act(ev);
  }, true);
  // A card over a figure: centred above it, clear of the rider and their
  // picture; below it when there is no room above.
  function cardOver(el) {
    var f = frame.getBoundingClientRect(), r = el.getBoundingClientRect();
    travelCard.classList.add('on');
    var w = travelCard.offsetWidth, h = travelCard.offsetHeight;
    var left = Math.max(8, Math.min(f.width - w - 8, r.left - f.left + r.width / 2 - w / 2));
    var top = r.top - f.top - h - 46;
    if (top < 8) top = r.bottom - f.top + 12;
    travelCard.style.left = left + 'px';
    travelCard.style.top = top + 'px';
  }
  // A traveller's pet: clicking it shows it.
  function petCard(w, ev) {
    var f = frame.getBoundingClientRect(), pet = w.pet;
    travelCard.innerHTML = (pet.u ? '<img class="pet" alt="" src="' + escapeHtml(pet.u) + '">' : '') +
      '<b>' + escapeHtml(pet.n || 'A pet') + '</b><span>' + escapeHtml(pet.t || '') + '</span>' +
      '<small>' + escapeHtml(w.owner.owner || w.owner.name) + '\'s ' + (pet.k === 'dog' ? 'dog' : 'cat') + '</small>';
    cardOver(w.el);
  }
  // A town's ordinary houses: scattered through its area, thickest around the
  // hall, kept clear of the hall and of the buildings it has placed, and the
  // same every time for the same town (a seeded shuffle, not Math.random).
  function seeded(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  var HOUSE_BOX = [-7, -11, 14, 12];
  // Each house is a number (0, 1, 2…) and keeps it: its shape, its colour and
  // which way it faces come from the town and that number alone, and so does
  // where it stands — unless somebody has moved it, in which case the town's
  // record says where (p.house_at). Moved houses are laid first, so the rest
  // keep clear of them.
  function drawHouses(p, fill) {
    var n = Math.min(p.houses || 0, 80), cottages = LIFE.cottages || [];
    if (!n || !cottages.length) return;
    var cw = terr.world.cells_w, ch = terr.world.cells_h;
    var hx = p.plot.x / 100 * cw, hy = p.plot.y / 100 * ch;
    var scale = 1 / (LIFE.units_per_cell || 3.4);           // town-art units to cells
    var keep = [{x: hx, y: hy - 3, r: 7}];                   // the hall and its steps
    D.world.forEach(function (q) {
      // Clear of its own buildings, and of every landmark.
      if (q.t !== String(p.id) && !q.k) return;
      var a = assetById(q.a), w = ((a && a.wc) || 8) * (q.s || 1);
      keep.push({x: q.x / 100 * cw, y: q.y / 100 * ch - w * 0.2, r: w * 0.45});
    });
    var seed = parseInt(String(p.id).slice(-9), 10) || 7;
    var at = p.house_at || {}, out = [];
    for (var i = 0; i < n; i++) {
      var look = seeded(seed * 31 + i * 7919);
      var house = {i: i, c: cottages[Math.floor(look() * cottages.length)], f: look() < 0.5};
      if (at[i]) {
        house.x = at[i][0] / 100 * cw; house.y = at[i][1] / 100 * ch; house.moved = true;
        keep.push({x: house.x, y: house.y, r: 2.6});
      }
      out.push(house);
    }
    var svg = fill.ownerSVGElement, pt = svg.createSVGPoint();
    var reach = 10 + Math.sqrt(n) * 4;
    out.forEach(function (house) {
      if (house.moved) return;
      var rand = seeded(seed + house.i * 104729);
      for (var tries = 0; tries < 80; tries++) {
        // Nearer the hall more often: a town is densest at its centre.
        var t = rand() * Math.PI * 2, d = reach * Math.pow(rand(), 0.75) + 6;
        pt.x = hx + Math.cos(t) * d; pt.y = hy + Math.sin(t) * d * 0.8;
        try { if (!fill.isPointInFill(pt)) continue; } catch (e) { return; }
        var clash = keep.some(function (k) {
          var dx = pt.x - k.x, dy = pt.y - k.y; return dx * dx + dy * dy < k.r * k.r;
        });
        if (clash) continue;
        house.x = pt.x; house.y = pt.y;
        keep.push({x: pt.x, y: pt.y, r: 2.6});
        return;
      }
    });
    // Who may move these: an admin any town's, a member their own.
    var movable = !D.ep.player || String(p.id) === String(D.me);
    out.forEach(function (h) {
      if (h.x === undefined) return;
      var el = standing('dlhouse' + (movable ? ' movable' : '') + (h.f ? ' flip' : ''), h.c, HOUSE_BOX, 0, scale);
      el.dataset.town = p.id; el.dataset.i = h.i; el.dataset.x = h.x; el.dataset.y = h.y;
      stand(el, h.x, h.y);
      if (movable) el.addEventListener('pointerdown', grabHouse);
    });
  }
  // Moving a house: grab it with the pointer or the hand and put it down
  // inside its town's area. Houses are never removed, only moved.
  function grabHouse(ev) {
    if (ev.button !== 0 || frame.classList.contains('placing') || frame.classList.contains('painting')) return;
    ev.stopPropagation(); ev.preventDefault();
    var el = ev.currentTarget;
    var from = {x: parseFloat(el.dataset.x), y: parseFloat(el.dataset.y)};
    var start = {x: ev.clientX, y: ev.clientY}, now = {x: from.x, y: from.y}, travelled = 0;
    var perCell = nat.w * view.k / terr.world.cells_w;
    try { el.setPointerCapture(ev.pointerId); } catch (e) {}
    el.classList.add('dragging');
    function move(m) {
      travelled = Math.abs(m.clientX - start.x) + Math.abs(m.clientY - start.y);
      now.x = from.x + (m.clientX - start.x) / perCell;
      now.y = from.y + (m.clientY - start.y) / perCell;
      stand(el, now.x, now.y);
    }
    function up() {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.classList.remove('dragging');
      swallowClick = true; setTimeout(function () { swallowClick = false; }, 0);
      if (travelled <= 3) return;
      var town = byId[el.dataset.town], i = el.dataset.i;
      var x = Math.round(now.x / terr.world.cells_w * 100 * 1000) / 1000;
      var y = Math.round(now.y / terr.world.cells_h * 100 * 1000) / 1000;
      fetch(D.ep.town, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: el.dataset.town, house: {i: +i, x: x, y: y}})
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (!res.ok) {
          // Outside the town's area: back where it was.
          stand(el, from.x, from.y);
          hint.textContent = res.error || 'That house could not go there.';
          return;
        }
        el.dataset.x = now.x; el.dataset.y = now.y;
        if (town) { town.house_at = town.house_at || {}; town.house_at[i] = [x, y]; }
        hint.textContent = 'House moved.';
      });
    }
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }
  function buildLife() {
    walkers = [];
    if (typeof terr === 'undefined' || !terr.world) return;
    world.querySelectorAll('.dlstand:not(.dlkeep)').forEach(function (n) { n.remove(); });
    // Houses stand whether or not anybody walks between them.
    D.people.forEach(function (p) {
      if (!p.plot || !p.houses) return;
      var g = document.querySelector('#dltinfl > g[data-town="' + p.id + '"]');
      var fill = g && g.querySelector('path');
      if (fill) drawHouses(p, fill);
    });
    if (!LIFE.on) return;
    var strongest = Math.max.apply(null, D.people.map(function (p) { return p.power || 0; }).concat([1]));
    D.people.forEach(function (p) {
      if (!p.plot) return;
      var g = document.querySelector('#dltinfl > g[data-town="' + p.id + '"]');
      var fill = g && g.querySelector('path');
      if (!fill) return;
      var spots = spotsIn(fill, 80);
      if (!spots.length) return;
      // Who walks here: one from each building family in turn, as in the town art.
      var pools = p.built.map(function (b) {
        return (LIFE.pools || {})[(LIFE.shapes || {})[b.key]] || LIFE.default || ['person'];
      });
      if (!pools.length) pools = [LIFE.default || ['person']];
      var crowd = 2 + Math.round((Math.max(2, LIFE.max || 12) - 2) * Math.sqrt((p.power || 0) / strongest));
      var colours = LIFE.colours || ['#5b4630'];
      for (var i = 0; i < crowd; i++) {
        var pool = pools[i % pools.length];
        var kind = pool[Math.floor(i / pools.length) % pool.length];
        addWalker(kind, colours[i % colours.length], i % 3,
                  {type: 'area', spots: spots}, spots[Math.floor(Math.random() * spots.length)]);
      }

      // The zoo: animals inside it, more for each tier it has reached.
      var zoo = LIFE.zoo && townPiece(p, LIFE.zoo), tier = townTier(p, LIFE.zoo);
      var meta = zoo && assetById(currentTile(p, LIFE.zoo) ? currentTile(p, LIFE.zoo).id : zoo.a);
      if (zoo && tier && meta) {
        var w = (meta.wc || 8) * (zoo.s || 1);
        var cx = zoo.x / 100 * terr.world.cells_w, cy = zoo.y / 100 * terr.world.cells_h - w * 0.2;
        var kinds = LIFE.zoo_kinds || ['cat', 'dog'];
        var hues = ['#8a6a4a', '#b08a5a', '#6e5a48', '#c9a36a', '#7d6b5d', '#a8907a'];
        for (var j = 0; j < (LIFE.per_tier || 2) * tier; j++) {
          var zone = {type: 'zoo', cx: cx, cy: cy, r: w * 0.32};
          addWalker(kinds[j % kinds.length], hues[j % hues.length], 0, zone,
                    {x: cx + (Math.random() - 0.5) * zone.r, y: cy + (Math.random() - 0.5) * zone.r * 0.6});
        }
      }
    });
    if (!lifeRaf && walkers.length) lifeRaf = requestAnimationFrame(stepLife);
    travellersReset();
  }
  function nextSpot(w) {
    if (w.zone.type === 'zoo') {
      var t = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * w.zone.r;
      return {x: w.zone.cx + Math.cos(t) * d, y: w.zone.cy + Math.sin(t) * d * 0.6};
    }
    // Somewhere not too far: the nearest of a few random spots.
    var best = null, bestD = Infinity, spots = w.zone.spots;
    for (var i = 0; i < 4; i++) {
      var s = spots[Math.floor(Math.random() * spots.length)];
      var d2 = (s.x - w.x) * (s.x - w.x) + (s.y - w.y) * (s.y - w.y);
      if (d2 < bestD) { bestD = d2; best = s; }
    }
    return best;
  }
  function stepLife(now) {
    lifeRaf = null;
    if (!walkers.length) return;
    var dt = Math.min(0.25, (now - (lifeLast || now)) / 1000);
    lifeLast = now;
    var close = typeof terr !== 'undefined' && terr.world &&
      nat.w * view.k / terr.world.cells_w >= ((D.sizes.lod || {}).life || 0);
    world.classList.toggle('lifefar', !close);   // hides walkers, not houses
    if (close && !document.hidden) {
      walkers.forEach(function (w) {
        if (w.wait > 0) { w.wait -= dt; }
        else {
          var dx = w.tx - w.x, dy = w.ty - w.y, d = Math.sqrt(dx * dx + dy * dy);
          if (d < 0.05) {
            var s = nextSpot(w);
            if (s) { w.tx = s.x; w.ty = s.y; }
            w.wait = Math.random() < 0.5 ? Math.random() * 4 : 0;
          } else {
            var step = Math.min(d, w.speed * dt);
            w.x += dx / d * step; w.y += dy / d * step;
            if (Math.abs(dx) > 0.01) w.face = dx < 0 ? -1 : 1;
          }
        }
        // A small bob while walking reads as walking at four pixels tall.
        var bob = w.wait > 0 ? 0 : Math.abs(Math.sin(now / 160 + w.speed * 7)) * 0.12;
        stand(w.el, w.x, w.y - bob);
        w.art.style.transform = w.face < 0 ? 'scaleX(-1)' : '';
      });
      // Their lanterns move with them.
      if (nightOn && (D.sizes.night || {}).walker_light > 0) nightSoon(true);
    }
    lifeRaf = requestAnimationFrame(stepLife);
  }

  applyLayers();
  fillKitCats();
  renderKit();

""" + terrain_ui.SCRIPT + forest_ui.SCRIPT + nightlights.SCRIPT + r"""
  redraw();
  redrawDecor();
  renderList();
  settleLabel();
  // The towns list opens with the map for admins, who place towns from it; a
  // member opens it when they want it.
  if (!D.ep.player) drawer.classList.add('open');
  placeZoom();
  // Arriving from the entrance page: "Place my town!" lands with placement
  // ready (?place=1), and a member whose town already stands is taken to it.
  if (D.ep.player && D.me && byId[D.me]) {
    var arrive = new URLSearchParams(location.search), mine = byId[D.me];
    if (mine.plot && (arrive.has('place') || arrive.has('mine'))) {
      // Centred once the map knows its size; fit() would undo it before then.
      var goHome = function () {
        if (view.k < 8 / WS) view.k = Math.min(kMax(), 8 / WS);
        view.x = frame.clientWidth / 2 - mine.plot.x / 100 * nat.w * view.k;
        view.y = frame.clientHeight / 2 - mine.plot.y / 100 * nat.h * view.k;
        clamp(); apply();
      };
      if (fit.done) goHome(); else fit.then = goHome;
      open(D.me);
    } else if (!mine.plot && arrive.has('place') && D.ep.settle) {
      settleBtn.onclick();
    }
  }
})();
"""
