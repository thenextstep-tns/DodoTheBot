"""
The terrain layer on the map page, and the tools that edit it.

Deliberately *on the map page* rather than a page of its own. The map already
owns panning, zooming, viewport culling and the coordinate maths, and the one
time this project drew its own second view of the same world the two
disagreed. A second pan-and-zoom would be that mistake again, one layer down.

**The ground is painted with library tiles.** The palette is the environment
tiles the person may use, one category at a time. Click a tile to paint with
it; Shift- or Ctrl-click more to paint a **random mix** of them.

**Three tools**

* **Brush** — drag to paint a disc along the drag. *Density* scatters the stroke
  (only that share of cells is painted) and *Soft edge* thins it towards the rim,
  so a wide brush lays down a ragged coastline or a sprinkling of flowers rather
  than a stamped circle. Every stroke gets a fresh random seed.
* **Select** — drag a rectangle, then fill it with the brush's tiles (density
  applies), clear it, or keep it as a pattern.
* **Pattern** — paint with the cells copied from a selection, tiled across the
  world, so a hand-made bit of ground can be repeated without repeating work.

Rasterising, randomness and limits all live on the server
(``web/dodoland/terrain_api.py``), so two clients can never paint the same
stroke two ways.

**Detail arrives with the zoom, the same bargain the towns make.** One coarse
request draws the whole continent in each tile's average colour; full-detail
chunks, textured with the tiles themselves, are fetched only for what is on
screen.
"""

from __future__ import annotations

CSS = """
/* The world's three layers. The reference sits under the terrain so it can be
   faded behind it while tracing; neither ever takes pointer events, because the
   frame owns panning and painting. */
#dlbase { opacity: var(--refop, 1); transition: opacity .15s ease; }
.dlterrain { position: absolute; left: 0; top: 0; width: 100%; height: 100%;
  pointer-events: none; z-index: 1; }
.dlterrain.off { display: none; }
.dlworld .dltown, .dlworld .dlpiece { z-index: 5; }
.dlframe.painting { cursor: crosshair; }
/* Overlay lines a fixed number of screen pixels wide at any zoom.
   non-scaling-stroke alone undoes only the SVG's own viewBox; the zoom is a CSS
   transform on the world around it, which still scaled a 1.6px line by 50.
   --inv (one screen pixel in world units) undoes that too. */
.dltline { vector-effect: non-scaling-stroke; stroke-width: calc(1px * var(--inv, 1));
  stroke-linecap: square; }
.dltline.wide { stroke-width: calc(3px * var(--inv, 1)); }
.dlwall { fill: none; stroke-linejoin: round; stroke-linecap: round; }
.dlroad { fill: none; stroke-linejoin: round; stroke-linecap: round; }
.dlworld.hide-roads #dltroads { display: none; }
.dlworld.hide-buildings #dltwalls { display: none; }
.dltdash { stroke-width: calc(1.5px * var(--inv, 1));
  stroke-dasharray: calc(5px * var(--inv, 1)) calc(3px * var(--inv, 1)); }

/* The terrain drawer, on the left like the toolkit and never open with it. */
.dlterrdrawer { left: 0; right: auto; border-left: 0;
  border-right: 1px solid var(--edge); transform: translateX(-100%);
  box-shadow: 6px 0 24px rgba(0,0,0,.28); }
.dlterrdrawer.open { transform: translateX(0); }
.dltmix { margin: 0 14px 8px; font-size: 12px; color: var(--soft); display: flex;
  gap: 6px; align-items: center; flex-wrap: wrap; min-height: 22px; }
.dltmix .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px 2px 2px;
  border: 1px solid var(--edge); border-radius: 999px; background: var(--deep); }
.dltmix .chip img { width: 16px; height: 16px; border-radius: 50%; object-fit: cover;
  image-rendering: pixelated; }
.dltmix button { background: none; border: 0; color: var(--lantern); cursor: pointer;
  font: inherit; font-size: 12px; padding: 0; }
.dltsliders { padding: 8px 14px; border-top: 1px solid var(--edge); display: grid;
  grid-template-columns: auto 1fr 3.2em; gap: 6px 10px; align-items: center;
  font-size: 12px; color: var(--soft); }
.dltsliders input[type=range] { width: 100%; }
.dltsliders output { text-align: right; font-variant-numeric: tabular-nums; }
.dltpanel { padding: 8px 14px; border-top: 1px solid var(--edge); font-size: 12px;
  color: var(--soft); display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.dltpanel[hidden] { display: none; }
.dltmsg { margin: 0; padding: 4px 14px 12px; font-size: 12px; color: var(--soft); }
.dltmsg.bad { color: #e0735f; font-weight: 600; }
.dltswatch { width: 100%; height: 48px; border-radius: 6px; }
"""

