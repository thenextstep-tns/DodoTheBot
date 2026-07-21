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
from disnake.ext import commands
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

class Fishing(commands.Cog, name="fishing"):
    def __init__(self, bot):
        self.bot = bot

#############################################
#              MAIN FUNCTION                #
#############################################

    @commands.command(name="fish", aliases=['fishing'], description = "Choose a cat and try to fish out a rare treasure!")
    async def fish(self, context, member: disnake.Member = None):
        # Display all cats from config_py.catcollection in a dropdown (a database in Mongo) with its parameters
        member = context.author
        user_id = member.id
        channel = self.bot.get_channel(config_py.FISHING_LOG)
        fishing_cost = config_py.fishing_cost
        if self.has_enough_balance(user_id):
            
            cats_list = await self.fetchOwnedCats(user_id)
    
            # Wait for the member to choose the cat
            selected_cat_id = await self.displayCatDropdown(cats_list, context)
            # Wait for random time to choose an object from config_py.items
            # Get those object's parameters from the database
            # Calculate StrengthEffort (item's weight * baseStrengthModifier),
            agility_needed, intellect_needed, strength_needed, item_name = await self.spawn_fishing_drop(context)
            # summonedcat.get("strength"), same for agility, intellect
            cat_agility, cat_intellect, cat_strength = self.fetch_cat_parameters(selected_cat_id)
            # Generate a random number to slightly adjust effort requirements
            # Compare cat's parameters with the new effort requirements
            agility_ratio, intellect_ratio, strength_ratio = self.calculate_fishing_ratios(agility_needed, intellect_needed, strength_needed, cat_agility, cat_intellect, cat_strength)
            
            agility_message = self.get_parameter_message("agility", agility_ratio)
            intellect_message = self.get_parameter_message("intellect", intellect_ratio)
            strength_message = self.get_parameter_message("strength", strength_ratio)
            
            fishing_outcome_message = await context.send(self.write_fishing_message(agility_message, intellect_message, strength_message))
            await asyncio.sleep(random.uniform(4, 7))
            # Show a nice embed if the object was successfully fished out
            item_info = self.find_item_by_name(item_name)
            # Show reactions under the embed, asking the user to choose what to do with the item (sell, put in the bag, throw away)
            # Save fishing results (user, cat's name, cat's id, time, object, chance to drop, result of the fish)
            await fishing_outcome_message.delete()
            if self.define_fishing_outcome(agility_ratio, intellect_ratio, strength_ratio):
                stashed, sold, thrown_away = await self.draw_victory_embed(context, item_name, user_id)
                fishing_success = 1
                # Form the GoodiesBag object
                text = await self.process_fishing_results(user_id, stashed, sold, thrown_away, item_info)
                await context.send(f"{text}\nThe Fishing Bait cost you {fishing_cost} coins. We subtracted them from your wallet :3")
                await self.subtract_fishing_cost(user_id)
                print ("Fishing SUCCESSFUL!")
            else:
                fishing_success = 0
                await context.send(f"Unfortunately, you couldn't fish that {item_name}. Better luck next time!")
                await context.send(f"The Fishing Bait cost you {fishing_cost} coins. We subtracted them from your wallet :3")
                await self.subtract_fishing_cost(user_id)
                print ("Fishing UNSUCCESSFUL!")
            # Fetch object stats
            
            # Form the FishingResult object
            await self.save_fishing_result(context, item_info, user_id, selected_cat_id, agility_ratio, intellect_ratio, strength_ratio, fishing_success)
    
            print("Fishing done!")
        else:
            await context.send("Sorry, you don't have enough coins to go fishing. Try doing dodo dailies to earn more coins!")

#############################################
#              HELPERS                      #
#############################################
    
    # Helper function: Fetch owned cats
    async def fetchOwnedCats(self, user_id):
        cats = config_py.catcollection
        query = {
        'owner': user_id,
        'FISHING': 1
        }
        owned_cats_able_to_fish = cats.find(query)
        # Sort the cats alphabetically by name
        sorted_cats = sorted(owned_cats_able_to_fish, key=lambda cat: cat['name'])
        return sorted_cats
        
