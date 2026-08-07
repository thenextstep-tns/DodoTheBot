"""
Seasonal cog — thread-based seasonal events: ``love`` (Valentine messages) and
``vote`` (Dodo of the Year nominations), plus an owner ``resetvote``. User-facing
text lives in ``lang``.
"""

import asyncio
import time

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages


class Seasonal(commands.Cog, name="seasonal"):
    """Valentine and Dodo-of-the-Year events."""

    def __init__(self, bot):
        self.bot = bot

    async def _ask(self, thread: discord.Thread, author, prompt: str, timeout: float) -> str | None:
        """Ask a question in ``thread`` and return the author's reply (or None on timeout)."""
        await thread.send(prompt)

        def check(message):
            return message.author.id == author.id and message.channel.id == thread.id

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=timeout)
            return reply.content
        except asyncio.TimeoutError:
            return None

    async def _close_thread(self, thread: discord.Thread, farewell: str = lang.SEASONAL_THREAD_GONE) -> None:
        """Send a farewell and delete the thread after a short delay."""
        await thread.send(farewell)
        await asyncio.sleep(10)
        await thread.delete()

    async def _open_thread(self, context: Context, name: str) -> discord.Thread:
        """Delete the invoking message (if any) and open a private thread."""
        if context.message:
            await context.message.delete()
        return await context.channel.create_thread(name=name, type=discord.ChannelType.private_thread)

    @commands.hybrid_command(
        name="love", aliases=["valentine", "smooch"], description="Send a valentine to someone you care for!"
    )
    async def love(self, context: Context, member: discord.Member = None) -> None:
        """Collect a valentine in a private thread and post it to the Valentine channel."""
        await context.defer(ephemeral=True)
        valentine_channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "VALENTINE_CHANNEL"))
        thread = await self._open_thread(context, f"Sending a love letter to a very special someone at {time.time()}")
        await thread.send(lang.LOVE_INTRO.format(mention=context.author.mention, channel=self.bot.guild_setting(context.guild, "VALENTINE_CHANNEL")))

        if member:
            who = member.name
        else:
            who = await self._ask(thread, context.author, lang.LOVE_Q_WHO, 30)
            if who is None:
                await self._close_thread(thread)
                return

        sender = await self._ask(thread, context.author, lang.LOVE_Q_FROM, 30)
        if sender is None:
            await self._close_thread(thread)
            return
        message = await self._ask(thread, context.author, lang.LOVE_Q_MESSAGE, 120)
        if message is None:
            await self._close_thread(thread)
            return

        await thread.send(lang.LOVE_CONFIRM.format(sender=sender, who=who))
        await thread.send(message)

        embed = messages.success(lang.LOVE_EMBED_DESCRIPTION.format(who=who, sender=sender), title=message)
        if member:
            await valentine_channel.send(lang.LOVE_NOTIFY.format(member_id=member.id))
        await valentine_channel.send(embed=embed)
        await valentine_channel.send(lang.LOVE_HEARTS)

        await self.bot.get_channel(self.bot.guild_setting(context.guild, "LOG_CHANNEL")).send(
            lang.LOVE_LOG.format(author=context.author, sender=sender, who=who, message=message)
        )
        await self._close_thread(thread)

    @commands.hybrid_command(name="vote", aliases=["doty"], description="Vote for the Dodo of the Year!")
    async def vote(self, context: Context) -> None:
        """Collect three DOTY nominations in a private thread and record them."""
        if config_py.votes.find_one({"user_id": str(context.author.id)}):
            await context.send(lang.VOTE_ALREADY)
            return

        await context.defer(ephemeral=True)
        doty_channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "DOTY_CHANNEL"))
        thread = await self._open_thread(context, f"Vote at {time.time()}")
        await thread.send(lang.VOTE_INTRO.format(mention=context.author.mention, channel=self.bot.guild_setting(context.guild, "DOTY_CHANNEL")))

        role_model = await self._ask(thread, context.author, lang.VOTE_Q1, 180)
        progress = role_model and await self._ask(thread, context.author, lang.VOTE_Q2, 180)
        community = progress and await self._ask(thread, context.author, lang.VOTE_Q3, 180)
        if not community:
            await self._close_thread(thread)
            return

        embed = messages.success(
            lang.VOTE_EMBED_DESCRIPTION.format(role_model=role_model, progress=progress, community=community),
            title=lang.VOTE_EMBED_TITLE.format(author=context.author),
        )
        await doty_channel.send(embed=embed)
        await doty_channel.send(lang.LOVE_HEARTS)
        config_py.votes.insert_one(
            {
                "user_id": str(context.author.id),
                "role_model": role_model,
                "progress_of_the_year": progress,
                "community_builder": community,
            }
        )
        await self._close_thread(thread, lang.VOTE_CLOSE)

    @commands.hybrid_command(name="resetvote", aliases=["resetdoty"], description="Reset a user's vote (owner only).")
    @checks.is_owner()
    async def resetvote(self, context: Context, user: discord.User) -> None:
        """Clear ``user``'s recorded DOTY vote so they can vote again."""
        result = config_py.votes.delete_one({"user_id": str(user.id)})
        if result.deleted_count:
            await context.send(lang.RESETVOTE_DONE.format(mention=user.mention))
        else:
            await context.send(lang.RESETVOTE_NONE)


async def setup(bot):
    await bot.add_cog(Seasonal(bot))
