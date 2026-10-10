"""
The tile library page — the bot owner's toolkit for painting the map.

Owner-only and not under ``/guild/{gid}``: the library is shared by every
server, so it belongs to no one guild's panel. It is also embedded as an
owner-only section of each server's DodoLand page (``heading=False``).

Each tile says **where it may be used and by whom**: a grid of layers against
user types. The owner is not a column — they can use everything everywhere.

Structural edits (add, move, remove, recategorise) reload the page, the one way
it can never show an order the server does not hold. Ticking a use or changing
a grid size saves in place: with a few hundred tiles a reload per checkbox would
make the grid unusable.
"""

from __future__ import annotations

import base64
import html

from aiohttp import web

from helpers.dodoland import tiles as tile_rules


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _bad(error) -> web.Response:
    return web.json_response({"ok": False, "error": str(error)})


def _decode(body: dict) -> tuple[bytes, str]:
    content_type = str(body.get("content_type") or "").lower()
    try:
        blob = base64.b64decode(str(body.get("data") or "").split(",")[-1], validate=True)
    except Exception:  # noqa: BLE001 - any decoding failure is the same refusal
        raise tile_rules.TileError("That upload could not be read.") from None
    return blob, content_type


# --------------------------------------------------------------------------- #
#  Rendering
# --------------------------------------------------------------------------- #
_STYLE = """
<style>
.tlpage { max-width: 1180px; }
.tlbox { background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius-md); padding: 12px 14px; margin: 14px 0; }
details.tlcat { background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius-md); margin: 10px 0; }
details.tlcat > summary { cursor: pointer; padding: 10px 14px; list-style: none;
  display: flex; align-items: baseline; gap: 10px; }
details.tlcat > summary::-webkit-details-marker { display: none; }
details.tlcat > summary::before { content: "▸"; color: var(--muted); }
details.tlcat[open] > summary::before { content: "▾"; }
details.tlcat > summary h2 { margin: 0; }
.tlsummary { color: var(--muted); font-size: 12px; }
.tlbody { padding: 0 14px 14px; }
.tlcathead { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  border-top: 1px solid var(--line); padding: 10px 0; }
.tlbulk { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  border-top: 1px solid var(--line); padding: 10px 0; font-size: 13px; }
.tlgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 10px; }
.tltile { border: 1px solid var(--line); border-radius: 8px; padding: 8px;
  display: flex; flex-direction: column; gap: 6px; }
.tlvars { display: flex; flex-wrap: wrap; gap: 4px; }
.tlvar { position: relative; width: 52px; height: 52px; border: 1px solid var(--line);
  border-radius: 4px; overflow: hidden;
  background: repeating-conic-gradient(#8884 0 25%, transparent 0 50%) 0 0 / 12px 12px; }
.tlvar img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; }
.tlvar button { position: absolute; top: 1px; right: 1px; padding: 0 5px; font-size: 11px;
  line-height: 16px; min-height: 0; }
.tlrow { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.tlrow input[type=text], .tlrow select { flex: 1; min-width: 0; }
.tlrow button, .tlcathead button, .tlbulk button { padding: 3px 8px; font-size: 12px; }
table.tluses { border-collapse: collapse; font-size: 12px; border: 0; border-radius: 0;
  width: 100%; overflow: visible; }
table.tluses th, table.tluses td { padding: 1px 4px; border: 0; text-align: center; }
table.tluses th:first-child, table.tluses td:first-child { text-align: left; }
.tlpack { color: var(--muted); font-size: 11px; }
.tlmsg { min-height: 1em; }
.tlmsg.bad { color: var(--color-danger, #c0392b); }
.tladd { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }
.tladd label { display: flex; flex-direction: column; gap: 3px; font-size: 13px; }
.tlempty { color: var(--muted); font-size: 13px; }
</style>
"""

# Short row labels for the matrix; the long ones are in the legend above it.
_SHORT = {"environment": "Environment", "objects": "Map objects", "buildings": "Buildings"}


def _category_options(categories: list[dict], selected: str) -> str:
    out = [f'<option value=""{" selected" if not selected else ""}>Uncategorised</option>']
    for cat in categories:
        chosen = " selected" if cat["cat_id"] == selected else ""
        out.append(f'<option value="{_e(cat["cat_id"])}"{chosen}>{_e(cat["name"])}</option>')
    return "".join(out)


