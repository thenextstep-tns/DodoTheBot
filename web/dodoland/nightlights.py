"""
The night's shared pieces, for the map and the lights editor alike.

``SCRIPT`` defines, at the top level of whatever script it is put in:

* ``findLights(img, N)`` - the lights a loaded picture has of its own (lit
  windows, lanterns, fires), found by colour and shape with the
  ``dodoland_window_*`` settings in ``N``: a mask of their pixels, a soft halo
  round them, and a spot per light (``{cx, cy, r}``, fractions of the
  picture), or null. The map lights these at night; the editor shows them, so
  what a tile gets by itself is never a surprise.
* ``skyAt(S, N, hour)`` - the light of the sky at that hour from the sun's
  settings ``S`` and the night's ``N``: how far into the night it is (``k``,
  0 day to 1 night), which side the sun is on, and ``at(f)``, the colour and
  strength of the night a fraction ``f`` of the way from the sun's side to the
  far side. Dusk runs through ``dodoland_dusk_colours`` (pink into purple,
  violet, blue), dawn through ``dodoland_dawn_colours`` (night into a warm
  orange), the sun's side always a little behind the far side.
* ``hexRgb(hex)`` - ``"#rrggbb"`` as ``[r, g, b]``.

Python never runs this; :mod:`web.dodoland.mappage` and
:mod:`web.dodoland.lights_ui` each include it in their page's script.
"""

# A placed piece stands at this fraction of its picture's height (the map's
# .dlpiece is translate(-50%, -85%)), which is where a light's pool falls.
PIECE_FOOT = 0.85

# The sky's colours from the day's edge into the night (dusk) and from the
# night into the day (dawn): the defaults of dodoland_dusk_colours and
# dodoland_dawn_colours.
DUSK = ["#e8849c", "#a5559b", "#64409a", "#0b1430"]
DAWN = ["#0b1430", "#5a3f78", "#e0895a", "#f5b26b"]


def colours(text, fallback: list) -> list:
    """``"#e8849c, #a5559b"`` -> ``["#e8849c", "#a5559b"]``; anything that is
    not #rrggbb is left out, and none at all is ``fallback``."""
    out = []
    for part in str(text or "").replace(";", ",").replace(" ", ",").split(","):
        v = part.strip().lower()
        if len(v) == 7 and v.startswith("#") and all(ch in "0123456789abcdef" for ch in v[1:]):
            out.append(v)
    return out or list(fallback)

