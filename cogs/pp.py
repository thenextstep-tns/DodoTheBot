"""
PP cog — the joke "pp meter" commands: measure a pp, check an average toward
someone, and list favourites / server-wide rankings. Text lives in ``lang``.
"""

import random

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages


def _bar(length: int) -> str:
    """Render the classic ``8===D`` bar of a given length."""
    return lang.PP_BAR.format(bars="=" * length)


class PP(commands.Cog, name="pp"):
    """The pp-meter joke commands."""

    def __init__(self, bot):
        self.bot = bot

    async def _format_ranking(self, results: list) -> str:
        """Turn aggregated ``{user, avg_pplength}`` rows into a numbered list."""
        lines = []
        for index, result in enumerate(results, start=1):
            user = await self.bot.fetch_user(result["user"])
            lines.append(lang.PP_RANKING_LINE.format(index=index, name=user.name, bar=_bar(int(result["avg_pplength"]))))
        return "\n".join(lines)

    @commands.hybrid_command(name="pp", description="Check the length of your or someone else's pp.")
    @checks.not_blacklisted()
    async def pp(self, context: Context, member: discord.Member = None, target: discord.Member = None) -> None:
        """Roll a pp length for ``member`` thinking of ``target`` and record it."""
        member = member or context.author
        target = target or context.author
        length = random.randrange(15)
        target_name = "themselves" if target == member else target.display_name

        if length < 2:
            embed = messages.warning(
                lang.PP_TOO_SMALL, title=lang.PP_TOO_SMALL_TITLE.format(name=member.display_name, target=target_name)
            )
        else:
            embed = messages.success(
                _bar(length), title=lang.PP_RESULT_TITLE.format(name=member.display_name, target=target_name)
            )
        config_py.pps.insert_one({"MeasuredUser": member.id, "ThoughtOfUser": target.id, "PPlength": length})
        await context.send(embed=embed)

    @commands.hybrid_command(name="checkpp", description="Check the average pp toward someone.")
    @checks.not_blacklisted()
    async def checkpp(self, context: Context, member: discord.Member = None, target: discord.Member = None) -> None:
        """Show ``member``'s average pp length when thinking of ``target``."""
        member = member or context.author
        target = target or context.author
        measurements = list(config_py.pps.find({"MeasuredUser": member.id, "ThoughtOfUser": target.id}))

        if not measurements:
            await context.send(lang.PP_CHECK_NONE)
            return

        average = sum(item["PPlength"] for item in measurements) // len(measurements)
        target_name = "themselves" if target == member else target.display_name
        await context.send(
            embed=messages.success(_bar(average), title=lang.PP_CHECK_TITLE.format(name=member.display_name, target=target_name))
        )

    @commands.hybrid_command(name="priorities", description="List your favourite people.")
    @checks.not_blacklisted()
    async def priorities(self, context: Context, member: discord.Member = None) -> None:
        """List ``member``'s favourites, ranked by average pp length toward them."""
        member = member or context.author
        results = [
            {"user": doc["_id"], "avg_pplength": doc["avg_pplength"]}
            for doc in config_py.pps.aggregate(
                [
                    {"$match": {"MeasuredUser": member.id}},
                    {"$group": {"_id": "$ThoughtOfUser", "avg_pplength": {"$avg": "$PPlength"}}},
                ]
            )
        ]
        if not results:
            await context.send(lang.PP_NONE)
            return
        results.sort(key=lambda x: x["avg_pplength"], reverse=True)
        await context.send(lang.PP_PRIORITIES.format(mention=member.mention, ranking=await self._format_ranking(results)))

    @commands.hybrid_command(name="hotties", description="Show the most desirable hotties on the server.")
    @checks.not_blacklisted()
    async def hotties(self, context: Context) -> None:
        """Rank everyone server-wide by average pp length thought toward them."""
        results = [
            {"user": doc["_id"], "avg_pplength": doc["avg_pplength"]}
            for doc in config_py.pps.aggregate(
                [
                    {"$group": {"_id": "$ThoughtOfUser", "avg_pplength": {"$avg": "$PPlength"}}},
                    {"$sort": {"avg_pplength": -1}},
                ]
            )
        ]
        if not results:
            await context.send(lang.PP_HOTTIES_NONE)
            return
        await context.send(lang.PP_HOTTIES.format(ranking=await self._format_ranking(results)))


async def setup(bot):
    await bot.add_cog(PP(bot))
