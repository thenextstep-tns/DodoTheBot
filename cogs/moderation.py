"""
Moderation cog — kick / ban / nick / purge / pin / unpin, plus the escalating
"you can't pin" fail system. Commands are hybrid (slash + prefix). User-facing
text lives in ``lang``.
"""

import asyncio
import datetime

from pymongo import ASCENDING

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

FOX_ID = 309719542115074049


class Moderation(commands.Cog, name="moderation"):
    """Server moderation commands."""

    def __init__(self, bot):
        self.bot = bot
        self.pin_fails = config_py.pin_fails
        self.pin_fails.create_index([("created_at", ASCENDING)], expireAfterSeconds=3600)

    def _log_channel(self, context: Context):
        """This guild's moderation log channel (per-guild, falls back to default)."""
        guild_id = context.guild.id if context.guild else None
        return self.bot.get_channel(self.bot.guild_config.get(guild_id, "LOG_CHANNEL"))

    # ----------------------------- kick / ban / nick ----------------------------- #
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @checks.not_blacklisted()
    async def kick(self, context: Context, member: discord.Member, *, reason: str = "Not specified") -> None:
        """Kick ``member``, logging it and DMing them the reason."""
        channel = self._log_channel(context)
        if member.guild_permissions.administrator:
            await context.send(embed=messages.error(lang.MOD_KICK_ADMIN, title="Oi!"))
            return
        try:
            embed = messages.embed(
                lang.MOD_KICK_DESCRIPTION.format(member=member, author=context.author.display_name),
                title=lang.MOD_KICK_TITLE,
                color=messages.ACCENT,
            )
            embed.add_field(name="Reason:", value=reason)
            await channel.send(embed=embed)
            try:
                await member.send(lang.MOD_KICK_DM.format(author=context.author.display_name, reason=reason))
            except discord.Forbidden:
                pass
            await member.kick(reason=reason)
        except discord.HTTPException:
            await channel.send(embed=messages.error(lang.MOD_KICK_ERROR, title="Oir!"))

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def ban(self, context: Context, member: discord.Member, *, reason: str = "Not specified") -> None:
        """Ban ``member``, logging it and DMing them the reason."""
        channel = self._log_channel(context)
        try:
            if member.guild_permissions.administrator:
                await context.send(embed=messages.error(lang.MOD_BAN_ADMIN, title="Oi!"))
                return
            embed = messages.embed(
                lang.MOD_BAN_DESCRIPTION.format(member=member, author=context.author.display_name),
                title=lang.MOD_BAN_TITLE,
                color=messages.ACCENT,
            )
            embed.add_field(name="Reason:", value=reason)
            await channel.send(embed=embed)
            try:
                await member.send(lang.MOD_BAN_DM.format(author=context.author.display_name, reason=reason))
            except discord.Forbidden:
                pass
            await member.ban(reason=reason)
        except discord.HTTPException:
            await context.send(embed=messages.error(lang.MOD_BAN_ERROR))

    @commands.hybrid_command(name="go", description="Send a member off to start the ZOOMIES.")
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def zoomies(self, context: Context, member: discord.Member) -> None:
        """DM a member the 'zoomies' prank and delete the invoking message."""
        try:
            await member.send(lang.MOD_ZOOMIES_DM)
        except discord.Forbidden:
            pass
        if context.message:
            await context.message.delete()

    @commands.hybrid_command(name="nick", description="Change a member's nickname.")
    @commands.has_permissions(manage_nicknames=True)
    @checks.not_blacklisted()
    async def nick(self, context: Context, member: discord.Member, *, nickname: str = None) -> None:
        """Change ``member``'s nickname (omit to reset)."""
        channel = self._log_channel(context)
        try:
            await member.edit(nick=nickname)
            embed = messages.embed(
                lang.MOD_NICK_DESCRIPTION.format(member=member, nickname=nickname),
                title=lang.MOD_NICK_TITLE,
                color=messages.ACCENT,
            )
            await context.send(embed=embed)
            await channel.send(embed=embed)
        except discord.HTTPException:
            await context.send(embed=messages.error(lang.MOD_NICK_ERROR, title="Oi!"))

    # ----------------------------------- purge ----------------------------------- #
    @commands.hybrid_command(name="purge", description="Delete a number of recent (unpinned) messages.")
    @commands.has_guild_permissions(manage_messages=True)
    @checks.not_blacklisted()
    async def purge(self, context: Context, amount: int) -> None:
        """Delete ``amount`` recent unpinned messages (max 50)."""
        channel = self._log_channel(context)
        guild_id = context.guild.id if context.guild else None
        purge_max = self.bot.params.get(guild_id, "purge_max")
        if amount < 1:
            await context.send(embed=messages.error(lang.MOD_PURGE_INVALID.format(amount=amount)))
            return
        if amount > purge_max:
            await context.send(lang.MOD_PURGE_TOO_MANY)
            fox = await self.bot.fetch_user(FOX_ID)
            await fox.send(lang.MOD_PURGE_ALERT_FOX)
            return

        purged = await context.channel.purge(limit=amount + 1, check=lambda m: not m.pinned)
        embed = messages.success(
            lang.MOD_PURGE_DESCRIPTION.format(author=context.author.display_name, count=len(purged) - 1),
            title=lang.MOD_PURGE_TITLE,
        )
        confirmation = await context.send(embed=embed)
        await asyncio.sleep(3)
        await confirmation.delete()
        await channel.send(embed=embed)

    # ------------------------------- pin / unpin --------------------------------- #
    async def _record_fail(self, user_id: int, reason: str) -> int:
        """Log a failed pin attempt and return the current (non-expired) fail count."""
        self.pin_fails.insert_one({"user_id": user_id, "reason": reason, "created_at": datetime.datetime.utcnow()})
        return self.pin_fails.count_documents({})

    async def _pin_fail_response(self, context: Context, reason: str, default_msg: str) -> None:
        """Send the escalating fail message appropriate to the current fail count."""
        fails = await self._record_fail(context.author.id, reason)
        if fails >= 21:
            await context.send(lang.MOD_PIN_RAGE)
        elif fails == 20:
            await context.send(lang.MOD_PIN_THREAT)
        elif 10 <= fails <= 19:
            await context.send(lang.MOD_PIN_ANNOYED[fails - 10])
        else:
            await context.send(default_msg)

    @commands.command(name="pin", description="Pin the message you replied to.")
    async def pin(self, context: Context) -> None:
        """Pin the replied-to message, with escalating refusals on repeated failures."""
        guild_id = context.guild.id if context.guild else None
        pin_roles = self.bot.params.get(guild_id, "pin_allowed_roles")
        if not any(role.id in pin_roles for role in context.author.roles):
            await self._pin_fail_response(context, "no_permission", lang.MOD_PIN_NO_PERMISSION)
            return
        if context.message is None or context.message.reference is None:
            await self._pin_fail_response(context, "no_reference", lang.MOD_PIN_NO_REFERENCE)
            return
        try:
            referenced = await context.channel.fetch_message(context.message.reference.message_id)
            await referenced.pin()
        except discord.HTTPException:
            await self._pin_fail_response(context, "exception", lang.MOD_PIN_FAILED)

    @commands.command(name="unpin", description="Unpin the message you replied to.")
    async def unpin(self, context: Context) -> None:
        """Unpin the replied-to message (requires the pin role)."""
        guild_id = context.guild.id if context.guild else None
        unpin_role = self.bot.params.get(guild_id, "unpin_role")
        if unpin_role and discord.utils.get(context.author.roles, id=unpin_role) is None:
            await context.send(lang.MOD_UNPIN_NO_PERMISSION)
            return
        if context.message is None or context.message.reference is None:
            await context.send(lang.MOD_UNPIN_NO_REFERENCE)
            return
        referenced = await context.channel.fetch_message(context.message.reference.message_id)
        await referenced.unpin()
        await context.send(lang.MOD_UNPIN_DONE.format(mention=context.author.mention))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
