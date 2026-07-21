""""
Version: 1.0
"""

import json
import os
import platform
import random
import sys
import requests
import asyncio
import time
from bs4 import BeautifulSoup

import aiohttp
import disnake
from disnake.ext import commands
from disnake.ext.commands import Context

from helpers import checks

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

class General(commands.Cog, name="general-normal"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="info",
        description="Get some useful (or not) information about the bot.",
    )
    @checks.not_blacklisted()
    async def botinfo(self, context: Context) -> None:
        """
        Basic info on Dodo
        """
        embed = disnake.Embed(
            description="This is our personal mentally challenged Instagram blog",
            color=config_py.success
        )
        embed.set_author(
            name="Dodo, the almost useless helper"
        )
        embed.add_field(
            name="Owner:",
            value="Salvy and Fox",
            inline=True
        )
        embed.add_field(
            name="Python Version:",
            value=f"{platform.python_version()}",
            inline=True
        )
        embed.add_field(
            name="Prefix:",
            value=f"/ (Slash Commands) or {config['prefix']} for normal commands",
            inline=False
        )
        embed.set_footer(
            text=f"Powered by electricity. Thank you, electricity"
        )
        await context.send(embed=embed)

    @commands.command(name="commands", description="Lists all loaded commands.")
    async def list_commands(self, context):
        """
        Lists all loaded commands, grouped on pages up to the 4096 character limit.
        """
        embeds = []
        current_parts = []
        current_length = 0
        CHAR_LIMIT = 4096

        for cog_name, cog in self.bot.cogs.items():
            command_list = []
            for command in cog.get_commands():
                command_list.append(f"- **{command.name}** - {command.description}")
            
            if command_list:
                command_list.sort(key=lambda cmd: cmd.lower())  
                
                # Format the text block for this specific cog
                cog_block = f"**Category: {cog_name}**\n" + "\n".join(command_list)
                
                # Account for the double newline separator length if we are appending
                separator_length = 2 if current_parts else 0 
                
                if current_length + separator_length + len(cog_block) > CHAR_LIMIT:
                    # Exceeds limit, build the current embed and start a new one
                    embed = disnake.Embed(
                        title="List of Loaded Commands",
                        description="\n\n".join(current_parts),
                        color=0x3498db 
                    )
                    embed.set_footer(text="Add dodo/gib/any other prefix before it and enjoy the weirdness!")
                    embeds.append(embed)
                    
                    # Reset trackers for the next page
                    current_parts = [cog_block]
                    current_length = len(cog_block)
                else:
                    # Fits comfortably, add to current parts
                    current_parts.append(cog_block)
                    current_length += separator_length + len(cog_block)

        if current_parts:
            embed = disnake.Embed(
                title="List of Loaded Commands",
                description="\n\n".join(current_parts),
                color=0x3498db 
            )
            embed.set_footer(text="Add dodo/gib/any other prefix before it and enjoy the weirdness!")
            embeds.append(embed)

        if not embeds:
            await context.send("No commands loaded.")
            return

        current_page = 0
        view = disnake.ui.View(timeout=180.0)

        prev_button = disnake.ui.Button(label="Previous", style=disnake.ButtonStyle.blurple, emoji="◀️", disabled=True)
        next_button = disnake.ui.Button(label="Next", style=disnake.ButtonStyle.blurple, emoji="▶️", disabled=len(embeds) <= 1)

        async def prev_callback(interaction: disnake.Interaction):
            nonlocal current_page
            current_page -= 1
            next_button.disabled = False
            if current_page == 0:
                prev_button.disabled = True
            await interaction.response.edit_message(embed=embeds[current_page], view=view)

        async def next_callback(interaction: disnake.Interaction):
            nonlocal current_page
            current_page += 1
            prev_button.disabled = False
            if current_page == len(embeds) - 1:
                next_button.disabled = True
            await interaction.response.edit_message(embed=embeds[current_page], view=view)

        prev_button.callback = prev_callback
        next_button.callback = next_callback

        view.add_item(prev_button)
        view.add_item(next_button)

        await context.send(embed=embeds[0], view=view)
    
    @commands.command(name="guide", description = "Helper command that is triggered on every message to check if we have a guide about the message on the website")
    @checks.not_blacklisted()
    async def dodo_check(self, context, tag):
        # Convert tags into a single string separated by dashes
    
        # Create the URL for the search
        search_url = f"https://dodo.nextstep.team/tag/{tag}"
    
        # Send a request to the website
        response = requests.get(search_url)
    
        if response.status_code == 200:
            # Parse the HTML content of the page
            soup = BeautifulSoup(response.text, 'html.parser')
    
            # Find all the article links on the page
            article_links = soup.find_all('h2', class_='wp-block-post-title')
    
            if article_links:
                # Create a list to store the links
                links = []
    
                for link in article_links:
                    # Extract the title and URL from each article link
                    title = link.get_text()
                    url = link.a['href']
    
                    # Append the link to the list
                    links.append((title, url))
    
                return links  # Return the list of links
            else:
                #await context.send("Sorry, I couldn't find anything, ask moderators or raid leads, maybe that guide is work in progress!")
                return []  # Return an empty list if no links were found
        else:
            await context.send("Something went wrong, let's try again!")
    
        
    
    @commands.command(
        name="server",
        description="Basic info on our server",
    )
    @checks.not_blacklisted()
    async def serverinfo(self, context: Context) -> None:
        """
        Basic info on the server
        """
        roles = [role.name for role in context.guild.roles]
        if len(roles) > 50:
            roles = roles[:50]
            roles.append(f">>>> Displaying[50/{len(roles)}] Roles")
        roles = ", ".join(roles)

        embed = disnake.Embed(
            title="**Server Name:**",
            description=f"{context.guild}",
            color=0x9C84EF
        )
        embed.set_thumbnail(
            url=context.guild.icon.url
        )
        embed.add_field(
            name="Server ID",
            value=context.guild.name
        )
        embed.add_field(
            name="Member Count",
            value=context.guild.member_count
        )
        embed.add_field(
            name="Text/Voice Channels",
            value=f"{len(context.guild.channels)}"
        )
        embed.add_field(
            name=f"Roles ({len(context.guild.roles)})",
            value=roles
        )
        embed.set_footer(
            text=f"Created at: {context.guild.created_at}"
        )
        await context.send(embed=embed)


    @commands.command(name="dodostats", description="Show how many times someone has used a certain command")
    async def dodostats(self, context, member: disnake.Member = None):
        """
        Check how many commands have you used over the course of your Dodos career
        """
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        
        if not member:
            member = context.author

        commands_use = config_py.commands_use
        usercommandsused = commands_use.find({ "User ID": member.id })
        countusercommanddailies = usercommandsused.count()

        if countusercommanddailies == 0:
            await channel.send(f"{member.display_name}, you haven't used our Dodo yet! She's waiting!")
            return

        commandslist = commands_use.distinct("Command")
        
        # Calculate counts and store them in a list
        command_stats = []
        for Command in commandslist:
            commanduse = commands_use.find({ "User ID": member.id, "Command": Command }).count()
            if commanduse != 0:
                command_stats.append((Command, commanduse))
                
        # Sort the list by usage count in descending order (highest to lowest)
        command_stats.sort(key=lambda item: item[1], reverse=True)
        
        embeds = []
        current_parts = []
        current_length = 0
        CHAR_LIMIT = 1999
        
        # Global stats header that we will attach to the top of every page
        stats_header = f"Since we started counting, {member.display_name} has used **{countusercommanddailies} dodo commands**! :dodo:\n\n"
        
        for Command, commanduse in command_stats:
            line = f"**{Command}** command - **{commanduse}** times"
            separator_length = 1 if current_parts else 0 # Length of a newline character
            
            # Check if adding this line exceeds the Discord embed limit
            if current_length + separator_length + len(line) + len(stats_header) > CHAR_LIMIT:
                    
                    # Store the current embed
                    embed = disnake.Embed(
                        title=f"{member.display_name}'s Dodo Stats",
                        description=stats_header + "\n".join(current_parts),
                        color=0x3498db
                    )
                    embeds.append(embed)
                    
                    # Reset trackers for the next page
                    current_parts = [line]
                    current_length = len(line)
            else:
                # Fits comfortably, add to current parts
                current_parts.append(line)
                current_length += separator_length + len(line)

        if current_parts:
            embed = disnake.Embed(
                title=f"{member.display_name}'s Dodo Stats",
                description=stats_header + "\n".join(current_parts),
                color=0x3498db
            )
            embeds.append(embed)

        if not embeds:
            await channel.send(f"{member.display_name}, no specific command data found.")
            return

        current_page = 0
        view = disnake.ui.View(timeout=180.0)

        prev_button = disnake.ui.Button(label="Previous", style=disnake.ButtonStyle.blurple, emoji="◀️", disabled=True)
        next_button = disnake.ui.Button(label="Next", style=disnake.ButtonStyle.blurple, emoji="▶️", disabled=len(embeds) <= 1)

        async def prev_callback(interaction: disnake.Interaction):
            nonlocal current_page
            current_page -= 1
            next_button.disabled = False
            if current_page == 0:
                prev_button.disabled = True
            await interaction.response.edit_message(embed=embeds[current_page], view=view)

        async def next_callback(interaction: disnake.Interaction):
            nonlocal current_page
            current_page += 1
            prev_button.disabled = False
            if current_page == len(embeds) - 1:
                next_button.disabled = True
            await interaction.response.edit_message(embed=embeds[current_page], view=view)

        prev_button.callback = prev_callback
        next_button.callback = next_callback

        view.add_item(prev_button)
        view.add_item(next_button)

        # Send the output to the target channel (PET_CHANNEL)
        await channel.send(embed=embeds[0], view=view)



