
import json
import os
import platform
import random
import sys
import datetime
import pytz
import openai
import requests
from bs4 import BeautifulSoup

import pymongo
from pymongo import MongoClient
from datetime import date
from datetime import datetime, timedelta

import dns
import asyncio

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import tasks, commands
from disnake.ext.commands import Bot
from disnake.ext.commands import Context
from disnake.utils import get

import exceptions

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)
        
if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

"""	
Setup bot intents (events restrictions)
For more information about intents, please go to the following websites:
https://docs.disnake.dev/en/latest/intents.html
https://docs.disnake.dev/en/latest/intents.html#privileged-intents


Default Intents:
intents.bans = True
intents.dm_messages = False
intents.dm_reactions = False
intents.dm_typing = False
intents.emojis = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_typing = False
intents.guilds = True
intents.integrations = True
intents.invites = True
intents.reactions = True
intents.typing = False
intents.voice_states = False
intents.webhooks = False

Privileged Intents (Needs to be enabled on dev page), please use them only if you need them:
intents.members = True
intents.messages = True
intents.presences = True
"""
intents = disnake.Intents.default()
intents.reactions = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = Bot(command_prefix=config["prefix"], intents=intents)
api = config_py.OPENAI_API
tags_dict = {}

ischatting = 0

@bot.event
async def on_ready() -> None:
    """
    The code in this even is executed when the bot is ready
    """
    print(f"Logged in as {bot.user.name}")
    print(f"disnake API version: {disnake.__version__}")
    print(f"Python version: {platform.python_version()}")
    print(f"Running on: {platform.system()} {platform.release()} ({os.name})")
    print("-------------------")
    status_task.start()
    api_import.start()
    check_reactions.start()
    #boss_battle_task.start()
    #set_server_time.start()

#    time_task.start()
    #FILE_NAME = 'memberList'+'.csv'
    #for guild in bot.guilds:
    #    if guild.id == 783594413632520203:
    #        print(
    #            f'{bot.user} is scraping the following server: \n' 
    #            f'{guild.name} (id: {guild.id})'
    #        )     
    #        for member in guild.members:
    #            line = '{},{},{}\n'.format(member.name+"#"+member.discriminator,member.display_name,member.id)
    #            print(line)        
    #        
    #        with open(FILE_NAME, mode='w',encoding='utf8') as f:
    #            f.write('username,nickName,id\n')
    #            for member in guild.members:
    #                line = '{},{},{}\n'.format(member.name+"#"+member.discriminator,member.display_name,member.id)
    #                f.write(line)
'''
@tasks.loop(minutes=5.0)
async def set_server_time() -> None:
    """
    Setup the server time
    """
    channel = bot.get_channel(config_py.TIME_CHANNEL)
    #tz = pytz.timezone('Europe/Berlin')
    #print (tz)
    #currentDateAndTime = datetime.now()
    currentTime = datetime.now(pytz.timezone('Europe/Berlin')).strftime("%H:%M:%S")
    channelName = ("Server Time: " + currentTime)
    print (channelName)
    await channel.edit(name = channelName)
'''
        

@tasks.loop(hours=24)
async def check_reactions():
    """
    Task that runs every 3 minutes to check and add missing reactions to specified messages.
    """
    for message_id, reactions in config_py.reaction_roles.items():
        print(f"Checking message ID {message_id} for missing reactions.")
        message = None
        for guild in bot.guilds:
            if message:
                break  # Exit the loop once the message is found
            for channel in guild.text_channels:
                try:
                    message = await channel.fetch_message(message_id)
                    if message:
                        print(f"Found message ID {message_id} in channel {channel.name} of guild {guild.name}.")
                        break  # Exit the loop once the message is found
                except disnake.NotFound:
                    continue  # Move to the next channel if the message isn't found
                except disnake.Forbidden:
                    print(f"No permission to read messages in channel {channel.name}")
                except disnake.HTTPException as e:
                    print(f"Failed to fetch message from channel {channel.name}: {e}")
        
        if message:
            for emoji in reactions.keys():
                bot_reacted = False
                for reaction in message.reactions:
                    if str(reaction.emoji) == emoji:
                        users = [user async for user in reaction.users()]
                        if bot.user in users:
                            bot_reacted = True
                            break

                if not bot_reacted:
                    print(f"Attempting to add reaction {emoji} to message ID {message_id}.")
                    try:
                        await message.add_reaction(emoji)
                        print(f"Successfully added reaction {emoji} to message ID {message_id}.")
                    except disnake.HTTPException as e:
                        print(f"Failed to add reaction {emoji} to message ID {message_id}: {e}")
                else:
                    continue
                    #print(f"Bot has already reacted with {emoji} on message ID {message_id}.")
        else:
            print(f"Message with ID {message_id} not found in any channel.")


#@tasks.loop(hours=3)
#async def boss_battle_task():
#    """
#    Every 3 hours, roll a dice and if the value is above 950, spawn a boss battle.
#    """
#    roll = random.randint(0, 1000)
#    print(f"Boss battle roll: {roll}")  # Debug log
#    if roll > 950:
#        print("Spawning boss battle...")  # Debug log
#        channel_id = random.choice(config_py.boss_spawn_channels)
#        channel = bot.get_channel(channel_id)
#        if channel:
#            await spawn_boss(channel)

#async def spawn_boss(channel):
#    """
#    Spawn a boss battle in the specified channel.
#    """
#    # Generate a description of a horribly fun monster
#    openai.api_key = config_py.PROXY_API
#    openai.api_base = "https://api.proxyapi.ru/openai/v1"
#    
#    description_response = openai.ChatCompletion.create(
#        model="gpt-3.5-turbo-0125",
#        temperature=1.3,
#        messages=[{"role": "system", "content": "You are a Dodo, helpful, naive and kind bird that wishes well sometimes ends up being clumsy and saying some kind but stupid stuff. Your main home is the ESO for Dodos Discord server that is dedicated to helping new players get into ESO end-game. You speak in a concise and clear but friendly language"},
#                  {"role": "user", "content": "Generate a very short, concise and picturesque description of a monster and its superpowers that would be both scary and horrible, and funny at the same time. Add a short description of what the monster is doing right now"}]
#    )
#    
#    monster_description = description_response.choices[0].message.content
#    
#    name_response = openai.ChatCompletion.create(
#        model="gpt-3.5-turbo-0125",
#        temperature=1,
##        messages=[{"role": "system", "content": ""},
 #                 {"role": "user", "content": f"Generate a name for this boss: {monster_description}. Reply with the name only without any additional words"}]
 #   )
 #   
 #   boss_name = name_response.choices[0].message.content.strip()
 ##   
    # Generate a picture of the monster
