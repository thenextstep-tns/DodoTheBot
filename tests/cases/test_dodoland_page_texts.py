"""DodoLand: every text on the entrance page is the server's to write.

Each is a setting with the page's own wording as its default; blank brings the default
back; markers like {server} are filled in; whatever an admin types is escaped, so
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
assert page_texts.say(params, G, "place_button") == "Place my town!"
print("texts           each is a setting whose default is the page's own wording")

params.set(G, page_texts.PREFIX + "place_button", "Let's go!")
assert page_texts.say(params, G, "place_button") == "Let&#x27;s go!"
params.set(G, page_texts.PREFIX + "place_button", "   ")
assert page_texts.say(params, G, "place_button") == "Place my town!", "blank did not bring the default back"
print("texts           an admin's wording is used; blank brings the default back")

assert "Everyone on Dodos gets" in page_texts.say(params, G, "welcome_lead", server="Dodos")
grow = page_texts.say(params, G, "grow_text", server="Dodos", building=("<b>Library</b>",))
assert "<b>Library</b>" in grow, "markup the page itself made was escaped"
params.set(G, page_texts.PREFIX + "welcome_title", '<script>alert(1)</script> & "quotes"')
foot = page_texts.say(params, G, "welcome_title")
assert "<script>" not in foot and "&lt;script&gt;" in foot, "an admin's text was not escaped"
params.set(G, page_texts.PREFIX + "name_placeholder", "{owner} Town")
assert page_texts.say(params, G, "name_placeholder", owner="<Nik>") == "&lt;Nik&gt; Town"
print("texts           markers are filled in, and nothing typed in can inject markup")

print("PASS")
