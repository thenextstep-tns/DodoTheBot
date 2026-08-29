"""
The map view: the map, and almost nothing else.

A map squeezed into a panel section between a settings form and a table is not a
map, it is a thumbnail. This page gives it the screen: the world fills the
window, and everything else is a drawer over the top of it.

Three decisions this page is built around.

**Only placed towns appear.** Nothing is auto-scattered here. A town exists on
the map because somebody put it there, so the map starts empty and fills up
deliberately. The graph-driven suggestion still exists in
``helpers/dodoland/mapview.py`` and is not used by this page; a map that placed
three hundred towns for you is a map you cannot curate, and curating it is the
point of building one by hand.

**A town is drawn from what stands in it.** Not a dot: the buildings that person
has actually reached a tier in, each drawn as its own kind — an inn, a hall, a
keep, a chapel — and each grown by its tier. A settlement with a library, a
bakery and a forge looks like a different place from one with barracks and a war
room, which is the whole reason buildings were worth having.

**Clicking a town opens it.** Standing, place, flourish, every building and its
tier, and the coordinates. A map you cannot interrogate is wallpaper.

**Detail arrives with the zoom.** Only towns inside the visible rectangle get a
DOM node at all, and their artwork is fetched the first time they are close
enough to be worth drawing. Shipping three hundred pre-rendered settlements and
hiding most of them with CSS costs the whole payload and the whole parse for the
handful anybody can actually see. Because of that this can afford as much
detail per building as it likes: what is on screen at high zoom is a few towns,
not the server.

Nothing is loaded from anywhere else. The towns are shapes this repository draws
and the few controls are ordinary characters, so the page renders identically on
a machine with no network at all. An icon font was tried first and dropped: it
could not express a tier, and pulling in a CDN for four buttons was not a trade
worth making.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json

from aiohttp import web

from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import standing
from helpers.dodoland import townart
from helpers.dodoland import towns as town_rules
from helpers.dodoland import store as store_module
from web.dodoland import theme


def _e(value) -> str:
    return html.escape(str(value))


def _name_of(guild, bot, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    if member is not None:
        return member.display_name
    user = bot.get_user(int(user_id))
    return user.name if user is not None else f"User {user_id}"


def _grown(power: int, biggest: int) -> float:
    """How far up the size curve a town sits, 0 to 1."""
    if power <= 0 or biggest <= 0:
        return 0.0
    return min(1.0, (power / biggest) ** 0.5)


def _rooms_of(guild, building: dict) -> list[str]:
    """The channels that build one building, named the way Discord names them."""
    out = []
    for channel_id in (building.get("channels") or {}):
        channel = guild.get_channel(int(channel_id))
        if channel is None and hasattr(guild, "get_thread"):
            channel = guild.get_thread(int(channel_id))
        out.append(f"#{channel.name}" if channel is not None
                   else f"#{channel_id}")
    return sorted(out)


def _collect(bot, guild) -> dict:
    """Everything the page needs, in one pass. Blocking; call in an executor."""
    buildings = bot.dodoland_buildings.buildings(guild.id)
    rooms = {b["key"]: _rooms_of(guild, b) for b in buildings}
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)
    lit_since = store_module.days_back(
        int(bot.dodoland_params.get(guild.id, "dodoland_lit_days")))

    rows = bot.dodoland.rows(guild.id, since=since)
    pairs = bot.dodoland.pair_rows(guild.id, since=since)
    result = standing.guild_standings(bot.dodoland, bot.dodoland_params, guild.id,
                                      buildings, since=since, rows=rows,
                                      pair_rows=pairs)
    glow = flourish_rules.flourish_map(bot, guild.id)
    plots = bot.dodoland_buildings.plots(guild.id)
    lit = {int(row.get("user_id", 0)) for row in rows
           if str(row.get("day") or "") >= lit_since}

    details = bot.dodoland_towns.all(guild.id)
    # The toolkit's output: what an admin has put on the map, and what each
    # person has put around their own town. One read each rather than one per
    # settlement.
    world_decor = bot.dodoland_decor.world(guild.id)
    town_decor = bot.dodoland_decor.towns(guild.id)
    base_pct = float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct"))
    growth = max(1.0, float(bot.dodoland_params.get(guild.id, "dodoland_town_growth")))
    biggest = max((p["power"] for p in result["order"]), default=0)
    people = []
    for person in result["order"]:
        uid = person["user_id"]
        mine = details.get(uid, {})
        built = []
        for key, score in person["buildings"].items():
            if score.get("tier") is None:
                continue
            built.append({
                "key": key,
                # What its owner calls it, falling back to what the server calls
                # it. Naming is free and changes nothing; the tier behind it is
                # neither.
                "name": town_rules.building_label(mine, key, score["name"]),
                "given": score["name"],
                "tier": int(score["tier"]) + 1,
                "title": score["tier_title"],
                "points": score["points"],
                # What actually builds it. The map makes somebody ask why a
                # building is there, and this is the answer.
                "rooms": rooms.get(key, []),
            })
        built.sort(key=lambda b: -b["tier"])
        shine = glow.get(uid) or flourish_rules.BLANK
        owner = _name_of(guild, bot, uid)
        people.append({
            "id": str(uid),
            "owner": owner,
            "name": town_rules.display_name(mine, owner),
            "blurb": str(mine.get("blurb") or ""),
            "has_image": bool(mine.get("image")),
            "power": person["power"],
            "place": person["place"],
            "reached": person["reached"],
            "built": built,
            "flourish": int(shine.get("level", 0)),
            "flourish_label": shine.get("label") or "",
            "rank": shine.get("rank_name") or "",
            "lit": uid in lit,
            "plot": plots.get(uid),
            # A town grows from the base width by its standing, on a square-root
            # curve. Linear growth would let one prolific person's settlement
            # swallow the map while everybody else stayed a speck, which is the
            # same reason the old marker sizing used a root.
            "w": round(base_pct * (1 + (growth - 1) * _grown(person["power"], biggest)), 4),
            # Placed relative to the town's own box, so it travels with the
            # town when the town is moved or grows.
            "decor": [{"id": d["piece_id"], "a": d["asset_id"],
                       "x": float(d.get("x", 50)), "y": float(d.get("y", 50)),
                       "s": float(d.get("scale", 1.0)),
                       "f": bool(d.get("flip"))}
                      for d in town_decor.get(uid, ())],
        })
    return {"people": people, "buildings": buildings,
            "total": len(result["people"]),
            "world": [{"id": d["piece_id"], "a": d["asset_id"],
                       "x": float(d.get("x", 50)), "y": float(d.get("y", 50)),
                       "s": float(d.get("scale", 1.0)),
                       "f": bool(d.get("flip"))} for d in world_decor],
            "assets": [{"id": a["asset_id"], "name": a.get("name") or "",
                        "building": a.get("building") or "",
                        "tier": int(a.get("min_tier") or 0)}
                       for a in bot.dodoland_assets.list(guild.id)]}


async def map_page(request: web.Request):
    """The map, given the whole window."""
    from web.routes import _page  # noqa: F401  (kept for the nav's sake)

    bot, guild = request.app["bot"], request["guild"]
    viewer = str(request.get("uid") or "")
    data = await asyncio.get_running_loop().run_in_executor(None, _collect, bot, guild)

    image = bot.dodoland_buildings.map_image(guild.id)
    if image:
        raw = image.get("data")
        blob = bytes(raw) if raw is not None else b""
        src = (f"data:{_e(image.get('content_type'))};base64,"
               f"{base64.b64encode(blob).decode('ascii')}")
        world = f'<img id="dlbase" alt="The map of {_e(guild.name)}" src="{src}">'
    else:
        world = ('<div class="dlnomap">No map uploaded yet. Upload one on the '
                 'DodoLand page first.</div>')

    placed = [p for p in data["people"] if p["plot"]]
    unplaced = [p for p in data["people"] if not p["plot"]]
    # How large a piece of decor is drawn at 100% zoom, before its own scale.
    decor_size = int(bot.dodoland_params.get(guild.id, "dodoland_asset_size"))
    sizes = {
        # A proportion of the map's width, not a pixel count. Positions are
        # percentages for the same reason: re-uploading the map at another
        # resolution must change neither where a town sits nor how big it looks.
        "town_pct": float(bot.dodoland_params.get(guild.id, "dodoland_town_width_pct")),
        "dot_below": int(bot.dodoland_params.get(guild.id, "dodoland_town_dot_below")),
        "detail_above": int(bot.dodoland_params.get(guild.id, "dodoland_detail_above")),
        "ratio": townart.HEIGHT / townart.WIDTH,
        "min_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_min_zoom")),
        "max_zoom": float(bot.dodoland_params.get(guild.id, "dodoland_map_max_zoom")),
    }

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Map · {_e(guild.name)}</title>
<style>{_CSS}</style>
</head><body>
<div class="dlbar">
  <a class="dlback" href="/guild/{guild.id}/dodoland">&larr; DodoLand</a>
  <b>{_e(guild.name)}</b>
  <span class="dlcount"><b id="dlplaced">{len(placed)}</b> on the map ·
    <b id="dlwaiting">{len(unplaced)}</b> waiting ·
    {len(data['people'])} with standing</span>
  <span class="dlspacer"></span>
  <button id="dlkit" class="dlghost">🧰 Toolkit</button>
  <button id="dltoggle" class="dlghost">Towns list</button>
</div>

<div class="dlframe" id="dlframe">
  <div class="dlworld" id="dlworld">{world}</div>
  <div class="dlzoom">
    <button type="button" id="dlin" title="Zoom in">+</button>
    <button type="button" id="dlout" title="Zoom out">&minus;</button>
    <button type="button" id="dlfit" title="Fit the whole map">&#9634;</button>
    <button type="button" id="dlnames" title="Show every name">A</button>
  </div>
  <div class="dlhint" id="dlhint">Drag to move, scroll to zoom</div>
</div>

<aside class="dldrawer" id="dldrawer">
  <div class="dldhead">
    <b>Towns</b>
    <button class="dlghost" id="dlclose">&times;</button>
  </div>
  <input class="dlsearch" id="dlsearch" placeholder="Search a name...">
  <div class="dllist" id="dllist"></div>
</aside>

<aside class="dldrawer dlkitdrawer" id="dlkitdrawer">
  <div class="dldhead">
    <b>Toolkit</b>
    <button class="dlghost" id="dlkitclose">&times;</button>
  </div>
  <p class="dlkithint">Pick something, then click the map to put it down.
  Click a placed piece to pick it up again.</p>
  <div class="dlkitgrid" id="dlkitgrid"></div>
  <div class="dlkitfoot">
    <label>Size <input type="range" id="dlkitscale" min="0.25" max="6"
      step="0.05" value="1"></label>
    <button class="dlghost" id="dlkitflip">Mirror</button>
    <button class="dlghost" id="dlkitdel">Remove</button>
  </div>
  <p class="dlkitmsg" id="dlkitmsg"></p>
</aside>

<aside class="dlcard" id="dlcard" hidden></aside>

<script>window.DL = {json.dumps({"people": data["people"], "sizes": sizes,
                                 "gid": str(guild.id), "me": viewer,
                                 "world": data["world"],
                                 "assets": data["assets"],
                                 "decorsize": decor_size})};</script>
<script>{_SCRIPT}</script>
</body></html>"""
    return web.Response(text=body, content_type="text/html")


