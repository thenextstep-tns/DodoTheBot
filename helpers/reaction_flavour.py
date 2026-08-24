"""
What to write in eighteen thousand cells.

Hand-writing 1,372 objects times 13 classes is not a thing a person does, and a
grid that is 99% blank is not an exploration game. So the cells are *written*
rather than generated: every line here was typed by hand, but it carries the
object's own name, so one line about being shown an animal reads differently for
a hedgehog than for a whale.

Three layers, most specific first:

1. :data:`SPECIFIC` — a particular object shown to a particular class, for the
   jokes that only work once. A mammoth is a remark about a Chonk's size. A
   ninja is a role model to a Ghost.
2. :data:`LINES` — a class and a *kind* of object. Showing a Loaf any container
   ends the same way, and that is correct: it gets in it.
3. :data:`FALLBACK` — the class meeting something it has no opinion about, which
   is still in character, because having no opinion is a thing cats are good at.

House rules for anything added here: present tense, one thing happens, under
about twelve words, and the joke is the cat rather than the object. No em
dashes. Nothing cruel: these are cats being cats, and the reason it is funny is
that they are all completely certain they are behaving reasonably.
"""

from __future__ import annotations

import re
import zlib

# --------------------------------------------------------------------------- #
#  What kind of thing is this?
# --------------------------------------------------------------------------- #
# Checked in order, first hit wins, so put the narrow ones first. Matching is on
# the Unicode name, which is wordy and literal and therefore unusually good at
# this: "SMILING FACE WITH HEART-SHAPED EYES" says face, and says it in English.
TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("family", ("family", "baby", "couple", "pregnan*", "kiss", "wedding", "cradl*", "nursing")),
    ("big", ("mammoth", "whale", "elephant", "dinosaur", "sauropod", "rex", "hippopotamus",
             "rhinoceros", "bison", "gorilla", "bear", "camel", "giraffe", "ox", "shark")),
    ("stealth", ("ninja", "spy", "detective", "sleuth", "ghost", "shadow", "mask", "burglar")),
    ("face", ("face", "smiling", "grinning", "frowning", "pouting", "crying", "expression",
              "smirk", "grimacing", "eyes", "tongue")),
    ("hand", ("hand", "finger", "thumbs", "palm", "fist", "clap", "wave", "arm", "nail")),
    ("food", ("food", "fish", "meat", "cheese", "bread", "cake", "fruit", "apple", "banana",
              "pizza", "burger", "rice", "egg", "milk", "cook*", "bacon", "chicken", "shrimp",
              "cookie", "candy", "honey", "butter", "sandwich", "taco", "sushi", "soup",
              "salad", "pie", "doughnut", "popcorn", "peach", "grapes", "cherr*", "melon",
              "lemon", "carrot", "potato", "corn", "beans")),
    ("animal", ("cat", "dog", "mouse", "rat", "bird", "fox", "wolf", "horse", "cow", "pig",
                "sheep", "goat", "rabbit", "squirrel", "hedgehog", "otter", "badger", "monkey",
                "lion", "tiger", "leopard", "deer", "frog", "snake", "turtle", "lizard",
                "crocodile", "penguin", "owl", "duck", "swan", "chick", "bug", "spider",
                "butterfly", "bee", "ant", "snail", "worm", "crab", "octopus", "seal",
                "sloth", "skunk", "raccoon", "bat", "dodo", "paw", "hatching*")),
    ("plant", ("plant", "flower", "tree", "leaf", "leaves*", "herb", "cactus", "mushroom",
               "blossom", "rose", "tulip", "clover", "seedling", "palm", "bouquet", "wheat")),
    ("water", ("water", "wave", "droplet", "rain", "ocean", "sea", "swim*", "shower", "bath*",
               "sweat", "fountain", "ice", "snow", "umbrella", "beach")),
    ("fire", ("fire", "flame", "candle", "explosion", "firework", "volcano", "hot", "sun",
              "light bulb", "lantern", "torch", "sparkler", "bomb")),
    ("vehicle", ("car", "truck", "bus", "train", "plane", "rocket", "boat", "ship", "bicycle",
                 "scooter", "tractor", "helicopter", "taxi", "motorcycle", "sled", "skateboard")),
    ("tool", ("tool", "hammer", "wrench", "screwdriver", "saw", "axe", "knife", "scissors",
              "drill", "nut and bolt", "pick", "shovel", "broom", "brush", "magnet", "gear",
              "chain", "hook", "ladder", "rope", "toolbox", "clamp")),
    ("container", ("box", "basket", "bag", "bucket", "jar", "can", "bottle", "cup", "bowl",
                   "envelope", "suitcase", "package", "crate", "pot", "briefcase", "purse",
                   "backpack", "luggage", "drawer", "cabinet", "wastebasket")),
    ("clothes", ("shirt", "trousers", "jeans", "dress", "coat", "sock", "shoe", "boot",
                 "hat", "cap", "glove", "scarf", "sandal", "kimono", "sari", "bikini",
                 "necktie", "apron", "sunglasses", "glasses", "crown", "ring")),
    ("money", ("money", "coin", "dollar", "euro", "yen", "pound", "bank", "credit card",
               "gem", "diamond", "treasure", "chart", "receipt", "moai")),
    ("music", ("music", "note", "guitar", "drum", "piano", "trumpet", "violin", "saxophone",
               "accordion", "banjo", "bell", "speaker", "headphone", "microphone", "radio")),
    ("tech", ("computer", "laptop", "phone", "screen", "keyboard", "printer", "mouse button",
              "camera", "television", "battery", "plug", "disk", "cd", "dvd", "joystick",
              "videocassette", "satellite", "antenna", "robot")),
    ("paper", ("paper", "book", "scroll", "newspaper", "note", "page", "card", "label",
               "bookmark", "ledger", "calendar", "memo", "clipboard", "chart", "file")),
    ("sport", ("ball", "sport", "trophy", "medal", "goal", "racket", "bat and ball", "dart",
               "bowling", "boxing", "skate", "ski", "surf", "kite", "flag in hole")),
    ("spooky", ("skull", "crossbones", "coffin", "headstone", "alien", "monster", "zombie",
                "vampire", "witch", "demon", "goblin", "biohazard", "radioactive", "urn")),
    ("weather", ("cloud", "sun", "moon", "star", "wind", "tornado", "fog", "rainbow",
                 "lightning", "thermometer", "comet", "milky way")),
    ("building", ("house", "building", "castle", "church", "hospital", "hotel", "school",
                  "office", "factory", "shop", "stadium", "bridge", "tent", "door", "window")),
    ("time", ("clock", "watch", "hourglass", "timer", "alarm", "calendar", "oclock")),
    ("symbol", ("arrow", "sign", "symbol", "mark", "button", "circle", "square", "triangle",
                "diamond shape", "cross", "check", "curly loop", "asterisk", "letter")),
)

