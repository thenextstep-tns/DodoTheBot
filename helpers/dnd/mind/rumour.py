"""
Rumour propagation — how a thing somebody saw becomes a thing everybody knows.

`03-KNOWLEDGE-BASE.md` §4. No model is involved: people who know each other well
enough talk, they pass on what struck them, and it arrives weaker and slightly
wrong. Run that on the world tick and a claim about a PC reaches someone who has
never met them, which is the whole of reputation.

Three properties are load-bearing:

* **It degrades.** A listener adopts at `confidence × trust(listener→teller) ×
  drift(mutations)`. Something six people deep is a half-memory of a half-memory,
  and that is why gossip is not a broadcast channel.
* **It drifts.** With some chance the claim itself changes — a name swapped for
  another name the teller knows, a number inflated. This is the interesting part
  and it is why a claim is stored as text with swappable pieces rather than an
  opaque sentence.
* **It is bounded.** Only pairs who actually know each other talk, each belief
  travels to a given person once, and the caller caps how many exchanges happen
  per tick. A world of 200 NPCs must not become 40,000 conversations.

Pure and seeded: no I/O, no configuration reads, no clock.
"""

from __future__ import annotations

from random import Random

from helpers.dnd.tuning import DEFAULT_RUMOURS, RumourTuning

# Words worth swapping when a claim drifts. Deliberately the kind of thing that
# changes in the retelling — magnitudes and certainties — rather than the verb,
# because a rumour that reverses its own meaning is a different rumour.
# **No replacement may itself be a key.** A vocabulary that can drift its own
# output compounds across hops into soup — six retellings turned "Kesh owes the
# Compact a debt" into "Kesh is in deep with some fortune to the Compact another
# debt". One substitution per hop, and it must terminate.
_DRIFT_WORDS: dict[str, tuple[str, ...]] = {
    "a": ("another", "more than one"),
    "some": ("countless", "any number of"),
    "several": ("countless", "any number of"),
    "many": ("countless", "hundreds of"),
    "once": ("repeatedly", "time and again"),
    "twice": ("repeatedly", "constantly"),
    "might": ("will", "does"),
    "maybe": ("certainly", "undoubtedly"),
    "said": ("swore", "let slip"),
    "saw": ("watched", "caught"),
    "owes": ("cheated", "swindled"),
    "debt": ("fortune", "ransom"),
    "took": ("stole", "seized"),
}
assert not (set(_DRIFT_WORDS) & {
    w.lower() for options in _DRIFT_WORDS.values() for o in options for w in o.split()
}), "a drift replacement must not itself be driftable"


def will_share(belief, teller_traits, rng: Random) -> bool:
    """Whether this is a thing the teller would actually bring up.

    Weighted by how sure they are and how much they like talking. A solitary,
    incurious person sits on what they know; a sociable one cannot help it.
    """
    appetite = 0.35 + 0.45 * float(getattr(teller_traits, "belonging", 0.5))
    appetite += 0.2 * float(getattr(teller_traits, "curiosity", 0.5))
    return rng.random() < max(0.0, min(1.0, belief.confidence * appetite))


def pick(beliefs: list, listener_id, rng: Random, *, max_hops: int = 6):
    """The belief a teller reaches for, or ``None`` if they have nothing to say.

    Weighted by confidence, because people repeat what they are sure of. Skips
    anything already told to this listener and anything that has changed hands
    too many times to be worth passing on.
    """
    candidates = [
        b for b in beliefs
        if b.mutations < max_hops
        and listener_id not in b.shared_with
        and str(b.holder_id) != str(listener_id)
        and b.subject_id is not None
    ]
    if not candidates:
        return None
    weights = [max(0.01, b.confidence) for b in candidates]
    return rng.choices(candidates, weights=weights)[0]


def drift(claim: str, rng: Random, vocabulary: dict | None = None) -> str:
    """Change one word of a claim into something a retelling would produce.

    Only ever one word, and never the verb. A rumour that mutates wholesale is
    noise; a rumour where *a* debt became *a fortune* is a story.
    """
    table = vocabulary or _DRIFT_WORDS
    words = claim.split()
    positions = [i for i, w in enumerate(words) if w.lower().strip(".,") in table]
    if not positions:
        return claim
    at = rng.choice(positions)
    key = words[at].lower().strip(".,")
    words[at] = rng.choice(table[key])
    return " ".join(words)


def travel(belief, trust: float, rng: Random,
           tuning: RumourTuning = DEFAULT_RUMOURS) -> tuple[str, int, float]:
    """What the claim looks like once it has arrived.

    Returns ``(claim, mutations, trust)`` for the listener's own belief. The
    confidence arithmetic itself lives in ``world/belief.adopt`` so that a
    rumour and a thing a GM simply told someone degrade by the same rule.
    """
    claim, mutations = belief.claim, belief.mutations
    if rng.random() < tuning.mutate_chance:
        drifted = drift(claim, rng)
        if drifted != claim:
            claim, mutations = drifted, mutations + 1
    return claim, mutations, max(0.0, min(1.0, trust))


def talkative_pairs(relationships: list, rng: Random,
                    tuning: RumourTuning = DEFAULT_RUMOURS) -> list:
    """Who ends up talking to whom this tick.

    Only directed pairs who are familiar enough to be having a conversation at
    all, sampled rather than exhausted so the cost is a constant per tick and
    not a function of how big the town has become.
    """
    eligible = [r for r in relationships if r.familiarity >= tuning.familiarity_floor]
    if not eligible:
        return []
    rng.shuffle(eligible)
    return eligible[: max(0, tuning.exchanges)]