# The palette is shared with the player pages (``web/dodoland/theme.py``) — it
# was copied into them once, and two copies of a colour scheme become two colour
# schemes the moment either is edited.
_CSS = theme.PALETTE + """
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--deep); color: var(--ink); overflow: hidden;
  font: 15px/1.5 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }

.dlbar { position: fixed; inset: 0 0 auto 0; height: 52px; z-index: 30;
  display: flex; align-items: center; gap: 14px; padding: 0 16px;
  background: var(--bar); color: #f4e6cf; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
.dlback { color: #f0c98a; text-decoration: none; }
.dlback:hover { text-decoration: underline; }
.dlcount { font-size: 13px; opacity: .8; }
.dlspacer { flex: 1 1 auto; }
.dlghost { background: none; border: 1px solid rgba(255,255,255,.25);
  color: inherit; border-radius: 8px; padding: 6px 12px; cursor: pointer;
  font: inherit; font-size: 13px; }
.dlghost:hover { background: rgba(255,255,255,.1); }

/* The map gets the window. Everything else floats over it. */
.dlframe { position: fixed; inset: 52px 0 0 0; overflow: hidden;
  cursor: grab; touch-action: none; background: var(--deep); }
.dlframe.dragging { cursor: grabbing; }
.dlframe.placing { cursor: crosshair; }
/* No will-change here, and it must stay that way. Promoting this to its own
   composited layer makes the browser rasterise it once at whatever size it
   happened to be and then scale that bitmap, so an SVG map stops being vector
   the moment anybody zooms and every town blurs with it. The transform is
   cheap enough without the hint. */
.dlworld { position: absolute; top: 0; left: 0; transform-origin: 0 0; }
.dlworld img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }
.dlnomap { padding: 40px; color: var(--soft); }

/* Above the drawers, and out from under the open one. These sat at z-index 12
   under a 340px drawer that opens by default, so the whole control column was
   invisible and every press landed on the drawer instead — which looks exactly
   like four buttons with no handlers. */
.dlzoom { position: fixed; right: 16px; top: 68px; display: flex;
  flex-direction: column; gap: 6px; z-index: 26;
  transition: right .18s ease; }
.dlzoom.shifted { right: 356px; }
.dlzoom button { width: 38px; height: 38px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--edge); background: var(--paper); color: var(--ink);
  box-shadow: 0 2px 10px rgba(0,0,0,.35); }
.dlzoom button.on { background: var(--lantern); color: #fff; }
.dlhint { position: absolute; left: 16px; bottom: 16px; z-index: 12;
  padding: 6px 12px; border-radius: 9px; font-size: 13px;
  background: rgba(0,0,0,.55); color: #fff3e0; }

/* A town is placed and sized in the map's own units and sits inside the element
   the zoom scales, so it shrinks and grows with the coastline exactly as a
   village on a paper map does. It is deliberately NOT counter-scaled: an
   earlier version pinned towns to a fixed screen size, which made them loom
   larger the further you zoomed out until the map was all roofs. */
.dltown { position: absolute; transform: translate(-50%, -100%);
  cursor: pointer; z-index: 5; }
.dlart { width: 100%; }
.dltown svg { display: block; width: 100%; height: auto; overflow: visible; }
/* Below a few dozen pixels a settlement is an illegible smudge, so it becomes a
   dot, which is what every map does as you pull away from it. */
.dltown.tiny .dlart, .dltown.tiny .dlname { display: none; }
.dltown.tiny .dldot { display: block; }
/* In flow, not absolute: when a town is a dot this is its only visible child,
   and an absolutely positioned one left the town with no height and therefore
   nothing to click. A dot you cannot open is not a town on a map. */
.dldot { display: none; width: 11px; height: 11px; border-radius: 50%;
  margin: 0 auto; background: #f0c98a; border: 2px solid #4a3524;
  box-shadow: 0 1px 3px rgba(0,0,0,.5); }
.dltown.tiny { min-width: 14px; }
.dltown.dim { opacity: .5; }
/* A filter on anything inside the scaled world rasterises it, so the selected
   town is marked with an outline on its ground plate rather than a glow. Same
   reason will-change is banned above: keep the vectors vectors. */
.dltown.on .dlart { outline: none; }
.dltown.on ellipse:first-of-type { stroke: var(--lantern); stroke-width: 3; }
.dltown.on .dldot { box-shadow: 0 0 0 3px var(--lantern); }
/* The name is drawn at a constant screen size, because a label that shrinks
   with the map stops being a label. It is the one thing here that is
   counter-scaled, and only ever the text. */
.dlname { position: absolute; left: 50%; top: 100%; margin-top: 4px;
  transform: translateX(-50%) scale(var(--inv, 1)); transform-origin: top center;
  padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: #fff6e4; background: rgba(20,14,8,.82); white-space: nowrap;
  opacity: 0; transition: opacity .12s ease; pointer-events: none; }
.dltown:hover { z-index: 9; }
.dltown:hover .dlname, .dlworld.named .dlname, .dltown.on .dlname { opacity: 1; }
""" + theme.TOWN_ART_CSS + """
/* Drawers float over the map rather than stealing its width. */
.dldrawer { position: fixed; top: 52px; bottom: 0; right: 0; width: 340px;
  z-index: 20; display: flex; flex-direction: column; background: var(--paper);
  border-left: 1px solid var(--edge); box-shadow: -6px 0 24px rgba(0,0,0,.28);
  transform: translateX(100%); transition: transform .18s ease; }
.dldrawer.open { transform: none; }
.dldhead { display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--edge); }
.dldhead .dlghost { border-color: var(--edge); }
.dlsearch { margin: 10px 14px; padding: 8px 10px; font: inherit; font-size: 14px;
  border: 1px solid var(--edge); border-radius: 8px; background: var(--deep);
  color: var(--ink); }
.dllist { flex: 1 1 auto; overflow-y: auto; padding: 0 8px 16px; }
.dlgroup { padding: 10px 6px 4px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .12em; color: var(--soft); }
.dlrow { display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 8px 8px; border: 0; border-radius: 8px; background: none;
  color: inherit; font: inherit; text-align: left; cursor: pointer; }
.dlrow:hover { background: var(--deep); }
.dlrow.armed { background: var(--lantern); color: #fff; }
.dlrow .n { flex: 1 1 auto; min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.dlrow .p { font-size: 12px; opacity: .75; }

.dlcard { position: fixed; left: 16px; bottom: 16px; width: 340px; z-index: 25;
  padding: 16px 18px; border-radius: 12px; background: var(--paper);
  border: 1px solid var(--edge); box-shadow: 0 10px 34px rgba(0,0,0,.35);
  /* The editor makes this tall enough to run off the top of the screen, and a
     Save button nobody can reach is a Save button that does not work. */
  max-height: calc(100vh - 84px); overflow-y: auto; }
.cardmsg { margin: 10px 0 0; font-size: 13px; color: var(--soft); }
.cardmsg.bad { color: #c0392b; font-weight: 600; }
.dlcard h3 { margin: 0 0 2px; font-size: 19px; }
.dlcard .sub { color: var(--soft); font-size: 13px; margin-bottom: 10px; }
.dlcard ul { list-style: none; margin: 8px 0 0; padding: 0; }
.dlcard li { display: flex; align-items: center; gap: 8px; padding: 3px 0;
  font-size: 14px; }
/* A building's own line, and the rooms that build it once it is the one being
   asked about. Every building's channels at once is a wall of names; the
   question is only ever asked about the one somebody just clicked. */
.dlcard li.bline { display: block; padding: 4px 0; }
.dlcard .btop { display: flex; align-items: center; gap: 8px; }
.dlcard li.bline.focus { background: var(--deep); border-radius: 8px;
  padding: 6px 8px; margin: 2px -8px; }
.brooms { font-size: 12px; color: var(--soft); margin-top: 3px;
  word-break: break-word; }
/* The lot under the pointer says it can be opened, and the one that is open is
   picked out by its ground plate rather than by a filter — a filter inside the
   scaled world rasterises whatever it touches. */
.lot.named { cursor: pointer; }
.dlcard li i { width: 20px; text-align: center; color: var(--lantern); }
.dlcard .acts { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.dlcard button.own { background: var(--lantern); color: #fff;
  border-color: var(--lantern); }
.yours { font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
  padding: 2px 7px; border-radius: 999px; vertical-align: middle;
  background: var(--lantern); color: #fff; }
.dlcard .blurb { margin: 8px 0 0; font-size: 14px; color: var(--soft);
  white-space: pre-wrap; }
.dledit { margin-top: 12px; display: none; }
.dledit.open { display: block; }
.dledit label { display: block; font-size: 12px; color: var(--soft);
  margin: 8px 0 3px; }
.dledit input, .dledit textarea { width: 100%; padding: 7px 9px; font: inherit;
  font-size: 14px; border: 1px solid var(--edge); border-radius: 8px;
  background: var(--deep); color: var(--ink); }
.dledit textarea { min-height: 70px; resize: vertical; }
.dlcard button { flex: 1 1 auto; padding: 7px 10px; border-radius: 8px;
  border: 1px solid var(--edge); background: var(--deep); color: var(--ink);
  font: inherit; font-size: 13px; cursor: pointer; }
.dlcard button:hover { background: var(--edge); }

/* ---- the toolkit -------------------------------------------------------- */
/* Decor sits inside `.dlworld`, so it scales and pans with the coastline
   exactly as a town does. It is placed at a percentage of the base image for
   the same reason towns are: re-uploading a redrawn map at another resolution
   must move nothing. */
.dlpiece { position: absolute; transform: translate(-50%, -85%);
  z-index: 4; cursor: pointer; }
.dlpiece img { display: block; width: 100%; height: auto;
  -webkit-user-drag: none; user-select: none; pointer-events: none; }
.dlpiece.flip img { transform: scaleX(-1); }
/* An outline rather than a filter: a filter inside the scaled world rasterises
   whatever it touches, which is the same rule the towns live under. */
.dlpiece.on { outline: 2px solid var(--lantern); outline-offset: 2px;
  border-radius: 3px; }
/* Grabbable, and grabbed. touch-action stops the browser treating a drag on a
   piece as a scroll of the page underneath it. */
.dlpiece { touch-action: none; cursor: grab; }
.dlpiece.dragging { cursor: grabbing; opacity: .85; }
/* Town decor belongs to a town and sits under its buildings, so a cart parked
   outside the tavern is outside the tavern rather than on its roof. */
.dlpiece.town { z-index: 3; }

.dlkitdrawer { left: 0; right: auto; border-left: 0;
  border-right: 1px solid var(--edge); transform: translateX(-100%);
  box-shadow: 6px 0 24px rgba(0,0,0,.28); }
.dlkitdrawer.open { transform: translateX(0); }
.dlkithint { margin: 0; padding: 0 14px 8px; font-size: 12px; color: var(--soft); }
.dlkitgrid { flex: 1 1 auto; overflow-y: auto; display: grid; gap: 8px;
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); padding: 0 14px 14px; }
.dlkititem { border: 1px solid var(--edge); border-radius: 9px; padding: 6px;
  background: var(--deep); cursor: pointer; display: flex; flex-direction: column;
  align-items: center; gap: 4px; font: inherit; color: inherit; }
.dlkititem img { width: 100%; height: 42px; object-fit: contain; }
.dlkititem span { font-size: 10px; text-align: center; line-height: 1.2;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.dlkititem.armed { border-color: var(--lantern); background: var(--paper);
  box-shadow: 0 0 0 2px var(--lantern) inset; }
/* A locked thing is shown, not hidden. Knowing the gilded banner exists at the
   third tier of the Gallery is the reason to want the third tier. */
.dlkititem.locked { opacity: .42; cursor: not-allowed; }
.dlkititem.locked span::after { content: " 🔒"; }
.dlkitfoot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 10px 14px; border-top: 1px solid var(--edge); }
.dlkitfoot label { font-size: 12px; color: var(--soft); display: flex;
  align-items: center; gap: 6px; flex: 1 1 120px; }
.dlkitfoot input[type=range] { flex: 1 1 auto; min-width: 60px; }
.dlkitmsg { margin: 0; padding: 0 14px 12px; font-size: 12px; color: var(--soft); }
.dlkitmsg.bad { color: #c0392b; font-weight: 600; }
.dlkitempty { padding: 0 14px; color: var(--soft); font-size: 13px; }

@media (max-width: 720px) {
  .dldrawer { width: 100%; }
  .dlcard { left: 8px; right: 8px; width: auto; }
}
"""

