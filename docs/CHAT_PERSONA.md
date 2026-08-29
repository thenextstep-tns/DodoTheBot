# Dodo's personality — how it works, and why it is built this way

Read this before touching `cogs/chat.py` or anything under `helpers/chat/`.

---

## The problem this replaced

The personality used to be one long system prompt: a persona, five prose
paragraphs describing five relationship bands, a drowsiness table, four numbered
tasks, and the user's entire stored memory — which the model was asked to **echo
back** on every single reply.

Three things were wrong with it.

**It was a mode switch.** The persona named four modes (puppy / toddler /
surreal / utility) and described each with intensity adjectives. Adjectives have
no scale, so a model given "be unhinged" is maximally unhinged every time. Once a
mode fired, the whole reply was that one note. That is what made her exhausting
rather than characterful.

**It was incoherent between messages.** `drowsiness = random.randint(0, 10)` was
re-rolled per message, so two replies five seconds apart could be "sharp and
tired" and then "very sleepy, rambling". One line, and it did more damage to the
character than the persona text did. It is gone, and nothing replaced it —
variation now comes from state, which is continuous and has reasons.

**It was expensive and lossy.** 600–900 tokens per call, of which the memory echo
was charged twice (in and out), grew without limit, and let one bad completion
truncate somebody's history permanently.

---

## The shape now

Four modules that never call a model, and one that does.

```
message
   │
   ├─ router.observe()          ring buffer of recent messages (in memory)
   │
   ├─ triggers.match()          one compiled regex scan per guild
   │
   ├─ router.decide()  ─────────► IGNORE      say nothing (feelings still land)
   │                              REFLEX      canned line, zero tokens
   │                              ENGAGE      one API call
   │                              SPONTANEOUS one API call, uninvited
   │
   └─ (engaging) state.load → dial.compute → prompt.build → model → state.save
```

Everything above the last line is arithmetic over in-process dicts. Nothing
touches the database or the API until a decision to speak has been made — which
matters, because the router runs on every message in every server.

| Module | Holds |
|---|---|
| `helpers/chat/state.py` | What she knows and feels about one person, and how it rots |
| `helpers/chat/triggers.py` | Per-server string listeners, compiled and cached |
| `helpers/chat/dial.py` | How much flourish this one reply is allowed |
| `helpers/chat/router.py` | Whether to speak, and whether speaking needs the model |
| `helpers/chat/prompt.py` | Assembling the three prompt blocks |

---

## Watching it work

The Events page carries a live **activity log**: every message that matched a
trigger or produced a reply, with the decision and the reason attached. Without
it the system is invisible from outside — a trigger that matched and stayed
silent looks exactly like the feature being switched off, so every number below
would be tuned by guesswork.

It is an in-memory ring per guild, lost on restart, because the alternative is a
database write on every message in every server.

### Defaults do not reach a server twice

Seeding runs only when a guild has **no** trigger rows. A server set up last week
keeps the wording it was first given and never sees a trigger shipped since —
this bit the live server, which sat on the first-ever notes for days while the
defaults in this repo moved on.

Two buttons on the page:

* **Add new defaults** — inserts defaults this server has never had, and touches
  nothing else. Safe: your edits survive.
* **Reset to defaults** — deletes everything and re-seeds. The only way to pull
  in *improved wording* for a trigger that already exists, and it discards edits.

## Triggers that run a command

A trigger can name a **command** instead of talking. It skips the router, the
dial and the model entirely, and needs no API key — it is an action, not speech.
With a **confirm emoji** set she offers the command and runs it only if the
person who spoke clicks, which is the difference between offering a signup sheet
and dumping one in the channel every time somebody says "trials".

This exists because `bot.py`'s `on_message` used to carry its own hardcoded
phrase listeners — `"no u"`, the raid-signup keywords, `"support cat"` — with no
route to the panel and no way to turn them off. The `"no u"` one was the worst of
it: unconditional, and positioned *ahead* of the chat cog, so the tunable
`banter` trigger it duplicated never got a word in. Its lines were good, so they
live in that trigger's canned pool now.

If a phrase makes Dodo do something, it belongs in this table. There is no
second place for it.

## Reading what she is actually told

`py -3.13 tests/preview_chat.py` prints the real assembled prompt for thirteen
representative situations — praise, worn-out banter, Xynode, someone hurting, a
straight question, joining uninvited. Free and offline. Add `--live` to also make
one real API call per scenario and print what she says back, which costs money.

The unit tests prove the machinery. They cannot tell you whether the character is
any good, because that judgement lives in prose — the persona and the trigger
notes. Read the preview, edit the prose, run it again.

## The three ideas worth keeping

### 1. A budget, not an adjective

The prompt never receives a mood word. It receives:

```
dial: 2 flourishes | 3 sentences max
```

Models obey counts almost perfectly and obey "be zany but not too zany" not at
all. The count is computed from the server's base allowance, the matched
trigger's worth, how close she is to this person, how worn out the bit is, and
whether the message is a real question. Set `chat_spice_max` to 0 and you have a
purely functional bot on that server, with no prompt rewriting.

### 2. Noticing without speaking

A trigger's `chance` is the odds she *replies*. Its feelings apply either way.

Set `chance` to 0 and she reads the insult, takes the affinity hit, records the
grudge, and says nothing — and it colours whatever she says three messages
later. This is the whole difference between a character and a soundboard, and it
costs one probability check.

### 3. Bits wear out — without her going flat

Fatigue eats the **trigger's** bonus and stops there; the base allowance is hers
no matter how tired the bit is. Let it eat into the base too and the fifth "no u"
gets a bot with no personality at all, which is a worse failure than repetition.