#    image_response = openai.Image.create(
#        model="dall-e-3",
#        prompt=monster_description,
#        n=1,
#        size="1024x1024"
#    )
#    
#    image_url = image_response.data[0].url
#    
#    # Define the reactions and their required counts
#    reactions = {
#        "⚔️": {"count": random.randint(1, 5), "description": "Attack the monster"},
#        "🤝": {"count": random.randint(1, 5), "description": "Try to befriend the horror"},
#        "🏃": {"count": random.randint(1, 5), "description": "Attempt to run away in PANIC!"},
#        "💣": {"count": random.randint(1, 5), "description": "Set a trap for the beast!"}
#    }
#    
#    # Create the embed
#    embed = disnake.Embed(
#        title=f"A Wild Boss Appears! Beware the {boss_name}",
#        description=f"{monster_description}\n\nReact with the following to defeat the boss:\n" + 
#                    "\n".join([f"{emoji} {data['count']} - {data['description']}" for emoji, data in reactions.items()]),
#        color=0xFF0000
#    )
#    embed.set_image(url=image_url)
#    
#    # Send the embed
#    boss_message = await channel.send(embed=embed)
#    
#    # Add reactions to the embed message
#    for emoji in reactions.keys():
#        await boss_message.add_reaction(emoji)
#    
#    # Wait for 2 minutes
#    await asyncio.sleep(120)
#    
#    # Check the reactions
#    boss_message = await channel.fetch_message(boss_message.id)
#    reaction_counts = {reaction.emoji: reaction.count - 1 for reaction in boss_message.reactions}
#    
#    defeated = all(reaction_counts.get(emoji, 0) >= data['count'] for emoji, data in reactions.items())
#    
#    if defeated:
#        total_reactions = sum(reaction_counts.values())
#        await channel.send("That was a hard-fought battle!! :dodo: Everyone who participated receives a sweetroll shower!!")
#        
#        participants = set()
#        for reaction in boss_message.reactions:
#            if reaction.emoji in reactions:
#                users = [user async for user in reaction.users() if not user.bot]
#                participants.update(users)
#        
#        sweetroll_entries = []
#        for user in participants:
#            for _ in range(total_reactions):
#                sweetroll = {
#                    "thief": user.id,
#                    "gifter": boss_name,
#                    "date": datetime.now()
#                }
#                sweetroll_entries.append(sweetroll)
#            await channel.send(f"{user.mention} received {total_reactions} sweetrolls!")
#        
#        if sweetroll_entries:
#            config_py.sweetrolls.insert_many(sweetroll_entries)
#    else:
#        await channel.send("The boss prevailed! Better luck next time.")
    

@tasks.loop(minutes=3.0)
async def status_task() -> None:
    """
    Setup the game status task of the bot
    """
    statuses = config_py.statuses
    await bot.change_presence(activity=disnake.Game(random.choice(statuses)))
    
@tasks.loop(minutes=60.0)
async def api_import() -> None:
    """
    Setup the game status task of the bot
    """
    global tags_dict
    tags_dict = await get_tags_from_wordpress_api()
    print ("API updated successfully")

# Removes the default help command of discord.py to be able to create our custom help command.
bot.remove_command("help")

def load_commands(command_type: str) -> None:
    for file in os.listdir(f"./cogs/{command_type}"):
        if file.endswith(".py"):
            extension = file[:-3]
            try:
                bot.load_extension(f"cogs.{command_type}.{extension}")
                print(f"Loaded extension '{extension}'")
            except Exception as e:
                exception = f"{type(e).__name__}: {e}"
                print(f"Failed to load extension {extension}\n{exception}")


if __name__ == "__main__":
    """
    This will automatically load slash commands and normal commands located in their respective folder.
    
    If you want to remove slash commands, which is not recommended due to the Message Intent being a privileged intent, you can remove the loading of slash commands below.
    """
    load_commands("slash")
    load_commands("normal")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(config_py.WAYSHRINE)
    if not channel:
        return

    starter_roles = [member.guild.get_role(role_id) for role_id in config_py.starter_roles]
    valid_starter_roles = [r for r in starter_roles if r is not None]
    await member.add_roles(*valid_starter_roles, reason="Adding starter roles")

    # Are they are returning player?
    document = config_py.left_roles.find_one({'_id': member.id})

    if document and 'roles' in document:
        roles_to_assign = [member.guild.get_role(role_id) for role_id in document['roles']]
        valid_roles_to_assign = [r for r in roles_to_assign if r is not None]
        
        if valid_roles_to_assign:
            await member.add_roles(*valid_roles_to_assign, reason="Reassigning roles from previous membership")

        await channel.send(
            f"Welcome back, {member.mention}! I have saved your roles from the last visit and "
            f"reassigned them to you, if anything has changed, make sure to update your roles in "
            f"<#{config_py.RANK_REQ}> and select the trials you wanna be notified about in "
            f"<#{config_py.SELECT_ROLES}>. Ping any of the admins if you have any questions, and happy raiding! :hearts:"
        )
        
        config_py.left_roles.delete_one({'_id': member.id})
        
    else:
        await channel.send(
            f"Welcome, {member.mention}! If you want to raid with us, post your clearsies in "
            f"<#{config_py.RANK_REQ}> and choose the trials you would like to join in "
            f"<#{config_py.SELECT_ROLES}>. Ping any of the admins if you have any questions, and happy raiding! :hearts:"
        )
        
@bot.event
async def on_member_remove(member):
    # Collect all role IDs that are listed in reaction_roles
    excluded_role_ids = set()
    for role_mapping in config_py.reaction_roles.values():
        excluded_role_ids.update(role_mapping.values())

    # Save roles excluding @everyone role and those listed in reaction_roles
    roles = [role.id for role in member.roles if role.id != member.guild.default_role.id and role.id not in excluded_role_ids]
    
    # Use update_one with upsert=True to create or update the document
    config_py.left_roles.update_one(
        {'_id': member.id},
        {'$set': {'roles': roles}},
        upsert=True
    )

