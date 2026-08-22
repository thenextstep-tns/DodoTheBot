# Playtest script — P0 through P2

Everything through P2 is proven by 305 unit tests and by nobody at all. This is
the script for the second kind of proof.

**Read the expectations before you type.** Each act ends with a falsifiable
claim. The point is not to admire the output — it is to catch the acts where the
output is *technically correct and completely boring*, because that is the risk
the roadmap names and the one tests cannot see.

Budget about 40 minutes. Do it in one channel of your test server, in order —
later acts depend on state earlier ones create.

Notation: **`>`** is what you type in Discord. **→** is what should come back.
**🚩** is a bug — stop and write down what you saw.

---

## Act 0 — A table exists

```
> /campaign create name:Harbour ruleset:freeform
```
→ "Harbour" created, ruleset **Freeform**. You are its GM because you made it.

```
> /character create name:Ondry role:harbour thief pronouns:he/him
> /character sheet
```
→ A sheet with stats. Note two or three numbers down — you need them in Act 2.

Now open the panel: **🎲 Tabletop** on your guild's nav bar. Harbour should be
listed with `1 PC · 0 NPCs · 0 scenes`, day 1, and an **Open →** link.

🚩 If the campaign card is missing but `/campaign list` shows it, the panel and
the bot disagree about the guild — that is a real bug.

---

## Act 1 — A roll actually changes the outcome

```
> /dice expression:2d6+3
> /dice expression:4d6kh3
> /dice expression:1d20adv
```
→ Three rolls, each showing the individual faces, not just a total. `kh3` should
drop the lowest of four; `adv` should show two d20s with the higher taken.

```
> /check approach:finesse dc:7 description:slipping past the night watch
> /check approach:finesse dc:12 description:slipping past the night watch
```
Run each **five times**.

Harbour is a **freeform** campaign. Freeform has four approaches — `force`,
`finesse`, `wits`, `presence` — and resolves on **2d6 + your rating**, so with
`finesse +2` every roll lands between 4 and 14. Its default DC is **7**. Do not
bring d20 numbers here: `dc:20` is not hard, it is *impossible*, and five
attempts at it tell you nothing.

| DC | fail | cost | success | triumph |
| --- | --- | --- | --- | --- |
| 7 | 16% | 41% | 25% | 16% |
| 12 | 83% | 16% | 0% | 0% |

→ DC 7 should mostly land somewhere other than failure; DC 12 should mostly
fail. Across the ten you want to see **all four degrees** — not just pass/fail.
DC 7 is the only band where triumph is reachable, which is why it is the one
used here.

🚩 If DC changes nothing, resolution is not consuming the roll.

**The real question:** does the check embed tell you anything a plain dice roller
wouldn't? If not, that's a note for P4, not a bug.

---

## Act 2 — The sheet came from a ruleset, not from a template

```
> /campaign create name:Deeps ruleset:srd5e
> /character create name:Vell role:wizard campaign:Deeps
> /character sheet campaign:Deeps
```
→ Vell's ability array should differ from Ondry's — different ruleset, different
role. This is the direct regression test for the old cog handing every character
an identical block.

🚩 Identical arrays for a thief and a wizard means the ruleset abstraction has
collapsed.

Then go back to Harbour for everything below:
```
> /campaign info name:Harbour
```

---

## Act 3 — Fog of war holds

```
> /lore add title:The Compact text:A shipping cartel that runs the north dock. kind:faction weight:0.8
> /lore add title:Marla's debt text:Marla owes the Compact 400 marks and they have stopped asking politely. secret:True weight:0.9
> /lore list
```
→ The secret's confirmation is **ephemeral** (only you saw it). `/lore list` as
GM shows both.

```
> /scene open title:The harbour office
> /look
```
→ An ephemeral player-view embed: the scene, who's present, your beliefs, and
retrieved facts — containing **The Compact** and **not one word** of Marla's debt.

🚩 If the secret appears in `/look`, stop. That is the single worst bug this
system can have, and `tests/test_dnd_p1.py` asserts against exactly it.

Also open the campaign in the panel while the scene is live. The scene and the
event count should both be there.

---

## Act 4 — Two people, two heads

```
> /npc create name:Marla role:harbourmaster culture:dockborn pronouns:she/her importance:0.8
> /npc create name:Sennet role:dock guard culture:dockborn importance:0.3
> /npc list
```
→ Each creation reports a **trait description** — and Marla's should not read
identically to Sennet's. Note them down.