FALLBACK_TAG = "thing"


_MATCHERS: dict[str, object] = {}


def _matcher(needles: tuple):
    """One regex per tag, matching whole words only.

    Plain substring matching put a European castle in the tool bin, because
    "eu-ROPE-an" contains rope. It also made a box an ox, a bath a bat, and a
    plant an ant. Needles are whole words unless they end in a star, which marks
    the handful that are deliberate prefixes.
    """
    key = chr(30).join(needles)
    if key not in _MATCHERS:
        parts = []
        for needle in needles:
            escaped = re.escape(needle.rstrip("*"))
            parts.append(escaped + ("" if needle.endswith("*") else r"\b"))
        _MATCHERS[key] = re.compile(r"\b(?:" + "|".join(parts) + r")")
    return _MATCHERS[key]


def tag_for(name: str) -> str:
    """Which kind of thing this is, from its Unicode name."""
    lowered = name.lower()
    for tag, needles in TAGS:
        if _matcher(needles).search(lowered):
            return tag
    return FALLBACK_TAG


def _article(thing: str) -> str:
    """"a" or "an", because "a accordion" undoes a whole line's worth of care."""
    return "an" if thing[:1] in "aeiou" else "a"


def _thing(name: str) -> str:
    """The object as you would say it out loud, for dropping into a sentence."""
    cleaned = name.lower()
    cleaned = re.sub(r"^(black|white|heavy|large|small|medium)\s+", "", cleaned)
    cleaned = re.sub(r"\s+(symbol|sign|selector|ornament)$", "", cleaned)
    return cleaned.strip() or "thing"


# --------------------------------------------------------------------------- #
#  The lines
# --------------------------------------------------------------------------- #
# {thing} becomes the object's name. Stats are the fight-long change, and they
# are small on purpose: a cell is a nudge, and a fight is a pile of nudges.
def L(text: str, **stats: int) -> tuple:
    return (text, {k: v for k, v in stats.items() if v})


