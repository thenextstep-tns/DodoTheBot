"""
DodoLand panel routes.

Mounted from ``web/routes.py:create_app`` with a function-level import, so this
package can import the shared chrome from ``routes`` without closing an import
cycle at module load.

**Every route is gated, and there are exactly three kinds of gate.**

``configure``/``full`` are the panel's scopes: an administrator acting on a whole
server, which is why those handlers take a user id — they are legitimately
working on other people's towns.

``owner`` is the bot owner's gate, for the tile library, which is shared by
every server and so belongs to none of them.

``player`` is ``web/dodoland/player.py``'s own gate: signed in with Discord,
still a member of that guild right now, and the server has switched this surface
on. **A player handler never reads a user id from the request** — not from the
path, the query or the body — so there is nothing to tamper with. That property
is what a public map link and a capability URL could not offer, which is why
both were built here and removed again.
"""

from __future__ import annotations

from aiohttp import web

# **The admin side is the bot owner's alone for now.** While the map is being
# built, one wrong click by a server admin could wipe a world (terrain, decor,
# every town's place), so every ``configure``/``full`` route below takes the
# bot owner's scope instead: a server's owner and admins get the same 404 as
# somebody with no access at all, and the DodoLand menu item is hidden from
# them (web/routes.py). Members' own pages (``player``) are unaffected: they
# only ever touch the member's own town. Set False to give the panel scopes back.
OWNER_ONLY = True


