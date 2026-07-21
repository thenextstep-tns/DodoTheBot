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
import anekos
import time
import openai

from anekos import NekosLifeClient, SFWImageTags
from asyncio import get_event_loop

import urllib.request
from urllib.request import urlopen

from bs4 import BeautifulSoup
from dadjokes import Dadjoke
from datetime import date
from collections import defaultdict

import re
import requests
import pymongo

import aiohttp
import disnake
from disnake.ext import commands
from disnake.ext.commands import Context

from helpers import checks

waifu = NekosLifeClient()

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

class Fun(commands.Cog, name="fun-normal"):
    def __init__(self, bot):
        self.bot = bot

#############################################
#              DODO THROW                   #
#############################################
#    @commands.command(name="throw", aliases=['toss'])
#    @checks.not_blacklisted()
#    async def throw(self, context, member: disnake.Member = None):
#        toss_message = await context.send(f"{context.author.mention} is about to throw {member.mention}!\nGuess the distance (in meters) in the next 10 seconds.")
#    
#        guesses = {}  # Dictionary to store guesses
#    
#        def is_integer(s):
#            try:
#                int(s)
#                return True
#            except ValueError:
#                return False
#    
#        def check_guess(message):
#            nonlocal guesses  # Declare guesses as a nonlocal variable
#            if message.author == context.author:
#                words = message.content.split()
#                valid_guesses = [int(word) for word in words if is_integer(word)]
#                if valid_guesses:
#                    # Assuming only the first valid integer found is the user's guess
#                    guesses[message.author.id] = valid_guesses[0]
#                    return True
#                return False
#    
#        try:
#            for i in range(10):
#                guess_message = await self.bot.wait_for('message', check=check_guess, timeout=5)
#                #await guess_message.delete()
#    
#            print (guesses)
#            await toss_message.edit(content=f"{context.author.mention} is throwing {member.mention}!\n Tossing...")
#            await asyncio.sleep(3)
#            min_distance = 1
#            max_distance = 100
#            toss_distance = random.randint(min_distance, max_distance)
#    
#            # Determine the winner based on the closest guess
#            closest_guess = None
#            closest_difference = max_distance
#            for user_id, guess in guesses.items():
#                difference = abs(toss_distance - guess)
#                if difference < closest_difference:
#                    closest_guess = user_id
#                    closest_difference = difference
#    
#            if closest_guess:
#                result_message = f"The toss distance was {toss_distance} meters.\n<@{closest_guess}> wins with a guess of {guesses[closest_guess]} meters!"
#            else:
#                result_message = f"The toss distance was {toss_distance} meters. No winner this time."
#    
#            await toss_message.edit(content=result_message)
#    
#        except asyncio.TimeoutError:
#            await toss_message.edit(content="Time's up! No valid guesses received.")

#############################################
#              DODO LOVE                    #
#############################################
    @commands.command(name="love", aliases = ['valentine', 'send love', 'smooch', 'send'], description = "Send a valentine to someone you deeply care for!")
    async def love(self, context, member : disnake.Member = None):
        """
        Send a valentine to someone you like
        """
        #channel = self.bot.get_channel(config_py.PET_CHANNEL)
        #if channel.id != context.message.channel.id:
        #    await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        valchannel = self.bot.get_channel(config_py.VALENTINE_CHANNEL)
        channel = self.bot.get_channel(context.message.channel.id)
        author = context.author
        ts = time.time()
        await context.message.delete()
        name = f"Sending a love letter to a very special someone at {ts}"
        await channel.create_thread(name=name)
        privatechannel = disnake.utils.get(context.guild.threads, name=name)
        print (channel.id)
        valpic = config_py.valentinegifs[random.randint(0, len(config_py.valentinegifs)-1)]
        await privatechannel.send("Hey there, " + "<@" + str(author.id) +">! I created this private thread for you to send a message. I will memorise it and send it to a specialised channel (" + "<#" + str(1072068365117562981) +">) which will be available on the Valentine's day! This thread is private, no one but us can see it! I will ask you just four questions and will await three responses, and then will save it all and delete the thread :heart: ")
        if not member:
            await privatechannel.send("QUESTION 1: **Who is your message for?**")
            def check(m):
            # we won't check the content here...
                return m.author.id == context.message.author.id 
            try:
                whomsg = await self.bot.wait_for('message', check=check, timeout = 30)
                who = whomsg.content
                
                ###
                await privatechannel.send("Now I need to know **who is the message FROM?** You can stay anonymous if you want to!")
                def check2(m):
                # we won't check the content here...
                    return m.author.id == context.message.author.id  
                try:
                    mfrom = await self.bot.wait_for('message', check=check2, timeout = 30)
                    await privatechannel.send("Nice! **Now is the time to write and send your message!**")
                    def check3(m):
                    # we won't check the content here...
                        return m.author.id == context.message.author.id 
                    try:
                        valmessage = await self.bot.wait_for('message', check=check3, timeout = 120)
                    except asyncio.exceptions.TimeoutError:
                        await privatechannel.send ("Timed out")
                        await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
                        await asyncio.sleep(10)
                        await privatechannel.delete()
                except asyncio.exceptions.TimeoutError:
                    await privatechannel.send ("Timed out")
                    await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
                    await asyncio.sleep(10)
                    await privatechannel.delete()
            except asyncio.exceptions.TimeoutError:
                await privatechannel.send ("Timed out")
                await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
                await asyncio.sleep(10)
                await privatechannel.delete()
            await privatechannel.send("Perfection! I will send a message from " + mfrom.content + " to " + who + "! The message will be:")
            await privatechannel.send(valmessage.content)
            
            embed = disnake.Embed(
                    title = f"{valmessage.content}",
                    description = f"To: {who}! From: {mfrom.content}",
                    color = config_py.success) 
            #embed.set_author(name=mfrom.content, icon_url=valpic)
            if member:
                await valchannel.send(f"<@{member.id}>! You got a valentine! :heart:" )
            await valchannel.send(embed = embed)
            await valchannel.send("= :heart: =")
            await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
            
            await asyncio.sleep(10)
            await privatechannel.delete()
            logschannel = self.bot.get_channel(config_py.LOG_CHANNEL)
            await logschannel.send (f"New valentine added! :smirk: {author} who said their name was {mfrom.content} sent this message to {who}: {valmessage.content}")
            
                ###
                
                
        else:
            who = member.name
            await privatechannel.send("Now I need to know **who is the message FROM?** You can stay anonymous if you want to!")
            def check2(m):
            # we won't check the content here...
                return m.author.id == context.message.author.id  
            try:
                mfrom = await self.bot.wait_for('message', check=check2, timeout = 30)
                await privatechannel.send("Nice! **Now is the time to write and send your message!**")
                def check3(m):
                # we won't check the content here...
                    return m.author.id == context.message.author.id 
                try:
                    valmessage = await self.bot.wait_for('message', check=check3, timeout = 120)
                except asyncio.exceptions.TimeoutError:
                    await privatechannel.send ("Timed out")
                    await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
                    await asyncio.sleep(10)
                    await privatechannel.delete()
            except asyncio.exceptions.TimeoutError:
                await privatechannel.send ("Timed out")
                await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
                await asyncio.sleep(10)
                await privatechannel.delete()
            
            await privatechannel.send("Perfection! I will send a message from " + mfrom.content + " to " + who + "! The message will be:")
            await privatechannel.send(valmessage.content)
            
            embed = disnake.Embed(
                    title = f"{valmessage.content}",
                    description = f"To: {who}! From: {mfrom.content}",
                    color = config_py.success) 
            #embed.set_author(name=mfrom.content, icon_url=valpic)
            if member:
                await valchannel.send(f"<@{member.id}>! You got a valentine! :heart: :arrow_down:" )
            await valchannel.send(embed = embed)
            await valchannel.send("= :heart: =")
            
            await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Love! :heart: ")
            
            await asyncio.sleep(10)
            await privatechannel.delete()
            logschannel = self.bot.get_channel(config_py.LOG_CHANNEL)
            await logschannel.send (f"New valentine added! :smirk: {author} who said their name was {mfrom.content} sent this message to {who}: {valmessage.content}")
            
      
