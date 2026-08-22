"""
A minimal in-memory stand-in for a pymongo collection.

Deliberately not a dependency. The engine's tests need to prove things about
*scoping and sequencing* — that one campaign can never see another's documents,
that event numbers are allocated atomically — and those are properties of our
query construction, not of MongoDB. A real driver (or mongomock) in
``requirements.txt`` would ship to the VPS to serve a test that does not need it.

Supports only what ``helpers/dnd/store/`` actually calls. If a repository starts
using an operator this does not implement, the test will fail loudly on the
unknown key rather than passing by silently ignoring it — which is the behaviour
you want from a fake.
"""

from __future__ import annotations

import itertools
import re
from typing import Any


class DuplicateKeyError(Exception):
    """Mirrors ``pymongo.errors.DuplicateKeyError`` for unique-index tests."""


def _matches(doc: dict, query: dict) -> bool:
    """Query matching for the operators the repositories use."""
    for key, condition in query.items():
        value = _resolve(doc, key)
        if isinstance(condition, re.Pattern):
            if not (isinstance(value, str) and condition.match(value)):
                return False
        elif isinstance(condition, dict):
            for operator, operand in condition.items():
                if operator == "$ne":
                    if value == operand:
                        return False
                elif operator == "$gt":
                    if not (value is not None and value > operand):
                        return False
                elif operator == "$gte":
                    if not (value is not None and value >= operand):
                        return False
                elif operator == "$lt":
                    if not (value is not None and value < operand):
                        return False
                elif operator == "$lte":
                    if not (value is not None and value <= operand):
                        return False
                elif operator == "$nin":
                    if value in operand:
                        return False
                elif operator == "$in":
                    if value not in operand:
                        return False
                else:
                    raise NotImplementedError(f"fake_mongo: operator {operator!r}")
        elif value != condition:
            return False
    return True


def _resolve(doc: dict, dotted: str) -> Any:
    """Read a possibly-dotted path, e.g. ``identity.name``."""
    current: Any = doc
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _assign(doc: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    current = doc
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


class FakeCollection:
    """An in-memory collection with the surface the store layer uses."""

    _ids = itertools.count(1)

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.docs: list[dict] = []
        self._unique: list[list[str]] = []

    # -- indices ------------------------------------------------------- #
    def create_index(self, keys, **kwargs) -> None:
        if kwargs.get("unique"):
            self._unique.append([field for field, _direction in keys])

    def _check_unique(self, doc: dict) -> None:
        for fields in self._unique:
            if any(_resolve(doc, f) is None for f in fields):
                continue
            for existing in self.docs:
                if all(_resolve(existing, f) == _resolve(doc, f) for f in fields):
                    raise DuplicateKeyError(f"duplicate on {fields}")

    # -- reads --------------------------------------------------------- #
    def find_one(self, query: dict | None = None):
        for doc in self.docs:
            if _matches(doc, query or {}):
                return dict(doc)
        return None

    def find(self, query: dict | None = None):
        return _FakeCursor([dict(d) for d in self.docs if _matches(d, query or {})])

    def count_documents(self, query: dict | None = None) -> int:
        return sum(1 for d in self.docs if _matches(d, query or {}))

    # -- writes -------------------------------------------------------- #
    def insert_one(self, doc: dict):
        stored = dict(doc)
        stored.setdefault("_id", f"id{next(self._ids)}")
        self._check_unique(stored)
        self.docs.append(stored)
        return type("Result", (), {"inserted_id": stored["_id"]})()

    def insert_many(self, docs: list[dict]):
        # Mirrors pymongo: the caller's dicts are stamped with their new _id in
        # place, which seeding relies on to render freshly created rows.
        for doc in docs:
            doc["_id"] = self.insert_one(doc).inserted_id
        return type("Result", (), {"inserted_ids": [d["_id"] for d in docs]})()

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        for doc in self.docs:
            if _matches(doc, query or {}):
                self._apply(doc, update)
                return type("Result", (), {"modified_count": 1})()
        if upsert:
            base = {k: v for k, v in (query or {}).items() if not isinstance(v, (dict, re.Pattern))}
            self._apply(base, update)
            self.insert_one(base)
            return type("Result", (), {"modified_count": 1})()
        return type("Result", (), {"modified_count": 0})()

    def find_one_and_update(self, query: dict, update: dict, return_document=True):
        for doc in self.docs:
            if _matches(doc, query or {}):
                self._apply(doc, update)
                return dict(doc)
        return None

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query or {}):
                self.docs.pop(index)
                return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    def delete_many(self, query: dict | None = None):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query or {})]
        return type("Result", (), {"deleted_count": before - len(self.docs)})()

    @staticmethod
    def _apply(doc: dict, update: dict) -> None:
        for operator, fields in update.items():
            if operator == "$set":
                for key, value in fields.items():
                    _assign(doc, key, value)
            elif operator == "$inc":
                for key, value in fields.items():
                    _assign(doc, key, (_resolve(doc, key) or 0) + value)
            elif operator == "$addToSet":
                for key, value in fields.items():
                    current = list(_resolve(doc, key) or [])
                    if value not in current:
                        current.append(value)
                    _assign(doc, key, current)
            elif operator == "$push":
                for key, value in fields.items():
                    _assign(doc, key, list(_resolve(doc, key) or []) + [value])
            elif operator == "$pull":
                for key, value in fields.items():
                    _assign(doc, key, [x for x in (_resolve(doc, key) or []) if x != value])
            else:
                raise NotImplementedError(f"fake_mongo: update operator {operator!r}")


class _FakeCursor:
    """Just enough cursor to support ``.sort(...).limit(...)`` chaining."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, spec, direction: int = 1):
        # pymongo accepts both sort("key", 1) and sort([("key", 1), …]); callers
        # in this repo use each, so the fake has to take both or it fails on the
        # call shape rather than on the behaviour under test.
        if isinstance(spec, str):
            spec = [(spec, direction)]
        for field, direction in reversed(spec):
            self._docs.sort(key=lambda d: _sort_key(_resolve(d, field)), reverse=direction < 0)
        return self

    def limit(self, count: int):
        if count:
            self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)


def _sort_key(value):
    """Sort mixed/missing values without raising, the way a real sort must."""
    if value is None:
        return (0, "")
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value))
