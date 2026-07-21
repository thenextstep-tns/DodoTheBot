"""
Race-stats cog — read-only leaderboards for the mouse races: a user's most
successful mice, and the top mice server-wide.
"""

from collections import defaultdict

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages


class RaceStats(commands.Cog, name="racestats"):
    """Mouse-racing leaderboards."""

    def __init__(self, bot):
        self.bot = bot

    def _most_successful_mice(self, user_id: int) -> list:
        """Return a user's mice ranked by wins then average finishing position."""
        stats = defaultdict(lambda: {"races_won": 0, "total_position": 0, "race_count": 0})
        for race in config_py.races.find():
            for participant in race["participants"]:
                if not {"user_id", "mouse_name", "position"} <= participant.keys():
                    continue
                participant_id = participant["user_id"]
                if isinstance(participant_id, dict) and "$numberLong" in participant_id:
                    participant_id = str(participant_id["$numberLong"])
                position = participant["position"]
                if isinstance(position, dict) and "$numberInt" in position:
                    position = int(position["$numberInt"])
                if str(participant_id) != str(user_id):
                    continue
                mouse = stats[participant["mouse_name"]]
                if int(position) == 1:
                    mouse["races_won"] += 1
                mouse["total_position"] += int(position)
                mouse["race_count"] += 1

        for mouse in stats.values():
            mouse["average_position"] = mouse["total_position"] / mouse["race_count"]
        return sorted(stats.items(), key=lambda x: (-x[1]["races_won"], x[1]["average_position"]))[:10]

    @commands.hybrid_command(name="mice", description="Check your most successful mice.")
    async def mice(self, context: Context, member: discord.Member = None) -> None:
        """Show a member's ten most successful mice."""
        member = member or context.author
        sorted_mice = self._most_successful_mice(member.id)
        if not sorted_mice:
            await context.send(
                "Looks like you don't have any race records yet! Start participating in races to see your stats :dodo:"
            )
            return

        response = f"**{member.display_name}'s Most Successful Mice:**\n"
        for index, (mouse, stats) in enumerate(sorted_mice, start=1):
            response += f"{index}. **{mouse}**, Wins: {stats['races_won']}, Avg Position: {stats['average_position']:.2f}\n"
        for chunk in range(0, len(response), 1999):
            await context.send(response[chunk : chunk + 1999])

    @commands.hybrid_command(name="mousestats", description="Show the top skeevatrons in recent history.")
    @checks.not_blacklisted()
    async def mousestats(self, context: Context) -> None:
        """Show the top ten mice (min. 5 races) by average finishing position."""
        pipeline = [
            {"$unwind": "$participants"},
            {"$match": {"participants.mouse_name": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$participants.mouse_name",
                    "starts": {"$sum": 1},
                    "total_position": {"$sum": "$participants.position"},
                    "favorite_handler": {"$first": "$participants.user_id"},
                }
            },
            {"$match": {"starts": {"$gte": 5}}},
            {
                "$project": {
                    "mouse_name": "$_id",
                    "starts": 1,
                    "average_position": {"$divide": ["$total_position", "$starts"]},
                    "favorite_handler": 1,
                }
            },
            {"$sort": {"average_position": 1}},
            {"$limit": 10},
        ]
        embed = messages.embed(
            "Only showing mice who participated in 5 or more races:", title="Top 10 Mice!", color=0x00FF00
        )
        for index, stats in enumerate(config_py.races.aggregate(pipeline), start=1):
            handler = context.guild.get_member(int(stats["favorite_handler"]))
            embed.add_field(
                name=f"{index}. {stats['mouse_name']}",
                value=f"Starts: {stats['starts']}, Avg. Position: {stats['average_position']:.2f}, "
                f"Fav. Handler: {handler.display_name if handler else 'Unknown'}",
                inline=False,
            )
        await context.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RaceStats(bot))
