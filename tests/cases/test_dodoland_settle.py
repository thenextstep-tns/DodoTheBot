"""DodoLand: the player's own settle page, and the two previews.

The settle page has no login: the token in the URL is the credential. So the
security properties are asserted directly, because every one of them fails
silently and in the wrong direction.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers import share_tokens  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.dodoland import standing, store as store_module  # noqa: E402
from helpers.dodoland.buildings import BuildingStore  # noqa: E402
from helpers.dodoland.store import ActivityStore  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402
from web.dodoland import settle  # noqa: E402

GUILD, OTHER = 42, 77
NIK, FOX = 1, 2
LIB = 900


class Member:
    bot = False

    def __init__(self, uid, name):
        self.id, self.name, self.display_name = uid, name, name


class Guild:
    name, id = "ESO for Dodos", GUILD

    def __init__(self):
        self.members = [Member(NIK, "Nik"), Member(FOX, "Fox")]
        self.channels = []

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_role(self, rid):
        return None


class TrialRanks:
    def get(self, gid):
        return {"ranks": []}

    def standings(self, gid, limit=100):
        return []


class Bot:
    def __init__(self):
        self.dodoland_params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
        self.dodoland = ActivityStore(FakeCollection(), FakeCollection(), self.dodoland_params)
        self.dodoland_buildings = BuildingStore(FakeCollection())
        self.share_tokens = share_tokens.ShareTokenStore(FakeCollection())
        self.trial_ranks = TrialRanks()
        self.guild = Guild()

    def get_guild(self, gid):
        return self.guild if int(gid) == GUILD else None


bot = Bot()
bot.dodoland_buildings.save_map(GUILD, {"data": b"\x89PNG-not-really",
                                        "content_type": "image/png"})
bot.dodoland.record(GUILD, NIK, "message", channel_id=LIB)
bot.dodoland.record(GUILD, FOX, "message", channel_id=LIB)

token = bot.share_tokens.issue(GUILD, kind=share_tokens.KIND_USER, user_id=NIK)
assert token


class Request(dict):
    def __init__(self, app, match, body=None):
        super().__init__()
        self.app = app
        self.match_info = match
        self._body = body or {}

    async def json(self):
        return self._body


def get(match):
    return asyncio.run(settle.settle_page(Request({"bot": bot}, match)))


def post(match, body):
    return asyncio.run(settle.api_settle_own(Request({"bot": bot}, match, body)))


# --------------------------------------------------------------------------- #
#  The page renders, and it is a player's page rather than the panel
# --------------------------------------------------------------------------- #
page = get({"gid": str(GUILD), "token": token})
assert page.status == 200
body = page.text
assert "Your town" in body
assert "panel.css" not in body, "the player page pulled in the admin stylesheet"
assert "dlpaper" in body and "--lantern" in body
print(f"page            renders its own cosy page, {len(body):,} bytes, no panel.css")

# A token in a URL leaks through referrers, caches and search engines.
for header, expected in (("Referrer-Policy", "no-referrer"),
                         ("X-Robots-Tag", "noindex, nofollow"),
                         ("Cache-Control", "no-store")):
    assert page.headers.get(header) == expected, header
assert "noindex" in body and "no-referrer" in body
print("page            no referrer, no index, no cache: the URL is a credential")

# Their own town is marked, and it is the only one that gets a label on a phone.
assert "dltown mine" in body or "mine" in body
print("page            the reader's own town is the one picked out")


# --------------------------------------------------------------------------- #
#  A link moves exactly one town: the one it names
# --------------------------------------------------------------------------- #
result = post({"gid": str(GUILD), "token": token}, {"x": 30, "y": 60})
assert result.status == 200
plots = bot.dodoland_buildings.plots(GUILD)
assert plots[NIK] == {"x": 30.0, "y": 60.0}, plots
assert FOX not in plots
print("settling        a player places their own town, and it is stored")

# The user id comes from the token, never the payload. Editing the body must not
# let somebody move anybody else's town.
post({"gid": str(GUILD), "token": token}, {"x": 10, "y": 10, "user_id": FOX})
plots = bot.dodoland_buildings.plots(GUILD)
assert plots[NIK] == {"x": 10.0, "y": 10.0}
assert FOX not in plots, "a payload field moved somebody else's town"
print("security        the payload cannot name a different person")

# Re-settling moves rather than making a second town.
assert len(bot.dodoland_buildings.plots(GUILD)) == 1
print("settling        moving moves: one person keeps one town")

# Off-map coordinates are clamped rather than stored.
post({"gid": str(GUILD), "token": token}, {"x": -500, "y": 9000})
spot = bot.dodoland_buildings.plots(GUILD)[NIK]
assert 0 <= spot["x"] <= 100 and 0 <= spot["y"] <= 100, spot
print("settling        a town can never be placed off the edge of the world")


# --------------------------------------------------------------------------- #
#  Bad tokens tell you nothing
# --------------------------------------------------------------------------- #
for match, why in (
    ({"gid": str(GUILD), "token": "wrong-token"}, "a wrong token"),
    ({"gid": str(OTHER), "token": token}, "a token used on another guild"),
    ({"gid": "not-a-number", "token": token}, "a nonsense guild"),
):
    assert get(match).status == 404, f"{why} was not refused"
    assert post(match, {"x": 1, "y": 1}).status == 404, f"{why} could still write"
print("security        wrong token, wrong guild and nonsense all answer 404 alike")

# A guild-wide public token must not work as somebody's personal settle link.
public = bot.share_tokens.issue(GUILD, kind=share_tokens.KIND_PUBLIC)
assert get({"gid": str(GUILD), "token": public}).status == 404
print("security        a public board link is not a licence to move a town")

# Revoking is immediate.
bot.share_tokens.revoke_all(GUILD, kind=share_tokens.KIND_USER, user_id=NIK)
assert get({"gid": str(GUILD), "token": token}).status == 404
print("security        revoking a link stops it at once")


# --------------------------------------------------------------------------- #
#  The two previews read different histories
# --------------------------------------------------------------------------- #
store = ActivityStore(FakeCollection(), FakeCollection(), bot.dodoland_params)
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
            "channels": {LIB: 1.0},
            "tiers": [{"title": "Desk", "percentile": 10, "floor": 1}]}
full = standing.guild_standings(store, bot.dodoland_params, GUILD, [building],
                                basis=store_module.BASIS_ALL)
lean = standing.guild_standings(store, bot.dodoland_params, GUILD, [building],
                                basis=store_module.BASIS_LIVE)
assert full["people"][NIK]["power"] > lean["people"][NIK]["power"]
assert full["basis"] == "all" and lean["basis"] == "live"
print("previews        the scorer honours the basis end to end")

print("PASS")
