"""
The lights editor: see and set one tile's lights by hand.

Opened from a tile's card in the tile library ("💡 Edit lights", the bot
owner's page), as a dialog over it. The tile's picture is shown large, at night
(or dusk, or dawn), lit the way the map lights it. Two kinds of light are on it:

* **found by itself** - what the map finds in the picture by colour and shape
  (lit windows, lanterns, fires: ``nightlights.findLights``, the very code the
  map runs), drawn as dashed rings. "Make them mine" turns them into lights of
  your own; the switch beside it stops the map finding any in this tile;
* **your own** - double-click the picture to add one, drag it to move it, click
  it to set its colour, its radius (in map cells, so the preview is the map's
  scale) and its intensity; Delete removes it. A light glows where it is put.

Town buildings (one tile per building and tier) are what drawn towns are made
of, so lights put on a tier light that building in every drawn town that has it
at that tier; a tier with an uploaded painting has the painting's lights
separately (the Uploaded / Drawn switch; the uploaded one opens first).

The dialog asks ``GET /api/dodoland/lights/{tile_id}`` (:func:`api_tile_lights`)
for the tile, and saves as it changes through the tile library's own endpoint
(``update_tile`` with ``lights`` / ``uploaded_lights`` / ``auto_lights``); the
map draws them at night (``web/dodoland/mappage.py``, ``drawNight``).
"""

from __future__ import annotations

from aiohttp import web

from web.dodoland import nightlights


def _guild_for(bot):
    """A server whose map scale the previews use: the first with towns."""
    for guild in bot.guilds:
        try:
            if bot.dodoland_buildings.plots(guild.id):
                return guild
        except Exception:  # noqa: BLE001
            continue
    return bot.guilds[0] if bot.guilds else None


def tile_data(bot, tile_id: str):
    """One tile, with what the editor needs to draw, scale and light it; None
    if there is no such tile."""
    from helpers.dodoland import townart
    from web.dodoland import mappage

    library = bot.dodoland_tiles
    t = library.get(tile_id)
    if not t or not t.get("variants"):
        return None
    guild = _guild_for(bot)
    params = bot.dodoland_params
    gid = guild.id if guild else 0
    try:
        shrink = max(0.1, float(params.get(gid, "dodoland_tile_scale")))
        hall_box = float(params.get(gid, "dodoland_hall_cells")) * townart.WIDTH / townart.HALL_SPAN
        landmarks = (str(params.get(gid, "dodoland_town_hall")), str(params.get(gid, "dodoland_zoo_building")))
        bscale = max(0.1, float(params.get(gid, "dodoland_building_scale")))
        night, sun = mappage._night_settings(bot, gid), mappage._sun_settings(bot, gid)
    except Exception:  # noqa: BLE001
        shrink, hall_box, landmarks, bscale, night, sun = 1.0, 35.0, (), 0.5, {}, {}
    v = t["variants"][0]
    dims = library.art_sizes([v] + ([t["uploaded"]] if t.get("uploaded") else []))
    w, h = dims.get(v, (0, 0))
    row = {"id": t["tile_id"], "name": t["name"], "v": v, "w": w, "h": h,
           "wc": mappage._tile_cells(t, w, shrink, hall_box, landmarks, bscale) if w else 1,
           "town": str(t.get("source") or "").startswith("building:"),
           "lights": t["lights"], "auto": t["auto_lights"]}
    if t.get("uploaded"):
        uw, uh = dims.get(t["uploaded"], (0, 0))
        painted = mappage.uploaded_sizes(bot, guild, [t], hall_box, landmarks, bscale) if guild else {}
        row.update({"up": t["uploaded"], "uw": uw, "uh": uh,
                    "uwc": (painted.get(t["tile_id"]) or (None, row["wc"]))[1],
                    "ulights": t["uploaded_lights"]})
    mode = str(params.get(gid, "dodoland_building_art") or "generated") if guild else "generated"
    return {"tile": row, "painted_first": mode == "uploaded", "night": night, "sun": sun}


