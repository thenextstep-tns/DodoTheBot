# LLM Layer

A leaf service (`01-ARCHITECTURE.md` §1, Invariant 1). It phrases things. It never
decides anything, never holds state, and can be switched off entirely without the
game stopping.

---

## 1. Backends

One interface, four implementations:

```python
class Backend(Protocol):
    key: str
    async def complete(self, task: Task, *, stream: bool = False) -> Response: ...
    def healthy(self) -> bool: ...
    def cost_per_1k(self) -> tuple[float, float]: ...   # (prompt, completion)
```

| Backend | Use | Notes |
| --- | --- | --- |
| `openai_compat` | **Tenant servers** | proxyapi.ru today, per-guild key — the pattern `cogs/chat.py` already established with the `chat_api_key` param. |
| `ollama` | **Dev + owner's server** | Points at a host URL. See §2 and §3. |
| `null` | Fallback, tests, free tier | Deterministic templates. Always available, always tested. |
| `cached` | Wrapper | Wraps any backend with the response cache (§6). |

Selected per guild via a `dnd_llm_backend` parameter, so a server can be moved
between them without a deploy.

## 2. The hardware reality

Measured on the production VPS (`45.141.76.118`) at planning time:

```
1 vCPU (shared Xeon Gold 6336Y) · 898 MB RAM · 1 GB swap · 15 GB disk
Bot process ≈ 271 MB · available ≈ 468 MB
```

**Ollama cannot run usefully on this box.** The arithmetic:

| Component | Resident |
| --- | --- |
| Ollama runtime, no model | ~200–300 MB |
| `gemma3:270m` Q4 + KV cache | ~600–800 MB |
| `qwen3:0.6b` Q4 + KV cache | ~1.0–1.2 GB |
| `llama3.2:1b` Q4 + KV cache | ~1.5–2.0 GB |

The smallest option needs ~800 MB–1.1 GB against ~468 MB available. It would
swap-thrash into an OOM kill of the bot. And on one shared core a 1B model
generates roughly 5–10 tok/s, so a 200-token narration takes 20–40 seconds —
before prompt processing.

**These are estimates, not measurements.** Before treating them as final, run §3.

### Resolution (owner's decision)

- **Dev + the owner's own server** → Ollama on the owner's laptop, reached over a
  tunnel (Tailscale, or `cloudflared` if a public hostname is wanted). The VPS
  holds no model; it makes an HTTP call like any other backend.
- **Tenant servers** → `openai_compat` with a per-guild key. A laptop cannot serve
  N customer guilds, and "product for many servers" was the chosen audience.
- **If local inference is later wanted for tenants** → a separate inference host,
  sized from §3's numbers. The backend interface means that is a config change.

The pluggable design means none of this blocks a single line of the build.

## 3. Benchmark before believing §2

A measured test, to be run **with the owner's approval** and never casually on
production:

```bash
# On the VPS, memory-capped so it cannot OOM the bot.
systemd-run --scope -p MemoryMax=400M -p MemorySwapMax=0 \
  ollama serve
```

Then, for `gemma3:270m` and `qwen3:0.6b`: record peak RSS, time-to-first-token,
tokens/sec at 512-token prompts, and whether the `dodo` service survives. Record
results in this file. If a model fits and clears ~15 tok/s, revisit §2 — I would
rather be wrong on the record than right by assertion.

Safeguards, non-negotiable: run it at a quiet hour, `MemoryMax` set, and
`systemctl status dodo` checked immediately after.

## 4. The five tasks

Narrow, typed, small. **Never one big "you are a Dungeon Master" prompt** — that
is the design error that makes every competitor's product drift.

```python
parse_intent(text, affordances)   -> Action | Clarify      # ~400 tok budget
render_scene(delta, kb)           -> prose                 # ~1200
render_dialogue(npc_view, intent) -> line                  # ~800
summarize_episode(events)         -> gist                  # ~600
propose_canon(gap, kb)            -> fact[]                # ~1500
```

Properties that follow from keeping them small:

