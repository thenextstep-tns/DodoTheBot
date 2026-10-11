"""
Moving a town moves what is in it.

A town is its hall at its plot and the area of influence around it. When the
hall moves, everything that belongs to the town goes with it, keeping where it
stood relative to the hall:

* the buildings built for the town (``town == uid``), wherever they stand;
* anything the town's owner placed inside the town's old area (``by == uid``) —
  their trees, their map art.

Each lands at the same offset from the new hall, unless that would put it
somewhere it cannot be: on ground nothing stands on (water, mountains — a kind
with no ``move``) it goes to the nearest ground that will hold it; outside the
town's new area it goes to the nearest place inside the area. The hall itself
gets the same treatment: a town dropped in the sea is put on the nearest shore.
Every such adjustment is reported back in plain words, so nobody finds their
tavern on the far side of the hill without being told why.

Blocking: the terrain, the areas and a nearest-cell search. Run in an executor.
"""

from __future__ import annotations

from helpers.dodoland import terrain as T


def _walkable(bot, guild):
    """``(cells_w, cells_h, ok)``: ``ok[y, x]`` where a thing may stand."""
    import numpy as np

    from helpers.dodoland import terrain_raster

    world = bot.dodoland_terrain.world(guild.id)
    cxs, cys = bot.dodoland_terrain.chunk_counts(guild.id)
    chunks = bot.dodoland_terrain.chunks(guild.id, [(x, y) for y in range(cys) for x in range(cxs)])
    cells = terrain_raster.grid(chunks, world["cells_w"], world["cells_h"])
    kinds = T.sync_tile_kinds(world["kinds"], {t["tile_id"]: t for t in bot.dodoland_tiles.tiles(guild.id)})
    stands = np.array([k.get("move") is not None for k in kinds] or [False])
    return world["cells_w"], world["cells_h"], stands[np.clip(cells, 0, len(kinds) - 1)]


def _cell(x_pct: float, y_pct: float, w: int, h: int) -> tuple[int, int]:
    return (min(w - 1, max(0, int(float(x_pct) / 100 * w))),
            min(h - 1, max(0, int(float(y_pct) / 100 * h))))


def _pct(cell: tuple[int, int], w: int, h: int) -> tuple[float, float]:
    return (round((cell[0] + 0.5) / w * 100, 3), round((cell[1] + 0.5) / h * 100, 3))


def _nearest(target: tuple[int, int], candidates):
    """The candidate cell (an ``(n, 2)`` array of x, y) closest to ``target``."""
    import numpy as np

    if candidates is None or not len(candidates):
        return None
    d = (candidates[:, 0] - target[0]) ** 2 + (candidates[:, 1] - target[1]) ** 2
    x, y = candidates[int(np.argmin(d))]
    return int(x), int(y)


def move_town(bot, guild, uid: int, x: float, y: float) -> dict:
    """Settle ``uid``'s town at ``(x, y)`` (map percentages), carrying what is
    in it. Returns ``{x, y, moved: [{piece_id, x, y}], notes: [str]}``."""
    import numpy as np

    from web.dodoland import influence_api

    uid = int(uid)
    notes: list[str] = []
    plots = bot.dodoland_buildings.plots(guild.id)
    old = plots.get(uid)
    w, h, ok = _walkable(bot, guild)
    if not w or not h:
        # No painted world: nothing to stand on or fall off, so everything the
        # town owns simply keeps its offset from the hall.
        spot = bot.dodoland_buildings.settle(guild.id, uid, x, y)
        moved = []
        if old:
            dx, dy = spot["x"] - float(old.get("x", 0)), spot["y"] - float(old.get("y", 0))
            for piece in bot.dodoland_decor.world(guild.id):
                if str(piece.get("town") or "") == str(uid):
                    nx, ny = round(float(piece["x"]) + dx, 3), round(float(piece["y"]) + dy, 3)
                    bot.dodoland_decor.move(guild.id, piece["piece_id"], x=nx, y=ny)
                    moved.append({"piece_id": piece["piece_id"], "x": nx, "y": ny})
        return {**spot, "moved": moved, "notes": notes}

    # The hall first: it must stand on something.
    hall = _cell(x, y, w, h)
    if not ok[hall[1], hall[0]]:
        r = 40
        x0, y0 = max(0, hall[0] - r), max(0, hall[1] - r)
        box = ok[y0:hall[1] + r + 1, x0:hall[0] + r + 1]
        found = np.argwhere(box)
        if not len(found):
            found = np.argwhere(ok)
            x0 = y0 = 0
        near = _nearest(hall, np.stack([found[:, 1] + x0, found[:, 0] + y0], axis=1)) if len(found) else None
        if near:
            hall = near
            x, y = _pct(hall, w, h)
            notes.append("The town hall would have stood in water or on a mountain, so it was "
                         "moved to the nearest open ground.")

    # What goes with it, decided before the area moves.
    carry = []
    if old:
        influence_api.current(bot, guild)
        old_area = influence_api._CELLS.get(guild.id, {}).get(str(uid)) or set()
        for piece in bot.dodoland_decor.world(guild.id):
            built_here = str(piece.get("town") or "") == str(uid)
            theirs = int(piece.get("by") or 0) == uid and _cell(piece["x"], piece["y"], w, h) in old_area
            if built_here or theirs:
                carry.append(piece)

    spot = bot.dodoland_buildings.settle(guild.id, uid, x, y)
    moved = []
    if not old or not carry:
        return {**spot, "moved": moved, "notes": notes}

    dx, dy = spot["x"] - float(old.get("x", 0)), spot["y"] - float(old.get("y", 0))
    influence_api.current(bot, guild)
    area = influence_api._CELLS.get(guild.id, {}).get(str(uid)) or set()
    room = np.array([c for c in area if ok[c[1], c[0]]] or [[hall[0], hall[1]]])
    wet = outside = 0
    for piece in carry:
        tx, ty = float(piece["x"]) + dx, float(piece["y"]) + dy
        cell = _cell(tx, ty, w, h)
        if cell in area and ok[cell[1], cell[0]]:
            nx, ny = round(tx, 3), round(ty, 3)
        else:
            if cell not in area:
                outside += 1
            else:
                wet += 1
            nx, ny = _pct(_nearest(cell, room), w, h)
        bot.dodoland_decor.move(guild.id, piece["piece_id"], x=nx, y=ny)
        moved.append({"piece_id": piece["piece_id"], "x": nx, "y": ny})

    if wet:
        notes.append(f"{wet} {'thing' if wet == 1 else 'things'} would have landed in water or on a "
                     "mountain, so they were moved to the nearest open ground.")
    if outside:
        notes.append(f"{outside} {'thing' if outside == 1 else 'things'} didn't fit inside the "
                     "town's new area, so they were moved to the nearest spot inside it.")
    return {**spot, "moved": moved, "notes": notes}
