"""
Cat scrap — the fight engine.

Free of Discord and Mongo: it takes plain cat dicts and returns a round-by-round
log, so the balance sandbox, the preview and the eventual command all run the
same code.

The design settled here, and the reasons:

**Classes decide nothing in combat.** Two cats with the same stat total are
exactly as likely to win, whatever their attributes are, because every combat
number is derived from the *total* alone. Attributes still decide a cat's class,
and the class decides how it reacts to the things people show it — so the
objects are the entire game and a class is a personality rather than a
statline. Class perks used to sit here and made the spread run from 23% to 66%;
they are gone on purpose.

**What an object does is temporary.** Stat changes from a shown object last for
that fight and nothing else. The only permanent movement is the spoils: the
winners take a point of each of the losers' two governing attributes, which is
also the only way a cat's class can be taken from it.

**A smaller team feels everything harder.** Bonuses and penalties are scaled by
how outnumbered you are, so three cats against five swing further in both
directions rather than simply losing.

**Being outmatched is worth something.** A cat facing a much larger total crits
more often and hits harder for it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
#  Tuning — every number the fight touches, in one place.
# --------------------------------------------------------------------------- #
TUNING: dict[str, float] = {
    "rounds": 6,
    "round_seconds": 5,
    # Bodies and swings, from the stat TOTAL only. This is what makes every
    # class and every class combination a coin flip before anybody shows
    # anything, which is the whole point of the redesign.
    "hp_base": 40, "hp_per_total": 1.1,
    "swipe_base": 4, "swipe_per_total": 0.22,
    "dodge_flat": 12, "crit_flat": 12, "crit_multiplier": 2.0,
    # A stat can be dragged down by objects and by losing, but never past this.
    "stat_floor": 1,
    # David and Goliath: how much bigger they have to be before it counts, and
    # what the underdog gets per point of ratio over that.
    "underdog_threshold": 1.0,
    "underdog_crit_per_ratio": 22, "underdog_crit_cap": 45,
    "underdog_damage_power": 1.0, "underdog_damage_cap": 2.2,
    # Outnumbered teams feel every object more. 1.0 = exactly proportional.
    "team_scale": 1.0, "team_scale_cap": 3.0,
    # Spoils
    "spoils_per_cat": 1,
    # The pre-fight layer
    "roster_max": 10,
    "taunt_resist_per_intellect": 2.0, "taunt_resist_cap": 80,
    "psps_lure_per_charm": 1.8, "psps_lure_cap": 85,
    "psps_backfire_per_charm": 1.6, "psps_backfire_cap": 75,
    # How many lines of history the embed keeps.
    "log_moves": 3,
}

ATTRIBUTES = ("strength", "agility", "intellect", "charm")
ATTR_SHORT = {"strength": "STR", "agility": "AGI", "intellect": "INT", "charm": "CHA"}


# --------------------------------------------------------------------------- #
#  Classes — identity and temperament, not combat maths
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CatClass:
    key: str
    name: str
    emoji: str
    primary: str
    secondary: str
    role: str
    temperament: str      # how it tends to react to things: drives the grid
    why: str              # why the name says those two attributes

    @property
    def label(self) -> str:
        if self.primary == "any":
            return "no specialism"
        return f"{ATTR_SHORT[self.primary]}›{ATTR_SHORT[self.secondary]}"

    @property
    def governing(self) -> tuple[str, ...]:
        """The attributes a winner takes and a loser gives up."""
        if self.primary == "any":
            return ATTRIBUTES
        return (self.primary, self.secondary)


GENERALIST = "alley"

CLASSES: tuple[CatClass, ...] = (
    CatClass("pouncer", "Pouncer", "🐅", "strength", "agility", "Opener",
             "Treats everything as something to ambush. Excited by anything that moves or hides.",
             "All of a cat's weight, delivered at speed. That is what a pounce is."),
    CatClass("loaf", "Loaf", "🍞", "strength", "intellect", "Immovable object",
             "Wants to sit on it, be warmed by it, or ignore it. Rarely impressed, never hurried.",
             "Heavy, and entirely unbothered. Sitting still is the clever part."),
    CatClass("chonk", "Chonk", "🐈‍⬛", "strength", "charm", "Damage sponge",
             "Food is the point. Anything large is a personal remark and will be taken as one.",
             "Mass that people adore instead of fearing."),
    CatClass("ricochet", "Ricochet", "🏓", "agility", "strength", "Counter-puncher",
             "Bats it, chases it, loses it under the sofa. Anything round is a project.",
             "Fast enough to come off the walls, solid enough to come back off them."),
    CatClass("ghost", "Ghost", "👻", "agility", "intellect", "Stealth ganker",
             "Admires anything sly or unseen and takes it as a lesson. Loud things are an insult.",
             "Quick, and clever enough to be quick where nobody is looking."),
    CatClass("gremlin", "Zoom Gremlin", "😼", "agility", "charm", "Chaos",
             "Destroys it, wears it, or knocks it off the table. Consequences are for later.",
             "Speed with no plan and total impunity, because look at it."),
    CatClass("barger", "Door Barger", "🚪", "intellect", "strength", "Defence breaker",
             "Works out how it opens, then opens it. Barriers are suggestions.",
             "Works out how the door opens, then simply goes through the door."),
    CatClass("stalker", "Shelf Stalker", "🗄️", "intellect", "agility", "High ground",
             "Wants it up high, or wants to watch it from up high. Patient about both.",
             "Worked out the high route, and is quiet enough to take it."),
    CatClass("purrsuader", "Purrsuader", "😻", "intellect", "charm", "Debuffer",
             "Sees a lever. Every object is a way of making a human do something.",
             "Worked out *you*, and is using you. Cunning with a purr on top."),
    CatClass("tyrant", "Lap Tyrant", "👑", "charm", "strength", "Disabler",
             "Claims it. Sits on it. It was always going to be hers.",
             "Rules by sitting on you. You are the one who allows it."),
    CatClass("weaver", "Ankle Weaver", "🧶", "charm", "agility", "Prop deflector",
             "Winds around it, trips you over it, and is adored for doing so.",
             "Winding round your ankles, adored, and impossible to actually step on."),
    CatClass("dinner", "Second Dinner", "🍽️", "charm", "intellect", "Sustain",
             "Is it food? It might be food. Sentiment works on her, and so does guilt.",
             "Has definitely not been fed. Knows exactly who to tell, and when."),
    CatClass(GENERALIST, "Alley Cat", "🐾", "any", "any", "Generalist",
             "Has met all of it before and found a use for most of it. Very little is new.",
             "No best stat and no worst one. It has had to be all of them at some point."),
)
CLASS_BY_KEY = {c.key: c for c in CLASSES}
_CLASS_BY_PAIR = {(c.primary, c.secondary): c for c in CLASSES if c.primary != "any"}

LEGACY_CLASS_MAP = {
    "Chonk": "chonk", "Zoomies Pro": "ricochet", "Smarty Pants": "stalker", "Aww summoner": "dinner",
    "Working Dog": "chonk", "Hound Dog": "ricochet", "Herding Dog": "stalker", "Companion Dog": "dinner",
}
GENERALIST_SPREAD = 8


def classify(cat: dict, spread: float = GENERALIST_SPREAD) -> CatClass:
    """A cat's class: its highest attribute, then its second highest.

    A cat whose attributes all sit within ``spread`` of each other has no
    governing pair and is an Alley Cat. Ties break in ``ATTRIBUTES`` order —
    arbitrary but stable, because the same cat must never classify two different
    ways between the sandbox and a fight.
    """
    values = {a: float(cat.get(a, 0) or 0) for a in ATTRIBUTES}
    if max(values.values()) - min(values.values()) <= spread:
        return CLASS_BY_KEY[GENERALIST]
    ranked = sorted(ATTRIBUTES, key=lambda a: (-values[a], ATTRIBUTES.index(a)))
    return _CLASS_BY_PAIR[(ranked[0], ranked[1])]


# --------------------------------------------------------------------------- #
#  Fighters
# --------------------------------------------------------------------------- #
@dataclass
class Fighter:
    name: str
    side: str
    owner: int = None
    ident: str = None                       # the pet's database id, for writing results back
    base: dict = field(default_factory=dict)
    mods: dict = field(default_factory=dict)   # this fight only, wiped when it ends
    hp: float = 0.0
    max_hp: float = 0.0
    cat_class: CatClass = None

    @classmethod
    def build(cls, raw: dict, side: str, tuning: dict) -> "Fighter":
        base = {a: int(raw.get(a, 0) or 0) for a in ATTRIBUTES}
        fighter = cls(name=str(raw.get("name") or "cat"), side=side,
                      owner=raw.get("owner"), ident=str(raw.get("_id") or raw.get("ident") or ""),
                      base=base, mods={a: 0 for a in ATTRIBUTES})
        fighter.cat_class = (CLASS_BY_KEY[raw["class"]] if raw.get("class") in CLASS_BY_KEY
                             else classify(base))
        fighter.max_hp = round(tuning["hp_base"] + fighter.total(tuning) * tuning["hp_per_total"])
        fighter.hp = fighter.max_hp
        return fighter

    def stat(self, name: str, tuning: dict) -> int:
        """An attribute as it stands *in this fight*, never below the floor."""
        return max(int(tuning["stat_floor"]), self.base[name] + self.mods.get(name, 0))

    def total(self, tuning: dict) -> int:
        return sum(self.stat(a, tuning) for a in ATTRIBUTES)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def public(self, tuning: dict) -> dict:
        return {
            "name": self.name, "side": self.side, "hp": max(0, round(self.hp)),
            "max_hp": round(self.max_hp), "class": self.cat_class.key,
            "class_name": self.cat_class.name, "emoji": self.cat_class.emoji,
            "alive": self.alive, "total": self.total(tuning),
            "stats": {a: self.stat(a, tuning) for a in ATTRIBUTES},
            "mods": {a: v for a, v in self.mods.items() if v},
        }


def team_scale(mine: int, theirs: int, tuning: dict) -> float:
    """How hard this team feels an object, given how outnumbered it is.

    Three cats against five feel every plus and every minus 5/3 as hard, and the
    five feel it 3/5 as hard. Outnumbered teams do not merely lose; they swing.
    """
    if mine <= 0:
        return 1.0
    raw = (theirs / mine) ** tuning["team_scale"]
    return max(1.0 / tuning["team_scale_cap"], min(tuning["team_scale_cap"], raw))


class Scrap:
    """One fight. Feed it rounds of shown objects; read ``rounds`` and ``outcome``."""

    def __init__(self, side_a: list[dict], side_b: list[dict], *, tuning: dict = None,
                 lookup=None, seed: int = None):
        self.tuning = {**TUNING, **(tuning or {})}
        self.rng = random.Random(seed)
        self.fighters = ([Fighter.build(c, "A", self.tuning) for c in side_a]
                         + [Fighter.build(c, "B", self.tuning) for c in side_b])
        # lookup(emoji, class_key) -> {"text": ..., "stats": {...}}; without one
        # the fight still runs, it is simply nobody showing anything.
        self.lookup = lookup or (lambda emoji, cls: None)
        self.rounds: list[dict] = []
        self.events: list[dict] = []
        self.history: list[str] = []
        self.round_no = 0

    # -- helpers ------------------------------------------------------------ #
    def log(self, kind: str, text: str, target: str = None, actor: str = None) -> None:
        # The battlefield strip marks the row a hit landed on, so every combat
        # event has to say who it happened to, not just what it read like.
        self.events.append({"kind": kind, "text": text, "target": target, "actor": actor})

    def side_of(self, side: str) -> list[Fighter]:
        return [f for f in self.fighters if f.side == side and f.alive]

    def enemies_of(self, fighter: Fighter) -> list[Fighter]:
        return [f for f in self.fighters if f.side != fighter.side and f.alive]

    def scale_for(self, side: str) -> float:
        other = "B" if side == "A" else "A"
        return team_scale(len(self.side_of(side)), len(self.side_of(other)), self.tuning)

    # -- showing things ------------------------------------------------------ #
    def show(self, emoji: str, shower: str = None) -> dict:
        """Show one object to the whole room.

        Every cat in the fight reacts, each according to its own class, whichever
        side it is on and whoever held the thing up. That is the mechanic: you
        are not aiming an object at a cat, you are letting an object into a room
        full of cats and finding out what it does to all of them.
        """
        reactions = []
        for fighter in self.fighters:
            if not fighter.alive:
                continue
            row = self.lookup(emoji, fighter.cat_class.key)
            if not row or not row.get("text"):
                continue
            scale = self.scale_for(fighter.side)
            applied = {}
            for attr, delta in (row.get("stats") or {}).items():
                if attr not in ATTRIBUTES or not delta:
                    continue
                # Scaled by how outnumbered the cat's side is, and rounded away
                # from zero so a small effect on a big team never silently
                # becomes nothing at all.
                scaled = delta * scale
                step = int(scaled) if abs(scaled) >= 1 else (1 if scaled > 0 else -1)
                fighter.mods[attr] = fighter.mods.get(attr, 0) + step
                applied[attr] = applied.get(attr, 0) + step
            reactions.append({"cat": fighter.name, "side": fighter.side,
                              "class": fighter.cat_class.key, "text": row["text"], "stats": applied})
        if reactions:
            self.history.append(self._history_line(emoji, shower, reactions))
            self.history = self.history[-int(self.tuning["log_moves"]):]
        return {"emoji": emoji, "shower": shower, "reactions": reactions}

    def _history_line(self, emoji: str, shower: str, reactions: list[dict]) -> str:
        """One shown object and everything it did, in a single readable line.

        Cats that reacted identically are named together. Five cats of the same
        class produce five identical sentences otherwise, and the line stops
        being readable at exactly the moment a group fight makes it interesting.
        """
        who = f"{shower}'s " if shower else ""
        grouped: dict[str, list[str]] = {}
        for reaction in reactions:
            grouped.setdefault(reaction["text"], []).append(reaction["cat"])
        parts = []
        for text, names in grouped.items():
            if len(names) > 2:
                subject = f"{', '.join(names[:-1])} and {names[-1]}"
            else:
                subject = " and ".join(names)
            parts.append(f"**{subject}**: {text}")
        return f"{who}{emoji} → " + " ".join(parts)

    # -- combat -------------------------------------------------------------- #
    def underdog(self, attacker: Fighter, target: Fighter) -> float:
        """How outmatched the attacker is, as a ratio at or above 1."""
        mine = max(1, attacker.total(self.tuning))
        theirs = max(1, target.total(self.tuning))
        return theirs / mine

    def swipe(self, attacker: Fighter, target: Fighter) -> None:
        tuning = self.tuning
        ratio = self.underdog(attacker, target)
        over = max(0.0, ratio - tuning["underdog_threshold"])

        # A power law rather than a straight ramp. Both health and damage scale
        # with the total, so a cat facing twice its own total is fighting
        # something like the square of the gap; a linear bonus either does
        # nothing at 1.25x or turns the underdog into a monster at 2.5x. Both
        # happened. This keeps the curve falling smoothly with no cliff at the
        # threshold and no overshoot past it.
        crit_chance = tuning["crit_flat"]
        damage_scale = 1.0
        david = ratio > tuning["underdog_threshold"]
        if david:
            damage_scale = min(tuning["underdog_damage_cap"],
                               ratio ** tuning["underdog_damage_power"])
            crit_chance = min(tuning["underdog_crit_cap"],
                              crit_chance + over * tuning["underdog_crit_per_ratio"])

        if self.rng.random() * 100 < tuning["dodge_flat"]:
            self.log("miss", f"{target.name} is not where {attacker.name} expected.",
                     target=target.name, actor=attacker.name)
            return

        damage = (tuning["swipe_base"] + attacker.total(tuning) * tuning["swipe_per_total"]) * damage_scale
        crit = self.rng.random() * 100 < crit_chance
        if crit:
            damage *= tuning["crit_multiplier"]

        target.hp -= damage
        if crit and david:
            verb = "gets absolutely everything into one on"
        elif crit:
            verb = "lands a proper one on"
        else:
            verb = "gets a paw on"
        self.log("crit" if crit else "hit", f"{attacker.name} {verb} {target.name}. ({round(damage)})",
                 target=target.name, actor=attacker.name)
        if not target.alive:
            self.log("ko", f"{target.name} is done. Under the sofa, not coming out.",
                     target=target.name, actor=attacker.name)

    # -- the loop -------------------------------------------------------------- #
    def step(self, shows: list[tuple] = None) -> dict:
        """One round: everything shown this round lands, then everyone swings."""
        self.round_no += 1
        self.events = []
        for entry in shows or []:
            emoji, shower = (entry if isinstance(entry, (tuple, list)) else (entry, None))
            self.show(emoji, shower)

        order = list(self.fighters)
        self.rng.shuffle(order)
        for fighter in order:
            if not fighter.alive or not self.side_of("A") or not self.side_of("B"):
                continue
            enemies = self.enemies_of(fighter)
            if enemies:
                self.swipe(fighter, self.rng.choice(enemies))

        snapshot = {
            "round": self.round_no,
            "events": list(self.events),
            "cats": [f.public(self.tuning) for f in self.fighters],
            "history": list(self.history),
        }
        self.rounds.append(snapshot)
        return snapshot

    def over(self) -> bool:
        return (not self.side_of("A") or not self.side_of("B")
                or self.round_no >= int(self.tuning["rounds"]))

    def run(self, shows_by_round: dict = None) -> dict:
        shows_by_round = shows_by_round or {}
        while not self.over():
            self.step(shows_by_round.get(self.round_no + 1))
        return {"rounds": self.rounds, "winner": self.winner(),
                "outcome": self.outcome(), "tuning": self.tuning}

    def winner(self) -> str | None:
        alive_a, alive_b = self.side_of("A"), self.side_of("B")
        if alive_a and not alive_b:
            return "A"
        if alive_b and not alive_a:
            return "B"
        if not alive_a and not alive_b:
            return None
        share = {s: sum(f.hp / f.max_hp for f in self.side_of(s)) / max(1, len(self.side_of(s)))
                 for s in ("A", "B")}
        if abs(share["A"] - share["B"]) < 0.001:
            # Two sides that are exactly level have nothing left to separate
            # them, and a draw pays nobody and records nothing. Toss for it
            # rather than leaving a fifth of all fights with no result.
            return self.rng.choice(("A", "B"))
        return "A" if share["A"] > share["B"] else "B"

    # -- what the fight leaves behind ------------------------------------------ #
    def outcome(self) -> dict:
        """Permanent consequences: the record, and the spoils.

        Every loser gives up a point of each of its two governing attributes and
        a winner takes those same two. Losers are dealt round the winners, so an
        outnumbered winning side collects more per cat rather than less — the
        cat that beat three of them has taken something from all three.

        Nothing here is written anywhere. The caller applies it, which keeps the
        engine free of the database and lets the sandbox show the spoils without
        handing anybody real stats.
        """
        winning = self.winner()
        if winning is None:
            return {"winner": None, "records": [], "transfers": []}
        losing = "B" if winning == "A" else "A"
        winners = [f for f in self.fighters if f.side == winning]
        losers = [f for f in self.fighters if f.side == losing]

        records = ([{"name": f.name, "ident": f.ident, "owner": f.owner, "won": True} for f in winners]
                   + [{"name": f.name, "ident": f.ident, "owner": f.owner, "won": False} for f in losers])

        transfers = []
        step = int(self.tuning["spoils_per_cat"])
        for index, loser in enumerate(losers):
            taker = winners[index % len(winners)] if winners else None
            attrs = list(loser.cat_class.governing)
            transfers.append({
                "from": loser.name, "from_ident": loser.ident,
                "to": taker.name if taker else None, "to_ident": taker.ident if taker else None,
                "attributes": attrs, "amount": step,
            })
        return {"winner": winning, "records": records, "transfers": transfers}


def simulate(side_a: list[dict], side_b: list[dict], **kwargs) -> dict:
    """Run one fight to the end and return ``{rounds, winner, outcome, tuning}``."""
    shows = kwargs.pop("shows", None)
    return Scrap(side_a, side_b, **kwargs).run(shows)


# --------------------------------------------------------------------------- #
#  Before the fight
# --------------------------------------------------------------------------- #
def taunt_odds(cat: dict, tuning: dict = None) -> dict:
    """Chance a taunted cat rises to it. Intellect is the only defence."""
    tuning = {**TUNING, **(tuning or {})}
    resist = min(tuning["taunt_resist_cap"],
                 int(cat.get("intellect", 0) or 0) * tuning["taunt_resist_per_intellect"])
    return {"resist": round(resist, 1), "hooked": round(100 - resist, 1)}


def psps_odds(cat: dict, tuning: dict = None) -> dict:
    """Chance a psps'd cat comes to you, and the chance it charms one of yours away instead."""
    tuning = {**TUNING, **(tuning or {})}
    charm = int(cat.get("charm", 0) or 0)
    return {
        "lured": round(min(tuning["psps_lure_cap"], charm * tuning["psps_lure_per_charm"]), 1),
        "backfire": round(min(tuning["psps_backfire_cap"], charm * tuning["psps_backfire_per_charm"]), 1),
    }


