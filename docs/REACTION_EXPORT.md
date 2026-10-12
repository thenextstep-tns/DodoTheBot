# Cat scrap reaction lines — export for writing outside this session

This is a self-contained brief. Paste the whole thing into Gemini (or any other
model) and ask it to write the next batch. No other context is needed — the
rule, the classes, and the object lists are all below.

## The rule

The object joins the fight. It is thrown in, rolled in, loosed, opened ringside,
or lands in the middle of it. It is never just held up for the cat to look at —
it is a thing now present in the arena that the cat has to deal with, use, or be
beaten by.

**What the cat does with it is the joke.** A clever cat turns it into an
advantage, a strong cat picks it up and throws it, a stupid cat gets tangled in
it, a charming cat gets somebody else to hold it. The same object should do a
different *kind* of thing for each of the 13 personalities below — not just a
different sentence, a different tactic.

**Bigger objects can favour the strong.** Don't assume every object is a hazard.
A plane in the ring is not automatically bad news — a Chonk can pick it up by
the tail and throw it. That's the correct, funny outcome.

**Swings are real.** Two or three points, across more than one attribute, when
the story earns it. Example: a Purrsuader who tries to befriend a bee gets
stung — that's `-3 CHA` for the swollen face, `-1 AGI` for the swelling, `+1 INT`
for learning better.

**The stat follows the state the cat ends in**, never the object itself.
Emboldened → strength. Wrong-footed → agility. Bonded/adored → charm.
Worked-something-out → intellect. Insulted/demoralised → negative.

**Both directions in every row.** An object that's good for all 13 classes is
not an object, it's a buff — that's a bug, not content. Exception: something
that frightens *everyone* (a vacuum-cleaner-type object) can have all 13 lose
something, but by different amounts, because different personalities panic
differently.

**Guessable first, twist second.** Most cells should be roughly what you'd
expect from that object and that cat. About a third can subvert it mildly.
Absurd is the seasoning, not the meal.

**Hard rules:**
- The cat cannot "leave the arena" or "leave the room" — there is no room, it's
  a fight, everyone is watching. It can flinch, hide behind something, refuse
  to look, get on top of something. It cannot exit.
- The line must be specifically about *this* object — if it would read
  identically with a different noun swapped in, it's filler, reject it.
- The line must be specifically about *this* cat's personality — no two
  classes should read like they could swap lines.
- Present tense, one thing happening, roughly a dozen words after the setup
  clause. No em dashes.

## Format of one line

Two beats: **[what arrives / what's done with it]. [what this cat does with it,
and what it costs or wins].**

```
"pouncer": L("A tin is opened ringside. He arrives before the lid is fully off.", agility=3),
"purrsuader": L("A tin is opened ringside. It was opened for her. She arranged it earlier.", charm=3, intellect=1),
```

Stat keys are exactly: `strength`, `agility`, `intellect`, `charm` (write STR/AGI/INT/CHA
if working outside Python — see "How to hand results back" below for the exact
syntax needed). Values are small integers, typically 1–3, positive or negative.
Omit a stat entirely rather than writing `=0`.

## The 13 cat personalities (write one line for each, per object)

| key | name | governs | personality |
|---|---|---|---|
| `pouncer` | Pouncer | STR›AGI | Treats everything as something to ambush. Excited by anything that moves or hides. |
| `loaf` | Loaf | STR›INT | Wants to sit on it, be warmed by it, or ignore it. Rarely impressed, never hurried. |
| `chonk` | Chonk | STR›CHA | Food is the point. Anything large is a personal remark and will be taken as one. |
| `ricochet` | Ricochet | AGI›STR | Bats it, chases it, loses it under the sofa. Anything round is a project. |
| `ghost` | Ghost | AGI›INT | Admires anything sly or unseen and takes it as a lesson. Loud things are an insult. |
| `gremlin` | Zoom Gremlin | AGI›CHA | Destroys it, wears it, or knocks it off the table. Consequences are for later. |
| `barger` | Door Barger | INT›STR | Works out how it opens, then opens it. Barriers are suggestions. |
| `stalker` | Shelf Stalker | INT›AGI | Wants it up high, or wants to watch it from up high. Patient about both. |
| `purrsuader` | Purrsuader | INT›CHA | Sees a lever. Every object is a way of making a human do something. |
| `tyrant` | Lap Tyrant | CHA›STR | Claims it. Sits on it. It was always going to be hers. |
| `weaver` | Ankle Weaver | CHA›AGI | Winds around it, trips you over it, and is adored for doing so. |
| `dinner` | Second Dinner | CHA›INT | Is it food? It might be food. Sentiment works on her, and so does guilt. |
| `alley` | Alley Cat | (no specialism) | Has met all of it before and found a use for most of it. Very little is new. |

## Worked examples (for tone/calibration only — do not repeat these objects)

```python
"🐙": {  # octopus, thrown into the ring
    "pouncer": L("An octopus lands in the ring. He pins one arm. Seven others object.", strength=1, agility=-2),
    "chonk": L("An octopus lands in the ring. He is fully wrapped and cannot see out.", agility=-3, strength=1),
    "barger": L("An octopus lands in the ring. He watches it open a jar and copies the grip.", intellect=3, strength=1),
    "purrsuader": L("An octopus lands in the ring. She asks it to hold the opponent. It does.", agility=2, charm=2),
    "ghost": L("An octopus lands in the ring. Two things that hide. It hides him too.", agility=2, intellect=2),
},
"🐝": {  # bee, loosed in the ring
    "purrsuader": L("A bee is loosed in the ring. She tries to befriend it. Swollen betrayal.", charm=-3, agility=-1, intellect=1),
    "gremlin": L("A bee is loosed in the ring. He eats the bee. The bee gets its revenge inside.", strength=-2, charm=-1),
},
"✈": {  # a plane, landing in the ring — the strength-favouring case
    "chonk": L("A plane lands in the ring. He picks it up by the tail and throws it. Nobody breathes.", strength=3, charm=2),
    "loaf": L("A plane lands in the ring. He sits on the nose and it does not take off.", strength=3, agility=-1),
},
```

## How to hand results back

Ask the other model to output **exactly** this Python format, one block per
object, using the object's emoji as the dict key and `L(text, **stats)` for each
of the 13 class rows, in the class order given above. That's the format
`helpers/reaction_written.py` already uses — a block can be pasted straight in
with no reformatting.

If the tool you use can't produce that exact syntax, plain text like this also
works, and I'll convert it:

