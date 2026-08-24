"""
The written cells: one object, thirteen cats, thirteen different afternoons.

This is the real content. Every line here was written for *that* object shown to
*that* class, and nothing in it is assembled from parts. The templates in
:mod:`helpers.reaction_flavour` are scaffolding for the objects that have not
been reached yet, and every object written here stops using them for good.

The rules, learned the hard way:

* **It happens in the arena.** A cat cannot "leave the room": there is no room,
  there is a fight, and everyone is watching. It can flinch, hide behind
  something, refuse to look, or get on top of the thing. It cannot exit.
* **It has to be about this object.** If the line would read the same with a
  different noun dropped in, it is filler and does not belong here.
* **It has to be about this cat.** A Loaf and a Zoom Gremlin do not have the
  same afternoon, ever.
* **The stats follow the story.** A cat that got what it wanted goes up in the
  attribute it used to get it. A cat that embarrassed itself goes down.
* Present tense, one thing happening, about a dozen words. No em dashes.

Progress: this file holds the written objects. Everything else falls back, and
the panel shows which is which, so the remaining work is always visible.
"""

from __future__ import annotations


def L(text: str, **stats: int) -> tuple:
    return (text, {k: v for k, v in stats.items() if v})


# Ordered roughly by how likely somebody is to actually react with it.
WRITTEN: dict[str, dict[str, tuple]] = {
    "🐟": {
        "pouncer": L("Takes the fish out of the air before it lands.", strength=2, agility=1),
        "loaf": L("Does not rise for the fish. The fish may be brought.", strength=1, intellect=1),
        "chonk": L("Eats the fish in one and looks for the next fish.", strength=3, agility=-1),
        "ricochet": L("Snatches the fish at a run and skids into a wall.", agility=2, intellect=-1),
        "ghost": L("The fish is gone. Nobody saw the fish go.", agility=2, intellect=1),
        "gremlin": L("Kills the fish again, thoroughly, in case.", strength=2, charm=-1),
        "barger": L("Ignores the fish and works out where fish are kept.", intellect=3),
        "stalker": L("Carries the fish up somewhere high to eat unjudged.", intellect=1, agility=2),
        "purrsuader": L("Gets a second fish out of a spectator without moving.", charm=3, intellect=1),
        "tyrant": L("The fish was always hers. You were holding it for her.", charm=2, strength=1),
        "weaver": L("Winds round the fish holder until the fish drops.", charm=2, agility=1),
        "dinner": L("Eats the fish, then tells everyone she has not been fed.", charm=3, intellect=1),
        "alley": L("Eats the fish fast, with one eye on everyone else.", strength=2, agility=1),
    },
    "🥛": {
        "pouncer": L("Ambushes the glass. The glass tips. Everyone loses.", strength=1, intellect=-1),
        "loaf": L("Drinks the milk slowly, sitting down, eyes shut.", strength=2, intellect=1),
        "chonk": L("Drinks all of it and regrets it in about an hour.", strength=2, agility=-1),
        "ricochet": L("Knocks the milk flying and chases what spills.", agility=2, strength=-1),
        "ghost": L("The level in the glass drops. No cat is near it.", agility=1, intellect=2),
        "gremlin": L("Puts one whole paw in the milk and licks the paw.", charm=1, intellect=-1),
        "barger": L("Gets the lid off the milk without spilling any.", intellect=3),
        "stalker": L("Watches the milk from above and waits to be alone.", intellect=2),
        "purrsuader": L("Looks at the milk, then at you, until it is poured.", charm=3),
        "tyrant": L("Sits beside the milk so nobody else may drink it.", charm=2, strength=1),
        "weaver": L("Winds round the pourer's legs and gets served first.", charm=2, agility=1),
        "dinner": L("Finishes the milk and reports the bowl still empty.", charm=2, intellect=1),
        "alley": L("Drinks the milk quickly. Milk does not come twice.", strength=2, agility=1),
    },
    "🧀": {
        "pouncer": L("Pounces the cheese. Cheese does not run. Slight anticlimax.", strength=1, intellect=-1),
        "loaf": L("Sits beside the cheese and warms it to room temperature.", strength=1, intellect=1),
        "chonk": L("Eats cheese he is not supposed to have and glows.", strength=2, charm=1),
        "ricochet": L("Bats the cheese under the nearest heavy object.", agility=2),
        "ghost": L("Steals the cheese during somebody else's sentence.", agility=2, intellect=1),
        "gremlin": L("Chews the corner off the cheese and abandons it.", strength=1, charm=-1),
        "barger": L("Opens the cheese wrapper. It was not difficult.", intellect=3),
        "stalker": L("Takes the cheese to the top of the fridge.", intellect=2, agility=1),
        "purrsuader": L("Convinces a stranger that she is allowed cheese.", charm=3, intellect=1),
        "tyrant": L("Puts a paw on the cheese. The cheese is now hers.", charm=2, strength=1),
        "weaver": L("Trips the cheese carrier. The cheese hits the floor.", agility=2, charm=1),
        "dinner": L("Cries at the cheese until a piece is handed over.", charm=3),
        "alley": L("Knows cheese is worth having. Takes it and goes.", strength=1, intellect=2),
    },
    "🐭": {
        "pouncer": L("This is the entire reason a Pouncer exists.", strength=3, agility=1),
        "loaf": L("Watches the mouse cross the arena. Stays exactly put.", intellect=2, agility=-1),
        "chonk": L("Gives chase for two metres, then reconsiders everything.", strength=1, agility=-1),
        "ricochet": L("Chases the mouse into a wall at full speed.", agility=2, intellect=-1),
        "ghost": L("Was already between the mouse and the exit.", agility=2, intellect=2),
        "gremlin": L("Catches the mouse and lets it go, to keep the game.", agility=2, intellect=-1),
        "barger": L("Works out which hole the mouse will use. Waits there.", intellect=3),
        "stalker": L("Tracks the mouse from the shelf without moving a whisker.", intellect=2, agility=1),
        "purrsuader": L("Brings the mouse to a human as an unwanted gift.", charm=2, intellect=1),
        "tyrant": L("Expects the mouse to be dealt with by staff.", charm=2, agility=-1),
        "weaver": L("Herds the mouse between everyone's ankles for fun.", agility=2, charm=1),
        "dinner": L("Considers the mouse dinner, then thinks better of it.", charm=1, intellect=1),
        "alley": L("Catches the mouse without ceremony. This is a job.", strength=2, agility=2),
    },
    "🐕": {
        "pouncer": L("Goes for the dog's tail from behind a chair.", strength=2, intellect=-1),
        "loaf": L("Sits still. The dog loses interest first. It always does.", strength=2, intellect=2),
        "chonk": L("Stands his ground because moving is not on the table.", strength=2, agility=-1),
        "ricochet": L("Runs three laps around the dog until it gives up.", agility=3),
        "ghost": L("Is on top of the wardrobe before the dog is through the door.", agility=2, intellect=1),
        "gremlin": L("Boxes the dog on the nose and instantly regrets it.", strength=1, charm=-1),
        "barger": L("Works out the dog is on a lead, and uses the extra metre.", intellect=3),
        "stalker": L("Waits above the dog for as long as it takes.", intellect=2, agility=1),
        "purrsuader": L("Befriends the dog, which is now working for her.", charm=3, intellect=1),
        "tyrant": L("Walks past the dog slowly, to make a point.", charm=2, strength=1),
        "weaver": L("Weaves under the dog and out the other side.", agility=3),
        "dinner": L("Complains at length that the dog gets fed first.", charm=2, intellect=1),
        "alley": L("Has settled things with bigger dogs than this one.", strength=2, intellect=1),
    },
    "🕷️": {
        "pouncer": L("Takes the spider in one paw from four feet away.", strength=2, agility=1),
        "loaf": L("Lets the spider walk across him. Does not comment.", intellect=2),
        "chonk": L("Eats the spider. Sneezes. Considers the matter closed.", strength=1, intellect=-1),
        "ricochet": L("Bats the spider across the arena and loses it.", agility=2, intellect=-1),
        "ghost": L("Studies how the spider waits. Approves of the method.", intellect=2, agility=1),
        "gremlin": L("Eats the spider in front of everyone, maintaining eye contact.", charm=1, strength=1),
        "barger": L("Follows the spider to find where the gap in the wall is.", intellect=3),
        "stalker": L("Watches the spider from above, professional to professional.", intellect=2),
        "purrsuader": L("Screams once and has a human deal with the spider.", charm=2, intellect=1),
        "tyrant": L("Requires that the spider be removed. By somebody else.", charm=2, agility=-1),
        "weaver": L("Follows the spider's thread with one paw, delighted.", agility=2, charm=1),
        "dinner": L("Establishes that the spider is not dinner. Loudly.", charm=1, intellect=-1),
        "alley": L("Eats the spider. Protein is protein.", strength=2, intellect=1),
    },
    "📦": {
        "pouncer": L("Waits inside the box. Everything that passes is prey.", strength=1, agility=2),
        "loaf": L("Fits the box exactly. Will not be leaving the box.", strength=2, intellect=1),
        "chonk": L("Does not fit the box. Wears the box instead.", strength=2, agility=-2),
        "ricochet": L("Enters the box at speed. The box travels.", agility=2, strength=1),
        "ghost": L("The box is empty. The box has never been empty.", agility=1, intellect=2),
        "gremlin": L("Destroys the box in a minute, then mourns the box.", strength=2, charm=-1),
        "barger": L("Opens the flaps from inside. Learns something about doors.", intellect=3),
        "stalker": L("Stands on the box and gains a foot of height.", intellect=2, agility=1),
        "purrsuader": L("Sits in the box looking beautiful until photographed.", charm=3),
        "tyrant": L("Claims the box. There was never any doubt about the box.", charm=2, strength=1),
        "weaver": L("In one end of the box, out the other, twice.", agility=3),
        "dinner": L("Cries from inside the box. The acoustics are excellent.", charm=3),
        "alley": L("A box is a house. Gets in and stops shivering.", strength=1, charm=1),
    },
    "🧶": {
        "pouncer": L("Ambushes the wool from behind and takes it down.", strength=1, agility=2),
        "loaf": L("Rests his chin on the wool. It is a pillow now.", strength=1, intellect=1),
        "chonk": L("Lies on the wool. The wool is not seen again.", strength=2, agility=-1),
        "ricochet": L("Sends the wool across the arena and follows it.", agility=3),
        "ghost": L("The wool unwinds slowly with no cat attached.", intellect=2, agility=1),
        "gremlin": L("Ties three cats together and looks proud.", charm=2, intellect=-1),
        "barger": L("Finds the loose end and pulls the whole thing apart.", intellect=2, strength=1),
        "stalker": L("Drops the wool off a shelf and watches it fall.", intellect=2, agility=1),
        "purrsuader": L("Plays with the wool adorably until somebody joins in.", charm=3),
        "tyrant": L("Sits in the middle of the wool and receives compliments.", charm=2),
        "weaver": L("This is what she is for. Everything gets wound.", charm=2, agility=3),
        "dinner": L("Eats a length of wool. This will be a problem later.", charm=1, intellect=-2),
        "alley": L("Bats the wool once, remembers being a kitten, joins in.", agility=2, charm=1),
    },
    "🔴": {
        "pouncer": L("Pounces the red dot. There is nothing under his paw.", strength=1, intellect=-2),
        "loaf": L("Watches the dot cross the floor. Declines to follow it.", intellect=2),
        "chonk": L("Chases the dot for four seconds and needs a rest.", strength=1, agility=-1),
        "ricochet": L("Follows the dot up a wall and keeps going.", agility=3, intellect=-1),
        "ghost": L("Works out where the dot comes from and stares at the hand.", intellect=3),
        "gremlin": L("Loses his entire mind over a dot on a wall.", agility=2, intellect=-2),
        "barger": L("Traces the beam back and sits on the pointer.", intellect=3),
        "stalker": L("Waits for the dot to come to the shelf. It does.", intellect=2, agility=1),
        "purrsuader": L("Chases the dot only while she is being watched.", charm=2, intellect=1),
        "tyrant": L("Refuses to chase the dot in front of people.", charm=1, agility=-1),
        "weaver": L("Follows the dot round three sets of ankles.", agility=2, charm=1),
        "dinner": L("Believes the dot is food and cannot be talked out of it.", charm=1, intellect=-2),
        "alley": L("Recognises a trick and does not fall for it twice.", intellect=2),
    },
    "🥒": {
        "pouncer": L("Launches at the cucumber and lands somewhere unplanned.", agility=2, strength=-1),
        "loaf": L("Notices the cucumber. Continues sitting on his own feet.", intellect=2),
        "chonk": L("Achieves about a foot of air. It is enormously impressive.", agility=1, strength=-1),
        "ricochet": L("Is airborne before the cucumder touches the floor.", agility=3),
        "ghost": L("Is not where the cucumber was put. Was never there.", agility=2, intellect=1),
        "gremlin": L("Screams, jumps, returns, and bites the cucumber.", agility=2, charm=-1),
        "barger": L("Sniffs the cucumber. Concludes: vegetable. Unimpressed.", intellect=3),
        "stalker": L("Sees the cucumber being placed. The trick fails entirely.", intellect=3),
        "purrsuader": L("Is startled, and makes it everybody else's fault.", charm=2, intellect=1),
        "tyrant": L("Refuses to acknowledge that the jump happened.", charm=2, strength=-1),
        "weaver": L("Hops the cucumber neatly and carries on winding.", agility=2, charm=1),
        "dinner": L("Assumes food, discovers cucumber, is personally insulted.", charm=1, intellect=-1),
        "alley": L("Has been startled by worse things than a vegetable.", strength=1, intellect=1),
    },
    "🧹": {
        "pouncer": L("Ambushes the bristles and wins decisively.", strength=2),
        "loaf": L("Is swept along the floor without changing expression.", strength=1, intellect=1),
        "chonk": L("Is swept around like a rug that has opinions.", strength=1, agility=-1),
        "ricochet": L("Rides the broom, falls off, blames the broom.", agility=1, strength=-1),
        "ghost": L("Is above the broom before the broom arrives.", agility=2, intellect=1),
        "gremlin": L("Declares war on the broom. The broom is unaware.", strength=1, charm=-1),
        "barger": L("Understands the broom, and fears it correctly.", intellect=2, charm=-1),
        "stalker": L("Is on the shelf. The broom cannot reach the shelf.", intellect=2, agility=1),
        "purrsuader": L("Makes the sweeping stop by being adorable at it.", charm=3),
        "tyrant": L("Sits on the swept pile. Sweeping is now over.", charm=2, strength=1),
        "weaver": L("Weaves between the bristles and out the far side.", agility=3),
        "dinner": L("Screams until the broom is put down. It is put down.", charm=2, intellect=1),
        "alley": L("Knows the broom. Steps aside before it starts.", agility=1, intellect=2),
    },
    "🚿": {
        "pouncer": L("Attacks the water. The water wins immediately.", strength=1, agility=-1),
        "loaf": L("Sits in the spray for a moment, then walks off steaming.", strength=2, intellect=1),
        "chonk": L("Becomes half his size and twice as furious.", strength=1, charm=-1),
        "ricochet": L("Is dry, wet, and dry again inside two seconds.", agility=3),
        "ghost": L("Was gone the moment the tap squeaked.", agility=2, intellect=2),
        "gremlin": L("Bites the shower. Is now a wet gremlin.", agility=1, charm=-2),
        "barger": L("Works out the tap and turns the water off.", intellect=3),
        "stalker": L("Watches the shower from the highest dry surface.", intellect=2, agility=1),
        "purrsuader": L("Sits wet and pitiful until somebody fetches a towel.", charm=3),
        "tyrant": L("Regards being wet as a failure of the household.", charm=2, strength=-1),
        "weaver": L("Slips between the drops. Emerges almost dry.", agility=3),
        "dinner": L("Drinks from the shower rather than the bowl provided.", intellect=1, charm=1),
        "alley": L("Has been rained on for years. Shrugs it off.", strength=2, intellect=1),
    },
    "🔥": {
        "pouncer": L("Crouches at the fire, then thinks better of pouncing.", intellect=1, strength=1),
        "loaf": L("Sits as close to the fire as physics allows.", strength=2, intellect=1),
        "chonk": L("Blocks the fire entirely. Everyone else is cold now.", strength=2, charm=1),
        "ricochet": L("Runs past the fire twice for no clear reason.", agility=2, intellect=-1),
        "ghost": L("Sits just outside the firelight, watching everybody.", intellect=2, agility=1),
        "gremlin": L("Bats at the fire once and learns nothing.", agility=1, intellect=-2),
        "barger": L("Understands heat before touching it. Rare, and smug.", intellect=3),
        "stalker": L("Watches the fire from above, where the warm air goes.", intellect=2, agility=1),
        "purrsuader": L("Takes the best spot by the fire and keeps it.", charm=3),
        "tyrant": L("The fire was lit for her. Everyone else may share.", charm=2, strength=1),
        "weaver": L("Winds past the fire close enough to worry people.", agility=2, charm=1),
        "dinner": L("Sits by the fire and mentions that fires cook things.", charm=2, intellect=1),
        "alley": L("Fire means people. People mean food. Moves closer.", intellect=2, charm=1),
    },
    "💀": {
        "pouncer": L("Pounces the skull. It rolls. Now it is a game.", strength=1, agility=1),
        "loaf": L("Sits beside the skull companionably. No comment.", intellect=2),
        "chonk": L("Pushes the skull off the table and watches it go.", strength=2, charm=1),
        "ricochet": L("Sends the skull round the arena at speed.", agility=2, strength=1),
        "ghost": L("Immediate, unsettling kinship with the skull.", intellect=2, agility=1),
        "gremlin": L("Wears the skull. Refuses to explain the skull.", charm=2, strength=1),
        "barger": L("Examines the jaw hinge with genuine professional interest.", intellect=3),
        "stalker": L("Puts the skull on a shelf, facing the other cats.", intellect=2, charm=-1),
        "purrsuader": L("Poses with the skull until somebody feels something.", charm=2, intellect=1),
        "tyrant": L("Sits in the skull. It is a throne with a face.", charm=2, strength=1),
        "weaver": L("Threads through both eye sockets without slowing.", agility=3),
        "dinner": L("Checks the skull for meat. Finds none. Is let down.", charm=1, intellect=-1),
        "alley": L("Has seen a skull before. Has seen several.", strength=1, intellect=2),
    },
    "🎃": {
        "pouncer": L("Ambushes from inside the pumpkin. Nobody expected a cat.", strength=1, agility=2),
        "loaf": L("Two heavy round things, sitting quietly together.", strength=2, intellect=1),
        "chonk": L("Is briefly mistaken for the pumpkin and says nothing.", strength=2, charm=1),
        "ricochet": L("Rolls the pumpkin the length of the arena.", agility=2, strength=1),
        "ghost": L("Occupies the pumpkin. The pumpkin now has opinions.", agility=1, intellect=2),
        "gremlin": L("Hollows the pumpkin further, uninvited, at speed.", strength=2, agility=1),
        "barger": L("Gets in through the mouth to see how it was made.", intellect=2, strength=1),
        "stalker": L("Sits on the pumpkin and gains commanding height.", intellect=2, agility=1),
        "purrsuader": L("Sits behind the pumpkin and becomes a photograph.", charm=3),
        "tyrant": L("Uses the pumpkin as a plinth. She is a monument.", charm=2, strength=1),
        "weaver": L("In one eye of the pumpkin and out the other.", agility=3),
        "dinner": L("Assumes the pumpkin is a very large portion.", charm=2, strength=1),
        "alley": L("Sleeps in the pumpkin. It is warm and nobody wants it.", strength=1, charm=1),
    },
    "👑": {
        "pouncer": L("Knocks the crown off whoever is wearing it.", strength=1, agility=2),
        "loaf": L("Sits under the crown. It fits, in a manner of speaking.", strength=1, intellect=1),
        "chonk": L("The crown sits on his head like a bracelet.", strength=1, charm=2),
        "ricochet": L("Sends the crown skidding under the seating.", agility=2),
        "ghost": L("The crown is on a different cat now. Nobody saw.", agility=2, intellect=2),
        "gremlin": L("Wears the crown backwards and will not be corrected.", charm=2, intellect=-1),
        "barger": L("Works out the crown means nothing and ignores it.", intellect=2),
        "stalker": L("Takes the crown up high where it can be admired.", intellect=1, agility=2),
        "purrsuader": L("Is given the crown. Did not have to ask for it.", charm=3, intellect=1),
        "tyrant": L("Puts it on. Of course it fits. It was always hers.", charm=3, strength=1),
        "weaver": L("Winds through the crown and wears it as a collar.", agility=2, charm=2),
        "dinner": L("Tries to eat the crown, briefly, out of principle.", charm=1, intellect=-1),
        "alley": L("Regards the crown as tradeable. Which it is.", intellect=2, charm=1),
    },
    "💻": {
        "pouncer": L("Attacks the cursor on the screen from the side.", agility=2, intellect=-1),
        "loaf": L("Sits on the keyboard. It is warm and flat and his.", strength=2, intellect=1),
        "chonk": L("Lies across the whole laptop. It runs hotter now.", strength=2, agility=-1),
        "ricochet": L("Walks over the keys at speed. Something is sent.", agility=1, intellect=-2),
        "ghost": L("Sits behind the screen where the light cannot reach.", intellect=2, agility=1),
        "gremlin": L("Sends a message to somebody with one confident paw.", charm=2, intellect=-1),
        "barger": L("Presses keys until the machine does something new.", intellect=3),
        "stalker": L("Watches the screen from above, head tilted.", intellect=2),
        "purrsuader": L("Sits between the human and the laptop. Work stops.", charm=2, intellect=2),
        "tyrant": L("Occupies the laptop. Nobody is working today.", charm=2, strength=1),
        "weaver": L("Walks across the keyboard slowly, tail up, twice.", charm=2, agility=1),
        "dinner": L("Cries at the laptop user until the laptop is closed.", charm=3),
        "alley": L("Sleeps on the laptop purely for the warmth.", strength=1, intellect=1),
    },
    "🚪": {
        "pouncer": L("Waits behind the door for whatever comes through it.", strength=1, agility=2),
        "loaf": L("Sits precisely in the doorway. Nobody may pass.", strength=2, intellect=1),
        "chonk": L("Fills the doorway completely, without meaning to.", strength=2, agility=-1),
        "ricochet": L("Through the door, round the room, back out again.", agility=3),
        "ghost": L("Is on the other side of the door already.", agility=2, intellect=1),
        "gremlin": L("Yowls at the door, goes through, wants it opened again.", charm=1, intellect=-2),
        "barger": L("Finally. A door. He has waited his whole life.", intellect=3, strength=1),
        "stalker": L("Sits on top of the door, balanced, watching.", intellect=2, agility=2),
        "purrsuader": L("Waits by the door until a human opens it for her.", charm=3),
        "tyrant": L("Requires the door open. And then closed. And then open.", charm=2, strength=1),
        "weaver": L("Slips through the gap before the door is properly open.", agility=3),
        "dinner": L("Cries at the door because dinner might be behind it.", charm=2, intellect=-1),
        "alley": L("Checks the door is not a trap, then goes through.", intellect=2, agility=1),
    },
    "🌧️": {
        "pouncer": L("Pounces raindrops on the glass, one at a time.", agility=2, intellect=-1),
        "loaf": L("Sits by the window and is glad to be indoors.", strength=1, intellect=2),
        "chonk": L("Sees the rain and returns to bed immediately.", strength=1, agility=-1),
        "ricochet": L("Runs from window to window as the rain moves.", agility=2),
        "ghost": L("Sits in the dark watching the rain, unblinking.", intellect=2, agility=1),
        "gremlin": L("Screams at the rain. The rain continues.", charm=1, intellect=-1),
        "barger": L("Checks every door in case one leads to dry outside.", intellect=2, strength=1),
        "stalker": L("Watches the rain from the highest windowsill.", intellect=2),
        "purrsuader": L("Blames the rain on the nearest human, at length.", charm=2, intellect=1),
        "tyrant": L("Demands the rain be stopped. Is astonished it continues.", charm=2),
        "weaver": L("Winds round wet ankles by the door, delighted.", charm=2, agility=1),
        "dinner": L("Points out that rainy days are for extra dinners.", charm=2, intellect=1),
        "alley": L("Knows exactly which corner stays dry. Goes there.", intellect=2, strength=1),
    },
    "🪑": {
        "pouncer": L("Waits under the chair for ankles. Ankles arrive.", strength=1, agility=2),
        "loaf": L("Occupies the chair entirely. The chair is resolved.", strength=2, intellect=1),
        "chonk": L("Fits the chair the way water fits a glass.", strength=2, charm=1),
        "ricochet": L("Uses the chair as a launch pad, twice.", agility=3),
        "ghost": L("Is under the chair. Has been for some time.", agility=1, intellect=2),
        "gremlin": L("Shreds the side of the chair while watching you.", strength=2, charm=-1),
        "barger": L("Works out how to get the chair to the counter.", intellect=3),
        "stalker": L("Uses the chair to reach the thing above the chair.", intellect=2, agility=1),
        "purrsuader": L("Takes the warm chair the second it is vacated.", charm=2, intellect=2),
        "tyrant": L("The chair is a throne and always has been.", charm=3),
        "weaver": L("Figure-eights the chair legs without touching one.", agility=3),
        "dinner": L("Sits on the chair at the table and waits to be served.", charm=2, intellect=1),
        "alley": L("A chair is off the ground and off the ground is safe.", intellect=2, strength=1),
    },
    "💉": {
        "pouncer": L("Ambushes the vet's hand. It was always going to happen.", strength=2, charm=-1),
        "loaf": L("Accepts the injection without moving at all.", strength=2, intellect=1),
        "chonk": L("Becomes immovable. Three people are now involved.", strength=3, agility=-1),
        "ricochet": L("Is behind the radiator before the cap is off.", agility=3),
        "ghost": L("Cannot be found. The appointment is rescheduled.", agility=3, intellect=1),
        "gremlin": L("Bites the vet. Everyone saw it coming except the vet.", strength=1, charm=-2),
        "barger": L("Works out the carrier door and is halfway home.", intellect=3, agility=1),
        "stalker": L("Watches from the top of the cupboard. Will not come down.", intellect=2, agility=2),
        "purrsuader": L("Is so charming the vet apologises to her.", charm=3, intellect=1),
        "tyrant": L("Regards the whole appointment as a serious betrayal.", charm=2, strength=-1),
        "weaver": L("Winds round the vet's legs and is briefly forgotten.", agility=2, charm=1),
        "dinner": L("Screams as though starving. The vet is unmoved.", charm=2, intellect=-1),
        "alley": L("Has had worse from a fence. Sits through it.", strength=2, intellect=1),
    },
    "🥊": {
        "pouncer": L("Grabs the glove with both paws and kicks it.", strength=2, agility=1),
        "loaf": L("Sits on the glove. The fight is over, apparently.", strength=2, intellect=1),
        "chonk": L("Leans on the glove until it stops being upright.", strength=2, charm=1),
        "ricochet": L("Bounces off the glove and comes straight back.", agility=2, strength=1),
        "ghost": L("Hits the glove once from somewhere behind it.", agility=2, intellect=1),
        "gremlin": L("Attacks the glove with everything, at 3am energy.", strength=2, charm=-1),
        "barger": L("Works out the glove is padded and stops worrying.", intellect=2, strength=1),
        "stalker": L("Drops onto the glove from above without warning.", intellect=1, agility=2),
        "purrsuader": L("Bats the glove gently and is called brave.", charm=3),
        "tyrant": L("Sits on the glove. She does not need a glove.", charm=2, strength=1),
        "weaver": L("Winds round the glove until nobody can swing it.", agility=2, charm=1),
        "dinner": L("Checks whether the glove is food. It smells promising.", charm=1, intellect=-1),
        "alley": L("Has been in real fights. Regards the glove as soft.", strength=2, intellect=1),
    },
    "👖": {
        "loaf": L("Sits on them. They are warm now, and they are his.", strength=1, intellect=1),
        "pouncer": L("Waits inside one leg for eleven minutes. Something will walk past.", agility=2),
        "chonk": L("Gets into them. Gets stuck in them. Refuses all help.", strength=2, agility=-1),
        "ricochet": L("Wears them briefly at full speed, off three walls.", agility=2, strength=-1),
        "ghost": L("Is inside the trousers. Nobody saw it get in.", agility=1, intellect=1),
        "gremlin": L("Shreds them to threads in nine seconds and is delighted.", strength=2, charm=-1),
        "barger": L("Works out the pockets. Removes everything in them.", intellect=2),
        "stalker": L("Drags them onto the wardrobe. They live up there now.", intellect=1, agility=1),
        "purrsuader": L("Lies on them so you cannot leave the house.", intellect=2, charm=1),
        "tyrant": L("Sits on them while you are still wearing them.", charm=2, strength=1),
        "weaver": L("Winds through both legs and comes out fully dressed.", charm=2, agility=1),
        "dinner": L("Cries into the trousers until fed.", charm=2),
        "alley": L("Has slept in worse. Sleeps in these.", strength=1, charm=1),
    },
    "🕯️": {
        "loaf": L("Sits close. Is warm. Is slightly on fire. Unbothered.", strength=1, intellect=-1),
        "pouncer": L("Stalks the flame. The flame does not move. Confusing.", agility=1, intellect=-1),
        "chonk": L("Blocks all the light. Room goes dark.", strength=2),
        "ricochet": L("Knocks it over twice at speed. House survives.", agility=2, intellect=-2),
        "ghost": L("Is lit from below and looks appalling.", intellect=1, charm=-1),
        "gremlin": L("Bats the flame. Learns. Bats it again. Learns nothing.", agility=1, intellect=-2),
        "barger": L("Works out heat before touching it. Rare and smug.", intellect=3),
        "stalker": L("Watches from above, planning something with wax.", intellect=2),
        "purrsuader": L("Arranges herself in the candlelight. Devastating.", charm=3),
        "tyrant": L("Sits between you and the candle. Deal with it.", charm=2, strength=1),
        "weaver": L("Winds past it four times without singeing a hair.", agility=3),
        "dinner": L("Cries at a candle. It is not food. She insists.", charm=2, intellect=-1),
        "alley": L("Fire means people. People mean food. Approaches.", intellect=1, charm=1),
    },
}


VARIATION = chr(0xFE0F)


def normalise(char: str) -> str:
    """Emoji with and without the variation selector are the same object.

    Discord sends some reactions with a trailing U+FE0F and the catalogue stores
    bare codepoints, so 🕷️ from a reaction and 🕷 from the catalogue are two
    different strings for the same spider. Without this, every line written for
    one of those objects is simply never found.
    """
    return (char or "").replace(VARIATION, "")


def written_for(char: str, class_key: str):
    """The hand-written line for this cell, or ``None`` if it is not written yet."""
    return _INDEX.get(normalise(char), {}).get(class_key)


_INDEX = {normalise(char): lines for char, lines in WRITTEN.items()}


def progress(total_objects: int, total_classes: int) -> dict:
    """How much of the grid is genuinely written, for the panel to show."""
    cells = sum(len(v) for v in WRITTEN.values())
    return {"objects": len(WRITTEN), "cells": cells,
            "total_objects": total_objects, "total_cells": total_objects * total_classes}
