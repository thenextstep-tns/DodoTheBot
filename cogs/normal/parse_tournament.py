import json
import os
import random
import sys
import asyncio
import inspirobot
import cat
import numpy as np
import io
import sqlite3
import csv
import bson
import datetime
import time
import uuid
from bson import ObjectId

import urllib.request
from urllib.request import urlopen

import re
import requests
import pymongo
from pymongo import MongoClient

import aiohttp
import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands, tasks
from disnake.ext.commands import Context
from disnake.ui import Select, View
from disnake import Interaction
from datetime import date
from collections import defaultdict

from helpers import checks
import PIL
from PIL import Image

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

connection = sqlite3.connect("dodo.db")
cursor = connection.cursor()

class ParseTournament(commands.Cog, name="Parse Tournament"):
    def __init__(self, bot):
        self.bot = bot
        self.reset_state()

    def reset_state(self):
        """Reset the state of the tournament."""
        self.parse_data = defaultdict(lambda: {"attempts": 0, "best_parse": 0, "difficulty": ""})
        self.main_message = None  # Store the main message here
        self.participants = {}
        self.signups_open = True  # Flag to track if signups are open
        self.max_attempts = 0  # Default max attempts per user

    @commands.command(name="parse", description="Parse the dummy and see the result!")
    async def start_championship(self, ctx, max_attempts: int=1):
        # Validate the max_attempts parameter
        if not max_attempts:
            max_attempts = 1
        if max_attempts < 1 or max_attempts > 3:
            await ctx.send("The number of attempts must be between 1 and 3. Usage: dodo parsefest <number_of_attempts>")
            return

        # Reset state when the command is invoked
        self.reset_state()
        self.max_attempts = max_attempts

        # Initialize the main message
        embed = disnake.Embed(
            title="Dodos Parse Championship",
            description=f"React with ✅ to participate! You have 20 seconds to join.\nEach player has {self.max_attempts} attempts.",
            color=config_py.warning
        )
        embed.add_field(name="Participants", value="No one yet!", inline=False)
        self.main_message = await ctx.send(embed=embed)
        await self.main_message.add_reaction("✅")
        
        # Schedule the removal of the reaction after 20 seconds
        self.remove_reaction_task.start()

