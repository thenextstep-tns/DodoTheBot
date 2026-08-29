# Knowledge Base

Four tiers of world knowledge, a retrieval budget instead of prompt-stuffing, and
a canon queue that stops the LLM from inventing the world out from under the GM.

---

## 1. Tiers

Resolved most-specific-first. Deliberately the same fallback shape as
`LangManager.get()` (`helpers/lang_manager.py`), so the codebase has one mental
model for layered config.

```
scene  →  campaign  →  server  →  global
```

| Tier | `scope` | Owner | Editable by | Contents |
| --- | --- | --- | --- | --- |
| `global` | — | Us | Bot owner | Rulesets, conditions, generic statblocks, behaviour archetypes, narrative primitives, name/culture tables |
| `server` | `guild_id` | Server admin | Panel `full` scope | House rules, default tone, content limits, shared setting |
| `campaign` | `campaign_id` | Campaign GM | Panel campaign-GM grant | Lore, factions, locations, NPCs, custom rules, GM style, arc plans |
| `scene` | `scene_id` | The engine | Written by the sim | Present entities, lighting, weather, time of day, active effects |

Global is the only unscoped, read-only-at-runtime collection.

## 2. Fact document

Knowledge is **chunked into facts**, not stored as prose blobs. A blob cannot be
retrieved selectively, which is how prompts get fat.

```jsonc
{
  "_id": ObjectId,
  "scope": "campaign",             // global | server | campaign | scene
  "scope_id": ObjectId,            // null for global
  "guild_id": …,                   // denormalized for the scope filter

  "kind": "lore",                  // lore | rule | location | faction | person
                                   // | item | custom | tone
  "title": "The Ashen Compact",
  "text": "Twelve houses swore to burn their own fleet before…",
  "tags": ["compact", "houses", "history", "ash"],
  "entities": [ObjectId],          // linked entities
  "weight": 0.8,                   // GM-set importance, biases retrieval
  "secret": true,                  // never surfaced to players, only to GM/sim
  "overrides": ObjectId,           // a lower-tier fact this replaces
  "source": "gm",                  // gm | import | llm_promoted | seed
  "created_at": …, "updated_at": …
}
```

`overrides` is what makes layering explicit: a campaign fact can *replace* a
global rule rather than merely sitting alongside it. Without it, "layered
knowledge" silently means "contradictory knowledge."

## 3. Retrieval

**Never stuff the whole KB into a prompt.** Each LLM task declares a token budget
and the retriever fills it by score.

```python
score = (
      0.35 * tag_overlap(fact, query_tags)
    + 0.25 * entity_overlap(fact, present_entities)
    + 0.15 * fact.weight
    + 0.15 * tier_bonus(fact.scope)      # scene 1.0 … global 0.25
    + 0.10 * recency(fact.updated_at)
)
```

Then: sort, take until the budget is spent, drop anything `secret` when rendering
for a player, and always force-include the campaign `tone` and `gm_style` facts.

**No embeddings at v1** — the deterministic-first rule applied to retrieval. Tag +
keyword + recency scoring runs in microseconds on one core and, unlike a vector
score, you can read why it ranked something first. If quality later demands it, a
384-dim MiniLM is ~90 MB and *would* run on the VPS (it is an encoder, not a
generator — nothing like the arithmetic in `08-LLM-LAYER.md` §2, and still local,
so Rule 1 holds). Keep the retriever behind an interface so that swap is additive.

Typical budgets: `render_scene` 1200 tokens, `render_dialogue` 800,
`parse_intent` 400 (fallback path only), `propose_canon` 1500 (bootstrap only).

## 4. Beliefs vs. facts

**Facts are what is true. Beliefs are what an entity thinks is true.** They are
different collections and must never be conflated.

- The **simulation** reads facts (`dnd_knowledge`) for world truth.
- **NPC decisions** read beliefs (`dnd_beliefs`), never facts.
- **Player-facing renders** read that character's beliefs, which gives fog of war
  for free.
- The GM panel shows both side by side — the "who's wrong about what" view, which
  is the single most fun page in the product.

### Belief kinds, and what time does to them

A belief carries a `source_kind` — how they came by it — but that says nothing
about *what sort of claim it is*, and the two decay in opposite directions. One
`kind` field, three values:

| Kind | Example | What time does |
| --- | --- | --- |
| `fact` | "the north dock floods at spring tide" | erodes slowly toward uncertainty |
| `rumour` | "Ondry works for the Compact" | erodes **fastest**; it was thin to begin with |
| `value` | "debts must be paid" | **does not erode** — hardens with reinforcement |

Without this, a rumour someone assumed once at confidence 0.35 is still held at
exactly 0.35 a decade later, which is not how anyone works: an unreinforced
suspicion about a stranger should soften into *"I had some idea about him once"*.
So `fact` and `rumour` take a confidence curve of the same shape memory uses
(`05-MEMORY.md` §4) — a power law, not a timer — with reinforcement resetting
the clock and contradiction collapsing it.

