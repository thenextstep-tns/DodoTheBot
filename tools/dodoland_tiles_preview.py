"""
Serve the real tile library page locally, against an in-memory library.

The page is JavaScript posting to an API, and the only real copy sits behind
the bot owner's Discord login. This runs the same three handlers from
``web/dodoland/tiles_ui.py`` — nothing reimplemented — with no gate and a
library that forgets everything when the process stops.

    py tools/dodoland_tiles_preview.py [port]     # then open /dodoland/tiles

Seeded with two categories and a few generated tiles so there is something to
reorder on first load.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))

from aiohttp import web  # noqa: E402
from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland.tiles import TileLibrary  # noqa: E402
from web.dodoland.tiles_ui import api_tiles, tile_art, tiles_page  # noqa: E402


def _swatch(fill: str, dot: str) -> bytes:
    """A 16x16 SVG tile: flat ground with a speck, enough to tell tiles apart."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
            f'shape-rendering="crispEdges"><rect width="16" height="16" fill="{fill}"/>'
            f'<rect x="5" y="6" width="3" height="2" fill="{dot}"/>'
            f'<rect x="11" y="11" width="2" height="2" fill="{dot}"/></svg>').encode()


def seeded() -> TileLibrary:
    library = TileLibrary(FakeCollection(), FakeCollection(), FakeCollection())
    water = library.add_category("Water")
    ground = library.add_category("Ground")
    for name, cat, fill, dot in (("Deep sea", water, "#1d3b63", "#2a5b8f"),
                                 ("Shallows", water, "#3f87b5", "#a8dced"),
                                 ("Grass", ground, "#46934f", "#7ab85c"),
                                 ("Sand", ground, "#e3c88f", "#9c7246")):
        row = library.add_tile(name=name, cat_id=cat["cat_id"],
                               data=_swatch(fill, dot), content_type="image/svg+xml")
        if name == "Grass":
            library.add_variant(row["tile_id"], data=_swatch(fill, "#2e6b3f"),
                                content_type="image/svg+xml")
    return library


class _Bot:
    def __init__(self) -> None:
        self.dodoland_tiles = seeded()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8778
    app = web.Application(client_max_size=16 * 1024 * 1024)
    app["bot"] = _Bot()
    static = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"

    async def home(_request):
        raise web.HTTPFound("/dodoland/tiles")

    app.add_routes([
        web.get("/", home),
        web.get("/dodoland/tiles", tiles_page),
        web.get("/dodoland/tiles/art/{vid}", tile_art),
        web.post("/api/dodoland/tiles", api_tiles),
        web.static("/static", str(static)),
    ])
    print(f"tile library preview on http://localhost:{port}/dodoland/tiles")
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
