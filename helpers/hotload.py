"""
Let a cog pick up new settings and texts on a plain cog reload, no restart.

A cog reload re-imports the cog only. ``helpers.parameters`` and ``lang`` stay
the copies loaded at startup, so a reloaded cog that uses a setting or a text
added since then fails (``KeyError: Unknown parameter`` / ``AttributeError``).

- ``register_missing(bot, cog)`` — call from the cog's ``setup``: reads the
  settings registry as it is on disk now and brings the running bot (and the
  panel, which reads the live ``PARAMETERS`` list) up to date for that cog.
- ``fresh_lang()`` — the texts as they are on disk now, for the cog to use in
  place of ``import lang``.

After a full restart both are no-ops in effect. This module is deliberately
separate: being new, it is imported fresh by the first reload that uses it.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

_log = logging.getLogger("dodo")
_ROOT = Path(__file__).resolve().parent.parent


def _load_private(name: str, path: Path):
    """The module at ``path`` as the file reads now, as a private copy (the live module is untouched)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh_lang():
    """``lang`` as it is on disk now. Nothing patches ``lang`` at runtime, so a fresh copy is equivalent."""
    return _load_private("_lang_on_disk", _ROOT / "lang.py")


def _specs_on_disk() -> list[dict]:
    return _load_private("helpers._parameters_on_disk", _ROOT / "helpers" / "parameters.py").PARAMETERS


def register_missing(bot, cog: str) -> list[str]:
    """Bring ``cog``'s settings in the running bot up to date with the file. Returns the keys added.

    New settings are added; known ones get their current default, label and
    description (updated in place, so the panel's list sees it too). Values
    admins have saved are never touched — those live in the database.
    """
    manager = bot.params
    live_list = sys.modules["helpers.parameters"].PARAMETERS
    added, refreshed = [], []
    for spec in _specs_on_disk():
        if spec["cog"] != cog:
            continue
        known = manager._by_key.get(spec["key"])
        if known is not None:
            if known != spec:
                known.clear()
                known.update(spec)
                refreshed.append(spec["key"])
            continue
        manager._by_key[spec["key"]] = spec
        manager._by_cog.setdefault(cog, []).append(spec)
        if all(existing["key"] != spec["key"] for existing in live_list):
            live_list.append(spec)
        added.append(spec["key"])
    if added or refreshed:
        _log.info(
            "%s settings updated without a restart: %d added (%s), %d refreshed (%s)",
            cog, len(added), ", ".join(added), len(refreshed), ", ".join(refreshed),
        )
    return added