#############################################################
    # Helper function: Display cat dropdown
    async def displayCatDropdown(self, cats_list, context):
        
        if not cats_list:
            await context.send("You don't have any cats available to fish with. Summon one of your cats and toggle fishing for them! 🐱")
            return None
        else:
            cat_options = [
                disnake.SelectOption(
                    label=f"{cat['name']} - S: {cat['strength']} A: {cat['agility']} I: {cat['intellect']}",
                    value=str(cat['_id'])
                )
                for index, cat in enumerate(cats_list)
            ]
        
            MAX_OPTIONS_PER_PAGE = 25
        
            view = disnake.ui.View()
            cat_dropdown = disnake.ui.Select(
                placeholder='Select a cat to fish with',
                min_values=1,
                max_values=1,
                options=cat_options[:MAX_OPTIONS_PER_PAGE]
            )
            view.add_item(cat_dropdown)
        
            message = await context.send("Please select a cat to fish with! 🐱 Choose wisely! Different cats are good for different types of loot!", view=view)
            selected_cat_id = None
        
            while selected_cat_id is None:
                try:
                    interaction = await self.bot.wait_for(
                        "message_interaction",
                        check=lambda i: i.component.custom_id == cat_dropdown.custom_id and i.message.id == message.id and i.user.id == context.author.id,
                        timeout=30.0
                    )
    
                    selected_cat_id = (interaction.values[0])
    
                except TimeoutError:
                    break
        
            #cat_dropdown.options = cat_options[MAX_OPTIONS_PER_PAGE * (int(interaction.values[0]) - 1):MAX_OPTIONS_PER_PAGE * int(interaction.values[0])]
            #await message.edit(view=view)
        
            view.stop()
            await message.edit(content="You have chosen the cat! 🐱 We begin fishing!", view=view)
            await interaction.response.send_message(":thinking: Hmmm, what is this? Looks like you can reel in")
            await message.delete()
            return selected_cat_id

#################################################################

    # HELPER: Pick a random item
    def pick_random_item(self):
        items = config_py.items
        itemscount = items.count_documents({})
        random_index = random.randint(0, itemscount - 1)
        random_item = items.find().skip(random_index).limit(1)[0]
        return random_item

################################################################

    # HELPER: Spawn fishing prey
    async def spawn_fishing_drop(self, context):
        # Get a random item
        random_item = self.pick_random_item()  # Assuming you have the pick_random_item function from the previous response
    
        # Fetch the type_id, quality_id, and weight from the random item
        type_id = random_item['type_id']
        quality_id = random_item['quality_id']
        weight = random_item['weight']
        item_name = random_item['name']
        item_cost = random_item['cost']
    
        # Fetch the agility_modifier from the ItemTypes collection based on type_id
        itemtypes = config_py.itemtypes
        item_type = itemtypes.find_one({'_id': type_id})
        agility_modifier = item_type['agility_modifier']
    
        # Fetch the base_agility_modifier from the BaseModifiers collection
        base_modifiers = config_py.base_modifiers
        base_agility_modifier = base_modifiers.find_one({'name': 'base_agility_modifier'})['modifier']
    
        # Calculate the Agility Needed
        agility_needed = agility_modifier * base_agility_modifier
    
        # Fetch the intellect_modifier from the ItemQualities collection based on quality_id
        itemqualities = config_py.itemqualities
        item_quality = itemqualities.find_one({'_id': quality_id})
        intellect_modifier = item_quality['intellect_modifier']
    
        # Fetch the base_intellect_modifier from the BaseModifiers collection
        base_intellect_modifier = base_modifiers.find_one({'name': 'base_intellect_modifier'})['modifier']
    
        # Calculate the Intellect Needed
        intellect_needed = intellect_modifier * base_intellect_modifier
    
        # Calculate the Strength Needed
        base_strength_modifier = base_modifiers.find_one({'name': 'base_strength_modifier'})['modifier']
        strength_needed = weight * base_strength_modifier
    
        item_img = "/root/"+random_item['img']
        
        # Create the embed
        embed = disnake.Embed(
            title=item_name,
            description= f"A new item has appeared for fishing!",
            color=disnake.Color.random()
        )
        
        # Set the item details in the embed
