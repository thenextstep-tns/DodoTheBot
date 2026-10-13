"""
The player front end: a person's own town, and nothing else.

This is the thing ``docs/DODOLAND.md`` §6 has been holding a place for. For its
whole life DodoLand has computed standings for several hundred people who could
not see them: a public map link, a per-player settle page and a ``/town`` command
were each built and removed again, because a half-finished thing behind a URL
somebody can paste is worse than no thing at all. What was wanted instead was
"a Discord login and an account that can manage its own town", and that is what
this is.

**Three rules hold this together. Breaking any of them re-opens the hole the
capability links were removed for.**

*One:* **a player handler never reads a user id from the request.** Not from the
path, not from the query, not from the body. Whose town this is comes from the
signed session cookie and from nowhere else, so there is no id to tamper with
and no way to phrase a request that edits somebody else's town. That is why
these are separate handlers rather than a softer scope bolted onto the panel's,
which do take an id because an admin is legitimately acting on other people.

*Two:* **membership is checked every time, not at login.** Someone who has left
the server loses their town page on their next request, not on their next login
seven days later.

*Three:* **the whole surface is off until a server turns it on.** Three
parameters, all defaulting to off: seeing your own town, seeing everybody's, and
placing your own. A deploy never switches any of them on for anybody.

What a player may do is exactly what an owner may do to their own town on the
map page — name it, describe it, picture it, name its buildings — plus, when the
server allows it, choose where it stands. What a player may never do is move a
number. Standing is earned; everything typed here is authored. That separation
is what lets naming be free, instant and reversible without a rename ever
becoming an exploit, and it is why this module imports the same ``TownStore``
the panel does rather than growing a second way to write a town.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from functools import wraps

from aiohttp import web

from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import standing
from helpers.dodoland import store as store_module
from helpers.dodoland import towns as town_rules
from web.dodoland import theme
from web.dodoland.theme import e

# The three switches. All default off in ``helpers/dodoland/parameters.py``.
TOWN_PAGES = "dodoland_town_pages"
WORLD_PAGE = "dodoland_world_page"
SELF_SETTLE = "dodoland_self_settle"


def town_pages_on(bot, guild_id: int) -> bool:
    """Whether members of this guild may open their own town at all."""
    return (bot.visibility.cog_enabled(guild_id, "dodoland")
            and bool(bot.dodoland_params.get(guild_id, TOWN_PAGES)))


def world_page_on(bot, guild_id: int) -> bool:
    """Whether members may look at everybody's towns on the map.

    Depends on the town pages: browsing a world you have no place in is a
    strange thing to be offered, and it means one switch to reason about rather
    than four combinations.
    """
    return town_pages_on(bot, guild_id) and bool(
        bot.dodoland_params.get(guild_id, WORLD_PAGE))


def self_settle_on(bot, guild_id: int) -> bool:
    """Whether a member may choose where their own town stands."""
    return world_page_on(bot, guild_id) and bool(
        bot.dodoland_params.get(guild_id, SELF_SETTLE))


# --------------------------------------------------------------------------- #
#  The gate
# --------------------------------------------------------------------------- #
def require_town(handler=None, *, world: bool = False, settle: bool = False):
    """Signed in, still a member, and the server has this surface switched on.

    A refusal is always 404 and never 403, the same bargain ``require_scope``
    makes: the answer tells nobody whether a town page exists on a server they
    have nothing to do with.

    The handler is handed ``request["uid"]`` — the only place a player handler
    is ever allowed to learn whose town it is working on.
    """

    def decorator(inner):
        @wraps(inner)
        async def wrapper(request: web.Request):
            from web.routes import _member_of, _session_user, login_redirect, resolve_scope

            uid = _session_user(request)
            if uid is None:
                raise login_redirect(request)
            bot = request.app["bot"]
            try:
                guild = bot.get_guild(int(request.match_info["gid"]))
            except (TypeError, ValueError, KeyError):
                guild = None
            if guild is None:
                return _gone()
            allowed = (self_settle_on(bot, guild.id) if settle
                       else world_page_on(bot, guild.id) if world
                       else town_pages_on(bot, guild.id))
            if not allowed:
                return _gone()
            # Checked per request rather than at login: somebody who has left
            # the server stops having a town page now, not in seven days when
            # their session expires.
            member = await _member_of(bot, guild, uid)
            if member is None:
                return _gone()
            request["uid"] = uid
            request["guild"] = guild
            request["member"] = member
            # Only so a page can offer an admin their way back into the panel.
            request["scope"] = await resolve_scope(bot, guild, uid)
            return await inner(request)

        return wrapper

    return decorator if handler is None else decorator(handler)


def _gone():
    return web.Response(status=404, text="Not found.", content_type="text/plain")


def _bad(error: str):
    return web.json_response({"ok": False, "error": str(error)})


# --------------------------------------------------------------------------- #
#  The server's standings, read once and shared
# --------------------------------------------------------------------------- #
# A place in a ranking and a percentile threshold only exist relative to
# everybody else, so showing one person their own town means scoring the whole
# server. That is a full scan of the day rows — the same one the panel page
# pays once — and a page every member can open is a page that must not pay it
# per visit. The snapshot is kept for as long as the server says.
_SNAPSHOTS: dict[int, tuple[float, dict]] = {}


def invalidate(guild_id: int) -> None:
    """Drop a guild's snapshot. Cheap, and always safe."""
    _SNAPSHOTS.pop(int(guild_id), None)