```
> /gm believe who:Marla claim:Ondry works for the Compact about:Ondry true:False
> /gm knows who:Marla
> /gm knows who:Ondry
```
→ Marla holds a belief about Ondry that is *false*, and Ondry's list does not
contain it. Two people, two different pictures of the same world.

```
> /look
```
→ Still shows **your** beliefs only. Marla's suspicion is not visible to Ondry.

**The real question:** knowing Marla wrongly thinks Ondry is Compact — does that
make you want to play the next scene? If it doesn't, the fog-of-war model is
correct and inert, and that matters more than any test result.

---

## Act 5 — Two witnesses to one night

This is P2's headline claim. Same event, two heads, different memories.

```
> /gm remember who:Marla what:a knife fight outside the harbour office feeling:-0.8 detail:green lantern clarity:1.0
> /gm remember who:Sennet what:a knife fight outside the harbour office feeling:-0.4 detail:green lantern clarity:0.35
```
→ Both confirmations report a **salience** and a sentence explaining what is
holding the memory in place. Marla's salience should be clearly higher.

**Write both salience numbers down.** You need them in Act 7.

```
> /npc mind who:Marla
> /npc mind who:Sennet
```
→ Both inspectors show the memory. Sennet's should already be **thinner** —
fields missing that Marla has, because at clarity 0.35 pieces were never taken
in at all, not decayed away later.

🚩 If Sennet's memory is as complete as Marla's, perception is not being applied
at encoding.

Try the floor while you're here:
```
> /gm remember who:Sennet what:something in the fog feeling:0 clarity:0.02
```
→ Below 0.05 perception nothing registers. He was there and remembers nothing.

---

## Act 6 — Forgetting has an order

Memory fields have different half-lives, in days:

| Field | Holds for |
| --- | --- |
| when (time & place) | 7 |
| details | 14 |
| participants (faces) | 45 |
| valence (how it felt) | 120 |
| gist (that it happened) | 240 |

So the order things go is: *when* → *details* → *faces* → *feeling* → *substance*.

```
> /gm advance days:10
> /npc mind who:Marla
```
→ "When" should have gone vague first — the inspector renders time as
*exact → day → season → year → sometime* as fidelity drops.

```
> /gm advance days:30
> /npc mind who:Marla
```
→ Details now blurring or hedged. Gist and feeling still solid.

```
> /gm advance days:300
> /npc mind who:Marla
> /npc mind who:Sennet
```
→ Marla should still know roughly what happened and how it felt. Sennet's may be
gone entirely, or reduced to a summary line. **The gap between them should have
widened**, not stayed flat.

🚩 If both degrade at the same rate, salience and retention are not reaching the
decay curve.

**Power law, not a timer.** The curve is `R(t) = (1 + t/S) ** -0.5`, so more is
lost in the first week than in the fifth year. You can see it: the change from
Act 6's first `advance 10` should be visibly larger than the change from the
last `advance 300`, despite thirty times the elapsed time.

---

## Act 7 — Something that marks a person permanently

Look at the salience you noted in Act 5. Imprints form at **0.85**, or after
**8** recalls of the same memory.

If Marla's was below 0.85 (likely — `/gm remember` records her as a witness, not
a participant, so relevance is dampened), lower the bar for the test:

```
> /gm tune show
> /gm tune set key:imprint_threshold value:0.4
> /gm remember who:Marla what:the night the boat burned with her brother aboard feeling:-1.0 detail:burning pitch clarity:1.0
```
→ The confirmation should end with **"that will mark them permanently"**.

```
> /gm advance days:3650
> /npc mind who:Marla
```
→ Ten years on. Every ordinary memory should be a ruin. **The imprint should be
byte-identical** — full clarity, no fields lost, half-life infinite.

🚩 An imprint that degraded at all is a bug. This one is asserted in the test
suite, so if it fails here the failure is in the wiring, not the model.

---

## Act 8 — Misremembering, not just forgetting

Below clarity 0.2 a field is either dropped or **filled with a plausible wrong
value drawn from that character's other memories**. Chance is 50% by default.

```
> /npc mind who:Marla
```
Read her faded memories closely. Look for a face or a detail that is *stated
confidently and belongs to a different memory of hers*. That is confabulation,
and it is the feature — she does not know what she has forgotten.

To force it, if nothing shows:
```
> /gm tune set key:memory_confabulate_chance value:1.0
> /gm advance days:200
> /npc mind who:Marla
```

**The real question:** when you find a confabulated detail, is it *interesting* —
does it read like a person misremembering, or like a database returning the
wrong row? This is the single most important judgement call in the whole script.

---

## Act 9 — Looking doesn't change the mind, asking does

Two commands touch memory and only one of them is read-only.