#        embed.set_thumbnail(url=item_img)
        embed.add_field(name="Quality", value=item_quality['quality'], inline=True)
        embed.add_field(name="Type", value=item_type['type'], inline=True)
        embed.add_field(name="Cost", value=str(item_cost) + " dodo coins", inline=True)
        embed.add_field(name="Agility Needed", value=agility_needed, inline=True)
        embed.add_field(name="Intellect Needed", value=intellect_needed, inline=True)
        embed.add_field(name="Strength Needed", value=strength_needed, inline=True)
        
        # Display the embed
        # Get the absolute file path for the image
        image_file_path = os.path.abspath(os.path.join('item_imgs', item_img))
    
        # Resize the image to a smaller size (e.g., 128x128)
        resized_image = Image.open(image_file_path)
        resized_image.thumbnail((128, 128))  # Adjust the size as per your requirement
    
        # Save the resized image to a temporary file
        temp_image_path = "temp_thumbnail.png"
        resized_image.save(temp_image_path)
    
        # Create a disnake.File object for the resized image
        resized_image_file = disnake.File(temp_image_path)
    
        # Set the disnake.File object as the thumbnail in the embed
        embed.set_thumbnail(url="attachment://thumbnail.png")
    
        # Send the embed with the resized image attachment
        await context.send(embed=embed)
    
        # Remove the temporary file
        os.remove(temp_image_path)
        return agility_needed, intellect_needed, strength_needed, item_name
        
######################################
    
    # GET ITEM PARAMETERS
    
    def find_item_by_name(self, item_name):
        # Assuming you have the items collection stored in a variable named "items_collection"
        items_collection = config_py.items
        item = items_collection.find_one({'name': item_name})
    
        if item:
            item_dict = {
                'item_id': item['_id'],
                'item_img': item['img'],
                'quality_id': item['quality_id'],
                'type_id': item['type_id'],
                'strength_modifier': item['strength_modifier'],
                'agility_modifier': item['agility_modifier'],
                'intellect_modifier': item['intellect_modifier'],
                'charm_modifier': item['charm_modifier'],
                'hp_modifier': item['hp_modifier'],
                'bite_modifier': item['bite_modifier'],
                'crit_chance_modifier': item['crit_chance_modifier'],
                'claim_res_modifier': item['claim_res_modifier'],
                'conversion_chance_modifier': item['conversion_chance_modifier'],
                'item_cost': item['cost'],
                'item_weight': item['weight'],
                'strength_required': item['strength_required'],
                'agility_required': item['agility_required'],
                'intellect_required': item['intellect_required'],
                'charm_required': item['charm_required'],
                'bite_required': item['bite_required'],
                'fights_won_required': item['fights_won_required'],
                'fights_lost_required': item['fights_lost_required']
            }
    
            return item_dict
        else:
            return None

