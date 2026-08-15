"""
Trial ranking runtime — clears/achievements into points, points into a rank role.

Recalculated the moment a scoring role changes, so getting a clear role hands
you the rank immediately, and swept hourly so nothing drifts if an event is
missed. Silent by design: the rank role appears, nothing is announced.
"""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands, tasks

from helpers import trial_ranks

# Role edits per guild per sweep, paced — a first run can re-rank everyone.
MAX_EDITS = 200
EDIT_PAUSE = 0.35


class TrialRanks(commands.Cog, name="trial_ranks"):
    """Keeps each member's trial rank in step with their clears."""

    def __init__(self, bot):
        self.bot = bot
        self.last_run: dict[int, dict] = {}
        self.sweep.start()

    def cog_unload(self) -> None:
        self.sweep.cancel()

    # ------------------------------------------------------------------ #
    #  Applying
    # ------------------------------------------------------------------ #
    async def apply(self, member, config: dict, *, edit: bool = True) -> dict:
        """Tidy a member's trial roles, then set the rank their score earns."""
        points = config.get("points") or {}
        ranks = config.get("ranks") or []
        trials = config.get("trials") or []
        held = {role.id for role in member.roles}

        # One role per trial: a stronger clear replaces the weaker ones, so the
        # scoring below sees the same tidy set the member will end up with.
        stale = trial_ranks.superseded(held, trials)
        out = {"score": 0, "rank": None, "granted": 0, "removed": 0, "cleared": 0}
        if stale and edit:
            roles = [member.guild.get_role(role_id) for role_id in stale]
            roles = [role for role in roles if role is not None]
            if roles:
                try:
                    await member.remove_roles(*roles, reason="Superseded by a better clear")
                    out["cleared"] = len(roles)
                    held -= stale
                except discord.HTTPException:
                    pass

        score = trial_ranks.score_for(held, points, trials=trials)
        rank = trial_ranks.rank_for(score, ranks)
        out["score"], out["rank"] = score, rank
        if not ranks or not edit:
            return out

        keep = rank["role_id"] if rank else None
        exclusive = config.get("exclusive", True)
        to_add, to_remove = [], []
        for rung in ranks:
            role = member.guild.get_role(rung["role_id"])
            if role is None:
                continue
            if role.id == keep and role.id not in held:
                to_add.append(role)
            elif role.id != keep and role.id in held and exclusive:
                to_remove.append(role)
        try:
            if to_add:
                await member.add_roles(*to_add, reason=f"Trial rank: {rank['name']} ({score} pts)")
                out["granted"] = len(to_add)
            if to_remove:
                await member.remove_roles(*to_remove, reason="Trial rank changed")
                out["removed"] = len(to_remove)
        except discord.HTTPException:
            pass
        return out

    async def run_for_guild(self, guild, *, edit: bool = True) -> dict:
        config = self.bot.trial_ranks.get(guild.id)
        summary = {"members": 0, "ranked": 0, "granted": 0, "removed": 0, "cleared": 0}
        if not config.get("enabled"):
            return {**summary, "skipped": "feature off"}
        edits = 0
        for member in guild.members:
            if member.bot:
                continue
            outcome = await self.apply(member, config, edit=edit and edits < MAX_EDITS)
            summary["cleared"] += outcome.get("cleared", 0)
            if outcome["granted"] or outcome["removed"] or outcome.get("cleared"):
                edits += 1
                await asyncio.sleep(EDIT_PAUSE)
            summary["members"] += 1
            summary["granted"] += outcome["granted"]
            summary["removed"] += outcome["removed"]
            if outcome["score"]:
                summary["ranked"] += 1
                await self.bot.loop.run_in_executor(
                    None, self.bot.trial_ranks.save_standing, guild.id, member.id,
                    member.display_name, outcome["score"],
                    (outcome["rank"] or {}).get("name"),
                )
        self.last_run[guild.id] = summary
        return summary

    # ------------------------------------------------------------------ #
    #  Triggers
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_member_update(self, before, after) -> None:
        if before.roles == after.roles or after.bot:
            return
        config = self.bot.trial_ranks.get(after.guild.id)
        if not config.get("enabled"):
            return
        changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        scoring = {int(role_id) for role_id in (config.get("points") or {})}
        scoring |= set(trial_ranks.slot_of(config.get("trials") or []))
        rank_roles = {rank["role_id"] for rank in config.get("ranks") or []}
        # Only react to scoring roles, and never to our own rank changes.
        if not (changed & scoring) or changed <= rank_roles:
            return
        try:
            outcome = await self.apply(after, config)
            await self.bot.loop.run_in_executor(
                None, self.bot.trial_ranks.save_standing, after.guild.id, after.id,
                after.display_name, outcome["score"], (outcome["rank"] or {}).get("name"),
            )
        except Exception as error:  # noqa: BLE001 - never break the gateway
            self.bot.logger.error(f"Trial rank update failed for {after.id}: {error}")

    @tasks.loop(hours=1)
    async def sweep(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                if self.bot.trial_ranks.get(guild.id).get("enabled"):
                    await self.run_for_guild(guild)
            except Exception as error:  # noqa: BLE001
                self.bot.logger.error(f"Trial rank sweep failed for {guild.id}: {error}")

    @sweep.before_loop
    async def before_sweep(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(45)


async def setup(bot):
    await bot.add_cog(TrialRanks(bot))
