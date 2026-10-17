"""
DodoLand's wiki: how the map works, in the bot owner's words.

A short list of sections (a title and a body each), one wiki for every server,
edited by the bot owner (``/dodoland/wiki``) and read from the map's "?"
button. Bodies are plain text with three marks: a blank line between
paragraphs, ``- `` at the start of a line for a bullet, ``**bold**``. Rendered
escaped, so nothing typed can run in anyone's browser.

Kept on the DodoLand config collection as ``{_id: "wiki", sections: [...]}``.
Until the owner saves, :data:`SKELETON` is the wiki.
"""

from __future__ import annotations

import html
import re

MAX_SECTIONS = 40
MAX_TITLE = 80
MAX_BODY = 6000

SKELETON = [
    ("What DodoLand is", "A shared map of the server, with a town for everyone on it.\n\n"
                         "- What the map is for\n- Who it is for"),
    ("Your town", "Placing your town, naming it, its picture and flag.\n\n- How to place it\n- How to move it"),
    ("Standing and tiers", "How talking with people makes your buildings grow.\n\n"
                           "- What counts\n- What a tier is\n- Reach: how many people you reached"),
    ("Buildings", "Each building and what grows it.\n\n- Which channels build which building"),
    ("Your traveller", "You on the roads: visiting the towns of the people you talk to most.\n\n"
                       "- Your colours and your horse\n- Pets that follow you\n- Finding your traveller"),
    ("Horses and zoos", "The runaway horse and the towns' horses: chase them into a zoo for sweetrolls.\n\n"
                        "- How to herd a horse\n- What a zoo pays\n- When a horse comes back"),
    ("The toolkit", "Putting things around your town: placing, moving, turning, painting the ground.\n\n"
                    "- Placing and moving\n- Turning (the two handles)\n- Painting the ground"),
    ("Day, night and lights", "The sun, the night, and the lights that come on in lively towns."),
    ("Questions", "- My town does not show on the map\n- Why did my building not grow?"),
]


def _clean(sections) -> list[dict]:
    if not isinstance(sections, list):
        raise ValueError("The wiki is a list of sections.")
    out = []
    for item in sections[:MAX_SECTIONS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:MAX_TITLE]
        body = str(item.get("body") or "").replace("\r\n", "\n").strip()[:MAX_BODY]
        if title or body:
            out.append({"title": title, "body": body})
    return out


def sections(collection) -> list[dict]:
    """The wiki as it stands: the owner's, or the skeleton."""
    doc = collection.find_one({"_id": "wiki"}) or {}
    saved = doc.get("sections")
    return list(saved) if saved else [{"title": t, "body": b} for t, b in SKELETON]


def save(collection, new) -> list[dict]:
    cleaned = _clean(new)
    collection.update_one({"_id": "wiki"}, {"$set": {"sections": cleaned}}, upsert=True)
    return cleaned


def render(body: str) -> str:
    """A body as HTML: paragraphs, bullets, bold; everything else escaped."""
    out = []
    for block in re.split(r"\n\s*\n", str(body or "").strip()):
        lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue

        def inline(text):
            return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))
        if all(ln.lstrip().startswith("- ") for ln in lines):
            out.append("<ul>" + "".join(f"<li>{inline(ln.lstrip()[2:])}</li>" for ln in lines) + "</ul>")
        else:
            out.append("<p>" + "<br>".join(inline(ln) for ln in lines) + "</p>")
    return "".join(out)