#    @start_championship.error
#    async def start_championship_error(self, ctx, error):
#        if isinstance(error, commands.MissingRequiredArgument):
#            await ctx.send("You must specify the number of attempts for each player. Usage: dodo parsefest <number_of_attempts>")

    @tasks.loop(seconds=20, count=1)
    async def remove_reaction_task(self):
        if self.main_message:
            await asyncio.sleep(20)
            self.signups_open = False  # Close signups

            # Fetch the current world record from the database
            world_record = config_py.parses.find_one(
                {"Championship Parse": 1}, 
                sort=[("Parse", -1)]
            )
            world_record_display = (
                f"World Record: {world_record['Parse']} DPS by {world_record['Name']}"
                if world_record else "No world record set yet."
            )

            # Update the embed to show the world record
            embed = self.main_message.embeds[0]
            embed.description = world_record_display
            await self.main_message.edit(embed=embed)

            await self.main_message.clear_reactions()
            await self.main_message.add_reaction("🎯")  # Add the target emoji for attempts

    @commands.command(name="stopfest")
    @commands.is_owner()
    async def stop_championship(self, ctx):
        """Command to stop the parsefest."""
        self.reset_state()
        await ctx.send("The parsefest has been stopped.")
        if self.main_message:
            await self.main_message.clear_reactions()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if self.signups_open and str(reaction.emoji) == "✅":
            if user.bot:
                return
            if user.id not in self.participants:
                self.participants[user.id] = user
                await self.update_main_message(user)
        elif not self.signups_open and str(reaction.emoji) == "🎯":
            if user.bot or user.id not in self.participants:
                return
            if self.parse_data[user.id]["attempts"] < self.max_attempts:
                await self.single_parse_attempt(user)
                await reaction.message.remove_reaction("🎯", user)  # Remove the user's target reaction after each attempt

    async def single_parse_attempt(self, user):
        channel = self.main_message.channel
        user_data = self.parse_data[user.id]

        if user_data["attempts"] >= self.max_attempts:
            await channel.send(f"{user.display_name}, you've already used all your attempts!", delete_after=5)
            return

        user_data["attempts"] += 1

        # Difficulty levels and corresponding changes
        difficulty_levels = {
            "1️⃣": {"actions": 3, "dps_mod": -35000},
            "2️⃣": {"actions": 4, "dps_mod": -25000},
            "3️⃣": {"actions": 5, "dps_mod": 0},
            "4️⃣": {"actions": 7, "dps_mod": 25000},
            "5️⃣": {"actions": 9, "dps_mod": 40000}
        }

        actions = {
            "⚔️": "Sword attack",
            "🪄": "Magic attack",
            "🛡️": "Block",
            "🏃": "Dodge",
            "😵": "Pretend to be dead",
            "🙏": f"Pray to the DPS deity - {random.choice(['Tea', 'Ellander', 'Deniz', 'Keegan', 'Ducky', 'NukeDuck', 'Strader'])}",
            "😕": "Confuse the boss",
            "💃": "Dance a crazy dance",
            "🌿": "Hide in the nearest bush"
        }

        # Ask the user to choose difficulty
        difficulty_message = await channel.send(
            f"{user.display_name}, choose your difficulty level:\n"
            "1️⃣ - Easy (-2 actions, -35000 from max DPS)\n"
            "2️⃣ - Medium (-1 action, -25000 from max DPS)\n"
            "3️⃣ - Baseline (5 actions, no changes)\n"
            "4️⃣ - Very Hard (+2 actions, +25000 to max DPS)\n"
            "5️⃣ - Insane (+4 actions, +40000 to max DPS)"
        )

        for emoji in difficulty_levels.keys():
            await difficulty_message.add_reaction(emoji)

        def check_difficulty(r, u):
            return u == user and str(r.emoji) in difficulty_levels

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=15.0, check=check_difficulty)
            chosen_level = str(reaction.emoji)
            selected_difficulty = difficulty_levels[chosen_level]
        except asyncio.TimeoutError:
            await channel.send(f"{user.display_name}, you took too long to choose! Defaulting to the normal difficulty.", delete_after=5)
            selected_difficulty = difficulty_levels["3️⃣"]  # Default to baseline if no choice is made

        await difficulty_message.delete()

        num_actions = selected_difficulty["actions"]
        dps_mod = selected_difficulty["dps_mod"]

        # Filter the actions to only include those that are within the difficulty level
        available_actions = dict(list(actions.items())[:num_actions])

        user_message = await channel.send(f"{user.display_name}, prebuff and get ready to parse!")
        for emoji in available_actions.keys():
            await user_message.add_reaction(emoji)

        await asyncio.sleep(2)

        await user_message.edit(content=f"{user.display_name}, click the right emoji as fast as you can once you see it here!")

        reaction_times = []
        for i in range(num_actions):  # Use the chosen number of actions
            chosen_emoji, chosen_action = random.choice(list(available_actions.items()))
            await asyncio.sleep(random.uniform(2, 3))
            await user_message.edit(content=f"{user.mention}, click the right emoji as fast as you can once you see it here!\nAction #{i+1}: {chosen_action} ({chosen_emoji})")

            start_time = time.time()
            try:
                reaction, react_user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=3.0,
                    check=lambda r, u: u == user and str(r.emoji) in available_actions
                )
                reaction_time = time.time() - start_time
                reaction_times.append(reaction_time)

                if str(reaction.emoji) != chosen_emoji:
                    # Penalize for wrong emoji
                    reaction_times[-1] += 1.0  # Add 1 second penalty

                await user_message.remove_reaction(reaction.emoji, user)  # Remove user's reaction after each action
            except asyncio.TimeoutError:
                await channel.send(f"{user.display_name}, you missed the action!", delete_after=5)
                reaction_times.append(3.0)  # Max time if missed

        average_reaction_time = sum(reaction_times) / len(reaction_times)
        final_parse = int((config_py.max_parse_championship + dps_mod) * max(0, 1 - average_reaction_time / 3))

        # Fetch the current world record for comparison
        current_world_record = config_py.parses.find_one(
            {"Championship Parse": 1}, 
            sort=[("Parse", -1)]
        )
        current_wr = current_world_record["Parse"] if current_world_record else 0

        # Save the result to the database
        parses = config_py.parses
        today = date.today().isoformat()
        parseobj = {
            "Name": user.display_name,
            "ID": user.id,
            "Date": today,
            "Parse": final_parse,
            "Championship Parse": 1,
            "Difficulty Level": chosen_level
        }
        parses.insert_one(parseobj)

        # Update the best parse and difficulty level
        if final_parse > user_data["best_parse"]:
            user_data["best_parse"] = final_parse
            user_data["difficulty"] = chosen_level

        # Check if a new world record was set
        new_world_record = ""
        if final_parse > current_wr:
            new_world_record = " **WR**"
            # Update the main embed with the new world record
            embed = self.main_message.embeds[0]
            embed.description = f"World Record: {final_parse} DPS by {user.display_name} (Difficulty: {chosen_level})"
            await self.main_message.edit(embed=embed)

        await channel.send(f"{user.display_name}, your DPS was: {final_parse}{new_world_record} (Difficulty: {chosen_level})", delete_after=5)
        await user_message.delete()

        await self.update_main_message(user)

    async def update_main_message(self, user):
        embed = self.main_message.embeds[0]
        participants_field = embed.fields[0]

        # Update or add the participant's score
        current_text = participants_field.value

        difficulty_display = f" (Difficulty: {self.parse_data[user.id]['difficulty']})" if self.parse_data[user.id]["attempts"] > 0 else ""

        if user.display_name in current_text:
            # Update existing participant score with attempts and difficulty
            current_text = re.sub(
                rf"{user.display_name}: \d+ DPS \(Attempts: \d+/{self.max_attempts}\)(?: \(Difficulty: .+\))?",
                f"{user.display_name}: {self.parse_data[user.id]['best_parse']} DPS (Attempts: {self.parse_data[user.id]['attempts']}/{self.max_attempts}){difficulty_display}",
                current_text
            )
        else:
            # Add new participant
            if current_text == "No one yet!":
                current_text = f"{user.display_name}: {self.parse_data[user.id]['best_parse']} DPS (Attempts: {self.parse_data[user.id]['attempts']}/{self.max_attempts}){difficulty_display}"
            else:
                current_text += f"\n{user.display_name}: {self.parse_data[user.id]['best_parse']} DPS (Attempts: {self.parse_data[user.id]['attempts']}/{self.max_attempts}){difficulty_display}"

        # Sort the scores in descending order based on DPS
        participants_list = sorted(
            current_text.splitlines(),
            key=lambda x: int(re.search(r"(\d+) DPS", x).group(1)),
            reverse=True
        )
        sorted_text = "\n".join(participants_list)

        embed.set_field_at(0, name="Participants and Scores", value=sorted_text, inline=False)

        if not self.signups_open and all(self.parse_data[uid]["attempts"] >= self.max_attempts for uid in self.participants):
            embed.title = "Dodos Parse Championship - Final Results"
            embed.description = "Here are the final results of the parse competition."

        await self.main_message.edit(embed=embed)

def setup(bot):
    bot.add_cog(ParseTournament(bot))
