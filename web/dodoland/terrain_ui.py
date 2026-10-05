"""
The terrain layer on the map page, and the brush that edits it.

Deliberately *on the map page* rather than a page of its own. The map already
owns panning, zooming, viewport culling and the coordinate maths, and the one
time this project drew its own second view of the same world the two
disagreed — the panel used to draw its own markers and consequently showed
something different from every other surface. A second pan-and-zoom would be
that mistake again, one layer down.

**Three layers inside the world, in this order.** The uploaded map is kept as an
admin *reference* and can be faded to nothing; the terrain is drawn over it; the
towns and decor sit on top of both. The reference is what you trace while
correcting the import, which is the only reason it still exists.

**Detail arrives with the zoom, the same bargain the towns make.** One coarse
request draws the whole continent; full-resolution chunks are fetched only for
what is on screen and only once anybody is close enough for a cell to be worth a
pixel. Asking for four million cells to look at a continent would be the same
mistake as shipping three hundred pre-rendered settlements to look at a map.
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

/* The brush's own drawer, on the left like the toolkit and never open with it. */
.dlterrdrawer { left: 0; right: auto; border-left: 0;
  border-right: 1px solid var(--edge); transform: translateX(-100%);
  box-shadow: 6px 0 24px rgba(0,0,0,.28); }
.dlterrdrawer.open { transform: translateX(0); }
.dltkinds { flex: 1 1 auto; overflow-y: auto; padding: 0 14px 12px; }
.dltkind { display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 7px 9px; margin-bottom: 5px; border: 1px solid var(--edge);
  border-radius: 9px; background: var(--deep); color: inherit; font: inherit;
  font-size: 13px; cursor: pointer; text-align: left; }
.dltkind:hover { border-color: var(--lantern); }
.dltkind.on { border-color: var(--lantern); background: var(--paper);
  box-shadow: 0 0 0 2px var(--lantern) inset; }
.dltswatch { width: 20px; height: 20px; border-radius: 5px; flex: 0 0 auto;
  border: 1px solid rgba(0,0,0,.45); }
.dltrule { margin-left: auto; font-size: 10px; opacity: .72; white-space: nowrap; }
.dltrow { display: flex; align-items: center; gap: 8px; padding: 10px 14px;
  border-top: 1px solid var(--edge); font-size: 12px; color: var(--soft); }
.dltrow input[type=range] { flex: 1 1 auto; min-width: 50px; }
.dltmsg { margin: 0; padding: 0 14px 12px; font-size: 12px; color: var(--soft); }
.dltmsg.bad { color: #c0392b; font-weight: 600; }
.dlthint { margin: 0; padding: 0 14px 8px; font-size: 12px; color: var(--soft); }
"""

DRAWER = """
<aside class="dldrawer dlterrdrawer" id="dlterrdrawer">
  <div class="dldhead">
    <b>Terrain</b>
    <button class="dlghost" id="dltclose">&times;</button>
  </div>
  <p class="dlthint">Pick a ground, then drag on the map to paint it. The
  uploaded map is underneath as a reference &mdash; fade it with the slider.</p>
  <div class="dltkinds" id="dltkinds"></div>
  <div class="dltrow">
    <label style="flex:1 1 auto;display:flex;align-items:center;gap:8px">Brush
      <input type="range" id="dltradius" min="0" max="40" step="1" value="6">
      <span id="dltradiusn" style="min-width:2.4em">6</span></label>
  </div>
  <div class="dltrow">
    <button class="dlghost" id="dltundo" disabled>&#8630; Undo</button>
    <button class="dlghost" id="dltredo" disabled>&#8631; Redo</button>
    <span id="dltdepth" style="margin-left:auto;opacity:.7"></span>
  </div>
  <div class="dltrow">
    <label style="flex:1 1 auto;display:flex;align-items:center;gap:8px">Reference
      <input type="range" id="dltref" min="0" max="100" step="5" value="0"></label>
    <button class="dlghost" id="dltoggleterr">Hide terrain</button>
  </div>
  <p class="dltmsg" id="dltmsg"></p>
</aside>
"""

