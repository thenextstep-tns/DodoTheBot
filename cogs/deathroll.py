"""
Death-roll cog — ``roll`` challenges another member to a death-roll duel for
gold: players alternate rolling a shrinking die, and whoever rolls a 1 loses.
"""

import asyncio
import random
from datetime import date

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

_ROLL_LOG_CHANNEL = 951482552684777482


class DeathRoll(commands.Cog, name="deathroll"):
    """The death-roll duel game."""

    def __init__(self, bot):
        self.bot = bot

    def _save_duel(self, *, bet, rounds, challenger, opponent, winner, loser) -> None:
        """Persist a finished duel to the database."""
        config_py.dodoroll.insert_one(
            {
                "Date": date.today().isoformat(),
                "Bet": bet,
                "Challenger": challenger.display_name,
                "Challenger ID": challenger.id,
                "Opponent": opponent.display_name,
                "Opponent ID": opponent.id,
                "Number of rounds": rounds,
                "Winner": winner.display_name,
                "Winner ID": winner.id,
                "Loser": loser.display_name,
                "Loser ID": loser.id,
            }
        )

    @commands.hybrid_command(name="roll", description="Challenge a friend to a death roll!")
    @checks.not_blacklisted()
    async def roll(self, context: Context, bet: int, opponent: discord.Member = None) -> None:
        """Death-roll ``opponent`` for ``bet`` gold."""
        await context.defer()
        challenger = context.author
        channel = context.channel

        bet_final = min(bet, config_py.roll_limit)
        if bet > config_py.roll_limit:
            await channel.send(lang.ROLL_OVER_LIMIT)
        if opponent is None:
            await context.send(lang.ROLL_NO_OPPONENT)
            return
        if opponent.id == challenger.id:
            await context.send(lang.ROLL_SELF_PLAY)
            return

        challenge_msg = await context.send(
            f"**{challenger.display_name}** just challenged **{opponent.display_name}** for **{bet_final} gold**! "
            f"**{opponent.mention}**, press the dice emoji under this message to accept and let the battle begin!"
        )
        emoji, _ = await messages.wait_for_reaction(
            self.bot, challenge_msg, config_py.roll_challenge_emoji, member=opponent, timeout=300
        )
        if emoji is None:
            await challenge_msg.clear_reactions()
            await channel.send(lang.ROLL_TIMEOUT_CANCEL)
            return
        if config_py.roll_challenge_emoji[emoji] == 1:
            await challenge_msg.clear_reactions()
            await channel.send(f"{opponent.display_name} declined the duel! :slight_frown: ")
            return

        await challenge_msg.clear_reactions()
        await channel.send(lang.ROLL_DUEL_ACCEPTED)
        await self._run_duel(context, channel, challenger, opponent, bet, bet_final)

    async def _run_duel(self, context, channel, challenger, opponent, bet, bet_final) -> None:
        """Run the alternating death-roll loop until someone rolls a 1 or times out."""
        current_roll = bet_final
        roller, waiting = opponent, challenger
        rounds = 0

        while True:
            rounds += 1
            teaser = await channel.send(random.choice(config_py.dice_gifs))
            await asyncio.sleep(random.randint(1, 3))
            await teaser.delete()

            next_roll = random.randint(1, current_roll - 1)
            if next_roll == 1:
                await channel.send(
                    embed=messages.embed(
                        f"**{roller.display_name}** rolled **1** and has lost the duel. "
                        f"Congratulations to {waiting.display_name} on winning **{bet}** gold!",
                        title=lang.ROLL_TITLE_LOSS,
                        color=config_py.error,
                    )
                )
                self._save_duel(bet=bet_final, rounds=rounds, challenger=challenger, opponent=opponent,
                                winner=waiting, loser=roller)
                await channel.send(lang.ROLL_DUEL_OVER)
                await self.bot.get_channel(config_py.roll_log).send(
                    f"**{waiting.display_name}** won a duel against **{roller.display_name}** for **{bet}** gold!"
                )
                return

            roll_msg = await channel.send(
                embed=messages.warning(
                    f"**{roller.display_name}** rolled **{next_roll}**! How will {waiting.display_name} respond?",
                    title=lang.ROLL_DUEL_ACCEPTED,
                )
            )
            emoji, _ = await messages.wait_for_reaction(
                self.bot, roll_msg, config_py.roll_duel_emoji, member=waiting, timeout=60
            )
            await roll_msg.clear_reactions()
            if emoji is None:
                await channel.send(f"**{waiting.display_name}** has timed out the duel. **{roller.display_name}** wins {bet} gold!")
                self._save_duel(bet=bet_final, rounds=rounds, challenger=challenger, opponent=opponent,
                                winner=roller, loser=waiting)
                await channel.send(lang.ROLL_DUEL_OVER)
                await self.bot.get_channel(_ROLL_LOG_CHANNEL).send(
                    f"**{roller.display_name}** won a duel against **{waiting.display_name}** for **{bet}** gold!"
                )
                return

            roller, waiting = waiting, roller
            current_roll = next_roll


async def setup(bot):
    await bot.add_cog(DeathRoll(bot))
