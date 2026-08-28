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

**A town is drawn from what stands in it.** Not a dot: a small cluster of the
buildings that person has actually reached a tier in, each one a Font Awesome
glyph, sized by how far it has come. A settlement with a library, a bakery and a
forge looks like a different place from one with barracks and a war room, which
is the whole reason buildings were worth having.

**Clicking a town opens it.** Standing, place, flourish, every building and its
tier, and the coordinates. A map you cannot interrogate is wallpaper.

Font Awesome is loaded from its CDN. It is the one external dependency on this
page and it degrades to nothing worse than missing glyphs.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json

from aiohttp import web

from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import standing
from helpers.dodoland import store as store_module

FONT_AWESOME = ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/"
                "css/all.min.css")


def _e(value) -> str:
    return html.escape(str(value))


def _name_of(guild, bot, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    if member is not None:
        return member.display_name
    user = bot.get_user(int(user_id))
    return user.name if user is not None else f"User {user_id}"


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

    by_key = {b["key"]: b for b in buildings}
    people = []
    for person in result["order"]:
        uid = person["user_id"]
        built = []
        for key, score in person["buildings"].items():
            if score.get("tier") is None:
                continue
            built.append({
                "key": key,
                "name": score["name"],
                "fa": by_key.get(key, {}).get("fa") or "fa-house",
                "tier": int(score["tier"]) + 1,
                "title": score["tier_title"],
                "points": score["points"],
            })
        built.sort(key=lambda b: -b["tier"])
        shine = glow.get(uid) or flourish_rules.BLANK
        people.append({
            "id": str(uid),
            "name": _name_of(guild, bot, uid),
            "power": person["power"],
            "place": person["place"],
            "reached": person["reached"],
            "built": built,
            "flourish": int(shine.get("level", 0)),
            "flourish_label": shine.get("label") or "",
            "rank": shine.get("rank_name") or "",
            "lit": uid in lit,
            "plot": plots.get(uid),
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
        "town": int(bot.dodoland_params.get(guild.id, "dodoland_town_size")),
        "min_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_min_zoom")),
        "max_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_max_zoom")),
    }

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Map · {_e(guild.name)}</title>
<link rel="stylesheet" href="{FONT_AWESOME}" crossorigin="anonymous" referrerpolicy="no-referrer">
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
    <button type="button" id="dlin" title="Zoom in"><i class="fa-solid fa-plus"></i></button>
    <button type="button" id="dlout" title="Zoom out"><i class="fa-solid fa-minus"></i></button>
    <button type="button" id="dlfit" title="Fit"><i class="fa-solid fa-expand"></i></button>
    <button type="button" id="dlnames" title="Show names"><i class="fa-solid fa-font"></i></button>
  </div>
  <div class="dlhint" id="dlhint">Drag to move, scroll to zoom</div>
</div>

<aside class="dldrawer" id="dldrawer">
  <div class="dldhead">
    <b>Towns</b>
    <button class="dlghost" id="dlclose"><i class="fa-solid fa-xmark"></i></button>
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

/* A town: a cluster of the buildings that actually stand in it. Counter-scaled
   so it keeps its size on screen however far the map is zoomed. */
.dltown { position: absolute; transform-origin: 50% 50%;
  transform: translate(-50%, -50%) scale(var(--inv, 1));
  display: flex; flex-direction: column; align-items: center;
  cursor: pointer; z-index: 5; }
/* A settlement, not a fence. Buildings overlap slightly, sit on a common
   baseline, and the tallest are drawn behind the shorter ones, so the cluster
   has a silhouette instead of being a row of evenly-spaced identical icons. */
.dlbuildings { display: flex; align-items: flex-end; justify-content: center;
  filter: drop-shadow(0 3px 4px rgba(0,0,0,.6)); }
