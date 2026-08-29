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
import math
from typing import Iterable, Optional

from helpers.dodoland import faicons

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
# Font Awesome was tried here once as a **webfont**, set as SVG ``<text>`` with a
# ``font-family``. It never rendered: no building had an emblem and the
# inhabitants came out as whatever the fallback font happened to have at those
# codepoints. A webfont inside an SVG fails silently, at a distance, in exactly
# the part people are meant to be looking at, and it fails outright in an
# ``<img>`` and in a fetched fragment, where nothing external is ever loaded.
#
# What is used now is Font Awesome's **artwork**, not its font: every icon is a
# single ``<path>``, vendored into ``helpers/dodoland/faicons.py`` by
# ``tools/vendor_fa_icons.py``. A path has none of that failure mode — no
# network, no loading, no fallback — and it scales with the drawing. The rule in
# ``docs/DODOLAND.md`` stands exactly as written: no webfont, no ``<text>``.
#
# The shapes carry what a building **is** and how far it has come; these carry
# what it is *for*. A keep with a shield on it and a keep with a map on it are
# the barracks and the war room, and no amount of masonry would have said which.

def icon(name: str, size: float = 10.0, colour: str = LINE,
         cx: float = 0.0, cy: float = 0.0, opacity: str = "") -> str:
    """One Font Awesome path, scaled to ``size`` across and centred on (cx, cy).

    Font Awesome draws in its own 512-unit box with the origin at the top left;
    a town is 120 units across. Both transforms are needed and in this order:
    scale first, then shift the icon's own centre onto the target point.
    """
    entry = faicons.ICONS.get(str(name or ""))
    if entry is None:
        return ""
    box, path = entry
    minx, miny, w, h = (float(v) for v in box.replace(",", " ").split())
    scale = size / max(w, h)
    fade = f' opacity="{opacity}"' if opacity else ""
    return (f'<g transform="translate({cx:.2f},{cy:.2f}) scale({scale:.5f}) '
            f'translate({-(minx + w / 2):.1f},{-(miny + h / 2):.1f})">'
            f'<path d="{path}" fill="{colour}"{fade}/></g>')


# The panel's vocabulary of emblems is simply whatever has been vendored, so
# adding an icon to ``tools/vendor_fa_icons.py`` adds it to the picker with
# nothing else to remember. ``EMBLEMS``/``GLYPHS`` keep their old names because
# ``buildings.py`` validates against them and every server's saved choices are
# keys in here.
EMBLEMS = faicons.ICONS
GLYPHS = EMBLEMS


def _emblem(cx: float, cy: float, name: str, size: float, colour: str,
            tier: int = 1) -> str:
    """An emblem as a medallion hung over its building.

    The icon alone was the problem, not the icon: tinted the building's own
    colour, seven units across, floating against a pale plate, it was a smudge
    that took real effort to identify. A disc of the building's colour with the
    icon knocked out of it in cream, ringed in the same dark line as the
    masonry, is legible at a fraction of the size — it is the same reason road
    signs are shapes with symbols punched out of them rather than symbols.
    """
    if not name or name not in EMBLEMS:
        return ""
    r = size * 0.62
    out = [f'<g class="emblem e{min(6, max(1, int(tier)))}">',
           f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{colour}" '
           f'stroke="{LINE}" stroke-width="1.5"/>',
           f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.84:.1f}" fill="none" '
           f'stroke="{WALL}" stroke-width=".7" opacity=".45"/>',
           icon(name, size=size * 0.66, colour=WALL, cx=cx, cy=cy)]
    if tier >= 5:
        # High tiers get a lit halo behind the medallion, close up only.
        # After the opening <g>, so the halo sits behind the disc rather than
        # in front of the icon.
        out.insert(1, _fx(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 1.7:.1f}" '
                          f'fill="{colour}" class="halo" opacity=".35"/>'))
    return "".join(out) + "</g>"


# --------------------------------------------------------------------------- #
#  Who lives there
# --------------------------------------------------------------------------- #
# A town with a menagerie in it and nothing alive in it is a shed with a fence
# around it. The animals were drawn here as an ellipse with a circle for a head
# and read as a bean; Font Awesome's silhouettes read as the animal at a
# fraction of the size, which is the entire job at map scale.

WALKER_COLOURS = ("#5b4630", "#6b5138", "#4a3826", "#7a5c3e")


def _person(c="#5b4630", hat: int = 0):
    """Somebody, at map scale. A head and a coat is all that survives.

    Hand-drawn rather than an icon: Font Awesome's person is a standing figure
    with a gap under the arms that closes up into a blob below about eight
    units, and a townsperson is drawn at four.
    """
    out = (f'<circle cx="0" cy="-2.6" r="1.5" fill="{c}"/>'
           f'<path d="M-1.8,2.6 Q-1.8,-1.2 0,-1.2 Q1.8,-1.2 1.8,2.6 Z" fill="{c}"/>')
    if hat == 1:  # a hat, so a crowd is not one person copied
        out += f'<path d="M-2.2,-3.6 L2.2,-3.6 L1.2,-5 L-1.2,-5 Z" fill="{c}"/>'
    elif hat == 2:  # a pack on the back
        out += f'<rect x="-3.2" y="-1" width="1.8" height="2.4" rx=".5" fill="{c}"/>'
    return out


def _child(c="#5b4630"):
    """Smaller, rounder. Scale alone is what says child at four units."""
    return (f'<circle cx="0" cy="-1.6" r="1.1" fill="{c}"/>'
            f'<path d="M-1.2,2.6 Q-1.2,-0.4 0,-0.4 Q1.2,-0.4 1.2,2.6 Z" fill="{c}"/>')


def _fa_walker(name: str, size: float):
    """An animal, from Font Awesome, standing on the ground line."""

    def draw(c=WALKER_COLOURS[0]):
        # Shifted up by half its height so its feet meet y=0 rather than its
        # middle: a horse floating at knee height in the road is worse than no
        # horse at all.
        return icon(name, size=size, colour=c, cx=0.0, cy=-size * 0.30)

    return draw


WANDERERS = {
    "person": _person,
    "child": _child,
    "cat": _fa_walker("cat", 6.0),
    "dog": _fa_walker("dog", 6.4),
    "horse": _fa_walker("horse", 8.0),
    "bird": _fa_walker("bird", 5.0),
    "kiwi": _fa_walker("kiwi", 5.4),
    "fish": _fa_walker("fish", 5.0),
    "bug": _fa_walker("bug", 4.4),
}

# Who wanders where, once there is something for them to wander around. A
# menagerie brings animals, an inn brings drinkers, a chapel brings birds.
LIFE = {
    "pen": ("cat", "dog", "horse", "kiwi", "bird", "person"),
    "inn": ("person", "person", "dog", "child"),
    "stage": ("person", "person", "child"),
    "works": ("person", "person"),
    "hall": ("person", "child"),
    "keep": ("person", "person", "horse"),
    "chapel": ("bird", "person", "bird"),
    "monument": ("person", "child", "bird"),
    "gate": ("person", "horse", "dog"),
}
# What wanders a town that has nothing in particular in it yet. Somewhere with
# one tent on it should still have somebody standing outside the tent.
DEFAULT_LIFE = ("person", "cat", "bird")


def glyph(name: str) -> str:
    """Whether an emblem by this name exists. Kept for validation."""
    return name if name in EMBLEMS else ""


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


# --------------------------------------------------------------------------- #
#  Small parts every family builds out of
# --------------------------------------------------------------------------- #
def _win(x, y, w=3.4, h=3.8, lit=False, arch=False) -> str:
    """A window, optionally with a light behind it."""
    if arch:
        shape = (f'<path d="M{x:.1f},{y + h:.1f} L{x:.1f},{y + w / 2:.1f} '
                 f'A{w / 2:.1f},{w / 2:.1f} 0 0 1 {x + w:.1f},{y + w / 2:.1f} '
                 f'L{x + w:.1f},{y + h:.1f} Z" fill="{GLASS}" stroke="{LINE}" '
                 f'stroke-width=".8"/>')
    else:
        shape = _rect(x, y, w, h, fill=GLASS, width=0.8, rx=0.4)
    if not lit:
        return shape
    return shape + _fx(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                       f'height="{h:.1f}" rx=".4" fill="#ffd98a" class="glow"/>')


def _lantern(x, y, r=1.7) -> str:
    """A hung lamp, with a halo that only wakes up close."""
    return (_fx(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 2.3:.1f}" '
                f'fill="#ffd27f" class="halo"/>')
            + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#ffd27f" '
              f'stroke="{LINE}" stroke-width=".8"/>')


def _tree(x, base, size=5.0, conifer=False, leaf="#3f8f5e") -> str:
    """A tree. Two kinds, because a row of identical ones reads as wallpaper."""
    trunk = (f'<rect x="{x - size * 0.16:.1f}" y="{base - size * 1.1:.1f}" '
             f'width="{size * 0.32:.1f}" height="{size * 1.15:.1f}" fill="#7a5233"/>')
    if conifer:
        return trunk + "".join(
            _tri(x - size * (0.85 - i * 0.2), base - size * (0.9 + i * 0.62),
                 x, base - size * (1.7 + i * 0.62),
                 x + size * (0.85 - i * 0.2), base - size * (0.9 + i * 0.62), leaf)
            for i in range(3))
    return (trunk
            + f'<circle cx="{x:.1f}" cy="{base - size * 1.5:.1f}" r="{size * 0.8:.1f}" '
              f'fill="{leaf}" stroke="{LINE}" stroke-width=".8"/>'
            + f'<circle cx="{x - size * 0.5:.1f}" cy="{base - size * 1.1:.1f}" '
              f'r="{size * 0.5:.1f}" fill="{leaf}" stroke="{LINE}" stroke-width=".7"/>')


def _bush(x, base, size=3.0, leaf="#4f9f6e") -> str:
    return (f'<ellipse cx="{x:.1f}" cy="{base - size * 0.5:.1f}" '
            f'rx="{size:.1f}" ry="{size * 0.72:.1f}" fill="{leaf}" '
            f'stroke="{LINE}" stroke-width=".7"/>')


def _pennant(x, y, colour, height=10.0, cls="banner") -> str:
    """A pole with a triangular flag that waves close up."""
    return (f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y - height:.1f}" '
            f'stroke="{LINE}" stroke-width="1.1"/>'
            f'<circle cx="{x:.1f}" cy="{y - height - 0.8:.1f}" r=".9" fill="{LINE}"/>'
            f'<polygon class="{cls}" points="{x:.1f},{y - height:.1f} '
            f'{x + 7:.1f},{y - height + 2.6:.1f} {x:.1f},{y - height + 5.2:.1f}" '
            f'fill="{colour}" stroke="{LINE}" stroke-width=".7"/>')


def _flag(x, y, colour, height=11.0) -> str:
    """Kept under its old name: several families and the tests call it."""
    return _pennant(x, y, colour, height=height)


def _crenels(left, top, width, teeth, fill=WALL_DARK, depth=3.2) -> str:
    """Battlements. The one thing that says fortress at any size."""
    teeth = max(2, int(teeth))
    step = width / (teeth * 2 - 1)
    return "".join(
        _rect(left + i * step * 2, top - depth, step, depth + 0.6,
              fill=fill, width=0.9, rx=0.2)
        for i in range(teeth))


