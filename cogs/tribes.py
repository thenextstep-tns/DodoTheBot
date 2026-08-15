"""
Tribe sweep — applies the role rules built on the panel's Tribes page.

Runs hourly per guild, and on demand from the panel. One sweep:

1. builds the guild's :class:`~helpers.tribes.MemberFacts` once (message and
   thread counts per member per channel, join dates, roles),
2. evaluates every member against every enabled tribe in memory,
3. grants the tribe's roles to members who match, and removes them from members
   who no longer do — but only for tribes that opted into removal,
4. stores the resulting membership (with ranks) for the stats page.

Everything expensive happens once per guild rather than per member: rankings
only exist relative to everybody else, and role edits are rate-limited so a
first run on a large server can't hammer the API.
"""

from __future__ import annotations

import asyncio
import datetime
import time

import discord
from discord.ext import commands, tasks

import config_py
from helpers import tribes as tribe_rules

# Role edits per guild per sweep. A first run can match hundreds of members;
# this keeps that spread over several sweeps instead of a burst of API calls.
MAX_ROLE_EDITS = 200
EDIT_PAUSE = 0.35
# Archived threads are fetched per channel for the "threads created" metric.
MAX_ARCHIVED_THREADS = 300


class Tribes(commands.Cog, name="tribes"):
    """Evaluates tribe rules and keeps their roles up to date."""

    def __init__(self, bot):
        self.bot = bot
        self.last_run: dict[int, dict] = {}
        self._running: set[int] = set()
        self.sweep.start()

    def cog_unload(self) -> None:
        self.sweep.cancel()

    # ------------------------------------------------------------------ #
    #  Facts
    # ------------------------------------------------------------------ #
    def _message_counts(self, channel_ids: list[int], bot_ids: list[int]) -> dict:
        """``{author: {channel: count}}`` for this guild's channels, humans only."""
        match: dict = {"channel": {"$in": channel_ids}}
        if bot_ids:
            match["author"] = {"$nin": bot_ids}
        pipeline = [
            {"$match": match},
            {"$group": {"_id": {"a": "$author", "c": "$channel"}, "n": {"$sum": 1}}},
        ]
        out: dict[int, dict[int, int]] = {}
        for row in config_py.messages.aggregate(pipeline, allowDiskUse=True):
            author, channel = row["_id"].get("a"), row["_id"].get("c")
            if isinstance(author, int) and isinstance(channel, int):
                out.setdefault(author, {})[channel] = row["n"]
        return out

    async def _thread_counts(self, guild) -> dict:
        """``{owner: {parent_channel: count}}`` for threads in this guild.

        Active threads come from the cache; archived ones are fetched per parent
        (capped), because thread ownership isn't in the message archive.
        """
        counts: dict[int, dict[int, int]] = {}

        def add(thread):
            owner_id = getattr(thread, "owner_id", None)
            parent_id = getattr(thread, "parent_id", None)
            if owner_id and parent_id:
                counts.setdefault(owner_id, {}).setdefault(parent_id, 0)
                counts[owner_id][parent_id] += 1

        for thread in getattr(guild, "threads", []):
            add(thread)
        for channel in guild.channels:
            if not isinstance(channel, (discord.ForumChannel, discord.TextChannel)):
                continue
            try:
                fetched = 0
                async for thread in channel.archived_threads(limit=MAX_ARCHIVED_THREADS):
                    add(thread)
                    fetched += 1
                    if fetched >= MAX_ARCHIVED_THREADS:
                        break
            except (discord.HTTPException, AttributeError):
                continue
        return counts

    async def build_facts(self, guild) -> tribe_rules.MemberFacts:
        channel_ids = [c.id for c in guild.channels] + [t.id for t in guild.threads]
        bot_ids = [m.id for m in guild.members if m.bot]
        messages = await self.bot.loop.run_in_executor(
            None, self._message_counts, channel_ids, bot_ids
        )
        threads = await self._thread_counts(guild)
        joined, created, roles = {}, {}, {}
        for member in guild.members:
            if member.bot:
                continue
            joined[member.id] = member.joined_at
            created[member.id] = member.created_at
            roles[member.id] = {role.id for role in member.roles}
        return tribe_rules.MemberFacts(messages, threads, joined, created, roles)

    # ------------------------------------------------------------------ #
    #  Sweep
    # ------------------------------------------------------------------ #
    async def run_for_guild(self, guild, *, apply_roles: bool = True) -> dict:
        """Evaluate every tribe for one guild. Returns a summary for the panel."""
        if guild.id in self._running:
            return {"skipped": "already running"}
        self._running.add(guild.id)
        started = time.monotonic()
        summary = {"tribes": 0, "matched": 0, "granted": 0, "removed": 0, "errors": 0}
        try:
            definitions = self.bot.tribes.enabled_for(guild.id)
            if not definitions:
                return {**summary, "at": datetime.datetime.now(datetime.timezone.utc)}
            facts = await self.build_facts(guild)
            edits = 0

            for tribe in definitions:
                condition = tribe.get("condition") or {}
                if not condition.get("children") and condition.get("type") in tribe_rules.GROUP_TYPES:
                    continue  # an empty rule matches nobody rather than everybody
                summary["tribes"] += 1
                roles = [guild.get_role(rid) for rid in tribe.get("role_ids") or []]
                roles = [r for r in roles if r is not None]
                rows = []

                for member in guild.members:
                    if member.bot:
                        continue
                    matched = tribe_rules.evaluate(condition, member.id, facts)
                    if matched:
                        rows.append({
                            "user_id": member.id,
                            "rank": tribe_rules.rank_of(condition, member.id, facts) or 0,
                            "name": member.display_name,
                        })
                    if not apply_roles or not roles or edits >= MAX_ROLE_EDITS:
                        continue
                    held = {r.id for r in member.roles}
                    try:
                        if matched:
                            missing = [r for r in roles if r.id not in held]
                            if missing:
                                await member.add_roles(*missing, reason=f"Tribe: {tribe.get('name')}")
                                summary["granted"] += len(missing)
                                edits += 1
                                await asyncio.sleep(EDIT_PAUSE)
                        elif tribe.get("remove_when_unmatched"):
                            extra = [r for r in roles if r.id in held]
                            if extra:
                                await member.remove_roles(*extra, reason=f"Tribe: {tribe.get('name')}")
                                summary["removed"] += len(extra)
                                edits += 1
                                await asyncio.sleep(EDIT_PAUSE)
                    except discord.HTTPException:
                        summary["errors"] += 1

                # Rank within the tribe: by the rule's own metric where it has
                # one, otherwise by messages sent, so a leaderboard always exists.
                fallback = facts.ranking("messages", [])
                for row in rows:
                    if not row["rank"]:
                        row["rank"] = fallback.get(row["user_id"], 0)
                rows.sort(key=lambda r: (r["rank"] == 0, r["rank"]))
                for position, row in enumerate(rows, start=1):
                    row["position"] = position
                summary["matched"] += len(rows)
                await self.bot.loop.run_in_executor(
                    None, self.bot.tribes.save_membership, guild.id, str(tribe["_id"]), rows
                )
            summary["seconds"] = round(time.monotonic() - started, 1)
            summary["at"] = datetime.datetime.now(datetime.timezone.utc)
            self.last_run[guild.id] = summary
            return summary
        finally:
            self._running.discard(guild.id)

    @tasks.loop(hours=1)
    async def sweep(self) -> None:
        for guild in list(self.bot.guilds):
            if not self.bot.visibility.feature_active(guild.id, "tribes", "tribes"):
                continue
            try:
                await self.run_for_guild(guild)
            except Exception as error:  # noqa: BLE001 - one guild must not stop the rest
                self.bot.logger.error(f"Tribe sweep failed for {guild.id}: {error}")

    @sweep.before_loop
    async def before_sweep(self) -> None:
        await self.bot.wait_until_ready()
        # Let the member cache settle before the first pass.
        await asyncio.sleep(30)


async def setup(bot):
    await bot.add_cog(Tribes(bot))
