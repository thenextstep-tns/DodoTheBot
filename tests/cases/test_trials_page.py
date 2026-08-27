"""Render the trial-ranks panel page end to end against stubs."""
import datetime
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from web import routes
from helpers import panel_access, trial_ranks as tr


class Role:
    managed = False
    def __init__(self, rid, name, position):
        self.id, self.name, self.position = rid, name, position
    def is_default(self): return False
    # discord.Role orders by position; the stub needs the same to be comparable
    # against the bot's top role.
    def __ge__(self, other): return self.position >= other.position


class Member:
    bot = False
    def __init__(self, uid, name, roles):
        self.id, self.name, self.display_name, self.roles = uid, name, name, roles
    @property
    def top_role(self):
        return max(self.roles, key=lambda r: r.position) if self.roles else Role(0, "@e", -1)


class Channel(discord.TextChannel):
    category = None
    def __init__(self, cid, name):
        self.id, self.name, self.position = cid, name, 0


class BotRole:
    id, name, position, managed = 9999, "Dodo", 10_000, False
    def is_default(self): return False
    def __ge__(self, other): return self.position >= other.position


class BotMember:
    top_role = BotRole()
    guild_permissions = type("P", (), {"manage_roles": True})()


class Guild:
    name, id = "ESO for Dodos", 42
    owner_id = 0
    me = BotMember()
    def __init__(self, roles, members, channels):
        self.roles, self.members, self.channels = roles, members, channels
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)
    def get_member(self, uid): return next((m for m in self.members if m.id == uid), None)
    def get_channel(self, cid): return next((c for c in self.channels if c.id == cid), None)


names = ["==== RANKS & ROLES ===="] + ["Fresh Meat", "Trialgoer", "Big Deal"] + \
        ["======== CLEARS ========"] + ["vAA", "vAA HM", "vKA", "vKA HM"]
roles, pos = [], 100
for n in names:
    roles.append(Role(200 + len(roles), n, pos)); pos -= 1
by = {r.name: r for r in roles}
members = [Member(1, "nikladushkin", [by["vAA"], by["vKA"]]),
           Member(2, "someone", [])]
guild = Guild(roles, members, [Channel(700, "mod-chat"), Channel(701, "rank-requests")])

config = {
    "enabled": True, "exclusive": True,
    "points": {str(by["vAA"].id): 1, str(by["vAA HM"].id): 2,
               str(by["vKA"].id): 4, str(by["vKA HM"].id): 15},
    "ranks": [{"role_id": by["Fresh Meat"].id, "min_points": 0, "name": "Fresh Meat",
               "description": "Welcome aboard."},
              {"role_id": by["Big Deal"].id, "min_points": 40, "name": "Big Deal",
               "description": ""}],
    "trials": [{"name": "vAA", "slots": {"veteran": by["vAA"].id,
                                        "full_hm": by["vAA HM"].id}}],
    "announce_channel_id": 700, "announce_message_id": 0,
}

now = datetime.datetime.now(datetime.timezone.utc)
ROSTER = [
    {"user_id": 1, "name": "nikladushkin", "state": tr.STATE_ENROLLED, "source": "panel",
     "at": now, "enrolled_at": now},
    {"user_id": 2, "name": "someone", "state": tr.STATE_DISMISSED, "source": "button",
     "at": now, "prompted_at": now, "read_at": now, "dismissed_at": now},
]


class TrialMgr:
    def enrolled_ids(self, gid): return {1}
    def get(self, gid): return config
    def image_role_ids(self, gid): return {by["Fresh Meat"].id}
    def roster(self, gid, limit=500): return ROSTER
    def interest_rows(self, gid, limit=1000): return []
    def wr_all(self, gid): return {1: {'name': 'Mobi', 'current': 5, 'former': 1}}
    def wr_for(self, gid, uid): return None
    def presets(self, gid): return [{'name': 'Mine', 'points': {'1': 2}, 'author_id': 777, 'author_name': 'Fox'},{'name': 'Theirs', 'points': {}, 'author_id': 888, 'author_name': 'Mido'}]


class ShareStub:
    def active(self, gid): return None


class Bot:
    trial_ranks = TrialMgr()
    share_tokens = ShareStub()
    def get_cog(self, name): return None


html = routes._trials_html(Bot(), guild, panel_access.SCOPE_CONFIG)

