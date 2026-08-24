"""Summon name matching: what wins, and what has to be confirmed first.

The bug this locks down: `summon Bobo` used to walk straight past the question
and summon "Bobobo", because a single partial match was treated as certainty.
"""
import asyncio
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from cogs.pet import Pet


class FakeCol:
    """The one pymongo method find_pets uses."""
    def __init__(self, *names): self.docs = [{"name": n, "owner": 1, "url": "u"} for n in names]
    def find(self, q): return [dict(d) for d in self.docs if all(d.get(k) == v for k, v in q.items())]


def cog(cats=(), dogs=(), waifus=()):
    pet = Pet.__new__(Pet)
    pet.pet_collections = {"cat": FakeCol(*cats), "dog": FakeCol(*dogs), "waifu": FakeCol(*waifus)}
    return pet


def match(pet, query, cutoff=0.7):
    tier, pets = pet.find_pets(1, query, cutoff=cutoff)
    return tier, [p["name"] for p in pets]

# --- the reported case -------------------------------------------------------
assert match(cog(cats=["Bobobo"]), "Bobo") == ("prefix", ["Bobobo"]), match(cog(cats=["Bobobo"]), "Bobo")
print("'Bobo' vs a lone 'Bobobo': prefix tier, not treated as exact")

# --- an exact name is never beaten by a longer one ---------------------------
assert match(cog(cats=["Bobobo", "Bobo"]), "Bobo") == ("exact", ["Bobo"])
assert match(cog(cats=["Bo", "Bobobo"]), "bo") == ("exact", ["Bo"]), "case-insensitive exact still wins"
print("an exact name wins outright, whatever else contains it")

# --- tiers are strictly ordered ---------------------------------------------
assert match(cog(cats=["Bobobo", "My bobo account"]), "Bobo") == ("prefix", ["Bobobo"]), \
    "a name starting with the query beats one merely containing it"
assert match(cog(cats=["My bobo account"]), "Bobo") == ("substring", ["My bobo account"])
assert match(cog(cats=["Bobobo"]), "Bobbo")[0] == "fuzzy", "a typo still finds it, as the last resort"
assert match(cog(cats=["Bobobo", "Bobbo"]), "Bobbo") == ("exact", ["Bobbo"]), \
    "an exact name is not dragged into the fuzzy tier"
print("tiers: exact > prefix > substring > fuzzy, best non-empty tier wins alone")

# --- within a tier, the closest name comes first ------------------------------
assert match(cog(cats=["Bobobobobo", "Bobob"]), "Bobo")[1] == ["Bobob", "Bobobobobo"]
print("inside a tier the closest name is offered first")

# --- ties across collections --------------------------------------------------
tier, names = match(cog(cats=["Rex"], dogs=["Rex"]), "Rex")
assert (tier, sorted(names)) == ("exact", ["Rex", "Rex"]), (tier, names)
print("a cat and a dog with one name is a real tie, still a question")

# --- nothing at all ------------------------------------------------------------
assert match(cog(cats=["Bobobo"]), "zzzzzz") == (None, [])
assert match(cog(cats=["Bobobo"]), "   ") == (None, []), "a blank name matches nothing, not everything"
assert match(cog(cats=["Bobobo"]), "Bobbo", cutoff=1.0) == (None, []), "cutoff 1 disables typo matching"
print("no match, blank query and a disabled cutoff all come back empty")


# --- routing: which of the three paths summon actually takes -------------------
class FakeAuthor:
    id = 1
    display_name = "nik"


class FakeContext:
    guild = None
    author = FakeAuthor()
    def __init__(self): self.sent = []
    async def send(self, *a, **k): self.sent.append(a[0] if a else k)


class FakeParams:
    def get(self, guild_id, key): return {"summon_fuzzy_cutoff": 0.7, "summon_max_matches": 25,
                                          "summon_choice_timeout": 30}[key]


def route(cats, query):
    """Run summon with the three outcomes stubbed; return which one fired."""
    pet = cog(cats=cats)
    pet.bot = type("B", (), {"params": FakeParams()})()
    fired = []
    async def summoned(context, p): fired.append(("summoned", p["name"]))
    async def confirm(context, p, name): fired.append(("confirm", p["name"]))
    async def choose(context, pets, name, *, exact): fired.append(("choose", exact, [p["name"] for p in pets]))
    pet.handle_pet_interaction, pet.confirm_pet_guess, pet.ask_user_to_choose_pet = summoned, confirm, choose
    context = FakeContext()
    asyncio.run(Pet.summon.callback(pet, context, pet_name=query))
    return fired[0] if fired else ("nothing", context.sent)


assert route(["Bobobo"], "Bobo") == ("confirm", "Bobobo"), route(["Bobobo"], "Bobo")
print("one near-miss is offered back, never summoned on its own")

assert route(["Bobo", "Bobobo"], "Bobo") == ("summoned", "Bobo")
print("an exact name summons with no extra click")

assert route(["Bobobo", "Bobos"], "Bobo") == ("choose", False, ["Bobos", "Bobobo"])
print("several near-misses go to the dropdown, flagged as inexact")

assert route(["Bobobo"], "zzzz")[0] == "nothing"
print("nothing close summons nothing")

print("PASS")
