"""
The parameter catalogue — every knob in the engine, in one list.

**Standing rule, and the reason this file exists:** *everything is a tweakable
parameter visible to the bot owner.* Not most things. Not the ones that seemed
worth exposing. A number that shapes behaviour and cannot be seen or changed is
a black box, and a simulation made of black boxes is not authorable — you can
only observe what it does and hope.

The rule had been kept for anything anybody thought to call a tunable, and
quietly broken everywhere else: **twenty-odd scalars and twenty weight tables**
sat in modules with no way to read them, let alone change them, including the
whole per-verb weighting the decision engine scores with. They were invisible
precisely because there was no list to be missing from.

So this is that list, and it has three jobs:

1. **Show everything**, including what is *not* yet exposed. The baked-in
   inventory below is rendered on the same page as the tunables, flagged, with
   the file it lives in and its current value. Nothing is hidden by being
   inconvenient.
2. **Say what each parameter touches.** A knob you cannot predict the blast
   radius of is barely better than a hidden one. Siblings (the parameters that
   combine into the same typed view) are derived; the interesting cross-system
   relations are authored in :data:`AFFECTS`.
3. **Stay honest by force.** `tests/test_dnd_catalogue.py` re-reads the source
   and fails if a baked-in entry has moved, changed value, or quietly become a
   tunable without being reclassified — so this list cannot rot the way the
   handoff's test count did.

**Adding a parameter to this catalogue is part of adding a parameter.** See
`14-CONVENTIONS.md` §4 invariant 1 and §6. A tunable that is not in
:data:`TUNABLE_NOTES`, or a constant that is not in :data:`BAKED_IN`, fails the
suite. That is deliberate: the rule was already written down twice and was still
broken forty times, so it is now a test rather than a paragraph.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Any

from helpers.dnd import interactions as interaction_registry
from helpers.dnd import packs as pack_registry
from helpers.dnd.tuning import BY_KEY, GROUPS, TUNABLES

HERE = os.path.dirname(os.path.abspath(__file__))
TUNING_SOURCE = os.path.join(HERE, "tuning.py")

# Where a parameter can be changed, most reachable first.
LAYER_CAMPAIGN = "campaign"   # a GM, on the campaign page
LAYER_SERVER = "server"       # a server admin, for every campaign
LAYER_DATA = "data"           # a row in helpers/dnd/data/, layered like tunables
LAYER_CODE = "code"           # nowhere yet — the work queue

STATUS_TUNABLE = "tunable"
STATUS_DATA = "data"
STATUS_BAKED = "baked-in"


@dataclass(frozen=True)
class Entry:
    """One parameter, everything a person needs to decide whether to touch it."""

    key: str
    label: str
    description: str
    default: Any
    span: str                      # the range, said the way this type says it
    group: str
    status: str
    layer: str
    where: str                     # the module that reads it
    view: str = ""                 # the typed view it arrives in, if any
    siblings: tuple = ()           # parameters that combine with it
    affects: tuple = ()            # what else moves when this moves
    note: str = ""                 # why it is not exposed, when it is not
    planned: str = ""              # where a baked-in one should end up

    @property
    def exposed(self) -> bool:
        return self.status != STATUS_BAKED


# --------------------------------------------------------------------------- #
#  Derived: which typed view each tunable arrives in
# --------------------------------------------------------------------------- #
_VIEWS: dict[str, str] | None = None


def views() -> dict[str, str]:
    """``{tunable key: the Tuning method that builds its view}``.

    Read out of ``tuning.py`` itself rather than maintained by hand — the whole
    point of this module is that hand-maintained parallel lists drift, and it
    would be absurd for the catalogue to be one.
    """
    global _VIEWS
    if _VIEWS is None:
        _VIEWS = {}
        tree = ast.parse(open(TUNING_SOURCE, encoding="utf-8").read())
        klass = next(
            (n for n in tree.body
             if isinstance(n, ast.ClassDef) and n.name == "Tuning"), None
        )
        for function in (klass.body if klass else []):
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in BY_KEY):
                    _VIEWS.setdefault(node.args[0].value, function.name)
        # The families read in a loop rather than named one by one — the ten
        # affordance switches and the nine scorer weights. The AST cannot see
        # them because there is no literal to see, so they are matched by
        # prefix. A test asserts every tunable lands in some view either way.
        for key in BY_KEY:
            if key in _VIEWS:
                continue
            for prefix, view in (("affordance_", "affordances"),
                                 ("decide_w_", "decision"),
                                 ("kb_", "knowledge"),
                                 ("need_", "needs")):
                if key.startswith(prefix):
                    _VIEWS[key] = view
                    break
    return dict(_VIEWS)


# Which module actually consumes each typed view. Authored, because it is a fact
# about the architecture rather than about the text of one file — but it is a
# short list and a wrong entry is visible on the page.
CONSUMED_BY = {
    "memory": "mind/memory/decay.py, encode.py, consolidate.py",
    "salience": "mind/memory/salience.py",
    "needs": "mind/needs.py",
    "relationships": "mind/relationships.py",
    "stakes": "mind/stakes.py",
    "rumours": "mind/rumour.py",
    "perception": "world/view.py",
    "affordances": "rules/ruleset.py, minds.affordances_for",
    "goals": "mind/goals.py",
    "behaviour": "mind/behaviour.py",
    "decision": "mind/decide.py",
    "continuity": "minds.tick, minds.advance, cogs/dnd/cog.py",
    "gists": "helpers/dnd/narrate.py",
    "report": "helpers/dnd/narrate.py, cogs/dnd/cog.py",
    "generation": "mind/traits.py, minds.spawn_npc",
    "knowledge": "store/knowledge.py",
}


# --------------------------------------------------------------------------- #
#  Authored: what moves when this moves
# --------------------------------------------------------------------------- #
# Only the relations that are *not* obvious from the grouping. Parameters in the
# same view are already listed as siblings, so this is for the ones that reach
# across a boundary — which are exactly the ones that surprise people.
AFFECTS: dict[str, tuple] = {
    "need_upkeep": (
        "Sets the ceiling every need approaches, so it decides whether "
        "deprivation is survivable. At 0 a besieged character starves on the "
        "documented schedule; at the default, ordinary living covers ordinary "
        "needs. Interlocks with **act_need_relief** — before NPCs could act, "
        "needs only ever rose and one advance emptied the world.",
        "act_need_relief", "need_urgency_power",
    ),
    "act_need_relief": (
        "How much acting settles the need it answered. The other half of the "
        "interlock above: at 0 nothing anybody does relieves anything.",
        "need_upkeep",
    ),
    "actors_per_advance": (
        "The cap on how many characters act per advance — the lever that keeps "
        "a 500-NPC world a fixed bill. **report_lines** caps how many of them "
        "are *reported*, which is a different number and often should be lower.",
        "report_lines", "candidate_cap",
    ),
    "report_lines": (
        "Caps the report, not the simulation. People still act past this — "
        "they are counted as *and N others*.",
        "actors_per_advance",
    ),
    "report_stakes": (
        "Turns on the band whose thresholds are **stake_everything**, "
        "**stake_mattered** and **stake_noted**. Those three do nothing while "
        "this is off.",
        "stake_everything", "stake_mattered", "stake_noted",
    ),
    "candidate_cap": (
        "The documented performance lever for the decision engine "
        "(`06-DECISION-ENGINE.md` §11). Waiting always survives it, so a "
        "character can never be left with nothing to choose.",
        "actors_per_advance", "pack_count",
    ),
    "pack_count": (
        "How many archetypes each person is a blend of. Widening this widens "
        "the candidate list, which **candidate_cap** then trims. **0 switches "
        "archetypes off for people who already have them**, not merely for the "
        "next NPC generated.",
        "candidate_cap", "pack_drift", "pack_shaping",
    ),
    "goal_attention_overhead": (
        "Charged per goal carried, so usable attention *falls* as the list "
        "grows — one goal gets 0.92 of a person, six get 0.09 each. This is "
        "what makes the relentless character and the one who never finishes "
        "anything the same subtraction. At 0 it is plain division.",
        "goal_cap", "goal_attention",
    ),
    "goal_cap": (
        "A blunt backstop, **off by default**. It refuses rather than evicting: "
        "which ambition to drop is not a decision to make behind a GM's back. "
        "**goal_attention_overhead** is the mechanism that actually limits.",
        "goal_attention_overhead",
    ),
    "memory_decay_rate": (
        "Global multiplier over every per-field half-life "
        "(**stability_gist** and friends). **0 freezes memory entirely** — "
        "nothing fades, nothing confabulates.",
        "stability_gist", "stability_valence", "stability_participants",
        "stability_details", "stability_when", "memory_curve_shape",
    ),
    "need_desire": (
        "Gated twice. This setting **and** the campaign's lines must agree; a "
        "fresh campaign ships with sexual content on its lines, so switching "
        "this on alone does nothing. It also gates five interaction kinds, "
        "which are refused outright rather than filtered.",
        "desire_bleed",
    ),
    "desire_bleed": (
        "How fast repulsion sours affinity and respect on contact. One "
        "direction only — letting attraction feed back would loop through "
        "affinity and infatuate the whole campaign.",
        "need_desire",
    ),
    "role_prior_weight": (
        "How hard somebody's trade pulls their disposition. **The trade table "
        "itself is still code** (`mind/traits.py::_ROLE_PRIORS`) — this makes "
        "roles switchable but not editable, which is why a GM cannot add a "
        "trade. See the baked-in list.",
        "culture_prior_weight", "role_fit_sharpness",
    ),
    "culture_prior_weight": (
        "Same shape as the above, and the same gap: **CULTURES** is code.",
        "role_prior_weight",
    ),
    "decide_temperature": (
        "The floor of the softmax temperature. The actual T is "
        "`temperature + spread × volatility`, so a steady person is "
        "predictable and a volatile one is not. **T is never 0** — argmax "
        "would make every character a machine.",
        "decide_temperature_spread",
    ),
    "decide_risk_curve": (
        "The exponent on fear of death. Kept inside 0…1 by construction rather "
        "than by clamping — clipping sawed the top off exactly where the "
        "difference between *frightened* and *cannot make themselves* lives.",
    ),
    "time_mode": (
        "**timeless** is not *off*: nothing ages on a tick **or** on command, "
        "for dungeon crawls. manual and automatic both age; only the trigger "
        "differs. `/gm advance` and the tick share one code path on purpose.",
        "tick_hours", "tick_days",
    ),
    "remember_idle": (
        "Whether waiting alone off-screen forms a memory. It is the commonest "
        "thing an unwatched character does and therefore most of what a large "
        "world costs to run. Off, the world still logs it — nobody remembers it.",
        "actors_per_advance",
    ),
    "gist_perspective": (
        "Words each person's memory from their own side of an event. The "
        "wording comes from the interaction kind's **phrase**, which is data a "
        "GM can edit.",
        "gist_summaries",
    ),
    "npc_importance_default": (
        "Importance is a **CPU knob** — it scales memory budgets and how "
        "closely somebody is simulated. It is *not* standing, and reading it as "
        "standing once made every PC immune to every event.",
        "memory_budget_scale",
    ),
    "memory_budget_scale": (
        "Multiplies every per-tier memory cap. The bounded-cost guarantee: this "
        "is why 500 NPCs is a fixed bill rather than an unbounded one.",
        "npc_importance_default",
    ),
}


# --------------------------------------------------------------------------- #
#  The work queue: what is still baked in
# --------------------------------------------------------------------------- #
# Every entry is verified against the source by the suite — path, name and
# current value — so this list cannot quietly go stale, and an entry that has
# been exposed since must be removed from it or the tests fail.
#
# `planned` is the tuning group or data file it should end up in. `note` says
# what it actually does, because a name and a number is not enough to decide
# whether you want to change it.
@dataclass(frozen=True)
class Baked:
    """One constant that shapes behaviour and has no control yet.

    **It does not store the value.** An earlier draft did, and the suite caught
    four entries transcribed wrong within minutes — a catalogue that keeps its
    own copy of a number is just a fifth hand-maintained table. The value is
    read out of the source at render time by :func:`live_values`, so the page
    cannot be wrong about it and the entry cannot rot.
    """

    path: str
    name: str
    label: str
    note: str
    planned: str
    affects: tuple = field(default_factory=tuple)


BAKED_IN: tuple = (
    # --- the decision engine's per-verb tables. The biggest black box here:
    # every one of these is read on every scoring pass, for every candidate.
    Baked("helpers/dnd/mind/decide.py", "RISK",
          "How much of a gamble each verb is",
          "Before anything about the person. The risk term then bends it by "
          "their fear of death, so this is the shared baseline everyone's "
          "courage is measured against.",
          "data/verbs.json", ("decide_risk_curve",)),
    Baked("helpers/dnd/mind/decide.py", "NORM",
          "How acceptable each verb is",
          "What a person's own sense of propriety says about doing it, before "
          "the specific situation. Saturates rather than scaling linearly.",
          "data/verbs.json"),
    Baked("helpers/dnd/mind/decide.py", "SOCIAL_SIGN",
          "Whether a verb is friendly or hostile",
          "Signs the relationship term: doing something warm to somebody you "
          "like scores well, doing something hostile to them does not.",
          "data/verbs.json"),
    Baked("helpers/dnd/mind/decide.py", "TRAIT_AFFINITY",
          "Which disposition reaches for which verb",
          "The term that finally made `boldness` matter — declared in P2, "
          "rolled, stored, displayed, and read by nothing until this table.",
          "data/verbs.json"),
    Baked("helpers/dnd/mind/decide.py", "RELATION_READS",
          "How a verb reads against a relationship",
          "Which axes of how you feel about somebody push you toward or away "
          "from doing a given thing to them.",
          "data/verbs.json"),
    Baked("helpers/dnd/mind/decide.py", "NEEDS_SERVED",
          "Which needs each verb answers",
          "Drives both the need term in scoring and, via "
          "`minds.relieve_needs`, what acting actually settles.",
          "data/verbs.json", ("act_need_relief",)),
    Baked("helpers/dnd/mind/decide.py", "DEBT_SCALE",
          "What counts as a large debt",
          "The divisor that turns a debt count into a −1…1 term. At 5, owing "
          "five favours is as heavy as the scale goes.",
          "Deciding"),

    # --- goals
    Baked("helpers/dnd/mind/goals.py", "SUPPORTED_BY",
          "Which feelings re-weigh which ambitions",
          "Maps relationship axes onto goal kinds, so a grudge cools when the "
          "feeling behind it does. Always a pull, never a jump.",
          "data/verbs.json", ("goal_reweigh", "goal_reweigh_step")),
    Baked("helpers/dnd/mind/goals.py", "DEBT_SCALE",
          "What counts as a large debt (goals)",
          "A second copy of the scorer's constant, in a second module. Both "
          "should become one parameter.",
          "Goals"),

    # --- needs
    Baked("helpers/dnd/mind/needs.py", "HOURS_TO_DESPERATE",
          "How long until each need is desperate",
          "The span for somebody getting *nothing* — which is what deprivation "
          "takes away. Partly exposed already: `need_hours_hunger` and three "
          "others override some of these, but not all six.",
          "Needs", ("need_upkeep",)),
    Baked("helpers/dnd/mind/needs.py", "HOURS_TO_CALM",
          "How long until pain and fear settle",
          "The two needs that *fall* on their own rather than rising.",
          "Needs"),
    Baked("helpers/dnd/mind/needs.py", "IMPULSE_THRESHOLD",
          "When a need becomes an urge",
          "The line between pressure and an impulse that shoves a decision. "
          "Exposed as `need_impulse_threshold` — this is only its default.",
          "(already exposed as need_impulse_threshold)"),

    # --- relationships
    Baked("helpers/dnd/mind/relationships.py", "TRAIT_MODIFIERS",
          "Which trait sharpens which relationship axis",
          "Why two people do not react identically to the same act: a fearful "
          "character takes a threat harder, an honourable one weighs a debt "
          "more.",
          "data/axes.json", ("relationship_scale",)),
    Baked("helpers/dnd/mind/relationships.py", "ATTRACTION_WEIGHTS",
          "What decides who is drawn to whom",
          "Weighted so a plain, trusted, familiar person is wanted **more** "
          "than a striking stranger. `allure` is deliberately the smallest term.",
          "data/axes.json", ("need_desire",)),
    Baked("helpers/dnd/mind/relationships.py", "FEAR_SUPPRESSES",
          "How much fear puts out desire",
          "Above 1 so that being afraid of somebody extinguishes wanting them "
          "almost entirely.",
          "Relationships", ("need_desire",)),

    # --- who people are
    Baked("helpers/dnd/mind/traits.py", "_ROLE_PRIORS",
          "What each trade implies about a person",
          "**The long-standing gap: a GM cannot add a trade.** Read backwards "
          "at generation. `role_prior_weight` makes it switchable but not "
          "editable.",
          "data/priors.json", ("role_prior_weight", "role_fit_sharpness")),
    Baked("helpers/dnd/mind/traits.py", "CULTURES",
          "What each culture implies about a person",
          "Same gap as trades, same fix. A campaign in its own setting cannot "
          "name its own peoples.",
          "data/priors.json", ("culture_prior_weight",)),
    Baked("helpers/dnd/mind/traits.py", "HERITABILITY",
          "How much children resemble their parents",
          "Exposed as `heritability` — this is its default.",
          "(already exposed as heritability)"),
    Baked("helpers/dnd/mind/traits.py", "SIBLING_VARIANCE",
          "How much siblings differ",
          "Exposed as `trait_variance` — this is its default.",
          "(already exposed as trait_variance)"),
    Baked("helpers/dnd/mind/traits.py", "RETENTION_VARIANCE",
          "How much memory faculty varies between people",
          "Why some characters remember nearly everything and some lose names "
          "by the next week.",
          "Generation", ("memory_retention_reach",)),

    # --- memory
    Baked("helpers/dnd/mind/memory/consolidate.py", "WORKING_FLOOR",
          "What survives the end of a scene",
          "Salience below this is dropped rather than promoted to mid-term. "
          "The trivia filter.",
          "Memory"),
    Baked("helpers/dnd/mind/memory/consolidate.py", "MID_FLOOR",
          "What survives into long-term",
          "The same filter one tier up.",
          "Memory"),
    Baked("helpers/dnd/mind/memory/consolidate.py", "PROTECT_DAYS",
          "How long a recalled memory is safe from pruning",
          "Something someone keeps reaching for is by definition still in use.",
          "Memory", ("memory_budget_scale",)),
    Baked("helpers/dnd/mind/memory/decay.py", "RETENTION_IMPRINT_SHIFT",
          "How much a good memory lowers the imprint bar",
          "People who remember well form formative memories slightly more "
          "readily.",
          "Memory", ("imprint_threshold",)),
    Baked("helpers/dnd/mind/memory/encode.py", "PARTIAL_CLARITY",
          "Clarity of a half-seen event", "Below this, detail and participants "
          "start dropping out at the moment of encoding.",
          "Memory"),
    Baked("helpers/dnd/mind/memory/encode.py", "COARSE_CLARITY",
          "Clarity at which an event is only its gist",
          "The distant witness who saw *a fight* and nothing more.",
          "Memory"),
    Baked("helpers/dnd/mind/memory/recall.py", "GIST_STRENGTHEN",
          "How much recalling something reinforces it",
          "Reconsolidation: thinking about something rewrites it, slightly "
          "stronger each time.",
          "Salience", ("salience_reinforce",)),
    Baked("helpers/dnd/mind/memory/recall.py", "CONTAMINATION_CHANCE",
          "Chance recall borrows a detail from elsewhere",
          "How a memory quietly acquires a detail that belongs to a different "
          "memory entirely.",
          "Forgetting", ("memory_confabulate_chance",)),
    Baked("helpers/dnd/mind/memory/recall.py", "RECENCY_WINDOW_DAYS",
          "How long something counts as recent for recall",
          "Inside this window a memory comes to mind more easily.",
          "Memory"),
    Baked("helpers/dnd/mind/memory/values.py", "WARMTH_WEIGHT",
          "How much warmth shapes what somebody notices",
          "Part of the value system that decides what is worth keeping.",
          "Salience", ("salience_value_weight",)),
    Baked("helpers/dnd/mind/memory/values.py", "DRIVE_CONCERNS",
          "Which words each drive cares about",
          "**English-only.** A grasping character keeps every debt and loses "
          "every kindness because of this table. Would need attention before a "
          "non-English campaign.",
          "data/values.json", ("salience_value_weight",)),
    Baked("helpers/dnd/world/memory.py", "CLEAR_THRESHOLD",
          "Clarity above which a memory reads as certain",
          "Decides whether recall says *I saw* or *I think*.",
          "Memory"),
    Baked("helpers/dnd/world/memory.py", "HEDGE_THRESHOLD",
          "Clarity below which a memory reads as a guess",
          "Below this a character hedges rather than asserts.",
          "Memory"),
    Baked("helpers/dnd/world/memory.py", "IMPRINT_RECALL_SALIENCE",
          "Salience a memory needs to imprint by repetition",
          "The floor under `imprint_recalls` — being recalled often is not "
          "enough on its own.",
          "Memory", ("imprint_recalls", "imprint_threshold")),

    # --- perception
    Baked("helpers/dnd/world/view.py", "PRESSING",
          "When a need is pressing enough to reach a decision",
          "The line above which a need is carried into the projection an NPC "
          "decides from.",
          "Perception", ("need_impulse_threshold",)),

    # --- knowledge retrieval
    Baked("helpers/dnd/store/knowledge.py", "W_TAGS",
          "Retrieval weight: tag match", "How much a fact's tags matching the "
          "query decides whether it is retrieved.", "Knowledge"),
    Baked("helpers/dnd/store/knowledge.py", "W_ENTITIES",
          "Retrieval weight: entity match",
          "How much naming the same people matters.", "Knowledge"),
    Baked("helpers/dnd/store/knowledge.py", "W_WEIGHT",
          "Retrieval weight: the fact's own importance", 
          "How much a fact being marked important by whoever wrote it counts toward being retrieved at all.", "Knowledge"),
    Baked("helpers/dnd/store/knowledge.py", "W_TIER",
          "Retrieval weight: how specific the tier is",
          "Campaign knowledge outranks global knowledge.", "Knowledge"),
    Baked("helpers/dnd/store/knowledge.py", "W_RECENCY",
          "Retrieval weight: recency", 
          "How much lately-written knowledge outranks old knowledge. The smallest of the five weights, deliberately: a campaign's founding facts should not sink.", "Knowledge"),
    Baked("helpers/dnd/store/knowledge.py", "RECENCY_DAYS",
          "How long a fact counts as recent", 
          "The window the recency weight above is measured over.", "Knowledge"),
    Baked("helpers/dnd/store/canon.py", "SOFT_CANON_WEIGHT",
          "How much weight an unruled proposal carries",
          "Soft canon is retrievable but is not a fact until a GM accepts it.",
          "Knowledge"),

    # --- rulesets
    Baked("helpers/dnd/rules/freeform.py", "DEFAULT_DC",
          "Default difficulty (freeform)", "What a check is set at when nobody "
          "says otherwise.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "DEFAULT_DC",
          "Default difficulty (SRD 5e)",
          "What a check is set at when the GM does not say. 15 is the "
          "SRD's *hard*; a table that wants a gentler game has no way to "
          "say so.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "DEFAULT_HIT_DIE",
          "Hit die for a class the table does not know", 
          "The fallback when somebody plays something the SRD list has never heard of.",
          "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "CLASS_HIT_DIE",
          "Hit die per class", 
          "How much health each class gets per level. A homebrew class cannot be added.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "CLASS_PRIORITY",
          "Which abilities each class wants first",
          "Drives the standard-array assignment at character creation.",
          "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "STANDARD_ARRAY",
          "The standard ability array", 
          "The six numbers a new character's abilities are drawn from before class priority assigns them.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "SKILL_ABILITY",
          "Which ability each skill uses", 
          "The SRD mapping. A table with a house skill cannot add one.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/freeform.py", "STANDARD_SPREAD",
          "The freeform approach spread", 
          "The four modifiers a freeform character distributes across Force, Finesse, Wits and Presence.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/freeform.py", "_CONCEPT_HINTS",
          "Which words suggest which approach",
          "Reads a character concept and guesses their strongest approach.",
          "data/rulesets.json"),

    # --- wording. Lower stakes than the weights, but a campaign in its own
    # setting should be able to say things its own way.
    Baked("helpers/dnd/narrate.py", "ACT_GISTS",
          "What an undirected act reads as in a memory", 
          "*I went to ground* against *Marla went to ground*. The commonest memory anybody holds about themselves.", "data/verbs.json"),
    Baked("helpers/dnd/narrate.py", "ACTED_PHRASES",
          "What an act reads as in the turn report", 
          "The verbs `/gm advance` uses. Separate from the memory wording because a report and a recollection are different registers.", "data/verbs.json"),
    Baked("helpers/dnd/narrate.py", "NEED_EASED",
          "What a settled need is called in a sentence", 
          "*that settled their hunger a little*. Blunt on purpose - there is no item model, so it never says what they ate.", "data/needs.json"),
    Baked("helpers/dnd/narrate.py", "STAKE_PHRASES",
          "The four stake-band phrasings",
          "The thresholds are tunable; the wording is not. Four phrases is a "
          "vocabulary rather than three numbers.",
          "data/needs.json", ("stake_everything", "stake_mattered", "stake_noted")),
    Baked("helpers/dnd/narrate.py", "_PERIODS",
          "How long a forgotten stretch is called", 
          "Day, week, fortnight, month, season, year - the thresholds a summary picks its word from.", "data/needs.json"),
    Baked("helpers/dnd/narrate.py", "_TONES",
          "How a forgotten stretch felt, in a word", 
          "bad / hard / quiet / good / fine, chosen by the mean valence of the memories being folded.", "data/needs.json"),
    Baked("helpers/dnd/minds.py", "ACT_AS_RELATION",
          "Which verb counts as which interaction kind",
          "The join between what an NPC *does* and what the relationship "
          "system records. A verb missing here still happens and is still "
          "remembered — it simply does not move how two people stand.",
          "data/verbs.json"),
    Baked("helpers/dnd/minds.py", "_SEEDS",
          "The backstory events a new NPC may be given",
          "Seeded history. Note the known bug: these are dated at most ~14 "
          "days back, so a formative childhood event reads as last week.",
          "data/priors.json"),
    Baked("helpers/dnd/mind/rumour.py", "_DRIFT_WORDS",
          "Which words a retelling swaps",
          "One word per hop, which is how *a debt* becomes *a fortune*. "
          "English-only.", "data/values.json", ("rumour_mutate",)),
    Baked("helpers/dnd/mind/memory/encode.py", "_COARSE",
          "What a half-seen event reduces to",
          "The distant witness's vocabulary. English-only.",
          "data/values.json", ("view_clarity_floor",)),
    Baked("helpers/dnd/mind/needs.py", "NEED_IMPULSE",
          "What each need makes somebody want to do", 
          "eat, drink, rest - the urge a need turns into once it crosses the impulse threshold.", "data/needs.json"),
    Baked("helpers/dnd/mind/needs.py", "NEED_LABELS",
          "Display names for the needs", 
          "What the inspector calls each one.", "data/needs.json"),
    Baked("helpers/dnd/mind/traits.py", "TRAIT_LABELS",
          "Display names for the disposition axes", 
          "What the inspector calls each axis of who somebody is.", "data/priors.json"),
    Baked("helpers/dnd/mind/traits.py", "_TRAIT_WORDS",
          "The two ends of each disposition axis, in words",
          "What the inspector calls somebody at each end of a scale.",
          "data/priors.json"),
    Baked("helpers/dnd/world/relationship.py", "AXIS_LABELS",
          "Display names for the relationship axes", 
          "Affinity, trust, fear, respect, familiarity, desire.", "data/axes.json"),
    Baked("helpers/dnd/rules/freeform.py", "APPROACH_LABELS",
          "Display names for the freeform approaches", 
          "Force, Finesse, Wits, Presence.", "data/rulesets.json"),
    Baked("helpers/dnd/rules/srd5e.py", "ABILITY_LABELS",
          "Display names for the SRD abilities", 
          "Strength through Charisma.", "data/rulesets.json"),
    Baked("helpers/dnd/migrate.py", "GIST_CHARS",
          "How much of a legacy history line becomes a memory",
          "Only used by the one-time importer.", "(importer only)"),

    # --- constants that already have a tunable in front of them. Listed so the
    # page can say "yes, this number is reachable, here is the control" rather
    # than leaving a reader to wonder whether it was overlooked.
    Baked("helpers/dnd/world/memory.py", "FIELD_STABILITY",
          "Base half-life of each memory field",
          "Which part of a memory rots first: time and place, then details, "
          "then faces, then how it felt, and the gist last. Exposed one field "
          "at a time as the five `stability_*` settings.",
          "(already exposed as stability_gist)", ("memory_decay_rate",)),
    Baked("helpers/dnd/world/memory.py", "SHAPE",
          "Sharpness of the forgetting curve",
          "0.5 matches the classic Ebbinghaus data.",
          "(already exposed as memory_curve_shape)"),
    Baked("helpers/dnd/world/memory.py", "CONFABULATE_THRESHOLD",
          "Clarity below which a field can be misremembered",
          "Below this a faded field may be filled with a plausible wrong value "
          "drawn from that character's other memories.",
          "(already exposed as memory_confabulate_threshold)"),
    Baked("helpers/dnd/world/memory.py", "IMPRINT_THRESHOLD",
          "Salience at which one event marks somebody permanently",
          "Imprints never decay, at any retention, over any span.",
          "(already exposed as imprint_threshold)"),
    Baked("helpers/dnd/world/memory.py", "IMPRINT_RECALLS",
          "Times a memory must be recalled to imprint anyway",
          "The other road to a formative memory: not one overwhelming night, "
          "but returning to something often enough.",
          "(already exposed as imprint_recalls)"),
    Baked("helpers/dnd/world/view.py", "MEMORY_LIMIT",
          "How many memories reach one decision",
          "The projection an NPC decides from is budgeted; this is the cap on "
          "its memory half. A cap of 0 is no cap.",
          "(already exposed as view_memory_limit)"),
    Baked("helpers/dnd/world/view.py", "BELIEF_LIMIT",
          "How many beliefs reach one decision",
          "The belief half of the same budget.",
          "(already exposed as view_belief_limit)"),
    Baked("helpers/dnd/world/view.py", "RELATIONSHIP_LIMIT",
          "How many relationships reach one decision",
          "The social half. In a crowded scene this is the one that bites.",
          "(already exposed as view_relationship_limit)"),
    Baked("helpers/dnd/world/view.py", "BELIEF_FLOOR",
          "Confidence below which a belief is not carried",
          "A floor of 0 lets everything through.",
          "(already exposed as view_belief_floor)"),
    Baked("helpers/dnd/world/view.py", "CLARITY_FLOOR",
          "Clarity below which a memory is not carried",
          "A memory too faded to be any use does not take up a slot.",
          "(already exposed as view_clarity_floor)"),
    Baked("helpers/dnd/world/view.py", "STRANGER_FLOOR",
          "How much of a stranger reaches a decision",
          "What somebody knows about a person they have never met.",
          "(already exposed as view_stranger_floor)"),

    # --- infrastructure. Not simulation, but still numbers with no control.
    Baked("helpers/dnd/world/campaign.py", "DEFAULT_SETTINGS",
          "What a fresh campaign starts with",
          "Including **the conservative safety lines**, which is why switching "
          "an optional need on does nothing until a line is cleared. Changing "
          "this changes only new campaigns.",
          "Continuity", ("need_desire",)),
    Baked("helpers/dnd/store/events.py", "_MAX_SEQ_RETRIES",
          "Retries when two writes claim the same event number",
          "Infrastructure rather than simulation: the event log's sequence is "
          "unique per campaign, and two simultaneous writes race for it.",
          "Rules"),
)


# --------------------------------------------------------------------------- #
#  Assembly
# --------------------------------------------------------------------------- #
_LIVE: dict[tuple, Any] | None = None


def live_values() -> dict[tuple, Any]:
    """``{(path, name): value}`` read straight out of the source.

    So the catalogue never keeps its own copy of a number it does not own. A
    table too large to print is summarised at render time rather than stored.
    """
    global _LIVE
    if _LIVE is None:
        _LIVE = {}
        root = os.path.dirname(HERE)          # helpers/
        for base, _dirs, files in os.walk(HERE):
            if "__pycache__" in base:
                continue
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                full = os.path.join(base, name)
                rel = os.path.relpath(full, os.path.dirname(root)).replace(os.sep, "/")
                try:
                    tree = ast.parse(open(full, encoding="utf-8").read())
                except (OSError, SyntaxError):
                    continue
                for node in tree.body:
                    targets = []
                    if isinstance(node, ast.Assign):
                        targets = [t.id for t in node.targets
                                   if isinstance(t, ast.Name)]
                    elif isinstance(node, ast.AnnAssign) and \
                            isinstance(node.target, ast.Name):
                        targets = [node.target.id]
                    for target in targets:
                        try:
                            _LIVE[(rel, target)] = ast.literal_eval(node.value)
                        except Exception:
                            continue
    return dict(_LIVE)


def shown_value(value: Any, limit: int = 5) -> str:
    """A value a person can read at a glance. Big tables become a shape."""
    if isinstance(value, dict):
        if len(value) <= limit and all(
                isinstance(v, (int, float, str)) for v in value.values()):
            return ", ".join(f"{k} {v}" for k, v in value.items())
        return f"{len(value)} entries"
    if isinstance(value, (tuple, list)):
        if len(value) <= limit and all(
                isinstance(v, (int, float)) for v in value):
            return ", ".join(str(v) for v in value)
        return f"{len(value)} entries"
    return str(value)


# A baked-in entry's `planned` says where it *should* live; this says which
# section of the page it belongs in meanwhile, so the catalogue reads by subject
# rather than by destination. `Rules` is a catalogue-only section: the rulesets
# have no tuning group because nothing in them is tunable yet, which is itself
# the point of listing them.
EXTRA_GROUPS = ("Rules",)
PLANNED_GROUP = {
    "data/verbs.json": "Deciding",
    "data/priors.json": "Generation",
    "data/axes.json": "Relationships",
    "data/needs.json": "Needs",
    "data/values.json": "Salience",
    "data/rulesets.json": "Rules",
    "(importer only)": "Rules",
}


def _group_for(baked: "Baked") -> str:
    """Which section of the catalogue a baked-in constant is listed under."""
    planned = baked.planned
    if planned in PLANNED_GROUP:
        return PLANNED_GROUP[planned]
    if planned.startswith("(already exposed as "):
        # It has a tunable already and this is only its default — file it beside
        # that tunable rather than in a section of its own.
        key = planned[len("(already exposed as "):].rstrip(")")
        spec = BY_KEY.get(key)
        return spec["group"] if spec else "Rules"
    return planned if planned in GROUPS else "Rules"


def _span(spec: dict) -> str:
    if spec["type"] == "choice":
        return " / ".join(str(c) for c in (spec.get("choices") or ()))
    if spec["type"] == "bool":
        return "on / off"
    return f"{spec['min']}–{spec['max']}"


def entries() -> list[Entry]:
    """Every parameter in the engine, exposed or not, in group order."""
    view_of = views()
    by_view: dict[str, list] = {}
    for spec in TUNABLES:
        by_view.setdefault(view_of.get(spec["key"], ""), []).append(spec["key"])

    out: list[Entry] = []
    for spec in TUNABLES:
        key = spec["key"]
        view = view_of.get(key, "")
        authored = AFFECTS.get(key, ())
        note = authored[0] if authored and isinstance(authored[0], str) else ""
        related = tuple(a for a in authored[1:]) if note else tuple(authored)
        out.append(Entry(
            key=key, label=spec["label"], description=spec["description"],
            default=spec["default"], span=_span(spec), group=spec["group"],
            status=STATUS_TUNABLE,
            layer=LAYER_SERVER if spec["scope"] == "server" else LAYER_CAMPAIGN,
            where=CONSUMED_BY.get(view, ""), view=view,
            siblings=tuple(k for k in by_view.get(view, ()) if k != key),
            affects=related, note=note,
        ))

    # The two data registries. Not one parameter each — a whole editable table.
    out.append(Entry(
        key="data/packs.json", label="Behaviour archetypes",
        description=(
            "What each archetype reaches for, and the disposition it implies. "
            f"{len(pack_registry.built_in())} ship; a GM may edit any of them "
            "or add their own from the campaign page."
        ),
        default=f"{len(pack_registry.built_in())} archetypes", span="editable",
        group="Behaviour", status=STATUS_DATA, layer=LAYER_DATA,
        where="mind/behaviour.py", view="behaviour",
        affects=("pack_count", "pack_drift", "pack_shaping", "candidate_cap"),
        note="Resolved built-in → server → campaign, like the tunables.",
    ))
    out.append(Entry(
        key="data/interactions.json", label="What people do to each other",
        description=(
            "Per interaction kind: how big it is, how it moves the two people, "
            "how it reads in a memory, and which optional need gates it. "
            f"{len(interaction_registry.built_in())} ship; all editable."
        ),
        default=f"{len(interaction_registry.built_in())} kinds", span="editable",
        group="Stakes", status=STATUS_DATA, layer=LAYER_DATA,
        where="mind/stakes.py, mind/relationships.py", view="stakes",
        affects=("stakes_capacity_reach", "stakes_need_reach",
                 "stakes_actor_echo", "need_desire"),
        note="Replaced four hand-maintained Python tables that had drifted apart.",
    ))

    live = live_values()
    for baked in BAKED_IN:
        already = baked.planned.startswith("(already exposed as ")
        here = (baked.path, baked.name)
        out.append(Entry(
            key=f"{baked.path}::{baked.name}", label=baked.label,
            description=baked.note,
            default=(shown_value(live[here]) if here in live else "?"),
            span="—",
            group=_group_for(baked), status=STATUS_BAKED, layer=LAYER_CODE,
            where=baked.path, affects=tuple(baked.affects),
            planned=baked.planned,
            note=("Already reachable — this constant is only the default "
                  "behind a tunable." if already
                  else "Not exposed yet. This is the work queue."),
        ))
    return out


def summary() -> dict:
    """Counts for the page header, and for the suite to assert against."""
    rows = entries()
    return {
        "total": len(rows),
        "tunable": sum(1 for e in rows if e.status == STATUS_TUNABLE),
        "data": sum(1 for e in rows if e.status == STATUS_DATA),
        "baked": sum(1 for e in rows if e.status == STATUS_BAKED),
        "groups": len(GROUPS),
    }


def grouped() -> list[tuple]:
    """``[(group, [Entry, ...])]`` in the panel's group order, exposed first.

    Baked-in entries sort to the bottom of their group so the page reads as
    *here is what you can change, and here is what you cannot yet*.
    """
    rows = entries()
    order = {name: index for index, name in enumerate(GROUPS + EXTRA_GROUPS)}
    buckets: dict[str, list] = {}
    for entry in rows:
        buckets.setdefault(entry.group, []).append(entry)
    for bucket in buckets.values():
        bucket.sort(key=lambda e: (e.status == STATUS_BAKED, e.label.lower()))
    return sorted(buckets.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))