####################################################################
    
    # DRAW A FANCY EMBED FOR THE ITEM
    async def draw_victory_embed(self, context, item_name, user_id):
        
        items_collection = config_py.items
        itemqualities = config_py.itemqualities
        itemtypes = config_py.itemtypes
        item = items_collection.find_one({'name': item_name})
        
        quality_id = item['quality_id']
        type_id = item['type_id']
        item_cost = item['cost']     
        item_quality = itemqualities.find_one({'_id': quality_id})
        item_type = itemtypes.find_one({'_id': type_id})
        
        item_img = "/root/"+item['img']
        
        embed = disnake.Embed(
            title=f"You have successfully fished out\n**{item_name}**!",
            description= f"Now you have to decide what to do with the item!\nUse the BACKPACK icon to stash it in your goodies bag if you have space!\nUse the COIN PURSE icon to sell it immediately\nUse the EXPLOSION icon to throw it away!",
            color=disnake.Color.random()
        )
        
        # Set the item details in the embed
        #embed.set_thumbnail(url=item_img)
        embed.add_field(name="Quality", value=item_quality['quality'], inline=True)
        embed.add_field(name="Type", value=item_type['type'], inline=True)
        embed.add_field(name="Cost", value=str(item_cost) + " dodo coins", inline=True)
        
        # Display the embed
        # Get the absolute file path for the image
        image_file_path = os.path.abspath(os.path.join('item_imgs', item_img))
    
        # Resize the image to a smaller size (e.g., 128x128)
        resized_image = Image.open(image_file_path)
        resized_image.thumbnail((128, 128))  # Adjust the size as per your requirement
    
        # Save the resized image to a temporary file
        temp_image_path = "temp_thumbnail.png"
        resized_image.save(temp_image_path)
    
        # Create a disnake.File object for the resized image
        resized_image_file = disnake.File(temp_image_path)
    
        # Set the disnake.File object as the thumbnail in the embed
        embed.set_thumbnail(url="attachment://thumbnail.png")
    
        # Send the embed with the resized image attachment
        victory_embed = await context.send(file=resized_image_file, embed=embed)
        
        stashed, sold, thrown_away = await self.add_fishing_result_actions(victory_embed, user_id)
        return stashed, sold, thrown_away

######################################

    async def save_fishing_result(self, context, item_info, user_id, selected_cat_id, agility_ratio, intellect_ratio, strength_ratio, fishing_success):
        fishing_results_collection = config_py.fishing_results
    
        # Get the current date and time
        current_datetime = datetime.datetime.now()
    
        # Prepare the fishing result data to be inserted into the database
        fishing_result_data = {
            'user_id': user_id,
            'cat_id': selected_cat_id,
            'time': current_datetime,
            'item_id': item_info['item_id'],
            'agility_ratio': agility_ratio,
            'intellect_ratio': intellect_ratio,
            'strength_ratio': strength_ratio,
            'fishing_success': fishing_success
        }
    
        # Insert the fishing result data into the database
        result = fishing_results_collection.insert_one(fishing_result_data)
    
        if result:
            print("Fishing result successfully saved to the database!")
        else:
            print("Failed to save fishing result to the database!")
    
        return result

######################################

    def fetch_cat_parameters(self, selected_cat_id):
        cats_collection = config_py.catcollection
    
        # Fetch the cat from the collection
        cat = cats_collection.find_one({'_id': ObjectId(selected_cat_id)})
    
        if cat:
            # Extract the relevant parameters from the cat document
            cat_name = cat['name']
            cat_strength = cat['strength']
            cat_agility = cat['agility']
            cat_intellect = cat['intellect']
            cat_charm = cat['charm']
            cat_hp = cat['hp']
            cat_bite = cat['bite']
            cat_critchance = cat['critchance']
            cat_claimres = cat['claimres']
            cat_conversionchance = cat['conversionchance']
            cat_fightswon = cat['fightswon']
            cat_fightslost = cat['fightslost']
            cat_fishing = cat['FISHING']
    
            # Return the cat's parameters
            return cat_agility, cat_intellect, cat_strength
        else:
            # Handle the case when the cat is not found
            print("Cat not found!")
            return None

###########################################
    def calculate_fishing_ratios(self, agility_needed, intellect_needed, strength_needed, cat_agility, cat_intellect, cat_strength):
        noise_factor = 0.05  # Adjust this value to control the amount of noise
        
        # Calculate the divided values with noise
        agility_ratio = cat_agility / (agility_needed + random.uniform(-noise_factor, noise_factor))
        intellect_ratio = cat_intellect / (intellect_needed + random.uniform(-noise_factor, noise_factor))
        strength_ratio = cat_strength / (strength_needed + random.uniform(-noise_factor, noise_factor))
        
        return agility_ratio, intellect_ratio, strength_ratio

