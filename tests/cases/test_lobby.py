"""Getting into a fight: the roster, and the button in the sign-up window.

The case that matters is the person who owns two thousand cats, has never picked
one, and has just pressed a button. They must not be sent away to read anything.
"""
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import config_py
from scrap_lab import FakeCollection

from helpers import scrap, scrap_lobby


class Cats(FakeCollection):
    def find_one(self, query):
        found = self.find(query)
        return found[0] if found else None


cats, dogs, rosters = Cats(), Cats(), Cats()
config_py.catcollection, config_py.dogcollection = cats, dogs
scrap_lobby._collections = lambda: {"cat": cats}
scrap_lobby._roster_collection = lambda: rosters

FOX = 309719542115074049


def add(name, total_bias=0, owner=FOX, collection=None):
    doc = {"_id": name.lower(), "name": name, "owner": owner,
           "strength": 10 + total_bias, "agility": 10, "intellect": 10, "charm": 10}
    (collection or cats).docs.append(doc)
    return doc


# --- nothing at all ----------------------------------------------------------
assert scrap_lobby.join(FOX)["status"] == scrap_lobby.NO_CATS
assert "Claim one" in scrap_lobby.explain(scrap_lobby.join(FOX))
print("somebody with no cats is told how to get one, not what a roster is")

# --- owns cats, has never picked ---------------------------------------------
add("Bobo")
add("Mittens", total_bias=25)
add("Rex", total_bias=5)
result = scrap_lobby.join(FOX)
assert result["status"] == scrap_lobby.NO_ROSTER
assert result["best"]["name"] == "Mittens", result["best"]
assert result["owned"] == 3
message = scrap_lobby.explain(result)
assert "Mittens" in message and "3 cats" in message
assert len(message) < 220, "one sentence, not a manual"
print("somebody who never picked is offered their best cat by name: %r" % result["best"]["name"])

# --- and the shortcut actually enrols them -----------------------------------
auto = scrap_lobby.join(FOX, auto=True)
assert auto["status"] == scrap_lobby.READY and auto.get("auto") is True
assert [c["name"] for c in auto["cats"]] == ["Mittens"]
assert [p["name"] for p in scrap_lobby.roster(FOX)] == ["Mittens"], "the pick sticks for next time"
print("saying yes to the shortcut enrols the cat rather than fighting once and forgetting")

# --- a roster just works -----------------------------------------------------
scrap_lobby.enrol(FOX, "bobo")
assert [p["name"] for p in scrap_lobby.roster(FOX)] == ["Bobo", "Mittens"], "newest first"
assert [c["name"] for c in scrap_lobby.join(FOX)["cats"]] == ["Bobo", "Mittens"]
print("a roster sends everyone on it, most recently summoned first")

# --- cats already in this fight are not sent twice ---------------------------
partial = scrap_lobby.join(FOX, already=["bobo"])
assert [c["name"] for c in partial["cats"]] == ["Mittens"]
assert scrap_lobby.join(FOX, already=["bobo", "mittens"])["status"] == scrap_lobby.ALREADY_IN
print("cats already on the sand are not sent in again")

# --- the roster is capped, and drops the oldest ------------------------------
for index in range(int(scrap.TUNING["roster_max"]) + 3):
    add("Spare%d" % index)
    scrap_lobby.enrol(FOX, "spare%d" % index)
assert len(scrap_lobby.roster(FOX)) == int(scrap.TUNING["roster_max"])
assert "Bobo" not in [p["name"] for p in scrap_lobby.roster(FOX)], "the oldest fell off the end"
print("the roster caps at %d and pushes the oldest out" % scrap.TUNING["roster_max"])

# --- a cat that no longer exists just falls out ------------------------------
cats.docs = [d for d in cats.docs if d["_id"] != "spare5"]
assert all(p["name"] != "Spare5" for p in scrap_lobby.roster(FOX))
print("a cat lost to a pink slip leaves the roster instead of breaking the join")

# --- dogs are not fighters ---------------------------------------------------
# "Pick my best" used to reach into the dog collection and put a Working Dog on
# a cat's roster. It is a cat fight; dogs get thrown in as objects instead.
other = 645590542125629470
add("Nugget", total_bias=40, owner=other, collection=dogs)
add("Tiddles", owner=other)
assert scrap_lobby.join(other)["best"]["name"] == "Tiddles", "a dog must never be picked"
assert all(p["name"] != "Nugget" for p in scrap_lobby.owned(other))
print("the best-cat pick never reaches into the dog collection")

# And the real, unpatched map is cats only, which is what production uses.
import importlib  # noqa: E402
_fresh = importlib.reload(importlib.import_module("helpers.scrap_lobby"))
assert set(_fresh._collections()) == {"cat"}, set(_fresh._collections())
print("the shipped collection map is cats only")

# --- the engine takes what this hands it -------------------------------------
fighter = scrap_lobby.as_fighter(scrap_lobby.best_of(scrap_lobby.owned(FOX)))
assert set(scrap.ATTRIBUTES) <= set(fighter) and fighter["ident"]
result = scrap.simulate([fighter], [scrap_lobby.as_fighter(add("Enemy", owner=other))], seed=1)
assert result["winner"] in ("A", "B")
assert result["outcome"]["records"][0]["ident"], "the record can be written back to the pet"
print("a roster cat drops straight into the engine and comes out with a record")

# --- the boxing glove on a summoned cat -------------------------------------
import config_py  # noqa: E402
from cogs import pet as pet_cog  # noqa: E402

GLOVE = "🥊"
assert GLOVE in config_py.pet_actions, "the glove has to be offered, or nobody can press it"
assert set(config_py.pet_actions) >= {"🐟", "💪", GLOVE}
assert hasattr(pet_cog.Pet, "enrol_for_fights"), "the glove needs somewhere to land"
print("summon offers fish, gym and glove, and the glove has a handler")

# --- the glove is a toggle, like the fish and the dumbbell beside it ---------
rosters.docs.clear()
scrap_lobby.enrol(FOX, "bobo")
assert [p["name"] for p in scrap_lobby.roster(FOX)] == ["Bobo"]
scrap_lobby.release(FOX, "bobo")
assert scrap_lobby.roster(FOX) == [], "pressing the glove again must take the cat off"
scrap_lobby.enrol(FOX, "bobo")
assert [p["name"] for p in scrap_lobby.roster(FOX)] == ["Bobo"], "and put it back on"
print("the roster supports taking a cat off, not only adding it")

print("PASS")
