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


def town_svg(buildings: Iterable[dict], *, lit: bool = True,
             flourish: int = 0, shapes: Optional[dict] = None,
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

    parts = [
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
            art = draw(0.0, 0.0, int(row.get("tier", 1)),
                       colours.get(key) or colour_for(key))
            # Drawn at the origin and moved into place, so one transform carries
            # both where it stands and how near it is.
            parts.append(f'<g transform="translate({x:.1f},{y:.1f}) '
                         f'scale({scale:.2f})">{art}</g>')

    body = "".join(parts)
    if flourish:
        glow = min(6, int(flourish))
        body = (f'<ellipse cx="{WIDTH / 2:.1f}" cy="{GROUND_Y + 6:.1f}" '
                f'rx="{WIDTH * 0.51:.1f}" ry="12" fill="none" '
                f'stroke="var(--fl{glow}, #ffd27f)" stroke-width="{1 + glow * 0.5:.1f}" '
                f'opacity=".85"/>') + body
    if not lit:
        body = f'<g opacity=".45">{body}</g>'
    return body


def one_svg(shape: str, tier: int, colour: Optional[str] = None) -> str:
    """A single building on its own, for previews and the buildings editor."""
    draw = SHAPES.get(shape or DEFAULT_SHAPE, _inn)
    return draw(WIDTH / 2, GROUND_Y, max(1, min(6, int(tier))), colour or PALETTE[0])
