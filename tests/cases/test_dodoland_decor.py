"""DodoLand's toolkit: putting something from the library on the ground.

The library, the tier locks and the toolkit strip all existed for a long time
with nothing that could place one. This is that half, and what it mostly has to
hold down is who may put what where:

* an admin dressing the **map** is not spending an unlock;
* a member dressing their **own town** is, and the refusal lives on the server
  rather than in the dimmed button;
* and a member can never touch a piece that is not theirs, however they phrase
  the request.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import assets as asset_rules  # noqa: E402
from helpers.dodoland import decor as decor_rules  # noqa: E402
from helpers.dodoland.assets import AssetStore  # noqa: E402
from helpers.dodoland.decor import DecorStore  # noqa: E402

GUILD, NIK, FOX = 42, 1, 2

assets = AssetStore(FakeCollection())
store = DecorStore(FakeCollection())

free = assets.add(GUILD, name="Campfire", data=b"x", content_type="image/png")
locked = assets.add(GUILD, name="Gilded banner", data=b"x",
                    content_type="image/png", building="gallery", min_tier=3)


# --------------------------------------------------------------------------- #
#  What is unlocked
# --------------------------------------------------------------------------- #
library = assets.list(GUILD)
# Somebody with nothing built still has the starter decor. A library where
# nothing is available on day one gives nobody a reason to open the map twice.
nobody = asset_rules.unlocked_for(library, None)
assert free["asset_id"] in nobody and locked["asset_id"] not in nobody, nobody

# min_tier 3 means the third tier, which is index 2.
almost = {"buildings": {"gallery": {"tier": 1}}}
enough = {"buildings": {"gallery": {"tier": 2}}}
assert locked["asset_id"] not in asset_rules.unlocked_for(library, almost)
assert locked["asset_id"] in asset_rules.unlocked_for(library, enough)
print("locks           a lock is a tier of a building, and it is off by one on purpose")


# --------------------------------------------------------------------------- #
#  The locks are enforced where they cannot be edited
# --------------------------------------------------------------------------- #
# The toolkit dims what is locked as a courtesy. This is what actually refuses
# it, because a dimmed button is a suggestion and a request is whatever
# somebody types.
allowed = asset_rules.unlocked_for(library, None)
try:
    store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=NIK,
                asset_id=locked["asset_id"], x=50, y=50, allowed=allowed)
except decor_rules.DecorError as error:
    assert "unlocked" in str(error), error
else:
    raise AssertionError("a locked asset was placed by asking for it directly")
print("locks           the server refuses a locked asset, not the browser")

# An admin dressing the world is not spending an unlock: they wrote the locks.
world = store.place(GUILD, scope=decor_rules.SCOPE_WORLD,
                    asset_id=locked["asset_id"], x=10, y=20)
assert world["owner_id"] == 0, world
assert len(store.world(GUILD)) == 1
print("scopes          an admin dresses the map without spending an unlock")


# --------------------------------------------------------------------------- #
#  A piece belongs to exactly one person
# --------------------------------------------------------------------------- #
mine = store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=NIK,
                   asset_id=free["asset_id"], x=40, y=60, allowed=allowed)
assert mine["owner_id"] == NIK

# Knowing somebody's piece id gets you nothing: the owner is a *query term*, so
# the row is never found rather than found and then refused.
assert not store.move(GUILD, mine["piece_id"], x=1, y=1, owner_id=FOX)
assert not store.remove(GUILD, mine["piece_id"], owner_id=FOX)
assert store.town(GUILD, NIK)[0]["x"] == 40.0, "somebody else moved it"
assert store.move(GUILD, mine["piece_id"], x=12, owner_id=NIK)
assert store.town(GUILD, NIK)[0]["x"] == 12.0
print("ownership       another member cannot move or remove your decor")

# A member cannot reach the world's decor through the town endpoint's store
# call either, because that passes an owner and the world has none.
assert not store.remove(GUILD, world["piece_id"], owner_id=NIK)
assert len(store.world(GUILD)) == 1
print("ownership       the map's own decor is not reachable as a possession")


# --------------------------------------------------------------------------- #
#  Limits, and cleaning up
# --------------------------------------------------------------------------- #
for _ in range(decor_rules.MAX_PER_TOWN - 1):
    store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=NIK,
                asset_id=free["asset_id"], x=50, y=50, allowed=allowed)
try:
    store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=NIK,
                asset_id=free["asset_id"], x=50, y=50, allowed=allowed)
except decor_rules.DecorError as error:
    assert str(decor_rules.MAX_PER_TOWN) in str(error), error
else:
    raise AssertionError("a town went past its own limit")
# One person filling their plot must not stop anybody else placing anything.
other = store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=FOX,
                    asset_id=free["asset_id"], x=50, y=50, allowed=allowed)
assert other["owner_id"] == FOX
print(f"limits          a town holds at most {decor_rules.MAX_PER_TOWN}, and the limit is per person")

# An off-map position is refused rather than stored and drawn somewhere absurd.
for bad in (-900, 900, "over there", None):
    try:
        store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=FOX,
                    asset_id=free["asset_id"], x=bad, y=50, allowed=allowed)
    except decor_rules.DecorError:
        pass
    else:
        raise AssertionError(f"{bad!r} was accepted as a position")
print("limits          a position that is not a position is refused")

# Deleting an asset takes every placement of it. Left behind, they render as a
# broken image on somebody's town, which reads as their town being broken.
dropped = store.forget_asset(GUILD, free["asset_id"])
assert dropped >= 2, dropped
assert all(row["asset_id"] != free["asset_id"] for row in store.town(GUILD, NIK))
assert all(row["asset_id"] != free["asset_id"] for row in store.town(GUILD, FOX))
print(f"cleanup         removing an asset unplaces its {dropped} pieces everywhere")

# Taking a town off the map takes its decor with it: the pieces were placed
# relative to a town that is no longer anywhere.
store.place(GUILD, scope=decor_rules.SCOPE_TOWN, owner_id=NIK,
            asset_id=locked["asset_id"], x=50, y=50,
            allowed={locked["asset_id"]})
assert store.clear_town(GUILD, NIK) >= 1
assert store.town(GUILD, NIK) == []
assert len(store.world(GUILD)) == 1, "unsettling a town took the map's decor"
print("cleanup         unsettling a town clears its decor and nothing else")


# --------------------------------------------------------------------------- #
#  Guild scoping, which every DodoLand store owes
# --------------------------------------------------------------------------- #
store.place(GUILD, scope=decor_rules.SCOPE_WORLD, asset_id=locked["asset_id"],
            x=5, y=5)
assert store.world(99) == [], "another guild's map decor leaked"
assert store.towns(99) == {}, "another guild's town decor leaked"
print("scoping         one guild never sees another's ground")


# --------------------------------------------------------------------------- #
#  The endpoints take no user id
# --------------------------------------------------------------------------- #
source = pathlib.Path("web/dodoland/decor_api.py").read_text(encoding="utf-8")
player_half = source[source.index("async def api_town_decor"):]
for forbidden in ('body.get("user_id")', "body.get('user_id')",
                  'body.get("owner_id")', "query.get"):
    assert forbidden not in player_half,     f"a player decor handler takes an id from the request: {forbidden}"
# ...and every write it makes narrows on the session's own id.
assert player_half.count("owner_id=uid") >= 3,     "a player decor write does not scope itself to the session's own town"
print("safety          the session decides whose town is being decorated")

print("PASS")
