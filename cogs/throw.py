"""
Version 1.1
"""

import json
import os
import random
import sys
import asyncio
import requests
import math
from datetime import datetime

import pymongo

import aiohttp
import disnake
from disnake.ext import commands

from helpers import checks

# Configuration
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

if not os.path.isfile("lang.py"):
    sys.exit("Language not found! Please add it and try again.")
else:
    import lang

class Throw(commands.Cog, name="throw"):
    def __init__(self, bot):
        self.bot = bot

#############################################
#              DODO THROW                   #
#############################################
    @commands.command(name="throw")
    async def dodothrow(self, ctx, member: disnake.Member):
        throwing_power_collection = config_py.user_power
        throwing_results_collection = config_py.throws

        # Step 1: Pick up and charge throw - math puzzle
        num1 = random.randint(3, 12)
        num2 = random.randint(53, 95)
        num3 = random.randint(2, 8)
        correct_answer = num1 * num2 * num3
        timeout_time = 5

        # Send initial message with puzzle
        puzzle_message = await ctx.send(f"To charge your throw, solve this puzzle within {timeout_time} seconds: {num1} * {num2} * {num3}")

        # Countdown before timeout, running concurrently
        countdown_task = asyncio.create_task(self.countdown(ctx, puzzle_message, num1, num2, num3, timeout_time))

        # Define the check function to ensure we only accept messages from the user in the right context
        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit()

        try:
            # Wait for the user's message input, but only accept numbers
            msg = await self.bot.wait_for('message', check=check, timeout=timeout_time)
            user_answer = int(msg.content)
            # Cancel the countdown once the answer is received
            countdown_task.cancel()
        except asyncio.TimeoutError:
            await puzzle_message.edit(content=f"{ctx.author.mention}, you took too long!")
            return
        except ValueError:
            await puzzle_message.edit(content=f"{ctx.author.mention}, that was not a valid number!")
            return

        # Step 2: Calculate the angle based on answer (Physics Based Calculation)
        g = 9.8  # Gravity constant in m/s^2

        # Calculate the ideal angle based on physics
        angle = 45
        if user_answer > correct_answer:
            angle = min(90, 45 + (user_answer - correct_answer) / correct_answer * 45)
        elif user_answer < correct_answer:
            angle = max(0, 45 - (correct_answer - user_answer) / correct_answer * 45)

        # Convert angle to radians for calculation
        angle_radians = math.radians(angle)

        # Step 3: Calculate the throw distance based on the angle
        max_distance = 5  # Maximum throw distance at 45 degrees
        distance = max_distance * math.sin(2 * angle_radians)  # Distance proportionally reduced by the angle

        # Fetch player's throwing power from the database (Power as initial velocity)
        player_data = throwing_power_collection.find_one({"_id": ctx.author.id})
        thrower_power = player_data["power"] if player_data else 1.0

        # Fetch target's power (the person being thrown)
        target_data = throwing_power_collection.find_one({"_id": member.id})
        target_power = target_data["power"] if target_data else 1.0

        # Modify the distance based on thrower's power (scales distance)
        total_force = distance * thrower_power

        # Step 4: Edit to show correct answer and prepare for throw
        gif_url = "https://tenor.com/bkIHP.gif"
        await puzzle_message.edit(content=f"The correct answer was {correct_answer}!\nTHROWING {member.mention} AT AN ANGLE OF {round(angle, 2)} degrees...\n{gif_url}")

        # Step 5: Keep the GIF on screen and simulate the throw with delay (3-5 seconds)
        await asyncio.sleep(random.randint(3, 5))

        # Step 6: Calculate landing and funny description
        landing_result = self.calculate_landing(total_force)
        funny_description = self.construct_funny_description(member)

        # Save results to the database with the current date
        throwing_results_collection.insert_one({
            "thrower_id": ctx.author.id,
            "target_id": member.id,
            "distance": landing_result,
            "date": datetime.utcnow()
        })

        # Step 7: Adjust power - increase for thrower, decrease for target
        power_increase = 0.05
        new_thrower_power = thrower_power + power_increase
        new_target_power = max(0, target_power - power_increase)  # Ensure target power doesn't go below zero

        throwing_power_collection.update_one(
            {"_id": ctx.author.id}, 
            {"$set": {"power": new_thrower_power}}, 
            upsert=True
        )
        throwing_power_collection.update_one(
            {"_id": member.id}, 
            {"$set": {"power": new_target_power}}, 
            upsert=True
        )

        # Step 8: Edit final results in the same message
        await puzzle_message.edit(content=f"{member.mention} landed {round(landing_result, 2)} meters away!\n{funny_description}\n"
                                          f"{ctx.author.mention}'s power increased to {round(new_thrower_power, 2)}!\n"
                                          f"{member.mention}'s power decreased to {round(new_target_power, 2)}.")

    # Countdown function to handle message updates
    async def countdown(self, ctx, puzzle_message, num1, num2, num3, timeout_time):
        try:
            for i in range(timeout_time, 0, -1):
                await puzzle_message.edit(content=f"To charge your throw, solve this puzzle: {num1} * {num2} * {num3}\nTime left: {i} seconds")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass  # Allow the countdown to be cancelled

    def calculate_landing(self, force):
        # Simple formula: force results in distance (this can be more complex)
        return force * random.uniform(0.8, 1.2)

    def construct_funny_description(self, member):
        # Parts of the description to be randomized
        part1 = [
            f"{member.mention} was launched with tremendous force!",
            f"{member.mention} was thrown into the great unknown!",
            f"{member.mention} took off like a rocket!"
        ]

        part2 = [
            "They were seen soaring through the sky,",
            "They disappeared into the clouds,",
            "They flew straight past the stratosphere,"
        ]

        part3 = [
            "defying all known laws of physics.",
            "creating a new constellation in the process.",
            "breaking the sound barrier on the way."
        ]

        part4 = [
            "Authorities are still investigating the exact trajectory.",
            "It's unlikely they'll return anytime soon.",
            "Observers are in shock and awe."
        ]

        # Construct the final description by randomly choosing one from each part
        return f"{random.choice(part1)} {random.choice(part2)} {random.choice(part3)} {random.choice(part4)}"
    
def setup(bot):
    bot.add_cog(Throw(bot))
