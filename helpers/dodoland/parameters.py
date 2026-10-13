"""
Per-guild tunables for DodoLand — **separate from ``helpers/parameters.py``.**

Same idea and the same typed-spec shape as the bot's parameter registry, but its
own list and its own collection, so town settings never appear among the general
cog settings. The DodoLand panel page renders these itself, the way tabletop
does (see ``helpers/dnd/parameters.py``, which this follows deliberately).

**The per-metric knobs are generated, not written.** Every entry in
:data:`helpers.dodoland.metrics.METRICS` produces a weight, a daily cap and (for
social acts) a per-partner cap. Nobody has to remember to expose a new metric's
numbers, because there is nowhere to forget: adding the metric adds the
parameters. That is the standing "everything is tweakable" rule made structural
instead of aspirational.

``ParamManager`` and ``coerce`` are reused from ``helpers/parameters.py`` rather
than reimplemented — that is machinery, not surface, and forking it would mean
fixing every coercion bug twice. What is separate is the spec list and the
collection.
"""

from __future__ import annotations

from config.database import db
from helpers.dodoland import metrics as metric_registry
from helpers.parameters import ParamManager

# DodoLand's own store, so a general settings reset never rewrites a server's
# town economy and vice versa.
dodoland_params_col = db["DodoLandParams"]

# Prefixes for the generated per-metric knobs. Kept as constants because the
# store and the panel both have to rebuild these keys.
WEIGHT_PREFIX = "dodoland_w_"
DAILY_CAP_PREFIX = "dodoland_cap_"
PARTNER_CAP_PREFIX = "dodoland_pcap_"
CHANNELS_PREFIX = "dodoland_ch_"


def weight_key(metric_key: str) -> str:
    return f"{WEIGHT_PREFIX}{metric_key}"


def daily_cap_key(metric_key: str) -> str:
    return f"{DAILY_CAP_PREFIX}{metric_key}"


def partner_cap_key(metric_key: str) -> str:
    return f"{PARTNER_CAP_PREFIX}{metric_key}"


def channels_key(metric_key: str) -> str:
    return f"{CHANNELS_PREFIX}{metric_key}"


def metric_setup(params, guild_id: int, metric_key: str) -> dict:
    """Every knob for one metric, resolved. What the panel renders a block from.

    One function so the panel, the scorer and any future surface can never
    disagree about what a metric's configuration is.
    """
    from helpers.dodoland import metrics as metric_registry

    metric = metric_registry.get(metric_key)
    setup = {
        "key": metric.key,
        "label": metric.label,
        "description": metric.description,
        "kind": metric.kind,
        "backfill": metric.backfill,
        "weight": int(params.get(guild_id, weight_key(metric.key))),
        "daily_cap": int(params.get(guild_id, daily_cap_key(metric.key))),
        "channels": list(params.get(guild_id, channels_key(metric.key)) or []),
    }
    setup["partner_cap"] = (
        int(params.get(guild_id, partner_cap_key(metric.key))) if metric.is_social else None
    )
    return setup