LINES: dict[str, dict[str, list]] = {
    "pouncer": {
        "face": [L("Takes the {thing} as a challenge and crouches.", strength=1),
                 L("Stares back at the {thing}. Neither of them blinks.", intellect=1)],
        "animal": [L("Has already decided where the {thing} will be ambushed.", strength=2),
                   L("Follows the {thing} with its whole body, badly hidden.", agility=1)],
        "food": [L("Ambushes the {thing}. It was not going anywhere.", strength=1, charm=-1)],
        "big": [L("Sizes up the {thing} and commits anyway.", strength=2, intellect=-1)],
        "container": [L("Gets in the {thing}. Waits. This is the good part.", agility=2)],
        "tool": [L("Attacks the {thing} the moment it moves.", strength=1)],
        "plant": [L("Hides behind the {thing}, entirely visible.", agility=1, intellect=-1)],
        "water": [L("Bats the {thing} once, then denies knowing about water.", agility=1)],
        "fire": [L("Stalks the {thing} and thinks better of it, just in time.", intellect=1)],
        "vehicle": [L("Would ambush the {thing} if it ever stopped.", strength=1)],
        "money": [L("Pounces the {thing} off the table for sport.", agility=1)],
        "symbol": [L("Pounces the {thing}. Nothing happens. Pounces it again.", strength=1, intellect=-1)],
    },
    "loaf": {
        "face": [L("Regards the {thing} without moving a single muscle.", intellect=1),
                 L("The {thing} is noted. The {thing} changes nothing.", intellect=1)],
        "animal": [L("Lets the {thing} come to him. It usually does.", strength=1, intellect=1)],
        "food": [L("Would like the {thing} brought over, please.", strength=1)],
        "big": [L("Two heavy things sitting near each other. Ideal.", strength=2)],
        "container": [L("Fits inside the {thing}. Somehow. Will not be leaving.", strength=2)],
        "tool": [L("Sits on the {thing}. Work is over.", strength=1, agility=-1)],
        "plant": [L("Flattens the {thing} into a nest and takes full credit.", strength=1)],
        "water": [L("Declines the {thing} with enormous dignity.", intellect=2)],
        "fire": [L("Sits close to the {thing}. Warm. Slightly singed. Unbothered.", strength=1, agility=-1)],
        "vehicle": [L("The {thing} is warm. That is the only relevant fact.", strength=1)],
        "money": [L("Sits on the {thing}. It is a cushion with numbers.", strength=1)],
        "symbol": [L("Has considered the {thing} and has no notes.", intellect=2)],
    },
    "chonk": {
        "face": [L("Assumes the {thing} is about him. Somehow it always is.", charm=1),
                 L("Answers the {thing} with a slow blink and a wobble.", charm=2)],
        "animal": [L("Would share a meal with the {thing}. Would take the bigger half.", strength=1)],
        "food": [L("The {thing} is gone. Looks around for the second {thing}.", strength=2, agility=-1)],
        "big": [L("Takes the {thing} as a personal remark about his size.", strength=2, charm=-1)],
        "container": [L("Does not fit in the {thing}. Gets in the {thing} regardless.", strength=2, agility=-2)],
        "tool": [L("Lies across the {thing} so nobody can use it.", strength=1)],
        "plant": [L("Eats a bit of the {thing}, then regrets it publicly.", strength=1, intellect=-1)],
        "water": [L("Wants nothing to do with the {thing} and says so loudly.", charm=1)],
        "fire": [L("Blocks the {thing} completely. Room goes dark.", strength=2)],
        "vehicle": [L("Considers the {thing} and decides it would need a bigger one.", charm=1)],
        "money": [L("Sits on the {thing} until somebody negotiates.", charm=2)],
        "symbol": [L("Decides the {thing} is a rude gesture and sulks handsomely.", charm=1, intellect=-1)],
    },
    "ricochet": {
        "face": [L("Bounces off two walls and comes back to check the {thing} again.", agility=2),
                 L("Reacts to the {thing} at a speed nobody asked for.", agility=1)],
        "animal": [L("Chases the {thing}, overshoots, tries to look deliberate.", agility=2, intellect=-1)],
        "food": [L("Takes the {thing} at a full run and eats it airborne.", agility=1, strength=1)],
        "big": [L("Runs a lap of the {thing}. Twice. For information.", agility=2)],
        "container": [L("Enters the {thing} at speed. The {thing} relocates.", agility=2, strength=1)],
        "tool": [L("Bats the {thing} under the sofa within four seconds.", agility=2)],
        "plant": [L("Corners on the {thing} and takes it with him.", agility=1, charm=-1)],
        "water": [L("Touches the {thing} and is instantly elsewhere.", agility=2)],
        "fire": [L("Knocks the {thing} over twice. House survives.", agility=1, intellect=-2)],
        "vehicle": [L("Races the {thing} down the hall and calls it a draw.", agility=2)],
        "money": [L("Sends the {thing} skidding under the fridge forever.", agility=1)],
        "symbol": [L("Whacks the {thing} until it stops being interesting.", agility=1, strength=1)],
    },
    "ghost": {
        "face": [L("Watches the {thing} from somewhere nobody is looking.", agility=1, intellect=1),
                 L("Is gone by the time anyone reacts to the {thing}.", agility=2)],
        "animal": [L("Studies how the {thing} moves. Takes notes. Improves.", intellect=2)],
        "food": [L("The {thing} is gone. Nobody saw the {thing} go.", agility=2)],
        "big": [L("Notes that the {thing} could never do this, and vanishes.", agility=1, intellect=1)],
        "container": [L("Is inside the {thing} already. Has been for some time.", agility=1, intellect=2)],
        "tool": [L("Borrows the {thing} silently. It is never seen again.", intellect=2)],
        "plant": [L("Uses the {thing} as cover, which is exactly what it was for.", agility=2)],
        "water": [L("Left the room the moment the {thing} appeared.", agility=2, intellect=1)],
        "fire": [L("Is lit from below by the {thing} and looks appalling.", intellect=1, charm=-1)],
        "vehicle": [L("Was in the {thing} the whole time. Surprise.", agility=1, intellect=1)],
        "money": [L("The {thing} moves six inches with nobody near it.", intellect=2)],
        "symbol": [L("Treats the {thing} as a signal meant only for him.", intellect=2)],
    },
    "gremlin": {
        "face": [L("Copies the {thing} back at you, worse.", charm=1, intellect=-1),
                 L("Answers the {thing} with a noise you have not heard before.", charm=1)],
        "animal": [L("Wants to fight the {thing}. Wants to be its friend. Both, now.", agility=1, charm=1)],
        "food": [L("Eats the {thing} too fast, then complains about it.", strength=1, intellect=-1)],
        "big": [L("Challenges the {thing}. Loses. Challenges it again.", strength=1, charm=-1)],
        "container": [L("Destroys the {thing}, then mourns the {thing}.", strength=1, charm=-1)],
        "tool": [L("Shreds the {thing} in nine seconds and is delighted.", strength=2, charm=-1)],
        "plant": [L("Eats the {thing}. Sicks up the {thing}. Repeats tomorrow.", strength=1, intellect=-2)],
        "water": [L("Puts a paw in the {thing} on purpose, screams about it.", agility=1, charm=-1)],
        "fire": [L("Bats the {thing}. Learns. Bats it again. Learns nothing.", agility=1, intellect=-2)],
        "vehicle": [L("Rides the {thing} without permission or a plan.", agility=2, intellect=-1)],
        "money": [L("Knocks the {thing} off the table while looking at you.", charm=2, intellect=-1)],
        "symbol": [L("Wears the {thing}. Refuses to explain the {thing}.", charm=2)],
    },
    "barger": {
        "face": [L("Works out what the {thing} wants, then does not provide it.", intellect=2),
                 L("Files the {thing} under things that open eventually.", intellect=1)],
        "animal": [L("Learns how the {thing} gets in, and copies it by Thursday.", intellect=2)],
        "food": [L("Locates where the {thing} is kept. This is the real prize.", intellect=2, strength=1)],
        "big": [L("Measures the {thing} against the cat flap. Optimistic.", intellect=1, strength=1)],
        "container": [L("Opens the {thing} from the inside. Learns a door.", intellect=3)],
        "tool": [L("Understands the {thing} correctly and immediately.", intellect=2)],
        "plant": [L("Digs the {thing} out to see what is under it.", strength=1, intellect=1)],
        "water": [L("Works out the tap. Nobody is safe now.", intellect=3)],
        "fire": [L("Understands heat before touching it. Rare and smug.", intellect=3)],
        "vehicle": [L("Gets into the {thing} the second a door opens.", intellect=2, agility=1)],
        "money": [L("Knows which drawer the {thing} lives in.", intellect=2)],
        "symbol": [L("Reads the {thing} as instructions and follows them badly.", intellect=1)],
    },
    "stalker": {
        "face": [L("Observes the {thing} from the top of the wardrobe.", intellect=2),
                 L("Has been watching the {thing} for some time now.", intellect=1, agility=1)],
        "animal": [L("Tracks the {thing} from above like weather.", intellect=2)],
        "food": [L("Takes the {thing} somewhere high to eat, unjudged.", intellect=1, agility=2)],
        "big": [L("Waits for the {thing} to look away. It will.", intellect=2)],
        "container": [L("Stacks the {thing} and gains a metre of altitude.", intellect=2, agility=1)],
        "tool": [L("Puts the {thing} on the shelf. It lives there now.", intellect=2)],
        "plant": [L("Uses the {thing} to get one shelf higher.", agility=2)],
        "water": [L("Watches the {thing} from a dry and superior position.", intellect=2)],
        "fire": [L("Observes the {thing} from above, planning something with wax.", intellect=2)],
        "vehicle": [L("Sits on the roof of the {thing} and surveys the land.", intellect=1, agility=1)],
        "money": [L("Knocks the {thing} off the shelf one item at a time.", intellect=1, agility=1)],
        "symbol": [L("Considers the {thing} at length from the high ground.", intellect=2)],
    },
    "purrsuader": {
        "face": [L("Mirrors the {thing} until you feel personally responsible.", charm=2, intellect=1),
                 L("Uses the {thing} against you within the minute.", intellect=2)],
        "animal": [L("Has the {thing} doing favours by the end of the day.", charm=2, intellect=1)],
        "food": [L("Gets a second {thing} out of you without standing up.", charm=2, intellect=1)],
        "big": [L("Is not impressed by the {thing}. Is impressed by leverage.", intellect=2)],
        "container": [L("Sits in the {thing} and looks at you until photographed.", charm=2)],
        "tool": [L("Lies on the {thing} so the job stops. The job stops.", intellect=2, charm=1)],
        "plant": [L("Poses beside the {thing}. Somebody says aww. That was the plan.", charm=3)],
        "water": [L("Makes the {thing} your problem in under a minute.", intellect=2)],
        "fire": [L("Arranges herself in the light of the {thing}. Devastating.", charm=3)],
        "vehicle": [L("Will be carried to the {thing}, thank you.", charm=2)],
        "money": [L("Understands exactly what the {thing} is for.", intellect=3)],
        "symbol": [L("Treats the {thing} as a contract you have already signed.", intellect=2)],
    },
    "tyrant": {
        "face": [L("Accepts the {thing} as tribute and offers nothing back.", charm=2),
                 L("The {thing} was for her. Everything is for her.", charm=2)],
        "animal": [L("Outranks the {thing}. The {thing} has not been told.", charm=2, strength=1)],
        "food": [L("The {thing} was always hers. You were merely holding it.", charm=2, strength=1)],
        "big": [L("Sits on the {thing}. Size is a matter of attitude.", charm=2, strength=1)],
        "container": [L("Claims the {thing}. It was always going to be hers.", charm=2)],
        "tool": [L("Sits on the {thing} until the project is abandoned.", charm=1, strength=1)],
        "plant": [L("Sits in the {thing}. It is a throne with leaves.", charm=2)],
        "water": [L("Will not be touching the {thing}. Someone else may.", charm=1)],
        "fire": [L("Sits between you and the {thing}. Deal with it.", charm=2, strength=1)],
        "vehicle": [L("Occupies the {thing}. Nobody is going anywhere.", charm=1, strength=2)],
        "money": [L("Sits on the {thing}. Negotiations may now begin.", charm=3)],
        "symbol": [L("Considers the {thing} an official recognition of herself.", charm=2)],
    },
    "weaver": {
        "face": [L("Winds round your ankles until the {thing} is forgotten.", charm=2, agility=1),
                 L("Answers the {thing} by being underfoot at speed.", agility=2)],
        "animal": [L("Figure-eights the {thing} until it gives up walking.", agility=2, charm=1)],
        "food": [L("Circles your ankles until the {thing} falls. It falls.", charm=2, agility=1)],
        "big": [L("Weaves between the feet of the {thing}, entirely unafraid.", agility=2, charm=1)],
        "container": [L("Around the {thing}, through it, out, and around again.", agility=2)],
        "tool": [L("Winds through the {thing} without disturbing one part of it.", agility=3)],
        "plant": [L("Threads through the {thing} and comes out wearing some.", agility=2, charm=1)],
        "water": [L("Skirts the {thing} at exactly one paw's distance.", agility=2)],
        "fire": [L("Passes the {thing} four times without singeing a hair.", agility=3)],
        "vehicle": [L("Under the {thing}, out the other side, no explanation.", agility=2)],
        "money": [L("Trips you into dropping the {thing}. Not an accident.", agility=2, charm=1)],
        "symbol": [L("Loops around the {thing} for reasons of her own.", agility=1, charm=1)],
    },
    "dinner": {
        "face": [L("Reads the {thing} as sympathy and escalates immediately.", charm=2),
                 L("Answers the {thing} with the sound of a cat never once fed.", charm=2)],
        "animal": [L("Tells the {thing} at length about the state of her bowl.", charm=2)],
        "food": [L("Eats the {thing}, then reports having received nothing.", charm=3, intellect=1)],
        "big": [L("Assumes the {thing} is a portion. An encouraging one.", charm=1, strength=1)],
        "container": [L("Cries from inside the {thing}. Acoustics are excellent.", charm=3)],
        "tool": [L("Checks whether the {thing} is food. Twice, to be fair to it.", intellect=-1, charm=1)],
        "plant": [L("Tries the {thing}. It is not dinner. Files a complaint.", charm=1, intellect=-1)],
        "water": [L("Would rather the {thing} came in a bowl, freshly poured.", charm=2)],
        "fire": [L("Cries at the {thing}. It is not food. She insists it should be.", charm=2, intellect=-1)],
        "vehicle": [L("Assumes the {thing} is bringing dinner. Waits at the door.", charm=2)],
        "money": [L("Knows the {thing} converts into food somehow.", intellect=2, charm=1)],
        "symbol": [L("Interprets the {thing} as a promise of supper.", charm=2, intellect=-1)],
    },
    "alley": {
        "face": [L("Has seen the {thing} before, on a worse night.", intellect=1, strength=1),
                 L("Reads the {thing} correctly and keeps its own counsel.", intellect=1, charm=1)],
        "animal": [L("Knows the {thing}. They have an understanding.", charm=1, intellect=1)],
        "food": [L("Eats the {thing} fast, watching the door. Old habit.", strength=2, agility=1)],
        "big": [L("Has been near bigger. Was fine. Is fine now.", strength=1, intellect=1)],
        "container": [L("{A} {thing} is a house. Finally, a house.", strength=1, charm=1)],
        "tool": [L("Has found a use for {a} {thing} before, and finds one again.", intellect=2)],
        "plant": [L("Knows which bit of the {thing} is safe. Eats that bit.", intellect=2)],
        "water": [L("Has been rained on. The {thing} holds no fear.", strength=1, intellect=1)],
        "fire": [L("Fire means people. People mean food. Approaches politely.", intellect=1, charm=1)],
        "vehicle": [L("Has slept under {a} {thing} warmer than this one.", strength=1, intellect=1)],
        "money": [L("Has watched people go strange about {a} {thing} before.", intellect=2)],
        "symbol": [L("Has seen the {thing} on a door and knows what it means.", intellect=2)],
    },
}


