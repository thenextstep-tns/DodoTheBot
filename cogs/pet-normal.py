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
import nekos
import numpy as np
import io
import bson

import urllib.request
from urllib.request import urlopen

import re
import requests
import pymongo

import aiohttp
import disnake
from waifuim import WaifuAioClient
from disnake.ext import commands
from disnake.ext.commands import Context

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

class Pet(commands.Cog, name="pet-normal"):
    def __init__(self, bot):
        self.bot = bot
        self.pet_collections = {
            'cat': config_py.catcollection,
            'dog': config_py.dogcollection,
            'waifu': config_py.waifucollection
        }
    
 
    
#####################################
#                                   #
#             DB UPDATE             #    
#                                   #
#####################################

#    @commands.command(
#        name="schemaupdate",
#        description="Updates the desired collection with the predefined query")
#    @checks.is_owner()
#    
#    async def schemaupdate(self, context: Context):
#        """
#        Updates the DB schema
#        """
#        cats = config_py.catcollection
#        update_query = {}
#        update_fields = {
#            '$set': {
#                'GYM': 0  # Set the initial value of the 'FISHING' parameter to 0
#            }
#        }
#        #cats.update_many(update_query, update_fields)
#        print("The collection updated successfully!")
    

#####################################
#                                   #
#             SHOWCATS              #    
#                                   #
#####################################    
    
    
    
    
    @commands.command(
        name="showcats",
        description="Show all your cats in a list!!")
    @checks.not_blacklisted()
    
    async def showcats(self, context: Context, member : disnake.Member = None):
        """
        Show all your cats in a tiny list
        """
        if not member:
            member = context.author
        cats = config_py.catcollection
        user = member.id
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        usercats = list(cats.find({ "owner" : user }))
        #print (usercats)
        await context.send("Ok, " + member.display_name + ", here comes your meow army! :cat: ")
        catslist = []
        i = 0
        for cat in usercats:
            i = i+1
            name = cat.get("name")
            cattype = cat.get("type")
            catslist.append(name)
            catstoprint = ", ".join(catslist)
            if len(catstoprint) > 1500:
                await channel.send(catstoprint)
                catstoprint = ""
                catslist = []
        if len(catslist) == 0:
            await channel.send("Doesn't look like you have any cats :pleading_face: , try dodo cat command to find a new one!")
        else:
            catstoprint = ", ".join(catslist)
            await channel.send(catstoprint)
        await channel.send ("I found " + str(i) + " cats" )
        #print (catstoprint)
    
    @commands.command(
        name="showdogs",
        description="Show all your dogs in a list!!")
    @checks.not_blacklisted()
    
    async def showdogs(self, context: Context, member : disnake.Member = None):
        """
        Show all your dogs in a tiny list
        """
        if not member:
            member = context.author
        dogs = config_py.dogcollection
        user = member.id
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        userdogs = list(dogs.find({ "owner" : user }))
        #print (usercats)
        dogslist = []
        #await context.send("Ok, " + member.display_name + ", here comes the army!")
        i = 0
        for dog in userdogs:
            i = i+1
            name = dog.get("name")
            dogtype = dog.get("type")
            dogslist.append(name)
            dogstoprint = ", ".join(dogslist)
            if len(dogstoprint) > 1500:
                await channel.send(dogstoprint)
                dogstoprint = ""
                dogslist = []
        if len(dogslist) == 0:
            await channel.send("Doesn't look like you have any dogs :pleading_face: , try dodo dog command to find a new one!")
        else:
            dogstoprint = ", ".join(dogslist)
            await channel.send(dogstoprint)
        await channel.send ("I found " + str(i) + " dogs" )
    