def _tower(x, base, height, radius, colour, *, conical=True, tier=1) -> str:
    """A round tower with a pointed cap. The keep's vocabulary."""
    out = [_rect(x - radius, base - height, radius * 2, height, fill=WALL_DARK)]
    # A vertical highlight, so a cylinder reads as a cylinder and not a plank.
    out.append(f'<rect x="{x - radius * 0.55:.1f}" y="{base - height:.1f}" '
               f'width="{radius * 0.5:.1f}" height="{height:.1f}" fill="{WALL}" '
               f'opacity=".5"/>')
    if conical:
        out.append(_tri(x - radius - 1.4, base - height, x,
                        base - height - radius * 2.1,
                        x + radius + 1.4, base - height, colour))
    else:
        out.append(_crenels(x - radius, base - height, radius * 2, 3))
    if tier >= 3:
        out.append(_win(x - 1.1, base - height + radius * 1.3, 2.2, 3.0,
                        lit=tier >= 5, arch=True))
    return "".join(out)


def _cottage(x, base, size=7.0, colour="#b0724a", variant: int = 0,
             wall: str = WALL) -> str:
    """One ordinary house. The town's filler, and its sense of scale.

    A settlement is mostly ordinary houses; the buildings somebody has earned
    are the landmarks standing among them. Without these a Legend's capital is
    four objects on an empty plate.

    Six variants, because sixty copies of one house is a housing estate rather
    than a town. They differ in **outline** — a gable end on, a long roof, a
    two-storey, a lean-to, a round hut, a walled yard — rather than only in
    colour, for the same reason the landmark families do: at this size colour
    is the first thing to go and the silhouette is the last.
    """
    w, h = size, size * 0.72
    left, top = x - w / 2, base - h
    door = _rect(x - w * 0.13, base - h * 0.46, w * 0.26, h * 0.46,
                 fill=DOOR, stroke="none", width=0, rx=0.3)

    if variant == 1:  # tall and narrow, two storeys, gable to the front
        w, h = size * 0.66, size * 1.15
        left, top = x - w / 2, base - h
        return (_rect(left, top, w, h, fill=wall, width=0.9, rx=0.3)
                + _tri(left - 0.8, top, x, top - w * 0.6, left + w + 0.8, top, colour)
                + _rect(x - w * 0.2, top + h * 0.22, w * 0.4, h * 0.22,
                        fill=GLASS, width=0.5, rx=0.2)
                + _rect(x - w * 0.16, base - h * 0.36, w * 0.32, h * 0.36,
                        fill=DOOR, stroke="none", width=0, rx=0.2))

    if variant == 2:  # long and low, roof running the length of it, a chimney
        w, h = size * 1.35, size * 0.56
        left, top = x - w / 2, base - h
        return (_rect(left, top, w, h, fill=wall, width=0.9, rx=0.3)
                + _rect(left - 1, top - h * 0.5, w + 2, h * 0.55,
                        fill=colour, width=0.9, rx=0.4)
                + _rect(left + w * 0.72, top - h * 1.25, w * 0.13, h * 0.8,
                        fill="#6b4a30", width=0.7, rx=0.2)
                + door)

    if variant == 3:  # a house with a lean-to shed against it
        return (_rect(left, top, w, h, fill=wall, width=0.9, rx=0.3)
                + _tri(left - 1.1, top, x, top - h * 0.8, left + w + 1.1, top, colour)
                + f'<path d="M{left + w:.1f},{base:.1f} L{left + w:.1f},'
                  f'{top + h * 0.3:.1f} L{left + w + size * 0.5:.1f},'
                  f'{top + h * 0.62:.1f} L{left + w + size * 0.5:.1f},{base:.1f} Z" '
                  f'fill="{WALL_DARK}" stroke="{LINE}" stroke-width=".8"/>'
                + door)

    if variant == 4:  # a round hut with a conical roof
        r = size * 0.42
        return (f'<path d="M{x - r:.1f},{base:.1f} L{x - r:.1f},{base - r * 0.9:.1f} '
                f'A{r:.1f},{r * 0.5:.1f} 0 0 1 {x + r:.1f},{base - r * 0.9:.1f} '
                f'L{x + r:.1f},{base:.1f} Z" fill="{wall}" stroke="{LINE}" '
                f'stroke-width=".9"/>'
                + _tri(x - r * 1.35, base - r * 0.9, x, base - r * 2.5,
                       x + r * 1.35, base - r * 0.9, colour)
                + _rect(x - r * 0.24, base - r * 0.72, r * 0.48, r * 0.72,
                        fill=DOOR, stroke="none", width=0, rx=0.2))

    if variant == 5:  # a house behind a low walled yard
        return (_rect(left + w * 0.12, top, w * 0.88, h, fill=wall, width=0.9, rx=0.3)
                + _tri(left - 0.2, top, x + w * 0.06, top - h * 0.78,
                       left + w + 1.1, top, colour)
                + _rect(left - size * 0.34, base - h * 0.34, w * 0.6, h * 0.34,
                        fill=WALL_DARK, width=0.7, rx=0.2)
                + _bush(left - size * 0.05, base, size * 0.2)
                + door)

    # 0: the plain gabled cottage everything else is a variation on.
    return (_rect(left, top, w, h, fill=wall, width=0.9, rx=0.4)
            + _tri(left - 1.1, top, x, top - h * 0.75, left + w + 1.1, top, colour)
            + door)

# --------------------------------------------------------------------------- #
#  The shape families
# --------------------------------------------------------------------------- #
# Each takes the centre x, the ground line, a tier 1-6 and a colour, and returns
# a fragment. They are written to be told apart in silhouette alone, and to
# escalate hard: tier one is a shed, tier six is the thing somebody points at.
#
# The rule for every family is the same. Each tier **adds a part that was not
# there before** — a wing, a tower, a storey, a courtyard — rather than scaling
# the same box up. A silhouette that only grows is a progress bar nobody can
# read; a silhouette that gains parts is a building you can watch being built.

