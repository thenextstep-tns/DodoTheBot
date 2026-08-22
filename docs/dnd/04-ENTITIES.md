# Entities, Sheets & Rulesets

One model for PCs, NPCs, creatures and factions. The differences are which
components are attached — not which class was instantiated.

---

## 1. Why one model

An NPC has to be as real as a PC, or the "intricate roleplay" requirement is
cosmetic. Two models guarantees drift: the PC path grows features the NPC path
never gets, and NPCs stay puppets.

So: `Entity` + optional components. A faction is an entity with `traits`,
`relationships` and an agenda but no `stats`, `needs` or `position`. A goblin is
an entity with `stats` and thin everything else. A questgiver has all of it.

```python
@dataclass
class Entity:
    id: ObjectId
    kind: Literal["pc", "npc", "creature", "faction"]
    tier: Literal["focus", "active", "dormant"]
    identity: Identity
    stats: dict | None            # shape owned by the ruleset
    traits: Traits | None
    inheritance: Inheritance | None
    needs: Needs | None
    conditions: list[str]
    inventory: list[Item]
    position: Position | None
    importance: float             # 0..1 — drives memory budget and tier promotion
```

`relationships`, `beliefs` and `memory` live in their own collections
(`02-DATA-MODEL.md` §1) and are loaded on demand — entities stay small and hot.

## 2. Rulesets as data

**Never hardcode 5e.** The current cog hardcodes one stat array for every
character ever created; that is the mistake.

A ruleset is a declaration plus a small resolver:

```python
class Ruleset(Protocol):
    key: str
    label: str
    def stat_schema(self) -> dict: ...                          # validates entity.stats
    def blank_sheet(self, concept: dict, rng: Random) -> dict: ...
    def derive(self, stats: dict) -> dict: ...                  # modifiers, DCs, saves
    def approaches(self, stats: dict) -> list[str]: ...         # for command choices
    def resolve(self, action: Action, actor_stats: dict,
                target_stats: dict | None, rng: Random) -> Outcome: ...
    def sheet_fields(self, stats: dict) -> list[tuple[str, str]]: ...
```

**Rulesets take stat dictionaries, not entities.** `rules/` sits *below* `world/`
in the layering (`01-ARCHITECTURE.md` §1), so importing the entity model here
would invert it and make a third ruleset impossible to add without touching the
world. `blank_sheet` also takes the RNG explicitly, because character generation
is part of what a replay has to reproduce.

`affordances` — what a scene physically permits — arrives with the scene model in
P1; it needs a `Scene` to be worth defining.