async def api_tile_lights(request: web.Request):
    """The tile the dialog edits. Gated with require_owner in the route table."""
    import asyncio

    data = await asyncio.get_running_loop().run_in_executor(
        None, tile_data, request.app["bot"], request.match_info["tile_id"])
    if data is None:
        return web.json_response({"ok": False, "error": "No such tile."}, status=404)
    return web.json_response({"ok": True, **data})


def dialog_html() -> str:
    """The editor dialog, for the owner's tile library page: markup, its
    style, and its script, which opens it from any ``.tllights`` button."""
    return f"""
<dialog id="lxdlg" class="lxdlg">
  <div class="lxbar">
    <b id="lxname">Lights</b>
    <span class="lxseg" id="lxpics" hidden><button type="button" data-pic="up">Uploaded</button><button type="button" data-pic="v">Drawn</button></span>
    <span class="lxseg" id="lxtime"><button type="button" data-t="night" class="on">Night</button><button type="button" data-t="dusk">Dusk</button><button type="button" data-t="dawn">Dawn</button><button type="button" data-t="day">Day</button></span>
    <button type="button" id="lxclose" class="lxclose" title="Close">✕</button>
  </div>
  <p class="muted lxsmall"><b>Double-click</b> the picture to add a light, <b>drag</b> one to move it, <b>click</b> one
  to change it. Dashed rings are the lights the map finds in the picture by itself. Radius is in map cells, so the
  preview is the map's own scale. Saved as you go.</p>
  <div class="lxstage" id="lxstage"><div class="lxhint">Loading…</div></div>
  <div class="lxside">
    <div class="lxfound" id="lxfound" hidden>
      <span id="lxfoundn"></span>
      <label class="lxsmall"><input type="checkbox" id="lxauto"> Light them on the map</label>
      <button type="button" id="lxadopt">Make them mine</button>
    </div>
    <div id="lxlights" class="lxlights"></div>
    <div id="lxedit" class="lxedit" hidden>
      <label>Colour <input type="color" id="lxcol"></label>
      <label>Radius <input type="range" id="lxrad" min="0.5" max="20" step="0.5"> <output id="lxradn"></output> cells</label>
      <label>Intensity <input type="range" id="lxint" min="0" max="2" step="0.05"> <output id="lxintn"></output></label>
      <button type="button" id="lxdel" class="danger">Remove this light</button>
    </div>
    <p id="lxmsg" class="muted lxsmall"></p>
  </div>
</dialog>
<style>{_CSS}</style>
<script>(function () {{{nightlights.SCRIPT}{_SCRIPT}}})();</script>"""


def light_summary(tile: dict) -> str:
    """What a tile card says about its lights, beside its Edit lights button."""
    own = len(tile.get("lights") or []) + len(tile.get("uploaded_lights") or [])
    parts = [f"{own} of my own" if own else "none of my own"]
    parts.append("finds its own" if tile.get("auto_lights", True) else "finds none")
    return ", ".join(parts)


