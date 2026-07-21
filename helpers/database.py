"""
Database helpers.

Thin wrappers over the common MongoDB access patterns that were repeated across
cogs (fetch-by-id, upsert, atomic increment, counting). They operate on a
pymongo ``Collection`` passed in by the caller — the collections themselves live
in ``config_py`` for now.
"""

from typing import Any, Optional


def get_by_id(collection, _id: Any) -> Optional[dict]:
    """Return the document with ``_id``, or ``None``."""
    return collection.find_one({"_id": _id})


def get_or_default(collection, _id: Any, field: str, default: Any = None) -> Any:
    """Return ``document[field]`` for ``_id``, falling back to ``default``."""
    document = collection.find_one({"_id": _id})
    return document.get(field, default) if document else default


def upsert(collection, _id: Any, fields: dict) -> None:
    """Set ``fields`` on the document with ``_id``, creating it if needed."""
    collection.update_one({"_id": _id}, {"$set": fields}, upsert=True)


def increment(collection, _id: Any, field: str, amount: int = 1) -> None:
    """Atomically add ``amount`` to ``field`` on the document with ``_id``."""
    collection.update_one({"_id": _id}, {"$inc": {field: amount}}, upsert=True)


def count(collection, query: dict = None) -> int:
    """Count documents matching ``query`` (all documents if omitted)."""
    return collection.count_documents(query or {})


def exists(collection, query: dict) -> bool:
    """Return whether any document matches ``query``."""
    return collection.count_documents(query, limit=1) > 0