Two implementations, built in parallel so the abstraction cannot quietly collapse
into one (this was the owner's explicit choice):

### `freeform`
Narrative resolution. Stats are four approaches — force, finesse, wits, presence
— rated −1…+3 from a one-strong/one-weak spread, assigned by keyword-matching the
character concept so a "sly archivist" and a "stubborn dockhand" differ.

Resolution is a 2d6 ladder against a default DC of 7: `≤6` fail, `7–9` cost,
`10–11` success, `12+` triumph. 2d6 rather than a single die because the bell
curve puts most rolls in the middle bands, which is where the interesting result
lives — **cost**, the *yes, but* that generates story on its own and gives the
simulation something to react to.

**Reaches playable first** — it exists to get the minds on screen without a
rules-engine dependency.

### `srd5e`
SRD 5.1 (CC-BY-4.0). Six abilities, proficiency, AC, HP, saves, skills,
advantage/disadvantage, conditions, the standard action economy. Data-driven from
the global KB. **Fills in behind freeform**; it exists to prove the abstraction is
real.

The pair is the test: if adding a third ruleset requires touching anything outside
`rules/`, the abstraction failed.

## 3. Traits — personal qualities

Numeric axes, not tags, because the decision engine multiplies them
(`06-DECISION-ENGINE.md` §4). Range −1…1 unless noted.

```python
@dataclass
class Traits:
    # Temperament — stable, changes only through imprints
    warmth: float        # cruel ↔ kind
    volatility: float    # steady ↔ explosive
    boldness: float      # timid ↔ reckless
    diligence: float     # feckless ↔ dogged
    openness: float      # rigid ↔ curious

    # Drives — 0..1, what they *want*; shift slowly with experience
    greed: float
    honour: float
    curiosity: float
    fear_of_death: float
    belonging: float

    flaws: list[str]     # narrative; can be triggered by cues
    bonds: list[Bond]    # entity + text; strong utility weights
    ideals: list[str]
```

Plus one **faculty**, kept separate from both: `retention`, how well this mind
holds on to things. It is not a disposition — it describes what the mind is
*capable* of rather than what it wants, so it never feeds the utility scorer the
way drives do. It multiplies memory stability directly (`05-MEMORY.md`).

Five temperament axes and five drives is a deliberate ceiling: enough for
distinct-feeling NPCs, few enough that a GM can read a sheet and predict
behaviour. More axes make the utility weights unreadable and the NPCs mushier,
not richer.

**Traits change rarely.** An NPC whose personality moves every session has no
personality. But one that never moves is furniture, and the difference between
those two is the whole of §3a.

### 3a-pre. Priors are read backwards, not forwards

A role prior applied at birth is a stereotype: *he is a thief, so here is the
pattern for the class.* A world built that way contains one thief, printed as
many times as you need. So the same table is used in **both directions**, and
the default direction is the reverse one:

| Direction | Question | Effect |
| --- | --- | --- |
| Forwards (`derive_traits`) | "what does a thief look like?" | stamps a disposition. Weighted by `role_prior_weight`; **0 disables it** |
| Backwards (`fit`) | "how thief-shaped is this person?" | only *notices*. Never flattens anyone |

**Bottom-up is the real generator.** `suggest_role` rolls a person first and
asks what someone like that would have become, weighted by fit. Across a
population the trades sort themselves and the stereotype emerges as a
distribution rather than a rule — measured over 400 people with the priors
switched **off entirely**, thieves come out at mean honour 0.35 and priests at
0.64, purely from who fell into what. Individuals still span the range, so the
honest thief exists and is interesting when he does.

`fit` also gives the GM a line worth reading — *"an odd fit for guard work"*,
*"has no business being a priest"* — which is how an emergent oddity gets
noticed instead of sitting unseen in a stat block.

**Both modes are supported on purpose.** Top-down populates a world fast and is
the right tool for testing a specific behaviour or running a short campaign;
bottom-up is for building one that has people in it. `role_prior_weight` and
`culture_prior_weight` slide between them, per server and per campaign.

*(The prior tables themselves are still Python. `04-ENTITIES.md` §9 step 1 says
culture and role should come from the campaign KB, and moving them there — so a
GM can add, edit and delete trades and cultures — is outstanding.)*

### 3a. Drift — a life changes a person, slowly

A boy raised rich and adored comes out gentle, capricious, and reasonably afraid
of dying. Send him to one war and he is the same boy with a bad memory. Send him
to six and he should not be that person any more: warmth worn down, fear of
death worn down, honour built up. Nothing in that sentence happens in a moment,
and that is the design constraint — **drift is an accumulation, never an
event.** No single battle moves an axis enough to notice. Forty do.

**Three layers, and conflating them is the mistake to avoid.**

| Layer | Lifespan | Written to the entity? |
| --- | --- | --- |
| **Baseline** | rolled at creation from culture and inheritance (§4) | once |
| **Drift** | permanent, accumulated over a life | **yes — slowly** |
| **Modulation** | hours to days: deprivation, mood, fear in the room (§5a) | **never** |

§5a's deprivation modulation is explicitly *not* a write, because a starving man
is not a crueller man — he is a man who is starving, and he is himself again
when he eats. Drift is the opposite: it is the part that does not lift.

**What accumulates.** An **exposure ledger** per trait axis, fed from three
sources that already exist:

- **Events** — what keeps happening to them and around them. Witnessing death
  pushes `warmth` down and `fear_of_death` down; being protected pushes
  `belonging` up.
- **Imprints** — the formative memories of `05-MEMORY.md`. These push hardest,
  which is what "temperament shifts when an imprint forms" was reaching for, and
  they push *once* and permanently.
- **Long-held beliefs** — a belief carried for years, reinforced and never
  contradicted, pulls the axes it implies. Someone who has believed for a decade
  that debts must be paid ends up with the `honour` to match. Belief age is the
  input, so this needs the belief lifecycle that `03-KNOWLEDGE-BASE.md` does not
  yet specify.

Drift applies when an accumulator crosses a threshold: the baseline moves one
small step, the accumulator drains, and the entity keeps living. Thresholds
rather than continuous integration, so an axis moves in legible increments a GM
can be told about rather than sliding invisibly.

**Four properties it has to have:**

1. **Bounded.** An axis may drift at most `drift_ceiling` from its birth value.
   Nobody becomes an entirely different person; the wealthy boy who has seen too
   much is recognisably him, ruined. Without a cap, long-running campaigns
   converge every NPC on the same weathered average.
2. **Asymmetric.** Warmth is lost faster than it is regained. Fear of death,
   once burned out, comes back slowly if at all. Each axis carries its own
   erosion and recovery rates because that is how people work.
3. **Plastic by life stage.** The young shift faster. A `plasticity` faculty
   alongside `retention`, high in youth and falling with age, multiplies the
   whole system. This is why the example is a *boy* sent to war and not a
   forty-year-old sergeant, and the difference should be visible in the numbers.
4. **Explainable.** The ledger is readable, like a decision trace. A GM asking
   *why is he not the boy he was* gets **"warmth −0.31 over eleven years: 40
   deaths witnessed, 2 imprints, the belief that nobody is coming"** — not a
   changed number with no story attached.

**Closed form for dormant entities.** Like needs (§5) and unlike anything that
requires per-tick iteration, drift must be extrapolatable in one step from
elapsed time and an exposure rate (`01-ARCHITECTURE.md` §6). An NPC nobody has
looked at for two in-world years is aged in a single calculation when they are
next observed, and must land where ticking would have put them.

**PCs accumulate but do not drift silently.** A player character's ledger fills
the same way, but crossing a threshold **proposes** the change rather than
applying it — surfaced to the player and the GM. Automating decisions for a PC
is already forbidden (`12-ROADMAP.md`, open question 2); quietly rewriting who
their character *is* would be worse.

### 3b. Rupture — when the ceiling is the wrong answer

`drift_ceiling` above exists so nobody becomes someone else. But a cap that
*never* breaks makes the extreme cases impossible, and the extreme cases are
real: someone tortured for months does not come back as themselves with slightly
lower warmth. They come back broken in one specific place. **Where there is a
guardrail there is a case that has to break it**, and the mechanic belongs in the
design rather than being discovered as a limitation later.

**Rupture is to traits what an imprint is to memory** — the rare, permanent,
disproportionate one. The symmetry is deliberate: same idea, one layer up.

Four conditions, all required, because this must be almost unreachable:

1. **Sustained, not singular.** A ledger's exposure must stay past an extreme
   threshold across a long span. One catastrophic night forms an imprint; it
   does not rupture. Months do.
2. **Narrow.** It moves **one** axis, chosen by what the exposure actually was,
   past the ceiling. "Changed completely in some specific aspect" — not a new
   personality, a person with something taken out of them. A blanket collapse of
   every axis is the failure mode to avoid; that produces a husk, not a
   character.
3. **Marked.** The entity carries the rupture as a record — what broke, when,
   and the exposure that did it — so it renders in the inspector as a fact about
   them rather than a number that quietly went out of range. It is also what
   `flaws` were always for (§3).
4. **Scarred, not healed.** Recovery is far slower than ordinary drift and never
   returns the axis to its birth value. The ceiling that was broken stays
   broken; the axis simply moves within a range that no longer includes who they
   used to be.

**This mechanic is gated by `11-SAFETY.md`, not merely tunable by it.** Torture
is already a default *line* for a fresh campaign, and lines are enforced by
making matching actions unproposable by the decision engine (§3 of that file).
So rupture-grade exposure cannot be generated by the simulation at a table that
has not opted in; a GM can still author it directly, which is the right division
— the machinery models consequence, the table decides what is on screen. Default
`rupture_enabled: false`, and turning it on should say plainly what it enables.

Tunables, per the standing rule, each able to go to zero:
`drift_enabled` (default **on** — this is a core mechanic, not a garnish),
`drift_rate`, `drift_ceiling`, `drift_plasticity_reach`, and per-source weights
for events, imprints and beliefs. Setting `drift_rate: 0` gives fixed
personalities and the pre-drift behaviour exactly. Rupture adds
`rupture_enabled` (default **off**), `rupture_threshold`, `rupture_duration` —
how long exposure must be sustained — and `rupture_recovery_rate`.

## 4. Inheritance — inherited qualities

Traits are partly derived from lineage plus culture, with variance. This makes
generated NPCs *coherent* rather than random, and hands you family and dynasty
stories at no extra cost.

```python
def derive_traits(parents, culture, rng) -> Traits:
    # 1. Culture supplies the prior (from the global KB culture table)
    base = culture.trait_prior                    # e.g. tidewater: +diligence, −openness
    # 2. Parents pull toward their midpoint
    if parents:
        base = lerp(base, mean(p.traits for p in parents), HERITABILITY)  # ~0.4
    # 3. Variance so siblings differ
    return jitter(base, sigma=0.25, rng=rng)
```

Heritability at ~0.4 is the number to tune: high enough that "she has her
mother's temper" reads as true, low enough that children are not clones. Recorded
in `inheritance.derived` so a GM can tell which NPCs were generated.

Also carried: culture (→ naming tables, default beliefs, faction priors) and
optional bloodline (→ mechanical traits per ruleset).

## 5. Needs — physiological

Only for `kind in (pc, npc, creature)`, only ticked for `focus`/`active` tiers,
extrapolated in closed form for `dormant` (`01-ARCHITECTURE.md` §6).

`hunger · thirst · fatigue · pain · warmth · safety · belonging`, each 0…1 where
1 is desperate.

```python
need += rate * elapsed_minutes            # rate from species/condition
need = clamp(need, 0, 1)
```

Needs feed the decision engine through **non-linear urgency**:

```python
urgency = need ** 3        # ignorable until it isn't
```

The cube is the whole trick. Linear needs produce NPCs who constantly fidget
about being slightly peckish; cubed, hunger is invisible at 0.4 and dominates at
0.9. That is how needs feel real without being annoying.

Unmet needs above threshold also generate **impulses** (`05-MEMORY.md` §6).

### 5a. Deprivation changes the person, not just the choice

Urgency alone only makes a hungry NPC *pick eating*. That is a vending machine
with a personality attached. Deprivation has to reach three further places, or
needs stay a number on an inspector page:

**Mood — the appraisal shift.** Sustained deprivation modulates the traits that
`06-DECISION-ENGINE.md` §4 appraises with: volatility up, warmth down, patience
down, and risk tolerance *up* — desperate people take chances a fed version of
themselves would not. This is a **temporary modulation applied at the
orchestration edge**, never a write to the stored trait. Traits are who someone
is and are stable (§4); this is what a bad week does to them, and it lifts when
they eat. `mind/needs.py` returns the modifier; `minds.py` composes it with the
base traits before handing an `EntityView` to the engine.

**Stats — ruleset conditions.** Crossing a deprivation threshold applies a
mechanical penalty *through the ruleset*, never directly: `freeform` adds to the
harm track (which already subtracts from everything you attempt), `srd5e` adds
levels of exhaustion. The engine says "this entity is at severity 3"; the
ruleset decides what that costs.

**Catastrophe — optional, and off by default.** With `need_lethal` enabled,
sustained maximum deprivation escalates on a per-need clock rather than all at
once: *impaired → incapacitated → dying → dead*. Thirst runs fastest, then
exhaustion, then hunger, with warmth conditional on climate. Death emits a
`WorldEvent` like anything else, so witnesses encode it, relationships shift and
rumours propagate — an NPC starving in a siege is a story beat the world already
knows how to carry.

**The interlock that matters:** lethality must stay off until the decision
engine can actually *satisfy* a need. At P2 nothing can eat, so needs peg at
1.00 within a day and stay there — turning this on would empty the world in a
week for no narrative reason. Ship the switch defaulted off, and gate the panel
control behind a warning that says exactly this.

Tunables, all layered default → server → campaign like everything else, and each
able to go to zero:

| Key | Does | Off means |
| --- | --- | --- |
| `need_mood_reach` | how far deprivation bends disposition | needs never colour mood |
| `need_condition_reach` | how hard thresholds hit the ruleset track | no mechanical penalty |
| `need_lethal` | whether deprivation can kill (**default off**) | NPCs suffer but never die |
| `need_days_to_death_{thirst,hunger,cold}` | the per-need clock once dying starts | — |
| `need_recovery_rate` | how fast satisfaction unwinds the above | — |

A campaign that wants none of this sets `need_mood_reach` and
`need_condition_reach` to 0 and leaves `need_lethal` off; needs then do nothing
but rank actions, which is the P2 behaviour preserved exactly.

## 6. Beliefs — what this entity thinks is true

Stored per entity in `dnd_beliefs` (`02-DATA-MODEL.md` §5), covered in
`03-KNOWLEDGE-BASE.md` §4. The rule that matters here:

> **NPC decisions read beliefs. Never world truth.**

Enforced by the decision engine receiving an `EntityView` — a projection built
from that entity's beliefs, memories and perception — rather than the world state.
`decide()` cannot see the world even if it wanted to, because it is never passed
it. Type-level enforcement of the fun.

## 7. Relationships

Directed and multi-axis (`02-DATA-MODEL.md` §6): `affinity`, `trust`, `fear`,
`respect`, `debt`, `familiarity`. `A→B ≠ B→A`, which is most of the drama.

Updated **only** from events, never by an LLM:

```python
DELTAS = {
    "helped":     {"affinity": +0.15, "trust": +0.10, "debt": -1},
    "betrayed":   {"affinity": -0.50, "trust": -0.70, "fear": +0.20},
    "threatened": {"fear": +0.30, "respect": +0.10, "affinity": -0.20},
    "gifted":     {"affinity": +0.10, "debt": -1},
    ...
}
```

Magnitude scales with the witness's `arousal` at encoding and their traits (a
high-`honour` NPC weights `debt` far more heavily).

