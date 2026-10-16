"""
The lights editor: put lights on a tile's picture, by hand.

``/dodoland/lights`` (the bot owner's, like the tile library it belongs to).
Pick a tile; its picture is shown large, at night, with its lights on it.
Double-click the picture to add a light, drag a light to move it, click one to
choose it and set its colour, its radius (in map cells, so the preview is the
map's own scale) and its intensity. A building tier with an uploaded painting
has its lights set on each picture separately (the drawn one and the painted
one), since their windows are in different places. A switch turns off finding
lit windows automatically for that tile, for when its lights are all placed by
hand.

Everything saves as it changes, through the tile library's own endpoint
(``update_tile`` with ``lights`` / ``uploaded_lights`` / ``auto_lights``); the
map draws them at night (``web/dodoland/mappage.py``, ``drawNight``).
"""

from __future__ import annotations

import json

from aiohttp import web


def _guild_for(bot):
    """A server whose map scale the previews use: the first with towns."""
    for guild in bot.guilds:
        try:
            if bot.dodoland_buildings.plots(guild.id):
                return guild
        except Exception:  # noqa: BLE001
            continue
    return bot.guilds[0] if bot.guilds else None


def editor_data(bot) -> dict:
    """Every placed tile, with what the editor needs to draw and scale it."""
    from helpers.dodoland import townart
    from web.dodoland import mappage

    library = bot.dodoland_tiles
    guild = _guild_for(bot)
    # The global tiles and that server's own (its building tiers among them).
    tiles = [t for t in library.tiles(guild.id if guild else None)
             if t["placement"] == "place" and t["variants"]]
    cats = {c["cat_id"]: c["name"] for c in library.categories()}
    params = bot.dodoland_params
    gid = guild.id if guild else 0
    try:
        shrink = max(0.1, float(params.get(gid, "dodoland_tile_scale")))
        hall_box = float(params.get(gid, "dodoland_hall_cells")) * townart.WIDTH / townart.HALL_SPAN
        landmarks = (str(params.get(gid, "dodoland_town_hall")), str(params.get(gid, "dodoland_zoo_building")))
        bscale = max(0.1, float(params.get(gid, "dodoland_building_scale")))
    except Exception:  # noqa: BLE001
        shrink, hall_box, landmarks, bscale = 1.0, 35.0, (), 0.5
    dims = library.art_sizes([t["variants"][0] for t in tiles] + [t["uploaded"] for t in tiles if t.get("uploaded")])
    painted = mappage.uploaded_sizes(bot, guild, tiles, hall_box, landmarks, bscale) if guild else {}
    out = []
    for t in tiles:
        v = t["variants"][0]
        w, h = dims.get(v, (0, 0))
        row = {"id": t["tile_id"], "name": t["name"], "cat": cats.get(t["cat_id"], ""),
               "v": v, "w": w, "h": h,
               "wc": mappage._tile_cells(t, w, shrink, hall_box, landmarks, bscale) if w else 1,
               "lights": t["lights"], "auto": t["auto_lights"]}
        if t.get("uploaded"):
            uw, uh = dims.get(t["uploaded"], (0, 0))
            row.update({"up": t["uploaded"], "uw": uw, "uh": uh,
                        "uwc": (painted.get(t["tile_id"]) or (None, row["wc"]))[1],
                        "ulights": t["uploaded_lights"]})
        out.append(row)
    mode = str(params.get(gid, "dodoland_building_art") or "generated") if guild else "generated"
    return {"tiles": out, "painted_first": mode == "uploaded"}


async def lights_page(request: web.Request):
    """The owner's lights editor. Gated with require_owner in the route table."""
    import asyncio

    from web.routes import _page

    data = await asyncio.get_running_loop().run_in_executor(None, editor_data, request.app["bot"])
    return _page("Lights editor", lights_html(data, request.query.get("tile") or ""))