```
🐙 (octopus)
pouncer: An octopus lands in the ring. He pins one arm. Seven others object. -2 AGI +1 STR
loaf: ...
```

Bring the output back to this session (or open a new one) and ask for it to be
merged into `helpers/reaction_written.py` — the merge step checks every line
against the hard rules above (no em dashes, no leaving the room, all 13
classes present, stats non-zero) before it goes in, so nothing bad slips
through even if the other model drifts.

## What's already done (do not repeat)

122 objects are already written: the most-used faces, most-used animals, and a
first pass of food and drink. Anything not listed below is either already done
or is genuinely low-priority (used under ~5 times in this server's whole
history).

## What's left, by group, ranked by how often people actually use it

Below is every remaining object, grouped, most-used first within each group.
Format: `emoji  name  (uses)`. Do the highest-count groups first — Food and
drink and Animals are closest to finished and worth completing before moving to
a new group.
### Odds and ends (293)

🦤 Dodo(51)  ⚔ Crossed swords(25)  ⛵ Sailboat(25)  🎅 Father christmas(22)  💕 Two hearts(20)  👉 White right pointing backhand index(13)  🛡 Shield(10)  🏃 Runner(9)
🏁 Chequered flag(8)  👈 White left pointing backhand index(7)  🪦 Headstone(5)  🧊 Ice cube(5)  💰 Money bag(5)  🧙 Mage(4)  🥋 Martial arts uniform(4)  💸 Money with wings(4)
🔫 Pistol(4)  🚣 Rowboat(4)  🚂 Steam locomotive(4)  👆 White up pointing backhand index(4)  🧑 Adult(3)  🥞 Pancakes(3)  🤌 Pinched fingers(3)  🏐 Volleyball(3)
☝ White up pointing index(3)  🛫 Airplane departure(2)  🫦 Biting lip(2)  📓 Notebook(2)  🚨 Police cars revolving light(2)  📢 Public address loudspeaker(2)  💞 Revolving hearts(2)  🌻 Sunflower(2)
🧌 Troll(2)  👇 White down pointing backhand index(2)  🎟 Admission tickets(1)  🛬 Airplane arriving(1)  🎈 Balloon(1)  🏀 Basketball and hoop(1)  👰 Bride with veil(1)  🌯 Burrito(1)
🐿 Chipmunk(1)  🌆 Cityscape at dusk(1)  🪙 Coin(1)  🧁 Cupcake(1)  🍡 Dango(1)  🩸 Drop of blood(1)  👓 Eyeglasses(1)  🧯 Fire extinguisher(1)
🎆 Fireworks(1)  ⚜ Fleur-de-lis(1)  🍔 Hamburger(1)  🚥 Horizontal traffic light(1)  🛖 Hut(1)  👺 Japanese goblin(1)  👹 Japanese ogre(1)  🥬 Leafy green(1)
🪄 Magic wand(1)  🤶 Mother christmas(1)  🌃 Night with stars(1)  💿 Optical disc(1)  🥜 Peanuts(1)  🎭 Performing arts(1)  📌 Pushpin(1)  🦺 Safety vest(1)
⚖ Scales(1)  🤳 Selfie(1)  🛍 Shopping bags(1)  🍰 Shortcake(1)  🕵 Sleuth or spy(1)  🛩 Small airplane(1)  🌅 Sunrise(1)  🌄 Sunrise over mountains(1)
🍵 Teacup without handle(1)  🎫 Ticket(1)  🚩 Triangular flag on post(1)  📐 Triangular ruler(1)  🔱 Trident emblem(1)  🚦 Vertical traffic light(1)  🍉 Watermelon(1)  👢 Womans boots(1)
⚗ Alembic(0)  🏈 American football(0)  🏺 Amphora(0)  🚛 Articulated lorry(0)  🛺 Auto rickshaw(0)  🏧 Automated teller machine(0)  🛄 Baggage claim(0)  🩰 Ballet shoes(0)
🗶 Ballot bold script x(0)  🗴 Ballot script x(0)  💈 Barber pole(0)  ⚾ Baseball(0)  🛀 Bath(0)  🛁 Bathtub(0)  🛏 Bed(0)  🚴 Bicyclist(0)
🎱 Billiards(0)  ♣ Black club suit(0)  🖿 Black folder(0)  ✒ Black nib(0)  ♠ Black spade suit(0)  ☎ Black telephone(0)  📚 Books(0)  🪃 Boomerang(0)
🤱 Breast-feeding(0)  🧱 Brick(0)  🩲 Briefs(0)  🥦 Broccoli(0)  🫧 Bubbles(0)  🕫 Bullhorn(0)  🕬 Bullhorn with sound waves(0)  🏕 Camping(0)
🗙 Cancellation x(0)  🎏 Carp streamer(0)  ⛓ Chains(0)  🌰 Chestnut(0)  🚸 Children crossing(0)  🎦 Cinema(0)  ㊗ Circled ideograph congratulation(0)  ㊙ Circled ideograph secret(0)
🛈 Circled information source(0)  🏙 Cityscape(0)  🗘 Clockwise right and left semicircle arrows(0)  📪 Closed mailbox with lowered flag(0)  📫 Closed mailbox with raised flag(0)  ⚰ Coffin(0)  🗜 Compression(0)  🎛 Control knobs(0)
🛋 Couch and lamp(0)  🎌 Crossed flags(0)  🛃 Customs(0)  🌀 Cyclone(0)  🛲 Diesel locomotive(0)  🎯 Direct hit(0)  🪔 Diya lamp(0)  🗎 Document(0)
🖻 Document with picture(0)  🖹 Document with text(0)  🖺 Document with text and picture(0)  ⏸ Double vertical bar(0)  🛗 Elevator(0)  🦲 Emoji component bald(0)  🗋 Empty document(0)  🗍 Empty pages(0)
🖷 Fax icon(0)  📠 Fax machine(0)  🤺 Fencer(0)  ⛴ Ferry(0)  🎞 Film frames(0)  📽 Film projector(0)  🧨 Firecracker(0)  🥏 Flying disc(0)
🌁 Foggy(0)  👣 Footprints(0)  🖾 Frame with an x(0)  🖼 Frame with picture(0)  🖽 Frame with tiles(0)  🍟 French fries(0)  ⚱ Funeral urn(0)  🫚 Ginger root(0)
🧤 Gloves(0)  🥽 Goggles(0)  🏌 Golfer(0)  💂 Guardsman(0)  💇 Haircut(0)  🪬 Hamsa(0)  🤾 Handball(0)  ✖ Heavy multiplication x(0)
🌺 Hibiscus(0)  ♨ Hot springs(0)  🪻 Hyacinth(0)  🏒 Ice hockey stick and puck(0)  👿 Imp(0)  🫵 Index pointing at the viewer(0)  🎎 Japanese dolls(0)  🤹 Juggling(0)
🕋 Kaaba(0)  🥝 Kiwifruit(0)  🪢 Knot(0)  🗬 Left thought bubble(0)  🎚 Level slider(0)  🚈 Light rail(0)  🖇 Linked paperclips(0)  🗢 Lips(0)
🪷 Lotus(0)  🦽 Manual wheelchair(0)  🗖 Maximize(0)  🦠 Microbe(0)  🪖 Military helmet(0)  🚐 Minibus(0)  💽 Minidisc(0)  🗕 Minimize(0)
🤻 Modern pentathlon(0)  🗰 Mood bubble(0)  🦼 Motorized wheelchair(0)  🛣 Motorway(0)  🗻 Mount fuji(0)  📛 Name badge(0)  🏞 National park(0)  🧿 Nazar amulet(0)
🪆 Nesting dolls(0)  🚳 No bicycles(0)  📵 No mobile phones(0)  🚷 No pedestrians(0)  🕲 No piracy(0)  🛪 Northeast-pointing airplane(0)  🕃 Notched left semicircle with three dots(0)  🕄 Notched right semicircle with three dots(0)
📔 Notebook with decorative cover(0)  🍢 Oden(0)  🚘 Oncoming automobile(0)  🗁 Open folder(0)  📭 Open mailbox with lowered flag(0)  📬 Open mailbox with raised flag(0)  🖸 Optical disc icon(0)  🗗 Overlap(0)
🐂 Ox(0)  📟 Pager(0)  🗐 Pages(0)  🛔 Pagoda(0)  📎 Paperclip(0)  🛂 Passport control(0)  🫛 Pea pod(0)  🚶 Pedestrian(0)
🎍 Pine decoration(0)  🪧 Placard(0)  🛐 Place of worship(0)  🛝 Playground slide(0)  🪠 Plunger(0)  🖩 Pocket calculator(0)  📾 Portable stereo(0)  📮 Postbox(0)
👝 Pouch(0)  🫗 Pouring liquid(0)  📿 Prayer beads(0)  🤴 Prince(0)  👸 Princess(0)  🦯 Probing cane(0)  🚙 Recreational vehicle(0)  🎗 Reminder ribbon(0)
🚻 Restroom(0)  🎀 Ribbon(0)  🥆 Rifle(0)  🗭 Right thought bubble(0)  🏵 Rosette(0)  📍 Round pushpin(0)  🏉 Rugby football(0)  🛒 Shopping trolley(0)
🩳 Shorts(0)  🖟 Sideways white down pointing index(0)  🖘 Sideways white left pointing index(0)  🖙 Sideways white right pointing index(0)  🖞 Sideways white up pointing index(0)  ⛷ Skier(0)  🛌 Sleeping accommodation(0)  🧦 Socks(0)
🥎 Softball(0)  🚤 Speedboat(0)  ⚕ Staff of aesculapius(0)  ⏱ Stopwatch(0)  📏 Straight ruler(0)  🛓 Stupa(0)  🌇 Sunset over buildings(0)  🏄 Surfer(0)
🏊 Swimmer(0)  🫔 Tamale(0)  🍊 Tangerine(0)  🖭 Tape cartridge(0)  🖀 Telephone on top of modem(0)  📞 Telephone receiver(0)  🖧 Three networked computers(0)  🗤 Three rays above(0)
🗥 Three rays below(0)  🗦 Three rays left(0)  🗧 Three rays right(0)  🚽 Toilet(0)  🖲 Trackball(0)  🚎 Trolleybus(0)  🔀 Twisted rightwards arrows(0)  👬 Two men holding hands(0)
🛧 Up-pointing airplane(0)  🛦 Up-pointing military airplane(0)  🛨 Up-pointing small airplane(0)  📳 Vibration mode(0)  🐃 Water buffalo(0)  🚾 Water closet(0)  🤽 Water polo(0)  🏋 Weight lifter(0)
🏱 White pennant(0)  🕾 White touchtone telephone(0)  🛜 Wireless(0)  👚 Womans clothes(0)  🩻 X-ray(0)