def _cell_options(selected: int) -> str:
    return "".join(f'<option value="{size}"{" selected" if size == selected else ""}>{size}px grid</option>'
                   for size in tile_rules.CELL_SIZES)


def _uses_matrix(uses: list[str], cls: str = "tluse") -> str:
    """Layers down the side, user types across the top."""
    head = "".join(f"<th>{_e(label)}</th>" for _, label in tile_rules.ROLES)
    rows = []
    for layer, _ in tile_rules.LAYERS:
        cells = "".join(
            f'<td><input type="checkbox" class="{cls}" data-use="{layer}:{role}"'
            f'{" checked" if f"{layer}:{role}" in uses else ""}></td>'
            for role, _ in tile_rules.ROLES)
        rows.append(f"<tr><td>{_e(_SHORT.get(layer, layer))}</td>{cells}</tr>")
    return f'<table class="tluses"><tr><th></th>{head}</tr>{"".join(rows)}</table>'


def _tile_card(tile: dict, categories: list[dict]) -> str:
    variants = "".join(
        f'<div class="tlvar"><img alt="" loading="lazy" src="/dodoland/tiles/art/{_e(vid)}">'
        f'<button class="tldelvar" data-vid="{_e(vid)}" title="Remove this variant">×</button></div>'
        for vid in tile.get("variants") or [])
    count = len(tile.get("variants") or [])
    pack = f'<span class="tlpack">from {_e(tile["pack"])}</span>' if tile.get("pack") else ""
    return f"""
<div class="tltile" data-tile="{_e(tile['tile_id'])}">
  <div class="tlvars">{variants}</div>
  <div class="tlrow"><input type="text" class="tlname" maxlength="{tile_rules.MAX_NAME}"
       value="{_e(tile.get('name'))}"><button class="tlrename">Save</button></div>
  <div class="tlrow"><select class="tlcatsel">{_category_options(categories, tile.get('cat_id') or '')}</select>
    <select class="tlcell" title="The pixel grid this art was drawn on">{_cell_options(tile.get('cell_px') or 16)}</select></div>
  {_uses_matrix(tile.get('uses') or [])}
  <div class="tlrow">
    <button class="tlmove" data-delta="-1" title="Move earlier">◀</button>
    <button class="tlmove" data-delta="1" title="Move later">▶</button>
    <span class="tlpack">{count} variant{'' if count == 1 else 's'}</span>
    <label class="small" style="margin-left:auto">+ variant
      <input type="file" class="tladdvar" hidden accept="image/png,image/webp,image/gif,image/svg+xml"></label>
    <button class="tldel">Remove</button>
  </div>
  {pack}
  <span class="tlmsg small muted"></span>
</div>"""


def _usage_summary(tiles: list[dict]) -> str:
    """'12 environment · 30 map objects' — what a folded category holds."""
    parts = []
    for layer, _ in tile_rules.LAYERS:
        n = sum(1 for t in tiles if any(u.startswith(layer + ":") for u in t.get("uses") or []))
        if n:
            parts.append(f"{n} {_SHORT.get(layer, layer).lower()}")
    unused = sum(1 for t in tiles if not t.get("uses"))
    if unused:
        parts.append(f"{unused} not usable yet")
    return " · ".join(parts)


