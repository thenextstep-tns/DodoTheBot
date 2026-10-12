# Data Model

MongoDB, via the existing `pymongo` client. Collections are declared in
`config/database.py` alongside the others, prefixed `dnd_`.

**Scope rule (from `01-ARCHITECTURE.md` §7):** every document except the global
knowledge base carries `guild_id` *and* `campaign_id`. Reads go through
`store/repo.py`, which requires a scope and injects the filter.

---

## 1. Collections

```python
# --- Dodo Tabletop (docs/dnd/) ---
dnd_campaigns   = db["DndCampaigns"]    # {guild_id, name, ruleset, settings, gm_ids}
dnd_entities    = db["DndEntities"]     # PCs, NPCs, factions, creatures — one model
dnd_scenes      = db["DndScenes"]       # what is on screen right now
dnd_events      = db["DndEvents"]       # append-only log; the spine
dnd_knowledge   = db["DndKnowledge"]    # KB facts, all four tiers
dnd_memories    = db["DndMemories"]     # per-entity memory entries
dnd_beliefs     = db["DndBeliefs"]      # who believes what, from whom, how surely
dnd_relations   = db["DndRelations"]    # directed pair state
dnd_clocks      = db["DndClocks"]       # faction agendas / fronts
dnd_canon_queue = db["DndCanonQueue"]   # LLM inventions awaiting GM promotion
dnd_snapshots   = db["DndSnapshots"]    # log compaction checkpoints
dnd_budgets     = db["DndBudgets"]      # token / cost accounting per guild+campaign
dnd_rulesets    = db["DndRulesets"]     # ruleset definitions as data
```

Rationale for splitting memory/beliefs/relations out of the entity document
instead of embedding: they are **unbounded-ish and independently queried**.
Embedding them recreates the current cog's growing-`history` failure and risks the
16 MB document cap on a long campaign. Entities stay small and hot; memory is
paged in only for entities that are thinking.

---

## 2. Campaign

```jsonc
{
  "_id": ObjectId,
  "guild_id": 852793776064692264,
  "name": "The Ashen Compact",
  "ruleset": "srd5e",              // key into dnd_rulesets
  "status": "active",              // active | paused | archived
  "gm_ids": [123, 456],            // campaign admins (panel + GM commands)
  "player_ids": [789],
  "channel_id": 111,               // forum channel for scenes
  "world_time": 4820160,           // in-world minutes since campaign epoch
  "seq": 1843,                     // last event seq
  "seed": 918273645,               // campaign RNG root
  "settings": {
    "tone": "grim, wry, low-magic",
    "gm_style": "terse; lets silence sit; never narrates player feelings",
    "tick_minutes": 10,            // world minutes per tick
    "tick_real_seconds": 900,
    "autonomous_gm": false,
    "canon_auto_accept": 0.0,      // 0 = GM approves everything
    "npc_focus_cap": 8,
    "safety": { /* 11-SAFETY.md */ }
  },
  "created_at": ISODate, "updated_at": ISODate
}
```

## 3. Entity

One model for PCs, NPCs, factions and creatures. Components are optional
sub-documents — a faction simply has no `stats` or `needs`.

```jsonc
{
  "_id": ObjectId,
  "guild_id": 852793776064692264,
  "campaign_id": ObjectId,
  "kind": "npc",                   // pc | npc | creature | faction
  "tier": "active",                // focus | active | dormant  (01-ARCH §6)
  "owner_id": 789,                 // discord user id, for kind=pc
  "tier_changed_at": 4820160,      // world time, for dormant extrapolation

  "identity": {
    "name": "Marla Venn",
    "pronouns": "she/her",         // explicit; never inferred from the name
    "species": "human",
    "role": "harbourmaster",
    "appearance": "…", "voice": "clipped, never finishes a sentence"
  },

  "stats": {                        // SCHEMA COMES FROM THE RULESET
    "abilities": {"STR": 9, "DEX": 13, "CON": 11, "INT": 15, "WIS": 14, "CHA": 12},
    "hp": {"current": 22, "max": 22, "temp": 0},
    "ac": 12,
    "proficiency": 2,
    "skills": {"insight": 4, "deception": 3}
  },

  "traits": {                       // 04-ENTITIES.md §3
    "temperament": {"warmth": -0.2, "volatility": 0.6, "boldness": 0.3,
                    "diligence": 0.8, "openness": -0.1},
    "drives": {"greed": 0.5, "honour": 0.7, "curiosity": 0.2,
               "fear_of_death": 0.4, "belonging": 0.6},
    "flaws": ["cannot refuse a debt"],
    "bonds": [{"entity_id": ObjectId, "text": "her brother's ship"}],
    "ideals": ["the harbour comes first"]
  },

  "inheritance": {
    "parents": [ObjectId, ObjectId],
    "culture": "tidewater",
    "bloodline": null,
    "derived": true                 // traits were seeded from lineage
  },

  "needs": {                        // 0..1, 1 = desperate
    "hunger": 0.2, "thirst": 0.1, "fatigue": 0.55, "pain": 0.0,
    "warmth": 0.3, "safety": 0.1, "belonging": 0.4,
    "ticked_at": 4820160
  },

  "conditions": ["exhausted:1"],
  "inventory": [{"item": "harbour seal", "qty": 1, "tags": ["authority"]}],
  "position": {"location_id": ObjectId, "scene_id": ObjectId},

  "memory_budget": {"mid": 40, "long": 120, "imprint": 12},
  "importance": 0.7,                // drives budget + tier promotion

  "created_at": ISODate, "updated_at": ISODate
}
```

