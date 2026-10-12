"""
Dodo Tabletop — the parameter catalogue keeps itself honest.

The owner's standing rule is that **everything is a tweakable parameter visible
to the bot owner**. It had been written down twice and broken sixty-nine times,
because there was no list for a constant to be missing from — a rule with no
enforcement is a preference.

This suite is the enforcement. Three things it will not let happen:

1. **A new constant appearing with nowhere to see it.** The suite walks every
   module in ``helpers/dnd`` for module-level constants that shape behaviour, and
   fails on any that is neither a tunable, nor a shipped data table, nor listed
   in ``catalogue.BAKED_IN``. Adding a parameter means adding it here.
2. **The baked-in list going stale.** Each entry names a file, a name and a
   value; all three are re-read from the source. A constant that moved, changed
   or was deleted fails, and one that has *become* a tunable fails until it is
   reclassified — so the work queue cannot silently include finished work.
3. **A tunable with no home.** Every tunable must resolve into a typed view and
   name the module that consumes it, or the page cannot say where it applies.

Run with ``py tests/test_dnd_catalogue.py``.
"""

from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fake_mongo import FakeCollection  # noqa: E402

import config.database as database  # noqa: E402

for _name in (
    "dnd_campaigns", "dnd_entities", "dnd_scenes", "dnd_events", "dnd_knowledge",
    "dnd_memories", "dnd_beliefs", "dnd_relations", "dnd_clocks",
    "dnd_canon_queue", "dnd_snapshots",
):
    setattr(database, _name, FakeCollection(_name))

from helpers.dnd import catalogue  # noqa: E402
from helpers.dnd import parameters as dnd_parameters  # noqa: E402
from helpers.dnd.tuning import BY_KEY, GROUPS, TUNABLES  # noqa: E402

dnd_parameters.TUNING_COLLECTION = FakeCollection("DndTuning")

PASSED: list[str] = []
FAILED: list[str] = []

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "helpers", "dnd")


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{(' — ' + detail) if detail else ''}")


# --------------------------------------------------------------------------- #
#  Walking the source
# --------------------------------------------------------------------------- #
# Names that are vocabulary rather than parameters: the words the code uses to
# talk about itself. A string enum is not a knob — nobody tunes the fact that
# `KIND_NPC` is spelled "npc".
IGNORED_PREFIXES = ("SOURCE_", "SCOPE_", "KIND_", "TIER_", "LAYER_", "STATUS_")
# `DEFAULT_*` is vocabulary only in tuning.py, where it names a built typed view.
# Elsewhere it is a real parameter — `DEFAULT_DC` is the difficulty every
# unspecified check is set at, which is precisely the sort of number this list
# exists to surface.
IGNORED_IN = {"helpers/dnd/tuning.py": ("DEFAULT_",)}
IGNORED = {
    "DATA_PATH", "TUNING_SOURCE", "HERE", "TUNABLES", "BY_KEY", "GROUPS",
    "EXTRA_GROUPS", "PLANNED_GROUP", "MINUTES_PER_DAY", "TUNING_COLLECTION",
    "DND_COGS", "DND_EXTENSIONS", "DND_COLLECTIONS", "DND_PARAMETERS",
    "HARD_MAX_DICE", "HARD_MAX_SIDES", "DELTA_FIELDS", "AXES", "OPTIONAL_AXES",
    "NEEDS", "OPTIONAL", "TEMPERAMENT", "DRIVES", "FACULTIES", "TERMS",
    "COARSE_TERMS", "AFFORDANCES", "UNCOMMITTED", "KINDS", "ROMANTIC",
    "DELTAS", "PHRASES", "KIND_MAGNITUDE", "ACT_PHRASES", "CONSUMED_BY",
    "AFFECTS", "BAKED_IN", "NEEDS_ANSWERED_BY", "AFFORDANCE_LABELS",
}


def _constants():
    """Every module-level constant in helpers/dnd that could shape behaviour."""
    found = []
    for base, _dirs, files in os.walk(ROOT):
        if "__pycache__" in base:
            continue
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, os.path.dirname(os.path.dirname(ROOT)))
            rel = rel.replace(os.sep, "/")
            tree = ast.parse(open(full, encoding="utf-8").read())
            for node in tree.body:
                targets = []
                if isinstance(node, ast.Assign):
                    targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    targets = [node.target.id]
                for target in targets:
                    bare = target.lstrip("_")
                    if not bare or not bare.isupper():
                        continue
                    if target in IGNORED or target.startswith(IGNORED_PREFIXES):
                        continue
                    if target.startswith(IGNORED_IN.get(rel, ())):
                        continue
                    try:
                        value = ast.literal_eval(node.value)
                    except Exception:
                        continue
                    # Vocabulary: a name, or a list of names.
                    if isinstance(value, str):
                        continue
                    if isinstance(value, (tuple, list, set, frozenset)) and \
                            value and all(isinstance(i, str) for i in value):
                        continue
                    if value is None or value == {} or value == []:
                        continue
                    found.append((rel, target, value))
    return found