#############################################
#              DODO VOTE                    #
#############################################
    @commands.command(name="vote", aliases = ['doty'], description = "Vote for the Dodo of the Year!")
    async def vote(self, context):
        """
        Vote for the Dodo of the Year!
        """
        #channel = self.bot.get_channel(config_py.PET_CHANNEL)
        #if channel.id != context.message.channel.id:
        #    await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        votes = config_py.votes
        author = context.author
        if votes.find_one({"user_id": str(author.id)}):
            await context.send("Looks like you have already voted in this round! If you feel like you did some oopsie :dodo: in your votes, please poke Fox!")
            return
        votechannel = self.bot.get_channel(config_py.DOTY_CHANNEL)
        channel = self.bot.get_channel(context.message.channel.id)
        ts = time.time()
        await context.message.delete()
        name = f"Vote at {ts}"
        await channel.create_thread(name=name)
        privatechannel = disnake.utils.get(context.guild.threads, name=name)
        print (channel.id)
        # valpic = config_py.valentinegifs[random.randint(0, len(config_py.valentinegifs)-1)]
        await privatechannel.send("Hey there, " + "<@" + str(author.id) +">! I created this private thread for you to send a message. I will memorise it and send it to a specialised channel (" + "<#" + str(1183470942928765028) +">) which will be available for everyone at the end of round 1! This thread is private, no one but us can see it! I will ask you just three questions and will await three responses, and then will save it all and delete the thread :heart: ")
        if privatechannel:
            await privatechannel.send(f"## Please note, that both Salvy and Fox are not participating in the votes \nDon't vote for them even if you really want to :hearts: ")
            await privatechannel.send(f"Time to nominate 3 people! \nYou have 60 seconds to answer every question \n# NOMINATION 1: **THE ROLE MODEL** \nIt's the person who sets an example showcasing exceptional skills, knowledge and dedication, always ready to support others, share their wisdom and help.")
            def check(m):
            # we won't check the content here...
                return m.author.id == context.message.author.id 
            try:
                whomsg = await self.bot.wait_for('message', check=check, timeout = 180)
                rolemodel = whomsg.content
                
                ###
                await privatechannel.send(f"Great! \n# NOMINATION 2: **THE PROGRESS OF THE YEAR** \nIt's the person who you think has achieved the breakthrough in their progress in the game, or found a fundamentally new role in the community, and leveled up as a Dodo significantly!")
                def check2(m):
                # we won't check the content here...
                    return m.author.id == context.message.author.id  
                try:
                    progress = await self.bot.wait_for('message', check=check2, timeout = 180)
                    await privatechannel.send("Thank you! \n# NOMINATION 3: **THE COMMUNITY BUILDER OF THE YEAR** \nIt's a very special someone who creates a cosiness and respect that has made you find your place in our community and happy to check out Discord posts")
                    def check3(m):
                    # we won't check the content here...
                        return m.author.id == context.message.author.id 
                    try:
                        community = await self.bot.wait_for('message', check=check3, timeout = 180)
                    except asyncio.exceptions.TimeoutError:
                        await privatechannel.send ("Timed out")
                        await privatechannel.send("The first round of the votes closes on 17.12! That's when we will know the first results! Thank you for using Dodo Vote! :heart: ")
                        await asyncio.sleep(10)
                        await privatechannel.delete()
                except asyncio.exceptions.TimeoutError:
                    await privatechannel.send ("Timed out")
                    await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Vote! :heart: ")
                    await asyncio.sleep(10)
                    await privatechannel.delete()
            except asyncio.exceptions.TimeoutError:
                await privatechannel.send ("Timed out")
                await privatechannel.send("Just like my family, this thread will now disappear. Thank you for using Dodo Vote! :heart: ")
                await asyncio.sleep(10)
                await privatechannel.delete()
            
            embed = disnake.Embed(
                    title = f"Nominations from {context.author}",
                    description = f"THE ROLE MODEL: {rolemodel}! \n PROGRESS OF THE YEAR: {progress.content} \n COMMUNITY BUILDER: {community.content} ",
                    color = config_py.success) 
            #embed.set_author(name=mfrom.content, icon_url=valpic)
            await votechannel.send(embed = embed)
            await votechannel.send("= :heart: =")
            vote_data = {
                "user_id": str(author.id),
                "role_model": rolemodel,
                "progress_of_the_year": progress.content,
                "community_builder": community.content
            }
            votes.insert_one(vote_data)
            await privatechannel.send("The first round of the votes closes on 17.12! That's when we will know the first results! Thank you for participating! :heart: ")
            
            await asyncio.sleep(10)
            await privatechannel.delete()
            logschannel = self.bot.get_channel(config_py.LOG_CHANNEL)
            

#############################################
#              DODO RESET                   #
#############################################


    @commands.command(name="resetvote", aliases=['resetdoty'], description = "Resets the voting status for a specific user. Only available for bot owners.")
    @checks.is_owner() 
    async def reset_vote(self, context, user: disnake.User):
        # Reset the voting status for a specific user
        if user.id in self.voting_status:
            self.voting_status[user.id] = False
            await context.send(f"Vote status for {user.mention} has been reset.")
        else:
            await context.send("User not found in the voting status records.")


#############################################
#              DODO CHAT                    #
#############################################
#    @commands.command(name="chat", description = "A helper command that is called every time you mention Dodo to trigger a reply. Can be ignored.")
#    async def chat(self, context, *, message):
#        """
#        Chat to DodoGPT
#        """
#        channel = self.bot.get_channel(config_py.PET_CHANNEL)
#        openai.api_key = config_py.PROXY_API
#        print("We started talking")
#        openai.api_base = "https://api.proxyapi.ru/openai/v1"
#        
#        # Create a list to store the response message(s)
#        response_messages = []
#    
#        chat_completion = openai.ChatCompletion.create(
#            model="gpt-4o", 
#            temperature=1, 
            #max_tokens=250,  # Adjust this value as needed
