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
from helpers.dodoland import townart
from helpers.dodoland import towns as town_rules
from helpers.dodoland import store as store_module

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


def _collect(bot, guild) -> dict:
    """Everything the page needs, in one pass. Blocking; call in an executor."""
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
    glow = flourish_rules.flourish_map(bot, guild.id)
    plots = bot.dodoland_buildings.plots(guild.id)
    lit = {int(row.get("user_id", 0)) for row in rows
           if str(row.get("day") or "") >= lit_since}

    details = bot.dodoland_towns.all(guild.id)
    base_pct = float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct"))
    growth = max(1.0, float(bot.dodoland_params.get(guild.id, "dodoland_town_growth")))
    biggest = max((p["power"] for p in result["order"]), default=0)
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
            })
        built.sort(key=lambda b: -b["tier"])
        shine = glow.get(uid) or flourish_rules.BLANK
        owner = _name_of(guild, bot, uid)
        people.append({
            "id": str(uid),
            "owner": owner,
            "name": town_rules.display_name(mine, owner),
            "blurb": str(mine.get("blurb") or ""),
            "has_image": bool(mine.get("image")),
            "power": person["power"],
            "place": person["place"],
            "reached": person["reached"],
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
            "w": round(base_pct * (1 + (growth - 1) * _grown(person["power"], biggest)), 4),
        })
    return {"people": people, "buildings": buildings, "total": len(result["people"])}


async def map_page(request: web.Request):
    """The map, given the whole window."""
    from web.routes import _page  # noqa: F401  (kept for the nav's sake)

    bot, guild = request.app["bot"], request["guild"]
    data = await asyncio.get_running_loop().run_in_executor(None, _collect, bot, guild)

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
    sizes = {
        # A proportion of the map's width, not a pixel count. Positions are
        # percentages for the same reason: re-uploading the map at another
        # resolution must change neither where a town sits nor how big it looks.
        "town_pct": float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct")),
        "dot_below": int(bot.dodoland_params.get(guild.id, "dodoland_town_dot_below")),
        "detail_above": int(bot.dodoland_params.get(guild.id, "dodoland_detail_above")),
        "ratio": townart.HEIGHT / townart.WIDTH,
        "min_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_min_zoom")),
        "max_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_max_zoom")),
    }

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Map · {_e(guild.name)}</title>
<style>{_CSS}</style>
</head><body>
<div class="dlbar">
  <a class="dlback" href="/guild/{guild.id}/dodoland">&larr; DodoLand</a>
  <b>{_e(guild.name)}</b>
  <span class="dlcount"><b id="dlplaced">{len(placed)}</b> on the map ·
    <b id="dlwaiting">{len(unplaced)}</b> waiting ·
    {len(data['people'])} with standing</span>
  <span class="dlspacer"></span>
  <button id="dltoggle" class="dlghost">Towns list</button>
</div>

<div class="dlframe" id="dlframe">
  <div class="dlworld" id="dlworld">{world}</div>
  <div class="dlzoom">
    <button type="button" id="dlin" title="Zoom in">+</button>
    <button type="button" id="dlout" title="Zoom out">&minus;</button>
    <button type="button" id="dlfit" title="Fit the whole map">&#9634;</button>
    <button type="button" id="dlnames" title="Show every name">A</button>
  </div>
  <div class="dlhint" id="dlhint">Drag to move, scroll to zoom</div>
</div>

<aside class="dldrawer" id="dldrawer">
  <div class="dldhead">
    <b>Towns</b>
    <button class="dlghost" id="dlclose">&times;</button>
  </div>
  <input class="dlsearch" id="dlsearch" placeholder="Search a name...">
  <div class="dllist" id="dllist"></div>
</aside>

<aside class="dlcard" id="dlcard" hidden></aside>

<script>window.DL = {json.dumps({"people": data["people"], "sizes": sizes,
                                 "gid": str(guild.id)})};</script>
