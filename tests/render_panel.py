"""
Render the tabletop panel pages to ``.preview/`` so they can be opened in a
browser and **clicked**.

``tests/test_dnd_panel.py`` asserts on HTML strings. That catches a missing
section and a leaked secret; it cannot catch a control that is wired to nothing,
because no test in this repo executes the page's JavaScript. Two bugs shipped
that way at once — a snowflake embedded as a numeric literal, and the status
element emitted below the script that looks it up — and between them every
control in the tabletop section did nothing at all, silently, for days.

So: after touching anything in ``web/dnd/pages.py``, run this, open the page,
click the thing you changed, and read the console.

    py tests/render_panel.py
    py -m http.server 8899 --directory .preview

The pages are real output from the real renderers against the in-memory store,
including a **real-shaped guild snowflake** — the thing that made the bug
invisible was a fixture id small enough to survive JavaScript intact.
"""

from __future__ import annotations

import io
import os
import sys
from random import Random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.test_dnd_panel as harness  # noqa: E402
from helpers import panel_access  # noqa: E402
from helpers.dnd import minds  # noqa: E402
from web.dnd import access, pages  # noqa: E402

OUT = ".preview"


def _write(name: str, body: str) -> None:
    css = io.open("web/static/panel.css", encoding="utf-8").read()
    io.open(os.path.join(OUT, name), "w", encoding="utf-8").write(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{name}</title><style>{css}</style></head><body>"
        '<header><a href="/" class="brand">🦤 Dodo Control Panel</a></header>'
        f"<main>{body}</main></body></html>"
    )
    print(f"{OUT}/{name}")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    guild, campaign, store = harness.build()
    bot = harness.FakeBot()

    _write("index.html", pages.campaigns_html(bot, guild, panel_access.SCOPE_FULL, 1))
    _write("campaign.html", pages.campaign_html(bot, guild, campaign, access.CAMPAIGN_GM))

    marla = minds.spawn_npc(
        store, name="Marla Venn", role="harbourmaster", culture="tidewater",
        world_time=0, rng=Random(7),
    )
    minds.remember(
        store, marla, "Ondry never paid what he owed at the north dock",
        world_time=0, rng=Random(1), valence=-0.6, details=["a green lantern"],
    )
    minds.advance(store, campaign, 900, Random(3))
    _write("inspector.html", pages._inspector_html(bot, guild, campaign, marla, store))

    print(f"\nguild id in the pages: {guild.id} (a real snowflake, on purpose)")
    print("now: py -m http.server 8899 --directory .preview — then click things")


if __name__ == "__main__":
    main()