### Stakes — the same act is not the same event

Deltas above are what an act is worth *in the abstract*. What it is worth to a
given person is `mind/stakes.py`, and without it a relationship system says a
paid debt is a paid debt:

> A merchant lord settles a stranger's debt with a wave of a finger. It costs him
> nothing he notices and he never learns the man's name. For the debtor it is the
> day his life did not end, and he tells everyone. The lord's reputation is built
> on an afternoon he has already forgotten — which is why nobody believes it
> later when he turns out to be selling people's organs.

Each party's **stake** scales both how far their relationship moves and how
firmly they remember, and a stake beneath noticing forms **no memory at all**.
Three inputs:

- **Capacity** — how insulated they are. Standing (`importance`) sets the
  ceiling; **disposition decides how much of it applies.** A warm, honourable
  lord notices what his household does for him; a cold one of identical rank
  does not. Deriving insulation from rank alone would hardcode *"the powerful
  never care"*, which is a cliché, not a rule.
- **Need pressure** — what it relieved. Bread means more to the starving.
  Deliberately *not* folded into capacity: being thirsty this afternoon should
  not lower a man's station, and with nothing yet able to satisfy a need (§5a)
  it would collapse every capacity in the world to zero.
- **Awareness, per direction and never assumed mutual.** You can do someone a
  kindness they never trace to you; you can come to admire someone who has no
  idea you exist. **Familiarity is therefore not symmetric** — it moves for
  whoever actually perceived the other.