for token in ("Casual", "Myth", "ladderrow", "rankrow", "addrank", "rankdesc",
              "rankimg-pick", "pilottag", "announcepost", "Fresh Meat", "Big Deal",
              "Welcome aboard", "trials/image/"):
    print(f"  {token!r:22} -> {html.count(token)}")

assert "Casual" not in html and "Myth" not in html, "the hardcoded ladder is gone"
assert "ladderrow" not in html
assert html.count("rankrow") >= 2, "one row per configured rank"
assert "Welcome aboard." in html, "description round-trips"
assert f"trials/image/{by['Fresh Meat'].id}.png" in html, "badge preview for the rank that has one"
assert html.count("rankimg-empty") == 1, "the rank with no badge says so"
# The funnel counters, computed off timestamps.
assert "<b>1</b> converted" in html
assert "<b>1</b> read how it works" in html
assert "<b>1</b> let it time out" in html
import re
sections = re.findall(r'<section class="trialpanel"[^>]*>', html)
assert len(sections) == 6 and sum("hidden" in x for x in sections) == 5
assert '<details class="group"' not in html, "accordions replaced by the side menu"
# Scoring moved onto the trial slots; Clears/Achievements panels are gone.
assert 'data-panel="clears"' not in html and 'data-panel="achievements"' not in html
import re as _re
_slots = _re.findall(r'class="rolepoints slotpoints" data-role="(\d+)"[^>]*value="([^"]*)"', html)
assert _slots and any(v for _, v in _slots), f"slot scores missing: {_slots}"
for _gone in ("Trial clear roles", "your roles, in the order they cost", "rung",
              "dry runs", "nothing is saved or applied"):
    assert _gone not in html, f"stale copy: {_gone}"
for _want in ("Trials Setup", "Users</h2>", "trialsearch", "extrascores", "addextra"):
    assert _want in html, f"missing: {_want}"
for must in ("trialnav", "triallayout", "rankrows",
             "trialmap", "previewout", "pilottag", "trialrun"):
    assert must in html, must   # hidden panels must stay in the DOM for Save
print("side menu OK")
# Presets: the viewer and each author travel to the page so the buttons can
# decide who may overwrite what.
_page = routes._trials_html(Bot(), guild, panel_access.SCOPE_CONFIG, 777)
assert 'data-uid="777"' in _page
assert 'data-author="777"' in _page and 'data-author="888"' in _page
assert 'id="presetsavenew"' in _page, "Save as new is always offered"
assert 'hidden>Save<' in _page and 'hidden>Delete<' in _page, "overwrite starts hidden"
# There is no master feature switch any more: enrolment is the only gate.
assert "trialsenabled" not in html, "the enabled checkbox is gone"
assert "Only the people under <b>Users</b> are affected" in html
print("preset ownership markup OK")
# World records: their own tab, and the bonus shown per holder.
assert 'data-panel="records"' in html and html.count('data-panel="records"') == 2
assert "World records" in html and "1 holders" in html
assert "+80" in html, "5 current + 1 former = 80 points"
assert tr.WR_MEDAL * 5 in html and tr.FORMER_WR_MEDAL in html
assert "wrtag" in html and "wrcurrent" in html and "wrformer" in html
_secs = re.findall(r'<section class="trialpanel"[^>]*>', html)
assert len(_secs) == 6 and sum("hidden" in x for x in _secs) == 5
# The tag box is a picker over real members, searchable by either name.
import json as _json
_members = _json.loads(re.search(
    r'id="all-members">(.*?)</script>', html, re.S).group(1))
assert {m["name"] for m in _members} == {"nikladushkin", "someone"}, _members
assert all("display" in m and "id" in m for m in _members)
assert isinstance(_members[0]["id"], str), "ids stay strings for JS"
assert 'class="mpick"' in html and 'id="wruser"' in html
# Enrolled members get a per-person recalculate button; nobody else does.
assert html.count('pilotrecalc') == 1, 'only the enrolled member has one'
assert html.count('pilotdel') == 2, 'but everyone can be taken off'
# The whole-server button. Asserted because the page rendering fine without it
# is exactly how it went missing: nothing here looked at it.
assert 'id="pilotenrolall"' in html, 'the mass-enrol button is on the Users panel'
print("world records tab OK, member picker carries", len(_members), "people")
print("PASS")
