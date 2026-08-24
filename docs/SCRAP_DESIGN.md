# Cat scrap — design in progress

**Status: design, not shipped.** The engine and a balance sandbox exist. There is
no command, nothing is wired to Discord, and no cat in the database is affected
by any of it. This document is the state of the argument, not a spec.

Where things are:

| Thing | Where |
| --- | --- |
| The engine | `helpers/scrap.py` — pure Python, no Discord, no Mongo |
| The sandbox | `/scrap` in the panel, bot-owner only (`web/routes.py`, `_scrap_html`) |
| Standalone lab | `py tests/scrap_lab.py` → `http://127.0.0.1:8898/scrap`, runs without the bot |
| Tests | `tests/cases/test_scrap.py` |

## The shape of it

You are not the cat. You are a human on the sidelines with a laser pointer, and
you cannot make a cat do anything. That premise is where the humour and the
mechanics both come from: your inputs are suggestions, and they can land on the
wrong cat.

A fight is six rounds of self-resolving cat violence — puffing, sideways
hopping, the yowl — with one **prop** click per side per round. No reaction
windows, no timing: the mid-race click already owns that mechanic in `racing`,
and timing-based interference has been tried here and is too fiddly.

## Four rules hold it up

**A class is derived, never stored.** A cat's class is its two governing
attributes *in order*. Every pet already in the database has one, so nothing
needs migrating, and *training shifts it* — which is the progression hook. Only
four of the twelve ordered pairs are reachable from a claim roll.

**A name has to say its attributes.** If you have to look up which stats a class
uses, the name has failed. Every class carries a `why` field justifying itself,
and the sandbox prints it, so the rule can be argued with on the page.

**Resistance dulls, it never negates.** Every prop names the attribute that
resists it, and a resisted effect still lands at 25% strength however absurd the
stat. No prop is ever a dead play.

**The ult charges off damage taken.** The player who is losing reaches the vacuum
first. That is the anti-snowball valve, doing balance work that would otherwise
come out of per-class numbers.

## The thirteen classes

Which attribute **leads** picks the perk family; the second picks the twist.

| Class | Pair | Rolled from | Perk | Why the name |
| --- | --- | --- | --- | --- |
| 🐅 Pouncer | STR›AGI | — | First swipe of the fight is doubled | A cat's whole weight, delivered at speed |
| 🍞 Loaf | STR›INT | — | Thorns; cannot be repositioned | Heavy and unbothered; sitting still is the clever part |
| 🐈‍⬛ Chonk | STR›CHA | Chonk | Flat damage reduction | Mass people adore instead of fearing |
| 🏓 Ricochet | AGI›STR | Zoomies Pro | Counterattacks on a dodge | Comes off the walls, and back off them |
| 👻 Ghost | AGI›INT | — | Vanishes; the hit that breaks cover always crits | Quick, and clever enough to be quick unseen |
| 😼 Zoom Gremlin | AGI›CHA | — | Chance of a second action in a round | Speed, no plan, total impunity |
| 🚪 Door Barger | INT›STR | — | Ignores defensive perks entirely | Works out the door, then goes through the door |
| 🗄️ Shelf Stalker | INT›AGI | Smarty Pants | On a cycle its attack cannot be dodged | Worked out the high route and is quiet enough to take it |
| 😻 Purrsuader | INT›CHA | — | Stacking haze that saps enemy damage | Worked out *you*, and is using you |
| 👑 Lap Tyrant | CHA›STR | — | Chance the enemy simply cannot act | Rules by sitting on you |
| 🧶 Ankle Weaver | CHA›AGI | — | Props aimed at it land on the thrower's cat | Underfoot, adored, impossible to step on |
| 🍽️ Second Dinner | CHA›INT | Aww summoner | Heals from damage dealt | Has definitely not been fed, and knows who to tell |
| 🐾 Alley Cat | no specialism | — | Copies an enemy perk; hits with its average | No best stat and no worst one |

## Balance: classes decide nothing

Every combat number comes from a cat's stat **total** alone, so all 169 matchups
sit inside 35-65% before anybody shows anything, and a 40/5/5/5 cat is exactly
the same size of cat as a 14/14/14/13 one. The class perks that used to live here
ran the spread from 23% to 66% and are gone. A class is now a personality: it
decides what a cat does when shown a thing, and the things are the whole game.