# Added after the first pass, for the tags that were landing on the fallback.
# Same rule as everything above: it has to make sense for every object in the
# tag, to somebody who has never played this before.
for _key, _extra in {
    "pouncer": {
        "hand": L("Grabs the {thing} with both paws and holds on.", strength=1, agility=1),
        "music": L("Stalks the {thing} until it makes the noise again.", agility=1),
        "tech": L("Pounces the {thing} the moment the screen moves.", agility=2),
        "paper": L("Ambushes the {thing} from underneath it.", agility=2),
        "clothes": L("Attacks the {thing} while it is still being worn.", strength=1, charm=-1),
        "sport": L("Catches the {thing} in mid air. Does not give it back.", strength=1, agility=1),
        "weather": L("Crouches at the window and chatters at the {thing}.", agility=1),
        "building": L("Finds the one gap in the {thing} and waits inside it.", agility=2),
        "time": L("Attacks the ticking. The ticking continues.", agility=1, intellect=-1),
        "spooky": L("Pounces the {thing} before it can do anything first.", strength=2),
        "family": L("Ambushes several ankles at once. A rich target.", agility=2),
        "stealth": L("Copies the {thing} and hides behind a curtain, tail out.", agility=1, intellect=-1),
    },
    "loaf": {
        "hand": L("Allows the {thing}. Does not respond to the {thing}.", intellect=1),
        "music": L("Sits through the entire {thing} without opening an eye.", intellect=2),
        "tech": L("Sits on the {thing} because it is warm and flat.", strength=1, intellect=1),
        "paper": L("Sits on the {thing}. It was being read. It is not now.", strength=1, intellect=1),
        "clothes": L("Sits on the {thing} and warms it thoroughly.", strength=1, charm=1),
        "sport": L("Declines to chase the {thing}. Declines firmly.", intellect=2),
        "weather": L("Observes the {thing} through glass. Stays in.", intellect=2),
        "building": L("Picks one warm corner of the {thing} and settles.", strength=1, intellect=1),
        "time": L("Outlasts the {thing}. Has all day.", intellect=2),
        "spooky": L("Sits beside the {thing}. Neither of them moves.", intellect=2),
        "family": L("Is picked up by all of them in turn. Endures it.", strength=1, charm=1),
        "stealth": L("Does not hide. Has never once hidden.", strength=2),
    },
    "chonk": {
        "hand": L("Headbutts the {thing} until it starts scratching.", charm=2),
        "music": L("Sits on the {thing} until the noise stops.", strength=2),
        "tech": L("Lies across the {thing}, warm side down.", strength=1, agility=-1),
        "paper": L("Sits on the {thing}. All of it. It is no longer visible.", strength=2),
        "clothes": L("Gets into the {thing} and cannot get out of the {thing}.", strength=2, agility=-2),
        "sport": L("Watches the {thing} roll away. Does not follow it.", strength=1, agility=-1),
        "weather": L("Refuses to go out in the {thing}. Sits by the door instead.", charm=1),
        "building": L("Occupies the warmest spot in the {thing} within a minute.", strength=1, charm=1),
        "time": L("Knows exactly what time the {thing} means. Dinner time.", charm=2),
        "spooky": L("Is unbothered by the {thing}. Is bothered by hunger.", strength=1, charm=1),
        "family": L("Is passed around and fed twice. A good day.", charm=2, strength=1),
        "stealth": L("Attempts to hide. Is entirely visible from all sides.", charm=2, agility=-1),
    },
    "ricochet": {
        "hand": L("Bats the {thing} four times and bolts.", agility=2),
        "music": L("Runs a full lap of the house when the {thing} starts.", agility=2),
        "tech": L("Walks across the {thing} at speed. Something has changed.", agility=1, intellect=-1),
        "paper": L("Shreds the {thing} and scatters it down the hall.", agility=2, strength=1),
        "clothes": L("Runs off with the {thing} and loses it somewhere.", agility=2),
        "sport": L("Sends the {thing} off three walls without stopping.", agility=2, strength=1),
        "weather": L("Tears round the room because the {thing} is happening.", agility=2),
        "building": L("Has been round the whole {thing} twice already.", agility=2),
        "time": L("Reacts to the alarm before anybody else is awake.", agility=2),
        "spooky": L("Bats the {thing} once, hard, and leaves at speed.", agility=1, strength=1),
        "family": L("Bounces off every person present in one circuit.", agility=2, charm=1),
        "stealth": L("Tries to sneak. Arrives at full speed instead.", agility=1, intellect=-1),
    },
    "ghost": {
        "hand": L("Is not there when the {thing} arrives.", agility=2),
        "music": L("Leaves the room the moment the {thing} starts.", agility=2, intellect=1),
        "tech": L("Sits behind the {thing} where the light does not reach.", intellect=2),
        "paper": L("The {thing} rustles. Nothing visible caused that.", intellect=2),
        "clothes": L("Is inside the {thing}. Nobody saw it get in.", agility=1, intellect=1),
        "sport": L("Takes the {thing} while everyone is looking elsewhere.", agility=2),
        "weather": L("Watches the {thing} from the darkest part of the sill.", intellect=2),
        "building": L("Knows a way into the {thing} that nobody else knows.", intellect=2, agility=1),
        "time": L("Appears the second the {thing} goes off, already awake.", agility=1, intellect=1),
        "spooky": L("Regards the {thing} as a colleague.", intellect=2, agility=1),
        "family": L("Is counted, then not counted, then found on a shelf.", agility=2),
        "stealth": L("Studies the {thing} closely. Takes notes. Improves.", agility=2, intellect=2),
    },
    "gremlin": {
        "hand": L("Grabs the {thing}, bites it gently, then bolts.", agility=1, charm=1),
        "music": L("Adds to the {thing} with a noise of its own.", charm=1, intellect=-1),
        "tech": L("Stands on the {thing} and sends a message to somebody.", charm=2, intellect=-1),
        "paper": L("Shreds the {thing} into confetti in nine seconds.", strength=2, charm=-1),
        "clothes": L("Wears the {thing} wrongly and refuses to remove it.", charm=2),
        "sport": L("Steals the {thing} mid game and hides it.", agility=2, charm=1),
        "weather": L("Screams at the {thing} through the window.", charm=1, intellect=-1),
        "building": L("Climbs the {thing} and cannot get down again.", agility=1, intellect=-2),
        "time": L("Answers the alarm by attacking the alarm.", strength=1, intellect=-1),
        "spooky": L("Wears the {thing}. Refuses to explain the {thing}.", charm=2),
        "family": L("Bites exactly one of them. Never the same one twice.", charm=1, intellect=-1),
        "stealth": L("Hides in plain sight and is very pleased with itself.", charm=2, intellect=-1),
    },
    "barger": {
        "hand": L("Studies the {thing}, then pushes it towards the food bowl.", intellect=2),
        "music": L("Finds where the noise comes from and stops it.", intellect=2),
        "tech": L("Presses the {thing} until something happens. Something does.", intellect=2),
        "paper": L("Moves the {thing} aside to see what is under it.", intellect=1, strength=1),
        "clothes": L("Gets into the {thing} through a sleeve, on purpose.", intellect=2),
        "sport": L("Works out where the {thing} will land and goes there.", intellect=2, agility=1),
        "weather": L("Looks at the {thing}, then at the cat flap. Decides.", intellect=2),
        "building": L("Finds the way into the {thing} within the hour.", intellect=3),
        "time": L("Learns what the {thing} means and wakes you first.", intellect=2),
        "spooky": L("Examines the {thing} at length. Concludes: bones.", intellect=2),
        "family": L("Identifies which one of them opens tins.", intellect=3),
        "stealth": L("Works out how the {thing} did it, then does it better.", intellect=2, agility=1),
    },
    "stalker": {
        "hand": L("Watches the {thing} from above and does not come down.", intellect=2),
        "music": L("Listens to the {thing} from the top of the bookcase.", intellect=2),
        "tech": L("Sits above the {thing}, watching the screen sideways.", intellect=2),
        "paper": L("Pushes the {thing} off the shelf, one sheet at a time.", intellect=1, agility=1),
        "clothes": L("Drags the {thing} up onto the wardrobe. It lives there.", intellect=1, agility=1),
        "sport": L("Tracks the {thing} in the air without moving its body.", intellect=2),
        "weather": L("Watches the {thing} from the highest window.", intellect=2),
        "building": L("Finds the highest point of the {thing} and takes it.", intellect=2, agility=1),
        "time": L("Waits out the {thing} from somewhere you cannot reach.", intellect=2),
        "spooky": L("Puts the {thing} on the shelf facing your bed.", intellect=2, charm=-1),
        "family": L("Observes all of them from the top of the door.", intellect=2),
        "stealth": L("Approves of the {thing}, quietly, from above.", intellect=2, agility=1),
    },
    "purrsuader": {
        "hand": L("Leans into the {thing} until it keeps going.", charm=3),
        "music": L("Sits on the {thing} until it is played to her instead.", charm=2, intellect=1),
        "tech": L("Sits between you and the {thing}. You put it down.", intellect=2, charm=1),
        "paper": L("Lies on the {thing} until the work stops. It stops.", intellect=2, charm=1),
        "clothes": L("Covers the {thing} in fur, affectionately, on purpose.", charm=2),
        "sport": L("Takes the {thing} and is chased. That was the goal.", charm=2, agility=1),
        "weather": L("Asks for the door. Sees the {thing}. Asks for the door again.", intellect=2),
        "building": L("Establishes which room she is not allowed in. Sleeps there.", intellect=2, charm=1),
        "time": L("Learns the {thing} and starts asking five minutes early.", intellect=3),
        "spooky": L("Poses beside the {thing} until somebody takes a photograph.", charm=2),
        "family": L("Works out which one of them gives in fastest.", intellect=2, charm=2),
        "stealth": L("Does not need to sneak. Is invited everywhere.", charm=3),
    },
    "tyrant": {
        "hand": L("Accepts the {thing}. Stops it when she is finished.", charm=2),
        "music": L("Sits on the {thing} mid performance.", charm=2, strength=1),
        "tech": L("Occupies the {thing}. The work is over for today.", charm=2, strength=1),
        "paper": L("Sits on the {thing} that you are reading.", charm=2),
        "clothes": L("The {thing} is a bed now. This is not negotiable.", charm=2, strength=1),
        "sport": L("Sits on the {thing} and dares anyone to want it.", charm=1, strength=1),
        "weather": L("Requires that the {thing} be turned off at once.", charm=2),
        "building": L("Claims the best chair in the {thing} permanently.", charm=2, strength=1),
        "time": L("Dinner happens when she says, not when the {thing} says.", charm=3),
        "spooky": L("Sits in the {thing}. It is a throne now.", charm=2, strength=1),
        "family": L("Selects one of them as staff. The others may watch.", charm=3),
        "stealth": L("Does not hide from anybody. Hiding is for staff.", charm=2),
    },
    "weaver": {
        "hand": L("Winds under the {thing} so it lands where she wants it.", charm=2, agility=1),
        "music": L("Weaves round the player's feet until the {thing} stops.", agility=2, charm=1),
        "tech": L("Walks across the {thing} slowly, tail up, twice.", charm=2, agility=1),
        "paper": L("Slides the {thing} off the desk in passing.", agility=2),
        "clothes": L("Threads through the {thing} and comes out wearing it.", agility=2, charm=1),
        "sport": L("Trips the player, not the {thing}. Same result.", agility=2, charm=1),
        "weather": L("Winds round your ankles at the door until it passes.", charm=2),
        "building": L("Knows every doorway in the {thing} and blocks the best one.", agility=1, charm=1),
        "time": L("Arrives at your ankles before the {thing} finishes.", agility=2, charm=1),
        "spooky": L("Threads straight through the {thing} without pausing.", agility=3),
        "family": L("Figure eights every one of them without being stepped on.", agility=2, charm=2),
        "stealth": L("Is underfoot the entire time and never once trodden on.", agility=3),
    },
    "dinner": {
        "hand": L("Sniffs the {thing} for food, finds none, and is wounded.", charm=2),
        "music": L("Sings along with the {thing}, badly, at length.", charm=2, intellect=-1),
        "tech": L("Sits on the {thing} and cries at whoever was using it.", charm=2),
        "paper": L("Checks whether the {thing} is food. It is not. It is chewed.", charm=1, intellect=-1),
        "clothes": L("Sleeps on the {thing} and wakes up hungry.", charm=2),
        "sport": L("Follows the {thing} briefly, in case it is food.", charm=1, intellect=-1),
        "weather": L("Complains at the {thing} as though you arranged it.", charm=2),
        "building": L("Cries in the corridor of the {thing}. Acoustics are excellent.", charm=3),
        "time": L("Knows the {thing} means dinner. Starts ten minutes early.", charm=2, intellect=1),
        "spooky": L("Cries at the {thing}. It does not feed her. She persists.", charm=2, intellect=-1),
        "family": L("Tells every one of them, separately, that she is starving.", charm=3, intellect=1),
        "stealth": L("Sneaks to the food bowl. Announces herself on arrival.", charm=2, intellect=-1),
    },
    "alley": {
        "hand": L("Accepts the {thing}, briefly, on its own terms.", charm=1, intellect=1),
        "music": L("Waits out the {thing} from under the nearest chair.", intellect=1, strength=1),
        "tech": L("Sleeps on the {thing} for the warmth and nothing else.", strength=1, intellect=1),
        "paper": L("Makes a bed of the {thing}. Paper is warmer than floor.", intellect=2),
        "clothes": L("Sleeps on the {thing}. Anything soft is worth having.", strength=1, charm=1),
        "sport": L("Watches the {thing} carefully. Does not join in.", intellect=1, agility=1),
        "weather": L("Finds cover before the {thing} arrives. Always has.", intellect=2),
        "building": L("Locates the warm vent in the {thing} immediately.", intellect=2),
        "time": L("Turns up at the same hour every day regardless.", intellect=1, charm=1),
        "spooky": L("Regards the {thing} calmly. Has seen worse in a bin.", intellect=1, strength=1),
        "family": L("Keeps a polite distance, then picks the kindest one.", intellect=1, charm=2),
        "stealth": L("Was already in the room before anyone opened a door.", agility=2, intellect=1),
    },
}.items():
    for _tag, _line in _extra.items():
        LINES.setdefault(_key, {}).setdefault(_tag, []).append(_line)


