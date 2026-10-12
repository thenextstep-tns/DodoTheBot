"""
Value alignment — why *this* person keeps *this* memory.

Uniform decay is the thing that makes simulated memory feel fake. Real people do
not forget evenly; they forget **selectively, along the grain of what they care
about**. A grasping harbourmaster will still know, ten years on, exactly who owes
him four marks, and will have entirely lost the afternoon someone was kind to
him. A sworn zealot has it the other way round.

So a memory's staying power is not just how loud it was at the time (salience) —
it is how much it *engages the drives this character actually has*. That is what
this module computes: a −1…1 alignment between a memory's content and an entity's
value system, which then stretches or shortens how long the memory holds
together (``decay.py``).

Deliberately keyword-driven and readable. A GM should be able to look at an NPC
who has forgotten a favour and see, in one line, that it is because nothing in
their value system was holding on to it. An opaque score would be worse than no
score.
"""

from __future__ import annotations

from helpers.dnd.mind.traits import DRIVES, Traits
from helpers.dnd.world.memory import Memory

# What each drive latches onto. Matched against a memory's gist, details and
# cues. Kept small and concrete — these are the things a person with that drive
# would actually replay in their head at three in the morning.
DRIVE_CONCERNS: dict[str, set[str]] = {
    # Kept deliberately concrete. Generic verbs like "took", "found" or "worth"
    # were removed after they matched things they had no business matching —
    # "she took me in and asked nothing" is not a memory about money.
    "greed": {
        "coin", "coins", "gold", "silver", "paid", "pay", "price", "owed", "owes",
        "debt", "debts", "cost", "sold", "bought", "purse", "cargo", "profit",
        "cheated", "wages", "rent", "fee", "bribe",
    },
    "honour": {
        "oath", "sworn", "swore", "promise", "promised", "vow", "betrayed",
        "betray", "duty", "shame", "shamed", "disgrace", "honour", "honor",
        "loyal", "traitor", "insult", "insulted", "dishonoured",
    },
    "curiosity": {
        "strange", "odd", "secret", "hidden", "book", "books", "letter", "map",
        "question", "unknown", "sigil", "locked", "discovered", "riddle",
        "puzzle", "rumour", "whispered", "curious",
    },
    "fear_of_death": {
        "blood", "died", "die", "death", "killed", "kill", "wound", "wounded",
        "knife", "blade", "sword", "drowned", "fire", "burned", "burn", "fell",
        "nearly", "escaped", "hurt", "pain", "sick", "plague",
    },
    "belonging": {
        "family", "brother", "sister", "mother", "father", "son", "daughter",
        "friend", "friends", "alone", "abandoned", "home", "together",
        "welcomed", "belonged", "crew", "kin", "lonely", "company",
    },
}

# Someone warm holds onto kindnesses; someone cold holds onto slights. Small
# next to the drive terms, because temperament colours memory rather than
# governing it. How far the resulting alignment stretches a memory's life is a
# tunable (``memory_alignment_reach``), applied in decay.py.
WARMTH_WEIGHT = 0.25


def _memory_words(memory: Memory) -> set[str]:
    words: set[str] = set(memory.cues)
    for chunk in [memory.gist, *memory.details]:
        for raw in str(chunk).lower().split():
            cleaned = "".join(c for c in raw if c.isalnum())
            if len(cleaned) > 2:
                words.add(cleaned)
    return words


def drive_engagement(memory: Memory, traits: Traits) -> dict[str, float]:
    """Per-drive: how strongly this memory speaks to it, weighted by how much
    the entity has of that drive.

    The drive strength is centred on 0.5 and doubled, so a drive at the neutral
    midpoint contributes nothing at all — an NPC with average greed neither
    clings to nor sheds a memory about money.
    """
    words = _memory_words(memory)
    if not words:
        return {}

    engagement: dict[str, float] = {}
    for drive in DRIVES:
        concerns = DRIVE_CONCERNS.get(drive, set())
        hits = len(words & concerns)
        if not hits:
            continue
        # Saturating in hit count: one strong cue is most of the signal, and a
        # long memory should not out-score a sharp one just by being wordy.
        touch = 1.0 - (0.6 ** hits)
        strength = (traits.axis(drive) - 0.5) * 2
        engagement[drive] = round(touch * strength, 4)
    return engagement


def alignment(memory: Memory, traits: Traits) -> float:
    """How well a memory sits with this character's values, −1…1.

    Positive means their value system is actively holding on to it. Negative
    means it runs against what they care about and will slip away faster than an
    equally loud memory that fits.
    """
    engagement = drive_engagement(memory, traits)
    total = sum(engagement.values())

    # Temperament tilt: warm people keep the good, cold people keep the bad.
    if memory.valence:
        total += WARMTH_WEIGHT * traits.axis("warmth") * memory.valence

    if not engagement and not memory.valence:
        return 0.0
    # Averaged over the drives that actually fired, so engaging one drive
    # strongly is not diluted by the four that had nothing to say.
    divisor = max(1, len(engagement))
    return round(max(-1.0, min(1.0, total / divisor)), 4)


def explain(memory: Memory, traits: Traits) -> str:
    """One line a GM can read: why this memory is sticking, or why it isn't.

    The inspector shows this next to every memory. "It faded because he never
    cared about it" is a satisfying answer; a bare number is not.
    """
    engagement = drive_engagement(memory, traits)
    if not engagement:
        score = alignment(memory, traits)
        if abs(score) < 0.05:
            return "nothing in their values holds this"
        return "held by temperament alone" if score > 0 else "runs against their temper"

    ordered = sorted(engagement.items(), key=lambda pair: -abs(pair[1]))
    bits = []
    for drive, value in ordered[:2]:
        verb = "holds onto" if value > 0 else "lets go of"
        bits.append(f"{verb} this ({drive.replace('_', ' ')})")
    return "; ".join(bits)