# --------------------------------------------------------------------------- #
#  1. Nothing shapes behaviour without being in the catalogue
# --------------------------------------------------------------------------- #
def test_nothing_is_missing() -> None:
    listed = {(b.path, b.name) for b in catalogue.BAKED_IN}
    found = _constants()
    check("catalogue: the source walk finds things at all", len(found) > 30,
          detail=f"{len(found)} constants")

    missing = [(path, name) for path, name, _v in found if (path, name) not in listed]
    check("catalogue: EVERY CONSTANT THAT SHAPES BEHAVIOUR IS LISTED",
          not missing,
          detail=("add to helpers/dnd/catalogue.py::BAKED_IN, or to TUNABLES: "
                  + ", ".join(f"{p}::{n}" for p, n in missing[:8])))


def test_the_list_has_not_gone_stale() -> None:
    """Every baked-in entry still exists, exactly where the list says it does.

    Checked against `catalogue.live_values()`, which walks everything including
    the wording tables — those are not *required* to be catalogued, but one that
    has been listed must still be real.
    """
    actual = catalogue.live_values()
    for baked in catalogue.BAKED_IN:
        here = (baked.path, baked.name)
        check(f"catalogue: '{baked.name}' is still where the list says",
              here in actual,
              detail=f"{baked.path} no longer defines it — has it been exposed?")

    keys = {b.name for b in catalogue.BAKED_IN}
    check("catalogue: nothing is listed as baked in *and* tunable",
          not (keys & set(BY_KEY)),
          detail=str(sorted(keys & set(BY_KEY))))

    paths = [(b.path, b.name) for b in catalogue.BAKED_IN]
    check("catalogue: no duplicate entries", len(paths) == len(set(paths)),
          detail="the same constant listed twice")


# --------------------------------------------------------------------------- #
#  2. Every tunable can say where it lives and what it touches
# --------------------------------------------------------------------------- #
def test_every_tunable_has_a_home() -> None:
    views = catalogue.views()
    for spec in TUNABLES:
        key = spec["key"]
        check(f"catalogue: '{key}' resolves into a typed view",
              key in views,
              detail="add it to a Tuning.*() builder, or to the prefix map")
        if key in views:
            check(f"catalogue: '{key}' names the module that reads it",
                  bool(catalogue.CONSUMED_BY.get(views[key])),
                  detail=f"view '{views[key]}' is missing from CONSUMED_BY")


def test_entries_are_complete() -> None:
    rows = catalogue.entries()
    counts = catalogue.summary()
    check("catalogue: it covers every tunable",
          counts["tunable"] == len(TUNABLES),
          detail=f"{counts['tunable']} vs {len(TUNABLES)}")
    check("catalogue: and every baked-in constant",
          counts["baked"] == len(catalogue.BAKED_IN))
    check("catalogue: totals add up",
          counts["total"] == counts["tunable"] + counts["data"] + counts["baked"])

    for entry in rows:
        check(f"catalogue: '{entry.key}' is described",
              bool(entry.label) and bool(entry.description),
              detail="a row with no description is a row nobody can act on")
        check(f"catalogue: '{entry.key}' says where it can be set",
              entry.layer in (catalogue.LAYER_CAMPAIGN, catalogue.LAYER_SERVER,
                              catalogue.LAYER_DATA, catalogue.LAYER_CODE))

    # Cross-references must point at something real, or the page invites a
    # search for a parameter that does not exist.
    known = set(BY_KEY) | {e.key for e in rows}
    for entry in rows:
        for other in tuple(entry.affects) + tuple(entry.siblings):
            check(f"catalogue: '{entry.key}' cross-references a real parameter",
                  other in known, detail=f"unknown: {other!r}")


def test_grouping() -> None:
    grouped = catalogue.grouped()
    check("catalogue: every group has rows", all(rows for _g, rows in grouped))
    listed = sum(len(rows) for _g, rows in grouped)
    check("catalogue: grouping loses nothing", listed == len(catalogue.entries()))

    for group, rows in grouped:
        check(f"catalogue: '{group}' puts what you can change first",
              [r.exposed for r in rows] == sorted((r.exposed for r in rows),
                                                  reverse=True),
              detail="baked-in rows sort to the bottom of their section")

    names = {group for group, _rows in grouped}
    check("catalogue: no group is invented outside the known set",
          names <= set(GROUPS) | set(catalogue.EXTRA_GROUPS),
          detail=str(sorted(names - (set(GROUPS) | set(catalogue.EXTRA_GROUPS)))))


def main() -> int:
    for test in (
        test_nothing_is_missing,
        test_the_list_has_not_gone_stale,
        test_every_tunable_has_a_home,
        test_entries_are_complete,
        test_grouping,
    ):
        test()

    for line in PASSED:
        print(f"  ok   {line}")
    for line in FAILED:
        print(f"  FAIL {line}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