# What a class does when the thing is none of the above. These appear a lot, so
# they carry the class rather than the object.
FALLBACK: dict[str, list] = {
    "pouncer": [L("Crouches. Waits for the {thing} to make the first move.", strength=1),
                L("Wiggles, commits, and lands on the {thing} from above.", agility=1, strength=1)],
    "loaf": [L("Looks at the {thing}. Does not get up for the {thing}.", intellect=1),
             L("Sits down beside the {thing} and closes both eyes.", strength=1, intellect=1)],
    "chonk": [L("Sniffs the {thing} thoroughly, then lies down on it.", strength=1, charm=1),
              L("Tries to eat the {thing}. It is not food. He tries anyway.", strength=1, intellect=-1)],
    "ricochet": [L("Bats the {thing} across the room and chases it.", agility=2),
                 L("Knocks the {thing} under the sofa in under a second.", agility=1, strength=1)],
    "ghost": [L("Watches the {thing} from behind something.", agility=1, intellect=1),
              L("The {thing} moves. No cat is anywhere near the {thing}.", intellect=2)],
    "gremlin": [L("Bites the {thing} to find out what it does.", strength=1, intellect=-1),
                L("Pushes the {thing} off the table, holding eye contact.", charm=2, intellect=-1)],
    "barger": [L("Turns the {thing} over to see how it works.", intellect=2),
               L("Checks the {thing} for a way inside. There usually is one.", intellect=1, strength=1)],
    "stalker": [L("Carries the {thing} somewhere higher and leaves it there.", intellect=1, agility=1),
                L("Watches the {thing} from the top of the cupboard.", intellect=2)],
    "purrsuader": [L("Sits beside the {thing} and looks up at you slowly.", charm=2),
                   L("Puts one paw on the {thing} and waits for you to react.", intellect=2)],
    "tyrant": [L("Sits on the {thing}. The {thing} is now hers.", charm=2),
               L("Lies across the {thing} so nobody else can have it.", charm=1, strength=1)],
    "weaver": [L("Winds twice around the {thing} and once around your legs.", charm=2, agility=1),
               L("Puts herself between you and the {thing}, deliberately.", agility=1, charm=1)],
    "dinner": [L("Sniffs the {thing}, finds no food in it, and complains.", charm=2),
               L("Cries next to the {thing} until somebody comes over.", charm=1, intellect=-1)],
    "alley": [L("Gives the {thing} one careful look and keeps its distance.", intellect=1, strength=1),
              L("Finds a use for the {thing} that nobody intended.", intellect=2)],
}

