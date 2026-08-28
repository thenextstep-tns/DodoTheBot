"""
The page a player picks their own plot on.

Behind a per-person capability link, the same way the trial board is: **no
session and no login, so the URL is the credential** and is treated like one.
The token names exactly one person in exactly one guild, and the only thing the
page can do is move that person's town. It cannot move anybody else's, cannot
read the standings, and cannot change a setting.

Why a link rather than the panel: the panel is admin-scoped because it ranks
everybody, and this must not be. A player choosing where they live is not an
administrative act and should never require handing somebody the whole page.

Why picking at all, rather than just accepting the suggestion: choosing where
you live is most of the fun. The graph-driven suggestion exists so the map is
never a scatter of unrelated dots and so somebody who never chooses still has a
sensible home, but it was always meant to be a starting position rather than a
verdict. Anybody who places their town keeps that spot.
"""

from __future__ import annotations

import base64
import html

from aiohttp import web

from helpers import share_tokens
from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import mapview
from helpers.dodoland import standing
from helpers.dodoland import store as store_module

# Never served from a cache or an index, and no referrer, which is how a token
# in a path leaks in practice.
_HEADERS = {
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
}


# --------------------------------------------------------------------------- #
#  The look
# --------------------------------------------------------------------------- #
# Deliberately **not** panel.css. That stylesheet is for an admin surface: dense,
# neutral, built for reading tables. This is the one page a player ever sees, and
# it should feel like unrolling a map on a table rather than opening a dashboard.
# So: warm paper, ink, a serif, generous space, and one thing to do on the page.
#
# Self-contained and inline, because the page is served from a capability link
# and should not depend on the panel's assets, its versioning, or its theme.
# System fonts only: no external request survives a strict network anyway, and a
# map that waits on a webfont to render is a map that flashes.
_COZY_CSS = """
:root {
  --paper: #f3e5cb; --paper-deep: #e8d5b0; --ink: #3b2a1a; --ink-soft: #6d5842;
  --edge: #c8ad83; --lantern: #d98d3a; --lantern-soft: rgba(217, 141, 58, .25);
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #241d18; --paper-deep: #1a1511; --ink: #efdcc0; --ink-soft: #b39d81;
    --edge: #4a3a2b; --lantern: #f0a64f; --lantern-soft: rgba(240, 166, 79, .28);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 28px 16px 60px; min-height: 100vh; color: var(--ink);
  background: var(--paper-deep);
  /* Two soft pools of light on the paper, so it reads as a lit table rather
     than a flat fill. */
  background-image:
    radial-gradient(1100px 600px at 18% -10%, var(--lantern-soft), transparent 60%),
    radial-gradient(900px 500px at 92% 110%, var(--lantern-soft), transparent 60%);
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  font-size: 17px; line-height: 1.65;
}
.dlpaper {
  max-width: 1040px; margin: 0 auto; padding: 34px clamp(18px, 5vw, 52px) 42px;
  background: var(--paper); border: 1px solid var(--edge); border-radius: 14px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .22), inset 0 0 90px rgba(140, 105, 60, .10);
}
.dleyebrow {
  margin: 0 0 2px; text-transform: uppercase; letter-spacing: .16em;
  font-size: 11px; color: var(--ink-soft);
}
h1 { margin: 0 0 10px; font-size: clamp(30px, 5vw, 42px); font-weight: 600;
  letter-spacing: .01em; }
.dllede { margin: 0 0 22px; font-size: 18px; color: var(--ink-soft); max-width: 60ch; }
.dlmsg { min-height: 1.6em; margin: 14px 0 0; color: var(--lantern);
  font-style: italic; }
.dlnote { margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--edge);
  color: var(--ink-soft); font-size: 15px; }
.dlnote p { margin: 0 0 6px; }

/* The map itself. A crosshair, because the whole page is one invitation. */
.dlcanvas {
  position: relative; display: block; margin: 8px 0 0; line-height: 0;
  border-radius: 10px; border: 1px solid var(--edge); overflow: hidden;
  cursor: crosshair; box-shadow: inset 0 0 60px rgba(60, 40, 20, .28);
}
.dlcanvas img { display: block; width: 100%; height: auto; }

/* A town is a marker, not a control: it must never eat the click meant for the
   map underneath it. */
.dltown {
  position: absolute; transform: translate(-50%, -50%); pointer-events: none;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
}
.dltowndot {
  display: block; width: calc(10px * var(--dl-size, 1));
  height: calc(10px * var(--dl-size, 1)); border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff6e2, var(--lantern) 70%);
  border: 2px solid rgba(255, 245, 225, .9);
  box-shadow: 0 2px 6px rgba(0, 0, 0, .45);
}
.dltownname {
  font-size: 11px; letter-spacing: .02em; color: #fff8ea; white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, .95), 0 0 10px rgba(0, 0, 0, .7);
}
/* Your own town: a ring of lantern light, so it is findable at a glance. */
.dltown.mine .dltowndot {
  border-color: #fffaf0;
  box-shadow: 0 0 0 4px var(--lantern), 0 0 22px 8px rgba(217, 141, 58, .55);
}
.dltown.mine .dltownname { font-size: 12.5px; font-weight: 600; }

/* Flourish, earned from trial rank alone. Warm at the bottom, otherworldly at
   the top, and always readable against a busy map. */
.dltown.fl1 .dltowndot { box-shadow: 0 0 8px 2px rgba(255, 214, 130, .9); }
.dltown.fl2 .dltowndot { box-shadow: 0 0 11px 3px rgba(255, 184, 77, .9); }
.dltown.fl3 .dltowndot { box-shadow: 0 0 15px 4px rgba(255, 196, 61, .95);
  border-color: #ffe9a8; }
.dltown.fl4 .dltowndot { box-shadow: 0 0 19px 6px rgba(120, 190, 255, .9);
  border-color: #dcefff; }
.dltown.fl5 .dltowndot { box-shadow: 0 0 24px 8px rgba(150, 130, 255, .9);
  border-color: #ece6ff; animation: dlbreathe 3.4s ease-in-out infinite; }
.dltown.fl6 .dltowndot { box-shadow: 0 0 30px 11px rgba(255, 140, 210, .9);
  border-color: #fff; animation: dlbreathe 2.2s ease-in-out infinite; }
@keyframes dlbreathe {
  0%, 100% { transform: scale(1); filter: brightness(1); }
  50% { transform: scale(1.16); filter: brightness(1.3); }
}
/* A crowded map of animated towns is a phone's whole frame budget, and some
   people have asked for less motion for reasons that are not about batteries. */
@media (prefers-reduced-motion: reduce) {
  .dltown.fl5 .dltowndot, .dltown.fl6 .dltowndot { animation: none; }
}
@media (max-width: 620px) {
  body { padding: 14px 8px 40px; font-size: 16px; }
  .dlpaper { padding: 22px 16px 30px; border-radius: 10px; }
  /* Names would tile into an unreadable mat at this width; the lights still
     read, and your own town keeps its label. */
  .dltown .dltownname { display: none; }
  .dltown.mine .dltownname { display: block; }
}
"""


