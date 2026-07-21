"""
Parsing cog — the low-effort ``parseold`` dummy parse plus the top/bottom parse
leaderboards.
"""

import random
from datetime import date

import pymongo

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages


class Parsing(commands.Cog, name="parsing"):
    """Dummy parse and parse leaderboards."""

    def __init__(self, bot):
        self.bot = bot

    async def _leaderboard(self, context: Context, title: str, order: int) -> None:
        """Post the 10 highest/lowest championship parses (``order`` = sort direction)."""
        top = config_py.parses.find({"Championship Parse": 1}).sort("Parse", order).limit(10)
        embed = messages.embed(title=title, color=discord.Color.green())
        for index, parse in enumerate(top, start=1):
            user = self.bot.get_user(parse["ID"]) or await self.bot.fetch_user(parse["ID"])
            embed.add_field(
                name=f"{index}. {user.display_name}",
                value=f"\U0001F3AF Parse: {parse['Parse']} | {parse['Date']} | Difficulty: {parse['Difficulty Level']}",
                inline=False,
            )
        await context.send(embed=embed)

    @commands.hybrid_command(name="topparses", description="Show the top-10 dodo parse users.")
    async def topparses(self, context: Context) -> None:
        """Show the ten highest championship parses."""
        await self._leaderboard(context, "Top 10 Parses", pymongo.DESCENDING)

    @commands.hybrid_command(name="bottomparses", description="Show the bottom-10 dodo parse users.")
    async def bottomparses(self, context: Context) -> None:
        """Show the ten lowest championship parses (it takes talent too!)."""
        await self._leaderboard(context, "Bottom 10 Parses", pymongo.ASCENDING)

    @commands.hybrid_command(name="parseold", description="Old parse that doesn't require any skill.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @checks.not_blacklisted()
    async def parseold(self, context: Context, member: discord.Member = None) -> None:
        """Roll a random dummy parse with a flavour message and record it."""
        member = member or context.author
        parse = random.randrange(config_py.max_parse) or 1  # avoid division by zero
        minutes = round(config_py.dummy_health / parse / 60)

        tiers = [
            (15000, config_py.error, f"{parse} DPS... Please leave the server",
             f"{member.display_name} couldn't handle pressing 5 buttons, and gave up after {minutes} of whatever it was with the result of..."),
            (50000, config_py.error, f"{parse} DPS. You must be new here :) ",
             f"{member.display_name}, is that... a heavy attack build? {minutes} minutes well wasted, your result is..."),
            (70000, config_py.warning, f"{parse} DPS. A little bit more and you will look like a proper Veteran!",
             f"{member.display_name} parsed the dummy for {minutes} minutes with the result of..."),
            (100000, config_py.warning, f"{parse} DPS! Sub 100k is so 2020",
             f"{member.display_name} parsed the dummy for {minutes} minutes with a result of..."),
            (120000, config_py.success, f"{parse} DPS! Is that an actual redguard magden?",
             f"{member.display_name} demolished the trial dummy in {minutes} minutes with a result of..."),
            (140000, config_py.success, f"{parse} DPS! Keegan would be proud. Ping him if you dare xD ",
             f"{member.display_name} evaporated the poor atronach dummy in {minutes} minutes with a result of..."),
        ]
        for threshold, color, description, author in tiers:
            if parse < threshold:
                break
        else:
            color, description, author = config_py.success, f"{parse} DPS! vote to kick", "Deniz, relog."

        embed = messages.embed(description, color=color)
        embed.set_author(name=author, icon_url=context.author.display_avatar)
        await context.send(embed=embed)
        config_py.parses.insert_one(
            {"Name": member.display_name, "ID": member.id, "Date": date.today().isoformat(), "Parse": parse}
        )


async def setup(bot):
    await bot.add_cog(Parsing(bot))
