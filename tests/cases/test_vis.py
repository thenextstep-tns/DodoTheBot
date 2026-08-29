"""Check that a guild-admin scope never sees owner-level commands/cogs."""
import sys, types
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers import panel_access
from helpers.visibility import LEVEL_OWNER, LEVEL_VISIBLE


class Cmd:
    def __init__(self, name, hidden=False):
        self.name, self.hidden, self.description = name, hidden, f"desc {name}"


class Cog:
    def __init__(self, cmds): self._c = cmds
    def get_commands(self): return self._c


class Vis:
    def __init__(self, stored=None): self.stored = stored or {}
    def stored_level(self, gid, name): return self.stored.get(name)
    def cog_enabled(self, gid, cog): return True
    def feature_enabled(self, gid, key): return True


class Params:
    def entries_for_cog(self, gid, cog): return []


class Bot:
    def __init__(self, cogs, vis):
        self.cogs, self.visibility, self.params = cogs, vis, Params()


routes.cog_categories.features_for_cog = lambda name: []

bot = Bot(
    {"owner": Cog([Cmd("shutdown", hidden=True), Cmd("evalcode", hidden=True)]),
     "fun": Cog([Cmd("roll"), Cmd("secret", hidden=True)])},
    Vis({"roll": LEVEL_VISIBLE}),
)

for scope in (panel_access.SCOPE_OWNER, panel_access.SCOPE_FULL):
    print(f"--- scope={scope}")
    for name in ("owner", "fun"):
        d = routes._cog_detail(bot, 1, name, scope=scope)
        print(f"  {name}: cmds={[c['name'] for c in d['commands']]} "
              f"level={d['level']} hidden={d['hidden']}")
        html = routes._command_cards(d["commands"], scope)
        assert ">owner<" not in html or scope == panel_access.SCOPE_OWNER, "owner leaked into HTML"
        assert "lvl-owner" not in html or scope == panel_access.SCOPE_OWNER, "owner card leaked"
        if scope != panel_access.SCOPE_OWNER:
            assert "secret" not in html and "shutdown" not in html, "hidden cmd leaked"

# owner cog must drop out for an admin, fun must survive
admin = [routes._cog_detail(bot, 1, n, scope=panel_access.SCOPE_FULL) for n in ("owner", "fun")]
kept = [m for m in admin if m["commands"] or m["features"] or m["params"] or not m["hidden"]]
print("kept for admin:", [m["cog"] for m in kept])
assert [m["cog"] for m in kept] == ["fun"]
print("PASS")