DRAWER = """
<aside class="dldrawer dlterrdrawer" id="dlterrdrawer">
  <div class="dldhead">
    <b>Terrain</b>
    <button class="dlghost" id="dltclose">&times;</button>
  </div>
  <div class="dlseg" id="dlttools">
    <button data-tool="brush" class="on">Brush</button>
    <button data-tool="select">Select</button>
    <button data-tool="pattern">Pattern</button>
  </div>
  <p class="dlkithint" id="dlthint"></p>
  <select class="dlsel" id="dltcat"></select>
  <div class="dlkitgrid" id="dltkinds"></div>
  <div class="dltmix" id="dltmix"></div>
  <div class="dltsliders" id="dltbrush">
    <label for="dltradius">Size</label><input type="range" id="dltradius" min="0" max="64" value="12"><output id="dltradiusn">12</output>
    <label for="dltdensity">Density</label><input type="range" id="dltdensity" min="5" max="100" step="5" value="100"><output id="dltdensityn">100%</output>
    <label for="dltsoft">Soft edge</label><input type="range" id="dltsoft" min="0" max="100" step="5" value="0"><output id="dltsoftn">0%</output>
  </div>
  <div class="dltpanel" id="dltselect" hidden>
    <span id="dltselinfo">Drag a rectangle on the map.</span>
    <button class="dlghost" id="dltfill" disabled>Fill</button>
    <button class="dlghost" id="dltclear" disabled>Clear</button>
    <button class="dlghost" id="dltkeep" disabled>Use as pattern</button>
  </div>
  <div class="dltpanel" id="dltpattern" hidden>
    <span id="dltpatinfo">No pattern yet: select an area and press “Use as pattern”.</span>
  </div>
  <div class="dltpanel">
    <button class="dlghost" id="dltundo" disabled>&#8630; Undo</button>
    <button class="dlghost" id="dltredo" disabled>&#8631; Redo</button>
    <span id="dltdepth" style="margin-left:auto;opacity:.7"></span>
  </div>
  <div class="dltpanel">
    <label style="flex:1 1 auto;display:flex;align-items:center;gap:8px">Reference
      <input type="range" id="dltref" min="0" max="100" step="5" value="0" style="flex:1"></label>
    <button class="dlghost" id="dltoggleterr">Hide terrain</button>
  </div>
  <p class="dltmsg" id="dltmsg"></p>
</aside>
"""

