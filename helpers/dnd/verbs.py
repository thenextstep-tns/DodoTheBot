"""
Verbs, resolved.

    built-in JSON  →  server override  →  campaign override

The third registry with this shape, after ``packs.py`` and ``interactions.py``,
and deliberately identical to both: one mental model for layered configuration,
and by now a pattern rather than a decision.

**This one sits lowest.** ``rules/ruleset.py`` reads it for the affordance list,
which means nothing here may import ``rules`` — the dependency runs the other
way. It imports the model and the standard library, and nothing else.

Why it exists: a verb used to be spread across eight hand-maintained tables in
five modules (see ``world/verb.py``), and adding one meant getting all eight
right. Missing one never raised — it made the verb unreachable, or weightless,
or unrememberable. The six verbs added alongside this file are the proof: they
are one JSON object each plus a grant in the two rulesets, where before they
would have been forty edits.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from helpers.dnd.world.verb import SOURCE_BUILTIN, Verb

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                         "verbs.json")

SOURCE_SERVER = "server"
SOURCE_CAMPAIGN = "campaign"

_BUILT_IN: dict[str, Verb] | None = None


def built_in() -> dict[str, Verb]:
    """The verbs that ship, loaded once.

    An empty registry here would leave characters with nothing they could
    possibly decide to do, so a broken file is not a survivable degradation the
    way a missing archetype is. It still does not raise on import — a module
    that cannot be imported takes the whole cog offline, and this project has
    had that outage twice — so the failure surfaces as an empty *Verbs* section
    in the panel and a failing test, rather than as a dead bot.
    """
    global _BUILT_IN
    if _BUILT_IN is None:
        _BUILT_IN = {}
        try:
            with open(DATA_PATH, encoding="utf-8") as handle:
                raw = json.load(handle)
            for doc in raw.get("verbs", []):
                verb = Verb.from_doc(doc, source=SOURCE_BUILTIN)
                if verb.key:
                    _BUILT_IN[verb.key] = verb
        except (OSError, ValueError):
            _BUILT_IN = {}
    return dict(_BUILT_IN)


def reload() -> dict[str, Verb]:
    """Drop the cache. For tests and for editing the file in a dev loop."""
    global _BUILT_IN
    _BUILT_IN = None
    return built_in()


class Verbs:
    """The verbs available to one campaign."""

    def __init__(self, server: Optional[dict] = None, campaign: Optional[dict] = None):
        self._server = server or {}
        self._campaign = campaign or {}

    @classmethod
    def for_campaign(cls, guild_id: Optional[int], campaign=None) -> "Verbs":
        from helpers.dnd import parameters as dnd_parameters

        server = dnd_parameters.verb_overrides(guild_id)
        own = {}
        if campaign is not None:
            own = (campaign.settings or {}).get("verbs") or {}
        return cls(server, own)

    def available(self) -> dict[str, Verb]:
        out = built_in()
        for layer, source in ((self._server, SOURCE_SERVER),
                              (self._campaign, SOURCE_CAMPAIGN)):
            for key, doc in (layer or {}).items():
                verb = Verb.from_doc({**doc, "key": key}, source=source)
                if verb.key:
                    out[verb.key] = verb
        return out

    def get(self, key: str) -> Optional[Verb]:
        return self.available().get(str(key).strip().lower())

    def source_of(self, key: str) -> str:
        key = str(key).strip().lower()
        if key in self._campaign:
            return SOURCE_CAMPAIGN
        if key in self._server:
            return SOURCE_SERVER
        return SOURCE_BUILTIN

    def keys(self) -> list[str]:
        return list(self.available())

    def entries(self) -> list[dict]:
        """Definitions plus where each came from, for the panel."""
        return [
            {**verb.to_doc(), "source": self.source_of(key), "verb": verb,
             "overridden": self.source_of(key) != SOURCE_BUILTIN and key in built_in()}
            for key, verb in self.available().items()
        ]


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else " " for c in str(text or "").lower())
    return "_".join(cleaned.split())[:24]


def validate(doc: dict) -> tuple[Optional[dict], str]:
    """Check a GM-authored verb. Returns ``(clean_doc, error)``.

    Two refusals only. A verb needs a name, and it needs to be *reachable*: an
    archetype proposes candidates by intersecting its weights with what the
    scene affords, so a verb no archetype ever reaches for and no goal is served
    by can never be proposed. That is the silent-failure mode this whole file
    exists to stop, so it is refused at the door instead.

    As with archetypes and interaction kinds, the key is derived from the name
    **only when there is no key already**, so renaming edits in place rather
    than forking.
    """
    doc = doc or {}
    label = str(doc.get("label") or "").strip()
    key = _slug(str(doc.get("key") or "") or label)
    if not key:
        return None, "A verb needs a name."

    verb = Verb.from_doc({**doc, "key": key, "label": label or key})
    if not verb.goals and not verb.traits:
        return None, (
            "Nothing would ever reach for this. Give it at least one "
            "disposition that leans toward it, or one kind of goal it serves — "
            "otherwise no character can ever propose it."
        )
    return verb.to_doc(), ""
