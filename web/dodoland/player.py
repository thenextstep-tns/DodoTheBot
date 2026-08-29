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
            from web.routes import _member_of, _session_user, resolve_scope

            uid = _session_user(request)
            if uid is None:
                raise web.HTTPFound("/login")
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

    rows = bot.dodoland.rows(guild.id, since=since)
    pairs = bot.dodoland.pair_rows(guild.id, since=since)
    result = standing.guild_standings(bot.dodoland, bot.dodoland_params, guild.id,
                                      buildings, since=since, rows=rows,
                                      pair_rows=pairs)
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
    from web.routes import _session_user

    uid = _session_user(request)
    if uid is None:
        raise web.HTTPFound("/login")
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
    """One person's town: what stands in it, what it cost, and what is next."""
    bot, guild, uid = request.app["bot"], request["guild"], request["uid"]
    loop = asyncio.get_running_loop()
    town = await loop.run_in_executor(None, my_town, bot, guild, uid)

    details = town["details"]
    owner = _display(guild, bot, uid)
    name = town_rules.display_name(details, owner)
    person = town["person"]

    # The artwork is drawn straight into the page rather than fetched. The map
    # fetches because it draws hundreds of towns and most are never looked at;
    # here there is exactly one and it is the thing the page is for.
    flag_url = f"/guild/{guild.id}/dodoland/me/picture"
    art = await loop.run_in_executor(
        None, lambda: _draw(bot, guild, uid, flag_url))

    if person is None:
        standing_html = (
            '<p class="lead">Nothing has been counted for you yet, so your town '
            'is a single tent — which is still somewhere. It fills in on its '
            'own as you talk to people.</p>')
        tiles = ""
    else:
        standing_html = ""
        flour = town["flourish"]
        tiles = "".join(
            f'<div class="tile"><b>{e(value)}</b><span>{e(label)}</span></div>'
            for label, value in (
                ("town standing", f"{person['power']:,}"),
                (f"of {town['population']} towns", f"#{person['place']}"),
                ("people reached", f"{person['reached']:,}"),
                ("flourish", flour.get("label") or "None"),
            ))

    body = f"""
<main class="doc">
  <section class="hero">
    <div class="art dltown close {"fl" + str(town["flourish"].get("level", 0))
                                  if town["flourish"].get("level") else ""}">
      <svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">{art}</svg>
    </div>
    <div class="heroinfo">
      <h1 id="townname">{e(name)}</h1>
      <p class="owner">{e(owner)}'s town in {e(guild.name)}
        {'· <b>lit</b>' if town['lit'] else '· <span class="muted">quiet lately</span>'}</p>
      {f'<p class="blurb" id="townblurb">{e(details.get("blurb"))}</p>'
       if details.get("blurb") else ''}
      {standing_html}
      <div class="tiles">{tiles}</div>
    </div>
  </section>

  {_flourish_html(town)}
  {_climb_html(town)}
  {_friends_html(town)}
  {_customise_html(guild, town, name)}
  <p class="foot">Standing is earned and cannot be typed in. Everything on this
  page you can edit is authored: naming your town, describing it and picturing
  it move no number at all, and never will.</p>
</main>
<script>var GID = "{guild.id}";</script>
<script>{_SCRIPT}</script>"""

    links = ""
    if world_page_on(bot, guild.id):
        links += f'<a class="dlghost" href="/guild/{guild.id}/dodoland/world">The world</a>'
    links += '<a class="dlghost" href="/logout">Log out</a>'
    return web.Response(
        text=_shell(f"{name} · {guild.name}", theme.bar(
            back=("/towns", "Your towns"), title=name,
            note=f"in {guild.name}", links=links) + body),
        content_type="text/html")


def _flourish_html(town: dict) -> str:
    """What your rank does to your town, and the fact that it does only that."""
    shine = town["flourish"]
    if not shine.get("level"):
        return ("""
<section class="card">
  <h2>Flourish</h2>
  <p class="muted">No flourish yet. Flourish is the one thing on this map that
  cannot be earned by being sociable — it comes from the trial ladder, and it is
  purely how your town <i>looks</i>. Every building here is reachable without
  it.</p>
</section>""")
    return f"""
<section class="card">
  <h2>Flourish</h2>
  <p><b>{e(shine.get('label'))}</b> — {e(shine.get('description'))}</p>
  <p class="muted">From your trial rank, <b>{e(shine.get('rank_name') or 'a rank')}</b>.
  Rank buys the effect and never a tier: it changes how your town looks and
  nothing about what stands in it.</p>
</section>"""