SCRIPT = r"""
  // --- the terrain layer ------------------------------------------------- //
  // `armed` is what the map page checks before handing a drag to us: null when
  // no tool is ready, otherwise the tool's name.
  var terr = {world: null, armed: null, tool: 'brush', mix: [], erase: false,
              radius: 12, density: 1, soft: 0, sel: null, pattern: null,
              have: {}, shown: true, busy: false, ver: 0};
  var terrLayer = document.createElement('div');
  terrLayer.className = 'dlterrain';
  var terrDrawer = document.getElementById('dlterrdrawer');
  var terrMsg = document.getElementById('dltmsg');
  var HINTS = {
    brush: 'Click a tile to paint with it. Shift- or Ctrl-click more to paint a random mix.',
    select: 'Drag a rectangle on the map, then fill it, clear it, or keep it as a pattern.',
    pattern: 'Drag on the map to paint with the pattern, tiled across the world.'
  };

  function terrSay(text, bad) {
    if (!terrMsg) return;
    terrMsg.textContent = text || '';
    terrMsg.classList.toggle('bad', !!bad);
  }
  function terrUrl(path, query) {
    return '/guild/' + D.gid + '/dodoland/terrain/' + path + (query || '');
  }
  function world_el() { return document.getElementById('dlworld'); }

  // One <svg> for the whole world in cell coordinates. `preserveAspectRatio
  // none` pins it to the base image exactly, so a cell and a pixel of the
  // uploaded map stay in register however either is scaled.
  function terrSetup(world) {
    terr.world = world;
    terr.ver = world.version;
    terrLayer.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" ' +
      'preserveAspectRatio="none" viewBox="0 0 ' + world.cells_w + ' ' +
      world.cells_h + '"><g id="dltdefs"></g>' +
      '<g id="dltover"></g><g id="dltdetail"></g><g id="dltinfl"></g><g id="dltroads"></g><g id="dltwalls"></g>' +
      '<rect id="dltsel" class="dltline dltdash" fill="rgba(240,166,79,.12)" stroke="#f0a64f" ' +
      'style="display:none"/>' +
      // The brush's exact footprint: the cells a stroke here will paint, traced
      // along their edges. Built once per size and moved with a transform.
      '<g id="dltcursor" style="display:none" pointer-events="none">' +
      '<path id="dltcurfill" fill="#fff" fill-opacity=".14" shape-rendering="crispEdges"/>' +
      '<path id="dltcurhalo" class="dltline wide" fill="none" stroke="#000" stroke-opacity=".55"/>' +
      '<path id="dltcurline" class="dltline" fill="none" stroke="#fff"/></g></svg>';
    world_el().appendChild(terrLayer);
    renderCats();
    renderPalette();
  }

  // --- the palette ------------------------------------------------------- //
  var catSel = document.getElementById('dltcat');
  function cats() {
    var out = [];
    (terr.world.palette || []).forEach(function (t) {
      if (out.indexOf(t.cat) < 0) out.push(t.cat);
    });
    return out;
  }
  function renderCats() {
    var list = cats();
    catSel.innerHTML = list.map(function (c) {
      return '<option>' + escapeHtml(c || 'Uncategorised') + '</option>';
    }).join('');
    try { var kept = window.localStorage.getItem('dl-terr-cat');
          if (kept && list.indexOf(kept) >= 0) catSel.value = kept; } catch (e) {}
  }
  catSel.onchange = function () {
    try { window.localStorage.setItem('dl-terr-cat', catSel.value); } catch (e) {}
    renderPalette();
  };
  function tileById(id) {
    var list = terr.world.palette || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function renderPalette() {
    var box = document.getElementById('dltkinds');
    if (!box || !terr.world) return;
    var shown = catSel.value;
    var cards = (terr.world.palette || []).filter(function (t) {
      return (t.cat || 'Uncategorised') === shown;
    }).map(function (t) {
      var on = terr.mix.indexOf(t.id) >= 0 && !terr.erase;
      return '<button class="dlkititem' + (on ? ' armed' : '') + '" data-t="' + t.id +
        '" title="' + escapeHtml(t.name) + (t.passable ? '' : ' — blocks roads') + '">' +
        '<img alt="" loading="lazy" style="image-rendering:pixelated" src="' + t.thumb + '">' +
        '<span>' + escapeHtml(t.name) + (t.passable ? '' : ' ⛔') + '</span></button>';
    });
    // The eraser: back to "nothing said about this cell".
    cards.unshift('<button class="dlkititem' + (terr.erase ? ' armed' : '') +
      '" data-erase="1" title="Erase back to unset ground">' +
      '<div class="dltswatch" style="background:repeating-conic-gradient(#8884 0 25%,transparent 0 50%) 0 0/12px 12px"></div>' +
      '<span>Eraser</span></button>');
    box.innerHTML = cards.join('');
    box.querySelectorAll('.dlkititem').forEach(function (el) {
      el.onclick = function (ev) {
        if (el.dataset.erase) {
          terr.erase = !terr.erase;
          if (terr.erase) terr.mix = [];
        } else {
          var id = el.dataset.t, at = terr.mix.indexOf(id);
          terr.erase = false;
          if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
            if (at >= 0) terr.mix.splice(at, 1); else if (terr.mix.length < 16) terr.mix.push(id);
          } else {
            terr.mix = (at >= 0 && terr.mix.length === 1) ? [] : [id];
          }
        }
        rearm();
        renderPalette();
      };
    });
    renderMix();
  }
  function renderMix() {
    var box = document.getElementById('dltmix');
    if (!box) return;
    if (terr.erase) { box.innerHTML = 'Erasing.'; return; }
    if (!terr.mix.length) { box.innerHTML = 'Nothing picked.'; return; }
    box.innerHTML = (terr.mix.length > 1 ? 'Random mix of:' : 'Painting:') +
      terr.mix.map(function (id) {
        var t = tileById(id);
        return t ? '<span class="chip"><img alt="" src="' + t.thumb + '">' +
                   escapeHtml(t.name) + '</span>' : '';
      }).join('') + ' <button id="dltmixclear">clear</button>';
    var clear = document.getElementById('dltmixclear');
    if (clear) clear.onclick = function () { terr.mix = []; rearm(); renderPalette(); };
  }

  // What a tool needs before a drag means anything.
  function rearm() {
    var ready = terr.tool === 'select' ||
                (terr.tool === 'pattern' && !!terr.pattern) ||
                (terr.tool === 'brush' && (terr.erase || terr.mix.length > 0));
    terr.armed = ready ? terr.tool : null;
    frame.classList.toggle('painting', !!terr.armed);
    if (!terr.armed) hideCursor();
    document.getElementById('dlthint').textContent = HINTS[terr.tool];
    var canFill = !!terr.sel && (terr.erase || terr.mix.length > 0);
    document.getElementById('dltfill').disabled = !canFill;
    document.getElementById('dltclear').disabled = !terr.sel;
    document.getElementById('dltkeep').disabled = !terr.sel;
  }

  document.querySelectorAll('#dlttools button').forEach(function (b) {
    b.onclick = function () {
      terr.tool = b.dataset.tool;
      document.querySelectorAll('#dlttools button').forEach(function (o) {
        o.classList.toggle('on', o === b);
      });
      document.getElementById('dltselect').hidden = terr.tool !== 'select';
      document.getElementById('dltpattern').hidden = terr.tool !== 'pattern';
      document.getElementById('dltbrush').style.display = terr.tool === 'select' ? 'none' : '';
      rearm();
    };
  });

  // --- drawing the world ------------------------------------------------- //
  // Zoomed out, the world is one shaded picture at a pixel per cell
  // (terrain_raster), scaled smoothly by the browser; up close the tiles fade in
  // over it. Loaded off-screen first and swapped in whole, so a repaint never
  // flashes an empty map.
  function terrOverview() {
    var url = terrUrl('picture', '?v=' + encodeURIComponent(terr.ver));
    var probe = new Image();
    probe.onload = function () {
      var g = document.getElementById('dltover');
      if (!g || !terr.world) return;
      g.removeAttribute('transform');
      g.innerHTML = '<image href="' + url + '" x="0" y="0" width="' + terr.world.cells_w +
        '" height="' + terr.world.cells_h + '" preserveAspectRatio="none"/>';
      // The reference stays up until there is ground to replace it. Hidden
      // once: after that the slider owns it.
      if (!terr.refHidden) { terr.refHidden = true; world_el().style.setProperty('--refop', 0); }
      if (typeof loaded === 'function') loaded('ground');
    };
    probe.onerror = function () { if (typeof loaded === 'function') loaded('ground'); };
    probe.src = url;
  }
  function terrDefs() {
    fetch(terrUrl('defs', '?v=' + terr.ver)).then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (defs) {
        var g = document.getElementById('dltdefs');
        if (g) g.innerHTML = defs || '';
      });
  }

  // Which chunks the viewport covers, in chunk coordinates.
  function visibleChunks() {
    if (!terr.world || !nat.w) return null;
    var cw = terr.world.cells_w, ch = terr.world.cells_h;
    var perCellX = (nat.w * view.k) / cw;
    var total = terr.world.chunks_x * terr.world.chunks_y;
    // Textures only once a cell is a few pixels across; below that a tile is
    // noise, and the shaded picture reads better. They fade in over the next
    // couple of pixels per cell instead of popping in at a line.
    var detail = document.getElementById('dltdetail');
    if (detail) detail.style.opacity = Math.max(0, Math.min(1, (perCellX - 2.5) / 2)).toFixed(2);
    if (perCellX < 2.5 && total > 0) return null;
    var x0 = (-view.x) / perCellX, x1 = (-view.x + frame.clientWidth) / perCellX;
    var perCellY = (nat.h * view.k) / ch;
    var y0 = (-view.y) / perCellY, y1 = (-view.y + frame.clientHeight) / perCellY;
    var C = terr.world.chunk;
    return {
      x0: Math.max(0, Math.floor(x0 / C) - 1),
      y0: Math.max(0, Math.floor(y0 / C) - 1),
      x1: Math.min(terr.world.chunks_x - 1, Math.floor(x1 / C) + 1),
      y1: Math.min(terr.world.chunks_y - 1, Math.floor(y1 / C) + 1)
    };
  }

  function terrDetail() {
    if (terr.busy || !terr.world) return;
    var box = visibleChunks();
    var g = document.getElementById('dltdetail');
    if (!g) return;
    if (!box) { g.innerHTML = ''; terr.have = {}; return; }
    var need = [];
    for (var cy = box.y0; cy <= box.y1; cy++) {
      for (var cx = box.x0; cx <= box.x1; cx++) {
        if (!terr.have[cx + ',' + cy + ',' + terr.ver]) need.push([cx, cy]);
      }
    }
    if (!need.length) return;
    if ((box.x1 - box.x0 + 1) * (box.y1 - box.y0 + 1) > 400) return;
    terr.busy = true;
    fetch(terrUrl('chunks', '?r=' + box.x0 + ',' + box.y0 + ',' + box.x1 + ',' + box.y1 +
                  '&v=' + terr.ver))
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (svg) {
        terr.busy = false;
        if (!svg) return;
        g.innerHTML = svg;
        terr.have = {};
        for (var cy = box.y0; cy <= box.y1; cy++) {
          for (var cx = box.x0; cx <= box.x1; cx++) {
            terr.have[cx + ',' + cy + ',' + terr.ver] = 1;
          }
        }
      })
      .catch(function () { terr.busy = false; });
  }

  // --- pointer ----------------------------------------------------------- //
  // Screen -> cell. The world element is the base image's natural size, and the
  // grid is laid over it, so one conversion serves both.
  function cellAt(clientX, clientY) {
    if (!terr.world || !nat.w) return null;
    var b = frame.getBoundingClientRect();
    var fx = (clientX - b.left - view.x) / (nat.w * view.k);
    var fy = (clientY - b.top - view.y) / (nat.h * view.k);
    // Floor: cell (x, y) is the square from x to x + 1, so the cell under the
    // pointer is the one painted. Rounding picked the nearest corner, which put
    // the brush half a cell off what it showed.
    return [Math.floor(fx * terr.world.cells_w), Math.floor(fy * terr.world.cells_h)];
  }
  function hideCursor() {
    var c = document.getElementById('dltcursor');
    if (c) c.style.display = 'none';
  }
  // The same disc the server paints (dx² + dy² <= r²), as two paths around
  // the origin cell: its cells, and the edges between a covered cell and an
  // uncovered one. Size 0 is one cell — a single tile.
  var footprintFor = -1;
  function footprint(r) {
    if (footprintFor === r) return;
    footprintFor = r;
    var inside = {}, fill = [], line = [];
    function has(x, y) { return inside[x + ',' + y] === 1; }
    for (var dy = -r; dy <= r; dy++) {
      var run = -1;
      for (var dx = -r; dx <= r + 1; dx++) {
        var on = dx <= r && dx * dx + dy * dy <= r * r;
        if (on) inside[dx + ',' + dy] = 1;
        if (on && run < 0) run = dx;
        if (!on && run >= 0) { fill.push('M' + run + ' ' + dy + 'h' + (dx - run) + 'v1h' + (run - dx) + 'z'); run = -1; }
      }
    }
    for (var y = -r; y <= r + 1; y++) {
      for (var x = -r; x <= r + 1; x++) {
        var me = has(x, y);
        if (me !== has(x, y - 1)) line.push('M' + x + ' ' + y + 'h1');
        if (me !== has(x - 1, y)) line.push('M' + x + ' ' + y + 'v1');
      }
    }
    document.getElementById('dltcurfill').setAttribute('d', fill.join(''));
    document.getElementById('dltcurhalo').setAttribute('d', line.join(''));
    document.getElementById('dltcurline').setAttribute('d', line.join(''));
  }
  function moveCursor(ev) {
    var c = document.getElementById('dltcursor');
    if (!c) return;
    var cell = terr.armed ? cellAt(ev.clientX, ev.clientY) : null;
    if (!cell) { hideCursor(); return; }
    // Selecting picks cells one at a time, so it shows the one cell it is on.
    footprint(terr.armed === 'select' ? 0 : terr.radius);
    c.setAttribute('transform', 'translate(' + cell[0] + ' ' + cell[1] + ')');
    c.style.display = '';
  }
  frame.addEventListener('pointermove', moveCursor);
  frame.addEventListener('pointerleave', hideCursor);

  // Escape or a right click: the terrain brush, the eraser and a selection go;
  // the drawer stays open on what it was showing.
  function terrPutDown() {
    terr.mix = []; terr.erase = false; terr.sel = null;
    if (stroke) stroke = null;
    drawSel();
    rearm();
    renderPalette();
    hideCursor();
  }
  function drawSel() {
    var r = document.getElementById('dltsel');
    if (!r) return;
    if (!terr.sel) { r.style.display = 'none'; return; }
    var s = terr.sel;
    r.setAttribute('x', Math.min(s[0], s[2])); r.setAttribute('y', Math.min(s[1], s[3]));
    r.setAttribute('width', Math.abs(s[2] - s[0]) + 1);
    r.setAttribute('height', Math.abs(s[3] - s[1]) + 1);
    r.style.display = '';
    document.getElementById('dltselinfo').textContent =
      (Math.abs(s[2] - s[0]) + 1) + ' × ' + (Math.abs(s[3] - s[1]) + 1) + ' cells';
  }

  var stroke = null;
  function strokeStart(ev) {
    var cell = cellAt(ev.clientX, ev.clientY);
    if (!cell) return false;
    if (terr.armed === 'select') { terr.sel = [cell[0], cell[1], cell[0], cell[1]]; drawSel(); }
    stroke = [cell];
    return true;
  }
  function strokeMove(ev) {
    if (!stroke) return;
    var cell = cellAt(ev.clientX, ev.clientY);
    if (!cell) return;
    if (terr.armed === 'select') { terr.sel[2] = cell[0]; terr.sel[3] = cell[1]; drawSel(); return; }
    var last = stroke[stroke.length - 1];
    // Thin the stroke: a pointer reports far more often than a cell changes.
    if (Math.abs(cell[0] - last[0]) + Math.abs(cell[1] - last[1]) >= 1) stroke.push(cell);
  }
  function strokeEnd() {
    var points = stroke;
    stroke = null;
    if (!points || !terr.armed) return;
    if (terr.armed === 'select') { rearm(); return; }
    var body = {mode: 'brush', radius: terr.radius, points: points.slice(0, 4000)};
    if (terr.armed === 'pattern') body.pattern = terr.pattern;
    paint(body, 'Painting…');
  }

  function what() {
    return terr.erase ? {kinds: [0]} : {tiles: terr.mix.slice()};
  }
  function paint(body, saying) {
    // The sliders first and the call's own settings over them, so "Clear"
    // clears every cell whatever the density is set to.
    var payload = Object.assign(body.pattern ? {} : what(), {
      density: terr.density, soft: terr.soft,
      // The randomiser: a fresh seed per stroke, so no two scattered strokes
      // land the same way — and the server, not the browser, rolls the dice.
      seed: Math.floor(Math.random() * 2147483647)
    }, body);
    terrSay(saying);
    fetch('/api/guild/' + D.gid + '/dodoland/terrain/paint', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { terrSay(res.error || 'That did not work.', true); return; }
      terrSay(res.cells.toLocaleString() + ' cells painted.');
      // A tile painted for the first time adds a ground, and its pattern.
      if (res.kinds && terr.world.kinds && res.kinds !== terr.world.kinds.length) {
        terr.world.kinds.length = res.kinds;
        terrDefs();
      }
      terrApplyChange(res);
    }).catch(function (err) { terrSay(String(err), true); });
  }

  // Only what changed. Refetching the whole viewport and rebuilding the
  // overview after every stroke was about a second of lag for a change that
  // touched four chunks.
  var overviewTimer = null;
  function terrApplyChange(res) {
    terr.ver = res.version;
    terr.have = {};
    terrDetail();
    setUndo(res.undo, res.redo);
    if (overviewTimer) clearTimeout(overviewTimer);
    overviewTimer = setTimeout(terrOverview, 2500);
  }
  function setUndo(undo, redo) {
    var u = document.getElementById('dltundo'), r = document.getElementById('dltredo');
    if (u) u.disabled = !undo;
    if (r) r.disabled = !redo;
    var d = document.getElementById('dltdepth');
    if (d) d.textContent = undo ? undo + ' to undo' : '';
  }
  function terrStep(redo) {
    fetch('/api/guild/' + D.gid + '/dodoland/terrain/undo', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({redo: !!redo})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { terrSay(res.error || 'That did not work.', true); return; }
      if (!res.moved) { terrSay(redo ? 'Nothing to redo.' : 'Nothing to undo.');
                        setUndo(res.undo, res.redo); return; }
      terrSay(redo ? 'Redone.' : 'Undone.');
      terrApplyChange(res);
    }).catch(function (err) { terrSay(String(err), true); });
  }

  // --- influence -------------------------------------------------------- //
  // Each placed town's area: a faint wash of its colour and a dashed border,
  // drawn in cell units inside the terrain, above the ground and under every
  // placed feature. Its own layer in the Layers panel.
  // The first answer is asked for as the script starts, alongside the world,
  // rather than after it: they do not depend on each other.
  var inflFirst = fetch('/guild/' + D.gid + '/dodoland/influence')
    .then(function (r) { return r.ok ? r.json() : {towns: []}; })
    .catch(function () { return {towns: []}; });
  function loadInfluence() {
    var ask = inflFirst || fetch('/guild/' + D.gid + '/dodoland/influence')
      .then(function (r) { return r.ok ? r.json() : {towns: []}; });
    inflFirst = null;
    ask
      .then(function (res) {
        var g = document.getElementById('dltinfl');
        if (!g) return;
        D.influence = res.towns || [];
        g.innerHTML = D.influence.map(function (t) {
          // The line is the smoothed border when there is one: the stepped
          // cell edges read as a staircase from any distance.
          return '<g data-town="' + t.id + '"><path d="' + t.fill + '" fill="' + t.colour +
            '" fill-opacity=".16" shape-rendering="crispEdges"/>' +
            '<path class="dltline dltdash" d="' + (t.ring || t.line) + '" fill="none" stroke="' + t.colour +
            '"/></g>';
        }).join('');
        if (typeof applyLayers === 'function') applyLayers();
        if (typeof markInfluence === 'function') markInfluence();
        drawWalls();
        if (typeof buildLife === 'function') buildLife();
        if (typeof loaded === 'function') loaded('reach');
      })
      .catch(function () { if (typeof loaded === 'function') loaded('reach'); });
  }

  // --- roads ------------------------------------------------------------ //
  // Laid by the bot between towns whose people talk to each other (roads_api).
  // Drawn in cell units like everything built: a packed-earth road with a
  // darker verge, and plank bridges where it crosses water.
  function loadRoads() {
    fetch('/guild/' + D.gid + '/dodoland/roads')
      .then(function (r) { return r.ok ? r.json() : {roads: []}; })
      .then(function (res) {
        var g = document.getElementById('dltroads');
        if (!g) return;
        var w = res.width || 2.4, out = [];
        (res.roads || []).forEach(function (road) {
          out.push('<path class="dlroad" d="' + road.d + '" stroke="#6b5136" stroke-width="' + (w + 0.9) + '"/>');
        });
        (res.roads || []).forEach(function (road) {
          out.push('<path class="dlroad" d="' + road.d + '" stroke="#c8a676" stroke-width="' + w + '"/>');
        });
        (res.roads || []).forEach(function (road) {
          (road.bridges || []).forEach(function (d) {
            out.push('<path class="dlroad" d="' + d + '" stroke="#4a3220" stroke-width="' + (w + 1.4) + '" stroke-linecap="butt"/>' +
                     '<path class="dlroad" d="' + d + '" stroke="#9c7347" stroke-width="' + (w + 0.4) + '" stroke-linecap="butt" stroke-dasharray="0.55 0.3"/>');
          });
        });
        g.innerHTML = out.join('');
        D.roads = res.roads || [];
        if (typeof applyLayers === 'function') applyLayers();
      })
      .catch(function () {});
  }

  // --- walls ------------------------------------------------------------ //
  // A walled town's wall runs along its area's smoothed border, so it grows
  // with the town instead of being laid stone by stone. Drawn in cell units:
  // a wall is as thick on the map as it would be on the ground, and it zooms
  // like everything else built. Towers stand at intervals along it.
  var WALL = {
    // Widths in cells. A town hall is about ten cells across, so a stone wall
    // is a third of a hall thick and its towers about half a hall.
    stone: {layers: [['#35302b', 3.4], ['#9a9186', 2.2], ['#c7bfb3', 0.9, '1.5 1.2']],
            tower: function (x, y) {
              return '<circle cx="' + x + '" cy="' + y + '" r="3" fill="#8e867b" stroke="#35302b" stroke-width="0.7"/>' +
                     '<circle cx="' + x + '" cy="' + y + '" r="1.4" fill="#5c554d"/>'; }, every: 42},
    palisade: {layers: [['#2f1f12', 2.4], ['#86592f', 1.5, '0.75 0.3']],
            tower: function (x, y) {
              x = +x; y = +y;
              return '<rect x="' + (x - 1.7) + '" y="' + (y - 1.7) + '" width="3.4" height="3.4" fill="#6b4425" stroke="#2f1f12" stroke-width="0.6"/>'; },
            every: 54}
  };
  function drawWalls() {
    var g = document.getElementById('dltwalls');
    if (!g) return;
    var byTown = {};
    (D.influence || []).forEach(function (t) { byTown[t.id] = t; });
    var out = [];
    D.people.forEach(function (p) {
      var style = WALL[p.walls], area = byTown[p.id];
      if (!style || !p.plot || !area || !area.ring) return;
      style.layers.forEach(function (layer) {
        out.push('<path class="dlwall" data-town="' + p.id + '" d="' + area.ring + '" stroke="' + layer[0] +
                 '" stroke-width="' + layer[1] + '"' + (layer[2] ? ' stroke-dasharray="' + layer[2] + '"' : '') + '/>');
      });
    });
    g.innerHTML = out.join('');
    // Towers, measured along the drawn path, one set per town.
    var done = {};
    g.querySelectorAll('.dlwall').forEach(function (path) {
      var id = path.getAttribute('data-town');
      if (done[id]) return;
      done[id] = true;
      var p = byId[id], style = WALL[p && p.walls];
      if (!style) return;
      var towers = [];
      try {
        var length = path.getTotalLength();
        for (var at = style.every / 2; at < length; at += style.every) {
          var pt = path.getPointAtLength(at);
          towers.push(style.tower(pt.x.toFixed(1), pt.y.toFixed(1)));
        }
      } catch (e) {}
      g.insertAdjacentHTML('beforeend', towers.join(''));
    });
  }

  // --- selection actions ------------------------------------------------- //
  function selRect() {
    var s = terr.sel;
    return [Math.min(s[0], s[2]), Math.min(s[1], s[3]), Math.max(s[0], s[2]), Math.max(s[1], s[3])];
  }
  document.getElementById('dltfill').onclick = function () {
    if (terr.sel) paint({mode: 'rect', rect: selRect()}, 'Filling…');
  };
  document.getElementById('dltclear').onclick = function () {
    if (!terr.sel) return;
    var keep = {erase: terr.erase, mix: terr.mix};
    terr.erase = true;
    paint({mode: 'rect', rect: selRect(), density: 1}, 'Clearing…');
    terr.erase = keep.erase; terr.mix = keep.mix;
  };
  document.getElementById('dltkeep').onclick = function () {
    if (!terr.sel) return;
    var r = selRect();
    fetch(terrUrl('cells', '?r=' + r.join(','))).then(function (x) { return x.json(); })
      .then(function (res) {
        if (!res.ok) { terrSay(res.error, true); return; }
        terr.pattern = {w: res.w, h: res.h, cells: res.cells};
        document.getElementById('dltpatinfo').textContent =
          'Pattern: ' + res.w + ' × ' + res.h + ' cells. Drag on the map to paint with it.';
        terrSay('Pattern kept. Switch to Pattern to paint with it.');
        rearm();
      });
  };

  // --- controls ---------------------------------------------------------- //
  document.getElementById('dltundo').onclick = function () { terrStep(false); };
  document.getElementById('dltredo').onclick = function () { terrStep(true); };
  // The shortcuts everybody already has in their fingers. Only while the
  // terrain drawer is open, so they cannot fire at somebody editing a town name.
  window.addEventListener('keydown', function (ev) {
    if (!terrDrawer.classList.contains('open')) return;
    if (!(ev.ctrlKey || ev.metaKey)) return;
    var key = (ev.key || '').toLowerCase();
    if (key === 'z' && !ev.shiftKey) { ev.preventDefault(); terrStep(false); }
    else if (key === 'y' || (key === 'z' && ev.shiftKey)) { ev.preventDefault(); terrStep(true); }
  });
  function slider(id, show, apply) {
    var el = document.getElementById(id), out = document.getElementById(id + 'n');
    el.oninput = function () { var v = parseInt(el.value, 10) || 0; apply(v); out.textContent = show(v); };
  }
  slider('dltradius', String, function (v) {
    terr.radius = v;
    if (terr.armed && terr.armed !== 'select') footprint(v);
  });
  slider('dltdensity', function (v) { return v + '%'; }, function (v) { terr.density = v / 100; });
  slider('dltsoft', function (v) { return v + '%'; }, function (v) { terr.soft = v / 100; });
  document.getElementById('dltref').oninput = function () {
    world_el().style.setProperty('--refop', (parseInt(this.value, 10) || 0) / 100);
  };
  var terrToggle = document.getElementById('dltoggleterr');
  terrToggle.onclick = function () {
    terr.shown = !terr.shown;
    terrLayer.classList.toggle('off', !terr.shown);
    terrToggle.textContent = terr.shown ? 'Hide terrain' : 'Show terrain';
  };
  // Closing the drawer puts the brush down, whoever closes it.
  function terrClose() {
    terrDrawer.classList.remove('open');
    terr.armed = null;
    frame.classList.remove('painting');
    hideCursor();
  }
  document.getElementById('dlterr').onclick = function () {
    if (terrDrawer.classList.contains('open')) { terrClose(); return; }
    if (typeof closeDrawers === 'function') closeDrawers('terr');
    terrDrawer.classList.add('open');
    rearm();
  };
  document.getElementById('dltclose').onclick = terrClose;

  fetch(terrUrl('world'))
    .then(function (r) { return r.json(); })
    .then(function (world) {
      if (!world.ok || !world.cells_w) {
        terrSay('No world yet. Import the map first with tools/dodoland_terrain_import.py.', true);
        if (typeof loaded === 'function') { loaded('ground'); loaded('reach'); }
        return;
      }
      terrSetup(world);
      rearm();
      loadInfluence();
      loadRoads();
      terrDefs();
      terrOverview();
      terrDetail();
      // The reference is hidden when the overview arrives (terrOverview): the
      // terrain *is* the map now, and the upload is only there to trace against.
    })
    .catch(function () {
      terrSay('The world could not be loaded.', true);
      if (typeof loaded === 'function') { loaded('ground'); loaded('reach'); }
    });
"""
