"""
The whole world as one picture, for the map seen from far away.

Zoomed out, the map used to be an SVG of flat rectangles at one per eight
cells: correct, and ugly — a staircase coast in average colours, and the first
thing anyone saw. This draws the grid at **one pixel per cell** instead and
gives it the shading a printed map has, so it reads well before any tile is
close enough to be seen:

* **water** darkens with depth (how far it is from land) and catches a light
  line where it meets the shore;
* **land** has a soft darker edge along every coast, and a gentle large-scale
  variation so a meadow is not one flat colour across a continent;
* **impassable land** (mountains) gets relief: a height from its own shape and
  some noise, lit from the north-west;
* a faint grain everywhere, so the picture does not look like a diagram.

Everything is derived from the grid; nothing is invented on it. The browser
scales the picture smoothly, which is what turns a pixel staircase into a coast
at every zoom below the one where real tiles take over. Every effect has a
strength, from the server's settings, and 0 turns it off.

Pure numpy + Pillow, no scipy: distances are approximated with blurs and
dilations, which are fast C in Pillow and are all a picture needs.
"""

from __future__ import annotations

import io
from typing import Iterable

from helpers.dodoland import terrain as T
from helpers.dodoland import terrainart


def _rgb(colour: str) -> tuple[int, int, int]:
    text = str(colour or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except (ValueError, IndexError):
        return 128, 128, 128


def grid(chunks: dict, cells_w: int, cells_h: int):
    """The world's kind indices as one ``(h, w)`` array."""
    import numpy as np

    out = np.zeros((-(-cells_h // T.CHUNK) * T.CHUNK, -(-cells_w // T.CHUNK) * T.CHUNK), dtype=np.int16)
    for (cx, cy), cells in chunks.items():
        out[cy * T.CHUNK:(cy + 1) * T.CHUNK, cx * T.CHUNK:(cx + 1) * T.CHUNK] = \
            np.asarray(cells, dtype=np.int16).reshape(T.CHUNK, T.CHUNK)
    return out[:cells_h, :cells_w]


def _noise(rng, h: int, w: int, cell: int):
    """Smooth value noise in [-1, 1]: a coarse random field scaled up bicubically."""
    import numpy as np
    from PIL import Image

    small = rng.random((max(2, h // cell + 2), max(2, w // cell + 2))).astype("float32")
    image = Image.fromarray((small * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    return np.asarray(image, dtype="float32") / 127.5 - 1.0


def _blur(mask, radius: float):
    import numpy as np
    from PIL import Image, ImageFilter

    image = Image.fromarray((mask * 255).astype("uint8"))
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype="float32") / 255.0


def _grow(mask, times: int):
    import numpy as np
    from PIL import Image, ImageFilter

    image = Image.fromarray((mask * 255).astype("uint8"))
    for _ in range(times):
        image = image.filter(ImageFilter.MaxFilter(3))
    return np.asarray(image) > 127


def render(cells, kinds: list[dict], colours: dict, *, seed: int = 1,
           shading: float = 1.0, grain: float = 1.0):
    """``cells`` (the :func:`grid` array) as an RGB ``PIL.Image``, one pixel a cell."""
    import numpy as np
    from PIL import Image

    h, w = cells.shape
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    palette = np.array([_rgb(terrainart.kind_fill(k, colours)) for k in kinds] or [(0, 0, 0)],
                       dtype="float32")
    index = np.clip(cells, 0, len(palette) - 1)
    rgb = palette[index]

    is_water = np.array([bool(k.get("water")) for k in kinds] or [False])[index]
    unset = index == T.UNKNOWN
    land = ~is_water & ~unset
    rock = np.array([bool(k.get("move") is None and not k.get("water")) for k in kinds] or [False])[index] & land

    light = np.ones((h, w), dtype="float32")
    if shading > 0:
        # Depth: how much land is near, at two scales. Open sea far from any
        # coast is darkest; a lagoon among islands stays light.
        near = 0.6 * _blur(land, 6) + 0.4 * _blur(land, 28)
        depth = np.clip(1.0 - near * 3.0, 0.0, 1.0)
        light = np.where(is_water, 1.0 - 0.28 * shading * depth, light)
        # Surf: the first cells of water along a shore.
        shore = _grow(land, 1) & is_water
        rgb = np.where(shore[..., None], rgb + (255 - rgb) * 0.35 * min(1.0, shading), rgb)
        # The land's own edge, a touch darker, so a coast reads as a line.
        edge = land & _grow(is_water, 1)
        light = np.where(edge, light * (1.0 - 0.18 * shading), light)
        # Relief on impassable ground: height from its shape plus noise, lit
        # from the north-west.
        if rock.any():
            height = _blur(rock, 2.5) * (0.75 + 0.25 * _noise(rng, h, w, 6))
            gy, gx = np.gradient(height)
            lit = np.clip(-(gx + gy) * 6.0, -1.0, 1.0)
            light = np.where(rock, light * (1.0 + 0.35 * shading * lit), light)
        # Broad variation over land: no meadow is one flat colour for a
        # thousand cells.
        broad = 0.6 * _noise(rng, h, w, 96) + 0.4 * _noise(rng, h, w, 24)
        light = np.where(land, light * (1.0 + 0.045 * shading * broad), light)
    if grain > 0:
        speck = rng.standard_normal((h, w)).astype("float32")
        light = light * (1.0 + 0.025 * grain * np.where(land, speck, speck * 0.4))

    out = np.clip(rgb * light[..., None], 0, 255).astype("uint8")
    out[unset] = (0, 0, 0)
    return Image.fromarray(out, "RGB")


def encode(image, quality: int = 86) -> bytes:
    """WebP: a 4k-wide picture of a continent in a few hundred KB."""
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=int(quality), method=4)
    return buffer.getvalue()


def picture(store, guild_id: int, colours: dict, *, shading: float = 1.0,
            grain: float = 1.0, kinds: Iterable[dict] = None) -> bytes:
    """The encoded overview of a guild's world straight from its store."""
    world = store.world(guild_id)
    cxs, cys = store.chunk_counts(guild_id)
    chunks = store.chunks(guild_id, [(cx, cy) for cy in range(cys) for cx in range(cxs)])
    cells = grid(chunks, world["cells_w"], world["cells_h"])
    return encode(render(cells, list(kinds) if kinds is not None else world["kinds"], colours,
                         seed=guild_id, shading=shading, grain=grain))
