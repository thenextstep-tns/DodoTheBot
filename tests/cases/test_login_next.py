"""Panel: a link survives the sign-in.

Somebody who follows a shared link (their town's map) while signed out is sent
to the login with the page remembered, and lands on it afterwards. Only a page
on this site may be remembered: never another site, never the login itself.
"""
import pathlib
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aiohttp.test_utils import make_mocked_request  # noqa: E402

from web import routes  # noqa: E402

# What may be returned to.
assert routes._safe_next("/guild/1/dodoland/me/map") == "/guild/1/dodoland/me/map"
assert routes._safe_next("/towns?x=1") == "/towns?x=1"
for bad in ("https://evil.example/", "//evil.example/x", "/\\evil.example", "evil", "",
            None, "/login?next=/x", "/oauth/callback?code=1", "/" + "a" * 600):
    assert routes._safe_next(bad) == "", bad
print("next            only a page on this site is remembered")

# A signed-out visit to a page goes to the login carrying it.
to = routes.login_redirect(make_mocked_request("GET", "/guild/7/dodoland/me/map?z=2"))
assert to.status == 302
target = urlparse(to.location)
assert target.path == "/login" and parse_qs(target.query)["next"] == ["/guild/7/dodoland/me/map?z=2"], to.location
# A form post is not replayed after sign-in: plain login.
assert routes.login_redirect(make_mocked_request("POST", "/api/guild/7/x")).location == "/login"
print("next            a signed-out page visit goes to the login with the page in hand")

print("PASS")
