""""
Version 1.0
"""

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

class Gym(commands.Cog, name="Gym"):
    def __init__(self, bot):
        self.bot = bot

#############################################
#              MAIN FUNCTION                #
#############################################

    @commands.command(name="gym", aliases=['train'], description="Choose a cat and send them to the gym to increase their parameters")
    async def gym(self, context, member: disnake.Member = None):
        member = member or context.author
        user_id = member.id
        gym_cost = config_py.gym_cost
        pet_id = None

        # Uncomment if balance check is needed
        # if not self.has_enough_balance(user_id):
        #     await context.send("You do not have enough balance to train a pet.")
        #     return

        if pet_id is None:
            # Fetch the user's gym eligible pets
            pets = await self.fetch_gym_eligible_pets(user_id)
            if not pets:
                await context.send("You do not own any pets eligible for the gym.")
                return
            pet_id = await self.display_pet_dropdown(pets, context)
            if pet_id is None:
                await context.send("No pet selected.")
                return

        muscle_groups = ['Chest and Arms', 'Core and Cardio', 'Brain by reading clever books', 'Beauty by attending the Grooming center']
        options = [disnake.SelectOption(label=group) for group in muscle_groups]

        class DropdownView(disnake.ui.View):
            def __init__(self, bot, user_id, pet_id):
                super().__init__(timeout=180)
                self.bot = bot
                self.user_id = user_id
                self.pet_id = pet_id

            @disnake.ui.select(placeholder="What do you wanna train today?", min_values=1, max_values=1, options=options)
            async def select_callback(self, select: disnake.ui.Select, interaction: disnake.MessageInteraction):
                muscle_group = select.values[0]
                gym_cog = self.bot.get_cog('Gym')
                if gym_cog is not None:
                    await gym_cog.register_gym_session(self.user_id, self.pet_id, muscle_group)
                    await interaction.response.send_message(f"{member.display_name}'s pet is now training their {muscle_group}.", ephemeral=True)
                    self.stop()
                else:
                    await interaction.response.send_message("GymCog is not loaded.", ephemeral=True)

        view = DropdownView(self.bot, user_id, pet_id)
        await context.send("Select what you wanna train today!", view=view)

    async def fetch_gym_eligible_pets(self, user_id):
        """Fetch gym eligible pets for a user, excluding those already at the gym."""
        # Find all gym eligible pets
        all_pets = list(config_py.catcollection.find({'owner': user_id, 'GYM': 1}))  # Ensure owner is compared correctly
        print(f"All gym eligible pets: {all_pets}")

        # Get the names of pets currently at the gym
        gym_pet_names = set(session["cat_id"] for session in config_py.db["GymSessions"].find())
        print(f"Gym pet names: {gym_pet_names}")

        # Exclude pets currently at the gym
        eligible_pets = [pet for pet in all_pets if pet['name'] not in gym_pet_names]
        print(f"Eligible pets: {eligible_pets}")

        return eligible_pets

    async def display_pet_dropdown(self, pets, context):
        """Display a dropdown to select a pet."""
        options = [disnake.SelectOption(label=pet['name'], description=str(pet['_id'])) for pet in pets]
        select = disnake.ui.Select(options=options, placeholder="Choose your pet for the gym", min_values=1, max_values=1)
        view = disnake.ui.View()
        view.add_item(select)
        message = await context.send("Select your pet:", view=view)

        def check(interaction):
            return interaction.message.id == message.id and interaction.user.id == context.author.id

        try:
            interaction = await self.bot.wait_for('interaction', check=check, timeout=60.0)
            selected_pet_id = interaction.values[0]
            await interaction.response.defer()
            return selected_pet_id
        except asyncio.TimeoutError:
            await context.send("You took too long to choose a pet.")
            return None

    async def register_gym_session(self, user_id, cat_id, muscle_group):
        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(hours=24)
        gym_sessions = config_py.db["GymSessions"]
        session = {
            "cat_id": cat_id,
            "start_time": start_time,
            "end_time": end_time,
            "muscle_group": muscle_group
        }
        gym_sessions.insert_one(session)
        self.schedule_attribute_increase(cat_id, muscle_group, end_time)

    def schedule_attribute_increase(self, cat_id, muscle_group, end_time):
        @tasks.loop(count=1)
        async def increase_attribute():
            await asyncio.sleep((end_time - datetime.datetime.now()).total_seconds())
            await self.increase_cat_attribute(cat_id, muscle_group)

        increase_attribute.start()

    async def increase_cat_attribute(self, cat_id, muscle_group):
        cats_collection = config_py.db["catcollection"]
        attribute_mapping = {
            'Chest and Arms': 'strength',
            'Core and Cardio': 'agility',
            'Library': 'intellect',
            'Grooming': 'charm'
        }
        attribute_to_increase = attribute_mapping[muscle_group]
        cats_collection.update_one({"_id": cat_id}, {"$inc": {attribute_to_increase: 1}})
        print(f"Updated {attribute_to_increase} for cat {cat_id}")

#############################################
#              HELPERS                      #
#############################################

#####################################
#                                   #
#            WALLET                 #
#                                   #
#####################################

    def has_enough_balance(self, user_id):
        wallets_collection = config_py.wallets
        gym_cost = config_py.gym_cost
    
        # Get the user's wallet document
        wallet = wallets_collection.find_one({"user_id": user_id})
    
        if not wallet:
            # If the user doesn't have a wallet, assume they have zero balance
            return False
    
        # Check if the user has enough balance for a fishing attempt
        return wallet.get("balance", 0) >= gym_cost
        
##################################################################

    # Charging for fishing
    async def subtract_fishing_cost(self, user_id):
        fishing_cost = config_py.fishing_cost
        wallets_collection = config_py.wallets
        user_wallet = wallets_collection.find_one({"user_id": user_id})
        
        if user_wallet:
            current_balance = user_wallet.get("balance", 0)
            if current_balance >= fishing_cost:
                new_balance = current_balance - fishing_cost
                wallets_collection.update_one({"user_id": user_id}, {"$set": {"balance": new_balance}})
            else:
                raise ValueError("User does not have enough coins.")
        else:
            raise ValueError("User does not have a wallet.")

    def has_enough_balance(self, user_id):
        wallets_collection = config_py.wallets
        gym_cost = config_py.gym_cost
    
        # Get the user's wallet document
        wallet = wallets_collection.find_one({"user_id": user_id})
    
        if not wallet:
            # If the user doesn't have a wallet, assume they have zero balance
            return False
    
        # Check if the user has enough balance for a fishing attempt
        return wallet.get("balance", 0) >= gym_cost

    
    
def setup(bot):
    bot.add_cog(Gym(bot))