def snapshot(bot, guild) -> dict:
    """Every number the player pages read. Blocking; call in an executor."""
    ttl = int(bot.dodoland_params.get(guild.id, "dodoland_player_cache_seconds"))
    cached = _SNAPSHOTS.get(guild.id)
    now = time.time()
    if cached and ttl > 0 and now - cached[0] < ttl:
        return cached[1]

    buildings = bot.dodoland_buildings.buildings(guild.id)
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)
    lit_since = store_module.days_back(
        int(bot.dodoland_params.get(guild.id, "dodoland_lit_days")))

    rows, pairs = standing.recent_rows(bot.dodoland, bot.dodoland_params, guild.id, since)
    # Shared with every other reader of the same rows (cached, read-only).
    result = standing.recent_standings(bot.dodoland, bot.dodoland_params, guild.id,
                                       buildings, since)
    partners: dict[int, dict[int, int]] = {}
    for row in pairs:
        a, b, n = int(row.get("a", 0)), int(row.get("b", 0)), int(row.get("n", 0) or 1)
        if not a or not b:
            continue
        partners.setdefault(a, {})[b] = partners.setdefault(a, {}).get(b, 0) + n
        partners.setdefault(b, {})[a] = partners.setdefault(b, {}).get(a, 0) + n

    data = {
        "result": result,
        "buildings": buildings,
        "flourish": flourish_rules.flourish_map(bot, guild.id),
        "plots": bot.dodoland_buildings.plots(guild.id),
        "partners": partners,
        "lit": {int(row.get("user_id", 0)) for row in rows
                if str(row.get("day") or "") >= lit_since},
        "window": window,
    }
    _SNAPSHOTS[guild.id] = (now, data)
    return data


# --------------------------------------------------------------------------- #
#  One person's town, assembled
# --------------------------------------------------------------------------- #
def _channel_name(guild, channel_id: int) -> str:
    channel = guild.get_channel(int(channel_id))
    return f"#{channel.name}" if channel is not None else f"#{channel_id}"


