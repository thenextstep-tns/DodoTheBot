"""
Parse-tournament cog — ``parse`` runs a reaction-based DPS "parse championship":
players sign up with ✅, then each takes timed reaction-speed attempts at a
chosen difficulty. Scores are tracked live in one embed and saved to the DB.
"""

import asyncio
import random
import re
import time
from collections import defaultdict
from datetime import date

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

_DIFFICULTY_LEVELS = {
    "1️⃣": {"actions": 3, "dps_mod": -35000},
    "2️⃣": {"actions": 4, "dps_mod": -25000},
    "3️⃣": {"actions": 5, "dps_mod": 0},
    "4️⃣": {"actions": 7, "dps_mod": 25000},
    "5️⃣": {"actions": 9, "dps_mod": 40000},
}
_DPS_DEITIES = ["Tea", "Ellander", "Deniz", "Keegan", "Ducky", "NukeDuck", "Strader"]


class ParseTournament(commands.Cog, name="parse_tournament"):
    """The Dodos Parse Championship minigame."""

    def __init__(self, bot):
        self.bot = bot
        self.reset_state()

    def reset_state(self) -> None:
        """Reset all per-tournament state."""
        self.parse_data = defaultdict(lambda: {"attempts": 0, "best_parse": 0, "difficulty": ""})
        self.main_message: discord.Message | None = None
        self.participants: dict[int, discord.User] = {}
        self.signups_open = True
        self.max_attempts = 0

    @property
    def _actions(self) -> dict:
        """The action emoji → description map (deity is re-rolled each access)."""
        return {
            "⚔️": "Sword attack",
            "🪄": "Magic attack",
            "🛡️": "Block",
            "🏃": "Dodge",
            "😵": "Pretend to be dead",
            "🙏": f"Pray to the DPS deity - {random.choice(_DPS_DEITIES)}",
            "😕": "Confuse the boss",
            "💃": "Dance a crazy dance",
            "🌿": "Hide in the nearest bush",
        }

    @commands.hybrid_command(name="parse", description="Start a parse championship (1-3 attempts each).")
    async def parse(self, context: Context, max_attempts: int = 1) -> None:
        """Open sign-ups for a parse championship."""
        if max_attempts < 1 or max_attempts > 3:
            await context.send(lang.PARSEFEST_INVALID_ATTEMPTS)
            return

        self.reset_state()
        self.max_attempts = max_attempts

        embed = messages.warning(lang.PARSEFEST_LOBBY.format(max_attempts=max_attempts), title=lang.PARSEFEST_TITLE)
        embed.add_field(name="Participants", value="No one yet!", inline=False)
        self.main_message = await context.send(embed=embed)
        await self.main_message.add_reaction("✅")
        asyncio.create_task(self._close_signups_after(20))

    @commands.hybrid_command(name="stopfest", description="Stop the running parse championship (owner only).")
    @checks.is_owner()
    async def stopfest(self, context: Context) -> None:
        """Abort the current championship."""
        message = self.main_message
        self.reset_state()
        await context.send(lang.PARSEFEST_STOPPED)
        if message:
            await message.clear_reactions()

    async def _close_signups_after(self, seconds: float) -> None:
        """After ``seconds``, close sign-ups and switch the message to attempt mode."""
        await asyncio.sleep(seconds)
        if not self.main_message:
            return
        self.signups_open = False

        world_record = config_py.parses.find_one({"Championship Parse": 1}, sort=[("Parse", -1)])
        embed = self.main_message.embeds[0]
        embed.description = (
            lang.PARSEFEST_WR.format(parse=world_record["Parse"], name=world_record["Name"])
            if world_record
            else lang.PARSEFEST_NO_WR
        )
        await self.main_message.edit(embed=embed)
        await self.main_message.clear_reactions()
        await self.main_message.add_reaction("🎯")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        if user.bot or not self.main_message:
            return
        if self.signups_open and str(reaction.emoji) == "✅":
            if user.id not in self.participants:
                self.participants[user.id] = user
                await self.update_main_message(user)
        elif not self.signups_open and str(reaction.emoji) == "🎯" and user.id in self.participants:
            if self.parse_data[user.id]["attempts"] < self.max_attempts:
                await self._single_parse_attempt(user)
                await reaction.message.remove_reaction("🎯", user)

    async def _single_parse_attempt(self, user: discord.User) -> None:
        """Run one full reaction-speed attempt for ``user`` and record the result."""
        channel = self.main_message.channel
        user_data = self.parse_data[user.id]
        if user_data["attempts"] >= self.max_attempts:
            await channel.send(f"{user.display_name}, you've already used all your attempts!", delete_after=5)
            return
        user_data["attempts"] += 1

        # 1. Choose difficulty.
        difficulty_message = await channel.send(lang.PARSEFEST_DIFFICULTY_MENU.format(name=user.display_name))
        chosen_level, _ = await messages.wait_for_reaction(
            self.bot, difficulty_message, _DIFFICULTY_LEVELS, member=user, timeout=15.0
        )
        if chosen_level is None:
            await channel.send(lang.PARSEFEST_DIFFICULTY_TIMEOUT.format(name=user.display_name), delete_after=5)
            chosen_level = "3️⃣"
        difficulty = _DIFFICULTY_LEVELS[chosen_level]
        await difficulty_message.delete()

        # 2. Play the reaction-speed rounds.
        num_actions, dps_mod = difficulty["actions"], difficulty["dps_mod"]
        available_actions = dict(list(self._actions.items())[:num_actions])

        user_message = await channel.send(lang.PARSEFEST_PREBUFF.format(name=user.display_name))
        for emoji in available_actions:
            await user_message.add_reaction(emoji)
        await asyncio.sleep(2)
        await user_message.edit(content=lang.PARSEFEST_GO.format(name=user.display_name))

        reaction_times = []
        for i in range(num_actions):
            target_emoji, target_action = random.choice(list(available_actions.items()))
            await asyncio.sleep(random.uniform(2, 3))
            await user_message.edit(
                content=lang.PARSEFEST_ACTION.format(
                    mention=user.mention, index=i + 1, action=target_action, emoji=target_emoji
                )
            )
            start_time = time.time()
            clicked, _ = await messages.wait_for_reaction(
                self.bot, user_message, available_actions, member=user, timeout=3.0, add=False
            )
            if clicked is None:
                await channel.send(lang.PARSEFEST_MISSED.format(name=user.display_name), delete_after=5)
                reaction_times.append(3.0)
                continue
            react_time = time.time() - start_time
            if clicked != target_emoji:
                react_time += 1.0  # wrong-emoji penalty
            reaction_times.append(react_time)
            await user_message.remove_reaction(clicked, user)

        # 3. Score, save, and update records.
        average = sum(reaction_times) / len(reaction_times)
        final_parse = int((config_py.max_parse_championship + dps_mod) * max(0, 1 - average / 3))

        world_record = config_py.parses.find_one({"Championship Parse": 1}, sort=[("Parse", -1)])
        current_wr = world_record["Parse"] if world_record else 0

        config_py.parses.insert_one(
            {
                "Name": user.display_name,
                "ID": user.id,
                "Date": date.today().isoformat(),
                "Parse": final_parse,
                "Championship Parse": 1,
                "Difficulty Level": chosen_level,
            }
        )
        if final_parse > user_data["best_parse"]:
            user_data["best_parse"] = final_parse
            user_data["difficulty"] = chosen_level

        new_wr = ""
        if final_parse > current_wr:
            new_wr = " **WR**"
            embed = self.main_message.embeds[0]
            embed.description = lang.PARSEFEST_WR_UPDATE.format(parse=final_parse, name=user.display_name, difficulty=chosen_level)
            await self.main_message.edit(embed=embed)

        await channel.send(
            lang.PARSEFEST_DPS.format(name=user.display_name, parse=final_parse, wr=new_wr, difficulty=chosen_level),
            delete_after=5,
        )
        await user_message.delete()
        await self.update_main_message(user)

    async def update_main_message(self, user: discord.User) -> None:
        """Re-render the participants/scores field, sorted by DPS."""
        embed = self.main_message.embeds[0]
        data = self.parse_data[user.id]
        current_text = embed.fields[0].value
        difficulty_display = f" (Difficulty: {data['difficulty']})" if data["attempts"] > 0 else ""
        line = (
            f"{user.display_name}: {data['best_parse']} DPS "
            f"(Attempts: {data['attempts']}/{self.max_attempts}){difficulty_display}"
        )

        if user.display_name in current_text:
            current_text = re.sub(
                rf"{re.escape(user.display_name)}: \d+ DPS \(Attempts: \d+/{self.max_attempts}\)(?: \(Difficulty: .+\))?",
                line,
                current_text,
            )
        elif current_text == "No one yet!":
            current_text = line
        else:
            current_text += f"\n{line}"

        sorted_lines = sorted(
            current_text.splitlines(), key=lambda x: int(re.search(r"(\d+) DPS", x).group(1)), reverse=True
        )
        embed.set_field_at(0, name=lang.PARSEFEST_SCORES, value="\n".join(sorted_lines), inline=False)

        if not self.signups_open and all(
            self.parse_data[uid]["attempts"] >= self.max_attempts for uid in self.participants
        ):
            embed.title = lang.PARSEFEST_FINAL_TITLE
            embed.description = lang.PARSEFEST_FINAL_DESCRIPTION

        await self.main_message.edit(embed=embed)


async def setup(bot):
    await bot.add_cog(ParseTournament(bot))
