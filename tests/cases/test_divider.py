"""Dividers no longer decide anything: moving one must change nothing that scores."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import trial_ranks as tr, trial_image


class Role:
    managed = False
    def __init__(self, rid, name, pos): self.id, self.name, self.position = rid, name, pos
    def is_default(self): return False


# Ids are stable in Discord however the list is reordered.
_IDS = {}


class Guild:
    name = "ESO for Dodos"
    def __init__(self, names):
        self.roles = [Role(_IDS.setdefault(n, 100 + len(_IDS)), n, 500 - i)
                      for i, n in enumerate(names)]
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)


LAYOUT = [
    "======= RANKS & ROLES =======",
    "Legend", "Master",
    "======== ACHIEVEMENTS ========",
    "Master Angler", "Godslayer",
    "========== CLEARS ==========",
    "vAA", "vRG HM",
]
before = Guild(LAYOUT)
rid = lambda n: _IDS[n]

CONFIG = {
    "points": {str(rid("Master Angler")): 20, str(rid("Godslayer")): 30,
               str(rid("vAA")): 1, str(rid("vRG HM")): 25},
    "trials": [{"name": "vRG", "slots": {"full_hm": rid("vRG HM")}}],
    "ranks": [{"role_id": rid("Legend"), "min_points": 40, "name": "Legend"}],
}

held = {rid("Godslayer"), rid("vRG HM")}
score_before = tr.score_for(held, CONFIG["points"], trials=CONFIG["trials"])
chart_before = len(trial_image.build(before, CONFIG))

# Delete the ACHIEVEMENTS divider — the case that used to silently unprice roles.
after = Guild([n for n in LAYOUT if "ACHIEVEMENT" not in n])
score_after = tr.score_for(held, CONFIG["points"], trials=CONFIG["trials"])
print(f"score before {score_before} / after {score_after}")
assert score_before == score_after == 55, (score_before, score_after)

# The chart is built from what's priced, so nothing drops out of it either.
chart_after = len(trial_image.build(after, CONFIG))
print("chart bytes before/after:", chart_before, chart_after)
assert chart_before == chart_after, "a role vanished from the chart when a divider moved"

# The only unpriced check left is about slots you mapped yourself.
assert tr.unpriced_slots(after, CONFIG) == [], "everything mapped is priced"
CONFIG["trials"].append({"name": "vAA", "slots": {"veteran": rid("vAA"),
                                                  "trifecta": rid("Godslayer")}})
CONFIG["points"][str(rid("vAA"))] = 0
gaps = tr.unpriced_slots(after, CONFIG)
print("unpriced slots:", [(g["trial"], g["name"], g["suggested"]) for g in gaps])
assert [g["name"] for g in gaps] == ["vAA"], gaps
assert gaps[0]["suggested"] == 1, "the built-in suggestion is offered"

# And the obsolete divider-driven helpers are gone for good.
for gone in ("unpriced", "orphaned_points", "with_defaults"):
    assert not hasattr(tr, gone), f"{gone} should have been removed with the dividers"
print("no divider-driven scoring helpers remain")
print("PASS")