- **A 4B model is enough.** None of these requires reasoning or recall — the
  prompt carries everything needed.
- **Latency is low** because prompts are short.
- **Output is structured** — JSON, validated against a schema, retried once on
  parse failure, then dropped to the fallback.
- **Each is independently cacheable** (§6).
- **Each has a deterministic fallback** (§5).

`render_dialogue` receives an `npc_view` (`04-ENTITIES.md` §6) — the NPC's
beliefs, mood, relationship to the listener, relevant memories, voice quirk. It
does *not* receive world truth, so the model **cannot leak what the NPC does not
know.** Fog of war is enforced by what is in the prompt, not by asking the model
to keep a secret.

## 5. Fallbacks

Every task degrades. `backend=null` is a **supported, tested configuration**, not
a broken state:

| Task | Fallback |
| --- | --- |
| `parse_intent` | Verb-table keyword parser over affordances; asks the player to disambiguate rather than guessing. |
| `render_scene` | Template: `"{actor} {verb}s {target}. {outcome_clause}"` filled from the state delta. |
| `render_dialogue` | Archetype line bank, selected by mood + relationship + intent. |
| `summarize_episode` | Structured gist from event kinds and participants — no prose. |
| `propose_canon` | Name/culture tables from the global KB. |

The **null-backend test suite** (`01-ARCHITECTURE.md` §10) runs the whole turn
loop this way. If it fails, the LLM has become load-bearing somewhere and
Invariant 1 has been broken.

## 6. Caching

Content-addressed on `(task, model, normalized_prompt_hash)`, stored in Mongo with
a TTL.

High-value hits: `render_dialogue` for repeated greetings, `summarize_episode` on
replay, `propose_canon` for name generation, and **every retry after a transient
failure**. Realistic hit rate ~20–35% in play, higher in dev where the same scene
is replayed constantly.

Cache reads never block the loop and a miss is never an error.

## 7. Budgets & cost control

Without caps, one enthusiastic server bankrupts the operator. Enforced in
`llm/budget.py`, per guild **and** per campaign:

```jsonc
{
  "guild_id": …, "campaign_id": …,
  "period": "2026-08",
  "prompt_tokens": 184320, "completion_tokens": 42110,
  "cost_usd": 0.94,
  "cap_usd": 5.00,
  "on_exceed": "degrade"        // degrade | block | notify
}
```

- `degrade` (default) — silently fall back to `null`. **The game keeps running.**
  This is only possible because of §5, and it is the whole argument for it.
- `block` — refuse LLM tasks, tell the GM.
- `notify` — keep going, warn the owner.

Per-guild BYO-key servers bill themselves and are capped only by their provider.
Caps by tier live in `10-MONETIZATION.md`.

## 8. Streaming & perceived latency

The single most important UX decision in the module:

1. Resolve mechanics and **post the outcome immediately** (< 50 ms):
   *"You hit for 7. The guard staggers back into the lantern."*
2. Stream the narration into a follow-up message, editing as tokens arrive.
3. If the model is slow or dies, step 1 already told the table what happened.

The game never waits on a model. On a 20-second local generation the table still
sees instant feedback — which is what makes "lightweight" true regardless of the
inference host.

## 9. Prompt construction

Assembled by `llm/tasks.py`, never by cogs:

```
[system]  task instruction + output schema + tone/gm_style (forced from KB)
[context] retrieved knowledge, budgeted (03-KNOWLEDGE-BASE.md §3)
[state]   the state delta or npc_view — structured, terse, not prose
[input]   the player text or the bound beat
```

Rules: no conversation history is ever replayed (state carries it — this is the
fix for the current cog's unbounded `history` string); system text is stable so
prompt caching works upstream; all player-facing strings still route through
`bot.lang`.

## 10. Safety integration

Every rendered output passes the content filter (`11-SAFETY.md`) **before** it is
posted. On a block: retry once with tightened constraints, then fall back to the
template. A filtered output is never posted raw and never silently dropped — the
GM is told.
