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

**Traits change rarely.** Temperament shifts only when an imprint forms; drives
drift slowly with reinforced experience. An NPC whose personality moves every
session has no personality.

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
