"""
Tunables — nothing in the simulation is baked in.

Every constant that shapes how minds behave is declared here with a default, a
range, and a plain-English description, and can be overridden at **two levels**:

    built-in default  →  server override  →  campaign override

A server admin sets the house style for the whole guild; a **campaign GM tunes
their own game** without touching anyone else's. Resolution is most-specific-wins,
the same shape as the knowledge tiers and ``LangManager.get`` — one mental model
for layered configuration across the whole codebase.

Where the values live:

* server overrides  → the ``DndParams`` collection, via ``helpers/dnd/parameters``
* campaign overrides → ``campaign.settings["tuning"]``, so a campaign carries its
  own rules with it and an export bundle needs no extra table

**The pure layer never reads this module.** ``mind/`` takes plain dataclasses
(:class:`MemoryTuning`, :class:`NeedsTuning`, …) as arguments, and this module's
job is to build them. That is what keeps the simulation deterministic and
testable without a database — and it means a tunable is one entry here plus one
field on a dataclass, never a lookup buried in a hot loop.

Adding a tunable: add a spec to :data:`TUNABLES`, add the field to the relevant
``*Tuning`` dataclass, and read it where the constant used to be. The panel
renders it automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from helpers.dnd.world import memory as memory_model

# Who may change a given tunable.
SCOPE_SERVER = "server"       # server admins only
SCOPE_CAMPAIGN = "campaign"   # campaign GMs (and server admins)

# Groups, in the order the panel shows them.
GROUPS = (
    "Memory", "Forgetting", "Salience", "Needs", "Relationships", "Stakes",
    "Continuity", "Knowledge", "Generation",
)


def _spec(key, group, label, description, default, kind="float",
          minimum=0.0, maximum=1.0, scope=SCOPE_CAMPAIGN, choices=None) -> dict:
    return {
        "key": key, "group": group, "label": label, "description": description,
        "default": default, "type": kind, "min": minimum, "max": maximum,
        "scope": scope, "choices": choices,
    }


# --------------------------------------------------------------------------- #
#  The registry
# --------------------------------------------------------------------------- #
TUNABLES: list[dict] = [
    # --- Forgetting -------------------------------------------------------- #
    _spec("memory_decay_rate", "Forgetting", "Forgetting speed",
          "Global multiplier on how fast memories fade. 1.0 is normal, 0.5 is half "
          "speed, and **0 switches forgetting off entirely** — memories are frozen "
          "exactly as encoded.",
          1.0, minimum=0.0, maximum=5.0),
    _spec("memory_curve_shape", "Forgetting", "Curve shape",
          "Sharpness of the forgetting curve. Higher means a steeper initial loss "
          "and a flatter long tail; lower means a more even fade. 0.5 matches the "
          "classic Ebbinghaus data.",
          memory_model.SHAPE, minimum=0.1, maximum=2.0),
    _spec("memory_salience_reach", "Forgetting", "Salience matters",
          "How much a memory mattering at the time protects it. At 6, something "
          "overwhelming lasts about seven times as long as something trivial.",
          6.0, minimum=0.0, maximum=20.0),
    _spec("memory_retention_reach", "Forgetting", "Personal differences",
          "How much an individual's retention faculty matters. At 2, someone with "
          "a perfect memory holds things twice as long as average and someone "
          "forgetful about a third as long. Set to 1 to make everyone the same.",
          2.0, minimum=1.0, maximum=6.0),
    _spec("memory_alignment_reach", "Forgetting", "Values matter",
          "How much a character's value system decides what they keep. At 1, a "
          "memory squarely in line with what they care about lasts twice as long "
          "as one that isn't. **Set to 0 for value-blind forgetting.**",
          1.0, minimum=0.0, maximum=4.0),
    _spec("memory_confabulate_chance", "Forgetting", "Misremembering",
          "Chance a faded detail is replaced with a plausible *wrong* value rather "
          "than simply going blank. 0 means characters know what they've forgotten.",
          0.5),
    _spec("memory_confabulate_threshold", "Forgetting", "Misremember below",
          "Clarity below which a field can be confabulated.",
          memory_model.CONFABULATE_THRESHOLD),

    # --- Memory shape ------------------------------------------------------ #
    _spec("stability_gist", "Memory", "Gist holds (days)",
          "Base days before the *substance* of a memory starts to blur. The "
          "longest-lived field: you remember that it happened long after the rest.",
          memory_model.FIELD_STABILITY["gist"], kind="int", minimum=1, maximum=5000),
    _spec("stability_valence", "Memory", "Feeling holds (days)",
          "Base days before *how it felt* fades. After this, a memory goes numb.",
          memory_model.FIELD_STABILITY["valence"], kind="int", minimum=1, maximum=5000),
    _spec("stability_participants", "Memory", "Faces hold (days)",
          "Base days before *who was there* blurs — the field most likely to be "
          "misremembered as someone else.",
          memory_model.FIELD_STABILITY["participants"], kind="int", minimum=1, maximum=5000),
    _spec("stability_details", "Memory", "Details hold (days)",
          "Base days before the specifics go.",
          memory_model.FIELD_STABILITY["details"], kind="int", minimum=1, maximum=5000),
    _spec("stability_when", "Memory", "Time & place hold (days)",
          "Base days before *when and where* is lost. The first thing to go.",
          memory_model.FIELD_STABILITY["when"], kind="int", minimum=1, maximum=5000),
    _spec("imprint_threshold", "Memory", "Imprint threshold",
          "Salience at which one event marks a character permanently. Imprints "
          "never decay. Lower means more formative memories.",
          memory_model.IMPRINT_THRESHOLD),
    _spec("imprint_recalls", "Memory", "Imprint by repetition",
          "Times a memory must be recalled before it becomes formative anyway.",
          memory_model.IMPRINT_RECALLS, kind="int", minimum=1, maximum=100),
    _spec("memory_budget_scale", "Memory", "Memory capacity",
          "Multiplier on how many memories an entity may hold. Higher is richer "
          "and slower; the cap is what keeps a big world cheap to run.",
          1.0, minimum=0.1, maximum=10.0),

    # --- Salience ---------------------------------------------------------- #
    _spec("salience_emotional", "Salience", "Weight: intensity",
          "How much raw emotional force decides whether something is remembered.",
          0.35),
    _spec("salience_relevance", "Salience", "Weight: was it about me",
          "How much being personally involved matters.", 0.25),
    _spec("salience_novelty", "Salience", "Weight: novelty",
          "How much being unlike anything before matters.", 0.20),
    _spec("salience_social", "Salience", "Weight: who was involved",
          "How much involving someone they care about matters.", 0.20),
    _spec("salience_reinforce", "Salience", "Reinforcement per recall",
          "How much recalling something strengthens it.", 0.15),
    _spec("salience_value_weight", "Salience", "Weight: does it fit their values",
          "How much a character *notices* things that matter to their value system "
          "in the first place. A grasping NPC clocks a debt others would miss. This "
          "compounds with 'Values matter' under Forgetting: what you notice more, "
          "you also keep longer. Set to 0 for value-blind attention.",
          0.5, minimum=0.0, maximum=2.0),

    # --- Needs ------------------------------------------------------------- #
    _spec("need_urgency_power", "Needs", "Urgency curve",
          "Exponent on need urgency. 3 means a need is ignorable until it suddenly "
          "isn't; 1 makes NPCs fret constantly about being slightly peckish.",
          3.0, minimum=1.0, maximum=6.0),
    _spec("need_hours_hunger", "Needs", "Hours to starving",
          "In-world hours from fed to desperate.", 48, kind="int", minimum=1, maximum=500),
    _spec("need_hours_thirst", "Needs", "Hours to parched",
          "In-world hours from watered to desperate.", 24, kind="int", minimum=1, maximum=500),
    _spec("need_hours_fatigue", "Needs", "Hours to exhausted",
          "In-world hours awake before collapse.", 20, kind="int", minimum=1, maximum=500),
    _spec("need_impulse_threshold", "Needs", "Impulse threshold",
          "How high a need must climb before it starts pulling at behaviour.", 0.55),

    # --- Relationships ----------------------------------------------------- #
    _spec("relationship_scale", "Relationships", "Relationship swing",
          "Multiplier on how far a single event moves a relationship. Lower makes "
          "opinions slow and hard-won.", 1.0, minimum=0.1, maximum=5.0),
    _spec("faction_prior", "Relationships", "Faction prior",
          "How strongly whose-side-you're-on seeds a first impression, before "
          "anything personal has happened.", 0.6),

    # --- Stakes ------------------------------------------------------------ #
    _spec("stakes_capacity_reach", "Stakes", "Circumstances matter",
          "How much what someone *has* decides what an event is worth to them. At "
          "1 a wealthy lord barely notices the debt he settles while it saves the "
          "debtor's life. **Set to 0 to make every event worth the same to "
          "everyone**, which is how most games do it.",
          1.0, minimum=0.0, maximum=4.0),
    _spec("stakes_need_reach", "Stakes", "Desperation matters",
          "How much a pressing need magnifies whatever relieves it. Bread means "
          "more to the starving. 0 ignores need entirely.",
          1.0, minimum=0.0, maximum=3.0),
    _spec("stakes_unknown_actor_floor", "Stakes", "Unknown benefactor",
          "How much an event still moves someone when they never learn who did "
          "it. Above 0 they are changed by it without having anyone to thank or "
          "blame; at 0 an anonymous act leaves no mark on them at all.",
          0.25),
    _spec("role_prior_weight", "Generation", "Role shapes the person",
          "How much a named role stamps its pattern onto a new NPC. **At 0 a "
          "thief is just a person who thieves** — traits roll freely and the "
          "stereotype only emerges across a population, from who ends up doing "
          "what. At 1 every thief arrives thief-shaped, which populates a world "
          "fast but makes them all the same person.",
          0.5),
    _spec("culture_prior_weight", "Generation", "Culture shapes the person",
          "The same, for where they are from. **0 means culture is a fact about "
          "them and not a temperament.**",
          0.5),
    _spec("role_fit_sharpness", "Generation", "Fit decides the trade",
          "When an NPC is created without a role, how strongly their disposition "
          "decides what they turned out to be. 0 draws a trade at random; high "
          "values make people fall into the work they are shaped for.",
          3.0, minimum=0.0, maximum=10.0),
    _spec("stakes_disposition_reach", "Stakes", "Character over station",
          "How much a person's warmth, honour and belonging override the "
          "insulation their standing gives them. High means a benevolent lord "
          "notices what his servants do for him while a cold one of equal rank "
          "does not. **Set to 0 and station alone decides**, so the powerful "
          "never notice anything — simpler, and a cliché.",
          0.7, minimum=0.0, maximum=1.0),
    _spec("time_mode", "Continuity", "How time works here",
          "**manual** — nothing moves unless you say so with `/gm advance`. The "
          "default, and right for most tables. "
          "**automatic** — the world turns on its own at the pace set below, so "
          "coming back after a week finds things changed. "
          "**timeless** — time is not a thing in this campaign. Nothing ages, "
          "nothing is forgotten, needs never press, and `/gm advance` politely "
          "declines. For a dungeon crawl, a one-shot, or any game where the "
          "world outside the room is not the point.",
          "manual", kind="choice", choices=["manual", "automatic", "timeless"]),
    _spec("tick_hours", "Continuity", "Real hours per tick",
          "How often the world moves while nobody is looking. Low values make a "
          "campaign feel alive and cost more; high ones are cheaper and calmer.",
          6.0, minimum=0.25, maximum=168.0),
    _spec("tick_days", "Continuity", "In-world days per tick",
          "How much time passes each time it turns. At 1 day per 6 hours, a week "
          "away is about a month in the world.",
          1.0, minimum=0.01, maximum=90.0),
    _spec("stakes_actor_echo", "Stakes", "Doing versus receiving",
          "How much of a feeling the person who *did* something keeps for the "
          "person they did it to. Helping someone warms you to them a little, "
          "and wronging them cools you — but never as much as being on the "
          "receiving end. **At 0 the actor's feelings do not move at all**; "
          "debt still changes hands either way.",
          0.3, minimum=0.0, maximum=1.0),
    _spec("stakes_familiarity_reach", "Stakes", "Knowing someone",
          "How much a significant event closes the distance between two people, "
          "on top of what the event kind gives. At 0 you know someone no better "
          "for having been saved by them than for having been introduced.",
          0.35, minimum=0.0, maximum=1.0),
    _spec("stakes_witness_reach", "Stakes", "Bystanders judge",
          "How far an event moves the feelings of people who merely *saw* it, "
          "relative to those it happened to. 0 means onlookers remember it and "
          "feel nothing about the person who did it.",
          0.5, minimum=0.0, maximum=2.0),

    # --- Knowledge (P1) ---------------------------------------------------- #
    _spec("kb_budget", "Knowledge", "Knowledge budget (tokens)",
          "How much campaign knowledge a scene may draw on.",
          1200, kind="int", minimum=100, maximum=20000),
    _spec("kb_max_facts", "Knowledge", "Max facts retrieved",
          "Hard cap on facts pulled per retrieval.", 40, kind="int", minimum=1, maximum=500),

    # --- Generation -------------------------------------------------------- #
    _spec("npc_importance_default", "Generation", "Default NPC importance",
          "How much a new NPC matters by default. Drives memory capacity and how "
          "often they are simulated.", 0.5),
    _spec("heritability", "Generation", "Heritability",
          "How strongly parents shape a generated child's disposition. 0 makes "
          "children independent of their parents.", 0.4),
    _spec("trait_variance", "Generation", "Personality spread",
          "How much generated personalities vary around their culture and role.",
          0.25, minimum=0.0, maximum=1.0),
    _spec("retention_variance", "Generation", "Memory spread",
          "How widely memory ability varies between people. 0 gives everyone the "
          "same memory.", 0.32, minimum=0.0, maximum=1.0),
]

BY_KEY: dict[str, dict] = {spec["key"]: spec for spec in TUNABLES}


def default(key: str) -> Any:
    spec = BY_KEY.get(key)
    return spec["default"] if spec else None


def coerce(key: str, raw: Any) -> Any:
    """Coerce and clamp a raw value into its spec's range.

    Clamping rather than rejecting: a GM dragging a slider past the end should
    get the extreme, not an error dialog.
    """
    spec = BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"Unknown tunable: {key!r}")
    if spec["type"] == "choice":
        # An unknown option falls back to the default rather than raising: a
        # tunable that can reject its own value is a tunable that can wedge a
        # campaign shut.
        text = str(raw).strip().lower()
        return text if text in (spec.get("choices") or ()) else spec["default"]
    if spec["type"] == "int":
        value = int(float(raw))
    elif spec["type"] == "bool":
        return str(raw).strip().lower() in ("1", "true", "on", "yes") if not isinstance(raw, bool) else raw
    else:
        value = float(raw)
    return max(spec["min"], min(spec["max"], value))


# --------------------------------------------------------------------------- #
#  Resolution
# --------------------------------------------------------------------------- #
class Tuning:
    """Resolved tunables for one campaign.

    Built once per command and passed down; the pure layer receives the typed
    views below rather than this object, so nothing in ``mind/`` ever performs a
    lookup.
    """

    def __init__(self, server: Optional[dict] = None, campaign: Optional[dict] = None):
        self._server = server or {}
        self._campaign = campaign or {}

    @classmethod
    def for_campaign(cls, guild_id: Optional[int], campaign=None) -> "Tuning":
        """Read the two override layers for a campaign."""
        from helpers.dnd import parameters as dnd_parameters

        server = dnd_parameters.tuning_overrides(guild_id)
        campaign_overrides = {}
        if campaign is not None:
            campaign_overrides = (campaign.settings or {}).get("tuning") or {}
        return cls(server, campaign_overrides)

    def get(self, key: str) -> Any:
        """Most specific wins: campaign, then server, then the built-in default."""
        for layer in (self._campaign, self._server):
            if key in layer:
                try:
                    return coerce(key, layer[key])
                except (KeyError, TypeError, ValueError):
                    continue
        return default(key)

    def source_of(self, key: str) -> str:
        """Which layer supplied the current value — shown in the panel so a GM
        can see whether they are looking at their own setting or inheriting one."""
        if key in self._campaign:
            return "campaign"
        if key in self._server:
            return "server"
        return "default"

    # ------------------------------------------------------------------ #
    #  Typed views for the pure layer
    # ------------------------------------------------------------------ #
    def memory(self) -> "MemoryTuning":
        return MemoryTuning(
            decay_rate=self.get("memory_decay_rate"),
            shape=self.get("memory_curve_shape"),
            salience_reach=self.get("memory_salience_reach"),
            retention_reach=self.get("memory_retention_reach"),
            alignment_reach=self.get("memory_alignment_reach"),
            confabulate_chance=self.get("memory_confabulate_chance"),
            confabulate_threshold=self.get("memory_confabulate_threshold"),
            imprint_threshold=self.get("imprint_threshold"),
            imprint_recalls=self.get("imprint_recalls"),
            budget_scale=self.get("memory_budget_scale"),
            stability={
                "gist": self.get("stability_gist"),
                "valence": self.get("stability_valence"),
                "participants": self.get("stability_participants"),
                "details": self.get("stability_details"),
                "when": self.get("stability_when"),
            },
        )

    def salience(self) -> "SalienceTuning":
        return SalienceTuning(
            emotional=self.get("salience_emotional"),
            relevance=self.get("salience_relevance"),
            novelty=self.get("salience_novelty"),
            social=self.get("salience_social"),
            reinforce=self.get("salience_reinforce"),
            value_weight=self.get("salience_value_weight"),
        )

    def needs(self) -> "NeedsTuning":
        return NeedsTuning(
            urgency_power=self.get("need_urgency_power"),
            impulse_threshold=self.get("need_impulse_threshold"),
            hours={
                "hunger": self.get("need_hours_hunger"),
                "thirst": self.get("need_hours_thirst"),
                "fatigue": self.get("need_hours_fatigue"),
            },
        )

    def relationships(self) -> "RelationshipTuning":
        return RelationshipTuning(
            scale=self.get("relationship_scale"),
            faction_prior=self.get("faction_prior"),
        )

    def continuity(self) -> "ContinuityTuning":
        return ContinuityTuning(
            mode=str(self.get("time_mode")),
            hours=self.get("tick_hours"),
            days=self.get("tick_days"),
        )

    def stakes(self) -> "StakesTuning":
        return StakesTuning(
            capacity_reach=self.get("stakes_capacity_reach"),
            need_reach=self.get("stakes_need_reach"),
            unknown_actor_floor=self.get("stakes_unknown_actor_floor"),
            witness_reach=self.get("stakes_witness_reach"),
            disposition_reach=self.get("stakes_disposition_reach"),
            familiarity_reach=self.get("stakes_familiarity_reach"),
            actor_echo=self.get("stakes_actor_echo"),
        )

    def generation(self) -> "GenerationTuning":
        return GenerationTuning(
            importance=self.get("npc_importance_default"),
            role_prior_weight=self.get("role_prior_weight"),
            culture_prior_weight=self.get("culture_prior_weight"),
            role_fit_sharpness=self.get("role_fit_sharpness"),
            heritability=self.get("heritability"),
            trait_variance=self.get("trait_variance"),
            retention_variance=self.get("retention_variance"),
        )

    def entries(self, *, scope: str = SCOPE_CAMPAIGN) -> list[dict]:
        """Specs plus current value and source, for the panel."""
        out = []
        for spec in TUNABLES:
            if scope == SCOPE_CAMPAIGN and spec["scope"] == SCOPE_SERVER:
                continue
            out.append({**spec, "value": self.get(spec["key"]),
                        "source": self.source_of(spec["key"])})
        return out


# --------------------------------------------------------------------------- #
#  Typed views — what the pure layer actually receives
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MemoryTuning:
    decay_rate: float = 1.0
    shape: float = memory_model.SHAPE
    salience_reach: float = 6.0
    retention_reach: float = 2.0
    alignment_reach: float = 1.0
    confabulate_chance: float = 0.5
    confabulate_threshold: float = memory_model.CONFABULATE_THRESHOLD
    imprint_threshold: float = memory_model.IMPRINT_THRESHOLD
    imprint_recalls: int = memory_model.IMPRINT_RECALLS
    budget_scale: float = 1.0
    stability: dict = field(default_factory=lambda: dict(memory_model.FIELD_STABILITY))

    @property
    def frozen(self) -> bool:
        """Whether forgetting is switched off entirely."""
        return self.decay_rate <= 0


@dataclass(frozen=True)
class SalienceTuning:
    emotional: float = 0.35
    relevance: float = 0.25
    novelty: float = 0.20
    social: float = 0.20
    reinforce: float = 0.15
    value_weight: float = 0.5


@dataclass(frozen=True)
class NeedsTuning:
    urgency_power: float = 3.0
    impulse_threshold: float = 0.55
    hours: dict = field(default_factory=lambda: {"hunger": 48, "thirst": 24, "fatigue": 20})


@dataclass(frozen=True)
class RelationshipTuning:
    scale: float = 1.0
    faction_prior: float = 0.6


@dataclass(frozen=True)
class ContinuityTuning:
    mode: str = "manual"
    hours: float = 6.0
    days: float = 1.0

    @property
    def automatic(self) -> bool:
        return self.mode == "automatic"

    @property
    def timeless(self) -> bool:
        """Nothing ages at all — not on a tick, not on a GM's command."""
        return self.mode == "timeless"


@dataclass(frozen=True)
class StakesTuning:
    capacity_reach: float = 1.0
    need_reach: float = 1.0
    unknown_actor_floor: float = 0.25
    witness_reach: float = 0.5
    disposition_reach: float = 0.7
    familiarity_reach: float = 0.35
    actor_echo: float = 0.3


@dataclass(frozen=True)
class GenerationTuning:
    importance: float = 0.5
    heritability: float = 0.4
    trait_variance: float = 0.25
    retention_variance: float = 0.32
    role_prior_weight: float = 0.5
    culture_prior_weight: float = 0.5
    role_fit_sharpness: float = 3.0


# Module-level defaults, so every pure function has something sensible to fall
# back on and can still be called from a test with no configuration at all.
DEFAULT_MEMORY = MemoryTuning()
DEFAULT_SALIENCE = SalienceTuning()
DEFAULT_NEEDS = NeedsTuning()
DEFAULT_RELATIONSHIPS = RelationshipTuning()
DEFAULT_STAKES = StakesTuning()
DEFAULT_GENERATION = GenerationTuning()
