"""DodoLand: the two previews read different histories.

This file used to cover the public map and the per-player settle page. Both were
removed: none of DodoLand is ready to be seen by the people it ranks, and a
half-finished thing behind a URL somebody can paste is worse than no thing at
all. What survives is the part that was never about those pages.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland import standing, store as store_module  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

GUILD, NIK, LIB = 42, 1, 900

params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
store = ActivityStore(FakeCollection(), FakeCollection(), params)
store.record(GUILD, NIK, "message", channel_id=LIB, day="2026-08-20")
store.replace_days(GUILD, [{"user_id": NIK, "day": "2024-01-01",
                            "acts": {"message": 50}, "scored": {"message": 50},
                            "channels": {str(LIB): {"message": 50}}}], [])

everything = store.totals(GUILD, NIK, basis=store_module.BASIS_ALL)
scratch = store.totals(GUILD, NIK, basis=store_module.BASIS_LIVE)
rebuilt = store.totals(GUILD, NIK, basis=store_module.BASIS_BACKFILL)
assert everything == {"message": 51}, everything
assert scratch == {"message": 1}, scratch
assert rebuilt == {"message": 50}, rebuilt
print("previews        with-history, from-scratch and rebuilt-only are three answers")

# The backfill boundary reads the live history only, or it would move every time
# the rebuild ran and then refuse to rebuild anything at all.
assert store.first_day(GUILD) == "2026-08-20", store.first_day(GUILD)
assert store.first_day(GUILD, basis=store_module.BASIS_ALL) == "2024-01-01"
print("previews        the rebuild boundary still reads only the live history")

building = {"key": "library", "name": "Library", "icon": "", "metric_weights": {},
            "channels": {str(LIB): 1.0},
            "tiers": [{"title": "Desk", "percentile": 10, "floor": 1}]}
full = standing.guild_standings(store, params, GUILD, [building],
                                basis=store_module.BASIS_ALL)
lean = standing.guild_standings(store, params, GUILD, [building],
                                basis=store_module.BASIS_LIVE)
assert full["people"][NIK]["power"] > lean["people"][NIK]["power"]
assert full["basis"] == "all" and lean["basis"] == "live"
print("previews        the scorer honours the basis end to end")

# Nothing in DodoLand may be reachable without a gate, and there are exactly
# two kinds: the panel's scopes, and the player gate in ``web/dodoland/player.py``
# (signed in, still a member, and the server has opened the surface). What must
# never come back is a capability URL that is itself the credential — that is
# what the public map link and the settle page were, and why they were removed.
# ``tests/cases/test_dodoland_player.py`` holds down what the player gate means.
routes = pathlib.Path("web/dodoland/__init__.py").read_text(encoding="utf-8")
for line in routes.splitlines():
    stripped = line.strip()
    if stripped.startswith("web.get(") or stripped.startswith("web.post("):
        assert ("configure(" in stripped or "full(" in stripped
                or "player." in stripped), f"an unscoped DodoLand route: {stripped}"
assert "/m/{gid}" not in routes and "/t/{gid}" not in routes,     "a capability-link route came back"
print("scoping         every DodoLand route sits behind a scope or the player gate")

print("PASS")