def _inn(x, base, tier, colour, symbol="") -> str:
    """Wide and low, with an awning and a hanging sign. Taverns and bakeries."""
    w, h = 15 + tier * 3.2, 8 + tier * 2.4
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h)]

    if tier >= 4:  # a second storey, jettied out over the ground floor
        upper = h * 0.62
        out.append(_rect(left - 1.6, top - upper, w + 3.2, upper, fill=WALL_DARK))
        roof_top = top - upper
        out.append(_tri(left - 3.4, roof_top, x, roof_top - h * 0.5,
                        left + w + 3.4, roof_top, colour))
        for i, wx in enumerate((x - w * 0.3, x, x + w * 0.24)[:1 + min(2, tier - 3)]):
            out.append(_win(wx - 1.8, roof_top + 2.4, 3.6, 4.0, lit=tier >= 5))
    else:
        out.append(_tri(left - 2, top, x, top - h * 0.45, left + w + 2, top, colour))

    # The striped awning: the thing that says "come in", and the family's tell.
    if tier >= 2:
        out.append(_rect(left, base - 5.0, w, 3.2, fill=colour, width=0.9, rx=0.4))
        for i in range(int(w // 4)):
            out.append(f'<rect x="{left + i * 4:.1f}" y="{base - 5.0:.1f}" width="2" '
                       f'height="3.2" fill="{WALL}" opacity=".7"/>')
        out.append(f'<ellipse cx="{left - 3.4:.1f}" cy="{base - 2:.1f}" rx="2.6" '
                   f'ry="3.4" fill="#a0713d" stroke="{LINE}" stroke-width=".8"/>')
    out.append(_door(x, base, w=4.6, h=6.4, arch=tier >= 4))
    out.append(_win(x - w * 0.38, base - h * 0.82, 3.4, 3.8, lit=tier >= 3))
    out.append(_win(x + w * 0.24, base - h * 0.82, 3.4, 3.8, lit=tier >= 3))

    if tier >= 3:  # the hanging sign on its bracket
        sx = left + w + 1
        out.append(f'<line x1="{left + w:.1f}" y1="{top + 2.5:.1f}" x2="{sx + 5:.1f}" '
                   f'y2="{top + 2.5:.1f}" stroke="{LINE}" stroke-width="1.1"/>')
        out.append(f'<line x1="{sx + 4:.1f}" y1="{top + 2.5:.1f}" x2="{sx + 4:.1f}" '
                   f'y2="{top + 5:.1f}" stroke="{LINE}" stroke-width=".9"/>')
        out.append(_rect(sx + 1, top + 5, 6, 5.4, fill=colour, width=1))
    if tier >= 4:  # chimney and smoke
        cx = left + w * 0.72
        out.append(_rect(cx, top - h * 0.62 - 6, 3.6, 7, fill="#6b4a30", width=0.9))
        out.append(_smoke(cx + 1.8, top - h * 0.62 - 9))
    if tier >= 5:  # lanterns either side of the door, benches outside
        out.append(_lantern(x - 5.2, base - h * 0.62))
        out.append(_lantern(x + 5.2, base - h * 0.62))
        out.append(_rect(left + 2, base - 2.4, 7, 1.2, fill="#8a6239", width=0.7, rx=0.3))
    if tier >= 6:  # a wing, window boxes and a flag: an inn with a yard
        out.append(_rect(left - 9, base - h * 0.7, 9.5, h * 0.7, fill=WALL_DARK))
        out.append(_tri(left - 10.4, base - h * 0.7, left - 4.2,
                        base - h * 0.7 - 5.5, left + 1, base - h * 0.7, colour))
        for wx in (x - w * 0.3, x + w * 0.24):
            out.append(_rect(wx - 2.2, base - h * 0.82 + 3.9, 4.4, 1.4,
                             fill="#c0392b", width=0.6, rx=0.4))
        out.append(_pennant(left + w * 0.2, top - h * 0.62 - h * 0.5, colour, 9))
    return "".join(out)


def _hall(x, base, tier, colour, symbol="") -> str:
    """Columns and a pediment. Libraries, galleries, moot halls."""
    w, h = 14 + tier * 2.6, 9 + tier * 3.2
    left, top = x - w / 2, base - h
    out = []

    if tier >= 5:  # a dome behind the pediment, drawn first so it sits behind
        r = w * 0.32
        out.append(f'<path d="M{x - r:.1f},{top + 1:.1f} A{r:.1f},{r * 1.15:.1f} '
                   f'0 0 1 {x + r:.1f},{top + 1:.1f} Z" fill="{colour}" '
                   f'stroke="{LINE}" stroke-width="1.1"/>')
        out.append(f'<path d="M{x - r * 0.45:.1f},{top - r * 0.72:.1f} '
                   f'A{r * 0.45:.1f},{r * 0.5:.1f} 0 0 1 {x + r * 0.45:.1f},'
                   f'{top - r * 0.72:.1f}" fill="none" stroke="{WALL}" '
                   f'stroke-width=".8" opacity=".55"/>')
        if tier >= 6:
            out.append(f'<circle cx="{x:.1f}" cy="{top - r * 1.28:.1f}" r="2.4" '
                       f'fill="#e6b422" stroke="{LINE}" stroke-width="1"/>')

    if tier >= 4:  # flanking wings, each with its own little roof
        for side in (-1, 1):
            wx = x + side * (w / 2 + 5.4)
            out.append(_rect(wx - 5.4, base - h * 0.56, 10.8, h * 0.56, fill=WALL_DARK))
            out.append(_tri(wx - 6.8, base - h * 0.56, wx,
                            base - h * 0.56 - 4.6, wx + 6.8, base - h * 0.56, colour))
            out.append(_win(wx - 1.8, base - h * 0.4, 3.6, 4.2, lit=tier >= 5,
                            arch=True))

    out.append(_rect(left, top, w, h, fill=WALL_DARK))
    # Columns: the classical tell, visible even as a smudge.
    count = 3 + min(5, tier)
    gap = w / (count + 1)
    for i in range(count):
        cx = left + gap * (i + 1)
        out.append(_rect(cx - 1.3, top + 2.4, 2.6, h - 2.4, fill=WALL, width=0.7, rx=0.3))
        if tier >= 3:  # capitals, so the columns are columns and not railings
            out.append(_rect(cx - 1.9, top + 2.0, 3.8, 1.3, fill=WALL, width=0.6, rx=0.2))
    out.append(_tri(left - 3.4, top + 2.4, x, top - h * 0.34,
                    left + w + 3.4, top + 2.4, colour))
    if tier >= 3:  # a frieze under the pediment
        for i in range(int(w // 5)):
            out.append(f'<circle cx="{left + 3 + i * 5:.1f}" cy="{top + 0.6:.1f}" '
                       f'r=".9" fill="{WALL}" opacity=".7"/>')
    out.append(_door(x, base, w=5.0, h=7.2, arch=tier >= 3))
    if tier >= 2:  # steps up to it
        steps = 1 + min(3, tier - 1)
        for i in range(steps):
            sw = w + 5 - i * 3.0
            out.append(_rect(x - sw / 2, base - 1.5 * (steps - i), sw, 1.7,
                             fill=WALL_DARK, width=0.7, rx=0.2))
    if tier >= 6:  # statues along the roofline and banners down the front
        for side in (-1, 1):
            sx = x + side * (w * 0.42)
            out.append(f'<circle cx="{sx:.1f}" cy="{top - h * 0.34 + 3:.1f}" r="1.6" '
                       f'fill="{WALL}" stroke="{LINE}" stroke-width=".8"/>')
            out.append(f'<path d="M{sx - 1.8:.1f},{top - h * 0.34 + 8:.1f} '
                       f'L{sx:.1f},{top - h * 0.34 + 4.4:.1f} '
                       f'L{sx + 1.8:.1f},{top - h * 0.34 + 8:.1f} Z" fill="{WALL}" '
                       f'stroke="{LINE}" stroke-width=".7"/>')
        for side in (-1, 1):
            bx = x + side * w * 0.22
            out.append(f'<path d="M{bx - 2:.1f},{top + 3:.1f} L{bx + 2:.1f},{top + 3:.1f} '
                       f'L{bx + 2:.1f},{top + 13:.1f} L{bx:.1f},{top + 11:.1f} '
                       f'L{bx - 2:.1f},{top + 13:.1f} Z" fill="{colour}" '
                       f'stroke="{LINE}" stroke-width=".7"/>')
    return "".join(out)


def _keep(x, base, tier, colour, symbol="") -> str:
    """A castle. Battlements, towers, a gatehouse. Barracks and war rooms.

    Rewritten because it was the least convincing family in the set: a box with
    teeth on it and, from tier three, two identical spikes stuck to its sides.
    A keep should read as fortified from the first tier and as a fortress by the
    last, and every rung between should add a piece of the castle rather than
    widen the box.
    """
    w, h = 15 + tier * 2.2, 10 + tier * 2.6
    left, top = x - w / 2, base - h
    out = []

    if tier >= 4:  # curtain walls running off both sides, with their own teeth
        wall_h = h * 0.44
        for side in (-1, 1):
            wx = x + side * (w / 2 + 6.5)
            out.append(_rect(wx - 6.5, base - wall_h, 13, wall_h, fill=WALL_DARK))
            out.append(_crenels(wx - 6.5, base - wall_h, 13, 4, depth=2.4))
        if tier >= 5:
            for side in (-1, 1):
                out.append(_tower(x + side * (w / 2 + 12.5), base, h * 0.78,
                                  3.6, colour, tier=tier))

    if tier >= 3:  # the great round tower, off to one side and taller than the hall
        out.append(_tower(x - w / 2 - 3.6, base, h * 1.06, 4.4, colour, tier=tier))

    # The hall itself.
    out.append(_rect(left, top, w, h, fill=WALL_DARK))
    # Stone courses, so a wall is masonry rather than a painted panel.
    for i in range(1, max(2, int(h // 5))):
        out.append(f'<line x1="{left:.1f}" y1="{top + i * 5:.1f}" '
                   f'x2="{left + w:.1f}" y2="{top + i * 5:.1f}" stroke="{LINE}" '
                   f'stroke-width=".4" opacity=".28"/>')
    if tier >= 5:  # machicolations: corbels under the battlements
        for i in range(int(w // 4)):
            out.append(f'<rect x="{left + 1 + i * 4:.1f}" y="{top - 1.2:.1f}" '
                       f'width="2.2" height="2" fill="{WALL_DARK}" stroke="{LINE}" '
                       f'stroke-width=".5"/>')
    out.append(_crenels(left, top, w, 3 + min(4, tier)))
    # Arrow slits rather than windows: a keep does not have windows.
    for i in range(1 + min(3, tier)):
        sx = left + w * (0.18 + i * 0.22)
        out.append(_rect(sx, top + 5, 1.7, 5.2, fill=LINE, stroke="none",
                         width=0, rx=0.5))
        if tier >= 5:
            out.append(_fx(f'<rect x="{sx:.1f}" y="{top + 5:.1f}" width="1.7" '
                           f'height="5.2" rx=".5" fill="#ffb547" class="glow"/>'))

    # The gatehouse: two short towers with the gate between them.
    gate_w = 11.0
    if tier >= 2:
        for side in (-1, 1):
            out.append(_rect(x + side * gate_w / 2 - 2.2, base - h * 0.62, 4.4,
                             h * 0.62, fill=WALL))
            out.append(_crenels(x + side * gate_w / 2 - 2.2, base - h * 0.62, 4.4,
                                2, fill=WALL, depth=2.0))
    out.append(f'<path d="M{x - 3.6:.1f},{base:.1f} L{x - 3.6:.1f},{base - 5:.1f} '
               f'A3.6,3.6 0 0 1 {x + 3.6:.1f},{base - 5:.1f} L{x + 3.6:.1f},'
               f'{base:.1f} Z" fill="#2a1c12" stroke="{LINE}" stroke-width="1"/>')
    if tier >= 4:  # a portcullis in the gateway
        for i in range(3):
            out.append(f'<line x1="{x - 3.6:.1f}" y1="{base - 1.6 - i * 2.2:.1f}" '
                       f'x2="{x + 3.6:.1f}" y2="{base - 1.6 - i * 2.2:.1f}" '
                       f'stroke="{WALL}" stroke-width=".7" opacity=".8"/>')
        for i in range(3):
            lx = x - 2.4 + i * 2.4
            out.append(f'<line x1="{lx:.1f}" y1="{base:.1f}" x2="{lx:.1f}" '
                       f'y2="{base - 7.4:.1f}" stroke="{WALL}" stroke-width=".7" '
                       f'opacity=".8"/>')

    if tier >= 6:
        # The donjon: one tower standing over everything, which is what makes a
        # castle a castle rather than a walled yard.
        out.append(_tower(x, base - h * 0.1, h * 1.75, 6.2, colour, tier=tier))
        out.append(_pennant(x, base - h * 0.1 - h * 1.75 - 12.4, colour, 8))
        for side in (-1, 1):
            out.append(_pennant(x + side * (w / 2 + 3.6),
                                base - h * 1.06 - 9.2, colour, 6))
        # A drawbridge over a moat.
        out.append(f'<path d="M{x - 3.6:.1f},{base:.1f} L{x + 3.6:.1f},{base:.1f} '
                   f'L{x + 5.4:.1f},{base + 3.6:.1f} L{x - 5.4:.1f},{base + 3.6:.1f} Z" '
                   f'fill="#8a6239" stroke="{LINE}" stroke-width=".9"/>')
    elif tier >= 3:
        out.append(_pennant(x - w / 2 - 3.6, base - h * 1.06 - 9.2, colour, 7))
    return "".join(out)


def _chapel(x, base, tier, colour, symbol="") -> str:
    """Tall, narrow, a steep spire and a rose window. Shrines and sanctuaries.

    Deliberately no cross, and no religious mark of any kind: this is a quiet
    room on a Discord server, not a church, and a server whose members do not
    share a religion should not have one planted in the middle of its map. What
    says chapel here is the proportion — tall, narrow, steep — and the rose
    window, which no other family has.
    """
    w, h = 10 + tier * 1.7, 11 + tier * 3.4
    left, top = x - w / 2, base - h
    spire = 9 + tier * 3.2
    out = []

    if tier >= 4:  # a bell tower alongside, with a bell in it
        th = h + spire * 0.45
        tx = left - 7.2
        out.append(_rect(tx, base - th, 7.2, th, fill=WALL_DARK))
        out.append(_tri(tx - 1.5, base - th, tx + 3.6, base - th - 10,
                        tx + 8.7, base - th, colour))
        out.append(f'<path d="M{tx + 1.9:.1f},{base - th + 8:.1f} '
                   f'A1.7,1.7 0 0 1 {tx + 5.3:.1f},{base - th + 8:.1f} '
                   f'L{tx + 5.3:.1f},{base - th + 11:.1f} L{tx + 1.9:.1f},'
                   f'{base - th + 11:.1f} Z" fill="#b8862b" stroke="{LINE}" '
                   f'stroke-width=".8"/>')
        if tier >= 6:
            out.append(_pennant(tx + 3.6, base - th - 10, colour, 6))

    if tier >= 5:  # a low side chapel, and flying buttresses over it
        out.append(_rect(x + w / 2, base - h * 0.42, 8.5, h * 0.42, fill=WALL_DARK))
        out.append(_tri(x + w / 2 - 1.2, base - h * 0.42, x + w / 2 + 4.2,
                        base - h * 0.42 - 4.4, x + w / 2 + 9.7,
                        base - h * 0.42, colour))
        for i in range(2):
            by = top + 6 + i * 9
            out.append(f'<path d="M{x + w / 2:.1f},{by:.1f} Q{x + w / 2 + 5:.1f},'
                       f'{by + 2:.1f} {x + w / 2 + 7:.1f},{base - h * 0.42:.1f}" '
                       f'fill="none" stroke="{LINE}" stroke-width="1.1"/>')

    out.append(_rect(left, top, w, h))
    out.append(_tri(left - 2.4, top, x, top - spire, left + w + 2.4, top, colour))
    if tier >= 3:  # tall lancet windows down the nave
        for i in range(min(3, tier - 1)):
            out.append(_win(left + 1.6 + i * (w - 4.4) / max(1, min(3, tier - 1) - 1 or 1),
                            top + h * 0.45, 2.6, h * 0.4, lit=tier >= 5, arch=True))
    if tier >= 2:  # the rose window: the family's tell, and nobody else has one
        r = 2.2 + tier * 0.45
        out.append(f'<circle cx="{x:.1f}" cy="{top + 6:.1f}" r="{r:.1f}" '
                   f'fill="{GLASS}" stroke="{LINE}" stroke-width="1"/>')
        for i in range(6):  # tracery, so it is a rose and not a porthole
            angle = i * math.pi / 3
            out.append(f'<line x1="{x:.1f}" y1="{top + 6:.1f}" '
                       f'x2="{x + r * math.cos(angle):.1f}" '
                       f'y2="{top + 6 + r * math.sin(angle):.1f}" stroke="{LINE}" '
                       f'stroke-width=".6" opacity=".8"/>')
        if tier >= 4:
            out.append(_fx(f'<circle cx="{x:.1f}" cy="{top + 6:.1f}" r="{r:.1f}" '
                           f'fill="#ffd98a" class="glow"/>'))
    out.append(_door(x, base, w=4.6, h=7.6, arch=True))
    if tier >= 6:  # a finial and lanterns on the spire — light, not a symbol
        out.append(f'<circle cx="{x:.1f}" cy="{top - spire - 3.2:.1f}" r="2.4" '
                   f'fill="#e6b422" stroke="{LINE}" stroke-width="1"/>')
        out.append(_fx(f'<circle cx="{x:.1f}" cy="{top - spire - 3.2:.1f}" r="5.6" '
                       f'fill="#ffd27f" class="halo"/>'))
        for side in (-1, 1):
            out.append(_lantern(x + side * (w / 2 + 1.6), top + 2, 1.4))
    return "".join(out)


def _pen(x, base, tier, colour, symbol="") -> str:
    """A fenced enclosure with shelters, trees and water. Menageries, gardens.

    The family that should look green from across the map: it is the only one
    whose defining feature is what grows in it rather than what is built in it.
    """
    w = 18 + tier * 3.6
    left = x - w / 2
    # The ground inside the fence is its own patch of green. That is what makes
    # this read as an enclosed *zone* — a piece of land somebody has fenced off
    # and planted — rather than as a hut with a railing in front of it.
    out = [f'<ellipse cx="{x:.1f}" cy="{base - 1:.1f}" rx="{w * 0.54:.1f}" '
           f'ry="{6 + tier * 0.9:.1f}" fill="#8fbf7a" stroke="#6f9f5c" '
           f'stroke-width="1"/>',
           f'<ellipse cx="{x:.1f}" cy="{base - 1.8:.1f}" rx="{w * 0.47:.1f}" '
           f'ry="{4.6 + tier * 0.7:.1f}" fill="#a2cf8a" opacity=".85"/>']

    if tier >= 6:  # a glasshouse at the back, which is the family's grand form
        gx = x + w * 0.24
        out.append(f'<path d="M{gx - 9:.1f},{base:.1f} L{gx - 9:.1f},{base - 8:.1f} '
                   f'Q{gx:.1f},{base - 20:.1f} {gx + 9:.1f},{base - 8:.1f} '
                   f'L{gx + 9:.1f},{base:.1f} Z" fill="{GLASS}" opacity=".75" '
                   f'stroke="{LINE}" stroke-width="1.1"/>')
        for i in range(3):
            out.append(f'<line x1="{gx - 4.5 + i * 4.5:.1f}" y1="{base:.1f}" '
                       f'x2="{gx - 4.5 + i * 4.5:.1f}" y2="{base - 14 + abs(i - 1) * 4:.1f}" '
                       f'stroke="{LINE}" stroke-width=".6" opacity=".7"/>')

    # Planting first, so the fence reads in front of it.
    if tier >= 2:
        out.append(_tree(left + w - 5.5, base, 5.0 + tier * 0.4, conifer=False))
    if tier >= 3:
        out.append(_tree(left + 4.5, base, 4.4 + tier * 0.3, conifer=True,
                         leaf="#2f7f52"))
        out.append(_bush(left + w * 0.55, base, 2.8))
    if tier >= 5:
        out.append(_tree(left + w * 0.36, base, 4.0, conifer=True, leaf="#357f56"))
        out.append(_bush(left + w * 0.2, base, 2.4, leaf="#5aa87a"))
        out.append(_bush(left + w * 0.78, base, 3.2))

    if tier >= 4:  # a pond
        out.append(f'<ellipse cx="{x - 1:.1f}" cy="{base - 2.4:.1f}" '
                   f'rx="{5 + tier:.1f}" ry="2.8" fill="{GLASS}" stroke="{LINE}" '
                   f'stroke-width=".8"/>')
        out.append(f'<path d="M{x - 5:.1f},{base - 3:.1f} q2,-1 4,0" fill="none" '
                   f'stroke="{WALL}" stroke-width=".6" opacity=".8"/>')
        # A few rocks around it.
        for i in range(3):
            out.append(f'<ellipse cx="{x + 5 + i * 3.4:.1f}" cy="{base - 1:.1f}" '
                       f'rx="{2.2 - i * 0.4:.1f}" ry="1.3" fill="#a89880" '
                       f'stroke="{LINE}" stroke-width=".6"/>')

    # The shelter, and a second one once there is a menagerie to shelter.
    sh = 6 + tier * 1.5
    out.append(_rect(left + 1.5, base - sh, 9.5, sh, fill=WALL))
    out.append(_tri(left - 0.2, base - sh, left + 6.2, base - sh - 5.5,
                    left + 12.6, base - sh, colour))
    if tier >= 3:
        out.append(_rect(left + w - 12, base - sh * 0.72, 8, sh * 0.72, fill=WALL_DARK))
        out.append(_tri(left + w - 13.4, base - sh * 0.72, left + w - 8,
                        base - sh * 0.72 - 4.2, left + w - 2.6,
                        base - sh * 0.72, colour))
        # A hay bale outside it.
        out.append(f'<ellipse cx="{left + w - 14.5:.1f}" cy="{base - 2:.1f}" rx="2.4" '
                   f'ry="2.2" fill="#d8b45c" stroke="{LINE}" stroke-width=".8"/>')

    # The fence runs right round the patch rather than across the front of it,
    # following the same ellipse the ground does, so the enclosure encloses
    # something. Posts are placed by angle and the rails follow the curve.
    rx, ry = w * 0.54, 6 + tier * 0.9
    posts = 9 + min(9, tier * 2)
    for rail in (5.0, 7.2):
        out.append(f'<path d="M{x - rx:.1f},{base - 1 - rail:.1f} '
                   f'A{rx:.1f},{ry:.1f} 0 0 0 {x + rx:.1f},{base - 1 - rail:.1f}" '
                   f'fill="none" stroke="#a0713d" stroke-width="1.3"/>')
    for i in range(posts):
        angle = math.pi * i / (posts - 1)
        px = x - rx * math.cos(angle)
        py = base - 1 + ry * math.sin(angle)
        out.append(_rect(px - 0.8, py - 8, 1.6, 8, fill="#a0713d", width=0.7, rx=0.2))
    # A gate in the near side, so the fence has a way in. Deliberately no taller
    # than the rails: a gate drawn as a full-height slab reads as a crate parked
    # in front of the enclosure rather than as a way into it.
    out.append(_rect(x - 2.6, base + ry - 7.2, 5.2, 6.0, fill="#c89a63",
                     width=0.8, rx=0.4))
    out.append(f'<line x1="{x - 2.6:.1f}" y1="{base + ry - 4.2:.1f}" '
               f'x2="{x + 2.6:.1f}" y2="{base + ry - 4.2:.1f}" stroke="#8a6239" '
               f'stroke-width=".7"/>')
    if tier >= 5:  # an aviary dome over one corner
        r = 7 + tier * 0.6
        ax = left + w * 0.62
        out.append(f'<path d="M{ax - r:.1f},{base:.1f} A{r:.1f},{r:.1f} 0 0 1 '
                   f'{ax + r:.1f},{base:.1f}" fill="none" stroke="{LINE}" '
                   f'stroke-width="1.2"/>')
        for i in range(5):
            angle = math.pi * (i + 1) / 6
            out.append(f'<line x1="{ax:.1f}" y1="{base:.1f}" '
                       f'x2="{ax - r * math.cos(angle):.1f}" '
                       f'y2="{base - r * math.sin(angle):.1f}" stroke="{LINE}" '
                       f'stroke-width=".5" opacity=".6"/>')
    return "".join(out)


def _works(x, base, tier, colour, symbol="") -> str:
    """Saw-tooth roof, stacks, a wheel, a lit forge. Forges and workshops."""
    w, h = 15 + tier * 2.8, 8 + tier * 2.4
    left, top = x - w / 2, base - h
    out = [_rect(left, top, w, h, fill=WALL_DARK)]

    # Saw-tooth roofline: unmistakable, and it is the whole tell.
    teeth = 2 + min(5, tier)
    tw = w / teeth
    for i in range(teeth):
        tx = left + i * tw
        out.append(f'<polygon points="{tx:.1f},{top:.1f} {tx:.1f},{top - 5:.1f} '
                   f'{tx + tw:.1f},{top:.1f}" fill="{colour}" stroke="{LINE}" '
                   f'stroke-width=".9" stroke-linejoin="round"/>')
        if tier >= 3:  # glazing on the north face of each tooth
            out.append(f'<line x1="{tx + 0.6:.1f}" y1="{top - 3.8:.1f}" '
                       f'x2="{tx + 0.6:.1f}" y2="{top - 0.6:.1f}" stroke="{GLASS}" '
                       f'stroke-width="1.4"/>')

    stacks = 1 + (1 if tier >= 4 else 0) + (1 if tier >= 6 else 0)
    for i in range(stacks):
        sx = left + w - 5.5 - i * 6.5
        sh = 7 + tier * 1.7 + i * 3
        out.append(_rect(sx, top - sh, 4.2, sh + 1, fill="#6b4a30", width=0.9))
        out.append(_rect(sx - 0.7, top - sh, 5.6, 1.8, fill="#5a3d27", width=0.7))
        if tier >= 4:
            out.append(_smoke(sx + 2.1, top - sh - 2))
    out.append(_door(x - w * 0.16, base, w=5.4, h=7))

    if tier >= 3:  # a water wheel on the end wall, and it turns
        r = 4.4 + tier * 0.7
        wx = left - 3.4
        spokes = "".join(
            f'<line x1="{-r * math.cos(i * math.pi / 6):.1f}" '
            f'y1="{-r * math.sin(i * math.pi / 6):.1f}" '
            f'x2="{r * math.cos(i * math.pi / 6):.1f}" '
            f'y2="{r * math.sin(i * math.pi / 6):.1f}" '
            f'stroke="{LINE}" stroke-width=".7"/>' for i in range(6))
        paddles = "".join(
            f'<rect x="{r * math.cos(i * math.pi / 3) - 1.1:.1f}" '
            f'y="{r * math.sin(i * math.pi / 3) - 1.1:.1f}" width="2.2" '
            f'height="2.2" rx=".3" fill="#8a6239" stroke="{LINE}" '
            f'stroke-width=".6"/>' for i in range(6))
        # Drawn about its own centre so the rotation has something to rotate
        # around. Motion here is a turning wheel, not a fading one: opacity is
        # for light, and a mill wheel that blinks is a broken mill wheel.
        out.append(f'<g class="wheel" transform="translate({wx:.1f},{base - r:.1f})">'
                   f'<circle cx="0" cy="0" r="{r:.1f}" fill="none" stroke="{LINE}" '
                   f'stroke-width="1.3"/>{spokes}{paddles}</g>')
    if tier >= 2:  # crates and barrels in the yard
        for i in range(min(3, tier - 1)):
            out.append(_rect(left + w + 0.5 + i * 4, base - 3.4 - (i % 2) * 3.4,
                             3.6, 3.6, fill="#a0713d", width=0.8, rx=0.3))
    if tier >= 5:  # the forge mouth, lit, and an anvil beside it
        out.append(_rect(x + w * 0.2, base - 5.4, 4.6, 5.4, fill="#ff9a3c", width=0.8))
        out.append(_fx(f'<rect x="{x + w * 0.2:.1f}" y="{base - 5.4:.1f}" width="4.6" '
                       f'height="5.4" rx=".8" fill="#ffd98a" class="glow"/>'))
        out.append(f'<path d="M{x + w * 0.2 - 7:.1f},{base:.1f} l0,-2 l1.4,-.8 '
                   f'l4,0 l1.4,.8 l0,2 Z" fill="#4a4a4a" stroke="{LINE}" '
                   f'stroke-width=".7"/>')
    if tier >= 6:  # a great gear on the gable, and it turns
        out.append(f'<g class="cog" transform="translate({left + 5.5:.1f},'
                   f'{top + h * 0.42:.1f})">{icon("gear", 11, colour)}</g>')
    return "".join(out)


def _stage(x, base, tier, colour, symbol="") -> str:
    """A proscenium arch with curtains and a marquee. Playhouses and arenas."""
    w, h = 15 + tier * 3.2, 11 + tier * 3.0
    left, top = x - w / 2, base - h
    out = []

    if tier >= 4:  # banked seating either side, stepping down and outward
        for side in (-1, 1):
            for i in range(min(3, tier - 2)):
                sx = x + side * (w / 2 + 1.5 + i * 3.2)
                sh = 8.5 - i * 2.2
                out.append(_rect(sx - 1.6 if side > 0 else sx - 1.6,
                                 base - sh, 3.4, sh, fill=WALL, width=0.8, rx=0.3))
    if tier >= 6:  # a rotunda: the roof goes round, which nothing else here does
        r = w * 0.5
        out.append(f'<path d="M{x - r:.1f},{top + 1:.1f} A{r:.1f},{r * 0.62:.1f} '
                   f'0 0 1 {x + r:.1f},{top + 1:.1f} Z" fill="{colour}" '
                   f'stroke="{LINE}" stroke-width="1.1"/>')
        for i in range(5):
            out.append(f'<line x1="{x - r + (i + 1) * r / 3:.1f}" y1="{top + 1:.1f}" '
                       f'x2="{x:.1f}" y2="{top - r * 0.56:.1f}" stroke="{LINE}" '
                       f'stroke-width=".5" opacity=".4"/>')

    out.append(_rect(left, top, w, h, fill=WALL_DARK))
    # The arch: a big opening rather than a door, which is the tell.
    aw, ah = w * 0.6, h * 0.7
    out.append(f'<path d="M{x - aw / 2:.1f},{base:.1f} L{x - aw / 2:.1f},'
               f'{base - ah * 0.55:.1f} A{aw / 2:.1f},{aw / 2:.1f} 0 0 1 '
               f'{x + aw / 2:.1f},{base - ah * 0.55:.1f} L{x + aw / 2:.1f},{base:.1f} Z" '
               f'fill="#2a1c12" stroke="{LINE}" stroke-width="1.1"/>')
    if tier >= 2:  # curtains, drawn back
        for side in (-1, 1):
            out.append(f'<path d="M{x + side * aw / 2:.1f},{base:.1f} '
                       f'L{x + side * aw / 2:.1f},{base - ah * 0.82:.1f} '
                       f'Q{x + side * aw * 0.26:.1f},{base - ah * 0.42:.1f} '
                       f'{x + side * aw * 0.22:.1f},{base:.1f} Z" fill="{colour}" '
                       f'stroke="{LINE}" stroke-width=".7"/>')
        out.append(f'<path d="M{x - aw / 2:.1f},{base - ah * 0.82:.1f} '
                   f'Q{x:.1f},{base - ah * 0.66:.1f} {x + aw / 2:.1f},'
                   f'{base - ah * 0.82:.1f}" fill="none" stroke="{colour}" '
                   f'stroke-width="2.4"/>')
    # The marquee over the doors.
    out.append(_rect(left - 2.4, top - 4, w + 4.8, 4.2, fill=colour, width=1))
    if tier >= 3:  # bulbs along it, which light up close
        bulbs = int((w + 4) // 4.5)
        for i in range(bulbs):
            bx = left - 1 + i * 4.5
            out.append(f'<circle cx="{bx:.1f}" cy="{top - 1.9:.1f}" r="1.1" '
                       f'fill="#ffd27f" stroke="{LINE}" stroke-width=".5"/>')
            out.append(_fx(f'<circle cx="{bx:.1f}" cy="{top - 1.9:.1f}" r="2.4" '
                           f'fill="#ffd27f" class="halo"/>'))
    if tier >= 5:  # spotlights, throwing beams up over the roof
        for side in (-1, 1):
            lx = x + side * w * 0.38
            out.append(f'<path d="M{lx:.1f},{top - 4:.1f} l{side * 2.6:.1f},-2.6 '
                       f'l1.6,1.6 l{-side * 2.6:.1f},2.6 Z" fill="#4a4a4a" '
                       f'stroke="{LINE}" stroke-width=".6"/>')
            out.append(_fx(f'<polygon class="beamlt" points="{lx:.1f},{top - 6:.1f} '
                           f'{lx + side * 16:.1f},{top - 26:.1f} '
                           f'{lx + side * 22:.1f},{top - 18:.1f}" fill="#ffe9a8" '
                           f'opacity=".28"/>'))
    if tier >= 6:
        for side in (-1, 1):
            out.append(_pennant(x + side * w * 0.44, top - 4, colour, 8))
    return "".join(out)


def _monument(x, base, tier, colour, symbol="") -> str:
    """A stepped plinth and a rising figure. Statues and landmarks."""
    steps = 1 + min(3, tier)
    out = []
    if tier >= 5:  # a ring of smaller stones around it, and braziers
        for i in range(6):
            angle = math.pi * (0.15 + i * 0.14)
            sx = x + math.cos(angle) * (16 + tier)
            out.append(_rect(sx - 1.2, base - 5.5, 2.4, 5.6, fill=WALL_DARK,
                             width=0.7, rx=0.6))
        for side in (-1, 1):
            bx = x + side * (12 + tier)
            out.append(_rect(bx - 2, base - 4, 4, 4, fill="#6b5138", width=0.8, rx=0.4))
            out.append(_lantern(bx, base - 5.6, 2.0))
    for i in range(steps):
        sw = 22 - i * 3.8
        out.append(_rect(x - sw / 2, base - 2.2 * (i + 1), sw, 2.4,
                         fill=WALL_DARK, width=0.9))
    top = base - 2.2 * steps
    ch = 9 + tier * 3.6
    # The column, fluted from tier three so it is not a pipe.
    out.append(_rect(x - 3.0, top - ch, 6.0, ch, fill=WALL, width=1))
    if tier >= 3:
        for i in range(3):
            out.append(f'<line x1="{x - 1.6 + i * 1.6:.1f}" y1="{top - ch + 1.5:.1f}" '
                       f'x2="{x - 1.6 + i * 1.6:.1f}" y2="{top - 1.5:.1f}" '
                       f'stroke="{LINE}" stroke-width=".45" opacity=".45"/>')
        out.append(_rect(x - 4.2, top - ch - 1.6, 8.4, 2.0, fill=WALL, width=0.8, rx=0.3))
    if tier >= 2:
        out.append(f'<circle cx="{x:.1f}" cy="{top - ch - 4.4:.1f}" r="3.4" '
                   f'fill="{colour}" stroke="{LINE}" stroke-width="1"/>')
    if tier >= 4:
        # What stands on the plinth is the building's **own emblem**, carved in
        # stone. A monument to the server's dodo should be a dodo, not a
        # generic figure with its arms out — the emblem already says what the
        # place is for, so the statue is the one place it should be the statue.
        fy = top - ch - 9
        if symbol and symbol in EMBLEMS:
            out.append(icon(symbol, size=8 + tier * 1.5, colour=WALL,
                            cx=x, cy=fy - 1))
            out.append(icon(symbol, size=8 + tier * 1.5, colour=LINE,
                            cx=x, cy=fy - 1, opacity=".18"))
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{fy - 2.6:.1f}" r="2.5" fill="{WALL}" '
                       f'stroke="{LINE}" stroke-width=".9"/>')
            out.append(f'<path d="M{x - 2.6:.1f},{fy + 4:.1f} Q{x - 2.6:.1f},'
                       f'{fy - 0.4:.1f} {x:.1f},{fy - 0.4:.1f} Q{x + 2.6:.1f},'
                       f'{fy - 0.4:.1f} {x + 2.6:.1f},{fy + 4:.1f} Z" fill="{WALL}" '
                       f'stroke="{LINE}" stroke-width=".9"/>')
            out.append(f'<path d="M{x - 6.4:.1f},{fy - 2:.1f} L{x - 2:.1f},'
                       f'{fy + 0.6:.1f} M{x + 6.4:.1f},{fy - 4:.1f} L{x + 2:.1f},'
                       f'{fy + 0.6:.1f}" fill="none" stroke="{WALL}" '
                       f'stroke-width="1.6" stroke-linecap="round"/>')
    if tier >= 6:  # a halo ring and an eternal flame at its foot
        fy = top - ch - 9
        out.append(f'<ellipse cx="{x:.1f}" cy="{fy - 4:.1f}" rx="9" ry="3.2" '
                   f'fill="none" stroke="#e6b422" stroke-width="1.6" opacity=".95"/>')
        out.append(_fx(f'<ellipse cx="{x:.1f}" cy="{fy - 4:.1f}" rx="12" ry="4.4" '
                       f'fill="none" stroke="{colour}" stroke-width="1" class="halo"/>'))
        out.append(f'<path d="M{x - 2.4:.1f},{base:.1f} q0,-4 2.4,-6 q2.4,2 2.4,6 Z" '
                   f'fill="#ff9a3c" stroke="{LINE}" stroke-width=".7"/>')
        out.append(_fx(f'<path d="M{x - 2.4:.1f},{base:.1f} q0,-4 2.4,-6 q2.4,2 2.4,6 Z" '
                       f'fill="#ffd98a" class="glow"/>'))
    return "".join(out)


def _gate(x, base, tier, colour, symbol="") -> str:
    """A free-standing arch. Wayshrines and thresholds."""
    w = 13 + tier * 2.6
    h = 13 + tier * 3.2
    post = 4.6
    out = []
    if tier >= 4:  # low walls running away either side
        for side in (-1, 1):
            wx = x + side * (w / 2 + 5)
            out.append(_rect(wx - 5, base - h * 0.34, 10, h * 0.34, fill=WALL_DARK))
            out.append(_crenels(wx - 5, base - h * 0.34, 10, 3, depth=1.8))
    out.append(_rect(x - w / 2, base - h, post, h, fill=WALL_DARK))
    out.append(_rect(x + w / 2 - post, base - h, post, h, fill=WALL_DARK))
    for i in range(1, 4):  # stone courses on the piers
        for side in (-1, 1):
            px = x + side * (w / 2) - (post if side > 0 else 0)
            out.append(f'<line x1="{px:.1f}" y1="{base - h + i * h / 4:.1f}" '
                       f'x2="{px + post:.1f}" y2="{base - h + i * h / 4:.1f}" '
                       f'stroke="{LINE}" stroke-width=".4" opacity=".3"/>')
    inner = (w - post * 2) / 2
    if tier >= 2:
        out.append(f'<path d="M{x - inner:.1f},{base:.1f} L{x - inner:.1f},'
                   f'{base - h * 0.5:.1f} A{inner:.1f},{inner:.1f} 0 0 1 '
                   f'{x + inner:.1f},{base - h * 0.5:.1f} L{x + inner:.1f},{base:.1f} Z" '
                   f'fill="#2a1c12" opacity=".55" stroke="{LINE}" stroke-width="1"/>')
    out.append(f'<path d="M{x - inner:.1f},{base - h * 0.5:.1f} '
               f'A{inner:.1f},{inner:.1f} 0 0 1 {x + inner:.1f},{base - h * 0.5:.1f}" '
               f'fill="none" stroke="{LINE}" stroke-width="1.5"/>')
    out.append(_rect(x - w / 2 - 1.8, base - h - 3.8, w + 3.6, 4.0, fill=colour, width=1))
    if tier >= 3:  # a keystone medallion in the arch
        out.append(f'<circle cx="{x:.1f}" cy="{base - h - 6.6:.1f}" r="3.0" '
                   f'fill="{colour}" stroke="{LINE}" stroke-width="1"/>')
    if tier >= 5:  # a portcullis and torches
        for i in range(3):
            out.append(f'<line x1="{x - inner:.1f}" y1="{base - 2 - i * 3:.1f}" '
                       f'x2="{x + inner:.1f}" y2="{base - 2 - i * 3:.1f}" '
                       f'stroke="{WALL}" stroke-width=".6" opacity=".7"/>')
        for side in (-1, 1):
            out.append(_lantern(x + side * (w / 2 - post / 2), base - h * 0.62, 1.9))
    if tier >= 6:  # figures standing on the lintel, and banners hung from it
        for side in (-1, 1):
            sx = x + side * w * 0.3
            out.append(f'<circle cx="{sx:.1f}" cy="{base - h - 8:.1f}" r="1.9" '
                       f'fill="{WALL}" stroke="{LINE}" stroke-width=".8"/>')
            out.append(f'<path d="M{sx - 2.2:.1f},{base - h - 3.8:.1f} '
                       f'Q{sx - 2.2:.1f},{base - h - 6.4:.1f} {sx:.1f},'
                       f'{base - h - 6.4:.1f} Q{sx + 2.2:.1f},{base - h - 6.4:.1f} '
                       f'{sx + 2.2:.1f},{base - h - 3.8:.1f} Z" fill="{WALL}" '
                       f'stroke="{LINE}" stroke-width=".8"/>')
        for side in (-1, 1):
            bx = x + side * w * 0.16
            out.append(f'<path d="M{bx - 2.2:.1f},{base - h + 0.2:.1f} '
                       f'L{bx + 2.2:.1f},{base - h + 0.2:.1f} L{bx + 2.2:.1f},'
                       f'{base - h + 11:.1f} L{bx:.1f},{base - h + 9:.1f} '
                       f'L{bx - 2.2:.1f},{base - h + 11:.1f} Z" fill="{colour}" '
                       f'stroke="{LINE}" stroke-width=".7"/>')
    return "".join(out)


SHAPES = {
    "inn": _inn, "hall": _hall, "keep": _keep, "chapel": _chapel,
    "pen": _pen, "works": _works, "stage": _stage, "monument": _monument,
    "gate": _gate,
}
def family_height(family: str, tier: int) -> float:
    """Roughly how tall a family stands at a tier, in the town's own units.

    Needed because the emblem hangs *over* its building and the flag flies from
    the top of the tallest one, and both were using a single formula for every
    family. A tier-six inn is nearly fifty units tall with its upper storey and
    its roof; the emblem was hung at thirty-nine and landed on the front wall
    like a sticker. Estimated rather than measured: the shapes are built out of
    string concatenation, so there is nothing to measure without parsing the
    SVG back, and being a couple of units generous costs nothing.
    """
    tier = max(1, min(6, int(tier)))
    if family == "inn":
        base = 8 + tier * 2.4
        return base + (base * 1.12 if tier >= 4 else base * 0.45) + (9 if tier >= 6 else 0)
    if family == "hall":
        base = 9 + tier * 3.2
        return base + base * 0.34 + (base * 0.4 if tier >= 5 else 0)
    if family == "keep":
        base = 10 + tier * 2.6
        if tier >= 6:
            return base * 1.85 + 14
        return base + (base * 0.2 if tier >= 3 else 4)
    if family == "chapel":
        return (11 + tier * 3.4) + (9 + tier * 3.2) + (6 if tier >= 6 else 0)
    if family == "pen":
        return max(6 + tier * 1.5 + 6, 7 + tier * 0.6, 20 if tier >= 6 else 0)
    if family == "works":
        base = 8 + tier * 2.4
        return base + 7 + tier * 1.7 + (3 if tier >= 4 else 0)
    if family == "stage":
        base = 11 + tier * 3.0
        return base + 4 + (base * 0.31 if tier >= 6 else 0)
    if family == "monument":
        return 2.2 * (1 + min(3, tier)) + (9 + tier * 3.6) + 10
    if family == "gate":
        return (13 + tier * 3.2) + 4 + (3 if tier >= 3 else 0)
    return 12 + tier * 4.0


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


# --------------------------------------------------------------------------- #
#  Laying a town out
# --------------------------------------------------------------------------- #
# The old layout was seven fixed slots in a narrow band across the middle of the
# plate. It had two consequences and both were visible from across the room: a
# town never used more than about half its own ground, and a settlement with
# seven buildings looked like a settlement with three, because they all landed
# on top of each other in the same place.
#
# What replaces it is laid out the way a small town actually is.
#
# **A centre, and streets in front of it.** The grandest building stands at
# mid-depth on the axis — near enough to be drawn large, far enough that things
# can stand in front of it. Everything else fans out in bands: a back row
# (small, high, drawn first), a wide middle, and a near row that overlaps the
# rest. That ordering is the whole illusion of depth.
#
# **The ground grows with the town.** A hamlet sits on a small plate; a capital
# gets a plate wide enough to hold what is on it. A fixed plate meant a big town
# was crowded and a small one was marooned in the middle of an empty field.
#
# **Ordinary houses fill the gaps.** The buildings somebody earned are the
# landmarks; a town is mostly the houses between them. Their number comes from
# reach — how many different people that person actually reached — so the town
# of the most connected person on the server is visibly the busiest place on the
# map, which is exactly what DodoLand claims to be measuring.

# (depth, sideways) per earned building, in the order they are handed out.
# Depth runs 0 at the back to 1 at the front; sideways is a fraction of the
# plate's half-width at that depth, so nothing stands off its own ground.
# Fixed rather than seeded, so a town does not rearrange itself between two
# page loads.
_PLOTS = (
    (0.46,  0.00),   # the centrepiece: mid-depth, on the axis
    (0.13, -0.46),   # back left
    (0.13,  0.48),   # back right
    (0.86, -0.60),   # front left, overlapping the middle
    (0.86,  0.56),   # front right
    (0.52, -0.94),   # the far edges of the middle band
    (0.52,  0.92),
)

# Where ordinary houses go. Deliberately not the same band as the landmarks:
# they crowd the near edges and the back skyline, which is where a town's own
# housing sits relative to its civic buildings.
def _density(count: int, richness: float) -> float:
    """How full a town is, 0 to 1: what it has built and who it reached."""
    built = min(1.0, count / float(MAX_BUILDINGS))
    return max(0.0, min(1.0, 0.45 * built + 0.55 * max(0.0, min(1.0, richness))))


# The widest the ground may ever be drawn, as a fraction of the town's width.
# Everything a town draws has to fit the 120x78 box it is given: on the map
# those boxes sit side by side and anything wider is painted over the
# neighbours. A big town therefore grows *denser*, not wider — which is also
# how a real one grows once it has run out of land.
MAX_PLATE = 0.41


def _plate(density: float, houses: int = 0) -> float:
    """Half-width of the ground, as a fraction of the town's width."""
    return min(MAX_PLATE, 0.30 + 0.09 * density + min(0.05, houses / 900.0))


PLATE_CY = GROUND_Y + 3.0


def _plate_ry(density: float) -> float:
    """Half the ground's depth, front to back."""
    return 8.0 + density * 2.0


def _stand(depth: float, plate: float = 0.40,
           ry: float = 9.0) -> tuple[float, float, float]:
    """Ground line, half-width and scale at a depth on the plate.

    **Both come from the plate's own ellipse.** They used to be straight lines:
    the ground ran from six units above the plate's centre to six below it while
    the plate itself ran ten either way, so the whole front of a town was bare
    sand; and the width grew linearly with depth, which is a trapezoid, so the
    built area and the ground it stood on were different shapes. Between them
    that left a third of every plate unused, at the front and around the back
    corners, which is exactly where it looked emptiest.

    Depth 0 is the plate's far edge and 1 is its near edge.

    Everything about the perspective is still shallow on purpose. This is a map
    pictogram, not a render: enough depth to read as a place, not enough to look
    like it is falling over.
    """
    across = depth * 2.0 - 1.0                       # -1 at the back, +1 in front
    y = PLATE_CY + across * ry * 0.94
    # The ellipse's own half-width at that line, so a building at the back
    # stands on ground that is actually there.
    frac = max(0.16, (1.0 - across * across) ** 0.5)
    half = WIDTH * plate * 1.06 * frac
    scale = 0.62 + 0.38 * depth
    return y, half, scale


def _house_spots(count: int) -> list[tuple[float, float]]:
    """``(depth, sideways)`` for ``count`` ordinary houses, laid out in rings.

    Generated rather than chosen from a list. The list held eighteen positions,
    which meant a town connected to sixty people and one connected to three
    hundred both filled it and looked identical — the single loudest thing
    wrong with the map, because reach is what DodoLand actually measures and it
    was the one quantity a town could not show.

    Houses sit in the annulus **outside** the landmark band: the buildings
    somebody earned hold the middle, and the housing rings them. Angles step by
    the golden angle so no number of houses lands in spokes, and radius steps
    by a square root so the rings stay evenly dense rather than piling up at
    the edge.
    """
    if count <= 0:
        return []
    spots = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for index in range(count):
        # 0.56 keeps the innermost ring clear of the landmarks; the outer edge
        # runs slightly past the plate so a big town's houses reach its shore.
        radius = 0.56 + 0.50 * math.sqrt((index + 0.5) / count)
        angle = index * golden
        sideways = math.cos(angle) * radius
        # Depth from the same circle, so the ring reads as a ring in
        # perspective rather than as a line of houses at one distance.
        depth = 0.5 + 0.46 * math.sin(angle) * radius
        spots.append((max(0.02, min(1.0, depth)), sideways))
    return spots


def _houses(count: int, plate: float, uid: str = "t",
            ry: float = 9.0) -> list[tuple]:
    """``(y, x, scale, svg)`` for the ordinary houses between the landmarks."""
    seed = int(hashlib.sha1(f"h{uid}".encode("utf-8")).hexdigest()[:8], 16)
    out = []
    for index, (depth, sideways) in enumerate(_house_spots(count)):
        y, half, scale = _stand(depth, plate, ry)
        spin = (seed >> (index * 5 % 20)) & 0x3FF
        # Houses are smaller than landmarks at the same depth, or the landmarks
        # stop being landmarks.
        roof, wall = HOUSE_COLOURS[spin % len(HOUSE_COLOURS)]
        out.append((y, WIDTH / 2 + sideways * half, scale * HOUSE_SCALE,
                    _cottage(0.0, 0.0, 6.4 + (spin % 5) * 0.7, roof,
                             variant=(spin // 7) % 6, wall=wall)))
    return out


# Roofs and walls, paired. Only the roof was ever coloured and every wall was
# the same cream, so sixty houses came out as sixty copies of one house in
# seven shades of brown — which is what they looked like.
HOUSE_COLOURS = (
    ("#b0724a", "#f6efe2"),   # tile on cream
    ("#8f5f42", "#e8dcc6"),   # dark tile on stone
    ("#9c6b4b", "#f2e4cd"),
    ("#7d5a6b", "#efe6e8"),   # slate on limewash
    ("#5f7a6b", "#e9efe6"),   # mossy on pale green
    ("#a8663f", "#fbf3e4"),
    ("#6b6f86", "#e6e8f0"),   # blue slate on grey
    ("#96613f", "#f0e0c4"),
)


def _defs(uid: str, colour: str) -> str:
    """Gradients this town's effects draw with.

    SVG gradients rather than CSS filters, deliberately: a filter inside the
    zoomed world rasterises whatever it touches, and the grandest buildings were
    the first to turn to mush when that was tried. A gradient stays vector at
    every zoom, which is the only way the top of the ladder can look like the
    top of the ladder.

    Ids carry the town's own suffix. Without that every town on the map shares
    one set of gradients and they all take the colour of whichever drew last.
    """
    return (
        f'<defs>'
        # A soft wash, for auras and warmed ground.
        f'<radialGradient id="au{uid}">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity=".85"/>'
        f'<stop offset="55%" stop-color="{colour}" stop-opacity=".28"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        f'</radialGradient>'
        # A standing beam of light, fading out at both ends.
        f'<linearGradient id="bm{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity="0"/>'
        f'<stop offset="45%" stop-color="{colour}" stop-opacity=".55"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        f'</linearGradient>'
        # The ring's own gradient, so a flourish is not a flat hoop of colour.
        # This is the single change that does the most for how rank reads: the
        # ring was one stroke at one opacity, which is why the top of the trial
        # ladder looked like a highlighter mark round a puddle.
        f'<linearGradient id="rg{uid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity=".15"/>'
        f'<stop offset="28%" stop-color="{colour}" stop-opacity="1"/>'
        f'<stop offset="50%" stop-color="#ffffff" stop-opacity=".85"/>'
        f'<stop offset="72%" stop-color="{colour}" stop-opacity="1"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity=".15"/>'
        f'</linearGradient>'
        # The sun's rays, brightest at the middle of their length.
        f'<linearGradient id="ry{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity="0"/>'
        f'<stop offset="60%" stop-color="{colour}" stop-opacity=".55"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity=".05"/>'
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

      4  the ground warms under it, and dust drifts across it
      5  it lifts, embers rise off the roof, an aura settles over it
      6  it hovers over its own shadow, wrapped in a ring of light with motes
         going round it and a beam standing over the whole thing

    Opacity, transform and gradients only. A CSS filter in here would rasterise
    the building it touches. Opacity is reserved for **light** — glows, halos,
    embers. Masonry, animals, water and rock never fade: a building that blinks
    reads as broken rather than as grand, and it was being applied to ponds.
    """
    tier = max(1, min(6, int(tier)))
    behind, front = "", ""

    if tier >= 4:  # the ground warms
        behind += _fx(f'<ellipse class="bglow" cx="0" cy="-1" rx="{12 + tier * 2.4:.0f}" '
                      f'ry="{6 + tier:.0f}" fill="url(#au{uid})"/>')
        # Motes of dust drifting across the warm ground: particles rather than
        # another thing fading in and out.
        for i in range(3):
            front += _fx(f'<circle class="drift d{i + 1}" cx="{-10 + i * 9}" cy="-3" '
                         f'r="{0.8 + i * 0.2:.1f}" fill="{colour}" opacity=".5"/>')

    if tier >= 5:  # an aura, and embers off the roof
        behind += _fx(f'<circle class="baura" cx="0" cy="{-12 - tier * 2:.0f}" '
                      f'r="{16 + tier * 2:.0f}" fill="url(#au{uid})" opacity=".5"/>')
        for i in range(5):
            front += _fx(f'<circle class="spark s{i + 1}" cx="{-8 + i * 4}" '
                         f'cy="{-14 - tier * 3}" r="{1.1 + (i % 3) * 0.25:.1f}" '
                         f'fill="{colour}"/>')

    if tier == 6:  # it leaves the ground
        # A shadow where it used to stand, and the building itself lifted: the
        # single clearest way to say "this is the top" without a label.
        behind += _fx(f'<ellipse class="bshadow" cx="0" cy="2" rx="14" ry="4" '
                      f'fill="#2a1c12" opacity=".45"/>')
        # Tall, but not taller than the town's own box: at ninety-two units in
        # a seventy-eight unit box this ran up out of the frame, and on the map
        # a town paints over whatever is above it.
        behind += _fx(f'<rect class="bbeam" x="-5" y="-62" width="10" height="62" '
                      f'fill="url(#bm{uid})"/>')
        behind += _fx(f'<ellipse class="bring" cx="0" cy="{-16 - tier * 2:.0f}" '
                      f'rx="{20 + tier:.0f}" ry="7" fill="none" stroke="{colour}" '
                      f'stroke-width="1.3" opacity=".7"/>')
        # Two motes going round the ring rather than sitting on it.
        front += _fx(f'<g class="orbit">'
                     f'<circle cx="{20 + tier:.0f}" cy="{-16 - tier * 2:.0f}" r="2" '
                     f'fill="{colour}"/>'
                     f'<circle cx="{-(20 + tier):.0f}" cy="{-16 - tier * 2:.0f}" r="1.5" '
                     f'fill="{colour}" opacity=".8"/></g>')
    return behind, front


# --------------------------------------------------------------------------- #
#  Life
# --------------------------------------------------------------------------- #
# Twelve walking routes, assigned per inhabitant from a hash of the town and
# their index. Two things this fixes at once: everybody was walking one of two
# routes, so a crowd moved like a chorus line, and animals almost never
# appeared because the six available spots filled up with people first.
WALK_ROUTES = 12

# How large an inhabitant is drawn, relative to the depth scale everything else
# on the plate uses. Houses carry their own 0.52 and the walkers carried none,
# so a townsperson came out two and a half times the height of the house they
# were standing next to. A person should be roughly half the height of a
# cottage door-to-eaves, which is what this lands on.
WALKER_SCALE = 0.20
# Cottages grew with it: at the old size a house was under three units tall and
# nothing could be in proportion to it without vanishing.
HOUSE_SCALE = 0.62


def _life(rows: list[dict], shapes: dict, *, richness: float = 0.0,
          plate: float = 0.40, uid: str = "t", ry: float = 9.0) -> str:
    """Creatures and people wandering the town, drawn from what stands there.

    A menagerie brings animals, an inn brings drinkers, a chapel brings birds.
    A town with a zoo in it and nothing moving is a shed with a fence around it.

    How many there are is reach: the most connected person on the server should
    have the busiest streets on the map, because that is the one thing DodoLand
    actually measures.
    """
    # Every family that stands here contributes its own inhabitants, and each
    # family gets at least one — so a menagerie always puts an animal out even
    # in a town full of taverns.
    pools: list[tuple[str, tuple]] = []
    for row in rows:
        family = shapes.get(str(row.get("key") or "")) or DEFAULT_SHAPE
        pools.append((family, LIFE.get(family) or DEFAULT_LIFE))
    if not pools:
        pools = [(DEFAULT_SHAPE, DEFAULT_LIFE)]

    crowd = 3 + int(round(11 * max(0.0, min(1.0, richness))))
    seed = int(hashlib.sha1(str(uid).encode("utf-8")).hexdigest()[:8], 16)

    out = []
    for index in range(crowd):
        family, pool = pools[index % len(pools)]
        # One from each family in turn before any family gets a second, so a
        # town's animals are never crowded out by its drinkers.
        name = pool[(index // len(pools)) % len(pool)]
        draw = WANDERERS.get(name) or _person
        # Spread over the whole plate rather than a fixed list of six spots.
        # Deterministic from the town's id: the same town looks the same on
        # every load, and two towns do not look like the same town.
        spin = (seed >> (index * 3 % 24)) & 0xFFF
        depth = 0.18 + ((spin % 79) / 79.0) * 0.80
        sideways = -1.0 + (((spin // 79) % 89) / 89.0) * 2.0
        y, half, scale = _stand(depth, plate, ry)
        x = WIDTH / 2 + sideways * half * 0.92
        route = 1 + (spin % WALK_ROUTES)
        body = draw(WALKER_COLOURS[spin % len(WALKER_COLOURS)],
                    **({"hat": spin % 3} if name == "person" else {}))
        out.append(
            f'<g class="walker r{route}" transform="translate({x:.1f},{y:.1f}) '
            f'scale({scale * WALKER_SCALE:.3f})">'
            f'<g class="gait">{body}</g></g>')
    return "".join(out)


# --------------------------------------------------------------------------- #
#  What goes on around a building
# --------------------------------------------------------------------------- #
# The spectacle used to be one enormous turning sun and a hoop the width of the
# settlement, drawn over the whole town regardless of what was in it. Every town
# on the map got the same object hanging over it, it said nothing about the
# place underneath, and at a glance it read as weather rather than as somebody's
# town.
#
# What replaces it is **topical and local**: things that belong to the building
# they belong to, orbiting or rising around that building. A tavern has mugs and
# music over it, a library has pages, a forge throws sparks, a menagerie has
# butterflies and leaves, a chapel has birds. You can tell what a place is from
# across the map by what is flying around it, which is the job the emblem was
# doing alone.
#
# Each entry is (icon name, how it moves, size). ``orbit`` goes round the
# building, ``rise`` lifts off it and fades, ``flit`` drifts side to side.
BUILDING_FX: dict[str, tuple[tuple[str, str, float], ...]] = {
    "inn":      (("mug", "rise", 4.6), ("music", "orbit", 4.0),
                 ("hotmug", "rise", 4.2)),
    "hall":     (("book", "orbit", 4.4), ("scroll", "rise", 4.0),
                 ("feather", "flit", 4.2)),
    "keep":     (("shield", "orbit", 4.6), ("bolt", "rise", 3.8)),
    "chapel":   (("bird", "orbit", 4.4), ("star", "rise", 3.4),
                 ("bell", "flit", 4.0)),
    "pen":      (("bug", "flit", 3.8), ("leaf", "rise", 4.0),
                 ("seedling", "orbit", 4.0)),
    "works":    (("gear", "orbit", 4.6), ("fire", "rise", 4.0),
                 ("hammer", "flit", 4.2)),
    "stage":    (("music", "rise", 4.4), ("masks", "orbit", 4.6),
                 ("star", "flit", 3.6)),
    "monument": (("star", "orbit", 4.0), ("gem", "rise", 3.8)),
    "gate":     (("key", "orbit", 4.2), ("compass", "flit", 4.0)),
}


def _building_fx(family: str, tier: int, colour: str, symbol: str = "") -> str:
    """Things belonging to this building, moving around it. Close up only.

    How many arrive is the tier, so the climb is still legible: a shed has one,
    a wonder has the lot. The building's own emblem joins in at the top, which
    is what makes a Dodo statue's flourish actually dodos.
    """
    tier = max(1, min(6, int(tier)))
    if tier < 2:
        return ""
    pool = list(BUILDING_FX.get(family) or BUILDING_FX["inn"])
    if tier >= 5 and symbol and symbol in EMBLEMS:
        pool.append((symbol, "orbit", 4.4))

    how_many = min(len(pool) * 2, tier - 1)
    out = []
    for index in range(how_many):
        name, motion, size = pool[index % len(pool)]
        lane = index // len(pool)
        if motion == "orbit":
            # Round the building, in its own group so the rotation has a centre.
            radius = 15 + tier * 1.6 + lane * 5
            # Each icon sits in its own `upright` group, which the stylesheet
            # turns backwards at exactly the speed the orbit turns forwards.
            # Without it the icon tumbles with the orbit and spends half of
            # every circuit upside down — which is what a music note over a
            # playhouse was doing.
            lead = icon(name, size, colour, cx=0, cy=0)
            trail = icon(name, size * 0.8, colour, cx=0, cy=0)
            out.append(
                f'<g class="fxorbit o{index % 4 + 1}">'
                f'<g transform="translate({radius:.1f},{-(12 + tier * 2.2):.1f})">'
                f'<g class="upright">{lead}</g></g>'
                f'<g transform="translate({-radius * 0.72:.1f},'
                f'{-(20 + tier * 2.6):.1f})">'
                f'<g class="upright">{trail}</g></g>'
                f'</g>')
        elif motion == "rise":
            out.append(f'<g class="fxrise u{index % 4 + 1}">'
                       f'{icon(name, size, colour, cx=-4 + index * 5, cy=-(16 + tier * 3))}'
                       f'</g>')
        else:  # flit
            out.append(f'<g class="fxflit f{index % 3 + 1}">'
                       f'{icon(name, size, colour, cx=6 - index * 7, cy=-(10 + tier * 2))}'
                       f'</g>')
    return _fx("".join(out))


def _flourish(level: int, colour: str, uid: str, plate: float) -> str:
    """What a trial rank does to a whole town. Cosmetic, always, by design.

    Deliberately quiet now, and low to the ground. It used to be a turning sun
    the width of the settlement with a hoop orbiting it, which every town got
    regardless of what stood in it — the same object hanging over three hundred
    different places, saying nothing about any of them.

    Rank belongs *under* a town, not over it. What it does:

      1  the ground warms
      2  lanterns come up around the edge of the plate
      3  a low band of light hugs the shore
      4  the band gains a second, wider one and a gradient sheen
      5  motes lift off the ground around the town
      6  the whole plate is lit from beneath, and the light moves

    The character of a town comes from what is *in* it — see ``BUILDING_FX``,
    which puts a tavern's mugs and a forge's sparks around the tavern and the
    forge. This is the frame; those are the picture.
    """
    if level <= 0:
        return ""
    level = min(6, int(level))
    cx, cy = WIDTH / 2, GROUND_Y + 3
    rx = WIDTH * (plate + 0.05)
    out = [f'<ellipse class="flwash" cx="{cx:.1f}" cy="{cy - 3:.1f}" '
           f'rx="{rx * 1.00:.1f}" ry="{rx * 0.24:.1f}" '
           f'fill="url(#au{uid})" opacity="{0.22 + level * 0.06:.2f}"/>']

    if level >= 2:  # lanterns standing around the edge of the plate
        for i in range(3 + level):
            angle = math.pi * (i + 0.5) / (3 + level)
            lx = cx - rx * 0.94 * math.cos(angle)
            ly = cy + rx * 0.26 * math.sin(angle)
            out.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx:.1f}" '
                       f'y2="{ly - 6:.1f}" stroke="{LINE}" stroke-width=".9"/>')
            out.append(_lantern(lx, ly - 7, 1.5))
    if level >= 3:  # a low band of light along the shore
        out.append(f'<ellipse class="flring" cx="{cx:.1f}" cy="{cy + 1:.1f}" '
                   f'rx="{rx:.1f}" ry="{rx * 0.19:.1f}" fill="none" '
                   f'stroke="url(#rg{uid})" stroke-width="{1.2 + level * 0.45:.1f}" '
                   f'stroke-linecap="round"/>')
    if level >= 4:
        out.append(f'<ellipse class="flring2" cx="{cx:.1f}" cy="{cy + 2:.1f}" '
                   f'rx="{rx * 1.06:.1f}" ry="{rx * 0.22:.1f}" fill="none" '
                   f'stroke="url(#rg{uid})" stroke-width="{level * 0.35:.1f}" '
                   f'opacity=".5"/>')
    if level >= 5:  # motes lifting off the ground, not orbiting overhead
        for i in range(5):
            out.append(_fx(f'<circle class="spark s{i + 1}" '
                           f'cx="{cx - rx * 0.7 + i * rx * 0.35:.1f}" '
                           f'cy="{cy - 2:.1f}" r="{1.3 + (i % 2) * 0.5:.1f}" '
                           f'fill="{colour}"/>'))
    if level >= 6:  # the plate itself lit from underneath
        out.insert(0, f'<ellipse class="flunder" cx="{cx:.1f}" cy="{cy + 3:.1f}" '
                      f'rx="{rx * 1.10:.1f}" ry="{rx * 0.26:.1f}" '
                      f'fill="url(#au{uid})" opacity=".7"/>')
    return "".join(out)


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
    # Small: it flies over one building, not over the county. The pole is a
    # third the height of a tier-six keep so it reads as a flag rather than a
    # billboard somebody parked on the town.
    return (
        f'<g class="townflag">'
        f'<defs><clipPath id="fg{uid}">'
        f'<path d="M0,-17 L13,-15 L13,-7 L0,-9 Z"/></clipPath></defs>'
        f'<line x1="0" y1="0" x2="0" y2="-18" stroke="{LINE}" stroke-width="1"/>'
        f'<circle cx="0" cy="-18.6" r="1" fill="{LINE}"/>'
        f'<g class="cloth">'
        f'<image href="{url}" x="0" y="-17" width="13" height="10" '
        f'preserveAspectRatio="xMidYMid slice" clip-path="url(#fg{uid})"/>'
        f'<path d="M0,-17 L13,-15 L13,-7 L0,-9 Z" fill="none" stroke="{LINE}" '
        f'stroke-width=".8"/></g></g>'
    )


def town_svg(buildings: Iterable[dict], *, lit: bool = True,
             flourish: int = 0, glow: str = "", richness: float = 0.0,
             houses: int = 0,
             uid: str = "t", flag: str = "", shapes: Optional[dict] = None,
             symbols: Optional[dict] = None,
             colours: Optional[dict] = None) -> str:
    """A whole settlement as an SVG fragment.

    ``buildings`` are ``{"key", "tier"}`` in any order. The grandest stands at
    mid-depth on the axis and the rest fan out around it in bands, drawn back to
    front so the near ones overlap the far ones. A town with nothing built is a
    single tent, not an empty patch: somebody who has just arrived should still
    be somewhere.

    ``richness`` is how many different people this person reached, normalised to
    0-1 by the caller. It is the one number that changes the *town* rather than
    any building in it: the ground grows, ordinary houses fill in between the
    landmarks, and the streets get busier. That is deliberate — reach is what
    DodoLand actually measures, and until now it was the one thing a town never
    showed.

    ``colours`` overrides the colour of individual buildings, so an owner can
    paint their own town. Anything absent falls back to the stable hash, which
    is what keeps two towns from being the same beige.
    """
    rows = sorted(buildings, key=lambda b: -int(b.get("tier", 1)))[:MAX_BUILDINGS]
    shapes = shapes or {}
    colours = colours or {}
    symbols = symbols or {}
    # Gradient ids must be unique per town or every town on the map shares one
    # set of gradients and they all take the colour of whichever drew last.
    uid = "".join(c for c in str(uid) if c.isalnum()) or "t"

    richness = max(0.0, min(1.0, float(richness or 0.0)))
    houses = max(0, int(houses or 0))
    # The ground has to hold what stands on it. A town of eighty houses on the
    # same plate as a town of eight is the same crowding problem the fixed
    # layout had, one level up.
    density = _density(len(rows), richness)
    plate = _plate(density, houses)
    plate_ry = _plate_ry(density)

    parts = [
        _defs(uid, glow or "#ffd27f"),
        # The ground, which grows with the town.
        f'<ellipse cx="{WIDTH / 2:.1f}" cy="{PLATE_CY:.1f}" '
        f'rx="{WIDTH * plate * 1.16:.1f}" ry="{plate_ry * 1.1:.1f}" '
        f'fill="#cdb894" stroke="#a68f6a" stroke-width="1.4"/>',
        f'<ellipse cx="{WIDTH / 2:.1f}" cy="{PLATE_CY - 0.8:.1f}" '
        f'rx="{WIDTH * plate * 1.06:.1f}" ry="{plate_ry * 0.9:.1f}" '
        f'fill="#ddcaa6"/>',
    ]

    standing: list[tuple] = []
    if not rows:
        cx = WIDTH / 2
        parts.append(_tri(cx - 9, GROUND_Y + 2, cx, GROUND_Y - 13, cx + 9,
                          GROUND_Y + 2, "#b98b4e"))
    else:
        # The plot table alternates left and right, so an *odd* number of
        # buildings is balanced and an even one is not: four landed with their
        # centre of mass a sixth of the plate to the left, which read as the
        # town huddling in one corner while its housing spilled off the other
        # side. Shifting the whole group back by its own centre of mass costs
        # nothing and centres every count.
        used = [_PLOTS[i % len(_PLOTS)] for i in range(len(rows))]
        drift = sum(sideways for _depth, sideways in used) / len(used)
        for index, row in enumerate(rows):
            depth, sideways = used[index]
            y, half, scale = _stand(depth, plate, plate_ry)
            standing.append((y, WIDTH / 2 + (sideways - drift) * half, scale, row))

    # Ordinary houses, from reach. Placed with the landmarks and sorted into the
    # same painter's order, so a cottage in front of the keep is in front of the
    # keep rather than layered on top of the whole town.
    drawn: list[tuple] = []
    if rows:
        drawn.extend(_houses(houses, plate, uid, plate_ry))

    # Which building flies the town's banner, decided before anything is drawn
    # so the flag can be built into that building rather than parked over it.
    bearer = (max(standing, key=lambda item: int(item[3].get("tier", 1)))[3]
              if (flag and standing) else None)

    for y, x, scale, row in standing:
        key = str(row.get("key") or "")
        family = shapes.get(key) or DEFAULT_SHAPE
        draw = SHAPES.get(family, _inn)
        tier = int(row.get("tier", 1))
        tint = colours.get(key) or colour_for(key)
        mark = symbols.get(key) or ""
        behind, front = _tier_effects(tier, tint, uid)
        # What belongs to this building, moving around this building: a
        # tavern's mugs, a forge's sparks, a menagerie's butterflies. This is
        # what the town-wide sun used to be, and it says something about the
        # place rather than the same thing about every place.
        front += _building_fx(family, tier, tint, mark)
        mass = draw(0.0, 0.0, tier, tint, mark)
        # Everything that is *part of the building* — its emblem, and its flag
        # if it is the one flying the town's banner — is assembled here and
        # lifted with it. They used to be added outside the hovering group, so
        # a tier-six building rose off the ground and left its own medallion and
        # its own flag hanging in the air behind it.
        attached = ""
        if mark:
            # The emblem hangs over its building as a medallion: the masonry
            # says what kind of place it is, the emblem says what it is *for*.
            # Far bigger than it used to be, and knocked out of a coloured disc
            # rather than tinted the same colour as the roof behind it — at the
            # old size and contrast it took real effort to tell a mug from a
            # book.
            # Just clear of the roof, using the same height estimate the flag
            # flies from. Sized to read and no larger: at eighteen percent of
            # the town's width it stopped being a sign on a building and became
            # a badge with a building behind it.
            size = 5.6 + tier * 0.85
            want = -(family_height(family, tier) + 5 + tier * 0.7)
            # In the lot's own coordinates, so the clamp has to account for
            # where the lot stands and how far back it is.
            ceiling = (3.0 - y) / scale + size * 0.62
            attached += _emblem(0.0, max(want, ceiling), mark, size, tint, tier)
        if bearer is not None and row is bearer:
            # Flown from the grandest building rather than parked at the edge of
            # the plate: a town's banner belongs over its centrepiece, and the
            # centrepiece is whatever it has built highest.
            attached += (f'<g transform="translate(7,'
                         f'{-family_height(family, tier):.1f})">'
                         f'{banner(flag, uid)}</g>')
        if tier == 6:
            # Detached from the ground, hovering over the shadow drawn for it.
            # Straight out of the original design, and the thing that makes
            # somebody ask how a town got like that.
            mass = f'<g class="lifted">{mass}{attached}</g>'
        else:
            mass += attached
        art = behind + mass + front
        drawn.append((y, x, scale, art))

    # Painter's algorithm: the far ones first, so the near ones cover them.
    drawn.sort(key=lambda item: item[0])
    for y, x, scale, art in drawn:
        # Drawn at the origin and moved into place, so one transform carries
        # both where it stands and how near it is.
        parts.append(f'<g class="lot" transform="translate({x:.1f},{y:.1f}) '
                     f'scale({scale:.2f})">{art}</g>')

    if rows:
        parts.append(_life(rows, shapes, richness=richness, plate=plate,
                           uid=uid, ry=plate_ry))
    if flag and not standing:
        parts.append(f'<g transform="translate({WIDTH * 0.5:.1f},'
                     f'{GROUND_Y - 6:.1f})">{banner(flag, uid)}</g>')

    body = "".join(parts)
    if flourish:
        # The rank's own colour where the server has one, so a Legend glows the
        # colour a Legend already is in the member list. An invented palette
        # made every high rank lilac and told nobody anything.
        body = _flourish(int(flourish), glow or "#ffd27f", uid, plate) + body
    if not lit:
        body = f'<g opacity=".45">{body}</g>'
    return body


def one_svg(shape: str, tier: int, colour: Optional[str] = None,
            symbol: str = "") -> str:
    """A single building on its own, for previews and the buildings editor."""
    draw = SHAPES.get(shape or DEFAULT_SHAPE, _inn)
    return draw(WIDTH / 2, GROUND_Y, max(1, min(6, int(tier))),
                colour or PALETTE[0], symbol)