############## SUMMON ####################


    @commands.command(name="summon", description="Summon one of your pets. The command is case-specific.")
    @checks.not_blacklisted()
    async def summon(self, context, *, pet_name):
        """ Handles the summoning of a pet with a specific name, case-sensitive. """
        owner_id = context.message.author.id
        pets = self.find_pets(owner_id, pet_name)

        if not pets:
            await context.send(f"I couldn't find '{pet_name}' in your collections. Please check the spelling and try again.")
            return

        if len(pets) > 1:
            await self.ask_user_to_choose_pet(context, pets)
        else:
            print (pets)
            await self.handle_pet_interaction(context, pets[0])

    def find_pets(self, owner_id, pet_name):
        """ Find pets by name across all collections, case-insensitively and including partial matches. """
        found_pets = []
        regex = re.compile(pet_name, re.IGNORECASE)  # Regular expression for case-insensitive partial match
        for pet_type, collection in self.pet_collections.items():
            # Search for pets where the name contains the given string, case-insensitively
            pets = collection.find({"owner": owner_id, "name": {"$regex": regex}})
            for pet in pets:
                pet['type'] = pet_type
                found_pets.append(pet)
        return found_pets

    async def ask_user_to_choose_pet(self, context, pets):
        """ Ask user to choose one of the pets if multiple or close matches are found. """
        if not pets:
            await context.send("Sorry, I couldn't find any pets with that name. Try a different name.")
            return
    
        emoji_list = list(config_py.pet_emoji.keys())[:len(pets)]  # Make sure there are enough emojis for the pets
        description = "\n".join([f"{emoji}: {pet['type'].title()} named {pet['name']}" for emoji, pet in zip(emoji_list, pets)])
        embed = disnake.Embed(title="Looks like you have several pets with that name!", description=description, color=config_py.info)
        choice_message = await context.send(embed=embed)
    
        # Add predefined emojis as reactions
        for emoji in emoji_list:
            await choice_message.add_reaction(emoji)
    
        # Define a check to ensure that the reaction is from the correct user and one of the provided emojis
        def check(reaction, user):
            return user == context.author and str(reaction.emoji) in emoji_list
    
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=10, check=check)
            selected_index = emoji_list.index(str(reaction.emoji))
            await self.handle_pet_interaction(context, pets[selected_index])
        except asyncio.TimeoutError:
            await choice_message.edit(content="Oops, too slow!. Please try the command again.", embed=None)

    async def handle_pet_interaction(self, context, pet):
        """ Manage interaction after a pet is summoned. """
        embed = self.create_pet_embed(pet)
        pet_msg = await context.send(embed=embed)

        # Adding reaction for each action
        for emoji in config_py.pet_actions:
            await pet_msg.add_reaction(emoji)

        # Process reaction actions
        def check(reaction, user):
            return user == context.author and str(reaction) in config_py.pet_actions

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=120, check=check)
            await self.process_reaction(context, reaction, pet)
        except asyncio.TimeoutError:
            await pet_msg.clear_reactions()

    def create_pet_embed(self, pet):
        """ Create an embed with pet details and actions. """
        description = f"Type: {pet['type'].title()}, Wins: {pet.get('fightswon', 0)}, Losses: {pet.get('fightslost', 0)}"
        embed = disnake.Embed(description=description, color=config_py.success)
        embed.set_image(url=pet['url'])
        embed.set_author(name=f"{pet['name']} at your service", icon_url=pet['url'])
        for emoji, action in config_py.pet_actions.items():
            embed.add_field(name=f"React with {emoji}", value=f"{action}", inline=False)
        return embed

    async def process_reaction(self, context, reaction, pet):
        """ Handle specific actions based on user's reaction. """
        if str(reaction.emoji) == u"\U0001F41F":  # Fishing emoji
            await self.toggle_fishing(pet['_id'], context.author.id, context.channel.id)
            # Assume toggle_fishing handles notifications internally
        elif str(reaction.emoji) == u"\U0001F4AA":  # Gym emoji
            await self.toggle_gym(pet['_id'], context.author.id, context.channel.id)
            # Assume toggle_gym handles notifications internally
        else:
            await context.send("This action is not recognized.")
    
    
    @commands.command(
        name="dog",
        description="Summon a new dog")
    @checks.not_blacklisted()
    async def newdog(self, context: Context, member : disnake.Member = None):
        
        
        # setting the right collection
        dogs = config_py.dogcollection
        owners = config_py.petownerscollection
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        #print (context.message)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        # setting a member
        if not member:
            member = context.author
        
            
        
        # checking member's ability to capture the cat
        claimskill = 2
        
        # picking a cat
        islookingfordog = 1
        while islookingfordog == 1:
            isOwned = 2 #starter state
            while isOwned != 0:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.thedogapi.com/v1/images/search?api_key=fb056807-277f-4e58-8373-fe5c39d8e9f2") as request:
                        if request.status == 200:
                            dogpicobj = await request.json()
                            dogpic = dogpicobj[0].get("url")
                        else:
                            embed = disnake.Embed(
                                title="Nope",
                                description="DogAPI is being weird at the moment, try again or later",
                                color = config_py.error)
                            await channel.send (embed = embed)
                dogquery = { "url" : dogpic }
                dogfoundindb = dogs.find_one(dogquery)
                if dogfoundindb == None:
                    isOwned = 0
                    print ("Dog isn't owned yet, we can proceed!")
                else:
                    print ("Dog is owned already, looking for the next one!")
                    isOwned = 1
            # checking if the cat belongs to anyone (imgurl), showing a message if it is
            if isOwned == 1:
                notemessagecolour = config_py.error
            else:
                notemessagecolour = config_py.success
                # if the cat is free setting up his parameters
                dogclass = config_py.dogclasses[random.randint(0, len(config_py.dogclasses)-1)]
                
                dogtype = dogclass[0]
                strength = random.randint(dogclass[1], dogclass[2])
                agility = random.randint(dogclass[3], dogclass[4])
                intellect = random.randint(dogclass[5], dogclass[6])
                charm = random.randint(dogclass[7], dogclass[8])
                hp = strength * 5
                bite = strength * 0.75
                critchance = agility * 1.85 / 100
                claimres = (agility + intellect + charm) * 0.8 / 100
                claimrespercent = int(round(claimres * 100))
                conversionchance = (charm*0.5+intellect*0.75-strength*0.15)/100
                claimchance = round(claimskill*claimres*100*1.7)
                
                # showing the dog
                embed = disnake.Embed(description=f"Strength = {strength}, Agility = {agility}, Intellect = {intellect}, Charm = {charm}, your chance to claim them is {claimchance}%", color=config_py.success)
                embed.set_image(url = dogpic)
                embed.set_author(name=f"{member.display_name}, this {dogtype} is free! Are you gonna claim them?")
                suggestion = await channel.send(embed=embed)
                reactions = { u"\U0001F44D" : 0, u"\U0001F44E" : 1, u"\u26D4" : 2}
                
                #adding claiming reactions
                for emoji in reactions:
                        await suggestion.add_reaction(emoji)
                def check (reaction, user):
                    return user.id == member.id and str(reaction) in reactions
                try:
                    reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                    userChoiceEmote = reaction.emoji
                    userChoiceIndex = reactions[userChoiceEmote]
                    if userChoiceIndex == 2:
                        await suggestion.clear_reactions()
                        await channel.send ("Alright, let's stop LFD (looking for dogs!) :hearts: ")
                        islookingfordog = 0
                    elif userChoiceIndex == 1:
                        await suggestion.clear_reactions()
                    else:
                        # Calculating if we have claimed the dog
                        claimseed = random.randint(0, 100)
                        if claimseed > 100 - claimchance:
                            await channel.send ("You have successfully claimed this dog! :white_check_mark: How are you going to name them? Hurry up, the others may name it too!")
                            namechosen = 0
                            while namechosen == 0:
                                namemsg = await self.bot.wait_for("message", timeout = 60)
                                name = str(namemsg.content).replace("@", " ")
                                
                                #checking if the name exists in the user's collection
                                namequery = { "name" : name, "owner" : namemsg.author.id }
                                nameexists = dogs.find_one(namequery)
                                if nameexists == None:
                                
                                    user = member.id
                                    
                                    # setting up the dog object
                                    dog = {
                                        "name" : name,
                                        "type" : dogtype,
                                        "url" : dogpic,
                                        "owner" : user,
                                        "strength" : strength,
                                        "agility" : agility,
                                        "intellect" : intellect,
                                        "charm" : charm,
                                        "hp" : hp,
                                        "bite" : bite,
                                        "critchance" : critchance,
                                        "claimres" : claimres,
                                        "conversionchance" : conversionchance,
                                        "fightswon" : 0,
                                        "fightslost" : 0,
                                    }
                                    dogs.insert_one(dog)
                                    
                                    islookingfordog = 0
                                    await channel.send (name + " has been added to your collection!")
                                    await suggestion.clear_reactions()
                                    namechosen = 1
                                    return
                                else:
                                    await channel.send ("I won't be able to distinguish between different " + name + "s. Please choose a unique name for your unique dog! Meow :3")
                        else:
                            dodgemessage = await channel.send ("This dog didn't trust you enough and they ran away! Wanna look for the next one?")
                            againreaction = { u"\U0001F44D" : 0,  u"\u26D4" : 1}
                            for emoji in againreaction:
                                await dodgemessage.add_reaction(emoji)
                            def againcheck (reaction, user):
                                return user.id == context.message.author.id and str(reaction) in reactions
                            try:
                                reaction, user = await self.bot.wait_for("reaction_add", timeout=15, check=againcheck)
                                userChoiceEmote = reaction.emoji
                                userChoiceIndex = reactions[userChoiceEmote]
                                if userChoiceIndex == 0:
                                    await suggestion.clear_reactions()
                                    await channel.send ("Okie dokie, find a new dog!")
                                    await dodgemessage.clear_reactions()
                                elif userChoiceIndex == 1:
                                    await channel.send ("Alright, " + member.display_name + " let's stop looking for dogs")
                                    await dodgemessage.clear_reactions()
                                    islookingfordog = 0
                                    break
                            except asyncio.exceptions.TimeoutError:
                                await dodgemessage.clear_reactions()
                                islookingfordog = 0
                            await suggestion.clear_reactions()
                        
                except asyncio.exceptions.TimeoutError:
                    await suggestion.clear_reactions()
                    islookingfordog = 0
    
    
    
    @commands.command(
        name="cat",
        description="Summon a new cat")
    @checks.not_blacklisted()
    async def newcat(self, context: Context, member : disnake.Member = None):
        
        
        # setting the right collection
        cats = config_py.catcollection
        owners = config_py.petownerscollection
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        
        # setting a member
        if not member:
            member = context.author
        
        # checking member's ability to capture the cat
        claimskill = 1.2
        
        # picking a cat
        islookingforcat = 1
        while islookingforcat == 1:
            isOwned = 2
            while isOwned != 0:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.thecatapi.com/v1/images/search?api_key=7fdd47a8-1509-4c98-91a0-30ef4c1dc6c5") as request:
                        if request.status == 200:
                            catpicobj = await request.json()
                            catpic = catpicobj[0].get("url")
                        else:
                            embed = disnake.Embed(
                                title="Nope",
                                description="CatAPI is being weird at the moment, try again or later",
                                color = config_py.error)
                            await channel.send (embed = embed)
                catquery = { "url" : catpic }
                catfoundindb = cats.find_one(catquery)
                if catfoundindb == None:
                    isOwned = 0
                    print ("Cat isn't owned yet, we can proceed!")
                else:
                    print ("Cat is owned already, looking for the next one!")
                    isOwned = 1
            # checking if the cat belongs to anyone (imgurl), showing a message if it is
            if isOwned == 1:
                notemessagecolour = config_py.error
            else:
                notemessagecolour = config_py.success
                # if the cat is free setting up his parameters
                catclass = config_py.catclasses[random.randint(0, len(config_py.catclasses)-1)]
                
                cattype = catclass[0]
                strength = random.randint(catclass[1], catclass[2])
                agility = random.randint(catclass[3], catclass[4])
                intellect = random.randint(catclass[5], catclass[6])
                charm = random.randint(catclass[7], catclass[8])
                hp = strength * 5
                bite = strength * 0.75
                critchance = agility * 1.85 / 100
                claimres = (agility + intellect + charm) * 0.8 / 100
                claimrespercent = int(round(claimres * 100))
                conversionchance = (charm*0.5+intellect*0.75-strength*0.15)/100
                claimchance = round(claimskill*claimres*100*1.2)
                
                # showing the cat
                embed = disnake.Embed(description=f"Strength = {strength}, Agility = {agility}, Intellect = {intellect}, Charm = {charm}, your chance to claim them is {claimchance}%", color=config_py.success)
                embed.set_image(url = catpic)
                embed.set_author(name=f"{member.display_name}, this {cattype} is free! Are you gonna claim them?")
                suggestion = await channel.send(embed=embed)
                reactions = { u"\U0001F44D" : 0, u"\U0001F44E" : 1, u"\u26D4" : 2}
                
                #adding claiming reactions
                for emoji in reactions:
                        await suggestion.add_reaction(emoji)
                def check (reaction, user):
                    return user.id == member.id and str(reaction) in reactions
                try:
                    reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                    userChoiceEmote = reaction.emoji
                    userChoiceIndex = reactions[userChoiceEmote]
                    if userChoiceIndex == 2:
                        await suggestion.clear_reactions()
                        await channel.send ("Alright, let's stop LFC (looking for cats!) :hearts: ")
                        islookingforcat = 0
                    elif userChoiceIndex == 1:
                        await suggestion.clear_reactions()
                    else:
                        # Calculating if we have claimed the cat
                        claimseed = random.randint(0, 100)
                        if claimseed > 100 - claimchance:
                            await channel.send ("You have successfully claimed this cat! :white_check_mark: How are you going to name them? Hurry up, the others may name it too!")
                            namechosen = 0
                            while namechosen == 0:
                                namemsg = await self.bot.wait_for("message", timeout = 60)
                                name = str(namemsg.content).replace("@", " ")
                                
                                #checking if the name exists in the user's collection
                                namequery = { "name" : name, "owner" : namemsg.author.id }
                                nameexists = cats.find_one(namequery)
                                if nameexists == None:
                                
                                    user = member.id
                                    
                                    # setting up the cat object
                                    cat = {
                                        "name" : name,
                                        "type" : cattype,
                                        "url" : catpic,
                                        "owner" : user,
                                        "strength" : strength,
                                        "agility" : agility,
                                        "intellect" : intellect,
                                        "charm" : charm,
                                        "hp" : hp,
                                        "bite" : bite,
                                        "critchance" : critchance,
                                        "claimres" : claimres,
                                        "conversionchance" : conversionchance,
                                        "fightswon" : 0,
                                        "fightslost" : 0,
                                        "FISHING" : 0,
                                    }
                                    cats.insert_one(cat)
                                    
                                    islookingforcat = 0
                                    await channel.send (name + " has been added to your collection!")
                                    await suggestion.clear_reactions()
                                    namechosen = 1
                                    return
                                else:
                                    await channel.send ("I won't be able to distinguish between different " + name + "s. Please choose a unique name for your unique cat! Meow :3")
                        else:
                            dodgemessage = await channel.send ("This cat was quite nimble, they dodged the claim and ran away! Wanna look for the next one?")
                            againreaction = { u"\U0001F44D" : 0,  u"\u26D4" : 1}
                            for emoji in againreaction:
                                await dodgemessage.add_reaction(emoji)
                            def againcheck (reaction, user):
                                return user.id == context.message.author.id and str(reaction) in reactions
                            try:
                                reaction, user = await self.bot.wait_for("reaction_add", timeout=15, check=againcheck)
                                userChoiceEmote = reaction.emoji
                                userChoiceIndex = reactions[userChoiceEmote]
                                if userChoiceIndex == 0:
                                    await suggestion.clear_reactions()
                                    await channel.send ("Okie dokie, find a new cat!")
                                    await dodgemessage.clear_reactions()
                                elif userChoiceIndex == 1:
                                    await channel.send ("Alright, " + member.display_name + " let's stop looking for cats")
                                    await dodgemessage.clear_reactions()
                                    islookingforcat = 0
                                    break
                            except asyncio.exceptions.TimeoutError:
                                await dodgemessage.clear_reactions()
                                islookingforcat = 0
                            await suggestion.clear_reactions()
                        
                except asyncio.exceptions.TimeoutError:
                    await suggestion.clear_reactions()
                    islookingforcat = 0    
    
    @commands.command(
        name="petfight",
        description="Fight other pets!")
    @checks.not_blacklisted()
    @commands.has_permissions(kick_members=True)
    async def duel(self, context : Context, mypet, opponent : disnake.Member, theirpet):
        
        cats = config_py.catcollection
        dogs = config_py.dogcollection
        duels = config_py.duels
        
        owner = context.message.author.id
        if not opponent:
            await context.send ("You forgor :skull: to pick an opponent.")
            return
        
        opponentid = opponent.id
        
        #finding my pet
        
        name = mypet
        
        summonquery = { "name" : name, "owner" : owner}
        summonedcat = cats.find_one(summonquery)
        summoneddog = dogs.find_one(summonquery)
        catfound = 0
        dogfound = 0
        #
        if summonedcat == None:
            catfound = 0
        else:
            catfound = 1
        if summoneddog == None:
            dogfound = 0
        else:
            dogfound = 1
        if catfound == 1 and dogfound == 1:
            bothpetsfoundmsg = await context.send("I found a cat and a dog with this name! Who would you want to fight for you? :eyes: ")
            for emoji in config_py.pet_emoji:
                await bothpetsfoundmsg.add_reaction(emoji)
            def check (reaction, user):
                return user.id == context.author.id and str(reaction) in config_py.pet_emoji
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                userChoiceEmote = reaction.emoji
                userChoiceIndex = config_py.pet_emoji[userChoiceEmote]
                if userChoiceIndex == 0:
                    await bothpetsfoundmsg.clear_reactions()
                    attackname = summonedcat.get("name")
                    attackurl = summonedcat.get("url")
                    attackwins = summonedcat.get("fightswon")
                    attacklosses = summonedcat.get("fightslost")
                    attacktype = summonedcat.get("type")
                    attackstrength = summonedcat.get("strength")
                    attackagility = summonedcat.get("agility")
                    attackintellect = summonedcat.get("intellect")
                    attackcharm = summonedcat.get("charm")
                    attackhp = summonedcat.get("hp")
                    attackbite = summonedcat.get("bite")
                    attackstrength = summonedcat.get("strength")
                    attackcritchance = summonedcat.get("critchance")
                    attackclaimres = summonedcat.get("claimres")
                    attackconversionchance = summonedcat.get("conversionchance")
                else:
                    await bothpetsfoundmsg.clear_reactions()
                    attackname = summoneddog.get("name")
                    attackurl = summoneddog.get("url")
                    attackwins = summoneddog.get("fightswon")
                    attacklosses = summoneddog.get("fightslost")
                    attacktype = summoneddog.get("type")
                    attackstrength = summoneddog.get("strength")
                    attackagility = summoneddog.get("agility")
                    attackintellect = summoneddog.get("intellect")
                    attackcharm = summoneddog.get("charm")
                    attackhp = summoneddog.get("hp")
                    attackbite = summoneddog.get("bite")
                    attackstrength = summoneddog.get("strength")
                    attackcritchance = summoneddog.get("critchance")
                    attackclaimres = summoneddog.get("claimres")
                    attackconversionchance = summoneddog.get("conversionchance")
        
            except asyncio.exceptions.TimeoutError:
                await bothpetsfoundmsg.clear_reactions()
            
        elif catfound == 1 and dogfound == 0:
            attackname = summonedcat.get("name")
            attackurl = summonedcat.get("url")
            attackwins = summonedcat.get("fightswon")
            attacklosses = summonedcat.get("fightslost")
            attacktype = summonedcat.get("type")
            attackstrength = summonedcat.get("strength")
            attackagility = summonedcat.get("agility")
            attackintellect = summonedcat.get("intellect")
            attackcharm = summonedcat.get("charm")
            attackhp = summonedcat.get("hp")
            attackbite = summonedcat.get("bite")
            attackstrength = summonedcat.get("strength")
            attackcritchance = summonedcat.get("critchance")
            attackclaimres = summonedcat.get("claimres")
            attackconversionchance = summonedcat.get("conversionchance")
        elif catfound == 0 and dogfound == 1:
            attackname = summoneddog.get("name")
            attackurl = summoneddog.get("url")
            attackwins = summoneddog.get("fightswon")
            attacklosses = summoneddog.get("fightslost")
            attacktype = summoneddog.get("type")
            attackstrength = summoneddog.get("strength")
            attackagility = summoneddog.get("agility")
            attackintellect = summoneddog.get("intellect")
            attackcharm = summoneddog.get("charm")
            attackhp = summoneddog.get("hp")
            attackbite = summoneddog.get("bite")
            attackstrength = summoneddog.get("strength")
            attackcritchance = summoneddog.get("critchance")
            attackclaimres = summoneddog.get("claimres")
            attackconversionchance = summoneddog.get("conversionchance")
        else:
            await context.send("I couldn't find any pets with that name in your collection :slight_frown: . Please check spelling and try again")
            return
        
        #finding opponentpet (type)
        name = theirpet
        summonquery = { "name" : name, "owner" : opponentid}
        summonedcat = cats.find_one(summonquery)
        summoneddog = dogs.find_one(summonquery)
        catfound = 0
        dogfound = 0
        #
        if summonedcat == None:
            catfound = 0
        else:
            catfound = 1
        if summoneddog == None:
            dogfound = 0
        else:
            dogfound = 1
        if catfound == 1 and dogfound == 1:
            bothpetsfoundmsg = await context.send("I found a cat and a dog with this name in your opponents collection! Who would you want to fight? :eyes: ")
            for emoji in config_py.pet_emoji:
                await bothpetsfoundmsg.add_reaction(emoji)
            def check (reaction, user):
                return user.id == context.author.id and str(reaction) in config_py.pet_emoji
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                userChoiceEmote = reaction.emoji
                userChoiceIndex = config_py.pet_emoji[userChoiceEmote]
                if userChoiceIndex == 0:
                    await bothpetsfoundmsg.clear_reactions()
                    defendname = summonedcat.get("name")
                    defendurl = summonedcat.get("url")
                    defendwins = summonedcat.get("fightswon")
                    defendlosses = summonedcat.get("fightslost")
                    defendtype = summonedcat.get("type")
                    defendstrength = summonedcat.get("strength")
                    defendagility = summonedcat.get("agility")
                    defendintellect = summonedcat.get("intellect")
                    defendcharm = summonedcat.get("charm")
                    defendhp = summonedcat.get("hp")
                    defendbite = summonedcat.get("bite")
                    defendstrength = summonedcat.get("strength")
                    defendcritchance = summonedcat.get("critchance")
                    defendclaimres = summonedcat.get("claimres")
                    defendconversionchance = summonedcat.get("conversionchance")
                else:
                    await bothpetsfoundmsg.clear_reactions()
                    defendname = summoneddog.get("name")
                    defendurl = summoneddog.get("url")
                    defendwins = summoneddog.get("fightswon")
                    defendlosses = summoneddog.get("fightslost")
                    defendtype = summoneddog.get("type")
                    defendstrength = summoneddog.get("strength")
                    defendagility = summoneddog.get("agility")
                    defendintellect = summoneddog.get("intellect")
                    defendcharm = summoneddog.get("charm")
                    defendhp = summoneddog.get("hp")
                    defendbite = summoneddog.get("bite")
                    defendstrength = summoneddog.get("strength")
                    defendcritchance = summoneddog.get("critchance")
                    defendclaimres = summoneddog.get("claimres")
                    defendconversionchance = summoneddog.get("conversionchance")
        
            except asyncio.exceptions.TimeoutError:
                await bothpetsfoundmsg.clear_reactions()
            
        elif catfound == 1 and dogfound == 0:
            defendname = summonedcat.get("name")
            defendurl = summonedcat.get("url")
            defendwins = summonedcat.get("fightswon")
            defendlosses = summonedcat.get("fightslost")
            defendtype = summonedcat.get("type")
            defendstrength = summonedcat.get("strength")
            defendagility = summonedcat.get("agility")
            defendintellect = summonedcat.get("intellect")
            defendcharm = summonedcat.get("charm")
            defendhp = summonedcat.get("hp")
            defendbite = summonedcat.get("bite")
            defendstrength = summonedcat.get("strength")
            defendcritchance = summonedcat.get("critchance")
            defendclaimres = summonedcat.get("claimres")
            defendconversionchance = summonedcat.get("conversionchance")
        elif catfound == 0 and dogfound == 1:
            defendname = summoneddog.get("name")
            defendurl = summoneddog.get("url")
            defendwins = summoneddog.get("fightswon")
            defendlosses = summoneddog.get("fightslost")
            defendtype = summoneddog.get("type")
            defendstrength = summoneddog.get("strength")
            defendagility = summoneddog.get("agility")
            defendintellect = summoneddog.get("intellect")
            defendcharm = summoneddog.get("charm")
            defendhp = summoneddog.get("hp")
            defendbite = summoneddog.get("bite")
            defendstrength = summoneddog.get("strength")
            defendcritchance = summoneddog.get("critchance")
            defendclaimres = summoneddog.get("claimres")
            defendconversionchance = summoneddog.get("conversionchance")
        else:
            await context.send("I couldn't find any pets with that name in your opponent's collection :angry: . Please check spelling and try again")
            return
        #asking the opponent for a challenge, increasing pet stats if they're not responding
        atk_r = requests.get(attackurl, timeout=4.0)
        with Image.open(io.BytesIO(atk_r.content)) as im:
            im.convert('RGB').save("duel_img/atk.jpg")
        def_r = requests.get(defendurl, timeout=4.0)
        with Image.open(io.BytesIO(def_r.content)) as im:
            im.convert('RGB').save("duel_img/def.jpg")
        
        list_im = ["duel_img/atk.jpg", "duel_img/versus.jpg", "duel_img/def.jpg"]
        imgs = [ PIL.Image.open(i) for i in list_im]
        min_shape = sorted( [(np.sum(i.size), i.size ) for i in imgs])[0][1]
        imgs_comb = np.hstack((np.asarray( i.resize(min_shape)) for i in imgs))
        imgs_comb = PIL.Image.fromarray( imgs_comb)
        imgs_comb.save('duel_img/duel.jpg')
        
        file = disnake.File("duel_img/duel.jpg", filename="duel.jpg")
        
        embed = disnake.Embed(description=f"Duel has been proposed! \n {context.author.display_name}'s **{attackname}** \n Strength: **{attackstrength}** \n Agility: **{attackagility}** \n Intellect: **{attackintellect}** \n Charm: **{attackcharm}** \n \n is challenging {opponent.display_name}'s **{defendname}** \n \n Strength: **{defendstrength}** \n Agility: **{defendagility}** \n Intellect: **{defendintellect}** \n Charm: **{defendcharm}** \n Will {opponent.display_name} accept the duel? ", color=config_py.success)
        embed.set_image(url="attachment://image.png")
        await context.send(file=file, embed=embed)
        
        #images = ["atk.jpg", 'versus.png']
        #for link in images: 
        #    urllib.request.urlopen(link)
        #starting the duel
        #loop of fight actions
        #saving the duel results
        #notifying the winner, updating stats
        
    
    @commands.command(
        name="snake",
        description="Show off your snake")
    @checks.not_blacklisted()
    async def snake(self, context: Context):
        await context.send(":snake:")

