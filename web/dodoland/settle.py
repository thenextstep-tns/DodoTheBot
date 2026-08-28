"""
The two pages members actually see: the shared map, and your own plot.

Both sit behind capability links, the way the trial board does: **no session and
no login, so the URL is the credential** and is treated like one.

* ``/m/{gid}/{token}`` — the whole server's map, read-only. One link, handed out
  by an admin, that anybody may look at. This is the point of the feature: a map
  worth screenshotting is a map people can see.
* ``/t/{gid}/{token}`` — one person's own link. The token names exactly one
  member, and the only thing it can do is move that member's town. It cannot
  move anybody else's, change a setting, or read the panel.

Why a link rather than the panel: the panel is admin-scoped because it ranks
everybody. Looking at the map, and choosing where you live, are not
administrative acts and should never require handing somebody the whole page.

Why picking at all, rather than accepting the suggestion: choosing where you live
is most of the fun. The graph-driven suggestion exists so the map is never a
scatter of unrelated dots and so somebody who never chooses still has a sensible
home. It was always meant to be a starting position rather than a verdict.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from helpers import share_tokens
from web.dodoland import townmap

_e = townmap.e


def _not_found() -> web.Response:
    """One answer for a bad token and for a guild that is not here.

    A public endpoint should never confirm which servers exist.
    """
    return web.Response(status=404, text="Not found.", content_type="text/plain")


def _resolve(request, kind: str):
    """``(bot, guild, record)`` for a valid link of that kind, or ``None``."""
    bot = request.app["bot"]
    try:
        guild_id = int(request.match_info["gid"])
    except (TypeError, ValueError):
        return None
    token = request.match_info.get("token") or ""
    record = bot.share_tokens.resolve(guild_id, token, kind=kind)
    if record is None:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    return bot, guild, record


async def asset_image(request: web.Request):
    """One asset's bytes.

    Unauthenticated on purpose: an asset id is a random token and the images are
    decorations an admin uploaded for the server to look at. Gating them behind
    a capability check would mean threading a token through every ``<img>`` on
    the page, which puts the token in far more places than it is worth.
    """
    bot = request.app["bot"]
    try:
        guild_id = int(request.match_info["gid"])
    except (TypeError, ValueError):
        return _not_found()
    row = bot.dodoland_assets.get(guild_id, request.match_info.get("aid") or "")
    if row is None:
        return _not_found()
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # Immutable: an asset id is never reused, so a long cache is safe and
        # keeps a toolkit of fifty icons from being refetched on every load.
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


# --------------------------------------------------------------------------- #
#  The public map
# --------------------------------------------------------------------------- #
async def public_map(request: web.Request):
    """Everybody's towns, read-only, for anybody holding the link."""
    resolved = _resolve(request, share_tokens.KIND_PUBLIC)
    if resolved is None:
        return _not_found()
    bot, guild, _record = resolved

    towns = await asyncio.get_running_loop().run_in_executor(
        None, townmap.build_towns, bot, guild)
    sizes = townmap.sizes_for(bot, guild)
    assets = bot.dodoland_assets.list(guild.id)

    settled = sum(1 for town in towns if town["settled"])
    lit = sum(1 for town in towns if town["lit"])
    body = f"""
<h1>The map of {_e(guild.name)}</h1>
<p class="dllede">Every town here was built by somebody turning up and talking to
people. <b>{len(towns):,}</b> of them, <b>{lit:,}</b> lit this month,
<b>{settled:,}</b> settled where their owner chose.</p>
{townmap.canvas(bot, guild, towns, sizes=sizes)}
<p class="dlmsg">Towns sit beside the people their owner talks to most, so the
clusters here are friendships.</p>
{townmap.roll(towns)}
{townmap.toolkit(assets, set(), guild_id=guild.id)}
<div class="dlnote">
  <p>A dim town simply has not been active this month. Nothing is ever taken
  away, and coming back lights it again.</p>
  <p>The glow around a town comes from its owner's trial rank. It is decoration
  and never changes what they have built.</p>
</div>"""
    return web.Response(
        text=townmap.page(f"The map of {guild.name}", guild, body,
                          script=townmap.VIEWPORT_SCRIPT),
        content_type="text/html", headers=townmap.HEADERS)


