"""
Who may open the control panel, and how much of it they see.

Separate from ``helpers/visibility.py``: that decides who may *run commands in
Discord*, this decides who may *open a web page*. Both are per-guild, but the
panel exposes server configuration, so it gets its own explicit grant table
rather than inheriting command rules.

Access is a **scope**, ordered from least to most:

    none   — no access at all (the page 404s/403s)
    stats  — the activity dashboard only
    config — stats, plus server settings and event rules
    full   — everything for that server: cogs, features, params, command levels
    owner  — bot owners; every server plus the bot-wide tooling

A member's scope is the highest of:

* ``owner`` if they are a bot owner,
* ``full`` if they hold Discord's Manage Server permission (or own the guild, or
  are on the legacy per-guild admin allowlist),
* whatever grants match their roles or their user id.

Grants are stored per guild as ``{guild_id, kind: "role"|"user", target_id,
scope}``, so the owner can hand a whole role a scope, or one person an exception.
Someone who is not a member of the guild has no scope there at all, whatever the
grants say.
"""

from __future__ import annotations

from typing import Optional

SCOPE_NONE = "none"
SCOPE_STATS = "stats"
SCOPE_CONFIG = "config"
SCOPE_FULL = "full"
SCOPE_OWNER = "owner"

# Grantable from the panel (``owner`` is implicit and never stored).
GRANTABLE_SCOPES = (SCOPE_STATS, SCOPE_CONFIG, SCOPE_FULL)
_ORDER = {SCOPE_NONE: 0, SCOPE_STATS: 1, SCOPE_CONFIG: 2, SCOPE_FULL: 3, SCOPE_OWNER: 4}

SCOPE_LABELS = {
    SCOPE_STATS: "Stats only",
    SCOPE_CONFIG: "Settings & events",
    SCOPE_FULL: "Full server control",
}


def at_least(scope: str, minimum: str) -> bool:
    """Whether ``scope`` meets or exceeds ``minimum``."""
    return _ORDER.get(scope, 0) >= _ORDER.get(minimum, 0)


def highest(*scopes: str) -> str:
    return max(scopes, key=lambda s: _ORDER.get(s, 0), default=SCOPE_NONE)


class PanelAccessManager:
    """Per-guild panel grants, cached. ``bot.panel_access``."""

    def __init__(self, collection, *, visibility) -> None:
        self._col = collection
        self._visibility = visibility
        self._cache: dict[int, list[dict]] = {}

    # ------------------------------------------------------------------ #
    #  Grants
    # ------------------------------------------------------------------ #
    def grants(self, guild_id: int) -> list[dict]:
        if guild_id not in self._cache:
            self._cache[guild_id] = [
                {
                    "kind": doc.get("kind"),
                    "target_id": int(doc.get("target_id", 0)),
                    "scope": doc.get("scope"),
                }
                for doc in self._col.find({"guild_id": guild_id})
                if doc.get("scope") in GRANTABLE_SCOPES and doc.get("kind") in ("role", "user")
            ]
        return self._cache[guild_id]

    def set_grant(self, guild_id: int, kind: str, target_id: int, scope: str) -> None:
        if kind not in ("role", "user"):
            raise ValueError(f"Unknown grant kind: {kind!r}")
        if scope not in GRANTABLE_SCOPES:
            raise ValueError(f"Unknown scope: {scope!r}")
        self._col.update_one(
            {"guild_id": guild_id, "kind": kind, "target_id": int(target_id)},
            {"$set": {"scope": scope}},
            upsert=True,
        )
        self._cache.pop(guild_id, None)

    def remove_grant(self, guild_id: int, kind: str, target_id: int) -> None:
        self._col.delete_one({"guild_id": guild_id, "kind": kind, "target_id": int(target_id)})
        self._cache.pop(guild_id, None)

    def invalidate(self, guild_id: Optional[int] = None) -> None:
        if guild_id is None:
            self._cache.clear()
        else:
            self._cache.pop(guild_id, None)

    # ------------------------------------------------------------------ #
    #  Resolution
    # ------------------------------------------------------------------ #
    def scope_for_member(self, guild_id: int, member) -> str:
        """The scope a **member object** has in their guild.

        ``member`` being ``None`` means they aren't in the guild, which is an
        immediate ``none`` — grants never apply to non-members.
        """
        if member is None:
            return SCOPE_NONE
        if self._visibility.is_owner(member.id):
            return SCOPE_OWNER

        scopes = [SCOPE_NONE]
        permissions = getattr(member, "guild_permissions", None)
        is_guild_owner = getattr(member.guild, "owner_id", None) == member.id
        if is_guild_owner or (permissions and permissions.manage_guild):
            scopes.append(SCOPE_FULL)
        # Legacy per-guild admin allowlist used by the command checks.
        if member.id in self._visibility.guild_admin_ids(guild_id):
            scopes.append(SCOPE_FULL)

        role_ids = {role.id for role in getattr(member, "roles", [])}
        for grant in self.grants(guild_id):
            if grant["kind"] == "user" and grant["target_id"] == member.id:
                scopes.append(grant["scope"])
            elif grant["kind"] == "role" and grant["target_id"] in role_ids:
                scopes.append(grant["scope"])
        return highest(*scopes)
