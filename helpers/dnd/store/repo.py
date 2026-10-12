"""
Scoped repositories — where multi-tenancy is guaranteed rather than remembered.

The cog this replaces stored no ``guild_id`` at all, so two servers could not
have used it without reading each other's games. The fix is not "remember to add
the filter": it is making an unscoped query **impossible to express**.

Every read and write goes through :class:`ScopedRepo`, which takes a
:class:`Scope` in its constructor and merges that scope into every filter it
builds. There is no method that accepts a raw filter and passes it through
untouched, and a caller cannot override ``guild_id`` or ``campaign_id`` by
putting them in a query — :meth:`ScopedRepo._filter` applies the scope *last*.

The rule that keeps this true: **collection handles from ``config.database`` are
imported only inside this package.** A cog reaching for ``dnd_entities``
directly is a review failure (docs/dnd/14-CONVENTIONS.md §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional


class ScopeError(ValueError):
    """Raised when a repository is built or used without a usable scope."""


@dataclass(frozen=True)
class Scope:
    """Which guild, and which campaign within it, a repository may see.

    ``campaign_id`` may be ``None`` for guild-wide queries — listing a server's
    campaigns, for instance. It may never be ``None`` for collections that are
    campaign-scoped; :class:`ScopedRepo` enforces that per subclass via
    :attr:`ScopedRepo.requires_campaign`.
    """

    guild_id: int
    campaign_id: Any = None

    def __post_init__(self) -> None:
        if not self.guild_id:
            raise ScopeError("a scope needs a guild_id — refusing to build an unscoped query")

    def for_campaign(self, campaign_id: Any) -> "Scope":
        return Scope(guild_id=self.guild_id, campaign_id=campaign_id)

    @property
    def has_campaign(self) -> bool:
        return self.campaign_id is not None


class ScopedRepo:
    """Base repository. Subclasses set :attr:`collection` and, usually,
    :attr:`requires_campaign`.

    Every query this builds carries the scope. Subclasses should express their
    reads in terms of :meth:`find_one`, :meth:`find` and friends rather than
    touching ``self._col`` — the private handle exists for the few operations
    (aggregation, bulk writes) the base class does not wrap, and those must
    still merge :meth:`_filter` themselves.
    """

    collection = None                 # set by the subclass
    requires_campaign: bool = True

    def __init__(self, scope: Scope, collection=None) -> None:
        col = collection if collection is not None else self.collection
        if col is None:
            raise ScopeError(f"{type(self).__name__} has no collection configured")
        if self.requires_campaign and not scope.has_campaign:
            raise ScopeError(
                f"{type(self).__name__} is campaign-scoped; the scope has no campaign_id"
            )
        self._scope = scope
        self._col = col

    # ------------------------------------------------------------------ #
    #  Scoping
    # ------------------------------------------------------------------ #
    @property
    def scope(self) -> Scope:
        return self._scope

    def _filter(self, query: Optional[dict] = None) -> dict:
        """Merge the caller's query with the scope. The scope is applied **last**
        and therefore always wins — a caller cannot widen it by passing their own
        ``guild_id``, accidentally or otherwise."""
        merged = dict(query or {})
        merged["guild_id"] = self._scope.guild_id
        if self.requires_campaign or self._scope.has_campaign:
            merged["campaign_id"] = self._scope.campaign_id
        return merged

    def _stamp(self, doc: dict) -> dict:
        """Stamp a document with the scope before it is written."""
        stamped = dict(doc)
        stamped["guild_id"] = self._scope.guild_id
        if self.requires_campaign or self._scope.has_campaign:
            stamped["campaign_id"] = self._scope.campaign_id
        return stamped

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def find_one(self, query: Optional[dict] = None) -> Optional[dict]:
        return self._col.find_one(self._filter(query))

    def find(self, query: Optional[dict] = None, *, sort=None, limit: int = 0) -> Iterator[dict]:
        cursor = self._col.find(self._filter(query))
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    def count(self, query: Optional[dict] = None) -> int:
        return self._col.count_documents(self._filter(query))

    def by_id(self, doc_id: Any) -> Optional[dict]:
        """Fetch by ``_id`` **within the scope** — an id from another campaign
        returns ``None`` rather than someone else's document."""
        return self.find_one({"_id": doc_id})

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def insert(self, doc: dict) -> Any:
        return self._col.insert_one(self._stamp(doc)).inserted_id

    def update(self, query: Optional[dict], patch: dict, *, upsert: bool = False) -> int:
        result = self._col.update_one(self._filter(query), {"$set": patch}, upsert=upsert)
        return result.modified_count

    def update_by_id(self, doc_id: Any, patch: dict) -> int:
        return self.update({"_id": doc_id}, patch)

    def apply(self, query: Optional[dict], operations: dict) -> int:
        """Apply raw update operators (``$push``, ``$addToSet``, ``$inc``, …).

        Still scoped: the filter goes through :meth:`_filter` like everything
        else, so an operator cannot escape the tenant boundary.
        """
        result = self._col.update_one(self._filter(query), operations)
        return result.modified_count

    def delete(self, query: Optional[dict]) -> int:
        return self._col.delete_one(self._filter(query)).deleted_count

    def delete_many(self, query: Optional[dict] = None) -> int:
        return self._col.delete_many(self._filter(query)).deleted_count
