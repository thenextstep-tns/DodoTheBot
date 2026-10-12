"""Naming a claimed pet: whose collection the name has to be unique in.

Anyone in the channel may name someone else's new pet — that race is the point
of the claim message. The bug this locks down: the uniqueness check used to run
against the *namer's* collection, so Fox naming Lyna's cat "Bobo" was refused
because Fox already owned a Bobo, while Lyna owned none.
"""
import asyncio
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from cogs.pet import Pet

FOX, LYNA = 309719542115074049, 645590542125629470


class FakeUser:
    def __init__(self, uid, bot=False): self.id, self.bot, self.display_name = uid, bot, str(uid)


class FakeChannel:
    def __init__(self, cid=1): self.id, self.sent = cid, []
    async def send(self, content=None, **k): self.sent.append(content)


class FakeMessage:
    def __init__(self, content, author, channel): self.content, self.author, self.channel = content, author, channel


class FakeCol:
    def __init__(self, *owned): self.docs = [{"name": n, "owner": o} for n, o in owned]
    def find_one(self, q): return next((d for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)
    def insert_one(self, doc): self.docs.append(doc)


class FakeSuggestion:
    async def clear_reactions(self): pass


def name_it(collection, claimer, messages):
    """Run the naming step; return (what got saved, what the channel said)."""
    pet = Pet.__new__(Pet)
    queue = list(messages)

    async def wait_for(event, timeout=None, check=None):
        while queue:
            message = queue.pop(0)
            if check is None or check(message):
                return message
        raise asyncio.TimeoutError

    pet.bot = type("B", (), {"wait_for": staticmethod(wait_for)})()
    channel = FakeChannel()
    asyncio.run(pet._name_and_save(
        None, channel, collection, FakeUser(claimer), "cat", "Chonk", "u", {}, {}, FakeSuggestion(),
    ))
    saved = [d for d in collection.docs if "type" in d]
    return saved, channel.sent


channel = FakeChannel()
fox, lyna, dodo = FakeUser(FOX), FakeUser(LYNA), FakeUser(999, bot=True)

# --- the reported case: Fox names Lyna's cat, Fox owns a Bobo, Lyna does not ---
col = FakeCol(("Bobo", FOX))
saved, said = name_it(col, LYNA, [FakeMessage("Bobo", fox, channel)])
assert [d["name"] for d in saved] == ["Bobo"], said
assert saved[0]["owner"] == LYNA, "the claimer owns it, not the namer"
assert not any("distinguish" in str(m) for m in said), said
print("Fox may name Lyna's cat 'Bobo' even though Fox owns a Bobo")

# --- the check that should fire: the name collides in the claimer's collection ---
col = FakeCol(("Bobo", LYNA))
saved, said = name_it(col, LYNA, [FakeMessage("Bobo", fox, channel), FakeMessage("Bobobo", fox, channel)])
assert any("distinguish" in str(m) for m in said), said
assert [d["name"] for d in saved] == ["Bobobo"], saved
print("a name Lyna already uses is refused, whoever types it, and naming continues")

# --- the bot must not name a pet ------------------------------------------------
col = FakeCol()
saved, said = name_it(col, LYNA, [FakeMessage("Rex, Bob, Sleepy, 47 more", dodo, channel),
                                  FakeMessage("Steve", fox, channel)])
assert [d["name"] for d in saved] == ["Steve"], saved
print("the bot's own messages are not names (a listing became a pet name once)")

# --- another channel must not name a pet ----------------------------------------
col = FakeCol()
elsewhere = FakeChannel(cid=2)
saved, said = name_it(col, LYNA, [FakeMessage("some unrelated chatter", fox, elsewhere),
                                  FakeMessage("Steve", fox, channel)])
assert [d["name"] for d in saved] == ["Steve"], saved
print("a message in another channel is not a name either")

# --- nobody says anything --------------------------------------------------------
col = FakeCol()
saved, said = name_it(col, LYNA, [])
assert saved == [] and said == [] or saved == [], (saved, said)
print("nobody names it, nothing is saved")

print("PASS")
