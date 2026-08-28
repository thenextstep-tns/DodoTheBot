"""
The map as players see it, shared by every page that draws one.

Two pages render this map: the public one anybody with the link can look at, and
the private one a player moves their own town on. They must not drift apart —
somebody settling their town and then seeing it somewhere else on the shared map
would be a bug nobody could explain — so the towns, the styling and the page
shell are all built here and neither page owns a copy.

Deliberately **not** ``panel.css``. That stylesheet is for an admin surface:
dense, neutral, built for reading tables. This is what a member of the server
actually sees, and it should feel like unrolling a map on a table rather than
opening a dashboard. Warm paper, ink, a serif, and one thing to do on the page.

Self-contained and inline, because these pages are served from capability links
and should not depend on the panel's assets, its versioning or its theme. System
fonts only: a map that waits on a webfont to render is a map that flashes.
"""

from __future__ import annotations

import base64
import html
from typing import Optional

from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import mapview
from helpers.dodoland import standing
from helpers.dodoland import store as store_module

# A token in a URL leaks through referrers, caches and search engines, so none
# of those get a chance at it.
HEADERS = {
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
}

COZY_CSS = """
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
  /* Two soft pools of light, so it reads as a lit table rather than a fill. */
  background-image:
    radial-gradient(1100px 600px at 18% -10%, var(--lantern-soft), transparent 60%),
    radial-gradient(900px 500px at 92% 110%, var(--lantern-soft), transparent 60%);
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  font-size: 17px; line-height: 1.65;
}
.dlpaper {
  max-width: 1100px; margin: 0 auto; padding: 34px clamp(18px, 5vw, 52px) 42px;
  background: var(--paper); border: 1px solid var(--edge); border-radius: 14px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .22), inset 0 0 90px rgba(140, 105, 60, .10);
}
.dleyebrow { margin: 0 0 2px; text-transform: uppercase; letter-spacing: .16em;
  font-size: 11px; color: var(--ink-soft); }
h1 { margin: 0 0 10px; font-size: clamp(30px, 5vw, 42px); font-weight: 600; }
.dllede { margin: 0 0 22px; font-size: 18px; color: var(--ink-soft); max-width: 62ch; }
.dlmsg { min-height: 1.6em; margin: 14px 0 0; color: var(--lantern); font-style: italic; }
.dlnote { margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--edge);
  color: var(--ink-soft); font-size: 15px; }
.dlnote p { margin: 0 0 6px; }

/* The map gets a framed block of its own. Not full-bleed: it sits inside a
   page with text around it, and a band running off both edges of the screen
   fights everything else on the page rather than framing anything. */
.dlstage { position: relative; margin: 14px 0 0; width: 100%; }
.dlframe { position: relative; height: min(72vh, 820px); overflow: hidden;
  border-radius: 12px; border: 1px solid var(--edge); background: var(--paper-deep);
  box-shadow: inset 0 0 100px rgba(60, 40, 20, .4);
  touch-action: none; cursor: grab; }
.dlframe.dragging { cursor: grabbing; }
.dlframe.pickable { cursor: crosshair; }
/* The image scales; the things standing on it do not. */
.dlworld { position: absolute; top: 0; left: 0; transform-origin: 0 0;
  will-change: transform; }
.dlworld img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }

.dlzoom { position: absolute; right: 12px; top: 12px; display: flex;
  flex-direction: column; gap: 6px; z-index: 5; }
.dlzoom button { width: 36px; height: 36px; font-size: 16px; line-height: 1;
  border-radius: 9px; border: 1px solid var(--edge); background: var(--paper);
  color: var(--ink); cursor: pointer; box-shadow: 0 2px 8px rgba(0, 0, 0, .3); }
.dlzoom button:hover { background: var(--paper-deep); }
.dlzoom button.on { background: var(--lantern); color: #fff; border-color: var(--lantern); }
.dlhint { position: absolute; left: 12px; bottom: 12px; z-index: 5;
  padding: 4px 10px; border-radius: 8px; font-size: 12px;
  background: rgba(0, 0, 0, .5); color: #fff6e6; }

/* A town sits in map space but is drawn at screen size. The counter-scale is
   what stops a dot becoming a saucer at 4x: the world is scaled by k, so every
   marker in it is scaled by 1/k and comes out the size it started. Without this
   the map is a field of coloured blobs the moment anybody zooms. */
.dltown { position: absolute; transform-origin: 50% 50%;
  transform: translate(-50%, -50%) scale(var(--dl-inv, 1));
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  pointer-events: none; }
.dltowndot { display: block;
  width: calc(var(--dl-base, 10px) * var(--dl-size, 1));
  height: calc(var(--dl-base, 10px) * var(--dl-size, 1)); border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff6e2, var(--lantern) 70%);
  border: 2px solid rgba(255, 245, 225, .9);
  box-shadow: 0 2px 6px rgba(0, 0, 0, .45);
  /* The dot is the only part that takes a pointer, so hovering one town cannot
     be blocked by a neighbour's invisible label box. */
  pointer-events: auto; }
.dltowndot:hover { border-color: #fff; }

/* Names are off by default and that is the whole point: three hundred labels
   drawn at once is a grey mat, which is exactly what shipped. Hover one to read
   it, or turn the whole set on from the button when the map is zoomed in far
   enough for them to fit. */
.dltownname { position: absolute; top: 100%; left: 50%; margin-top: 3px;
  transform: translateX(-50%); font-size: 11px; white-space: nowrap;
  color: #fff8ea; opacity: 0; pointer-events: none; z-index: 3;
  text-shadow: 0 1px 3px rgba(0, 0, 0, .95), 0 0 8px rgba(0, 0, 0, .85); }
.dltown:hover { z-index: 6; }
.dltown:hover .dltownname { opacity: 1; }
.dlworld.named .dltownname { opacity: 1; }
/* Dormancy is a view, never a subtraction: quiet is dim, not smaller. */
.dltown.dim { opacity: .4; }
.dltown.mine { z-index: 4; }
.dltown.mine .dltowndot { border-color: #fffaf0;
  box-shadow: 0 0 0 3px var(--lantern), 0 0 18px 6px rgba(217, 141, 58, .5); }
.dltown.mine .dltownname { opacity: 1; font-weight: 600; }

/* Flourish, earned from trial rank alone. */
.dltown.fl1 .dltowndot { box-shadow: 0 0 6px 2px rgba(255, 214, 130, .9); }
.dltown.fl2 .dltowndot { box-shadow: 0 0 8px 3px rgba(255, 184, 77, .9); }
.dltown.fl3 .dltowndot { box-shadow: 0 0 10px 3px rgba(255, 196, 61, .95);
  border-color: #ffe9a8; }
.dltown.fl4 .dltowndot { box-shadow: 0 0 12px 4px rgba(120, 190, 255, .9);
  border-color: #dcefff; }
.dltown.fl5 .dltowndot { box-shadow: 0 0 15px 5px rgba(150, 130, 255, .9);
  border-color: #ece6ff; animation: dlbreathe 3.4s ease-in-out infinite; }
.dltown.fl6 .dltowndot { box-shadow: 0 0 18px 6px rgba(255, 140, 210, .9);
  border-color: #fff; animation: dlbreathe 2.2s ease-in-out infinite; }
@keyframes dlbreathe {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.35); }
}
@media (prefers-reduced-motion: reduce) {
  .dltown.fl5 .dltowndot, .dltown.fl6 .dltowndot { animation: none; }
}

/* The toolkit: everything that can be placed, locked ones dimmed. A reward you
   cannot see is not a reward. */
.dlkit { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
.dlkititem { width: 84px; text-align: center; font-size: 11px;
  color: var(--ink-soft); }
.dlkititem img { display: block; width: 56px; height: 56px; margin: 0 auto 4px;
  object-fit: contain; border-radius: 8px; border: 1px solid var(--edge);
  background: var(--paper-deep); padding: 4px; }
.dlkititem.locked { opacity: .38; }
.dlkititem.locked img { filter: grayscale(1); }

.dlroll { margin-top: 26px; }
.dlroll table { width: 100%; border-collapse: collapse; font-size: 15px; }
.dlroll th { text-align: left; font-weight: 600; color: var(--ink-soft);
  border-bottom: 1px solid var(--edge); padding: 6px 8px; }
.dlroll td { padding: 6px 8px; border-bottom: 1px solid rgba(200, 173, 131, .35); }
.dlroll .num { text-align: right; white-space: nowrap; }
.dlrank { font-size: 13px; color: var(--ink-soft); }

@media (max-width: 620px) {
  body { padding: 14px 8px 40px; font-size: 16px; }
  .dlpaper { padding: 22px 16px 30px; border-radius: 10px; }
  /* Names would tile into an unreadable mat at this width; the lights still
     read, and your own town keeps its label. */
  .dltown .dltownname { display: none; }
  .dltown.mine .dltownname { display: block; }
}
"""