def my_town(bot, guild, user_id: int) -> dict:
    """What this person has built, with the arithmetic left visible.

    Every building the server has, not only the ones already standing: the point
    of showing somebody their own town is showing them what is not in it yet and
    what the next rung costs. A building nobody has reached tier 1 in is the
    most useful row on the page.
    """
    data = snapshot(bot, guild)
    result = data["result"]
    person = result["people"].get(int(user_id))
    details = bot.dodoland_towns.get(guild.id, user_id) or {}
    shine = data["flourish"].get(int(user_id)) or dict(flourish_rules.BLANK)

    rows = []
    for building in data["buildings"]:
        key = building["key"]
        score = (person or {}).get("buildings", {}).get(key) or {
            "points": 0, "by_channel": {}, "by_metric": {}, "tier": None,
            "tier_title": None,
        }
        resolved = result["tiers"].get(key) or []
        reached = score.get("tier")
        points = int(score.get("points") or 0)
        nxt = None
        if resolved and (reached is None or reached + 1 < len(resolved)):
            step = resolved[0] if reached is None else resolved[reached + 1]
            floor = 0 if reached is None else int(resolved[reached]["threshold"])
            span = max(1, int(step["threshold"]) - floor)
            nxt = {
                "title": step["title"],
                "threshold": int(step["threshold"]),
                "short": max(0, int(step["threshold"]) - points),
                # Progress across *this* rung rather than from zero, so a long
                # climb does not look like standing still.
                "progress": max(0.0, min(1.0, (points - floor) / span)),
            }
        rows.append({
            "key": key,
            "given": building.get("name") or key,
            "name": town_rules.building_label(details, key, building.get("name") or key),
            "icon": building.get("icon") or "",
            "points": points,
            "tier": reached,
            "tier_title": score.get("tier_title"),
            "tiers": len(resolved),
            "next": nxt,
            "rooms": sorted(((_channel_name(guild, cid), int(p))
                             for cid, p in (score.get("by_channel") or {}).items()),
                            key=lambda r: -r[1])[:4],
            "acts": sorted(((metric_registry.get(m).label, int(p))
                            for m, p in (score.get("by_metric") or {}).items()
                            if m in metric_registry.BY_KEY),
                           key=lambda r: -r[1])[:4],
        })
    # Standing towns first, then the closest to their next rung: what somebody
    # is nearly at is more interesting than what they have not started.
    rows.sort(key=lambda r: (-(r["tier"] if r["tier"] is not None else -1),
                             -(r["next"]["progress"] if r["next"] else 0)))

    friends = data["partners"].get(int(user_id)) or {}
    top = sorted(friends.items(), key=lambda kv: -kv[1])[:8]
    return {
        "person": person,
        "details": details,
        "flourish": shine,
        "buildings": rows,
        "population": len(result["people"]),
        "plot": data["plots"].get(int(user_id)),
        "lit": int(user_id) in data["lit"],
        "window": data["window"],
        "friends": [(_display(guild, bot, other), n) for other, n in top],
    }