############################################

    def define_fishing_outcome(self, agility_ratio, intellect_ratio, strength_ratio):
        average_ratio = (agility_ratio + intellect_ratio + strength_ratio) / 3
        if average_ratio > 1:
            return True
        else:
            return False 

############################################

    def get_parameter_message(self, parameter_name, ratio):
        if ratio > 2:
            message = f":white_check_mark: Wow! Fishing this item with so much {parameter_name} should be a piece of cake for your cat!"
        elif ratio > 1:
            message = f":ballot_box_with_check: Great! Your cat's {parameter_name} is looking good for fishing this item."
        elif ratio > 0.5:
            message = f":warning: Not bad! Your cat's {parameter_name} is somewhat sufficient, but it might be not enough... :pleading_face:"
        else:
            message = f":no_entry: Uh-oh! Your cat's {parameter_name} is a bit low for this fishing trip."
    
        return message

############################################

    def write_fishing_message(self, agility_message, intellect_message, strength_message):
        message = (f"\nLet's see how your stats are looking for this reel in!\n {agility_message}\n {intellect_message}\n {strength_message}\n\n YOUR CAT IS TRYING REALLY HARD TO REEL IN! WAIT JUST A BIT LONGER :fish:")
        return message

#############################################
#                                           #
#           INVENTORY                       #
#                                           #
#############################################

    # GET ALL THE AVAILABLE INVENTORY ITEMS
    async def fetchGoodiesBag(self, user_id):
        goodies_bag = config_py.goodies_bag
        query = {
            'user': user_id,
            'equipped': 0,
            'sold': 0,
            'thrown_away': 0
        }
        items_in_goodies_bag = goodies_bag.find(query)
        sorted_items = sorted(items_in_goodies_bag, key=lambda item: item['name'])
        return sorted_items
        
    # COUNT FREE INVENTORY ITEMS
    async def countGoodiesBag(self, user_id):
        goodies_bag = config_py.goodies_bag
        query = {
            'user': user_id,
            'equipped': 0,
            'sold': 0,
            'thrown_away': 0
        }
        goodies_bag_count = goodies_bag.count_documents(query)
        return goodies_bag_count
        
#############################################################

    # ADD REACTIONS TO THE MESSAGE WHAT TO DO WITH THE ITEM
    async def add_fishing_result_actions(self, message, user_id):
        for emoji in config_py.fishing_result_actions:
                await message.add_reaction(emoji)
                stashed = 0
                sold = 0
                thrown_away = 0
        def check (reaction, user):
            return user.id == user_id and str(reaction) in config_py.fishing_result_actions
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=20, check=check)
            userChoiceEmote = reaction.emoji
            userChoiceIndex = config_py.fishing_result_actions[userChoiceEmote]
            print (userChoiceIndex)
            if userChoiceIndex == "Put in the goodies bag":
                await message.edit(content = "You have decided to put the item in your inventory")
                stashed = 1
                await message.clear_reactions()
                return stashed, sold, thrown_away
            elif userChoiceIndex == "Sell":
                await message.edit(content = "You sold the item")
                sold = 1
                await message.clear_reactions()
                return stashed, sold, thrown_away                    
            elif userChoiceIndex == "Throw away":
                await message.edit(content = "You decided to throw the item away")
                thrown_away = 1
                await message.clear_reactions()
                return stashed, sold, thrown_away
            await message.clear_reactions()
        except asyncio.exceptions.TimeoutError:
            await message.clear_reactions()