def e(value) -> str:
    return html.escape(str(value))


def member_name(guild, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    return member.display_name if member else "Somebody"


def build_towns(bot, guild):
    """Every town, ready to draw. Blocking; call it in an executor.

    One function so the public map and a player's own map can never place the
    same town in two different places.
    """
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

    partners: dict = {}
    for row in pairs:
        a, b, n = int(row.get("a", 0)), int(row.get("b", 0)), int(row.get("n", 0))
        partners.setdefault(a, {})[b] = partners.setdefault(a, {}).get(b, 0) + n
        partners.setdefault(b, {})[a] = partners.setdefault(b, {}).get(a, 0) + n
    lit = {int(row.get("user_id", 0)) for row in rows
           if str(row.get("day") or "") >= lit_since}

    return mapview.towns(
        result["order"], partners=partners,
        settled=bot.dodoland_buildings.plots(guild.id),
        flourish=flourish_rules.flourish_map(bot, guild.id),
        names={p["user_id"]: member_name(guild, p["user_id"]) for p in result["order"]},
        lit=lit,
    )


def sizes_for(bot, guild) -> dict:
    """Every knob the map's drawing depends on, in one read."""
    get = bot.dodoland_params.get
    return {
        "min_zoom": float(get(guild.id, "dodoland_map_min_zoom")),
        "max_zoom": float(get(guild.id, "dodoland_map_max_zoom")),
        "name_zoom": float(get(guild.id, "dodoland_map_name_zoom")),
        "town": int(get(guild.id, "dodoland_town_size")),
        "big_town": float(get(guild.id, "dodoland_big_town")),
        "asset": int(get(guild.id, "dodoland_asset_size")),
    }


def canvas(bot, guild, towns, *, mine: int = 0, pickable: bool = False,
           sizes: Optional[dict] = None) -> str:
    """The base image with every town on it, inside a pan-and-zoom viewport.

    The whole world is one transformed element rather than a set of separately
    positioned ones, so a town stays pinned to the coastline it was placed on at
    every zoom level, and panning is one transform rather than several hundred
    layout changes.

    Names are hidden by default and revealed as you zoom in. Three hundred
    labels drawn at once is a grey mat rather than a map, which is exactly what
    the first version produced.
    """
    image = bot.dodoland_buildings.map_image(guild.id)
    if not image:
        return ('<p class="dllede">There is no map of this land yet. Ask an admin '
                'to upload one, then come back.</p>')

    sizes = sizes or {}
    raw = image.get("data")
    blob = bytes(raw) if raw is not None else b""
    encoded = base64.b64encode(blob).decode("ascii")
    # The biggest towns keep their names at every zoom: a map with no legible
    # landmarks is hard to orient on.
    big_at = float(sizes.get("big_town", 2.2))

    markers = ""
    for town in towns:
        own = mine and town["user_id"] == int(mine)
        classes = f"dltown fl{town['flourish']}"
        if own:
            classes += " mine"
        if not town["lit"]:
            classes += " dim"
        if town["size"] >= big_at:
            classes += " big"
        label = "Your town" if own else town["name"]
        title = f"{town['name']} · {town['power']:,}"
        if town["rank_name"]:
            title += f" · {town['rank_name']}"
        markers += (
            f'<div class="{classes}" style="left:{town["x"]}%;top:{town["y"]}%;'
            f'--dl-size:{town["size"]:g}" title="{e(title)}">'
            f'<span class="dltowndot"></span>'
            f'<span class="dltownname">{e(label)}</span></div>'
        )

    pick = " pickable" if pickable else ""
    return f"""
<div class="dlstage">
  <div class="dlframe{pick}" id="dlframe"
       style="--dl-base:{int(sizes.get('town', 10))}px"
       data-scale="{float(sizes.get('scale', 1.0)):g}"
       data-min="{float(sizes.get('min_zoom', 0.5)):g}"
       data-max="{float(sizes.get('max_zoom', 8.0)):g}"
       data-namezoom="{float(sizes.get('name_zoom', 1.8)):g}">
    <div class="dlworld" id="dlworld">
      <img alt="The map of {e(guild.name)}"
           src="data:{e(image.get('content_type'))};base64,{encoded}">
      {markers}
    </div>
    <div class="dlzoom">
      <button type="button" id="dlzoomin" title="Zoom in">+</button>
      <button type="button" id="dlzoomout" title="Zoom out">&minus;</button>
      <button type="button" id="dlzoomfit" title="Fit the whole map">&#9633;</button>
      <button type="button" id="dlnames" title="Show every name">A</button>
    </div>
    <div class="dlhint" id="dlhint">Drag to move, scroll to zoom, hover a town for its name</div>
  </div>
</div>"""


def toolkit(assets: list[dict], unlocked: set, *, guild_id: int) -> str:
    """Everything that can be placed, with the locked ones dimmed.

    The whole library is shown to everybody on purpose. Knowing the gilded
    banner exists at Renowned is the reason to want Renowned; a locked thing
    nobody can see rewards nobody.
    """
    if not assets:
        return ""
    items = ""
    for row in assets:
        free = row["asset_id"] in unlocked
        need = ""
        if not free and row.get("building"):
            need = f"tier {int(row.get('min_tier', 0))} of {row['building']}"
        items += (
            f'<div class="dlkititem{"" if free else " locked"}" '
            f'title="{e(row["name"] + ((" · needs " + need) if need else ""))}">'
            f'<img alt="{e(row["name"])}" loading="lazy" '
            f'src="/guild/{int(guild_id)}/dodoland/asset/{e(row["asset_id"])}">'
            f'<div>{e(row["name"])}</div>'
            f'{f"<div>{e(need)}</div>" if need else ""}</div>'
        )
    return (f'<h2 style="margin-top:26px">The toolkit</h2>'
            f'<p class="dllede">What can stand on your patch of the world. '
            f'Dimmed things are waiting on a tier you have not reached.</p>'
            f'<div class="dlkit">{items}</div>')


VIEWPORT_SCRIPT = """
<script>
(function () {
  var frame = document.getElementById('dlframe');
  var world = document.getElementById('dlworld');
  if (!frame || !world) return;

  var minZoom = parseFloat(frame.dataset.min) || 0.5;
  var maxZoom = parseFloat(frame.dataset.max) || 8;
  var hint = document.getElementById('dlhint');
  var view = {x: 0, y: 0, k: 1};
  var natural = {w: 0, h: 0};

  function apply() {
    world.style.transform =
      'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.k + ')';
    // Towns live in map space but must be drawn at screen size, so each one is
    // scaled back by 1/k. Without this a dot becomes a saucer at 4x and the map
    // turns into a field of blobs.
    world.style.setProperty('--dl-inv', (1 / view.k).toFixed(4));
  }
  function clamp() {
    // Never let the world be dragged entirely off the frame: there is no way
    // back from a blank screen except reloading.
    var w = natural.w * view.k, h = natural.h * view.k;
    var fw = frame.clientWidth, fh = frame.clientHeight;
    var slack = 80;
    view.x = Math.min(fw - slack, Math.max(slack - w, view.x));
    view.y = Math.min(fh - slack, Math.max(slack - h, view.y));
  }
  function fit() {
    if (!natural.w) return;
    view.k = Math.max(minZoom, Math.min(maxZoom,
      frame.clientWidth / natural.w));
    view.x = (frame.clientWidth - natural.w * view.k) / 2;
    view.y = (frame.clientHeight - natural.h * view.k) / 2;
    apply();
  }
  function zoomAt(factor, cx, cy) {
    var next = Math.min(maxZoom, Math.max(minZoom, view.k * factor));
    if (next === view.k) return;
    // Keep whatever is under the cursor under the cursor.
    view.x = cx - (cx - view.x) * (next / view.k);
    view.y = cy - (cy - view.y) * (next / view.k);
    view.k = next;
    clamp();
    apply();
  }

  var img = world.querySelector('img');
  function measure() {
    natural.w = img.naturalWidth || frame.clientWidth;
    natural.h = img.naturalHeight || Math.round(frame.clientHeight);
    world.style.width = natural.w + 'px';
    fit();
  }
  if (img.complete && img.naturalWidth) measure();
  else img.addEventListener('load', measure);
  window.addEventListener('resize', function () { clamp(); apply(); });

  frame.addEventListener('wheel', function (event) {
    event.preventDefault();
    var box = frame.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15,
           event.clientX - box.left, event.clientY - box.top);
  }, {passive: false});

  var dragging = false, moved = 0, last = null;
  frame.addEventListener('pointerdown', function (event) {
    dragging = true; moved = 0; last = {x: event.clientX, y: event.clientY};
    frame.classList.add('dragging');
    frame.setPointerCapture(event.pointerId);
  });
  frame.addEventListener('pointermove', function (event) {
    if (!dragging) return;
    var dx = event.clientX - last.x, dy = event.clientY - last.y;
    moved += Math.abs(dx) + Math.abs(dy);
    view.x += dx; view.y += dy;
    last = {x: event.clientX, y: event.clientY};
    clamp(); apply();
  });
  function endDrag() { dragging = false; frame.classList.remove('dragging'); }
  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);

  document.getElementById('dlzoomin').addEventListener('click', function () {
    zoomAt(1.4, frame.clientWidth / 2, frame.clientHeight / 2);
  });
  document.getElementById('dlzoomout').addEventListener('click', function () {
    zoomAt(1 / 1.4, frame.clientWidth / 2, frame.clientHeight / 2);
  });
  document.getElementById('dlzoomfit').addEventListener('click', fit);

  // Names are off until asked for. Hovering a town always shows its own.
  var namesBtn = document.getElementById('dlnames');
  if (namesBtn) namesBtn.addEventListener('click', function () {
    var on = world.classList.toggle('named');
    namesBtn.classList.toggle('on', on);
    hint.textContent = on
      ? 'Every name shown. Zoom in if they overlap.'
      : 'Drag to move, scroll to zoom, hover a town for its name';
  });

  // Exposed so the settle page can turn a click into map coordinates without
  // duplicating any of this.
  window.dlMapPoint = function (event) {
    var box = frame.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left - view.x) / (natural.w * view.k)) * 100,
      y: ((event.clientY - box.top - view.y) / (natural.h * view.k)) * 100,
      dragged: moved > 6
    };
  };
})();
</script>"""


def roll(towns, limit: int = 500) -> str:
    """Every town as a list, with where it stands and where it sits.

    A map alone cannot be scanned, searched or copied from, and on a phone the
    names are hidden entirely. This is the same information in the order that
    matters, with the coordinates so a position can be read off rather than
    guessed at.
    """
    rows = ""
    ordered = sorted(towns, key=lambda t: (-t["power"], t["name"]))
    for index, town in enumerate(ordered[:limit], start=1):
        built = ", ".join(str(v) for v in town["tiers"].values()) or "nothing yet"
        rank = (f'<div class="dlrank">{e(town["flourish_label"])}'
                + (f' · {e(town["rank_name"])}' if town["rank_name"] else "")
                + "</div>") if town["flourish"] else ""
        where = ("chosen" if town["settled"] else "suggested")
        rows += (f"<tr><td class='num'>{index}</td>"
                 f"<td><b>{e(town['name'])}</b>{rank}</td>"
                 f"<td>{e(built)}</td>"
                 f"<td class='num'>{town['power']:,}</td>"
                 f"<td class='num'>{town['x']:.1f}, {town['y']:.1f}</td>"
                 f"<td>{where}</td></tr>")
    if not rows:
        return ""
    more = (f'<p class="dllede">Showing {limit:,} of {len(towns):,}.</p>'
            if len(towns) > limit else "")
    return (
        f'<div class="dlroll"><h2>Every town</h2>{more}<table><thead><tr><th></th>'
        '<th>Town</th><th>What stands there</th><th class="num">Standing</th>'
        '<th class="num">Position</th><th>Placed</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def page(title: str, guild, body: str, *, script: str = "") -> str:
    """The shared page shell."""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="referrer" content="no-referrer">
<title>{e(title)}</title>
<style>{COZY_CSS}</style>
</head><body>
<main class="dlpaper">
  <p class="dleyebrow">{e(guild.name)}</p>
  {body}
</main>
{script}
</body></html>"""
