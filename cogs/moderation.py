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
# How often the "working through N members" status message is refreshed.
PROGRESS_EVERY = 25
# How long a finished mass-role sweep stays registered, so member updates that
# arrive over the gateway just after the last call are still recognised as ours.
BULK_ROLE_GRACE = 10.0


class Moderation(commands.Cog, name="moderation"):
    """Server moderation commands."""

    def __init__(self, bot):
        self.bot = bot
        self.pin_fails = config_py.pin_fails
        self.pin_fails.create_index([("created_at", ASCENDING)], expireAfterSeconds=3600)
        # (guild_id, role_id) pairs currently being swept by addrole/removerole. The
        # log cog watches this so a sweep doesn't post one audit entry per member.
        if not hasattr(bot, "bulk_role_ops"):
            bot.bulk_role_ops = set()

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

    # ------------------------- mass role add / remove ---------------------------- #
    def _role_blocker(self, context: Context, role: discord.Role) -> str:
        """Return why ``role`` can't be mass-managed here, or ``None`` if it can."""
        me = context.guild.me
        if not me.guild_permissions.manage_roles:
            return lang.MOD_ROLE_BOT_NO_PERMISSION
        if role.is_default() or role.managed:
            return lang.MOD_ROLE_UNMANAGEABLE.format(role=role.name)
        if role >= me.top_role:
            return lang.MOD_ROLE_ABOVE_ME.format(role=role.name)
        if context.author != context.guild.owner and role >= context.author.top_role:
            return lang.MOD_ROLE_ABOVE_YOU.format(role=role.name)
        return None

    async def _mass_role(self, context: Context, role: discord.Role, *, add: bool) -> None:
        """Add or remove ``role`` for every member, after confirming the head count.

        Reports a summary plus a paginated list of the members that failed, both in
        the invoking channel and in the guild's log channel.
        """
        blocker = self._role_blocker(context, role)
        if blocker:
            await context.send(embed=messages.error(blocker, title="Oi!"))
            return

        if not context.guild.chunked:
            await context.guild.chunk()
        members = context.guild.members
        # For "add" we want the members missing the role; for "remove", the ones that have it.
        targets = [member for member in members if (role not in member.roles) == add]
        skipped = len(members) - len(targets)

        if not targets:
            nobody = lang.MOD_ROLE_NOBODY_ADD if add else lang.MOD_ROLE_NOBODY_REMOVE
            await context.send(embed=messages.warning(nobody.format(role=role.name)))
            return

        confirm_text = (lang.MOD_ROLE_CONFIRM_ADD if add else lang.MOD_ROLE_CONFIRM_REMOVE).format(
            role=role.name, targets=len(targets), total=len(members), skipped=skipped
        )
        confirmed = await messages.prompt_confirm(
            context,
            context.author,
            embed=messages.warning(confirm_text, title=lang.MOD_ROLE_CONFIRM_TITLE),
        )
        if not confirmed:
            await context.send(lang.MOD_ROLE_CANCELLED)
            return

        reason = lang.MOD_ROLE_REASON.format(
            action="add" if add else "remove", role=role.name, author=context.author
        )
        status = await context.send(lang.MOD_ROLE_WORKING.format(targets=len(targets), done=0))
        failures: list[str] = []
        changed = 0
        sweep = (context.guild.id, role.id)
        self.bot.bulk_role_ops.add(sweep)
        try:
            for index, member in enumerate(targets, start=1):
                try:
                    if add:
                        await member.add_roles(role, reason=reason)
                    else:
                        await member.remove_roles(role, reason=reason)
                    changed += 1
                except discord.HTTPException as exception:
                    failures.append(
                        lang.MOD_ROLE_FAILURE_LINE.format(member=member.display_name, error=str(exception)[:200])
                    )
                if index % PROGRESS_EVERY == 0:
                    await status.edit(content=lang.MOD_ROLE_WORKING.format(targets=len(targets), done=index))
        finally:
            self.bot.loop.call_later(BULK_ROLE_GRACE, self.bot.bulk_role_ops.discard, sweep)
        try:
            await status.delete()
        except discord.HTTPException:
            pass

        summary = messages.success(
            (lang.MOD_ROLE_RESULT_ADD if add else lang.MOD_ROLE_RESULT_REMOVE).format(
                count=changed, role=role.name, author=context.author.display_name
            ),
            title=lang.MOD_ROLE_ADD_TITLE if add else lang.MOD_ROLE_REMOVE_TITLE,
        )
        summary.add_field(
            name=lang.MOD_ROLE_FIELD_SKIPPED_ADD if add else lang.MOD_ROLE_FIELD_SKIPPED_REMOVE,
            value=str(skipped),
        )
        summary.add_field(name=lang.MOD_ROLE_FIELD_FAILED, value=str(len(failures)))

        failure_embeds = messages.paged_embeds(
            failures,
            title=lang.MOD_ROLE_FAILURES_TITLE,
            color=messages.ERROR,
            separator="\n",
            footer=lang.MOD_ROLE_FAILURES_FOOTER,
        )

        destinations = [context]
        channel = self._log_channel(context)
        if channel and channel.id != context.channel.id:
            destinations.append(channel)
        for destination in destinations:
            await destination.send(embed=summary)
            await messages.send_paged(destination, failure_embeds)

    @commands.hybrid_command(name="addrole", description="Give a role to every member of the server.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @checks.not_blacklisted()
    async def addrole(self, context: Context, *, role: discord.Role) -> None:
        """Give ``role`` to everyone on the server."""
        await self._mass_role(context, role, add=True)

    @commands.hybrid_command(name="removerole", description="Take a role away from every member of the server.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @checks.not_blacklisted()
    async def removerole(self, context: Context, *, role: discord.Role) -> None:
        """Take ``role`` away from everyone on the server."""
        await self._mass_role(context, role, add=False)

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
