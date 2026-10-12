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
.dlworld.hide-ground #dltshade { display: none; }
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
.dltsliders .dltshape { margin: 0; }
.dltsliders .dltshape button { padding: 4px 6px; font-size: 12px; }
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
    <span class="dltlabel">Shape</span><div class="dlseg dltshape" id="dltshape"><button data-shape="round" class="on" title="Round brush">&#9679; Round</button><button data-shape="square" title="Square brush: straight edges, for roads">&#9632; Square</button></div><span></span>
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
              radius: 12, shape: 'round', density: 1, soft: 0, sel: null, pattern: null,
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
    return D.ep.base + '/terrain/' + path + (query || '');
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
      '<g id="dltover"></g><g id="dltdetail"></g><g id="dltshade"></g><g id="dltinfl"></g><g id="dltroads"></g><g id="dltwalls"></g>' +
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
    // The shading for close up, loaded the same way and kept out of sight
    // until the tiles fade in.
    var shadeUrl = terrUrl('shade', '?v=' + encodeURIComponent(terr.ver));
    var sp = new Image();
    sp.onload = function () {
      var g = document.getElementById('dltshade');
      if (!g || !terr.world) return;
      g.innerHTML = '<image href="' + shadeUrl + '" x="0" y="0" width="' + terr.world.cells_w +
        '" height="' + terr.world.cells_h + '" preserveAspectRatio="none" style="pointer-events:none"/>';
    };
    sp.src = shadeUrl;
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
    var from = (D.sizes.lod || {}).tiles;
    if (from === undefined) from = 2.5;
    var fade = Math.max(0, Math.min(1, (perCellX - from) / 2)).toFixed(2);
    if (detail) detail.style.opacity = fade;
    // The shading comes in with the tiles: far out it is already in the picture.
    var shadeG = document.getElementById('dltshade');
    if (shadeG) shadeG.style.opacity = fade;
    if (perCellX < from && total > 0) return null;
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

  // --- the close-up ground, baked ------------------------------------------ //
  // Each 64-cell chunk is drawn once into a canvas — its textures, and where
  // two grounds meet, one faded into the other through a soft mask — and shown
  // as a plain picture. Moving and scaling finished pictures is what the
  // browser does fastest, so panning costs the same however much is drawn.
  // A stroke re-bakes only the chunks it touched and their neighbours.
  var bake = {kinds: null, art: '', rle: {}, cells: {}, known: {}, gen: {}, drawn: {},
              imgs: {}, blocks: {}, fetching: false, queued: false};
  var BLUR_OK = (function () {
    try { var c = document.createElement('canvas').getContext('2d'); return typeof c.filter === 'string'; }
    catch (e) { return false; }
  })();
  function bakeDecode(rle) {
    var out = new Uint16Array(4096), i = 0;
    String(rle || '').split(' ').forEach(function (part) {
      var x = part.indexOf('x');
      if (x < 0) return;
      var n = +part.slice(0, x), v = +part.slice(x + 1);
      out.fill(v, i, Math.min(4096, i + n));
      i += n;
    });
    return out;
  }
  function bakeBump(cx, cy) {
    for (var dy = -1; dy <= 1; dy++)
      for (var dx = -1; dx <= 1; dx++) {
        var k = (cx + dx) + ',' + (cy + dy);
        bake.gen[k] = (bake.gen[k] || 0) + 1;
      }
  }
  // After a stroke or an undo: forget those chunks' cells, so they are read
  // again, and mark them and their neighbours (whose blends reach them) stale.
  function bakeTouched(touched) {
    touched.forEach(function (t) { delete bake.known[t[0] + ',' + t[1]]; bakeBump(t[0], t[1]); });
  }
  function bakeImg(vid) {
    var im = bake.imgs[vid];
    if (!im) {
      im = bake.imgs[vid] = new Image();
      im.decoding = 'async';
      im.onload = function () { bakeSoon(); };
      im.src = bake.art + vid;
    }
    return im.complete && im.naturalWidth ? im : null;
  }
  // A kind's 4x4 block of tiles at a detail, once; null until its art is in.
  function bakeBlock(k, res) {
    var key = k + '@' + res;
    if (bake.blocks[key]) return bake.blocks[key];
    var lay = bake.kinds[k].layout, imgs = [];
    for (var i = 0; i < lay.block.length; i++) {
      var im = bakeImg(lay.block[i]);
      if (!im) return null;
      imgs.push(im);
    }
    var cw = lay.size[0] * res, ch = lay.size[1] * res;
    var cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.round(cw * 4)); cv.height = Math.max(1, Math.round(ch * 4));
    var ctx = cv.getContext('2d');
    // Pixel art stays crisp when drawn larger; drawn smaller it is smoothed,
    // or a field shimmers.
    ctx.imageSmoothingEnabled = res < (lay.px || 16);
    for (var j = 0; j < 4; j++)
      for (var x = 0; x < 4; x++)
        ctx.drawImage(imgs[j * 4 + x], Math.round(x * cw), Math.round(j * ch),
                      Math.round((x + 1) * cw) - Math.round(x * cw), Math.round((j + 1) * ch) - Math.round(j * ch));
    bake.blocks[key] = cv;
    return cv;
  }
  // The fill for kind k on a canvas whose top-left is world cell (ox, oy):
  // its block repeated from the world's origin, so neighbouring chunks meet.
  function bakeStyle(ctx, k, res, ox, oy) {
    var kind = bake.kinds[k];
    if (!kind.layout) return kind.fill;
    var block = bakeBlock(k, res);
    if (!block) return null;
    var pat = ctx.createPattern(block, 'repeat');
    var bw = block.width, bh = block.height;
    var tx = -((ox * res) % bw), ty = -((oy * res) % bh);
    if (pat.setTransform) pat.setTransform(new DOMMatrix([1, 0, 0, 1, tx, ty]));
    return pat;
  }
  // The cells of a square around a chunk (margin m), from it and its neighbours.
  function bakeArea(cx, cy, m) {
    var A = 64 + 2 * m, out = new Uint16Array(A * A);
    for (var y = 0; y < A; y++) {
      var gy = cy * 64 - m + y, ky = Math.floor(gy / 64), ly = gy - ky * 64;
      for (var x = 0; x < A; x++) {
        var gx = cx * 64 - m + x, kx = Math.floor(gx / 64), lx = gx - kx * 64;
        var cells = bake.cells[kx + ',' + ky];
        out[y * A + x] = cells ? cells[ly * 64 + lx] : 0;
      }
    }
    return out;
  }
  // Rows of runs where test(value) holds, as one path in canvas pixels.
  function bakePath(cells, A, res, x0, y0, n, test) {
    var path = new Path2D();
    for (var y = y0; y < y0 + n; y++) {
      var x = x0;
      while (x < x0 + n) {
        if (!test(cells[y * A + x])) { x++; continue; }
        var s = x;
        while (x < x0 + n && test(cells[y * A + x])) x++;
        path.rect((s - x0) * res, (y - y0) * res, (x - s) * res, res);
      }
    }
    return path;
  }
  // A region's border as closed loops of cell corners (the region always on
  // one side), corners only — the same walk as influence.loops.
  function bakeLoops(cells, A, test) {
    var next = new Map();
    function add(ax, ay, bx, by) {
      var k = ax * 65536 + ay, l = next.get(k);
      if (!l) next.set(k, l = []);
      l.push([bx, by]);
    }
    for (var y = 0; y < A; y++) {
      for (var x = 0; x < A; x++) {
        if (!test(cells[y * A + x])) continue;
        if (y === 0 || !test(cells[(y - 1) * A + x])) add(x, y, x + 1, y);
        if (x === A - 1 || !test(cells[y * A + x + 1])) add(x + 1, y, x + 1, y + 1);
        if (y === A - 1 || !test(cells[(y + 1) * A + x])) add(x + 1, y + 1, x, y + 1);
        if (x === 0 || !test(cells[y * A + x - 1])) add(x, y + 1, x, y);
      }
    }
    var loops = [];
    while (next.size) {
      var startKey = next.keys().next().value, sx = Math.floor(startKey / 65536), sy = startKey % 65536;
      var loop = [[sx, sy]], hx = sx, hy = sy;
      while (true) {
        var k = hx * 65536 + hy, ways = next.get(k);
        if (!ways || !ways.length) { next.delete(k); break; }
        var step = ways.pop();
        if (!ways.length) next.delete(k);
        if (step[0] === sx && step[1] === sy) break;
        loop.push(step);
        hx = step[0]; hy = step[1];
      }
      var corners = loop.filter(function (pt, i) {
        var a = loop[(i - 1 + loop.length) % loop.length], c = loop[(i + 1) % loop.length];
        return (pt[0] - a[0]) !== (c[0] - pt[0]) || (pt[1] - a[1]) !== (c[1] - pt[1]);
      });
      if (corners.length >= 3) loops.push(corners);
    }
    return loops;
  }
  // A region on a half-cell grid, with a bridge wherever two of its cells
  // touch only at a corner: a road painted diagonally is one shape, not beads.
  function bakeHalf(area, A, test) {
    var inside = new Uint8Array(A * A), B = A * 2, out = new Uint8Array(B * B);
    for (var i = 0; i < A * A; i++) inside[i] = test(area[i]) ? 1 : 0;
    for (var y = 0; y < A; y++)
      for (var x = 0; x < A; x++)
        if (inside[y * A + x]) {
          var o = (2 * y) * B + 2 * x;
          out[o] = out[o + 1] = out[o + B] = out[o + B + 1] = 1;
        }
    for (var y = 0; y < A - 1; y++)
      for (var x = 0; x < A - 1; x++) {
        var a = inside[y * A + x], b = inside[y * A + x + 1], c = inside[(y + 1) * A + x], d = inside[(y + 1) * A + x + 1];
        if (a && d && !b && !c) { out[(2 * y + 1) * B + 2 * x + 2] = 1; out[(2 * y + 2) * B + 2 * x + 1] = 1; }
        if (b && c && !a && !d) { out[(2 * y + 1) * B + 2 * x + 1] = 1; out[(2 * y + 2) * B + 2 * x + 2] = 1; }
      }
    return out;
  }
  // An outline evened out along its own length: the corner points resampled
  // every half cell, then each moved to a Gaussian-weighted average of its
  // neighbours along the outline (a Gaussian of ``reach`` half-cells). Stairs and
  // spikes shorter than that even out into slopes and curves; a long side
  // stays straight, a big shape keeps its size (it shrinks only by about
  // reach squared over its radius).
  function bakeResample(loop) {
    var out = [];
    for (var i = 0; i < loop.length; i++) {
      var a = loop[i], b = loop[(i + 1) % loop.length];
      var n = Math.max(1, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1])));
      for (var j = 0; j < n; j++) out.push([a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n]);
    }
    return out;
  }
  function bakeGauss(pts, reach) {
    var n = pts.length, sigma = reach, r = Math.ceil(sigma * 3);
    if (n < 4 || sigma < 0.25) return pts;
    r = Math.min(r, Math.floor((n - 1) / 2));
    var w = [], total = 0;
    for (var j = -r; j <= r; j++) { var v = Math.exp(-j * j / (2 * sigma * sigma)); w.push(v); total += v; }
    var out = [];
    for (var i = 0; i < n; i++) {
      var x = 0, y = 0;
      for (var j = -r; j <= r; j++) {
        var q = pts[((i + j) % n + n) % n], k = w[j + r];
        x += q[0] * k; y += q[1] * k;
      }
      out.push([x / total, y / total]);
    }
    return out;
  }
  // The smoothed outline of a region of the area, as a path in pixels with
  // ``m`` cells of margin taken off.
  function bakeSmoothPath(area, A, m, res, test, strength) {
    var path = new Path2D(), s = Math.min(1, strength);
    var reach = 2 * (D.sizes.straighten === undefined ? 1.5 : D.sizes.straighten) * s;
    bakeLoops(bakeHalf(area, A, test), A * 2, function (v) { return v === 1; }).forEach(function (loop) {
      // Half-cell units throughout, then back to cells.
      var pts = bakeGauss(bakeResample(loop), reach);
      pts.forEach(function (pt, i) {
        var x = (pt[0] / 2 - m) * res, y = (pt[1] / 2 - m) * res;
        if (i) path.lineTo(x, y); else path.moveTo(x, y);
      });
      path.closePath();
    });
    return path;
  }
  function bakeChunk(key, res) {
    var at = key.split(','), cx = +at[0], cy = +at[1];
    var K = bake.kinds, width = D.sizes.blend_width || 0, strength = D.sizes.blend_strength || 0;
    var smooth = Math.max(0, D.sizes.smoothing || 0);
    var blend = BLUR_OK && width > 0 && strength > 0;
    var coastK = D.sizes.coast_shading || 0, coastW = D.sizes.coast_width || 0;
    var coast = BLUR_OK && coastK > 0 && coastW > 0;
    // Everything is drawn on a canvas a margin larger than the chunk, so a
    // curve, a blend or the coast's shading carries over the chunk line just
    // as the neighbour draws it; the chunk is cut out at the end.
    var m = Math.max(blend ? Math.ceil(width) + 1 : 0,
                     smooth > 0 ? Math.ceil(2 * (D.sizes.straighten || 1.5)) + 2 : 0,
                     coast ? Math.ceil(coastW * 2.4) + 1 : 0, 1);
    var A = 64 + 2 * m, big = A * res, size = 64 * res, ready = true;
    var area = bakeArea(cx, cy, m);
    var near = {};
    for (var i = 0; i < A * A; i++) near[area[i]] = 1;
    function known(v) { return v && K[v]; }
    function isLand(v) { return v && K[v] && K[v].land; }
    function canvas() { var c = document.createElement('canvas'); c.width = c.height = big; return c; }
    var kinds = Object.keys(near).map(Number).filter(known).sort(function (a, b) { return a - b; });
    // Each kind's shape, once. Smoothed, a kind's shape is the outline of
    // itself *and everything ranked above it*: drawn lowest first, where a
    // corner is rounded off what shows is the ground beneath. The lowest
    // fills all known ground. Unsmoothed, each is its own cells.
    var shapes = {};
    kinds.forEach(function (k, i) {
      shapes[k] = smooth > 0 && i === 0 ? null
        : smooth > 0 ? bakeSmoothPath(area, A, 0, res, function (v) { return known(v) && v >= k; }, smooth)
        : bakePath(area, A, res, 0, 0, A, function (v) { return v === k; });
    });
    var knownClip = bakePath(area, A, res, 0, 0, A, known);
    function fillShape(c, k) {
      if (shapes[k]) c.fill(shapes[k], 'evenodd'); else c.fillRect(0, 0, big, big);
    }
    // Land and water as drawn, from the very same shapes in the same order,
    // so the blend and the coast's shading meet the fills exactly.
    var landMask = canvas(), waterMask = canvas();
    if (blend || coast) {
      var lc = landMask.getContext('2d');
      lc.save(); lc.clip(knownClip); lc.fillStyle = '#fff';
      kinds.forEach(function (k) {
        lc.globalCompositeOperation = K[k].land ? 'source-over' : 'destination-out';
        fillShape(lc, k);
      });
      lc.restore();
      var wc = waterMask.getContext('2d');
      wc.fillStyle = '#fff'; wc.fill(knownClip);
      wc.globalCompositeOperation = 'destination-out'; wc.drawImage(landMask, 0, 0);
    }
    // A shape (or picture) blurred, kept to a mask, and tinted.
    function soft(draw, sigma, keep, tint) {
      var src = canvas(), sc = src.getContext('2d');
      sc.fillStyle = '#fff'; sc.strokeStyle = '#fff';
      draw(sc);
      var out = canvas(), oc = out.getContext('2d');
      oc.filter = 'blur(' + Math.max(0.5, sigma * res).toFixed(1) + 'px)';
      oc.drawImage(src, 0, 0);
      oc.filter = 'none';
      oc.globalCompositeOperation = 'destination-in'; oc.drawImage(keep, 0, 0);
      oc.globalCompositeOperation = 'source-in'; oc.fillStyle = tint; oc.fillRect(0, 0, big, big);
      return out;
    }
    var cv = canvas(), ctx = cv.getContext('2d');
    var lowestLand = Infinity;
    kinds.forEach(function (k) { if (K[k].land) lowestLand = Math.min(lowestLand, k); });
    kinds.forEach(function (k) {
      var style = bakeStyle(ctx, k, res, cx * 64 - m, cy * 64 - m);
      if (style === null) { ready = false; return; }
      ctx.save(); ctx.clip(knownClip); ctx.fillStyle = style; fillShape(ctx, k); ctx.restore();
      // The blend, land into land: the kind's shape grown by half the width
      // and blurred, kept to land as drawn, in the kind's own texture. Kinds
      // ranked above are drawn after and cover what spilled onto them.
      if (!blend || !K[k].land || k <= lowestLand) return;
      // Its land only: smoothed, its fill shape takes in the water ranked
      // above it, and a blend must not spill from a lake's shore.
      var from = smooth > 0 ? bakeSmoothPath(area, A, 0, res, function (v) { return isLand(v) && v >= k; }, smooth)
                            : shapes[k];
      var spill = soft(function (c) {
        c.lineWidth = width * res; c.lineJoin = 'round';
        c.fill(from, 'evenodd'); c.stroke(from);
      }, width / 3, landMask, style);
      ctx.globalAlpha = strength; ctx.drawImage(spill, 0, 0); ctx.globalAlpha = 1;
    });
    // The coast: land a little darker towards the water, water a little
    // brighter with surf, from the shore as drawn.
    if (coast && kinds.some(function (k) { return !K[k].land; }) && kinds.some(function (k) { return K[k].land; })) {
      // Half strength at the shore line (the blur), so twice the old values.
      ctx.globalAlpha = Math.min(1, 0.36 * coastK);
      ctx.drawImage(soft(function (c) { c.drawImage(waterMask, 0, 0); }, coastW * 0.8, landMask, '#000'), 0, 0);
      ctx.globalAlpha = Math.min(1, 0.7 * Math.min(1, coastK));
      ctx.drawImage(soft(function (c) { c.drawImage(landMask, 0, 0); }, coastW * 0.5, waterMask, '#fff'), 0, 0);
      ctx.globalAlpha = 1;
    }
    var out = document.createElement('canvas');
    out.width = out.height = size;
    out.getContext('2d').drawImage(cv, m * res, m * res, size, size, 0, 0, size, size);
    return {canvas: out, ready: ready};
  }
  function bakeShow(key, res) {
    var made = bakeChunk(key, res), at = key.split(',');
    var g = document.getElementById('dltdetail');
    if (!g) return;
    var gen = bake.gen[key] || 0;
    made.canvas.toBlob(function (blob) {
      if (!blob) return;
      var url = URL.createObjectURL(blob), old = bake.drawn[key];
      var el = old && old.el && old.el.isConnected ? old.el
        : document.createElementNS('http://www.w3.org/2000/svg', 'image');
      // A hair over 64 cells, so neighbouring pictures never show a seam.
      el.setAttribute('x', at[0] * 64); el.setAttribute('y', at[1] * 64);
      el.setAttribute('width', 64.04); el.setAttribute('height', 64.04);
      el.setAttribute('preserveAspectRatio', 'none');
      el.setAttribute('style', 'image-rendering:pixelated;pointer-events:none');
      el.setAttribute('href', url);
      if (!el.isConnected) g.appendChild(el);
      if (old && old.url) URL.revokeObjectURL(old.url);
      bake.drawn[key] = {el: el, url: url, res: res, gen: gen, ready: made.ready};
    }, 'image/png');
    // Claimed now, so it is not baked twice while the picture encodes.
    bake.drawn[key] = Object.assign({}, bake.drawn[key] || {}, {res: res, gen: gen, ready: made.ready, pending: true});
  }
  function bakeRes(per) {
    var want = per * (window.devicePixelRatio || 1), res = 2;
    while (res < want && res < 64) res *= 2;
    return Math.min(res, D.sizes.ground_detail || 16);
  }
  function bakeSoon() {
    if (bake.queued) return;
    bake.queued = true;
    requestAnimationFrame(function () { bake.queued = false; terrDetail(); });
  }
  function bakeFetch(box) {
    if (bake.fetching) return;
    // One chunk more all round than is drawn: a chunk's blend reaches in from
    // its neighbours.
    var x0 = Math.max(0, box.x0 - 1), y0 = Math.max(0, box.y0 - 1);
    var x1 = Math.min(terr.world.chunks_x - 1, box.x1 + 1), y1 = Math.min(terr.world.chunks_y - 1, box.y1 + 1);
    var missing = false;
    for (var cy = y0; cy <= y1 && !missing; cy++)
      for (var cx = x0; cx <= x1; cx++) if (!bake.known[cx + ',' + cy]) { missing = true; break; }
    if (!missing && bake.kinds) return;
    bake.fetching = true;
    fetch(terrUrl('rle', '?r=' + [x0, y0, x1, y1].join(',') + '&v=' + encodeURIComponent(terr.ver)))
      .then(function (r) { return r.ok ? r.json() : {ok: false}; })
      .then(function (res) {
        bake.fetching = false;
        if (!res.ok) return;
        if (!bake.kinds || res.kinds.length !== bake.kinds.length) bake.blocks = {};
        bake.kinds = res.kinds;
        bake.art = res.art;
        Object.keys(res.chunks).forEach(function (key) {
          var rle = res.chunks[key];
          bake.known[key] = true;
          if (bake.rle[key] !== rle) {
            bake.rle[key] = rle;
            bake.cells[key] = rle ? bakeDecode(rle) : null;
            var at = key.split(',');
            bakeBump(+at[0], +at[1]);
          }
        });
        bakeSoon();
      })
      .catch(function () { bake.fetching = false; });
  }
  // Called whenever the view moves (and after a stroke): fetch what is
  // missing, bake what is due a few chunks a frame, let go of the furthest.
  function terrDetail() {
    if (!terr.world) return;
    var box = visibleChunks();
    var g = document.getElementById('dltdetail');
    if (!g || !box) return;
    if ((box.x1 - box.x0 + 1) * (box.y1 - box.y0 + 1) > 400) return;
    bakeFetch(box);
    if (!bake.kinds) return;
    var per = (nat.w * view.k) / terr.world.cells_w, res = bakeRes(per), budget = 3, more = false;
    for (var cy = box.y0; cy <= box.y1; cy++) {
      for (var cx = box.x0; cx <= box.x1; cx++) {
        var key = cx + ',' + cy, d = bake.drawn[key];
        if (!bake.known[key]) { more = true; continue; }
        if (!bake.cells[key]) {
          if (d && d.el) { d.el.remove(); if (d.url) URL.revokeObjectURL(d.url); delete bake.drawn[key]; }
          continue;
        }
        var stale = !d || d.gen !== (bake.gen[key] || 0) || (!d.ready && !d.pending) ||
          (d.res < res && d.res < (D.sizes.ground_detail || 16));
        if (!stale) continue;
        if (budget-- > 0) bakeShow(key, res); else more = true;
      }
    }
    if (more) bakeSoon();
    var keys = Object.keys(bake.drawn), cap = D.sizes.ground_chunks || 300;
    if (keys.length > cap) {
      var mx = (box.x0 + box.x1) / 2, my = (box.y0 + box.y1) / 2;
      keys.sort(function (a, b) {
        var pa = a.split(','), pb = b.split(',');
        return (Math.abs(pb[0] - mx) + Math.abs(pb[1] - my)) - (Math.abs(pa[0] - mx) + Math.abs(pa[1] - my));
      });
      keys.slice(0, keys.length - cap).forEach(function (key) {
        var d = bake.drawn[key];
        if (d.el) d.el.remove();
        if (d.url) URL.revokeObjectURL(d.url);
        delete bake.drawn[key];
      });
    }
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
  var footprintFor = '';
  function footprint(r) {
    var shape = terr.armed === 'select' ? 'square' : terr.shape;
    if (footprintFor === r + shape) return;
    footprintFor = r + shape;
    var inside = {}, fill = [], line = [];
    function has(x, y) { return inside[x + ',' + y] === 1; }
    for (var dy = -r; dy <= r; dy++) {
      var run = -1;
      for (var dx = -r; dx <= r + 1; dx++) {
        var on = dx <= r && (shape === 'square' || dx * dx + dy * dy <= r * r);
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
    var body = {mode: 'brush', radius: terr.radius, shape: terr.shape, points: points.slice(0, 4000)};
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
    fetch(D.ep.paint, {
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
    bakeTouched(res.touched || []);
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
    fetch(D.ep.undo, {
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
  var inflFirst = fetch(D.ep.base + '/influence')
    .then(function (r) { return r.ok ? r.json() : {towns: []}; })
    .catch(function () { return {towns: []}; });
  function loadInfluence() {
    var ask = inflFirst || fetch(D.ep.base + '/influence')
      .then(function (r) { return r.ok ? r.json() : {towns: []}; });
    inflFirst = null;
    ask
      .then(function (res) {
        var g = document.getElementById('dltinfl');
        if (!g) return;
        D.influence = res.towns || [];
        if (typeof refreshPop === 'function') refreshPop();
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
    fetch(D.ep.base + '/roads')
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
  // Round or square; remembered per viewer.
  try { if (window.localStorage.getItem('dl-brush-shape') === 'square') terr.shape = 'square'; } catch (e) {}
  document.querySelectorAll('#dltshape button').forEach(function (b) {
    b.classList.toggle('on', b.dataset.shape === terr.shape);
    b.onclick = function () {
      terr.shape = b.dataset.shape;
      try { window.localStorage.setItem('dl-brush-shape', terr.shape); } catch (e) {}
      document.querySelectorAll('#dltshape button').forEach(function (o) { o.classList.toggle('on', o === b); });
      if (terr.armed && terr.armed !== 'select') footprint(terr.radius);
    };
  });
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