.dlbuildings i { color: #f7e7c8; margin: 0 -2px; }
.dlbuildings i:nth-child(2n) { color: #e8cfa4; }
.dlbuildings i:nth-child(3n) { color: #fff3dd; }
/* Taller tiers read as bigger buildings, so a grown town looks grown. */
.dlb1 { font-size: 12px; } .dlb2 { font-size: 15px; } .dlb3 { font-size: 19px; }
.dlb4 { font-size: 23px; } .dlb5 { font-size: 28px; } .dlb6 { font-size: 34px; }
.dlground { width: 70%; min-width: 30px; height: 6px; border-radius: 50%;
  margin-top: -3px; background: rgba(20,10,0,.5); filter: blur(1.5px); }
/* Legible on any coastline: a pill rather than text floating on white. */
.dlname { margin-top: 5px; padding: 2px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 600; letter-spacing: .01em;
  color: #fff6e4; background: rgba(20,14,8,.82); white-space: nowrap;
  opacity: 0; transition: opacity .12s ease; }
.dltown:hover { z-index: 9; }
.dltown:hover .dlname, .dlworld.named .dlname, .dltown.on .dlname { opacity: 1; }
.dltown.dim { opacity: .45; }
.dltown.on .dlbuildings { filter: drop-shadow(0 0 6px var(--lantern))
  drop-shadow(0 2px 3px rgba(0,0,0,.55)); }
/* Flourish: earned from trial rank, decoration only, never a tier. */
.fl1 .dlbuildings i { text-shadow: 0 0 6px rgba(255,214,130,.95); }
.fl2 .dlbuildings i { text-shadow: 0 0 8px rgba(255,184,77,.95); }
.fl3 .dlbuildings i { text-shadow: 0 0 10px rgba(255,196,61,1); color: #fff2cf; }
.fl4 .dlbuildings i { text-shadow: 0 0 12px rgba(120,190,255,1); color: #eaf5ff; }
.fl5 .dlbuildings i { text-shadow: 0 0 14px rgba(150,130,255,1); color: #f1ecff;
  animation: dlglow 3.4s ease-in-out infinite; }
.fl6 .dlbuildings i { text-shadow: 0 0 18px rgba(255,140,210,1); color: #fff;
  animation: dlglow 2.2s ease-in-out infinite; }
@keyframes dlglow { 0%,100% { filter: brightness(1); } 50% { filter: brightness(1.4); } }
@media (prefers-reduced-motion: reduce) {
  .fl5 .dlbuildings i, .fl6 .dlbuildings i { animation: none; }
}

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
.dlcard .acts { display: flex; gap: 8px; margin-top: 14px; }
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
    world.style.setProperty('--inv', (1 / view.k).toFixed(4));
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
  function draw(person) {
    var el = document.createElement('div');
    el.className = 'dltown fl' + person.flourish + (person.lit ? '' : ' dim');
    el.dataset.id = person.id;
    el.style.left = person.plot.x + '%';
    el.style.top = person.plot.y + '%';
    // A town is what stands in it. Six buildings is already a skyline; past
    // that the cluster stops reading as a place.
    // Tallest in the middle, shorter ones flanking: a silhouette rather than a
    // row. Six is already a skyline; past that the cluster stops reading as a
    // place at all.
    var top = person.built.slice(0, 6);
    var arranged = [];
    top.forEach(function (b, i) {
      if (i % 2) arranged.push(b); else arranged.unshift(b);
    });
    var shown = arranged.map(function (b) {
      return '<i class="fa-solid ' + b.fa + ' dlb' + Math.min(6, b.tier) +
        '" title="' + escapeHtml(b.name + ' — ' + b.title) + '"></i>';
    }).join('');
    if (!shown) shown = '<i class="fa-solid fa-campground dlb1"></i>';
    el.innerHTML = '<div class="dlbuildings">' + shown + '</div>' +
      '<div class="dlground"></div>' +
      '<div class="dlname">' + escapeHtml(person.name) + '</div>';
    el.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (moved > 6) return;
      open(person.id);
    });
    world.appendChild(el);
    return el;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function redraw() {
    world.querySelectorAll('.dltown').forEach(function (n) { n.remove(); });
    D.people.forEach(function (p) { if (p.plot) draw(p); });
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
      return '<li><i class="fa-solid ' + b.fa + '"></i><span>' +
        escapeHtml(b.name) + ' — <b>' + escapeHtml(b.title) + '</b></span>' +
        '<span style="margin-left:auto;opacity:.7">' + b.points.toLocaleString() +
        '</span></li>';
    }).join('') || '<li style="opacity:.7">Nothing built yet.</li>';
    card.innerHTML =
      '<h3>' + escapeHtml(p.name) + '</h3>' +
      '<div class="sub">#' + p.place + ' · ' + p.power.toLocaleString() +
        ' standing · ' + p.reached.toLocaleString() + ' people reached' +
        (p.rank ? ' · ' + escapeHtml(p.flourish_label) + ' (' + escapeHtml(p.rank) + ')' : '') +
        '</div>' +
      '<ul>' + rows + '</ul>' +
      (p.plot ? '<div class="sub" style="margin-top:10px">At ' +
        p.plot.x.toFixed(1) + ', ' + p.plot.y.toFixed(1) + '</div>' : '') +
      '<div class="acts">' +
        '<button data-act="move">Move</button>' +
        '<button data-act="remove">Remove</button>' +
        '<button data-act="close">Close</button></div>';
    card.hidden = false;
    card.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        if (b.dataset.act === 'close') { closeCard(); }
        else if (b.dataset.act === 'move') { arm(id); closeCard(); }
        else { place(id, null); closeCard(); }
      };
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
