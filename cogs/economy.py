"""
Economy cog — the Dodo Bank ``wallet`` and the ``sweetrolls`` collectible stats.
User-facing text lives in ``lang``.
"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
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
            await context.send(lang.ECONOMY_WALLET_BALANCE.format(balance=wallet["balance"]))
        else:
            await context.send(lang.ECONOMY_WALLET_CREATED)
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
        name = member.display_name

        nemesis, nemesis_count = await self._top_counterpart("stolen_from", "thief", user_id)
        sugar_daddy, sugar_count = await self._top_counterpart("gifted_to", "gifter", user_id)

        lines = [
            lang.SWEETROLLS_STOLEN.format(
                name=name,
                stolen=rolls.count_documents({"thief": user_id}),
                golden=rolls.count_documents({"thief": user_id, "golden": 1}),
            ),
            lang.SWEETROLLS_STOLEN_FROM.format(name=name, stolen_from=rolls.count_documents({"stolen_from": user_id})),
            lang.SWEETROLLS_GIFTS.format(
                name=name,
                given=rolls.count_documents({"gifter": user_id}),
                received=rolls.count_documents({"gifted_to": user_id}),
            ),
            lang.SWEETROLLS_RHUBARB.format(name=name, count=rolls.count_documents({"victim": user_id, "rhubarb": 1})),
        ]
        if nemesis_count > 0:
            lines.append(lang.SWEETROLLS_NEMESIS.format(name=name, nemesis=nemesis.display_name, count=nemesis_count))
        else:
            lines.append(lang.SWEETROLLS_NO_NEMESIS.format(name=name))
        if sugar_count > 0:
            lines.append(lang.SWEETROLLS_SUGAR_DADDY.format(name=name, daddy=sugar_daddy.display_name, count=sugar_count))
        else:
            lines.append(lang.SWEETROLLS_NO_SUGAR_DADDY.format(name=name))

        await context.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(Economy(bot))
