"""Build the /rank card against stubs: layout, role colour, and step ordering."""
import asyncio, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
import discord
from cogs.trial_ranks import TrialRanks
import lang
from helpers import trial_ranks as tr


class Role:
    managed = False
    def __init__(self, rid, name, colour=0):
        self.id, self.name, self.position = rid, name, 1
        self.colour = discord.Colour(colour)
    @property
    def mention(self): return f"<@&{self.id}>"
    def is_default(self): return False


class Guild:
    id, name = 42, "ESO for Dodos"
    def __init__(self, roles): self.roles, self.members = roles, []
    def get_role(self, rid): return next((r for r in self.roles if r.id == rid), None)


class Asset: url = "https://example.invalid/a.png"


class Member:
    bot = False
    id = 7
    display_name = "Mido"
    display_avatar = Asset()
    colour = discord.Colour.default()
    def __init__(self, guild, roles, uid=7): self.guild, self.roles, self.id = guild, roles, uid


NAMES = ["Fresh Meat", "Trialgoer", "Expert",
         "vAA", "vAA HM", "vKA", "vKA Vrol HM", "vKA HM", "Godslayer (vAA trifecta)",
         "Immortal Redeemer (vKA trifecta)", "Master Angler"]
ROLES = {n: Role(100 + i, n, 0xE67E22 if n == "Expert" else 0) for i, n in enumerate(NAMES)}
guild = Guild(list(ROLES.values()))
rid = lambda n: ROLES[n].id

CONFIG = {
    "enabled": True, "exclusive": True,
    "points": {str(rid("vAA")): 1, str(rid("vAA HM")): 2,
               str(rid("vKA")): 4, str(rid("vKA Vrol HM")): 5, str(rid("vKA HM")): 15,
               str(rid("Godslayer (vAA trifecta)")): 30,
               str(rid("Immortal Redeemer (vKA trifecta)")): 20,
               str(rid("Master Angler")): 3},
    "trials": [
        {"name": "vAA", "slots": {"veteran": rid("vAA"), "full_hm": rid("vAA HM"),
                                  "trifecta": rid("Godslayer (vAA trifecta)")}},
        {"name": "vKA", "slots": {"veteran": rid("vKA"), "partial1": rid("vKA Vrol HM"),
                                  "full_hm": rid("vKA HM"),
                                  "trifecta": rid("Immortal Redeemer (vKA trifecta)")}},
    ],
    "ranks": tr.validate_ranks([
        {"role_id": rid("Fresh Meat"), "min_points": 0, "description": "Everyone starts here."},
        {"role_id": rid("Trialgoer"), "min_points": 5, "description": ""},
        {"role_id": rid("Expert"), "min_points": 40, "description": "Ask before you tank."},
    ], guild=guild),
}


WR = {99: {"current": 1, "former": 2}}


class Mgr:
    def get(self, gid): return CONFIG
    def image(self, gid, role_id): return None
    def wr_for(self, gid, uid): return WR.get(uid)
    # The stub has to answer what the card now asks it, or the card silently
    # loses a field and the test that was meant to catch that passes anyway.
    def wr_all(self, gid): return dict(WR)
    def enrolled_ids(self, gid): return {m.id for m in guild.members}


class Bot: trial_ranks = Mgr()


cog = TrialRanks.__new__(TrialRanks)
cog.bot = Bot()


def show(label, member):
    embed, files, view = asyncio.run(TrialRanks.rank_embed(cog, member))
    print(f'view: {"interest button" if view else "none"}')
    print(f"\n=== {label} ===")
    print(f"author: {embed.author.name}")
    print("description:")
    for line in (embed.description or "").splitlines():
        print(f"    {line if line else '(blank)'}")
    print(f"colour: {embed.colour}")
    for f in embed.fields:
        print(f"[{f.name}]")
        for line in f.value.splitlines():
            print(f"    {line}")
    return embed


e = show("mid-ladder, holds vAA + vKA", Member(guild, [ROLES["vAA"], ROLES["vKA"]]))

# The rank name is a role mention, on its own line above the stars.
assert e.title is None, "the rank line moved out of the title so mentions render"
first, second = e.description.splitlines()[:2]
assert first == f"## <@&{rid('Trialgoer')}>", first   # heading, so it isn't lost
# No board yet, so no place on the line and no stray trailing space.
assert set(second) <= {"⭐", "⚪"} and second, second
# Trialgoer has no colour and neither does the member, so the card falls back.
assert e.colour == discord.Colour.blurple(), e.colour


def slot_of(name):
    return next((s for t in CONFIG["trials"] for s, r in t["slots"].items()
                 if ROLES[name].id == r), None)


def check_order(embed, label):
    steps = next(f for f in embed.fields if f.name == "Next steps:").value.splitlines()
    order = [line.split(" · ")[1] for line in steps]
    kinds = [tr.step_priority(slot_of(n)) for n in order]
    print(f"{label} order:", list(zip(order, kinds)))
    assert kinds == sorted(kinds), f"not grouped: {list(zip(order, kinds))}"
    assert "(upgrade)" not in "\n".join(steps)
    return order, kinds