#########################
#                       #
#        HELPERS        #
#                       #
#########################
  
# FISHING TOGGLER 

    async def toggle_fishing(self, cat_id, user_id, channel_id):
        cats = config_py.catcollection
    
        # Fetch the cat from the collection
        cat = cats.find_one({'_id': cat_id})
        print(cat)
        if cat:
            cat_object_id = bson.ObjectId(cat_id)
            update_query = {'_id': cat_object_id}
            fishing_status = cat.get('FISHING', 0)  # Default to 0 if FISHING is not set
    
            if fishing_status == 1:
                # If fishing is already enabled, switch it to 0
                update_fields = {'$set': {'FISHING': 0}}
                cats.update_one(update_query, update_fields)
                await self.sendFishingNotification(channel_id, cat['name'], 1, 0)  # Notification for disabling fishing
            else:
                # If fishing is disabled, check the count of cats with fishing enabled
                count = await self.countCatsWithFishingEnabled(user_id)
                if count >= 25:
                    # If the count is already 25 or more, send an alert message
                    await self.sendFishingNotification(channel_id, cat['name'], 2, count)  # Notification for limit reached
                    return
                else:
                    # If the count is below 25, enable fishing for the cat
                    update_fields = {'$set': {'FISHING': 1}}
                    cats.update_one(update_query, update_fields)
                    await self.sendFishingNotification(channel_id, cat['name'], 0, count + 1)  # Notification for enabling fishing
        else:
            # Handle the case when the cat is not found
            print("Cat not found!")
            