Draws are gone too. Two exactly level sides toss for it, because a draw pays
nobody and records nothing.

**David and Goliath.** A cat facing a bigger total crits more and hits harder,
on a power law rather than a ramp, so the curve falls smoothly instead of
cliff-edging at a threshold. A cat at half its opponent's total still takes
about 38%. At a third, it does not, and should not.

## What a fight leaves behind

| | |
| --- | --- |
| Object effects | This fight only. Held in `Fighter.mods`, never written down |
| Reach | Every cat in the room reacts, both sides, per its own class |
| Outnumbered | Deltas scale by `other_team / own_team`, so 3-against-5 swing 1.67x in both directions |
| Spoils | Each loser gives a point of both governing attributes; a winner takes those two |
| Record | `fightswon` / `fightslost`, incremented for the first time since the field was invented |
| Recovery | The gym, which is the only way back up |

`helpers/scrap_store.py` writes all of that; the engine stays free of Mongo.

## Settled

- Roster of up to **10** cats, put there by summoning them.
- **Taunt** a cat by name to start a fight; intellect is the only resistance.
- **Psps** a cat to lure it — charm decides whether it comes *and* whether it
  psps one of yours back instead.
- Props: laser, can, cucumber, slipper, and the **vacuum as the ult**.
- Dogs, sweetrolls and pumpkins get thrown in as props.
- Titles accrete from the fight log ("Bobo, who has eaten four dogs").

## Open, and blocking a spec

1. **The INT family's conditional perks** — the balance problem above.
2. **Champions.** Four belts, one per leading attribute, was the sketch.
3. **Pink slips.** Winner takes the loser's cat, but only for title fights.
4. **Crowd interference.** Endorsed, provided the target is unambiguous: colour
   and sigil per side, target named inside the button label, per-person cap.
5. Whether the whole thing is 20–30s or the current six rounds, nearer 35–40s at
   a readable pace.

## Standing constraints for whoever builds this

- Every number is already in `scrap.TUNING`; when one is right it moves to
  `helpers/parameters.py`, never a constant in a cog.
- The engine must stay free of Discord and Mongo. The sandbox being the same
  code as the fight is the only reason the sandbox is worth anything.
- `panel.js` mirrors `classify()` for its live class label. The two lists must
  agree — `tests/cases/test_scrap.py` checks that they do.
- Visual and terse. Two bars, a status icon and one line of text per beat.

## The reaction grid (built, seeded thin)

Every object down the side, every class across the top. The game is exploration:
finding out that a Loaf sits on your trousers and a Zoom Gremlin shreds them.

| Thing | Where |
| --- | --- |
| Catalogue builder | `helpers/emoji_catalogue.py`, rebuild with `py -3 helpers/emoji_catalogue.py` |
| Catalogue data | `helpers/data/emoji_catalogue.json` - 1,401 distinct objects |
| Layers and storage | `helpers/reactions.py`, collection `EmojiReactions` |
| The page | `/guild/{gid}/reactions`, admins and mods (`SCOPE_CONFIG`) |
| Renderer | `web/reactions_page.py` |
| Offline | `py tests/scrap_lab.py` then `/reactions` - in-memory, cannot touch live data |
| Tests | `tests/cases/test_reactions.py` |

**The catalogue is 1,401, not 3,700.** Collapsed on purpose: single codepoints
only (no ZWJ compounds), no skin tones, no flags, and colour and gender words
stripped before deduplication so nine coloured circles are one circle and the
man and woman farmer are one farmer. The rules live at the top of
`emoji_catalogue.py` and are the only opinion involved.

**Three layers answer any cell:** this server's row, the global row, then the
shipped `SEED`. Nothing is pre-written to the database, so a fresh server
inherits everything and an edited server stores one row. Clearing an override
uncovers the layer underneath rather than emptying the cell - the API returns
the *resolved* cell after a write for exactly this reason.

**Coverage today: 104 of 18,213 cells (0.6%).** Eight objects are seeded across
all thirteen classes - trousers, cucumber, box, broom, skull, fish, candle,
pumpkin. That is the shape proven end to end, not the content.

**Filling the rest is the open job.** ~18,000 cells at roughly a line each. The
realistic route is batches by group: write a screenful, read it back on the page,
keep what lands. House style from the seed: one thing happens, it is specific, it
is over inside a line, and no em dashes.