# --------------------------------------------------------------------------- #
#  Hand-written parameters: what is tracked, and over what window
# --------------------------------------------------------------------------- #
_BASE_PARAMETERS: list[dict] = [
    {"key": "dodoland_tracked_channels", "cog": "dodoland", "type": "list_channel", "default": [],
     "label": "Tracked channels",
     "description": "Channels DodoLand counts activity in. Leave empty to count every channel the bot can see, minus the ignored list."},
    {"key": "dodoland_ignored_channels", "cog": "dodoland", "type": "list_channel", "default": [],
     "label": "Ignored channels",
     "description": "Never counted, even when the tracked list is empty. Bot-spam and command channels belong here, or the town gets built out of /pumpkin presses."},
    {"key": "dodoland_min_message_chars", "cog": "dodoland", "type": "int", "default": 4,
     "label": "Minimum message length",
     "description": "Shorter messages are not counted at all. Stops 'k', '+' and 'f' from being currency."},
    {"key": "dodoland_max_mentions", "cog": "dodoland", "type": "int", "default": 5,
     "label": "Mentions counted per message",
     "description": "Distinct people one message can credit. A cost ceiling, not a game rule: each named person costs two writes, so a message listing thirty people should not spend thirty times a normal message's budget."},
    {"key": "dodoland_public_base_url", "cog": "dodoland", "type": "str", "default": "",
     "label": "Public address",
     "description": "Where this panel is reachable from outside, e.g. https://dodobot.nextstep.team. Used whenever a town's address has to be written somewhere outside the browser that is already on it. Blank makes such a link relative, which will not work in Discord."},
    # --- the player-facing surface ---------------------------------------- #
    # All three default off, and that is the point rather than caution: for its
    # whole life DodoLand has computed standings for people who could not see
    # them, so turning any of this on is a deliberate act by the server's owner
    # and never something a deploy does on their behalf.
    {"key": "dodoland_town_pages", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Members can open their own town",
     "description": "Turns on the player front end: a member signs in with Discord and gets their own town — its standing, every building and tier, what the next tier costs, and the name, description and picture they can give it. They see their own town and nobody else's. Off until a server is ready to be looked at."},
    {"key": "dodoland_world_page", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Members can browse the world",
     "description": "Lets a signed-in member open the map itself and look at everybody's towns, read-only. This is the whole point of the design — a socialite's reward is being seen — but it also shows every placed town's standing to the whole server, so it is its own decision. Needs the setting above."},
    {"key": "dodoland_autotile_cells", "cog": "dodoland", "type": "int", "default": 2,
     "label": "Smart ground: cells per tile",
     "description": "How many map cells one smart ground tile spans, across and down. Bigger makes its texture larger and its repeats rarer; a border still shows the tile's edge, a band of it as wide as one cell. 1 is a tile per cell."},
    {"key": "dodoland_autotile_blend", "cog": "dodoland", "type": "float", "default": 0.5,
     "label": "Smart ground: edge blending (cells)",
     "description": "How far, in map cells, a smart ground's edge and corner tiles fade into its seamless inside texture. 0 is a hard line where the edge tile stops; 1 blends across a whole cell. The edge's own fringe (grass blades, a shoreline) is always kept."},
    {"key": "dodoland_autotile_inset", "cog": "dodoland", "type": "float", "default": 0.03,
     "label": "Smart ground: trim tile edges",
     "description": "How much of each smart ground picture's own edge is left out when it is drawn, as a share of its width (0.03 is 3%). Drawn tiles carry a thin frame at their edges, which repeated across the ground is a grid; trimming it hides the grid. 0 draws the whole picture."},
    {"key": "dodoland_autotile_variation", "cog": "dodoland", "type": "float", "default": 0.25,
     "label": "Smart ground: share of varied centre tiles",
     "description": "Inside a smart ground (Smart ground in the tile library), how many cells show one of its variation tiles (flowers, cracks, ripples...) instead of its plain centre. 0 is plain everywhere, 1 is variations everywhere. Which cell gets which is fixed, so the ground does not shuffle."},
    {"key": "dodoland_gate_width", "cog": "dodoland", "type": "float", "default": 4.0,
     "label": "Gate width (cells)",
     "description": "How wide the opening a gate makes in a town's wall is, in map cells. A town hall is about ten cells across."},
    {"key": "dodoland_influence_pieces_block", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Placed things stop a town's area",
     "description": "On: placed things whose tile does not let influence spread (a pond, a mountain range) cut holes in towns' areas. Off: areas follow only the painted ground, and nothing placed on the map breaks them."},
    {"key": "dodoland_walls_option", "cog": "dodoland", "type": "bool", "default": True,
     "label": "Offer town walls",
     "description": "Shows the walls choice (none, palisade, stone) on a town's card. A wall runs round the town's land and stops at the shore; where walled towns overlap they share one outer wall. Off hides the choice; walls already chosen are kept."},
    {"key": "dodoland_member_pieces", "cog": "dodoland", "type": "int", "default": 150,
     "label": "Things a member may place",
     "description": "How many pieces one member may have on the map around their own town, counting its buildings. A brush stroke that would go over it places what fits. 0 stops members placing anything from the toolkit; their buildings still go up from the town card."},
    {"key": "dodoland_population_per_cell", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Population per tile of reach",
     "description": "A town's population, shown on its card, is the number of map tiles its area covers times this. It grows as the town's influence does."},
    {"key": "dodoland_picture_max_kb", "cog": "dodoland", "type": "int", "default": 1024,
     "label": "Largest town picture (KB)",
     "description": "The biggest picture or GIF a member may upload as their town's flag. Only PNG, JPEG, GIF and WebP are taken, checked from the file itself, not its name."},
    {"key": "dodoland_people_per_house", "cog": "dodoland", "type": "int", "default": 4,
     "label": "People reached per house",
     "description": "One ordinary house appears in somebody's town for every this many different people they have reached. This is the main thing that makes a well-connected person's town look like a town: at 4, reaching sixty people is fifteen houses and reaching three hundred is seventy-five, which is the difference between a village and a city. Set it to 0 to stop drawing houses at all."},
    {"key": "dodoland_max_houses", "cog": "dodoland", "type": "int", "default": 90,
     "label": "Most houses a town can have",
     "description": "A ceiling, so the single most connected person on a very large server does not end up with a thousand roofs in one settlement. Reach it and the town is as big as towns get here."},
    {"key": "dodoland_busy_town_reach", "cog": "dodoland", "type": "int", "default": 120,
     "label": "A town's streets are full at this much reach",
     "description": "How many different people somebody has to have reached before their streets are as busy as they get — how many inhabitants walk about, and how wide the ground is before the houses widen it further. Separate from the houses above because a crowd and a housing count are different things: past a point more people in the street is noise, while more houses still reads as a bigger town."},
    {"key": "dodoland_player_cache_seconds", "cog": "dodoland", "type": "int", "default": 60,
     "label": "Player page freshness (seconds)",
     "description": "A place in a ranking only exists relative to everybody else, so showing one member their own town means scoring the whole server — the same full read the panel pays once per load. This is how long that answer is reused for. 0 recomputes it on every visit, which a server of any size will feel."},
    {"key": "dodoland_self_settle", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Members can place their own town",
     "description": "Lets a member choose where on the map their own town stands, and move it later. They can never move anybody else's. Off means placement stays an admin act, which is what keeps a curated map curated."},
    {"key": "dodoland_building_art", "cog": "dodoland", "type": "str", "default": "generated",
     "choices": ["generated", "uploaded"],
     "label": "Building artwork",
     "description": "Which pictures the town buildings are drawn with. generated: the drawings DodoLand makes from each building's shape, tier and colour. uploaded: the painted pictures uploaded per building and tier (tools/dodoland_import_building_art.py); a building or tier with none uploaded keeps its generated drawing. Both are kept, so switching back and forth loses nothing."},
    {"key": "dodoland_uploaded_building_scale", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Uploaded buildings: size",
     "description": "How big the uploaded building pictures are drawn. 1 makes each building's top tier about as big on the map as its generated drawing's top tier, with the lower tiers in proportion to it, so a building still visibly grows. 1.5 is half as big again."},
    {"key": "dodoland_entrance_building", "cog": "dodoland", "type": "str", "default": "",
     "label": "Building shown growing on the entrance page",
     "description": "The key of the building a newcomer sees growing from its first tier to its top one, as the example of what activity does. Blank uses the town hall, or the building with the most tiers if there is none."},
    {"key": "dodoland_entrance_stages", "cog": "dodoland", "type": "int", "default": 4,
     "label": "Stages shown growing on the entrance page",
     "description": "How many of that building's tiers are shown side by side, always including its first and its top one. 2 shows only the start and the end."},
    {"key": "dodoland_map_min_zoom", "cog": "dodoland", "type": "float", "default": 0.4,
     "label": "Minimum zoom",
     "description": "How far out the map can be pulled. Below 1 the whole world fits in the frame with room around it."},
    {"key": "dodoland_map_max_zoom", "cog": "dodoland", "type": "float", "default": 8.0,
     "label": "Maximum zoom",
     "description": "How far in the map can be pushed. High values are only useful on a large, detailed base image."},
    {"key": "dodoland_map_name_zoom", "cog": "dodoland", "type": "float", "default": 1.8,
     "label": "Zoom names appear at",
     "description": "Town names stay hidden until the map is zoomed at least this far. Three hundred labels drawn at once is a grey mat rather than a map, so they arrive as you look closer."},
    {"key": "dodoland_town_width_pct", "cog": "dodoland", "type": "float", "default": 3.0,
     "label": "Base town width (% of the map)",
     "description": "How wide the *smallest* town is drawn, as a percentage of the map's width. A proportion rather than a pixel count, for the same reason positions are: re-uploading the map at another resolution then changes neither where a town sits nor how big it looks. Every town grows from this by its standing."},
    {"key": "dodoland_town_growth", "cog": "dodoland", "type": "float", "default": 2.5,
     "label": "Largest town is this many times the base",
     "description": "The strongest town on the server is drawn this much wider than the smallest, and everything in between is placed on a square-root curve. The root matters: growth linear in standing would make one prolific person's town swallow the map while everybody else stayed a speck. 1 makes every town the same size."},
    {"key": "dodoland_town_style", "cog": "dodoland", "type": "str", "default": "classic",
     "choices": ["classic", "hall"],
     "label": "How a town is drawn",
     "description": "classic draws a whole generated town at its plot, every building it has earned packed round a plate. hall draws only its town hall, with the town's flag on it, small at the plot: the town's reach is its area of influence, and its other buildings are the ones its owner places on the map."},
    {"key": "dodoland_town_hall", "cog": "dodoland", "type": "str", "default": "moot",
     "label": "Which building is the town hall",
     "description": "The key of the building drawn as a town's hall when towns are drawn as halls. The hall is shown at the tier the town has reached in that building, and at the first tier until it has any. A key this server does not have falls back to a plain hall."},
    {"key": "dodoland_hall_cells", "cog": "dodoland", "type": "float", "default": 2.5,
     "label": "Town hall size (cells)",
     "description": "How many map cells wide a town hall is drawn when towns are drawn as halls. About the size of a generated town's house is two or three."},
    {"key": "dodoland_tile_scale", "cog": "dodoland", "type": "float", "default": 5.0,
     "label": "Tile scale (art shrinks by)",
     "description": "Every tile is drawn this many times smaller than its own px-per-cell says: ground textures, placed objects and buildings alike, so they stay in proportion to each other while the map stays the same size. At 5 a pixel-art house from a 16px pack is about two map cells wide, the size of a house in a generated town. 1 draws art at its native size; larger makes everything finer."},
    {"key": "dodoland_influence_base", "cog": "dodoland", "type": "float", "default": 6.0,
     "label": "Influence of the weakest town (cells)",
     "description": "How far the least powerful placed town's area of influence reaches, in map cells of open ground. An area spreads from the town hall like water, paying what each kind of ground costs to grow onto, so it reaches less far through hills and not at all across sea or mountains. 0 means a town is only its own plot."},
    {"key": "dodoland_influence_top", "cog": "dodoland", "type": "float", "default": 40.0,
     "label": "Influence of the strongest town (cells)",
     "description": "How far the most powerful town reaches. Everything in between sits on a square-root curve of town power, the same curve town size uses, so one prolific person's area cannot swallow the map. Set it equal to the weakest town's for every area to be the same size. The work grows with the square of this: at a few hundred, recomputing every area takes several seconds (done behind the scenes when only standings changed), and one area stops at 400,000 cells."},
    {"key": "dodoland_influence_water_cost", "cog": "dodoland", "type": "float", "default": 2.0,
     "label": "Influence cost over water",
     "description": "How many cells of open ground one cell of water a town's area may spread over costs (only water whose tile lets influence spread, such as shallow water; deep sea never). 1 treats shallows like land; higher keeps an area hugging its coast."},
    {"key": "dodoland_breadth_bonus", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Influence: breadth bonus",
     "description": "Rewards taking part across the server rather than in one corner. For how far a town's area reaches (nothing else), its power is multiplied by 1 + this x its owner's breadth: the share of the lively rooms they can write in that they actually wrote in. At 1, someone in every one of them reaches as if twice as powerful; someone in half, 1.5x. The strongest town still reaches the strongest setting, so this decides who gets the large areas, not how large they get. 0 turns breadth off."},
    {"key": "dodoland_breadth_days", "cog": "dodoland", "type": "int", "default": 30,
     "label": "Influence: breadth window (days)",
     "description": "How far back breadth looks, both for which rooms are lively and for where the person wrote."},
    {"key": "dodoland_breadth_others", "cog": "dodoland", "type": "int", "default": 2,
     "label": "Influence: people for a lively room",
     "description": "A room counts as lively for somebody when at least this many other people wrote in it during the window. Rooms nobody uses are not held against anyone."},
    {"key": "dodoland_breadth_min_messages", "cog": "dodoland", "type": "int", "default": 1,
     "label": "Influence: messages to count as taking part",
     "description": "How many messages a person must have written in a lively room during the window for it to count as one of theirs. Higher stops a single hello in every channel from counting as breadth."},
    {"key": "dodoland_breadth_min_rooms", "cog": "dodoland", "type": "int", "default": 3,
     "label": "Influence: lively rooms before breadth counts",
     "description": "Somebody who can write in fewer lively rooms than this gets no breadth bonus, so being in the only two rooms one can see is not being everywhere."},
    {"key": "dodoland_breadth_curve", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Influence: breadth curve",
     "description": "The shape of the reward. 1 is straight: each room adds the same. Below 1 (e.g. 0.5) the first few rooms beyond one's usual add the most; above 1 (e.g. 2) the reward is saved for those in nearly all of them."},
    {"key": "dodoland_influence_clear_forest", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Influence clears forest",
     "description": "Whether a town's area can spread into forest, at twice the cost of open ground. Off, forests are a border the area grows round."},
    {"key": "dodoland_detail_above", "cog": "dodoland", "type": "int", "default": 70,
     "label": "Show close-up detail above (px)",
     "description": "When a town is drawn wider than this many screen pixels, its high-tier flourishes wake up: smoke, lit windows, hovering, orbiting motes, and the inhabitants start walking. At map scale that would be noise on three hundred towns at once. Keep it well under what a town can actually reach, which is the map's width times the town width times the maximum zoom — set too high, nothing ever happens at any zoom."},
    {"key": "dodoland_town_dot_below", "cog": "dodoland", "type": "int", "default": 26,
     "label": "Collapse to a dot below (px)",
     "description": "When a town would be drawn narrower than this many screen pixels, it is replaced by a dot. Buildings at that size are illegible smudges, and every real map does the same thing as you zoom out."},
    {"key": "dodoland_big_town", "cog": "dodoland", "type": "float", "default": 2.2,
     "label": "Always-labelled size",
     "description": "Towns at least this many times the base size keep their name at every zoom level, so the map has landmarks to orient on."},
    {"key": "dodoland_asset_size", "cog": "dodoland", "type": "int", "default": 28,
     "label": "Decor size (px)",
     "description": "How large a placed decoration is drawn at 100% zoom."},
    {"key": "dodoland_newcomer_days", "cog": "dodoland", "type": "int", "default": 3,
     "label": "Newcomer window (days)",
     "description": "How long after joining somebody still counts as new, so talking to them scores as welcoming. Short on purpose: it is a welcome, not a friendship."},
    {"key": "dodoland_voice_min_minutes", "cog": "dodoland", "type": "int", "default": 5,
     "label": "Minimum shared voice (min)",
     "description": "How long two people must be in a voice channel together before it counts as sharing one. Stops walking through a channel from making you everybody's friend."},
    {"key": "dodoland_count_bots", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Count bots",
     "description": "Whether bot accounts earn and grant standing. Off, in every sane configuration."},
    {"key": "dodoland_count_self_acts", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Count acts on yourself",
     "description": "Whether reacting to or replying to your own message scores. Off: it is the cheapest farm there is."},
    {"key": "dodoland_building_scale", "cog": "dodoland", "type": "float", "default": 0.5,
     "label": "Town building size",
     "description": "How large a town's placed buildings are drawn, as a fraction of its town hall's scale. The town hall and the zoo are always drawn at the hall's scale: they are the landmarks."},
    {"key": "dodoland_lod_tiles", "cog": "dodoland", "type": "float", "default": 2.5,
     "label": "Detail: Ground tiles from (px per cell)",
     "description": "The ground's own tile textures start fading in at this many screen pixels per map cell, and are fully in two pixels later; below it the ground is the shaded picture. Higher keeps the painted look further in."},
    {"key": "dodoland_lod_environment", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Environment features from (px per cell)",
     "description": "Placed ground features (ponds, rocks set into the ground) show once a map cell is at least this many screen pixels. 0 shows them at every zoom."},
    {"key": "dodoland_lod_objects", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Map objects from (px per cell)",
     "description": "Trees, bushes, map art and other placed objects show once a map cell is at least this many screen pixels. 0 shows them at every zoom."},
    {"key": "dodoland_lod_buildings", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Town buildings from (px per cell)",
     "description": "Placed town buildings show once a map cell is at least this many screen pixels. 0 shows them at every zoom. Town halls follow the town dot setting."},
    {"key": "dodoland_lod_houses", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Houses from (px per cell)",
     "description": "Towns' ordinary houses show once a map cell is at least this many screen pixels. 0 shows them at every zoom."},
    {"key": "dodoland_lod_life", "cog": "dodoland", "type": "float", "default": 1.2,
     "label": "Detail: People and animals from (px per cell)",
     "description": "Walking people and animals appear (and move) once a map cell is at least this many screen pixels."},
    {"key": "dodoland_lod_influence", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Influence areas from (px per cell)",
     "description": "Towns' areas of influence show once a map cell is at least this many screen pixels. 0 shows them at every zoom."},
    {"key": "dodoland_lod_walls", "cog": "dodoland", "type": "float", "default": 0.0,
     "label": "Detail: Town walls from (px per cell)",
     "description": "Town walls show once a map cell is at least this many screen pixels. 0 shows them at every zoom."},
    {"key": "dodoland_lod_forest", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Detail: Painted forests from (px per cell)",
     "description": "Painted forests draw their trees once a map cell is at least this many screen pixels. Further out than that a forest is not drawn tree by tree. 0 draws them at every zoom, which is slow on a wide view of a heavily forested map."},
    {"key": "dodoland_forest_detail_max", "cog": "dodoland", "type": "float", "default": 12.0,
     "label": "Painted forests: sharpest detail (px per cell)",
     "description": "The finest a painted forest is drawn at, in pixels per map cell. Zoomed in beyond it, the trees are enlarged rather than redrawn. Higher is crisper up close and uses more memory; 8 to 16 suits pixel art."},
    {"key": "dodoland_forest_spacing_full", "cog": "dodoland", "type": "float", "default": 0.95,
     "label": "Painted forests: tree spacing at 100% density (tree widths)",
     "description": "How far apart trees stand in a forest painted at 100% density, in widths of its own trees. 1 is crown touching crown; below 1 they overlap into a canopy, above it ground shows between them. The brush's density slider runs in a straight line from the 0% setting below to this one, and changing either redraws forests already painted."},
    {"key": "dodoland_forest_spacing_zero", "cog": "dodoland", "type": "float", "default": 1.95,
     "label": "Painted forests: tree spacing at 0% density (tree widths)",
     "description": "How far apart trees would stand at 0% density, in widths of its own trees: the sparse end of the density slider (the slider stops at 20%). With the defaults, 100% is 0.95 tree widths apart and 80% is 1.15."},
    {"key": "dodoland_forest_strip_cells", "cog": "dodoland", "type": "float", "default": 2.0,
     "label": "Painted forests: depth strip (cells)",
     "description": "A painted forest is drawn in horizontal strips this many map cells deep, each stacked by where its trees stand, so walkers and placed pieces pass behind the trees in front of them and in front of the trees behind. Thinner is more exact (a walker can be at most this far wrong) but makes more pictures to draw; 1 to 3 suits most maps."},
    {"key": "dodoland_forest_full_at", "cog": "dodoland", "type": "float", "default": 4.0,
     "label": "Painted forests: every tree from (px per cell)",
     "description": "From this many screen pixels per map cell, every tree of a painted forest is drawn. Further out, where a tree is a pixel or two and most hide under the rest, only a share is drawn in proportion (half as many at half this), which keeps a wide view of a big forest fast; zooming in adds the rest. 0 always draws every tree."},
    {"key": "dodoland_forest_chunks_max", "cog": "dodoland", "type": "int", "default": 200,
     "label": "Painted forests: chunks drawn at once",
     "description": "How many 64-cell squares of forest the map keeps drawn. Those furthest from the view are dropped first. Higher keeps more forest ready when panning; lower uses less memory."},
    {"key": "dodoland_life_on", "cog": "dodoland", "type": "bool", "default": True,
     "label": "People and animals on the map",
     "description": "Whether people walk inside each placed town's area of influence, and animals inside a placed zoo. Who walks where comes from the town's buildings: an inn brings drinkers and a dog, a keep brings horses, a zoo its animals."},
    {"key": "dodoland_life_max", "cog": "dodoland", "type": "int", "default": 12,
     "label": "Most people in a town",
     "description": "How many people walk in the most powerful town; the least powerful has two, and the rest sit on the square-root curve town reach uses."},
    {"key": "dodoland_zoo_building", "cog": "dodoland", "type": "str", "default": "menagerie",
     "label": "Which building is the zoo",
     "description": "The key of the building whose animals wander inside it once it is built on the map."},
    {"key": "dodoland_zoo_animals", "cog": "dodoland", "type": "int", "default": 2,
     "label": "Zoo animals per tier",
     "description": "How many animals a placed zoo holds for each tier it has reached."},
    {"key": "dodoland_roads_on", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Roads between towns",
     "description": "Whether the map lays roads between placed towns whose people talk to each other. The bot finds the way over the terrain; nobody draws them."},
    {"key": "dodoland_roads_per_town", "cog": "dodoland", "type": "int", "default": 3,
     "label": "Roads per town",
     "description": "How many of a town's strongest connections get a road. A road either end keeps is built, so a popular town can have more. Low keeps the map a network rather than a hairball."},
    {"key": "dodoland_roads_min", "cog": "dodoland", "type": "int", "default": 3,
     "label": "Interactions for a road",
     "description": "How many interactions (replies, mentions, time in voice together…) two towns' people need over the standing window before a road joins them."},
    {"key": "dodoland_roads_bridge", "cog": "dodoland", "type": "float", "default": 6.0,
     "label": "Cost of a bridge",
     "description": "How many steps of open ground one step over water a road may cross (shallows, rivers, lakes; never the open sea) is worth. Higher makes roads walk round to cross where a river is narrow."},
    {"key": "dodoland_roads_reuse", "cog": "dodoland", "type": "float", "default": 0.35,
     "label": "Road sharing",
     "description": "What ground already carrying a road costs a new one, as a fraction. Low and roads merge into trunk roads with branches; 1 and every pair gets its own way."},
    {"key": "dodoland_roads_step", "cog": "dodoland", "type": "int", "default": 2,
     "label": "Road search grid (cells)",
     "description": "Roads are found on a coarser copy of the map, this many cells to a step. 1 is exact and slow on a big map; 2 or 3 is a good balance."},
    {"key": "dodoland_roads_width", "cog": "dodoland", "type": "float", "default": 2.4,
     "label": "Road width (cells)",
     "description": "How wide a road is drawn, in map cells. A town hall is about ten."},
    {"key": "dodoland_overview_shading", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Zoomed-out shading",
     "description": "How strongly the map seen from far away is shaded: water darkening with depth, surf along every shore, a darker coastline, relief on mountains and a gentle variation across land. 0 is flat colour; 1 is the designed look; up to 2 is dramatic."},
    {"key": "dodoland_coast_shade_width", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Coast shading: width (cells)",
     "description": "Close up, the land darkens a little towards the water and the water brightens with surf along the shore, both following the smoothed shoreline. This is about how far each reaches, in map cells. Their strength follows the close-up shading setting; 0 turns both off."},
    {"key": "dodoland_tile_blend_width", "cog": "dodoland", "type": "float", "default": 0.9,
     "label": "Grounds blend: width (cells)",
     "description": "Close up, wherever two different kinds of land meet (grass against grass, grass against a road), one fades into the other instead of stopping at a hard square edge: its own texture is laid over its neighbour, thinning out over about this many map cells. 0 keeps hard edges. Water is left to the coast's own shading."},
    {"key": "dodoland_tile_blend_strength", "cog": "dodoland", "type": "float", "default": 0.85,
     "label": "Grounds blend: strength at the border",
     "description": "How much of the spilling ground covers its neighbour right at the border, from 0 to 0.99, fading to nothing at the blend's width. Near 1 there is no visible line at all; lower lets the original square edge show through."},
    {"key": "dodoland_ground_smoothing", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Ground: smooth borders",
     "description": "Close up, where two kinds of ground meet (grass and grass, grass and a road, land and water) the border is drawn as a smooth line instead of following the square cells: a stair of cells becomes a slope, a one-cell road painted diagonally a straight even line. 1 is fully smooth, lower keeps more of the corners, 0 draws the square cells as they are painted. Every kind of ground is smoothed, shores and coasts included. Only the picture changes; painting, roads and towns still work cell by cell."},
    {"key": "dodoland_ground_straighten", "cog": "dodoland", "type": "float", "default": 1.5,
     "label": "Ground: smoothing reach (cells)",
     "description": "How far along a border the smoothing looks either way, in map cells. Steps and spikes shorter than about this even out into slopes and curves, while the shape as a whole keeps its size and outline; corners round off by about this much. Higher is softer and more flowing, lower keeps more of the painted detail. Scaled by the smooth borders setting."},
    {"key": "dodoland_hit_alpha", "cog": "dodoland", "type": "int", "default": 96,
     "label": "Placed things: how solid a click must land",
     "description": "A building, tree or anything else placed takes a click, a drag or the hover outline only where its picture is at least this opaque (0 to 255); its empty corners, faint glow and soft shadow let the click through to what is beneath. Lower makes glows and shadows clickable too; 0 makes the whole picture's rectangle clickable, as it used to be."},
    {"key": "dodoland_ground_detail_max", "cog": "dodoland", "type": "float", "default": 16.0,
     "label": "Ground: sharpest detail (px per cell)",
     "description": "Close up, each 64-cell square of ground is drawn once into a picture and the map moves and scales finished pictures, which is what keeps panning smooth. This is the finest such a picture is drawn, in pixels per map cell; zoomed in further, it is enlarged rather than redrawn. Higher is crisper and uses more memory (16 is a 1024px picture per square)."},
    {"key": "dodoland_ground_chunks_max", "cog": "dodoland", "type": "int", "default": 300,
     "label": "Ground: squares kept drawn",
     "description": "How many of those ground pictures the map keeps ready; the furthest from the view are dropped first and redrawn when you come back. Higher makes returning to a place instant; lower uses less memory."},
    {"key": "dodoland_detail_shading", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Shading over close-up tiles",
     "description": "How strongly the zoomed-out map's shading — water darkening with depth, surf along shores, the coast's darker edge, relief on mountains — is laid over the real tiles once you zoom in. 1 matches the zoomed-out look; 0 shows the tiles bare."},
    {"key": "dodoland_overview_grain", "cog": "dodoland", "type": "float", "default": 1.0,
     "label": "Zoomed-out grain",
     "description": "A faint speckle over the map seen from far away, so it reads as a painted map rather than a diagram. 0 turns it off."},
    {"key": "dodoland_rows_cache_s", "cog": "dodoland", "type": "int", "default": 60,
     "label": "Map activity cache (seconds)",
     "description": "How long the map keeps the activity it was drawn from before reading it again. Reading it is the slowest part of opening the map; within this many seconds, every view of the map shares one read. 0 reads it fresh every time. The settings page always reads fresh."},
    {"key": "dodoland_rows_stale_s", "cog": "dodoland", "type": "int", "default": 1800,
     "label": "Map activity: serve while refreshing (seconds)",
     "description": "Once the map activity cache is older than its freshness, pages keep using it for up to this long while one fresh read happens in the background, so nobody waits on that read. Past this the next page waits for a fresh read. Set it equal to the cache time to always wait for fresh numbers."},
    {"key": "dodoland_window_days", "cog": "dodoland", "type": "int", "default": 365,
     "label": "Standing window (days)",
     "description": "How far back standing is totalled. This is a window, not a decay: days outside it are still stored and still count toward all-time records."},
    {"key": "dodoland_lit_days", "cog": "dodoland", "type": "int", "default": 30,
     "label": "Lit window (days)",
     "description": "A town with activity inside this window is drawn lit, otherwise dim. This is the only thing dormancy ever costs anyone: brightness, never progress."},
    {"key": "dodoland_keep_days", "cog": "dodoland", "type": "int", "default": 1095,
     "label": "Keep daily rows (days)",
     "description": "How long the per-day rows are retained. Three years by default. Lowering this permanently discards history."},
    {"key": "dodoland_partner_weight", "cog": "dodoland", "type": "int",
     "default": metric_registry.PARTNER_WEIGHT,
     "label": f"Points: {metric_registry.PARTNER_LABEL}",
     "description": metric_registry.PARTNER_DESCRIPTION},
    {"key": "dodoland_reach_counts", "cog": "dodoland", "type": "str", "default": "people",
     "choices": ["people", "days"],
     "label": "People reached counts",
     "description": "people: how many different people you are connected to over the standing window — each person once, however often you talk. days: each person once per day you interacted (the old count), which grows every time the same group is pinged again."},
    {"key": "dodoland_reach_mentions_alone", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Mentions alone reach people",
     "description": "Off: somebody you have only ever pinged — never replied to, never talked with in a thread or in voice — is not a person reached. On: a ping alone is enough. Pings still score for the buildings of the room they are in either way."},
    {"key": "dodoland_mass_ping_at", "cog": "dodoland", "type": "int", "default": 4,
     "label": "Mass ping at (people)",
     "description": "A message naming this many people or more is a mass ping: it scores for the room's buildings like any mention, but connects its author to nobody, so it adds no people reached. 0 treats every ping as personal."},
    {"key": "dodoland_partner_daily_cap", "cog": "dodoland", "type": "int",
     "default": metric_registry.PARTNER_DAILY_CAP,
     "label": "Daily cap: new people reached",
     "description": "How many different people can score in one day. A ceiling on a genuinely good day, not a limit on how many people you may talk to."},
]


