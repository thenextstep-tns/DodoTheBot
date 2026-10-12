"""Broad strokes in the picker, boss/title/clear detail once you pick."""
import datetime, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from cogs.trial_ranks import TrialRanks, INTEREST_MARKS
from helpers import trial_ranks as tr


class Role:
    managed = False
    def __init__(self, rid, name): self.id, self.name, self.position = rid, name, 1
    def is_default(self): return False


class Member:
    bot = False
    def __init__(self, uid, name): self.id, self.display_name, self.name = uid, name, name
    @property
    def mention(self): return f"<@{self.id}>"


class Guild:
    id = 42
    def __init__(self, roles, members): self.roles, self.members = roles, members
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)
    def get_member(self, uid): return next((m for m in self.members if m.id == uid), None)


NAMES = ["vRG", "vRG Oaxiltso HM", "vRG Bahsei HM", "vRG HM", "Immortal Redeemer", "vDSR HM"]
ROLES = {n: Role(100 + i, n) for i, n in enumerate(NAMES)}
rid = lambda n: ROLES[n].id
people = [Member(1000 + i, n) for i, n in enumerate(
    ["Fox", "Mido", "Nik", "Salvy", "Ash", "Kira", "Tom"])]
guild = Guild(list(ROLES.values()), people)

CONFIG = {"trials": [{"name": "vRG", "slots": {
    "veteran": rid("vRG"), "partial1": rid("vRG Oaxiltso HM"),
    "partial2": rid("vRG Bahsei HM"), "full_hm": rid("vRG HM"),
    "trifecta": rid("Immortal Redeemer")}}], "points": {}, "ranks": []}

now = datetime.datetime.now(datetime.timezone.utc)
# Different people are short of different bosses inside the same raid.
want = {
    "Fox":   [rid("vRG Bahsei HM"), rid("vRG HM")],
    "Mido":  [rid("vRG Bahsei HM")],
    "Nik":   [rid("vRG Bahsei HM")],
    "Salvy": [rid("vRG Oaxiltso HM")],
    "Ash":   [rid("Immortal Redeemer")],
    "Kira":  [rid("vRG HM")],
    "Tom":   [rid("vDSR HM")],
}
rows = [{"user_id": m.id, "name": m.display_name, "at": now, "role_ids": want[m.display_name]}
        for m in people]
buckets = tr.interest_buckets(guild, CONFIG, rows)

print("=== picker (broad strokes) ===")
for b in buckets:
    print(f"   {b['name']} — {b['count']}/{tr.GROUP_SIZE}")

cog = TrialRanks.__new__(TrialRanks)
vrg = next(b for b in buckets if b["name"] == "vRG")
embed = TrialRanks._interest_detail(cog, guild, vrg)
print(f"\n=== detail: {embed.title} ===")
print(embed.description)
for f in embed.fields:
    print(f"[{f.name}]")
    for line in f.value.splitlines():
        print("   ", line)

# One person counts once for the raid, but every clear they need is listed.
assert vrg["count"] == 6, vrg["count"]
counts = {e["name"]: e["count"] for e in vrg["by_role"]}
assert counts["vRG Bahsei HM"] == 3, counts
assert counts["vRG HM"] == 2, counts
assert counts["Immortal Redeemer"] == 1, counts
# Busiest clear leads the breakdown.
assert vrg["by_role"][0]["name"] == "vRG Bahsei HM"
# Each person's own missing clears travel with them.
fox = next(m for m in vrg["members"] if m["name"] == "Fox")
assert {r["name"] for r in fox["roles"]} == {"vRG Bahsei HM", "vRG HM"}
assert "vRG Bahsei HM, vRG HM" in next(f for f in embed.fields if f.name == "Who").value
print("\noverview:")
print(TrialRanks._interest_overview(cog, buckets).description)
print("\nPASS")
