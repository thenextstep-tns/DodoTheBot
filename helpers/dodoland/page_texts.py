"""
Every text on DodoLand's entrance page (a member's own town page), editable
per server.

Each is a DodoLand setting of type ``text`` (``dodoland_text_<key>``) whose
default is the page's own wording, edited in the panel under
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
    ("welcome_title", "Heading", "Welcome to DodoLand", ()),
    ("welcome_lead", "Under the heading",
     "Everyone on {server} gets a town on a shared map. Setting yours up takes a minute.",
     ("server",)),
    ("step_name", "Step 1: heading", "Name your town", ()),
    ("name_placeholder", "Step 1: the empty name field", "{owner}'s town", ("owner",)),
    ("step_picture", "Step 2: heading", "Pick a picture", ()),
    ("picture_hint", "Step 2: explanation",
     "It flies as your town's flag. PNG, JPG, GIF or WebP, under {mb}MB.", ("mb",)),
    ("picture_choose", "Step 2: button when there is no picture yet", "Choose a picture", ()),
    ("picture_change", "Step 2: button when there is one", "Change picture", ()),
    ("step_grow", "Step 3: heading", "Watch it grow", ()),
    ("grow_text", "Step 3: explanation",
     "Talking with people on {server} makes your buildings grow and unlocks new things to put "
     "around your town. Here is the {building} on its way up:", ("server", "building")),
    ("place_button", "Main button, for a town not on the map yet", "Place my town!", ()),
    ("home_button", "Main button, for a town already on the map", "Go to my town", ()),
    ("map_button", "Main button, when an admin places the towns", "Open the map", ()),
    ("save_button", "Main button, when the map is closed to members", "Save my town", ()),
    ("admin_places", "Note when an admin places the towns",
     "An admin puts towns on this server's map, so yours will appear there soon.", ()),
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
                    "description": "Shown on DodoLand's entrance page. Leave it blank for the "
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