`stats` is deliberately schemaless at the DB layer — its shape is validated by
the **ruleset**, so `freeform` and `srd5e` characters coexist in one collection.

## 4. Memory entry

```jsonc
{
  "_id": ObjectId,
  "guild_id": …, "campaign_id": …,
  "entity_id": ObjectId,
  "tier": "long",                  // working | mid | long | imprint
  "encoded_at": 4818300,           // world time
  "last_recalled_at": 4819900,
  "recall_count": 3,

  "gist": "Marla was betrayed at the harbour",   // decays last
  "valence": -0.8,                                // −1..1
  "arousal": 0.9,
  "participants": [ObjectId],
  "location_id": ObjectId,
  "details": ["a green lantern", "rain"],
  "when": {"world_time": 4818300, "precision": "day"},

  "salience": 0.86,
  "fidelity": {                    // 1.0 = crisp, 0.0 = gone. Decays per field.
    "gist": 1.0, "valence": 0.95, "participants": 0.7,
    "details": 0.3, "when": 0.1
  },
  "confabulated": ["details"],     // fields replaced with plausible wrong values
  "source_event_seq": 1802,
  "cues": ["green lantern", "harbour", "rain"]   // recall triggers
}
```

Imprints are `tier: "imprint"` and are simply exempt from the decay pass.

## 5. Belief

The generalization of `cogs/chat.py`'s rumour system. **NPCs act on this, never
on world truth.**

```jsonc
{
  "_id": ObjectId,
  "guild_id": …, "campaign_id": …,
  "holder_id": ObjectId,           // who believes it
  "subject_id": ObjectId,          // who/what it is about
  "claim": "smuggled relics through the north dock",
  "confidence": 0.6,               // 0..1
  "source": {"kind": "told", "by": ObjectId, "at": 4819100},
                                   // witnessed | told | inferred | assumed
  "truth": false,                  // GM-visible only; the holder cannot see this
  "mutations": 2,                  // times it changed hands (rumour drift)
  "shared_with": [ObjectId]
}
```

## 6. Relationship

Directed — `A→B` is not `B→A`, which is most of the drama.

```jsonc
{
  "guild_id": …, "campaign_id": …,
  "from_id": ObjectId, "to_id": ObjectId,
  "affinity": 0.3,    // like ↔ dislike
  "trust": -0.4,      // rely ↔ suspect
  "fear": 0.7,
  "respect": 0.2,
  "debt": -2,         // negative = they owe you
  "familiarity": 0.8, // how well known
  "updated_at": 4820000
}
```

## 7. Event log & compaction

`dnd_events` follows `01-ARCHITECTURE.md` §3. It is the only append-only
collection and the only one that grows without bound, so:

- **Compaction** runs per arc. Events older than the current arc are replaced by
  a `dnd_snapshots` document (full projected state + state hash), retaining
  individually only events with `salience >= 0.7` or referenced by an imprint.
- Replay starts from the newest snapshot at or before the target `seq`.
- A campaign's full history stays exportable — snapshots plus retained events are
  the export bundle (`10-MONETIZATION.md` §5).

## 8. Indices

Applied at startup by `store/indices.py`, following the pattern the bot already
uses for its other collections.

```python
dnd_entities:   [("campaign_id", 1), ("tier", 1)]
                [("campaign_id", 1), ("kind", 1)]
                [("campaign_id", 1), ("owner_id", 1)]
dnd_events:     [("campaign_id", 1), ("seq", 1)]  unique=True   # optimistic concurrency
                [("campaign_id", 1), ("world_time", 1)]
dnd_memories:   [("entity_id", 1), ("tier", 1), ("salience", -1)]
                [("entity_id", 1), ("cues", 1)]
dnd_beliefs:    [("campaign_id", 1), ("holder_id", 1)]
                [("campaign_id", 1), ("subject_id", 1)]
dnd_relations:  [("campaign_id", 1), ("from_id", 1), ("to_id", 1)] unique=True
dnd_knowledge:  [("scope", 1), ("scope_id", 1), ("tags", 1)]
dnd_clocks:     [("campaign_id", 1), ("status", 1)]
dnd_canon_queue:[("campaign_id", 1), ("status", 1)]
```

The unique `(campaign_id, seq)` index is doing real work: it is the optimistic
concurrency control for the event log (`01-ARCHITECTURE.md` §8).

## 9. Sizing

Per active campaign, order of magnitude:

| Collection | Docs | Avg size | Total |
| --- | --- | --- | --- |
| entities | 200 | 2 KB | 400 KB |
| memories | 200 × ~60 | 400 B | ~5 MB |
| beliefs | ~800 | 250 B | 200 KB |
| relations | ~1500 | 150 B | 225 KB |
| events (post-compaction) | ~3000 | 400 B | 1.2 MB |

**~7 MB per campaign.** Atlas free tier (512 MB) holds ~70 campaigns; the memory
budget system (`05-MEMORY.md` §5) is what keeps this from growing without bound.
Storage caps per tier are in `10-MONETIZATION.md`.
