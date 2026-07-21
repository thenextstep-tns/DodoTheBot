""""
Copyright © Krypton 2021 - https://github.com/kkrypt0nn (https://krypt0n.co.uk)
Description:
This is a template to create your own discord bot in python.

Version: 4.1
"""

import json
import os
import sys

import disnake
from disnake.ext import commands
from disnake.ext.commands import Context

from helpers import json_manager, checks

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

class Owner(commands.Cog, name="owner-normal"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="kill",
        description="Make the bot shutdown. Only works if you're the owner",
    )
    @checks.is_owner()
    async def shutdown(self, context: Context):
        """
        Makes the bot shutdown.
        """
        embed = disnake.Embed(
            description="Ah shit, not again! Family, here I come :wave:",
            color=0x9C84EF
        )
        await context.send(embed=embed)
        await self.bot.close()
        
#########################
#       PURGE ROLE      #
#########################

    @commands.command(name="cleanrole", description = "Allows you to remove a role from all the people on the server who have it. Only works if you have a permission for that")
    @checks.is_owner()
    async def remove_role(self, context, *, role_name: str):
        # Check if the user invoking the command has the necessary permissions
        if not context.author.guild_permissions.manage_roles:
            await context.send("You don't have the required permissions to manage roles.")
            return
    
        # Get the role by name
        role = disnake.utils.get(context.guild.roles, name=role_name)
    
        # Check if the role exists
        if role is None:
            await context.send(f"Role '{role_name}' not found.")
            return
    
        # Iterate through all members with the specified role and remove the role
        members_with_role = [member for member in context.guild.members if role in member.roles]
        for member in members_with_role:
            await member.remove_roles(role)
    
        await context.send(f"Role '{role_name}' removed from all members who had it.")
    
    @commands.command(
        name="addons",
        description="Show the add-ons that we use. Works automatically if you mention addons, so can be skipped",
    )
    @checks.is_owner()
    
    
    async def say(self, context: Context):
        """
        Show the add-ons that we recommend
        """
        embed = disnake.Embed (
            title = "Hey! Here's the list of add-ons that we would recommend!",
            description = "http://dodos.fun/add-ons/")
        embed.set_image (url = "http://dodos.fun/wp-content/uploads/2022/03/unknown-4-1-1024x579-1.png")
        await context.send(embed = embed)




    @commands.group(
        name="blacklist"
    )
    async def blacklist(self, context: Context):
        """
        Lets you add or remove a user from not being able to use the bot.
        """
        if context.invoked_subcommand is None:
            with open("blacklist.json") as file:
                blacklist = json.load(file)
            embed = disnake.Embed(
                title=f"There are currently {len(blacklist['ids'])} blacklisted IDs",
                description=f"{', '.join(str(id) for id in blacklist['ids'])}",
                color=0x9C84EF
            )
            await context.send(embed=embed)#

    @blacklist.command(
        name="add"
    )
    @checks.is_owner()    
    async def blacklist_add(self, context: Context, member: disnake.Member = None):
        """
        Lets you add a user from not being able to use the bot.
        """
        try:
            user_id = member.id
            with open("blacklist.json") as file:
                blacklist = json.load(file)
            if user_id in blacklist['ids']:
                embed = disnake.Embed(
                    title="Error!",
                    description=f"**{member.name}** is already in the blacklist.",
                    color=0xE02B2B
                )
                return await context.send(embed=embed)
            json_manager.add_user_to_blacklist(user_id)
            embed = disnake.Embed(
                title="User Blacklisted",
                description=f"**{member.name}** has been successfully added to the blacklist",
                color=0x9C84EF
            )
            with open("blacklist.json") as file:
                blacklist = json.load(file)
            embed.set_footer(
                text=f"There are now {len(blacklist['ids'])} users in the blacklist"
            )
            await context.send(embed=embed)
        except:
            embed = disnake.Embed(
                title="Error!",
                description=f"An unknown error occurred when trying to add **{member.name}** to the blacklist.",
                color=0xE02B2B
            )
            await context.send(embed=embed)#

    @blacklist.command(
        name="remove"
    )
    @checks.is_owner()
    async def blacklist_remove(self, context, member: disnake.Member = None):
        """
        Lets you remove a user from not being able to use the bot.
        """
        try:
            user_id = member.id
            json_manager.remove_user_from_blacklist(user_id)
            embed = disnake.Embed(
                title="User removed from blacklist",
               description=f"**{member.name}** has been successfully removed from the blacklist",
               color=0x9C84EF
            )
            with open("blacklist.json") as file:
                blacklist = json.load(file)
            embed.set_footer(
                text=f"There are now {len(blacklist['ids'])} users in the blacklist"
            )
            await context.send(embed=embed)
        except:
            embed = disnake.Embed(
                title="Error!",
                description=f"**{member.name}** is not in the blacklist.",
                color=0xE02B2B
            )
            await context.send(embed=embed)#

def setup(bot):
    bot.add_cog(Owner(bot))
