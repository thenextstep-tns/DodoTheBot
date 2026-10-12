"""
Every text on a member's town page (the entrance to DodoLand), editable per
server.

Each is a DodoLand setting of type ``text`` (``dodoland_text_<key>``) whose
default is the wording the page has always had, edited in the panel under
*What members can see*. Blank means the default. ``{name}`` markers in a text
are filled in by the page (the rank, a number of days…); the panel shows which
a text has. Texts are plain: the page escapes them, so nothing typed here can
break the page or run in a member's browser.
"""

from __future__ import annotations

import html
from typing import Any

PREFIX = "dodoland_text_"

# (key, what it is, default, the {markers} it may use)
TEXTS = [
    ("owner_line", "Under the town's name", "{owner}'s town in {server}", ("owner", "server")),
    ("lit", "Status when active lately", "lit", ()),
    ("quiet", "Status when quiet lately", "quiet lately", ()),
    ("nothing_yet", "When nothing has been counted for someone yet",
     "Nothing has been counted for you yet, so your town is a single tent — which is still "
     "somewhere. It fills in on its own as you talk to people.", ()),
    ("tile_standing", "Tile: town standing", "town standing", ()),
    ("tile_place", "Tile: place among towns", "of {towns} towns", ("towns",)),
    ("tile_reached", "Tile: people reached", "people reached", ()),
    ("tile_flourish", "Tile: flourish", "flourish", ()),
    ("tile_no_flourish", "Tile: no flourish", "None", ()),
    ("flourish_title", "Flourish: heading", "Flourish", ()),
    ("flourish_none", "Flourish: when someone has none",
     "No flourish yet. Flourish is the one thing on this map that cannot be earned by being "
     "sociable — it comes from the trial ladder, and it is purely how your town looks. Every "
     "building here is reachable without it.", ()),
    ("flourish_from", "Flourish: where it comes from",
     "From your trial rank, {rank}. Rank buys the effect and never a tier: it changes how your "
     "town looks and nothing about what stands in it.", ("rank",)),
    ("decorate_title", "Decorate: heading", "Decorate", ()),
    ("decorate_intro", "Decorate: explanation",
     "Things you have earned the right to put around your town. Pick one, then click your town "
     "above to put it down; click a piece you have placed to pick it up again.", ()),
    ("decorate_size", "Decorate: size slider", "Size", ()),
    ("decorate_mirror", "Decorate: mirror button", "Mirror", ()),
    ("decorate_remove", "Decorate: remove button", "Remove", ()),
    ("climb_title", "The climb: heading", "The climb", ()),
    ("climb_intro", "The climb: explanation",
     "Every building this server has, whether or not you have reached it. Thresholds are a "
     "percentile of what everybody else has actually scored, so they move as the server does — "
     "this is where yours sit today.", ()),
    ("climb_not_yet", "The climb: a building not reached", "not yet", ()),
    ("climb_more", "The climb: points to the next tier", "{points} more to reach {tier}", ("points", "tier")),
    ("climb_top", "The climb: at the top tier", "Nothing above this one.", ()),
    ("reached_title", "Who you reached: heading", "Who you reached", ()),
    ("reached_intro", "Who you reached: explanation",
     "Reach, not volume: what counts is how many different people you reached and who reached "
     "back, capped per person per day so nobody can be farmed. These are the people you have "
     "shared the most days with, over the last {days} days.", ("days",)),
    ("customise_title", "Customise: heading", "Customise", ()),
    ("customise_intro", "Customise: explanation",
     "Yours to write. A picture flies as a flag over whatever you have built highest.", ()),
    ("label_name", "Customise: name field", "Town name", ()),
    ("label_blurb", "Customise: description field", "Description", ()),
    ("label_picture", "Customise: picture field", "Picture or GIF (under {mb}MB)", ("mb",)),
    ("label_building_names", "Customise: building names", "Building names", ()),
    ("save", "Customise: save button", "Save", ()),
    ("clear_picture", "Customise: remove picture button", "Remove picture", ()),
    ("foot", "At the bottom of the page",
     "Standing is earned and cannot be typed in. Everything on this page you can edit is "
     "authored: naming your town, describing it and picturing it move no number at all, and "
     "never will.", ()),
    ("map_link", "Top bar: link to the map", "The map", ()),
    ("logout", "Top bar: log out", "Log out", ()),
]
DEFAULTS = {key: default for key, _label, default, _markers in TEXTS}


def specs() -> list[dict]:
    """The settings, for ``helpers/dodoland/parameters.py``."""
    out = []
    for key, label, default, markers in TEXTS:
        fills = (" It may use " + ", ".join("{" + m + "}" for m in markers) +
                 ", filled in by the page.") if markers else ""
        out.append({"key": PREFIX + key, "cog": "dodoland", "type": "text", "default": default,
                    "label": f"Member page: {label}",
                    "description": "Shown on a member's own town page. Leave it blank for the "
                                   "default wording." + fills})
    return out


def say(params, guild_id: int, key: str, **fill: Any) -> str:
    """One text, ready for the page: the server's wording (or the default),
    escaped, with its markers filled. A value passed as ``(html,)`` is put in
    as markup the page made itself (bold rank names); everything else is
    escaped."""
    raw = ""
    try:
        raw = str(params.get(guild_id, PREFIX + key) or "")
    except KeyError:
        pass
    text = html.escape(raw.strip() or DEFAULTS[key])
    for name, value in fill.items():
        marker = "{" + name + "}"
        if marker in text:
            markup = value[0] if isinstance(value, tuple) else html.escape(str(value))
            text = text.replace(marker, markup)
    return text
