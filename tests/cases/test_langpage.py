"""The rebuilt strings page: index, one panel open, one editor."""
import sys, types
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from web import routes
from helpers.lang_manager import LangManager


class Col:
    docs = []
    def find(self, q=None): return []
    def find_one(self, q): return None
    def distinct(self, f): return []
    def update_one(self, *a, **k): pass
    def delete_one(self, *a, **k): pass


mod = types.ModuleType("lang")
mod.TRIAL_CARD_TOP = "Top of the ladder"
mod.TRIAL_CONSENT_ASK = "Hey {mention}!"
mod.MOD_BAN = "Banned {user}"
mod.FUN_LIST = ["one", "two"]

mgr = LangManager(mod, Col())
html = routes._lang_html(type("B", (), {"lang": mgr})())

for want in ("langpage", "langnav", "langdrawer", "langsearch", "langedited",
             "drawersave", "drawerreset", "drawerph", "TRIAL_CARD_TOP", "MOD_BAN"):
    assert want in html, want

import re
panels = re.findall(r'<section class="langpanel"[^>]*>', html)
print("groups:", len(panels), "| hidden:", sum("hidden" in p for p in panels))
assert len(panels) == 3 and sum("hidden" in p for p in panels) == 2, \
    "one group open, the rest closed"

# The placeholder rides on the row so the drawer can offer it click-to-insert.
# Slice from this row to the next one rather than regexing nested divs.
_at = html.index('data-key="TRIAL_CONSENT_ASK"')
_next = html.find('<div class="langrow"', _at)
row = html[_at:_next if _next > 0 else _at + 1200]
assert "{mention}" in row and 'class="ph"' in row, row[:200]
# Rows are searchable on key *and* text.
assert 'data-search="' in row and "hey {mention}" in row.lower()
# Lists are marked so the editor knows to split on newlines.
assert 'data-list="1"' in html and ">list<" in html
# Not a page of live textareas any more: every row's value is a hidden index
# copy, and the only editable box is the drawer's single one.
index_copies = html.count('class="langvalue" hidden')
assert html.count("<textarea") == index_copies + 1, "exactly one editable textarea"
assert 'id="drawervalue"' in html
print("textareas:", index_copies, "hidden index copies + 1 editor")
print("PASS")