def mechanics() -> dict:
    """Everything the sandbox needs to describe the game, from the source."""
    rollable = set(LEGACY_CLASS_MAP.values())
    return {
        "classes": [{
            "key": c.key, "name": c.name, "emoji": c.emoji, "label": c.label,
            "primary": c.primary, "secondary": c.secondary,
            "primary_short": ATTR_SHORT.get(c.primary, "—"),
            "secondary_short": ATTR_SHORT.get(c.secondary, "—"),
            "role": c.role, "perk": c.temperament, "why": c.why,
            "rollable": c.key in rollable,
        } for c in CLASSES],
        "props": [],
        "attributes": [{
            "key": a, "short": ATTR_SHORT[a], "job": job,
        } for a, job in (
            ("strength", "Part of your total. Nothing else — no class fights better than another."),
            ("agility", "Part of your total. Health and damage both come from the total."),
            ("intellect", "Part of your total, and the only defence against being taunted."),
            ("charm", "Part of your total, and what decides psps."),
        )],
        "prefight": [
            {"name": "Roster", "emoji": "\U0001F3AF",
             "summary": f"Up to {int(TUNING['roster_max'])} cats fight for you, put there by summoning them."},
            {"name": "Taunt", "emoji": "\U0001F5E3️",
             "summary": "Call a cat by name and it has to answer. Intellect is the only thing that "
                        "lets it stay out of it."},
            {"name": "Psps", "emoji": "\U0001F90F",
             "summary": "Charm decides whether a psps'd cat comes over, and whether it psps one of "
                        "yours back instead."},
        ],
        "legacy": LEGACY_CLASS_MAP,
        "tuning": TUNING,
    }
