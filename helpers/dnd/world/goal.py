"""
Goals — what somebody is trying to make happen.

Needs say what a body is short of; goals say what a *person* is after, and the
difference is the whole gap between an NPC who eats when hungry and one who is
saving to buy back their sister's indenture. A need is satisfied and gone. A goal
outlives the scene it was formed in, and that persistence is what makes an NPC
look like they have a life rather than a mood.

Two decisions worth knowing:

**A goal names the verbs that serve it.** ``acquire`` is advanced by taking and
using; ``avoid`` by fleeing and hiding. That mapping is what lets the decision
engine score a candidate action against a goal without a planner — it is the
cheap half of GOAP, and it is why `06-DECISION-ENGINE.md` §1 could rule search
out. It also means a goal can only ever ask for something a ruleset actually
affords (``rules/ruleset.py``), so a goal cannot quietly become unreachable.

**Goals live on the entity, not in their own collection.** They are never read
without the person whose goals they are, which is the opposite of memory and
beliefs — the rule this layer follows is that unbounded or independently queried
components get a collection, and these are neither.

Anybody may want any number of things. What limits them is **attention**, which
is divided across everything they are carrying by how much they care about each
(``mind/goals.py``) — so a long list is not refused, it is simply unproductive.
That is why ``priority`` is the load-bearing field on this record: it is not a
sort order, it is the share of a person a goal gets.

Frozen, like everything the decision engine may see: advancing a goal returns a
new one. The pure arithmetic lives in ``mind/goals.py``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

# What someone can be after. Deliberately few: each kind has to earn itself by
# mapping onto verbs a scene can actually offer, and a taxonomy nobody can hold
# in their head produces goals that never fire.
ACQUIRE = "acquire"
AVOID = "avoid"
HARM = "harm"
PROTECT = "protect"
REACH = "reach"
LEARN = "learn"
BEFRIEND = "befriend"

KINDS = (ACQUIRE, AVOID, HARM, PROTECT, REACH, LEARN, BEFRIEND)

KIND_LABELS = {
    ACQUIRE: "Get hold of",
    AVOID: "Stay away from",
    HARM: "See them suffer",
    PROTECT: "Keep them safe",
    REACH: "Get to",
    LEARN: "Find out",
    BEFRIEND: "Get closer to",
}

# Which affordances serve which goal, and how much. The values are the *shape* of
# the goal term in the scorer, not weights to be tuned per entity: taking serves
# acquisition squarely, using something serves it obliquely.
#
# Every verb here is one of ``rules.ruleset.AFFORDANCES``. A goal that asked for
# a verb no ruleset grants would be a goal nobody could ever pursue, and there is
# a test that says so.
# **Derived from `helpers/dnd/data/verbs.json`.** Stored per verb there, because
# a verb should be one record; read per goal here, because scoring a candidate
# against a goal has to be a lookup and a multiply — that is the cheap half of
# GOAP and the reason `06-DECISION-ENGINE.md` §1 could rule search out entirely.
#
# **Filled on first read, not at import**, and that is not a style choice:
# `world/__init__.py` imports this module eagerly, so anything that imports any
# model under `world/` drags this in with it — and the verb registry imports
# `world.verb`. Reaching for the registry at module level here therefore made
# the registry import itself. A dict that populates itself the first time
# somebody looks keeps every existing read working, including
# `behaviour.py`'s `from ... import SERVED_BY as SERVED`.
class _ServedBy(dict):
    """The goal→verb table, loaded the first time it is actually read."""

    _loaded = False

    def _fill(self):
        if self._loaded:
            return
        # Imported here rather than at the top: see the note above.
        from helpers.dnd import verbs as verb_data
        from helpers.dnd.world import verb as verb_model

        self._loaded = True
        super().update(verb_model.as_served_by(verb_data.built_in()))

    def __getitem__(self, key):
        self._fill()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._fill()
        return super().get(key, default)

    def __iter__(self):
        self._fill()
        return super().__iter__()

    def __len__(self):
        self._fill()
        return super().__len__()

    def __contains__(self, key):
        self._fill()
        return super().__contains__(key)

    def items(self):
        self._fill()
        return super().items()

    def keys(self):
        self._fill()
        return super().keys()

    def values(self):
        self._fill()
        return super().values()


SERVED_BY: dict[str, dict[str, float]] = _ServedBy()

# How a goal ended up in someone's head. Kept because "why does she want this"
# is the first question a GM asks of a decision trace.
ORIGIN_GM = "gm"              # authored
ORIGIN_NEED = "need"          # grew out of a need that would not go away
ORIGIN_BELIEF = "belief"      # something they came to believe
ORIGIN_EVENT = "event"        # something that happened to them
ORIGIN_CLOCK = "clock"        # handed down by a faction
ORIGINS = (ORIGIN_GM, ORIGIN_NEED, ORIGIN_BELIEF, ORIGIN_EVENT, ORIGIN_CLOCK)

STATUS_OPEN = "open"
STATUS_DONE = "done"
STATUS_DROPPED = "dropped"
STATUSES = (STATUS_OPEN, STATUS_DONE, STATUS_DROPPED)


@dataclass(frozen=True)
class Goal:
    """One thing one person is trying to bring about."""

    key: str = ""                    # unique within this entity; the panel's handle
    kind: str = ACQUIRE
    text: str = ""                   # the GM's words, or a templated line
    subject_id: Any = None           # who or what it is about, when it is about one

    priority: float = 0.5            # 0..1, how much they care
    progress: float = 0.0            # 0..1, how far along
    deadline: int | None = None      # world time it stops being worth anything

    origin: str = ORIGIN_GM
    created_at: int = 0
    touched_at: int = 0              # last time it moved; decay measures from here
    status: str = STATUS_OPEN

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #
    def to_doc(self) -> dict:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Goal":
        doc = doc or {}
        kind = doc.get("kind", ACQUIRE)
        return cls(
            key=str(doc.get("key", "")),
            kind=kind if kind in KINDS else ACQUIRE,
            text=str(doc.get("text", "")),
            subject_id=doc.get("subject_id"),
            priority=float(doc.get("priority", 0.5)),
            progress=float(doc.get("progress", 0.0)),
            deadline=(int(doc["deadline"]) if doc.get("deadline") is not None else None),
            origin=doc.get("origin", ORIGIN_GM),
            created_at=int(doc.get("created_at", 0)),
            touched_at=int(doc.get("touched_at", doc.get("created_at", 0))),
            status=doc.get("status", STATUS_OPEN),
        )

    # ------------------------------------------------------------------ #
    #  Reading one
    # ------------------------------------------------------------------ #
    @property
    def open(self) -> bool:
        return self.status == STATUS_OPEN

    def served_by(self, verb: str) -> float:
        """How much doing ``verb`` serves this goal, 0..1.

        The engine's goal term is this number times how much they care. A verb
        the goal has no use for scores nothing rather than scoring against it —
        being unhelpful is not the same as being counterproductive, and the
        scorer has other terms for that.
        """
        return SERVED_BY.get(self.kind, {}).get(verb, 0.0)

    def expired(self, world_time: int) -> bool:
        return self.deadline is not None and int(world_time) > self.deadline

    def describe(self) -> str:
        """One line, for the inspector and for a decision trace."""
        label = KIND_LABELS.get(self.kind, self.kind)
        body = self.text or label.lower()
        return f"{body} ({int(self.progress * 100)}%)"

    # ------------------------------------------------------------------ #
    #  Changing one — always a new goal
    # ------------------------------------------------------------------ #
    def with_progress(self, progress: float, world_time: int) -> "Goal":
        return replace(self, progress=max(0.0, min(1.0, progress)),
                       touched_at=int(world_time))

    def with_priority(self, priority: float) -> "Goal":
        """How much they care, changed. Not a touch: wanting something more is
        not the same as having done anything about it, and the decay clock keys
        on the latter."""
        return replace(self, priority=max(0.0, min(1.0, float(priority))))

    def with_status(self, status: str) -> "Goal":
        return replace(self, status=status if status in STATUSES else self.status)


def next_key(existing, kind: str) -> str:
    """A handle unique within one entity's goals.

    Deterministic rather than random: a campaign has to replay identically, and a
    uuid in a document that a replay reconstructs would differ every run.
    """
    taken = {g.key if isinstance(g, Goal) else str((g or {}).get("key", ""))
             for g in (existing or ())}
    index = 1
    while f"{kind}-{index}" in taken:
        index += 1
    return f"{kind}-{index}"


def from_docs(docs) -> list["Goal"]:
    return [Goal.from_doc(d) for d in (docs or [])]


def to_docs(goals) -> list[dict]:
    return [g.to_doc() for g in (goals or [])]
