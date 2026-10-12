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

**Scoped overrides.** ``lang.SOME_KEY`` is a module global, so it can only ever
hold one value for the whole process. Anything per-server or per-language has to
come through :meth:`LangManager.get`, which resolves

    guild + locale  ->  guild + default locale  ->  global + locale
                    ->  global + default        ->  the value in lang.py

Mutating the module is kept for the global/default layer, so every existing
``lang.KEY`` read keeps working and means exactly what it used to. Cogs move to
``bot.lang.get(...)`` where they need a server's or a user's own wording.
"""

from __future__ import annotations

import copy
import re
import string
from typing import Optional

_FORMATTER = string.Formatter()

# Rows written before overrides had a scope carry neither field; they are the
# global, default-locale layer, which is exactly what a missing value means.
_GLOBAL_QUERY = {"guild_id": None, "locale": None}


# Discord's own caps. The hard one is the largest any single field accepts, so
# anything above it is refused; the rest only earn a warning because whether a
# string is a message, an embed body or a button label isn't knowable from here.
HARD_LIMIT = 4096      # embed description
MESSAGE_LIMIT = 2000   # a plain message
BUTTON_LIMIT = 80      # a component label
_CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")


def _looks_like_label(key: str) -> bool:
    """Keys whose wording ends up on a button, where 80 characters is the cap."""
    return key.endswith(("_BUTTON", "_LABEL")) or "_BUTTON_" in key


def _normalise_locale(locale: Optional[str]) -> Optional[str]:
    """BCP-47 as Discord sends it (``en-GB``), or ``None`` for the default."""
    text = (locale or "").strip()
    if not text:
        return None
    parts = text.replace("_", "-").split("-")
    return parts[0].lower() + ("-" + parts[1].upper() if len(parts) > 1 else "")


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

    def __init__(self, lang_module, collection, *, default_locale: Optional[str] = None):
        self._lang = lang_module
        self.default_locale = _normalise_locale(default_locale)
        self._scope_cache: dict[tuple, dict] = {}
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
        for doc in self._col.find(_GLOBAL_QUERY):
            key, value = doc.get("key"), doc.get("value")
            if key in self._defaults and self._is_valid(key, value):
                setattr(self._lang, key, value)

    # ------------------------------------------------------------------ #
    #  Introspection (for the editor)
    # ------------------------------------------------------------------ #
    def keys(self) -> list[str]:
        return sorted(self._defaults)

    def _overrides(self) -> dict:
        """The global, default-locale overrides — the layer that lang.KEY sees."""
        return {doc["key"]: doc["value"] for doc in self._col.find(_GLOBAL_QUERY)
                if self._is_valid(doc.get("key"), doc.get("value"))}

    # ------------------------------------------------------------------ #
    #  Scoped resolution
    # ------------------------------------------------------------------ #
    def _scoped(self, guild_id: Optional[int], locale: Optional[str]) -> dict:
        """Every override for one (guild, locale) pair, cached."""
        key = (int(guild_id) if guild_id else None, locale or None)
        if key not in self._scope_cache:
            query = {"guild_id": key[0], "locale": key[1]}
            self._scope_cache[key] = {
                doc["key"]: doc["value"] for doc in self._col.find(query)
                if self._is_valid(doc.get("key"), doc.get("value"))
            }
        return self._scope_cache[key]

    def get(self, key: str, *, guild=None, locale: Optional[str] = None,
            default_locale: Optional[str] = None):
        """The wording to use here, walking the fallback chain.

        Every step is optional and the chain always ends somewhere real — the
        constant in ``lang.py`` — so a missing translation degrades to the
        original wording rather than to an empty string or a raised key.
        """
        guild_id = getattr(guild, "id", guild)
        locale = _normalise_locale(locale)
        base = _normalise_locale(default_locale or self.default_locale)
        for scope_guild, scope_locale in (
            (guild_id, locale),
            (guild_id, base),
            (None, locale),
            (None, base),
        ):
            if scope_guild is None and scope_locale is None:
                continue          # that layer is the module itself, handled below
            found = self._scoped(scope_guild, scope_locale).get(key)
            if found is not None:
                return found
        return getattr(self._lang, key, self._defaults.get(key))

    def locales(self) -> list[str]:
        """Locales that actually have something stored, for the panel's picker."""
        try:
            found = self._col.distinct("locale")
        except Exception:  # noqa: BLE001
            return []
        return sorted(loc for loc in found if loc)

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

    def validate(self, key: str, value, *, guild_id: Optional[int] = None) -> Optional[str]:
        """Return an error message if the edit must be refused, else ``None``.

        Only things that would actually break at runtime are refused. Style is
        reported by :meth:`warnings` instead — an editor that blocks on taste
        gets fought rather than followed.
        """
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
        for item in (value if isinstance(value, list) else [value]):
            if len(item) > HARD_LIMIT:
                return (f"{len(item)} characters — Discord refuses anything over "
                        f"{HARD_LIMIT} in a single field.")
        return None

    def warnings(self, key: str, value, *, guild_id: Optional[int] = None) -> list[str]:
        """Things worth knowing that aren't worth refusing."""
        out = []
        default = self._defaults.get(key)
        for item in (value if isinstance(value, list) else [value]):
            if not isinstance(item, str):
                continue
            if len(item) > MESSAGE_LIMIT:
                out.append(f"{len(item)} characters — too long for a plain message "
                           f"({MESSAGE_LIMIT}); fine inside an embed description.")
            if len(item) > BUTTON_LIMIT and _looks_like_label(key):
                out.append(f"{len(item)} characters — a button label is capped at "
                           f"{BUTTON_LIMIT}.")
            for token, what in (("**", "bold"), ("`", "code")):
                if item.count(token) % 2:
                    out.append(f"Unbalanced {what} markers ({token}).")
            if "@everyone" in item or "@here" in item:
                out.append("Contains @everyone/@here — it will ping if the message "
                           "allows those mentions.")
            # A custom emoji is a reference to one guild's uploads. Global
            # wording is read in every server, where that id renders as raw text.
            if guild_id is None and _CUSTOM_EMOJI.search(item):
                out.append("Custom server emoji only render where the bot shares "
                           "that server — in a global string it shows as raw text.")
        if default is not None:
            missing = _all_fields(default) - _all_fields(value)
            if missing:
                shown = ", ".join(sorted(f"{{{f}}}" if f else "{}" for f in missing))
                out.append(f"Drops placeholder(s) the default uses: {shown}")
        return out

    def set(self, key: str, value, *, guild_id: Optional[int] = None,
            locale: Optional[str] = None) -> Optional[str]:
        """Store + apply an override. Returns an error message, or ``None`` on success.

        Only the global/default layer touches the module: that is the one whose
        value ``lang.KEY`` is supposed to mean.
        """
        error = self.validate(key, value, guild_id=guild_id)
        if error:
            return error
        guild_id = int(guild_id) if guild_id else None
        locale = _normalise_locale(locale)
        self._col.update_one({"key": key, "guild_id": guild_id, "locale": locale},
                             {"$set": {"value": value}}, upsert=True)
        if guild_id is None and locale is None:
            setattr(self._lang, key, value)
        self._scope_cache.pop((guild_id, locale), None)
        return None

    def reset(self, key: str, *, guild_id: Optional[int] = None,
              locale: Optional[str] = None) -> None:
        """Drop one scope's override and fall back to whatever is underneath."""
        if key not in self._defaults:
            return
        guild_id = int(guild_id) if guild_id else None
        locale = _normalise_locale(locale)
        self._col.delete_one({"key": key, "guild_id": guild_id, "locale": locale})
        if guild_id is None and locale is None:
            setattr(self._lang, key, copy.deepcopy(self._defaults[key]))
        self._scope_cache.pop((guild_id, locale), None)
