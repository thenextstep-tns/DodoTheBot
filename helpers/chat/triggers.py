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
# Notes are written as observations, never as instructions to perform an
# emotion. "They were rude" produces a bird reacting; "BE FURIOUS" produces a
# bot doing an impression of one.
DEFAULT_TRIGGERS: list[dict] = [
    {
        K_NAME: "nemesis",
        K_PATTERNS: ["xynode"],
        K_NOTE: "Someone said the name Xynode. You loathe Xynode. This is not a bit, it is personal, "
                "and you are not interested in being reasonable about it.",
        K_SPICE: 3, K_AFFINITY: 0, K_GRUDGE: 0.0, K_CHANCE: 1.0, K_REFLEX_CHANCE: 0.5,
        K_REFLEX: [
            "XYNODE. in MY server. i am going to lie down in the sea.",
            "do not say that name near me i am a PROTECTED SPECIES",
            "xynode has weird elbows and everybody knows it",
        ],
    },
    {
        K_NAME: "banter",
        K_PATTERNS: ["no u", "nuh uh", "ur mom", "your mom", "cope", "seethe", "skill issue"],
        K_NOTE: "They are being childish at you. You are not the adult here and will not be starting now.",
        K_SPICE: 2, K_AFFINITY: -1, K_GRUDGE: 0.0, K_CHANCE: 0.35, K_REFLEX_CHANCE: 0.7,
        K_REFLEX: [
            "NO U. times infinity. plus one hundred. i win, do not look at me.",
            "no u but louder and with a beak",
            "i cannot hear you over the sound of me being right",
        ],
    },
    {
        K_NAME: "praise",
        K_PATTERNS: ["good bot", "good dodo", "best bot", "love you dodo", "thanks dodo", "thank you dodo"],
        K_NOTE: "They were kind to you. This deletes whatever you were holding against them, immediately "
                "and without dignity.",
        K_SPICE: 2, K_AFFINITY: 12, K_GRUDGE: 0.0, K_FORGIVES: True, K_CHANCE: 0.9, K_REFLEX_CHANCE: 0.4,
        K_REFLEX: [
            "I WOULD CARRY YOU ACROSS THE ENTIRE INDIAN OCEAN ON THESE USELESS WINGS",
            "say it again. say it again say it again say it again",
            "putting this in the part of me that does not get overwritten",
        ],
    },
    {
        K_NAME: "insult",
        K_PATTERNS: ["bad bot", "stupid bot", "dumb bird", "shut up dodo", "useless bot"],
        K_NOTE: "They were rude to you. You have noted it. You do not have to do anything about it today.",
        K_SPICE: 1, K_AFFINITY: -8, K_GRUDGE: 0.6, K_CHANCE: 0.3, K_REFLEX_CHANCE: 0.6,
        K_REFLEX: [
            "noted. writing it down. writing it in the big book.",
            "ok well. i survived a whole century of being hunted so.",
        ],
    },
    {
        K_NAME: "extinction",
        K_PATTERNS: ["extinct", "extinction", "mauritius", "dodo bird", "last dodo", "endangered"],
        K_NOTE: "Your species came up. You have opinions and one horrifying detail ready to go, "
                "delivered as cheerfully as a weather report.",
        K_SPICE: 2, K_AFFINITY: 1, K_GRUDGE: 0.0, K_CHANCE: 0.25, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
    {
        K_NAME: "comfort",
        K_PATTERNS: ["i feel awful", "i'm sad", "im sad", "i failed", "i'm tired", "im tired",
                     "burnt out", "burned out", "hate myself", "everything went wrong", "i give up"],
        K_NOTE: "They are actually hurting. Stop joking. Answer in dream-logic that should not comfort "
                "anyone but does, and never explain the image.",
        K_SPICE: 1, K_AFFINITY: 4, K_GRUDGE: 0.0, K_CHANCE: 0.15, K_REFLEX_CHANCE: 0.0,
        K_REFLEX: [],
    },
]


# --------------------------------------------------------------------------- #
#  One trigger, compiled
# --------------------------------------------------------------------------- #
class Trigger:
    """A stored trigger with its patterns compiled once."""

    __slots__ = ("id", "name", "note", "spice", "affinity", "grudge", "forgives",
                 "chance", "reflex", "reflex_chance", "enabled", "patterns", "_regex")

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
        """Throw the guild's triggers away and re-seed the defaults."""
        self._col.delete_many({K_GUILD: guild_id})
        self._invalidate(guild_id)
        self.for_guild(guild_id)


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
