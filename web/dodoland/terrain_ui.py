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
.dlterrain > svg, .dltdetail { position: absolute; left: 0; top: 0; width: 100%; height: 100%; }
.dltdetail canvas { position: absolute; display: block; image-rendering: pixelated; pointer-events: none; }
.dlworld .dltown, .dlworld .dlpiece { z-index: 5; }
.dlframe.painting { cursor: crosshair; }
/* Overlay lines a fixed number of screen pixels wide at any zoom.
   non-scaling-stroke alone undoes only the SVG's own viewBox; the zoom is a CSS
   transform on the world around it, which still scaled a 1.6px line by 50.
   --inv (one screen pixel in world units) undoes that too. */
.dltline { vector-effect: non-scaling-stroke; stroke-width: calc(1px * var(--inv, 1));
  stroke-linecap: square; }
.dltline.wide { stroke-width: calc(3px * var(--inv, 1)); }
.dlwall, .dlwall use { fill: none; stroke-linejoin: round; stroke-linecap: butt; }
#dltwalls defs path { fill: none; }
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
/* Select and Pattern are hidden for everyone; only the brush is left. */
#dlttools[hidden] { display: none; }
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
  <div class="dlseg" id="dlttools" hidden>
    <button data-tool="brush" class="on">Brush</button>
    <button data-tool="select" hidden>Select</button>
    <button data-tool="pattern" hidden>Pattern</button>
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
    // Below: the overview picture. Between: the close-up ground, each chunk
    // its own canvas, shown as it was drawn (an image per chunk inside the svg
    // had to be encoded, decoded and the whole svg redrawn for every one, which
    // at a change of detail was a second's freeze). Above: shading, areas,
    // roads, walls, the selection and the brush.
    var box = 'xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" ' +
      'preserveAspectRatio="none" viewBox="0 0 ' + world.cells_w + ' ' + world.cells_h + '"';
    terrLayer.innerHTML =
      '<svg ' + box + '><g id="dltdefs"></g><g id="dltover"></g></svg>' +
      '<div id="dltdetail" class="dltdetail"></div>' +
      '<svg ' + box + '><g id="dltshade"></g><g id="dltinfl"></g><g id="dltroads"></g><g id="dltwalls"></g>' +
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
  // Each 64-cell chunk is drawn once into a canvas and shown as a plain
  // picture. Moving and scaling finished pictures is what the browser does
  // fastest, so panning costs the same however much is drawn. A stroke
  // re-bakes only the chunks it touched and their neighbours.
  //
  // Drawn on a dual grid: every ground is laid at the cell *corners*. A corner
  // looks at the four cells round it; which of them hold this ground (or one
  // drawn after it) is a number 0-15, and the corner gets that one of sixteen
  // shapes - a rounded corner, a straight edge, an inner corner, a diagonal
  // join - made once per ground and detail (dualTiles). So an edge is a curve
  // wherever it turns, and baking a chunk is stamping small pictures and one
  // texture fill per ground: nothing traced, nothing blurred. A smart ground (a
  // 3 x 3 tileset) also gets its fringe - a shore's rocks and foam, a path's
  // pebbles - laid along the same curves from its edge tile.
  var bake = {kinds: null, art: '', rle: {}, cells: {}, known: {}, gen: {}, drawn: {},
              imgs: {}, blocks: {}, dual: {}, fetching: false, queued: false};
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
  // again, and mark them and their neighbours (whose edges reach them) stale.
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
  // A ground texture pushed into the background (dodoland_ground_*), the same
  // as terrainart.mute_rgb does to the zoomed-out picture's colours: contrast
  // pulled towards a mid-tone, saturation lowered, a little warm tint. Done
  // once to each texture as it is prepared, never while drawing.
  function groundMute(cv) {
    var M = D.sizes.ground_mute;
    if (!M || (M.contrast === 1 && M.saturation === 1 && !M.tint_amount)) return cv;
    var x = cv.getContext('2d'), w = cv.width, h = cv.height;
    if (!w || !h) return cv;
    var img = x.getImageData(0, 0, w, h), d = img.data;
    var c = M.contrast, s = M.saturation, mid = M.mid * 255, t = M.tint_amount;
    var tr = M.tint[0], tg = M.tint[1], tb = M.tint[2];
    for (var i = 0; i < d.length; i += 4) {
      if (!d[i + 3]) continue;
      var r = mid + (d[i] - mid) * c, g = mid + (d[i + 1] - mid) * c, b = mid + (d[i + 2] - mid) * c;
      var l = 0.299 * r + 0.587 * g + 0.114 * b;
      r = l + (r - l) * s; g = l + (g - l) * s; b = l + (b - l) * s;
      d[i] = r * (1 - t) + tr * t; d[i + 1] = g * (1 - t) + tg * t; d[i + 2] = b * (1 - t) + tb * t;
    }
    x.putImageData(img, 0, 0);
    return cv;
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
    bake.blocks[key] = groundMute(cv);
    return cv;
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
  function autoHash(x, y) {
    var h = (x * 374761393 + y * 668265263) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  // A tile's picture made ready to draw, once: a part of it (fractions x, y,
  // w, h of the picture after trimming ``inset`` off every side), made
  // seamless along 'x', 'y' or both ('xy'): the picture blended over itself
  // shifted by half, so repeated it has no seam. Null until it has loaded.
  function autoProc(vid, mode, inset, part) {
    part = part || [0, 0, 1, 1];
    var key = vid + '|' + mode + '|' + inset + '|' + part.join(',');
    bake.autoImgs = bake.autoImgs || {};
    if (bake.autoImgs[key]) return bake.autoImgs[key];
    var im = bakeImg(vid);
    if (!im) return null;
    var iw = im.naturalWidth * (1 - 2 * inset), ih = im.naturalHeight * (1 - 2 * inset);
    var w = Math.max(1, Math.round(iw * part[2])), h = Math.max(1, Math.round(ih * part[3]));
    function blank() { var c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
    var cv = blank();
    cv.getContext('2d').drawImage(im, im.naturalWidth * inset + iw * part[0], im.naturalHeight * inset + ih * part[1],
                                  w, h, 0, 0, w, h);
    function pass(src, horizontal) {
      var out = blank(), oc = out.getContext('2d');
      // The picture shifted by half, wrapped round: its seam is in the middle.
      if (horizontal) { oc.drawImage(src, -w / 2, 0); oc.drawImage(src, w / 2, 0); }
      else { oc.drawImage(src, 0, -h / 2); oc.drawImage(src, 0, h / 2); }
      // The picture itself over it, fading out towards its own edges.
      var top = blank(), tc = top.getContext('2d');
      tc.drawImage(src, 0, 0);
      var g = horizontal ? tc.createLinearGradient(0, 0, w, 0) : tc.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(0.3, '#000'); g.addColorStop(0.7, '#000'); g.addColorStop(1, 'rgba(0,0,0,0)');
      tc.globalCompositeOperation = 'destination-in'; tc.fillStyle = g; tc.fillRect(0, 0, w, h);
      oc.drawImage(top, 0, 0);
      return out;
    }
    if (mode.indexOf('x') >= 0) cv = pass(cv, true);
    if (mode.indexOf('y') >= 0) cv = pass(cv, false);
    bake.autoImgs[key] = groundMute(cv);
    return cv;
  }
  // A variation, faded out towards its edges so it melts into the ground.
  function autoSoft(vid, inset) {
    var key = vid + '|soft|' + inset;
    bake.autoImgs = bake.autoImgs || {};
    if (bake.autoImgs[key]) return bake.autoImgs[key];
    var src = autoProc(vid, '', inset);
    if (!src) return null;
    var cv = document.createElement('canvas'); cv.width = src.width; cv.height = src.height;
    var c = cv.getContext('2d'), r = Math.min(src.width, src.height) / 2;
    c.drawImage(src, 0, 0);
    var g = c.createRadialGradient(src.width / 2, src.height / 2, r * 0.45, src.width / 2, src.height / 2, r);
    g.addColorStop(0, '#000'); g.addColorStop(1, 'rgba(0,0,0,0)');
    c.globalCompositeOperation = 'destination-in'; c.fillStyle = g; c.fillRect(0, 0, src.width, src.height);
    bake.autoImgs[key] = cv;
    return cv;
  }

  // --- the dual grid's sixteen shapes ------------------------------------- //
  // A corner's four cells, as bits: 1 up-left, 2 up-right, 4 down-right, 8
  // down-left. Its tile spans from the up-left cell's centre (u, v = 0, 0) to
  // the down-right's (1, 1). At (u, v), dualAt gives f, how much the ground is
  // there (it is where f > 0.5: bilinear between the four cells, so a lone
  // corner is a rounded quarter, three an inner curve; two diagonal cells are
  // joined by a band, so a road painted diagonally is one road), d, how far in
  // from its edge that is (cells), and t, where along the edge (0-1, the same
  // at both ends, so a fringe runs on across neighbouring tiles).
  function dualAt(idx, u, v) {
    var a = idx & 1, b = (idx >> 1) & 1, c = (idx >> 2) & 1, e = (idx >> 3) & 1;
    var f = a * (1 - u) * (1 - v) + b * u * (1 - v) + c * u * v + e * (1 - u) * v;
    var gu = (b - a) * (1 - v) + (c - e) * v, gv = (e - a) * (1 - u) + (c - b) * u;
    var d = (f - 0.5) / Math.max(0.35, Math.hypot(gu, gv)), t;
    if (idx === 5 || idx === 10) {
      // Two diagonal cells: a band along the diagonal, 0.6 of a cell across.
      var off = idx === 5 ? Math.abs(u - v) / Math.SQRT2 : Math.abs(u + v - 1) / Math.SQRT2;
      var band = 0.5 + (0.3 - off) * 1.5;
      if (band > f) { f = band; d = 0.3 - off; }
      t = idx === 5 ? (u + v) / 2 : (u + 1 - v) / 2;
    } else if (idx === 3 || idx === 12) t = u;          // a straight edge across
    else if (idx === 6 || idx === 9) t = v;             // a straight edge down
    else {
      // A corner, rounded: along the curve round the odd one out of the four.
      // (the one ground corner of a rounded tip, the one bare corner of an inner curve).
      var odd = a + b + c + e === 1 ? idx : ~idx & 15;
      var ox = odd === 2 || odd === 4 ? 1 : 0, oy = odd === 4 || odd === 8 ? 1 : 0;
      t = Math.atan2(Math.abs(v - oy), Math.abs(u - ox)) / (Math.PI / 2);
    }
    return {f: f, d: d, t: t};
  }
  // The sixteen shapes of kind k at ``res`` pixels a cell, made once: masks
  // (white where the ground is, its edge feathered by dodoland_ground_feather)
  // and, for a smart ground, its fringe - the outer band of its top edge tile
  // laid along each edge, dodoland_ground_fringe of a cell deep, fading into
  // the inside. Null while a picture is still loading.
  function dualTiles(k, res) {
    var key = k + '@' + res;
    if (bake.dual[key]) return bake.dual[key];
    var kind = bake.kinds[k], auto = kind.auto, R = Math.max(2, Math.round(res));
    var feather = Math.max(0.001, D.sizes.ground_feather == null ? 0.08 : D.sizes.ground_feather);
    var depth = Math.max(0, Math.min(0.5, D.sizes.ground_fringe == null ? 0.5 : D.sizes.ground_fringe));
    var band = null, bw = 0, bh = 0;
    if (auto && depth > 0) {
      // One cell of the edge tile's outer band, seamless across, at this detail.
      var N = Math.max(1, Math.round(D.sizes.autotile_cells || 2));
      var inset = Math.max(0, Math.min(0.2, D.sizes.autotile_inset == null ? 0.03 : D.sizes.autotile_inset));
      var src = autoProc(auto.edges.top_center, 'x', inset, [0, 0, 1 / N, 1 / N]);
      if (!src) return null;
      bw = R; bh = Math.max(1, Math.round(R * depth));
      var bc = document.createElement('canvas'); bc.width = bw; bc.height = bh;
      var bx = bc.getContext('2d');
      bx.drawImage(src, 0, 0, src.width, src.height * depth, 0, 0, bw, bh);
      band = bx.getImageData(0, 0, bw, bh).data;
    }
    var out = {mask: [], fringe: []};
    for (var idx = 1; idx < 15; idx++) {
      var m = document.createElement('canvas'); m.width = m.height = R;
      var mx = m.getContext('2d'), mi = mx.createImageData(R, R), md = mi.data;
      var fr = null, fd = null;
      if (band) { fr = document.createElement('canvas'); fr.width = fr.height = R; fd = mx.createImageData(R, R); }
      for (var py = 0; py < R; py++)
        for (var px = 0; px < R; px++) {
          var at = dualAt(idx, (px + 0.5) / R, (py + 0.5) / R), o = (py * R + px) * 4;
          var x = (at.f - 0.5 + feather) / (2 * feather), alpha = x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x);
          md[o] = md[o + 1] = md[o + 2] = 255; md[o + 3] = Math.round(alpha * 255);
          if (!band || at.d < -feather || at.d >= depth) continue;
          var sx = Math.min(bw - 1, Math.floor(((at.t % 1) + 1) % 1 * bw));
          var sy = Math.min(bh - 1, Math.max(0, Math.floor(at.d / depth * bh)));
          var so = (sy * bw + sx) * 4, fade = Math.min(1, (depth - at.d) / (depth * 0.35));
          fd.data[o] = band[so]; fd.data[o + 1] = band[so + 1]; fd.data[o + 2] = band[so + 2];
          fd.data[o + 3] = Math.round(band[so + 3] * fade * alpha);
        }
      mx.putImageData(mi, 0, 0);
      out.mask[idx] = m;
      if (fr) { fr.getContext('2d').putImageData(fd, 0, 0); out.fringe[idx] = fr; }
    }
    bake.dual[key] = out;
    return out;
  }
  // The fill for kind k on a canvas whose top-left is world cell (ox, oy),
  // laid from the world's origin so neighbouring chunks meet: a smart ground's
  // seamless centre (N cells a tile) with its variations faded in now and
  // then, a tile pack's block of tiles, or a plain colour. Drawn into the box
  // [x, y, w, h] (pixels) with ``mode``: source-in takes the shape already on
  // ``c``, source-over fills the box. A variation goes only where ``here(x, y)``
  // (area cells) says the ground is. False while a picture is still loading.
  function bakeFill(c, k, res, ox, oy, A, box, mode, here) {
    var kind = bake.kinds[k];
    c.globalCompositeOperation = mode;
    if (kind.auto) {
      var N = Math.max(1, Math.round(D.sizes.autotile_cells || 2));
      var inset = Math.max(0, Math.min(0.2, D.sizes.autotile_inset == null ? 0.03 : D.sizes.autotile_inset));
      var share = D.sizes.autotile_variation || 0, set = kind.auto, span = N * res;
      var block = autoBlock(set, res);
      if (!block) return false;
      var pat = c.createPattern(block, 'repeat');
      if (pat.setTransform) pat.setTransform(new DOMMatrix([1, 0, 0, 1, -(((ox * res) % span) + span) % span,
                                                             -(((oy * res) % span) + span) % span]));
      c.fillStyle = pat; c.fillRect(box[0], box[1], box[2], box[3]);
      c.globalCompositeOperation = 'source-atop';
      if (set.center.length > 1 && share > 0) {
        for (var by = Math.floor(oy / N); by <= Math.floor((oy + A - 1) / N); by++)
          for (var bx = Math.floor(ox / N); bx <= Math.floor((ox + A - 1) / N); bx++) {
            if (autoHash(bx, by) >= share) continue;
            var hx = bx * N + Math.floor(N / 2) - ox, hy = by * N + Math.floor(N / 2) - oy;
            if (!here(hx, hy)) continue;
            var vid = set.center[1 + Math.floor(autoHash(by + 7919, bx + 104729) * (set.center.length - 1))];
            var soft = autoSoft(vid, inset);
            if (!soft) return false;
            c.drawImage(soft, (bx * N - ox) * res - span * 0.15, (by * N - oy) * res - span * 0.15, span * 1.3, span * 1.3);
          }
      }
    } else if (kind.layout) {
      var blk = bakeBlock(k, res);
      if (!blk) return false;
      var p2 = c.createPattern(blk, 'repeat');
      if (p2.setTransform) p2.setTransform(new DOMMatrix([1, 0, 0, 1, -((ox * res) % blk.width), -((oy * res) % blk.height)]));
      c.fillStyle = p2; c.fillRect(box[0], box[1], box[2], box[3]);
    } else {
      c.fillStyle = kind.fill; c.fillRect(box[0], box[1], box[2], box[3]);
    }
    c.globalCompositeOperation = 'source-over';
    return true;
  }
  // A smart ground's seamless centre at ``res`` pixels a cell, N cells a tile,
  // once; null until its picture is in.
  function autoBlock(set, res) {
    var N = Math.max(1, Math.round(D.sizes.autotile_cells || 2));
    var inset = Math.max(0, Math.min(0.2, D.sizes.autotile_inset == null ? 0.03 : D.sizes.autotile_inset));
    var bkey = set.center[0] + '|' + res + '|' + N + '|' + inset;
    bake.autoBlocks = bake.autoBlocks || {};
    if (bake.autoBlocks[bkey]) return bake.autoBlocks[bkey];
    var base = autoProc(set.center[0], 'xy', inset);
    if (!base) return null;
    var block = bake.autoBlocks[bkey] = document.createElement('canvas');
    block.width = block.height = Math.max(1, Math.round(N * res));
    var bk = block.getContext('2d'); bk.imageSmoothingEnabled = true;
    bk.drawImage(base, 0, 0, block.width, block.height);
    return block;
  }
  // Everything a chunk's bake would otherwise make the first time it meets a
  // ground, made while the map loads ("Preparing the ground" on the loading
  // card): every ground's pictures fetched, then at every detail the bake
  // uses, its textures, its sixteen corner shapes and its fringe - a few
  // milliseconds at a time, so the card keeps moving. Chunks baked afterwards
  // only stamp and fill.
  function bakeTake(res) {
    if (!bake.kinds || res.kinds.length !== bake.kinds.length) { bake.blocks = {}; bake.dual = {}; }
    bake.kinds = res.kinds;
    bake.art = res.art;
  }
  function bakeWarm() {
    function done() { if (typeof loaded === 'function') loaded('textures'); }
    fetch(terrUrl('rle', '?r=0,0,0,0&v=' + encodeURIComponent(terr.ver)))
      .then(function (r) { return r.ok ? r.json() : {ok: false}; })
      .then(function (res) {
        if (!res.ok) { done(); return; }
        bakeTake(res);
        var jobs = [], top = D.sizes.ground_detail || 16, levels = [];
        for (var r = 2; r <= top; r *= 2) levels.push(r);
        var inset = Math.max(0, Math.min(0.2, D.sizes.autotile_inset == null ? 0.03 : D.sizes.autotile_inset));
        // Ask for every picture now; each job waits until its own are in.
        bake.kinds.forEach(function (kind, k) {
          if (!kind) return;
          if (kind.auto) {
            kind.auto.center.concat([kind.auto.edges.top_center]).forEach(bakeImg);
            kind.auto.center.slice(1).forEach(function (vid) { jobs.push(function () { return autoSoft(vid, inset); }); });
          } else if (kind.layout) kind.layout.block.forEach(bakeImg);
          levels.forEach(function (lv) {
            jobs.push(function () {
              if (kind.auto && !autoBlock(kind.auto, lv)) return null;
              if (!kind.auto && kind.layout && !bakeBlock(k, lv)) return null;
              return dualTiles(k, lv);
            });
          });
        });
        var started = performance.now(), budget = D.sizes.bake_budget_ms || 8;
        (function step() {
          var t0 = performance.now(), waiting = [];
          while (jobs.length && performance.now() - t0 < budget) {
            var job = jobs.shift();
            if (!job()) waiting.push(job);   // its pictures are not in yet
          }
          jobs = waiting.concat(jobs);
          // Pictures that never arrive do not hold the map up for long.
          if (!jobs.length || performance.now() - started > 15000) { done(); bakeSoon(); return; }
          setTimeout(step, waiting.length && waiting.length === jobs.length ? 60 : 0);
        })();
      })
      .catch(done);
  }
  // A scratch canvas for one ground's layer, kept and reused; only the box
  // about to be drawn in is cleared.
  function bakeScratch(w, box) {
    var c = bake.scratch;
    if (!c || c.width !== w) { c = bake.scratch = document.createElement('canvas'); c.width = c.height = w; }
    var x = c.getContext('2d');
    x.setTransform(1, 0, 0, 1, 0, 0); x.globalCompositeOperation = 'source-over'; x.globalAlpha = 1;
    x.clearRect(box[0], box[1], box[2], box[3]);
    return c;
  }
  // One chunk. Grounds are drawn in order - plain grounds by their rank, then
  // smart grounds by theirs - each over everything drawn before it, as the
  // shape of itself and every ground drawn after it: where a later ground
  // rounds off, an earlier one shows beneath, never a gap. One cell of margin
  // round the chunk, so its edge corners see their neighbours. Each ground
  // works only in its own box; the first, where it covers the whole chunk (it
  // does unless the chunk has unpainted cells), is simply filled in.
  function bakeChunk(key, res) {
    var at = key.split(','), cx = +at[0], cy = +at[1], K = bake.kinds;
    var m = 1, A = 64 + 2 * m, big = A * res, size = 64 * res, ready = true;
    var area = bakeArea(cx, cy, m), present = {}, unknown = false;
    for (var i = 0; i < A * A; i++) {
      if (area[i] && K[area[i]]) present[area[i]] = 1; else unknown = true;
    }
    var kinds = Object.keys(present).map(Number).sort(function (a, b) {
      return ((K[a].auto ? 1 : 0) - (K[b].auto ? 1 : 0)) || (a - b);
    });
    var rank = new Int32Array(K.length + 1).fill(-1);
    kinds.forEach(function (k, n) { rank[k] = n; });
    // Drawn straight into the chunk's picture, shifted by the margin.
    var out = document.createElement('canvas');
    out.width = out.height = size;
    var ctx = out.getContext('2d'), ox = cx * 64 - m, oy = cy * 64 - m;
    ctx.translate(-m * res, -m * res);
    kinds.forEach(function (k, n) {
      if (n === 0 && !unknown) {
        if (!bakeFill(ctx, k, res, ox, oy, A, [0, 0, big, big], 'source-over', function () { return true; })) ready = false;
        return;
      }
      var tiles = dualTiles(k, res);
      if (!tiles) { ready = false; return; }
      var whole = new Path2D(), edges = [], x0 = A, y0 = A, x1 = 0, y1 = 0;
      function has(x, y) { return x >= 0 && y >= 0 && x < A && y < A && rank[area[y * A + x]] >= n; }
      // Corner (x, y) sits between cells x-1 and x, y-1 and y.
      for (var y = 1; y < A; y++) {
        var run = -1;
        for (var x = 1; x <= A; x++) {
          var idx = x < A ? (has(x - 1, y - 1) ? 1 : 0) | (has(x, y - 1) ? 2 : 0) | (has(x, y) ? 4 : 0) | (has(x - 1, y) ? 8 : 0) : 0;
          if (idx) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
          if (idx === 15) { if (run < 0) run = x; continue; }
          if (run >= 0) { whole.rect((run - 0.5) * res, (y - 0.5) * res, (x - run) * res, res); run = -1; }
          if (idx) edges.push(idx, x, y);
        }
      }
      if (x1 < x0) return;
      var box = [(x0 - 0.5) * res, (y0 - 0.5) * res, (x1 - x0 + 1) * res, (y1 - y0 + 1) * res];
      var layer = bakeScratch(big, box), lc = layer.getContext('2d');
      lc.fillStyle = '#fff'; lc.fill(whole);
      for (var e = 0; e < edges.length; e += 3)
        lc.drawImage(tiles.mask[edges[e]], (edges[e + 1] - 0.5) * res, (edges[e + 2] - 0.5) * res, res, res);
      if (!bakeFill(lc, k, res, ox, oy, A, box, 'source-in', has)) { ready = false; return; }
      if (tiles.fringe.length) {
        lc.globalCompositeOperation = 'source-atop';
        for (var f = 0; f < edges.length; f += 3) {
          var fr = tiles.fringe[edges[f]];
          if (fr) lc.drawImage(fr, (edges[f + 1] - 0.5) * res, (edges[f + 2] - 0.5) * res, res, res);
        }
        lc.globalCompositeOperation = 'source-over';
      }
      ctx.drawImage(layer, box[0], box[1], box[2], box[3], box[0], box[1], box[2], box[3]);
    });
    return {canvas: out, ready: ready};
  }
  function bakeShow(key, res) {
    var made = bakeChunk(key, res), at = key.split(',');
    var g = document.getElementById('dltdetail');
    if (!g) return;
    var gen = bake.gen[key] || 0, el = made.canvas, old = bake.drawn[key];
    var cw = terr.world.cells_w, ch = terr.world.cells_h;
    // In percent of the world, a hair over 64 cells so neighbours never seam.
    el.style.left = (at[0] * 64 / cw * 100) + '%';
    el.style.top = (at[1] * 64 / ch * 100) + '%';
    el.style.width = (64.04 / cw * 100) + '%';
    el.style.height = (64.04 / ch * 100) + '%';
    // Swapped in one step, so a chunk never flashes empty between pictures.
    if (old && old.el && old.el.isConnected) old.el.replaceWith(el); else g.appendChild(el);
    bake.drawn[key] = {el: el, res: res, gen: gen, ready: made.ready};
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
        bakeTake(res);
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
    var per = (nat.w * view.k) / terr.world.cells_w, res = bakeRes(per), more = false;
    var due = [], mx = (box.x0 + box.x1) / 2, my = (box.y0 + box.y1) / 2;
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
        if (stale) due.push([Math.abs(cx - mx) + Math.abs(cy - my), key]);
      }
    }
    // Nearest the middle of the view first, and only for a few milliseconds a
    // frame (dodoland_bake_budget_ms): the rest waits for the next frame
    // instead of freezing this one.
    due.sort(function (a, b) { return a[0] - b[0]; });
    var started = performance.now(), budgetMs = D.sizes.bake_budget_ms || 8;
    for (var i = 0; i < due.length; i++) {
      if (i > 0 && performance.now() - started > budgetMs) { more = true; break; }
      bakeShow(due[i][1], res);
    }
    if (more) bakeSoon();
    // Kept drawn: at most so many chunks and so much memory (a canvas holds
    // its whole picture, 4 MB for a chunk at full detail), the furthest from
    // the view dropped first and never one that is on screen.
    var keys = Object.keys(bake.drawn), cap = D.sizes.ground_chunks || 300;
    var budget = (D.sizes.ground_memory_mb || 256) * 1048576, used = 0;
    keys.forEach(function (k) { var el = bake.drawn[k].el; if (el) used += el.width * el.height * 4; });
    if (keys.length > cap || used > budget) {
      var cx0 = (box.x0 + box.x1) / 2, cy0 = (box.y0 + box.y1) / 2;
      keys.sort(function (a, b) {
        var pa = a.split(','), pb = b.split(',');
        return (Math.abs(pb[0] - cx0) + Math.abs(pb[1] - cy0)) - (Math.abs(pa[0] - cx0) + Math.abs(pa[1] - cy0));
      });
      for (var j = 0; j < keys.length && (keys.length - j > cap || used > budget); j++) {
        var at = keys[j].split(','), d = bake.drawn[keys[j]];
        if (+at[0] >= box.x0 && +at[0] <= box.x1 && +at[1] >= box.y0 && +at[1] <= box.y1) continue;
        if (d.el) { used -= d.el.width * d.el.height * 4; d.el.remove(); }
        if (d.url) URL.revokeObjectURL(d.url);
        delete bake.drawn[keys[j]];
      }
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
        D.walls = res.walls || [];
        D.gates = res.gates || [];
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
        // Kept for the travellers who walk them (mappage.py, travellersReset).
        terr.roads = res.roads || [];
        if (typeof travellersReset === 'function') setTimeout(travellersReset, 0);
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
  // Walls come with the areas (influence_api.walls): every walled town's land
  // as one territory, so overlapping walled towns share an outer wall and have
  // none between them, and a wall stops where it meets water. Each run is an
  // open path in cell units, drawn raised like the map's own art: the path
  // repeated upward is the wall's face (courses of stone, or stakes), the top
  // sits on it, and towers stand along it and at its ends.
  var WALL = {
    // t: thickness, h: height, in cells. A town hall is about ten cells across.
    stone: {t: 1.5, h: 2.1, step: 0.3, shadow: 'rgba(20,16,12,.3)', edge: '#3a332c',
            faces: ['#8a8276', '#968e82'], top: '#cbc3b6', merlon: ['#a99f92', '#d6cfc3'],
            dash: '0.85 0.6', every: 34, tower: 'stone'},
    palisade: {t: 0.8, h: 2.3, step: 0.3, shadow: 'rgba(20,12,6,.3)', edge: '#2b1b0f',
               faces: ['#7a5230', '#8a5f37'], stakes: '0.42 0.1', top: '#a7784a',
               tips: '#5a3a1f', every: 44, tower: 'wood'}
  };
  function towerSvg(kind, x, y, s) {
    var r = kind === 'stone' ? 1.55 : 1.25, ht = s.h + (kind === 'stone' ? 1.5 : 1.8);
    var f = function (n) { return (+n).toFixed(2); };
    var out = '<ellipse cx="' + f(x + 0.45) + '" cy="' + f(y + 0.3) + '" rx="' + f(r + 0.5) + '" ry="' + f(r * 0.55 + 0.3) +
      '" fill="' + s.shadow + '"/>';
    if (kind === 'stone') {
      out += '<rect x="' + f(x - r) + '" y="' + f(y - ht) + '" width="' + f(2 * r) + '" height="' + f(ht) +
        '" fill="#8e867a" stroke="' + s.edge + '" stroke-width="0.18"/>' +
        '<ellipse cx="' + f(x) + '" cy="' + f(y) + '" rx="' + f(r) + '" ry="' + f(r * 0.5) + '" fill="#7d7569" stroke="' + s.edge + '" stroke-width="0.18"/>' +
        '<rect x="' + f(x - r) + '" y="' + f(y - ht) + '" width="' + f(2 * r) + '" height="' + f(ht) + '" fill="#8e867a"/>' +
        '<ellipse cx="' + f(x) + '" cy="' + f(y - ht) + '" rx="' + f(r) + '" ry="' + f(r * 0.5) + '" fill="#cfc8bc" stroke="' + s.edge + '" stroke-width="0.18"/>' +
        '<ellipse cx="' + f(x) + '" cy="' + f(y - ht) + '" rx="' + f(r * 0.62) + '" ry="' + f(r * 0.3) + '" fill="#6f675c"/>';
      // Merlons round the top.
      for (var a = 0; a < 8; a++) {
        var ang = a / 8 * Math.PI * 2, mx = x + Math.cos(ang) * r * 0.86, my = y - ht + Math.sin(ang) * r * 0.43;
        out += '<rect x="' + f(mx - 0.28) + '" y="' + f(my - 0.55) + '" width="0.56" height="0.6" fill="#bfb7aa" stroke="' + s.edge + '" stroke-width="0.1"/>';
      }
      out += '<line x1="' + f(x - r) + '" y1="' + f(y - ht) + '" x2="' + f(x - r) + '" y2="' + f(y) + '" stroke="' + s.edge + '" stroke-width="0.18"/>' +
        '<line x1="' + f(x + r) + '" y1="' + f(y - ht) + '" x2="' + f(x + r) + '" y2="' + f(y) + '" stroke="' + s.edge + '" stroke-width="0.18"/>' +
        '<rect x="' + f(x - 0.22) + '" y="' + f(y - ht * 0.62) + '" width="0.44" height="0.8" fill="#2d2721"/>';
    } else {
      out += '<rect x="' + f(x - r) + '" y="' + f(y - ht) + '" width="' + f(2 * r) + '" height="' + f(ht) +
        '" fill="#7f5532" stroke="' + s.edge + '" stroke-width="0.16"/>' +
        '<line x1="' + f(x - r * 0.33) + '" y1="' + f(y - ht) + '" x2="' + f(x - r * 0.33) + '" y2="' + f(y) + '" stroke="#5f3d22" stroke-width="0.12"/>' +
        '<line x1="' + f(x + r * 0.33) + '" y1="' + f(y - ht) + '" x2="' + f(x + r * 0.33) + '" y2="' + f(y) + '" stroke="#5f3d22" stroke-width="0.12"/>' +
        '<rect x="' + f(x - r - 0.3) + '" y="' + f(y - ht - 0.35) + '" width="' + f(2 * r + 0.6) + '" height="0.5" fill="#9b6b3f" stroke="' + s.edge + '" stroke-width="0.12"/>' +
        '<path d="M' + f(x - r - 0.45) + ' ' + f(y - ht - 0.35) + 'L' + f(x) + ' ' + f(y - ht - 2.1) + 'L' + f(x + r + 0.45) + ' ' + f(y - ht - 0.35) +
        'Z" fill="#6b3a20" stroke="' + s.edge + '" stroke-width="0.14"/>';
    }
    return out;
  }
  function drawWalls() {
    var g = document.getElementById('dltwalls');
    if (!g) return;
    var runs = D.walls || [], out = [], towers = [];
    var use = function (id, dy, stroke, width, extra) {
      return '<use href="#' + id + '" transform="translate(0 ' + (-dy).toFixed(2) + ')" stroke="' + stroke +
        '" stroke-width="' + width + '"' + (extra || '') + '/>';
    };
    out.push('<defs>' + runs.map(function (r, i) {
      return '<path id="dlwrun' + i + '" d="' + r.d + '"/>';
    }).join('') + '</defs>');
    runs.forEach(function (r, i) {
      var s = WALL[r.style];
      if (!s) return;
      var id = 'dlwrun' + i, t = s.t;
      // Its shadow, and the measured path the towers are spaced along.
      out.push('<path class="dlwall dlwmeasure" data-run="' + i + '" d="' + r.d + '" stroke="' + s.shadow +
               '" stroke-width="' + (t + 0.9) + '" transform="translate(0.45 0.3)"/>');
      out.push('<g class="dlwall">');
      out.push(use(id, 0, s.edge, (t + 0.3).toFixed(2)));
      // The face: the path repeated upward, in courses (stone) or stakes (wood).
      for (var k = 0, n = Math.round(s.h / s.step); k <= n; k++) {
        var dy = k * s.step, shade = s.faces[Math.floor(dy / 0.6) % 2];
        out.push(use(id, dy, shade, t, s.stakes ? ' stroke-dasharray="' + s.stakes + '"' : ''));
      }
      if (s.stakes) {
        // Between the stakes, the dark of the gaps; then the cut tops and tips.
        out.push(use(id, s.h, s.edge, (t + 0.25).toFixed(2)));
        out.push(use(id, s.h, s.top, t, ' stroke-dasharray="' + s.stakes + '"'));
        out.push(use(id, s.h + 0.3, s.tips, (t * 0.6).toFixed(2), ' stroke-dasharray="0.18 0.34"'));
      } else {
        out.push(use(id, s.h, s.edge, (t + 0.3).toFixed(2)));
        out.push(use(id, s.h, s.top, t));
        // Battlements along the wall walk.
        out.push(use(id, s.h + 0.4, s.edge, (t + 0.1).toFixed(2), ' stroke-dasharray="' + s.dash + '"'));
        out.push(use(id, s.h + 0.45, s.merlon[0], t, ' stroke-dasharray="' + s.dash + '"'));
        out.push(use(id, s.h + 0.6, s.merlon[1], (t * 0.85).toFixed(2), ' stroke-dasharray="' + s.dash + '"'));
      }
      out.push('</g>');
    });
    // Gateways: the opening between two runs, raised like the wall, with a
    // dark arch (stone) or a pair of plank doors (wood).
    (D.gates || []).forEach(function (gt) {
      var s = WALL[gt.style];
      if (!s) return;
      var ax = gt.a[0], ay = gt.a[1], bx = gt.b[0], by = gt.b[1], h = s.h + 0.4;
      var f = function (n) { return (+n).toFixed(2); };
      var lerp = function (t) { return [ax + (bx - ax) * t, ay + (by - ay) * t]; };
      var face = 'M' + f(ax) + ' ' + f(ay) + 'L' + f(bx) + ' ' + f(by) + 'L' + f(bx) + ' ' + f(by - h) +
                 'L' + f(ax) + ' ' + f(ay - h) + 'Z';
      out.push('<path d="' + face + '" fill="' + s.faces[0] + '" stroke="' + s.edge + '" stroke-width="0.18"/>');
      var l = lerp(0.22), r = lerp(0.78), top = Math.min(l[1], r[1]) - h * 0.72;
      if (gt.style === 'stone') {
        out.push('<path d="M' + f(l[0]) + ' ' + f(l[1]) + 'L' + f(l[0]) + ' ' + f(top + 0.6) +
                 'Q' + f((l[0] + r[0]) / 2) + ' ' + f(top - 0.7) + ' ' + f(r[0]) + ' ' + f(top + 0.6) +
                 'L' + f(r[0]) + ' ' + f(r[1]) + 'Z" fill="#2a241e"/>');
      } else {
        var m = lerp(0.5);
        out.push('<path d="M' + f(l[0]) + ' ' + f(l[1]) + 'L' + f(l[0]) + ' ' + f(top) + 'L' + f(r[0]) + ' ' + f(top) +
                 'L' + f(r[0]) + ' ' + f(r[1]) + 'Z" fill="#6b4425" stroke="' + s.edge + '" stroke-width="0.14"/>' +
                 '<line x1="' + f(m[0]) + '" y1="' + f(top) + '" x2="' + f(m[0]) + '" y2="' + f(m[1]) +
                 '" stroke="' + s.edge + '" stroke-width="0.18"/>');
      }
      out.push('<path d="M' + f(ax) + ' ' + f(ay - h) + 'L' + f(bx) + ' ' + f(by - h) + '" stroke="' + s.edge +
               '" stroke-width="' + (s.t + 0.3).toFixed(2) + '" fill="none"/>' +
               '<path d="M' + f(ax) + ' ' + f(ay - h) + 'L' + f(bx) + ' ' + f(by - h) + '" stroke="' + s.top +
               '" stroke-width="' + s.t + '" fill="none"/>');
    });
    g.innerHTML = out.join('');
    // Towers along each run and at both ends (where a wall meets the shore),
    // drawn after every wall and the nearer (lower) ones last.
    g.querySelectorAll('.dlwmeasure').forEach(function (path) {
      var r = runs[+path.getAttribute('data-run')], s = WALL[r && r.style];
      if (!s) return;
      try {
        var length = path.getTotalLength(), count = Math.max(1, Math.round(length / s.every));
        for (var k = 0; k <= count; k++) {
          var pt = path.getPointAtLength(length * k / count);
          towers.push({x: pt.x, y: pt.y, s: s});
        }
      } catch (e) {}
    });
    // Where runs meet (two walls joining, short runs by a shore) their end
    // towers would crowd together: one is enough.
    // A gate stands between two towers, always.
    // Set back along the wall, so the opening between them stays open.
    var kept = (D.gates || []).filter(function (gt) { return WALL[gt.style]; }).reduce(function (all, gt) {
      var dx = gt.b[0] - gt.a[0], dy = gt.b[1] - gt.a[1], n = Math.sqrt(dx * dx + dy * dy) || 1, k = 1.3 / n;
      return all.concat([{x: gt.a[0] - dx * k, y: gt.a[1] - dy * k, s: WALL[gt.style]},
                         {x: gt.b[0] + dx * k, y: gt.b[1] + dy * k, s: WALL[gt.style]}]);
    }, []);
    towers.forEach(function (w) {
      for (var i = 0; i < kept.length; i++) {
        var dx = kept[i].x - w.x, dy = kept[i].y - w.y;
        if (dx * dx + dy * dy < 36) return;   // within six cells of one already standing
      }
      kept.push(w);
    });
    towers = kept;
    towers.sort(function (a, b) { return a.y - b.y; });
    g.insertAdjacentHTML('beforeend', towers.map(function (w) {
      return towerSvg(w.s.tower, w.x, w.y, w.s);
    }).join(''));
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
        if (typeof loaded === 'function') { loaded('ground'); loaded('reach'); loaded('textures'); }
        return;
      }
      terrSetup(world);
      rearm();
      loadInfluence();
      loadRoads();
      terrOverview();
      bakeWarm();
      terrDetail();
      // The reference is hidden when the overview arrives (terrOverview): the
      // terrain *is* the map now, and the upload is only there to trace against.
    })
    .catch(function () {
      terrSay('The world could not be loaded.', true);
      if (typeof loaded === 'function') { loaded('ground'); loaded('reach'); loaded('textures'); }
    });
"""
