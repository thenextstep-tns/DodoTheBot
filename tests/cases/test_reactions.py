"""The emoji catalogue and the reaction grid.

The catalogue's whole job is *not* being Unicode: no skin tones, no flags, no
nine colours of the same circle. The grid's whole job is layering — a server
that clears its own note must fall back to what was underneath, not to nothing.
"""
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from helpers import emoji_catalogue, reactions


def routes_classes():
    from web import routes
    return routes._scrap_classes()
from scrap_lab import FakeCollection, FakeGuild   # the in-memory store the lab uses

rows = emoji_catalogue.load()
assert rows, "the catalogue file is missing; run py -3 helpers/emoji_catalogue.py"
chars = [r["char"] for r in rows]

# --- the catalogue is a list of things, not a list of codepoints --------------
assert len(chars) == len(set(chars)), "the same emoji appears twice"
assert 800 < len(rows) < 2500, f"{len(rows)} looks wrong for a curated catalogue"
print("%d distinct objects, no duplicates" % len(rows))

for row in rows:
    assert len(row["char"]) == 1, f"{row['name']} is a sequence, not a single emoji"
    assert "SKIN TONE" not in row["name"].upper()
    assert not (0x1F1E6 <= ord(row["char"]) <= 0x1F1FF), "regional indicators are flags"
print("single codepoints only: no skin tones, no flag halves, no ZWJ sequences")

# Colour families collapse to one row: one circle, not nine.
names = {r["name"].lower() for r in rows}
circles = [n for n in names if n.endswith("circle") and " " not in n.replace("circle", "").strip()]
assert sum(1 for c in ("red circle", "blue circle", "green circle") if c in names) == 0, \
    "coloured circles should have collapsed into one family"
hearts = [n for n in names if n in ("red heart", "blue heart", "green heart", "yellow heart")]
assert len(hearts) <= 1, hearts
print("colour variants collapsed: %d circle rows, %d coloured-heart rows" % (len(circles), len(hearts)))

# The examples the design is built on have to actually be in there.
for needed in "👖🥒📦🧹💀🐟🎃":
    assert needed in chars, f"{needed} is missing from the catalogue"
print("the seeded objects are all present in the catalogue")

# --- layering ----------------------------------------------------------------
memory = FakeCollection()
reactions._collection = lambda: memory
GUILD, OTHER = 1, 2
CELL = ("👖", "loaf")

seeded = reactions.grid(GUILD, ["👖"], ["loaf"])["👖"]["loaf"]
assert seeded["source"] == "written" and seeded["text"].startswith("Sits on them")
print("an untouched cell answers from what somebody wrote for it")

# Everything the seed does not name still answers, from the written flavour
# layer, because a blank cell in a fight is a cat doing nothing at all.
blankest = reactions.grid(GUILD, ["🪗"], ["alley"])["🪗"]["alley"]
assert blankest["source"] == "seeded" and blankest["text"], blankest
print("an unwritten object has a seeded starting point to edit, not a blank")

# Every cell in the whole grid holds something editable.
from helpers import reaction_written as _rw  # noqa: E402
_sources = {_rw.line_for(r["char"], k)[2] for r in rows for k in [c["key"] for c in routes_classes()]}
assert "empty" not in _sources, "a blank cell is nothing to edit"
print("no cell in the grid is blank: %s" % ", ".join(sorted(_sources)))

# Hand-written cells are marked apart from stand-ins, so the panel can show what
# still needs a person rather than reporting the grid as finished.
from helpers import reaction_written  # noqa: E402

for _char, _lines in reaction_written.WRITTEN.items():
    assert set(_lines) == {c["key"] for c in routes_classes()}, _char
    for _text, _stats in _lines.values():
        assert _text and _text[-1] == ".", _text
        assert len(_text) < 90, _text
        assert "leaves the room" not in _text.lower(), "a cat cannot leave a fight: " + _text
        assert set(_stats) <= set(("strength", "agility", "intellect", "charm")), _stats
        assert any(_stats.values()), "a reaction with no stat change does nothing: " + _text