# In the panel's own colours (panel.css: --panel, --text, --line, --muted).
_CSS = """
.lxdlg { width: min(980px, calc(100vw - 32px)); max-height: calc(100vh - 32px); border: 1px solid var(--line, #ddd);
  border-radius: 14px; background: var(--panel, #fff); color: var(--text, #222); padding: 14px 16px; }
.lxdlg::backdrop { background: rgba(0, 0, 0, .45); }
.lxbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.lxclose { margin-left: auto; background: none; border: 1px solid var(--line, #ddd); border-radius: 8px;
  color: var(--text, #222); cursor: pointer; padding: 4px 10px; font: inherit; }
.lxseg { display: inline-flex; border: 1px solid var(--line, #ddd); border-radius: 8px; overflow: hidden; }
.lxseg button { background: none; border: 0; color: var(--text, #222); padding: 5px 10px; cursor: pointer; font: inherit; }
.lxseg button.on { background: #f0a64f; color: #1b130a; }
.lxstage { position: relative; height: min(460px, 55vh); border-radius: 12px; overflow: hidden; background: #6f8a4f;
  display: flex; align-items: center; justify-content: center; user-select: none; }
.lxbox { position: relative; }
.lxbox img { display: block; width: 100%; height: 100%; image-rendering: pixelated; pointer-events: none; }
.lxhint { color: #fff8; }
.lxdot { position: absolute; width: 16px; height: 16px; margin: -8px 0 0 -8px; border-radius: 50%;
  border: 2px solid #fff; box-shadow: 0 0 0 1px #0008; cursor: grab; touch-action: none; z-index: 3; }
.lxdot.on { outline: 2px solid #f0a64f; outline-offset: 2px; }
.lxdot.dragging { cursor: grabbing; }
.lxghost { position: absolute; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
  border: 2px dashed #ffe1a8; cursor: pointer; z-index: 2; box-sizing: border-box; }
.lxghost.off { opacity: .45; }
.lxring { position: absolute; border: 1px dashed #fff8; border-radius: 50%; pointer-events: none; z-index: 1; }
.lxside { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.lxfound { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 6px 10px;
  border: 1px dashed var(--line, #ddd); border-radius: 8px; font-size: 13px; }
.lxlights { display: flex; gap: 6px; flex-wrap: wrap; }
.lxchip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 999px;
  border: 1px solid var(--line, #ddd); cursor: pointer; font-size: 12px; background: var(--panel, #fff); color: var(--text, #222); }
.lxchip.on { border-color: #f0a64f; }
.lxchip i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.lxedit { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.lxedit label { display: inline-flex; align-items: center; gap: 6px; }
.lxsmall { font-size: 12px; }
.lxseg[hidden], .lxedit[hidden], .lxfound[hidden] { display: none; }
"""

