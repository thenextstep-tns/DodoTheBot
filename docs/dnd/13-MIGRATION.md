# Migration from `cogs/dnd.py`

There is live data in the `dodo_dnd` database. It is small and shallow, but it is
somebody's game and it does not get thrown away.

---

## 1. What exists

A separate logical database on the shared client:

```python
_db = config_py.client["dodo_dnd"]
sessions_collection   = _db["sessions"]
characters_collection = _db["characters"]
actions_collection    = _db["actions"]
```

| Old | Shape | Maps to |
| --- | --- | --- |
| `sessions` | `{session_id, title, description, players[], combat, history, message_id, status}` | One **campaign** + one closed **scene** |
| `characters` | `{player_id, session_id, name, class, race, stats, hp, ac, equipment, relationships, history}` | One **entity** (`kind: pc`) |
| `actions` | `{session_id, player_id, action_description, gm_narrative, summary, timestamp}` | **Events** + seed **memories** |

Notes that shape the mapping:

- **No `guild_id` anywhere.** Sessions were created in DMs and posted to one
  global `DND_FORUM_CHANNEL_ID`. Guild has to be inferred or asked for.
- **`stats` is the same hardcoded block on every character** — `STR 15, DEX 14,
  CON 13, INT 12, WIS 10, CHA 8`, HP 10, AC 10. It carries no information, so
  importing it as real stats would be importing a lie.
- **`relationships` is always `{}`.** Written on creation, never read.
- **`history` is an append-only LLM-written bullet string**, unbounded.

## 2. Mapping

### Session → campaign + scene

```python
campaign = {
    "guild_id": resolved_guild_id,          # §3
    "name": session["title"],
    "ruleset": "freeform",                  # the old data has no real mechanics
    "status": "archived" if session["status"] == "completed" else "active",
    "gm_ids": [session_creator_id],         # §3
    "player_ids": session["players"],
    "world_time": 0,
    "seed": derive_seed(session["session_id"]),
    "settings": {**DEFAULTS, "tone": "", "gm_style": ""},
}
```

`session["description"]` becomes a **campaign knowledge fact**
(`kind: "lore"`, `title: "Premise"`, `weight: 0.9`) — it is the only real
worldbuilding in the old schema and it should be retrievable, not decorative.

The old forum message becomes one **closed scene** so the thread stays linked.

### Character → entity

```python
entity = {
    "kind": "pc", "owner_id": char["player_id"],
    "identity": {
        "name": char["name"],
        "pronouns": "they/them",            # never inferred from a name; §4
        "species": char["race"],
        "role": char["class"],
    },
    "stats": freeform.blank_sheet({"class": char["class"], "race": char["race"]}),
    "traits": derive_traits(parents=None, culture=None, rng=seeded(char)),
    "importance": 1.0,
    "inventory": [{"item": e, "qty": 1} for e in char.get("equipment", [])],
}
```

**The old `stats` block is deliberately dropped.** It was identical for every
character ever created, so preserving it would import noise as signal. Instead the
freeform ruleset generates a real sheet from class and race, and the migration
report says plainly that this happened.

`relationships: {}` is dropped — there is nothing in it.

### Actions → events + seed memories

Each action becomes a `WorldEvent` (`kind: "legacy_action"`) carrying the original
text and narrative, so nothing is lost and the log reads in order.

The `history` strings are **not** parsed into structured memory — they are
LLM-written prose with no reliable structure, and inventing structure from them
would fabricate a past that never happened. Instead:

- `session["history"]` → one campaign knowledge fact, `title: "Previous
  chapters"`, `weight: 0.7`. Retrievable as lore, which is what it actually is.
- `character["history"]` → **one seed memory per character**, `tier: "long"`,
  `salience: 0.6`, gist = the first ~200 characters, fidelity degraded to reflect
  that it is a summary of a summary.

That is the honest import: the old system's memory was a prose blob, so it becomes
a prose blob in the right place rather than pretending to be episodic memory.

## 3. The unknowns

Two fields cannot be derived and must be asked for:

- **`guild_id`** — not stored. Resolution order: look up `message_id` in the
  forum channel and read its guild; else ask the bot owner during migration; else
  park the campaign in a `needs_guild` state, visible on the owner panel.
- **GM identity** — `sessions` records no creator. Resolution: the author of the
  forum message if fetchable, else the owner assigns it.

The migration is **interactive and owner-run**, not an automatic startup hook. It
prints a plan, asks about the unknowns, and only then writes.

## 4. Pronouns

Old characters have no pronoun field. The importer sets `they/them` and does not
guess from names — a wrong guess misgenders someone's character, and the player
can set it in one click afterward. The migration report lists every character with
defaulted pronouns so players can be prompted.

## 5. Procedure

```
/owner dnd_migrate --dry-run     # prints the full plan, writes nothing
/owner dnd_migrate --guild <id>  # executes for one guild's sessions
/owner dnd_migrate --report      # what was imported, dropped, defaulted
```

1. **Dry run first**, always. It reports counts, unknowns, and every field being
   dropped with the reason.
2. Writes go to the new `dnd_*` collections in the main database. **The old
   `dodo_dnd` database is never modified or deleted** — it is the rollback.
3. Idempotent: re-running skips already-imported records by `legacy_id`.
4. The report is saved to the owner panel, not just printed to a console.

## 6. Cutover

1. New module ships as cog `dnd`; the old one is renamed to `dnd_legacy` and
   marked owner-only in `visibility`.
2. Both loadable for **one release**, so a group mid-session is not interrupted.
3. Legacy `DND_*` lang keys are kept until `dnd_legacy` is removed — the panel's
   lang editor would otherwise show broken keys.
4. `helpers/cog_categories.py`: `dnd` moves out of the `ai` category into its own
   (`09-SURFACES.md` §8).
5. After one release: delete `cogs/dnd.py`, drop the legacy lang keys, and archive
   the `dodo_dnd` database (dump to disk first, then drop).

## 7. What is explicitly not preserved

Stated up front so it is a decision, not a discovery:

| Dropped | Why |
| --- | --- |
| Hardcoded `stats` block | Identical for every character; carries no information |
| `relationships: {}` | Always empty |
| `combat.initiative_order` | Hand-typed numbers with no live encounter to belong to |
| Structured memory from `history` | Would fabricate a past; imported as lore instead |
| `actions_collection` counts in `/save_stats` | Recomputable from the event log |