# The jokes that only work once, for one object and one class.
SPECIFIC: dict[tuple, tuple] = {
    ("🦣", "chonk"): L("Takes the mammoth as a pointed remark and leaves the room.", charm=-2, strength=2),
    ("🦣", "alley"): L("Recognises a fellow survivor of something.", intellect=2, charm=1),
    ("🥷", "ghost"): L("Sits up straight. This is what he wants to be.", agility=2, intellect=2),
    ("🥷", "gremlin"): L("Is deeply confused by the ninja and bites the nearest thing.", intellect=-2, strength=1),
    ("👨‍👩‍👧", "dinner"): L("Thinks of her family and where she fits. Which is centrally.", charm=3, intellect=1),
    ("👨‍👩‍👧", "alley"): L("Watches the family a moment longer than it means to.", charm=2, intellect=1),
    ("🪞", "tyrant"): L("Meets her equal at last, and is delighted with her.", charm=3),
    ("🪞", "pouncer"): L("Ambushes a cat who ambushes back at exactly the same moment.", strength=1, intellect=-1),
    ("🚪", "barger"): L("Finally. A door. He has been waiting his entire life.", intellect=3, strength=1),
    ("🧹", "gremlin"): L("Declares war on the broom. The broom is unaware.", strength=1, charm=-1),
    ("📦", "loaf"): L("Fits. Somehow fits. Will not be leaving.", strength=2, intellect=1),
    ("🥒", "ricochet"): L("Was already gone before the cucumber landed.", agility=3),
    ("🐟", "dinner"): L("Eats the fish and reports never having been fed.", charm=3, intellect=1),
    ("💀", "ghost"): L("Immediate, unsettling kinship.", intellect=2, agility=1),
    ("🧶", "weaver"): L("Everything she believes in, in one object.", charm=2, agility=2),
    ("👑", "tyrant"): L("Puts it on. It fits. Of course it fits.", charm=3),
    ("🍞", "loaf"): L("Sits next to the bread. Two loaves, no conversation.", strength=1, intellect=2),
    ("🐈‍⬛", "chonk"): L("Recognises himself and is pleased with what he sees.", charm=2, strength=1),
    ("🎣", "stalker"): L("Watches the rod from the shelf, calculating the arc.", intellect=2, agility=1),
    ("🧻", "gremlin"): L("The entire roll, in under a minute, joyfully.", agility=2, charm=1),
    ("🛁", "chonk"): L("Absolutely not. Leaves at a speed nobody expected of him.", agility=2, charm=-1),
    ("☂️", "loaf"): L("Sits underneath. Weather is now somebody else's issue.", intellect=2),
    ("🔔", "purrsuader"): L("Learns what the bell means, and then who answers it.", intellect=3),
    ("🌡️", "dinner"): L("Cries at the thermometer in case it is a very thin fish.", charm=1, intellect=-1),
    ("🕯️", "ghost"): L("Is lit from below and looks genuinely upsetting.", intellect=1, charm=-1),
}


