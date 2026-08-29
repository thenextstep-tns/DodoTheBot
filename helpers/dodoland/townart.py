"""
Drawing a town out of primitive shapes.

A town is not an icon. It is a place, and it should look like one: a ground
plate, a few buildings standing on it, the grandest in the middle and the
smallest at the edges. Everything here is rectangles, triangles, circles and
polygons, so it renders anywhere, scales cleanly, needs no font and no network,
and can be told apart at a glance from somebody else's town.

Two rules the whole file is built on.

**A building's kind is its silhouette.** A chapel is tall and narrow with a
spire. A keep is squat with battlements. An inn is wide and low with an awning
and a hanging sign. Colour alone was tried first and failed: fifteen buildings
in eight colours read as confetti, and at map size the only thing that survives
is the outline. If two buildings cannot be told apart in black, they cannot be
told apart at all.

**A building's tier is its geometry.** Tier one is a shed. Tier six has a spire,
a dome or a flag, depending on what it is. The silhouette is the progress bar:
you can see how far somebody has come without reading a number, which is the
whole reason to have a map rather than a table.

An icon font was tried before either of these and dropped. A glyph cannot
express a tier, and every glyph in a row at the same size reads as a fence
rather than a settlement.

The output is a fragment, not a document: the caller places it inside its own
``<svg>`` so a whole map is one element rather than three hundred.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional

# The town's own coordinate space. Everything below is in these units, and the
# caller scales the whole thing, so a town keeps its proportions at any size.
WIDTH = 120.0
HEIGHT = 78.0
GROUND_Y = 64.0

WALL = "#f6efe2"
WALL_DARK = "#e6dac6"
LINE = "#3a2718"
DOOR = "#4a3524"
GLASS = "#7fb2d9"

PALETTE = ("#c0392b", "#2f6fa8", "#3f8f5e", "#b8862b", "#7a4fa3", "#c05a8a",
           "#2f8f8f", "#a0522d")

MAX_BUILDINGS = 7


def colour_for(key: str) -> str:
    """A stable colour per building key.

    Hashed rather than assigned in order, so adding a building does not
    re-colour every town on the map.
    """
    digest = hashlib.sha1(str(key).encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def _rect(x, y, w, h, fill=WALL, stroke=LINE, width=1.1, rx=0.8) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')


def _tri(x1, y1, x2, y2, x3, y3, fill) -> str:
    return (f'<polygon points="{x1:.1f},{y1:.1f} {x2:.1f},{y2:.1f} {x3:.1f},{y3:.1f}" '
            f'fill="{fill}" stroke="{LINE}" stroke-width="1.1" stroke-linejoin="round"/>')


def _door(x, base, w=4.0, h=6.0, arch=False) -> str:
    if arch:
        return (f'<path d="M{x - w / 2:.1f},{base:.1f} L{x - w / 2:.1f},{base - h * 0.6:.1f} '
                f'A{w / 2:.1f},{w / 2:.1f} 0 0 1 {x + w / 2:.1f},{base - h * 0.6:.1f} '
                f'L{x + w / 2:.1f},{base:.1f} Z" fill="{DOOR}"/>')
    return _rect(x - w / 2, base - h, w, h, fill=DOOR, stroke="none", width=0, rx=0.6)


# --------------------------------------------------------------------------- #
#  Symbols and inhabitants, drawn rather than typed
# --------------------------------------------------------------------------- #
# These were Font Awesome glyphs set as SVG text. They did not render: the
# emblems were missing above every building and the wanderers came out as
# whatever the fallback font had at those codepoints. A webfont is a dependency
# that fails silently and at a distance, which is the worst way for the part
# people are meant to look at to fail, so everything here is drawn the same way
# the buildings are.
#
# The shapes carry what a building **is** and how far it has come; these carry
# what it is *for*. A keep with a shield on it and a keep with a map on it are
# the barracks and the war room, and no amount of masonry would have said which.

def _emblem_mug(c):
    return (f'<rect x="-3" y="-3.4" width="5.4" height="6.6" rx="1" fill="{c}" '
            f'stroke="{LINE}" stroke-width=".9"/>'
            f'<path d="M2.6,-1.6 A2.2,2.2 0 0 1 2.6,2.2" fill="none" '
            f'stroke="{LINE}" stroke-width=".9"/>')


def _emblem_book(c):
    return (f'<path d="M-4,-3 L0,-2 L0,3.4 L-4,2.4 Z" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".8"/>'
            f'<path d="M4,-3 L0,-2 L0,3.4 L4,2.4 Z" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".8" opacity=".8"/>')


def _emblem_shield(c):
    return (f'<path d="M0,-3.8 L3.6,-2.2 L3.6,1 Q3.6,3.2 0,4.2 Q-3.6,3.2 -3.6,1 '
            f'L-3.6,-2.2 Z" fill="{c}" stroke="{LINE}" stroke-width=".9"/>')


def _emblem_map(c):
    return (f'<path d="M-4,-2.6 L-1.2,-3.6 L1.2,-2.2 L4,-3.2 L4,2.8 L1.2,3.8 '
            f'L-1.2,2.4 L-4,3.4 Z" fill="{c}" stroke="{LINE}" stroke-width=".8"/>')


def _emblem_masks(c):
    return (f'<circle cx="-1.6" cy="0" r="3" fill="{c}" stroke="{LINE}" stroke-width=".8"/>'
            f'<circle cx="1.8" cy="0.6" r="2.6" fill="{WALL}" stroke="{LINE}" '
            f'stroke-width=".8" opacity=".95"/>')


def _emblem_paw(c):
    return (f'<ellipse cx="0" cy="1.4" rx="3" ry="2.4" fill="{c}"/>'
            f'<circle cx="-2.4" cy="-1.8" r="1.2" fill="{c}"/>'
            f'<circle cx="0" cy="-2.6" r="1.2" fill="{c}"/>'
            f'<circle cx="2.4" cy="-1.8" r="1.2" fill="{c}"/>')


def _emblem_frame(c):
    return (f'<rect x="-3.8" y="-3" width="7.6" height="6.2" rx=".6" fill="{WALL}" '
            f'stroke="{LINE}" stroke-width=".9"/>'
            f'<path d="M-3,2 L-0.6,-1 L1,0.8 L2.4,-0.6 L3,2 Z" fill="{c}"/>')


def _emblem_bread(c):
    return (f'<path d="M-4,2.2 Q-4,-3 0,-3 Q4,-3 4,2.2 Z" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".9"/>'
            f'<path d="M-1.6,-2.4 L-2.4,1.6 M0.6,-2.6 L0,1.8" stroke="{LINE}" '
            f'stroke-width=".6" fill="none"/>')


def _emblem_gear(c):
    spokes = "".join(
        f'<rect x="-.8" y="-4.4" width="1.6" height="2.2" fill="{c}" '
        f'transform="rotate({a})"/>' for a in range(0, 360, 45))
    return (spokes + f'<circle cx="0" cy="0" r="2.8" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".8"/><circle cx="0" cy="0" r="1" fill="{WALL}"/>')


def _emblem_dove(c):
    return (f'<path d="M-3.6,1.4 Q-1,-2.6 3.2,-2.2 Q1.6,1.6 -1,2.2 Z" fill="{c}" '
            f'stroke="{LINE}" stroke-width=".7"/>'
            f'<path d="M-1,-0.6 Q0.6,-3.4 2.6,-3.6" fill="none" stroke="{LINE}" '
            f'stroke-width=".7"/>')


def _emblem_bottle(c):
    return (f'<path d="M-1.2,-4 L1.2,-4 L1.2,-1.6 Q2.6,-0.6 2.6,1 L2.6,3.4 '
            f'L-2.6,3.4 L-2.6,1 Q-2.6,-0.6 -1.2,-1.6 Z" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".8"/>')


def _emblem_scales(c):
    return (f'<line x1="0" y1="-3.6" x2="0" y2="3.2" stroke="{LINE}" stroke-width="1"/>'
            f'<line x1="-3.6" y1="-2.4" x2="3.6" y2="-2.4" stroke="{LINE}" stroke-width="1"/>'
            f'<path d="M-5,-2.4 L-2.2,-2.4 L-3.6,0.6 Z" fill="{c}"/>'
            f'<path d="M2.2,-2.4 L5,-2.4 L3.6,0.6 Z" fill="{c}"/>')


def _emblem_door(c):
    return (f'<path d="M-2.8,3.4 L-2.8,-1.4 A2.8,2.8 0 0 1 2.8,-1.4 L2.8,3.4 Z" '
            f'fill="{c}" stroke="{LINE}" stroke-width=".9"/>'
            f'<circle cx="1.4" cy="1.2" r=".7" fill="{WALL}"/>')


def _emblem_monument(c):
    return (f'<path d="M-2,3.4 L-1,-3.6 L1,-3.6 L2,3.4 Z" fill="{c}" stroke="{LINE}" '
            f'stroke-width=".8"/>'
            f'<rect x="-3.2" y="3.2" width="6.4" height="1.4" fill="{c}" '
            f'stroke="{LINE}" stroke-width=".7"/>')


def _emblem_gamepad(c):
    return (f'<rect x="-4.2" y="-2.2" width="8.4" height="4.6" rx="2.2" fill="{c}" '
            f'stroke="{LINE}" stroke-width=".8"/>'
            f'<circle cx="2" cy="0" r=".9" fill="{WALL}"/>'
            f'<rect x="-3" y="-.6" width="2.4" height=".9" fill="{WALL}"/>')


EMBLEMS = {
    "mug": _emblem_mug, "book": _emblem_book, "shield": _emblem_shield,
    "map": _emblem_map, "masks": _emblem_masks, "paw": _emblem_paw,
    "image": _emblem_frame, "camera": _emblem_frame, "bread": _emblem_bread,
    "gear": _emblem_gear, "dove": _emblem_dove, "bottle": _emblem_bottle,
    "scales": _emblem_scales, "door": _emblem_door,
    "monument": _emblem_monument, "gamepad": _emblem_gamepad,
}
# Kept as the panel's vocabulary so a building can be given any of them.
GLYPHS = EMBLEMS


def _person(c="#5b4630"):
    """Somebody, at map scale. A head and a coat is all that survives."""
    return (f'<circle cx="0" cy="-2.6" r="1.5" fill="{c}"/>'
            f'<path d="M-1.8,2.6 Q-1.8,-1.2 0,-1.2 Q1.8,-1.2 1.8,2.6 Z" fill="{c}"/>')


def _beast(c="#5b4630"):
    """A four-legged thing: body, head, tail, legs."""
    return (f'<ellipse cx="0" cy="0" rx="2.6" ry="1.5" fill="{c}"/>'
            f'<circle cx="2.4" cy="-1.2" r="1.1" fill="{c}"/>'
            f'<path d="M-2.4,-0.6 Q-4,-1.8 -3.4,-2.8" fill="none" stroke="{c}" '
            f'stroke-width=".8"/>'
            f'<path d="M-1.4,1.2 L-1.4,2.6 M1.2,1.2 L1.2,2.6" stroke="{c}" '
            f'stroke-width=".9"/>')


def _bird(c="#5b4630"):
    """Two arcs. Every child draws a bird this way and everybody reads it."""
    return (f'<path d="M-3,0 Q-1.5,-2 0,0 Q1.5,-2 3,0" fill="none" stroke="{c}" '
            f'stroke-width="1"/>')


WANDERERS = {"person": _person, "beast": _beast, "bird": _bird}

# Who wanders where, once there is something for them to wander around.
LIFE = {
    "pen": ("beast", "beast", "bird"),
    "inn": ("person", "person"),
    "stage": ("person", "person"),
    "works": ("person",),
    "hall": ("person",),
    "keep": ("person",),
    "chapel": ("bird", "person"),
    "monument": ("person",),
    "gate": ("person",),
}


def glyph(name: str) -> str:
    """Whether an emblem by this name exists. Kept for validation."""
    return name if name in EMBLEMS else ""


def _symbol(x, y, name, size=7.0, colour=LINE, extra="") -> str:
    """One emblem, drawn at a point and scaled to roughly ``size`` across."""
    draw = EMBLEMS.get(str(name or ""))
    if draw is None:
        return ""
    scale = size / 8.0
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({scale:.2f})"'
            f'{extra}>{draw(colour)}</g>')


def _fx(body: str) -> str:
    """Wrap a close-up flourish.

    Effects are hidden until the map is zoomed in far enough to see them.
    At map scale they would be noise on three hundred towns at once; up close
    they are the reward for having built the thing. The gate is one CSS class on
    the world, so nothing here has to know about zoom.
    """
    return f'<g class="fx">{body}</g>'


def _smoke(x, y) -> str:
    """Three puffs rising from a chimney. Only ever seen close up."""
    return _fx(
        f'<circle class="pf1" cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#fff" opacity=".55"/>'
        f'<circle class="pf2" cx="{x + 1:.1f}" cy="{y - 5:.1f}" r="2.8" fill="#fff" opacity=".4"/>'
        f'<circle class="pf3" cx="{x - 1:.1f}" cy="{y - 10:.1f}" r="3.2" fill="#fff" opacity=".25"/>'
    )


def _lit_window(x, y, w=3.6, h=3.6) -> str:
    """A window with a light behind it."""
    return (_rect(x, y, w, h, fill=GLASS, width=0.7)
            + _fx(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                  f'fill="#ffd98a" class="glow"/>'))


def _flag(x, y, colour, height=11.0) -> str:
    return (f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y - height:.1f}" '
            f'stroke="{LINE}" stroke-width="1.2"/>'
            f'<polygon class="banner" points="{x:.1f},{y - height:.1f} '
            f'{x + 8:.1f},{y - height + 3:.1f} {x:.1f},{y - height + 6:.1f}" '
            f'fill="{colour}"/>')


# --------------------------------------------------------------------------- #
#  The shape families
# --------------------------------------------------------------------------- #
# Each takes the centre x, the ground line, a tier 1-6 and a colour, and returns
# a fragment. They are written to be told apart in silhouette alone.

def _inn(x, base, tier, colour) -> str:
    """Wide and low, with an awning and a hanging sign. Taverns and bakeries."""
    w, h = 14 + tier * 3.0, 8 + tier * 2.8
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h), _tri(left - 2, top, x, top - h * 0.4, left + w + 2, top, colour)]
    # A striped awning across the front: the thing that says "come in".
    out.append(_rect(left, base - 4.5, w, 3, fill=colour, width=0.9, rx=0.4))
    for i in range(int(w // 4)):
        out.append(f'<rect x="{left + i * 4:.1f}" y="{base - 4.5:.1f}" width="2" '
                   f'height="3" fill="{WALL}" opacity=".65"/>')
    out.append(_door(x, base, arch=False))
    if tier >= 2:  # a barrel outside
        out.append(f'<ellipse cx="{left - 3:.1f}" cy="{base - 2:.1f}" rx="2.6" ry="3.4" '
                   f'fill="#a0713d" stroke="{LINE}" stroke-width=".8"/>')
    if tier >= 3:  # the hanging sign
        out.append(f'<line x1="{left + w:.1f}" y1="{top + 3:.1f}" x2="{left + w + 6:.1f}" '
                   f'y2="{top + 3:.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(_rect(left + w + 3, top + 3, 5, 5, fill=colour, width=0.9))
    if tier >= 4:
        cx = left + w * 0.66
        out.append(_rect(cx, top - h * 0.4 - 5, 3.4, 6, fill="#6b4a30",
                         stroke=LINE, width=0.9))
        out.append(_smoke(cx + 1.7, top - h * 0.4 - 8))
    if tier >= 5:  # upper floor windows, lit
        for wx in (x - 6, x + 2.5):
            out.append(_lit_window(wx, top + 3))
    if tier >= 6:
        out.append(_flag(x, top - h * 0.4, colour))
    return "".join(out)


def _hall(x, base, tier, colour) -> str:
    """Columns and a pediment. Libraries, galleries, moot halls."""
    w, h = 13 + tier * 2.8, 9 + tier * 3.4
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h, fill=WALL_DARK)]
    # Columns: the classical tell, visible even as a smudge.
    count = 2 + min(4, tier)
    gap = w / (count + 1)
    for i in range(count):
        cx = left + gap * (i + 1)
        out.append(_rect(cx - 1.2, top + 2, 2.4, h - 2, fill=WALL, width=0.7, rx=0.3))
    out.append(_tri(left - 3, top + 2, x, top - h * 0.36, left + w + 3, top + 2, colour))
    out.append(_door(x, base, w=4.4, h=6.5, arch=tier >= 3))
    if tier >= 4:  # steps
        out.append(_rect(left - 2, base - 1.6, w + 4, 1.8, fill=WALL_DARK, width=0.8, rx=0.3))
    if tier >= 5:  # a dome behind the pediment
        r = w * 0.3
        out.insert(0, f'<path d="M{x - r:.1f},{top:.1f} A{r:.1f},{r:.1f} 0 0 1 '
                      f'{x + r:.1f},{top:.1f} Z" fill="{colour}" stroke="{LINE}" '
                      f'stroke-width="1"/>')
    if tier >= 6:
        out.append(f'<circle cx="{x:.1f}" cy="{top - h * 0.36 - 4:.1f}" r="3" '
                   f'fill="{colour}" stroke="{LINE}" stroke-width="1"/>')
    return "".join(out)


def _keep(x, base, tier, colour) -> str:
    """Squat and fortified, with battlements. Barracks, war rooms, cellars."""
    w, h = 13 + tier * 2.4, 9 + tier * 3.0
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h, fill=WALL_DARK)]
    # Crenellations: the tell. Teeth along the top rather than a roof at all.
    teeth = 3 + min(4, tier)
    tw = w / (teeth * 2 - 1)
    for i in range(teeth):
        out.append(_rect(left + i * tw * 2, top - 3, tw, 3.4, fill=WALL_DARK, width=0.9, rx=0.2))
    out.append(_door(x, base, w=4.4, h=6.5, arch=True))
    for i in range(min(3, tier)):  # arrow slits
        out.append(_rect(left + w * (0.22 + i * 0.28), top + 4, 1.6, 4.5,
                         fill=LINE, stroke="none", width=0, rx=0.4))
    if tier >= 3:  # a corner tower
        th = h * 0.85 + 4
        out.insert(0, _rect(left - 6, base - th, 6.4, th, fill=WALL))
        out.insert(1, _tri(left - 7.4, base - th, left - 2.8, base - th - 7,
                           left + 0.4, base - th, colour))
    if tier >= 5:  # a second one, the other side
        th = h * 0.7 + 4
        out.insert(0, _rect(left + w - 0.4, base - th, 6.4, th, fill=WALL))
        out.insert(1, _tri(left + w - 1.8, base - th, left + w + 2.8, base - th - 7,
                           left + w + 6.8, base - th, colour))
    if tier >= 6:
        out.append(_flag(x, top - 3, colour))
    return "".join(out)


def _chapel(x, base, tier, colour) -> str:
    """Tall, narrow, a steep spire and a round window. Shrines and sanctuaries."""
    w, h = 9 + tier * 1.8, 10 + tier * 3.6
    left, top = x - w / 2, base - h
    spire = 8 + tier * 3.0
    out = [
        _rect(left, top, w, h),
        _tri(left - 2, top, x, top - spire, left + w + 2, top, colour),
        _door(x, base, w=4, h=7, arch=True),
    ]
    if tier >= 2:  # the rose window, lit from within
        r = 2 + tier * 0.35
        out.append(f'<circle cx="{x:.1f}" cy="{top + 5:.1f}" r="{r:.1f}" '
                   f'fill="{GLASS}" stroke="{LINE}" stroke-width=".9"/>')
        if tier >= 4:
            out.append(_fx(f'<circle cx="{x:.1f}" cy="{top + 5:.1f}" r="{r:.1f}" '
                           f'fill="#ffd98a" class="glow"/>'))
    if tier >= 4:  # a bell tower alongside
        th = h + spire * 0.5
        out.insert(0, _rect(left - 6.5, base - th, 6.5, th, fill=WALL_DARK))
        out.insert(1, _tri(left - 8, base - th, left - 3.2, base - th - 9,
                           left + 0.5, base - th, colour))
    if tier >= 6:  # a cross on the spire
        out.append(f'<line x1="{x:.1f}" y1="{top - spire:.1f}" x2="{x:.1f}" '
                   f'y2="{top - spire - 7:.1f}" stroke="{LINE}" stroke-width="1.4"/>')
        out.append(f'<line x1="{x - 3:.1f}" y1="{top - spire - 4:.1f}" x2="{x + 3:.1f}" '
                   f'y2="{top - spire - 4:.1f}" stroke="{LINE}" stroke-width="1.4"/>')
    return "".join(out)


def _pen(x, base, tier, colour) -> str:
    """A fenced enclosure with a shelter and a tree. Menageries and gardens."""
    w = 16 + tier * 3.2
    left = x - w / 2
    out = []
    # Fence first: it is the whole silhouette at small sizes.
    posts = 4 + min(5, tier)
    for i in range(posts):
        px = left + (w / (posts - 1)) * i
        out.append(_rect(px - 0.8, base - 7, 1.6, 7, fill="#a0713d", width=0.7, rx=0.2))
    out.append(f'<line x1="{left:.1f}" y1="{base - 5:.1f}" x2="{left + w:.1f}" '
               f'y2="{base - 5:.1f}" stroke="#a0713d" stroke-width="1.4"/>')
    # A shelter in the corner.
    sh = 6 + tier * 1.6
    out.append(_rect(left + 1, base - sh, 9, sh, fill=WALL))
    out.append(_tri(left - 0.6, base - sh, left + 5.5, base - sh - 5,
                    left + 11.6, base - sh, colour))
    if tier >= 2:  # a tree
        out.append(f'<rect x="{left + w - 6:.1f}" y="{base - 7:.1f}" width="2" '
                   f'height="7" fill="#7a5233"/>')
        out.append(f'<circle cx="{left + w - 5:.1f}" cy="{base - 9:.1f}" '
                   f'r="{3.5 + tier * 0.5:.1f}" fill="#3f8f5e" stroke="{LINE}" '
                   f'stroke-width=".9"/>')
    if tier >= 4:  # a pond
        out.append(f'<ellipse cx="{x + 2:.1f}" cy="{base - 2.5:.1f}" rx="{4 + tier:.1f}" '
                   f'ry="2.6" fill="{GLASS}" stroke="{LINE}" stroke-width=".8"/>')
    if tier >= 5:  # an aviary dome
        r = 6 + tier
        out.append(f'<path d="M{x - r:.1f},{base:.1f} A{r:.1f},{r:.1f} 0 0 1 '
                   f'{x + r:.1f},{base:.1f}" fill="none" stroke="{LINE}" stroke-width="1.1"/>')
        out.append(f'<line x1="{x:.1f}" y1="{base:.1f}" x2="{x:.1f}" y2="{base - r:.1f}" '
                   f'stroke="{LINE}" stroke-width=".7" opacity=".7"/>')
    return "".join(out)


def _works(x, base, tier, colour) -> str:
    """Saw-tooth roof, a stack, a wheel. Forges and workshops."""
    w, h = 14 + tier * 2.6, 8 + tier * 2.6
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h, fill=WALL_DARK)]
    # Saw-tooth roofline: unmistakable, and it is the whole tell.
    teeth = 2 + min(4, tier)
    tw = w / teeth
    for i in range(teeth):
        tx = left + i * tw
        out.append(f'<polygon points="{tx:.1f},{top:.1f} {tx:.1f},{top - 4.5:.1f} '
                   f'{tx + tw:.1f},{top:.1f}" fill="{colour}" stroke="{LINE}" '
                   f'stroke-width=".9" stroke-linejoin="round"/>')
    # The chimney stack.
    out.append(_rect(left + w - 5, top - 6 - tier * 1.6, 4, 7 + tier * 1.6,
                     fill="#6b4a30", width=0.9))
    out.append(_door(x - 2, base, w=5, h=6.5))
    if tier >= 3:  # a water wheel
        r = 4 + tier * 0.7
        out.append(f'<circle cx="{left - 3:.1f}" cy="{base - r:.1f}" r="{r:.1f}" '
                   f'fill="none" stroke="{LINE}" stroke-width="1.2"/>')
        for i in range(4):
            import math
            a = i * math.pi / 4
            out.append(f'<line x1="{left - 3 - r * math.cos(a):.1f}" '
                       f'y1="{base - r - r * math.sin(a):.1f}" '
                       f'x2="{left - 3 + r * math.cos(a):.1f}" '
                       f'y2="{base - r + r * math.sin(a):.1f}" '
                       f'stroke="{LINE}" stroke-width=".7"/>')
    if tier >= 5:  # a forge, glowing and smoking
        out.append(f'<rect x="{x + 3:.1f}" y="{base - 5:.1f}" width="4" height="5" '
                   f'fill="#ff9a3c" stroke="{LINE}" stroke-width=".8"/>')
        out.append(_fx(f'<rect x="{x + 3:.1f}" y="{base - 5:.1f}" width="4" height="5" '
                       f'fill="#ffd98a" class="glow"/>'))
    if tier >= 4:
        out.append(_smoke(left + w - 3, top - 8 - tier * 1.6))
    return "".join(out)


def _stage(x, base, tier, colour) -> str:
    """A proscenium arch with curtains. Playhouses and arenas."""
    w, h = 14 + tier * 3.0, 10 + tier * 3.0
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h, fill=WALL_DARK)]
    # The arch: a big opening rather than a door, which is the tell.
    aw, ah = w * 0.6, h * 0.66
    out.append(f'<path d="M{x - aw / 2:.1f},{base:.1f} L{x - aw / 2:.1f},'
               f'{base - ah * 0.55:.1f} A{aw / 2:.1f},{aw / 2:.1f} 0 0 1 '
               f'{x + aw / 2:.1f},{base - ah * 0.55:.1f} L{x + aw / 2:.1f},{base:.1f} Z" '
               f'fill="#2a1c12" stroke="{LINE}" stroke-width="1.1"/>')
    if tier >= 2:  # curtains
        out.append(f'<path d="M{x - aw / 2:.1f},{base:.1f} L{x - aw / 2:.1f},'
                   f'{base - ah * 0.8:.1f} Q{x - aw * 0.25:.1f},{base - ah * 0.4:.1f} '
                   f'{x - aw * 0.22:.1f},{base:.1f} Z" fill="{colour}"/>')
        out.append(f'<path d="M{x + aw / 2:.1f},{base:.1f} L{x + aw / 2:.1f},'
                   f'{base - ah * 0.8:.1f} Q{x + aw * 0.25:.1f},{base - ah * 0.4:.1f} '
                   f'{x + aw * 0.22:.1f},{base:.1f} Z" fill="{colour}"/>')
    out.append(_rect(left - 2, top - 3.5, w + 4, 3.8, fill=colour, width=1))
    if tier >= 4:  # tiers of seating either side
        for i in range(min(3, tier - 2)):
            out.append(_rect(left - 3 - i * 2, base - 3 - i * 2.4, 3, 3 + i * 2.4,
                             fill=WALL, width=0.8))
            out.append(_rect(left + w + i * 2, base - 3 - i * 2.4, 3, 3 + i * 2.4,
                             fill=WALL, width=0.8))
    if tier >= 6:
        out.append(_flag(x, top - 3.5, colour))
    return "".join(out)


def _monument(x, base, tier, colour) -> str:
    """A stepped plinth and a rising figure. Statues and landmarks."""
    steps = 1 + min(3, tier)
    out = []
    for i in range(steps):
        sw = 20 - i * 3.5
        out.append(_rect(x - sw / 2, base - 2.2 * (i + 1), sw, 2.4, fill=WALL_DARK, width=0.9))
    top = base - 2.2 * steps
    ch = 8 + tier * 3.4
    out.append(_rect(x - 2.6, top - ch, 5.2, ch, fill=WALL, width=1))
    if tier >= 2:
        out.append(f'<circle cx="{x:.1f}" cy="{top - ch - 3:.1f}" r="3.2" '
                   f'fill="{colour}" stroke="{LINE}" stroke-width="1"/>')
    if tier >= 4:  # a figure, sketched
        out.append(f'<circle cx="{x:.1f}" cy="{top - ch - 7:.1f}" r="2.4" '
                   f'fill="{WALL}" stroke="{LINE}" stroke-width=".9"/>')
        out.append(f'<path d="M{x - 3:.1f},{top - ch - 2:.1f} L{x:.1f},'
                   f'{top - ch - 5:.1f} L{x + 3:.1f},{top - ch - 2:.1f}" fill="none" '
                   f'stroke="{LINE}" stroke-width="1.1"/>')
    if tier >= 6:  # a halo, because the top of a ladder should be obvious
        out.append(f'<circle cx="{x:.1f}" cy="{top - ch - 7:.1f}" r="6.5" fill="none" '
                   f'stroke="{colour}" stroke-width="1.4" opacity=".9"/>')
    return "".join(out)


def _gate(x, base, tier, colour) -> str:
    """A free-standing arch. Wayshrines and thresholds."""
    w = 12 + tier * 2.4
    h = 12 + tier * 3.2
    out = [
        _rect(x - w / 2, base - h, 4.2, h, fill=WALL_DARK),
        _rect(x + w / 2 - 4.2, base - h, 4.2, h, fill=WALL_DARK),
        f'<path d="M{x - w / 2 + 4.2:.1f},{base - h * 0.55:.1f} '
        f'A{(w - 8.4) / 2:.1f},{(w - 8.4) / 2:.1f} 0 0 1 '
        f'{x + w / 2 - 4.2:.1f},{base - h * 0.55:.1f}" fill="none" stroke="{LINE}" '
        f'stroke-width="1.4"/>',
        _rect(x - w / 2 - 1.5, base - h - 3.4, w + 3, 3.6, fill=colour, width=1),
    ]
    if tier >= 3:
        out.append(f'<circle cx="{x:.1f}" cy="{base - h - 6:.1f}" r="2.6" '
                   f'fill="{colour}" stroke="{LINE}" stroke-width=".9"/>')
    if tier >= 5:  # lanterns on the posts
        for lx in (x - w / 2 + 2.1, x + w / 2 - 2.1):
            out.append(f'<circle cx="{lx:.1f}" cy="{base - h + 4:.1f}" r="2" '
                       f'fill="#ffd27f" stroke="{LINE}" stroke-width=".8"/>')
            out.append(_fx(f'<circle cx="{lx:.1f}" cy="{base - h + 4:.1f}" r="3.4" '
                           f'fill="#ffd27f" class="halo"/>'))
    if tier >= 6:
        out.append(_flag(x, base - h - 3.4, colour))
    return "".join(out)


SHAPES = {
    "inn": _inn, "hall": _hall, "keep": _keep, "chapel": _chapel,
    "pen": _pen, "works": _works, "stage": _stage, "monument": _monument,
    "gate": _gate,
}
SHAPE_LABELS = {
    "inn": "Inn — wide, awning, hanging sign",
    "hall": "Hall — columns and a pediment",
    "keep": "Keep — battlements and towers",
    "chapel": "Chapel — tall, spire, rose window",
    "pen": "Enclosure — fence, shelter, tree",
    "works": "Workshop — saw-tooth roof and a stack",
    "stage": "Playhouse — an arch and curtains",
    "monument": "Monument — a plinth and a figure",
    "gate": "Gate — a free-standing arch",
}
DEFAULT_SHAPE = "inn"


# Where the buildings stand on the plate, as (depth, sideways) pairs.
#
# Depth runs 0 at the back to 1 at the front. A building further back is drawn
# higher up, smaller, and earlier, so the ones in front overlap it: that is the
# whole trick, and it is what turns a row of houses into a village with a
# middle. Sideways is a fraction of the plate's half-width at that depth, so
# nothing stands off the edge of its own ground.
#
# The order is deliberate rather than random: the grandest building lands
# centre and slightly back, where a keep or a cathedral belongs, and the rest
# fan out around it. Fixed rather than seeded so a town does not rearrange
# itself between two page loads.
_PLOTS = (
    (0.34,  0.00),   # the centrepiece
    (0.78, -0.52),   # front left
    (0.16,  0.46),   # back right
    (0.92,  0.20),   # front, nearest
    (0.50, -0.82),   # far left, mid
    (0.06, -0.28),   # back left
    (0.68,  0.80),   # right, forward
)


def _stand(depth: float) -> tuple[float, float, float]:
    """Ground line, half-width and scale at a depth on the plate.

    Everything about perspective here is linear and shallow on purpose. This is
    a map pictogram, not a render: enough depth to read as a place, not enough
    to look like it is falling over.
    """
    y = GROUND_Y - 5.0 + depth * 11.0
    half = WIDTH * 0.40 * (0.55 + 0.45 * depth)
    scale = 0.70 + 0.30 * depth
    return y, half, scale


def _defs(uid: str, colour: str) -> str:
    """Gradients this town's effects draw with.

    SVG gradients rather than CSS filters, deliberately: a filter inside the
    zoomed world rasterises whatever it touches, and the grandest buildings were
    the first to turn to mush when that was tried. A gradient stays vector at
    every zoom, which is the only way the top of the ladder can look like the
    top of the ladder.
    """
    return (
        f'<defs>'
        f'<radialGradient id="au{uid}">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity=".85"/>'
        f'<stop offset="55%" stop-color="{colour}" stop-opacity=".28"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<linearGradient id="bm{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity="0"/>'
        f'<stop offset="45%" stop-color="{colour}" stop-opacity=".55"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        f'</linearGradient>'
        f'</defs>'
    )


def _tier_effects(tier: int, colour: str, uid: str) -> tuple[str, str]:
    """What a building gains for being grand. Returns (behind, in front).

    The original design had thirty tiers of escalating spectacle and was right
    to: a ladder whose top rung looks like its bottom rung is not worth
    climbing. What was wrong with it was the arithmetic — it asked one person
    for 125,000 acts on a server whose entire history is 306,927 messages — and
    the thresholds here are derived from the server's own distribution instead,
    so the top of this ladder is genuinely reachable. Having fixed the numbers
    there is no reason left to be timid about the spectacle.

    Effects stack rather than replace, so the climb reads as a climb:

      4  the ground warms under it
      5  it lifts off the ground, embers rise, an aura settles over it
      6  it hovers over its own shadow, wrapped in a ring of light with motes
         going round it and a beam standing over the whole thing

    Opacity, transform and gradients only. A CSS filter in here would rasterise
    the building it touches.
    """
    tier = max(1, min(6, int(tier)))
    behind, front = "", ""

    if tier >= 4:  # the ground warms
        behind += _fx(f'<ellipse class="bglow" cx="0" cy="-1" rx="{12 + tier * 2.4:.0f}" '
                      f'ry="{6 + tier:.0f}" fill="url(#au{uid})"/>')

    if tier >= 5:  # an aura, and embers off the roof
        behind += _fx(f'<circle class="baura" cx="0" cy="{-12 - tier * 2:.0f}" '
                      f'r="{16 + tier * 2:.0f}" fill="url(#au{uid})" opacity=".5"/>')
        for i in range(4):
            front += _fx(f'<circle class="spark s{i + 1}" cx="{-6 + i * 4}" '
                         f'cy="{-14 - tier * 3}" r="{1.2 + i * 0.2:.1f}" fill="{colour}"/>')

    if tier == 6:  # it leaves the ground
        # A shadow where it used to stand, and the building itself lifted: the
        # single clearest way to say "this is the top" without a label.
        behind += _fx(f'<ellipse class="bshadow" cx="0" cy="2" rx="14" ry="4" '
                      f'fill="#2a1c12" opacity=".45"/>')
        behind += _fx(f'<rect class="bbeam" x="-5" y="-92" width="10" height="92" '
                      f'fill="url(#bm{uid})"/>')
        behind += _fx(f'<ellipse class="bring" cx="0" cy="{-16 - tier * 2:.0f}" '
                      f'rx="{20 + tier:.0f}" ry="7" fill="none" stroke="{colour}" '
                      f'stroke-width="1.3" opacity=".7"/>')
        front += _fx(f'<g class="orbit">'
                     f'<circle cx="{20 + tier:.0f}" cy="{-16 - tier * 2:.0f}" r="2" '
                     f'fill="{colour}"/>'
                     f'<circle cx="{-(20 + tier):.0f}" cy="{-16 - tier * 2:.0f}" r="1.5" '
                     f'fill="{colour}" opacity=".8"/></g>')
    return behind, front


def _life(rows: list[dict], shapes: dict) -> str:
    """Creatures and people wandering the town, seen only up close.

    Drawn from what actually stands there: a menagerie brings animals, an inn
    brings drinkers, a chapel brings birds. A town with a zoo in it and nothing
    moving is a shed with a fence around it.
    """
    out = ""
    spots = ((0.22, 0.88), (0.72, 0.93), (0.42, 0.97), (0.85, 0.84),
             (0.12, 0.80), (0.60, 0.86))
    index = 0
    for row in rows:
        family = shapes.get(str(row.get("key") or "")) or DEFAULT_SHAPE
        pool = LIFE.get(family) or ()
        # One wanderer per building, two once it is grand enough to draw a crowd.
        for step in range(1 if int(row.get("tier", 1)) < 4 else 2):
            if index >= len(spots) or not pool:
                break
            fx, fy = spots[index]
            name = pool[(index + step) % len(pool)]
            # Not wrapped in the close-up gate: a town's inhabitants are part
            # of the town. Only their walking waits for close range, which is a
            # CSS animation, not a display rule.
            draw = WANDERERS.get(name) or _person
            out += (f'<g class="walker w{index % 3 + 1}" '
                    f'transform="translate({WIDTH * fx:.1f},{HEIGHT * fy:.1f})">'
                    + draw() + '</g>')
            index += 1
    return out


def banner(url: str, uid: str) -> str:
    """A town's own picture, flying as a flag over it.

    A picture sitting in a card is a picture. A picture on a pole above your
    town, rippling, is a thing somebody made and put up where everybody can see
    it, which is the entire point of letting people upload one.

    The ripple is a repeating skew on the cloth alone; the pole stays still.
    Clipped to the flag's shape so any aspect ratio looks like cloth rather than
    a photograph nailed to a stick.
    """
    if not url:
        return ""
    return (
        f'<g class="townflag">'
        f'<defs><clipPath id="fg{uid}">'
        f'<path d="M0,-34 L26,-30 L26,-14 L0,-18 Z"/></clipPath></defs>'
        f'<line x1="0" y1="2" x2="0" y2="-36" stroke="{LINE}" stroke-width="1.6"/>'
        f'<circle cx="0" cy="-36.6" r="1.6" fill="{LINE}"/>'
        f'<g class="cloth">'
        f'<image href="{url}" x="0" y="-34" width="26" height="20" '
        f'preserveAspectRatio="xMidYMid slice" clip-path="url(#fg{uid})"/>'
        f'<path d="M0,-34 L26,-30 L26,-14 L0,-18 Z" fill="none" stroke="{LINE}" '
        f'stroke-width="1.1"/></g></g>'
    )


def town_svg(buildings: Iterable[dict], *, lit: bool = True,
             flourish: int = 0, glow: str = "", richness: float = 0.0,
             uid: str = "t", flag: str = "", shapes: Optional[dict] = None,
             symbols: Optional[dict] = None,
             colours: Optional[dict] = None) -> str:
    """A whole settlement as an SVG fragment.

    ``buildings`` are ``{"key", "tier"}`` in any order. The grandest stands
    centre and slightly back and the rest are spread across the plate, drawn
    back to front so the near ones overlap the far ones. A town with nothing
    built is a single tent, not an empty patch: somebody who has just arrived
    should still be somewhere.
    """
    rows = sorted(buildings, key=lambda b: -int(b.get("tier", 1)))[:MAX_BUILDINGS]
    shapes = shapes or {}
    colours = colours or {}
    # Gradient ids must be unique per town or every town on the map shares one
    # set and they all take the colour of whichever drew last.
    uid = "".join(c for c in str(uid) if c.isalnum()) or "t"

    parts = [
        _defs(uid, glow or "#ffd27f"),
        f'<ellipse cx="{WIDTH / 2:.1f}" cy="{GROUND_Y + 6:.1f}" rx="{WIDTH * 0.47:.1f}" '
        f'ry="10" fill="#cdb894" stroke="#a68f6a" stroke-width="1.4"/>',
        f'<ellipse cx="{WIDTH / 2:.1f}" cy="{GROUND_Y + 5:.1f}" rx="{WIDTH * 0.43:.1f}" '
        f'ry="8" fill="#ddcaa6"/>',
    ]

    if not rows:
        cx = WIDTH / 2
        parts.append(_tri(cx - 9, GROUND_Y + 2, cx, GROUND_Y - 13, cx + 9,
                          GROUND_Y + 2, "#b98b4e"))
    else:
        standing = []
        for index, row in enumerate(rows):
            depth, sideways = _PLOTS[index % len(_PLOTS)]
            y, half, scale = _stand(depth)
            standing.append((y, WIDTH / 2 + sideways * half, scale, row))
        # Painter's algorithm: the far ones first, so the near ones cover them.
        standing.sort(key=lambda item: item[0])
        for y, x, scale, row in standing:
            key = str(row.get("key") or "")
            draw = SHAPES.get(shapes.get(key) or DEFAULT_SHAPE, _inn)
            tier = int(row.get("tier", 1))
            tint = colours.get(key) or colour_for(key)
            behind, front = _tier_effects(tier, tint, uid)
            mass = draw(0.0, 0.0, tier, tint)
            if tier == 6:
                # Detached from the ground, hovering over the shadow drawn for
                # it. Straight out of the original design, and the thing that
                # makes somebody ask how a town got like that.
                mass = f'<g class="lifted">{mass}</g>'
            art = behind + mass + front
            # The building's emblem, hung above it: what the place is *for*,
            # where the masonry only says what kind of place it is.
            mark = (symbols or {}).get(key)
            if mark:
                art += _symbol(0, -(12 + tier * 3.6), mark,
                               size=6.5 + tier * 0.5, colour=tint,
                               extra=f' class="emblem e{min(6, tier)}"')
            # Drawn at the origin and moved into place, so one transform carries
            # both where it stands and how near it is.
            parts.append(f'<g transform="translate({x:.1f},{y:.1f}) '
                         f'scale({scale:.2f})">{art}</g>')

    if rows:
        parts.append(_life(rows, shapes))
    if flag:
        # Planted at the front-left of the plate, where it does not stand in
        # front of the buildings it belongs to.
        parts.append(f'<g transform="translate({WIDTH * 0.12:.1f},'
                     f'{GROUND_Y + 2:.1f})">{banner(flag, uid)}</g>')
    body = "".join(parts)
    if flourish:
        level = min(6, int(flourish))
        # The rank's own colour where the server has one, so a Legend glows the
        # colour a Legend already is in the member list. An invented palette
        # made every high rank lilac and told nobody anything.
        ring = glow or "#ffd27f"
        rings = f'<ellipse class="flring" cx="{WIDTH / 2:.1f}" cy="{GROUND_Y + 6:.1f}" '                 f'rx="{WIDTH * 0.51:.1f}" ry="12" fill="none" stroke="{ring}" '                 f'stroke-width="{1 + level * 0.6:.1f}" opacity=".9"/>'
        if level >= 4:  # a second, wider ring: rank should be visible at a glance
            rings = (f'<ellipse class="flring2" cx="{WIDTH / 2:.1f}" '
                     f'cy="{GROUND_Y + 6:.1f}" rx="{WIDTH * 0.56:.1f}" ry="14" '
                     f'fill="none" stroke="{ring}" stroke-width="{level * 0.4:.1f}" '
                     f'opacity=".45"/>') + rings
        if level >= 5:  # motes of light over the town, close up only
            for i, (mx, my) in enumerate(((0.3, 0.2), (0.55, 0.05), (0.75, 0.28))):
                rings += _fx(f'<circle class="mote m{i + 1}" '
                             f'cx="{WIDTH * mx:.1f}" cy="{HEIGHT * my:.1f}" r="2.2" '
                             f'fill="{ring}"/>')
        body = rings + body
    if not lit:
        body = f'<g opacity=".45">{body}</g>'
    return body


def one_svg(shape: str, tier: int, colour: Optional[str] = None) -> str:
    """A single building on its own, for previews and the buildings editor."""
    draw = SHAPES.get(shape or DEFAULT_SHAPE, _inn)
    return draw(WIDTH / 2, GROUND_Y, max(1, min(6, int(tier))), colour or PALETTE[0])
