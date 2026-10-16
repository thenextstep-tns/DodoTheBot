"""
The tile library editor — everything that can be put on the map.

Two places, one editor:

* ``/dodoland/tiles`` — the bot owner's page. Every tile everywhere, all of it
  editable, and the categories.
* a section of each server's DodoLand page — that server's view: the global
  tiles (read-only unless you are the bot owner) and the server's own tiles,
  which its admins upload, edit and remove. This is what the asset library used
  to be, and why it could be replaced completely.

Each tile carries its **layer**, **who has access**, the **requirement** a player
must meet, whether **roads can cross** it, whether it is **resizable** and to
what range, and its scale in px per map cell.

Structural edits (add, move, remove, recategorise) reload the page, the one way
it can never show an order the server does not hold. Field edits save in place:
with hundreds of tiles a reload per checkbox would make the editor unusable.
"""

from __future__ import annotations

import base64
import html
import json
from typing import Optional

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
.tlpage { max-width: 1240px; }
.tlbox { background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius-md); padding: 12px 14px; margin: 14px 0; }
details.tlcat { background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius-md); margin: 10px 0; }
details.tlcat > summary { cursor: pointer; padding: 10px 14px; list-style: none;
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
details.tlcat > summary::-webkit-details-marker { display: none; }
details.tlcat > summary::before { content: "▸"; color: var(--muted); }
details.tlcat[open] > summary::before { content: "▾"; }
details.tlcat > summary h2 { margin: 0; }
.tlsummary { color: var(--muted); font-size: 12px; }
.tlbody { padding: 0 14px 14px; }
.tlcathead, .tlbulk { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  border-top: 1px solid var(--line); padding: 10px 0; font-size: 13px; }
.tlgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 10px; }
.tltile { border: 1px solid var(--line); border-radius: 8px; padding: 8px;
  display: flex; flex-direction: column; gap: 5px; font-size: 12px; }
