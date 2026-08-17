"""
Importing the legacy ``dodo_dnd`` database.

The old cog's data is small and shallow, but it is somebody's game, so it does
not get thrown away. What it *does* get is honesty about what survives: see
``docs/dnd/13-MIGRATION.md`` §7 for the full list of what is dropped and why.

The two decisions worth restating here, because they look like data loss and are
not:

**The old stat block is discarded.** Every character ever created got the same
``STR 15, DEX 14, CON 13, INT 12, WIS 10, CHA 8``, HP 10, AC 10 — identical
whether they were a wizard or a barbarian. Importing that would be importing
noise as signal. A real sheet is generated from the character's class and race
instead, and the report says so.

**Prose history is not parsed into memory.** ``session.history`` and
``character.history`` are LLM-written bullet strings with no reliable structure.
Inventing episodic memories from them would fabricate a past that never happened.
They are imported as *lore* — which is what they actually are.

The importer is **interactive and owner-run**, never a startup hook, and it never
modifies or deletes the source database. ``dodo_dnd`` is the rollback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any

import config_py
from helpers.dnd import rules
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.world import event as event_kinds
from helpers.dnd.world.campaign import STATUS_ACTIVE, STATUS_ARCHIVED, Campaign
from helpers.dnd.world.entity import KIND_PC, TIER_DORMANT, Entity, Identity

# The legacy database, on the shared client. Read-only throughout this module.
_legacy_db = config_py.client["dodo_dnd"]
legacy_sessions = _legacy_db["sessions"]
legacy_characters = _legacy_db["characters"]
legacy_actions = _legacy_db["actions"]

# How much of a prose history blob becomes a seed memory's gist. Long enough to
# be recognisable, short enough not to pretend it is structured recall.
GIST_CHARS = 200


@dataclass
class Report:
    """What a run did, or would do. Printed before anything is written."""

    dry_run: bool = True
    guild_id: int = 0
    campaigns: int = 0
    characters: int = 0
    actions: int = 0
    skipped: int = 0
    defaulted_pronouns: list[str] = field(default_factory=list)
    regenerated_stats: list[str] = field(default_factory=list)
    unknown_guild: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        mode = "DRY RUN — nothing was written" if self.dry_run else "IMPORTED"
        out = [
            f"**{mode}**",
            f"Campaigns: {self.campaigns} · Characters: {self.characters} · Events: {self.actions}",
        ]
        if self.skipped:
            out.append(f"Already imported, skipped: {self.skipped}")
        if self.regenerated_stats:
            out.append(
                f"Stats regenerated from class/race for {len(self.regenerated_stats)} character(s) — "
                "the old block was identical for everyone and carried no information."
            )
        if self.defaulted_pronouns:
            names = ", ".join(self.defaulted_pronouns[:10])
            out.append(
                f"Pronouns defaulted to they/them for {len(self.defaulted_pronouns)}: {names}"
                + ("…" if len(self.defaulted_pronouns) > 10 else "")
                + " — players should set their own."
            )
        if self.unknown_guild:
            out.append(
                f"{len(self.unknown_guild)} session(s) have no resolvable server and were left alone: "
                + ", ".join(self.unknown_guild[:5])
            )
        out.extend(self.notes)
        return out


def _seed_from(value: Any) -> int:
    """A stable seed per legacy session, so a dry run and the real run agree."""
    return abs(hash(str(value))) & 0xFFFFFFFF


def _character_concept(doc: dict) -> dict:
    return {
        "name": str(doc.get("name", "Unnamed")),
        "role": str(doc.get("class", "")),
        "species": str(doc.get("race", "")),
    }


def plan(guild_id: int, *, ruleset_key: str = "srd5e", limit: int = 0) -> Report:
    """What an import into ``guild_id`` would do. Writes nothing."""
    return _run(guild_id, ruleset_key=ruleset_key, dry_run=True, limit=limit)


def execute(guild_id: int, *, ruleset_key: str = "srd5e", limit: int = 0) -> Report:
    """Import legacy sessions into ``guild_id``. Idempotent by ``legacy_id``."""
    return _run(guild_id, ruleset_key=ruleset_key, dry_run=False, limit=limit)


def _run(guild_id: int, *, ruleset_key: str, dry_run: bool, limit: int) -> Report:
    report = Report(dry_run=dry_run, guild_id=guild_id)
    ruleset = rules.get(ruleset_key)
    repo = campaigns_for(guild_id)

    sessions = list(legacy_sessions.find({}))
    if limit:
        sessions = sessions[:limit]

    for session in sessions:
        legacy_id = session.get("session_id")
        if legacy_id is None:
            report.skipped += 1
            continue

        # Idempotency: a second run must not duplicate a campaign.
        if repo.by_legacy_id(legacy_id) is not None:
            report.skipped += 1
            continue

        title = str(session.get("title") or f"Imported session {legacy_id}")
        status = STATUS_ARCHIVED if session.get("status") == "completed" else STATUS_ACTIVE
        characters = list(legacy_characters.find({"session_id": legacy_id}))
        actions = list(legacy_actions.find({"session_id": legacy_id}))

        report.campaigns += 1
        report.characters += len(characters)
        report.actions += len(actions)

        if dry_run:
            for doc in characters:
                report.defaulted_pronouns.append(str(doc.get("name", "?")))
                report.regenerated_stats.append(str(doc.get("name", "?")))
            continue

        campaign = repo.create(
            Campaign(
                guild_id=guild_id,
                name=title,
                ruleset=ruleset.key,
                status=status,
                # The old schema records no creator, so GMs are assigned after
                # the fact by the owner running this (13-MIGRATION.md §3).
                gm_ids=[],
                player_ids=[int(p) for p in (session.get("players") or [])],
                seed=_seed_from(legacy_id),
                legacy_id=legacy_id,
            )
        )
        store = campaign_store(guild_id, campaign.id)
        rng = Random(campaign.seed)

        store.events.append(
            event_kinds.CAMPAIGN_CREATED,
            payload={"name": title, "ruleset": ruleset.key, "imported_from": str(legacy_id)},
        )

        # The premise is the only real worldbuilding the old schema holds, so it
        # becomes a retrievable fact rather than a field nobody reads again.
        premise = str(session.get("description") or "").strip()
        if premise:
            store.events.append(
                event_kinds.LEGACY_ACTION,
                payload={"kind": "premise", "text": premise, "legacy_id": f"{legacy_id}:premise"},
            )

        history = str(session.get("history") or "").strip()
        if history:
            store.events.append(
                event_kinds.LEGACY_ACTION,
                payload={"kind": "previous_chapters", "text": history,
                         "legacy_id": f"{legacy_id}:history"},
            )

        for doc in characters:
            concept = _character_concept(doc)
            entity = store.entities.create(
                Entity(
                    guild_id=guild_id,
                    campaign_id=campaign.id,
                    kind=KIND_PC,
                    tier=TIER_DORMANT,
                    owner_id=int(doc["player_id"]) if doc.get("player_id") else None,
                    identity=Identity(
                        name=concept["name"],
                        pronouns="they/them",        # never inferred from a name
                        species=concept["species"],
                        role=concept["role"],
                    ),
                    # Regenerated, not copied — see the module docstring.
                    stats=ruleset.blank_sheet(concept, rng),
                    inventory=[{"item": str(i), "qty": 1} for i in (doc.get("equipment") or [])],
                    importance=1.0,
                    legacy_id=doc.get("_id"),
                )
            )
            report.defaulted_pronouns.append(entity.name)
            report.regenerated_stats.append(entity.name)

            char_history = str(doc.get("history") or "").strip()
            if char_history:
                store.events.append(
                    event_kinds.LEGACY_ACTION,
                    actor_id=entity.id,
                    payload={"kind": "character_history", "text": char_history[:GIST_CHARS],
                             "full_length": len(char_history),
                             "legacy_id": f"{doc.get('_id')}:history"},
                )

        for doc in actions:
            store.events.append(
                event_kinds.LEGACY_ACTION,
                payload={
                    "kind": "action",
                    "text": str(doc.get("action_description", "")),
                    "narrative": str(doc.get("gm_narrative", "")),
                    "summary": str(doc.get("summary", "")),
                    "user_id": doc.get("player_id"),
                    "legacy_id": str(doc.get("_id")),
                },
            )

    if not sessions:
        report.notes.append("No legacy sessions found — nothing to import.")
    elif dry_run:
        report.notes.append(
            "The old `dodo_dnd` database is never modified; it stays as the rollback."
        )
        report.notes.append(
            "Campaigns are imported with **no GM** — assign one with `/campaign` afterwards."
        )
    return report


def legacy_counts() -> dict:
    """A quick census of the source database, for the report header."""
    return {
        "sessions": legacy_sessions.count_documents({}),
        "characters": legacy_characters.count_documents({}),
        "actions": legacy_actions.count_documents({}),
    }
