"""
The reaction grid page: every object down the side, every class across the top.

Pure rendering — no routing, no auth, no database. ``web/routes.py`` gates the
page and hands the data in, which keeps this importable from a test without
dragging the whole panel in behind it.

The grid is paginated because it is eighteen thousand cells. Twenty-five rows a
screen is 325 cells, which is already at the edge of what a browser lays out
without complaint, and far past what anyone reads at once.
"""

from __future__ import annotations

import html
import urllib.parse

PER_PAGE = 25
SOURCE_MARK = {"guild": ("✎", "written here"), "global": ("◆", "written for every server"),
               "seed": ("·", "shipped default"), "written": ("", "written for this kind of object"),
               "empty": ("", "nobody has decided yet")}


def _chip(stats: dict) -> str:
    """Stat deltas as compact signed chips, so a glance reads the whole cell."""
    if not stats:
        return ""
    parts = []
    for key, value in stats.items():
        sign = "+" if value > 0 else ""
        cls = "up" if value > 0 else "down"
        parts.append(f'<span class="rxstat {cls}">{key[:3].upper()} {sign}{value}</span>')
    return '<span class="rxstats">' + "".join(parts) + "</span>"


def _cell(emoji: str, cls: str, cell: dict) -> str:
    mark, why = SOURCE_MARK[cell["source"]]
    text = cell["text"]
    body = html.escape(text) if text else '<span class="rxempty">not decided</span>'
    return (f'<td class="rxcell rx-{cell["source"]}" data-emoji="{html.escape(emoji)}" '
            f'data-cls="{html.escape(cls)}" title="{html.escape(why)}" tabindex="0">'
            f'<span class="rxmark">{mark}</span>'
            f'<span class="rxtext">{body}</span>{_chip(cell["stats"])}</td>')


def _row(entry: dict, classes: list[dict], grid: dict) -> str:
    emoji = entry["char"]
    picture = (f'<img src="{html.escape(entry["url"])}" alt="" class="rxcustom">'
               if entry.get("custom") else f'<span class="rxglyph">{emoji}</span>')
    cells = "".join(_cell(emoji, c["key"], grid[emoji][c["key"]]) for c in classes)
    return (f'<tr data-emoji="{html.escape(emoji)}"><th class="rxhead" scope="row">{picture}'
            f'<span class="rxname">{html.escape(entry["name"])}</span></th>{cells}</tr>')


def _query(params: dict, **changes) -> str:
    merged = {k: v for k, v in {**params, **changes}.items() if v not in ("", None, 1)}
    return "?" + urllib.parse.urlencode(merged) if merged else ""


def _pager(guild_id: int, params: dict, page: int, pages: int, total: int) -> str:
    if pages <= 1:
        return f'<div class="rxpager"><span class="muted small">{total} objects</span></div>'
    base = f"/guild/{guild_id}/reactions"
    links = []
    if page > 1:
        links.append(f'<a class="chip" href="{base}{_query(params, page=page - 1)}">← previous</a>')
    links.append(f'<span class="muted small">page {page} of {pages} · {total} objects</span>')
    if page < pages:
        links.append(f'<a class="chip" href="{base}{_query(params, page=page + 1)}">next →</a>')
    return '<div class="rxpager">' + "".join(links) + "</div>"


def render(guild, classes: list[dict], rows: list[dict], grid: dict, groups: list[str],
           params: dict, page: int, pages: int, total: int, coverage: dict) -> str:
    """The whole page body. ``rows`` is only the current page of the catalogue."""
    heads = "".join(
        f'<th class="rxclass" title="{html.escape(c["perk"])}">'
        f'<span class="rxclassemoji">{c["emoji"]}</span>'
        f'<span class="rxclassname">{html.escape(c["name"])}</span>'
        f'<span class="rxclasspair">{html.escape(c["label"])}</span></th>'
        for c in classes)

    options = "".join(
        f'<option value="{html.escape(g)}"{" selected" if params.get("group") == g else ""}>'
        f'{html.escape(g)}</option>' for g in groups)

    body = "".join(_row(entry, classes, grid) for entry in rows) or (
        f'<tr><td class="muted" colspan="{len(classes) + 1}">Nothing matches that.</td></tr>')

    filled_pct = coverage["percent"]
    return f"""
    <div class="rxpage" data-guild="{guild.id}">
      <div class="panelhead"><h1>🐈 Reaction grid</h1></div>
      <div class="explain"><p>What each kind of cat does when you show it a thing.
      Click any cell to write it. What you write here applies to this server only;
      cells you leave alone fall back to the shared default.</p></div>

      <div class="rxbar">
        <form class="rxfilters" method="get">
          <select name="group"><option value="">Every group</option>{options}</select>
          <input type="search" name="q" placeholder="Search objects…"
                 value="{html.escape(params.get("q") or "")}" autocomplete="off">
          <button type="submit">Filter</button>
        </form>
        <div class="rxcoverage" title="{coverage['filled']} of {coverage['cells']} cells written">
          <div class="rxmeter"><i style="width:{min(100, filled_pct)}%"></i></div>
          <span class="muted small">{filled_pct}% written
          ({coverage['filled']} of {coverage['cells']})</span>
        </div>
      </div>

      {_pager(guild.id, params, page, pages, total)}

      <div class="rxscroll">
        <table class="rxgrid">
          <thead><tr><th class="rxcorner">Object</th>{heads}</tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>

      {_pager(guild.id, params, page, pages, total)}

      <div class="rxeditor" hidden>
        <div class="rxeditorhead"><b class="rxeditortitle"></b>
          <button class="rxclose" title="Close">✕</button></div>
        <textarea class="rxtextarea" rows="3" maxlength="160"
                  placeholder="Sits on them. They are warm now, and they are his."></textarea>
        <div class="rxeditorstats">
          <label>STR<input type="number" data-stat="strength" step="1"></label>
          <label>AGI<input type="number" data-stat="agility" step="1"></label>
          <label>INT<input type="number" data-stat="intellect" step="1"></label>
          <label>CHA<input type="number" data-stat="charm" step="1"></label>
        </div>
        <div class="rxeditorfoot">
          <button class="rxsave">Save</button>
          <button class="rxclear ghost">Clear</button>
          <span class="muted small rxeditornote"></span>
        </div>
      </div>
    </div>"""