Witnesses take a share of the same event (`stakes_witness_reach`), which is how
a reputation reaches people it never happened to.

Every part is tunable to zero: `stakes_capacity_reach: 0` makes every event
worth the same to everyone, `stakes_disposition_reach: 0` lets station alone
decide.

**Faction standing propagates as a prior**, not as a fact: a member of a hostile
faction *starts* at that standing, and their own traits and memories move them
off it. That is how you get the sympathetic enemy soldier without scripting one.

## 8. Sheets

The sheet is a **render of the entity**, per ruleset, per audience:

| Audience | Sees |
| --- | --- |
| Player (own PC) | Stats, inventory, conditions, **their character's beliefs**, their own memories, known relationships |
| Player (other PC) | Public identity only |
| GM | Everything, plus truth-vs-belief diff, memory inspector, decision trace |
| Sim | The `EntityView` (§6) |

Discord surfaces it as an ephemeral embed with buttons; the panel renders the full
version (`09-SURFACES.md`).

## 9. NPC generation

1. Pick culture and role (from campaign KB, or GM-specified).
2. Derive traits from culture + optional parents (§4).
3. Roll stats via `ruleset.blank_sheet(concept)`.
4. Seed beliefs from culture defaults + faction membership + local knowledge.
5. Seed 1–3 memories, one of which may be an **imprint** — this is what makes a
   fresh NPC feel like they have a past on first contact.
6. Set `importance` from role, which sets the memory budget (`05-MEMORY.md` §5).
7. Optionally, one `propose_canon` call for name, appearance and a voice quirk;
   with `backend=null`, name tables and templates cover it.

Step 5 is what separates this from every generator that produces a statblock with
a name attached.
