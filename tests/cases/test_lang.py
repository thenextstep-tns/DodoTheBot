"""Fallback chain, scoped writes, and validation that refuses only real breakage."""
import sys, types
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers.lang_manager import LangManager, HARD_LIMIT, MESSAGE_LIMIT, _normalise_locale


class Col:
    def __init__(self): self.docs = []
    def _m(self, q, d):
        return all(d.get(k) == v for k, v in q.items())
    def find(self, q=None): return [d for d in self.docs if self._m(q or {}, d)]
    def find_one(self, q): return next(iter(self.find(q)), None)
    def distinct(self, field): return list({d.get(field) for d in self.docs})
    def update_one(self, q, u, upsert=False):
        doc = self.find_one(q)
        if doc is None:
            doc = dict(q); self.docs.append(doc)
        doc.update(u.get("$set", {}))
    def delete_one(self, q):
        doc = self.find_one(q)
        if doc: self.docs.remove(doc)


def fresh():
    mod = types.ModuleType("lang")
    mod.GREETING = "Hello {name}"
    mod.PLAIN = "Just words"
    mod.TRIAL_BUTTON_LABEL = "CHECK MY RANK"
    return mod, Col()


# --- legacy rows (no scope fields) are the global/default layer ---
mod, col = fresh()
col.docs.append({"key": "PLAIN", "value": "Legacy override"})
mgr = LangManager(mod, col)
assert mod.PLAIN == "Legacy override", "pre-scope rows must still apply"
assert mgr.get("PLAIN") == "Legacy override"
print("legacy rows honoured:", mod.PLAIN)

# --- the chain ---
mod, col = fresh()
mgr = LangManager(mod, col)
assert mgr.get("GREETING") == "Hello {name}", "ends at the constant"

mgr.set("GREETING", "Global hi {name}")
assert mod.GREETING == "Global hi {name}", "global/default still mutates the module"
assert mgr.get("GREETING") == "Global hi {name}"

mgr.set("GREETING", "Globalny {name}", locale="pl")
mgr.set("GREETING", "Server hi {name}", guild_id=42)
mgr.set("GREETING", "Serwer {name}", guild_id=42, locale="pl")

cases = [
    (dict(guild=42, locale="pl"), "Serwer {name}"),
    (dict(guild=42, locale="de"), "Server hi {name}"),   # guild, no de -> guild default
    (dict(guild=99, locale="pl"), "Globalny {name}"),    # other guild -> global pl
    (dict(guild=99, locale="de"), "Global hi {name}"),   # -> global default
    (dict(), "Global hi {name}"),
]
for kwargs, expect in cases:
    got = mgr.get("GREETING", **kwargs)
    print(f"   {str(kwargs):34} -> {got}")
    assert got == expect, (kwargs, got, expect)

# A guild override must never leak into the process-wide module.
assert mod.GREETING == "Global hi {name}", "per-guild wording escaped into lang.KEY"
mgr.apply_all()
assert mod.GREETING == "Global hi {name}", "apply_all must only replay the global layer"
print("module still global-only:", mod.GREETING)

# --- reset peels one layer ---
mgr.reset("GREETING", guild_id=42, locale="pl")
assert mgr.get("GREETING", guild=42, locale="pl") == "Server hi {name}"
mgr.reset("GREETING")
assert mod.GREETING == "Hello {name}", "resetting global restores the constant"
print("reset falls through correctly")

assert _normalise_locale("EN_gb") == "en-GB" and _normalise_locale("  ") is None

# --- validation: refuse only what breaks ---
mod, col = fresh()
mgr = LangManager(mod, col)
assert mgr.validate("GREETING", "Hi {name} {oops}"), "new placeholder is refused"
assert mgr.validate("GREETING", "x" * (HARD_LIMIT + 1)), "over the hard cap is refused"
assert mgr.validate("GREETING", "Hi") is None, "dropping a placeholder is allowed"
assert mgr.validate("NOPE", "x"), "unknown key refused"
print("errors:", mgr.validate("GREETING", "Hi {name} {oops}"))

warn = lambda v, **kw: mgr.warnings("GREETING", v, **kw)
assert any("Drops placeholder" in w for w in warn("Hi")), warn("Hi")
assert any("too long for a plain message" in w for w in warn("x" * (MESSAGE_LIMIT + 1)))
assert any("Unbalanced bold" in w for w in warn("**oops {name}"))
assert any("@everyone" in w for w in warn("hey @everyone {name}"))
assert any("Custom server emoji" in w for w in warn("hi <:dodo:123> {name}"))
assert not any("Custom server emoji" in w for w in warn("hi <:dodo:123> {name}", guild_id=42)), \
    "a guild's own emoji is fine in that guild's wording"
assert warn("Hello {name}") == [], "a clean edit says nothing"
long_label = mgr.warnings("TRIAL_BUTTON_LABEL", "x" * 90)
assert any("button label" in w for w in long_label), long_label
print("warnings:", warn("**hey @everyone <:dodo:1> "))
print("PASS")