def _display(guild, bot, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    if member is not None:
        return member.display_name
    user = bot.get_user(int(user_id))
    return user.name if user is not None else f"User {user_id}"


# --------------------------------------------------------------------------- #
#  Where a member may go
# --------------------------------------------------------------------------- #
async def player_guilds(bot, user_id) -> list:
    """Guilds where this person is a member and the town pages are switched on.

    Cache-only membership, like ``accessible_guilds``: the members intent keeps
    it authoritative, and a fetch per guild would turn one page load into an API
    call per server the bot is in.
    """
    out = []
    for guild in bot.guilds:
        if not town_pages_on(bot, guild.id):
            continue
        if guild.get_member(int(user_id)) is not None:
            out.append(guild)
    return sorted(out, key=lambda g: g.name.lower())


async def towns_home(request: web.Request):
    """Where a signed-in member lands: the towns they have, across servers."""
    from web.routes import _session_user, login_redirect

    uid = _session_user(request)
    if uid is None:
        raise login_redirect(request)
    bot = request.app["bot"]
    guilds = await player_guilds(bot, uid)

    if not guilds:
        body = ("<h1>No towns yet</h1><p class=\"lead\">None of the servers you "
                "are in have opened DodoLand to their members. There is nothing "
                "wrong with your account — there is simply nothing to show you "
                "yet.</p>")
    else:
        cards = ""
        for guild in guilds:
            icon = (f'<img class="gicon" src="{e(guild.icon.url)}" alt="" '
                    f'width="52" height="52">' if guild.icon else
                    f'<div class="gicon ph">{e((guild.name or "?")[:1].upper())}</div>')
            cards += (f'<a class="towncard" href="/guild/{guild.id}/dodoland/me">'
                      f'{icon}<div><b>{e(guild.name)}</b>'
                      f'<span class="muted">Your town</span></div></a>')
        body = (f'<h1>Your towns</h1><p class="lead">One town per server, built '
                f'out of who you actually talk to.</p><div class="towngrid">'
                f'{cards}</div>')

    return web.Response(text=_shell("Your towns", theme.bar(
        back=None, title="\U0001F3D8 DodoLand",
        links='<a class="dlghost" href="/logout">Log out</a>',
    ) + f'<main class="doc">{body}</main>'), content_type="text/html")


# --------------------------------------------------------------------------- #
#  Your own town
# --------------------------------------------------------------------------- #
@require_town
async def my_town_page(request: web.Request):
    """The entrance to DodoLand: name your town, pick its picture, see what
    activity does, and go and put it on the map. Nothing else — the standings,
    the climb and the decorations live on the map, where they mean something."""
    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    from helpers.dodoland import page_texts

    def t(key, **fill):
        # The server's own wording for this page (editable in the panel).
        return page_texts.say(bot.dodoland_params, guild.id, key, **fill)

    def facts():
        details = bot.dodoland_towns.get(guild.id, uid) or {}
        plot = bot.dodoland_buildings.plots(guild.id).get(int(uid))
        return details, plot, _example(bot, guild)

    details, plot, example = await asyncio.get_running_loop().run_in_executor(None, facts)
    owner = _display(guild, bot, uid)
    name = town_rules.display_name(details, owner)

    # Where the big button goes. A town not on the map yet is placed from it
    # when members may place their own; one already standing is visited.
    world, settle = world_page_on(bot, guild.id), self_settle_on(bot, guild.id)
    the_map = f"/guild/{guild.id}/dodoland/me/map"
    note = ""
    if world and settle and not plot:
        go, href = t("place_button"), the_map + "?place=1"
    elif world and plot:
        go, href = t("home_button"), the_map + "?mine=1"
    elif world:
        go, href = t("map_button"), the_map
        note = f'<p class="muted small">{t("admin_places")}</p>'
    else:
        go, href = t("save_button"), ""

    flag = (f'<img alt="" src="/guild/{guild.id}/dodoland/me/picture">'
            if details.get("image") else '<span class="noflag">\U0001F3F3️</span>')
    grow = ""
    if example:
        building, stages, box = example
        figures = '<i class="arrow">→</i>'.join(
            f'<figure><svg viewBox="{box}" xmlns="http://www.w3.org/2000/svg">'
            f'<g class="dltown close">{art}</g></svg><figcaption>{e(title)}</figcaption></figure>'
            for art, title in stages)
        grow = f"""
  <section class="step">
    <span class="num">3</span>
    <div class="stepbody">
      <h2>{t("step_grow")}</h2>
      <p>{t("grow_text", server=guild.name, building=("<b>" + e(building) + "</b>",))}</p>
      <div class="grow">{figures}</div>
    </div>
  </section>"""

    limit = town_rules.picture_limit(bot.dodoland_params, guild.id)
    mb = town_rules.size_label(limit)
    body = f"""
<main class="doc welcome">
  <h1>{t("welcome_title")}</h1>
  <p class="lead">{t("welcome_lead", server=guild.name)}</p>

  <section class="step">
    <span class="num">1</span>
    <div class="stepbody">
      <h2>{t("step_name")}</h2>
      <input id="tname" maxlength="{town_rules.MAX_NAME}" autocomplete="off"
        value="{e(details.get('name') or '')}" placeholder="{t('name_placeholder', owner=owner)}">
    </div>
  </section>

  <section class="step">
    <span class="num">2</span>
    <div class="stepbody">
      <h2>{t("step_picture")}</h2>
      <p class="muted">{t("picture_hint", mb=mb)}</p>
      <div class="pick">
        <div class="flag" id="tflag">{flag}</div>
        <label class="ghostbtn" for="tpic">{t("picture_change") if details.get("image") else t("picture_choose")}</label>
        <input id="tpic" type="file" hidden accept="image/png,image/jpeg,image/gif,image/webp">
      </div>
    </div>
  </section>
{grow}
  <div class="go">
    <button id="tgo" data-href="{e(href)}">{go}</button>
    <p class="cardmsg" id="tmsg"></p>
    {note}
  </div>
</main>
<script>var GID = "{guild.id}", MAX_BYTES = {limit}, MAX_LABEL = "{mb}";</script>
<script>{_SCRIPT}</script>"""

    links = f'<a class="dlghost" href="/logout">{t("logout")}</a>'
    if world:
        links = f'<a class="dlghost" href="{the_map}">{t("map_link")}</a>' + links
    return web.Response(
        text=_shell(f"{name} · {guild.name}", theme.bar(
            back=("/towns", "Your towns"), title="\U0001F3D8 DodoLand",
            links=links) + body),
        content_type="text/html")


# How far a building at each tier reaches inside townart's 120 x 78 box, over
# every shape (measured with getBBox): a top tier's beam of light rises far above
# the box. The stages share one crop, the union of the tiers shown, so they stand
# on one ground line at one scale and the growth reads as growth.
_TIER_REACH = {1: (48, 37, 73, 70), 2: (43, 31, 80, 71), 3: (37, 24, 82, 72),
               4: (35, -4, 89, 73), 5: (26, -9, 94, 74), 6: (25, -24, 95, 75)}


def _crop(tiers) -> str:
    boxes = [_TIER_REACH[max(1, min(6, t))] for t in tiers]
    x0, y0 = min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2
    x1, y1 = max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2
    return f"{x0} {y0} {x1 - x0} {y1 - y0}"


def _example(bot, guild):
    """The building a newcomer sees growing, and the stages shown: ``(name,
    [(svg, tier title), ...])``, or None when the server has no buildings."""
    from helpers.dodoland import townart

    buildings = [b for b in bot.dodoland_buildings.buildings(guild.id) if b.get("tiers")]
    if not buildings:
        return None
    params = bot.dodoland_params
    want = (str(params.get(guild.id, "dodoland_entrance_building") or "").strip()
            or str(params.get(guild.id, "dodoland_town_hall") or "").strip())
    building = (next((b for b in buildings if b["key"] == want), None)
                or max(buildings, key=lambda b: len(b["tiers"])))
    tiers = building["tiers"]
    count = max(2, min(len(tiers), int(params.get(guild.id, "dodoland_entrance_stages") or 2)))
    # Evenly spread, always the first tier and the top one.
    picks = sorted({round(i * (len(tiers) - 1) / max(1, count - 1)) for i in range(count)})
    colour = building.get("colour") or townart.colour_for(building["key"])
    stages = [(townart.building_svg(building.get("shape") or "", i + 1, colour,
                                    building.get("symbol") or "", uid=f"ex{i + 1}"),
               str(tiers[i].get("title") or f"Tier {i + 1}"))
              for i in picks]
    return building.get("name") or building["key"], stages, _crop([i + 1 for i in picks])


# --------------------------------------------------------------------------- #
#  Your own picture, and your own writes
# --------------------------------------------------------------------------- #
@require_town
async def my_picture(request: web.Request):
    """Your town's picture. No id in the path, so there is none to change."""
    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    image = (bot.dodoland_towns.get(guild.id, uid) or {}).get("image")
    if not image:
        return _gone()
    raw = image.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(image.get("content_type") or "image/png"),
        # Short: its owner replaces it in place, and a long cache would show
        # them yesterday's picture on the page they just uploaded it from.
        headers={"Cache-Control": "private, max-age=60"},
    )