#############################################################

    async def process_fishing_results(self, user_id, stashed, sold, thrown_away, item_info):
        goodies_bag_collection = config_py.goodies_bag
        wallets_collection = config_py.wallets
    
        # Process the stashed item
        if stashed:
            # Check if the goodies bag is full (contains 24 items)
            goodies_bag_count = await self.countGoodiesBag(user_id)
    
            if goodies_bag_count < 24:
                # If the goodies bag is not full, add the item to the goodies bag
                goodies_bag_data = {
                    'user': user_id,
                    'item_instance_id': str(uuid.uuid4()),  # Generate a unique ID for the item instance
                    'item_id': item_info['item_id'],
                    'cost': item_info['item_cost'],
                    'sold': 0,
                    'thrown_away': 0,
                    'equipped': 0
                }
    
                # Insert the item into the goodies bag collection
                result = goodies_bag_collection.insert_one(goodies_bag_data)
    
                if result:
                    return("Item stashed in the goodies bag!")
                else:
                    return("Failed to stash item in the goodies bag!")
            else:
                # If the goodies bag is full, display a message indicating it's full
                return("Sorry, your goodies bag is full! There's no more space to store anything else.")
        
        # Process the sold item
        if sold:
            # Set the 'sold' field to 1 for the item in the goodies bag collection
            goodies_bag_data = {
                'user': user_id,
                'item_instance_id': str(uuid.uuid4()),  # Generate a unique ID for the item instance
                'item_id': item_info['item_id'],
                'cost': item_info['item_cost'],
                'sold': 1,
                'thrown_away': 0,
                'equipped': 0
            }
            result = goodies_bag_collection.insert_one(goodies_bag_data)
            user_wallet = wallets_collection.find_one({"user_id": user_id})
            if user_wallet:
                # Calculate the selling price of the item (you can adjust this based on your logic)
                selling_price = item_info['item_cost']
                # Update the user's balance
                new_balance = user_wallet.get("balance", 0) + selling_price
                wallets_collection.update_one({"user_id": user_id}, {"$set": {"balance": new_balance}})
                return (f"Item sold! You earned {selling_price} dodo coins!")
            else:
                # If the user does not have a wallet, create a new one with the initial balance
                selling_price = item_info['item_cost']
                new_wallet = {
                    "user_id": user_id,
                    "balance": selling_price
                }
                result = wallets_collection.insert_one(new_wallet)
        
        
        # Process the thrown_away item
        if thrown_away:
            # Set the 'thrown_away' field to 1 for the item in the goodies bag collection
            goodies_bag_data = {
                'user': user_id,
                'item_instance_id': str(uuid.uuid4()),  # Generate a unique ID for the item instance
                'item_id': item_info['item_id'],
                'cost': item_info['item_cost'],
                'sold': 0,
                'thrown_away': 1,
                'equipped': 0
            }
            result = goodies_bag_collection.insert_one(goodies_bag_data)
            return("We threw it away! EW!")

#############################################
#              ITEMS                        #
#############################################
    
    items = config_py.items
    itemtypes = config_py.itemtypes
    itemsources = config_py.itemsources
    itemqualities = config_py.itemqualities
    
    def resolve_quality_id(item_quality, qualities_collection):
        quality = qualities_collection.find_one({'quality': item_quality})
        if quality:
            return quality['_id']
        else:
            # Handle the case when the quality is not found
            return None
    
    def resolve_type_id(item_type, types_collection):
        item_type = types_collection.find_one({'type': item_type})
        if item_type:
            return item_type['_id']
        else:
            # Handle the case when the item type is not found
            return None
    
    def resolve_sourcing_id(item_sourcing, sourcings_collection):
        sourcing = sourcings_collection.find_one({'sourcing': item_sourcing})
        if sourcing:
            return sourcing['_id']
        else:
            # Handle the case when the item sourcing is not found
            return None
    