_SCRIPT = r"""
(function () {
  var D = window.DL, frame = document.getElementById('dlframe'),
      world = document.getElementById('dlworld'),
      base = document.getElementById('dlbase'),
      hint = document.getElementById('dlhint'),
      list = document.getElementById('dllist'),
      drawer = document.getElementById('dldrawer'),
      card = document.getElementById('dlcard');
  var byId = {};
  D.people.forEach(function (p) { byId[p.id] = p; });

  // --- the viewport ---------------------------------------------------- //
  var view = {x: 0, y: 0, k: 1}, nat = {w: 0, h: 0};
  function apply() {
    world.style.transform = 'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.k + ')';
    // Towns live in map space but are drawn at screen size, so each is scaled
    // back by 1/k. Without this a town becomes a billboard at 4x.
    // Only labels are counter-scaled: a name that shrinks with the map stops
    // being a name. The towns themselves scale with the world on purpose.
    world.style.setProperty('--inv', (1 / view.k).toFixed(4));
    levelOfDetail();
  }
  function clamp() {
    // Two different jobs depending on which is bigger. When the world is larger
    // than the frame, stop it being dragged past its own edges. When it is
    // smaller, centre it instead: the old rule took a min of one bound and a
    // max of another that had crossed over, which pinned the map to a nonsense
    // position and is what made zooming out and back in leave a mess.
    var w = nat.w * view.k, h = nat.h * view.k;
    var fw = frame.clientWidth, fh = frame.clientHeight;
    view.x = (w <= fw) ? (fw - w) / 2 : Math.min(0, Math.max(fw - w, view.x));
    view.y = (h <= fh) ? (fh - h) / 2 : Math.min(0, Math.max(fh - h, view.y));
  }
  function fit() {
    if (!nat.w || !nat.h) return;
    // Re-read: a resize or a replaced image can change these underneath us.
    if (base && base.naturalWidth) { nat.w = base.naturalWidth; nat.h = base.naturalHeight; }
    // Measured after layout: called too early the frame has no height yet and
    // the map ends up stranded in the middle of a black screen, which is what
    // it did. A little air so the coastline is not flush against the edges.
    var fw = frame.clientWidth, fh = frame.clientHeight;
    if (!fw || !fh) { requestAnimationFrame(fit); return; }
    var pad = 24;
    view.k = Math.min((fw - pad * 2) / nat.w, (fh - pad * 2) / nat.h);
    view.k = Math.min(D.sizes.max_zoom, Math.max(D.sizes.min_zoom, view.k));
    clamp();
    apply();
  }
  function zoom(f, cx, cy) {
    var n = Math.min(D.sizes.max_zoom, Math.max(D.sizes.min_zoom, view.k * f));
    if (n === view.k) return;
    view.x = cx - (cx - view.x) * (n / view.k);
    view.y = cy - (cy - view.y) * (n / view.k);
    view.k = n; clamp(); apply();
  }
  function measure() {
    if (!base) return;
    // An SVG with no intrinsic size reports 0, so fall back to what it actually
    // laid out at rather than to a number that makes fit() meaningless.
    var box = base.getBoundingClientRect();
    nat.w = base.naturalWidth || Math.round(box.width) || frame.clientWidth;
    nat.h = base.naturalHeight || Math.round(box.height) || frame.clientHeight;
    // Width only: the image carries its own aspect, and pinning a height too
    // means any disagreement between the two shows as the world drifting away
    // from the coastline drawn on it.
    world.style.width = nat.w + 'px';
    requestAnimationFrame(fit);
  }
  if (base) { if (base.complete && base.naturalWidth) measure();
              else base.addEventListener('load', measure); }
  window.addEventListener('resize', function () { clamp(); apply(); });

  frame.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var b = frame.getBoundingClientRect();
    zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX - b.left, ev.clientY - b.top);
  }, {passive: false});

  // Pointer capture is taken only once a drag has actually started. Taking it
  // on pointerdown routes every following event to the frame, so a plain click
  // on a town never reaches the town and nothing opens. That is why towns and
  // dots were unclickable.
  var down = false, captured = false, moved = 0, last = null, pid = null;
  frame.addEventListener('pointerdown', function (ev) {
    down = true; captured = false; moved = 0; pid = ev.pointerId;
    last = {x: ev.clientX, y: ev.clientY};
  });
  frame.addEventListener('pointermove', function (ev) {
    if (!down) return;
    var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
    moved += Math.abs(dx) + Math.abs(dy);
    if (!captured && moved > 4) {
      // Now it is a drag rather than a click, so hold on to the pointer.
      captured = true;
      frame.classList.add('dragging');
      try { frame.setPointerCapture(pid); } catch (e) {}
    }
    if (!captured) return;
    view.x += dx; view.y += dy; last = {x: ev.clientX, y: ev.clientY};
    clamp(); apply();
  });
  ['pointerup', 'pointercancel'].forEach(function (e) {
    frame.addEventListener(e, function () {
      down = false; captured = false; frame.classList.remove('dragging');
    });
  });
  document.getElementById('dlin').onclick = function () {
    zoom(1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlout').onclick = function () {
    zoom(1 / 1.4, frame.clientWidth / 2, frame.clientHeight / 2); };
  document.getElementById('dlfit').onclick = fit;
  var namesBtn = document.getElementById('dlnames');
  namesBtn.onclick = function () {
    var on = world.classList.toggle('named');
    namesBtn.classList.toggle('on', on);
  };

  // --- towns ------------------------------------------------------------ //
  // --- level of detail -------------------------------------------------- //
  // Three questions, asked on every pan and zoom: is this town on screen at
  // all, is it big enough to be more than a dot, and is it close enough for its
  // flourishes. Only the first decides whether it exists in the DOM.
  var nodes = {}, art = {};

  function draw(person) {
    var el = document.createElement('div');
    el.className = 'dltown fl' + person.flourish + (person.lit ? '' : ' dim');
    el.dataset.id = person.id;
    el.style.left = person.plot.x + '%';
    el.style.top = person.plot.y + '%';
    // A percentage of the world, which is the base image's own width, so a town
    // is a fixed fraction of the map whatever resolution that image happens to
    // be. It sits inside the element the zoom scales, so it shrinks and grows
    // with the coastline.
    el.style.width = (person.w || D.sizes.town_pct) + '%';
    el.innerHTML = '<span class="dldot"></span>' +
      '<div class="dlart"></div>' +
      '<div class="dlname">' + escapeHtml(person.name) + '</div>';
    el.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (moved > 6) return;
      // Which building was clicked, if any. A town is a pile of overlapping
      // silhouettes and the one you want is often behind another, so clicking
      // it brings it out and opens the card on it.
      var lot = ev.target.closest && ev.target.closest('.lot.named');
      var key = lot && lot.getAttribute('data-building');
      if (lot) {
        // Paint order is document order in SVG, so moving the group to the end
        // of its parent is what "bring to the front" means here.
        lot.parentNode.appendChild(lot);
      }
      open(person.id, key || null);
    });
    world.appendChild(el);
    nodes[person.id] = el;
    return el;
  }

  function needArt(person, el) {
    // Fetched once per town, then kept. A town that is never approached is
    // never drawn, which is what lets a building be as detailed as it likes.
    if (art[person.id] === undefined) {
      art[person.id] = null;  // in flight; do not ask twice
      fetch('/guild/' + D.gid + '/dodoland/town/' + person.id + '/art')
        .then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (svg) {
          art[person.id] = svg;
          var host = nodes[person.id];
          if (host && svg) {
            host.querySelector('.dlart').innerHTML =
              '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
              svg + '</svg>';
          }
        }).catch(function () { art[person.id] = ''; });
    } else if (art[person.id]) {
      var host = el.querySelector('.dlart');
      if (!host.firstChild) {
        host.innerHTML = '<svg viewBox="0 0 120 78" xmlns="http://www.w3.org/2000/svg">' +
          art[person.id] + '</svg>';
      }
    }
  }

  function levelOfDetail() {
    if (!nat.w) return;
    // Sizes differ per town now, so the thresholds are asked per town rather
    // than once for the map. A large settlement keeps its buildings and its
    // smoke further out than a hamlet does, which is what you would expect.
    var mapPx = nat.w * view.k / 100;

    // The visible rectangle, in map percentages, with a margin so a town does
    // not pop in at the very edge of the frame.
    var pad = nat.w * (D.sizes.town_pct / 100) * view.k * 3;
    var x0 = ((-view.x - pad) / (nat.w * view.k)) * 100;
    var x1 = ((-view.x + frame.clientWidth + pad) / (nat.w * view.k)) * 100;
    var y0 = ((-view.y - pad) / (nat.h * view.k)) * 100;
    var y1 = ((-view.y + frame.clientHeight + pad) / (nat.h * view.k)) * 100;

    D.people.forEach(function (p) {
      if (!p.plot) return;
      var on = p.plot.x >= x0 && p.plot.x <= x1 && p.plot.y >= y0 && p.plot.y <= y1;
      var el = nodes[p.id];
      if (!on) {
        if (el) { el.remove(); delete nodes[p.id]; }
        return;
      }
      if (!el) el = draw(p);
      var shown = (p.w || D.sizes.town_pct) * mapPx;
      var tiny = shown < D.sizes.dot_below;
      el.classList.toggle('tiny', tiny);
      el.classList.toggle('close', shown > D.sizes.detail_above);
      // A dot needs no artwork, which is most of the saving on a wide view.
      if (!tiny) needArt(p, el);
    });
    // Decor is sized against the base image, which is 0 until it has loaded.
    if (typeof resizeDecor === 'function') resizeDecor();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function redraw() {
    world.querySelectorAll('.dltown').forEach(function (n) { n.remove(); });
    nodes = {};
    levelOfDetail();
    var on = D.people.filter(function (p) { return p.plot; }).length;
    document.getElementById('dlplaced').textContent = on;
    document.getElementById('dlwaiting').textContent = D.people.length - on;
  }

  // --- the town card ----------------------------------------------------- //
  var openId = null;
  function open(id, focusKey) {
    var p = byId[id];
    if (!p) return;
    openId = id;
    world.querySelectorAll('.dltown').forEach(function (n) {
      n.classList.toggle('on', n.dataset.id === id);
    });
    var rows = p.built.map(function (b) {
      // The rooms that build it, on the one that was clicked. Every building
      // at once is a wall of channel names; the question is only ever asked
      // about the building somebody just pointed at.
      var on = focusKey && b.key === focusKey;
      var rooms = (b.rooms && b.rooms.length)
        ? b.rooms.map(escapeHtml).join(' ')
        : 'No rooms are attached to it yet.';
      return '<li class="bline' + (on ? ' focus' : '') + '"' +
        ' data-key="' + escapeHtml(b.key) + '">' +
        '<div class="btop"><span>' + escapeHtml(b.name) + ' — <b>' +
        escapeHtml(b.title) + '</b></span>' +
        '<span style="margin-left:auto;opacity:.7">' + b.points.toLocaleString() +
        '</span></div>' +
        (on ? '<div class="brooms">Built by ' + rooms + '</div>' : '') +
        '</li>';
    }).join('') || '<li style="opacity:.7">Nothing built yet.</li>';

    // Every building can be renamed, which is why they are inputs rather than
    // text once the editor is open. Naming is free and moves no number.
    var nameFields = p.built.map(function (b) {
      return '<label>' + escapeHtml(b.given) + '</label>' +
        '<input class="bname" data-key="' + escapeHtml(b.key) + '" maxlength="48" value="' +
        escapeHtml(b.name) + '">';
    }).join('');

    // Whose town this is decides what the card offers. Editing somebody
    // else's is an administrative act and says so, rather than quietly looking
    // like editing your own.
    var mine = D.me && String(p.id) === String(D.me);
    card.innerHTML =
      '<h3>' + escapeHtml(p.name) +
        (mine ? ' <span class="yours">yours</span>' : '') + '</h3>' +
      '<div class="sub">' + escapeHtml(p.owner) + ' · #' + p.place + ' · ' +
        p.power.toLocaleString() + ' standing · ' + p.reached.toLocaleString() +
        ' people reached' +
        (p.rank ? ' · ' + escapeHtml(p.flourish_label) + ' (' + escapeHtml(p.rank) + ')' : '') +
        '</div>' +
      (p.blurb ? '<p class="blurb">' + escapeHtml(p.blurb) + '</p>' : '') +
      (p.has_image
        ? '<div class="cardflag"><img alt="" src="/guild/' + D.gid +
          '/dodoland/town/' + p.id + '/picture"></div>'
        : '') +
      '<ul>' + rows + '</ul>' +
      (p.plot ? '<div class="sub" style="margin-top:10px">At ' +
        p.plot.x.toFixed(1) + ', ' + p.plot.y.toFixed(1) + '</div>' : '') +
      '<div class="acts">' +
        (mine
          ? '<button data-act="edit" class="own">Customise your town</button>'
          : '<button data-act="edit">Admin edit</button>') +
        '<button data-act="move">Move</button>' +
        '<button data-act="remove">Remove</button>' +
        '<button data-act="close">Close</button></div>' +
      '<div class="dledit">' +
        '<label>Town name</label>' +
        '<input id="tname" maxlength="48" value="' + escapeHtml(p.name) + '">' +
        '<label>Description</label>' +
        '<textarea id="tblurb" maxlength="600">' + escapeHtml(p.blurb) + '</textarea>' +
        '<label>Picture or GIF</label>' +
        '<input id="tpic" type="file" accept="image/png,image/jpeg,image/gif,image/webp">' +
        (nameFields ? '<label style="margin-top:12px"><b>Building names</b></label>' +
          nameFields : '') +
        '<div class="acts"><button data-act="save" class="own">Save</button>' +
        '<button data-act="clearpic">Remove picture</button></div>' +
        '<p class="cardmsg" id="dlcardmsg"></p>' +
      '</div>';
    card.hidden = false;
    var editor = card.querySelector('.dledit');
    card.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        var act = b.dataset.act;
        if (act === 'close') { closeCard(); }
        else if (act === 'move') { arm(id); closeCard(); }
        else if (act === 'remove') { place(id, null); closeCard(); }
        else if (act === 'edit') { editor.classList.toggle('open'); }
        else if (act === 'clearpic') { saveTown(id, {clear_image: true}); }
        else if (act === 'save') {
          var names = {};
          card.querySelectorAll('.bname').forEach(function (i) {
            names[i.dataset.key] = i.value;
          });
          var pic = card.querySelector('#tpic');
          var chosen = pic && pic.files && pic.files[0];
          var payload = {
            name: card.querySelector('#tname').value,
            blurb: card.querySelector('#tblurb').value,
            building_names: names
          };
          if (!chosen) { saveTown(id, payload); return; }
          if (chosen.size > 6 * 1024 * 1024) {
            var box = document.getElementById('dlcardmsg');
            if (box) {
              box.classList.add('bad');
              box.textContent = 'That picture is ' +
                (chosen.size / 1048576).toFixed(1) + 'MB. The limit is 6MB, so ' +
                'nothing was saved. Pick a smaller one, or clear it and save ' +
                'the rest.';
            }
            return;
          }
          var reader = new FileReader();
          reader.onload = function () {
            payload.image = String(reader.result).split(',').pop();
            payload.content_type = chosen.type;
            saveTown(id, payload);
          };
          reader.readAsDataURL(chosen);
        }
      };
    });
  }

  function saveTown(id, payload) {
    // Anything this says has to appear in the card. It used to go to the hint
    // bar in the far corner of the map, behind the card and often off screen,
    // so a refused save looked exactly like a button that did nothing.
    var say = function (text, bad) {
      var box = document.getElementById('dlcardmsg');
      if (box) { box.textContent = text; box.classList.toggle('bad', !!bad); }
      hint.textContent = text;
    };
    payload.user_id = id;
    say('Saving...');
    fetch('/api/guild/' + D.gid + '/dodoland/town', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { say(res.error || 'That did not work.', true); return; }
      say('Saved. Reloading...');
      setTimeout(function () { window.location.reload(); }, 400);
    }).catch(function (err) { say(String(err), true); });
  }
  function closeCard() {
    card.hidden = true; openId = null;
    world.querySelectorAll('.dltown.on').forEach(function (n) {
      n.classList.remove('on');
    });
  }

  // --- placing ----------------------------------------------------------- //
  var armed = null;
  function arm(id) {
    armed = id;
    frame.classList.add('placing');
    hint.textContent = 'Click the map to place ' + byId[id].name;
    renderList();
  }
  function place(id, point) {
    fetch('/api/guild/' + D.gid + '/dodoland/settle', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(point
        ? {user_id: id, x: point.x, y: point.y}
        : {user_id: id, remove: true})
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { hint.textContent = res.error || 'That did not work.'; return; }
      byId[id].plot = point ? {x: res.x, y: res.y} : null;
      armed = null;
      frame.classList.remove('placing');
      hint.textContent = point ? 'Placed.' : 'Removed from the map.';
      redraw(); renderList();
    });
  }
  frame.addEventListener('click', function (ev) {
    if (moved > 6 || !nat.w) return;
    var b = frame.getBoundingClientRect();
    var at = {
      x: ((ev.clientX - b.left - view.x) / (nat.w * view.k)) * 100,
      y: ((ev.clientY - b.top - view.y) / (nat.h * view.k)) * 100
    };
    // Settling a town and placing decor are the same gesture on the same
    // surface, so only one of them may ever be armed at a time.
    if (armed) { place(armed, at); return; }
    if (armedAsset) { placeDecor(at); return; }
    // Nothing armed and nothing under the pointer: let go. Without this a
    // selected piece stayed selected for ever and Remove kept pointing at it.
    if (heldPiece) { hold(heldPiece); }
  });

  // --- the list ---------------------------------------------------------- //
  var search = document.getElementById('dlsearch');
  function renderList() {
    var q = (search.value || '').toLowerCase();
    var hit = D.people.filter(function (p) {
      return !q || p.name.toLowerCase().indexOf(q) >= 0;
    });
    var waiting = hit.filter(function (p) { return !p.plot; });
    var placed = hit.filter(function (p) { return p.plot; });
    function group(title, rows) {
      if (!rows.length) return '';
      return '<div class="dlgroup">' + title + ' (' + rows.length + ')</div>' +
        rows.map(function (p) {
          return '<button class="dlrow' + (armed === p.id ? ' armed' : '') +
            '" data-id="' + p.id + '"><span class="n">' + escapeHtml(p.name) +
            '</span><span class="p">' + p.power.toLocaleString() + '</span></button>';
        }).join('');
    }
    list.innerHTML = group('Not on the map', waiting) + group('Placed', placed);
    list.querySelectorAll('.dlrow').forEach(function (row) {
      row.onclick = function () {
        var p = byId[row.dataset.id];
        if (p.plot) { open(p.id); }
        else { arm(p.id); }
      };
    });
  }
  search.addEventListener('input', renderList);
  // The zoom controls have to stay reachable whichever drawer is open, so
  // they step aside rather than hide behind it.
  var zoombar = document.querySelector('.dlzoom');
  function placeZoom() {
    zoombar.classList.toggle('shifted', drawer.classList.contains('open'));
  }
  document.getElementById('dltoggle').onclick = function () {
    drawer.classList.toggle('open');
    kitDrawer.classList.remove('open');
    placeZoom();
  };
  document.getElementById('dlclose').onclick = function () {
    drawer.classList.remove('open');
    placeZoom();
  };


  // --- the toolkit ------------------------------------------------------- //
  // Two things it does, and they are one gesture each: pick something from the
  // library and click the ground to put it there, or click a piece already on
  // the ground to take hold of it. Everything else — size, mirror, remove —
  // acts on whatever is held.
  //
  // Positions are percentages of the base image, exactly like a town's, so a
  // redrawn map at another resolution moves nothing that has been placed.
  var kitDrawer = document.getElementById('dlkitdrawer'),
      kitGrid = document.getElementById('dlkitgrid'),
      kitMsg = document.getElementById('dlkitmsg'),
      kitScale = document.getElementById('dlkitscale');
  var armedAsset = null, heldPiece = null, pieces = {};

  function kitSay(text, bad) {
    if (!kitMsg) return;
    kitMsg.textContent = text || '';
    kitMsg.classList.toggle('bad', !!bad);
  }

  function assetUrl(id) {
    return '/guild/' + D.gid + '/dodoland/asset/' + id;
  }

  function renderKit() {
    if (!D.assets.length) {
      kitGrid.innerHTML = '<p class="dlkitempty">The asset library is empty. ' +
        'Upload something on the DodoLand page first.</p>';
      return;
    }
    kitGrid.innerHTML = D.assets.map(function (a) {
      return '<button class="dlkititem' +
        (armedAsset === a.id ? ' armed' : '') + '" data-asset="' + a.id + '">' +
        '<img alt="" src="' + assetUrl(a.id) + '">' +
        '<span>' + escapeHtml(a.name) + '</span></button>';
    }).join('');
    kitGrid.querySelectorAll('.dlkititem').forEach(function (el) {
      el.onclick = function () {
        armedAsset = (armedAsset === el.dataset.asset) ? null : el.dataset.asset;
        heldPiece = null;
        frame.classList.toggle('placing', !!armedAsset);
        kitSay(armedAsset ? 'Click the map to place it.' : '');
        renderKit();
      };
    });
  }

  function pieceWidth(piece) {
    // A percentage of the base image, so decor shrinks with the coastline the
    // same way a town does. `nat.w` is 0 until the map image has loaded, and
    // dividing by 1 then made every piece twenty-eight times the width of the
    // world — so a piece drawn before the image arrives is redrawn after it.
    if (!nat.w) return null;
    return (D.decorsize * piece.s / nat.w * 100) + '%';
  }

  function drawPiece(piece) {
    var el = document.createElement('div');
    el.className = 'dlpiece' + (piece.f ? ' flip' : '');
    el.dataset.id = piece.id;
    el.style.left = piece.x + '%';
    el.style.top = piece.y + '%';
    var w = pieceWidth(piece);
    if (w) el.style.width = w;
    el.innerHTML = '<img alt="" src="' + assetUrl(piece.a) + '">';

    // Dragging, and clicking, from one gesture. The frame owns panning and
    // takes pointer capture as soon as a drag starts, so a piece that only
    // listened for `click` could be selected and never moved: every attempt to
    // drag one panned the map underneath it instead. Stopping the event here
    // is what keeps the map still while a piece is being moved.
    el.addEventListener('pointerdown', function (ev) {
      ev.stopPropagation();
      ev.preventDefault();
      var start = {x: ev.clientX, y: ev.clientY};
      var from = {x: piece.x, y: piece.y};
      var travelled = 0;
      try { el.setPointerCapture(ev.pointerId); } catch (e) {}
      el.classList.add('dragging');

      function onMove(move) {
        var dx = move.clientX - start.x, dy = move.clientY - start.y;
        travelled = Math.abs(dx) + Math.abs(dy);
        if (travelled <= 3 || !nat.w) return;
        // Screen pixels back into the map's own percentages: undo the zoom,
        // then divide by the base image's size.
        piece.x = from.x + (dx / view.k / nat.w) * 100;
        piece.y = from.y + (dy / view.k / nat.h) * 100;
        el.style.left = piece.x + '%';
        el.style.top = piece.y + '%';
      }

      function onUp() {
        el.removeEventListener('pointermove', onMove);
        el.removeEventListener('pointerup', onUp);
        el.removeEventListener('pointercancel', onUp);
        el.classList.remove('dragging');
        try { el.releasePointerCapture(ev.pointerId); } catch (e) {}
        if (travelled <= 3) { hold(piece.id); return; }
        hold(piece.id, true);
        decorPost({action: 'move', piece_id: piece.id,
                   x: Math.round(piece.x * 1000) / 1000,
                   y: Math.round(piece.y * 1000) / 1000},
                  function () { kitSay('Moved.'); });
      }

      el.addEventListener('pointermove', onMove);
      el.addEventListener('pointerup', onUp);
      el.addEventListener('pointercancel', onUp);
    });
    world.appendChild(el);
    pieces[piece.id] = el;
    return el;
  }

  function redrawDecor() {
    world.querySelectorAll('.dlpiece').forEach(function (n) { n.remove(); });
    pieces = {};
    D.world.forEach(drawPiece);
    if (heldPiece && pieces[heldPiece]) pieces[heldPiece].classList.add('on');
  }

  function resizeDecor() {
    // Only the widths, so this can run on every zoom without rebuilding the
    // nodes — and without throwing away a piece mid-drag.
    D.world.forEach(function (piece) {
      var el = pieces[piece.id], w = pieceWidth(piece);
      if (el && w) el.style.width = w;
    });
  }

  function pieceById(id) {
    for (var i = 0; i < D.world.length; i++) {
      if (D.world[i].id === id) return D.world[i];
    }
    return null;
  }

  function hold(id, keep) {
    heldPiece = (!keep && heldPiece === id) ? null : id;
    armedAsset = null;
    frame.classList.remove('placing');
    world.querySelectorAll('.dlpiece').forEach(function (n) {
      n.classList.toggle('on', n.dataset.id === heldPiece);
    });
    var p = heldPiece && pieceById(heldPiece);
    if (p) { kitScale.value = p.s; kitSay('Held. Drag the size, mirror it, or remove it.'); }
    else { kitSay(''); }
  }

  function decorPost(payload, then) {
    fetch('/api/guild/' + D.gid + '/dodoland/decor', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: 'The server answered with ' + r.status + '.'};
      });
    }).then(function (res) {
      if (!res.ok) { kitSay(res.error || 'That did not work.', true); return; }
      then(res);
    }).catch(function (err) { kitSay(String(err), true); });
  }

  function placeDecor(point) {
    decorPost({action: 'place', asset_id: armedAsset, x: point.x, y: point.y,
               scale: parseFloat(kitScale.value) || 1},
      function (res) {
        D.world.push({id: res.piece.piece_id, a: res.piece.asset_id,
                      x: res.piece.x, y: res.piece.y, s: res.piece.scale,
                      f: !!res.piece.flip});
        redrawDecor();
        kitSay('Placed. Click again to place another.');
      });
  }

  if (kitScale) kitScale.oninput = function () {
    var p = heldPiece && pieceById(heldPiece);
    if (!p) { kitSay('Click a placed piece first.', true); return; }
    p.s = parseFloat(kitScale.value) || 1;
    // Just the width. Rebuilding every node on each step of a slider threw the
    // element out from under the pointer.
    resizeDecor();
  };
  if (kitScale) kitScale.onchange = function () {
    var p = heldPiece && pieceById(heldPiece);
    if (!p) return;
    decorPost({action: 'move', piece_id: p.id, scale: p.s},
              function () { kitSay('Resized.'); });
  };
  document.getElementById('dlkitflip').onclick = function () {
    var p = heldPiece && pieceById(heldPiece);
    if (!p) { kitSay('Click a placed piece first.', true); return; }
    p.f = !p.f;
    redrawDecor();
    decorPost({action: 'move', piece_id: p.id, flip: p.f},
              function () { kitSay('Mirrored.'); });
  };
  document.getElementById('dlkitdel').onclick = function () {
    var p = heldPiece && pieceById(heldPiece);
    if (!p) { kitSay('Click a placed piece first.', true); return; }
    decorPost({action: 'remove', piece_id: p.id}, function () {
      D.world = D.world.filter(function (q) { return q.id !== p.id; });
      heldPiece = null;
      redrawDecor();
      kitSay('Removed.');
    });
  };
  document.getElementById('dlkit').onclick = function () {
    kitDrawer.classList.toggle('open');
    drawer.classList.remove('open');
    if (typeof placeZoom === 'function') placeZoom();
  };
  document.getElementById('dlkitclose').onclick = function () {
    kitDrawer.classList.remove('open');
    armedAsset = null;
    frame.classList.remove('placing');
    renderKit();
  };
  renderKit();

  redraw();
  redrawDecor();
  renderList();
  drawer.classList.add('open');
  placeZoom();
})();
"""