**Values invert it.** A value is not evidence about the world, it is a stance
toward it, and stances calcify. Every event consistent with a value raises its
confidence; time alone does nothing. This is what makes an NPC cheated once at
twenty still insistent about honesty at fifty.

Three fields carry it: `kind`, `reinforced_at`, and `reinforcement_count`.

**Values are the slow input to personality.** A value held for years and
repeatedly reinforced feeds the exposure ledger in `04-ENTITIES.md` §3a and
gradually pulls the trait axes it implies. That is the loop that closes the
system: events form memories, memories and repetition form beliefs, long-held
beliefs reshape the person, and the reshaped person appraises the next event
differently.

### Rumour propagation

Runs on the world tick, no LLM:

1. Pick pairs with `familiarity > threshold` who share a location.
2. The holder selects a belief to share, weighted by `confidence × arousal ×
   relevance-to-listener`.
3. The listener adopts it with `confidence' = confidence × trust(listener→holder)
   × decay(mutations)`.
4. With probability `p_mutate`, the claim **drifts** — a participant, place or
   magnitude is swapped. `mutations += 1`.
5. Both encode a memory of the telling.

Step 4 is the fun. It is also why the claim is stored as structured-ish text with
swappable slots rather than an opaque sentence.

## 5. The canon queue

**The mechanism that prevents world drift.** Anything the LLM invents — a name, a
tavern, a cousin, a rule interpretation — is written to `dnd_canon_queue`, never
to `dnd_knowledge`.

```jsonc
{
  "_id": ObjectId, "campaign_id": …, "guild_id": …,
  "status": "pending",             // pending | accepted | rejected | auto
  "kind": "person",
  "proposal": {"title": "Ondry the ferryman", "text": "…", "tags": [...]},
  "context": {"event_seq": 1841, "task": "render_dialogue"},
  "confidence": 0.7,               // model's own or heuristic
  "created_at": …, "resolved_by": 123, "resolved_at": …
}
```

Flow:

1. LLM output is scanned for **novel proper nouns and asserted facts** not present
   in retrieved knowledge.
2. Each becomes a queue entry. The prose still gets posted — the player sees it.
3. Until promoted, it is **soft canon**: retrievable at low weight for continuity
   within the arc, but not authoritative and not exported.
4. The GM promotes, edits or rejects from the panel — one click, batched.
5. `settings.canon_auto_accept` (0.0–1.0) lets a trusting GM auto-promote above a
   confidence threshold. Default `0.0`: the GM approves everything.

Soft canon is the compromise that makes this usable. Hard-rejecting inventions
mid-scene produces incoherent prose; accepting them all produces drift. Soft canon
keeps the scene coherent and defers the decision to someone with authority.

## 6. Session-zero bootstrap

A campaign KB must not require four hours of typing, or the product goes unused.

1. **Interview** — 8–12 questions on the panel: genre, tone, one-line premise,
   power level, magic, the party's tie to each other, three things that must be
   true, three that must never happen (feeds `11-SAFETY.md`).
2. **Generate** — one `propose_canon` batch produces ~30 draft facts: 5 locations,
   6 factions, 12 NPCs, 5 hooks, plus tone and gm_style facts.
3. **Approve** — everything lands in the canon queue as a reviewable list. The GM
   accepts, edits or rejects in a few minutes.
4. **Seed** — accepted facts become knowledge; NPC facts spawn entities with
   traits derived from culture (`04-ENTITIES.md` §4).

Also supported: **import** a bundle (`10-MONETIZATION.md` §5), or start empty and
write facts by hand. Bootstrap is a convenience, never a requirement — with
`backend=null` it degrades to a blank campaign plus templates.

## 7. Global KB seeding

Ships in `helpers/dnd/data/` as JSON, loaded to `dnd_knowledge` on first run and
versioned so upgrades re-seed cleanly.

- **Rulesets** — `freeform`, `srd5e` (SRD 5.1, **CC-BY-4.0**, attribution
  required in the docs and the panel footer).
- **Conditions** — blinded, charmed, frightened, grappled, … with mechanical
  effects as data.
- **Behaviour archetypes** — coward, zealot, merchant, predator, loyalist,
  opportunist: trait priors + action weights (`06-DECISION-ENGINE.md` §4).
- **Name & culture tables** — for generation, per culture.
- **Narrative primitives** — beat definitions (`07-NARRATIVE-ENGINE.md` §3).

**Legal:** SRD 5.1 content is CC-BY-4.0 and safe to redistribute with attribution.
Do **not** ship statblocks, adventures, or setting material from published books.
Any third-party ruleset must be user-supplied, and the import path must say so.