def tiles_html(library: tile_rules.TileLibrary, *, heading: bool = True) -> str:
    """The whole editor. ``heading=False`` drops the page title, for when it is
    embedded as a section of a server's DodoLand page — the same editor, the
    same library, reachable from where the owner already works."""
    categories = library.categories()
    groups = library.grouped()
    sections = []
    for cat, tiles in groups:
        real = bool(cat["cat_id"])
        head_tools = ""
        if real:
            head_tools = f"""
  <div class="tlcathead">
    <input type="text" class="tlcatname" maxlength="{tile_rules.MAX_NAME}" value="{_e(cat['name'])}">
    <button class="tlcatrename">Rename</button>
    <button class="tlcatmove" data-delta="-1" title="Move up">▲</button>
    <button class="tlcatmove" data-delta="1" title="Move down">▼</button>
    <button class="tlcatdel">Delete</button>
    <span class="tlmsg small muted"></span>
  </div>"""
            if tiles:
                head_tools += f"""
  <div class="tlbulk"><span>Set every tile in this category to:</span>
    {_uses_matrix([], cls='tlbulkuse')}
    <button class="tlbulkapply">Apply to all {len(tiles)}</button>
    <span class="tlmsg small muted"></span></div>"""
        cards = "".join(_tile_card(t, categories) for t in tiles) or \
            '<p class="tlempty">No tiles in this category yet.</p>'
        sections.append(f"""
<details class="tlcat" data-cat="{_e(cat['cat_id'])}">
  <summary><h2>{_e(cat['name'])} <span class="muted">· {len(tiles)}</span></h2>
    <span class="tlsummary">{_e(_usage_summary(tiles))}</span></summary>
  <div class="tlbody">{head_tools}
  <div class="tlgrid">{cards}</div></div>
</details>""")
    total = sum(len(tiles) for _, tiles in groups)
    body = "".join(sections) or '<p class="tlempty">The library is empty. Add a category, then a tile.</p>'
    legend = "; ".join(f"<b>{_e(_SHORT[k])}</b> is {_e(label.split('(')[-1].rstrip(')'))}"
                       for k, label in tile_rules.LAYERS)
    return f"""{_STYLE}
<div class="tlpage">
  {'<div class="panelhead"><h1>🧱 Tile library</h1></div>' if heading else ''}
  <div class="explain"><p>The tiles every server paints its map with. Shared by all
  servers; only the bot owner edits it. Tick where each tile may be used and by whom —
  {legend}. The bot owner can use every tile everywhere; road tiles are the bot's
  (layer 2) and are not ticked here. A tile can hold up to {tile_rules.MAX_VARIANTS}
  variants; the map picks one per cell so repeated ground does not read as wallpaper.
  Set the grid size to the one the art was drawn on, so a 32px pack's tree is not
  drawn twice the size of a 16px pack's.
  {total} tile(s) in {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}.</p></div>

  <div class="tlbox">
    <div class="tladd">
      <label>New category<input type="text" id="tlnewcat" maxlength="{tile_rules.MAX_NAME}" placeholder="Water"></label>
      <button id="tladdcat">Add category</button>
      <span id="tlcatmsg" class="tlmsg small muted"></span>
    </div>
  </div>

  <div class="tlbox">
    <div class="tladd">
      <label>Tile name<input type="text" id="tlnewname" maxlength="{tile_rules.MAX_NAME}" placeholder="Deep sea"></label>
      <label>Category<select id="tlnewcatsel">{_category_options(categories, categories[0]['cat_id'] if categories else '')}</select></label>
      <label>Grid<select id="tlnewcell">{_cell_options(tile_rules.DEFAULT_CELL)}</select></label>
      <label>Image(s) — several files make several variants
        <input type="file" id="tlnewfile" multiple accept="image/png,image/webp,image/gif,image/svg+xml"></label>
      <button id="tladdtile">Add tile</button>
      <span id="tltilemsg" class="tlmsg small muted"></span>
    </div>
  </div>

  {body}
</div>
<script>
(function () {{
  function say(el, text, good) {{
    if (!el) return;
    el.textContent = text;
    el.classList.toggle('bad', !good);
  }}
  function post(body) {{
    return fetch('/api/dodoland/tiles', {{method: 'POST', credentials: 'same-origin',
      headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)}})
      .then(function (r) {{ return r.json(); }})
      .catch(function () {{ return {{ok: false, error: 'the server did not answer'}}; }});
  }}
  function read(file) {{
    return new Promise(function (resolve, reject) {{
      var reader = new FileReader();
      reader.onload = function () {{ resolve({{data: reader.result, content_type: file.type}}); }};
      reader.onerror = reject;
      reader.readAsDataURL(file);
    }});
  }}
  // Structural edits report next to their control, then reload.
  function act(msg, body) {{
    say(msg, 'Saving...', true);
    return post(body).then(function (res) {{
      if (res.ok) {{ say(msg, 'Saved.', true); window.location.reload(); }}
      else say(msg, 'Refused: ' + res.error, false);
      return res;
    }});
  }}
  // In-place edits report and stay put.
  function save(msg, body) {{
    say(msg, 'Saving...', true);
    return post(body).then(function (res) {{
      say(msg, res.ok ? 'Saved.' : 'Refused: ' + res.error, res.ok);
      return res;
    }});
  }}
  function msgIn(el) {{ return el.querySelector('.tlmsg'); }}
  function checked(root, cls) {{
    return Array.prototype.slice.call(root.querySelectorAll('.' + cls + ':checked'))
      .map(function (box) {{ return box.dataset.use; }});
  }}

  // Which categories are unfolded survives the reload every structural edit
  // does. A convenience only: without storage everything starts folded.
  var KEY = 'dl-tiles-open';
  function openSet() {{
    try {{ return JSON.parse(window.localStorage.getItem(KEY) || '[]'); }} catch (e) {{ return []; }}
  }}
  var wasOpen = openSet();
  document.querySelectorAll('details.tlcat').forEach(function (det) {{
    if (wasOpen.indexOf(det.dataset.cat) >= 0) det.open = true;
    det.addEventListener('toggle', function () {{
      var now = openSet().filter(function (id) {{ return id !== det.dataset.cat; }});
      if (det.open) now.push(det.dataset.cat);
      try {{ window.localStorage.setItem(KEY, JSON.stringify(now)); }} catch (e) {{}}
    }});
  }});

  document.getElementById('tladdcat').addEventListener('click', function () {{
    act(document.getElementById('tlcatmsg'),
        {{action: 'add_category', name: document.getElementById('tlnewcat').value}});
  }});

  document.getElementById('tladdtile').addEventListener('click', function () {{
    var msg = document.getElementById('tltilemsg');
    var files = Array.prototype.slice.call(document.getElementById('tlnewfile').files || []);
    var name = document.getElementById('tlnewname').value;
    if (!files.length) {{ say(msg, 'Pick an image first.', false); return; }}
    if (!name.trim()) {{ say(msg, 'Give it a name.', false); return; }}
    say(msg, 'Uploading...', true);
    Promise.all(files.map(read)).then(function (images) {{
      act(msg, {{action: 'add_tile', name: name,
                 cat_id: document.getElementById('tlnewcatsel').value,
                 cell_px: parseInt(document.getElementById('tlnewcell').value, 10),
                 images: images}});
    }}, function () {{ say(msg, 'That file could not be read.', false); }});
  }});

  document.querySelectorAll('details.tlcat').forEach(function (sec) {{
    var cat = sec.dataset.cat, head = sec.querySelector('.tlcathead');
    if (!head) return;
    var msg = msgIn(head);
    sec.querySelector('.tlcatrename').addEventListener('click', function () {{
      act(msg, {{action: 'rename_category', cat_id: cat,
                 name: sec.querySelector('.tlcatname').value}});
    }});
    sec.querySelectorAll('.tlcatmove').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        act(msg, {{action: 'move_category', cat_id: cat, delta: parseInt(btn.dataset.delta, 10)}});
      }});
    }});
    sec.querySelector('.tlcatdel').addEventListener('click', function () {{
      if (window.confirm('Delete this category?')) act(msg, {{action: 'remove_category', cat_id: cat}});
    }});
    var bulk = sec.querySelector('.tlbulk');
    if (bulk) bulk.querySelector('.tlbulkapply').addEventListener('click', function () {{
      var uses = checked(bulk, 'tlbulkuse');
      var what = uses.length ? uses.join(', ') : 'nowhere (nobody but the owner)';
      if (!window.confirm('Set every tile in this category to: ' + what + '?')) return;
      act(msgIn(bulk), {{action: 'set_category_uses', cat_id: cat, uses: uses}});
    }});
  }});

  document.querySelectorAll('.tltile').forEach(function (card) {{
    var tile = card.dataset.tile, msg = msgIn(card);
    card.querySelector('.tlrename').addEventListener('click', function () {{
      save(msg, {{action: 'update_tile', tile_id: tile, name: card.querySelector('.tlname').value}});
    }});
    card.querySelector('.tlcatsel').addEventListener('change', function (ev) {{
      act(msg, {{action: 'update_tile', tile_id: tile, cat_id: ev.target.value}});
    }});
    card.querySelector('.tlcell').addEventListener('change', function (ev) {{
      save(msg, {{action: 'update_tile', tile_id: tile, cell_px: parseInt(ev.target.value, 10)}});
    }});
    card.querySelectorAll('.tluse').forEach(function (box) {{
      box.addEventListener('change', function () {{
        save(msg, {{action: 'set_uses', tile_id: tile, uses: checked(card, 'tluse')}});
      }});
    }});
    card.querySelectorAll('.tlmove').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        act(msg, {{action: 'move_tile', tile_id: tile, delta: parseInt(btn.dataset.delta, 10)}});
      }});
    }});
    card.querySelector('.tldel').addEventListener('click', function () {{
      if (window.confirm('Remove this tile and all its variants?'))
        act(msg, {{action: 'remove_tile', tile_id: tile}});
    }});
    card.querySelectorAll('.tldelvar').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        act(msg, {{action: 'remove_variant', tile_id: tile, vid: btn.dataset.vid}});
      }});
    }});
    card.querySelector('.tladdvar').addEventListener('change', function (ev) {{
      var file = (ev.target.files || [])[0];
      if (!file) return;
      read(file).then(function (img) {{
        act(msg, {{action: 'add_variant', tile_id: tile, data: img.data, content_type: img.content_type}});
      }});
    }});
  }});
}})();
</script>"""