#####################################
#                                   #
#               SCHEDULE            #          
#                                   #
#####################################
#    @commands.command(
#        name="schedule",
#        description="Check what we have planned for the current week",
#        aliases = ['raid', 'raids', 'raid info', 'sup']
#    )
#    @checks.not_blacklisted()
#    async def schedule(self, context: Context) -> None:
#        """
#        Check what we have planned for the current week.
#        """
#        weeklyChannel = self.bot.get_channel(config_py.WEEKLY_CHANNEL)
#        schedule = await weeklyChannel.fetch_message(config_py.WEEKLY_MESSAGE)
        #await context.send ("I haven't found a message to fetch our schedule from, sorry :pleading_face: ")
#        await context.send(lang.SCHEDULE_INTROS[random.randint(0, len(lang.SCHEDULE_INTROS)-1)])
#        await context.send(schedule.content)

#####################################
#           REMIND                  #          
#####################################
    @commands.command(
        name="remind",
        description="Set yourself an alarm in minutes, dodo will poke you in due time",
        aliases = ['alarm', 'poke', 'remember']
    )
    @checks.not_blacklisted()
    async def reminder(self, context, minutes: int, *, reminder_text: str):
        # Save user and channel information
        member = context.author
        channel = context.channel
        await channel.send(f"Ok! I will remind you of this: '{reminder_text}' in {minutes} minute(s)!")
        # Sleep for the specified number of minutes
        await asyncio.sleep(minutes * 60)
    
        # Send a reminder to the user in the same channel
        reminder_message = f"Hey {member.mention}, you asked me to remind you of this: {reminder_text} :heart: :dodo: "
        await channel.send(reminder_message)