#            messages=[{"role": "system", "content": "You are a Dodo, helpful, naive and kind bird that wishes well sometimes ends up being clumsy and saying some kind but stupid stuff. You main home is the ESO for Dodos Discord server that is dedicated new players to get into ESO end-game. You speak in a concise and clear but friendly language"}, {"role": "user", "content": f"{message}"}])
    
        # Get the response content
#        response_content = chat_completion.choices[0].message.content
        
        # Split the response into multiple messages if it's too long
#        while response_content:
            # Determine how many characters to send in this message
#            chars_to_send = min(len(response_content), 1990)
            
            # Create the message
#            response_message = response_content[:chars_to_send]
#            response_content = response_content[chars_to_send:]
            
            # Send the message
#            response_messages.append(response_message)
    
        # Send all response messages
#        for response_message in response_messages:
#            await context.send(response_message)

#############################################
#              DODO CRINGE                  #
#############################################
    @commands.command(name="cringe", description = "Assembles the cringe team randomly")
    @checks.not_blacklisted()
    async def cringe(self, context):
        """
        Assembles the cringe team randomly
        """
        cringe = config_py.CRINGE
        cringechoice = cringe[random.randint(0, len(cringe)-1)]
        user = await self.bot.fetch_user(cringechoice)
        challenge = random.choice(config_py.CHALLENGES)
        await context.send(f"{user.mention} You have been chosen for the cringe team! \nHEED THE CALL, your cringe challenge is: {challenge}! Good luck, and may the cringe be with you!")


#############################################
#           DODO D20 BLOCK                  #
#############################################

    @commands.command(name="d20", description="Rolls a 20-sided die with an optional modifier")
    @checks.not_blacklisted()
    async def d20(self, context, modifier: int = 0):
        """
        Rolls a 20-sided die. Accepts an optional integer modifier.
        """
        roll_result = random.randint(1, 20)
        total = roll_result + modifier

        if modifier == 0:
            message = f"You rolled: **{roll_result}**"
        else:
            modifier_sign = "+" if modifier > 0 else ""
            message = f"You rolled: **{roll_result}** {modifier_sign}{modifier} = **{total}**"

        if roll_result == 20:
            message += "\n **Critical Success!**"
        elif roll_result == 1:
            message += "\n **Critical Failure!**"

        await context.send(message)

    @commands.command(name="d20m", description="Gather players to roll a d20 multiplayer style")
    @checks.not_blacklisted()
    async def d20m(self, context):
        """
        Gathers dice reactions for a set time, then rolls a d20 for everyone who reacted.
        """
        join_msg = await context.send(f"React with the dice emoji within 7 seconds to join the d20 roll!")
        await join_msg.add_reaction("\U0001f3b2")

        await asyncio.sleep(7)

        # Re-fetch the message to get the latest reactions
        join_msg = await context.channel.fetch_message(join_msg.id)
        
        reaction = next((r for r in join_msg.reactions if str(r.emoji) == "\U0001f3b2"), None)
        
        players = []
        if reaction:
            async for user in reaction.users():
                if not user.bot:
                    players.append(user)

        # Clear reactions (requires manage_messages permission)
        try:
            await join_msg.clear_reactions()
        except disnake.Forbidden:
            pass 

        if not players:
            await context.send("No one joined the roll in time.")
            return

        # Roll for everyone
        results = {player: random.randint(1, 20) for player in players}
        max_roll = max(results.values())
        winners = [player for player, roll in results.items() if roll == max_roll]

        # Build results embed
        embed = disnake.Embed(title="Multiplayer d20 Results", color=disnake.Color.blurple())
        
        description_lines = []
        for player, roll in sorted(results.items(), key=lambda item: item[1], reverse=True):
            description_lines.append(f"{player.mention}: **{roll}**")
        
        embed.description = "\n".join(description_lines)

        if len(winners) == 1:
            embed.add_field(name="Winner", value=f"{winners[0].mention} wins with a roll of {max_roll}!", inline=False)
        else:
            winner_mentions = ", ".join(w.mention for w in winners)
            embed.add_field(name="Tie!", value=f"{winner_mentions} tied with a roll of {max_roll}!", inline=False)

        await context.send(embed=embed)
        

#############################################
#              DODO CHAT                    #
#############################################
    @commands.command(name="imagine", description = "Imagines something using DodoGPT. Currently only available for Salvy and Fox due to budgeting limitations (imagination costs money :( ).")
    @checks.is_owner()
    async def imagine(self, context, *, message):
        """
        Chat to DodoGPT
        """
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        openai.api_key = config_py.PROXY_API
        print("We started imagining")
        imagine_message = await context.send(":thinking: Give me a few seconds please, I'm gonna do my very best!")
        openai.api_base = "https://api.proxyapi.ru/openai/v1"
    
        response = openai.Image.create(
            model="dall-e-3",
            prompt = message,
            n = 1,
            size="1024x1024")
        
        image_url = response.data[0].url
        await imagine_message.edit(content=f"{image_url}")



        
#############################################
#               DODO MICE                   #
#############################################

    def most_successful_mice(self, user_id):
        Races = config_py.races
        race_documents = Races.find()
        mouse_stats = defaultdict(lambda: {'races_won': 0, 'total_position': 0, 'race_count': 0})
        
        for race in race_documents:
            for participant in race['participants']:
                if 'user_id' in participant and 'mouse_name' in participant and 'position' in participant:
                    user_id_participant = participant['user_id']
                    if isinstance(user_id_participant, dict) and '$numberLong' in user_id_participant:
                        user_id_participant = str(user_id_participant['$numberLong'])
                    else:
                        user_id_participant = str(user_id_participant)

                    position = participant['position']
                    if isinstance(position, dict) and '$numberInt' in position:
                        position = int(position['$numberInt'])
                    else:
                        position = int(position)

                    if user_id_participant == str(user_id):
                        mouse_name = participant['mouse_name']
                        
                        if position == 1:
                            mouse_stats[mouse_name]['races_won'] += 1
                        
                        mouse_stats[mouse_name]['total_position'] += position
                        mouse_stats[mouse_name]['race_count'] += 1
        
        for mouse in mouse_stats:
            mouse_stats[mouse]['average_position'] = mouse_stats[mouse]['total_position'] / mouse_stats[mouse]['race_count']
        
        sorted_mice = sorted(mouse_stats.items(), key=lambda x: (-x[1]['races_won'], x[1]['average_position']))[:10]
        return sorted_mice

    @commands.command(name="mice", description="Check your most successful mice!")
    async def mice(self, context, member: disnake.Member = None):
        """
        Check your most successful mice
        """

        if not member:
            member = context.author

        sorted_mice = self.most_successful_mice(member.id)

        if sorted_mice:
            response_lines = [f"**{member.display_name}'s Most Successful Mice:**\n"]
            for idx, (mouse, stats) in enumerate(sorted_mice, start=1):
                line = f"{idx}. **{mouse}**, Wins: {stats['races_won']}, Avg Position: {stats['average_position']:.2f}\n"
                response_lines.append(line)
            
            response = ''.join(response_lines)

            # Split the response if it exceeds the character limit
            if len(response) > 1999:
                parts = [response[i:i+1999] for i in range(0, len(response), 1999)]
            else:
                parts = [response]

            for part in parts:
                await context.send(part)
        else:
            await context.send("Looks like you don't have any race records yet! Start participating in races to see your stats :dodo:")

    
