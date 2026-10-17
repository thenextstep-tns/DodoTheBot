"""
DodoLand's wiki: the owner's editor and the map's reader (helpers/dodoland/wiki.py).

* ``GET /dodoland/wiki`` - the bot owner's editor: a title and a body per
  section, moved up and down, added and removed, saved at once.
* ``POST /api/dodoland/wiki`` - saves it (``{sections: [{title, body}]}``).
* ``GET .../dodoland/wiki`` (the panel's map and a member's reader) - the wiki
  rendered, for the map's "?" button: ``{sections: [{title, html}]}``.
"""

from __future__ import annotations

import json

from aiohttp import web

from helpers.dodoland import wiki


def _collection():
    import config_py

    return config_py.dodoland_config


async def wiki_read(request: web.Request):
    """The wiki, rendered, for the map."""
    return web.json_response({"ok": True, "sections": [
        {"title": s["title"], "html": wiki.render(s["body"])} for s in wiki.sections(_collection())]})


async def api_wiki(request: web.Request):
    """The owner saves the wiki. Gated with require_owner in the route table."""
    try:
        body = await request.json()
        saved = wiki.save(_collection(), body.get("sections"))
    except (ValueError, AttributeError, json.JSONDecodeError) as error:
        return web.json_response({"ok": False, "error": str(error) or "That could not be read."}, status=400)
    return web.json_response({"ok": True, "count": len(saved)})


async def wiki_page(request: web.Request):
    """The owner's editor. Gated with require_owner in the route table."""
    from web.routes import _page

    data = json.dumps(wiki.sections(_collection())).replace("<", "\\u003c")
    body = f"""
<h1>📖 DodoLand wiki</h1>
<p class="muted">What members read from the map's <b>?</b> button. One section each: a title and its text.
In the text, a blank line starts a new paragraph, a line starting with <code>- </code> is a bullet, and
<code>**bold**</code> is bold. <a href="/dodoland/tiles">Tile library</a></p>
<div id="wk"></div>
<p><button id="wkadd" type="button">Add a section</button> <button id="wksave" type="button" class="primary">Save</button>
<span id="wkmsg" class="muted"></span></p>
<style>
.wksec {{ border: 1px solid var(--line, #ddd); border-radius: 10px; padding: 10px; margin: 10px 0; background: var(--panel, #fff); }}
.wksec input {{ width: 100%; font: inherit; font-weight: 700; padding: 6px 8px; margin-bottom: 6px; }}
.wksec textarea {{ width: 100%; min-height: 120px; font: inherit; padding: 6px 8px; }}
.wksec .acts {{ display: flex; gap: 6px; justify-content: flex-end; margin-top: 6px; }}
</style>
<script>
(function () {{
  var sections = {data}, host = document.getElementById('wk'), msg = document.getElementById('wkmsg');
  function esc(s) {{ return String(s).replace(/[&<>"]/g, function (c) {{ return {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}}[c]; }}); }}
  function read() {{
    host.querySelectorAll('.wksec').forEach(function (el, i) {{
      sections[i] = {{title: el.querySelector('input').value, body: el.querySelector('textarea').value}};
    }});
  }}
  function draw() {{
    host.innerHTML = sections.map(function (s, i) {{
      return '<div class="wksec"><input value="' + esc(s.title) + '" placeholder="Title">' +
        '<textarea placeholder="Text">' + esc(s.body) + '</textarea><div class="acts">' +
        '<button type="button" data-up="' + i + '">\\u25b2</button><button type="button" data-down="' + i + '">\\u25bc</button>' +
        '<button type="button" data-del="' + i + '" class="danger">Remove</button></div></div>';
    }}).join('');
    host.querySelectorAll('button').forEach(function (b) {{
      b.onclick = function () {{
        read();
        var i;
        if (b.dataset.up !== undefined && (i = +b.dataset.up) > 0) sections.splice(i - 1, 0, sections.splice(i, 1)[0]);
        if (b.dataset.down !== undefined && (i = +b.dataset.down) < sections.length - 1) sections.splice(i + 1, 0, sections.splice(i, 1)[0]);
        if (b.dataset.del !== undefined) sections.splice(+b.dataset.del, 1);
        draw();
      }};
    }});
  }}
  document.getElementById('wkadd').onclick = function () {{ read(); sections.push({{title: '', body: ''}}); draw(); }};
  document.getElementById('wksave').onclick = function () {{
    read(); msg.textContent = 'Saving\\u2026';
    fetch('/api/dodoland/wiki', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{sections: sections}})}})
      .then(function (r) {{ return r.json(); }})
      .then(function (res) {{ msg.textContent = res.ok ? 'Saved (' + res.count + ' sections).' : (res.error || 'Not saved.'); }})
      .catch(function (e) {{ msg.textContent = String(e); }});
  }};
  draw();
}})();
</script>"""
    return _page("DodoLand wiki", body)

