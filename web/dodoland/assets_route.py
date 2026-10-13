"""
Serving an uploaded asset's bytes to the panel.

This is all that remains of DodoLand's outward-facing surface, and it is
deliberately small. The public map, the per-player settle page and the ``/town``
command were built and then removed: none of DodoLand is ready to be seen by the
server, and a half-finished thing behind a link somebody can paste is worse than
no thing at all. When it is ready it gets a proper front end with a Discord
login and an account that can manage its own stuff, not a capability URL.

The route is panel-scoped like every other DodoLand route, so an asset is
readable by the same people who can already read the page it appears on.
"""

from __future__ import annotations

from aiohttp import web


async def asset_image(request: web.Request):
    """One tile's first image, for the map toolkit and the decor placed from it.

    The path still says ``asset``: decor rows carry the id in ``asset_id`` and
    the toolkit builds these URLs. It is a tile id since the tile library
    replaced the asset library, and only a tile this server can see is served.
    """
    bot = request.app["bot"]
    guild = request["guild"]
    tile_id = request.match_info.get("aid") or ""
    tile = bot.dodoland_tiles.visible(tile_id, guild.id)
    want = request.query.get("v") or ""
    # ``?v=`` asks for one of the tile's own variants, and only one of its own.
    row = None
    if tile is not None:
        row = (bot.dodoland_tiles.art(want) if want and (want in tile["variants"] or want == tile.get("uploaded"))
               else bot.dodoland_tiles.first_art(tile_id))
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # An asset id is never reused, so a long cache is safe and keeps a
        # library of fifty icons from being refetched on every page load.
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )


# (guild, user, original size, width) -> (webp bytes, type). Small: a card each.
_THUMBS: dict[tuple, tuple[bytes, str]] = {}


async def _thumbnail(guild_id: int, user_id: int, data: bytes, width: int) -> tuple[bytes, str]:
    """``data`` no wider than ``width``, as WebP, made once per picture."""
    import asyncio
    import io

    key = (int(guild_id), int(user_id), len(data), int(width))
    if key in _THUMBS:
        return _THUMBS[key]

    def shrink():
        from PIL import Image

        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:  # noqa: BLE001 - not a picture we can read: send it as it is
            return data, "application/octet-stream"
        if image.width > width:
            image = image.resize((width, max(1, round(image.height * width / image.width))), Image.LANCZOS)
        out = io.BytesIO()
        image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB").save(out, "WEBP", quality=85)
        return out.getvalue(), "image/webp"

    made = await asyncio.get_running_loop().run_in_executor(None, shrink)
    if made[1] == "application/octet-stream":
        return data, "image/png"
    if len(_THUMBS) > 500:
        _THUMBS.clear()
    _THUMBS[key] = made
    return made


async def town_picture(request: web.Request):
    """A town's own picture or GIF, if its owner set one."""
    bot, guild = request.app["bot"], request["guild"]
    try:
        user_id = int(request.match_info.get("uid") or 0)
    except (TypeError, ValueError):
        user_id = 0
    row = bot.dodoland_towns.get(guild.id, user_id) if user_id else {}
    image = (row or {}).get("image")
    if not image:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = image.get("data")
    body = bytes(raw) if raw is not None else b""
    kind = str(image.get("content_type") or "image/png")
    # ``?w=`` asks for a copy that wide at most (a card, not a poster): an
    # owner's photo can be megabytes. A GIF is sent as it is, to keep moving.
    try:
        want = max(0, min(2048, int(request.query.get("w") or 0)))
    except ValueError:
        want = 0
    if want and body and "gif" not in kind:
        body, kind = await _thumbnail(guild.id, user_id, body, want)
    return web.Response(
        body=body,
        content_type=kind,
        # Short: unlike an asset, a town picture is replaced in place by its
        # owner, so a long cache would show them yesterday's.
        headers={"Cache-Control": "private, max-age=60"},
    )