#############################################
#              DODO WALLET                  #
#############################################
    @commands.command(name="wallet", description = "Check your Dodo Bank account!")
    async def wallet(self, context, member : disnake.Member = None):
        """
        Check your bank account
        """
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        if not member:
            member = context.author
        wallets = config_py.wallets
        wallet = wallets.find_one({"user_id": member.id})
        if wallet:
            balance = wallet["balance"]
            await channel.send(f"You have {balance} coins in your wallet!")
        else:
            await channel.send("Looks like you don't really have a wallet! But fear not! We will make you one this instant :dodo: ")
            new_wallet = {"user_id": member.id, "balance": 0}
            result = wallets.insert_one(new_wallet)

#############################################
#           DODO PARSES                     #
#############################################
    @commands.command(name="topparses", description="Show the list of top-10 dodo parse users!")
    async def top_parses(self, context):
        parses = config_py.parses
        top_parses = parses.find(
            {"Championship Parse": 1}
        ).sort("Parse", pymongo.DESCENDING).limit(10)
    
        embed = disnake.Embed(title="Top 10 Parses", color=disnake.Color.green())
    
        for index, parse in enumerate(top_parses, start=1):
            user = self.bot.get_user(parse["ID"])
            if user is None:
                user = await self.bot.fetch_user(parse["ID"])
    
            # Unicode emoji format
            embed.add_field(
                name=f"{index}. {user.display_name}",
                value=f"\U0001F3AF Parse: {parse['Parse']} | {parse['Date']} | Difficulty: {parse['Difficulty Level']}",
                inline=False
            )
    
        await context.send(embed=embed)
        
#####################################
#      DODO BOTTOMFEEDERS           #
#####################################

    @commands.command(name="bottomparses", description = "Show the bottom-10 list of the dodo parse users! Hey, it takes talent too!!")
    async def bottom_parses(self, context):
        parses = config_py.parses
        top_parses = parses.find(
            {"Championship Parse": 1}
        ).sort("Parse", pymongo.ASCENDING).limit(10)
    
        embed = disnake.Embed(title="Bottom 10 Parses", color=disnake.Color.green())
    
        for index, parse in enumerate(top_parses, start=1):
            user = self.bot.get_user(parse["ID"])
            if user is None:
                user = await self.bot.fetch_user(parse["ID"])
    
            # Unicode emoji format
            embed.add_field(
                name=f"{index}. {user.display_name}",
                value=f"\U0001F3AF Parse: {parse['Parse']} | {parse['Date']} | Difficulty: {parse['Difficulty Level']}",
                inline=False
            )
    
        await context.send(embed=embed)
        



#############################################
#              DODO ROAST                  #
#############################################
    
    @commands.command(
        name="roast",
        description="Insult someone in style")
    @checks.not_blacklisted()
    
    async def insult(self, context: Context, member: disnake.Member = None):
        """
        Insult someone in style
        """
        if not member:
            member = context.author
            await context.send ("Do you really wanna insult yourself? Even to a Dodo like me, it's a bit too much.")
            insult1 = lang.INSULT_1[random.randint(0, len(lang.INSULT_1)-1)]
            insult2 = lang.INSULT_2[random.randint(0, len(lang.INSULT_2)-1)]
            insult3 = lang.INSULT_3[random.randint(0, len(lang.INSULT_3)-1)]
            await context.send(f"{member.display_name}, thou {insult1} {insult2} {insult3}!")
        elif member.id == 824171812518494238:
            await context.send (lang.DODO_INSULT[random.randint(0, len(lang.DODO_INSULT)-1)])
        else:
            insult1 = lang.INSULT_1[random.randint(0, len(lang.INSULT_1)-1)]
            insult2 = lang.INSULT_2[random.randint(0, len(lang.INSULT_2)-1)]
            insult3 = lang.INSULT_3[random.randint(0, len(lang.INSULT_3)-1)]
            await context.send(f"{member.display_name}, thou {insult1} {insult2} {insult3}!")


#############################################
#              DODO AVGPP                   #
#############################################
    
    @commands.command(
        name="checkpp",
        description="Checks the average pp towards someone else")
    @checks.not_blacklisted()
    
    async def checkpp(self, context: Context, member: disnake.Member = None, target: disnake.Member = None):
        """
        Check the length of your or someone else's pp
        """
        pps = config_py.pps
        
        if not member:
            member = context.author
        if not target:
            target = context.author
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        
        ppcheck = list(pps.find({ "MeasuredUser" : member.id, "ThoughtOfUser" : target.id }))
        print (ppcheck)
        
        ppsum = 0
        ppcount = 0
        for Item in ppcheck:
            ppsum += Item["PPlength"]
            ppcount = ppcount + 1 
        
        
        
        if ppsum == 0:
            await channel.send ("We haven't checked how this combination would affect their pps yet! Use dodo pp to check it!")
        else:
            length = int(ppsum / ppcount)
            if channel.id != context.message.channel.id:
                await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
            
            if target == member:
                targetname = "themselves"
            else:
                targetname = target.display_name
                
            embed = disnake.Embed(
                    title = f"How much does {member.display_name} like {targetname} on average??",
                    description = f"8{'='*length}D", color=config_py.success)
            await channel.send (embed = embed)


