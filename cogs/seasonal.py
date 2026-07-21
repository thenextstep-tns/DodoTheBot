"""
Seasonal cog — thread-based seasonal events: ``love`` (Valentine messages) and
``vote`` (Dodo of the Year nominations), plus an owner ``resetvote``.

Each command opens a private thread and asks the user a short series of
questions, then posts the result to the relevant public channel.
"""

import asyncio
import time

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages

_THREAD_GONE = "Just like my family, this thread will now disappear. Thank you! :heart: "


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

    async def _close_thread(self, thread: discord.Thread, farewell: str = _THREAD_GONE) -> None:
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
        valentine_channel = self.bot.get_channel(config_py.VALENTINE_CHANNEL)
        thread = await self._open_thread(context, f"Sending a love letter to a very special someone at {time.time()}")
        await thread.send(
            f"Hey there, {context.author.mention}! I created this private thread for you to send a message. "
            f"I will memorise it and send it to <#{config_py.VALENTINE_CHANNEL}>, which will be available on "
            "Valentine's day! This thread is private. I'll ask a few questions, then save it all and delete the thread :heart: "
        )

        if member:
            who = member.name
        else:
            who = await self._ask(thread, context.author, "QUESTION 1: **Who is your message for?**", 30)
            if who is None:
                await self._close_thread(thread)
                return

        sender = await self._ask(
            thread, context.author, "Now I need to know **who is the message FROM?** You can stay anonymous if you want to!", 30
        )
        if sender is None:
            await self._close_thread(thread)
            return
        message = await self._ask(thread, context.author, "Nice! **Now is the time to write and send your message!**", 120)
        if message is None:
            await self._close_thread(thread)
            return

        await thread.send(f"Perfection! I will send a message from {sender} to {who}! The message will be:")
        await thread.send(message)

        embed = messages.success(f"To: {who}! From: {sender}", title=message)
        if member:
            await valentine_channel.send(f"<@{member.id}>! You got a valentine! :heart:")
        await valentine_channel.send(embed=embed)
        await valentine_channel.send("= :heart: =")

        await self.bot.get_channel(config_py.LOG_CHANNEL).send(
            f"New valentine added! :smirk: {context.author} who said their name was {sender} "
            f"sent this message to {who}: {message}"
        )
        await self._close_thread(thread)

    @commands.hybrid_command(name="vote", aliases=["doty"], description="Vote for the Dodo of the Year!")
    async def vote(self, context: Context) -> None:
        """Collect three DOTY nominations in a private thread and record them."""
        if config_py.votes.find_one({"user_id": str(context.author.id)}):
            await context.send(
                "Looks like you have already voted in this round! If you feel like you did some oopsie :dodo: "
                "in your votes, please poke Fox!"
            )
            return

        await context.defer(ephemeral=True)
        doty_channel = self.bot.get_channel(config_py.DOTY_CHANNEL)
        thread = await self._open_thread(context, f"Vote at {time.time()}")
        await thread.send(
            f"Hey there, {context.author.mention}! This private thread collects your nominations. "
            f"They'll be posted to <#{config_py.DOTY_CHANNEL}> at the end of round 1.\n"
            "## Please note that both Salvy and Fox are not participating in the votes.\n"
            "Don't vote for them even if you really want to :hearts: You have 180 seconds per question."
        )

        role_model = await self._ask(
            thread, context.author,
            "# NOMINATION 1: **THE ROLE MODEL**\nThe person who sets an example with exceptional skills, knowledge and "
            "dedication, always ready to support others.", 180,
        )
        progress = role_model and await self._ask(
            thread, context.author,
            "# NOMINATION 2: **THE PROGRESS OF THE YEAR**\nThe person who achieved a breakthrough in their progress or "
            "found a fundamentally new role in the community.", 180,
        )
        community = progress and await self._ask(
            thread, context.author,
            "# NOMINATION 3: **THE COMMUNITY BUILDER OF THE YEAR**\nThe special someone who creates the cosiness and "
            "respect that made you find your place here.", 180,
        )
        if not community:
            await self._close_thread(thread)
            return

        embed = messages.success(
            f"THE ROLE MODEL: {role_model}!\nPROGRESS OF THE YEAR: {progress}\nCOMMUNITY BUILDER: {community}",
            title=f"Nominations from {context.author}",
        )
        await doty_channel.send(embed=embed)
        await doty_channel.send("= :heart: =")
        config_py.votes.insert_one(
            {
                "user_id": str(context.author.id),
                "role_model": role_model,
                "progress_of_the_year": progress,
                "community_builder": community,
            }
        )
        await self._close_thread(
            thread, "The first round of the votes closes on 17.12! Thank you for participating! :heart: "
        )

    @commands.hybrid_command(name="resetvote", aliases=["resetdoty"], description="Reset a user's vote (owner only).")
    @checks.is_owner()
    async def resetvote(self, context: Context, user: discord.User) -> None:
        """Clear ``user``'s recorded DOTY vote so they can vote again."""
        result = config_py.votes.delete_one({"user_id": str(user.id)})
        if result.deleted_count:
            await context.send(f"Vote status for {user.mention} has been reset.")
        else:
            await context.send("User not found in the voting status records.")


async def setup(bot):
    await bot.add_cog(Seasonal(bot))