@bot.event
async def on_reaction_add(reaction, user):
    # Check if the reaction is from the bot and the emoji is the eyes emoji
    if user.bot or str(reaction.emoji) != u"\U0001F4D6":
        return

    # Check if the author of the message is in the same guild (server) as the bot
    if reaction.message.guild is None:
        return

    # Check if the author of the message pressed the eyes emoji
    message = reaction.message
    if user == message.author:
        # Create a command context for the guide command
        ctx = await bot.get_context(message)

        # Extract the tags from the message content
        content = message.content.lower()
        tags = [tag for tag in tag_dict.keys() if tag.lower() in content]
        if len(tags) == 0:
            await message.clear_reactions()
            return
        else:
            # Create an embed to collect the results
            embed = disnake.Embed(
                title="📚 Potentially helpful resources found!",
                color=disnake.Color.brand_green()
            )
            
            for tag in tags:
                try:
                    links = await ctx.invoke(bot.get_command("guide"), tag=tag)
            
                    if links:
                        result_text = "\n".join([f"📖 [{title}]({url})" for title, url in links])
                        
                        embed.add_field(
                            name=f"✨ {tag.capitalize()}", 
                            value=result_text, 
                            inline=False
                        )
            
                except Exception as e:
                    print(f"Error calling guide command for tag '{tag}': {e}")
            
            # set_footer anchors this text at the absolute bottom of the embed
            embed.set_footer(text="Hey there! We have some articles on our website on the stuff that was mentioned in the last message, maybe some of it is useful! 💖")
    
            # Send the combined results as a single embed
            await message.channel.send(embed=embed)

@bot.event
async def on_message(message: disnake.Message) -> None:
    """
    The code in this event is executed every time someone sends a message, with or without the prefix
    :param message: The message that was sent.
    """
    global tag_dict
    messages = config_py.messages
    source_channel_id = 1109080900030955604  # ID of 
    mod_channel_id = 1113035754923368478  # ID of the mod channel
    if message.channel.id == source_channel_id:
        if message.author.id != 824171812518494238:
            source_channel = bot.get_channel(source_channel_id)
            mod_channel = bot.get_channel(mod_channel_id)
            content = message.content
            author = message.author.mention
            await mod_channel.send(f"**NEW ATG SIGN-UP from {source_channel.name}**\nAuthor: {author}\nContent: {content}")
            await bot.process_commands(message)
        else:
            return
    await check_for_harmful_messages(message)

    msg = (f"{message.content}")
    msgobj = {
        "tag": "",  # You can modify this to store a specific tag if needed
        "message": msg,
        "intent": "",  # You can set intent based on additional logic later if needed
        "author": message.author.id,
        "channel": message.channel.id  # Save the channel ID where the message was sent
    }
    
    messages.insert_one(msgobj)
    msg = (f"{message.content}")
    
    if ('no u' in msg.lower() or 'no you' in msg.lower()):
        print ("we detected a no u")
        channel = bot.get_channel(message.channel.id)
        nouanswers = ['no u', 'no you', 'No, you', 'No You!', 'NO YOU!', 'NO YOUUU!!', "No, Tomtem!", 'no, Ducky.', "no, this time it's definitely you", 'nope, you all the way'
            ]
        tauntedanswers = ['Ah sh*t, here we go again.', "Don't make me angy. You wouldn't like me when I'm angy", "...", "it's time to stop", "http://dodos.fun/wp-content/uploads/2021/05/angy.jpg", "a trolling is happening"
            ]
        nouseed = random.randint(0, 10)
        if nouseed < 5:
            await channel.send(f"{tauntedanswers[random.randint(0, len(tauntedanswers)-1)]}")
        else:
            await channel.send(f"{nouanswers[random.randint(0, len(nouanswers)-1)]}")
    
    elif("schedule" in msg.lower() or "trials" in msg.lower() or "chappelles-tyrone-tyrone-biggums-gif" in msg.lower() or "raids" in msg.lower() or "happening" in msg.lower()) and not message.author.bot:
       for reaction in config_py.addons:
            await message.add_reaction(reaction)
       def check (reaction, user):
           return str(reaction) in config_py.addons and user.id == message.author.id
       try:
           reaction, user = await bot.wait_for("reaction_add", timeout = 15, check = check)
           userChoiceEmote = reaction.emoji
           userChoiceIndex = config_py.addons[userChoiceEmote]
           if userChoiceIndex == 0:
               context = await bot.get_context(message)
               schedule = bot.get_command("schedule123")
               await context.invoke(schedule)
               await message.clear_reactions()
       except asyncio.exceptions.TimeoutError:
            await message.clear_reactions()
    
    elif("support cat" in msg.lower() or "goodnight cat" in msg.lower() or "good night cat" in msg.lower()):
        context = await bot.get_context(message)
        cat = bot.get_command("cat")
        await context.invoke(cat)

    if message.author.id in config_py.DODOLOVE:
        heart_reactions = ["❤️", "💖", "💕", "💞", "💘", "❣️"]
        await message.add_reaction(random.choice(heart_reactions))

    print(f"{message.guild.name}: {message.channel}: {message.author}: {message.author.name}: {message.content}")
    dodo_id = bot.user.id
    if dodo_id in (user.id for user in message.mentions) and message.author.id != dodo_id:
        ctx = await bot.get_context(message)
        command_name = "chat"
        if message.reference:
            replied_message = await message.channel.fetch_message(message.reference.message_id)
            context_message = replied_message.content
            context_author = replied_message.author.display_name
            command_message = message.content
            await ctx.invoke(bot.get_command(command_name), message = f"{context_author} previously said: {context_message}. Then {message.author} said: {command_message}")
            print (message)
        else:
            command_message = message.content
            await ctx.invoke(bot.get_command(command_name), message = command_message)
    await check_sweetroll_chance(message)
    await bot.process_commands(message)
    await check_tags(message)
    


