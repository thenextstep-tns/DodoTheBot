"""
Look at the artwork without a bot, a database or a login.

DodoLand's towns are drawn by ``helpers/dodoland/townart.py`` and animated by
``web/dodoland/theme.py``. Neither can be judged by reading it: "the emblems are
hard to tell apart" and "the flourish looks bland" are things you find out by
looking, and the only place they were previously visible was a live map behind
an admin login on a server with real data on it.

    py tools/dodoland_art_preview.py            # writes and names an HTML file
    py tools/dodoland_art_preview.py out.html   # somewhere specific

Every shape at every tier, every emblem, every flourish level, and a few whole
towns. It imports the same two modules the map does, so what it shows is what
the map shows — there is no second copy of the drawing anywhere, which is the
one thing that would make this worse than useless.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from helpers.dodoland import flourish as flourish_rules  # noqa: E402
from helpers.dodoland import townart  # noqa: E402
from web.dodoland import theme  # noqa: E402


def _svg(fragment: str, *, width: int = 200, extra: str = "",
         box: str = "") -> str:
    """One drawing, wrapped the way the map wraps it.

    ``box`` overrides the viewBox to crop away empty sky — only for looking at
    a single building, never for a whole town, which has to be judged in the
    box the map actually gives it.
    """
    view = box or f"0 0 {townart.WIDTH:.0f} {townart.HEIGHT:.0f}"
    return (f'<div class="dltown close {extra}" style="width:{width}px">'
            f'<svg viewBox="{view}" '
            f'xmlns="http://www.w3.org/2000/svg">{fragment}</svg></div>')


def _town(rows, **kwargs) -> str:
    return townart.town_svg(rows, **kwargs)


def shapes_grid() -> str:
    """Every shape family, tier 1 to 6. The silhouette test, in one screen."""
    out = ""
    for shape in townart.SHAPES:
        cells = "".join(
            f'<div class="cell"><span class="lab">{tier}</span>'
            f'{_svg(townart.one_svg(shape, tier, symbol='star'), width=150, box='14 14 92 56')}</div>'
            for tier in range(1, 7))
        label = townart.SHAPE_LABELS.get(shape, shape)
        out += (f'<section><h2>{label}</h2>'
                f'<div class="row">{cells}</div></section>')
    return out


def emblems_grid() -> str:
    """Every emblem, at the size a mid-tier building hangs one."""
    cells = ""
    for name in sorted(townart.EMBLEMS):
        mark = townart._emblem(20, 20, name, 26, "#2f6fa8")
        cells += (f'<div class="cell"><span class="lab">{name}</span>'
                  f'<svg viewBox="0 0 40 40" width="80" height="80" '
                  f'xmlns="http://www.w3.org/2000/svg">{mark}</svg></div>')
    return f'<section><h2>emblems</h2><div class="row wrap">{cells}</div></section>'


def flourish_row() -> str:
    """The same town at every flourish level, which is how rank is read."""
    rows = [{"key": "library", "tier": 5}, {"key": "inn", "tier": 4},
            {"key": "menagerie", "tier": 3}, {"key": "chapel", "tier": 3}]
    shapes = {"library": "hall", "inn": "inn", "menagerie": "pen",
              "chapel": "chapel"}
    symbols = {"library": "book", "inn": "mug", "menagerie": "paw",
               "chapel": "dove"}
    cells = ""
    for level in range(0, 7):
        colour = ("", "#e8c07a", "#c0392b", "#d4a017", "#2f6fa8", "#7a4fa3",
                  "#ff6ec7")[level]
        art = _town(rows, flourish=level, glow=colour, uid=f"f{level}",
                    shapes=shapes, symbols=symbols)
        cells += (f'<div class="cell"><span class="lab">{level} · '
                  f'{flourish_rules.LEVELS[level]["label"]}</span>'
                  f'{_svg(art, width=260, extra=f"fl{level}" if level else "")}</div>')
    return f'<section><h2>flourish</h2><div class="row wrap">{cells}</div></section>'


def towns_row() -> str:
    """Whole towns: a newcomer, a middling one, and the biggest on the server."""
    small = [{"key": "inn", "tier": 1}]
    middle = [{"key": "inn", "tier": 3}, {"key": "library", "tier": 2},
              {"key": "forge", "tier": 2}]
    big = [{"key": "library", "tier": 6}, {"key": "inn", "tier": 6},
           {"key": "keep", "tier": 5}, {"key": "menagerie", "tier": 5},
           {"key": "chapel", "tier": 4}, {"key": "forge", "tier": 4},
           {"key": "gate", "tier": 3}]
    shapes = {"library": "hall", "inn": "inn", "forge": "works",
              "keep": "keep", "menagerie": "pen", "chapel": "chapel",
              "gate": "gate"}
    symbols = {"library": "book", "inn": "mug", "forge": "gear",
               "keep": "shield", "menagerie": "paw", "chapel": "dove",
               "gate": "door"}
    cells = ""
    for label, rows, level, reach in (("nothing built", [], 0, 0.0),
                                      ("a newcomer", small, 0, 0.05),
                                      ("middling", middle, 2, 0.3),
                                      ("the biggest, a Legend", big, 6, 1.0)):
        art = _town(rows, flourish=level, glow="#ff6ec7" if level == 6 else "",
                    uid=label.replace(" ", ""), shapes=shapes, symbols=symbols,
                    richness=reach)
        cells += (f'<div class="cell wide"><span class="lab">{label}</span>'
                  f'{_svg(art, width=330, extra=f"fl{level}" if level else "")}</div>')
    return f'<section><h2>towns</h2><div class="row wrap">{cells}</div></section>'


PAGE_CSS = """
body { padding: 24px 28px 80px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .1em;
     color: var(--soft); margin: 28px 0 6px; }
.row { display: flex; gap: 12px; align-items: flex-start; }
.row.wrap { flex-wrap: wrap; }
.cell { background: var(--paper); border: 1px solid var(--edge);
        border-radius: 10px; padding: 10px; }
.lab { display: block; font-size: 11px; color: var(--soft); margin-bottom: 4px; }
.dltown svg { display: block; width: 100%; height: auto; overflow: visible; }
.note { color: var(--soft); max-width: 62em; }
"""


def build(sections: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>DodoLand artwork</title>
<style>{theme.PALETTE}{theme.CHROME}{theme.TOWN_ART_CSS}{PAGE_CSS}</style>
</head><body>
<h1>DodoLand artwork</h1>
<p class="note">Straight out of <code>helpers/dodoland/townart.py</code> and
<code>web/dodoland/theme.py</code>, wrapped exactly as the map wraps it
(<code>.dltown.close</code>, so the close-up flourishes and the walking are
running). Nothing here is a second copy of the drawing.</p>
{sections}
</body></html>"""


# Four pages rather than one. A single page ran to several screens of scrolling,
# and the section you wanted was never the one on screen.
PAGES = {
    "": lambda: towns_row() + flourish_row(),
    "-shapes": shapes_grid,
    "-emblems": emblems_grid,
}


def main(argv: list[str]) -> int:
    stem = pathlib.Path(argv[1] if len(argv) > 1 else "dodoland_art.html")
    for suffix, section in PAGES.items():
        target = stem.with_name(stem.stem + suffix + stem.suffix)
        target.write_text(build(section()), encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