### Signs and symbols (128)

➡ Black rightwards arrow(362)  ⬅ Leftwards black arrow(349)  ⬆ Upwards black arrow(90)  🔸 Small orange diamond(89)  ♦ Black diamond suit(82)  ⬇ Downwards black arrow(45)  ▶ Black right-pointing triangle(38)  ™ Trade mark sign(30)
💠 Diamond shape with a dot inside(26)  ❌ Cross mark(25)  💫 Dizzy symbol(23)  ↗ North east arrow(11)  🟥 Large red square(10)  ↖ North west arrow(10)  🚫 No entry sign(9)  🤘 Sign of the horns(9)
❗ Heavy exclamation mark symbol(7)  💤 Sleeping symbol(6)  ❓ Black question mark ornament(5)  💯 Hundred points symbol(5)  ↙ South west arrow(5)  💦 Splashing sweat symbol(5)  💥 Collision symbol(4)  ↘ South east arrow(4)
♿ Wheelchair symbol(4)  ⏬ Black down-pointing double triangle(3)  🔄 Anticlockwise downwards and upwards open circle arrows(2)  ♻ Black universal recycling symbol(2)  ⏫ Black up-pointing double triangle(2)  🔃 Clockwise downwards and upwards open circle arrows(2)  🔽 Down-pointing small red triangle(2)  ➕ Heavy plus sign(2)
💋 Kiss mark(2)  ➖ Heavy minus sign(1)  ☢ Radioactive sign(1)  🚬 Smoking symbol(1)  💢 Anger symbol(0)  ♈ Aries(0)  ⚛ Atom symbol(0)  🚼 Baby symbol(0)
🔙 Back with leftwards arrow above(0)  💵 Banknote with dollar sign(0)  💶 Banknote with euro sign(0)  💷 Banknote with pound sign(0)  💴 Banknote with yen sign(0)  ☣ Biohazard sign(0)  ⏺ Black circle for record(0)  ⏪ Black left-pointing double triangle(0)
⏮ Black left-pointing double triangle with vertical bar(0)  ◀ Black left-pointing triangle(0)  ⏩ Black right-pointing double triangle(0)  ⏭ Black right-pointing double triangle with vertical bar(0)  ⏯ Black right-pointing triangle with double vertical bar(0)  ▪ Black small square(0)  🔲 Black square button(0)  ⏹ Black square for stop(0)
🛉 Boys symbol(0)  🕈 Celtic cross(0)  🤂 Circled cross formee(0)  🤀 Circled cross formee with four dots(0)  🕀 Circled cross pommee(0)  Ⓜ Circled latin capital letter m(0)  🔁 Clockwise rightwards and leftwards open circle arrows(0)  🔂 Clockwise rightwards and leftwards open circle arrows with circled one overlay(0)
🚧 Construction sign(0)  🕂 Cross pommee(0)  🕁 Cross pommee with half-circle below(0)  ➰ Curly loop(0)  💱 Currency exchange(0)  🗛 Decrease font size symbol(0)  🚯 Do not litter symbol(0)  ➿ Double curly loop(0)
🔻 Down-pointing red triangle(0)  ✳ Eight spoked asterisk(0)  🔚 End with leftwards arrow above(0)  🛊 Girls symbol(0)  💘 Heart with arrow(0)  ➗ Heavy division sign(0)  💲 Heavy dollar sign(0)  ❣ Heavy heart exclamation mark ornament(0)
⭕ Heavy large circle(0)  🕇 Heavy latin cross(0)  ⛑ Helmet with white cross(0)  🔆 High brightness symbol(0)  ⚡ High voltage sign(0)  🗚 Increase font size symbol(0)  🔠 Input symbol for latin capital letters(0)  🔤 Input symbol for latin letters(0)
🔡 Input symbol for latin small letters(0)  🔢 Input symbol for numbers(0)  🔣 Input symbol for symbols(0)  🔰 Japanese symbol for beginner(0)  🪯 Khanda(0)  🔶 Large orange diamond(0)  🤇 Left half circle(0)  🤆 Left half circle with dot(0)
🤃 Left half circle with four dots(0)  🗸 Light check mark(0)  🔗 Link symbol(0)  💌 Love letter(0)  🔅 Low brightness symbol(0)  🔾 Lower right shadowed white circle(0)  🕎 Menorah with nine branches(0)  🚹 Mens symbol(0)
❎ Negative squared cross mark(0)  🔞 No one under eighteen symbol(0)  🚭 No smoking symbol(0)  🚱 Non-potable water symbol(0)  🛑 Octagonal sign(0)  🕉 Om symbol(0)  🔛 On with exclamation mark with left right arrow above(0)  👐 Open hands sign(0)
☮ Peace symbol(0)  🚰 Potable water symbol(0)  🛇 Prohibited sign(0)  🚮 Put litter in its place symbol(0)  🔜 Soon with rightwards arrow above(0)  🕅 Symbol for marks chapter(0)  🔝 Top with upwards arrow above(0)  🛆 Triangle with rounded corners(0)
↕ Up down arrow(0)  🔺 Up-pointing red triangle(0)  🔼 Up-pointing small red triangle(0)  🔿 Upper right shadowed white circle(0)  ❕ White exclamation mark ornament(0)  🕆 White latin cross(0)  🚺 Womens symbol(0)  ☯ Yin yang(0)

