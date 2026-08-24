"""
The emoji catalogue — one row per *distinct thing*, not per codepoint.

The reaction grid needs a list of objects a cat can be shown, and Unicode is a
poor list for that: it carries five skin tones of the same waving hand, nine
colours of the same circle, and a man and a woman doing the same job. For this
game those are all one row. Twelve hearts is eleven rows of nothing to write
about.

So the catalogue is built by *collapsing* families rather than by enumerating
codepoints. The rules below are the whole opinion, kept in one place and
re-runnable — Unicode gains emoji every year:

* only single codepoints, so no ZWJ sequences (no "man firefighter", no
  "family: woman, girl, dog") — those are compounds of things already listed;
* no skin-tone modifiers, and nothing whose name mentions one;
* no regional indicators, so no flags: 250 countries is padding, not content;
* colour words are stripped from the name and the family deduplicated, so the
  red circle survives and the other eight go;
* gender and age words are stripped the same way, so "man farmer" and "woman
  farmer" collapse into one farmer.

Rebuild with::

    py -3 helpers/emoji_catalogue.py

which rewrites ``helpers/data/emoji_catalogue.json`` and prints the counts.
Nothing at runtime rebuilds it: the file is the catalogue, so a Unicode upgrade
on the box cannot silently change what the game contains.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

DATA = pathlib.Path(__file__).resolve().parent / "data" / "emoji_catalogue.json"

# The modern planes are pictographs almost end to end, so those are taken whole.
BLOCKS: tuple[tuple[int, int, str], ...] = (
    (0x1F300, 0x1F5FF, "Things and places"),
    (0x1F600, 0x1F64F, "Faces and gestures"),
    (0x1F680, 0x1F6FF, "Travel and warnings"),
    (0x1F900, 0x1F9FF, "People, food and oddities"),
    (0x1FA70, 0x1FAFF, "Newer things"),
    (0x1F7E0, 0x1F7EB, "Shapes"),
)

# The old blocks are not. 2600-27BF holds real emoji sitting among dingbats and
# printers' marks that no font renders as emoji and nobody can show a cat, and
# 1F000-1F0FF is 200 mahjong tiles and playing cards for two usable pictures.
# There is no emoji-data.txt on the box to ask, so the usable ones are listed by
# hand. Adding to this list is the way to add a legacy emoji.
ALLOWED = {
    "Weather and sky": "\u2600\u2601\u2602\u2603\u2604\u26c4\u26c5\u26c8\u2744\u2745\u2747\u26a1\u2b50\u1f7e1",
    "Symbols and warnings": "\u2620\u2622\u2623\u26a0\u26d4\u267b\u267e\u267f\u2757\u2753\u2754\u2755\u2049\u203c"
                            "\u2705\u274c\u274e\u2714\u2716\u271d\u2721\u262a\u262e\u262f\u2638\u2639\u263a"
                            "\u2795\u2796\u2797\u27a1\u27b0\u27bf\u2b55\u2122\u2139\u24c2\u3030\u303d\u3297\u3299",
    "Tools and objects": "\u2692\u2693\u2694\u2695\u2696\u2697\u2699\u269b\u269c\u26cf\u26d1\u26d3\u26ea"
                         "\u26f0\u26f1\u26f2\u26f3\u26f4\u26f5\u26fa\u26fd\u2702\u2708\u2709\u270f\u2712"
                         "\u2648\u26bd\u26be\u26f7\u26f8\u26f9\u2660\u2663\u2665\u2666\u2668\u26b0\u26b1"
                         "\u231a\u231b\u23f0\u23f1\u23f2\u23f3\u260e\u2611\u2615\u2618\u261d\u1f004\u1f0cf",
    "Hands and faces": "\u270a\u270b\u270c\u270d\u2764\u2763\u2728\u2733\u2734\u2757",
}

# Single codepoints that are emoji but live off on their own.
STRAYS = "\u23e9\u23ea\u23eb\u23ec\u23ed\u23ee\u23ef\u23f8\u23f9\u23fa\u25aa\u25ab\u25b6\u25c0\u25fb\u25fc\u25fd\u25fe\u2b05\u2b06\u2b07\u2b1b\u2b1c\u2194\u2195\u2196\u2197\u2198\u2199\u21a9\u21aa"

# Words that make two rows out of one thing. Stripped before deduplication.
COLOURS = ("red", "orange", "yellow", "green", "blue", "light blue", "purple", "violet",
           "brown", "black", "white", "grey", "gray", "pink")
PEOPLE = ("man", "woman", "men", "women", "person", "people", "boy", "girl",
          "older", "old", "baby", "child", "male", "female", "sign")
# Numbers only ever make the same thing again: twelve o'clock faces, ten keycap
# digits, four "three o'clock"s. One clock is a clock.
NUMBERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
           "eleven", "twelve", "thirty", "digit", "keycap")
NOISE = re.compile(r"\b(" + "|".join(COLOURS + PEOPLE + NUMBERS) + r")\b")

SKIP_NAME = re.compile(r"SKIN TONE|REGIONAL INDICATOR|TAG |VARIATION SELECTOR|ZERO WIDTH")


def family(name: str) -> str:
    """The name with everything that only varies the *presentation* removed."""
    collapsed = NOISE.sub("", name.lower().replace(":", " "))
    return re.sub(r"\s+", " ", collapsed).strip(" -")


def title(name: str) -> str:
    """A readable label: 'FACE WITH TEARS OF JOY' -> 'Face with tears of joy'."""
    cleaned = name.lower().replace("_", " ")
    return cleaned[:1].upper() + cleaned[1:]


def build() -> list[dict]:
    """Walk the blocks and collapse each family to a single row."""
    seen: dict[str, dict] = {}
    rows: list[dict] = []

    def consider(char: str, group: str) -> None:
        try:
            name = unicodedata.name(char)
        except ValueError:
            return                                    # unassigned codepoint
        if unicodedata.category(char) != "So":        # not a pictograph
            return
        if SKIP_NAME.search(name):
            return
        key = family(name)
        if not key or key in seen:
            return
        row = {"char": char, "codepoint": f"U+{ord(char):04X}", "name": title(name),
               "family": key, "group": group}
        seen[key] = row
        rows.append(row)

    for start, end, group in BLOCKS:
        for code in range(start, end + 1):
            consider(chr(code), group)
    for group, chars in ALLOWED.items():
        for char in chars:
            consider(char, group)
    for char in STRAYS:
        consider(char, "Odds and ends")
    return rows


def load() -> list[dict]:
    """The catalogue as built. Falls back to an empty list rather than raising:
    a missing file must not stop the panel from loading."""
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def by_group(rows: list[dict] = None) -> dict[str, list[dict]]:
    """Rows bucketed by group, in the order the blocks are declared."""
    rows = rows if rows is not None else load()
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["group"], []).append(row)
    return buckets


def main() -> int:
    rows = build()
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} distinct emoji -> {DATA}")
    for group, bucket in by_group(rows).items():
        print(f"  {len(bucket):5d}  {group}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