```
> /npc mind who:Marla
> /npc mind who:Marla
```
→ **Identical.** Same recall counts, same salience, same clarity. The inspector
must never be an observation that disturbs its subject.

🚩 Any drift between two consecutive inspections is a bug.

```
> /gm recall who:Marla cue:green lantern
```
→ A recall embed, and if the cue matches an imprint it surfaces separately and
first — the burned NPC reacts to fire *before* reasoning about it.

```
> /npc mind who:Marla
```
→ **Now something has changed.** Recall count up; the gist firmed up; a present
detail may have leaked in as a false one. Recall rewrites, deliberately.

Cues are lowercased and split on whitespace, then matched against the **detail**
you gave at `/gm remember` — so `green lantern` works and `a green lantern, I
think` matches on the useful words too.

---

## Act 10 — People feel things about each other

```
> /gm relate who:Marla toward:Ondry what:helped description:he paid her debt to the Compact without being asked
> /gm relate who:Marla toward:Ondry
> /gm relate who:Ondry toward:Marla
```

`what:` is **not** free text — it is one of sixteen predefined event kinds, each
carrying its own multi-axis delta: `attacked, bested, betrayed, gifted, healed,
helped, insulted, kept_word, lied, met, praised, saved, stole, talked,
threatened, travelled`. The kind is what moves trust, warmth, debt and fear.
`description:` is your prose, and it becomes **what they both remember**. Leave
`what:` blank to look without changing anything.

→ The reply may still say **"a stranger"**. That is not a failure: one favour
from a cold-natured harbourmaster lands just under the threshold where the
one-line summary changes. The numbers moved — the look-only call above shows all
five axes and both directions, and that is where to check.

→ **Both of them now remember it.** Run `/npc mind who:Marla` and
`/npc mind who:Ondry`: the same event, encoded separately, so the two accounts
can already differ. Then:

```
> /gm recall who:Marla cue:compact
```
→ The memory comes back, because the cues were extracted from your description.
Without a `description:` the gist is templated from the kind instead — *"Ondry
helped Marla"* — so an undescribed event still leaves a memory rather than none.

→ Multi-axis feelings (trust, warmth, debt, fear). The second call with no
`what:` just looks.

→ **The two directions should not match.** Marla owing Ondry is not the same
relationship as Ondry being owed, and if the panel shows them as mirror images
the model has quietly become symmetric.

Then check it compounds with memory:
```
> /gm remember who:Marla what:Ondry standing between her and the Compact's men feeling:0.7 detail:north dock clarity:1.0
> /npc mind who:Marla
```
→ A memory involving someone she now has feelings about should score higher on
the social contribution to salience than the same event with a stranger.

---

## Act 11 — Every knob turns, including all the way off

The standing rule is that nothing is baked in and anything that can be softened
can be switched off entirely. Verify the strongest version of that:

```
> /gm tune set key:memory_decay_rate value:0
> /npc mind who:Sennet
> /gm advance days:3650
> /npc mind who:Sennet
```
→ `/gm advance` should report the world as **frozen**, and Sennet's memories
should be byte-identical across a decade. Forgetting is off.

```
> /gm tune set key:memory_decay_rate
> /gm tune show
```
→ Blank value clears the override back to inherited. `/gm tune show` should say
where each value comes from — default, server, or campaign.

Now the same knob from the other surface: panel → 🎲 Tabletop → the campaign →
tuning section. **The value you set in Discord must already be showing there.**

🚩 Two surfaces disagreeing about a tunable means the resolution order broke.

---

## Act 12 — The inspector as the demo

Panel → 🎲 Tabletop → Harbour → click **Marla**.

This page is the P2 deliverable — the thing that is supposed to prove the phase
worked. Look for:

- Traits and needs as meters, not numbers
- Every memory with **per-field clarity**, so you can see what has gone
- A line per memory explaining *why it is sticking* — salience, her retention
  faculty, her values
- Beliefs, with source and confidence
- Feelings toward others **and** how others feel about her, separately

**The real question, and the only one that matters:** reading this page, do you
know who Marla is? Could you play her at a table from it — not "look up her
stats", but *speak as her*?

If yes, P2 worked and P3 is worth building.
If no, write down precisely what is missing. That list is worth more than the
next phase.

---

## Cleanup

```
> /scene close
```
Leave the campaigns — a second session of this script wants the aged state.

---

## What to send back

1. Every 🚩 you hit, with the command and what came back.
2. Act 8's answer: did a confabulation read like a person or like a bug?
3. Act 12's answer: could you play Marla from that page?
4. The one place you were *bored*. That is the most useful line in the report.