@require_town
async def api_my_town(request: web.Request):
    """Name, describe and picture your own town.

    Deliberately not audited. ``_record_change`` is the panel's trail of what
    administrators did to a server's configuration, and somebody renaming their
    own town is neither. Filling that log with every rename would bury the
    changes it exists to show.
    """
    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return _bad("That request could not be read.")

    if body.get("gate_add") is not None or body.get("gate_remove") is not None:
        # A gate in the town's own wall, snapped to it (influence_api.gate_edit).
        import asyncio

        from web.dodoland import influence_api
        try:
            add = body.get("gate_add")
            remove = body.get("gate_remove")
            add = (float(add["x"]), float(add["y"])) if add is not None else None
            remove = (float(remove["x"]), float(remove["y"])) if remove is not None else None
        except (TypeError, ValueError, KeyError):
            return _bad("That gate could not be read.")
        why = await asyncio.get_running_loop().run_in_executor(
            None, lambda: influence_api.gate_edit(bot, guild, str(uid), add=add, remove=remove))
        if why:
            return _bad(why)
        return web.json_response({"ok": True})

    if body.get("house") is not None:
        # One ordinary house moved by hand: inside the town's own area only.
        import asyncio

        from web.dodoland import influence_api
        house = body.get("house") or {}
        try:
            index, hx, hy = int(house.get("i")), float(house.get("x")), float(house.get("y"))
        except (TypeError, ValueError):
            return _bad("That house move could not be read.")
        ok = await asyncio.get_running_loop().run_in_executor(
            None, influence_api.inside, bot, guild, str(uid), hx, hy)
        if not ok:
            return _bad("A house stays inside its town's area.")
        try:
            bot.dodoland_towns.move_house(guild.id, uid, index, hx, hy)
        except town_rules.TownError as error:
            return _bad(error)
        return web.json_response({"ok": True})
    try:
        bot.dodoland_towns.save(
            guild.id, uid,
            name=body.get("name"), blurb=body.get("blurb"),
            building_names=body.get("building_names"),
            walls=body.get("walls"),
        )
        if body.get("clear_image"):
            bot.dodoland_towns.save_image(guild.id, uid, None)
        elif body.get("image"):
            try:
                blob = base64.b64decode(str(body["image"]).split(",")[-1],
                                        validate=True)
            except Exception:
                return _bad("That picture could not be read.")
            bot.dodoland_towns.save_image(
                guild.id, uid,
                {"data": blob, "content_type": str(body.get("content_type") or "")},
                max_bytes=town_rules.picture_limit(bot.dodoland_params, guild.id),
            )
    except town_rules.TownError as error:
        return _bad(error)
    return web.json_response({"ok": True})