def for_cell(row: dict, class_key: str) -> dict:
    """The line for one object shown to one class.

    Deterministic: the same object and class always give the same line, because a
    reaction that changes every time you look at it is not something anybody can
    learn, and learning them is the game.
    """
    char, name = row["char"], row.get("name", "thing")
    if (char, class_key) in SPECIFIC:
        text, stats = SPECIFIC[(char, class_key)]
        return {"text": text, "stats": dict(stats), "source": "written"}

    tag = tag_for(name)
    options = LINES.get(class_key, {}).get(tag) or FALLBACK.get(class_key) or []
    if not options:
        return {"text": "", "stats": {}, "source": "empty"}
    index = zlib.crc32(f"{char}{class_key}".encode("utf-8")) % len(options)
    text, stats = options[index]
    thing = _thing(name)
    return {"text": text.format(thing=thing, a=_article(thing), A=_article(thing).capitalize()),
            "stats": dict(stats), "source": "written"}


def coverage_report(rows: list[dict], classes: list[str]) -> dict:
    """How many cells the written lines actually reach, and via which layer."""
    counts = {"written": 0, "empty": 0, "specific": len(SPECIFIC)}
    tags: dict[str, int] = {}
    for row in rows:
        tags[tag_for(row.get("name", ""))] = tags.get(tag_for(row.get("name", "")), 0) + 1
        for key in classes:
            counts[for_cell(row, key)["source"]] += 1
    return {"counts": counts, "tags": tags}
