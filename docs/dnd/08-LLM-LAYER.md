# LLM Layer

A leaf service (`01-ARCHITECTURE.md` §1, Invariant 1). It phrases things. It never
decides anything, never holds state, and can be switched off entirely without the
game stopping.

**Two standing rules, set by the owner:**

> **1. No inference leaves hardware we control.** No hosted APIs, no third-party
> model providers, in any tier, for any tenant. Local only.
>
> **2. Deterministic first.** If a computation can be done in Python, it is done
> in Python. A model is called only where *prose quality is itself the product*.
> See §5 — this cut the AI surface from five tasks to two.

---

## 1. Backends

```python
class Backend(Protocol):
    key: str
    async def complete(self, task: Task, *, stream: bool = False) -> Response: ...
    def healthy(self) -> bool: ...
```

| Backend | Use |
| --- | --- |
| `ollama` | The only inference backend. Points at a host URL. |
| `null` | Deterministic templates. Always available, always tested, and the **automatic fallback whenever the Ollama host is unreachable**. |
| `cached` | Wrapper adding the response cache (§9). |

The `openai_compat` backend from the earlier draft is **removed**. Rule 1 makes it
dead code, and dead code with an API key field in it is a liability.

`null` is not a degraded mode to be ashamed of — it is the reason a laptop being
asleep is a non-event rather than an outage.

## 2. The inference host

### Rejected: the VPS

Measured: 1 vCPU, 898 MB RAM, ~468 MB available with the bot running. The smallest
usable model plus the Ollama runtime needs ~800 MB–1.1 GB, and one shared core
yields ~5–10 tok/s. It would swap-thrash into an OOM kill of the bot. **Closed —
do not revisit, and do not install Ollama there.**

### Chosen: the owner's laptop

Measured 2026-08-16:

```
CPU   AMD Ryzen 7 8845H — 8 cores / 16 threads, Zen 4, 3.8 GHz base
RAM   28 GB LPDDR5X-7500, 4 × 32-bit sub-channels (128-bit bus)
GPU   AMD Radeon 780M (gfx1103, RDNA3, 12 CU), ~4 GB UMA carve-out
Disk  133 GB free (C:), 126 GB free (G:)
OS    Windows 11
```

**Memory bandwidth is the binding constraint on token generation**, not the CPU:

```
7500 MT/s × 128 bit ÷ 8 = 120 GB/s theoretical
                        ≈ 75–85 GB/s achievable in practice (llama.cpp streaming reads)
```

That is roughly 35% better than the DDR5-5600 SODIMMs in a typical laptop, and it
converts almost linearly into tokens per second.

**Caveat: the RAM is soldered LPDDR5X.** 28 GB is the ceiling on this machine — no
upgrade path. Size the model choice accordingly.

## 3. What this hardware runs

Generation speed ≈ `effective_bandwidth ÷ model_bytes`, at ~75 GB/s effective:

| Model (Q4_K_M) | On disk | Theoretical | **Realistic** | Verdict |
| --- | --- | --- | --- | --- |
| Qwen3 1.7B | 1.1 GB | 68 tok/s | 40–55 | Fast; prose is thin |
| Llama 3.2 3B | 2.0 GB | 37 tok/s | 25–35 | Good utility model |
| **Qwen3 4B** | **2.5 GB** | **30 tok/s** | **20–28** | **Start here** |
| Qwen2.5 7B / Llama 3.1 8B | 4.7 GB | 16 tok/s | 12–16 | Best prose/speed trade |
| Mistral Nemo 12B | 7.1 GB | 10.5 tok/s | 8–12 | Noticeably slower |
| Qwen3 14B | 9.0 GB | 8.3 tok/s | 6–9 | Only if quality demands it |
| 24B+ | 15 GB+ | 5 tok/s | 3–5 | Too slow, too heavy |

**Recommendation: Qwen3 4B Q4_K_M to start** — ~2.5 GB resident, 20–28 tok/s,
strong instruction-following and reliable JSON for its size. Our tasks need style
and obedience, not knowledge or reasoning, because the prompt carries everything
(§6). Move to an 8B only if prose quality measurably disappoints; that costs
roughly half the speed.

### The RAM situation

28 GB total, but at the time of measurement only **5.74 GB was free** — Chrome,
Discord, Telegram and Claude were holding the rest. So budget against *free* RAM,
not total:

| Model | Resident (weights + 4k KV + runtime) | Fits in 5.7 GB free? |
| --- | --- | --- |
| Qwen3 4B Q4 | ~3.3 GB | Yes, comfortably |
| Llama 3.1 8B Q4 | ~5.8 GB | Only after closing things |

Another argument for the 4B: it coexists with a working laptop. "Lightweight" was
a stated requirement, and a model that forces you to close your browser is not
lightweight.

### The iGPU: try it, don't depend on it

The 780M shares the same memory bus, so **generation speed barely improves** — it
is bandwidth-bound either way. What the iGPU *does* help is **prompt processing
(prefill)**, which is compute-bound: roughly 100 tok/s on CPU versus 500–800 tok/s
on the 780M. For our 400–1500 token prompts that is 12 s → 2 s.

But `gfx1103` is **not officially supported by ROCm**. Options, in order of
reliability:

1. **CPU-only** — guaranteed to work. This is the baseline and it is already fine.
2. **Vulkan backend (llama.cpp)** — works well on 780M; the more dependable
   acceleration path.
3. **ROCm with `HSA_OVERRIDE_GFX_VERSION=11.0.2`** — sometimes works, sometimes
   crashes.

Treat acceleration as a bonus measured after the fact, never as a number the
design depends on.

## 4. Deployment

```
┌──────────────┐   Tailscale    ┌─────────────────────┐
│  VPS (bot)   │ ─────────────► │  Laptop: Ollama     │
│  45.141.…    │   :11434       │  127.0.0.1:11434    │
└──────────────┘                └─────────────────────┘
        │
        └── host unreachable ──► backend = null ──► templates ──► game continues
```

Tailscale over `cloudflared`: no public hostname, no exposed port, WireGuard
encryption, and the laptop keeps a stable address across networks.

Recommended environment on the laptop:

```
OLLAMA_KEEP_ALIVE=5m          # release RAM when idle
OLLAMA_MAX_LOADED_MODELS=1    # one model, never a surprise second
OLLAMA_NUM_PARALLEL=1         # one request at a time; we queue (§8)
OLLAMA_HOST=0.0.0.0:11434     # bind for the tunnel; Tailscale ACL is the gate
```

And in the model options: **`num_ctx=4096`.** Our largest prompt budget is 1500
tokens, so a bigger context buys nothing and costs real memory — KV cache scales
linearly with context, and on an 8B a 32k window is ~4 GB of pure waste. This one
setting is the difference between a polite background service and a laptop-eater.

**Laptop asleep is a supported state.** The health check fails, the backend
switches to `null`, the game keeps running on templates, and the GM sees a notice.
Nothing breaks, nothing queues forever.

## 5. The AI budget

Rule 2 applied. The earlier draft had five LLM tasks; four of them turned out not
to need a model.

| Task | Verdict | How |
| --- | --- | --- |
| `summarize_episode` | **Non-AI.** | Structured gist from event kinds and participants. The consolidation grouping and scoring were always deterministic (`05-MEMORY.md` §8); only the phrasing was AI, and a template phrases it fine because nobody reads these — the *engine* does. |
| `propose_canon` | **Non-AI by default.** | Name/culture tables from the global KB cover generation. AI is used **once per campaign**, for the session-zero bootstrap batch (`03-KNOWLEDGE-BASE.md` §6), where richness genuinely matters and the cost is paid a single time. |
| `parse_intent` | **Non-AI first, AI on failure.** | A verb+affordance parser resolves the great majority of input, because the affordance list is small and known. AI is the fallback for genuinely ambiguous input — and even then, asking the player to disambiguate is often better than guessing. |
| `render_scene` | **AI.** | Prose quality *is* the product here. |
| `render_dialogue` | **AI.** | Same, plus voice and mood. |

So: **two tasks always call a model, one calls it as a fallback, two never do.**

### Adding a call site

Any new place that wants to call a model must add a row to the table above stating
(a) the deterministic alternative, and (b) why it is insufficient. "It would be
nicer" is not a reason. This is a review gate, not a suggestion — the drift from
"simulation with a renderer" to "LLM with extra steps" happens one convenient call
site at a time.

## 6. Task construction

Assembled by `llm/tasks.py`, never by cogs:

```
[system]  task instruction + output schema + tone/gm_style (forced from KB)
[context] retrieved knowledge, budgeted (03-KNOWLEDGE-BASE.md §3)
[state]   the state delta or npc_view — structured and terse, not prose
[input]   the player text or the bound beat
```