def dodoland_routes() -> list:
    """Route table for the DodoLand pages."""
    from helpers import panel_access
    from web.dodoland.api import (
        api_dodoland_backfill, api_dodoland_buildings,
        api_dodoland_map, api_dodoland_param, api_dodoland_settle,
        api_dodoland_shapes, api_dodoland_suggest, api_dodoland_town,
    )
    from web.dodoland.assets_route import (
        asset_image, town_art, town_picture,
    )
    from web.dodoland import player
    from web.dodoland.decor_api import (
        api_town_decor, api_town_toolkit, api_world_decor,
        player_asset_image,
    )
    from web.dodoland.forest_api import api_forest_paint, forest_chunks
    from web.dodoland.terrain_api import (
        api_terrain_paint, api_terrain_undo, terrain_cells, terrain_overview,
        terrain_picture, terrain_rle, terrain_shade, terrain_world,
    )
    from web.dodoland.influence_api import influence_layer
    from web.dodoland.roads_api import roads_layer
    from web.dodoland import player_map
    from web.dodoland.mappage import map_page
    from web.dodoland.lights_ui import api_tile_lights
    from web.dodoland.horse_api import api_horse
    from web.dodoland.look_api import api_my_pets, api_town_pets
    from web.dodoland.tiles_ui import (
        api_guild_tiles, api_tiles, guild_tile_art, tile_art, tiles_page,
    )
    from web.dodoland.pages import dodoland_page
    from web.routes import require_owner, require_scope

    # Reading the page means reading everybody's standing, so it takes the same
    # scope the settings page does rather than the softer stats scope.
    configure = require_scope(panel_access.SCOPE_OWNER if OWNER_ONLY else panel_access.SCOPE_CONFIG)
    full = require_scope(panel_access.SCOPE_OWNER if OWNER_ONLY else panel_access.SCOPE_FULL)
    # The tile library belongs to no one server, so it is not under
    # /guild/{gid} and takes the bot owner's gate rather than a panel scope.
    owner = require_owner
    return [
        web.get("/dodoland/tiles", owner(tiles_page)),
        web.get("/api/dodoland/lights/{tile_id}", owner(api_tile_lights)),
        web.get("/dodoland/tiles/art/{vid}", owner(tile_art)),
        web.post("/api/dodoland/tiles", owner(api_tiles)),
        web.get("/guild/{gid}/dodoland", configure(dodoland_page)),
        # The map deserves the whole window, so it is its own page.
        web.get("/guild/{gid}/dodoland/map", configure(map_page)),
        web.get("/guild/{gid}/dodoland/asset/{aid}", configure(asset_image)),
        web.get("/guild/{gid}/dodoland/town/{uid}/picture", configure(town_picture)),
        # Drawn on demand, so the map ships no artwork it may never show.
        web.get("/guild/{gid}/dodoland/town/{uid}/art", configure(town_art)),
        web.post("/api/guild/{gid}/dodoland/param", full(api_dodoland_param)),
        web.post("/api/guild/{gid}/dodoland/buildings", full(api_dodoland_buildings)),
        web.post("/api/guild/{gid}/dodoland/map", full(api_dodoland_map)),
        # The tile library, as one server sees it: the global tiles and its
        # own, which its admins manage. It replaced the asset library.
        web.post("/api/guild/{gid}/dodoland/tiles", full(api_guild_tiles)),
        web.get("/guild/{gid}/dodoland/tiles/art/{vid}", configure(guild_tile_art)),
        web.post("/api/guild/{gid}/dodoland/suggest", full(api_dodoland_suggest)),
        web.post("/api/guild/{gid}/dodoland/shapes", full(api_dodoland_shapes)),
        # The world itself. Read by anybody who can read the map; painted only
        # with the scope that changes a server's configuration, because terrain
        # is configuration — it decides where everybody's town may ever grow.
        web.get("/guild/{gid}/dodoland/terrain/world", configure(terrain_world)),
        web.get("/guild/{gid}/dodoland/terrain/overview", configure(terrain_overview)),
        web.get("/guild/{gid}/dodoland/terrain/picture", configure(terrain_picture)),
        web.get("/guild/{gid}/dodoland/terrain/shade", configure(terrain_shade)),
        web.get("/guild/{gid}/dodoland/terrain/rle", configure(terrain_rle)),
        web.get("/guild/{gid}/dodoland/forest/chunks", configure(forest_chunks)),
        web.get("/guild/{gid}/dodoland/terrain/cells", configure(terrain_cells)),
        # Every placed town's area of influence, for the map's Influence layer.
        web.get("/guild/{gid}/dodoland/influence", configure(influence_layer)),
        # The roads the bot lays between connected towns (layer 2).
        web.get("/guild/{gid}/dodoland/roads", configure(roads_layer)),
        web.post("/api/guild/{gid}/dodoland/terrain/paint", full(api_terrain_paint)),
        web.post("/api/guild/{gid}/dodoland/forest/paint", full(api_forest_paint)),
        web.post("/api/guild/{gid}/dodoland/terrain/undo", full(api_terrain_undo)),
        # Moving somebody's town is configuration while there is no player-facing
        # way for them to move it themselves.
        web.post("/api/guild/{gid}/dodoland/settle", full(api_dodoland_settle)),
        # Names, descriptions and pictures. Authored, never scored.
        web.post("/api/guild/{gid}/dodoland/town", full(api_dodoland_town)),
        # Rewrites historical rows, so it takes the highest scope on the page.
        web.post("/api/guild/{gid}/dodoland/backfill", full(api_dodoland_backfill)),
        # --- the player front end ----------------------------------------- #
        # Its gate lives in player.py and is applied by the handlers themselves,
        # because it has to answer three questions the panel's scopes do not:
        # is this person still in the guild, has this server switched the
        # surface on, and — for settling — is it the kind that lets a member
        # place their own town. None of these take a user id.
        web.get("/guild/{gid}/dodoland/me", player.my_town_page),
        web.get("/guild/{gid}/dodoland/me/picture", player.my_picture),
        web.post("/api/guild/{gid}/dodoland/me/town", player.api_my_town),
        web.post("/api/guild/{gid}/dodoland/me/settle", player.api_my_settle),
        # The toolkit. An admin dresses the map; a member dresses their own
        # town and only their own — the handler never reads a user id from the
        # request, and the tier locks are enforced there rather than in the UI.
        web.post("/api/guild/{gid}/dodoland/decor", full(api_world_decor)),
        # The runaway horse: everybody's map sees and chases the same one.
        web.get("/api/guild/{gid}/dodoland/horse", full(api_horse)),
        web.post("/api/guild/{gid}/dodoland/horse", full(api_horse)),
        web.get("/api/guild/{gid}/dodoland/me/horse", player.require_town(world=True)(api_horse)),
        # A town owner's cats and dogs, to choose the ones following them.
        web.get("/api/guild/{gid}/dodoland/pets", full(api_town_pets)),
        web.get("/api/guild/{gid}/dodoland/me/pets", player.require_town(api_my_pets)),
        web.post("/api/guild/{gid}/dodoland/me/horse", player.require_town(world=True)(api_horse)),
        web.get("/api/guild/{gid}/dodoland/me/toolkit",
                player.require_town(api_town_toolkit)),
        web.post("/api/guild/{gid}/dodoland/me/decor",
                 player.require_town(api_town_decor)),
        web.get("/guild/{gid}/dodoland/me/asset/{aid}",
                player.require_town(player_asset_image)),
        web.get("/guild/{gid}/dodoland/me/asset/{aid}/{vid}",
                player.require_town(player_asset_image)),
        # --- the map, for a member ----------------------------------------- #
        # The same page and the same readers as the admin map, behind the
        # player gate with the world page on. A member paints inside their own
        # town's area with player tiles, undoes only their own strokes, and
        # builds only their own town's buildings; see web/dodoland/player_map.py.
        web.get("/guild/{gid}/dodoland/me/map", player.require_town(world=True)(player_map.page)),
        web.get("/guild/{gid}/dodoland/me/w/terrain/world", player.require_town(world=True)(player_map.reader(terrain_world))),
        web.get("/guild/{gid}/dodoland/me/w/terrain/picture", player.require_town(world=True)(player_map.reader(terrain_picture))),
        web.get("/guild/{gid}/dodoland/me/w/terrain/shade", player.require_town(world=True)(player_map.reader(terrain_shade))),
        web.get("/guild/{gid}/dodoland/me/w/terrain/rle", player.require_town(world=True)(player_map.reader(terrain_rle))),
        web.get("/guild/{gid}/dodoland/me/w/forest/chunks", player.require_town(world=True)(player_map.reader(forest_chunks))),
        web.get("/guild/{gid}/dodoland/me/w/terrain/cells", player.require_town(world=True)(player_map.reader(terrain_cells))),
        web.get("/guild/{gid}/dodoland/me/w/influence", player.require_town(world=True)(player_map.reader(influence_layer))),
        web.get("/guild/{gid}/dodoland/me/w/roads", player.require_town(world=True)(player_map.reader(roads_layer))),
        web.get("/guild/{gid}/dodoland/me/w/tiles/art/{vid}", player.require_town(world=True)(player_map.reader(guild_tile_art))),
        web.get("/guild/{gid}/dodoland/me/w/asset/{aid}", player.require_town(world=True)(player_map.reader(asset_image))),
        web.get("/guild/{gid}/dodoland/me/w/town/{uid}/art", player.require_town(world=True)(player_map.reader(town_art))),
        web.get("/guild/{gid}/dodoland/me/w/town/{uid}/picture", player.require_town(world=True)(player_map.reader(town_picture))),
        web.post("/api/guild/{gid}/dodoland/me/terrain/paint", player.require_town(world=True)(player_map.paint)),
        web.post("/api/guild/{gid}/dodoland/me/terrain/undo", player.require_town(world=True)(player_map.undo)),
        web.post("/api/guild/{gid}/dodoland/me/build", player.require_town(world=True)(player_map.build)),
        # Not under /guild/{gid}: it is the page that tells somebody which
        # guilds they have a town in, so it cannot already know one.
        web.get("/towns", player.towns_home),
    ]