#############################################
#              DODO PRIORITIES              #
#############################################
    
    @commands.command(
        name="priorities",
        description="Lists all your favourite people")
    @checks.not_blacklisted()
    
    async def pplist(self, context: Context, member: disnake.Member = None):
        """
        Lists all your favourite people
        """
        pps = config_py.pps
        
        if not member:
            member = context.author
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")        
        ppschecked = pps.find( { "MeasuredUser": member.id } )
        ppscheckedcount = ppschecked.count()
        
        if ppscheckedcount == 0:
            await channel.send ("You haven't used our dodo pp command yet! Never late to start! :eggplant: ")
        
        else:
            # Calculate average PPlength for each ThoughtOfUser separately
            pipeline = [
                {"$match": {"MeasuredUser": member.id}},
                {"$group": {"_id": "$ThoughtOfUser", "avg_pplength": {"$avg": "$PPlength"}}}
            ]
            cursor = pps.aggregate(pipeline)
            
            # Collect results and sort them in descending order
            results = []
            for document in cursor:
                results.append({"user": document["_id"], "avg_pplength": document["avg_pplength"]})
            sorted_results = sorted(results, key=lambda x: x["avg_pplength"], reverse=True)
            
            # Format and send the results
            if len(sorted_results) == 0:
                await channel.send("You haven't used our dodo pp command yet! Never late to start! :eggplant:")
            else:
                message = f"Here are your priorities, {member.mention}:"
                for i, result in enumerate(sorted_results, start=1):
                    user = await self.bot.fetch_user(result["user"])
                    avg_pplength = result["avg_pplength"]
                    bars = "=" * int(avg_pplength)
                    message += f"\n{i}. **{user.name}**: \n 8{bars}D"
                await channel.send(message)


#############################################
#              DODO HOTGIRLS                #
#############################################
    
    @commands.command(
        name="hotties",
        description="Show the most desirable hotties on the server")
    @checks.not_blacklisted()
    
    async def hotties(self, context: Context, member: disnake.Member = None):
        """
        Show the most desirable hotties on the server
        """
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")        
        pps = config_py.pps
        pipeline = [
            {"$group": {"_id": "$ThoughtOfUser", "avg_pplength": {"$avg": "$PPlength"}}},
            {"$sort": {"avg_pplength": -1}}
        ]
        cursor = pps.aggregate(pipeline)
        
        # Collect results and format them
        results = []
        for document in cursor:
            results.append({"user": document["_id"], "avg_pplength": document["avg_pplength"]})
        
        if len(results) == 0:
            await channel.send("Nobody has been thought of yet! :thinking:")
        else:
            message = "Here are the most desired hot girls in your area :tired_face: :"
            for i, result in enumerate(results, start=1):
                user = await self.bot.fetch_user(result["user"])
                avg_pplength = result["avg_pplength"]
                bars = "=" * int(avg_pplength)
                message += f"\n{i}. **{user.name}**: \n 8{bars}D"
            await channel.send(message)

#############################################
#              DODO PP                      #
#############################################
    
    @commands.command(
        name="pp",
        description="Check the length of your or someone else's pp")
    @checks.not_blacklisted()
    
    async def pp(self, context: Context, member: disnake.Member = None, target: disnake.Member = None):
        """
        Check the length of your or someone else's pp
        """
        pps = config_py.pps
        
        if not member:
            member = context.author
        if not target:
            target = context.author
        
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        length = random.randrange(15)
        if target == member:
            targetname = "themselves"
        else:
            targetname = target.display_name
        if length < 2:
            embed = disnake.Embed(
                title = f"{member.display_name}'s pp when thinking of {targetname}! Oops!",
                description = "This pp is too small to display. Maybe it's cold where you are?",
                color = config_py.warning)
        else:
            embed = disnake.Embed(
                title = f"We caught {member.display_name} thinking of {targetname}! :smirk: ",
                description = f"8{'='*length}D", color=config_py.success)
            
        ppobj = {
            "MeasuredUser" : member.id,
            "ThoughtOfUser" : target.id,
            "PPlength" : length,
        }
        pps.insert_one(ppobj)
        await channel.send(embed = embed)


#############################################
#              DODO GAY                     #
#############################################
    
    @commands.command(
        name="gay",
        description="Check how gay someone is at this very moment ")
    @checks.not_blacklisted()
    
    async def gay(self, context: Context, member: disnake.Member = None):
        """
        Check how gay someone is at this very moment
        """
        if not member:
            member = context.author
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        gayness = random.randint(0, 100)
        
        straightjokes = ["The only thing you see in the LGBT flag are straight lines...", "When you play chess you only use rooks, because they go straight.",
        "When someone asks you directions, you always tell them to go straight", "Straighter than a ruler!", "You must be really good at playing poker, since you always keep a straight face", "Keep it up, breeder :heart: "]
        slightlygayjokes = ["You are on the right path!"]
        mediumgayjokes = ["That actually explains so much... :open_mouth: "]
        fouranswer = ["I once yelled COW! at a woman on a bicycle and she gave me the middle finger. Then she plowed her bike straight into the cow... I know it's unrelated, just wanted to share"]
        heavygayjokes = ["I hope you never have to pass the walk and turn test :pleading_face: ", "It made me remember that argument we had, when we were constantly going in circles..."]
        fullgayjokes = ["You look fantastic, no hetero :smirk: Must be all the time you've spent in the closet!", "The time has come for the Vestige to know the truth!", "I would ask you how it feels to be so gay, but I'm afraid I wouldn't get a straight answer"]
        
        
        if gayness == 4:
            phrase = fouranswer[random.randint(0, len(fouranswer)-1)]
        if gayness < 20:
            phrase = straightjokes[random.randint(0, len(straightjokes)-1)]
        elif gayness < 40:
            phrase = slightlygayjokes[random.randint(0, len(slightlygayjokes)-1)]
        elif gayness < 60:
            phrase = mediumgayjokes[random.randint(0, len(mediumgayjokes)-1)]
        elif gayness < 80:
            phrase = heavygayjokes[random.randint(0, len(heavygayjokes)-1)]
        else:
            phrase = fullgayjokes[random.randint(0, len(fullgayjokes)-1)]
        embed = disnake.Embed(
                title = f"{member.display_name}, we checked your momentary gayness, and here's the result!",
                description = f"{member.display_name}, you are {gayness}% gay! {phrase}",
                color = config_py.warning) 
        await channel.send(embed = embed)