def _e(value) -> str:
    return html.escape(str(value))


def _not_found() -> web.Response:
    """One answer for a bad token and for a guild that is not here.

    A public endpoint should not confirm which servers exist.
    """
    return web.Response(status=404, text="Not found.", content_type="text/plain")


def _resolve(request):
    """``(bot, guild, user_id)`` for a valid link, or ``None``."""
    bot = request.app["bot"]
    try:
        guild_id = int(request.match_info["gid"])
    except (TypeError, ValueError):
        return None
    token = request.match_info.get("token") or ""
    record = bot.share_tokens.resolve(guild_id, token, kind=share_tokens.KIND_USER)
    if record is None or not record.get("user_id"):
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    return bot, guild, int(record["user_id"])


async def settle_page(request: web.Request):
    """The map, with the reader's own town highlighted and movable."""
    resolved = _resolve(request)
    if resolved is None:
        return _not_found()
    bot, guild, user_id = resolved

    image = bot.dodoland_buildings.map_image(guild.id)
    buildings = bot.dodoland_buildings.buildings(guild.id)
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)

    import asyncio

    loop = asyncio.get_running_loop()

    def work():
        result = standing.guild_standings(bot.dodoland, bot.dodoland_params,
                                          guild.id, buildings, since=since)
        partners: dict = {}
        for row in bot.dodoland.pair_rows(guild.id, since=since):
            a, b, n = int(row.get("a", 0)), int(row.get("b", 0)), int(row.get("n", 0))
            partners.setdefault(a, {})[b] = partners.setdefault(a, {}).get(b, 0) + n
            partners.setdefault(b, {})[a] = partners.setdefault(b, {}).get(a, 0) + n
        names = {p["user_id"]: (guild.get_member(p["user_id"]).display_name
                                if guild.get_member(p["user_id"]) else "Somebody")
                 for p in result["order"]}
        return mapview.towns(
            result["order"], partners=partners,
            settled=bot.dodoland_buildings.plots(guild.id),
            flourish=flourish_rules.flourish_map(bot, guild.id),
            names=names,
        )

    towns = await loop.run_in_executor(None, work)
    mine = next((town for town in towns if town["user_id"] == user_id), None)

    if not image:
        canvas = ('<p class="dllede">There is no map of this land yet. Ask an '
                  'admin to draw one, then come back to this link.</p>')
    else:
        raw = image.get("data")
        blob = bytes(raw) if raw is not None else b""
        encoded = base64.b64encode(blob).decode("ascii")
        markers = ""
        for town in towns:
            own = town["user_id"] == user_id
            classes = f"dltown fl{town['flourish']}" + (" mine" if own else "")
            label = "Your town" if own else town["name"]
            markers += (
                f'<div class="{classes}" style="left:{town["x"]}%;top:{town["y"]}%;'
                f'--dl-size:{town["size"]:g}" title="{_e(label)}">'
                f'<span class="dltowndot"></span>'
                f'<span class="dltownname">{_e(label)}</span></div>'
            )
        canvas = f"""
<div class="dlcanvas" id="dlcanvas">
  <img class="dlmap" alt="The map of {_e(guild.name)}"
       src="data:{_e(image.get('content_type'))};base64,{encoded}">
  {markers}
</div>"""

    if mine is None:
        where = "You have not founded a town yet. Click anywhere on the map to build one."
    elif mine["settled"]:
        where = "This is where you chose to live. Click anywhere to pack up and move."
    else:
        where = ("We put your town beside the people you talk to most, to save you "
                 "the walk. It is only a suggestion: click anywhere to choose for yourself.")

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="referrer" content="no-referrer">
<title>Your town in {_e(guild.name)}</title>
<style>{_COZY_CSS}</style>
</head><body>
<main class="dlpaper">
  <p class="dleyebrow">{_e(guild.name)}</p>
  <h1>Your town</h1>
  <p class="dllede">{_e(where)}</p>
  {canvas}
  <p class="dlmsg" id="dlsettlemsg"></p>
  <div class="dlnote">
    <p>Only your own town can be moved from here, and it is yours to move as
    often as you like.</p>
    <p><b>Where you build never changes what you have earned.</b></p>
  </div>