#    items_data = []
#    with open('items_1907.csv', 'r') as file:
#        reader = csv.DictReader(file)
#        items_data = list(reader)
#    
#    # Step 3: Format the data for insertion into the Items collection
#    formatted_items = []
#    for item in items_data:
#        name = item['Name']
#        img = item['Image']
#        item_quality = item['ItemQuality']
#        item_type = item['ItemType']
#        item_sourcing = item['ItemSourcing']
#        strength_modifier = int(item['StrengthModifier'])
#        agility_modifier = int(item['AgilityModifier'])
#        intellect_modifier = int(item['IntellectModifier'])
#        charm_modifier = int(item['CharmModifier'])
#        hp_modifier = int(item['HPModifier'])
#        bite_modifier = int(item['BiteModifier'])
#        crit_chance_modifier = int(item['CritchanceModifier'])
#        claim_res_modifier = int(item['ClaimresModifier'])
#        conversion_chance_modifier = int(item['ConversionchanceModifier'])
#        cost = int(item['Cost'])
#        weight = int(item['Weight'])
#        strength_required = int(item['StrengthRequired'])
#        agility_required = int(item['AgilityRequired'])
#        intellect_required = int(item['IntellectRequired'])
#        charm_required = int(item['CharmRequired'])
#        bite_required = int(item['BiteRequired'])
#        fights_won_required = int(item['FightswonRequired'])
#        fights_lost_required = int(item['FightslostRequired'])
#    
#        # Resolve the relationships with helper collections
#        quality_id = resolve_quality_id(item_quality, itemqualities)
#        type_id = resolve_type_id(item_type, itemtypes)
#        sourcing_id = resolve_sourcing_id(item_sourcing, itemsources)
#    
#        # Create the item document
#        formatted_item = {
#            'name': name,
#            'img': img,
#            'quality_id': quality_id,
#            'type_id': type_id,
#            'sourcing_id': sourcing_id,
#            'strength_modifier': strength_modifier,
#            'agility_modifier': agility_modifier,
#            'intellect_modifier': intellect_modifier,
#            'charm_modifier': charm_modifier,
#            'hp_modifier': hp_modifier,
#            'bite_modifier': bite_modifier,
#            'crit_chance_modifier': crit_chance_modifier,
#            'claim_res_modifier': claim_res_modifier,
#            'conversion_chance_modifier': conversion_chance_modifier,
#            'cost': cost,
#            'weight': weight,
#            'strength_required': strength_required,
#            'agility_required': agility_required,
#            'intellect_required': intellect_required,
#            'charm_required': charm_required,
#            'bite_required': bite_required,
#            'fights_won_required': fights_won_required,
#            'fights_lost_required': fights_lost_required
#        }
#        formatted_items.append(formatted_item)
#    
#    # Step 4: Connect to your MongoDB database
#    
#    # Step 5: Insert the formatted items into the Items collection
#    items.insert_many(formatted_items)#


#####################################
#                                   #
#            WALLET                 #
#                                   #
#####################################

    def has_enough_balance(self, user_id):
        wallets_collection = config_py.wallets
        fishing_cost = config_py.fishing_cost
    
        # Get the user's wallet document
        wallet = wallets_collection.find_one({"user_id": user_id})
    
        if not wallet:
            # If the user doesn't have a wallet, assume they have zero balance
            return False
    
        # Check if the user has enough balance for a fishing attempt
        return wallet.get("balance", 0) >= fishing_cost
        
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

#    # Get the Dailies and Wallets collections
#    dailies_collection = config_py.dailies
#    wallets_collection = config_py.wallets
#    
#    # Query the Dailies collection to get the sum of Points for each user_id
#    pipeline = [
#        {"$group": {"_id": "$Player", "balance": {"$sum": "$Points"}}},
##        {"$project": {"_id": 0, "user_id": "$_id", "balance": 1}}
#   ]
#    
#    results = dailies_collection.aggregate(pipeline)
#    
#    # Update or insert the documents in the Wallets collection
#    for result in results:
#        user_id = result["user_id"]
#        balance = result["balance"]
#    
#        # Check if the user_id already exists in the Wallets collection
#        existing_wallet = wallets_collection.find_one({"user_id": user_id})
#    
#        if existing_wallet:
#            # Update the existing document with the new balance
##            wallets_collection.update_one({"user_id": user_id}, {"$set": {"balance": balance}})
 #       else:
 #           # Insert a new document with the user_id and balance
 #           wallets_collection.insert_one({"user_id": user_id, "balance": balance})#

#
# SETUP
#
    

    
    
def setup(bot):
    bot.add_cog(Fishing(bot))
