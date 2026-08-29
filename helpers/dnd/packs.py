"""
Behaviour packs, resolved.

    built-in JSON  →  server override  →  campaign override

The same shape as ``tuning.py``, and deliberately so: this codebase has one
mental model for layered configuration and archetypes are configuration, not
world content. A server admin adds the house archetypes; a **campaign GM adds
their own** without touching anyone else's game.

Why this file exists at all: ``04-ENTITIES.md`` §9 says culture and role priors
should come from the campaign's own data, and they still do not — they are
tables in ``mind/traits.py``, which is why a GM cannot add a trade. Packs were
the next thing in line to make that mistake, so they do not: the six that ship
live in ``helpers/dnd/data/packs.json`` as data, and a GM who needs a *smuggler*
adds one from the panel.

Where the overrides live, mirroring tunables exactly:

* server    → the ``DndTuning`` document's ``packs`` map, via ``helpers/dnd/parameters``
* campaign  → ``campaign.settings["packs"]``, so a campaign carries its
  archetypes with it and an export bundle needs no extra table

A campaign-level pack with the same key as a built-in **replaces** it. That is
how you retune the coward for a game where nobody runs, without editing a file
that ships.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from helpers.dnd.rules.ruleset import AFFORDANCES
from helpers.dnd.world.pack import BehaviourPack, restricted_to

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "packs.json")

SOURCE_BUILTIN = "builtin"
SOURCE_SERVER = "server"
SOURCE_CAMPAIGN = "campaign"

_BUILT_IN: dict[str, BehaviourPack] | None = None


def built_in() -> dict[str, BehaviourPack]:
    """The archetypes that ship, loaded once.

    A missing or unreadable file yields an empty registry rather than raising:
    packs shape behaviour, and a campaign whose NPCs are undifferentiated is a
    duller campaign, not a broken one. The engine falls back to weighing every
    affordance evenly, which is exactly what turning packs off does.
    """
    global _BUILT_IN
    if _BUILT_IN is None:
        _BUILT_IN = {}
        try:
            with open(DATA_PATH, encoding="utf-8") as handle:
                raw = json.load(handle)
            for doc in raw.get("packs", []):
                pack = restricted_to(
                    BehaviourPack.from_doc(doc, source=SOURCE_BUILTIN), AFFORDANCES
                )
                if pack.key:
                    _BUILT_IN[pack.key] = pack
        except (OSError, ValueError):
            _BUILT_IN = {}
    return dict(_BUILT_IN)


def reload() -> dict[str, BehaviourPack]:
    """Drop the cache. For tests and for editing the file in a dev loop."""
    global _BUILT_IN
    _BUILT_IN = None
    return built_in()


class Packs:
    """The archetypes available to one campaign."""

    def __init__(self, server: Optional[dict] = None, campaign: Optional[dict] = None):
        self._server = server or {}
        self._campaign = campaign or {}

    @classmethod
    def for_campaign(cls, guild_id: Optional[int], campaign=None) -> "Packs":
        from helpers.dnd import parameters as dnd_parameters

        server = dnd_parameters.pack_overrides(guild_id)
        campaign_packs = {}
        if campaign is not None:
            campaign_packs = (campaign.settings or {}).get("packs") or {}
        return cls(server, campaign_packs)

    # ------------------------------------------------------------------ #
    #  Resolution
    # ------------------------------------------------------------------ #
    def available(self) -> dict[str, BehaviourPack]:
        """Every archetype this campaign can draw on, most specific definition
        winning. Insertion order is built-ins first, then anything added."""
        out = built_in()
        for layer, source in ((self._server, SOURCE_SERVER),
                              (self._campaign, SOURCE_CAMPAIGN)):
            for key, doc in (layer or {}).items():
                pack = restricted_to(
                    BehaviourPack.from_doc({**doc, "key": key}, source=source),
                    AFFORDANCES,
                )
                if pack.key:
                    out[pack.key] = pack
        return out

    def get(self, key: str) -> Optional[BehaviourPack]:
        return self.available().get(str(key).strip().lower())

    def source_of(self, key: str) -> str:
        """Which layer supplied the definition in force — shown in the panel so a
        GM can see whether they are editing their own archetype or a shipped one."""
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
            {**pack.to_doc(), "source": self.source_of(key), "pack": pack,
             "overridden": self.source_of(key) != SOURCE_BUILTIN and key in built_in()}
            for key, pack in self.available().items()
        ]


def _slug(text: str) -> str:
    """A key from a name: lowercase, alphanumerics, dashes between words."""
    parts = ["".join(c for c in word if c.isalnum()) for word in str(text).lower().split()]
    return "-".join(part for part in parts if part)


def validate(doc: dict) -> tuple[Optional[dict], str]:
    """Check a GM-authored pack. Returns ``(clean_doc, error)``.

    Refuses rather than silently repairing on only two counts — a pack needs a
    key, and it needs at least one verb it actually reaches for. Weights for
    verbs no ruleset grants are dropped quietly, because that is a definition
    getting tidier rather than a GM being wrong.
    """
    # A GM names an archetype once; the key is this module's business. Derived
    # from the name only when there is no key already — an existing archetype
    # keeps its key when it is renamed, or renaming the coward would quietly
    # leave the coward alone and add a second archetype beside it.
    doc = doc or {}
    label = str(doc.get("label") or "").strip()
    key = _slug(str(doc.get("key") or "") or label)
    if not key:
        return None, "An archetype needs a name."

    pack = restricted_to(
        BehaviourPack.from_doc({**doc, "key": key, "label": label or key}),
        AFFORDANCES,
    )
    if not any(v > 0 for v in pack.weights.values()):
        return None, (
            "An archetype that reaches for nothing would never propose anything. "
            "Give at least one action a weight above zero."
        )
    return pack.to_doc(), ""