def draw_town(bot, guild, user_id: int, *, flag_url: str = "") -> str:
    """One town as an SVG **fragment**, drawn from what its owner has built.

    Blocking (it reads the day rows), so call it in an executor. The caller
    wraps the fragment in an ``<svg viewBox>`` of its own: the map wants a town
    at the size of a village and the town page wants the same town at the size
    of a picture, and neither should have to unpick a document to get it.

    ``flag_url`` is where the town's picture can be read from *by whoever is
    going to look at this drawing* — the panel and a signed-in member reach the
    same picture by different addresses, and the flag has to point at the one
    the viewer can actually fetch. Empty means no flag flies.

    **Every argument ``town_svg`` takes is passed here.** It sat for several
    changes calling that function with an argument list three revisions old, so
    emblems, the rank colour, the per-town gradient id and the flag were all
    silently dropped while the drawing code supported every one of them. The
    towns looked plausible, which is why nothing pointed at it.
    """
    import math

    from helpers.dodoland import flourish as flourish_rules
    from helpers.dodoland import standing, townart
    from helpers.dodoland import store as store_module
    from helpers.dodoland import towns as town_rules

    buildings = bot.dodoland_buildings.buildings(guild.id)
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)
    lit_since = store_module.days_back(
        int(bot.dodoland_params.get(guild.id, "dodoland_lit_days")))
    # Scored among everybody, as the card and the map score them: a tier is a
    # percentile, and one person scored alone gets the wrong ones.
    every, _ = standing.recent_rows(bot.dodoland, bot.dodoland_params, guild.id, since)
    rows = [row for row in every if int(row.get("user_id", 0)) == int(user_id)]
    result = standing.recent_standings(bot.dodoland, bot.dodoland_params, guild.id,
                                       buildings, since)
    person = result["people"].get(user_id) or {}
    built = [{"key": key, "tier": int(score["tier"]) + 1}
             for key, score in (person.get("buildings") or {}).items()
             if score.get("tier") is not None]
    glow = flourish_rules.flourish_map(bot, guild.id).get(user_id) or {}
    lit = any(str(row.get("day") or "") >= lit_since for row in rows)
    details = bot.dodoland_towns.get(guild.id, user_id) or {}

    reached = int(person.get("reached") or 0)

    # Drawn as a hall: the town hall alone, its flag on it. Its reach is the
    # influence layer and its other buildings are what its owner places.
    if str(bot.dodoland_params.get(guild.id, "dodoland_town_style")) == "hall":
        key = str(bot.dodoland_params.get(guild.id, "dodoland_town_hall"))
        hall = next((b for b in buildings if b["key"] == key), {"key": key, "shape": "hall"})
        score = (person.get("buildings") or {}).get(key) or {}
        tier = int(score["tier"]) + 1 if score.get("tier") is not None else 1
        return townart.hall_svg(
            hall.get("shape") or "hall", tier,
            town_rules.building_colour(details, key, "") or townart.colour_for(str(user_id)),
            hall.get("symbol") or "", flag_url if details.get("image") else "", str(user_id),
            # The owner's trial rank, which is what flourish is, on the hall.
            flourish=int(glow.get("level", 0)), glow=str(glow.get("colour") or ""))

    # How many ordinary houses stand around what they built. **Linear in reach**
    # on purpose: this is the one number on the map that is supposed to say how
    # connected somebody is, and a logarithm made sixty people and three hundred
    # come out as fifteen houses and eighteen — a difference nobody could see,
    # in the quantity the whole system exists to measure.
    per_house = int(bot.dodoland_params.get(guild.id, "dodoland_people_per_house"))
    cap = max(0, int(bot.dodoland_params.get(guild.id, "dodoland_max_houses")))
    houses = min(cap, reached // per_house) if per_house > 0 else 0

    # How busy the streets are, and how wide the ground starts. This one *does*
    # saturate: past a point more figures walking about is noise rather than
    # information, while more roofs still reads as a bigger town.
    target = max(1, int(bot.dodoland_params.get(guild.id, "dodoland_busy_town_reach")))
    richness = min(1.0, math.log1p(reached) / math.log1p(target))

    return townart.town_svg(
        built,
        lit=lit,
        flourish=int(glow.get("level", 0)),
        # The rank's own colour, so a Legend glows the colour a Legend is.
        glow=str(glow.get("colour") or ""),
        # Unique per town, or every town on the map shares one set of
        # gradients and they all take the colour of whichever drew last.
        uid=str(user_id),
        flag=flag_url if details.get("image") else "",
        richness=richness,
        houses=houses,
        shapes={b["key"]: b.get("shape") for b in buildings},
        symbols={b["key"]: b.get("symbol") for b in buildings},
        # What its owner painted it, falling back to the stable hash per key.
        colours={b["key"]: town_rules.building_colour(details, b["key"], "")
                 for b in buildings},
    )


async def town_art(request: web.Request):
    """One town's artwork, drawn on demand.

    The map asks for this the first time a town comes close enough to be worth
    drawing, and never again. Shipping every settlement with the page and hiding
    the far ones costs the whole payload for the few anybody can see, and it is
    what put a megabyte of unused SVG in front of every page load.

    Because art is fetched rather than shipped, a building can be as detailed as
    it likes: what is on screen at high zoom is a handful of towns.
    """
    import asyncio

    bot, guild = request.app["bot"], request["guild"]
    try:
        user_id = int(request.match_info.get("uid") or 0)
    except (TypeError, ValueError):
        user_id = 0
    if not user_id:
        return web.Response(status=404, text="Not found.", content_type="text/plain")

    flag = request.get("dl_base", f"/guild/{guild.id}/dodoland") + f"/town/{user_id}/picture"
    art = await asyncio.get_running_loop().run_in_executor(
        None, lambda: draw_town(bot, guild, user_id, flag_url=flag))
    return web.Response(text=art, content_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=120"})
