# Surfaces — Discord & Web Panel

Two front ends over one engine. Discord is where you *play*; the panel is where
you *build and inspect*.

---

## 1. Design rule

**Play needs one tap. Building needs a real screen.**

Anything a player does mid-scene must be a button or a short command — never a
form. Anything a GM does between sessions (lore, NPCs, canon, tuning) belongs on
the panel, where there is room. The current cog gets this backwards: it puts
character creation behind a three-field modal and offers no panel at all.

## 2. Discord: play surface

### Scenes are forum threads

A scene opens a thread in the campaign's forum channel. The thread *is* the scene:
narration posts into it, the pinned first message is the live scene card
(location, present entities, time, weather, conditions), edited in place as state
changes.

Async-first (the chosen default) means the thread stays open for days and players
drop in when free.

### The action bar

Pinned to the scene card, always available:

```
[ Act ]  [ Say ]  [ Look ]  [ Sheet ]  [ Roll ]
```

- **Act** — modal, one field, free text → `parse_intent`. Ambiguity comes back as
  an ephemeral disambiguation with buttons, never a wrong guess.
- **Say** — modal, one field. Dialogue is separated from action because NPCs
  respond to *speech* differently than to deeds.
- **Look** — ephemeral: the scene as **your character believes it to be**. Fog of
  war falls straight out of per-entity beliefs (`03-KNOWLEDGE-BASE.md` §4).
- **Sheet** — ephemeral sheet with tabs: stats, inventory, *what I know*, *who I
  know*, *what I remember*.
- **Roll** — dice, and unlike today's cog it is **wired into resolution**: a roll
  requested by the engine is claimed by the button and feeds the outcome.

### Commands

```
/dnd campaign create|list|join|leave
/dnd character create|sheet|retire
/dnd scene open|close|recap
/dnd act <text>          # for people who prefer typing
/dnd roll <expr>
/gm suggest              # narrative proposals (07-NARRATIVE-ENGINE.md §6)
/gm npc spawn|inspect|tier
/gm canon                # pending canon queue, inline approve
/gm undo                 # event-log rewind
/gm scene set <field>
```

Registered through the existing visibility system so a server can hide GM commands
from players. All strings via `bot.lang` (new `DND_*` keys replacing the 21 that
exist).

### What players see

**Only their own character's beliefs and memories.** Not world truth, not other
PCs' sheets, not `secret` knowledge. This is the fog-of-war payoff and it is free.

### Notifications

Async play means the world moves while you are away. On return, a personal digest:
what happened in your scenes, what your character heard, which clocks advanced
visibly. Opt-in, rate-limited, and mindful that nobody wants a bot DM every hour.

## 3. Web panel: GM surface

A new module, `web/dnd/`, mounted from `create_app`. **Not appended to
`web/routes.py`** — that file is already 3281 lines and adding a subsystem to it
would be the last straw. Same server-rendered HTML-string style as the existing
pages so it looks native.

Pages, per campaign:

| Page | Contents |
| --- | --- |
| **Overview** | Status, players, world time, active clocks, recent events |
| **Knowledge** | The campaign KB: lore, factions, locations, rules. Tag-filtered, tier-aware, showing what each fact overrides |
| **Canon queue** | Pending LLM inventions — approve / edit / reject, batched |
| **Entities** | All PCs/NPCs/factions; filter by tier, importance, faction |
| **Entity inspector** | The crown jewel — see §5 |
| **Clocks** | Faction agendas, drag to adjust, see what blocks them |
| **Narrative** | Drama state, threads, spotlight balance, beat history, live suggestions |
| **Settings** | Tone, GM style, ruleset, tick rate, autonomous mode, safety |
| **Load** | Render calls used vs. cap, queue wait p95, fallback rate, inference-host reachability |
| **Import/Export** | Campaign bundle in and out |

## 4. Access control — the gap in the current system

`helpers/panel_access.py` scopes are **per guild**: `none < stats < config < full
< owner`. A campaign GM is *not* a server admin — they need full control of their
campaign and none of the server.