@bot.event
async def on_message_delete(message):
    #msg = str(message.author)+ ' deleted a message in #'+str(message.channel)+ ": '**" +str(message.content) +"**'"
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    embed = disnake.Embed(
        title = f"{message.author.display_name} just deleted a message in #{str(message.channel)}",
        description = "**" +str(message.content) +"**",
        color = config_py.error)
    embed.set_author(name=f"A message was deleted", icon_url=message.author.display_avatar)
    await channel.send(embed = embed)

@bot.event
async def on_slash_command(interaction: ApplicationCommandInteraction) -> None:
    """
    The code in this event is executed every time a slash command has been *successfully* executed
    :param interaction: The slash command that has been executed.
    """
    print(
        f"Executed {interaction.data.name} command in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.author} (ID: {interaction.author.id})")


@bot.event
async def on_slash_command_error(interaction: ApplicationCommandInteraction, error: Exception) -> None:
    """
    The code in this event is executed every time a valid slash command catches an error
    :param interaction: The slash command that failed executing.
    :param error: The error that has been faced.
    """
    if isinstance(error, exceptions.UserBlacklisted):
        """
        The code here will only execute if the error is an instance of 'UserBlacklisted', which can occur when using
        the @checks.is_owner() check in your command, or you can raise the error by yourself.
        
        'hidden=True' will make so that only the user who execute the command can see the message
        """
        embed = disnake.Embed(
            title="Error!",
            description="You are blacklisted from using the bot.",
            color=0xE02B2B
        )
        print("A blacklisted user tried to execute a command.")
        return await interaction.send(embed=embed, ephemeral=True)
    elif isinstance(error, commands.errors.MissingPermissions):
        embed = disnake.Embed(
            title="Error!",
            description="You are missing the permission(s) `" + ", ".join(
                error.missing_permissions) + "` to execute this command!",
            color=0xE02B2B
        )
        print("A blacklisted user tried to execute a command.")
        return await interaction.send(embed=embed, ephemeral=True)
    raise error


@bot.event
async def on_command_completion(context: Context) -> None:
    """
    The code in this event is executed every time a normal command has been *successfully* executed
    :param context: The context of the command that has been executed.
    """
    commands = config_py.commands_use
    full_command_name = context.command.qualified_name
    split = full_command_name.split(" ")
    executed_command = str(split[0])
    today = date.today().isoformat()
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    command = {
        "Command" : executed_command,
        "Guild" : context.guild.name,
        "Name" : context.message.author.display_name,
        "User ID" : context.message.author.id,
        "Date" : today
        
    }
    commands.insert_one(command)
    await channel.send(f"Executed {executed_command} command in {context.guild.name} (ID: {context.message.guild.id}) by {context.message.author} (ID: {context.message.author.id})")
    print(
        f"Executed {executed_command} command in {context.guild.name} (ID: {context.message.guild.id}) by {context.message.author} (ID: {context.message.author.id})")


