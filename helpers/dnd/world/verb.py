"""
Verbs — the things anybody can decide to do, and everything that follows from it.

A verb used to be spread across **eight** hand-maintained tables in five modules:
what a scene may grant it (`rules/ruleset.AFFORDANCES`), how much of a gamble it
is (`RISK`), what a room thinks of it (`NORM`), which way it points socially
(`SOCIAL_SIGN`), which dispositions reach for it (`TRAIT_AFFINITY`), how it reads
against a relationship (`RELATION_READS`), which needs it answers
(`NEEDS_SERVED`), which ambitions it serves (`goal.SERVED_BY`), what it records
as (`minds.ACT_AS_RELATION`), and two ways of putting it into words
(`narrate.ACT_GISTS`, `ACTED_PHRASES`).

Adding one verb meant editing all of them and getting every one right. Missing a
table did not raise: it silently made the verb unreachable, or weightless, or
unremembered, or unnameable — and *"the NPCs are boring"* is a very hard bug to
trace back to a dictionary that was one key short.

So a verb is one record now, in `helpers/dnd/data/verbs.json`, resolved
built-in → server → campaign like the archetypes and the interaction kinds. A GM
can reweigh what attacking is worth in their game, or add a verb the engine has
never heard of, and everything downstream picks it up because there is only one
place to pick it up from.

**What is still not here, on purpose:** whether a *scene* physically permits the
verb. That is the ruleset's job (`rules/`), it depends on the fiction rather than
on the verb, and the two rulesets deliberately disagree about it. A verb says
what it *is*; a ruleset says whether you could do it just now.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SOURCE_BUILTIN = "builtin"


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _weights(raw, *, signed: bool = True) -> dict:
    """A ``{name: weight}`` map, cleaned. Non-numeric entries are dropped."""
    out = {}
    for name, value in (raw or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        out[str(name)] = _clamp(number) if signed else max(0.0, min(1.0, number))
    return out


@dataclass(frozen=True)
class Verb:
    """One thing a character can decide to do."""

    key: str = ""
    label: str = ""
    description: str = ""

    # --- what kind of act it is ------------------------------------------- #
    # Aimed at a person. Directed verbs get a target and can record against a
    # relationship; undirected ones happen in a room.
    directed: bool = False
    # The null band: hanging back rather than committing. These are granted to
    # anyone still conscious in every ruleset, and are what stops a decision
    # coming down to "commit or nothing".
    uncommitted: bool = False
    # Whether a campaign may switch it off. `wait` may not: it is the floor the
    # engine falls back to, and a campaign where nobody may do nothing has none.
    switchable: bool = True

    # --- what the scorer reads -------------------------------------------- #
    risk: float = 0.1          # how much of a gamble, before the person
    norm: float = 0.0          # what a room thinks. Negative is "not done here"
    social_sign: float = 0.0   # −1 hostile … +1 friendly
    needs: tuple = ()          # which needs it plausibly answers
    traits: dict = field(default_factory=dict)     # dispositions that reach for it
    relation: dict = field(default_factory=dict)   # how it reads against a bond
    goals: dict = field(default_factory=dict)      # goal kind → how well it serves

    # --- what happens afterwards ------------------------------------------ #
    # The interaction kind this records as, or "" for one that moves nothing
    # between two people. Must name a kind in `data/interactions.json`.
    records: str = ""
    # How it reads in the turn report — "went for", "spoke to".
    report: str = ""
    # How it reads in a memory of it, with `{a}` for whoever did it. Undirected
    # verbs only; a directed one takes its wording from the interaction kind, so
    # that a memory and a relationship log never describe the same act
    # differently.
    gist: str = ""

    source: str = SOURCE_BUILTIN

    def to_doc(self) -> dict:
        return {
            "key": self.key, "label": self.label, "description": self.description,
            "directed": self.directed, "uncommitted": self.uncommitted,
            "switchable": self.switchable, "risk": self.risk, "norm": self.norm,
            "social_sign": self.social_sign, "needs": list(self.needs),
            "traits": dict(self.traits), "relation": dict(self.relation),
            "goals": dict(self.goals), "records": self.records,
            "report": self.report, "gist": self.gist,
        }

    @classmethod
    def from_doc(cls, doc: dict, *, source: str = SOURCE_BUILTIN) -> "Verb":
        doc = doc or {}
        key = str(doc.get("key") or "").strip().lower()

        def number(name, default=0.0, low=-1.0):
            try:
                return max(low, min(1.0, float(doc.get(name, default))))
            except (TypeError, ValueError):
                return default

        label = str(doc.get("label") or "").strip() or key.replace("_", " ").title()
        return cls(
            key=key,
            label=label,
            description=str(doc.get("description") or "").strip(),
            directed=bool(doc.get("directed")),
            uncommitted=bool(doc.get("uncommitted")),
            switchable=bool(doc.get("switchable", True)),
            risk=number("risk", 0.1, low=0.0),
            norm=number("norm"),
            social_sign=number("social_sign"),
            needs=tuple(str(n) for n in (doc.get("needs") or ())),
            traits=_weights(doc.get("traits")),
            relation=_weights(doc.get("relation")),
            goals=_weights(doc.get("goals"), signed=False),
            records=str(doc.get("records") or "").strip().lower(),
            report=str(doc.get("report") or "").strip() or key,
            gist=str(doc.get("gist") or "").strip(),
        )


# --------------------------------------------------------------------------- #
#  The shapes the pure layers take
# --------------------------------------------------------------------------- #
# Each of these rebuilds one of the tables this file replaced, so the modules
# that consumed them keep their existing shape and the diff stays honest.
def keys(catalogue: dict) -> tuple:
    return tuple(catalogue)


def labels(catalogue: dict) -> dict:
    return {key: verb.label for key, verb in catalogue.items()}


def uncommitted(catalogue: dict) -> tuple:
    return tuple(key for key, verb in catalogue.items() if verb.uncommitted)


def switchable(catalogue: dict) -> tuple:
    return tuple(key for key, verb in catalogue.items() if verb.switchable)


def directed(catalogue: dict) -> tuple:
    return tuple(key for key, verb in catalogue.items() if verb.directed)


def as_risk(catalogue: dict) -> dict:
    return {key: verb.risk for key, verb in catalogue.items()}


def as_norm(catalogue: dict) -> dict:
    return {key: verb.norm for key, verb in catalogue.items()}


def as_social_sign(catalogue: dict) -> dict:
    return {key: verb.social_sign for key, verb in catalogue.items()}


def as_needs_served(catalogue: dict) -> dict:
    return {key: tuple(verb.needs) for key, verb in catalogue.items()}


def as_trait_affinity(catalogue: dict) -> dict:
    return {key: dict(verb.traits) for key, verb in catalogue.items() if verb.traits}


def as_relation_reads(catalogue: dict) -> dict:
    return {key: dict(verb.relation) for key, verb in catalogue.items() if verb.relation}


def as_records(catalogue: dict) -> dict:
    """``{verb: interaction kind}`` — what an act counts as between two people."""
    return {key: verb.records for key, verb in catalogue.items() if verb.records}


def as_report_phrases(catalogue: dict) -> dict:
    return {key: verb.report for key, verb in catalogue.items()}


def as_gists(catalogue: dict) -> dict:
    return {key: verb.gist for key, verb in catalogue.items() if verb.gist}


def as_served_by(catalogue: dict) -> dict:
    """``{goal kind: {verb: weight}}`` — the goal table, inverted.

    Stored per verb because that is where the rest of a verb's definition lives
    and a verb should be one record; read per goal because scoring a candidate
    against a goal is a lookup and a multiply, which is what let the design rule
    out search entirely (`06-DECISION-ENGINE.md` §1).
    """
    out: dict = {}
    for key, verb in catalogue.items():
        for kind, weight in verb.goals.items():
            if weight > 0:
                out.setdefault(kind, {})[key] = weight
    return out