</main>
<script>
(function () {{
  var canvas = document.getElementById('dlcanvas');
  if (!canvas) return;
  var msg = document.getElementById('dlsettlemsg');
  canvas.addEventListener('click', function (event) {{
    var box = canvas.getBoundingClientRect();
    var x = ((event.clientX - box.left) / box.width) * 100;
    var y = ((event.clientY - box.top) / box.height) * 100;
    msg.textContent = 'Packing up...';
    fetch(window.location.pathname + '/settle', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{x: x, y: y}})
    }}).then(function (r) {{ return r.json(); }}).then(function (res) {{
      if (!res.ok) {{ msg.textContent = res.error || 'That did not work.'; return; }}
      var mine = canvas.querySelector('.dltown.mine');
      if (!mine) {{ window.location.reload(); return; }}
      mine.style.left = res.x + '%';
      mine.style.top = res.y + '%';
      msg.textContent = 'Settled. This is your patch of the world until you move it.';
    }}).catch(function () {{ msg.textContent = 'That did not work.'; }});
  }});
}})();
</script>
</body></html>"""
    return web.Response(text=body, content_type="text/html", headers=_HEADERS)


async def api_settle_own(request: web.Request):
    """Move the town belonging to the link. Never anybody else's.

    The user id comes from the token and is never read from the request body,
    which is the whole security property: possessing a link lets you move one
    town, and no amount of editing the payload changes which.
    """
    resolved = _resolve(request)
    if resolved is None:
        return _not_found()
    bot, guild, user_id = resolved

    try:
        body = await request.json()
        x, y = float(body.get("x")), float(body.get("y"))
    except (TypeError, ValueError, Exception):  # noqa: B014 - any bad body is one answer
        return web.json_response({"ok": False, "error": "That position made no sense."},
                                 headers=_HEADERS)
    if not bot.dodoland_buildings.map_image(guild.id):
        return web.json_response({"ok": False, "error": "This server has no map yet."},
                                 headers=_HEADERS)
    spot = bot.dodoland_buildings.settle(guild.id, user_id, x, y)
    return web.json_response({"ok": True, **spot}, headers=_HEADERS)
