# Safety & Consent

Not in the original brief. It is here because a public roleplay product with
LLM-generated output and per-server tenancy cannot ship without it — and because
the tabletop community expects these tools by name.

Cheap to build (mostly settings and a filter), and it protects the business.

---

## 1. Lines & veils

Standard tabletop consent tooling, per campaign, set at session zero and editable
by any player at any time.

- **Lines** — never appears. The engine will not generate it; if a player writes
  it, the GM is notified and the content is not narrated.
- **Veils** — happens off screen. The event occurs in the simulation, but is
  narrated as a cut: *"You find the room afterward."*

```jsonc
"safety": {
  "lines": ["sexual content", "harm to children", "torture"],
  "veils": ["graphic gore", "on-screen death of a PC"],
  "intensity": "moderate",          // gentle | moderate | harsh
  "x_card_enabled": true,
  "notify_gm_on_block": true
}
```

Defaults are conservative: a fresh campaign starts with lines on sexual content
and harm to children, and `intensity: moderate`. A GM opting into harsher content
is a deliberate act, and it is audited.

## 2. The X-card

A button on every scene card. Any player, any time, no explanation required:

1. The current beat is **retconned** — trivial, because events are a log
   (`02-DATA-MODEL.md` §7) and `/gm undo` already exists.
2. The scene rewinds to before the beat.
3. The GM is notified privately; other players see a neutral "the scene rewound".
4. The blocked content is recorded to the campaign's lines automatically.

Step 4 is what makes it a *tool* rather than a panic button: the table does not
have to have the conversation twice.

## 3. Content filtering

Three layers, in order:

1. **Prompt constraints** — lines and veils are injected into every render task's
   system prompt. Cheap and catches most of it.
2. **Output filter** — every rendered output is checked before posting. Layered:
   a term list from lines/veils first (free, deterministic), then an optional
   moderation endpoint when the backend has one.
3. **Simulation constraints** — some things never enter the event stream at all.
   Actions matching a line are not proposable by the decision engine, so an NPC
   cannot *decide* to do them.

Layer 3 is the one competitors skip, and it is the reliable one: filtering output
is a race, but a candidate action that is never generated cannot be narrated.

On a block: retry once with tightened constraints, then fall back to the
deterministic template (`08-LLM-LAYER.md` §5). Never post raw filtered output,
never silently drop the turn — the GM is told what happened.

## 4. Player-to-player

RP is a social surface, so the usual protections apply:

- The existing moderation and anti-spam cogs still run in scene threads.
- A GM can mute a player from a campaign without a server-level action.
- Direct-address between PCs is bounded by the same content filter.
- Report path: `/dnd report` — snapshots the scene state and notifies the server
  admins, not just the campaign GM.

## 5. Data & privacy

- Campaign content is **per guild** and never leaks across tenants — enforced by
  the scope filter in `store/repo.py` (`01-ARCHITECTURE.md` §7) and covered by the
  tenant-isolation test.
- Player-written text is sent to whichever LLM backend the server has configured.
  **This must be stated plainly** in the campaign settings page, including which
  provider, since a server on BYO-key has chosen their own processor.
- A campaign can be exported and deleted by its GM; deletion is real, not a flag.
- With `backend=null`, no player text leaves the host at all. Worth advertising —
  for some groups it is the deciding feature.

## 6. Where the engine helps

The simulation architecture gives some safety properties for free:

- **NPCs cannot leak secrets they do not know** — `render_dialogue` receives only
  the NPC's beliefs (`08-LLM-LAYER.md` §4), so this is structural rather than a
  prompt instruction the model might ignore.
- **No prompt injection into world state** — nothing a player types becomes truth;
  it becomes an *intent* that the simulation validates. "You find a +10 sword"
  typed by a player resolves to a failed action, not an item.
- **Escalation is governed** — the drama manager forces a `respite` when tension
  stays high (`07-NARRATIVE-ENGINE.md` §7), so unattended play cannot spiral.

## 7. What we do not do

No automated psychological profiling of players, no sentiment scoring of people
(the chat cog's relationship score is about the *bot's* mood and stays there), no
storage of player messages beyond campaign content, and no training on user
campaigns.
