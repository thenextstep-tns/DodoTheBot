"""
Turn an uploaded map image into terrain the bot can read.

    py tools/dodoland_terrain_import.py <guild_id> [--scale 3] [--dry-run]

The map is the only real terrain there is, so this reads it rather than asking
anybody to paint a continent by hand. It opens a page in a browser, which
rasterises the image, sorts every cell into the nearest of the colours actually
present, and posts the result back here to be written as chunks.

**Why the browser does the rasterising.** The uploaded map may be an SVG, and an
SVG has no pixels until something renders it — a server-side rasteriser is a
dependency this project does not have and does not need, because the one piece
of software guaranteed to be in front of an admin is a browser. Rendering a
vector map at three times its nominal size also yields *more* coastline detail
than the source's own pixel grid would, which a raster import can never do.

This is a prototype of where the import belongs: the panel will do exactly this,
with the admin confirming the colour assignment. The flow is the same, which is
why it is worth building this way rather than as a throwaway.

**It never guesses what a colour means.** It reports the colours it found with
their coverage and uses the assignment in ``ASSIGNMENT`` below; anything
unassigned becomes ``unknown`` and shows up as a hole, because a map that
half-imported must look half-imported.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from helpers.dodoland import terrain as T  # noqa: E402

PORT = 8791

# Which colour in the uploaded map means which kind of ground. Keys are the hex
# the map actually uses; run with --dry-run to see what is in yours.
#
# For ESO for Dodos: a pale background showing through as land, four bands of
# sea shading toward the shore, and the lakes drawn last on top.
ASSIGNMENT: dict[str, str] = {
    "#e8eff4": "plains",     # the background the sea is cut out of — the land
    "#6a8abb": "deep",       # outermost band
    "#7b97c2": "sea",
    "#8aa3c9": "sea",
    "#95abcd": "shallows",   # the ring against the shore
    "#99b3e4": "lake",       # the inland blobs
}


def load_map(guild_id: int) -> tuple[bytes, str]:
    import config_py

    row = config_py.dodoland_config.find_one({"_id": int(guild_id)}, {"map": 1})
    if not row or not row.get("map"):
        raise SystemExit(f"guild {guild_id} has no map uploaded")
    image = row["map"]
    return bytes(image.get("data") or b""), str(image.get("content_type") or "")


def source_size(data: bytes, content_type: str) -> tuple[int, int]:
    """The map's own dimensions, from the SVG header or the PNG/JPEG chunk."""
    if "svg" in content_type:
        head = data[:2000].decode("utf-8", "replace")
        box = re.search(r'viewBox="\s*[\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)', head)
        if box:
            return int(float(box.group(1))), int(float(box.group(2)))
        w = re.search(r'\swidth="(\d+)', head)
        h = re.search(r'\sheight="(\d+)', head)
        if w and h:
            return int(w.group(1)), int(h.group(1))
        raise SystemExit("could not find the SVG's size")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    raise SystemExit(f"cannot measure a {content_type!r} map; convert it to PNG or SVG")


def sized_svg(data: bytes, width: int, height: int) -> bytes:
    """The same SVG asked to render at the grid's size.

    Rewriting width/height while leaving viewBox alone is what makes the browser
    rasterise the *vectors* at the target resolution rather than scaling up its
    own small bitmap — the whole reason a vector map can be imported finer than
    it was drawn.
    """
    text = data.decode("utf-8", "replace")
    text = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"', r"\1", text, count=1)
    text = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r"\1", text, count=1)
    text = text.replace("<svg", f'<svg width="{width}" height="{height}"', 1)
    return text.encode("utf-8")


