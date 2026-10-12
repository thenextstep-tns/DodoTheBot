# Narrative Engine

Story structure is a **state machine**, not a prompt. The drama manager decides
*what should happen next*; the LLM only phrases it.

---

## 1. Two modes, one machine

| Mode | Who decides | Ships |
| --- | --- | --- |
| **Suggester** | Human GM picks from proposals | Phase 5a — first |
| **Autonomous GM** | Engine picks and runs | Phase 5b |

Same drama manager, same beat catalogue, same state. The only difference is
whether a human approves the beat. Building suggester first is deliberate: it is
useful on day one, it is safe (a human filters every output), and it generates the
data that shows whether autonomous selection is any good — the GM's accept/reject
record *is* the eval set.

## 2. Drama state

Tracked per campaign, updated on every event. Cheap, all of it.

```python
@dataclass
class DramaState:
    tension: float                      # 0..1, current scene pressure
    tension_history: list[float]        # for curve shape
    spotlight: dict[ObjectId, float]    # per PC: decayed share of recent focus
    threads: list[Thread]               # unresolved hooks
    beats_since: dict[str, int]         # beats since each kind last fired
    arc_position: float                 # 0..1 through the current arc
    last_beat: str | None
```

**Spotlight** is the one GMs consistently get wrong and a machine gets right:

```python
spotlight[pc] = spotlight[pc] * DECAY + involvement_this_event
```

An NPC seeking the quietest player is worth more to a table than any amount of
prose quality. It is also nearly free to compute.

**Threads** are unresolved things with an age and a heat: a question nobody
answered, an NPC goal in progress, a clock at 6/8, a promoted canon fact nothing
has used yet. Threads are the raw material for every proposal.

## 3. Beats

A beat is a *shape*, not content. Defined as data in the global KB.

```jsonc
{
  "key": "complication",
  "preconditions": {"tension": "<0.7", "beats_since.complication": ">=3"},
  "raises_tension": 0.25,
  "spotlight": "lowest",              // whom it targets
  "sources": ["thread", "clock", "npc_goal", "imprint"],
  "weight": 1.0
}
```

Catalogue (v1): `reveal · complication · reversal · respite · escalation ·
consequence · arrival · departure · discovery · confrontation · quiet`.

Eleven beats is enough for a coherent rhythm and few enough that a GM can learn
what the engine is doing. `quiet` and `respite` are in the list on purpose —
engines that only escalate exhaust a table in two sessions.

## 4. Beat selection

```python
def next_beat(drama: DramaState, world: WorldView) -> Beat:
    return max(
        (b for b in CATALOGUE if b.preconditions_met(drama)),
        key=lambda b: (
              0.30 * tension_fit(b, drama)        # toward the target curve
            + 0.25 * thread_pressure(b, world)    # hot, old, unresolved
            + 0.20 * spotlight_need(b, drama)     # who is being left out
            + 0.15 * variety(b, drama)            # anti-repetition
            + 0.10 * b.weight
        ),
    )
```

`tension_fit` targets a **curve**, not a level: rise through the arc, spike, then
release. The target at `arc_position` comes from a simple shape function, so the
engine reaches for a `respite` after a spike without being told to.

Selection is deterministic given `(drama, world)`. Suggester mode returns the top
3–5 rather than the argmax.

## 5. Beat → content

A selected beat is **bound to real world state** before anything is rendered:

```
beat: complication
  ├─ source thread: "the Compact wants the north dock" (clock 6/8, age 4 days)
  ├─ agent: Marla Venn (active, believes you work for the Compact, fear 0.7)
  ├─ target: quietest PC (spotlight 0.08)
  └─ proposed event: Marla bars the dock gate and calls the watch
```

That binding is the proposal. Only *then* is the LLM asked to render prose for it
— and with `backend=null`, a template renders the same binding, and the game
continues.

This ordering is the difference between "the AI made something up" and "the world
did something, and here is how it read."

## 6. Suggester mode

The GM's panel and a `/gm suggest` command show 3–5 bound proposals:

> **1. Complication — Marla bars the north dock** *(clock 6/8, spotlight: Kesh)*
> She believes you work for the Compact (confidence 0.6, told by Ondry). Fear 0.7.
> `[Use] [Reroll] [Edit] [Dismiss]`
>
> **2. Reveal — Ondry's imprint triggers** *(thread age 9 days)*
> The green lantern is in this scene. He has never told anyone what happened.
> `[Use] [Reroll] [Edit] [Dismiss]`

Every proposal cites *why*, from real state. A GM can accept it, twist it, or
dismiss it — and dismissals feed `variety` so the engine stops offering that
shape.

This mode makes a human GM better rather than replacing them, which is both the
faster product and, for a lot of tables, the more wanted one.

## 7. Autonomous GM mode

Same pipeline, no approval step, plus:

- **Pacing governor** — max beats per real hour, respecting async rhythm. A
  play-by-post table wants 1–3 beats a day, not 1–3 an hour.
- **Player-response window** — after a beat, wait for player input up to a
  timeout before advancing. Async-first means the world is patient by default.
- **Safety gate** — every rendered beat passes the content filter
  (`11-SAFETY.md`) before posting. Non-negotiable in this mode.
- **GM override** — a human can always interrupt, retcon (events are a log, so
  undo is real), or take back the chair mid-scene.
- **Escalation guard** — if tension has been above 0.8 for N beats with no
  release, force a `respite`. Runaway escalation is the most common failure mode
  of an unattended narrative engine.

## 8. Scene lifecycle

```
open ──► running ──► resolving ──► closed
  │         │            │
  │         │            └─ consolidate working→mid memory (05-MEMORY.md §8)
  │         │               update threads, spotlight, clocks
  │         └─ turn loop (01-ARCHITECTURE.md §4), beats between turns
  └─ bind location, present entities, promote them to focus tier
```

A scene is a Discord forum thread. `session.py` subclasses `PersistentFlow`
(`kind = "dnd_scene"`) so a restart resumes it — something the current cog does
not do.

## 9. Arcs

An arc is a run of scenes with a tension curve and a set of threads. It ends when
its principal threads resolve, or the GM ends it. Arc end triggers:

- mid → long memory consolidation for everyone involved,
- event log compaction (`02-DATA-MODEL.md` §7),
- thread pruning and clock review,
- an arc summary written to campaign knowledge — **the campaign's own history
  becomes retrievable lore**, which is how a long campaign stays coherent without
  a growing prompt.

## 10. What this is not

It does not write your story. It selects a *shape* from real state and hands the
GM (or the renderer) a bound proposal. Every interesting specific — who, why, with
what history — comes from the simulation, not from the model's imagination. That
is precisely why the output stays consistent with a campaign that has been running
for six months.
