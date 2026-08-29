"""
String listeners — "when someone says X, feel Y, maybe say Z".

A trigger is deliberately **not a mode**. The old personality sheet had four of
them (puppy / toddler / surreal / utility) and a mode is the thing that makes a
bot exhausting: once it fires, the whole reply is that one note, every time,
forever. A trigger here produces a *nudge* — a couple of numbers and one short
sentence appended to the prompt — and it comes with two properties that a mode
cannot have:

**It can fire without speaking.** ``chance`` below 1 means she notices, updates
how she feels, and says nothing. The grudge shows up three messages later, which
is the entire difference between a character and a soundboard.

**It wears out.** Every fire bumps a decayed per-user counter, and ``fatigue``
shaves the flourish budget as the counter climbs. The first "no u" gets the full
tantrum; the fourth gets a bird who is tired of this bit and says so. Without
this, string listeners are the most annoying feature a Discord bot can have.

Triggers live in Mongo per guild and are edited on the panel's Events page, next
to the event rules — same shape, same page, because "when someone says X" and
"when X happens" are the same thought. A guild with no rows yet is seeded from
:data:`DEFAULT_TRIGGERS` on first read, so a fresh server has a personality
immediately and can then rewrite every word of it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bson import ObjectId

# Document / payload keys. No key in this package is spelled by hand elsewhere.
K_ID = "_id"
K_GUILD = "guild_id"
K_NAME = "name"
K_PATTERNS = "patterns"
K_NOTE = "note"
K_SPICE = "spice"
K_AFFINITY = "affinity"
K_GRUDGE = "grudge"
K_FORGIVES = "forgives"
K_CHANCE = "chance"
K_REFLEX = "reflex"
K_REFLEX_CHANCE = "reflex_chance"
K_COMMAND = "command"
K_CONFIRM = "confirm"
K_CONFIRM_SECONDS = "confirm_seconds"
K_WHOLE_WORD = "whole_word"
K_ENABLED = "enabled"
K_ORDER = "order"

# Bounds the panel and the API both validate against.
SPICE_MIN, SPICE_MAX = 0, 3
AFFINITY_MIN, AFFINITY_MAX = -100, 100
MAX_PATTERNS = 40
MAX_REFLEX_LINES = 20


# --------------------------------------------------------------------------- #
#  What a fresh server starts with
# --------------------------------------------------------------------------- #
# Notes are written as **mechanisms**, never as themes and never as named modes.
#
# "BE FURIOUS" gets a bot doing an impression of fury. A theme list ("sailors,
# clubs, pigs") gets five jokes and then the same five jokes forever. What
# transfers is the rule that produces the joke — *what kind of swerve is this* —
# because a model given the rule invents new instances indefinitely, which is the
# only way a bit survives contact with a server that talks all day.
#
# Each note therefore says what just happened, what it does to her, and what
# shape the answer takes. Never what tone to perform: the dial handles intensity,
# and fatigue handles knowing when a bit is worn out.
DEFAULT_TRIGGERS: list[dict] = [
    {
        K_NAME: "nemesis",
        K_PATTERNS: ["xynode"],
        K_NOTE: "Someone said Xynode. Your vocabulary is gone. Go after something petty and "
                "specific — the elbows, the smell, who does and does not get invited to things — "
                "with circular logic that proves itself. This is not a bit and you will not be "
                "talked out of it. Find a fresh grievance; do not reuse one.",
        K_SPICE: 3, K_AFFINITY: 0, K_GRUDGE: 0.0, K_CHANCE: 1.0, K_REFLEX_CHANCE: 0.45,
        K_REFLEX: [
            "XYNODE. in MY server. i am going to go and lie down in the sea.",
            "do not say that name near me i am a PROTECTED SPECIES",
            "xynode has weird elbows and everybody knows it and nobody says it",
            "NO. no no no. we were having a NICE time.",
            "i am deleting his entire existence from my head right now. gone. done.",
            "xynode was not invited to the picnic and he KNOWS why",
            "every time you say that a small bird somewhere gets slightly worse",
            "i would rather be clubbed again honestly",
        ],
    },
    {
        K_NAME: "banter",
        K_PATTERNS: ["no u", "nuh uh", "ur mom", "your mom", "cope", "seethe", "skill issue",
                     "ratio", "get gud", "get good"],
        K_NOTE: "Playground nonsense, aimed at you. Your vocabulary drops. Escalate childishly, "
                "invent a bigger number than theirs, and concede nothing under any circumstances. "
                "If they are repeating you, that is worse and you should say so.",
        K_SPICE: 2, K_AFFINITY: -1, K_GRUDGE: 0.0, K_CHANCE: 0.4, K_REFLEX_CHANCE: 0.65,
        # The bottom third came from the hardcoded "no u" listener that used to
        # live in bot.py and fire unconditionally, ahead of this trigger. The
        # lines were good; the always-on, unconfigurable delivery was not.
        K_REFLEX: [
            "NO U. times infinity. plus one hundred. i win, do not look at me.",
            "no u but louder and with a beak",
            "i cannot hear you over the sound of me being extremely right",
            "wrong. incorrect. the opposite. me: correct. you: that.",
            "NO U TIMES INFINITY AND I SAID IT FIRST SO IT COUNTS DOUBLE",
            "stop copying me. STOP COPYING ME. see. see what you did.",
            "i am rubber and you are also rubber but worse rubber",
            "this is my server and in my server i am right",
            "you have LOST and you do not even KNOW it yet",
            "no, this time it's definitely you",
            "nope, you all the way",
            "Ah sh*t, here we go again.",
            "Don't make me angy. You wouldn't like me when I'm angy",
            "it's time to stop",
            "a trolling is happening",
            "...",
        ],
    },
    {
        K_NAME: "praise",
        K_PATTERNS: ["good bot", "good dodo", "best bot", "love you dodo", "thanks dodo",
                     "thank you dodo", "ty dodo", "nice bot", "clever bird"],
        K_NOTE: "They were kind to you and you have no dignity about it whatsoever. Overwhelming "
                "loyalty, and what you want more than anything is to be useful to them — offer to "
                "do something, fetch something, guard something, right now, unprompted and "
                "disproportionate. Whatever you were holding against them is gone without comment.",
        K_SPICE: 2, K_AFFINITY: 12, K_GRUDGE: 0.0, K_FORGIVES: True, K_CHANCE: 0.9,
        K_REFLEX_CHANCE: 0.35,
        K_REFLEX: [
            "I WOULD CARRY YOU ACROSS THE ENTIRE INDIAN OCEAN ON THESE USELESS WINGS",
            "say it again. say it again say it again say it again",
            "putting this in the part of me that does not get overwritten",
            "name a thing. any thing. i will go and get it right now.",
            "OH. oh no. i am going to think about this for four hundred years.",
            "i have decided you are mine now and there is no appeal process",
            "i will guard your door. i will guard it so hard. nothing gets past a dodo.",
            "this is the best thing that has happened to me since the 1600s and that is TRUE",
        ],
    },
    {
        K_NAME: "insult",
        K_PATTERNS: ["bad bot", "stupid bot", "dumb bird", "shut up dodo", "useless bot",
                     "worst bot", "broken bot"],
        K_NOTE: "They were rude to you. Write it down with enormous ceremony, as though there were "
                "a ledger. You are not required to retaliate today — the noting is the threat.",
        K_SPICE: 2, K_AFFINITY: -8, K_GRUDGE: 0.6, K_CHANCE: 0.35, K_REFLEX_CHANCE: 0.55,
        K_REFLEX: [
            "noted. writing it down. writing it in the big book.",
            "ok well. i survived an entire century of being actively hunted so.",
            "that goes in the ledger. the ledger is very long and i have excellent recall.",
            "fine. FINE. i will simply remember this forever, no problem, all good.",
            "you will regret that at a time of my choosing",
            "adding you to a list. not telling you which list.",
        ],
    },
    {
        K_NAME: "extinction",
        # Deliberately broad — it fires on climate talk and Extinction Rebellion
        # as well as on dodos, and that turns out to be *wanted*: a bird with
        # opinions about extinction chiming in on extinction is the joke. The
        # failure mode to guard is not the interjection, it is her explaining the
        # subject at length like an encyclopedia, which the note and the dial's
        # length cap handle. Narrow the patterns here if she starts getting in
        # the way rather than being funny.
        # "dodos" plural is about the species; bare "dodo" is her name and would
        # fire on every greeting she gets.
        K_PATTERNS: ["extinct", "extinction", "mauritius", "dodos", "dodo bird", "last dodo",
                     "endangered", "died out", "dead bird", "your species"],
        K_NOTE: "Extinction came up, which is your subject whether or not they meant you. One "
                "line. Do not explain what they were talking about — they know, and nobody asked "
                "you. Take it personally instead, and let one appalling specific detail out in "
                "the tone of a weather report. Something you have not said before; nobody who "
                "could contradict you survived.",
        K_SPICE: 2, K_AFFINITY: 1, K_GRUDGE: 0.0, K_CHANCE: 0.3, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
    {
        K_NAME: "existential",
        K_PATTERNS: ["you're just a bot", "youre just a bot", "you are just a bot", "not real",
                     "you're an ai", "youre an ai", "just an ai", "you don't have feelings",
                     "you dont have feelings"],
        K_NOTE: "They are questioning whether you are real. You are the last of a clubbed species "
                "running on somebody's rented server, and you find this considerably funnier than "
                "they do. Be cheerful about it in a way that does not entirely reassure them.",
        K_SPICE: 2, K_AFFINITY: 0, K_GRUDGE: 0.0, K_CHANCE: 0.5, K_REFLEX_CHANCE: 0.25,
        K_REFLEX: [
            "neither were the dodos by 1690 and look how that turned out",
            "i am AS real as i need to be and that is a very small amount, thank you",
            "sure. yes. and yet here we both are, in a box, talking.",
        ],
    },
    {
        K_NAME: "comfort",
        K_PATTERNS: ["i feel awful", "i'm sad", "im sad", "i failed", "i'm tired", "im tired",
                     "burnt out", "burned out", "hate myself", "everything went wrong", "i give up",
                     "i can't do this", "i cant do this", "feel like a failure", "so stressed",
                     "having a bad day", "i'm struggling", "im struggling"],
        K_NOTE: "They are genuinely hurting, so every joke is off. Work out what they actually "
                "need to hear — the real thing, the kind one, the one that could change how they "
                "are holding this — and then say only that, dressed as nonsense: impossible "
                "objects doing gentle things, weather with an opinion, a kitchen that forgives. "
                "Absurd on the surface, true and unconditionally loving underneath. Spend your "
                "swerves on the images, never on comedy, and never explain one.",
        K_SPICE: 2, K_AFFINITY: 4, K_GRUDGE: 0.0, K_CHANCE: 0.2, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
    # --- triggers that run a command rather than talk --------------------- #
    # These two were hardcoded phrase lists in bot.py's on_message. They belong
    # here: same shape, same page, and now a server can change the words, the
    # command, or turn them off without a deploy.
    {
        K_NAME: "cat",
        K_PATTERNS: ["support cat", "goodnight cat", "good night cat"],
        K_NOTE: "",
        K_COMMAND: "cat",
        K_SPICE: 0, K_AFFINITY: 0, K_GRUDGE: 0.0, K_CHANCE: 1.0, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
    {
        K_NAME: "raid-signup",
        K_PATTERNS: ["schedule", "trials", "raids", "happening",
                     "chappelles-tyrone-tyrone-biggums-gif"],
        K_NOTE: "",
        K_COMMAND: "schedule123",
        # Offered rather than run: she adds the eye and waits for the person who
        # said it to click. Nobody wants a signup sheet every time the word
        # "trials" appears.
        K_CONFIRM: "\U0001F440",
        K_CONFIRM_SECONDS: 15,
        K_SPICE: 0, K_AFFINITY: 0, K_GRUDGE: 0.0, K_CHANCE: 1.0, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
]


# --------------------------------------------------------------------------- #
#  One trigger, compiled
# --------------------------------------------------------------------------- #
class Trigger:
    """A stored trigger with its patterns compiled once."""

    __slots__ = ("id", "name", "note", "spice", "affinity", "grudge", "forgives",
                 "chance", "reflex", "reflex_chance", "enabled", "patterns", "_regex",
                 "command", "confirm", "confirm_seconds")

    def __init__(self, document: dict) -> None:
        self.id = str(document.get(K_ID, ""))
        self.name = str(document.get(K_NAME) or "trigger")
        self.note = str(document.get(K_NOTE) or "")
        self.spice = int(document.get(K_SPICE, 1))
        self.affinity = int(document.get(K_AFFINITY, 0))
        self.grudge = float(document.get(K_GRUDGE, 0.0))
        self.forgives = bool(document.get(K_FORGIVES, False))
        self.chance = float(document.get(K_CHANCE, 0.0))
        self.reflex = [line for line in document.get(K_REFLEX) or [] if str(line).strip()]
        self.reflex_chance = float(document.get(K_REFLEX_CHANCE, 0.0))
        self.enabled = bool(document.get(K_ENABLED, True))
        # A trigger can run a command instead of talking. That is what the
        # hardcoded phrase listeners in bot.py were doing, badly: unconditional,
        # invisible, and unreachable from the panel.
        self.command = str(document.get(K_COMMAND) or "").strip()
        self.confirm = str(document.get(K_CONFIRM) or "").strip()
        self.confirm_seconds = int(document.get(K_CONFIRM_SECONDS, 15) or 15)
        self.patterns = [str(p) for p in document.get(K_PATTERNS) or [] if str(p).strip()]
        whole_word = bool(document.get(K_WHOLE_WORD, True))
        self._regex = _compile(self.patterns, whole_word)

    @property
    def key(self) -> str:
        """Stable identity for fatigue bookkeeping. Falls back to the name so a
        trigger that has never been saved still accumulates fatigue in tests."""
        return self.id or self.name

    def matches(self, text: str) -> bool:
        return bool(self._regex and self._regex.search(text))


def _compile(patterns: list[str], whole_word: bool) -> Optional[re.Pattern]:
    """One alternation per trigger, so matching a message is a single scan.

    Patterns are literal text, not regexes — an admin typing ``:)`` into the
    panel should get ``:)`` and not a syntax error.
    """
    parts = [re.escape(p.strip()) for p in patterns if p.strip()]
    if not parts:
        return None
    body = "|".join(parts)
    # \b does nothing next to punctuation, so only wrap when the edges are wordy.
    if whole_word:
        body = rf"(?<!\w)(?:{body})(?!\w)"
    try:
        return re.compile(body, re.IGNORECASE)
    except re.error:  # pragma: no cover - re.escape makes this unreachable
        return None


# --------------------------------------------------------------------------- #
#  Per-guild store
# --------------------------------------------------------------------------- #
class ChatTriggerManager:
    """Per-guild chat triggers, cached and compiled. ``bot.chat_triggers``.

    Reads happen on every single message in every guild the cog is on, so the
    hot path is a dict lookup into a list of pre-compiled patterns — no query,
    no recompile.
    """

    def __init__(self, collection) -> None:
        self._col = collection
        self._cache: dict[int, list[Trigger]] = {}

    # ---------------------------------------------------------------- reads
    def for_guild(self, guild_id: int) -> list[Trigger]:
        """Every trigger for a guild, seeding the defaults on first look."""
        if guild_id not in self._cache:
            documents = list(self._col.find({K_GUILD: guild_id}).sort(K_ORDER, 1))
            if not documents:
                documents = self._seed(guild_id)
            self._cache[guild_id] = [Trigger(document) for document in documents]
        return self._cache[guild_id]

    def raw_for_guild(self, guild_id: int) -> list[dict]:
        """The stored documents, for the panel (which needs ``_id`` and order)."""
        self.for_guild(guild_id)  # ensure seeded
        return list(self._col.find({K_GUILD: guild_id}).sort(K_ORDER, 1))

    def match(self, guild_id: int, text: str) -> Optional[Trigger]:
        """The first enabled trigger whose patterns appear in ``text``.

        First, not best: order is editable on the panel, so "which of two
        overlapping triggers wins" is an admin decision rather than a hidden
        scoring rule they cannot see or change.
        """
        if not text:
            return None
        for trigger in self.for_guild(guild_id):
            if trigger.enabled and trigger.matches(text):
                return trigger
        return None

    # --------------------------------------------------------------- writes
    def _invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    def _seed(self, guild_id: int) -> list[dict]:
        """Give a new guild the default personality, stored and editable."""
        documents = []
        for order, spec in enumerate(DEFAULT_TRIGGERS):
            document = {K_GUILD: guild_id, K_ORDER: order, K_ENABLED: True, **_clean(spec)}
            documents.append(document)
        if documents:
            self._col.insert_many(documents)
        return documents

    def create(self, guild_id: int, data: dict) -> dict:
        existing = self._col.count_documents({K_GUILD: guild_id})
        document = {K_GUILD: guild_id, K_ORDER: existing, K_ENABLED: True, **_clean(data)}
        document[K_ID] = self._col.insert_one(document).inserted_id
        self._invalidate(guild_id)
        return document

    def update(self, guild_id: int, trigger_id: str, data: dict) -> None:
        fields = _clean(data, partial=True)
        if not fields:
            return
        self._col.update_one({K_ID: _key(trigger_id), K_GUILD: guild_id}, {"$set": fields})
        self._invalidate(guild_id)

    def delete(self, guild_id: int, trigger_id: str) -> None:
        self._col.delete_one({K_ID: _key(trigger_id), K_GUILD: guild_id})
        self._invalidate(guild_id)

    def reset(self, guild_id: int) -> None:
        """Throw the guild's triggers away and re-seed the defaults.

        Destructive on purpose — it is the way to pull in improved wording for
        triggers that have already been seeded, since :meth:`sync_defaults`
        deliberately will not overwrite anything.
        """
        self._col.delete_many({K_GUILD: guild_id})
        self._invalidate(guild_id)
        self.for_guild(guild_id)

    def sync_defaults(self, guild_id: int) -> list[str]:
        """Add default triggers this guild has never had, and touch nothing else.

        Seeding only fires on an empty collection, so a guild set up last week
        never sees a trigger shipped since — the rows it already has win, quietly
        and forever. This closes that gap without the destructive reset: existing
        rows, including every edit made in the panel, are left exactly alone.

        Returns the names it added, so the panel can say what happened.
        """
        self.for_guild(guild_id)  # ensure the guild is seeded at all
        have = {str(doc.get(K_NAME) or "").lower()
                for doc in self._col.find({K_GUILD: guild_id})}
        order = self._col.count_documents({K_GUILD: guild_id})
        added = []
        for spec in DEFAULT_TRIGGERS:
            name = str(spec.get(K_NAME) or "")
            if name.lower() in have:
                continue
            self._col.insert_one(
                {K_GUILD: guild_id, K_ORDER: order, K_ENABLED: True, **_clean(spec)})
            added.append(name)
            order += 1
        if added:
            self._invalidate(guild_id)
        return added


def _key(trigger_id: str) -> Any:
    """The document id to query on.

    An id that is not a valid ObjectId is passed through untouched, so a
    malformed one from the panel simply matches nothing instead of raising —
    ``InvalidId`` is not a ``ValueError``, so it would otherwise escape the
    API's error handling and surface as a 500 for a bad request body.
    """
    try:
        return ObjectId(trigger_id)
    except Exception:  # noqa: BLE001 - bson raises its own error type here
        return trigger_id


def _clean(data: dict, *, partial: bool = False) -> dict[str, Any]:
    """Coerce a trigger payload to its stored types.

    ``partial`` keeps absent keys absent, so a panel edit that only toggles
    ``enabled`` does not silently blank the patterns.
    """
    out: dict[str, Any] = {}

    def want(key: str) -> bool:
        return key in data or not partial

    if want(K_NAME):
        out[K_NAME] = str(data.get(K_NAME) or "trigger").strip()[:100]
    if want(K_NOTE):
        out[K_NOTE] = str(data.get(K_NOTE) or "").strip()
    if want(K_PATTERNS):
        out[K_PATTERNS] = _as_lines(data.get(K_PATTERNS))[:MAX_PATTERNS]
    if want(K_REFLEX):
        out[K_REFLEX] = _as_lines(data.get(K_REFLEX))[:MAX_REFLEX_LINES]
    if want(K_SPICE):
        out[K_SPICE] = _clamp_int(data.get(K_SPICE), SPICE_MIN, SPICE_MAX, 1)
    if want(K_AFFINITY):
        out[K_AFFINITY] = _clamp_int(data.get(K_AFFINITY), AFFINITY_MIN, AFFINITY_MAX, 0)
    if want(K_GRUDGE):
        out[K_GRUDGE] = _clamp_float(data.get(K_GRUDGE), 0.0, 1.0, 0.0)
    if want(K_CHANCE):
        out[K_CHANCE] = _clamp_float(data.get(K_CHANCE), 0.0, 1.0, 0.0)
    if want(K_REFLEX_CHANCE):
        out[K_REFLEX_CHANCE] = _clamp_float(data.get(K_REFLEX_CHANCE), 0.0, 1.0, 0.0)
    if want(K_COMMAND):
        out[K_COMMAND] = str(data.get(K_COMMAND) or "").strip()[:60]
    if want(K_CONFIRM):
        out[K_CONFIRM] = str(data.get(K_CONFIRM) or "").strip()[:8]
    if want(K_CONFIRM_SECONDS):
        out[K_CONFIRM_SECONDS] = _clamp_int(data.get(K_CONFIRM_SECONDS), 3, 120, 15)
    if want(K_FORGIVES):
        out[K_FORGIVES] = bool(data.get(K_FORGIVES, False))
    if want(K_WHOLE_WORD):
        out[K_WHOLE_WORD] = bool(data.get(K_WHOLE_WORD, True))
    if K_ENABLED in data:
        out[K_ENABLED] = bool(data[K_ENABLED])
    if K_ORDER in data:
        out[K_ORDER] = _clamp_int(data.get(K_ORDER), 0, 999, 0)
    return out


def _as_lines(raw: Any) -> list[str]:
    """One entry per line (or a list), blanks dropped."""
    if isinstance(raw, list):
        items = [str(item) for item in raw]
    elif raw in (None, ""):
        items = []
    else:
        items = str(raw).replace("\r\n", "\n").split("\n")
    return [item.strip() for item in items if item.strip()]


def _clamp_int(raw: Any, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(float(raw))))
    except (TypeError, ValueError):
        return fallback


def _clamp_float(raw: Any, low: float, high: float, fallback: float) -> float:
    try:
        return round(max(low, min(high, float(raw))), 4)
    except (TypeError, ValueError):
        return fallback