<script>{_SCRIPT}</script>
</body></html>"""
    return web.Response(text=body, content_type="text/html")


_CSS = """
:root {
  --paper: #f3e5cb; --deep: #e0cba6; --ink: #3b2a1a; --soft: #6d5842;
  --edge: #c8ad83; --lantern: #b9762a; --bar: #241d18;
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #241d18; --deep: #171310; --ink: #efdcc0; --soft: #b39d81;
          --edge: #4a3a2b; --lantern: #f0a64f; --bar: #120f0c; }
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--deep); color: var(--ink); overflow: hidden;
  font: 15px/1.5 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }

.dlbar { position: fixed; inset: 0 0 auto 0; height: 52px; z-index: 30;
  display: flex; align-items: center; gap: 14px; padding: 0 16px;
  background: var(--bar); color: #f4e6cf; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
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
.dlworld { position: absolute; top: 0; left: 0; transform-origin: 0 0;
  will-change: transform; }
.dlworld img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }
.dlnomap { padding: 40px; color: var(--soft); }

.dlzoom { position: absolute; right: 16px; top: 16px; display: flex;
  flex-direction: column; gap: 6px; z-index: 12; }
.dlzoom button { width: 38px; height: 38px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--edge); background: var(--paper); color: var(--ink);
  box-shadow: 0 2px 10px rgba(0,0,0,.35); }
