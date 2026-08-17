"""Render the whole guild cogs page for owner vs guild-admin and diff what leaks."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers import panel_access


class Cmd:
    def __init__(self, name, hidden=False):
        self.name, self.hidden, self.description = name, hidden, f"desc {name}"


class Cog:
    def __init__(self, cmds): self._c = cmds
    def get_commands(self): return self._c


class Vis:
    def stored_level(self, gid, name): return None
    def cog_enabled(self, gid, cog): return True
    def feature_enabled(self, gid, key): return True


class Params:
    def entries_for_cog(self, gid, cog): return []


class Guild:
    id, name, icon = 42, "Test Guild", None
    roles, channels = [], []


class Bot:
    def __init__(self):
        self.cogs = {
            "owner": Cog([Cmd("shutdown", hidden=True), Cmd("evalcode", hidden=True)]),
            "general": Cog([Cmd("help"), Cmd("debugstate", hidden=True)]),
            "fun": Cog([Cmd("roll")]),
            "spam": Cog([]),  # passive, no commands at all
        }
        self.visibility, self.params = Vis(), Params()
        self.panel_access = type("PA", (), {"grants": staticmethod(lambda gid: [])})()


routes.cog_categories.features_for_cog = lambda name: []

bot, guild = Bot(), Guild()
owner_html = routes._guild_html(bot, guild, scope=panel_access.SCOPE_OWNER)
admin_html = routes._guild_html(bot, guild, scope=panel_access.SCOPE_FULL)

for label, doc in (("OWNER", owner_html), ("ADMIN", admin_html)):
    print(f"--- {label}")
    for token in ("shutdown", "evalcode", "debugstate", "help", "roll",
                  "lvl-owner", "🔒", "Panel access", "Reload", "spam",
                  'id="cog-owner"'):
        print(f"   {token!r:20} -> {doc.count(token)}")

assert "shutdown" not in admin_html and "evalcode" not in admin_html
assert "debugstate" not in admin_html
assert 'id="cog-owner"' not in admin_html
assert "lvl-owner" not in admin_html and "🔒" not in admin_html
assert "Panel access" not in admin_html and "Reload" not in admin_html
assert "help" in admin_html and "roll" in admin_html
assert "spam" in admin_html  # real passive cog keeps its toggle
print("PASS")
