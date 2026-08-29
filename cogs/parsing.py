"""
Parsing cog — the low-effort ``parseold`` dummy parse plus the top/bottom parse
leaderboards. User-facing text lives in ``lang``.
"""

import random
from datetime import date

import pymongo

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

# Embed colour per parseold tier (aligned with lang.PARSEOLD_TIERS, then top tier).
_TIER_COLORS = [config_py.error, config_py.error, config_py.warning, config_py.warning,
                config_py.success, config_py.success]
_TOP_TIER_COLOR = config_py.success


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
                value=lang.PARSING_LEADERBOARD_VALUE.format(
                    parse=parse["Parse"], date=parse["Date"], difficulty=parse["Difficulty Level"]
                ),
                inline=False,
            )
        await context.send(embed=embed)

    @commands.hybrid_command(name="topparses", description="Show the top-10 dodo parse users.")
    async def topparses(self, context: Context) -> None:
        """Show the ten highest championship parses."""
        await self._leaderboard(context, lang.PARSING_TOP_TITLE, pymongo.DESCENDING)

    @commands.hybrid_command(name="bottomparses", description="Show the bottom-10 dodo parse users.")
    async def bottomparses(self, context: Context) -> None:
        """Show the ten lowest championship parses (it takes talent too!)."""
        await self._leaderboard(context, lang.PARSING_BOTTOM_TITLE, pymongo.ASCENDING)

    @commands.hybrid_command(name="parseold", description="Old parse that doesn't require any skill.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @checks.not_blacklisted()
    async def parseold(self, context: Context, member: discord.Member = None) -> None:
        """Roll a random dummy parse with a flavour message and record it."""
        member = member or context.author
        parse = random.randrange(config_py.max_parse) or 1  # avoid division by zero
        minutes = round(config_py.dummy_health / parse / 60)

        color, description, author = _TOP_TIER_COLOR, *lang.PARSEOLD_TOP_TIER
        for index, (threshold, desc_template, author_template) in enumerate(lang.PARSEOLD_TIERS):
            if parse < threshold:
                color = _TIER_COLORS[index]
                description = desc_template
                author = author_template
                break

        embed = messages.embed(
            description.format(parse=parse, name=member.display_name, minutes=minutes), color=color
        )
        embed.set_author(name=author.format(parse=parse, name=member.display_name, minutes=minutes), icon_url=context.author.display_avatar)
        await context.send(embed=embed)
        config_py.parses.insert_one(
            {"Name": member.display_name, "ID": member.id, "Date": date.today().isoformat(), "Parse": parse}
        )


async def setup(bot):
    await bot.add_cog(Parsing(bot))