written = reactions.grid(GUILD, ["🐟"], ["chonk"])["🐟"]["chonk"]
assert written["source"] == "written" and "next fish" in written["text"], written
print("all %d written objects carry a line for every class, all thirteen"
      % len(reaction_written.WRITTEN))

reactions.save(reactions.GLOBAL, *CELL, "Everyone's default trousers line.", {"strength": 1})
assert reactions.grid(GUILD, ["👖"], ["loaf"])["👖"]["loaf"]["source"] == "global"
print("a global row covers the seed for every server")

reactions.save(GUILD, *CELL, "This server's trousers line.", {"charm": 2})
mine = reactions.grid(GUILD, ["👖"], ["loaf"])["👖"]["loaf"]
theirs = reactions.grid(OTHER, ["👖"], ["loaf"])["👖"]["loaf"]
assert mine["source"] == "guild" and mine["text"] == "This server's trousers line."
assert theirs["source"] == "global", "one server's edit must not leak into another"
print("a guild row covers the global one, and only for that guild")

# --- clearing uncovers, it does not empty ------------------------------------
after = reactions.save(GUILD, *CELL, "", {})
assert after["cleared"] is True
assert after["source"] == "global" and after["text"] == "Everyone's default trousers line.", after
print("clearing an override returns the layer underneath, not a blank cell")

# Stat numbers with no words next to them are not a cell.
blank = reactions.save(GUILD, "🥒", "ghost", "   ", {"charm": 3})
assert blank["cleared"] is True and blank["source"] == "written"
print("a description-less stat change is treated as a clear")

# Bad stat keys and non-numbers never reach the database.
reactions.save(GUILD, "📦", "chonk", "Fits.", {"strength": 2, "luck": 9, "agility": 0})
row = memory.find({"guild_id": GUILD, "emoji": "📦", "cls": "chonk"})[0]
assert row["stats"] == {"strength": 2}, row["stats"]
print("unknown stats and zeroes are dropped on the way in")

# --- coverage counts cells, not rows -----------------------------------------
before = reactions.coverage(GUILD, len(rows), 13)["filled"]
reactions.save(GUILD, "👖", "loaf", "Written twice over the same cell.", {})
assert reactions.coverage(GUILD, len(rows), 13)["filled"] == before, \
    "overriding a cell that already had a default must not count as two"
print("coverage counts distinct cells across every layer")

# --- the page renders --------------------------------------------------------
from web import reactions_page, routes  # noqa: E402

guild = FakeGuild()
classes = routes._scrap_classes()
visible = rows[:reactions_page.PER_PAGE]
grid = reactions.grid(guild.id, [r["char"] for r in visible], [c["key"] for c in classes])
page = reactions_page.render(guild, classes, visible, grid, ["Faces and gestures"],
                             {"group": "", "q": ""}, 1, 40, len(rows),
                             reactions.coverage(guild.id, len(rows), len(classes)))
assert page.count("<th class=\"rxclass\"") == len(classes) == 13
assert page.count("class=\"rxcell") == len(visible) * len(classes)
for cls in classes:
    assert cls["name"] in page
assert "rxeditor" in page and "rxsave" in page
print("the grid page builds: %d columns x %d rows of clickable cells"
      % (len(classes), len(visible)))

# A custom server emoji renders as its image, not as a glyph that does not exist.
custom = {"char": "<:dodo:1>", "codepoint": "guild:1", "name": "Dodo", "family": "guild-1",
          "group": "This server", "url": "https://cdn.example/dodo.png", "custom": True}
one = reactions.grid(guild.id, [custom["char"]], [c["key"] for c in classes])
markup = reactions_page.render(guild, classes, [custom], one, [], {"group": "", "q": ""},
                               1, 1, 1, {"filled": 0, "cells": 1, "percent": 0.0})
assert "cdn.example/dodo.png" in markup and "rxcustom" in markup
print("a server's own emoji renders as its image")

print("PASS")
