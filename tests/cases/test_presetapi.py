"""Call the preset endpoint the way the browser does, and surface any 500."""
import asyncio, sys, traceback
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers import panel_access


class Role:
    managed = False
    def __init__(self, rid, name): self.id, self.name, self.position = rid, name, 1
    def is_default(self): return False


class Member:
    display_name = "Fox"
    id = 777


class Guild:
    id = 42
    def __init__(self, roles): self.roles = roles
    def get_role(self, rid): return next((r for r in self.roles if int(rid) == r.id), None)
    def get_member(self, uid): return Member()


ROLES = [Role(101, "Legend"), Role(102, "vRG HM"), Role(103, "Master Angler")]
guild = Guild(ROLES)


class Presets:
    docs = {}
    def preset(self, gid, name): return self.docs.get(name)
    def save_preset(self, gid, name, data, *, author_id=0, author_name=""):
        self.docs[name] = {"name": name, "author_id": author_id,
                           "author_name": author_name, **data}
    def delete_preset(self, gid, name): self.docs.pop(name, None)
    def get(self, gid): return {}


class Bot:
    trial_ranks = Presets()
    def get_cog(self, n): return None


class Req(dict):
    method = "POST"
    def __init__(self, payload):
        super().__init__(uid=777, scope=panel_access.SCOPE_CONFIG, guild=guild)
        self._payload = payload
        self.app = {"bot": Bot()}
        self.match_info = {"gid": "42"}
    async def json(self): return self._payload


# Exactly what the panel sends: role ids as strings, ranks from readRanks().
payload = {
    "action": "preset_save",
    "name": "Season 1",
    "points": {"102": 25, "103": 20},
    "ranks": [{"role_id": "101", "min_points": 40, "description": "Top"}],
    "trials": [{"name": "vRG", "slots": {"full_hm": "102"}}],
}

handler = routes.api_guild_trials
inner = getattr(handler, "__wrapped__", handler)   # skip the scope decorator
try:
    resp = asyncio.run(inner(Req(payload)))
    print("status:", resp.status)
    print("body:", resp.text)
    assert resp.status == 200 and '"ok": true' in resp.text.lower(), resp.text
except Exception:
    traceback.print_exc()
    print("\n>>> 500 reproduced <<<")
    sys.exit(1)

def call(payload):
    return asyncio.run(inner(Req(payload)))

# Load it back, the way the panel does.
loaded = call({"action": "preset_load", "name": "Season 1"})
print("load:", loaded.status, loaded.text[:160])
assert loaded.status == 200 and '"ok": true' in loaded.text.lower()

# Overwrite it as the same author (the reported case).
again = call({**payload, "points": {"102": 30}})
print("overwrite:", again.status, again.text)
assert '"ok": true' in again.text.lower(), again.text

# Someone else must be refused with a *message*, never a bare failure.
class Other(Req):
    def __init__(self, payload):
        super().__init__(payload); self["uid"] = 999
resp = asyncio.run(inner(Other({**payload, "name": "Season 1"})))
print("other author:", resp.status, resp.text[:140])
assert resp.status == 200 and '"ok": false' in resp.text.lower()
import json as _j
assert _j.loads(resp.text).get("error"), "a refusal must carry a reason, or the UI shows 'Failed'"

# A role that has since been deleted: still a message, not a 500.
bad = call({**payload, "points": {"999999": 5}})
print("dead role:", bad.status, bad.text[:140])
assert '"ok": false' in bad.text.lower() and _j.loads(bad.text).get("error")
print("PASS")
