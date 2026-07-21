"""
PP cog — the joke "pp meter" commands: measure a pp, check an average toward
someone, and list favourites / server-wide rankings.
"""

import random

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages


def _bar(length: int) -> str:
    """Render the classic ``8===D`` bar of a given length."""
    return f"8{'=' * length}D"


class PP(commands.Cog, name="pp"):
    """The pp-meter joke commands."""

    def __init__(self, bot):
        self.bot = bot

    async def _format_ranking(self, results: list) -> str:
        """Turn aggregated ``{user, avg_pplength}`` rows into a numbered list."""
        lines = []
        for index, result in enumerate(results, start=1):
            user = await self.bot.fetch_user(result["user"])
            lines.append(f"{index}. **{user.name}**: \n {_bar(int(result['avg_pplength']))}")
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
                "This pp is too small to display. Maybe it's cold where you are?",
                title=f"{member.display_name}'s pp when thinking of {target_name}! Oops!",
            )
        else:
            embed = messages.success(
                _bar(length), title=f"We caught {member.display_name} thinking of {target_name}! :smirk: "
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
            await context.send("We haven't checked how this combination would affect their pps yet! Use dodo pp to check it!")
            return

        average = sum(item["PPlength"] for item in measurements) // len(measurements)
        target_name = "themselves" if target == member else target.display_name
        await context.send(
            embed=messages.success(
                _bar(average), title=f"How much does {member.display_name} like {target_name} on average??"
            )
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
            await context.send("You haven't used our dodo pp command yet! Never late to start! :eggplant:")
            return
        results.sort(key=lambda x: x["avg_pplength"], reverse=True)
        await context.send(f"Here are your priorities, {member.mention}:\n{await self._format_ranking(results)}")

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
            await context.send("Nobody has been thought of yet! :thinking:")
            return
        await context.send(
            f"Here are the most desired hot girls in your area :tired_face: :\n{await self._format_ranking(results)}"
        )


async def setup(bot):
    await bot.add_cog(PP(bot))