# --------------------------------------------------------------------------- #
#  One person's own plot
# --------------------------------------------------------------------------- #
_SETTLE_SCRIPT = """
<script>
(function () {
  var canvas = document.getElementById('dlframe');
  if (!canvas) return;
  var msg = document.getElementById('dlsettlemsg');
  canvas.addEventListener('click', function (event) {
    // The viewport owns the transform, so it owns the maths. A click at the end
    // of a pan is a pan, not a decision to move house.
    var point = window.dlMapPoint ? window.dlMapPoint(event) : null;
    if (!point || point.dragged) return;
    msg.textContent = 'Packing up...';
    fetch(window.location.pathname + '/settle', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({x: point.x, y: point.y})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { msg.textContent = res.error || 'That did not work.'; return; }
      var mine = canvas.querySelector('.dltown.mine');
      if (!mine) { window.location.reload(); return; }
      mine.style.left = res.x + '%';
      mine.style.top = res.y + '%';
      msg.textContent = 'Settled. This is your patch of the world until you move it.';
    }).catch(function () { msg.textContent = 'That did not work.'; });
  });
})();
</script>"""


async def settle_page(request: web.Request):
    """The map, with the reader's own town highlighted and movable."""
    resolved = _resolve(request, share_tokens.KIND_USER)
    if resolved is None or not (resolved[2] or {}).get("user_id"):
        return _not_found()
    bot, guild, record = resolved
    user_id = int(record["user_id"])

    towns = await asyncio.get_running_loop().run_in_executor(
        None, townmap.build_towns, bot, guild)
    sizes = townmap.sizes_for(bot, guild)
    mine = next((town for town in towns if town["user_id"] == user_id), None)

    if mine is None:
        where = ("You have not founded a town yet. Click anywhere on the map to "
                 "build one.")
    elif mine["settled"]:
        where = "This is where you chose to live. Click anywhere to pack up and move."
    else:
        where = ("We put your town beside the people you talk to most, to save you "
                 "the walk. It is only a suggestion: click anywhere to choose for "
                 "yourself.")

    body = f"""
<h1>Your town</h1>
<p class="dllede">{_e(where)}</p>
{townmap.canvas(bot, guild, towns, mine=user_id, pickable=True, sizes=sizes)}
<p class="dlmsg" id="dlsettlemsg"></p>
<div class="dlnote">
  <p>Only your own town can be moved from this link, and it is yours to move as
  often as you like.</p>
  <p><b>Where you build never changes what you have earned.</b></p>
</div>"""
    return web.Response(
        text=townmap.page(f"Your town in {guild.name}", guild, body,
                          script=townmap.VIEWPORT_SCRIPT + _SETTLE_SCRIPT),
        content_type="text/html", headers=townmap.HEADERS)


async def api_settle_own(request: web.Request):
    """Move the town belonging to the link. Never anybody else's.

    The user id comes from the token and is never read from the request body,
    which is the whole security property: holding a link lets you move one town,
    and no amount of editing the payload changes which one.
    """
    resolved = _resolve(request, share_tokens.KIND_USER)
    if resolved is None or not (resolved[2] or {}).get("user_id"):
        return _not_found()
    bot, guild, record = resolved

    try:
        body = await request.json()
        x, y = float(body.get("x")), float(body.get("y"))
    except Exception:  # noqa: BLE001 - any unusable body gets the same answer
        return web.json_response({"ok": False, "error": "That position made no sense."},
                                 headers=townmap.HEADERS)
    if not bot.dodoland_buildings.map_image(guild.id):
        return web.json_response({"ok": False, "error": "This server has no map yet."},
                                 headers=townmap.HEADERS)
    spot = bot.dodoland_buildings.settle(guild.id, int(record["user_id"]), x, y)
    return web.json_response({"ok": True, **spot}, headers=townmap.HEADERS)