#############################################
#              DODO PARSE                   #
#############################################
    
    @commands.command(
        name="parseold",
        description="Old version that doesn't require any skill")
    @commands.cooldown(1, 5, commands.BucketType.user)    
    @checks.not_blacklisted()
    
    async def parse(self, context: Context, member: disnake.Member = None):
        """
        Parse the dummy and see the result!
        """
        parses = config_py.parses
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        if not member:
            member = context.author
        parse = random.randrange(config_py.max_parse)
        parseTime = round(config_py.dummy_health/parse)
        parseTimeMinutes = round(config_py.dummy_health/parse/60)
        parseTimeSeconds = parseTime - parseTimeMinutes
        if parse < 15000:
            embed = disnake.Embed(description=f"{parse} DPS... Please leave the server", color=config_py.error)
            embed.set_author(name=f"{member.display_name} couldn't handle pressing 5 buttons, and gave up after {parseTimeMinutes} of whatever it was with the result of...", icon_url=member.display_avatar)
        elif parse < 50000:
            embed = disnake.Embed(description=f"{parse} DPS. You must be new here :) ", color=config_py.error)
            embed.set_author(name=f"{member.display_name}, is that... a heavy attack build? {parseTimeMinutes} minutes well wasted, your result is...", icon_url=member.display_avatar)
        elif parse < 70000:
            embed = disnake.Embed(description=f"{parse} DPS. A little bit more and you will look like a proper Veteran!", color=config_py.warning)
            embed.set_author(name=f"{member.display_name} parsed the dummy for {parseTimeMinutes} minutes with the result of...", icon_url=member.display_avatar)
        elif parse < 100000:
            embed = disnake.Embed(description=f"{parse} DPS! Sub 100k is so 2020", color=config_py.warning)
            embed.set_author(name=f"{member.display_name} parsed the dummy for {parseTimeMinutes} minutes with a result of...", icon_url=member.display_avatar)
        elif parse < 120000:
            embed = disnake.Embed(description=f"{parse} DPS! Is that an actual redguard magden?", color=config_py.success)
            embed.set_author(name=f"{member.display_name} demolished the trial dummy in {parseTimeMinutes} minutes with a result of...", icon_url=member.display_avatar)
        elif parse < 139999:
            embed = disnake.Embed(description=f"{parse} DPS! Keegan would be proud. Ping him if you dare xD ", color=config_py.success)
            embed.set_author(name=f"{member.display_name} evaporated the poor atronach dummy in {parseTimeMinutes} minutes with a result of...", icon_url=member.display_avatar)
        elif parse > 140000:
            embed = disnake.Embed(description=f"{parse} DPS! vote to kick", color=config_py.success)
            embed.set_author(name=f"Deniz, relog.", icon_url=member.display_avatar)
        await channel.send(embed=embed)
        today = date.today().isoformat()
        parseobj = {
            "Name" : member.display_name,
            "ID" : member.id,
            "Date" : today,
            "Parse" : parse
        }
        parses.insert_one(parseobj)

#############################################
#              DODO WISDOM                  #
#############################################
    
    @commands.command(
        name="wisdom",
        description="Show an inspirational message to someone you deeply care about!")
    @checks.not_blacklisted()
    
    async def wisdom(self, context: Context, member: disnake.Member = None):
        """
        Show an inspirational message to you or someone you deeply care about!
        """
        if not member:
            member = context.author
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        quote = inspirobot.generate()
        inspirobot.HTTPS = False
        embed = disnake.Embed(
            title= "This may change your life",
            color = config_py.success
            )
        embed.set_image(url = quote.url)
        embed.set_author(name = f"{member.display_name},")
        await channel.send(embed = embed)
            

#############################################
#              DODO FUTURE                  #
#############################################
    @commands.command(name="future", description = "Spawn a random Taro card to predict your or someone else's future!")
    @checks.not_blacklisted()
    async def tarot(self, context: Context, member : disnake.Member = None):
        """
        Make dodo show you a single Tarot card
        """
        if not member:
            member = context.author
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        URL = "http://chaoticshiny.com/tarotgen.php"
        soup = BeautifulSoup(urlopen(URL), 'html.parser')
        tarot = soup.find_all("div", {"id": "output"})
        print (tarot)
        tarotsides = ["not inverted", "inverted"]
        tarotside = 0
        tarotroll = random.randint(0, 10)
        if tarotroll > 5:
            tarotside = tarotsides[1]
        else:
            tarotside = tarotsides[0]
        tarotname = tarot[0].contents[0].next_sibling.get_text()
        tarotdescription = tarot[0].contents[0].next_sibling.next_sibling.next_sibling
        #print (tarot[0].contents[0].next_sibling.next_sibling.next_sibling)
        #tarotmessage = tarot[0].contents[0]
        #print (soup.get_text(tarot[0].contents[0]))
       
        #tarotname = tarot.find("b")
        #print (tarotname)
        
        await channel.send(f"{member.display_name}, I see {tarotname}. The card is {tarotside}")
        await channel.send(tarotdescription)    