order, kinds = check_order(e, "\nno HMs held —")
assert kinds[0] == tr.STEP_HARDMODE, "a hardmode has to come first"
# The trifecta of a trial whose hardmode is still missing is not advice, it's
# noise — you can't get one without the other.
assert "Godslayer (vAA trifecta)" not in order, order

# Holding both hardmodes, the trifectas become the real next step — and the
# cheaper (older) one leads.
e3 = show("both HMs held", Member(guild, [ROLES["vAA HM"], ROLES["vKA HM"]]))
order3, kinds3 = check_order(e3, "HMs held —")
trifectas = [n for n, k in zip(order3, kinds3) if k == tr.STEP_TRIFECTA]
assert len(trifectas) == 2, trifectas
assert trifectas[0] == "Immortal Redeemer (vKA trifecta)", \
    f"cheaper trifecta first, got {trifectas}"

# A rank with a colour drives the embed's stripe.
e2 = show("top rank, coloured role", Member(guild, [ROLES["Godslayer (vAA trifecta)"],
                                                    ROLES["vKA HM"]]))
assert e2.colour.value == 0xE67E22, hex(e2.colour.value)
assert e2.description.splitlines()[0] == f"## <@&{rid('Expert')}>"

# A record holder: medals beside the name, and the bonus inside the total.
holder = show("world-record holder", Member(guild, [ROLES["vAA"], ROLES["vKA"]], uid=99))
assert tr.WR_MEDAL in holder.author.name, holder.author.name
assert tr.FORMER_WR_MEDAL in holder.author.name, holder.author.name
# 5 from clears + 15 for the current record + 2x5 for the former ones.
field = next(f for f in holder.fields if f.name.endswith("points"))
assert field.name == "30 points", field.name
# Somebody with no records is untouched by any of it.
plain = next(f for f in e.fields if f.name.endswith("points"))
assert plain.name == "5 points" and tr.WR_MEDAL not in e.author.name, plain.name
print("records add to the total and show with the name")

# With nobody on the roster there is no board to place anyone on, so the field
# is left off rather than asserting a position of one out of one.
assert not any(f.name.startswith("Where you stand") for f in e.fields),     "no standings field when the server has no enrolled members"

# --- where they stand, and the two people directly ahead -------------------- #
guild.members = [
    Member(guild, [ROLES["Godslayer (vAA trifecta)"], ROLES["vKA HM"]], uid=1),  # 45
    Member(guild, [ROLES["vKA HM"]], uid=2),                                     # 15
    Member(guild, [ROLES["vAA HM"], ROLES["vKA"]], uid=3),                       # 6
    Member(guild, [ROLES["vAA"], ROLES["vKA"]], uid=7),                          # 5, ours
    Member(guild, [ROLES["vKA"]], uid=4),                                        # 4
    Member(guild, [ROLES["Master Angler"]], uid=5),                              # 3
]
for who, label in zip(guild.members, ("Ace", "Fox", "Rosa", "Mido", "Tea", "Bram")):
    who.display_name = label
mido = next(m for m in guild.members if m.id == 7)
CONFIG["board_url"] = "https://dodobot.example/r/42/tok"
card = show("standings", mido)

# The place rides on the rank line, next to the role, where it is read first.
assert card.description.splitlines()[0] == f"## <@&{rid('Trialgoer')}> #4 of 6",     card.description.splitlines()[0]

board = next(f for f in card.fields if f.name == "Where you stand")
rows = board.value.splitlines()
# Two ahead and two behind, top-down, so the slice reads like the board it is a
# slice of. Both gaps are magnitudes: the direction is the side they are on.
assert rows == ["**#2** Fox · 15 (+10)",
                "**#3** Rosa · 6 (+1)",
                "**#4 Mido · 5** ← you",
                "**#5** Tea · 4 (-1)",
                "**#6** Bram · 3 (-2)"], rows
print("standings:", rows)

# The link is the last line of the body. A Discord footer is plain text, so a
# link put there would arrive as an unclickable URL.
last = card.fields[-1].value.splitlines()[-1]
assert last == "[See the full rankings](https://dodobot.example/r/42/tok)", last
assert card.footer.text == lang.TRIAL_CARD_FOOTER, "the footer itself is unchanged"

# Leader: nobody above, and it says so instead of printing an empty list.
top = show("the leader", guild.members[0])
assert top.description.splitlines()[0].endswith("#1 of 6"), top.description
lead = next(f for f in top.fields if f.name == "Where you stand")
rows = lead.value.splitlines()
# It goes first. Appended, it would sit between the leader and the people
# behind them, which is where it used to go and read as a break in the list.
assert rows[0] == lang.TRIAL_CARD_BOARD_TOP, rows
assert rows[1].endswith("← you") and rows[2].startswith("**#2**"), rows

# No link configured means no link line, not an empty one.
CONFIG["board_url"] = ""
bare = show("no board link", mido)
assert "full rankings" not in bare.fields[-1].value, bare.fields[-1].value
print("PASS")
