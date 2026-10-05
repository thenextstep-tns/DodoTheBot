"""
The thirty-two colours DodoLand is drawn with.

A tight shared palette is what makes a hundred separate objects look like one
world. The first version of the town art let every building pick its own colour
and fifteen buildings in eight colours read as confetti; the answer was never
*fewer* colours, it was a disciplined set that everything draws from — terrain,
buildings, decor, and whatever an artist delivers later.

Thirty-two is the 8-bit convention and it is a real constraint rather than a
decorative one: it forces shading to be chosen rather than interpolated, which
is most of why pixel art stays legible at sixteen pixels across.

**Two scopes, and the split matters.**

*World* colours — water, ground, rock — belong to the server. One world, one sea.

*Town* colours — roofs, walls, trim, banners — belong to each town, which may
override them. A town recolouring its roofs is character. A town recolouring the
sea is a town that can hide itself from the map, so terrain is not offered.

Names are the stable thing. Everything downstream refers to a slot by name and
never to a hex value, so a server can retint its whole world by editing this
mapping and nothing else has to know.
"""

from __future__ import annotations

from typing import Optional

# --------------------------------------------------------------------------- #
#  The base ramp
# --------------------------------------------------------------------------- #
# Ordered by family, and within a family from dark to light, so a shading pair
# is always "the slot below" and never a lookup.
PALETTE: dict[str, str] = {
    # Neutrals and outlines. `ink` is the outline colour for everything.
    "ink":        "#1b1a21",
    "shadow":     "#2f2b3a",
    "slate":      "#4a4759",
    "stone_dark": "#6b6a7d",
    "stone":      "#8f8da3",
    "stone_lt":   "#b8b6c6",
    "cream":      "#e8e0cf",
    "white":      "#f7f3e8",
    # Water, deep to foam.
    "deep":       "#1d3b63",
    "sea":        "#2a5b8f",
    "shallow":    "#3f87b5",
    "river":      "#5fb3d4",
    "foam":       "#a8dced",
    # Ground.
    "sand":       "#e3c88f",
    "dirt":       "#9c7246",
    "mud":        "#6e4e30",
    "marsh":      "#5a7a4a",
    "grass_dark": "#2e6b3f",
    "grass":      "#46934f",
    "grass_lt":   "#7ab85c",
    # Timber.
    "wood_dark":  "#5a3b22",
    "wood":       "#8a5a30",
    "wood_lt":    "#c08a4e",
    # Roofs — the four a town picks between by default.
    "roof_red":   "#b5342e",
    "roof_blue":  "#2f5f9e",
    "roof_green": "#2f7a4f",
    "roof_gold":  "#c89a2a",
    # Accents, for banners, light and flourish.
    "gold":       "#f0c040",
    "fire":       "#e8702a",
    "blood":      "#8f2230",
    "royal":      "#6b3fa0",
    "rose":       "#d4568f",
}

SLOTS: tuple[str, ...] = tuple(PALETTE)

# What a town is allowed to repaint. Everything else is the world's.
TOWN_SLOTS: tuple[str, ...] = (
    "roof_red", "roof_blue", "roof_green", "roof_gold",
    "wood", "wood_dark", "wood_lt", "cream", "stone", "gold",
)


class PaletteError(ValueError):
    """A rejected palette edit, with a message meant for the panel."""


def _hex(value) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 7 or not text.startswith("#"):
        raise PaletteError(f"{value!r} is not a colour. Use #rrggbb.")
    try:
        int(text[1:], 16)
    except ValueError:
        raise PaletteError(f"{value!r} is not a colour. Use #rrggbb.") from None
    return text


def resolve(world: Optional[dict] = None, town: Optional[dict] = None) -> dict[str, str]:
    """The palette as one mapping, after the server's and the town's overrides.

    Order is deliberate: the base ramp, then whatever the server changed, then
    whatever this town changed — and a town may only reach the slots in
    :data:`TOWN_SLOTS`, so no amount of town-level editing can repaint the sea.
    """
    out = dict(PALETTE)
    for slot, colour in (world or {}).items():
        if slot in out:
            out[slot] = _hex(colour)
    for slot, colour in (town or {}).items():
        if slot in TOWN_SLOTS:
            out[slot] = _hex(colour)
    return out


def validate_overrides(values, *, town: bool = False) -> dict[str, str]:
    """Clean a set of overrides, refusing unknown or unreachable slots."""
    if not isinstance(values, dict):
        raise PaletteError("Palette overrides must be a mapping.")
    allowed = TOWN_SLOTS if town else SLOTS
    out: dict[str, str] = {}
    for slot, colour in values.items():
        slot = str(slot)
        if slot not in allowed:
            raise PaletteError(
                f"{slot!r} is not a colour a town may change."
                if town and slot in SLOTS else f"There is no {slot!r} colour.")
        if str(colour or "").strip():
            out[slot] = _hex(colour)
    return out


def shade(slot: str) -> str:
    """The slot one step darker, for the outline-and-shadow pass.

    Ramps are ordered dark to light within a family, so this is the previous
    slot — unless that would cross into another family, in which case the
    colour shades to ``ink`` like everything else.
    """
    families = (
        ("ink", "shadow", "slate", "stone_dark", "stone", "stone_lt", "cream", "white"),
        ("deep", "sea", "shallow", "river", "foam"),
        ("mud", "dirt", "sand"),
        ("grass_dark", "grass", "grass_lt"),
        ("wood_dark", "wood", "wood_lt"),
    )
    for ramp in families:
        if slot in ramp:
            index = ramp.index(slot)
            return ramp[index - 1] if index else slot
    return "shadow"