#############################################
#              DODO ROLL                    #
#############################################
    
    @commands.command(
        name="roll",
        description="Challenge your friend to a death roll!")
    @checks.not_blacklisted()
    async def deathroll(self, context: Context, bet, opponent : disnake.Member = None):
        """
        Challenge your friend to a death roll
        """
        channel = self.bot.get_channel(config_py.ROLL_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.ROLL_CHANNEL) + ">")
        rolls = config_py.dodoroll
        challenger = context.author
        betint = int(bet)
        if betint > config_py.roll_limit:
            await channel.send(lang.ROLL_OVER_LIMIT)
            betfinal = config_py.roll_limit
        else:
            betfinal = bet
        betfinalint = int(betfinal)
        challengerid = context.author.id
        challengername = context.author.display_name
        if not opponent:
            await channel.send(lang.ROLL_NO_OPPONENT)
            return
        elif opponent.id == challenger.id:    
            await channel.send(lang.ROLL_SELF_PLAY)
            return
        else:
            opponentid = opponent.id
            opponentname = opponent.name
            challengemsg = await channel.send (f"**{challengername}** just challenged **{opponentname}** for **{betfinal} gold**! **<@{opponentid}>**, if you are willing to accept the fight, press the dice emoji under this message and let the battle begin!")
            for emoji in config_py.roll_challenge_emoji:
                await challengemsg.add_reaction(emoji)
            def check (reaction, user):
                return user.id == opponentid and str(reaction) in config_py.roll_challenge_emoji
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=300, check=check)
                userChoiceEmote = reaction.emoji
                userChoiceIndex = config_py.roll_challenge_emoji[userChoiceEmote]
                if userChoiceIndex == 1:
                    await challengemsg.clear_reactions()
                    await channel.send (f"{opponentname} declined the duel! :slight_frown: ")
                else:
                    await channel.send (lang.ROLL_DUEL_ACCEPTED)
                    
                    #Duel starts
                    areDuelling = 1
                    currentroll = betfinalint
                    currentroller = opponent
                    notcurrentroller = context.author
                    rounds = 0
                    while areDuelling == 1:
                        rounds = rounds + 1
                        diceteaser = await context.send(config_py.dice_gifs[random.randint(0, len(config_py.dice_gifs)-1)])
                        await asyncio.sleep(random.randint(1, 3))
                        await diceteaser.delete()
                        nextroll = random.randint(1, currentroll-1)
                        if nextroll == 1:
                            embed = disnake.Embed(
                                description = f"**{currentroller.display_name}** rolled **1** and has lost the duel. Congratulations to {notcurrentroller.display_name} on winning **{bet}** gold!",
                                title = lang.ROLL_TITLE_LOSS,
                                color = config_py.error
                                )
                            await channel.send(embed=embed)
                            areDuelling = 0
                            today = date.today().isoformat()
                            #forming and posting the obj to db
                            
                            duel = {
                                "Date" : today,
                                "Bet" : betfinalint,
                                "Challenger" : challengername,
                                "Challenger ID" : challengerid,
                                "Opponent" : opponentname,
                                "Opponent ID" : opponentid,
                                "Number of rounds" : rounds,
                                "Winner" : notcurrentroller.display_name,
                                "Winner ID" : notcurrentroller.id,
                                "Loser" : currentroller.display_name,
                                "Loser ID" : currentroller.id,
                            }
                            rolls.insert_one(duel)
                            await channel.send(lang.ROLL_DUEL_OVER)
                            channel = self.bot.get_channel(config_py.roll_log)
                            await channel.send(f"**{notcurrentroller.display_name}** won a duel against **{currentroller.display_name}** for **{bet}** gold!")
                            
                        else:
                            embed = disnake.Embed(
                                description = f"**{currentroller.display_name}** rolled **{nextroll}**! How will {notcurrentroller.display_name} respond?",
                                title = lang.ROLL_DUEL_ACCEPTED,
                                color = config_py.warning
                                )
                            nextrollmsg = await channel.send(embed=embed)
                            for emoji in config_py.roll_duel_emoji:
                                await nextrollmsg.add_reaction(emoji)
                            def nextcheck(reaction, user):
                                return user.id == notcurrentroller.id and str(reaction) in config_py.roll_duel_emoji
                            try:
                                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=nextcheck)
                                await nextrollmsg.clear_reactions()
                                if currentroller == opponent:
                                    currentroller = challenger
                                    notcurrentroller = opponent
                                else:
                                    currentroller = opponent
                                    notcurrentroller = challenger
                                currentroll = nextroll
                            except asyncio.exceptions.TimeoutError:
                                await nextrollmsg.clear_reactions()
                                areDuelling = 0
                                await channel.send(f"**{notcurrentroller.display_name}** has timed out the duel. **{currentroller.display_name}** wins {bet} gold!")
                                duel = {
                                    "Date" : today,
                                    "Bet" : betfinalint,
                                    "Challenger" : challengername,
                                    "Challenger ID" : challengerid,
                                    "Opponent" : opponentname,
                                    "Opponent ID" : opponentid,
                                    "Number of rounds" : rounds,
                                    "Winner" : currentroller.display_name,
                                    "Winner ID" : currentroller.id,
                                    "Loser" : notcurrentroller.display_name,
                                    "Loser ID" : notcurrentroller.id,
                                }
                                rolls.insert_one(duel)
                                await channel.send(lang.ROLL_DUEL_OVER)
                                channel = self.bot.get_channel(951482552684777482)
                                await channel.send(f"**{currentroller.display_name}** won a duel against **{notcurrentroller.display_name}** for **{bet}** gold!")
                        
                    #invoking dodo singleroll with the needed number
            except asyncio.exceptions.TimeoutError:
                await challengemsg.clear_reactions()
                await channel.send (lang.ROLL_TIMEOUT_CANCEL)
    
    @commands.command(
        name="fact",
        description="Get a random fact."
    )
    @checks.not_blacklisted()
    async def randomfact(self, context: Context):
        """
        Get a random fact.
        :param context: The context in which the command has been executed.
        """
        # This will prevent your bot from stopping everything when doing a web request - see: https://discordpy.readthedocs.io/en/stable/faq.html#how-do-i-make-a-web-request
        
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if channel.id != context.message.channel.id:
            await context.send ("Hey hey, I will reply in the dedicated channel :heart: " + "check <#" + str(config_py.PET_CHANNEL) + ">")
        
        async with aiohttp.ClientSession() as session:
            async with session.get("https://uselessfacts.jsph.pl/random.json?language=en") as request:
                if request.status == 200:
                    data = await request.json()
                    embed = disnake.Embed(
                        description=data["text"],
                        color=0xD75BF4
                    )
                else:
                    embed = disnake.Embed(
                        title="Error!",
                        description="There is something wrong with the API, please try again later",
                        color=0xE02B2B
                    )
                await context.send(embed=embed)
                
#####################################
#                                   #
#       DODO RACESTATS              #
#                                   #
#####################################
    @commands.command(name="mousestats", description = "Show the top skeevatrons in recent history")
    @checks.not_blacklisted()
    async def mouse_stats(self, context):
        """
        Show statistics of each mouse in the races
        """
        collection = config_py.races
        lowest_number_of_races = 5
        pipeline = [
            {
                "$unwind": "$participants"
            },
            {
                "$match": {
                    "participants.mouse_name": {"$ne": None}  # Exclude documents where mouse_name is missing
                }
            },
            {
                "$group": {
                    "_id": "$participants.mouse_name",
                    "starts": {"$sum": 1},
                    "total_position": {"$sum": "$participants.position"},
                    "best_avg_position": {"$min": "$participants.position"},  # Calculate the best average position
                    "favorite_handler": {"$first": "$participants.user_id"}  # Store the user_id for the best average position
                }
            },
            {
                "$match": {
                    "starts": {"$gte": 5}  # Filter mice with 2 or more starts
                }
            },
            {
                "$project": {
                    "mouse_name": "$_id",
                    "starts": 1,
                    "average_position": {"$divide": ["$total_position", "$starts"]},
                    "favorite_handler": 1  # Include the favorite handler in the output
                }
            },
            {
                "$sort": {"average_position": 1}
            },
            {
                "$limit": 10
            }
        ]
        cursor = collection.aggregate(pipeline)
        mouse_stats = list(cursor)
    
        # Create and send the mouse statistics embed
        mouse_stats_embed = disnake.Embed(
            title="Top 10 Mice!",
            description="Only showing mice who participated in 5 or more races:",
            color=0x00FF00,  # Green color
        )
    
        for index, stats in enumerate(mouse_stats, 1):
            user_id = int(stats['favorite_handler'])
            user = context.guild.get_member(user_id)
            display_name = user.display_name if user else "Unknown"
            mouse_stats_embed.add_field(
                name=f"{index}. {stats['mouse_name']}",
                value=f"Starts: {stats['starts']}, Avg. Position: {stats['average_position']:.2f}, Fav. Handler: {display_name}",
                inline=False,
            )
    
        await context.send(embed=mouse_stats_embed) 