SCRIPT = r"""
  // --- the terrain layer ------------------------------------------------- //
  var terr = {world: null, armed: null, radius: 6, have: {}, shown: true,
              busy: false, ver: 0};
  var terrLayer = document.createElement('div');
  terrLayer.className = 'dlterrain';
  var terrDrawer = document.getElementById('dlterrdrawer');
  var terrMsg = document.getElementById('dltmsg');

  function terrSay(text, bad) {
    if (!terrMsg) return;
    terrMsg.textContent = text || '';
    terrMsg.classList.toggle('bad', !!bad);
  }

  function terrUrl(path, query) {
    return '/guild/' + D.gid + '/dodoland/terrain/' + path + (query || '');
  }

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
      '<g id="dltover"></g><g id="dltdetail"></g></svg>';
    world_el().appendChild(terrLayer);
    renderKinds();
  }
  function world_el() { return document.getElementById('dlworld'); }

  function renderKinds() {
    var box = document.getElementById('dltkinds');
    if (!box || !terr.world) return;
    box.innerHTML = terr.world.kinds.map(function (k, i) {
      // What a ground *does* is the thing an admin is choosing between, so it
      // is on the button rather than two clicks away.
      var rule = k.build ? 'buildable'
               : (k.clearable ? 'clearable' : (k.grow !== null ? 'open' : 'blocked'));
      return '<button class="dltkind' + (terr.armed === i ? ' on' : '') +
        '" data-k="' + i + '">' +
        '<span class="dltswatch" style="background:' + k.colour + '"></span>' +
        escapeHtml(k.label) + '<span class="dltrule">' + rule + '</span></button>';
    }).join('');
    box.querySelectorAll('.dltkind').forEach(function (el) {
      el.onclick = function () {
        var i = parseInt(el.dataset.k, 10);
        terr.armed = (terr.armed === i) ? null : i;
        frame.classList.toggle('painting', terr.armed !== null);
        terrSay(terr.armed === null ? '' : 'Drag on the map to paint.');
        renderKinds();
      };
    });
  }

  function terrOverview() {
    fetch(terrUrl('overview', '?v=' + terr.ver))
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (svg) {
        var g = document.getElementById('dltover');
        if (!g || !terr.world) return;
        // The overview is drawn at one cell per `overview_step`, so it has to be
        // scaled back up into the full cell grid the <svg> is laid out in.
        g.setAttribute('transform', 'scale(' + terr.world.overview_step + ')');
        g.innerHTML = svg;
      });
  }

  // Which chunks the viewport covers, in chunk coordinates.
  function visibleChunks() {
    if (!terr.world || !nat.w) return null;
    var cw = terr.world.cells_w, ch = terr.world.cells_h;
    var perCellX = (nat.w * view.k) / cw;
    // The detail tier is textured, and a motif is eight cells across — below
    // about a pixel per cell it is sub-pixel noise that aliases into a shimmer
    // rather than resolving into trees. The flat overview is showing the same
    // coastline until then, and fetches nothing.
    if (perCellX < 1.0) return null;
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
    // One request for the whole rectangle. Per chunk would be sixty requests
    // on every pan.
    fetch(terrUrl('chunks', '?r=' + box.x0 + ',' + box.y0 + ',' + box.x1 + ',' + box.y1))
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

  // --- painting ---------------------------------------------------------- //
  // Screen -> cell. The world element is the base image's natural size, and the
  // grid is laid over it, so one conversion serves both.
  function cellAt(clientX, clientY) {
    if (!terr.world || !nat.w) return null;
    var b = frame.getBoundingClientRect();
    var fx = (clientX - b.left - view.x) / (nat.w * view.k);
    var fy = (clientY - b.top - view.y) / (nat.h * view.k);
    return [Math.round(fx * terr.world.cells_w), Math.round(fy * terr.world.cells_h)];
  }

  var stroke = null;
  function strokeStart(ev) {
    var cell = cellAt(ev.clientX, ev.clientY);
    if (!cell) return false;
    stroke = [cell];
    return true;
  }
  function strokeMove(ev) {
    if (!stroke) return;
    var cell = cellAt(ev.clientX, ev.clientY);
    if (!cell) return;
    var last = stroke[stroke.length - 1];
    // Thin the stroke: a pointer reports far more often than a cell changes,
    // and sending every sample is thousands of duplicate points.
    if (Math.abs(cell[0] - last[0]) + Math.abs(cell[1] - last[1]) >= 1) {
      stroke.push(cell);
    }
  }
  function strokeEnd() {
    if (!stroke || terr.armed === null) { stroke = null; return; }
    var points = stroke.slice(0, 4000);
    stroke = null;
    terrSay('Painting ' + points.length + ' points…');
    fetch('/api/guild/' + D.gid + '/dodoland/terrain/paint', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind: terr.armed, radius: terr.radius, points: points})
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { terrSay(res.error || 'That did not work.', true); return; }
      terrSay(res.cells.toLocaleString() + ' cells, ' + res.chunks + ' chunks.');
      terrApplyChange(res);
    }).catch(function (err) { terrSay(String(err), true); });
  }

  // Only what changed. Refetching the whole viewport and rebuilding the
  // overview after every stroke was about a second of lag for a change that
  // touched four chunks.
  var overviewTimer = null;
  function terrApplyChange(res) {
    terr.ver = res.version;
    (res.touched || []).forEach(function (k) {
      delete terr.have[k[0] + ',' + k[1] + ',' + (res.version - 1)];
      delete terr.have[k[0] + ',' + k[1] + ',' + res.version];
    });
    terrDetail();
    setUndo(res.undo, res.redo);
    // The coarse view is only on screen when nobody is zoomed in, so it can
    // wait for a pause rather than being rebuilt mid-stroke.
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

  // --- controls ---------------------------------------------------------- //
  var undoBtn = document.getElementById('dltundo');
  if (undoBtn) undoBtn.onclick = function () { terrStep(false); };
  var redoBtn = document.getElementById('dltredo');
  if (redoBtn) redoBtn.onclick = function () { terrStep(true); };
  // The shortcuts everybody already has in their fingers. Only while the
  // terrain drawer is open, so they cannot fire at somebody editing a town name.
  window.addEventListener('keydown', function (ev) {
    if (!terrDrawer.classList.contains('open')) return;
    if (!(ev.ctrlKey || ev.metaKey)) return;
    var key = (ev.key || '').toLowerCase();
    if (key === 'z' && !ev.shiftKey) { ev.preventDefault(); terrStep(false); }
    else if (key === 'y' || (key === 'z' && ev.shiftKey)) {
      ev.preventDefault(); terrStep(true);
    }
  });
  var radius = document.getElementById('dltradius');
  if (radius) radius.oninput = function () {
    terr.radius = parseInt(radius.value, 10) || 0;
    document.getElementById('dltradiusn').textContent = terr.radius;
  };
  var ref = document.getElementById('dltref');
  if (ref) ref.oninput = function () {
    world_el().style.setProperty('--refop', (parseInt(ref.value, 10) || 0) / 100);
  };
  var terrToggle = document.getElementById('dltoggleterr');
  if (terrToggle) terrToggle.onclick = function () {
    terr.shown = !terr.shown;
    terrLayer.classList.toggle('off', !terr.shown);
    terrToggle.textContent = terr.shown ? 'Hide terrain' : 'Show terrain';
  };
  document.getElementById('dlterr').onclick = function () {
    terrDrawer.classList.toggle('open');
    drawer.classList.remove('open');
    if (typeof kitDrawer !== 'undefined') kitDrawer.classList.remove('open');
    if (typeof placeZoom === 'function') placeZoom();
  };
  document.getElementById('dltclose').onclick = function () {
    terrDrawer.classList.remove('open');
    terr.armed = null;
    frame.classList.remove('painting');
    renderKinds();
  };

  fetch(terrUrl('world'))
    .then(function (r) { return r.json(); })
    .then(function (world) {
      if (!world.ok || !world.cells_w) {
        terrSay('No world yet. Import the map first with ' +
                'tools/dodoland_terrain_import.py.', true);
        return;
      }
      terrSetup(world);
      // The texture patterns, once. Chunks reference them by id.
      fetch(terrUrl('defs')).then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (defs) {
          var g = document.getElementById('dltdefs');
          if (g && defs) g.innerHTML = defs;
        });
      terrOverview();
      terrDetail();
      // Start with the reference hidden: the terrain *is* the map now, and the
      // upload is only there to trace against.
      world_el().style.setProperty('--refop', 0);
    })
    .catch(function () { terrSay('The world could not be loaded.', true); });
"""