# --------------------------------------------------------------------------- #
#  Handlers. Gated with require_owner in the route table.
# --------------------------------------------------------------------------- #
async def tiles_page(request: web.Request):
    from web.routes import _page

    return _page("Tile library", tiles_html(request.app["bot"].dodoland_tiles))


async def tile_art(request: web.Request):
    """One variant's bytes. A variant id is never reused, so cache hard."""
    row = request.app["bot"].dodoland_tiles.art(request.match_info.get("vid") or "")
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )


async def api_tiles(request: web.Request):
    """Every library edit, by ``action``."""
    library = request.app["bot"].dodoland_tiles
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _bad("That request could not be read.")
    action = str(body.get("action") or "")
    try:
        if action == "add_category":
            return web.json_response({"ok": True, "category": library.add_category(body.get("name"))})
        if action == "rename_category":
            library.rename_category(body.get("cat_id"), body.get("name"))
        elif action == "move_category":
            library.move_category(body.get("cat_id"), int(body.get("delta") or 0))
        elif action == "remove_category":
            library.remove_category(body.get("cat_id"))
        elif action == "set_category_uses":
            changed = library.set_category_uses(body.get("cat_id"), body.get("uses") or [])
            return web.json_response({"ok": True, "changed": changed})
        elif action == "add_tile":
            images = body.get("images") or []
            if not images:
                return _bad("A tile needs at least one image.")
            if len(images) > tile_rules.MAX_VARIANTS:
                return _bad(f"A tile holds at most {tile_rules.MAX_VARIANTS} variants.")
            # Decode every file before storing any, so a bad third file does
            # not leave a tile with two of the three variants it was given.
            decoded = [_decode(image) for image in images]
            for blob, content_type in decoded:
                tile_rules.check_image(blob, content_type)
            first, rest = decoded[0], decoded[1:]
            row = library.add_tile(name=body.get("name"), cat_id=body.get("cat_id"),
                                   data=first[0], content_type=first[1],
                                   cell_px=body.get("cell_px") or tile_rules.DEFAULT_CELL)
            for blob, content_type in rest:
                library.add_variant(row["tile_id"], data=blob, content_type=content_type)
            return web.json_response({"ok": True, "tile": library.get(row["tile_id"])})
        elif action == "update_tile":
            library.update_tile(body.get("tile_id"), name=body.get("name"),
                                cat_id=body.get("cat_id"), cell_px=body.get("cell_px"))
        elif action == "set_uses":
            uses = library.set_uses(body.get("tile_id"), body.get("uses") or [])
            return web.json_response({"ok": True, "uses": uses})
        elif action == "move_tile":
            library.move_tile(body.get("tile_id"), int(body.get("delta") or 0))
        elif action == "remove_tile":
            library.remove_tile(body.get("tile_id"))
        elif action == "add_variant":
            blob, content_type = _decode(body)
            library.add_variant(body.get("tile_id"), data=blob, content_type=content_type)
        elif action == "remove_variant":
            library.remove_variant(body.get("tile_id"), body.get("vid"))
        else:
            return _bad(f"Unknown action {action!r}.")
    except (tile_rules.TileError, ValueError) as error:
        return _bad(error)
    return web.json_response({"ok": True})
