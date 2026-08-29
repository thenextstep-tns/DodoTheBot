"""The cat-scrap engine: classes, objects, spoils and the underdog.

The rules this protects, in the order they were asked for: an object's effect
lasts one fight; it reaches every cat in the room; no class beats another before
anybody shows anything; outnumbered teams feel objects harder; winners take the
losers' governing attributes; records get written; and a badly outmatched cat
still has a chance.
"""
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers import scrap


def cat(name, **stats):
    base = {"strength": 10, "agility": 10, "intellect": 10, "charm": 10}
    base.update(stats)
    return {"name": name, "ident": name.lower(), **base}


def shaped(cls):
    if cls.primary == "any":
        return cat(cls.name, strength=15, agility=15, intellect=15, charm=15)
    return cat(cls.name, **{"strength": 5, "agility": 5, "intellect": 5, "charm": 5,
                            cls.primary: 40, cls.secondary: 10})


# --- classes still come from the two governing attributes, in order ----------
for cls in scrap.CLASSES:
    assert scrap.classify(shaped(cls)).key == cls.key, cls.name
assert scrap.classify(cat("x", strength=40, intellect=20)).key == "loaf"
assert scrap.classify(cat("x", intellect=40, strength=20)).key == "barger"
print("all %d classes classify from their own stat shape, order included" % len(scrap.CLASSES))

for cls in scrap.CLASSES:
    assert cls.why and cls.temperament and cls.role
    assert len(cls.governing) >= 2
print("every class explains its name and knows what it stands to lose")

# --- 3. no class beats another before anybody shows anything -----------------
spread = []
for a in scrap.CLASSES:
    for b in scrap.CLASSES:
        wins = sum(1 for seed in range(60)
                   if scrap.simulate([shaped(a)], [shaped(b)], seed=seed)["winner"] == "A")
        spread.append(wins / 60)
assert 0.35 <= min(spread) and max(spread) <= 0.65, (min(spread), max(spread))
print("all %d matchups sit inside 35-65%% before any object is shown" % len(spread))

# Equal totals are equal whatever the shape, which is what makes that true.
lopsided = cat("Spike", strength=40, agility=5, intellect=5, charm=5)
even = cat("Even", strength=14, agility=14, intellect=14, charm=13)
fight = scrap.Scrap([lopsided], [even])
assert fight.fighters[0].max_hp == fight.fighters[1].max_hp
print("a 40/5/5/5 cat and a 14/14/14/13 cat are the same size of cat")

# --- 1 + 2. an object hits everyone, and only for this fight -----------------
LOOK = {("x", "loaf"): {"text": "sits on it", "stats": {"strength": 2}},
        ("x", "ghost"): {"text": "is elsewhere", "stats": {"agility": 2, "charm": -1}}}
loaf, ghost = shaped(scrap.CLASS_BY_KEY["loaf"]), shaped(scrap.CLASS_BY_KEY["ghost"])
fight = scrap.Scrap([loaf], [ghost], lookup=lambda e, c: LOOK.get((e, c)))
shown = fight.show("x", "@Fox")
assert {r["cat"] for r in shown["reactions"]} == {"Loaf", "Ghost"}, shown
assert {r["side"] for r in shown["reactions"]} == {"A", "B"}, "both sides react, not just the target"
print("one object reaches every cat in the room, on both sides")

assert fight.fighters[0].base["strength"] == 40, "the stored stat must not move"
assert fight.fighters[0].mods["strength"] == 2, "the fight-long modifier holds the change"
assert fight.fighters[0].stat("strength", fight.tuning) == 42
print("an object changes the fight, never the cat")

# Stats cannot be driven below the floor however grim the objects get.
DRAIN = {("bad", "loaf"): {"text": "regrets it", "stats": {"strength": -50}}}
grim = scrap.Scrap([loaf], [ghost], lookup=lambda e, c: DRAIN.get((e, c)))
grim.show("bad")
assert grim.fighters[0].stat("strength", grim.tuning) == scrap.TUNING["stat_floor"]
print("no object can take a cat below the stat floor")