#####################################
    
    @commands.command(
        name="schedule123",
        description="Sends the user the current schedule in DMs",
    )
    @checks.not_blacklisted()
    async def invite123(self, context: Context) -> None:
        """
        Sends the user the current schedule in DMs
        """
        weeklyChannel = self.bot.get_channel(config_py.WEEKLY_CHANNEL)
        schedule = await weeklyChannel.fetch_message(config_py.WEEKLY_MESSAGE)
        try:
            await context.author.send(schedule.content)
            await context.send("I sent you our current schedule in a private message!")
        except disnake.Forbidden:
            await context.send("I couldn't send you our schedule in DMs, so I will send it in here:")
            await context.send(schedule.content)
    
    
    
    @commands.command(
        name="ping",
        description="Check if the bot is alive.",
    )
    @checks.not_blacklisted()
    async def ping(self, context: Context) -> None:
        """
        Check if the bot is alive.
        """
        embed = disnake.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.bot.latency * 1000)}ms.",
            color=config_py.success
        )
        await context.send(embed=embed)

    @commands.command(
        name="invite",
        description="Get the invite link of the bot to be able to invite it. Won't work if you're not Fox",
    )
    @checks.not_blacklisted()
    async def invite(self, context: Context) -> None:
        """
        Get the invite link of the bot to be able to invite it.
        """
        embed = disnake.Embed(
            description=f"Invite me to your server by clicking [here](https://discordapp.com/oauth2/authorize?&client_id={config['application_id']}&scope=bot+applications.commands&permissions={config['permissions']}). Except it won't work if you're not Fox. For now.",
            color=config_py.warning
        )
        try:
            # To know what permissions to give to your bot, please see here: https://discordapi.com/permissions.html and remember to not give Administrator permissions.
            await context.author.send(embed=embed)
            await context.send("I sent you a private message!")
        except disnake.Forbidden:
            await context.send(embed=embed)

    #@commands.command(
    #    name="8ball",
    #    description="Ask any question to the bot.",
    #)
    #@checks.not_blacklisted()
    #async def eight_ball(self, context: Context, *, question: str) -> None:
    #    """
    #    Ask any question to the bot.
    #    :param context: The context in which the command has been executed.
    #    :param question: The question that should be asked by the user.
    #    """
    #    answers = ["It is certain.", "It is decidedly so.", "You may rely on it.", "Without a doubt.",
    #               "Yes - definitely.", "As I see, yes.", "Most likely.", "Outlook good.", "Yes.",
    #               "Signs point to yes.", "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    #               "Cannot predict now.", "Concentrate and ask again later.", "Don't count on it.", "My reply is no.",
    #               "My sources say no.", "Outlook not so good.", "Very doubtful."]
    #    embed = disnake.Embed(
    #        title="**My Answer:**",
    #        description=f"{random.choice(answers)}",
    #        color=0x9C84EF
    #    )
    #    embed.set_footer(
    #        text=f"The question was: {question}"
    #    )
    #    await context.send(embed=embed)

    #@commands.command(
    #    name="bitcoin",
    #    description="Get the current price of bitcoin.",
    #)
    #@checks.not_blacklisted()
    #async def bitcoin(self, context: Context) -> None:
    #    """
    #    Get the current price of bitcoin.
    #    :param context: The context in which the command has been executed.
    #    """
    #    # This will prevent your bot from stopping everything when doing a web request - see: https://discordpy.readthedocs.io/en/stable/faq.html#how-do-i-make-a-web-request
    #    async with aiohttp.ClientSession() as session:
    #        async with session.get("https://api.coindesk.com/v1/bpi/currentprice/BTC.json") as request:
    #            if request.status == 200:
    #                data = await request.json(
    #                    content_type="application/javascript")  # For some reason the returned content is of type JavaScript
    #                embed = disnake.Embed(
    #                    title="Bitcoin price",
    #                    description=f"The current price is {data['bpi']['USD']['rate']} :dollar:",
    #                    color=0x9C84EF
    #                )
    #            else:
    #                embed = disnake.Embed(
    #                    title="Error!",
    #                    description="There is something wrong with the API, please try again later",
    #                    color=0xE02B2B
    #                )
    #            await context.send(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
