"""
Painted forests on the map page: the brush that paints them, and the drawing.

Spliced into ``mappage._SCRIPT`` inside the same closure as the toolkit (it uses
``brush``, ``mix``, ``armedAsset``, ``assetById``, ``toCell``…), the way
``terrain_ui`` is.

**Nothing per tree exists anywhere.** The server keeps which stand grows on each
cell (``helpers/dodoland/forest.py``); here each chunk's trees are grown from
its cells: a staggered grid spaced by the stand's own tree width, a point kept
where the cell under it holds the stand, its tile, size, mirror and nudge drawn
from a hash of the grid point and the stand's seed. So the same forest always
shows the same trees, and they are worked out only for the chunks in view.

Each chunk's trees are drawn onto **one canvas**, far cheaper than an element
per tree, sorted by how far down the map each stands so the nearer overlap the
further. The layer sits above the ground and below placed objects and towns.
"""

MODE = """
      <div class="dlseg" id="dlforestmode" title="Forest: paint a stretch of forest, or clear it. Painted forest stores no trees, so any amount of it costs the same."><button data-fm="paint" class="on">Paint forest</button><button data-fm="erase">Erase forest</button></div>"""

CSS = """
/* Painted forests: canvases in depth strips, stacked among the pieces and
   walkers (the layer itself must not be a stacking context). */
.dlforest { display: contents; }
.dlforest canvas { position: absolute; image-rendering: pixelated; pointer-events: none; }
.dlworld.hide-objects .dlforest, .dlforest.far { display: none; }
.dlforestpv { position: absolute; inset: 0; pointer-events: none; z-index: 21; }
#dlforestmode[hidden] { display: none; }
"""

