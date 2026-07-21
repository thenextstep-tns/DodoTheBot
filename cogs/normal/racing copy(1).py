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
import math
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

class Racing(commands.Cog, name="Racing"):
    def __init__(self, bot):
        self.bot = bot

    ############# NEW MOUSE #################
    @commands.command(name="newmouse", description="Add a new mouse name and choose a class")
    async def newmouse(self, context, *, mouse_name: str):
        """
        Adds a new mouse name and allows the user to choose a class
        """
        # Check if the mouse name already exists
        if config_py.user_mice.find_one({'name': mouse_name}):
            await context.send(f"The mouse name '{mouse_name}' already exists in the list.")
            return

        # Get the available classes from the database
        classes = list(config_py.mouse_classes.find())
        class_emojis = {c['emoji']: c['name'] for c in classes}
        
        # Send a message with reactions for each class
        class_message = await context.send(
            "Choose a class for your mouse:\n" +
            "\n".join([f"{c['emoji']} {c['name']}: {c['description']}" for c in classes])
        )

        for emoji in class_emojis:
            await class_message.add_reaction(emoji)

        def check(reaction, user):
            return user == context.author and str(reaction.emoji) in class_emojis

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            mouse_class = class_emojis[str(reaction.emoji)]

            # Add the new mouse name and class to the database
            config_py.user_mice.insert_one({'user_id': context.author.id, 'name': mouse_name, 'class': mouse_class})

            await context.send(f"The mouse name '{mouse_name}' with class '{mouse_class}' has been added to the list.")
        except asyncio.TimeoutError:
            await context.send("You took too long to choose a class. Please try again.")

    ############# MAIN RACE #################
    @commands.command(name="race", description="Challenge your guildies to a skeevaton race!")
    @checks.not_blacklisted()
    async def race(self, context, countdown: int = 20):
        """
        Starts a skeevatron race
        """
        race_starter = context.author
        track_length = random.randint(15, 45)
        race_name = f"{race_starter}'s race"
        race_message = await context.send(
            f"{race_starter.mention} started the race of {track_length} laps! You have {countdown} seconds to react and add your skeevaton to the race roster.\n"
            "React with 🐁 to join the race."
        )

        await race_message.add_reaction(u"\U0001F401")
        await self.update_race_message(race_message, race_starter, track_length, countdown)

        await asyncio.sleep(1)
        race_message = await context.channel.fetch_message(race_message.id)
        mouse_users = await self.get_reaction_users(race_message, u"\U0001F401")

        if not mouse_users:
            await context.send("No one joined the race. Race cancelled.")
            return

        user_mouse_names_classes = self.assign_mice_classes(mouse_users)
        
        await self.send_lineup_embed(race_message, context, user_mouse_names_classes)
        await self.run_race_lights(race_message, race_starter, track_length, user_mouse_names_classes)

        positions, completed_mice, finished_order = self.initialize_race(mouse_users)
        debug_log = []
        await self.run_race(context, race_message, race_starter, mouse_users, user_mouse_names_classes,
                            positions, completed_mice, track_length, finished_order, debug_log)

        race_results = self.calculate_race_results(finished_order)
        await self.send_race_summary(context, race_starter, user_mouse_names_classes, race_results)

        self.save_race_results(race_name, race_starter, user_mouse_names_classes, race_results)
        
        # NEW: After the race, update relationships based on results
        await self.update_relationships(context, race_results, user_mouse_names_classes)
        # NEW: Process adoption after relationship updates
        await self.adoption_check(context, user_mouse_names_classes)

    ############# GIGARACE #####################################
    @commands.command(name="gigarace", description="Challenge your guildies to a gigarace!")
    @checks.not_blacklisted()
    @checks.is_owner()
    async def gigarace(self, context):
        """
        Starts a gigarace with a full day countdown
        """
        race_starter = context.author
        announcement_channel = self.bot.get_channel(config_py.ANNOUNCEMENT_CHANNEL)
        track_length = 45
        race_name = f"{race_starter}'s gigarace"
        race_message = await announcement_channel.send(
            f"THE **GIGARACE** HAS JUST BEEN ANNOUNCED! You have 9 hours (32400 seconds) to react and add your skeevaton to the race roster.\n"
            "React with 🐁 to join the race.\n 1st place - 100 000 gold \n 2nd place - 50 000 gold \n 3rd place - 10 000 gold  "
        )
    
        await race_message.add_reaction(u"\U0001F401")
        # Full day countdown: 32400 seconds
        await self.update_gigarace_message(race_message, race_starter, track_length, 32400)
    
        await asyncio.sleep(1)
        race_message = await announcement_channel.fetch_message(race_message.id)
        mouse_users = await self.get_reaction_users(race_message, u"\U0001F401")
    
        if not mouse_users:
            await context.send("No one joined the gigarace. Race cancelled.")
            return
    
        user_mouse_names_classes = self.assign_mice_classes(mouse_users)
        
        await self.send_lineup_embed(race_message, context, user_mouse_names_classes)
        await self.run_race_lights(race_message, race_starter, track_length, user_mouse_names_classes)
    
        positions, completed_mice, finished_order = self.initialize_race(mouse_users)
        debug_log = []
        await self.run_race(context, race_message, race_starter, mouse_users, user_mouse_names_classes,
                            positions, completed_mice, track_length, finished_order, debug_log)
    
        race_results = self.calculate_race_results(finished_order)
        await self.send_race_summary(context, race_starter, user_mouse_names_classes, race_results)
    
        self.save_race_results(race_name, race_starter, user_mouse_names_classes, race_results)
        await self.update_relationships(context, race_results, user_mouse_names_classes)
        await self.adoption_check(context, user_mouse_names_classes)

    ############# HANDLING THE STARTER MESSAGE #################
    async def update_race_message(self, race_message, race_starter, track_length, time_left):
        end_time = time.time() + time_left
        while time.time() < end_time:
            remaining_time = int(end_time - time.time())
            await race_message.edit(content=(
                f"{race_starter.mention} started the race of {track_length} laps! You have {remaining_time} seconds "
                "to react and add your skeevaton to the race roster.\nReact with 🐁 to join the race."
            ))
            await asyncio.sleep(1)
            
    async def update_gigarace_message(self, race_message, race_starter, track_length, time_left):
        end_time = time.time() + time_left
        while time.time() < end_time:
            remaining_time = int(end_time - time.time())
            await race_message.edit(content=(
                f"THE **GIGARACE** HAS JUST BEEN ANNOUNCED! You have {remaining_time} seconds to react and add "
                "your skeevaton to the race roster.\nReact with 🐁 to join the race.\n "
                "1st place - 100 000 gold\n 2nd place - 50 000 gold\n 3rd place - 10 000 gold "
            ))
            await asyncio.sleep(100)

    ############# REACTIONS HANDLER #################
    async def get_reaction_users(self, race_message, emoji):
        for reaction in race_message.reactions:
            if str(reaction.emoji) == emoji:
                return [user async for user in reaction.users()]  # if not user.bot
        return []

    def assign_mice_classes(self, mouse_users):
        """
        Assigns a random mouse from the DB to each user who reacted.
        """
        available_mice = list(config_py.user_mice.find())
        random.shuffle(available_mice)
        assigned_mice_classes = {}
        for user in mouse_users:
            mouse = available_mice.pop()
            mouse_class = config_py.mouse_classes.find_one({"name": mouse['class']})
            if mouse_class:
                assigned_mice_classes[user.id] = {
                    "name": mouse['name'],
                    "class": mouse_class['name'],
                    "class_description": mouse_class['description']
                }
        return assigned_mice_classes

    async def send_lineup_embed(self, race_message, context, user_mouse_names_classes):
        line_up_embed = disnake.Embed(
            title="Race Line-up",
            description="The race is about to start!\n",
            color=0xFF0000,
        )
        for user_id, mouse_info in user_mouse_names_classes.items():
            user = context.guild.get_member(user_id)
            mouse_name = mouse_info["name"]
            mouse_class = mouse_info["class"]
            line_up_embed.add_field(
                name=f"{user.display_name}'s {mouse_name} ({mouse_class})",
                value="",
            )
        await race_message.edit(embed=line_up_embed, content="")

    async def run_race_lights(self, race_message, race_starter, track_length, user_mouse_names_classes):
        black_circle = u"\U000026AB"
        red_circle = u"\U0001F534"
        green_circle = u"\U0001F7E2"
        
        roster_description = "\n".join([
            f"{mouse_info['name']} ({mouse_info['class']})" for mouse_info in user_mouse_names_classes.values()
        ])

        lights_embed = disnake.Embed(
            title="Race is about to start!",
            description=(
                f"{roster_description}\n\n"
                "Reactions:\n"
                "🧀 Cheese: Increases your move by 1\n"
                "🍷 Wine: Multiplies your move by 2\n"
                "💣 Bomb: Drops everyone else back by 5"
            ),
            color=0xFFFF00
        )
        
        # Simple countdown lights
        for i in range(5):
            lights = [red_circle if j <= i else black_circle for j in range(5)]
            lights_text = ''.join(lights)
            lights_embed.set_footer(text=lights_text)
            await race_message.edit(embed=lights_embed)
            await asyncio.sleep(1)
        
        await asyncio.sleep(1)
        lights_text = ''.join([green_circle] * 5)
        lights_embed.set_footer(text=lights_text)
        lights_embed.description = f"{roster_description}\n\nGOOOO!!!"
        await race_message.edit(embed=lights_embed)

    def initialize_race(self, mouse_users):
        positions = {user.id: 0 for user in mouse_users}
        completed_mice = set()
        finished_order = []
        return positions, completed_mice, finished_order

    async def run_race(self, context, race_message, race_starter, mouse_users, user_mouse_names_classes,
                      positions, completed_mice, track_length, finished_order, debug_log):
        """
        Main race loop that handles random events, dice rolls, and finishing logic.
        """
        initial_players = len(mouse_users)
        bonus_roll_users = set()  # for cheese or wine events
        bomb_user = None
        bomb_effect_applied = False
        move_counter = 0
    
        green_flag = "## We are racing :mouse2:"
    
        # Mapping for adopted mouse owners (Starry Eyes event).
        adopted_owners = {}
        for user in mouse_users:
            mouse_name = user_mouse_names_classes[user.id]['name']
            doc = config_py.user_mice.find_one({"name": mouse_name})
            if doc and doc.get("adopted_by") == user.id:
                adopted_owners[user.id] = True
    
        # Dictionary to hold starry eyes boost (number of moves remaining)
        starry_boost = {}
    
        # NEW: For Bomb Dodger counters (up to 3 dodges).
        bomb_dodges_used = defaultdict(int)
    
        # NEW: Check if any Navigator is in the race (for treasure map event).
        any_navigator = any(info["class"] == "Navigator" for info in user_mouse_names_classes.values())
    
        while len(finished_order) < initial_players:
            await race_message.clear_reactions()
    
            event_roll = random.randint(1, 100)
            event_text = green_flag
    
            # --- POSSIBLE EVENTS ---
            # 1. Treasure Map (if a Navigator is present)
            if any_navigator and event_roll == 95:
                event_text = "## A Treasure Map just appeared! Click the map emoji to pick it up!"
                map_emoji = "🗺️"
                await race_message.add_reaction(map_emoji)
    
                def check_map(reaction, user):
                    return (str(reaction.emoji) == map_emoji and user in mouse_users and not user.bot)
    
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=2.0, check=check_map)
                    if user_mouse_names_classes[user.id]["class"] == "Navigator":
                        positions[user.id] += 20
                        debug_log.append(f"Move {move_counter + 1}: {user_mouse_names_classes[user.id]['name']} used the Treasure Map! +20 move.")
                    else:
                        debug_log.append(f"Move {move_counter + 1}: Mouse picked up a map but doesn't know how to read, so it just looks at it in confusion and nothing happens.")
                except asyncio.TimeoutError:
                    pass
                finally:
                    await race_message.clear_reaction(map_emoji)
    
            # 2. Starry Eyes (for adopted mice)
            elif 81 <= event_roll <= 82 and adopted_owners:
                event_text = "## Starry Eyes! Click ✨ to inspire your mouse!"
                await race_message.edit(content=event_text)
                star_owner = await self.starry_eyes_event(race_message, mouse_users, adopted_owners)
                if star_owner:
                    starry_boost[star_owner.id] = config_py.STAR_INSPIRATION_DURATION
    
            # 3. Cheese Event
            elif 86 <= event_roll <= 88:
                event_text = "## Cheese appeared! Click the cheese emoji to grab it!"
                await race_message.edit(content=event_text)
                bonus_user = await self.cheese_event(context, race_message, mouse_users, race_starter)
                if bonus_user:
                    bonus_roll_users.add(bonus_user)
    
            # 4. Wine Event
            elif 89 <= event_roll <= 92:
                event_text = "## Wine appeared! Click the wine emoji to grab it!"
                await race_message.edit(content=event_text)
                bonus_user = await self.wine_event(context, race_message, mouse_users, race_starter)
                if bonus_user:
                    bonus_roll_users.add(bonus_user)
    
            # 5. Bomb Event
            elif 93 <= event_roll <= 94:
                event_text = "## Bomb appeared! Click the bomb emoji to grab it!"
                await race_message.edit(content=event_text)
                bomb_user = await self.bomb_event(context, race_message, mouse_users, race_starter)
                bomb_effect_applied = False
            else:
                await asyncio.sleep(1)
    
            # --- PER-USER MOVE LOGIC ---
            for user in mouse_users:
                if user.id not in completed_mice:
                    roll = self.roll_dice()  # possible outcomes: -1, 1, 2, 3
    
                    mouse_info = user_mouse_names_classes[user.id]
                    mouse_class = mouse_info["class"]
                    debug_message = f"Move {move_counter + 1}: {mouse_info['name']}: {roll} "
    
                    # --- Lucky Mouse: pick a random class bonus each turn ---
                    # Use the DB reference from config_py.mouse_classes
                    class_data = config_py.mouse_classes.find_one({"name": mouse_class})
                    if mouse_class == "Lucky Mouse":
                        all_classes = list(config_py.mouse_classes.find({"name": {"$ne": "Lucky Mouse"}}))
                        if all_classes:
                            random_class = random.choice(all_classes)
                            debug_message += f"[Lucky Mouse: randomly got {random_class['name']}!] "
                            # For this move, override the class_data with the random bonus
                            class_data = random_class
    
                    # --- Apply Starry Eyes boost if active ---
                    if user.id in starry_boost and starry_boost[user.id] > 0:
                        roll += config_py.STAR_INSPIRATION_BOOST
                        debug_message += f"({mouse_info['name']} got a +{config_py.STAR_INSPIRATION_BOOST} starry boost!) "
                        starry_boost[user.id] -= 1
                        if starry_boost[user.id] == 0:
                            del starry_boost[user.id]
    
                    # Store the pre-event roll for Wine Connoisseur logic
                    pre_event_roll = roll
    
                    # --- Cheese Event Logic ---
                    if user in bonus_roll_users and 86 <= event_roll <= 88:
                        roll += 1
                        debug_message += f"({mouse_info['name']} munched on cheese! +1) "
                        if "cheese_bonus" in class_data.get("bonus", {}):
                            cheese_bonus = class_data["bonus"]["cheese_bonus"]
                            roll += cheese_bonus
                            debug_message += f"(Cheese Seeker bonus +{cheese_bonus}!) "
    
                    # --- Wine Event Logic ---
                    if user in bonus_roll_users and 89 <= event_roll <= 92:
                        if mouse_class == "Wine Connoisseur":
                            if pre_event_roll < 0:
                                roll = 0
                                debug_message += f"(Wine Connoisseur negated negative roll to 0!) "
                            else:
                                doubled = pre_event_roll * 2
                                roll = doubled
                                debug_message += f"(Wine Connoisseur doubled roll from {pre_event_roll} to {roll}!) "
                        else:
                            roll = roll * 2
                            debug_message += f"(Wine event doubled the roll to {roll}!) "
    
                    # --- Bomb Event Logic ---
                    if bomb_user and user != bomb_user and 93 <= event_roll <= 94 and not bomb_effect_applied:
                        if class_data and class_data["name"] == "Bomb Dodger":
                            if bomb_dodges_used[user.id] < 3:
                                bomb_dodges_used[user.id] += 1
                                debug_message += f"({mouse_info['name']} dodged the bomb! {bomb_dodges_used[user.id]}/3) "
                            else:
                                bomb_damage = 5
                                roll -= bomb_damage
                                debug_message += f"({mouse_info['name']} couldn't dodge any more bombs and got hit by one, -{bomb_damage} => {roll}) "
                        elif class_data and "reduce_negative" in class_data.get("bonus", {}) and class_data["name"] == "Guardian":
                            bomb_damage = 5
                            half_damage = int(bomb_damage * class_data["bonus"]["reduce_negative"])
                            roll -= half_damage
                            debug_message += f"(Guardian halved bomb effect to -{half_damage} => {roll}) "
                        else:
                            roll -= 5
                            debug_message += f"({mouse_info['name']} got hit by a bomb => {roll}) "
    
                    if 93 <= event_roll <= 94:
                        bomb_effect_applied = True
                    
                    # --- Speedster Bonus ---
                    if "speed_bonus" in class_data.get("bonus", {}):
                        # Let's assume a 33% chance for the Speedster bonus
                        chance = random.randint(1, 100)
                        if chance <= 15:
                            bonus_amount = class_data["bonus"]["speed_bonus"]
                            roll += bonus_amount
                            debug_message += f"(Speedster triggered +{bonus_amount}!) "
                    
                    # --- Guardian Negative Mitigation ---
                    if class_data and "reduce_negative" in class_data.get("bonus", {}):
                        if roll < 0:
                            original_roll = roll
                            roll = math.ceil(roll * class_data["bonus"]["reduce_negative"])
                            debug_message += f"(Guardian halved negative roll from {original_roll} to {roll}) "
    
                    # --- Apply the final roll to the user's position ---
                    positions[user.id] += roll
                    if positions[user.id] > track_length:
                        positions[user.id] = track_length
    
                    # If only one mouse remains, force finish it.
                    if len(mouse_users) - len(completed_mice) == 1:
                        for remaining_user in mouse_users:
                            if remaining_user.id not in completed_mice:
                                positions[remaining_user.id] = track_length
                                completed_mice.add(remaining_user.id)
                                finished_order.append(remaining_user)
                                debug_message += f"({mouse_info['name']} forced finish!) "
                                break
    
                    # Check if the mouse just finished the race.
                    if positions[user.id] >= track_length and user.id not in completed_mice:
                        positions[user.id] = track_length
                        completed_mice.add(user.id)
                        finished_order.append(user)
                        debug_message += f"({mouse_info['name']} finished!) "
    
                    debug_log.append(debug_message)
    
            move_counter += 1
            # Always show the last 10 actions in the embed footer.
            await self.update_race_progress(race_message, race_starter, mouse_users, user_mouse_names_classes,
                                            positions, track_length, debug_log, event_text, move_counter)

    async def cheese_event(self, context, race_message, mouse_users, race_starter):
        cheese_emoji = u"\U0001F9C0"  # Unicode for cheese emoji

        await race_message.add_reaction(cheese_emoji)

        def check(reaction, user):
            return str(reaction.emoji) == cheese_emoji and user in mouse_users and not user.bot

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=2.0, check=check)
            await race_message.remove_reaction(cheese_emoji, user)
            await race_message.remove_reaction(cheese_emoji, self.bot.user)
            return user  # Return the user who clicked the cheese
        except asyncio.TimeoutError:
            await race_message.clear_reaction(cheese_emoji)
            return None

    async def wine_event(self, context, race_message, mouse_users, race_starter):
        wine_emoji = u"\U0001F377"  # Unicode for wine emoji

        await race_message.add_reaction(wine_emoji)

        def check(reaction, user):
            return str(reaction.emoji) == wine_emoji and user in mouse_users and not user.bot

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=2.0, check=check)
            await race_message.remove_reaction(wine_emoji, user)
            await race_message.remove_reaction(wine_emoji, self.bot.user)
            return user  # Return the user who clicked the wine
        except asyncio.TimeoutError:
            await race_message.clear_reaction(wine_emoji)
            return None

    async def bomb_event(self, context, race_message, mouse_users, race_starter):
        bomb_emoji = u"\U0001F4A3"  # Unicode for bomb emoji

        await race_message.add_reaction(bomb_emoji)

        def check(reaction, user):
            return str(reaction.emoji) == bomb_emoji and user in mouse_users and not user.bot

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=2.0, check=check)
            await race_message.remove_reaction(bomb_emoji, user)
            await race_message.remove_reaction(bomb_emoji, self.bot.user)
            return user
        except asyncio.TimeoutError:
            await race_message.clear_reaction(bomb_emoji)
            return None

    def roll_dice(self):
        roll = random.randint(0, 10)
        if roll <= 1:
            return -1
        elif 1 < roll <= 7:
            return 1
        elif 7 < roll <= 9:
            return 2
        else:
            return 3

    async def update_race_progress(self, race_message, race_starter, mouse_users, user_mouse_names_classes,
                                   positions, track_length, debug_log, event_text, move_counter):
        mouse_emoji = u"\U0001F401"
        race_lines = [
            f"{user.mention}'s {user_mouse_names_classes[user.id]['name']} \n"
            f":triangular_flag_on_post: {''.join(['-' if i != positions[user.id] else mouse_emoji for i in range(track_length)])} :checkered_flag:"
            for user in mouse_users
        ]
        race_description = "\n".join(race_lines)
        race_embed = disnake.Embed(
            title=f"THE SKEEVATON RACE IS ON!",
            description=f"{race_starter.mention}'s race:\nMove {move_counter}\n{race_description}",
            color=0x00ff00,
        )
        # Show last 10 debug log messages.
        last_10_actions = debug_log[-10:]
        footer_text = "\n".join(last_10_actions)
        race_embed.set_footer(text=footer_text)
        await race_message.edit(embed=race_embed, content=event_text)

    def calculate_race_results(self, finished_order):
        race_results = {user: {"position": i + 1, "points": self.get_points(i)} for i, user in enumerate(finished_order)}
        return race_results

    def get_points(self, position):
        points = [10, 6, 4, 3, 2, 1]
        return points[position] if position < 6 else 0

    async def send_race_summary(self, context, race_starter, user_mouse_names_classes, race_results):
        summary_message = f"The race has ended!\nRace Results:\n"
        for user, result in race_results.items():
            summary_message += f"{user.mention}'s {user_mouse_names_classes[user.id]['name']} - {result['points']} points\n"
        await context.send(summary_message)

    def save_race_results(self, race_name, race_starter, user_mouse_names_classes, race_results):
        race_data = {
            "race_name": race_name,
            "race_starter_id": race_starter.id,
            "participants": [
                {
                    "user_id": user.id,
                    "mouse_name": user_mouse_names_classes[user.id]['name'],
                    "position": result['position'],
                    "points": result['points'],
                    "is_winner": result['position'] <= 6,
                }
                for user, result in race_results.items()
            ],
        }
        config_py.races.insert_one(race_data)

    # ================================
    # NEW FUNCTIONS: Relationship, Adoption, Starry Eyes & Cheese Drop
    # ================================
    async def mousechat(self, context, *, message):
        """
        Chat to DodoGPT.
        This function sends the given message to the DodoGPT chat API and relays the response.
        """
        import openai
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        openai.api_key = config_py.PROXY_API
        print("We started talking")
        openai.api_base = "https://api.proxyapi.ru/openai/v1"
        
        response_messages = []
    
        chat_completion = openai.ChatCompletion.create(
            model="gpt-4o", 
            temperature=1, 
            messages=[
                {"role": "system", "content": f"You return the message in the form of direct speech playing your role:"},
                {"role": "user", "content": f"{message}"}
            ]
        )
    
        response_content = chat_completion.choices[0].message.content
        
        while response_content:
            chars_to_send = min(len(response_content), 1990)
            response_message = response_content[:chars_to_send]
            response_content = response_content[chars_to_send:]
            response_messages.append(response_message)
    
        for response_message in response_messages:
            await context.send(response_message)

    async def update_relationships(self, context, race_results, user_mouse_names_classes):
        """
        After each race, calculates and updates relationship points.
        For 2 mice: winner gets +10 and loser gets -10.
        For 3+ mice: 
          - Top half (positions 1 to floor(N/2)) get positive points as:
              ceil((RELATIONSHIP_BASE_POINTS / finish position) * number_of_participants)
          - If odd, the middle position (floor(N/2)+1) gets 0.
          - Bottom half get exactly -1/4 of the points of their mirror (mirror = (N + 1 - position)).
        Updates the mouse document's "Relationship" field and sends an embed message listing updates.
        """
        import math
    
        message_lines = []
        participants_count = len(race_results)
        base_points = config_py.RELATIONSHIP_BASE_POINTS
    
        # Build a points distribution mapping: finish position -> points_gained
        points_distribution = {}
    
        if participants_count == 2:
            # Special case for 2 mice: clear winner and loser.
            points_distribution[1] = 10
            points_distribution[2] = -10
        else:
            # Determine top half size (integer division)
            top_half_size = participants_count // 2
    
            # Award positive points for top half using the original formula.
            for pos in range(1, top_half_size + 1):
                points_distribution[pos] = math.ceil((base_points / pos) * participants_count)
    
            # For odd number of participants, assign the middle position 0 points.
            if participants_count % 2 == 1:
                middle_pos = top_half_size + 1
                points_distribution[middle_pos] = 0
                bottom_start = top_half_size + 2
            else:
                bottom_start = top_half_size + 1
    
            # For positions in the bottom half, mirror the corresponding top-half position.
            for pos in range(bottom_start, participants_count + 1):
                mirror_pos = participants_count + 1 - pos
                mirrored_points = points_distribution.get(mirror_pos, 0)
                # Bottom half gets exactly negative one quarter of the mirrored top-half points.
                points_distribution[pos] = int(round(-0.25 * mirrored_points))
    
        # Loop through each user in the race and update their relationship points.
        for user in race_results:
            if getattr(user, "bot", False):
                continue
    
            pos = race_results[user]['position']
            points_gained = points_distribution.get(pos, 0)
            mouse_name = user_mouse_names_classes[user.id]['name']
            mouse_doc = config_py.user_mice.find_one({"name": mouse_name})
            rel_list = mouse_doc.get("Relationship", [])
            updated = False
    
            for entry in rel_list:
                if entry["user_id"] == user.id:
                    entry["relationship_points"] += points_gained
                    updated = True
                    break
    
            if not updated:
                rel_list.append({"user_id": user.id, "relationship_points": points_gained})
    
            config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"Relationship": rel_list}})
            message_lines.append(f"{user.mention} gains {points_gained} relationship points with **{mouse_name}**!")
    
        if message_lines:
            embed = disnake.Embed(title="Relationship Points Adjusted", color=config_py.main_color)
            embed.description = "\n".join(message_lines)
            await context.send(embed=embed)

    async def adoption_check(self, context, user_mouse_names_classes):
        """
        After relationships are updated, checks if any mouse has reached the adoption threshold.
        If so, pings the owner and uses mousechat to send a heartwarming, meme-style message.
        The owner can react with 👍 or 👎. If mouse is already adopted, checks re-adoption conditions.
        """
        threshold = config_py.MOUSE_ADOPTION_RANK
        for user_id, info in user_mouse_names_classes.items():
            user = self.bot.get_user(user_id)
            user_name = user.name
            mouse_name = info['name']
            mouse_doc = config_py.user_mice.find_one({"name": mouse_name})
            rel_list = mouse_doc.get("Relationship", [])
            user_points = next((entry["relationship_points"] for entry in rel_list if entry["user_id"] == user_id), 0)

            if user_points >= threshold and not mouse_doc.get("adopted_by"):
                prompt = (
                    f"You are a little {mouse_name}, and your relationship with {user_name} just reached a new height! "
                    "Look at tham with sad, hopeful eyes and ask them in the mousy cutest way possible to adopt you. "
                    "When prompted for adoption, return your message strictly in the following format: "
                    "**Name of the mouse**: Your direct speech. Don't add any additional text"
                )
                await self.mousechat(context, message=prompt)
                adopt_msg = await context.send(
                    f"{user.mention}, do you want to adopt {mouse_name}? React with 👍 for yes or 👎 for no."
                )
                await adopt_msg.add_reaction("👍")
                await adopt_msg.add_reaction("👎")
                try:
                    reaction, reactor = await self.bot.wait_for(
                        'reaction_add',
                        timeout=20.0,
                        check=lambda r, u: u == user and str(r.emoji) in ["👍", "👎"]
                    )
                except asyncio.TimeoutError:
                    await adopt_msg.clear_reactions()
                    continue
                if str(reaction.emoji) == "👍":
                    config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"adopted_by": user.id}})
                    await context.send(f"**{mouse_name}** happily chirps that it will serve you with all its smol heart!")
                else:
                    config_py.user_mice.update_one(
                        {"name": mouse_name, "Relationship.user_id": user_id},
                        {"$inc": {"Relationship.$.relationship_points": -500}}
                    )
                    await context.send(
                        f"{mouse_name} is heartbroken... :pleading_face: it slinks away and hides in shame and neglect. :broken_heart:"
                    )
                await adopt_msg.clear_reactions()

            elif user_points >= threshold and mouse_doc.get("adopted_by") and mouse_doc.get("adopted_by") != user_id:
                current_owner = mouse_doc["adopted_by"]
                current_owner_points = next((entry["relationship_points"] for entry in rel_list if entry["user_id"] == current_owner), 0)
                if current_owner_points < threshold:
                    prompt = (
                        f"{mouse_name} feels neglected by its current owner and turns to you with pleading eyes. "
                        f"It wonders if you'll adopt it instead!"
                    )
                    await self.mousechat(context, message=prompt)
                    adopt_msg = await context.send(
                        f"{user.mention}, do you want to readopt {mouse_name}? React with 👍 for yes or 👎 for no."
                    )
                    await adopt_msg.add_reaction("👍")
                    await adopt_msg.add_reaction("👎")
                    try:
                        reaction, reactor = await self.bot.wait_for(
                            'reaction_add',
                            timeout=20.0,
                            check=lambda r, u: u == user and str(r.emoji) in ["👍", "👎"]
                        )
                    except asyncio.TimeoutError:
                        await adopt_msg.clear_reactions()
                        continue
                    if str(reaction.emoji) == "👍":
                        config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"adopted_by": user.id}})
                        await context.send(
                            f"{mouse_name} joyfully announces its readoption and vows to serve you faithfully!"
                        )
                    else:
                        config_py.user_mice.update_one(
                            {"name": mouse_name, "Relationship.user_id": user_id},
                            {"$inc": {"Relationship.$.relationship_points": -500}}
                        )
                        await context.send(
                            f"{mouse_name} is heartbroken... :pleading_face: it slinks away and hides in shame and neglect. :broken_heart:"
                        )
                    await adopt_msg.clear_reactions()

    async def starry_eyes_event(self, race_message, mouse_users, adopted_owners):
        """
        Handles the starry eyes event during races.
        Only owners of adopted mice (in adopted_owners) may trigger this event by clicking the ✨ emoji.
        Returns the user who triggered the event.
        """
        star_emoji = "✨"
        await race_message.add_reaction(star_emoji)
        def check(reaction, user):
            return (
                str(reaction.emoji) == star_emoji and user in mouse_users
                and not user.bot and user.id in adopted_owners
            )
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=2.0, check=check)
            await race_message.remove_reaction(star_emoji, user)
            await race_message.remove_reaction(star_emoji, self.bot.user)
            return user
        except asyncio.TimeoutError:
            await race_message.clear_reaction(star_emoji)
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listens for every message. With a random chance, the bot adds a cheese emoji to the message.
        The first user to click it gets +5 relationship points for a random mouse. If that meets
        the threshold, adoption is triggered.
        """
        if message.author.bot:
            return
        if random.randint(0, 1000) > config_py.CHEESE_DROP_THRESHOLD:
            try:
                await message.add_reaction("🧀")
                self.bot.loop.create_task(self.handle_cheese_drop(message))
            except Exception:
                pass
    
    async def handle_cheese_drop(self, message):
        """
        Waits for the first reaction on the cheese emoji (with a 3-second timeout), updates relationship points 
        for a random mouse, sends a confirmation embed, and triggers adoption if needed.
        """
        def check(reaction, user):
            return str(reaction.emoji) == "🧀" and not user.bot
    
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=3.0, check=check)
            mice = list(config_py.user_mice.find())
            if not mice:
                return
            chosen_mouse = random.choice(mice)
            rel_list = chosen_mouse.get("Relationship", [])
            updated = False
            for entry in rel_list:
                if entry["user_id"] == user.id:
                    entry["relationship_points"] += 5
                    updated = True
                    break
            if not updated:
                rel_list.append({"user_id": user.id, "relationship_points": 5})
            config_py.user_mice.update_one({"_id": chosen_mouse["_id"]}, {"$set": {"Relationship": rel_list}})
            notification_channel = self.bot.get_channel(config_py.PET_CHANNEL)
            embed = disnake.Embed(
                title="Cheese Collected!",
                description=(
                    f"{user.mention} collected a piece of magical cheese for {chosen_mouse['name']} "
                    f"and gained 5 relationship points!"
                ),
                color=config_py.success
            )
            await notification_channel.send(embed=embed)
            # Remove the cheese reaction from the clicking user after a short delay
            await asyncio.sleep(2)
            await reaction.message.remove_reaction("🧀", user)
            threshold = config_py.MOUSE_ADOPTION_RANK
            user_points = next((entry["relationship_points"] for entry in rel_list if entry["user_id"] == user.id), 0)
            if user_points >= threshold and not chosen_mouse.get("adopted_by"):
                await self.adoption_prompt_channel(message.channel, user, chosen_mouse["name"])
        except asyncio.TimeoutError:
            # Remove the cheese reaction from the message if no one clicked within 3 seconds
            try:
                await message.clear_reaction("🧀")
            except Exception:
                pass
            return

    async def adoption_prompt_channel(self, channel, target_user, mouse_name):
        """
        Prompts the target user to adopt a mouse in a channel context.
        Uses reactions: 👍 to adopt, 👎 to decline (which deducts 500 points).
        """
        embed = disnake.Embed(
            title=f"Adopt {mouse_name}?",
            description=(
                f"{target_user.mention}, your bond with {mouse_name} has grown strong.\n"
                "React with 👍 to adopt or 👎 to decline (and break its little heart)"
            ),
            color=config_py.main_color
        )
        msg = await channel.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", timeout=60.0,
                check=lambda r, u: u == target_user and r.message.id == msg.id and str(r.emoji) in ["👍", "👎"]
            )
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            return

        if str(reaction.emoji) == "👍":
            config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"adopted_by": target_user.id}})
            await channel.send(f"{mouse_name} happily chirps that it will serve you with all its heart!")
        else:
            config_py.user_mice.update_one(
                {"name": mouse_name, "Relationship.user_id": target_user.id},
                {"$inc": {"Relationship.$.relationship_points": -100}}
            )
            await channel.send(f"{mouse_name} is heartbroken... :pleading_face: it slinks away and hides in shame and neglect. :broken_heart:")
        await msg.clear_reactions()
        
    @commands.command(name="relationships", description="Show your relationships with mice")
    async def relationships(self, context):
        """
        Lists all the mouse relationships for the command invoker.
        It displays the mouse name, class, and relationship points sorted in descending order.
        The embed is paginated (10 per page) and can be navigated with ◀️ and ▶️ reactions.
        """
        # Query the database for mice that have a Relationship entry for the user.
        mouse_docs = list(config_py.user_mice.find({"Relationship.user_id": context.author.id}))
        if not mouse_docs:
            await context.send("You have no relationships with any mice yet.")
            return

        rel_list = []
        for doc in mouse_docs:
            for rel in doc.get("Relationship", []):
                if rel["user_id"] == context.author.id:
                    rel_list.append({
                        "name": doc["name"],
                        "class": doc.get("class", "Unknown"),
                        "points": rel["relationship_points"]
                    })
                    break

        if not rel_list:
            await context.send("You have no relationships with any mice yet.")
            return

        # Sort relationships descending by points.
        rel_list.sort(key=lambda x: x["points"], reverse=True)

        # Split into pages (10 per page).
        pages = [rel_list[i:i+10] for i in range(0, len(rel_list), 10)]
        current_page = 0

        embed = disnake.Embed(
            title="Your Mouse Relationships",
            description=self.build_relationship_page(pages[current_page]),
            color=config_py.main_color
        )
        embed.set_footer(text=f"Page {current_page + 1}/{len(pages)}")
        msg = await context.send(embed=embed)

        # If more than one page, add reaction arrows.
        if len(pages) > 1:
            await msg.add_reaction("◀️")
            await msg.add_reaction("▶️")

        def check(reaction, user):
            return (
                user == context.author
                and str(reaction.emoji) in ["◀️", "▶️"]
                and reaction.message.id == msg.id
            )

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                if str(reaction.emoji) == "◀️":
                    current_page = (current_page - 1) % len(pages)
                elif str(reaction.emoji) == "▶️":
                    current_page = (current_page + 1) % len(pages)

                embed = disnake.Embed(
                    title="Your Mouse Relationships",
                    description=self.build_relationship_page(pages[current_page]),
                    color=config_py.main_color
                )
                embed.set_footer(text=f"Page {current_page + 1}/{len(pages)}")
                await msg.edit(embed=embed)
                # Remove the user's reaction after processing.
                await msg.remove_reaction(reaction.emoji, user)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except Exception:
                    pass
                break

    def build_relationship_page(self, page_data):
        """
        Helper function to build the embed description for a page of relationships.
        Each relationship is listed with its mouse name, class, and relationship points.
        """
        lines = []
        for rel in page_data:
            lines.append(f"**{rel['name']}** ({rel['class']}) - {rel['points']} points")
        return "\n".join(lines)


def setup(bot):
    bot.add_cog(Racing(bot))