#####################################
#                                   #
#       DODO SWEETROLLS             #
#                                   #
#####################################
    @commands.command(name="sweetrolls", description = "Show how many sweetrolls you or your friends have")
    @checks.not_blacklisted()
    async def sweetrolls(self, context, member: disnake.Member = None):
        if not member:
            member = context.author
        # Get the user's ID
        sweetrolls = config_py.sweetrolls
        user_id = member.id
        
        # Count the number of sweetrolls stolen by the user
        stolen_by_user_count = sweetrolls.count_documents({"thief": user_id})
        golden_count = sweetrolls.count_documents({"thief": user_id, "golden": 1})
        
        # Count the number of sweetrolls stolen from the user
        stolen_from_user_count = sweetrolls.count_documents({"stolen_from": user_id})
        
        # Count the number of sweetrolls gifted by user:
        gifted_by_user = sweetrolls.count_documents({"gifter": user_id})
        
        # Count the number of sweetrolls gifted to user:
        gifted_to_user = sweetrolls.count_documents({"gifted_to": user_id})
        
        # Count the number of rhubarb betrayals that happened to the user
        rhubarb_count = sweetrolls.count_documents({"victim": user_id, "rhubarb": 1})
        
        # Find the user who stole the most sweetrolls
        pipeline = [
            {"$match": {"stolen_from": user_id}},
            {"$group": {"_id": "$thief", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1}
        ]
        arch_nemesis = list(sweetrolls.aggregate(pipeline))
        
        if arch_nemesis:
            arch_nemesis_id = arch_nemesis[0]["_id"]
            arch_nemesis_count = arch_nemesis[0]["count"]
            if arch_nemesis_id:
                arch_nemesis_user = await self.bot.fetch_user(arch_nemesis_id)
            else:
                arch_nemesis_user = None
        else:
            arch_nemesis_count = 0
            arch_nemesis_user = None
        
        # Find the user that gifted them the most sweetrolls
        pipeline_gift = [
            {"$match": {"gifted_to": user_id}},
            {"$group": {"_id": "$gifter", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1}
        ]
        sugar_daddy = list(sweetrolls.aggregate(pipeline_gift))
        
        if sugar_daddy:
            sugar_daddy_id = sugar_daddy[0]["_id"]
            sugar_daddy_count = sugar_daddy[0]["count"]
            if sugar_daddy_id:
                sugar_daddy_user = await self.bot.fetch_user(sugar_daddy_id)
            else:
                sugar_daddy_user = None
        else:
            sugar_daddy_count = 0
            sugar_daddy_user = None
                
        # Send the sweetroll information as a message
        message = f"{member.display_name} stole **{stolen_by_user_count}** sweetrolls including **{golden_count}** golden sweetrolls...\n"
        message += f"People stole **{stolen_from_user_count}** sweetrolls from {member.display_name}. :pleading_face: \n"
        message += f"{member.display_name} has given away **{gifted_by_user}** sweetrolls and received **{gifted_to_user}** as gifts!\n"
        message += f"{member.display_name} has suffered **{rhubarb_count}** rhubarb betrayal(s)!\n"
        
        if arch_nemesis_count > 0:
            message += f"{member.display_name}'s arch-nemesis is **{arch_nemesis_user.display_name}** with **{arch_nemesis_count}** stolen sweetrolls. :smirk:\n"
        else:
            message += f"{member.display_name} don't have an arch-nemesis (yet). \n"
        if sugar_daddy_count > 0:
            message += f"{member.display_name}'s sugar doddy is **{sugar_daddy_user.display_name}** with **{sugar_daddy_count}** sweetrolls gifted. :smirk:\n"
        else:
            message += f"{member.display_name} don't have a sugar doddy (yet). \n"
        
        await context.send(message)
    

    
    
    
def setup(bot):
    bot.add_cog(Fun(bot))


#    @commands.command(
#        name="coinflip",
#        description="Make a coin flip, but give your bet before."
#    )
#    @checks.not_blacklisted()
#    async def coinflip(self, context: Context) -> None:
#        """
#        Make a coin flip, but give your bet before.
#        :param context: The context in which the command has been executed.
#        """
#        buttons = Choice()
#        embed = disnake.Embed(
#            description="What is your bet?",
#            color=0x9C84EF
#        )
#        message = await context.send(embed=embed, view=buttons)
#        await buttons.wait()  # We wait for the user to click a button.
#        result = random.choice(["heads", "tails"])
#        if buttons.choice == result:
#            # User guessed correctly
#            embed = disnake.Embed(
#                description=f"Correct! You guessed `{buttons.choice}` and I flipped the coin to `{result}`.",
#                color=0x9C84EF
#            )
#        else:
#            embed = disnake.Embed(
#                description=f"Woops! You guessed `{buttons.choice}` and I flipped the coin to `{result}`, better luck next time!",
#                color=0xE02B2B
#            )
#        await message.edit(embed=embed, view=None)#

#    @commands.command(
#        name="rps",
#        description="Play the rock paper scissors against the bot."
#    )
#    @checks.not_blacklisted()
#    async def rock_paper_scissors(self, context: Context) -> None:
#        """
#        Play the rock paper scissors game against the bot.
#        :param context: The context in which the command has been executed.
#        """
#        view = RockPaperScissorsView()
#        await context.send("Please make your choice", view=view)



#class Choice(disnake.ui.View):
#    def __init__(self):
#        super().__init__()
#        self.choice = None
#
#    @disnake.ui.button(label="Heads", style=disnake.ButtonStyle.blurple)
#    async def confirm(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
#        self.choice = button.label.lower()
#        self.stop()#
#
#    @disnake.ui.button(label="Tails", style=disnake.ButtonStyle.blurple)
#    async def cancel(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
#        self.choice = button.label.lower()
#        self.stop()
#
#
#class RockPaperScissors(disnake.ui.Select):
#    def __init__(self):
#
#        options = [
#            disnake.SelectOption(
#                label="Scissors", description="You choose scissors.", emoji="🪨"
#            ),
#            disnake.SelectOption(
#                label="Rock", description="You choose rock.", emoji="🧻"
#            ),
#            disnake.SelectOption(
#                label="paper", description="You choose paper.", emoji="✂"
#            ),
#        ]
#
#        super().__init__(
#            placeholder="Choose...",
#            min_values=1,
#            max_values=1,
#            options=options,
#        )
#
#    async def callback(self, interaction: disnake.MessageInteraction):
#        choices = {
#            "rock": 0,
#            "paper": 1,
#            "scissors": 2,
#        }
#        user_choice = self.values[0].lower()
#        user_choice_index = choices[user_choice]

#        bot_choice = random.choice(list(choices.keys()))
#        bot_choice_index = choices[bot_choice]

#        result_embed = disnake.Embed(color=0x9C84EF)
#        result_embed.set_author(name=interaction.author.display_name, icon_url=interaction.author.avatar.url)

#        if user_choice_index == bot_choice_index:
#            result_embed.description = f"**That's a draw!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
#            result_embed.colour = 0xF59E42
#        elif user_choice_index == 0 and bot_choice_index == 2:
#            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
#            result_embed.colour = 0x9C84EF
#        elif user_choice_index == 1 and bot_choice_index == 0:
#            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
#            result_embed.colour = 0x9C84EF
#        elif user_choice_index == 2 and bot_choice_index == 1:
#            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
#            result_embed.colour = 0x9C84EF
#        else:
#            result_embed.description = f"**I won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
#            result_embed.colour = 0xE02B2B
#        await interaction.response.defer()
#        await interaction.edit_original_message(embed=result_embed, content=None, view=None)


#class RockPaperScissorsView(disnake.ui.View):
#    def __init__(self):
#        super().__init__()
#
#        self.add_item(RockPaperScissors())