# --- 4. outnumbered teams feel objects harder -------------------------------
assert scrap.team_scale(2, 5, scrap.TUNING) > 1 > scrap.team_scale(5, 2, scrap.TUNING)
small = scrap.Scrap([loaf], [dict(ghost), dict(ghost, name="G2"), dict(ghost, name="G3")],
                    lookup=lambda e, c: LOOK.get((e, c)))
small.show("x")
lone = small.fighters[0]
outnumbering = small.fighters[1]
assert lone.mods["strength"] > 2, "the outnumbered cat feels a plus harder"
assert abs(outnumbering.mods["agility"]) < 2, "the bigger team feels it less"
print("a 1-against-3 cat gains %+d where each of the three gains %+d"
      % (lone.mods["strength"], outnumbering.mods["agility"]))

# The amplification cuts both ways: being outnumbered makes bad news worse too.
punished = scrap.Scrap([loaf], [dict(ghost), dict(ghost, name="G2"), dict(ghost, name="G3")],
                       lookup=lambda e, c: DRAIN.get((e, c)))
punished.show("bad")
assert punished.fighters[0].mods["strength"] <= -50, "a smaller team loses more, not less"
print("and the same cat loses more from a bad object than a big team would")

# --- 8. David and Goliath ----------------------------------------------------
david, goliath = cat("David"), cat("Goliath", strength=20, agility=20, intellect=20, charm=20)
fight = scrap.Scrap([david], [goliath])
assert fight.underdog(fight.fighters[0], fight.fighters[1]) > 1
assert fight.underdog(fight.fighters[1], fight.fighters[0]) < 1
wins = sum(1 for seed in range(300) if scrap.simulate([david], [goliath], seed=seed)["winner"] == "A")
assert 0.15 < wins / 300 < 0.5, wins / 300
print("a cat at half the total still takes %.0f%% off one twice its size" % (wins / 3))

# --- 5 + 7. spoils and records ----------------------------------------------
chonk = cat("Chonky", strength=40, charm=10, agility=5, intellect=5)
assert scrap.classify(chonk).key == "chonk"
outcome = scrap.simulate([chonk], [cat("Winner", strength=90, agility=90,
                                       intellect=90, charm=90)], seed=2)["outcome"]
assert outcome["winner"] == "B"
transfer = outcome["transfers"][0]
assert transfer["from"] == "Chonky" and transfer["to"] == "Winner"
assert set(transfer["attributes"]) == {"strength", "charm"}, transfer["attributes"]
print("a beaten Chonk gives up STR and CHA, and the winner takes those two")

won = {r["name"] for r in outcome["records"] if r["won"]}
lost = {r["name"] for r in outcome["records"] if not r["won"]}
assert won == {"Winner"} and lost == {"Chonky"}
assert all(r["ident"] for r in outcome["records"]), "every record carries the pet id to write to"
print("every cat leaves with a win or a loss recorded against its id")

# Uneven sides: three losers against one winner means the winner collects thrice.
outcome = scrap.simulate([cat("Solo", strength=99, agility=99, intellect=99, charm=99)],
                         [cat("L1"), cat("L2"), cat("L3")], seed=1)["outcome"]
assert outcome["winner"] == "A"
assert len(outcome["transfers"]) == 3
assert {t["to"] for t in outcome["transfers"]} == {"Solo"}
print("one cat that beats three takes something from all three")

# --- a fight always produces a result ----------------------------------------
results = [scrap.simulate([cat("A")], [cat("B")], seed=s)["winner"] for s in range(200)]
assert None not in results, "a draw pays nobody and records nothing"
print("200 mirror fights, no draws, %d-%d" % (results.count("A"), results.count("B")))

# --- 9. the history keeps the last few moves and no more ---------------------
fight = scrap.Scrap([loaf], [ghost], lookup=lambda e, c: LOOK.get((e, c)))
for _ in range(6):
    fight.show("x", "@Fox")
assert len(fight.history) == int(scrap.TUNING["log_moves"]) == 3
assert "**Loaf**" in fight.history[-1] and "sits on it" in fight.history[-1]
print("the log keeps the last %d moves" % scrap.TUNING["log_moves"])

# Cats that react identically are named together rather than repeated.
same = scrap.Scrap([dict(loaf), dict(loaf, name="Loaf2"), dict(loaf, name="Loaf3")], [ghost],
                   lookup=lambda e, c: LOOK.get((e, c)))