### Faces (118)

😃 Smiling face with open mouth(285)  😀 Grinning face(116)  😇 Smiling face with halo(95)  🥲 Smiling face with tear(92)  😩 Weary face(86)  😜 Face with stuck-out tongue and winking eye(84)  😬 Grimacing face(84)  🤪 Grinning face with one large and one small eye(80)
😍 Smiling face with heart-shaped eyes(76)  😐 Neutral face(72)  😘 Face throwing a kiss(66)  😈 Smiling face with horns(64)  😎 Smiling face with sunglasses(64)  😔 Pensive face(49)  🤤 Drooling face(43)  😢 Crying face(42)
☺ White smiling face(38)  🤬 Serious face with symbols covering mouth(31)  😠 Angry face(30)  😞 Disappointed face(29)  🙄 Face with rolling eyes(29)  😵 Dizzy face(28)  🤯 Shocked face with exploding head(28)  😒 Unamused face(28)
🥹 Face holding back tears(27)  🧐 Face with monocle(25)  😹 Cat face with tears of joy(23)  🤓 Nerd face(22)  😫 Tired face(22)  😡 Pouting face(20)  😤 Face with look of triumph(19)  😝 Face with stuck-out tongue and tightly-closed eyes(19)
🥵 Overheated face(18)  😥 Disappointed but relieved face(17)  🥶 Freezing face(17)  😶 Face without mouth(16)  😕 Confused face(15)  😨 Fearful face(15)  🤗 Hugging face(15)  🙁 Slightly frowning face(15)
🐲 Dragon face(14)  🤭 Smiling face with smiling eyes and hand covering mouth(14)  🙀 Weary cat face(14)  🥱 Yawning face(14)  😸 Grinning cat face with smiling eyes(13)  🤮 Face with open mouth vomiting(12)  😌 Relieved face(12)  😓 Face with cold sweat(10)
🤫 Face with finger covering closed lips(10)  🤩 Grinning face with star eyes(10)  🤖 Robot face(10)  😻 Smiling cat face with heart-shaped eyes(10)  🐺 Wolf face(10)  🐱 Cat face(9)  😰 Face with open mouth and cold sweat(9)  🤢 Nauseated face(9)
🌚 New moon with face(9)  😲 Astonished face(6)  🤕 Face with head-bandage(6)  🦊 Fox face(6)  😣 Persevering face(6)  😪 Sleepy face(6)  😺 Smiling cat face with open mouth(6)  🫣 Face with peeking eye(5)
🫠 Melting face(5)  😴 Sleeping face(5)  ☹ White frowning face(5)  🐻 Bear face(4)  😼 Cat face with wry smile(4)  😖 Confounded face(4)  😿 Crying cat face(4)  🐶 Dog face(4)
🤠 Face with cowboy hat(4)  🤒 Face with thermometer(4)  🥴 Face with uneven eyes and wavy mouth(4)  😯 Hushed face(4)  🫡 Saluting face(4)  🤧 Sneezing face(4)  😧 Anguished face(3)  🥸 Disguised face(3)
🫤 Face with diagonal mouth(3)  🌞 Sun with face(3)  😟 Worried face(3)  🙅 Face with no good gesture(2)  🐴 Horse face(2)  😗 Kissing face(2)  😙 Kissing face with smiling eyes(2)  🦁 Lion face(2)
🐷 Pig face(2)  🤐 Zipper-mouth face(2)  🕐 Clock face one oclock(1)  🐹 Hamster face(1)  😚 Kissing face with closed eyes(1)  🤑 Money-mouth face(1)  🐵 Monkey face(1)  🐼 Panda face(1)
🐯 Tiger face(1)  🕜 Clock face one-thirty(0)  🐮 Cow face(0)  🫥 Dotted line face(0)  💆 Face massage(0)  😷 Face with medical mask(0)  🙆 Face with ok gesture(0)  🫢 Face with open eyes and hand over mouth(0)
🌛 First quarter moon with face(0)  🌝 Full moon with face(0)  🦒 Giraffe face(0)  😽 Kissing cat face with closed eyes(0)  🌜 Last quarter moon with face(0)  🤥 Lying face(0)  🙍 Person frowning(0)  🙎 Person with pouting face(0)
😾 Pouting cat face(0)  🐰 Rabbit face(0)  🫨 Shaking face(0)  🦄 Unicorn face(0)  🌬 Wind blowing face(0)  🦓 Zebra face(0)