# CAT COUNTER
    
    async def countCatsWithFishingEnabled(self, user_id):
        cats = config_py.catcollection
        query = {
            'owner': user_id,
            'FISHING': 1
        }
        count = cats.count_documents(query)
        return count   
        
    async def sendFishingNotification(self, channel_id, cat_name, fishing_status, count):
        channel = self.bot.get_channel(channel_id)
        
        if fishing_status == 0:
            await channel.send(f"{cat_name} can now fish!")
        elif fishing_status == 1:
            await channel.send(f"You took away {cat_name}'s fishing pole. They won't be able to fish anymore.")
        else:
            await channel.send(f"You already have 25 cats that can fish. Toggle one off, and {cat_name} will be able to join!")
       
############3 TOGGLE GYM ##################
    async def toggle_gym(self, cat_id, user_id, channel_id):
        cats = config_py.catcollection
    
        # Fetch the cat from the collection
        cat = cats.find_one({'_id': cat_id})
        print(cat)
        if cat:
            cat_object_id = bson.ObjectId(cat_id)
            update_query = {'_id': cat_object_id}
            gym_status = cat.get('GYM', 0)  # Default to 0 if GYM is not set
    
            if gym_status == 1:
                # If gym is already enabled, switch it to 0
                update_fields = {'$set': {'GYM': 0}}
                cats.update_one(update_query, update_fields)
                await self.sendGymNotification(channel_id, cat['name'], 1, 0)  # Notification for disabling gym
            else:
                # If gym is disabled, check the count of cats with gym enabled
                count = await self.countCatsWithGymEnabled(user_id)
                if count >= 25:
                    # If the count is already 25 or more, send an alert message
                    await self.sendGymNotification(channel_id, cat['name'], 2, count)  # Notification for limit reached
                    return
                else:
                    # If the count is below 25, enable gym for the cat
                    update_fields = {'$set': {'GYM': 1}}
                    cats.update_one(update_query, update_fields)
                    await self.sendGymNotification(channel_id, cat['name'], 0, count + 1)  # Notification for enabling gym
        else:
            # Handle the case when the cat is not found
            print("Cat not found!")
            
    async def countCatsWithGymEnabled(self, user_id):
        cats = config_py.catcollection
        query = {
            'owner': user_id,
            'GYM': 1
        }
        count = cats.count_documents(query)
        return count
    
    async def sendGymNotification(self, channel_id, cat_name, gym_status, count):
        channel = self.bot.get_channel(channel_id)
        
        if gym_status == 0:
            await channel.send(f"{cat_name} can now use the gym!")
        elif gym_status == 1:
            await channel.send(f"{cat_name} is no longer allowed to use the gym.")
        else:
            await channel.send(f"You already have 25 cats using the gym. Toggle one off, and {cat_name} will be able to join!")



def setup(bot):
    bot.add_cog(Pet(bot))

