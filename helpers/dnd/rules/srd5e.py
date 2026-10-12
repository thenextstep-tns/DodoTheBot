"""
The ``srd5e`` ruleset — D&D 5e as published in the SRD 5.1.

**Licensing.** SRD 5.1 is released under CC-BY-4.0 and may be redistributed with
attribution; the attribution is carried in :data:`ATTRIBUTION` and shown in the
panel footer. Statblocks, adventures and setting material from published books
are *not* covered and must never be added here.

This ruleset exists as much to prove the abstraction as to be played: two
implementations built side by side is the only way to be sure ``rules/`` isn't
quietly assuming one system. If adding a third ever requires editing something
outside this package, the abstraction has failed.

Scope at P0: abilities, modifiers, proficiency, ability checks and saves,
advantage/disadvantage, AC, HP. Attacks, conditions and the action economy come
with the combat work in P3.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.rules import dice
from helpers.dnd.rules import ruleset
from helpers.dnd.rules.ruleset import (
    COST,
    FAIL,
    SUCCESS,
    TRIUMPH,
    Action,
    Outcome,
    register,
)

ATTRIBUTION = (
    "This work includes material from the System Reference Document 5.1 by Wizards of the "
    "Coast LLC, available under the Creative Commons Attribution 4.0 International License."
)

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

ABILITY_LABELS = {
    "STR": "Strength", "DEX": "Dexterity", "CON": "Constitution",
    "INT": "Intelligence", "WIS": "Wisdom", "CHA": "Charisma",
}

# The SRD standard array. Assigned by class priority rather than dealt out
# identically to everyone — the whole point of the rewrite.
STANDARD_ARRAY = (15, 14, 13, 12, 10, 8)

DEFAULT_DC = 15

# SRD conditions, split by what they take away. The first group removes actions
# and reactions entirely; the second sets speed to 0 and leaves the hands free.
# ``prone`` is in neither on purpose — a prone creature fights and crawls.
INCAPACITATING = frozenset({
    "incapacitated", "paralyzed", "paralysed", "petrified", "stunned",
    "unconscious",
})
IMMOBILISING = frozenset({"grappled", "restrained"})

# Ability priority per SRD class, best first. A class not listed falls back to
# DEFAULT_PRIORITY, so a homebrew class still gets a coherent, non-uniform block.
CLASS_PRIORITY = {
    "barbarian": ("STR", "CON", "DEX", "WIS", "CHA", "INT"),
    "bard":      ("CHA", "DEX", "CON", "WIS", "INT", "STR"),
    "cleric":    ("WIS", "CON", "STR", "CHA", "DEX", "INT"),
    "druid":     ("WIS", "CON", "DEX", "INT", "CHA", "STR"),
    "fighter":   ("STR", "CON", "DEX", "WIS", "CHA", "INT"),
    "monk":      ("DEX", "WIS", "CON", "STR", "INT", "CHA"),
    "paladin":   ("STR", "CHA", "CON", "WIS", "DEX", "INT"),
    "ranger":    ("DEX", "WIS", "CON", "STR", "INT", "CHA"),
    "rogue":     ("DEX", "INT", "CON", "CHA", "WIS", "STR"),
    "sorcerer":  ("CHA", "CON", "DEX", "WIS", "INT", "STR"),
    "warlock":   ("CHA", "CON", "DEX", "WIS", "INT", "STR"),
    "wizard":    ("INT", "CON", "DEX", "WIS", "CHA", "STR"),
}
DEFAULT_PRIORITY = ("DEX", "CON", "WIS", "STR", "INT", "CHA")

# Hit die per class, for starting HP (max at 1st level, per the SRD).
CLASS_HIT_DIE = {
    "barbarian": 12, "fighter": 10, "paladin": 10, "ranger": 10,
    "bard": 8, "cleric": 8, "druid": 8, "monk": 8, "rogue": 8, "warlock": 8,
    "sorcerer": 6, "wizard": 6,
}
DEFAULT_HIT_DIE = 8

# Which ability each SRD skill keys off, for check resolution.
SKILL_ABILITY = {
    "athletics": "STR",
    "acrobatics": "DEX", "sleight of hand": "DEX", "stealth": "DEX",
    "arcana": "INT", "history": "INT", "investigation": "INT",
    "nature": "INT", "religion": "INT",
    "animal handling": "WIS", "insight": "WIS", "medicine": "WIS",
    "perception": "WIS", "survival": "WIS",
    "deception": "CHA", "intimidation": "CHA",
    "performance": "CHA", "persuasion": "CHA",
}


def modifier(score: int) -> int:
    """The SRD ability modifier: floor((score − 10) / 2)."""
    return (score - 10) // 2


class Srd5e:
    """D&D 5e SRD 5.1. Stateless — all methods are pure given their inputs."""

    key = "srd5e"
    label = "D&D 5e (SRD 5.1)"
    attribution = ATTRIBUTION

    def stat_schema(self) -> dict:
        return {
            "abilities": {"type": "object", "keys": list(ABILITIES), "value_range": [1, 30]},
            "level": {"type": "int", "range": [1, 20]},
            "hp": {"type": "object", "keys": ["current", "max", "temp"]},
            "ac": {"type": "int", "range": [0, 30]},
            "proficiency": {"type": "int", "range": [2, 6]},
            "proficient_skills": {"type": "array", "of": "str"},
            "hit_die": {"type": "int"},
        }

    def blank_sheet(self, concept: dict, rng: Random) -> dict:
        """Standard array assigned by class priority — a wizard and a barbarian
        come out genuinely different, which the old cog never managed."""
        role = str(concept.get("role", "")).strip().lower()
        priority = CLASS_PRIORITY.get(role, DEFAULT_PRIORITY)
        abilities = {ability: STANDARD_ARRAY[i] for i, ability in enumerate(priority)}

        hit_die = CLASS_HIT_DIE.get(role, DEFAULT_HIT_DIE)
        con_mod = modifier(abilities["CON"])
        dex_mod = modifier(abilities["DEX"])
        max_hp = max(1, hit_die + con_mod)          # 1st level: full hit die + CON

        return {
            "abilities": abilities,
            "level": 1,
            "proficiency": 2,
            "hit_die": hit_die,
            "hp": {"current": max_hp, "max": max_hp, "temp": 0},
            "ac": 10 + dex_mod,                      # unarmoured; gear adjusts it later
            "proficient_skills": [],
        }

    def derive(self, stats: dict) -> dict:
        abilities = stats.get("abilities", {})
        mods = {a: modifier(int(abilities.get(a, 10))) for a in ABILITIES}
        return {
            "modifiers": mods,
            "initiative": mods["DEX"],
            "proficiency": int(stats.get("proficiency", 2)),
            "passive_perception": 10 + mods["WIS"]
            + (int(stats.get("proficiency", 2)) if "perception" in stats.get("proficient_skills", []) else 0),
        }

    def approaches(self, stats: dict) -> list[str]:
        """Abilities plus skills — a check may be either in 5e."""
        return list(ABILITIES) + sorted(SKILL_ABILITY)

    def affordances(self, actor_stats: dict, situation) -> frozenset:
        """What the SRD's conditions and action economy permit.

        Where freeform reads the GM's words, this reads the condition list, and
        the differences are the point — a *prone* creature can still fight and
        can still crawl away, a *grappled* one has speed 0 but full use of its
        hands, and a creature at 0 hit points is unconscious whatever anyone has
        written in ``conditions``. Two rulesets that agreed here would mean the
        abstraction had collapsed into one.
        """
        conditions = situation.conditions
        # 0 HP is unconsciousness in the SRD, and it is a fact about the sheet
        # rather than a condition someone remembered to add.
        down = int((actor_stats.get("hp") or {}).get("current", 1)) <= 0
        if down or any(c in INCAPACITATING for c in conditions):
            return frozenset({ruleset.WAIT})

        # Watching costs no action worth the name and is available to anyone who
        # is not incapacitated — including the prone and the grappled, who can
        # still see perfectly well.
        allowed = {ruleset.WAIT, ruleset.WATCH}
        # Perception is not an action in the SRD's economy and costs nothing a
        # condition takes away, so both of these survive prone, grappled and
        # restrained. Blindness would cost accuracy on a check, not the option.
        allowed.add(ruleset.LISTEN)
        allowed.add(ruleset.SEARCH)
        if situation.others:
            allowed.add(ruleset.SPEAK)
            # Speaking and threatening go together here: the SRD gags a
            # character with `incapacitated`, which has already returned above.
            allowed.add(ruleset.THREATEN)

        # Speed 0. You keep your action; you do not get to leave.
        immobile = any(c in IMMOBILISING for c in conditions)
        if not immobile:
            allowed.add(ruleset.MOVE)          # prone still counts — you crawl
            if not situation.sealed:
                allowed.add(ruleset.FLEE)
            # Keeping up with somebody needs the speed that `grappled` and
            # `restrained` take away, which is exactly what `immobile` covers.
            if situation.others:
                allowed.add(ruleset.FOLLOW)

        # Attacks, and anything else needing a free hand, survive being prone or
        # grappled; blindness costs accuracy, not the option.
        if situation.reachable:
            allowed.add(ruleset.ATTACK)
            allowed.add(ruleset.HELP)
            # Interposing is the SRD's *Protect* reaction in spirit: you need a
            # body to cover and a third party to cover them from.
            if len(situation.others) > 1:
                allowed.add(ruleset.PROTECT)
            if situation.carrying:
                allowed.add(ruleset.GIVE)
            if situation.anyone_carrying:
                allowed.add(ruleset.TAKE)
        if situation.features:
            allowed.add(ruleset.TAKE)
        if situation.carrying or situation.features:
            allowed.add(ruleset.USE)

        # Hiding needs to be unseen: heavy obscurement, cover, or already
        # invisible. Being invisible is the one condition that *adds* an option.
        if "invisible" in conditions or situation.obscured or situation.features:
            allowed.add(ruleset.HIDE)

        return frozenset(allowed)

    def resolve(
        self, action: Action, actor_stats: dict, target_stats: dict | None, rng: Random
    ) -> Outcome:
        derived = self.derive(actor_stats)
        mods = derived["modifiers"]

        approach = (action.approach or "DEX").strip()
        skill = approach.lower()
        if skill in SKILL_ABILITY:
            ability = SKILL_ABILITY[skill]
            bonus = mods[ability]
            if skill in actor_stats.get("proficient_skills", []):
                bonus += derived["proficiency"]
            label = skill.title()
        else:
            ability = approach.upper() if approach.upper() in ABILITIES else "DEX"
            bonus = mods[ability]
            label = ABILITY_LABELS[ability]

        dc = action.difficulty if action.difficulty is not None else DEFAULT_DC
        spec = dice.DiceSpec(count=1, sides=20, modifier=bonus)
        result = dice.roll(spec, rng)
        natural = result.faces[0] if result.faces else 0

        # Natural 1 and 20 are decisive on their own. The SRD only makes them
        # automatic for attack rolls, but treating them as the two extreme
        # degrees keeps the four-band contract every ruleset shares, and it is
        # what tables expect at a check anyway.
        if natural == 20:
            degree = TRIUMPH
        elif natural == 1:
            degree = FAIL
        elif result.total >= dc + 5:
            degree = TRIUMPH
        elif result.total >= dc:
            degree = SUCCESS
        elif result.total >= dc - 2:
            degree = COST          # a near miss is "yes, but", not a brick wall
        else:
            degree = FAIL

        return Outcome(
            degree=degree,
            roll=result,
            dc=dc,
            summary=_SUMMARIES[degree].format(label=label, total=result.total, dc=dc),
            detail={"approach": approach, "ability": ability, "bonus": bonus, "natural": natural},
        )

    def sheet_fields(self, stats: dict) -> list[tuple[str, str]]:
        abilities = stats.get("abilities", {})
        derived = self.derive(stats)
        mods = derived["modifiers"]
        hp = stats.get("hp", {})

        fields = [
            (a, f"{abilities.get(a, 10)} ({mods[a]:+d})") for a in ABILITIES
        ]
        fields.append(("HP", f"{hp.get('current', 0)}/{hp.get('max', 0)}"))
        fields.append(("AC", str(stats.get("ac", 10))))
        fields.append(("Prof", f"+{derived['proficiency']}"))
        fields.append(("Passive Perc.", str(derived["passive_perception"])))
        return fields


_SUMMARIES = {
    FAIL: "{label} check fails ({total} vs DC {dc}).",
    COST: "{label} check just misses ({total} vs DC {dc}) — it works, at a price.",
    SUCCESS: "{label} check succeeds ({total} vs DC {dc}).",
    TRIUMPH: "{label} check succeeds decisively ({total} vs DC {dc}).",
}


srd5e = register(Srd5e())