@bot.event
async def on_command_error(context: Context, error) -> None:
    """
    The code in this event is executed every time a normal valid command catches an error
    :param context: The normal command that failed executing.
    :param error: The error that has been faced.
    """
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        embed = disnake.Embed(
            title="Hey, please slow down!",
            description=f"You can use this command again in {f'{round(hours)} hours' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} seconds' if round(seconds) > 0 else ''}.",
            color=0xE02B2B
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = disnake.Embed(
            title="Error!",
            description="You are missing the permission(s) `" + ", ".join(
                error.missing_permissions) + "` to execute this command!",
            color=0xE02B2B
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = disnake.Embed(
            title="Error!",
            description=str(error).capitalize(),
            # We need to capitalize because the command arguments have no capital letter in the code.
            color=0xE02B2B
        )
        await context.send(embed=embed)
    raise error

@bot.event
async def on_raw_reaction_add(payload):
    message_id = payload.message_id
    if message_id in config_py.reaction_roles:
        reaction_role_map = config_py.reaction_roles[message_id]
        if str(payload.emoji) in reaction_role_map:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(message_id)
            member = payload.member
            role_id = reaction_role_map[str(payload.emoji)]
            if member:
                await add_role_to_user(member, role_id, message)

@bot.event
async def on_raw_reaction_remove(payload):
    message_id = payload.message_id
    if message_id in config_py.reaction_roles:
        reaction_role_map = config_py.reaction_roles[message_id]
        if str(payload.emoji) in reaction_role_map:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(message_id)
            guild = message.guild
            member = guild.get_member(payload.user_id)
            role_id = reaction_role_map[str(payload.emoji)]
            if member:
                await remove_role_from_user(member, role_id, message)


async def get_tags_from_wordpress_api():
    global tag_dict
    api_url = "https://dodo.nextstep.team/wp-json/wp/v2/tags"
    tag_dict = {}
    page = 1
    
    while True:
        try:
            response = requests.get(api_url, params={"page": page})
            if response.status_code == 200:
                tags = response.json()
                if not tags:  # No more tags on this page
                    break
                for tag in tags:
                    tag_dict[tag["name"]] = tag["link"]
                page += 1  # Move to the next page
            else:
                print(f"Failed to fetch tags for page {page}. Status code: {response.status_code}")
                break  # Exit the loop on error
        except Exception as e:
            #print(f"Error: {e}")
            break  # Exit the loop on error
    
    #print(tag_dict)
    return tag_dict


async def check_for_harmful_messages(message: disnake.Message):
    if any(allowed_link in message.content for allowed_link in config_py.allowed_links):
        return
    if any(restricted_string in message.content.lower() for restricted_string in config_py.restricted_strings):
        member_roles = [role.id for role in message.author.roles]
        if not any(role in member_roles for role in config_py.allowed_roles):
            log_channel = bot.get_channel(config_py.E4D_LOG)
            embed = disnake.Embed(title="Oi!!", description=f"**User:** {message.author}\n**Content:** {message.content}", color=disnake.Color.red())
            if "@everyone" in message.content and "discord.gg" in message.content.lower():
                user_embed = disnake.Embed(
                    title="You have been banned!",
                    description=f"You have been banned from {message.guild.name} for unauthorized activities.",
                    color=disnake.Color.dark_red()
                )
                user_embed.set_thumbnail(url=message.guild.icon.url if message.guild.icon else None)
                user_embed.add_field(name="Reason", value="Unauthorized invite link with @everyone mention", inline=False)
                user_embed.set_footer(text="Contact the server admin for more information.")
                try:
                    await message.author.send(embed=user_embed)
                except disnake.errors.HTTPException:
                    print("Failed to send DM to user.")
                embed.title = "Immediate Ban for Unauthorized Mention and Link"
                embed.description = f"**User:** {message.author}\n**Content:** {message.content}\n**Action:** User has been banned for including an unauthorized invite link along with '@everyone'."
                embed.color = disnake.Color.dark_red()
                await log_channel.send(embed=embed)
                await message.guild.ban(message.author, reason="Unauthorized invite link with @everyone mention")
                await message.delete()
                return
            else:
                embed.title = "Deleted Message with Restricted Content"
                embed.description = f"**User:** {message.author}\n**Content:** {message.content}\n**Action:** Message deleted due to restricted content."
                embed.color = disnake.Color.orange()
                await log_channel.send(embed=embed)
                await message.delete()
                warning_message = "Oi! Something doesn't look right in this chat! I will delete the message. :hearts: Please poke any of the admins if you think I'm being crazy."
                await message.channel.send(warning_message)
                return                
                return

async def remove_role_later(member: disnake.Member, role: disnake.Role):
    """
    Waits 1 hour, then removes the specified role from the member if they still have it.
    This is not persistent; if the bot restarts, the timer is lost.
    """
    await asyncio.sleep(3600)  # 1 hour
    try:
        if role in member.roles:
            await member.remove_roles(role)
    except disnake.HTTPException:
        pass  # Member might have left, or permissions changed


async def run_pumpkin_game(channel: disnake.TextChannel, original_message: disnake.Message, discoverer: disnake.User, bot, config_py):
    """
    Starts and manages the pumpkin pull minigame.
    """
    pumpkins = config_py.pumpkins
    pull_collection = config_py.pull  # NEW: Added pull collection
    weight = random.randint(5, 800)  # Pumpkin weight in kgs
    explosion_time = datetime.now() + timedelta(minutes=weight/8)
    
    # NEW: Get discoverer's base strength
    discoverer_data = pull_collection.find_one({"_id": discoverer.id})
    base_strength = discoverer_data.get("strength", 50) if discoverer_data else 50

    # pullers stores {user_id: pull_strength}
    pullers = {discoverer.id: base_strength}
    total_strength = base_strength
    
    PUMPKIN_ROLE_ID = 1430471888412475413
    GAME_EMOJI = u"\U0001F383"  # Pumpkin
    guild = original_message.guild
    
    if not guild:
        return # Cannot run game without a guild

    # 1. Create the initial game embed
    embed = disnake.Embed(
        title="🎃 A GIANT PUMPKIN APPEARS! 🎃",
        description=(
            f"A massive pumpkin just burst from the ground! It looks unstable...\n"
            f"React with 🎃 to help pull it out before it explodes!"
        ),
        color=disnake.Color.orange(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Discovered by", value=discoverer.mention, inline=False)
    embed.add_field(name="🎃 Weight", value=f"**{weight} kg**", inline=True)
    embed.add_field(name="Total Strength", value=f"**{total_strength} kg**", inline=True)
    embed.add_field(name="💥 Explodes in", value=f"<t:{int(explosion_time.timestamp())}:R>", inline=True)
    embed.add_field(name="Pullers", value=f"{discoverer.mention}: {pullers[discoverer.id]}kg", inline=False)
    embed.set_footer(text="React to pull! Your strength is saved from previous pulls and will increase for next time!")

    game_message = await original_message.channel.send(embed=embed)
    await game_message.add_reaction(GAME_EMOJI)

    # NEW: Remove reaction from the original "trigger" message
    # to guide users to the new embed.
    try:
        await original_message.remove_reaction(GAME_EMOJI, bot.user)
    except disnake.HTTPException:
        pass  # Already removed, or no permissions, etc.

    # 2. Main Game Loop
    while datetime.now() < explosion_time:
        remaining_time = (explosion_time - datetime.now()).total_seconds()
        if remaining_time <= 0:
            break # Safety break, though timeout should handle this
        
        try:
            reaction, user = await bot.wait_for(
                "reaction_add",
                timeout=remaining_time,
                check=lambda r, u: str(r.emoji) == GAME_EMOJI and u.id != bot.user and r.message.id == game_message.id
            )

            # Update strength - ONLY if user is new
            if user.id not in pullers:
                # NEW: Get new puller's base strength
                user_data = pull_collection.find_one({"_id": user.id})
                base_strength = user_data.get("strength", 50) if user_data else 50
                pullers[user.id] = base_strength  # Add new puller with their saved strength
            
                total_strength = sum(pullers.values())

                # Update embed with new puller list
                puller_list_str = "\n".join([f"<@{uid}>: {strength}kg" for uid, strength in pullers.items()])
                embed.set_field_at(2, name="Total Strength", value=f"**{total_strength} kg**", inline=True)
                embed.set_field_at(4, name=f"Pullers ({len(pullers)})", value=puller_list_str, inline=False)

                await game_message.edit(embed=embed)
            
            # 3. WIN CONDITION
            if total_strength >= weight:
                reward_per_person = round(weight / len(pullers))
                
                win_embed = disnake.Embed(
                    title="🎃 SUCCESS! 🎃",
                    description=f"You did it! The **{weight}kg** pumpkin was pulled from the ground!",
                    color=disnake.Color.green()
                )
                win_embed.add_field(name="Total Pullers", value=str(len(pullers)), inline=True)
                win_embed.add_field(name="Reward Each", value=f"**{reward_per_person} kg** of pumpkin!", inline=True)
                win_embed.set_footer(text="Your pumpkin stats and pull strength (+5kg!) have been updated.")
                
                await game_message.edit(embed=win_embed)
                await game_message.clear_reactions()

                # Add stats and check roles for each winner
                for user_id, current_strength in pullers.items():
                    # NEW: Save updated pull strength (+5kg for next time)
                    new_strength = current_strength + 5
                    pull_collection.update_one(
                        {"_id": user_id},
                        {"$set": {"strength": new_strength, "last_pull": datetime.now()}},
                        upsert=True
                    )
                    
                    # Original pumpkin stat logic
                    pumpkins.insert_one({"collector": user_id, "date": datetime.now(), "weight_collected": reward_per_person})
                    pumpkin_count = pumpkins.count_documents({"collector": user_id})

                    if pumpkin_count >= 50:
                        try:
                            role = guild.get_role(PUMPKIN_ROLE_ID)
                            member = await guild.fetch_member(user_id)
                            if role and member and role not in member.roles:
                                await member.add_roles(role)
                                await channel.send(
                                    f"**Wow!** <@{user_id}> has collected 50 pumpkins and earned the **{role.name}** role!"
                                )
                        except disnake.Forbidden:
                            await channel.send(f"I tried to give <@{user_id}> the pumpkin role, but I don't have permissions!")
                        except Exception as e:
                            print(f"Error adding pumpkin role: {e}")
                
                # await original_message.remove_reaction(GAME_EMOJI, bot.user) # REMOVED: Moved to start of function
                return # End game

        except asyncio.TimeoutError:
            # This triggers when remaining_time runs out
            break # Exit loop to handle explosion
    
    # 4. EXPLOSION (if loop finishes without win)
    if total_strength < weight:
        explode_embed = disnake.Embed(
            title="💥 BOOOOOOM! 💥",
            description=(
                f"Oh no! The **{weight}kg** pumpkin was too strong!\n"
                f"It exploded, covering everyone in pumpkin guts!"
            ),
            color=disnake.Color.red()
        )
        puller_list_str = "\n".join([f"<@{uid}>" for uid in pullers.keys()])
        explode_embed.add_field(name="Covered in Guts", value=puller_list_str or "Nobody...", inline=False)
        explode_embed.set_footer(text="You've... earned a temporary role. Your strength (+5kg!) has been saved.")

        await game_message.edit(embed=explode_embed) # Changed from `embed` to `explode_embed`
        await game_message.clear_reactions()

        # NEW: Save pull strength even on a loss
        for user_id, current_strength in pullers.items():
            new_strength = current_strength + 5 # Increase strength for next time
            pull_collection.update_one(
                {"_id": user_id},
                {"$set": {"strength": new_strength, "last_pull": datetime.now()}},
                upsert=True
            )

        role_to_give = guild.get_role(PUMPKIN_ROLE_ID)
        if role_to_give:
            for user_id in pullers.keys():
                try:
                    member = await guild.fetch_member(user_id)
                    if role_to_give not in member.roles:
                        await member.add_roles(role_to_give)
                        # Schedule role removal
                        bot.loop.create_task(remove_role_later(member, role_to_give))
                except disnake.Forbidden:
                    await channel.send(f"I tried to give <@{user_id}> the sticky pumpkin role, but I don't have permissions!")
                except Exception as e:
                    print(f"Error adding temporary pumpkin role: {e}")

    # await original_message.remove_reaction(GAME_EMOJI, bot.user) # REMOVED: Moved to start of function


async def _run_sweetroll_event(message: disnake.Message, sweetrolls, pumpkins, channel, spawn_emoji, is_rhubarb, is_pumpkin):
    """
    Internal function to run the actual event logic as a non-blocking task.
    This contains the blocking 'await bot.wait_for' calls.
    """
    
    # These must be globally available or passed in
    # bot, config_py
    
    try:
        await message.add_reaction(spawn_emoji)

        def check(reaction, user):
            return user != bot.user and str(reaction.emoji) == spawn_emoji

        try:
            reaction, user = await bot.wait_for(
                "reaction_add",
                timeout=config_py.SWEETROLL_COOLDOWN,
                check=check,
            )

            # ――――――――――――――――――――――――――――――――――――――――
            # BRANCH 1: RHUBARB BETRAYAL (Unchanged)
            # ――――――――――――――――――――――――――――――――――――――――
            if is_rhubarb:
                rhubarb_messages = [
                    "The sweetroll cackled, morphed into rhubarb, and your taste-buds filed a complaint!",
                    "SURPRISE! The sweetroll was a rhubarb double agent—enjoy the sour rebellion!",
                    "A puff of pink smoke—now it's rhubarb! Your mouth instantly puckers like a prune.",
                    "The pastry peeled off its frosting disguise and hissed, “Rhubarb time!”",
                    "In a flash, icing turned to stalks—your courage wilted faster than lettuce.",
                    "You bite down expecting fluff, but get tart betrayal straight to the soul.",
                    "The confection shouted “PLOT TWIST!” and became rhubarb, mocking your hunger.",
                    "Sour chaos erupts as the roll transmutes, leaving you chewing regrets.",
                    "It looked innocent, but the rhubarb ambush left you questioning culinary physics.",
                    "Sweet? Never heard of her—welcome to the Rhubarb Revolution.",
                    "A gleeful squeal—“Fooled ya!”—echoed as the roll turned fibrous and tangy.",
                    "Your face contorts; the rhubarb coup is complete.",
                    "Frosting evaporates, stalks sprout—this is **not** the pastry you were looking for.",
                    "Rhubarb sorcery engages! Your dreams crumble into tart reality.",
                    "You taste betrayal seasoned with sourness—chef’s kiss of misfortune.",
                ]
                await channel.send(
                    f"{user.mention} picked up the sweetroll, but it **BETRAYED** them! "
                    f"{random.choice(rhubarb_messages)}"
                )
                sweetrolls.insert_one(
                    {"victim": user.id, "date": datetime.now(), "rhubarb": 1}
                )
                await message.remove_reaction(spawn_emoji, bot.user)
                return

            # ――――――――――――――――――――――――――――――――――――――――
            # BRANCH 2: PUMPKIN MINIGAME (NEW)
            # ――――――――――――――――――――――――――――――――――――――――
            elif is_pumpkin:
                # The user who clicked the reaction is the 'discoverer'
                # This function will now take over and run the game.
                # We await it so this 'check' function is busy until the game ends.
                await run_pumpkin_game(channel, message, user, bot, config_py)
                # The reaction is removed either by the game
                # or by the TimeoutError exception below.

            # ――――――――――――――――――――――――――――――――――――――――
            # BRANCH 3: NORMAL SWEETROLL (Unchanged, just in an 'else')
            # ――――――――――――――――――――――――――――――――――――――――
            else:
                if user and user.id == message.author.id:
                    await channel.send(
                        "A sweetroll fell out but the owner picked it up before anyone else could! Great job! :cupcake:"
                    )
                    await message.remove_reaction(spawn_emoji, bot.user)

                elif user and user.id != message.author.id:
                    # Amulet protection check
                    if message.author.id in config_py.SWEETROLLAMULET:
                        magic_roll = random.randint(1, 100)
                        if magic_roll <= 98:
                            protective_messages = [
                                "The amulet shimmered, and the sweetroll was protected!",
                                "A burst of light from the amulet scared off the thief!",
                                "The sweetroll glowed briefly and remained safe!",
                                "An invisible shield protected the sweetroll!",
                                "The thief's hands were repelled by a magical force!",
                                "A sudden gust of wind blew the thief away from the sweetroll!",
                                "The amulet hummed, and the sweetroll stayed put!",
                                "A faint voice said 'Not today!' and the sweetroll was untouched!",
                                "The amulet sparkled, warding off the theft attempt!",
                                "A soft glow surrounded the sweetroll, keeping it safe!",
                            ]
                            await channel.send(random.choice(protective_messages))
                            await message.remove_reaction(spawn_emoji, bot.user) # Need to remove reaction here too
                            return
                        else:
                            golden_messages = [
                                "The amulet's magic faltered, and the sweetroll was stolen! It was imbued with the magic of the amulet!",
                                "The thief's skill overcame the magic, stealing the sweetroll! Why does it shimmer?",
                                "The amulet's resonance wasn't enough! A sweetroll was stolen!",
                                "The amulet's power was tested and failed, losing the golden sweetroll!",
                                "A rare magical surge allowed the golden sweetroll to be stolen!",
                                "Despite its protection, the golden sweetroll was snatched!",
                                "The thief overcame the amulet's magic, claiming the golden sweetroll!",
                                "A strange magic broke through the amulet's defenses, stealing the sweetroll!",
                                "Even the amulet couldn't prevent the theft of the golden sweetroll!",
                                "A flicker of light, the golden sweetroll was stolen!",
                            ]
                            sweetrolls.insert_one(
                                {
                                    "stolen_from": message.author.id,
                                    "thief": user.id,
                                    "date": datetime.now(),
                                    "golden": 1,
                                }
                            )
                            golden_count = sweetrolls.count_documents(
                                {"thief": user.id, "golden": 1}
                            )
                            await channel.send(
                                f"{random.choice(golden_messages)} "
                                f"{user.mention} now has {golden_count} golden sweetroll(s)!"
                            )
                            await message.remove_reaction(spawn_emoji, bot.user)
                            return

                    # Theft or gift roll
                    steal_or_gift_roll = random.randint(1, 100)
                    target_is_ghost = message.author.id == 305162419733397505
                    target_name = "Ghost" if target_is_ghost else message.author.mention
                    
                    if steal_or_gift_roll < config_py.SWEETROLL_GIFTING:
                        sweetrolls.insert_one(
                            {
                                "stolen_from": message.author.id,
                                "thief": user.id,
                                "date": datetime.now(),
                            }
                        )
                        await message.remove_reaction(spawn_emoji, bot.user)
                        await channel.send(
                            f"{user.mention} just stole the sweetroll from {target_name}!"
                        )
                    else:
                        sweetrolls.insert_one(
                            {
                                "gifted_to": message.author.id,
                                "gifter": user.id,
                                "date": datetime.now(),
                            }
                        )
                        await message.remove_reaction(spawn_emoji, bot.user)
                        await channel.send(
                            f"{user.mention} suddenly gifted a sweetroll to {target_name}! Extreme generosity!"
                        )

        except asyncio.TimeoutError:
            # Nobody reacted in time
            try:
                await message.remove_reaction(spawn_emoji, bot.user)
            except disnake.HTTPException:
                pass # Message or reaction was already gone
    
    except Exception as e:
        print(f"Error in _run_sweetroll_event: {e}")
        # Optionally remove reaction on any other error
        try:
            await message.remove_reaction(spawn_emoji, bot.user)
        except disnake.HTTPException:
            pass


async def check_sweetroll_chance(message: disnake.Message):
    """
    Checks if a sweetroll/pumpkin spawns. This part is fast.
    If a spawn happens, it launches the event logic as a non-blocking task.
    """
    
    # These must be globally available
    # bot, config_py
    
    sweetrolls = config_py.sweetrolls
    pumpkins = config_py.pumpkins
    channel = bot.get_channel(config_py.PET_CHANNEL)

    sweetroll_roll = random.randint(1, 100)
    sweetroll_needed = config_py.SWEETROLL_NEEDED

    # Only continue if a sweetroll (or secret rhubarb or pumpkin!) is going to spawn
    if sweetroll_roll > sweetroll_needed:
        # ­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­
        # 1-in-~167 chance that the “sweetroll” is secretly a rhubarb roll
        # This check happens first, as it disguises itself as a sweetroll.
        # ­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­­
        is_rhubarb = random.randint(1, 1000) >= 995

        # NEW: Check for pumpkin IF it's not a rhubarb
        is_pumpkin = False
        if not is_rhubarb:
            # This gives a 10% chance for a spawn to be a pumpkin (100 - 90)
            if random.randint(1, 100) > 60:
                is_pumpkin = True

        # Determine which emoji to use for the reaction
        if is_pumpkin:
            spawn_emoji = u"\U0001F383"  # Pumpkin
        else:
            spawn_emoji = u"\U0001F9C1"  # Sweetroll (even if it's a rhubarb)

        # LAUNCH THE NON-BLOCKING TASK
        # This lets check_sweetroll_chance return immediately,
        # unblocking the on_message event.
        asyncio.create_task(_run_sweetroll_event(
            message, sweetrolls, pumpkins, channel, 
            spawn_emoji, is_rhubarb, is_pumpkin
        ))

async def check_tags(message):
    if message.author == bot.user:
        return
    content = message.content.lower().split()
    reaction = u"\U0001F4D6"
    for tag, tag_url in tag_dict.items():
        if tag.lower() in content:
            # React with the eyes emoji
            await message.add_reaction(reaction)
    await asyncio.sleep (5)
    await message.remove_reaction(reaction, bot.user)
    

async def add_role_to_user(member, role_id, message):
    role = message.guild.get_role(role_id)
    if role:
        await member.add_roles(role)
        log_channel = bot.get_channel(config_py.E4D_ROLE_LOG)
        await log_channel.send(f"Added {role.name} to {member.display_name} in {message.guild.name}.")
        # Send a notification to the channel and delete it after 5 seconds
        if role_id == 807064226697969686:  # The specific role ID for in-game guild roles
            moderators_channel = bot.get_channel(1060472908188749904)  # Moderators' chat channel ID
            await moderators_channel.send(f"{member.display_name} added the in-game guild role to themselves. Please invite them to the guild in-game.")
        temp_message = await message.channel.send(f"{member.display_name}, I've given you the {role.name} role.")
        await asyncio.sleep(5)
        await temp_message.delete()

async def remove_role_from_user(member, role_id, message):
    role = message.guild.get_role(role_id)
    if role:
        await member.remove_roles(role)
        log_channel = bot.get_channel(config_py.E4D_ROLE_LOG)
        await log_channel.send(f"Removed {role.name} from {member.display_name} in {message.guild.name}.")
        # Send a notification to the channel and delete it after 5 seconds
        temp_message = await message.channel.send(f"The {role.name} role has been removed from you, {member.display_name}.")
        await asyncio.sleep(5)
        await temp_message.delete()
        

# =========================================================
# AUTOBOT TRAP LISTENER
# =========================================================

async def handle_trap_trigger(member: disnake.Member):
    """
    Punishes a user immediately with a ban, sends an alert, and handles admin reaction
    to potentially revoke the ban.
    """
    try:
        alert_channel_id = int(config_py.ALERT_CHANNEL_ID)
        ban_emoji = config_py.BAN_EMOJI
        check_emoji = getattr(config_py, "CHECK_EMOJI", "✅")
        wait_duration = config_py.WAIT_DURATION
    except AttributeError as e:
        print(f"Warning: Missing Trap Listener constant in config_py: {e}")
        return

    guild = member.guild
    alert_channel = guild.get_channel(alert_channel_id)
    
    if not alert_channel:
        print(f"ERROR: Alert channel {alert_channel_id} not found in guild {guild.name}")
        return

    # 1. Immediate Ban
    try:
        await guild.ban(member, reason="Triggered bot trap role")
        print(f"DEBUG: User {member.name} (ID: {member.id}) banned immediately.")
    except disnake.Forbidden:
        print(f"ERROR: Missing permissions to ban {member.name}.")
        await alert_channel.send(f"⚠️ I caught {member.mention} triggering the trap, but I lack permissions to ban them!")
        return
    except disnake.HTTPException as e:
        print(f"ERROR: HTTP exception during punishment: {e}")
        return

    # 2. Send Alert
    alert_message = await alert_channel.send(
        f"🚨 I caught {member.mention} ({member.name}) triggering the BOT trap role and **banned** them immediately.\n\n"
        f"{check_emoji} **Cancel Ban (False Alarm)**\n"
        f"{ban_emoji} **Confirm Ban (Dismiss)**"
    )
    
    await alert_message.add_reaction(check_emoji)
    await alert_message.add_reaction(ban_emoji)

    def check(reaction, user):
        return (
            reaction.message.id == alert_message.id 
            and str(reaction.emoji) in [str(ban_emoji), str(check_emoji)]
            and not user.bot
        )

    # 3. Wait for Admin Reaction
    try:
        # Note: Assuming 'bot' is accessible in your broader scope where this is called
        reaction, user = await bot.wait_for('reaction_add', timeout=wait_duration, check=check)
        
        try:
            await alert_message.clear_reactions()
        except (disnake.Forbidden, disnake.NotFound):
            pass
        
        emoji_clicked = str(reaction.emoji)

        if emoji_clicked == str(check_emoji):
            try:
                # Unban the user.
                await guild.unban(member, reason=f"Ban cancelled by {user.display_name}")
                await alert_channel.send(
                    f"✅ Ban revoked for **{member.name}** by {user.mention}. \n"
                    f"*Note: They have been removed from the server and will need a new invite link to rejoin.*"
                )
            except disnake.Forbidden:
                await alert_channel.send(f"⚠️ I don't have permission to unban {member.name}! {user.mention}, please do it manually.")
        
        elif emoji_clicked == str(ban_emoji):
            await alert_channel.send(f"🔒 Ban confirmed for **{member.name}** by {user.mention}.")

    except asyncio.TimeoutError:
        try:
            await alert_message.clear_reactions()
        except (disnake.Forbidden, disnake.NotFound):
            pass

# =========================================================
# LISTENERS
# =========================================================

@bot.event
async def on_member_update(before: disnake.Member, after: disnake.Member):
    """
    Triggers when an existing member updates their profile/roles.
    Catches users selecting the role in Onboarding AFTER initial join state.
    """
    try:
        trap_role_id = int(config_py.TRAP_ROLE_ID)
    except AttributeError:
        return

    had_role = any(r.id == trap_role_id for r in before.roles)
    has_role = any(r.id == trap_role_id for r in after.roles)

    # Only trigger if they didn't have it before, and have it now
    if not had_role and has_role:
        await handle_trap_trigger(after)

@bot.event
async def on_member_join(member: disnake.Member):

    STARTER_ROLE_IDS = [
    860463705107726367, 860463432598683668, 860463544306892801,
    860465085783736331, 860456372595458069, 860465893305745438,
    885850447137603596, 907295536598642738, 798229065898917889,
    787933341806624818
]

    try:
        trap_role_id = int(config_py.TRAP_ROLE_ID)
        
        # Check if they have the trap role upon arrival
        if any(r.id == trap_role_id for r in member.roles):
            await handle_trap_trigger(member)
            return
            
    except (AttributeError, ValueError):
        pass

    # Use disnake.Object to apply roles by ID without requiring a guild cache lookup
    roles_to_add = [disnake.Object(id=role_id) for role_id in STARTER_ROLE_IDS]
    
    await member.add_roles(*roles_to_add, reason="Automatic starter roles on join")
            
# Run the bot with the token
bot.run(config["token"])
