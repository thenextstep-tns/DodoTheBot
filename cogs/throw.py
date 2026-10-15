"""
Throw cog — ``throw`` launches another member a physics-derived distance after
the thrower solves a timed arithmetic puzzle that grows with their power. Throwers gain power, targets
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
from helpers import database as db
from helpers import messages
from helpers.hotload import fresh_lang, register_missing

# Texts as they are on disk now, so new ones work after just `reload throw`.
lang = fresh_lang()

_MAX_DISTANCE = 5.0  # metres at the ideal 45° angle
_PUZZLE_TIMEOUT = 5


def _span(value, fallback) -> tuple:
    """A ``(low, high)`` range from a "min, max" list setting; ``fallback`` if it isn't two numbers."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        value = fallback
    low, high = sorted(int(v) for v in value[:2])
    return low, high


def _pick(param, defaults: dict, key: str) -> int:
    """A random number from the "min, max" range setting ``key`` (its default if the setting is malformed)."""
    low, high = _span(param(key), defaults[key])
    return random.randint(low, high)


def _build_puzzle(power: float, param, defaults: dict) -> tuple:
    """``(tier, text, answer)`` for a thrower with ``power``. Harder as power grows,
    but always something that feels fair to estimate in a few seconds:

    - below ``throw_tier_sums_until``: 2–3 numbers added and subtracted
    - below ``throw_tier_mixed_until``: one multiplication and one addition
    - below ``throw_tier_product_until``: three numbers multiplied
    - above that: one more number to multiply per ``throw_power_per_factor``,
      up to ``throw_max_factors`` numbers
    """
    if power < param("throw_tier_sums_until"):
        low, high = _span(param("throw_sum_terms"), defaults["throw_sum_terms"])
        numbers = [_pick(param, defaults, "throw_sum_numbers") for _ in range(random.randint(max(2, low), max(2, high)))]
        # Precision needs a positive answer: reroll the signs a few times, then add everything.
        for _ in range(10):
            signs = [random.choice((1, -1)) for _ in numbers[1:]]
            if numbers[0] + sum(s * n for s, n in zip(signs, numbers[1:])) > 0:
                break
        else:
            signs = [1] * len(signs)
        text = str(numbers[0]) + "".join(f" {'+' if s > 0 else '-'} {n}" for s, n in zip(signs, numbers[1:]))
        return "sums", text, numbers[0] + sum(s * n for s, n in zip(signs, numbers[1:]))

    if power < param("throw_tier_mixed_until"):
        a, b, c = _pick(param, defaults, "throw_mixed_numbers"), _pick(param, defaults, "throw_mixed_multipliers"), _pick(param, defaults, "throw_mixed_added")
        text = f"{a} * {b} + {c}" if random.random() < 0.5 else f"{c} + {a} * {b}"
        return "mixed", text, a * b + c

    factors = [_pick(param, defaults, key) for key in ("throw_product_first", "throw_product_second", "throw_product_third")]
    tier = "product"
    if power >= param("throw_tier_product_until"):
        tier = "big_product"
        extra = 1 + int((power - param("throw_tier_product_until")) // max(param("throw_power_per_factor"), 0.01))
        extra = min(extra, max(0, param("throw_max_factors") - len(factors)))
        factors += [random.randint(param("throw_extra_factor_min"), param("throw_extra_factor_max")) for _ in range(extra)]
    return tier, " * ".join(str(f) for f in factors), math.prod(factors)


class Throw(commands.Cog, name="throw"):
    """The 'dodo throw' minigame."""

    def __init__(self, bot):
        self.bot = bot

    def _defaults(self) -> dict:
        """Each throw setting's built-in default, from the running registry."""
        return {spec["key"]: spec["default"] for spec in self.bot.params.specs_for_cog("throw")}

    @commands.hybrid_command(name="throw", description="Throw another member a physics-derived distance.")
    async def throw(self, context: Context, member: discord.Member) -> None:
        """Charge a throw via a timed puzzle, then launch ``member``."""
        guild_id = context.guild.id if context.guild else None
        param = lambda key: self.bot.params.get(guild_id, key)  # noqa: E731
        self_throw = member.id == context.author.id

        # Whoever you threw last is still waddling back from wherever they landed.
        if not self_throw:
            last = config_py.throws.find_one(
                {"thrower_id": context.author.id, "target_id": member.id}, sort=[("date", -1)]
            )
            if last:
                walk_time = last["distance"] / param("throw_waddle_speed")
                waited = (datetime.utcnow() - last["date"]).total_seconds()
                if waited < walk_time:
                    await context.send(lang.THROW_STILL_WADDLING.format(
                        member=member.mention, distance=round(last["distance"], 2), seconds=math.ceil(walk_time - waited)
                    ))
                    return

        thrower_power = db.get_or_default(config_py.user_power, context.author.id, "power", 1.0)
        target_power = db.get_or_default(config_py.user_power, member.id, "power", 1.0)

        puzzle_tier, puzzle, correct_answer = _build_puzzle(thrower_power, param, self._defaults())

        puzzle_message = await context.send(lang.THROW_PUZZLE.format(timeout=_PUZZLE_TIMEOUT, puzzle=puzzle))
        countdown = asyncio.create_task(self._countdown(puzzle_message, puzzle))

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

        total_force = distance * thrower_power

        if self_throw:
            in_air = lang.THROW_SELF_JUMPING.format(answer=correct_answer, angle=round(angle, 2))
        else:
            in_air = lang.THROW_THROWING.format(
                answer=correct_answer, member=member.mention, angle=round(angle, 2), gif="https://tenor.com/bkIHP.gif"
            )
        await puzzle_message.edit(content=in_air)
        await asyncio.sleep(random.randint(3, 5))

        landing = total_force * random.uniform(0.8, 1.2)
        # Re-read: another throw may have moved either power while this one was in the air.
        thrower_power = db.get_or_default(config_py.user_power, context.author.id, "power", 1.0)
        target_power = db.get_or_default(config_py.user_power, member.id, "power", 1.0)
        precision = max(0.0, 1 - abs(user_answer - correct_answer) / correct_answer)
        # Straight up and straight back down: the target lands on the thrower's head.
        head_landing = angle >= 90 and not self_throw

        if self_throw:
            # Throwing yourself is just jumping: no power changes hands.
            gain = 0.0
            new_thrower_power = new_target_power = thrower_power
        elif head_landing:
            swing = param("throw_head_landing_power")
            gain = -swing
            new_thrower_power = max(0, thrower_power - swing)
            new_target_power = target_power + swing
        else:
            step = param("throw_gain_step")
            # Steep near a perfect answer, then a long flat tail: most answers are way off.
            raw_gain = param("throw_max_gain") / (1 + (1 - precision) / param("throw_gain_falloff"))
            gain = round(round(raw_gain / step) * step, 4)
            new_thrower_power = thrower_power + gain
            new_target_power = max(0, target_power - gain * param("throw_target_loss_ratio"))
        if not self_throw:
            db.upsert(config_py.user_power, context.author.id, {"power": new_thrower_power})
            db.upsert(config_py.user_power, member.id, {"power": new_target_power})

        config_py.throws.insert_one({
            "thrower_id": context.author.id,
            "target_id": member.id,
            "guild_id": guild_id,
            "puzzle": puzzle,
            "puzzle_tier": puzzle_tier,
            "answer": user_answer,
            "correct_answer": correct_answer,
            "precision": precision,
            "angle": angle,
            "distance": landing,
            "head_landing": head_landing,
            "self_throw": self_throw,
            "thrower_power_change": new_thrower_power - thrower_power,
            "target_power_change": new_target_power - target_power,
            "date": datetime.utcnow(),
        })

        if self_throw:
            content = lang.THROW_SELF_RESULT.format(distance=round(landing, 2))
        elif head_landing:
            content = lang.THROW_HEAD_LANDING.format(
                member=member.mention,
                thrower=context.author.mention,
                new_thrower_power=round(new_thrower_power, 2),
                new_target_power=round(new_target_power, 2),
            )
        else:
            content = lang.THROW_RESULT.format(
                member=member.mention,
                distance=round(landing, 2),
                funny=self._funny_description(member),
                thrower=context.author.mention,
                new_thrower_power=round(new_thrower_power, 2),
                new_target_power=round(new_target_power, 2),
            ) + "\n" + lang.THROW_PRECISION.format(precision=round(precision * 100, 1), gain=round(gain, 2))
        await puzzle_message.edit(content=content)

    @commands.hybrid_command(name="throwstats", description="Your throwing record, and the all-time throwing records.")
    async def throwstats(self, context: Context, member: discord.Member = None) -> None:
        """Show ``member``'s (or the caller's) throw stats next to the world records.

        Mentions sit inside the embed, so nobody named in it is pinged.
        """
        member = member or context.author
        throws = config_py.throws

        thrown = throws.count_documents({"thrower_id": member.id})
        been_thrown = throws.count_documents({"target_id": member.id})
        longest = throws.find_one({"thrower_id": member.id}, sort=[("distance", -1)])
        favourite = next(throws.aggregate([
            {"$match": {"thrower_id": member.id}},
            {"$group": {"_id": "$target_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1},
        ]), None)
        # Only throws since precision started being saved count towards the average.
        precision = next(throws.aggregate([
            {"$match": {"thrower_id": member.id, "precision": {"$exists": True}}},
            {"$group": {"_id": None, "average": {"$avg": "$precision"}, "count": {"$sum": 1}}},
        ]), None)
        most_throws = next(throws.aggregate([
            {"$group": {"_id": "$thrower_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1},
        ]), None)
        record = throws.find_one({}, sort=[("distance", -1)])

        none = lang.THROWSTATS_NONE
        lines = [
            lang.THROWSTATS_THROWN.format(count=thrown),
            lang.THROWSTATS_BEEN_THROWN.format(count=been_thrown),
            lang.THROWSTATS_LONGEST.format(
                throw=lang.THROWSTATS_THROW.format(distance=round(longest["distance"], 2), target=f"<@{longest['target_id']}>")
                if longest else none
            ),
            lang.THROWSTATS_PRECISION.format(
                precision=lang.THROWSTATS_PRECISION_VALUE.format(
                    average=round(precision["average"] * 100, 1), count=precision["count"]
                )
                if precision else none
            ),
            lang.THROWSTATS_FAVOURITE.format(
                partner=lang.THROWSTATS_PARTNER.format(target=f"<@{favourite['_id']}>", count=favourite["count"])
                if favourite else none
            ),
            "",
            lang.THROWSTATS_WR_TITLE,
            lang.THROWSTATS_WR_MOST.format(
                record=lang.THROWSTATS_WR_MOST_RECORD.format(thrower=f"<@{most_throws['_id']}>", count=most_throws["count"])
                if most_throws else none
            ),
            lang.THROWSTATS_WR_LONGEST.format(
                record=lang.THROWSTATS_WR_LONGEST_RECORD.format(
                    thrower=f"<@{record['thrower_id']}>",
                    target=lang.THROWSTATS_THEMSELVES if record["target_id"] == record["thrower_id"] else f"<@{record['target_id']}>",
                    distance=round(record["distance"], 2),
                )
                if record else none
            ),
        ]
        embed = messages.embed(
            "\n".join(lines), title=lang.THROWSTATS_TITLE.format(name=member.display_name), color=config_py.main_color
        )
        await context.send(embed=embed)

    async def _countdown(self, puzzle_message: discord.Message, puzzle: str) -> None:
        """Tick the puzzle message's countdown once per second until cancelled."""
        try:
            for remaining in range(_PUZZLE_TIMEOUT, 0, -1):
                await puzzle_message.edit(content=lang.THROW_COUNTDOWN.format(puzzle=puzzle, remaining=remaining))
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
    # Settings added since the bot started work after just `reload throw`.
    register_missing(bot, "throw")
    await bot.add_cog(Throw(bot))
