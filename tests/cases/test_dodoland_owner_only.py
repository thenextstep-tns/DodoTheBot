"""DodoLand's admin side is the bot owner's alone, for now.

While the map is being built one wrong click by a server admin could wipe a
world, so every admin-side DodoLand route (pages, readers and every write)
takes the bot owner's scope: a server's owner or a full-scope admin gets the
same 404 as a stranger, and the menu item is hidden from them. Members' own
pages are not affected. These go through the real route table and gate.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aiohttp.test_utils import make_mocked_request  # noqa: E402

from helpers import panel_access  # noqa: E402
from web import auth, dodoland, routes  # noqa: E402

OWNER, ADMIN, G = 1, 2, 55


class Member:
    def __init__(self, uid):
        self.id = uid


class Guild:
    id = G
    owner_id = ADMIN   # the server's own owner, and a full-scope admin
    name = "Dodos"

    def get_member(self, uid):
        return Member(uid)


class Visibility:
    def is_owner(self, uid):
        return int(uid) == OWNER


class Access:
    def scope_for_member(self, gid, member):
        return panel_access.SCOPE_FULL


class Bot:
    visibility = Visibility()
    panel_access = Access()

    def get_guild(self, gid):
        return Guild() if int(gid) == G else None


assert dodoland.OWNER_ONLY, "the DodoLand admin side is open to server admins"
admin_routes = [r for r in dodoland.dodoland_routes()
                if "/dodoland/me" not in r.path and r.path != "/towns" and "{gid}" in r.path]
assert len(admin_routes) >= 25, f"only {len(admin_routes)} admin routes found"


def call(route, uid):
    path = route.path.replace("{gid}", str(G))
    for name in ("{uid}", "{aid}", "{vid}"):
        path = path.replace(name, "1")
    match = {"gid": str(G), "uid": "1", "aid": "1", "vid": "1"}
    request = make_mocked_request(route.method, path, match_info=match,
                                  headers={"Cookie": f"{auth.SESSION_COOKIE}={auth.make_session(uid)}"},
                                  app={"bot": Bot()})
    try:
        return asyncio.run(route.handler(request))
    except Exception as error:  # noqa: BLE001 - past the gate, the fake bot runs out
        return error


for route in admin_routes:
    got = call(route, ADMIN)
    assert getattr(got, "status", None) == 404, f"a server admin reached {route.method} {route.path}"
print(f"gate            a server's owner and full admins get 404 on all {len(admin_routes)} admin routes")

passed = 0
for route in admin_routes:
    got = call(route, OWNER)
    if not (getattr(got, "status", None) == 404 and getattr(got, "text", "") == "Guild not found."):
        passed += 1
assert passed == len(admin_routes), f"the bot owner was turned away from {len(admin_routes) - passed} routes"
print("gate            the bot owner gets through every one")

assert routes._dodoland_scope() == panel_access.SCOPE_OWNER
nav_admin = routes._guild_nav(Guild(), panel_access.SCOPE_FULL, "")
nav_owner = routes._guild_nav(Guild(), panel_access.SCOPE_OWNER, "")
assert "DodoLand" not in nav_admin and "DodoLand" in nav_owner, "the menu item shows to server admins"
print("menu            the DodoLand menu item is the bot owner's only")

print("PASS")