def lights_html(data: dict, pick: str = "") -> str:
    """The editor's body, for :func:`editor_data`'s tiles; ``pick`` is chosen first."""
    return f"""
<h1>💡 Lights editor</h1>
<p class="muted">Pick a tile. <b>Double-click</b> its picture to add a light, <b>drag</b> a light to move it,
<b>click</b> one to change its colour, radius and intensity. Radius is in map cells, so the preview is the
map's own scale. Saved as you go. <a href="/dodoland/tiles">← Tile library</a></p>
<div class="lxwrap">
  <aside class="lxlist">
    <input id="lxq" class="lxin" placeholder="Search tiles…">
    <select id="lxcat" class="lxin"></select>
    <label class="lxsmall"><input type="checkbox" id="lxonly"> Only tiles with lights</label>
    <div id="lxgrid" class="lxgrid"></div>
  </aside>
  <section class="lxmain">
    <div class="lxbar">
      <b id="lxname">Pick a tile</b>
      <span class="lxseg" id="lxpics" hidden><button data-pic="v">Drawn</button><button data-pic="up">Painted</button></span>
      <span class="lxseg" id="lxtime"><button data-t="night" class="on">Night</button><button data-t="day">Day</button></span>
    </div>
    <div class="lxstage" id="lxstage"><div class="lxhint">No tile chosen.</div></div>
    <div class="lxside">
      <label class="lxsmall"><input type="checkbox" id="lxauto"> Also find lit windows in it automatically</label>
      <div id="lxlights" class="lxlights"></div>
      <div id="lxedit" class="lxedit" hidden>
        <label>Colour <input type="color" id="lxcol"></label>
        <label>Radius <input type="range" id="lxrad" min="0.5" max="20" step="0.5"> <output id="lxradn"></output> cells</label>
        <label>Intensity <input type="range" id="lxint" min="0" max="2" step="0.05"> <output id="lxintn"></output></label>
        <button id="lxdel" class="danger">Remove this light</button>
      </div>
      <p id="lxmsg" class="muted lxsmall"></p>
    </div>
  </section>
</div>
<style>{_CSS}</style>
<script>var LX = {_js(data)}; var LX_PICK = {_js(pick)};</script>
<script>{_SCRIPT}</script>"""


def _js(value) -> str:
    """JSON that is safe inside a <script> (a tile named "</script>" stays text)."""
    return json.dumps(value).replace("<", "\\u003c")


_CSS = """
.lxwrap { display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }
.lxlist { flex: 0 0 280px; max-width: 100%; display: flex; flex-direction: column; gap: 8px; }
.lxin { width: 100%; padding: 7px 9px; border-radius: 8px; border: 1px solid var(--edge, #444);
  background: var(--deep, #1c1a17); color: inherit; font: inherit; }
.lxgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; max-height: 70vh; overflow-y: auto; }
.lxtile { border: 1px solid transparent; border-radius: 8px; padding: 4px; background: var(--deep, #1c1a17);
  cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 2px; color: inherit; font: inherit; }
.lxtile img { width: 100%; height: 56px; object-fit: contain; }
.lxtile span { font-size: 10px; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.lxtile.on { border-color: #f0a64f; }
.lxtile.lit span::after { content: " 💡"; }
.lxmain { flex: 1 1 520px; min-width: 300px; }
.lxbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.lxseg { display: inline-flex; border: 1px solid var(--edge, #444); border-radius: 8px; overflow: hidden; }
.lxseg button { background: none; border: 0; color: inherit; padding: 5px 10px; cursor: pointer; font: inherit; }
.lxseg button.on { background: #f0a64f; color: #1b130a; }
.lxstage { position: relative; height: 460px; border-radius: 12px; overflow: hidden; background: #6f8a4f;
  display: flex; align-items: center; justify-content: center; user-select: none; }
.lxstage.night { background: #3c4a33; }
.lxbox { position: relative; }
.lxbox img { display: block; width: 100%; height: 100%; image-rendering: pixelated; pointer-events: none; }
.lxbox canvas { position: absolute; inset: 0; pointer-events: none; }
.lxhint { color: #fff8; }
.lxdot { position: absolute; width: 16px; height: 16px; margin: -8px 0 0 -8px; border-radius: 50%;
  border: 2px solid #fff; box-shadow: 0 0 0 1px #0008; cursor: grab; touch-action: none; }
.lxdot.on { outline: 2px solid #f0a64f; outline-offset: 2px; }
.lxring { position: absolute; border: 1px dashed #fff6; border-radius: 50%; pointer-events: none; }
.lxside { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.lxlights { display: flex; gap: 6px; flex-wrap: wrap; }
.lxchip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 999px;
  border: 1px solid var(--edge, #444); cursor: pointer; font-size: 12px; background: none; color: inherit; }
.lxchip.on { border-color: #f0a64f; }
.lxchip i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.lxedit { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.lxedit label { display: inline-flex; align-items: center; gap: 6px; }
.lxsmall { font-size: 12px; }
.lxseg[hidden], .lxedit[hidden] { display: none; }
"""

