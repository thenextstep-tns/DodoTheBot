"""
Capability links: a URL that is itself the credential.

Used for the public trial-rank leaderboard, and built so the per-recipient
tokens that will back a "see the full rankings" button can reuse it unchanged.

The rules that make this safe are all here, so there is one place to check them:

* **Only a hash is stored.** A token is 256 bits from ``secrets``, so a plain
  SHA-256 is enough — there is nothing to brute-force and no password to
  stretch. A dump of the collection therefore hands out no working links.
* **Shown once.** The consequence of hashing: the panel can display a new link
  at the moment it is issued and never again. Lost means rotate, which is the
  same bargain as an API key and the reason the bargain is worth taking.
* **Compared in constant time**, so a timing oracle can't be walked one
  character at a time.
* **Revocable and expirable**, per token and per kind, because "rotate the
  link" has to be a real answer when one leaks.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import secrets
from typing import Optional

# 32 bytes of entropy, URL-safe. Long enough that guessing is not a threat model.
TOKEN_BYTES = 32
# What a token is for. Guild-wide links are handed out by an admin; per-user
# ones will be minted per embed so a leak is traceable and revocable alone.
KIND_PUBLIC = "public"
KIND_USER = "user"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ShareTokenStore:
    """Issues and resolves capability tokens. ``bot.share_tokens``."""

    def __init__(self, collection) -> None:
        self._col = collection
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if self._col is None or self._indexed:
            return
        self._indexed = True
        try:
            self._col.create_index("token_hash", unique=True, background=True)
            # Mongo drops a document once expires_at passes; rows without one
            # are kept, which is what a link with no expiry means.
            self._col.create_index("expires_at", expireAfterSeconds=0, background=True)
        except Exception:  # noqa: BLE001 - housekeeping never blocks a request
            pass

    def issue(self, guild_id: int, *, kind: str = KIND_PUBLIC,
              user_id: Optional[int] = None, ttl_days: Optional[int] = None,
              replace: bool = True) -> str:
        """Mint a token and return it in the clear, this once.

        ``replace`` retires every existing token of the same kind, which is what
        makes the panel's button a rotation rather than an accumulation of live
        links nobody is tracking.
        """
        if self._col is None:
            return ""
        self._ensure_indexes()
        if replace:
            self.revoke_all(guild_id, kind=kind, user_id=user_id)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "guild_id": int(guild_id),
            "kind": kind,
            "user_id": int(user_id) if user_id else None,
            "token_hash": _hash(token),
            "created_at": now,
        }
        if ttl_days:
            doc["expires_at"] = now + datetime.timedelta(days=int(ttl_days))
        self._col.insert_one(doc)
        return token

    def resolve(self, guild_id: int, token: str, *, kind: Optional[str] = None) -> Optional[dict]:
        """The token's record, or ``None``. Never raises on a bad token."""
        if self._col is None or not token:
            return None
        self._ensure_indexes()
        query = {"guild_id": int(guild_id), "token_hash": _hash(token)}
        if kind:
            query["kind"] = kind
        try:
            doc = self._col.find_one(query)
        except Exception:  # noqa: BLE001
            return None
        if doc is None:
            return None
        # The lookup is already by hash, so this compare adds little; it is here
        # so the check stays constant-time if the storage ever changes.
        if not hmac.compare_digest(doc.get("token_hash", ""), _hash(token)):
            return None
        expires = doc.get("expires_at")
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            if expires <= datetime.datetime.now(datetime.timezone.utc):
                return None      # TTL sweeps run late; never serve a dead token
        return doc

    def revoke_all(self, guild_id: int, *, kind: Optional[str] = None,
                   user_id: Optional[int] = None) -> int:
        if self._col is None:
            return 0
        query: dict = {"guild_id": int(guild_id)}
        if kind:
            query["kind"] = kind
        if user_id:
            query["user_id"] = int(user_id)
        try:
            return self._col.delete_many(query).deleted_count
        except Exception:  # noqa: BLE001
            return 0

    def active(self, guild_id: int, *, kind: str = KIND_PUBLIC) -> Optional[dict]:
        """Whether a link of this kind exists, without revealing it."""
        if self._col is None:
            return None
        try:
            return self._col.find_one({"guild_id": int(guild_id), "kind": kind})
        except Exception:  # noqa: BLE001
            return None