SCRIPT = r"""
  // --- painted forests -------------------------------------------------- //
  var FOREST = {stands: [], rle: {}, cells: {}, known: {}, drawn: {}, imgs: {},
                ver: '', fetching: false, erase: false, stroke: null, queued: false};
  function forestErasing() { return brush.pat === 'forest' && FOREST.erase; }
  function forestLayer() {
    if (!FOREST.layer) {
      FOREST.layer = document.createElement('div');
      FOREST.layer.className = 'dlforest';
      world.appendChild(FOREST.layer);
    }
    return FOREST.layer;
  }
  // "3x0 2x5" -> the chunk's 4096 stand indices.
  function forestDecode(rle) {
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
  // A number in [0, 1) from a grid point, a stand's seed and a purpose: the
  // same inputs always give the same tree.
  function forestRand(gx, gy, seed, n) {
    var h = (Math.imul(gx, 73856093) ^ Math.imul(gy, 19349663) ^ seed ^ Math.imul(n + 1, 83492791)) >>> 0;
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b) >>> 0;
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b) >>> 0;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  // A stand's grid: spaced by its trees' average width at its size, closer
  // the denser, rows 0.8 of a step apart (a staggered stand, not a plantation).
  // The spacing, in tree widths, runs straight from the server's setting at 0%
  // density to its setting at 100%.
  function standShape(stand) {
    if (stand._shape) return stand._shape;
    var tiles = [], total = 0;
    (stand.mix || []).forEach(function (id) {
      var a = assetById(id);
      if (a && a.wc) { tiles.push(a); total += a.wc * Math.min(a.hi, Math.max(a.lo, stand.scale)); }
    });
    var w = tiles.length ? total / tiles.length : 2;
    var at0 = D.sizes.forest_gap_zero, at1 = D.sizes.forest_gap_full;
    if (at0 === undefined) at0 = 1.95;
    if (at1 === undefined) at1 = 0.95;
    var gap = Math.max(0.3, w * (at0 + (at1 - at0) * stand.density));
    stand._shape = {tiles: tiles, gap: gap, row: gap * 0.8};
    return stand._shape;
  }
  // Every tree whose grid point falls in chunk (cx, cy), nearest last.
  // ``keep`` (0-1) is the share drawn: far out, where a tree is a pixel or
  // two, a dense stand is thousands of them per chunk and most are invisible
  // under the rest; the same seed picks which, so zooming in only adds trees.
  function forestTrees(cx, cy, cells, keep) {
    if (keep === undefined) keep = 1;
    var X0 = cx * 64, Y0 = cy * 64, out = [], present = {};
    for (var i = 0; i < 4096; i++) if (cells[i]) present[cells[i]] = true;
    Object.keys(present).forEach(function (k) {
      var index = +k, s = FOREST.stands[index];
      if (!s || !s.mix) return;
      var sh = standShape(s);
      if (!sh.tiles.length) return;
      var gy0 = Math.ceil(Y0 / sh.row), gy1 = Math.ceil((Y0 + 64) / sh.row) - 1;
      for (var gy = gy0; gy <= gy1; gy++) {
        var off = (gy & 1) ? 0.5 : 0, py = gy * sh.row;
        var gx0 = Math.ceil(X0 / sh.gap - off), gx1 = Math.ceil((X0 + 64) / sh.gap - off) - 1;
        for (var gx = gx0; gx <= gx1; gx++) {
          var px = (gx + off) * sh.gap;
          var lx = Math.floor(px) - X0, ly = Math.floor(py) - Y0;
          if (lx < 0 || lx > 63 || ly < 0 || ly > 63 || cells[ly * 64 + lx] !== index) continue;
          if (keep < 1 && forestRand(gx, gy, s.seed, 6) >= keep) continue;
          var a = sh.tiles[Math.floor(forestRand(gx, gy, s.seed, 3) * sh.tiles.length)];
          var sc = s.scale * (1 + (forestRand(gx, gy, s.seed, 4) * 2 - 1) * s.jitter);
          sc = Math.min(a.hi, Math.max(a.lo, sc));
          out.push({a: a, w: a.wc * sc,
                    x: px + (forestRand(gx, gy, s.seed, 1) - 0.5) * sh.gap * 0.7,
                    y: py + (forestRand(gx, gy, s.seed, 2) - 0.5) * sh.gap * 0.6,
                    f: !!s.flip && forestRand(gx, gy, s.seed, 5) < 0.5});
        }
      }
    });
    out.sort(function (p, q) { return p.y - q.y; });
    return out;
  }
  function forestImg(a) {
    var im = FOREST.imgs[a.id];
    if (!im) {
      im = FOREST.imgs[a.id] = new Image();
      im.decoding = 'async';
      im.onload = function () { forestSoon(); };
      im.src = assetUrl(a.id);
    }
    return im.complete && im.naturalWidth ? im : null;
  }
  // A tree's baked shadow (the map's shadowFor, from the same sun), as a
  // loaded picture to draw onto the strip; null until it is ready, and the
  // forest is redrawn when it is.
  function forestShadow(a, flip) {
    if (typeof shadowFor !== 'function' || !shadowsOn()) return false;
    var got = null;
    shadowFor(assetUrl(a.id), flip, function (s) {
      if (!s.img) {
        s.img = new Image();
        s.img.onload = function () { forestSoon(); };
        s.img.src = s.url;
      }
      got = s;
    });
    return got && got.img && got.img.complete && got.img.naturalWidth ? got : null;
  }
  // Every forest drawn again: the sun moved, so its shadows did.
  function forestRedrawAll() {
    Object.keys(FOREST.drawn).forEach(forestDrop);
    forestSoon();
  }
  function forestDrop(key) {
    var d = FOREST.drawn[key];
    if (d) (d.els || []).forEach(function (el) { el.remove(); });
    delete FOREST.drawn[key];
  }
  // One chunk's trees, anchored the way a placed piece is (its middle, 85% of
  // the way down the drawing), drawn in **strips** a couple of cells deep by
  // where each trunk stands. Each strip stacks by its lowest trunk exactly as
  // a piece or a walker does (depth), so somebody walking through the wood
  // passes behind the trees in front of them and in front of those behind.
  // Zoomed out (below dodoland_forest_merge px a cell) a forest is not trees
  // standing among the towns but a texture: each chunk is one flat picture,
  // trees drawn back to front, no shadows - one layer for the browser to move
  // instead of dozens of strips each holding every tree's shadow.
  function forestMerged() { return pxPerCell() < (D.sizes.forest_merge == null ? 6 : D.sizes.forest_merge); }
  function forestRenderFlat(key, res, trees) {
    var at = key.split(','), cx = +at[0], cy = +at[1], ready = true, ch = cellsH();
    var x0 = cx * 64 - 2, y0 = cy * 64 - 4, bw = 68, bh = 70;
    var cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.ceil(bw * res)); cv.height = Math.max(1, Math.ceil(bh * res));
    var ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    trees.sort(function (a, b) { return a.y - b.y; }).forEach(function (t) {
      var im = forestImg(t.a);
      if (!im) { ready = false; return; }
      var h = t.w * im.naturalHeight / im.naturalWidth, x = (t.x - t.w / 2 - x0) * res, y = (t.y - h * 0.85 - y0) * res;
      if (t.f) { ctx.save(); ctx.translate(x + t.w * res, y); ctx.scale(-1, 1); ctx.drawImage(im, 0, 0, t.w * res, h * res); ctx.restore(); }
      else ctx.drawImage(im, x, y, t.w * res, h * res);
    });
    forestDrop(key);
    cv.style.left = (x0 / D.cells_w * 100) + '%';
    cv.style.top = (y0 / ch * 100) + '%';
    cv.style.width = (bw / D.cells_w * 100) + '%';
    cv.style.height = (bh / ch * 100) + '%';
    cv.style.zIndex = depth(cy * 64 / ch * 100);
    forestLayer().appendChild(cv);
    FOREST.drawn[key] = {els: [cv], res: res, rle: ready ? FOREST.rle[key] : null, ready: ready, flat: true};
  }
  function forestRender(key, res) {
    var at = key.split(','), cx = +at[0], cy = +at[1];
    var trees = forestTrees(cx, cy, FOREST.cells[key], forestKeep(res)), ready = true;
    if (forestMerged()) { forestRenderFlat(key, res, trees); return; }
    var strip = Math.max(0.5, D.sizes.forest_strip || 2), strips = {};
    trees.forEach(function (t) {
      var im = forestImg(t.a);
      if (!im) { ready = false; return; }
      var h = t.w * im.naturalHeight / im.naturalWidth;
      var n = Math.floor(t.y / strip), g = strips[n];
      if (!g) g = strips[n] = {items: [], x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity, low: -Infinity};
      var x0 = t.x - t.w / 2, y0 = t.y - h * 0.85;
      // Its shadow, from the same sun as everything else on the map.
      var sh = forestShadow(t.a, !!t.f), shade = null;
      if (sh === null) ready = false;
      else if (sh) {
        shade = {img: sh.img, x0: x0 + sh.left / 100 * t.w, y0: y0 + sh.top / 100 * h,
                 w: sh.width / 100 * t.w, h: sh.height / 100 * h};
        g.x0 = Math.min(g.x0, shade.x0); g.y0 = Math.min(g.y0, shade.y0);
        g.x1 = Math.max(g.x1, shade.x0 + shade.w); g.y1 = Math.max(g.y1, shade.y0 + shade.h);
      }
      g.items.push({t: t, im: im, x0: x0, y0: y0, h: h, shade: shade});
      g.x0 = Math.min(g.x0, x0); g.y0 = Math.min(g.y0, y0);
      g.x1 = Math.max(g.x1, x0 + t.w); g.y1 = Math.max(g.y1, y0 + h);
      g.low = Math.max(g.low, t.y);
    });
    forestDrop(key);
    var ch = cellsH(), els = [];
    Object.keys(strips).forEach(function (n) {
      var g = strips[n], bw = g.x1 - g.x0, bh = g.y1 - g.y0;
      var r = Math.min(res, 4096 / Math.max(bw, bh));
      var cv = document.createElement('canvas');
      cv.width = Math.max(1, Math.ceil(bw * r));
      cv.height = Math.max(1, Math.ceil(bh * r));
      var ctx = cv.getContext('2d');
      // Every tree's shadow first, then the trees over them.
      ctx.imageSmoothingEnabled = true;
      g.items.forEach(function (s) {
        if (s.shade) ctx.drawImage(s.shade.img, (s.shade.x0 - g.x0) * r, (s.shade.y0 - g.y0) * r, s.shade.w * r, s.shade.h * r);
      });
      ctx.imageSmoothingEnabled = false;
      g.items.forEach(function (s) {
        var x = (s.x0 - g.x0) * r, y = (s.y0 - g.y0) * r, w = s.t.w * r, h = s.h * r;
        if (s.t.f) {
          ctx.save(); ctx.translate(x + w, y); ctx.scale(-1, 1);
          ctx.drawImage(s.im, 0, 0, w, h); ctx.restore();
        } else {
          ctx.drawImage(s.im, x, y, w, h);
        }
      });
      cv.style.left = (g.x0 / D.cells_w * 100) + '%';
      cv.style.top = (g.y0 / ch * 100) + '%';
      cv.style.width = (bw / D.cells_w * 100) + '%';
      cv.style.height = (bh / ch * 100) + '%';
      cv.style.zIndex = depth(g.low / ch * 100);
      forestLayer().appendChild(cv);
      els.push(cv);
    });
    FOREST.drawn[key] = {els: els, res: res, rle: ready ? FOREST.rle[key] : null, ready: ready};
  }
  // The share of trees drawn at a detail: all of them from the server's
  // setting up, fewer in proportion below it (0 draws every tree always).
  function forestKeep(res) {
    var full = D.sizes.forest_full || 0;
    return full > 0 ? Math.max(0.05, Math.min(1, res / full)) : 1;
  }
  // Pixels per cell to draw at: a step up from what the screen shows, so a
  // little zooming does not redraw, and never past the server's setting.
  function forestRes(per) {
    var want = per * (window.devicePixelRatio || 1), res = 1;
    while (res < want && res < 64) res *= 2;
    return Math.max(1, Math.min(res, (D.sizes.forest_detail || 12)));
  }
  function forestBox() {
    var cw = D.cells_w, ch = cellsH(), k = nat.w * view.k;
    var maxX = Math.ceil(cw / 64) - 1, maxY = Math.ceil(ch / 64) - 1;
    var x0 = (-view.x) / k * cw, x1 = (-view.x + frame.clientWidth) / k * cw;
    var y0 = (-view.y) / (nat.h * view.k) * ch, y1 = (-view.y + frame.clientHeight) / (nat.h * view.k) * ch;
    return [Math.max(0, Math.floor(x0 / 64) - 1), Math.max(0, Math.floor(y0 / 64) - 1),
            Math.min(maxX, Math.floor(x1 / 64) + 1), Math.min(maxY, Math.floor(y1 / 64) + 1)];
  }
  function forestFetch(box) {
    if (FOREST.fetching) return;
    var missing = false;
    for (var cy = box[1]; cy <= box[3] && !missing; cy++)
      for (var cx = box[0]; cx <= box[2]; cx++) if (!FOREST.known[cx + ',' + cy]) { missing = true; break; }
    if (!missing) return;
    FOREST.fetching = true;
    fetch(D.ep.forest + '?r=' + box.join(',') + '&v=' + encodeURIComponent(FOREST.ver))
      .then(function (r) { return r.ok ? r.json() : {ok: false}; })
      .then(function (res) {
        FOREST.fetching = false;
        if (!res.ok) return;
        if (res.stands) FOREST.stands = res.stands;
        for (var cy = box[1]; cy <= box[3]; cy++) {
          for (var cx = box[0]; cx <= box[2]; cx++) {
            var key = cx + ',' + cy, rle = (res.chunks || {})[key];
            FOREST.known[key] = true;
            if (rle) { FOREST.rle[key] = rle; FOREST.cells[key] = forestDecode(rle); }
            else { delete FOREST.rle[key]; delete FOREST.cells[key]; }
          }
        }
        forestSoon();
      })
      .catch(function () { FOREST.fetching = false; });
  }
  function forestSoon() {
    if (FOREST.queued) return;
    FOREST.queued = true;
    requestAnimationFrame(function () { FOREST.queued = false; forestView(); });
  }
  // Called whenever the view moves: fetch what is missing, draw what is due
  // (a few chunks a frame, so a big zoom does not freeze the page), and let go
  // of the furthest when more are kept than the setting allows.
  function forestView() {
    if (!D.cells_w || !nat.w || !D.ep.forest) return;
    var layer = forestLayer(), per = pxPerCell();
    var lod = (D.sizes.lod || {}).forest || 0;
    // Hidden by a class, not an inline style, so the Layers switch still works.
    layer.classList.toggle('far', per < lod);
    if (per < lod) return;
    var box = forestBox(), res = forestRes(per), budget = 6, more = false;
    forestFetch(box);
    for (var cy = box[1]; cy <= box[3]; cy++) {
      for (var cx = box[0]; cx <= box[2]; cx++) {
        var key = cx + ',' + cy, d = FOREST.drawn[key];
        if (!FOREST.rle[key]) {
          if (d && FOREST.known[key]) forestDrop(key);
          continue;
        }
        var stale = !d || d.rle !== FOREST.rle[key] || !d.ready || (d.res < res && d.res < (D.sizes.forest_detail || 12)) ||
                    !!d.flat !== forestMerged();
        if (!stale) continue;
        if (budget-- > 0) forestRender(key, res); else more = true;
      }
    }
    if (more) forestSoon();
    var keys = Object.keys(FOREST.drawn), cap = D.sizes.forest_chunks || 200;
    if (keys.length > cap) {
      var mx = (box[0] + box[2]) / 2, my = (box[1] + box[3]) / 2;
      keys.sort(function (a, b) {
        var pa = a.split(','), pb = b.split(',');
        return (Math.abs(pb[0] - mx) + Math.abs(pb[1] - my)) - (Math.abs(pa[0] - mx) + Math.abs(pa[1] - my));
      });
      keys.slice(0, keys.length - cap).forEach(forestDrop);
    }
  }

  // The stroke: points gathered as the brush moves, shown as a wash on the
  // frame, painted by the server in one request when the button comes up.
  var forestPv = document.createElement('canvas');
  forestPv.className = 'dlforestpv';
  frame.appendChild(forestPv);
  function forestPreview(c, first) {
    if (first) {
      forestPv.width = frame.clientWidth; forestPv.height = frame.clientHeight;
    }
    var ctx = forestPv.getContext('2d');
    ctx.fillStyle = FOREST.erase ? 'rgba(220, 80, 60, .28)' : 'rgba(40, 120, 50, .35)';
    var k = nat.w * view.k, x = view.x + c.x / D.cells_w * k, y = view.y + c.y / cellsH() * nat.h * view.k;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(3, brush.r * pxPerCell()), 0, Math.PI * 2);
    ctx.fill();
  }
  function forestPreviewClear() {
    forestPv.getContext('2d').clearRect(0, 0, forestPv.width, forestPv.height);
  }
  function forestStrokeStart(ev) {
    var c = toCell(ev);
    FOREST.stroke = {points: [[Math.round(c.x), Math.round(c.y)]], last: c};
    forestPreview(c, true);
  }
  function forestStrokeMove(ev) {
    var s = FOREST.stroke;
    if (!s) return;
    var c = toCell(ev);
    if (Math.hypot(c.x - s.last.x, c.y - s.last.y) < Math.max(1, brush.r * 0.25)) return;
    s.points.push([Math.round(c.x), Math.round(c.y)]);
    s.last = c;
    forestPreview(c);
  }
  function forestStrokeCancel() { FOREST.stroke = null; forestPreviewClear(); }
  function forestStrokeEnd() {
    var s = FOREST.stroke;
    FOREST.stroke = null;
    if (!s) return;
    var body = {mode: 'brush', points: s.points.slice(0, 4000), radius: Math.round(brush.r), shape: 'round'};
    var erase = FOREST.erase;
    if (erase) {
      body.erase = true;
    } else {
      body.mix = mix.length ? mix.slice() : (armedAsset ? [armedAsset] : []);
      body.density = brush.den;
      body.scale = parseFloat(kitScale.value) || 1;
      body.jitter = brush.jit;
      body.flip = brush.flip;
    }
    kitSay(erase ? 'Clearing forest…' : 'Planting forest…');
    fetch(D.ep.forest_paint, {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify(body)})
      .then(function (r) {
        return r.json().catch(function () { return {ok: false, error: 'The server answered with ' + r.status + '.'}; });
      })
      .then(function (res) {
        forestPreviewClear();
        if (!res.ok) { kitSay(res.error || 'That did not work.', true); return; }
        FOREST.ver = res.version || FOREST.ver;
        (res.touched || []).forEach(function (t) { delete FOREST.known[t[0] + ',' + t[1]]; });
        kitSay((erase ? 'Cleared forest from ' : 'Planted forest on ') + res.cells.toLocaleString() + ' cells.');
        forestView();
      })
      .catch(function () { forestPreviewClear(); kitSay('The server could not be reached.', true); });
  }
  document.querySelectorAll('#dlforestmode button').forEach(function (b) {
    b.onclick = function () {
      FOREST.erase = b.dataset.fm === 'erase';
      document.querySelectorAll('#dlforestmode button').forEach(function (o) { o.classList.toggle('on', o === b); });
      kitSay(FOREST.erase ? 'Drag over forest to clear it.' : 'Pick trees (shift-click for a mix), then drag to paint forest.');
    };
  });
"""