_SCRIPT = r"""
  var dlg = document.getElementById('lxdlg');
  if (!dlg) return;
  var N = {}, S = {}, paintedFirst = false;
  var cur = null, card = null, pic = 'v', sel = -1, time = 'night', saveT = null;
  var stage = document.getElementById('lxstage'), msg = document.getElementById('lxmsg');
  function art(v) { return '/dodoland/tiles/art/' + v; }
  function lightsOf(t) { return (pic === 'up' ? t.ulights : t.lights) || []; }
  function mine() { return pic === 'up' ? (cur.ulights = cur.ulights || []) : (cur.lights = cur.lights || []); }

  // Opened from a tile card's Edit lights button.
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('.tllights');
    if (!b) return;
    ev.preventDefault();
    open(b.dataset.tile, b.closest('.tltile'));
  });
  function open(id, from) {
    card = from; cur = null; sel = -1; msg.textContent = '';
    stage.innerHTML = '<div class="lxhint">Loading…</div>';
    document.getElementById('lxname').textContent = 'Lights';
    if (!dlg.open) dlg.showModal();
    fetch('/api/dodoland/lights/' + encodeURIComponent(id))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) { stage.innerHTML = '<div class="lxhint">' + (res.error || 'Not found.') + '</div>'; return; }
        N = res.night || {}; S = res.sun || {}; paintedFirst = res.painted_first;
        cur = res.tile;
        pic = cur.up ? 'up' : 'v';
        document.getElementById('lxname').textContent = '💡 ' + cur.name;
        document.getElementById('lxpics').hidden = !cur.up;
        document.getElementById('lxauto').checked = cur.auto !== false;
        renderStage();
      })
      .catch(function (err) { stage.innerHTML = '<div class="lxhint">' + String(err) + '</div>'; });
  }
  document.getElementById('lxclose').onclick = function () { dlg.close(); };
  dlg.addEventListener('close', function () {
    // The card says what it has now.
    if (cur && card) {
      var s = card.querySelector('.tllightsum');
      var own = (cur.lights || []).length + (cur.ulights || []).length;
      if (s) s.textContent = (own ? own + ' of my own' : 'none of my own') + ', ' + (cur.auto !== false ? 'finds its own' : 'finds none');
    }
  });
  document.querySelectorAll('#lxpics button').forEach(function (b) {
    b.onclick = function () { pic = b.dataset.pic; sel = -1; renderStage(); };
  });
  document.querySelectorAll('#lxtime button').forEach(function (b) {
    b.onclick = function () { time = b.dataset.t; renderStage(); };
  });
  document.getElementById('lxauto').onchange = function (ev) {
    if (!cur) return;
    cur.auto = ev.target.checked; drawGhosts(); drawGlow(); save();
  };

  // --- what the map finds in a picture by itself -------------------------- //
  var found = {};
  function foundIn(src, done) {
    if (found[src] !== undefined) { done(found[src]); return; }
    var im = new Image();
    im.onload = function () {
      try { found[src] = findLights(im, N); } catch (e) { found[src] = null; }
      done(found[src]);
    };
    im.onerror = function () { found[src] = null; done(null); };
    im.src = src;
  }
  // Turn what was found into lights of your own (and stop finding them), so
  // each can be moved, recoloured or removed.
  function adopt(pickIndex) {
    var f = cur && found[picSrc()];
    if (!f) return;
    var list = mine(), spill = N.spill == null ? 6 : N.spill, wc = picCells(), first = list.length;
    f.spots.forEach(function (sp) {
      if (list.length >= 16) return;
      list.push({x: +sp.cx.toFixed(4), y: +sp.cy.toFixed(4), colour: '#ffbe64',
                 radius: Math.max(0.5, Math.round(sp.r * spill * wc * 2) / 2), intensity: 1});
    });
    cur.auto = false;
    document.getElementById('lxauto').checked = false;
    sel = pickIndex == null ? -1 : first + pickIndex;
    renderStage(); save();
    msg.textContent = 'They are yours now: move, recolour or remove each one.';
  }
  document.getElementById('lxadopt').onclick = function () { adopt(); };

  // --- the stage: the picture, its sky, and its lights ---------------------- //
  var box = null, cv = null, dims = null;
  function picSrc() { return art(pic === 'up' ? cur.up : cur.v); }
  function picCells() { return (pic === 'up' ? cur.uwc : cur.wc) || 1; }
  function fit() {
    var w = pic === 'up' ? cur.uw : cur.w, h = pic === 'up' ? cur.uh : cur.h;
    // Big enough to work on, with room round it for the light to spread.
    var maxW = Math.min(stage.clientWidth - 80, 620), maxH = stage.clientHeight - 60;
    var k = Math.min(maxW / Math.max(1, w), maxH / Math.max(1, h), 12);
    var dw = Math.max(1, Math.round(w * k));
    return {w: dw, h: Math.max(1, Math.round(h * k)), cell: dw / picCells()};
  }
  function sky() {
    var rise = S.rise == null ? 6 : S.rise, set = S.set == null ? 20 : S.set;
    return skyAt(S, N, {night: 23, dusk: set + 0.15, dawn: rise, day: 13}[time]);
  }
  function renderStage() {
    document.querySelectorAll('#lxpics button').forEach(function (b) { b.classList.toggle('on', b.dataset.pic === pic); });
    document.querySelectorAll('#lxtime button').forEach(function (b) { b.classList.toggle('on', b.dataset.t === time); });
    if (!cur) return;
    dims = fit();
    stage.innerHTML = '<div class="lxbox" style="width:' + dims.w + 'px;height:' + dims.h + 'px">' +
      '<img alt="" src="' + picSrc() + '"></div><canvas></canvas>';
    box = stage.querySelector('.lxbox');
    cv = stage.querySelector('canvas');
    cv.width = stage.clientWidth; cv.height = stage.clientHeight;
    cv.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none';
    var src = picSrc();
    foundIn(src, function () { if (cur && picSrc() === src) { drawGhosts(); drawGlow(); } });
    drawDots(); drawGhosts(); drawGlow(); renderChips();
  }
  function origin() {
    var b = box.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return {x: b.left - s.left, y: b.top - s.top};
  }
  var stamps = {};
  function stamp(c) {
    var key = c.join(',');
    if (stamps[key]) return stamps[key];
    var s = document.createElement('canvas'); s.width = s.height = 256;
    var x = s.getContext('2d'), g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
    g.addColorStop(0, 'rgba(' + key + ',1)'); g.addColorStop(0.35, 'rgba(' + key + ',.7)');
    g.addColorStop(0.7, 'rgba(' + key + ',.22)'); g.addColorStop(1, 'rgba(' + key + ',0)');
    x.fillStyle = g; x.fillRect(0, 0, 256, 256);
    return (stamps[key] = s);
  }
  // The same night the map draws: the sky over everything, light cut out
  // round each light, and a warm glow over what it lights; with what the map
  // finds by itself, if it may.
  function drawGlow() {
    var c = cv.getContext('2d');
    c.clearRect(0, 0, cv.width, cv.height);
    var st = sky();
    if (Math.max(st.at(0).a, st.at(1).a) < 0.01) return;
    var g = c.createLinearGradient(st.sunLeft ? 0 : cv.width, 0, st.sunLeft ? cv.width : 0, 0);
    for (var i = 0; i <= 4; i++) { var a = st.at(i / 4); g.addColorStop(i / 4, 'rgba(' + a.rgb.join(',') + ',' + a.a.toFixed(3) + ')'); }
    c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
    c.fillStyle = g; c.fillRect(0, 0, cv.width, cv.height);
    var o = origin(), lights = [];
    lightsOf(cur).forEach(function (L) {
      var x = o.x + L.x * dims.w, y = o.y + L.y * dims.h, r = L.radius * dims.cell;
      lights.push({x: x, y: y + r * 0.15, top: y, r: r, k: L.intensity, rgb: hexRgb(L.colour)});
    });
    var f = cur.auto !== false && found[picSrc()], spill = N.spill == null ? 6 : N.spill;
    if (f) f.spots.forEach(function (sp) {
      var r = Math.max(1, sp.r * dims.w * spill), x = o.x + sp.cx * dims.w, y = o.y + sp.cy * dims.h;
      lights.push({x: x, y: y + r * 0.25, top: y, r: r, k: 1, rgb: [255, 190, 100]});
    });
    var white = stamp([255, 255, 255]);
    c.globalCompositeOperation = 'destination-out';
    lights.forEach(function (l) {
      c.globalAlpha = Math.min(1, 0.85 * l.k); c.drawImage(white, l.x - l.r, l.y - l.r * 0.7, l.r * 2, l.r * 1.4);
      c.globalAlpha = Math.min(1, l.k); c.drawImage(white, l.x - l.r * 0.22, l.top - l.r * 0.22, l.r * 0.44, l.r * 0.44);
    });
    if (f) {
      c.globalAlpha = 1; c.drawImage(f.mask, o.x, o.y, dims.w, dims.h);
      c.globalAlpha = 0.7; c.drawImage(f.halo, o.x, o.y, dims.w, dims.h);
    }
    c.globalCompositeOperation = 'source-over';
    var glow = (N.light_glow == null ? 0.35 : N.light_glow) * st.k;
    lights.forEach(function (l) {
      var s = stamp(l.rgb);
      c.globalAlpha = Math.min(1, glow * l.k); c.drawImage(s, l.x - l.r, l.y - l.r * 0.7, l.r * 2, l.r * 1.4);
      c.globalAlpha = Math.min(1, glow * 2 * l.k); c.drawImage(s, l.x - l.r * 0.18, l.top - l.r * 0.18, l.r * 0.36, l.r * 0.36);
    });
    if (f) {
      var wg = (N.window_glow == null ? 0.8 : N.window_glow) * st.k;
      c.globalAlpha = wg * 0.55; c.drawImage(f.halo, o.x, o.y, dims.w, dims.h);
      c.globalAlpha = wg * 0.18;
      c.drawImage(stamp([255, 190, 90]), o.x + dims.w * 0.1, o.y + dims.h * 0.55, dims.w * 0.8, dims.h * 0.5);
    }
    c.globalAlpha = 1;
  }
  // The lights found by itself, as dashed rings: clicking one makes them all
  // your own, with that one chosen.
  function drawGhosts() {
    stage.querySelectorAll('.lxghost').forEach(function (n) { n.remove(); });
    var f = cur && found[picSrc()], panel = document.getElementById('lxfound');
    panel.hidden = !f;
    if (!f) return;
    document.getElementById('lxfoundn').textContent = 'Found by itself: ' + f.spots.length +
      (f.spots.length === 1 ? ' light' : ' lights') + (cur.auto === false ? ' (off)' : '');
    var o = origin();
    f.spots.forEach(function (sp, i) {
      var d = document.createElement('div');
      d.className = 'lxghost' + (cur.auto === false ? ' off' : '');
      d.style.left = (o.x + sp.cx * dims.w) + 'px'; d.style.top = (o.y + sp.cy * dims.h) + 'px';
      d.title = 'Found by itself. Click to make the found lights your own.';
      d.addEventListener('pointerdown', function (ev) { ev.stopPropagation(); });
      d.addEventListener('click', function (ev) { ev.stopPropagation(); adopt(i); });
      stage.appendChild(d);
    });
  }
  function placeDot(d, L) {
    var o = origin();
    d.style.left = (o.x + L.x * dims.w) + 'px'; d.style.top = (o.y + L.y * dims.h) + 'px';
  }
  function placeRing() {
    var ring = stage.querySelector('.lxring'), L = cur && lightsOf(cur)[sel];
    if (!L) { if (ring) ring.remove(); return; }
    if (!ring) { ring = document.createElement('div'); ring.className = 'lxring'; stage.appendChild(ring); }
    var o = origin(), r = L.radius * dims.cell;
    ring.style.left = (o.x + L.x * dims.w - r) + 'px'; ring.style.top = (o.y + L.y * dims.h - r) + 'px';
    ring.style.width = ring.style.height = (r * 2) + 'px';
  }
  function drawDots() {
    stage.querySelectorAll('.lxdot').forEach(function (n) { n.remove(); });
    lightsOf(cur).forEach(function (L, i) {
      var d = document.createElement('div');
      d.className = 'lxdot' + (i === sel ? ' on' : '');
      d.dataset.i = i;
      d.style.background = L.colour;
      d.title = 'Drag to move, click to edit';
      placeDot(d, L);
      stage.appendChild(d);
      // The dot that was pressed is the one that moves: nothing is redrawn
      // under the pointer until it lets go.
      d.addEventListener('pointerdown', function (ev) {
        ev.preventDefault(); ev.stopPropagation();
        select(i, true);
        try { d.setPointerCapture(ev.pointerId); } catch (e) {}
        d.classList.add('dragging');
        var moved = false;
        function move(m) {
          var b = box.getBoundingClientRect();
          L.x = +Math.max(0, Math.min(1, (m.clientX - b.left) / b.width)).toFixed(4);
          L.y = +Math.max(0, Math.min(1, (m.clientY - b.top) / b.height)).toFixed(4);
          moved = true;
          placeDot(d, L); placeRing(); drawGlow();
        }
        function up() {
          d.removeEventListener('pointermove', move); d.removeEventListener('pointerup', up);
          d.removeEventListener('pointercancel', up);
          d.classList.remove('dragging');
          if (moved) save();
        }
        d.addEventListener('pointermove', move); d.addEventListener('pointerup', up);
        d.addEventListener('pointercancel', up);
      });
    });
    placeRing();
  }
  stage.addEventListener('dblclick', function (ev) {
    if (!cur || !box || ev.target.closest('.lxdot, .lxghost')) return;
    var b = box.getBoundingClientRect(), list = mine();
    if (list.length >= 16) { msg.textContent = 'A picture holds at most 16 lights.'; return; }
    var last = list[list.length - 1];
    list.push({x: +Math.max(0, Math.min(1, (ev.clientX - b.left) / b.width)).toFixed(4),
               y: +Math.max(0, Math.min(1, (ev.clientY - b.top) / b.height)).toFixed(4),
               colour: last ? last.colour : '#ffc46b', radius: last ? last.radius : 3, intensity: last ? last.intensity : 1});
    select(list.length - 1);
    save();
  });
  // Choosing a light; keepDots when its dot is under the pointer right now.
  function select(i, keepDots) {
    sel = i;
    var L = lightsOf(cur)[i];
    if (L) {
      document.getElementById('lxcol').value = L.colour;
      document.getElementById('lxrad').value = L.radius; document.getElementById('lxradn').textContent = L.radius;
      document.getElementById('lxint').value = L.intensity; document.getElementById('lxintn').textContent = L.intensity;
    }
    if (keepDots) {
      stage.querySelectorAll('.lxdot').forEach(function (n) { n.classList.toggle('on', +n.dataset.i === i); });
      placeRing();
    } else drawDots();
    drawGlow(); renderChips();
  }
  function renderChips() {
    var host = document.getElementById('lxlights'), list = lightsOf(cur);
    host.innerHTML = list.map(function (L, i) {
      return '<button type="button" class="lxchip' + (i === sel ? ' on' : '') + '" data-i="' + i + '"><i style="background:' +
        L.colour + '"></i>Light ' + (i + 1) + ' · ' + L.radius + ' cells</button>';
    }).join('') || '<span class="muted lxsmall">No lights of your own yet. Double-click the picture to add one.</span>';
    host.querySelectorAll('.lxchip').forEach(function (b) { b.onclick = function () { select(+b.dataset.i); }; });
    document.getElementById('lxedit').hidden = !(sel >= 0 && list[sel]);
  }
  function edited(field, value) {
    var L = lightsOf(cur)[sel];
    if (!L) return;
    L[field] = value;
    document.getElementById('lxradn').textContent = L.radius;
    document.getElementById('lxintn').textContent = L.intensity;
    var d = stage.querySelector('.lxdot[data-i="' + sel + '"]');
    if (d) d.style.background = L.colour;
    placeRing(); drawGlow(); renderChips();
    save();
  }
  document.getElementById('lxcol').oninput = function (ev) { edited('colour', ev.target.value); };
  document.getElementById('lxrad').oninput = function (ev) { edited('radius', parseFloat(ev.target.value)); };
  document.getElementById('lxint').oninput = function (ev) { edited('intensity', parseFloat(ev.target.value)); };
  function removeSelected() {
    var list = lightsOf(cur);
    if (sel < 0 || !list[sel]) return;
    list.splice(sel, 1); sel = -1;
    drawDots(); drawGlow(); renderChips(); save();
  }
  document.getElementById('lxdel').onclick = removeSelected;
  dlg.addEventListener('keydown', function (ev) {
    var tag = document.activeElement && document.activeElement.tagName;
    if ((ev.key === 'Delete' || ev.key === 'Backspace') && cur && sel >= 0 && tag !== 'INPUT' && tag !== 'SELECT') removeSelected();
  });
  window.addEventListener('resize', function () { if (cur && dlg.open) renderStage(); });

  // Saved a moment after the last change, through the tile library.
  function save() {
    clearTimeout(saveT);
    msg.textContent = 'Saving…';
    var t = cur, which = pic;
    saveT = setTimeout(function () {
      var fields = {auto_lights: t.auto !== false};
      fields[which === 'up' ? 'uploaded_lights' : 'lights'] = which === 'up' ? (t.ulights || []) : (t.lights || []);
      fetch('/api/dodoland/tiles', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'update_tile', tile_id: t.id, fields: fields})})
        .then(function (r) { return r.json(); })
        .then(function (res) {
          msg.textContent = res.ok ? 'Saved. The map shows it after a reload.' : (res.error || 'That did not save.');
        })
        .catch(function (err) { msg.textContent = String(err); });
    }, 450);
  }
"""
