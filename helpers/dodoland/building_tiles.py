"""
A server's town buildings, as tiles players can place (layer 4).

Every building a server defines — the tavern, the town hall, the zoo — is drawn
by ``townart`` at each of its tiers. This turns each (building, tier) into one
of the server's own tiles in the global **Town buildings** category:

* layer ``buildings``, placed, for players and admins;
* **required**: that building at that tier, so the third-tier library is
  something a player unlocks by building a third-tier library;
* it blocks roads, and it resizes a little either way.

They are derived, not authored: :func:`sync` rebuilds them from the building
definitions and is called whenever those are saved, so renaming a building,
changing its shape or emblem, or adding a tier never leaves stale art behind.
A tile's ``source`` is ``building:<guild>:<key>:<tier>``, which is how a
re-sync finds the tile it made last time. Removing a building removes its tiles.
"""

from __future__ import annotations

from typing import Iterable

from helpers.dodoland import tiles as tile_rules
from helpers.dodoland import townart

CATEGORY = "Town buildings"
PACK = "DodoLand town art"
# The art is drawn in townart's 120 x 78 box; at 12 units a cell a building
# takes about ten map cells, the scale a town was always drawn at.
CELL_PX = 12


def svg_for(building: dict, tier: int, css: str = "") -> bytes:
    """One building at one tier as a standalone SVG image.

    ``css`` is the town artwork's stylesheet (``web.dodoland.theme.TOWN_ART_CSS``),
    passed in rather than imported so this module stays below the web layer. The
    art's glows and moving parts are scoped to a town seen close up, so the
    building is wrapped as one; animations inside an SVG image still play.
    """
    colour = building.get("colour") or townart.colour_for(building["key"])
    body = townart.one_svg(building.get("shape") or "", tier, colour, building.get("symbol") or "")
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {townart.WIDTH:g} '
            f'{townart.HEIGHT:g}" width="{townart.WIDTH:g}" height="{townart.HEIGHT:g}">')
    style = f"<style>{css}</style>" if css else ""
    return (head + style + f'<g class="dltown close">{body}</g></svg>').encode("utf-8")


def _source(guild_id: int, key: str, tier: int) -> str:
    return f"building:{int(guild_id)}:{key}:{tier}"


def sync(library: tile_rules.TileLibrary, guild_id: int, buildings: Iterable[dict],
         css: str = "") -> dict:
    """Make the server's building tiles match its buildings. Returns counts."""
    buildings = list(buildings)
    cat = next((c for c in library.categories() if c["name"] == CATEGORY), None)
    cat = cat or library.add_category(CATEGORY)
    wanted = set()
    added = updated = 0
    for building in buildings:
        tiers = building.get("tiers") or []
        for tier in range(1, len(tiers) + 1):
            source = _source(guild_id, building["key"], tier)
            wanted.add(source)
            title = str(tiers[tier - 1].get("title") or f"Tier {tier}")
            name = f"{building.get('name') or building['key']} · {title}"[:tile_rules.MAX_NAME]
            art = svg_for(building, tier, css)
            requires = {"building": building["key"], "tier": tier}
            tile = library.by_source(source)
            if tile is None:
                library.add_tile(name=name, cat_id=cat["cat_id"], data=art,
                                 content_type="image/svg+xml", guild_id=guild_id,
                                 layer="buildings", access=["admin", "player"], requires=requires,
                                 passable=False, resizable=True, scale_min=0.5, scale_max=2.0,
                                 # A road goes round a house; the town it
                                 # belongs to does not stop at its own door.
                                 spreads=True,
                                 cell_px=CELL_PX, pack=PACK, source=source)
                added += 1
                continue
            changes = {}
            if tile["name"] != name:
                changes["name"] = name
            if tile["requires"] != requires:
                changes["requires"] = requires
            if changes:
                library.update_tile(tile["tile_id"], **changes)
            old = library.art(tile["variants"][0]) if tile["variants"] else None
            if old is None or bytes(old.get("data") or b"") != art:
                vid = library.add_variant(tile["tile_id"], data=art, content_type="image/svg+xml")
                for stale in [v for v in library.get(tile["tile_id"])["variants"] if v != vid]:
                    library.remove_variant(tile["tile_id"], stale)
                changes["art"] = True
            updated += bool(changes)
    removed = 0
    prefix = f"building:{int(guild_id)}:"
    for tile in library.tiles(guild_id):
        if tile["source"].startswith(prefix) and tile["source"] not in wanted:
            library.remove_tile(tile["tile_id"])
            removed += 1
    return {"added": added, "updated": updated, "removed": removed, "total": len(wanted)}