Every trigger fire bumps a per-user, per-trigger counter that decays on a
half-life (`chat_fatigue_halflife_minutes`). `chat_fatigue_bite` turns that
counter into lost flourish budget, and past two the dial line says so outright:

```
dial: 1 flourish | 2 sentences max | this bit has been pulled 4 times lately and you know it
```

First "no u" gets the full tantrum. Fourth gets a bird who is tired of it. Without
this, string listeners are the most annoying feature a Discord bot can have.

---

## Memory is a delta

The model returns `"learned": "one new fact"` or `null`. Python appends it.

Facts are a capped list with hit counts (`chat_facts_max`,
`chat_facts_recall`, `chat_fact_halflife_days`): re-stating something bumps its
count instead of duplicating it, and when the cap is hit the least-reinforced,
oldest fact loses. Recall is "the things that keep coming up", not "everything,
forever".

The old `memory` blob migrates into fact zero on first read, so nothing already
stored was lost. It is still written back as a joined summary for anything that
reads the old field.

## Feelings decay lazily

There is no scheduler and no sweep. Every decaying value carries a timestamp and
is aged **on read**:

- **affinity** drifts toward neutral at `chat_relationship_drift_per_day`. This is
  the "she forgives" knob; set it to 0 to freeze relationships permanently.
- **grudges** fade on `chat_grudge_halflife_hours` and are dropped below
  `chat_grudge_floor`. Any trigger with `forgives` set clears them all instantly —
  petty grudges are supposed to be cheap to end.
- **fatigue** stores the already-decayed count, so an entry never needs touching.

A user who has not spoken in a month costs exactly one document read to catch up.

---

## Where the knobs are

**Per-server parameters** (44 of them) live in `helpers/parameters.py` under the
`chat` cog and render in the panel under that cog. See
`docs/PER_SERVER_PARAMETERS.md` for the groups.

**String listeners** live in Mongo (`ChatTriggers`) and are edited on the panel's
**Events page**, under the event rules — because "when someone says X" and "when
X happens" are the same thought, and both belong on the same page. A guild with
no rows is seeded from `DEFAULT_TRIGGERS` on first read, so a fresh server has a
personality immediately and can then rewrite every word of it.

Each trigger row carries: the phrases, what she feels (a sentence, in her point
of view), the relationship change, the grudge strength, the extra flourishes, the
chance she replies, the canned lines, and how often a reply uses one.

**Two feature switches** gate the listeners independently of the cog:
`chat_listeners` and `chat_unprompted`.

### Writing a trigger's "she feels" line

Describe the situation, never the performance.

> ✅ "They were rude to you. You have noted it. You do not have to do anything about it today."
>
> ❌ "BE FURIOUS AND USE ALL CAPS"

The first produces a bird reacting. The second produces a bot doing an
impression of one. This is the same mistake the old four-mode sheet made, one row
at a time.

---

## Joining a conversation uninvited

Very rarely, in a channel with an actual live conversation, she reads the last
few messages and contributes like a regular user. Gated four ways:

1. `chat_spontaneous_chance` — per message, default **0.002**
2. `chat_spontaneous_min_messages` / `chat_spontaneous_min_speakers` — so she
   interrupts a conversation, not somebody thinking out loud alone
3. `chat_spontaneous_cooldown_seconds` — never twice in a row
4. The model may answer with an empty `say`, and then nothing is posted — she is
   explicitly told to stay quiet unless she has something worth adding

The difference between charming and infuriating here is entirely frequency.
Raise the chance with care; 1-in-500 is charming and 1-in-20 is not.

---

## She likes some people for no reason

`chat_first_impression_spread` gives a stranger an arbitrary ±60 points before
they have said a word. It is derived from their user id, not from `random` —
which is the whole point. Random would make it *noise*: she would like you
differently every time she looked at you. Derived from the id it is an
**opinion**: unearned, unjustifiable, and completely consistent from then on.

The daily drift pulls it back toward neutral, so an unearned dislike fades if
they never come back. It is a first impression, not a life sentence. Set the
spread to 0 and everyone starts equal.

## Costs

| | Before | After |
|---|---|---|
| System prompt | 600–900 tokens | ~230 tokens (128 words assembled + persona) |
| Memory in the output | the whole blob | ~10 tokens |
| A bare "no u" | one full call | zero |
| A phrase she notices but ignores | n/a (didn't exist) | zero |

Canned trigger lines keep working after `chat_daily_call_cap` is spent, which is
the point of having them.

---

## Handoff — state as of 2026-08-22

**Done and tested.** `tests/cases/test_chat.py` covers the mind,
`test_chatcog.py` drives the cog end to end against a fake Discord and a fake
model, `test_trigpage.py` renders the panel and checks every control is bound to
the API. 34/34 in the suite.

The dispatch moved out of `bot.py` — `on_message` now calls `_dispatch_chat`,
and the cog decides everything. Role pings and un-pinged replies are newly
answered; both were previously missed because the old check only looked at
`message.mentions`.

**Not done, in rough priority order:**

1. **Nothing tunes itself.** The defaults are guesses, particularly
   `chat_ambient_multiplier` and the per-trigger `chance` values. Watch a real
   server for a week and adjust.
2. **DMs never trigger.** `handle_message` skips trigger matching without a
   guild, so a DM only works through a mention or `/chat`. Probably worth
   letting a DM be answered plainly, but that is a token-cost decision.
3. **Rumours are still one-directional.** They are stored against the target and
   recalled when talking *to* them. Nothing spreads them to third parties the way
   the D&D rumour model does (`helpers/dnd/mind/rumour.py`), and that would be
   the obvious next step if the feature earns it.
4. **No per-channel personality.** Everything is per server. A quiet
   announcements channel and a shitposting channel get the same bird, minus the
   deny-list.
