# Playtest — the minds, and what they do about each other

The first playtest (`PLAYTEST.md`) proved the machinery exists: sheets from a
ruleset, fog of war, two witnesses to one night, memory that forgets in order.
It stopped at P2 and its verdict was that the game around the simulation was not
playable.

**This one is about the part that came after: people deciding things.** You will
put four people in a room, give two of them a reason to care about each other,
and then push. Every act asks the same question — *did somebody do something a
person would do, and can you find out why?*

---

## How to read this

Each act is **what you type**, **what you should see**, and **what it would mean
if you saw something else**. Where a step is testing something specific, it says
so.

Two things to keep open:

* the channel you play in;
* the panel — `Tabletop → your campaign → 🧭 Archetypes` and any NPC's inspector.

Write down anything that made you stop and re-read. That reaction is the most
valuable output of this document; the bugs are a bonus.

**A note on time.** `/gm advance` now does two things: it ages minds *and* lets
people act. Advance small amounts (a quarter day, a day) to watch a scene
develop; advance a week to see whether the world holds together without you.

---

## Act 0 — A room, and four people in it

```
/campaign create name:The Ashen Dock ruleset:freeform
/scene open title:The harbour office
/npc create name:Marla Venn role:harbourmaster culture:tidewater
/npc create name:Ondry Kass role:dockhand culture:tidewater
/npc create name:Sera Vaunt role:merchant culture:city archetype:merchant
/npc create name:Rook role:enforcer culture:highland archetype:predator
/gm present who:Marla Venn
/gm present who:Ondry Kass
/gm present who:Sera Vaunt
/gm present who:Rook
```

**Expect:** four NPCs, each with a disposition line. Two of them were *asked*
for an archetype; two were rolled and had one *noticed* in them.

**Look:** open Sera's and Rook's inspectors → **What they reach for**.

- Sera and Rook should lead with the archetype you named.
- The others should have been given one that suits whoever the dice produced.
- The **fit** column is the interesting one. Somebody who is *"merchant in name
  only"* is the good case, not a bug: you asked for a type and got a person.

> **Testing:** archetypes work in both directions. If every asked-for NPC is
> identical, `pack_shaping` is too high. If naming one changes nothing, it is 0.

---

## Act 1 — Nobody is a blank

```
/npc mind who:Rook
```

**Expect:** disposition, a body, a couple of memories he came into the world
with, and an archetype mixture.

**The question this act is really asking:** does Rook read as somebody, before
anything has happened to him? If he reads as a statblock, say so — that is the
P2 verdict repeating, and it matters more than any bug.

---

## Act 2 — Give two people a reason

```
/gm relate who:Ondry Kass toward:Marla Venn what:helped description:She covered his shortfall at the tally without being asked.
/gm relate who:Rook toward:Ondry Kass what:threatened description:Rook put a hand on the ledger and did not move it.
```

**Expect:** each is recorded, and **both parties remember it differently.**

```
/npc mind who:Ondry Kass
/npc mind who:Marla Venn
```

- Ondry should hold *both*: a warm one about Marla, a frightening one about Rook.
- Marla's memory of covering the shortfall should be **fainter** than Ondry's.
  It cost her nothing; it was his week.

> **Testing:** stakes. If the two memories are equally vivid, stakes are not
> reaching memory salience — that was a real bug once.

---

## Act 3 — Give somebody something to want

```
/gm advance days:0.1
```

Then in the panel, open **Ondry's inspector → What they want** and give him:

- kind **Get closer to**, about **Marla Venn**, priority **0.9**
- text: *"get Marla to speak for him at the hearing"*

And give **Rook**:

- kind **See them suffer**, about **Ondry Kass**, priority **0.8**
- text: *"make an example of the dockhand"*

**Expect:** the *What they want* table shows each goal with **Cares**,
**Attention**, **Progress** and **Pressing**, plus a line saying how the person's
attention is divided.

> **Testing:** attention. With one goal each they should be near 0.9 of a whole
> person. Add three throwaway goals to Ondry and watch his real one drop to
> around a tenth. That is the mechanic — you cannot pursue everything.

---

## Act 4 — Let them move, and watch what they do

```
/gm advance days:0.25
```

**Expect** — and this is the act the whole document exists for — a report that
ends with something like:

> **While that happened:**
> · **Ondry Kass** spoke to **Marla Venn** — closer to *get Marla to speak for him*
> · **Rook** hung back and watched
> · **Sera Vaunt** spoke to **Rook**
> · **Marla Venn** did nothing

**What to check:**

- Did anyone do something that made sense *for them*? Rook watching rather than
  lunging is the middle band working, not the engine failing to act.
- Did a goal move?
- Does the mixture feel like four different people, or four coin flips?

> **If everybody did nothing**, that is a real finding and worth reporting
> immediately. The needs model was changed for exactly this reason during the
> build; a regression there makes the whole world inert.

---

## Act 5 — Ask why

```
/npc why who:Ondry Kass
/npc why who:Rook
```

**Expect:** the choice, what it beat, and the terms that decided it — *"it served
what they are after +0.51, what it might cost −0.90"*.

**This is the act that decides whether any of this was worth building.** Read the
reasons and ask yourself: do they explain the behaviour, or merely accompany it?
If the numbers do not persuade you that the NPC had a reason, say so plainly.

> **Testing:** explainability (`06-DECISION-ENGINE.md` §12).

---

## Act 6 — Put your thumb on it

Now act as a player, and see whether the world responds to *you*.

```
/check approach:presence description:I tell Rook the harbourmaster is watching him
```

Then record what your character actually did:

```
/gm relate who:Rook toward:<your character> what:threatened description:You put yourself between Rook and Ondry.
```

```
/gm advance days:0.25
/npc why who:Rook
```

**Expect:** Rook's reasoning to have *changed* — the risk term should now carry
your character, and his feelings about you should appear.

**What to look for:** does the world bend around a human action, or carry on as
though you were not there? This is the single most important question in the
document.

---

## Act 7 — Change what somebody believes

```
/gm believe who:Marla Venn about:Rook claim:Rook is being paid by the Compact
/gm knows who:Marla Venn
/gm advance days:0.25
/npc why who:Marla Venn
```

**Expect:** Marla now holds a belief she did not have, and it should be visible
in what she considers doing about Rook.

> **Testing:** NPCs act on what they *believe*, not on what is true. Mark the
> belief false in the panel and confirm **she still acts on it** — that is the
> whole design, and if she does not, the view is leaking world truth.

---

## Act 8 — Let a week go by without you

```
/gm advance days:7
```

**Expect:** clocks move, rumours travel, several people act, at least one goal
advances, and nothing crashes.

Then:

```
/npc mind who:Ondry Kass
/npc list
```

**What to check:**

- Is Ondry's goal further along than it was?
- Has anybody's **archetype mixture** shifted? Rook, if he has been menacing
  people, should be drifting further toward predator.
- Do the memories formed during the week read as things that happened, or as
  log noise?

> **Testing:** the P3 acceptance criterion, and drift.

---

## Act 9 — The awkward questions

Not tests. The things the last playtest was actually about.

1. **How many commands did you have to remember?** Which ones did you have to
   look up twice?
2. **Did you ever not know what to do next?** Where?
3. **When something interesting happened, did you find out from the game or from
   the panel?** If it was the panel every time, the payoff is still invisible at
   the table and that is the next thing to fix.
4. **Was any of it worth it?** The engine is deep. Did the depth reach you.
5. **What did you want to type that does not exist?**

---

## Optional — the adult layer

Off by default and gated twice on purpose. Only if your table wants it:

1. Campaign page → **🛑 Lines** → clear *sexual content*.
2. **This game's rules → 🍞 Needs** → switch on *Desire as a body need*.

Until you do **both**, the setting will say it is being overruled by a line.
That is deliberate: agreeing to play something and enabling the machinery for it
are two decisions.

Then `/gm relate ... what:flirted`, `what:courted`, `what:rebuffed` become
available, an **Allure** control appears on each inspector, and attraction
becomes directed — somebody can be drawn to one person and repelled by another,
and repulsion sours the whole acquaintance rather than sitting in its own column.

---

## What to send back

- Every line that made you stop.
- Anything that did nothing when you clicked or typed it.
- Your answer to Act 9.4, in your own words, however blunt.

The last playtest's verdict shaped six increments of work. This one is meant to
do the same.
