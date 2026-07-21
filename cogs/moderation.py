"""
Moderation cog — kick / ban / nick / purge / pin / unpin, plus the escalating
"you can't pin" fail system. All user commands are hybrid (slash + prefix).
"""

import asyncio
import datetime

from pymongo import ASCENDING

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages

FOX_ID = 309719542115074049
_PIN_ALLOWED_ROLES = [852793776064692264, 1055862512689623181]
_UNPIN_ROLE = 852793776064692264


class Moderation(commands.Cog, name="moderation"):
    """Server moderation commands."""

    def __init__(self, bot):
        self.bot = bot
        self.pin_fails = config_py.pin_fails
        # Pin fails auto-expire after an hour.
        self.pin_fails.create_index([("created_at", ASCENDING)], expireAfterSeconds=3600)
        self.annoyed_messages = [
            "You really don't have permission to pin messages here.",
            "Still not allowed.",
            "Nope. Try asking someone with permissions.",
            "Persistent, aren't you? Still no.",
            "This isn't working, stop.",
            "Seriously, stop.",
            "You're starting to annoy me.",
            "Enough already.",
            "Final warning: stop it.",
            "STOP.",
        ]

    # ----------------------------- kick / ban / nick ----------------------------- #
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @checks.not_blacklisted()
    async def kick(self, context: Context, member: discord.Member, *, reason: str = "Not specified") -> None:
        """Kick ``member``, logging it and DMing them the reason."""
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        if member.guild_permissions.administrator:
            await context.send(
                embed=messages.error(
                    "You can't kick other admins like that, ask Fox, he will gladly do it.", title="Oi!"
                )
            )
            return
        try:
            embed = messages.embed(
                f"**{member}** was kicked by **{context.author.display_name}**!",
                title="User Kicked!",
                color=messages.ACCENT,
            )
            embed.add_field(name="Reason:", value=reason)
            await channel.send(embed=embed)
            try:
                await member.send(f"You were kicked by **{context.author.display_name}**!\nReason: {reason}")
            except discord.Forbidden:
                pass
            await member.kick(reason=reason)
        except discord.HTTPException:
            await channel.send(
                embed=messages.error(
                    "An error occurred while trying to kick the user. Make sure my role is above theirs.", title="Oir!"
                )
            )

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def ban(self, context: Context, member: discord.Member, *, reason: str = "Not specified") -> None:
        """Ban ``member``, logging it and DMing them the reason."""
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        try:
            if member.guild_permissions.administrator:
                await context.send(
                    embed=messages.error(
                        "Don't ban admins! Do you have any idea how hard it is to find a good admin?", title="Oi!"
                    )
                )
                return
            embed = messages.embed(
                f"**{member}** was banned by **{context.author.display_name}**!",
                title="User Banned!",
                color=messages.ACCENT,
            )
            embed.add_field(name="Reason:", value=reason)
            await channel.send(embed=embed)
            try:
                await member.send(f"You were banned by **{context.author.display_name}**!\nReason: {reason}")
            except discord.Forbidden:
                pass
            await member.ban(reason=reason)
        except discord.HTTPException:
            await context.send(
                embed=messages.error(
                    "An error occurred while trying to ban the user. Make sure my role is above theirs."
                )
            )

    @commands.hybrid_command(name="go", description="Send a member off to start the ZOOMIES.")
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def zoomies(self, context: Context, member: discord.Member) -> None:
        """DM a member the 'zoomies' prank and delete the invoking message."""
        try:
            await member.send(
                "There is an urgent task for you! Activate your SalvyFoxBumblephant and "
                "start the ZOOMIES at zoomies.dodos.fun"
            )
        except discord.Forbidden:
            pass
        if context.message:
            await context.message.delete()

    @commands.hybrid_command(name="nick", description="Change a member's nickname.")
    @commands.has_permissions(manage_nicknames=True)
    @checks.not_blacklisted()
    async def nick(self, context: Context, member: discord.Member, *, nickname: str = None) -> None:
        """Change ``member``'s nickname (omit to reset)."""
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        try:
            await member.edit(nick=nickname)
            embed = messages.embed(
                f"**{member}'s** new nickname is **{nickname}**!", title="Changed Nickname!", color=messages.ACCENT
            )
            await context.send(embed=embed)
            await channel.send(embed=embed)
        except discord.HTTPException:
            await context.send(
                embed=messages.error(
                    "An error occurred while changing the nickname. Make sure my role is above theirs.", title="Oi!"
                )
            )

    # ----------------------------------- purge ----------------------------------- #
    @commands.hybrid_command(name="purge", description="Delete a number of recent (unpinned) messages.")
    @commands.has_guild_permissions(manage_messages=True)
    @checks.not_blacklisted()
    async def purge(self, context: Context, amount: int) -> None:
        """Delete ``amount`` recent unpinned messages (max 50)."""
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        if amount < 1:
            await context.send(embed=messages.error(f"`{amount}` is not a valid number."))
            return
        if amount > 50:
            await context.send(
                "Oi, chief, if you wanna sabotage the whole server, at least suffer and delete it in small chunks"
            )
            fox = await self.bot.fetch_user(FOX_ID)
            await fox.send("Someone is trying to purge more than 50 messages at once, check on them")
            return

        purged = await context.channel.purge(limit=amount + 1, check=lambda m: not m.pinned)
        embed = messages.success(
            f"**{context.author.display_name}** has purged the chat from the filth and deleted "
            f"**{len(purged) - 1}** message(s)!",
            title="Purged!",
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
            await context.send("I won't be gentle. On your knees.")
        elif fails == 20:
            await context.send("Try to pin me once more, and I'll pin you so hard you won't even be able to squeak.")
        elif 10 <= fails <= 19:
            await context.send(self.annoyed_messages[fails - 10])
        else:
            await context.send(default_msg)

    @commands.command(name="pin", description="Pin the message you replied to.")
    async def pin(self, context: Context) -> None:
        """Pin the replied-to message, with escalating refusals on repeated failures."""
        if not any(role.id in _PIN_ALLOWED_ROLES for role in context.author.roles):
            await self._pin_fail_response(context, "no_permission", "You do not have permission to pin messages.")
            return
        if context.message is None or context.message.reference is None:
            await self._pin_fail_response(
                context, "no_reference", ":shrug: I have no idea which message to pin, please reply to a message."
            )
            return
        try:
            referenced = await context.channel.fetch_message(context.message.reference.message_id)
            await referenced.pin()
        except discord.HTTPException:
            await self._pin_fail_response(context, "exception", "Something went wrong, I couldn't pin that.")

    @commands.command(name="unpin", description="Unpin the message you replied to.")
    async def unpin(self, context: Context) -> None:
        """Unpin the replied-to message (requires the pin role)."""
        if discord.utils.get(context.author.roles, id=_UNPIN_ROLE) is None:
            await context.send("You do not have permission to unpin messages.")
            return
        if context.message is None or context.message.reference is None:
            await context.send(":shrug: I have no idea which message to unpin, please reply to a message.")
            return
        referenced = await context.channel.fetch_message(context.message.reference.message_id)
        await referenced.unpin()
        await context.send(f"Message unpinned by {context.author.mention}.")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