@require_town(world=True, settle=True)
async def api_my_settle(request: web.Request):
    """Put your own town somewhere on the map, or take it off again.

    The id is the session's, so this can only ever move one town. Removing it
    touches nothing anybody earned: a town's position and a town's standing
    have never had anything to do with each other.
    """
    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return _bad("That request could not be read.")

    if body.get("remove"):
        bot.dodoland_buildings.unsettle(guild.id, uid)
        # Its buildings go with the town they belonged to, as on the admin side.
        bot.dodoland_decor.remove_town_buildings(guild.id, uid)
        invalidate(guild.id)
        return web.json_response({"ok": True, "removed": True})
    try:
        x, y = float(body.get("x")), float(body.get("y"))
    except (TypeError, ValueError):
        return _bad("A town needs a position.")
    # Founded on open ground: never inside another town's area. It may grow
    # into one later; it may not be dropped into one.
    from web.dodoland import influence_api
    other = await asyncio.get_running_loop().run_in_executor(
        None, lambda: influence_api.claimed_by(bot, guild, x, y, but=str(uid)))
    if other:
        member = guild.get_member(int(other)) if other.isdigit() else None
        whose = (town_rules.display_name(bot.dodoland_towns.get(guild.id, int(other)) or {},
                                         member.display_name if member else "another town")
                 if other.isdigit() else "another town")
        return _bad(f"That is inside {whose}'s area. Put your town on open ground; "
                    "it can grow into its neighbours later.")
    # Everything in the town moves with it (web/dodoland/town_move.py).
    from web.dodoland import town_move
    spot = await asyncio.get_running_loop().run_in_executor(
        None, town_move.move_town, bot, guild, uid, x, y)
    # The world page reads plots out of the snapshot, so a move nobody can see
    # for a minute looks exactly like a move that did not save.
    invalidate(guild.id)
    return web.json_response({"ok": True, **spot})