So: a **campaign-scoped grant**, additive to the existing model.

```jsonc
// dnd_campaigns.gm_ids  →  resolved into a campaign scope
{"campaign_id": ObjectId, "user_id": 123, "role": "gm"}   // gm | co_gm | player
```

Resolution:

```python
def campaign_scope(user_id, campaign) -> str:
    if panel_access.scope_for_member(guild_id, member) >= FULL:  return "gm"
    if user_id in campaign.gm_ids:                                return "gm"
    if user_id in campaign.player_ids:                            return "player"
    return "none"
```

Deliberately kept **out** of `PanelAccessManager`: that class answers "how much of
this *server* do you see", and overloading it with per-object ownership would make
both questions harder to reason about. `web/dnd/` gets its own small resolver that
*consults* it.

Campaign edits are audited into `config_audit` like every other panel change.

## 5. The entity inspector

The page that sells the product. For one entity:

- **Sheet** — stats, conditions, inventory
- **Traits** — temperament and drive axes as bars, with what each is doing to
  their decisions right now
- **Needs** — live values with urgency curves
- **Memory** — every tier, sorted by salience, **fidelity bars per field**,
  confabulated fields flagged in red with the true value beside them, imprints
  and their cues (`05-MEMORY.md` §9)
- **Beliefs** — what they think is true, with source, confidence, and a
  truth-vs-belief diff only the GM can see
- **Relationships** — the directed multi-axis grid, both ways
- **Decision trace** — the last N decisions with full term breakdowns
  (`06-DECISION-ENGINE.md` §12)
- **Impulses** — the live queue with decay curves

That last pair is the demo. Anyone can claim their NPCs have memory; showing a GM
*why* Marla drew her knife — imprint +0.62, cue "green lantern", fear 0.41 — is
the thing no competitor can show.

## 6. Bot-owner pages

Under the existing owner scope: global KB editor, ruleset management, entitlement
and tier administration, cross-guild budget and health, and the
`08-LLM-LAYER.md` §3 benchmark results.

## 7. Parameters

Added to `helpers/parameters.py` under `cog: "dnd"` — typed specs give free panel
inputs (`helpers/parameters.py` docstring):

| Key | Type | Default | Purpose |
| --- | --- | --- | --- |
| `dnd_llm_backend` | choice | `null` | `ollama` / `null`. There is no hosted-API option by design (`08-LLM-LAYER.md` §1) |
| `dnd_ollama_url` | str | `""` | Tailscale URL of the inference host. A server may point at its own Ollama |
| `dnd_ollama_model` | str | `qwen3:4b` | Model tag on that host |
| `dnd_llm_queue_cap` | int | `12` | Queue depth before tasks drop to templates |
| `dnd_tick_seconds` | int | `900` | Real seconds per world tick |
| `dnd_tick_minutes` | int | `10` | World minutes per tick |
| `dnd_focus_cap` | int | `8` | Max focus-tier NPCs per scene |
| `dnd_active_cap` | int | `200` | Max active-tier NPCs per campaign |
| `dnd_daily_render_cap` | int | `200` | Model calls per day before degrading to templates |
| `dnd_canon_auto_accept` | float | `0.0` | Auto-promote confidence threshold |
| `dnd_default_ruleset` | choice | `freeform` | `freeform` / `srd5e` |

## 8. Features

Added to `helpers/cog_categories.py` `FEATURES`, individually toggleable per guild
(the enforcement point for tiering — `10-MONETIZATION.md`):

| Feature | Effect when off |
| --- | --- |
| `dnd_world_tick` | World freezes between scenes; no clocks, no off-screen NPCs |
| `dnd_autonomous_gm` | Suggester only; no unattended GM |
| `dnd_npc_chatter` | NPCs act but do not speak unprompted |
| `dnd_canon_auto` | Every LLM invention needs GM approval |

The `ai` category in `cog_categories.py` currently lists `dnd` alongside `chat`
and `talkengine`. Tabletop should become **its own category** — it is a product,
not a chat feature.
