"""
Economy cog — the Dodo Bank ``wallet`` and the ``sweetrolls`` collectible stats.
"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks


class Economy(commands.Cog, name="economy"):
    """Wallet and sweetroll statistics."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="wallet", description="Check your Dodo Bank account.")
    async def wallet(self, context: Context, member: discord.Member = None) -> None:
        """Show ``member``'s coin balance, creating a wallet if they lack one."""
        member = member or context.author
        wallet = config_py.wallets.find_one({"user_id": member.id})
        if wallet:
            await context.send(f"You have {wallet['balance']} coins in your wallet!")
        else:
            await context.send(
                "Looks like you don't really have a wallet! But fear not! We will make you one this instant :dodo: "
            )
            config_py.wallets.insert_one({"user_id": member.id, "balance": 0})

    async def _top_counterpart(self, match_field: str, group_field: str, user_id: int):
        """Return (user, count) for the person topping an aggregated sweetroll relation."""
        result = list(
            config_py.sweetrolls.aggregate(
                [
                    {"$match": {match_field: user_id}},
                    {"$group": {"_id": f"${group_field}", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 1},
                ]
            )
        )
        if not result or not result[0]["_id"]:
            return None, 0
        return await self.bot.fetch_user(result[0]["_id"]), result[0]["count"]

    @commands.hybrid_command(name="sweetrolls", description="Show how many sweetrolls you or your friends have.")
    @checks.not_blacklisted()
    async def sweetrolls(self, context: Context, member: discord.Member = None) -> None:
        """Summarize a member's sweetroll thefts, gifts, betrayals and rivals."""
        member = member or context.author
        rolls = config_py.sweetrolls
        user_id = member.id

        stolen_by = rolls.count_documents({"thief": user_id})
        golden = rolls.count_documents({"thief": user_id, "golden": 1})
        stolen_from = rolls.count_documents({"stolen_from": user_id})
        gifted_by = rolls.count_documents({"gifter": user_id})
        gifted_to = rolls.count_documents({"gifted_to": user_id})
        rhubarb = rolls.count_documents({"victim": user_id, "rhubarb": 1})

        nemesis, nemesis_count = await self._top_counterpart("stolen_from", "thief", user_id)
        sugar_daddy, sugar_count = await self._top_counterpart("gifted_to", "gifter", user_id)

        lines = [
            f"{member.display_name} stole **{stolen_by}** sweetrolls including **{golden}** golden sweetrolls...",
            f"People stole **{stolen_from}** sweetrolls from {member.display_name}. :pleading_face: ",
            f"{member.display_name} has given away **{gifted_by}** sweetrolls and received **{gifted_to}** as gifts!",
            f"{member.display_name} has suffered **{rhubarb}** rhubarb betrayal(s)!",
        ]
        if nemesis_count > 0:
            lines.append(f"{member.display_name}'s arch-nemesis is **{nemesis.display_name}** with **{nemesis_count}** stolen sweetrolls. :smirk:")
        else:
            lines.append(f"{member.display_name} don't have an arch-nemesis (yet). ")
        if sugar_count > 0:
            lines.append(f"{member.display_name}'s sugar doddy is **{sugar_daddy.display_name}** with **{sugar_count}** sweetrolls gifted. :smirk:")
        else:
            lines.append(f"{member.display_name} don't have a sugar doddy (yet). ")

        await context.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(Economy(bot))
