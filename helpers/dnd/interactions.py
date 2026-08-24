"""
Interaction kinds, resolved.

    built-in JSON  →  server override  →  campaign override

The same shape as ``tuning.py`` and ``packs.py``, deliberately: this codebase
has one mental model for layered configuration, and what an act is worth is
configuration rather than world content.

What this replaced is the interesting part. The set of kinds was written down
**four times** — ``DELTAS``, ``PHRASES`` and ``ROMANTIC`` in
``mind/relationships.py`` and ``KIND_MAGNITUDE`` in ``mind/stakes.py`` — all
keyed by the same strings and all maintained by hand. They had drifted before
anybody looked: the five romantic kinds went into three of the four and were
never given a magnitude, so ``lay_with`` fell through to the 0.4 default and was
worth exactly as much as ``lied``. No test could have caught it, because there
was nowhere the set of kinds was defined as one thing.

Where the overrides live, mirroring packs exactly:

* server    → the ``DndTuning`` document's ``interactions`` map
* campaign  → ``campaign.settings["interactions"]``, so a campaign carries its
  own social physics in its export bundle and needs no extra table

A campaign-level kind with the same key as a built-in **replaces** it, which is
how you make betrayal the end of the world in one game without touching a file
that ships — or add a kind the engine has never heard of.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from helpers.dnd.world.interaction import (
    SOURCE_BUILTIN,
    Interaction,
    as_deltas,
    as_magnitudes,
    as_phrases,
)

DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "interactions.json"
)

SOURCE_SERVER = "server"
SOURCE_CAMPAIGN = "campaign"

_BUILT_IN: dict[str, Interaction] | None = None


def built_in() -> dict[str, Interaction]:
    """The kinds that ship, loaded once.

    Unlike behaviour packs, an empty registry here is **not** a survivable
    degradation — with no kinds nothing can happen between two people at all, so
    a broken file would silently turn the social simulation off. It still does
    not raise on import, because a module that cannot be imported takes the
    whole cog offline and this project has had that outage twice; instead the
    failure is visible where it matters, in an empty *Interactions* panel
    section and in a test that asserts the shipped file parses.
    """
    global _BUILT_IN
    if _BUILT_IN is None:
        _BUILT_IN = {}
        try:
            with open(DATA_PATH, encoding="utf-8") as handle:
                raw = json.load(handle)
            for doc in raw.get("interactions", []):
                kind = Interaction.from_doc(doc, source=SOURCE_BUILTIN)
                if kind.key:
                    _BUILT_IN[kind.key] = kind
        except (OSError, ValueError):
            _BUILT_IN = {}
    return dict(_BUILT_IN)


def reload() -> dict[str, Interaction]:
    """Drop the cache. For tests and for editing the file in a dev loop."""
    global _BUILT_IN
    _BUILT_IN = None
    return built_in()


class Interactions:
    """The interaction kinds available to one campaign."""

    def __init__(self, server: Optional[dict] = None, campaign: Optional[dict] = None):
        self._server = server or {}
        self._campaign = campaign or {}

    @classmethod
    def for_campaign(cls, guild_id: Optional[int], campaign=None) -> "Interactions":
        from helpers.dnd import parameters as dnd_parameters

        server = dnd_parameters.interaction_overrides(guild_id)
        own = {}
        if campaign is not None:
            own = (campaign.settings or {}).get("interactions") or {}
        return cls(server, own)

    # ------------------------------------------------------------------ #
    #  Resolution
    # ------------------------------------------------------------------ #
    def available(self) -> dict[str, Interaction]:
        """Every kind this campaign can record, most specific definition winning.
        Insertion order is built-ins first, then anything added."""
        out = built_in()
        for layer, source in ((self._server, SOURCE_SERVER),
                              (self._campaign, SOURCE_CAMPAIGN)):
            for key, doc in (layer or {}).items():
                kind = Interaction.from_doc({**doc, "key": key}, source=source)
                if kind.key:
                    out[kind.key] = kind
        return out

    def get(self, key: str) -> Optional[Interaction]:
        return self.available().get(str(key).strip().lower())

    def source_of(self, key: str) -> str:
        key = str(key).strip().lower()
        if key in self._campaign:
            return SOURCE_CAMPAIGN
        if key in self._server:
            return SOURCE_SERVER
        return SOURCE_BUILTIN

    def keys(self) -> list[str]:
        return sorted(self.available())

    # ------------------------------------------------------------------ #
    #  The shapes the pure layers take
    # ------------------------------------------------------------------ #
    # Each of these is what one pure module wants, built at the orchestration
    # edge and passed in — `mind/` never reaches for this registry itself.
    def deltas(self) -> dict[str, dict]:
        return as_deltas(self.available())

    def phrases(self) -> dict[str, str]:
        return as_phrases(self.available())

    def magnitudes(self) -> dict[str, float]:
        return as_magnitudes(self.available())

    def entries(self) -> list[dict]:
        """Definitions plus where each came from, for the panel."""
        return [
            {**kind.to_doc(), "source": self.source_of(key), "kind": kind,
             "overridden": self.source_of(key) != SOURCE_BUILTIN and key in built_in()}
            for key, kind in self.available().items()
        ]


def _slug(text: str) -> str:
    """A key from a name: lowercase, alphanumerics, underscores between words."""
    cleaned = "".join(
        char if char.isalnum() else " " for char in str(text or "").lower()
    )
    return "_".join(cleaned.split())[:40]


def validate(doc: dict) -> tuple[Optional[dict], str]:
    """Check a GM-authored interaction kind. Returns ``(clean_doc, error)``.

    Refuses on two counts only — it needs a name, and it needs to *do* something
    to somebody. Unknown axes are dropped quietly by
    :meth:`Interaction.from_doc`, because that is a definition getting tidier
    rather than a GM being wrong.

    The key is derived from the name **only when there is no key already**, the
    same rule archetypes learned the hard way: an existing kind keeps its key
    when renamed, or renaming *Betrayed* would leave betrayal alone and add a
    second kind beside it.
    """
    doc = doc or {}
    label = str(doc.get("label") or "").strip()
    key = _slug(str(doc.get("key") or "") or label)
    if not key:
        return None, "This needs a name."

    kind = Interaction.from_doc({**doc, "key": key, "label": label or key})
    if not kind.deltas:
        return None, (
            "An act that changes nothing between two people would leave no "
            "trace. Move at least one of the sliders, or set a debt."
        )
    return kind.to_doc(), ""


def upsert(store: dict, doc: dict, *, key: str = "") -> tuple[str, dict]:
    """Add or edit one kind in an override map. Returns ``(key, new_map)``.

    ``key`` is sent by an existing card so a **rename edits in place**; the add
    form sends only a name and the key is slugged from it here. Sending the name
    as the key from both would fork a definition every time somebody renamed one
    — which is exactly what archetypes did before they were fixed the same way.
    """
    settled = str(key).strip().lower() or _slug(doc.get("label") or doc.get("key"))
    if not settled:
        return "", dict(store or {})
    out = dict(store or {})
    out[settled] = Interaction.from_doc({**doc, "key": settled}).to_doc()
    return settled, out