# --------------------------------------------------------------------------- #
#  Generated parameters: three per metric
# --------------------------------------------------------------------------- #
def _metric_parameters() -> list[dict]:
    """A weight, a daily cap and (for social acts) a partner cap per metric."""
    out: list[dict] = []
    for metric in metric_registry.METRICS:
        out.append({
            "key": weight_key(metric.key), "cog": "dodoland", "type": "int",
            "default": metric.weight,
            "label": f"Points: {metric.label}",
            "description": f"{metric.description} Set to 0 to stop this counting toward standing without losing the record of it.",
        })
        out.append({
            "key": daily_cap_key(metric.key), "cog": "dodoland", "type": "int",
            "default": metric.daily_cap,
            "label": f"Daily cap: {metric.label}",
            "description": "How many of these can score for one person in a day. 0 removes the cap entirely.",
        })
        out.append({
            "key": channels_key(metric.key), "cog": "dodoland", "type": "list_channel",
            "default": [],
            "label": f"Channels: {metric.label}",
            "description": (
                "Channels this metric counts in. Empty means wherever DodoLand tracks at all, "
                "which is the setting most metrics want; narrow it when a metric only makes "
                "sense somewhere specific, such as pictures in the fashion and housing rooms."
            ),
        })
        if metric.is_social:
            out.append({
                "key": partner_cap_key(metric.key), "cog": "dodoland", "type": "int",
                "default": metric.partner_cap,
                "label": f"Per-person cap: {metric.label}",
                "description": (
                    "How many of these can score from one other person in a day. This is the "
                    "anti-farm number: past it the act still happens and simply stops scoring, "
                    "so two friends cannot build each other a city. 0 removes the cap."
                ),
            })
    return out


def _text_parameters() -> list[dict]:
    """Every text on a member's town page (helpers/dodoland/page_texts.py)."""
    from helpers.dodoland import page_texts

    return page_texts.specs()


DODOLAND_PARAMETERS: list[dict] = _BASE_PARAMETERS + _metric_parameters() + _text_parameters()


def manager() -> ParamManager:
    """A ``ParamManager`` over DodoLand's own specs and collection."""
    return ParamManager(dodoland_params_col, DODOLAND_PARAMETERS)