.dlzoom button.on { background: var(--lantern); color: #fff; }
.dlhint { position: absolute; left: 16px; bottom: 16px; z-index: 12;
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
.dltown svg { display: block; width: 100%; height: auto; overflow: visible; }
/* Below a few dozen pixels a settlement is an illegible smudge, so it becomes a
   dot, which is what every map does as you pull away from it. */
.dltown.tiny .dlart, .dltown.tiny .dlname { display: none; }
.dltown.tiny .dldot { display: block; }
.dldot { display: none; width: 9px; height: 9px; border-radius: 50%;
  background: #f0c98a; border: 2px solid #4a3524;
  box-shadow: 0 1px 3px rgba(0,0,0,.5);
  position: absolute; left: 50%; bottom: 0; transform: translate(-50%, 50%); }
.dltown.dim { opacity: .5; }
.dltown.on svg { filter: drop-shadow(0 0 6px var(--lantern)); }
.dltown.on .dldot { box-shadow: 0 0 0 3px var(--lantern); }
/* The name is drawn at a constant screen size, because a label that shrinks
   with the map stops being a label. It is the one thing here that is
   counter-scaled, and only ever the text. */
.dlname { position: absolute; left: 50%; top: 100%; margin-top: 4px;
  transform: translateX(-50%) scale(var(--inv, 1)); transform-origin: top center;
  padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: #fff6e4; background: rgba(20,14,8,.82); white-space: nowrap;
  opacity: 0; transition: opacity .12s ease; pointer-events: none; }
.dltown:hover { z-index: 9; }
.dltown:hover .dlname, .dlworld.named .dlname, .dltown.on .dlname { opacity: 1; }
/* Close-up flourishes: smoke, lit windows, waving banners, lantern halos. Off
   until the map says we are close enough, because three hundred smoking
   chimneys at map scale is noise rather than detail. */
.fx { display: none; }
.dltown.close .fx { display: inline; }
.dltown.close .glow { filter: blur(1.6px); animation: dlflicker 4s ease-in-out infinite; }
.dltown.close .halo { filter: blur(2.4px); opacity: .75;
  animation: dlflicker 3s ease-in-out infinite; }
.dltown.close .pf1 { animation: dlrise 5s linear infinite; }
.dltown.close .pf2 { animation: dlrise 5s linear infinite 1.6s; }
.dltown.close .pf3 { animation: dlrise 5s linear infinite 3.2s; }
.dltown.close .banner { animation: dlwave 2.6s ease-in-out infinite;
  transform-box: fill-box; transform-origin: left center; }
@keyframes dlflicker { 0%,100% { opacity: .85; } 50% { opacity: .45; } }
@keyframes dlrise {
  0% { opacity: 0; transform: translateY(0) scale(.7); }
  25% { opacity: .5; }
  100% { opacity: 0; transform: translateY(-14px) scale(1.4); }
}
@keyframes dlwave { 0%,100% { transform: skewY(0deg); } 50% { transform: skewY(-6deg); } }
@media (prefers-reduced-motion: reduce) {
  .dltown.close .glow, .dltown.close .halo, .dltown.close .pf1,
  .dltown.close .pf2, .dltown.close .pf3, .dltown.close .banner
    { animation: none; }
}

/* Flourish colours the ring the town art draws on its own ground plate. */
.fl1 { --fl1: #ffd682; } .fl2 { --fl2: #ffb84d; } .fl3 { --fl3: #ffc43d; }
.fl4 { --fl4: #78beff; } .fl5 { --fl5: #9682ff; } .fl6 { --fl6: #ff8cd2; }
.fl5 svg, .fl6 svg { animation: dlglow 3s ease-in-out infinite; }
@keyframes dlglow { 0%,100% { filter: brightness(1); } 50% { filter: brightness(1.3); } }
@media (prefers-reduced-motion: reduce) { .fl5 svg, .fl6 svg { animation: none; } }

/* Drawers float over the map rather than stealing its width. */
.dldrawer { position: fixed; top: 52px; bottom: 0; right: 0; width: 340px;
  z-index: 20; display: flex; flex-direction: column; background: var(--paper);
  border-left: 1px solid var(--edge); box-shadow: -6px 0 24px rgba(0,0,0,.28);
  transform: translateX(100%); transition: transform .18s ease; }
.dldrawer.open { transform: none; }
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

.dlcard { position: fixed; left: 16px; bottom: 16px; width: 330px; z-index: 25;
  padding: 16px 18px; border-radius: 12px; background: var(--paper);
  border: 1px solid var(--edge); box-shadow: 0 10px 34px rgba(0,0,0,.35); }
.dlcard h3 { margin: 0 0 2px; font-size: 19px; }
.dlcard .sub { color: var(--soft); font-size: 13px; margin-bottom: 10px; }
.dlcard ul { list-style: none; margin: 8px 0 0; padding: 0; }
.dlcard li { display: flex; align-items: center; gap: 8px; padding: 3px 0;
  font-size: 14px; }
.dlcard li i { width: 20px; text-align: center; color: var(--lantern); }
.dlcard .acts { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.dlcard .blurb { margin: 8px 0 0; font-size: 14px; color: var(--soft);
  white-space: pre-wrap; }
.dlcard img.pic { width: 100%; border-radius: 8px; margin-top: 10px;
  border: 1px solid var(--edge); }
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
  var view = {x: 0, y: 0, k: 1}, nat = {w: 0, h: 0};
  function apply() {
    world.style.transform = 'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.k + ')';
    // Towns live in map space but are drawn at screen size, so each is scaled
    // back by 1/k. Without this a town becomes a billboard at 4x.
    // Only labels are counter-scaled: a name that shrinks with the map stops
    // being a name. The towns themselves scale with the world on purpose.
    world.style.setProperty('--inv', (1 / view.k).toFixed(4));
    levelOfDetail();
  }
  function clamp() {
    var w = nat.w * view.k, h = nat.h * view.k, s = 90;
    view.x = Math.min(frame.clientWidth - s, Math.max(s - w, view.x));
    view.y = Math.min(frame.clientHeight - s, Math.max(s - h, view.y));
  }
  function fit() {
    if (!nat.w || !nat.h) return;
    // Measured after layout: called too early the frame has no height yet and
    // the map ends up stranded in the middle of a black screen, which is what
    // it did. A little air so the coastline is not flush against the edges.
    var fw = frame.clientWidth, fh = frame.clientHeight;
    if (!fw || !fh) { requestAnimationFrame(fit); return; }
    var pad = 24;
    view.k = Math.min((fw - pad * 2) / nat.w, (fh - pad * 2) / nat.h);
    view.k = Math.min(D.sizes.max_zoom, Math.max(D.sizes.min_zoom, view.k));
    view.x = (fw - nat.w * view.k) / 2;
    view.y = (fh - nat.h * view.k) / 2;
    apply();
  }
  function zoom(f, cx, cy) {
    var n = Math.min(D.sizes.max_zoom, Math.max(D.sizes.min_zoom, view.k * f));
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
    nat.w = base.naturalWidth || Math.round(box.width) || frame.clientWidth;
    nat.h = base.naturalHeight || Math.round(box.height) || frame.clientHeight;
    world.style.width = nat.w + 'px';
    world.style.height = nat.h + 'px';
    requestAnimationFrame(fit);
  }
  if (base) { if (base.complete && base.naturalWidth) measure();
              else base.addEventListener('load', measure); }
  window.addEventListener('resize', function () { clamp(); apply(); });

  frame.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var b = frame.getBoundingClientRect();
    zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX - b.left, ev.clientY - b.top);
  }, {passive: false});

  var dragging = false, moved = 0, last = null;
  frame.addEventListener('pointerdown', function (ev) {
    dragging = true; moved = 0; last = {x: ev.clientX, y: ev.clientY};
    frame.classList.add('dragging'); frame.setPointerCapture(ev.pointerId);
  });
  frame.addEventListener('pointermove', function (ev) {
    if (!dragging) return;
    var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
    moved += Math.abs(dx) + Math.abs(dy);
    view.x += dx; view.y += dy; last = {x: ev.clientX, y: ev.clientY};
    clamp(); apply();
  });
  ['pointerup', 'pointercancel'].forEach(function (e) {
    frame.addEventListener(e, function () {
      dragging = false; frame.classList.remove('dragging');
    });
  });
  document.getElementById('dlin').onclick = function () {
    zoom(1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlout').onclick = function () {
    zoom(1 / 1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlfit').onclick = fit;
  var namesBtn = document.getElementById('dlnames');
  namesBtn.onclick = function () {
    var on = world.classList.toggle('named');
    namesBtn.classList.toggle('on', on);
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
    // A percentage of the world, which is the base image's own width, so a town
    // is a fixed fraction of the map whatever resolution that image happens to
    // be. It sits inside the element the zoom scales, so it shrinks and grows
    // with the coastline.
    el.style.width = (person.w || D.sizes.town_pct) + '%';
    el.innerHTML = '<span class="dldot"></span>' +
      '<div class="dlart"></div>' +
      '<div class="dlname">' + escapeHtml(person.name) + '</div>';
    el.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (moved > 6) return;
      open(person.id);
    });
    world.appendChild(el);
    nodes[person.id] = el;
    return el;
  }

  function needArt(person, el) {
    // Fetched once per town, then kept. A town that is never approached is
    // never drawn, which is what lets a building be as detailed as it likes.
    if (art[person.id] === undefined) {
      art[person.id] = null;  // in flight; do not ask twice
      fetch('/guild/' + D.gid + '/dodoland/town/' + person.id + '/art')
        .then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (svg) {
          art[person.id] = svg;
          var host = nodes[person.id];
          if (host && svg) {
            host.querySelector('.dlart').innerHTML =
              '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
              svg + '</svg>';
          }
        }).catch(function () { art[person.id] = ''; });
    } else if (art[person.id]) {
      var host = el.querySelector('.dlart');
      if (!host.firstChild) {
        host.innerHTML = '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
          art[person.id] + '</svg>';
      }
    }
  }

  function levelOfDetail() {
    if (!nat.w) return;
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
    var on = D.people.filter(function (p) { return p.plot; }).length;
    document.getElementById('dlplaced').textContent = on;
    document.getElementById('dlwaiting').textContent = D.people.length - on;
  }

  // --- the town card ----------------------------------------------------- //
  var openId = null;
  function open(id) {
    var p = byId[id];
    if (!p) return;
    openId = id;
    world.querySelectorAll('.dltown').forEach(function (n) {
      n.classList.toggle('on', n.dataset.id === id);
    });
    var rows = p.built.map(function (b) {
      return '<li><span>' + escapeHtml(b.name) + ' — <b>' +
        escapeHtml(b.title) + '</b></span>' +
        '<span style="margin-left:auto;opacity:.7">' + b.points.toLocaleString() +
        '</span></li>';
    }).join('') || '<li style="opacity:.7">Nothing built yet.</li>';

    // Every building can be renamed, which is why they are inputs rather than
    // text once the editor is open. Naming is free and moves no number.
    var nameFields = p.built.map(function (b) {
      return '<label>' + escapeHtml(b.given) + '</label>' +
        '<input class="bname" data-key="' + escapeHtml(b.key) + '" maxlength="48" value="' +
        escapeHtml(b.name) + '">';
    }).join('');

    card.innerHTML =
      '<h3>' + escapeHtml(p.name) + '</h3>' +
      '<div class="sub">' + escapeHtml(p.owner) + ' · #' + p.place + ' · ' +
        p.power.toLocaleString() + ' standing · ' + p.reached.toLocaleString() +
        ' people reached' +
        (p.rank ? ' · ' + escapeHtml(p.flourish_label) + ' (' + escapeHtml(p.rank) + ')' : '') +
        '</div>' +
      (p.blurb ? '<p class="blurb">' + escapeHtml(p.blurb) + '</p>' : '') +
      (p.has_image ? '<img class="pic" alt="" src="/guild/' + D.gid +
        '/dodoland/town/' + p.id + '/picture">' : '') +
      '<ul>' + rows + '</ul>' +
      (p.plot ? '<div class="sub" style="margin-top:10px">At ' +
        p.plot.x.toFixed(1) + ', ' + p.plot.y.toFixed(1) + '</div>' : '') +
      '<div class="acts">' +
        '<button data-act="edit">Edit</button>' +
        '<button data-act="move">Move</button>' +
        '<button data-act="remove">Remove</button>' +
        '<button data-act="close">Close</button></div>' +
      '<div class="dledit">' +
        '<label>Town name</label>' +
        '<input id="tname" maxlength="48" value="' + escapeHtml(p.name) + '">' +
        '<label>Description</label>' +
        '<textarea id="tblurb" maxlength="600">' + escapeHtml(p.blurb) + '</textarea>' +
        '<label>Picture or GIF</label>' +
        '<input id="tpic" type="file" accept="image/png,image/jpeg,image/gif,image/webp">' +
        (nameFields ? '<label style="margin-top:12px"><b>Building names</b></label>' +
          nameFields : '') +
        '<div class="acts"><button data-act="save">Save</button>' +
        '<button data-act="clearpic">Remove picture</button></div>' +
      '</div>';
    card.hidden = false;
    var editor = card.querySelector('.dledit');
    card.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        var act = b.dataset.act;
        if (act === 'close') { closeCard(); }
        else if (act === 'move') { arm(id); closeCard(); }
        else if (act === 'remove') { place(id, null); closeCard(); }
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
            building_names: names
          };
          if (!chosen) { saveTown(id, payload); return; }
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

  function saveTown(id, payload) {
    payload.user_id = id;
    hint.textContent = 'Saving...';
    fetch('/api/guild/' + D.gid + '/dodoland/town', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { hint.textContent = res.error || 'That did not work.'; return; }
      hint.textContent = 'Saved.';
      window.location.reload();
    });
  }
  function closeCard() {
    card.hidden = true; openId = null;
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
  function place(id, point) {
    fetch('/api/guild/' + D.gid + '/dodoland/settle', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(point
        ? {user_id: id, x: point.x, y: point.y}
        : {user_id: id, remove: true})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { hint.textContent = res.error || 'That did not work.'; return; }
      byId[id].plot = point ? {x: res.x, y: res.y} : null;
      armed = null;
      frame.classList.remove('placing');
      hint.textContent = point ? 'Placed.' : 'Removed from the map.';
      redraw(); renderList();
    });
  }
  frame.addEventListener('click', function (ev) {
    if (!armed || moved > 6 || !nat.w) return;
    var b = frame.getBoundingClientRect();
    place(armed, {
      x: ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100,
      y: ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100
    });
  });

  // --- the list ---------------------------------------------------------- //
  var search = document.getElementById('dlsearch');
  function renderList() {
    var q = (search.value || '').toLowerCase();
    var hit = D.people.filter(function (p) {
      return !q || p.name.toLowerCase().indexOf(q) >= 0;
    });
    var waiting = hit.filter(function (p) { return !p.plot; });
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
        else { arm(p.id); }
      };
    });
  }
  search.addEventListener('input', renderList);
  document.getElementById('dltoggle').onclick = function () {
    drawer.classList.toggle('open');
  };
  document.getElementById('dlclose').onclick = function () {
    drawer.classList.remove('open');
  };

  redraw();
  renderList();
  drawer.classList.add('open');
})();
"""