### Animals (85)

🪱 Worm(8)  🦆 Duck(5)  🙉 Hear-no-evil monkey(4)  🙊 Speak-no-evil monkey(3)  🍤 Fried shrimp(2)  🐓 Rooster(2)  🐫 Bactrian camel(1)  🦫 Beaver(1)
🪲 Beetle(1)  🪳 Cockroach(1)  🦗 Cricket(1)  🕊 Dove of peace(1)  🐪 Dromedary camel(1)  🦅 Eagle(1)  🪶 Feather(1)  🦍 Gorilla(1)
🐣 Hatching chick(1)  🏇 Horse racing(1)  🦎 Lizard(1)  🦉 Owl(1)  🦚 Peacock(1)  🐖 Pig(1)  🦐 Shrimp(1)  🦥 Sloth(1)
🦖 T-rex(1)  🐅 Tiger(1)  🍹 Tropical drink(1)  🦡 Badger(0)  🦬 Bison(0)  🐡 Blowfish(0)  🐛 Bug(0)  🎠 Carousel horse(0)
🪸 Coral(0)  🐄 Cow(0)  🏏 Cricket bat and ball(0)  🐊 Crocodile(0)  🦌 Deer(0)  🐬 Dolphin(0)  🫏 Donkey(0)  🐘 Elephant(0)
🍥 Fish cake with swirl design(0)  🦩 Flamingo(0)  🪰 Fly(0)  🐥 Front-facing baby chick(0)  🪿 Goose(0)  🦮 Guide dog(0)  🦔 Hedgehog(0)  🦛 Hippopotamus(0)
🌭 Hot dog(0)  🪼 Jellyfish(0)  🦘 Kangaroo(0)  🖦 Keyboard and mouse(0)  🐨 Koala(0)  🐞 Lady beetle(0)  🐆 Leopard(0)  🦙 Llama(0)
🦞 Lobster(0)  🫎 Moose(0)  🦟 Mosquito(0)  🐁 Mouse(0)  🪤 Mouse trap(0)  🖯 One button mouse(0)  🦧 Orangutan(0)  🦜 Parrot(0)
🐾 Paw prints(0)  🐧 Penguin(0)  🐽 Pig nose(0)  🐩 Poodle(0)  🐏 Ram(0)  🐀 Rat(0)  🦏 Rhinoceros(0)  🦕 Sauropod(0)
🦂 Scorpion(0)  🦭 Seal(0)  🐑 Sheep(0)  🦨 Skunk(0)  🕸 Spider web(0)  🦑 Squid(0)  🦢 Swan(0)  🧸 Teddy bear(0)
🐠 Tropical fish(0)  🦃 Turkey(0)  🐢 Turtle(0)  🐋 Whale(0)  🪽 Wing(0)

### Food and drink (82)

🍻 Clinking beer mugs(8)  🌸 Cherry blossom(7)  🍾 Bottle with popping cork(4)  🍸 Cocktail glass(3)  🥖 Baguette bread(2)  🌾 Ear of rice(2)  🍴 Fork and knife(2)  🥧 Pie(2)
🍷 Wine glass(2)  🍽 Fork and knife with plate(1)  🍨 Ice cream(1)  🔍 Left-pointing magnifying glass(1)  🍍 Pineapple(1)  🥨 Pretzel(1)  🥪 Sandwich(1)  🍝 Spaghetti(1)
🍜 Steaming bowl(1)  🍓 Strawberry(1)  🥙 Stuffed flatbread(1)  🍣 Sushi(1)  🥑 Avocado(0)  🍼 Baby bottle(0)  🥯 Bagel(0)  🫘 Beans(0)
🫑 Bell pepper(0)  🍱 Bento box(0)  🧃 Beverage box(0)  🫐 Blueberries(0)  🕏 Bowl of hygieia(0)  🥣 Bowl with spoon(0)  🧋 Bubble tea(0)  🧈 Butter(0)
🍬 Candy(0)  🍒 Cherries(0)  🥢 Chopsticks(0)  🥥 Coconut(0)  🍚 Cooked rice(0)  🥐 Croissant(0)  🥤 Cup with straw(0)  🍛 Curry and rice(0)
🍮 Custard(0)  🥩 Cut of meat(0)  🍩 Doughnut(0)  🥟 Dumpling(0)  🧆 Falafel(0)  🫓 Flatbread(0)  🫕 Fondue(0)  🥠 Fortune cookie(0)
🧄 Garlic(0)  🥗 Green salad(0)  🍯 Honey pot(0)  🌶 Hot pepper(0)  🫙 Jar(0)  🍭 Lollipop(0)  🧴 Lotion bottle(0)  🥭 Mango(0)
🧉 Mate drink(0)  🍈 Melon(0)  🥮 Moon cake(0)  🍄 Mushroom(0)  🫒 Olive(0)  🧅 Onion(0)  🦪 Oyster(0)  🍐 Pear(0)
🍲 Pot of food(0)  🍗 Poultry leg(0)  🍎 Red apple(0)  🍙 Rice ball(0)  🍘 Rice cracker(0)  🔎 Right-pointing magnifying glass(0)  🍠 Roasted sweet potato(0)  🍶 Sake bottle and cup(0)
🧂 Salt shaker(0)  🥘 Shallow pan of food(0)  🍧 Shaved ice(0)  🥄 Spoon(0)  🌮 Taco(0)  🥡 Takeout box(0)  🫖 Teapot(0)  🍅 Tomato(0)
🥃 Tumbler glass(0)  🧇 Waffle(0)

