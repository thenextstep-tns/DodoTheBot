# Ideas parking lot

Things worth building that are **not yet planned**, kept out of the roadmap on
purpose. The roadmap is a commitment; this is not. An idea lives here until it
has a phase, a shape and a reason to be built then rather than later — at which
point it moves into `12-ROADMAP.md` and stops being an idea.

Nothing here is scheduled. Nothing here should be implemented because it is
here. If you are picking work up, `12-ROADMAP.md` is the file you want.

**Adding an entry:** what the idea is, what already exists that it could lean
on, where it fits the world, what has to be true first, and when it makes sense
to build. Half a page. If it needs more than that it is a design doc, not an
idea.

---

## 1. Telepathy — reading a mind as a player skill

*Raised 2026-08-22.*

`/npc mind` is a GM tool: it shows disposition, needs, memories with per-field
clarity, and why each memory is sticking. Players cannot run it and should not
be able to — but *some* characters, in some settings, should be able to read a
person, and be bad at it.

The idea: keep the command GM-only by default, and let a character with a
**telepathy skill** run a version of it whose fidelity is proportional to their
rating and their roll. A weak telepath does not get a refusal — they get a
**worse reading**, and cannot tell the difference.

### What already exists

More than it looks like.

- **The gate is already built.** `/npc mind` runs `context.require_gm(...)`, so
  restricting it is not work — opening it selectively is.
- **Per-field fidelity rendering already exists.** `05-MEMORY.md` renders every
  memory field at a clarity: stated plainly above 0.7, hedged above 0.3, and
  below 0.2 either blank *or replaced with a plausible wrong value drawn from
  that character's other memories*.
- **Beliefs already carry source and confidence** (`03-KNOWLEDGE-BASE.md` §4),
  with `mutations` and `shared_with` fields.

### The shape it should take

**Do not build an obfuscation layer.** A bad reading is not a new rendering
mode — it is the existing renderer with a **clarity ceiling** imposed by the
roll. Cap every field at `min(actual_clarity, read_quality)` and the current
code already produces exactly the right output.

That gives the feature its best property for free: below the confabulation
threshold a field is not blanked, it is **filled with a plausible wrong value**.
A poor telepath does not learn nothing — they learn something false, confidently,
and have no way to know. That is worth more than any amount of hedged prose, and
it costs nothing to implement because forgetting already works that way.

Two consequences worth designing in:

- **A reading should write a belief, not return a string.** The telepath forms a
  `Belief` about the target with `confidence = read_quality` and `source =
  telepathy`. It then decays, propagates and can be wrong like any other belief,
  and P3's rumour machinery carries it without modification. The embed is a
  *view* of that belief, not the payload.
- **Reading someone is an event.** Emit a `WorldEvent`. Whether the target
  notices is then a second check against their own traits — a paranoid,
  high-diligence NPC catching someone in their head is a scene, and the
  relationship delta writes itself.

### What has to be true first

- **Character advancement does not exist.** Nothing in `04-ENTITIES.md` or
  either ruleset has XP, levels, or skill improvement, so "developed gradually"
  has nowhere to live. This is the real blocker and it is bigger than the idea:
  a progression slice is its own piece of design.
- **Both rulesets need an answer.** `srd5e` has no telepathy skill in the SRD
  list; `freeform` has four approaches and no skills at all. This is probably a
  campaign-level *tag* on a character rather than a ruleset skill — which is the
  more interesting answer anyway, since it keeps the abstraction clean.
- **Tunables, per the standing rule:** `telepathy_enabled` (default **off** —
  most campaigns are not psychic), `telepathy_reach` (how much rating moves
  quality), `telepathy_detectable`, and a floor/ceiling on read quality. Off by
  default means a table that does not want mind-reading never sees it.

### When

**After P3, not before.** Today a mind contains needs and memories. After P3 it
also contains *intentions* — what this person is about to do and the term
breakdown of why. Reading that is worth a skill and a roll; reading a needs bar
is not. Building it earlier means shipping the mechanic before the thing that
makes it interesting exists.

Sequenced behind the progression slice it depends on, so realistically: a small
P3.5, or fold it into P5 alongside the drama state, where "what does this
character know about that character" is already the currency.