SCRIPT = f"  var PIECE_FOOT = {PIECE_FOOT};" + r"""
  function hexRgb(hex) {
    return [1, 3, 5].map(function (i) { return parseInt(String(hex).slice(i, i + 2), 16) || 0; });
  }
  function findLights(im, N) {
    N = N || {};
    var sc = Math.min(1, 256 / Math.max(im.naturalWidth || 1, im.naturalHeight || 1));
    var w = Math.max(1, Math.round((im.naturalWidth || 120) * sc)), h = Math.max(1, Math.round((im.naturalHeight || 78) * sc));
    var c = document.createElement('canvas'); c.width = w; c.height = h;
    var x = c.getContext('2d'); x.drawImage(im, 0, 0, w, h);
    var d = x.getImageData(0, 0, w, h), px = d.data;
    var minR = N.min_red == null ? 200 : N.min_red, minG = N.min_green == null ? 100 : N.min_green;
    var warm = N.warmth == null ? 80 : N.warmth;
    var maxArea = Math.max(2, (N.max_size == null ? 0.006 : N.max_size) * w * h);
    var minContrast = N.contrast == null ? 45 : N.contrast;
    var lum = new Float32Array(w * h), hot = new Uint8Array(w * h);
    for (var i = 0, j = 0; j < w * h; i += 4, j++) {
      lum[j] = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
      hot[j] = px[i + 3] > 128 && px[i] >= minR && px[i + 1] >= minG && px[i] - px[i + 2] >= warm ? 1 : 0;
    }
    // Patches of warm pixels (4-connected), each judged on its own: a light
    // is small, and clearly brighter than what surrounds it - which is what
    // tells a lantern from a thatched roof of the same colour.
    var seen = new Int32Array(w * h).fill(-1), keep = [], stack = [];
    for (var start = 0; start < w * h; start++) {
      if (!hot[start] || seen[start] >= 0) continue;
      var id = keep.length + 1000, cells = [], x0 = w, y0 = h, x1 = 0, y1 = 0, sum = 0;
      stack.push(start); seen[start] = id;
      while (stack.length) {
        var q = stack.pop(), qx = q % w, qy = (q - qx) / w;
        cells.push(q); sum += lum[q];
        if (qx < x0) x0 = qx; if (qx > x1) x1 = qx; if (qy < y0) y0 = qy; if (qy > y1) y1 = qy;
        [q - 1, q + 1, q - w, q + w].forEach(function (n2) {
          if (n2 < 0 || n2 >= w * h || seen[n2] >= 0 || !hot[n2]) return;
          if ((n2 === q - 1 && qx === 0) || (n2 === q + 1 && qx === w - 1)) return;
          seen[n2] = id; stack.push(n2);
        });
      }
      if (cells.length > maxArea) continue;
      var pad = 2, rsum = 0, rn = 0;
      for (var ry = Math.max(0, y0 - pad); ry <= Math.min(h - 1, y1 + pad); ry++)
        for (var rx = Math.max(0, x0 - pad); rx <= Math.min(w - 1, x1 + pad); rx++) {
          var k2 = ry * w + rx;
          if (hot[k2] || px[k2 * 4 + 3] <= 128) continue;
          rsum += lum[k2]; rn++;
        }
      var inner = sum / cells.length, ring = rn ? rsum / rn : 0;
      if (rn && inner - ring < minContrast) continue;
      keep.push({cells: cells, cx: (x0 + x1 + 1) / 2 / w, cy: (y0 + y1 + 1) / 2 / h,
                 r: Math.sqrt(cells.length / Math.PI) / w, glow: inner - ring});
    }
    if (!keep.length) return null;
    // Lights close together are one light (a window's panes, a fire's
    // flames), and a picture keeps only its strongest few (dodoland_window_merge,
    // dodoland_window_most): a painting is full of small warm highlights.
    var near = (N.merge == null ? 0.08 : N.merge), most = N.most == null ? 6 : N.most;
    keep.sort(function (a, b) { return b.glow * b.cells.length - a.glow * a.cells.length; });
    var groups = [];
    keep.forEach(function (blob) {
      var g = null;
      for (var gi = 0; gi < groups.length && !g; gi++) {
        var dx = groups[gi].cx - blob.cx, dy = (groups[gi].cy - blob.cy) * h / w;
        if (Math.sqrt(dx * dx + dy * dy) <= near) g = groups[gi];
      }
      if (g) { g.cells = g.cells.concat(blob.cells); g.r = Math.sqrt(g.cells.length / Math.PI) / w; return; }
      if (groups.length < most) groups.push({cells: blob.cells, cx: blob.cx, cy: blob.cy, r: blob.r, glow: blob.glow});
    });
    keep = groups;
    if (!keep.length) return null;
    for (var m = 0; m < w * h * 4; m += 4) px[m + 3] = 0;
    keep.forEach(function (blob) {
      blob.cells.forEach(function (q) { px[q * 4] = px[q * 4 + 1] = px[q * 4 + 2] = 255; px[q * 4 + 3] = 255; });
      delete blob.cells;
    });
    x.putImageData(d, 0, 0);
    var halo = document.createElement('canvas'); halo.width = w; halo.height = h;
    var hx = halo.getContext('2d');
    hx.filter = 'blur(' + Math.max(1.5, w / 60).toFixed(1) + 'px)';
    hx.drawImage(c, 0, 0); hx.drawImage(c, 0, 0);
    return {mask: c, halo: halo, spots: keep};
  }
  function skyAt(S, N, h) {
    S = S || {}; N = N || {};
    var rise = S.rise == null ? 6 : S.rise, set = S.set == null ? 20 : S.set;
    var T = N.twilight == null ? 1.75 : N.twilight;
    function smooth(a, b, x) { var t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); }
    var evening = h >= 12;
    var k = evening ? smooth(set - T * 0.45, set + T * 0.55, h) : 1 - smooth(rise - T * 0.55, rise + T * 0.45, h);
    // Both lists run from the day's edge (k 0) into the night (k 1): dusk is
    // written that way, dawn is written night first and so turned round.
    var dusk = N.dusk_colours || ['#e8849c', '#a5559b', '#64409a', '#0b1430'];
    var dawn = N.dawn_colours || ['#0b1430', '#5a3f78', '#e0895a', '#f5b26b'];
    var stops = (evening ? dusk : dawn.slice().reverse()).map(hexRgb);
    var dark = N.darkness == null ? 0.62 : N.darkness, tint = N.tint == null ? 0.25 : N.tint;
    var spread = N.spread == null ? 0.35 : N.spread;
    function colour(t) {
      if (stops.length === 1) return stops[0];
      var f = Math.max(0, Math.min(1, t)) * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(f)), u = f - i;
      return stops[i].map(function (v, n) { return Math.round(v + (stops[i + 1][n] - v) * u); });
    }
    return {k: k, evening: evening, dark: dark * k,
            // The evening sun is in the west (left), the morning sun in the east.
            sunLeft: evening,
            at: function (f) {
              var t = Math.max(0, Math.min(1, k + spread * (f - 0.5) * Math.min(1, 4 * k * (1 - k) + 0.0001)));
              return {rgb: colour(t), a: Math.min(1, dark * t + tint * 4 * t * (1 - t))};
            }};
  }
"""