def _climb_html(town: dict) -> str:
    """Every building, what it is worth, and what the next rung costs."""
    rows = ""
    for b in town["buildings"]:
        if b["tier"] is None:
            badge = '<span class="badge none">not yet</span>'
        else:
            badge = (f'<span class="badge">{e(b["tier_title"] or "Tier")}</span>'
                     f'<span class="muted small">tier {b["tier"] + 1}'
                     f' of {b["tiers"]}</span>')
        if b["next"]:
            bar = (f'<div class="bar"><i style="width:'
                   f'{b["next"]["progress"] * 100:.1f}%"></i></div>'
                   f'<div class="muted small">{b["next"]["short"]:,} more to reach '
                   f'<b>{e(b["next"]["title"])}</b></div>')
        else:
            bar = '<div class="muted small">Nothing above this one.</div>'
        rooms = " · ".join(f"{e(n)} {p:,}" for n, p in b["rooms"])
        acts = " · ".join(f"{e(n)} {p:,}" for n, p in b["acts"])
        detail = ""
        if rooms or acts:
            detail = (f'<div class="muted small breakdown">'
                      f'{("Rooms: " + rooms) if rooms else ""}'
                      f'{"<br>" if rooms and acts else ""}'
                      f'{("From: " + acts) if acts else ""}</div>')
        renamed = ('' if b["name"] == b["given"]
                   else f'<span class="muted small">({e(b["given"])})</span>')
        rows += f"""
  <li class="brow">
    <div class="bhead"><span class="bicon">{e(b['icon'])}</span>
      <b>{e(b['name'])}</b> {renamed} {badge}
      <span class="pts">{b['points']:,}</span></div>
    {bar}{detail}
  </li>"""
    return f"""
<section class="card">
  <h2>The climb</h2>
  <p class="muted">Every building this server has, whether or not you have
  reached it. Thresholds are a percentile of what everybody else has actually
  scored, so they move as the server does — this is where yours sit today.</p>
  <ul class="climb">{rows}</ul>
</section>"""


def _friends_html(town: dict) -> str:
    """Who you reached. The number DodoLand is actually built around."""
    if not town["friends"]:
        return ""
    chips = "".join(f'<span class="chip">{e(n)} <b>{c:,}</b></span>'
                    for n, c in town["friends"])
    return f"""
<section class="card">
  <h2>Who you reached</h2>
  <p class="muted">Reach, not volume: what counts is how many different people
  you reached and who reached back, capped per person per day so nobody can be
  farmed. These are the people you have shared the most days with, over the last
  {town['window']} days.</p>
  <div class="chips">{chips}</div>
</section>"""


def _customise_html(guild, town: dict, name: str) -> str:
    details = town["details"]
    fields = "".join(
        f'<label>{e(b["given"])}</label>'
        f'<input class="bname" data-key="{e(b["key"])}" maxlength="48" '
        f'value="{e(b["name"])}">'
        for b in town["buildings"] if b["tier"] is not None)
    picture = ""
    if details.get("image"):
        picture = (f'<div class="cardflag"><img alt="Your town\'s picture" '
                   f'src="/guild/{guild.id}/dodoland/me/picture"></div>')
    return f"""
<section class="card">
  <h2>Customise</h2>
  <p class="muted">Yours to write. A picture flies as a flag over whatever you
  have built highest.</p>
  <label>Town name</label>
  <input id="tname" maxlength="{town_rules.MAX_NAME}" value="{e(name)}">
  <label>Description</label>
  <textarea id="tblurb" maxlength="{town_rules.MAX_BLURB}">{e(details.get('blurb') or '')}</textarea>
  <label>Picture or GIF (under
    {town_rules.MAX_IMAGE_BYTES // (1024 * 1024)}MB)</label>
  <input id="tpic" type="file"
    accept="image/png,image/jpeg,image/gif,image/webp">
  {picture}
  {('<label class="grouplabel">Building names</label>' + fields) if fields else ''}
  <div class="acts">
    <button id="tsave" class="own">Save</button>
    <button id="tclear">Remove picture</button>
  </div>
  <p class="cardmsg" id="tmsg"></p>
</section>"""