same.show("x", "@Fox")
assert same.history[-1].count("sits on it") == 1, same.history[-1]
print("three cats doing the same thing get one sentence, not three")

# --- a borrowed cat has nothing at stake -------------------------------------
# Dodo makes up the numbers by borrowing a cat off somebody who is not here.
# It fights for real, but its owner never agreed to any of this, so it must
# leave with exactly the stats it arrived with.
mine = cat("Mine", strength=40, agility=40, intellect=40, charm=40)
loaned = dict(cat("Loaned", strength=6), stakes=False)

for seed in range(40):
    result = scrap.simulate([mine], [loaned], seed=seed)
    out = result["outcome"]
    assert all(r["name"] != "Loaned" for r in out["records"]), "no record against a borrowed cat"
    for t in out["transfers"]:
        assert t["from"] != "Loaned" and t["to"] != "Loaned", t
print("a borrowed cat never appears in a record or a transfer, won or lost")

# The human still settles up, in both directions, against a borrowed opponent.
# Evenly matched on purpose, so both results actually occur.
even_mine = cat("Mine")
even_loan = dict(cat("Loaned"), stakes=False)
won = lost = 0
for seed in range(80):
    out = scrap.simulate([even_mine], [even_loan], seed=seed)["outcome"]
    names = {t["to"] for t in out["transfers"]} | {t["from"] for t in out["transfers"]}
    assert "Mine" in names, out["transfers"]
    assert "Loaned" not in names, out["transfers"]
    won += out["winner"] == "A"
    lost += out["winner"] == "B"
assert won and lost, (won, lost)
print("the human gains on a win and loses on a loss, %d-%d, borrowed cat untouched"
      % (won, lost))

# But its stats still move during the fight, like everybody else's.
LOAN = {("x", "alley"): {"text": "reacts", "stats": {"strength": 3}}}
bout = scrap.Scrap([mine], [dict(loaned)], lookup=lambda e, c: LOAN.get((e, c)))
bout.show("x")
borrowed = bout.fighters[1]
assert borrowed.mods["strength"] != 0, "mid-fight stats still apply to a borrowed cat"
assert borrowed.base["strength"] == 6, "and its stored stats are still untouched"
print("a borrowed cat is still affected mid-fight, just never permanently")

# --- the scoreboard is readable text, not a code block -----------------------
from helpers import scrap_embed  # noqa: E402

board = scrap.Scrap([cat("Steak"), cat("Bobo")], [cat("Cheeky Pumpkin")], seed=2)
snap = board.step()
owner_map = {"Steak": "Fox", "Bobo": "Fox", "Cheeky Pumpkin": "Dodo"}
view = scrap_embed.scoreboard(snap, seconds_left=3, owners=owner_map, events=snap["events"])

assert "```" not in view, "a code block hides every emoji in it, which is the whole board"
for name, owner in owner_map.items():
    assert scrap_embed._clip(name) in view and owner in view, name
assert any(cls.emoji in view for cls in scrap.CLASSES), "cats show their class emoji"
assert "▰" in view or "▱" in view, "health is visible"
longest = max(len(line) for line in view.split(chr(10)))
assert longest < 120, "a line this long wraps into nonsense on a phone: %d" % longest
print("the board is plain text with emoji, widest line %d characters" % longest)

# An uneven side leaves a blank rather than pairing a cat against nothing.
assert len(scrap_embed.battlefield(snap, owner_map).split(chr(10))) == 2
print("uneven teams still line up one row per pairing")

# The line above the embed says who threw what in.
assert scrap_embed.shown_line({"Fox": ["🥒"]}).startswith("**Fox** added")
assert scrap_embed.shown_line({}) == ""
print("the added line names the thrower and their objects")

# --- the round count is a setting, not a constant ----------------------------
tough = lambda n: dict(name=n, strength=90, agility=1, intellect=1, charm=1, ident=n.lower())
short = scrap.simulate([tough("A")], [tough("B")], tuning={"rounds": 3}, seed=5)
assert len(short["rounds"]) == 3, len(short["rounds"])
assert "round_seconds" not in scrap.TUNING,     "the engine must not carry a second round length that nothing reads"
print("the round count comes from tuning, and there is only one round length")

print("PASS")
