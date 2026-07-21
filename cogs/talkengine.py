"""
Talk-engine cog — the ``imitate`` command builds a Markov chain from a user's
public message history and generates a sentence in their "voice".
"""

import random
import re

import markovify

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py


class MessageImitator(commands.Cog, name="talkengine"):
    """Generate Markov-chain imitations of a user's messages."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _strip_pings(text: str) -> str:
        """Remove characters and keywords that could ping people."""
        text = re.sub(r"[@#&!<>]", "", text)
        return re.sub(r"@everyone|@here", "", text)

    @commands.hybrid_command(name="imitate", description="Imitate a user based on their public messages.")
    async def imitate(self, context: Context, user: discord.User = None) -> None:
        """Imitate ``user`` (or the caller) using a Markov model of their messages."""
        user = user or context.author
        thinking = await context.send("🤔 Hmmmm let me think... ")

        history = [
            msg["message"]
            for msg in config_py.messages.find(
                {"author": user.id, "channel": {"$in": config_py.public_channels}}
            ).limit(10000)
        ]
        if not history:
            await thinking.edit(content=f"No public messages found for user {user.display_name}.")
            return

        random.shuffle(history)

        # Randomize the model each run so the same user reads differently over time.
        state_size = random.choice([1, 2, 3, 4])
        max_overlap_ratio = random.uniform(0.3, 0.9)
        max_overlap_total = random.randint(5, 15)
        min_words = random.randint(10, 24)
        max_words = random.randint(25, 50)

        # Seed with the invoking message's text when available (prefix invocation only).
        seed = self._strip_pings(context.message.content) if context.message else ""
        corpus = " ".join([seed] + [self._strip_pings(msg) for msg in history])
        text_model = markovify.Text(corpus, state_size=state_size)

        imitation = None
        for _ in range(150):
            imitation = text_model.make_sentence(
                tries=1000,
                max_overlap_ratio=max_overlap_ratio,
                max_overlap_total=max_overlap_total,
                min_words=min_words,
                max_words=max_words,
                test_output=False,
            )
            if imitation:
                break

        if not imitation:
            await thinking.edit(content=f"Unable to generate a coherent message for {user.display_name}.")
            return

        embed = discord.Embed(description=imitation, color=discord.Color.random())
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        await thinking.edit(content=f"Hi, my name is {user.display_name}, and this is what I think:", embed=embed)


async def setup(bot):
    await bot.add_cog(MessageImitator(bot))