def _draw(bot, guild, user_id: int, flag_url: str) -> str:
    from web.dodoland.assets_route import draw_town

    return draw_town(bot, guild, user_id, flag_url=flag_url)


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

    try:
        bot.dodoland_towns.save(
            guild.id, uid,
            name=body.get("name"), blurb=body.get("blurb"),
            building_names=body.get("building_names"),
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
        invalidate(guild.id)
        return web.json_response({"ok": True, "removed": True})
    try:
        x, y = float(body.get("x")), float(body.get("y"))
    except (TypeError, ValueError):
        return _bad("A town needs a position.")
    spot = bot.dodoland_buildings.settle(guild.id, uid, x, y)
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
.owner { margin: 0 0 10px; color: var(--soft); font-size: 14px; }
.blurb { white-space: pre-wrap; margin: 0 0 12px; }

.hero { display: flex; gap: 24px; align-items: flex-end; flex-wrap: wrap;
  margin-bottom: 24px; }
/* The artwork is the page's subject, so it gets a real size rather than the
   thumbnail it is on the map. It carries `dltown close` because that is the
   pair of classes the shared artwork rules key off — on the map `close` is
   toggled by zoom, and on a page showing exactly one town it is simply true. */
.art { flex: 0 0 320px; max-width: 100%; }
.art svg { display: block; width: 100%; height: auto; overflow: visible; }
.heroinfo { flex: 1 1 300px; min-width: 260px; }

.tiles { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.tile { flex: 1 1 auto; min-width: 108px; padding: 10px 12px; border-radius: 10px;
  background: var(--paper); border: 1px solid var(--edge); }
.tile b { display: block; font-size: 20px; line-height: 1.2; }
.tile span { font-size: 12px; color: var(--soft); }

.card { background: var(--paper); border: 1px solid var(--edge);
  border-radius: 12px; padding: 18px 20px; margin-bottom: 18px; }
.card p { margin: 0 0 10px; }

ul.climb { list-style: none; margin: 0; padding: 0; }
.brow { padding: 12px 0; border-top: 1px solid var(--edge); }
.brow:first-child { border-top: 0; }
.bhead { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.bicon { font-size: 17px; }
.pts { margin-left: auto; font-variant-numeric: tabular-nums; opacity: .75; }
.badge { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
  padding: 2px 8px; border-radius: 999px; background: var(--lantern);
  color: #fff; }
.badge.none { background: none; border: 1px solid var(--edge); color: var(--soft); }
/* Progress across the current rung, not from zero: a long climb drawn from
   zero looks like standing still, which is the opposite of what it is. */
.bar { height: 6px; border-radius: 999px; background: var(--deep);
  margin: 8px 0 4px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--lantern); }
.breakdown { margin-top: 4px; }

.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { padding: 4px 10px; border-radius: 999px; background: var(--deep);
  border: 1px solid var(--edge); font-size: 13px; }

label { display: block; font-size: 12px; color: var(--soft); margin: 12px 0 4px; }
label.grouplabel { margin-top: 20px; font-size: 13px; color: var(--ink);
  font-weight: 700; }
input, textarea { width: 100%; padding: 8px 10px; font: inherit; font-size: 14px;
  border: 1px solid var(--edge); border-radius: 8px; background: var(--deep);
  color: var(--ink); }
textarea { min-height: 84px; resize: vertical; }
.acts { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.acts button { padding: 8px 14px; border-radius: 8px; border: 1px solid var(--edge);
  background: var(--deep); color: var(--ink); font: inherit; cursor: pointer; }
.acts button.own { background: var(--lantern); border-color: var(--lantern);
  color: #fff; }
.acts button:hover { filter: none; opacity: .88; }
/* A save with no feedback is indistinguishable from no save at all, and the
   message has to appear where the button was rather than somewhere off screen. */
.cardmsg { margin: 12px 0 0; font-size: 13px; color: var(--soft); min-height: 1em; }
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
.foot { color: var(--soft); font-size: 13px; }
@media (max-width: 620px) {
  .art { flex-basis: 100%; }
}
"""

_SCRIPT = r"""
(function () {
  var msg = document.getElementById('tmsg');
  function say(text, bad) {
    if (!msg) return;
    msg.textContent = text;
    msg.classList.toggle('bad', !!bad);
  }
  function post(payload) {
    say('Saving...');
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
      if (!res.ok) { say(res.error || 'That did not work.', true); return; }
      say('Saved. Reloading...');
      setTimeout(function () { window.location.reload(); }, 400);
    }).catch(function (err) { say(String(err), true); });
  }

  var save = document.getElementById('tsave');
  if (save) save.onclick = function () {
    var names = {};
    document.querySelectorAll('.bname').forEach(function (i) {
      names[i.dataset.key] = i.value;
    });
    var payload = {
      name: document.getElementById('tname').value,
      blurb: document.getElementById('tblurb').value,
      building_names: names
    };
    var pic = document.getElementById('tpic');
    var chosen = pic && pic.files && pic.files[0];
    if (!chosen) { post(payload); return; }
    // Caught here rather than after the upload: the commonest refusal is a
    // picture over the limit, and finding that out after a slow upload of it
    // is the worst possible moment.
    if (chosen.size > 6 * 1024 * 1024) {
      say('That picture is ' + (chosen.size / 1048576).toFixed(1) +
          'MB. The limit is 6MB, so nothing was saved. Pick a smaller one, or ' +
          'clear it and save the rest.', true);
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      payload.image = String(reader.result).split(',').pop();
      payload.content_type = chosen.type;
      post(payload);
    };
    reader.readAsDataURL(chosen);
  };

  var clear = document.getElementById('tclear');
  if (clear) clear.onclick = function () { post({clear_image: true}); };
})();
"""
