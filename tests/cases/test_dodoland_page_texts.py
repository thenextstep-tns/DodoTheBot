"""DodoLand: every text on a member's town page is the server's to write.

Each is a setting with the old wording as its default; blank brings the default
back; markers like {days} are filled in; whatever an admin types is escaped, so
it can neither break the page nor run in a member's browser.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fake_mongo import FakeCollection  # noqa: E402

from helpers.dodoland import page_texts  # noqa: E402
from helpers.dodoland import parameters as dodo_params  # noqa: E402
from helpers.parameters import ParamManager  # noqa: E402

params = ParamManager(FakeCollection(), dodo_params.DODOLAND_PARAMETERS)
G = 5

keys = {spec["key"] for spec in dodo_params.DODOLAND_PARAMETERS}
assert all(page_texts.PREFIX + k in keys for k in page_texts.DEFAULTS), "a page text is not a setting"
assert page_texts.say(params, G, "decorate_title") == "Decorate"
print("texts           each is a setting whose default is the wording the page always had")

params.set(G, page_texts.PREFIX + "decorate_title", "Make it yours")
assert page_texts.say(params, G, "decorate_title") == "Make it yours"
params.set(G, page_texts.PREFIX + "decorate_title", "   ")
assert page_texts.say(params, G, "decorate_title") == "Decorate", "blank did not bring the default back"
print("texts           an admin's wording is used; blank brings the default back")

assert "over the last 30 days" in page_texts.say(params, G, "reached_intro", days=30)
rank = page_texts.say(params, G, "flourish_from", rank=("<b>Legend</b>",))
assert "<b>Legend</b>" in rank, "markup the page itself made was escaped"
params.set(G, page_texts.PREFIX + "foot", '<script>alert(1)</script> & "quotes"')
foot = page_texts.say(params, G, "foot")
assert "<script>" not in foot and "&lt;script&gt;" in foot, "an admin's text was not escaped"
params.set(G, page_texts.PREFIX + "owner_line", "{owner} of {server}")
assert page_texts.say(params, G, "owner_line", owner="<Nik>", server="Dodos") == "&lt;Nik&gt; of Dodos"
print("texts           markers are filled in, and nothing typed in can inject markup")

print("PASS")
