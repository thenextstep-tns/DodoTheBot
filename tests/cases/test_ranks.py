"""Exercise the free-form ladder: validation, migration, scoring, next-rank advice."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import trial_ranks as tr


class Role:
    def __init__(self, rid, name): self.id, self.name = rid, name
    managed = False
    position = 1
    def is_default(self): return False


class Guild:
    def __init__(self, roles): self.roles = roles
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)


R = {n: Role(100 + i, n) for i, n in enumerate(
    ["Fresh Meat", "Trialgoer", "Big Deal",          # ranks
     "vAA", "vAA HM", "vKA", "vKA HM", "Godslayer"])}  # clears
guild = Guild(list(R.values()))
rid = lambda n: R[n].id

points = {str(rid("vAA")): 1, str(rid("vAA HM")): 2,
          str(rid("vKA")): 4, str(rid("vKA HM")): 15,
          str(rid("Godslayer")): 30}
trials = [{"name": "vAA", "slots": {"veteran": rid("vAA"), "full_hm": rid("vAA HM")}},
          {"name": "vKA", "slots": {"veteran": rid("vKA"), "full_hm": rid("vKA HM")}}]

# --- validation: free-form names, ordering by points, duplicate rejection ---
ranks = tr.validate_ranks([
    {"role_id": rid("Big Deal"), "min_points": 40, "description": "The real ones."},
    {"role_id": rid("Fresh Meat"), "min_points": 0},
    {"role_id": rid("Trialgoer"), "min_points": 10},
], guild=guild)
print("order:", [(r["name"], r["min_points"]) for r in ranks])
assert [r["name"] for r in ranks] == ["Fresh Meat", "Trialgoer", "Big Deal"]

for bad, why in (
    ([{"role_id": rid("Fresh Meat"), "min_points": 5},
      {"role_id": rid("Trialgoer"), "min_points": 5}], "same threshold"),
    ([{"role_id": rid("Fresh Meat"), "min_points": 5},
      {"role_id": rid("Fresh Meat"), "min_points": 9}], "same role"),
    ([{"role_id": rid("Fresh Meat"), "min_points": -1}], "negative"),
):
    try:
        tr.validate_ranks(bad, guild=guild)
        raise AssertionError(f"{why} should have been rejected")
    except tr.TrialError as e:
        print(f"rejected ({why}):", e)

# --- migration off the old fixed ladder ---
legacy = [{"tier": "Veteran", "name": "Veteran", "role_id": rid("Big Deal"), "min_points": 40},
          {"tier": "Casual", "name": "Casual", "role_id": rid("Fresh Meat"), "min_points": 0}]
migrated = tr._migrate_ranks(legacy)
print("migrated:", [(m["name"], m["min_points"]) for m in migrated])
assert [m["role_id"] for m in migrated] == [rid("Fresh Meat"), rid("Big Deal")]
assert "tier" not in migrated[0]

# --- scoring + rank_for + progress ---
held = {rid("vAA"), rid("vAA HM"), rid("vKA")}     # vAA HM supersedes vAA
score = tr.score_for(held, points, trials=trials)
print("score:", score)                              # 2 + 4 = 6
assert score == 6
assert tr.rank_name(tr.rank_for(score, ranks), guild) == "Fresh Meat"
assert tr.rank_name(tr.next_rank_for(score, ranks), guild) == "Trialgoer"

state = tr.missing_for_next(guild, held, points, ranks, trials=trials)
print(f"score={state['score']} needs={state['needed']} "
      f"pct={round(state['fraction']*100)}%")
for s in state["steps"]:
    print(f"   +{s['gain']:>3}  {s['name']}{'  (upgrade)' if s['upgrade'] else ''}")
names = [s["name"] for s in state["steps"]]
# vAA is held and vAA HM already supersedes it: neither may be suggested.
assert "vAA" not in names and "vAA HM" not in names, names
# vKA HM is an upgrade over the held vKA, so it's worth 15-4=11, not 15.
step = next(s for s in names if s == "vKA HM")
assert next(s for s in state["steps"] if s["name"] == "vKA HM")["gain"] == 11
# Cheapest first, and enough of them to actually close the 4-point gap.
gains = [s["gain"] for s in state["steps"]]
assert gains == sorted(gains), gains
assert sum(gains) >= state["needed"]

# --- top of the ladder ---
top = tr.missing_for_next(guild, {rid("Godslayer"), rid("vKA HM")}, points, ranks, trials=trials)
print("top:", top["score"], "next:", top["next"], "fraction:", top["fraction"])
assert top["next"] is None and top["fraction"] == 1.0 and top["steps"] == []

# --- exact-tag matching ---
class M:
    bot = False
    def __init__(self, name, disc="0", nick=None):
        self.name, self.discriminator = name, disc
        self.display_name = nick or name
        self.id = 999
class G2:
    members = [M("nikladushkin", nick="Nik")]
    def get_member(self, i): return None
g2 = G2()
assert tr.find_by_tag(g2, "nikladushkin") is not None
assert tr.find_by_tag(g2, "@nikladushkin") is not None
assert tr.find_by_tag(g2, "NikLadushkin") is not None
assert tr.find_by_tag(g2, "Nik") is None, "a nickname must not match"
assert tr.find_by_tag(g2, "nikla") is None, "a prefix must not match"
print("PASS")