# --------------------------------------------------------------------------- #
#  Chrome
# --------------------------------------------------------------------------- #
def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>{_CSS}</style>
</head><body>
{body}
</body></html>"""


_CSS = theme.PALETTE + theme.CHROME + theme.TOWN_ART_CSS + """
.dlnote { font-size: 13px; opacity: .8; }
.doc { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { margin: 0 0 4px; font-size: 30px; }
h2 { margin: 0 0 8px; font-size: 19px; }
.lead { color: var(--soft); }
.muted { color: var(--soft); }
.small { font-size: 13px; }

/* The entrance: three numbered steps and one button, nothing else. */
.welcome { max-width: 640px; }
.welcome h1 { font-size: 32px; }
.welcome .lead { font-size: 16px; margin: 0 0 24px; }
.step { display: flex; gap: 16px; background: var(--paper);
  border: 1px solid var(--edge); border-radius: 14px; padding: 18px 20px;
  margin-bottom: 14px; }
.step .num { flex: 0 0 34px; height: 34px; border-radius: 50%;
  background: var(--lantern); color: #fff; font-weight: 700; font-size: 17px;
  display: grid; place-items: center; }
.stepbody { flex: 1 1 auto; min-width: 0; }
.stepbody p { margin: 0 0 10px; }
input { width: 100%; padding: 11px 13px; font: inherit; font-size: 16px;
  border: 1px solid var(--edge); border-radius: 10px; background: var(--deep);
  color: var(--ink); }
input:focus { outline: 2px solid var(--lantern); outline-offset: 1px; }
.pick { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.flag { width: 96px; height: 64px; border-radius: 8px; overflow: hidden;
  background: var(--deep); border: 1px solid var(--edge);
  display: grid; place-items: center; }
.flag img { width: 100%; height: 100%; object-fit: cover; }
.noflag { font-size: 30px; opacity: .5; }
.ghostbtn { padding: 9px 16px; border-radius: 10px; border: 1px solid var(--edge);
  background: var(--deep); color: var(--ink); cursor: pointer; font-size: 14px; }
.ghostbtn:hover { border-color: var(--lantern); }
.grow { display: flex; align-items: flex-end; gap: 4px; margin-top: 6px; }
.grow figure { flex: 1 1 0; min-width: 0; margin: 0; text-align: center; }
.grow svg { display: block; width: 100%; height: auto; max-height: 200px; overflow: visible; }
.grow figcaption { font-size: 12px; color: var(--soft); margin-top: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.grow .arrow { flex: 0 0 auto; font-style: normal; color: var(--soft);
  align-self: center; font-size: 18px; }
.go { text-align: center; margin-top: 26px; }
.go button { padding: 15px 38px; border-radius: 999px; border: 0;
  background: var(--lantern); color: #fff; font: inherit; font-size: 19px;
  font-weight: 700; cursor: pointer; box-shadow: 0 6px 18px rgba(0,0,0,.18); }
.go button:hover { filter: brightness(1.08); }
.go button:disabled { opacity: .6; cursor: wait; }
/* A save with no feedback is indistinguishable from no save at all, and the
   message has to appear where the button was rather than somewhere off screen. */
.cardmsg { margin: 12px 0 0; font-size: 14px; color: var(--soft); min-height: 1em; }
.cardmsg.bad { color: #c0392b; font-weight: 600; }

.towngrid { display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
.towncard { display: flex; gap: 12px; align-items: center; padding: 14px;
  border-radius: 12px; background: var(--paper); border: 1px solid var(--edge);
  color: inherit; text-decoration: none; }
.towncard:hover { border-color: var(--lantern); }
.towncard b { display: block; }
.towncard .muted { font-size: 13px; }
.gicon { border-radius: 10px; }
.gicon.ph { width: 52px; height: 52px; display: grid; place-items: center;
  background: var(--deep); font-size: 22px; }
@media (max-width: 520px) {
  .step { padding: 14px; gap: 12px; }
  .grow .arrow { display: none; }
}
"""

_SCRIPT = r"""
(function () {
  var msg = document.getElementById('tmsg'),
      go = document.getElementById('tgo'),
      nameBox = document.getElementById('tname'),
      pic = document.getElementById('tpic'),
      flag = document.getElementById('tflag');
  var startName = nameBox.value, chosen = null;
  function say(text, bad) {
    msg.textContent = text || '';
    msg.classList.toggle('bad', !!bad);
  }

  // The picture shows as the flag the moment it is picked, and one over the
  // limit is refused then, not after a slow upload of it.
  var KINDS = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  pic.onchange = function () {
    var f = pic.files && pic.files[0];
    if (!f) return;
    var ext = /\.(png|jpe?g|gif|webp)$/i.test(f.name);
    if (KINDS.indexOf(f.type) < 0 || !ext) {
      chosen = null; pic.value = '';
      say('That is not a picture this takes. Use a PNG, JPG, GIF or WebP.', true);
      return;
    }
    if (f.size > MAX_BYTES) {
      chosen = null; pic.value = '';
      say('That picture is ' + (f.size > 1048576 ? (f.size / 1048576).toFixed(1) + 'MB'
          : Math.round(f.size / 1024) + 'KB') + '. The limit is ' + MAX_LABEL +
          ', so pick a smaller one.', true);
      return;
    }
    chosen = f;
    say('');
    flag.innerHTML = '';
    var img = document.createElement('img');
    img.alt = '';
    img.src = URL.createObjectURL(f);
    flag.appendChild(img);
  };

  function onward() {
    var href = go.dataset.href;
    if (href) { window.location.href = href; return; }
    go.disabled = false;
    say('Saved.');
    startName = nameBox.value; chosen = null; pic.value = '';
  }

  function post(payload) {
    // GID is interpolated as a string: a 64-bit snowflake written as a bare
    // numeric literal loses its last digits and every request 404s.
    fetch('/api/guild/' + GID + '/dodoland/me/town', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { go.disabled = false; say(res.error || 'That did not work.', true); return; }
      onward();
    }).catch(function (err) { go.disabled = false; say(String(err), true); });
  }

  go.onclick = function () {
    var payload = {};
    if (nameBox.value !== startName) payload.name = nameBox.value;
    // Nothing changed: straight on, no save to wait for.
    if (!chosen && !('name' in payload)) { onward(); return; }
    go.disabled = true;
    say('Saving...');
    if (!chosen) { post(payload); return; }
    var reader = new FileReader();
    reader.onload = function () {
      payload.image = String(reader.result).split(',').pop();
      payload.content_type = chosen.type;
      post(payload);
    };
    reader.readAsDataURL(chosen);
  };
  nameBox.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') go.click();
  });
})();
"""
