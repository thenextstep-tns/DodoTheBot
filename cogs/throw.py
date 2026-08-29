"""
Throw cog — ``throw`` launches another member a physics-derived distance after
the thrower solves a timed multiplication puzzle. Throwers gain power, targets
lose it, and each throw is logged. Text lives in ``lang``.
"""

import asyncio
import math
import random
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import database as db

_MAX_DISTANCE = 5.0  # metres at the ideal 45° angle
_PUZZLE_TIMEOUT = 5
_POWER_STEP = 0.05


class Throw(commands.Cog, name="throw"):
    """The 'dodo throw' minigame."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="throw", description="Throw another member a physics-derived distance.")
    async def throw(self, context: Context, member: discord.Member) -> None:
        """Charge a throw via a timed puzzle, then launch ``member``."""
        num1, num2, num3 = random.randint(3, 12), random.randint(53, 95), random.randint(2, 8)
        correct_answer = num1 * num2 * num3

        puzzle_message = await context.send(
            lang.THROW_PUZZLE.format(timeout=_PUZZLE_TIMEOUT, num1=num1, num2=num2, num3=num3)
        )
        countdown = asyncio.create_task(self._countdown(puzzle_message, num1, num2, num3))

        def check(msg):
            return msg.author == context.author and msg.channel == context.channel and msg.content.isdigit()

        try:
            answer_msg = await self.bot.wait_for("message", check=check, timeout=_PUZZLE_TIMEOUT)
            user_answer = int(answer_msg.content)
            countdown.cancel()
        except asyncio.TimeoutError:
            await puzzle_message.edit(content=lang.THROW_TIMEOUT.format(mention=context.author.mention))
            return

        angle = 45.0
        if user_answer > correct_answer:
            angle = min(90, 45 + (user_answer - correct_answer) / correct_answer * 45)
        elif user_answer < correct_answer:
            angle = max(0, 45 - (correct_answer - user_answer) / correct_answer * 45)
        distance = _MAX_DISTANCE * math.sin(2 * math.radians(angle))

        thrower_power = db.get_or_default(config_py.user_power, context.author.id, "power", 1.0)
        target_power = db.get_or_default(config_py.user_power, member.id, "power", 1.0)
        total_force = distance * thrower_power

        await puzzle_message.edit(
            content=lang.THROW_THROWING.format(
                answer=correct_answer, member=member.mention, angle=round(angle, 2), gif="https://tenor.com/bkIHP.gif"
            )
        )
        await asyncio.sleep(random.randint(3, 5))

        landing = total_force * random.uniform(0.8, 1.2)
        config_py.throws.insert_one(
            {"thrower_id": context.author.id, "target_id": member.id, "distance": landing, "date": datetime.utcnow()}
        )

        new_thrower_power = thrower_power + _POWER_STEP
        new_target_power = max(0, target_power - _POWER_STEP)
        db.upsert(config_py.user_power, context.author.id, {"power": new_thrower_power})
        db.upsert(config_py.user_power, member.id, {"power": new_target_power})

        await puzzle_message.edit(
            content=lang.THROW_RESULT.format(
                member=member.mention,
                distance=round(landing, 2),
                funny=self._funny_description(member),
                thrower=context.author.mention,
                new_thrower_power=round(new_thrower_power, 2),
                new_target_power=round(new_target_power, 2),
            )
        )

    async def _countdown(self, puzzle_message: discord.Message, num1: int, num2: int, num3: int) -> None:
        """Tick the puzzle message's countdown once per second until cancelled."""
        try:
            for remaining in range(_PUZZLE_TIMEOUT, 0, -1):
                await puzzle_message.edit(
                    content=lang.THROW_COUNTDOWN.format(num1=num1, num2=num2, num3=num3, remaining=remaining)
                )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _funny_description(member: discord.Member) -> str:
        """Build a randomized flavour sentence for where the target landed."""
        return (
            f"{random.choice(lang.THROW_FUNNY_PART1).format(member=member.mention)} "
            f"{random.choice(lang.THROW_FUNNY_PART2)} "
            f"{random.choice(lang.THROW_FUNNY_PART3)} "
            f"{random.choice(lang.THROW_FUNNY_PART4)}"
        )


async def setup(bot):
    await bot.add_cog(Throw(bot))
