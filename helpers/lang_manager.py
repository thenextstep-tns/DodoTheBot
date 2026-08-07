"""
Editable user-facing strings.

``lang.py`` holds every string the bot says, as module-level constants that cogs
read as ``lang.SOME_KEY`` at call time. This manager lets those be overridden
from the control panel **without touching source**: overrides are stored in Mongo
and applied by mutating the ``lang`` module in place, so existing ``lang.SOME_KEY``
look-ups pick them up live.

Only ``str`` and ``list[str]`` constants (UPPER_SNAKE names) are editable — the
two kinds actually present in ``lang.py``. Edits are validated so they can't
introduce a ``{placeholder}`` the calling code won't supply (which would crash the
command): the fields used by an override must be a subset of the original's.
"""

from __future__ import annotations

import copy
import string
from typing import Optional

_FORMATTER = string.Formatter()


def _fields(text: str) -> set[str]:
    """The set of format field names referenced in ``text`` (``""`` for positional)."""
    out: set[str] = set()
    try:
        for _literal, field_name, _spec, _conv in _FORMATTER.parse(text):
            if field_name is not None:
                # Normalise "a.b"/"a[0]" to the root name; positional -> "".
                root = field_name.split(".")[0].split("[")[0]
                out.add(root)
    except ValueError:
        # Malformed braces — treat as "has an unknown field" so validation can flag it.
        out.add("<invalid>")
    return out


def _is_editable(value) -> bool:
    """Editable = a string, or a list whose items are all strings. Anything else
    (e.g. a list of ``(label, value)`` tuples) is left out of the editor."""
    return isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))


def _all_fields(value) -> set[str]:
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            if isinstance(item, str):
                result |= _fields(item)
        return result
    return _fields(value)


class LangManager:
    """Snapshot the defaults, apply overrides, and mediate edits. ``bot.lang``."""

    def __init__(self, lang_module, collection):
        self._lang = lang_module
        self._col = collection
        # Snapshot pristine defaults BEFORE applying any override.
        self._defaults: dict[str, object] = {
            name: copy.deepcopy(value)
            for name, value in vars(lang_module).items()
            if not name.startswith("_") and name.upper() == name and _is_editable(value)
        }
        self.apply_all()

    # ------------------------------------------------------------------ #
    #  Applying
    # ------------------------------------------------------------------ #
    def apply_all(self) -> None:
        """Push every stored override onto the live ``lang`` module."""
        for doc in self._col.find({}):
            key, value = doc.get("key"), doc.get("value")
            if key in self._defaults and self._is_valid(key, value):
                setattr(self._lang, key, value)

    # ------------------------------------------------------------------ #
    #  Introspection (for the editor)
    # ------------------------------------------------------------------ #
    def keys(self) -> list[str]:
        return sorted(self._defaults)

    def _overrides(self) -> dict:
        return {doc["key"]: doc["value"] for doc in self._col.find({})}

    def entry(self, key: str, overrides: Optional[dict] = None) -> Optional[dict]:
        if key not in self._defaults:
            return None
        overrides = overrides if overrides is not None else self._overrides()
        default = self._defaults[key]
        current = getattr(self._lang, key, default)
        return {
            "key": key,
            "group": key.split("_")[0],
            "is_list": isinstance(default, list),
            "default": default,
            "current": current,
            "overridden": key in overrides,
            "fields": sorted(f for f in _all_fields(default) if f and f != "<invalid>"),
        }

    def all_entries(self) -> list[dict]:
        overrides = self._overrides()
        return [self.entry(key, overrides) for key in self.keys()]

    # ------------------------------------------------------------------ #
    #  Validation + writes
    # ------------------------------------------------------------------ #
    def _is_valid(self, key: str, value) -> bool:
        default = self._defaults.get(key)
        if default is None:
            return False
        if isinstance(default, list):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return False
        elif not isinstance(value, str):
            return False
        # No new placeholders beyond what the default (and thus the caller) supports.
        return _all_fields(value) <= _all_fields(default)

    def validate(self, key: str, value) -> Optional[str]:
        """Return an error message if the edit is invalid, else ``None``."""
        if key not in self._defaults:
            return f"Unknown string '{key}'."
        default = self._defaults[key]
        if isinstance(default, list) and not isinstance(value, list):
            return "This entry is a list; provide one item per line."
        if not isinstance(default, list) and not isinstance(value, str):
            return "This entry is a single string."
        extra = _all_fields(value) - _all_fields(default)
        if extra:
            shown = ", ".join(sorted(f"{{{f}}}" if f else "{}" for f in extra))
            return f"Uses placeholder(s) the command won't provide: {shown}"
        return None

    def set(self, key: str, value) -> Optional[str]:
        """Store + apply an override. Returns an error message, or ``None`` on success."""
        error = self.validate(key, value)
        if error:
            return error
        self._col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)
        setattr(self._lang, key, value)
        return None

    def reset(self, key: str) -> None:
        """Drop the override and restore the pristine default."""
        if key not in self._defaults:
            return
        self._col.delete_one({"key": key})
        setattr(self._lang, key, copy.deepcopy(self._defaults[key]))
