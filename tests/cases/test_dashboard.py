"""Dashboard status board, and the nav that used to vanish on the stats page."""
import inspect, re, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers import panel_access, health


class G:
    icon = None
    def __init__(self, i, n, m): self.id, self.name, self.member_count = i, n, m


class Mon(health.HealthMonitor):
    def __init__(self, rows=()): super().__init__(None); self._rows = list(rows)
    def samples(self, days=None): return self._rows


class Bot:
    guilds = [G(1, "ESO for Dodos", 452), G(2, "Test", 12)]
    latency = 0.083
    health = Mon()
    extensions = {}
    commands = []
    def is_ready(self): return True


entries = [(g, panel_access.SCOPE_OWNER) for g in Bot.guilds]
html = routes._dashboard_html(Bot(), entries, panel_access.SCOPE_OWNER)
assert "All Systems Operational" in html and "statusbanner ok" in html
assert "installations" in html and "464" in html and "83 ms" in html
assert "no history recorded yet" in html, "never imply uptime that wasn't measured"
assert html.count('class="hbar none"') == 90 and 'class="hbar ok"' not in html

# Each bar carries everything the hover card shows, so the popover needs no
# request and there is no second source of truth to drift from the bars.
import datetime
day = datetime.datetime.now(datetime.timezone.utc)
rows = ([{"at": day, "status": health.STATUS_DOWN, "latency_ms": None}] * 12
        + [{"at": day, "status": health.STATUS_OK, "latency_ms": 40}] * 12)
Bot.health = Mon(rows)
lit = routes._dashboard_html(Bot(), entries, panel_access.SCOPE_OWNER)
import re as _re
bar = _re.search(r'<span class="hbar down"[^>]*>', lit).group(0)
print("today's bar:", bar[:150])
for attr in ("data-day", "data-state", "data-uptime", "data-samples",
             "data-down", "data-degraded"):
    assert attr in bar, attr
assert 'data-down="1 hr"' in bar, bar        # 12 down samples x 5 min
assert 'data-samples="24"' in bar
assert 'tabindex="0"' in bar, "reachable by keyboard, not mouse-only"
assert 'id="hpop"' in lit, "the popover container is on the page"
print("bars carry date, state, uptime, sample count and outage duration")
Bot.health = Mon()

Bot.latency = 2.5
assert "Degraded" in routes._dashboard_html(Bot(), [], panel_access.SCOPE_OWNER)
Bot.latency = float("nan")   # discord.py before the first heartbeat
down = routes._dashboard_html(Bot(), [], panel_access.SCOPE_OWNER)
assert "Not connected" in down and "statusbanner down" in down
Bot.latency = 0.05

admin = routes._dashboard_html(Bot(), [(Bot.guilds[0], panel_access.SCOPE_CONFIG)],
                               panel_access.SCOPE_CONFIG)
assert "statusbanner" not in admin, "bot-wide health is owner-only"
print("status board: ok / degraded / down, and admins see none of it")

# The nav bar: the stats page used to rebind `scope` to a stats.Scope, which the
# nav reads as a permission level — so every link silently disappeared.
src = inspect.getsource(routes.guild_stats_page)
# Anchored: "query_scope = stats.Scope(" contains the bad substring.
assert not re.search(r"^\s*scope = stats\.Scope\(", src, re.M),     "stats.Scope must not shadow the panel scope"
assert re.search(r"^\s*query_scope = stats\.Scope\(", src, re.M)
nav = routes._guild_nav(Bot.guilds[0], panel_access.SCOPE_OWNER, "stats")
for label in ("Cogs", "Settings", "Events", "Trial ranks", "Stats", "Change log", "Tribes"):
    assert label in nav, f"missing from the top bar: {label}"
assert 'class="active"' in nav
print("stats nav intact:", nav.count("<a href") , "links")

# The Dashboard link is gone; the brand is the way back.
page = routes._page("x", "<p>y</p>", scope=panel_access.SCOPE_OWNER,
                    guild=Bot.guilds[0], current="stats")
body = page.text
assert ">Dashboard</a>" not in body, "the brand replaces the Dashboard link"
assert 'class="brand"' in body
print("PASS")