_SCRIPT = r"""
(function () {
  var tiles = LX.tiles, cur = null, pic = 'v', sel = -1, night = true, saveT = null;
  var grid = document.getElementById('lxgrid'), q = document.getElementById('lxq'),
      catSel = document.getElementById('lxcat'), only = document.getElementById('lxonly'),
      stage = document.getElementById('lxstage'), msg = document.getElementById('lxmsg');
  function art(v) { return '/dodoland/tiles/art/' + v; }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  var cats = []; tiles.forEach(function (t) { if (cats.indexOf(t.cat) < 0) cats.push(t.cat); });
  cats.sort();
  catSel.innerHTML = '<option value="">Every category</option>' + cats.map(function (c) {
    return '<option>' + esc(c) + '</option>'; }).join('');
  function lightsOf(t) { return (pic === 'up' ? t.ulights : t.lights) || []; }
  function hasLights(t) { return (t.lights && t.lights.length) || (t.ulights && t.ulights.length); }
  function renderGrid() {
    var term = q.value.toLowerCase(), c = catSel.value;
    var shown = tiles.filter(function (t) {
      return (!c || t.cat === c) && (!term || t.name.toLowerCase().indexOf(term) >= 0) && (!only.checked || hasLights(t));
    }).slice(0, 240);
    grid.innerHTML = shown.map(function (t) {
      return '<button class="lxtile' + (cur && cur.id === t.id ? ' on' : '') + (hasLights(t) ? ' lit' : '') +
        '" data-id="' + t.id + '"><img loading="lazy" alt="" src="' + art(t.up && LX.painted_first ? t.up : t.v) +
        '"><span>' + esc(t.name) + '</span></button>';
    }).join('') || '<p class="muted lxsmall">Nothing matches.</p>';
    grid.querySelectorAll('.lxtile').forEach(function (b) {
      b.onclick = function () { choose(b.dataset.id); };
    });
  }
  [q, catSel, only].forEach(function (el) { el.addEventListener('input', renderGrid); });
  function choose(id) {
    cur = tiles.filter(function (t) { return t.id === id; })[0] || null;
    if (!cur) return;
    pic = cur.up && LX.painted_first ? 'up' : 'v';
    sel = -1;
    document.getElementById('lxname').textContent = cur.name;
    var pics = document.getElementById('lxpics');
    pics.hidden = !cur.up;
    document.getElementById('lxauto').checked = cur.auto !== false;
    renderGrid(); renderStage();
  }
  document.querySelectorAll('#lxpics button').forEach(function (b) {
    b.onclick = function () { pic = b.dataset.pic; sel = -1; renderStage(); };
  });
  document.querySelectorAll('#lxtime button').forEach(function (b) {
    b.onclick = function () { night = b.dataset.t === 'night'; renderStage(); };
  });
  document.getElementById('lxauto').onchange = function (ev) { if (cur) { cur.auto = ev.target.checked; save(); } };

  // --- the stage: the picture, its night, and its lights ------------------- //
  var box = null, cv = null, dims = null;
  function fit() {
    var w = pic === 'up' ? cur.uw : cur.w, h = pic === 'up' ? cur.uh : cur.h;
    var wc = pic === 'up' ? cur.uwc : cur.wc;
    // Big enough to work on, room round it for the light to spread.
    var maxW = Math.min(stage.clientWidth - 80, 560), maxH = stage.clientHeight - 80;
    var k = Math.min(maxW / Math.max(1, w), maxH / Math.max(1, h));
    k = Math.min(k, 12);
    return {w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)), cell: Math.max(1, w * k) / Math.max(0.01, wc || 1)};
  }
  function renderStage() {
    document.querySelectorAll('#lxpics button').forEach(function (b) { b.classList.toggle('on', b.dataset.pic === pic); });
    document.querySelectorAll('#lxtime button').forEach(function (b) { b.classList.toggle('on', (b.dataset.t === 'night') === night); });
    stage.classList.toggle('night', night);
    if (!cur) return;
    dims = fit();
    stage.innerHTML = '<div class="lxbox" style="width:' + dims.w + 'px;height:' + dims.h + 'px">' +
      '<img alt="" src="' + art(pic === 'up' ? cur.up : cur.v) + '"></div><canvas id="lxnight"></canvas>';
    box = stage.querySelector('.lxbox');
    cv = stage.querySelector('#lxnight');
    cv.width = stage.clientWidth; cv.height = stage.clientHeight;
    cv.style.position = 'absolute'; cv.style.left = 0; cv.style.top = 0; cv.style.pointerEvents = 'none';
    drawDots(); drawGlow(); renderChips();
  }
  function origin() {
    var b = box.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return {x: b.left - s.left, y: b.top - s.top};
  }
  function rgb(hex) { return [1, 3, 5].map(function (i) { return parseInt(hex.slice(i, i + 2), 16); }); }
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
  // The same night the map draws: dark over everything, light cut out round
  // each light, a warm glow over what it lights.
  function drawGlow() {
    var c = cv.getContext('2d');
    c.clearRect(0, 0, cv.width, cv.height);
    if (!night) return;
    c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
    c.fillStyle = 'rgba(11,20,48,.62)'; c.fillRect(0, 0, cv.width, cv.height);
    var o = origin(), list = lightsOf(cur), white = stamp([255, 255, 255]);
    c.globalCompositeOperation = 'destination-out';
    list.forEach(function (L) {
      var x = o.x + L.x * dims.w, y = o.y + L.y * dims.h, r = L.radius * dims.cell, k = L.intensity;
      c.globalAlpha = Math.min(1, 0.85 * k); c.drawImage(white, x - r, y + r * 0.15 - r * 0.7, r * 2, r * 1.4);
      c.globalAlpha = Math.min(1, k); c.drawImage(white, x - r * 0.22, y - r * 0.22, r * 0.44, r * 0.44);
    });
    c.globalCompositeOperation = 'source-over';
    list.forEach(function (L) {
      var x = o.x + L.x * dims.w, y = o.y + L.y * dims.h, r = L.radius * dims.cell, k = L.intensity, s = stamp(rgb(L.colour));
      c.globalAlpha = Math.min(1, 0.35 * k); c.drawImage(s, x - r, y + r * 0.15 - r * 0.7, r * 2, r * 1.4);
      c.globalAlpha = Math.min(1, 0.7 * k); c.drawImage(s, x - r * 0.18, y - r * 0.18, r * 0.36, r * 0.36);
    });
    c.globalAlpha = 1;
  }
  function drawDots() {
    stage.querySelectorAll('.lxdot, .lxring').forEach(function (n) { n.remove(); });
    var o = origin();
    lightsOf(cur).forEach(function (L, i) {
      var d = document.createElement('div');
      d.className = 'lxdot' + (i === sel ? ' on' : '');
      d.style.left = (o.x + L.x * dims.w) + 'px'; d.style.top = (o.y + L.y * dims.h) + 'px';
      d.style.background = L.colour;
      d.title = 'Drag to move, click to edit';
      stage.appendChild(d);
      if (i === sel) {
        var r = L.radius * dims.cell, ring = document.createElement('div');
        ring.className = 'lxring';
        ring.style.left = (o.x + L.x * dims.w - r) + 'px'; ring.style.top = (o.y + L.y * dims.h - r) + 'px';
        ring.style.width = ring.style.height = (r * 2) + 'px';
        stage.appendChild(ring);
      }
      d.addEventListener('pointerdown', function (ev) {
        ev.preventDefault(); ev.stopPropagation();
        select(i);
        d.setPointerCapture(ev.pointerId);
        function move(m) {
          var b = box.getBoundingClientRect();
          L.x = Math.max(0, Math.min(1, (m.clientX - b.left) / b.width));
          L.y = Math.max(0, Math.min(1, (m.clientY - b.top) / b.height));
          drawDots(); drawGlow();
        }
        function up() {
          d.removeEventListener('pointermove', move); d.removeEventListener('pointerup', up);
          save();
        }
        d.addEventListener('pointermove', move); d.addEventListener('pointerup', up);
      });
    });
  }
  stage.addEventListener('dblclick', function (ev) {
    if (!cur || !box) return;
    var b = box.getBoundingClientRect();
    var list = pic === 'up' ? (cur.ulights = cur.ulights || []) : (cur.lights = cur.lights || []);
    if (list.length >= 16) { msg.textContent = 'A picture holds at most 16 lights.'; return; }
    var last = list[list.length - 1];
    list.push({x: Math.max(0, Math.min(1, (ev.clientX - b.left) / b.width)),
               y: Math.max(0, Math.min(1, (ev.clientY - b.top) / b.height)),
               colour: last ? last.colour : '#ffc46b', radius: last ? last.radius : 3, intensity: last ? last.intensity : 1});
    select(list.length - 1);
    save();
  });
  function select(i) {
    sel = i;
    var L = lightsOf(cur)[i], ed = document.getElementById('lxedit');
    ed.hidden = !L;
    if (L) {
      document.getElementById('lxcol').value = L.colour;
      document.getElementById('lxrad').value = L.radius; document.getElementById('lxradn').textContent = L.radius;
      document.getElementById('lxint').value = L.intensity; document.getElementById('lxintn').textContent = L.intensity;
    }
    drawDots(); drawGlow(); renderChips();
  }
  function renderChips() {
    var box2 = document.getElementById('lxlights'), list = lightsOf(cur);
    box2.innerHTML = list.map(function (L, i) {
      return '<button class="lxchip' + (i === sel ? ' on' : '') + '" data-i="' + i + '"><i style="background:' + L.colour +
        '"></i>Light ' + (i + 1) + ' · ' + L.radius + ' cells</button>';
    }).join('') || '<span class="muted lxsmall">No lights yet. Double-click the picture to add one.</span>';
    box2.querySelectorAll('.lxchip').forEach(function (b) { b.onclick = function () { select(+b.dataset.i); }; });
    document.getElementById('lxedit').hidden = !(sel >= 0 && list[sel]);
  }
  function edited(field, value) {
    var L = lightsOf(cur)[sel];
    if (!L) return;
    L[field] = value;
    document.getElementById('lxradn').textContent = L.radius;
    document.getElementById('lxintn').textContent = L.intensity;
    drawDots(); drawGlow(); renderChips();
    save();
  }
  document.getElementById('lxcol').oninput = function (ev) { edited('colour', ev.target.value); };
  document.getElementById('lxrad').oninput = function (ev) { edited('radius', parseFloat(ev.target.value)); };
  document.getElementById('lxint').oninput = function (ev) { edited('intensity', parseFloat(ev.target.value)); };
  document.getElementById('lxdel').onclick = function () {
    var list = lightsOf(cur);
    if (sel < 0 || !list[sel]) return;
    list.splice(sel, 1); sel = -1;
    drawDots(); drawGlow(); renderChips(); save();
  };
  window.addEventListener('keydown', function (ev) {
    if ((ev.key === 'Delete' || ev.key === 'Backspace') && sel >= 0 && document.activeElement.tagName !== 'INPUT') {
      document.getElementById('lxdel').onclick();
    }
  });
  window.addEventListener('resize', function () { if (cur) renderStage(); });

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
          msg.textContent = res.ok ? 'Saved. The map shows it at night after a reload.' : (res.error || 'That did not save.');
          renderGrid();
        })
        .catch(function (err) { msg.textContent = String(err); });
    }, 450);
  }
  renderGrid();
  if (LX_PICK) choose(LX_PICK);
})();
"""