### Screens and paper (73)

📝 Memo(8)  🗓 Spiral calendar pad(7)  📋 Clipboard(2)  📕 Closed book(2)  🕹 Joystick(2)  📅 Calendar(1)  📷 Camera(1)  📸 Camera with flash(1)
🖌 Lower left paintbrush(1)  📖 Open book(1)  ♾ Permanent paper sign(1)  🧾 Receipt(1)  📜 Scroll(1)  📆 Tear-off calendar(1)  🧮 Abacus(0)  📶 Antenna with bars(0)
🖂 Back of envelope(0)  📊 Bar chart(0)  🔖 Bookmark(0)  📑 Bookmark tabs(0)  📇 Card index(0)  🗂 Card index dividers(0)  📉 Chart with downwards trend(0)  📈 Chart with upwards trend(0)
💹 Chart with upwards trend and yen sign(0)  🖁 Clamshell mobile phone(0)  💳 Credit card(0)  🖥 Desktop computer(0)  📀 Dvd(0)  📧 E-mail symbol(0)  🗌 Empty page(0)  ✉ Envelope(0)
📩 Envelope with downwards arrow above(0)  🗄 File cabinet(0)  📁 File folder(0)  💾 Floppy disk(0)  🖅 Flying envelope(0)  📗 Green book(0)  🖴 Hard disk(0)  🪪 Identification card(0)
📥 Inbox tray(0)  📨 Incoming envelope(0)  🏷 Label(0)  📒 Ledger(0)  🖊 Lower left ballpoint pen(0)  🖍 Lower left crayon(0)  🖉 Lower left pencil(0)  📱 Mobile phone(0)
📴 Mobile phone off(0)  📲 Mobile phone with rightwards arrow at left(0)  🎥 Movie camera(0)  📰 Newspaper(0)  📂 Open file folder(0)  📤 Outbox tray(0)  🗏 Page(0)  📄 Page facing up(0)
🗟 Page with circled text(0)  📃 Page with curl(0)  🖆 Pen over stamped envelope(0)  ✏ Pencil(0)  🖨 Printer(0)  🖶 Printer icon(0)  🧧 Red gift envelope(0)  🧻 Roll of paper(0)
🗞 Rolled-up newspaper(0)  🖵 Screen(0)  🖃 Stamped envelope(0)  🗠 Stock chart(0)  🕼 Telephone receiver with page(0)  📺 Television(0)  📹 Video camera(0)  📼 Videocassette(0)
🖮 Wired keyboard(0)

### Tools and objects (72)

☑ Ballot box with check(15)  ⏳ Hourglass with flowing sand(8)  🪩 Mirror ball(7)  ⏰ Alarm clock(4)  🔨 Hammer(4)  🩹 Adhesive bandage(3)  🔑 Key(3)  🪓 Axe(2)
✂ Black scissors(2)  🛠 Hammer and wrench(2)  🧵 Spool of thread(2)  💡 Electric light bulb(1)  🔌 Electric plug(1)  🔦 Electric torch(1)  ⌛ Hourglass(1)  🔬 Microscope(1)
💊 Pill(1)  🪡 Sewing needle(1)  ⏲ Timer clock(1)  🗳 Ballot box with ballot(0)  🗹 Ballot box with bold check(0)  🗷 Ballot box with bold script x(0)  🗵 Ballot box with script x(0)  🧼 Bar of soap(0)
🧺 Basket(0)  🔋 Battery(0)  🔔 Bell(0)  🔕 Bell with cancellation stroke(0)  🛎 Bellhop bell(0)  🪣 Bucket(0)  🗃 Card file box(0)  🪚 Carpentry saw(0)
🔐 Closed lock with key(0)  🩼 Crutch(0)  🧬 Dna double helix(0)  🤈 Downward facing hook(0)  🤊 Downward facing hook with dot(0)  🤉 Downward facing notched hook(0)  🤋 Downward facing notched hook with dot(0)  ⚙ Gear(0)
🪮 Hair pick(0)  ⚒ Hammer and pick(0)  🪝 Hook(0)  🏮 Izakaya lantern(0)  🪜 Ladder(0)  🛅 Left luggage(0)  ↩ Leftwards arrow with hook(0)  🔒 Lock(0)
🔏 Lock with ink pen(0)  🪫 Low battery(0)  🧳 Luggage(0)  🧲 Magnet(0)  🕰 Mantelpiece clock(0)  🪞 Mirror(0)  🔩 Nut and bolt(0)  🔓 Open lock(0)
🧫 Petri dish(0)  ⛏ Pick(0)  🪒 Razor(0)  ↪ Rightwards arrow with hook(0)  🕭 Ringing bell(0)  🧷 Safety pin(0)  🪛 Screwdriver(0)  🧽 Sponge(0)
🩺 Stethoscope(0)  🔭 Telescope(0)  🧪 Test tube(0)  🧰 Toolbox(0)  🪥 Toothbrush(0)  🗑 Wastebasket(0)  ⌚ Watch(0)  🔧 Wrench(0)

### People (60)

🧛 Vampire(13)  🫂 People hugging(9)  🤸 Person doing cartwheel(8)  👯 Woman with bunny ears(8)  👻 Ghost(5)  🧠 Brain(4)  🙌 Person raising both hands in celebration(4)  💃 Dancer(2)
🧝 Elf(2)  🦵 Leg(2)  🦸 Superhero(2)  🎨 Artist palette(1)  👼 Baby angel(1)  🌽 Ear of maize(1)  🦶 Foot(1)  💁 Information desk person(1)
🕺 Man dancing(1)  🦿 Mechanical leg(1)  👄 Mouth(1)  🥷 Ninja(1)  👃 Nose(1)  🙇 Person bowing deeply(1)  👾 Alien monster(0)  🧔 Bearded person(0)
🕱 Black skull and crossbones(0)  🦴 Bone(0)  👤 Bust in silhouette(0)  👥 Busts in silhouette(0)  👷 Construction worker(0)  🧏 Deaf person(0)  👂 Ear(0)  🦻 Ear with hearing aid(0)
🦱 Emoji component curly hair(0)  🦰 Emoji component red hair(0)  👽 Extraterrestrial alien(0)  🧚 Fairy(0)  👪 Family(0)  🧞 Genie(0)  🧎 Kneeling person(0)  🫁 Lungs(0)
👫 Man and woman holding hands(0)  🕴 Man in business suit levitating(0)  🤵 Man in tuxedo(0)  👲 Man with gua pi mao(0)  👳 Man with turban(0)  🧜 Merperson(0)  🧗 Person climbing(0)  🧘 Person in lotus position(0)
🧖 Person in steamy room(0)  👱 Person with blond hair(0)  🧕 Person with headscarf(0)  👮 Police officer(0)  🤰 Pregnant woman(0)  🗾 Silhouette of japan(0)  🗣 Speaking head in silhouette(0)  🧍 Standing person(0)
🦹 Supervillain(0)  👅 Tongue(0)  🦷 Tooth(0)  🧟 Zombie(0)