Budgets: `render_scene` 1200 tokens, `render_dialogue` 800, `parse_intent` 400.

Rules: **no conversation history is ever replayed** — state carries it, which is
the fix for the current cog's unbounded `history` string; system text stays byte-
stable so Ollama's prompt cache hits; output is JSON, schema-validated, retried
once, then dropped to the template.

`render_dialogue` receives an `npc_view` (`04-ENTITIES.md` §6) — beliefs, mood,
relationship, relevant memories, voice quirk. It does **not** receive world truth,
so the model *cannot* leak what the NPC does not know. Fog of war is enforced by
what is in the prompt, not by asking a 4B model to keep a secret.

## 7. Fallbacks

`backend=null` is a supported, tested configuration:

| Task | Fallback |
| --- | --- |
| `parse_intent` | The verb-table parser that already runs first; ambiguity becomes a disambiguation prompt to the player. |
| `render_scene` | Template from the state delta: `"{actor} {verb}s {target}. {outcome_clause}"` |
| `render_dialogue` | Archetype line bank selected by mood + relationship + intent. |

The **null-backend suite** (`01-ARCHITECTURE.md` §10) runs the whole turn loop this
way. If it fails, a model has become load-bearing and Invariant 1 is broken.

## 8. Queueing & capacity

`OLLAMA_NUM_PARALLEL=1` means requests serialize, so the bot maintains a small
priority queue:

1. `parse_intent` fallback — a player is waiting
2. `render_dialogue` — a player is waiting
3. `render_scene` — a player is waiting, but mechanics already posted
4. bootstrap batches — nobody is waiting

Queue depth is capped; over the cap, the task drops to its template rather than
making anyone wait. **A player never waits on a queue.**

### Does one laptop serve many servers?

Better than expected, because **async play and local inference are complementary**.
At ~20 tok/s a 200-token render takes ~10 s, so the host produces roughly 5 renders
per minute sustained. A play-by-post campaign generates 1–3 beats *per day*. The
duty cycle is tiny — one laptop can back a large number of campaigns as long as
they do not burst simultaneously, which the queue and the template fallback
already handle.

The honest limits, stated because they will arrive eventually:

- **Live sessions burst.** A 4-hour live table wants many renders in an hour. A
  handful of concurrent live sessions will saturate the host and fall back to
  templates.
- **The laptop must be awake.** Fine for the owner's server, not a service level
  anyone can promise a stranger.

If the product grows past this, the answer consistent with Rule 1 is **a dedicated
inference box we own** — not a hosted API. The backend interface makes that a URL
change. A second option, also compliant: tenant servers point at *their own*
Ollama, which is a genuinely attractive selling point for privacy-minded groups.

## 9. Caching

Content-addressed on `(task, model, normalized_prompt_hash)`, in Mongo with a TTL.
Hits are highest on `render_dialogue` greetings and on replay during development.
A cache hit costs nothing and skips the queue, so it is worth more here than it
would be against a hosted API.

## 10. Resource accounting

There is no per-token bill, so `dnd_budgets` stops being about money and becomes
about **load**:

```jsonc
{
  "guild_id": …, "campaign_id": …, "period": "2026-08",
  "requests": 412, "generated_tokens": 61840,
  "queue_wait_ms_p95": 2200, "fallback_rate": 0.06
}
```

`fallback_rate` is the health metric to watch — a rising number means the host is
saturated, asleep, or the queue cap is too low. Surfaced through
`helpers/health.py` alongside the existing samples.

Tier limits (`10-MONETIZATION.md`) shift accordingly: they cap **requests per day
and queue priority**, not dollars.

## 11. Safety integration

Every rendered output passes the content filter (`11-SAFETY.md`) before posting.
On a block: retry once with tightened constraints, then fall back to the template.
Filtered output is never posted raw and never silently dropped — the GM is told.

## 12. Setup checklist

For when P4 starts:

- [ ] Install Ollama on the laptop; `ollama pull qwen3:4b`
- [ ] Set the environment from §4, especially `num_ctx=4096`
- [ ] Measure: peak RSS, time-to-first-token, tok/s at a 1200-token prompt.
      **Record the results in this file** — §3 is estimates until then
- [ ] Try the Vulkan backend; record whether prefill improves. Do not block on it
- [ ] Tailscale on both hosts; verify the VPS reaches `:11434`
- [ ] Verify the unreachable-host path falls back to `null` cleanly
- [ ] Confirm `dnd_llm_backend` switches without a redeploy