.tltile.ro { opacity: .92; }
.tltile.own { border-color: var(--color-primary, #c33); }
.tlvars { display: flex; flex-wrap: wrap; gap: 4px; }
.tlvar { position: relative; width: 52px; height: 52px; border: 1px solid var(--line);
  border-radius: 4px; overflow: hidden;
  background: repeating-conic-gradient(#8884 0 25%, transparent 0 50%) 0 0 / 12px 12px; }
.tlvar img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; }
.tlvar button { position: absolute; top: 1px; right: 1px; padding: 0 5px; font-size: 11px;
  line-height: 16px; min-height: 0; }
.tlrow { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.tlrow > .grow { flex: 1; min-width: 0; }
.tlrow input[type=number] { width: 4.6em; }
.tlrow button, .tlcathead button, .tlbulk button { padding: 3px 8px; font-size: 12px; }
.tlk { color: var(--muted); min-width: 5.2em; }
.tlpack { color: var(--muted); font-size: 11px; }
.tlbadge { font-size: 10px; padding: 1px 6px; border-radius: 9px; border: 1px solid var(--line);
  color: var(--muted); }
.tlmsg { min-height: 1em; }
.tlmsg.bad { color: var(--color-danger, #c0392b); }
.tladd { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }
.tladd label { display: flex; flex-direction: column; gap: 3px; font-size: 13px; }
.tlempty { color: var(--muted); font-size: 13px; }
</style>
"""

_SHORT = {"environment": "Environment", "objects": "Map objects", "buildings": "Buildings"}


def _options(pairs, selected, *, keep: bool = False) -> str:
    out = ['<option value="__keep">— leave as is —</option>'] if keep else []
    for value, label in pairs:
        chosen = " selected" if (not keep and str(value) == str(selected)) else ""
        out.append(f'<option value="{_e(value)}"{chosen}>{_e(label)}</option>')
    return "".join(out)


def _category_options(categories: list[dict], selected: str) -> str:
    return _options([("", "Uncategorised")] + [(c["cat_id"], c["name"]) for c in categories],
                    selected)


class _Ctx:
    """What one rendering of the editor knows about who is looking."""

    def __init__(self, *, owner: bool, guild_id: Optional[int], buildings: list[dict],
                 api: str, art: str) -> None:
        self.owner = owner
        self.guild_id = guild_id
        self.buildings = buildings
        self.api = api
        self.art = art

    def can_edit(self, tile: dict) -> bool:
        return self.owner or (self.guild_id is not None and tile["guild_id"] == self.guild_id)

    def building_options(self, selected: str, *, keep: bool = False) -> str:
        pairs = [("", "nothing")] + [(b["key"], b.get("name") or b["key"]) for b in self.buildings]
        if selected and selected not in {p[0] for p in pairs}:
            pairs.append((selected, f"{selected} (not on this server)"))
        return _options(pairs, selected, keep=keep)


def _fields(tile: dict, ctx: _Ctx, dis: str) -> str:
    """The rule fields of one tile card."""
    req = tile["requires"]
    access = "".join(
        f'<label><input type="checkbox" class="tlacc" value="{role}"{dis}'
        f'{" checked" if role in tile["access"] else ""}> {_e(label)}</label>'
        for role, label in tile_rules.ROLES)
    return f"""
  <div class="tlrow"><span class="tlk">Layer</span>
    <select class="tlf grow" data-f="layer"{dis}>{_options(tile_rules.LAYERS, tile['layer'])}</select>
    <select class="tlf" data-f="placement" title="Painted ground or a placed feature (only the environment is painted)"{dis}>{_options(tile_rules.PLACEMENTS, tile['placement'])}</select></div>
  <div class="tlrow"><span class="tlk">Access</span>{access}</div>
  <div class="tlrow" title="What a player must have reached first. Admins are never locked."><span class="tlk">Requires</span>
    <select class="tlreqb grow"{dis}>{ctx.building_options(req['building'])}</select>
    tier <input type="number" class="tlreqt" min="0" max="12" value="{req['tier']}"{dis}></div>
  <div class="tlrow"><label title="Whether a road may be drawn through it"><input type="checkbox" class="tlf"
       data-f="passable"{dis}{" checked" if tile['passable'] else ""}> Roads can cross</label>
    <label title="Whether a town's area of influence can grow over it"><input type="checkbox" class="tlf"
       data-f="spreads"{dis}{" checked" if tile['spreads'] else ""}> Influence spreads</label></div>
  <div class="tlrow"><label><input type="checkbox" class="tlf" data-f="resizable"{dis}
       {" checked" if tile['resizable'] else ""}> Resizable</label>
    <input type="number" class="tlf" data-f="scale_min" step="0.05" min="{tile_rules.SCALE_FLOOR}"
       max="{tile_rules.SCALE_CEILING}" value="{tile['scale_min']}"{dis} title="Smallest">–
    <input type="number" class="tlf" data-f="scale_max" step="0.05" min="{tile_rules.SCALE_FLOOR}"
       max="{tile_rules.SCALE_CEILING}" value="{tile['scale_max']}"{dis} title="Largest">×</div>
  <div class="tlrow" title="At night it lights the ground around it: how far, in map cells (0 = no light), and in what colour"><span class="tlk">Light</span>
    <input type="number" class="tlf" data-f="light_radius" step="0.5" min="0" max="{tile_rules.MAX_LIGHT}"
       value="{tile['light_radius']}"{dis}> cells
    <input type="color" class="tlf" data-f="light_colour" value="{tile['light_colour']}"{dis}></div>
  <div class="tlrow" title="How many of this art's pixels make one map cell"><span class="tlk">Scale</span>
    <input type="number" class="tlf" data-f="cell_px" list="tlcellsizes" min="{tile_rules.MIN_CELL}"
       max="{tile_rules.MAX_CELL}" value="{tile['cell_px']}"{dis}> px per map cell</div>"""


def _tile_card(tile: dict, categories: list[dict], ctx: _Ctx) -> str:
    editable = ctx.can_edit(tile)
    dis = "" if editable else " disabled"
    variants = "".join(
        f'<div class="tlvar"><img alt="" loading="lazy" src="{ctx.art}{_e(vid)}">'
        + (f'<button class="tldelvar" data-vid="{_e(vid)}" title="Remove this variant">×</button>'
           if editable else "") + "</div>"
        for vid in tile["variants"])
    count = len(tile["variants"])
    scope = ("<span class=\"tlbadge\">this server's</span>" if tile["guild_id"]
             else "<span class=\"tlbadge\">all servers</span>")
    tools = ""
    if editable:
        tools = f"""
  <div class="tlrow">
    <button class="tlmove" data-delta="-1" title="Move earlier">◀</button>
    <button class="tlmove" data-delta="1" title="Move later">▶</button>
    <span class="tlpack">{count} variant{'' if count == 1 else 's'}</span>
    <label class="small" style="margin-left:auto">+ variant
      <input type="file" class="tladdvar" hidden accept="image/png,image/webp,image/gif,image/svg+xml"></label>
    <button class="tldel">Remove</button>
  </div>"""
    pack = f'<span class="tlpack">from {_e(tile["pack"])}</span>' if tile.get("pack") else ""
    return f"""
<div class="tltile{'' if editable else ' ro'}{' own' if tile['guild_id'] else ''}" data-tile="{_e(tile['tile_id'])}">
  <div class="tlvars">{variants}</div>
  <div class="tlrow"><input type="text" class="tlname grow" maxlength="{tile_rules.MAX_NAME}"
       value="{_e(tile['name'])}"{dis}>{'<button class="tlrename">Save</button>' if editable else ''}{scope}</div>
  <div class="tlrow"><select class="tlcatsel grow"{dis}>{_category_options(categories, tile.get('cat_id') or '')}</select></div>
  {_fields(tile, ctx, dis)}
  {tools}
  {pack}
  <span class="tlmsg small muted"></span>
</div>"""


def _summary(tiles: list[dict]) -> str:
    parts = []
    for layer, _ in tile_rules.LAYERS:
        n = sum(1 for t in tiles if t["layer"] == layer)
        if n:
            parts.append(f"{n} {_SHORT[layer].lower()}")
    nobody = sum(1 for t in tiles if not t["access"])
    if nobody:
        parts.append(f"{nobody} owner-only")
    blocked = sum(1 for t in tiles if not t["passable"])
    if blocked:
        parts.append(f"{blocked} block roads")
    own = sum(1 for t in tiles if t["guild_id"])
    if own:
        parts.append(f"{own} this server's")
    return " · ".join(parts)


def _bulk(ctx: _Ctx, count: int) -> str:
    keep = '<option value="__keep">— leave —</option>'
    yesno = keep + '<option value="1">yes</option><option value="0">no</option>'
    access = keep + "".join(f'<option value="{v}">{l}</option>' for v, l in (
        ("admin,player", "admins and players"), ("admin", "admins only"),
        ("player", "players only"), ("", "nobody (owner only)")))
    return f"""
  <div class="tlbulk"><b>Set every tile here{'' if ctx.owner else ' that is this server’s'}:</b>
    layer <select class="tlbk" data-f="layer">{_options(tile_rules.LAYERS, '', keep=True)}</select>
    access <select class="tlbk" data-f="access">{access}</select>
    requires <select class="tlbk" data-f="req_building">{ctx.building_options('', keep=True)}</select>
    tier <input type="number" class="tlbk" data-f="req_tier" min="0" max="12" placeholder="—">
    roads cross <select class="tlbk" data-f="passable">{yesno}</select>
    influence spreads <select class="tlbk" data-f="spreads">{yesno}</select>
    resizable <select class="tlbk" data-f="resizable">{yesno}</select>
    <button class="tlbulkapply">Apply to {count}</button>
    <span class="tlmsg small muted"></span></div>"""


def tiles_html(library: tile_rules.TileLibrary, *, heading: bool = True, owner: bool = True,
               guild_id: Optional[int] = None, buildings: Optional[list[dict]] = None) -> str:
    """The whole editor.

    ``owner`` with no ``guild_id`` is the owner's page: everything, everywhere.
    With a ``guild_id`` it is that server's section — global tiles plus its own,
    with the global ones read-only unless ``owner``.
    """
    if guild_id is None:
        ctx = _Ctx(owner=True, guild_id=None, buildings=buildings or [],
                   api="/api/dodoland/tiles", art="/dodoland/tiles/art/")
    else:
        ctx = _Ctx(owner=owner, guild_id=int(guild_id), buildings=buildings or [],
                   api=f"/api/guild/{int(guild_id)}/dodoland/tiles",
                   art=f"/guild/{int(guild_id)}/dodoland/tiles/art/")
    categories = library.categories()
    groups = library.grouped(guild_id)
    sections = []
    for cat, tiles in groups:
        real = bool(cat["cat_id"])
        head = ""
        if real and ctx.owner:
            head = f"""
  <div class="tlcathead">
    <input type="text" class="tlcatname" maxlength="{tile_rules.MAX_NAME}" value="{_e(cat['name'])}">
    <button class="tlcatrename">Rename</button>
    <button class="tlcatmove" data-delta="-1" title="Move up">▲</button>
    <button class="tlcatmove" data-delta="1" title="Move down">▼</button>
    <button class="tlcatdel">Delete</button>
    <span class="tlmsg small muted"></span>
  </div>"""
        editable_here = [t for t in tiles if ctx.can_edit(t)]
        if real and editable_here:
            head += _bulk(ctx, len(editable_here))
        cards = "".join(_tile_card(t, categories, ctx) for t in tiles) or \
            '<p class="tlempty">No tiles in this category yet.</p>'
        sections.append(f"""
<details class="tlcat" data-cat="{_e(cat['cat_id'])}">
  <summary><h2>{_e(cat['name'])} <span class="muted">· {len(tiles)}</span></h2>
    <span class="tlsummary">{_e(_summary(tiles))}</span></summary>
  <div class="tlbody">{head}
  <div class="tlgrid">{cards}</div></div>
</details>""")
    total = sum(len(t) for _, t in groups)
    body = "".join(sections) or '<p class="tlempty">The library is empty.</p>'
    new_category = ""
    if ctx.owner:
        new_category = f"""
  <div class="tlbox"><div class="tladd">
      <label>New category<input type="text" id="tlnewcat" maxlength="{tile_rules.MAX_NAME}" placeholder="Water"></label>
      <button id="tladdcat">Add category</button>
      <span id="tlcatmsg" class="tlmsg small muted"></span></div></div>"""
    scope_pick = ""
    if ctx.owner and ctx.guild_id is not None:
        scope_pick = """<label>For<select id="tlnewscope"><option value="server">this server only</option>
          <option value="global">all servers</option></select></label>"""
    who = ("Every tile on every server. Server admins see the global ones read-only and "
           "manage their own server's." if ctx.guild_id is None or ctx.owner else
           "The global tiles come from the bot owner and are read-only here. Tiles you "
           "upload belong to this server only, and you can edit and remove them.")
    return f"""{_STYLE}
<div class="tlpage" data-api="{_e(ctx.api)}">
  {'<div class="panelhead"><h1>🧱 Tile library</h1></div>' if heading else ''}
  <div class="explain"><p>Everything that can be put on the map. {who}
  Each tile has a <b>layer</b>, <b>access</b> (the bot owner can always use everything),
  a <b>requirement</b> a player must reach first — a building and its tier, as the asset
  library had — whether <b>roads can cross</b> it, whether it is <b>resizable</b>, and its
  <b>scale</b> in the art's pixels per map cell (16 or 32 for pixel art).
  {total} tile(s).</p></div>
  {new_category}
  <div class="tlbox"><div class="tladd">
      <label>Tile name<input type="text" id="tlnewname" maxlength="{tile_rules.MAX_NAME}" placeholder="Campfire"></label>
      <label>Category<select id="tlnewcatsel">{_category_options(categories, categories[0]['cat_id'] if categories else '')}</select></label>
      <label>Layer<select id="tlnewlayer">{_options(tile_rules.LAYERS, tile_rules.DEFAULT_LAYER)}</select></label>
      {scope_pick}
      <label>Image(s) — several files make several variants
        <input type="file" id="tlnewfile" multiple accept="image/png,image/webp,image/gif,image/svg+xml"></label>
      <button id="tladdtile">Add tile</button>
      <span id="tltilemsg" class="tlmsg small muted"></span>
  </div></div>
  {body}
</div>
<datalist id="tlcellsizes">{''.join(f'<option value="{s}"></option>' for s in tile_rules.CELL_SIZES)}</datalist>
<script>
(function () {{
  var API = {json.dumps(ctx.api)};
  function say(el, text, good) {{ if (!el) return; el.textContent = text; el.classList.toggle('bad', !good); }}
  function post(body) {{
    return fetch(API, {{method: 'POST', credentials: 'same-origin',
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
  function act(msg, body) {{
    say(msg, 'Saving...', true);
    return post(body).then(function (res) {{
      if (res.ok) {{ say(msg, 'Saved.', true); window.location.reload(); }}
      else say(msg, 'Refused: ' + res.error, false);
      return res;
    }});
  }}
  function save(msg, body) {{
    say(msg, 'Saving...', true);
    return post(body).then(function (res) {{
      say(msg, res.ok ? 'Saved.' : 'Refused: ' + res.error, res.ok);
      return res;
    }});
  }}
  function msgIn(el) {{ return el.querySelector('.tlmsg'); }}

  var KEY = 'dl-tiles-open';
  function openSet() {{ try {{ return JSON.parse(window.localStorage.getItem(KEY) || '[]'); }} catch (e) {{ return []; }} }}
  var wasOpen = openSet();
  document.querySelectorAll('details.tlcat').forEach(function (det) {{
    if (wasOpen.indexOf(det.dataset.cat) >= 0) det.open = true;
    det.addEventListener('toggle', function () {{
      var now = openSet().filter(function (id) {{ return id !== det.dataset.cat; }});
      if (det.open) now.push(det.dataset.cat);
      try {{ window.localStorage.setItem(KEY, JSON.stringify(now)); }} catch (e) {{}}
    }});
  }});

  var addCat = document.getElementById('tladdcat');
  if (addCat) addCat.addEventListener('click', function () {{
    act(document.getElementById('tlcatmsg'),
        {{action: 'add_category', name: document.getElementById('tlnewcat').value}});
  }});

  document.getElementById('tladdtile').addEventListener('click', function () {{
    var msg = document.getElementById('tltilemsg');
    var files = Array.prototype.slice.call(document.getElementById('tlnewfile').files || []);
    var name = document.getElementById('tlnewname').value;
    if (!files.length) {{ say(msg, 'Pick an image first.', false); return; }}
    if (!name.trim()) {{ say(msg, 'Give it a name.', false); return; }}
    var scope = document.getElementById('tlnewscope');
    say(msg, 'Uploading...', true);
    Promise.all(files.map(read)).then(function (images) {{
      act(msg, {{action: 'add_tile', name: name,
                 cat_id: document.getElementById('tlnewcatsel').value,
                 layer: document.getElementById('tlnewlayer').value,
                 scope: scope ? scope.value : '', images: images}});
    }}, function () {{ say(msg, 'That file could not be read.', false); }});
  }});

  document.querySelectorAll('details.tlcat').forEach(function (sec) {{
    var cat = sec.dataset.cat, head = sec.querySelector('.tlcathead');
    if (head) {{
      var msg = msgIn(head);
      head.querySelector('.tlcatrename').addEventListener('click', function () {{
        act(msg, {{action: 'rename_category', cat_id: cat, name: head.querySelector('.tlcatname').value}});
      }});
      head.querySelectorAll('.tlcatmove').forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          act(msg, {{action: 'move_category', cat_id: cat, delta: parseInt(btn.dataset.delta, 10)}});
        }});
      }});
      head.querySelector('.tlcatdel').addEventListener('click', function () {{
        if (window.confirm('Delete this category?')) act(msg, {{action: 'remove_category', cat_id: cat}});
      }});
    }}
    var bulk = sec.querySelector('.tlbulk');
    if (bulk) bulk.querySelector('.tlbulkapply').addEventListener('click', function () {{
      var fields = {{}}, said = [];
      bulk.querySelectorAll('.tlbk').forEach(function (el) {{
        // An empty select is a choice (nobody, nothing); an empty box is not.
        if (el.value === '__keep' || (el.tagName === 'INPUT' && el.value === '')) return;
        fields[el.dataset.f] = el.value; said.push(el.dataset.f + ' = ' + (el.value || 'none'));
      }});
      if (!said.length) {{ say(msgIn(bulk), 'Pick something to change first.', false); return; }}
      if (!window.confirm('Set every tile here: ' + said.join(', ') + '?')) return;
      act(msgIn(bulk), {{action: 'update_category', cat_id: cat, fields: fields}});
    }});
  }});

  document.querySelectorAll('.tltile:not(.ro)').forEach(function (card) {{
    var tile = card.dataset.tile, msg = msgIn(card);
    function field(name, value) {{ var f = {{}}; f[name] = value;
      return save(msg, {{action: 'update_tile', tile_id: tile, fields: f}}); }}
    card.querySelector('.tlrename').addEventListener('click', function () {{
      field('name', card.querySelector('.tlname').value);
    }});
    card.querySelector('.tlcatsel').addEventListener('change', function (ev) {{
      act(msg, {{action: 'update_tile', tile_id: tile, fields: {{cat_id: ev.target.value}}}});
    }});
    card.querySelectorAll('.tlf').forEach(function (el) {{
      el.addEventListener('change', function () {{
        field(el.dataset.f, el.type === 'checkbox' ? el.checked : el.value);
      }});
    }});
    card.querySelectorAll('.tlacc').forEach(function (box) {{
      box.addEventListener('change', function () {{
        field('access', Array.prototype.slice.call(card.querySelectorAll('.tlacc:checked'))
          .map(function (b) {{ return b.value; }}));
      }});
    }});
    function requirement() {{
      field('requires', {{building: card.querySelector('.tlreqb').value,
                         tier: parseInt(card.querySelector('.tlreqt').value || '0', 10)}});
    }}
    card.querySelector('.tlreqb').addEventListener('change', requirement);
    card.querySelector('.tlreqt').addEventListener('change', requirement);
    card.querySelectorAll('.tlmove').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        act(msg, {{action: 'move_tile', tile_id: tile, delta: parseInt(btn.dataset.delta, 10)}});
      }});
    }});
    card.querySelector('.tldel').addEventListener('click', function () {{
      if (window.confirm('Remove this tile and all its variants? Anything placed from it goes too.'))
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
#  Handlers
# --------------------------------------------------------------------------- #
async def tiles_page(request: web.Request):
    """The owner's page. Gated with require_owner in the route table."""
    from helpers.dodoland import buildings as building_rules
    from web.routes import _page

    return _page("Tile library", tiles_html(request.app["bot"].dodoland_tiles,
                                            buildings=building_rules.default_buildings()))


def _art_response(row) -> web.Response:
    if row is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")
    raw = row.get("data")
    return web.Response(
        body=bytes(raw) if raw is not None else b"",
        content_type=str(row.get("content_type") or "image/png"),
        # A variant id is never reused, so cache hard.
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )


async def tile_art(request: web.Request):
    """One variant's bytes, for the owner's page."""
    return _art_response(request.app["bot"].dodoland_tiles.art(request.match_info.get("vid") or ""))


async def guild_tile_art(request: web.Request):
    """One variant's bytes, if the tile it belongs to is visible to this server."""
    library, guild = request.app["bot"].dodoland_tiles, request["guild"]
    row = library.art(request.match_info.get("vid") or "")
    if row is None or library.visible(row.get("tile_id"), guild.id) is None:
        return _art_response(None)
    return _art_response(row)


def _fields_from(body: dict) -> dict:
    """Turn the editor's field names into the library's."""
    raw = dict(body.get("fields") or {})
    out = {}
    for key in ("name", "cat_id", "cell_px", "layer", "placement", "scale_min", "scale_max", "requires",
                "light_radius", "light_colour"):
        if key in raw:
            out[key] = raw[key]
    for key in ("passable", "spreads", "resizable"):
        if key in raw:
            value = raw[key]
            out[key] = value in (True, 1, "1", "true", "yes") if not isinstance(value, bool) else value
    if "access" in raw:
        value = raw["access"]
        out["access"] = [v for v in (value.split(",") if isinstance(value, str) else value) if v]
    if "req_building" in raw or "req_tier" in raw:
        out["requires"] = {"building": raw.get("req_building") or "",
                           "tier": raw.get("req_tier") or (1 if raw.get("req_building") else 0)}
    return out


async def _handle(request: web.Request, *, owner: bool, guild_id: Optional[int]):
    """Every edit, by ``action``. ``owner`` may touch anything; otherwise only
    tiles belonging to ``guild_id``, and never a category."""
    bot = request.app["bot"]
    library = bot.dodoland_tiles
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _bad("That request could not be read.")
    action = str(body.get("action") or "")

    def mine(tile_id) -> dict:
        tile = library.get(tile_id)
        if tile is None:
            raise tile_rules.TileError("That tile no longer exists.")
        if not owner and tile["guild_id"] != guild_id:
            raise tile_rules.TileError("That tile belongs to the bot owner; it is read-only here.")
        return tile

    try:
        if action in ("add_category", "rename_category", "move_category", "remove_category") and not owner:
            return _bad("Only the bot owner changes categories.")
        if action == "add_category":
            return web.json_response({"ok": True, "category": library.add_category(body.get("name"))})
        if action == "rename_category":
            library.rename_category(body.get("cat_id"), body.get("name"))
        elif action == "move_category":
            library.move_category(body.get("cat_id"), int(body.get("delta") or 0))
        elif action == "remove_category":
            library.remove_category(body.get("cat_id"))
        elif action == "update_category":
            changed = library.update_category(body.get("cat_id"),
                                              None if owner else guild_id, **_fields_from(body))
            return web.json_response({"ok": True, "changed": changed})
        elif action == "add_tile":
            images = body.get("images") or []
            if not images:
                return _bad("A tile needs at least one image.")
            if len(images) > tile_rules.MAX_VARIANTS:
                return _bad(f"A tile holds at most {tile_rules.MAX_VARIANTS} variants.")
            decoded = [_decode(image) for image in images]
            for blob, content_type in decoded:
                tile_rules.check_image(blob, content_type)
            # A server admin's upload is that server's. The owner chooses, and
            # on their own page there is no server to give it to.
            scope = tile_rules.GLOBAL
            if guild_id is not None and not (owner and body.get("scope") == "global"):
                scope = guild_id
            first, rest = decoded[0], decoded[1:]
            row = library.add_tile(name=body.get("name"), cat_id=body.get("cat_id"),
                                   data=first[0], content_type=first[1], guild_id=scope,
                                   layer=body.get("layer") or tile_rules.DEFAULT_LAYER,
                                   resizable=True)
            for blob, content_type in rest:
                library.add_variant(row["tile_id"], data=blob, content_type=content_type)
            return web.json_response({"ok": True, "tile": library.get(row["tile_id"])})
        elif action == "update_tile":
            mine(body.get("tile_id"))
            tile = library.update_tile(body.get("tile_id"), **_fields_from(body))
            return web.json_response({"ok": True, "tile": tile})
        elif action == "move_tile":
            mine(body.get("tile_id"))
            library.move_tile(body.get("tile_id"), int(body.get("delta") or 0))
        elif action == "remove_tile":
            mine(body.get("tile_id"))
            library.remove_tile(body.get("tile_id"))
            # Placed pieces of it would draw as broken images on somebody's map.
            bot.dodoland_decor.forget_tile(body.get("tile_id"))
        elif action == "add_variant":
            mine(body.get("tile_id"))
            blob, content_type = _decode(body)
            library.add_variant(body.get("tile_id"), data=blob, content_type=content_type)
        elif action == "remove_variant":
            mine(body.get("tile_id"))
            library.remove_variant(body.get("tile_id"), body.get("vid"))
        else:
            return _bad(f"Unknown action {action!r}.")
    except (tile_rules.TileError, ValueError, TypeError) as error:
        return _bad(error)
    return web.json_response({"ok": True})


async def api_tiles(request: web.Request):
    """The owner's endpoint. Gated with require_owner in the route table."""
    return await _handle(request, owner=True, guild_id=None)


async def api_guild_tiles(request: web.Request):
    """A server's endpoint. Gated with the panel's full scope; the bot owner
    arriving here keeps their rights over global tiles."""
    from helpers import panel_access

    return await _handle(request, owner=request.get("scope") == panel_access.SCOPE_OWNER,
                         guild_id=request["guild"].id)