### Weather and sky (52)

⭐ White medium star(15)  ☀ Black sun with rays(7)  🌎 Earth globe americas(4)  ✨ Sparkles(4)  🌫 Fog(3)  🌍 Earth globe europe-africa(2)  ❄ Snowflake(2)  🌩 Cloud with lightning(1)
🎇 Firework sparkler(1)  🌟 Glowing star(1)  🌌 Milky way(1)  ☃ Snowman(1)  🌖 Waning gibbous moon symbol(1)  🌔 Waxing gibbous moon symbol(1)  🌢 Black droplet(0)  🌂 Closed umbrella(0)
☁ Cloud(0)  🌨 Cloud with snow(0)  🌪 Cloud with tornado(0)  ☄ Comet(0)  🌙 Crescent moon(0)  🌏 Earth globe asia-australia(0)  ✴ Eight pointed black star(0)  🖄 Envelope with lightning(0)
🌓 First quarter moon symbol(0)  🌕 Full moon symbol(0)  🌐 Globe with meridians(0)  🌗 Last quarter moon symbol(0)  🗲 Lightning mood(0)  🗱 Lightning mood bubble(0)  🎑 Moon viewing ceremony(0)  🌑 New moon symbol(0)
🪐 Ringed planet(0)  🌠 Shooting star(0)  🔯 Six pointed star with middle dot(0)  🏂 Snowboarder(0)  ⛄ Snowman without snow(0)  ❇ Sparkle(0)  ☪ Star and crescent(0)  ✡ Star of david(0)
🌡 Thermometer(0)  ⛈ Thunder cloud and rain(0)  ❅ Tight trifoliate snowflake(0)  ☂ Umbrella(0)  ⛱ Umbrella on ground(0)  🌘 Waning crescent moon symbol(0)  🌒 Waxing crescent moon symbol(0)  🌣 White sun(0)
🌥 White sun behind cloud(0)  🌦 White sun behind cloud with rain(0)  🌤 White sun with small cloud(0)  🎐 Wind chime(0)

### Hands and gestures (45)

🤞 Hand with index and middle fingers crossed(21)  🏳 Waving white flag(16)  ✌ Victory hand(15)  🤏 Pinching hand(14)  👎 Thumbs down sign(8)  🦾 Mechanical arm(6)  🏹 Bow and arrow(5)  🤝 Handshake(5)
🙋 Happy person raising one hand(5)  💅 Nail polish(4)  🤲 Palms up together(4)  ✊ Raised fist(4)  ✋ Raised hand(4)  🤟 I love you hand sign(3)  🤜 Right-facing fist(3)  👊 Fisted hand sign(2)
🤛 Left-facing fist(2)  🌊 Water wave(2)  ✍ Writing hand(2)  🤙 Call me hand(1)  🎬 Clapper board(1)  🤚 Raised back of hand(1)  🪭 Folding hand fan(0)  🫰 Hand with index finger and thumb crossed(0)
🕻 Left hand telephone receiver(0)  🖎 Left writing hand(0)  🫲 Leftwards hand(0)  🫷 Leftwards pushing hand(0)  🫳 Palm down hand(0)  🌴 Palm tree(0)  🫴 Palm up hand(0)  🖐 Raised hand with fingers splayed(0)
🖖 Raised hand with part between middle and ring fingers(0)  🖑 Reversed raised hand with fingers splayed(0)  🖓 Reversed thumbs down sign(0)  🖒 Reversed thumbs up sign(0)  🖔 Reversed victory hand(0)  🕽 Right hand telephone receiver(0)  🕩 Right speaker with one sound wave(0)  🫱 Rightwards hand(0)
🫸 Rightwards pushing hand(0)  🔉 Speaker with one sound wave(0)  🖏 Turned ok hand sign(0)  🖗 White down pointing left hand index(0)  🤼 Wrestlers(0)

### Buildings and places (43)

🏡 House with garden(5)  ⛺ Tent(3)  🏠 House building(2)  🏰 European castle(1)  🏭 Factory(1)  🏥 Hospital(1)  🏫 School(1)  🏦 Bank(0)
🌉 Bridge at night(0)  🏗 Building construction(0)  ⛪ Church(0)  🎪 Circus tent(0)  🏛 Classical building(0)  🧭 Compass(0)  🏪 Convenience store(0)  🏬 Department store(0)
🏚 Derelict house building(0)  🗔 Desktop window(0)  🏤 European post office(0)  🎡 Ferris wheel(0)  ⛲ Fountain(0)  🛕 Hindu temple(0)  🏨 Hotel(0)  🏘 House buildings(0)
🏯 Japanese castle(0)  🏣 Japanese post office(0)  🏩 Love hotel(0)  🖋 Lower left fountain pen(0)  🕌 Mosque(0)  🏢 Office building(0)  🚃 Railway car(0)  🛤 Railway track(0)
🎢 Roller coaster(0)  🎒 School satchel(0)  🏟 Stadium(0)  🚉 Station(0)  🗽 Statue of liberty(0)  🚟 Suspension railway(0)  🕍 Synagogue(0)  🗼 Tokyo tower(0)
💒 Wedding(0)  🪟 Window(0)  🗺 World map(0)

### Transport (43)