PAGE = """<!doctype html><meta charset="utf-8"><title>Terrain import</title>
<body style="font:14px system-ui;background:#241d18;color:#efdcc0;padding:24px">
<h2>Reading the map…</h2><pre id="log"></pre>
<script>
const CFG = __CFG__;
const log = (m) => { document.getElementById('log').textContent += m + "\\n"; };

function nearest(r, g, b, table) {
  let best = 0, bestD = Infinity;
  for (let i = 0; i < table.length; i++) {
    const c = table[i];
    const d = (r-c[0])**2 + (g-c[1])**2 + (b-c[2])**2;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

const img = new Image();
img.onload = () => {
  const W = CFG.w, H = CFG.h, CH = CFG.chunk;
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d', {willReadFrequently: true});
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, W, H);
  log(`rendered ${W}x${H}`);
  const px = ctx.getImageData(0, 0, W, H).data;

  // Every distinct colour, so the tool can report what is actually in the map
  // rather than assuming what should be.
  const seen = new Map();
  for (let i = 0; i < px.length; i += 4) {
    const k = (px[i] << 16) | (px[i+1] << 8) | px[i+2];
    seen.set(k, (seen.get(k) || 0) + 1);
  }
  const found = [...seen.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40)
    .map(([k, n]) => ['#' + k.toString(16).padStart(6, '0'), n]);
  log(`${seen.size} distinct colours`);

  // Classify against the assignment's colours only. An antialiased edge pixel
  // lands on whichever side it is closest to, which is what a coastline wants.
  const table = CFG.colours.map(c => [
    parseInt(c.slice(1,3),16), parseInt(c.slice(3,5),16), parseInt(c.slice(5,7),16)]);
  const chunks = [];
  const cxs = Math.ceil(W / CH), cys = Math.ceil(H / CH);
  for (let cy = 0; cy < cys; cy++) {
    for (let cx = 0; cx < cxs; cx++) {
      const cells = new Array(CH * CH).fill(0);
      for (let y = 0; y < CH; y++) {
        const gy = cy * CH + y;
        if (gy >= H) break;
        for (let x = 0; x < CH; x++) {
          const gx = cx * CH + x;
          if (gx >= W) break;
          const o = (gy * W + gx) * 4;
          cells[y * CH + x] = CFG.kinds[nearest(px[o], px[o+1], px[o+2], table)];
        }
      }
      // Run-length, exactly as the store encodes it.
      let rle = [], v = null, run = 0;
      for (const c of cells) {
        if (c === v) { run++; continue; }
        if (v !== null) rle.push(run + 'x' + v);
        v = c; run = 1;
      }
      if (v !== null) rle.push(run + 'x' + v);
      chunks.push({cx, cy, rle: rle.join(' ')});
    }
    if (cy % 5 === 0) log(`chunk row ${cy}/${cys}`);
  }
  log(`${chunks.length} chunks, posting…`);
  fetch('/result', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chunks, found})})
    .then(() => { log('done — you can close this tab'); document.title = 'Imported'; });
};
img.onerror = () => log('the map image could not be rendered');
img.src = CFG.src;
</script>
"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("guild_id", type=int)
    ap.add_argument("--scale", type=float, default=3.0,
                    help="cells per unit of the map's own coordinates")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what was found and write nothing")
    args = ap.parse_args(argv[1:])

    data, content_type = load_map(args.guild_id)
    src_w, src_h = source_size(data, content_type)
    cells_w, cells_h = int(src_w * args.scale), int(src_h * args.scale)
    print(f"map     {content_type}, {src_w}x{src_h}, {len(data):,} bytes")
    print(f"grid    {cells_w}x{cells_h} cells "
          f"({cells_w * cells_h:,}), {-(-cells_w // T.CHUNK) * -(-cells_h // T.CHUNK)} chunks")

    kinds = T.base_kinds(T.TERRAIN)
    colours = list(ASSIGNMENT)
    indices = [T.index_of(kinds, ASSIGNMENT[c]) for c in colours]

    payload = sized_svg(data, cells_w, cells_h) if "svg" in content_type else data
    src = f"data:{content_type};base64," + base64.b64encode(payload).decode("ascii")
    page = PAGE.replace("__CFG__", json.dumps({
        "w": cells_w, "h": cells_h, "chunk": T.CHUNK,
        "colours": colours, "kinds": indices, "src": src,
    }))

    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            size = int(self.headers.get("Content-Length") or 0)
            result.update(json.loads(self.rfile.read(size)))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            done.set()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\nopen http://127.0.0.1:{PORT}/ — rendering there, waiting…")
    try:
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception:
        pass
    if not done.wait(timeout=600):
        print("timed out waiting for the browser")
        return 1
    server.shutdown()

    print("\ncolours found in the map, by coverage:")
    total = cells_w * cells_h
    for hexed, count in (result.get("found") or [])[:12]:
        known = ASSIGNMENT.get(hexed)
        print(f"  {hexed}  {count / total:6.2%}  -> {known or 'UNASSIGNED -> unknown'}")

    chunks = result.get("chunks") or []
    counts: dict[int, int] = {}
    for chunk in chunks:
        for token in chunk["rle"].split():
            run, _, value = token.partition("x")
            counts[int(value)] = counts.get(int(value), 0) + int(run)
    print("\nterrain written:")
    for index, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kinds[index]['label']:<12} {count / total:6.2%}  ({count:,} cells)")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    import config_py
    from helpers.dodoland.terrain import TerrainStore

    store = TerrainStore(config_py.dodoland_chunks, config_py.dodoland_world)
    store.wipe(args.guild_id, layer=T.TERRAIN)
    store.set_world(args.guild_id, cells_w=cells_w, cells_h=cells_h,
                    source_w=src_w, source_h=src_h, kinds=kinds)
    for chunk in chunks:
        store._chunks.update_one(
            {"guild_id": int(args.guild_id), "layer": T.TERRAIN,
             "cx": chunk["cx"], "cy": chunk["cy"]},
            {"$set": {"rle": chunk["rle"]}}, upsert=True)
    print(f"\nwrote {len(chunks)} chunks for guild {args.guild_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
