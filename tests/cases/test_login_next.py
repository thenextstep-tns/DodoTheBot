"""Panel: a link survives the sign-in, and the sign-in is never a surprise.

Somebody who follows a shared link (their town's map) while signed out is sent
to the welcome page with the page remembered, and lands on it afterwards. Only a
page on this site may be remembered: never another site, never the login itself.

The welcome page is there on purpose: an unknown site that bounces a visitor
straight into a Discord sign-in is what a phishing page does, and Google Safe
Browsing flagged the domain for it. Nothing signed-out goes to Discord without
the visitor clicking through a page that says what this is.
"""
import asyncio
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
            None, "/login?next=/x", "/oauth/callback?code=1", "/welcome?next=/x", "/" + "a" * 600):
    assert routes._safe_next(bad) == "", bad
print("next            only a page on this site is remembered")

# A signed-out visit to a page goes to the welcome page carrying it.
to = routes.login_redirect(make_mocked_request("GET", "/guild/7/dodoland/me/map?z=2"))
assert to.status == 302
target = urlparse(to.location)
assert target.path == "/welcome" and parse_qs(target.query)["next"] == ["/guild/7/dodoland/me/map?z=2"], to.location
# A form post is not replayed after sign-in: plain welcome.
assert routes.login_redirect(make_mocked_request("POST", "/api/guild/7/x")).location == "/welcome"
print("next            a signed-out page visit goes to the welcome page with the page in hand")

# The welcome page explains, links to the login with the page kept, and does not
# redirect by itself.
page = asyncio.run(routes.welcome(make_mocked_request("GET", "/welcome?next=%2Ftowns")))
assert page.status == 200, page.status
assert "discord.com" in page.text and "identify" in page.text
assert 'href="/login?next=%2Ftowns"' in page.text, "the button lost the page to return to"
assert "http-equiv" not in page.text and "location" not in page.text.lower(), "the welcome page redirects"
print("welcome         says what this is and where sign-in happens; the visitor clicks through")

print("PASS")