⚓ Anchor(1)  🛸 Flying saucer(1)  ⛽ Fuel pump(1)  🚔 Oncoming police car(1)  🏎 Racing car(1)  🚡 Aerial tramway(0)  🚑 Ambulance(0)  🚲 Bicycle(0)
🚌 Bus(0)  🚏 Bus stop(0)  🛶 Canoe(0)  🚚 Delivery truck(0)  🚒 Fire engine(0)  🚁 Helicopter(0)  🚄 High-speed train(0)  🚅 High-speed train with bullet nose(0)
🚇 Metro(0)  🚝 Monorail(0)  🛥 Motor boat(0)  🛵 Motor scooter(0)  🚍 Oncoming bus(0)  🛱 Oncoming fire engine(0)  🚖 Oncoming taxi(0)  🪂 Parachute(0)
🛳 Passenger ship(0)  🛻 Pickup truck(0)  🚓 Police car(0)  🏍 Racing motorcycle(0)  🚀 Rocket(0)  🛰 Satellite(0)  📡 Satellite antenna(0)  🛴 Scooter(0)
💺 Seat(0)  🚢 Ship(0)  🛹 Skateboard(0)  🛷 Sled(0)  🚕 Taxi(0)  🚜 Tractor(0)  🚆 Train(0)  🚊 Tram(0)
🚋 Tram car(0)  🛞 Wheel(0)  ☸ Wheel of dharma(0)

### Music and sound (37)

🎵 Musical note(10)  🎹 Musical keyboard(6)  🎶 Multiple musical notes(5)  📣 Cheering megaphone(2)  🥁 Drum with drumsticks(2)  🗒 Spiral note pad(2)  🎼 Musical score(1)  📯 Postal horn(1)
📻 Radio(1)  🪗 Accordion(0)  🪕 Banjo(0)  🎜 Beamed ascending musical notes(0)  🎝 Beamed descending musical notes(0)  🗅 Empty note(0)  🗇 Empty note pad(0)  🗆 Empty note page(0)
🪈 Flute(0)  🎸 Guitar(0)  🎧 Headphone(0)  🪘 Long drum(0)  🪇 Maracas(0)  🎤 Microphone(0)  🎘 Musical keyboard with jacks(0)  🗈 Note(0)
🗊 Note pad(0)  🗉 Note page(0)  🛢 Oil drum(0)  🔘 Radio button(0)  🕨 Right speaker(0)  🕪 Right speaker with three sound waves(0)  🎷 Saxophone(0)  🔈 Speaker(0)
🔇 Speaker with cancellation stroke(0)  🔊 Speaker with three sound waves(0)  🎙 Studio microphone(0)  🎺 Trumpet(0)  🎻 Violin(0)

### Plants and nature (36)

🌳 Deciduous tree(4)  🌹 Rose(4)  🏖 Beach with umbrella(2)  🌲 Evergreen tree(2)  🍀 Four leaf clover(2)  🌋 Volcano(2)  🌵 Cactus(1)  🍂 Fallen leaf(1)
🍃 Leaf fluttering in wind(1)  ☘ Shamrock(1)  🖪 Black hard shell floppy disk(0)  🌼 Blossom(0)  💐 Bouquet(0)  🎕 Bouquet of flowers(0)  🏜 Desert(0)  🏝 Desert island(0)
🪹 Empty nest(0)  🎴 Flower playing cards(0)  🌿 Herb(0)  🍁 Maple leaf(0)  ⛰ Mountain(0)  🚵 Mountain bicyclist(0)  🚠 Mountain cableway(0)  🚞 Mountain railway(0)
🪺 Nest with eggs(0)  🪴 Potted plant(0)  🪨 Rock(0)  🌱 Seedling(0)  🏔 Snow capped mountain(0)  🖬 Soft shell floppy disk(0)  🐚 Spiral shell(0)  🎋 Tanabata tree(0)
🌷 Tulip(0)  💮 White flower(0)  🥀 Wilted flower(0)  🪵 Wood(0)

### Clothes and jewellery (33)

🎓 Graduation cap(8)  💎 Gem stone(7)  🥂 Clinking glasses(5)  💄 Lipstick(2)  👟 Athletic shoe(1)  👗 Dress(1)  👜 Handbag(1)  👠 High-heeled shoe(1)
👔 Necktie(1)  💍 Ring(1)  🛟 Ring buoy(1)  👙 Bikini(0)  🧢 Billed cap(0)  💼 Briefcase(0)  🧥 Coat(0)  🕶 Dark sunglasses(0)
🥿 Flat shoe(0)  🥾 Hiking boot(0)  👘 Kimono(0)  🥼 Lab coat(0)  👞 Mans shoe(0)  🩱 One-piece swimsuit(0)  🫅 Person with crown(0)  👛 Purse(0)
🎽 Running shirt with sash(0)  🥻 Sari(0)  🧣 Scarf(0)  🎿 Ski and ski boot(0)  👕 T-shirt(0)  🩴 Thong sandal(0)  🎩 Top hat(0)  👒 Womans hat(0)
👡 Womans sandal(0)

### Games and sport (29)

🎲 Game die(8)  🥇 First place medal(4)  🎊 Confetti ball(3)  ⚽ Soccer ball(2)  🔮 Crystal ball(1)  🥈 Second place medal(1)  🥉 Third place medal(1)  🏆 Trophy(1)
🏸 Badminton racquet and shuttlecock(0)  🎳 Bowling(0)  🥌 Curling stone(0)  🤿 Diving mask(0)  🏑 Field hockey stick and ball(0)  ⛳ Flag in hole(0)  🥅 Goal net(0)  ⛸ Ice skate(0)
🧩 Jigsaw puzzle piece(0)  🪁 Kite(0)  🥍 Lacrosse stick and ball(0)  🎖 Military medal(0)  ⛹ Person with ball(0)  🪅 Pinata(0)  🛼 Roller skate(0)  🎰 Slot machine(0)
🏅 Sports medal(0)  🏓 Table tennis paddle and ball(0)  🎾 Tennis racquet and ball(0)  🎮 Video game(0)  🪀 Yo-yo(0)

### Hearts and feelings (21)

👁 Eye(13)  ♥ Black heart suit(12)  💗 Growing heart(6)  💙 Blue heart(2)  🕳 Hole(2)  💬 Speech balloon(1)  🫀 Anatomical heart(0)  💓 Beating heart(0)
💣 Bomb(0)  💑 Couple with heart(0)  💟 Heart decoration(0)  🫶 Heart hands(0)  💝 Heart with ribbon(0)  🎔 Heart with tip on the left(0)  💏 Kiss(0)  🗮 Left anger bubble(0)
🗨 Left speech bubble(0)  🗯 Right anger bubble(0)  🗩 Right speech bubble(0)  💭 Thought balloon(0)  🗪 Two speech bubbles(0)
