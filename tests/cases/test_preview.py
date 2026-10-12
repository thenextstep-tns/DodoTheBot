"""Preview rows carry direction, tag, and per-row breakdown for the filters."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import trial_ranks as tr


class Role:
    managed = False
    def __init__(self, rid, name): self.id, self.name, self.position = rid, name, 1
    def is_default(self): return False


class Member:
    bot = False
    def __init__(self, uid, name, roles):
        self.id, self.name, self.display_name, self.roles = uid, name, name, roles


class Guild:
    def __init__(self, roles): self.roles = roles
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)


N = ["Low", "Mid", "High", "vAA", "vAA HM"]
R = {n: Role(100 + i, n) for i, n in enumerate(N)}
guild = Guild(list(R.values()))
rid = lambda n: R[n].id

points = {str(rid("vAA")): 15, str(rid("vAA HM")): 40}
trials = [{"name": "vAA", "slots": {"veteran": rid("vAA"), "full_hm": rid("vAA HM")}}]
ranks = tr.validate_ranks([
    {"role_id": rid("Low"), "min_points": 0},
    {"role_id": rid("Mid"), "min_points": 10},
    {"role_id": rid("High"), "min_points": 30},
], guild=guild)


def row_for(member):
    """Mirrors the server's row_for so direction can be checked in isolation."""
    held = {r.id for r in member.roles}
    score = tr.score_for(held, points, trials=trials)
    projected = tr.rank_for(score, ranks)
    current_rank = next((r for r in ranks if r["role_id"] in held), None)
    was = int((current_rank or {}).get("min_points") or 0)
    now = int((projected or {}).get("min_points") or 0)
    if current_rank is None and projected is None:
        d = ""
    elif current_rank is None:
        d = "up"
    elif projected is None:
        d = "down"
    else:
        d = "up" if now > was else ("down" if now < was else "")
    return {"name": member.display_name, "tag": member.name, "score": score,
            "current": (current_rank or {}).get("name"),
            "rank": (projected or {}).get("name"), "direction": d,
            "breakdown": tr.breakdown_for(guild, held, points, trials)}


cases = [
    ("holds Low, earns High", Member(1, "up_user", [R["Low"], R["vAA HM"]]), "up"),
    ("holds High, earns Low", Member(2, "down_user", [R["High"], R["vAA"]]), "down"),
    ("holds Mid, stays Mid", Member(3, "same_user", [R["Mid"], R["vAA"]]), ""),
    ("no rank, earns High", Member(4, "new_user", [R["vAA HM"]]), "up"),
]
for label, member, expect in cases:
    row = row_for(member)
    print(f"{label:26} {row['current'] or '—':>5} -> {row['rank'] or '—':<5} "
          f"score={row['score']:<3} direction={row['direction']!r}")
    assert row["direction"] == expect, (label, row["direction"], expect)

# The filters need these three fields on every row.
row = row_for(cases[0][1])
assert row["tag"] == "up_user", "username travels for the search filter"
assert any(b["name"] == "vAA HM" for b in row["breakdown"]), "clear-role filter needs breakdown"
# Superseded roles are marked, not hidden — that's what the expanded row shows.
sup = [b for b in row["breakdown"] if not b["counted"]]
print("superseded rows kept:", [b["name"] for b in sup])
print("PASS")
