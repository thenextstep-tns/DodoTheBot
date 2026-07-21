""""
Version 1.0
"""

import json
import os
import sys
import time
import asyncio
import pymongo

import datetime
from pymongo import ASCENDING

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


class Moderation(commands.Cog, name="moderation-normal"):
    def __init__(self, bot):
        self.bot = bot

        # --- BEGIN: moved from Pin class ---
        # Mongo: connect and prepare collection for pin fails (TTL 1 hour)
        # Expects config_py.MONGO_URI and config_py.DB_NAME to be set
        self.pin_fails = config_py.pin_fails

        # Create TTL index so fails expire automatically after 1 hour
        self.pin_fails.create_index(
            [("created_at", ASCENDING)],
            expireAfterSeconds=3600
        )

        # Messages for fails 10–19
        self.annoyed_messages = [
            "You really don’t have permission to pin messages here.",
            "Still not allowed.",
            "Nope. Try asking someone with permissions.",
            "Persistent, aren’t you? Still no.",
            "This isn’t working, stop.",
            "Seriously, stop.",
            "You’re starting to annoy me.",
            "Enough already.",
            "Final warning: stop it.",
            "STOP."
        ]
        # --- END: moved from Pin class ---

    # --- BEGIN: moved helpers from Pin class ---
    async def record_fail(self, user_id: int, reason: str):
        """Log a failed pin attempt with timestamp"""
        self.pin_fails.insert_one({
            "user_id": user_id,
            "reason": reason,
            "created_at": datetime.datetime.utcnow()
        })

    async def count_fails(self):
        """Count all current fails (not expired yet)"""
        return self.pin_fails.count_documents({})
    # --- END: moved helpers from Pin class ---

###### EVERYTHING ELSE ######
    
    @commands.command(
        name="kick",
        description="Kick a user out of the server. Only works if you have a permission to kick members",
    )
    @commands.has_permissions(kick_members=True)
    @checks.not_blacklisted()
    async def kick(self, context: Context, member: disnake.Member, *, reason: str = "Not specified") -> None:
        """
        Kick a user out of the server.
        :param context: The context in which the command has been executed.
        :param member: The member that should be kicked from the server.
        :param reason: The reason for the kick. Default is "Not specified".
        """
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        if member.guild_permissions.administrator:
            embed = disnake.Embed(
                title="Oi!",
                description="You can't kick other admins like that, ask Fox, he will gladly do it.",
                color=config_py.error
            )
            await context.send(embed=embed)
        else:
            try:
                embed = disnake.Embed(
                    title="User Kicked!",
                    description=f"**{member}** was kicked by **{context.author.display_name}**!",
                    color=0x9C84EF
                )
                embed.add_field(
                    name="Reason:",
                    value=reason
                )
                await channel.send(embed=embed)
                try:
                    await member.send(
                        f"You were kicked by **{context.author.display_name}**!\nReason: {reason}"
                    )
                except disnake.Forbidden:
                    # Couldn't send a message in the private messages of the user
                    pass
                await member.kick(reason=reason)
            except:
                embed = disnake.Embed(
                    title="Oir!",
                    description="An error occurred while trying to kick the user. Maybe it's for the best, but if you insist, make sure my role is above the role of the user you want to kick.",
                    color=0xE02B2B
                )
                await channel.send(embed=embed)

    @commands.command(
        name="nick",
        description="Change the nickname of a user on a server. Only works if you have a permission to manage nicknames",
    )
    @commands.has_permissions(manage_nicknames=True)
    @checks.not_blacklisted()
    async def nick(self, context: Context, member: disnake.Member, *, nickname: str = None) -> None:
        """
        Change the nickname of a user on a server.
        :param context: The context in which the command has been executed.
        :param member: The member that should have its nickname changed.
        :param nickname: The new nickname of the user. Default is None, which will reset the nickname.
        """
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        try:
            await member.edit(nick=nickname)
            embed = disnake.Embed(
                title="Changed Nickname!",
                description=f"**{member}'s** new nickname is **{nickname}**!",
                color=0x9C84EF
            )
            await context.send(embed=embed)
            await channel.send(embed=embed)
        except:
            embed = disnake.Embed(
                title="Oi!",
                description="An error occurred while trying to change the nickname of the user. Make sure my role is above the role of the user you want to change the nickname.",
                color=0xE02B2B
            )
            await context.send(embed=embed)

    @commands.command(
        name="ban",
        description="Bans a user from the server. Only works for people who have the permission to ban others",
    )
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def ban(self, context: Context, member: disnake.Member, *, reason: str = "Not specified") -> None:
        """
        Bans a user from the server.
        :param context: The context in which the command has been executed.
        :param member: The member that should be banned from the server.
        :param reason: The reason for the ban. Default is "Not specified".
        """
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        try:
            if member.guild_permissions.administrator:
                embed = disnake.Embed(
                    title="Oi!",
                    description="Don't ban admins! Do you have any idea, how hard it is to find a good admin?",
                    color=0xE02B2B
                )
                await context.send(embed=embed)
            else:
                embed = disnake.Embed(
                    title="User Banned!",
                    description=f"**{member}** was banned by **{context.author.display_name}**!",
                    color=0x9C84EF
                )
                embed.add_field(
                    name="Reason:",
                    value=reason
                )
                await channel.send(embed=embed)
                try:
                    await member.send(f"You were banned by **{context.author.display_name}**!\nReason: {reason}")
                except disnake.Forbidden:
                    # Couldn't send a message in the private messages of the user
                    pass
                await member.ban(reason=reason)
        except:
            embed = disnake.Embed(
                title="Error!",
                description="An error occurred while trying to ban the user. Make sure my role is above the role of the user you want to ban.",
                color=0xE02B2B
            )
            await context.send(embed=embed)
            
    @commands.command(
        name="go",
        description="Starts something funny. Only works for people who have the permission to ban others",
    )
    @commands.has_permissions(ban_members=True)
    @checks.not_blacklisted()
    async def ban(self, context: Context, member: disnake.Member):
        try:
            await member.send(f"There is an urgent task for you! Activate your SalvyFoxBumblephant and start the ZOOMIES at zoomies.dodos.fun")
        except disnake.Forbidden:
            # Couldn't send a message in the private messages of the user
            pass
        await context.message.delete()
        
    def check_roles(self, user, role_id):
        """
        Check if the user has a specific role by ID
        """
        role = disnake.utils.get(user.roles, id=role_id)
        return role is not None

    @commands.command(name="pin", description="Pin a replied message")
    async def pin(self, context):
        allowed_roles = [852793776064692264, 1055862512689623181]

        async def handle_fail(reason: str, default_msg: str):
            await self.record_fail(context.author.id, reason)
            fails = await self.count_fails()

            if fails >= 21:
                await context.send("I won’t be gentle. On your knees.")
                return True
            elif fails == 20:
                await context.send("Try to pin me once more, and I'll pin you so hard you won't even be able to squeak.")
                return True
            elif 10 <= fails <= 19:
                idx = fails - 10
                await context.send(self.annoyed_messages[idx])
                return True
            else:
                await context.send(default_msg)
                return True

        # Role check
        if not any(role.id in allowed_roles for role in context.author.roles):
            if await handle_fail("no_permission", "You do not have permission to pin messages."):
                return

        # Must be a reply
        if context.message.reference is None:
            if await handle_fail("no_reference", ":shrug: I have no idea which message to pin, please reply to a message."):
                return

        # Try to pin
        try:
            referenced_message = await context.channel.fetch_message(context.message.reference.message_id)
            await referenced_message.pin()
        except Exception:
            if await handle_fail("exception", "Something went wrong, I couldn’t pin that."):
                return

    @commands.command(name="unpin", description="Unpin a replied message")
    async def unpin(self, context):
        """
        Unpins the message that the user replied to
        """
        role_id = 852793776064692264
        if not self.check_roles(context.author, role_id):
            await context.send("You do not have permission to unpin messages.")
            return

        if context.message.reference is None:
            await context.send(":shrug: I have no idea which message to unpin, please reply to a message.")
            return

        referenced_message = await context.channel.fetch_message(context.message.reference.message_id)
        await referenced_message.unpin()
        await context.send(f"Message unpinned by {context.author.mention}.")

##########################################
###  POPULATE ###############################
############################################

#    @commands.command(
#        name="populate",
#        description="Adds every existing member to the channel",
#    )
#    @commands.has_guild_permissions(manage_messages=True)
#    @checks.not_blacklisted()
#    async def populate(self, context: Context) -> None:
#        """
#        Add fukken everyone to the channel
#        """
#        channel_id = context.channel.id
#        members = context.guild.members
#        ping_message = ""
#        ping_list = []
#        messages_to_delete = []
#        
#        for member in members:
#        # Check if the member can see the channel (or thread)
#            member_permissions = context.channel.permissions_for(member)
#            if member not in context.channel.members and member_permissions.view_channel:
#                # Ping the user and add it to the ping message
#                ping_message += f"{member.mention} "
#    
#                # Check if the ping message exceeds the character limit (1500)
#                if len(ping_message) > 1500:
#                    # Send the existing list of pings
#                    message = await disnake.TextChannel.send(self.bot.get_channel(channel_id), ping_message)
#                    messages_to_delete.append(message)
#    
#                    # Clean the ping message and start over
#                    ping_message = ""
#    
#                # Add the member to the ping list
#                ping_list.append(member)
#    
#        # Send any remaining pings if there are any
#        if ping_message:
#            message = await disnake.TextChannel.send(self.bot.get_channel(channel_id), ping_message)
#            messages_to_delete.append(message)
#    
#        # Clean the ping list
#        ping_list.clear()
#    
#        # Delete the messages sent by the bot
#        for message in messages_to_delete:
#            await message.delete()

#############################

    @commands.command(
        name="purge",
        description="Purges filth from the chat. Or the chat from the filth. Only works if you have a permission to manage messages",
    )
    @commands.has_guild_permissions(manage_messages=True)
    @checks.not_blacklisted()
    async def purge(self, context: Context, amount: int) -> None:
        """
        Delete a number of messages.
        :param context: The context in which the command has been executed.
        :param amount: The number of messages that should be deleted.
        """
        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
        try:
            amount = int(amount)
        except:
            embed = disnake.Embed(
                title="Oi!",
                description=f"`{amount}` is not a valid number.",
                color=config_py.error
            )
            await context.send(embed=embed)
            return
        if amount < 1:
            embed = disnake.Embed(
                title="Error!",
                description=f"`{amount}` is not a valid number.",
                color=config_py.error
            )
            await context.send(embed=embed)
            return
        if amount > 50:
            await context.send ("Oi, chief, if you wanna sabotage the whole server, at least suffer and delete it in small chunks")
            fox = await self.bot.get_or_fetch_user(309719542115074049)
            await fox.send("Someone is trying to purge more than 50 messages at once, check on them")
            return
        else:
            purged_messages = await context.channel.purge(limit=amount+1, check=lambda message: not message.pinned)
            embed = disnake.Embed(
                title="Purged!",
                description=f"**{context.author.display_name}** has purged the chat from the filth and deleted **{len(purged_messages)-1}** message(s)!",
                color=config_py.success
            )
            purgemsg = await context.send(embed=embed)
            await asyncio.sleep(3)
            await purgemsg.delete()
            await channel.send(embed=embed)
        

#    @commands.command(
#        name="hackban",
#        description="Bans a user without the user having to be in the server. We won't use it at all."
#    )
#    @commands.has_permissions(kick_members=True)
#    async def hackban(self, context: Context, user_id: int, *, reason: str) -> None:
#        """
#        Bans a user without the user having to be in the server.
#        :param context: The context in which the command has been executed.
#        :param user_id: The ID of the user that should be banned.
#        :param reason: The reason for the ban. Default is "Not specified".
#        """
#        try:
#            await self.bot.http.ban(user_id, context.guild.id, reason=reason)
#            user = await self.bot.get_or_fetch_user(user_id)
#            embed = disnake.Embed(
#                title="User Banned!",
#                description=f"**{user} (ID: {user_id}) ** was banned by **{context.author.display_name}**!",
#                color=0x9C84EF
#            )
#            embed.add_field(
#                name="Reason:",
#                value=reason
#            )
#            await context.send(embed=embed)
#        except:
#            embed = disnake.Embed(
#                title="Error!",
#                description="An error occurred while trying to ban the user. Make sure ID is an existing ID that belongs to a user.",
#                color=0xE02B2B
#            )
#            await context.send(embed=embed)
#            
#    
#    @commands.command(
#        name="legend",
#        description="This is a command that adds boilerplate Legend clears")
#    @commands.has_permissions(manage_roles=True)
#    @checks.not_blacklisted()
#    async def legend(self, context, member : disnake.Member = None):
#        """
#        This is a command that adds boilerplate Legend clears
#        """
#        channel = self.bot.get_channel(config_py.LOG_CHANNEL)
##        for x in config_py.legend:
 #           role = context.guild.get_role(x) 
 #           await member.add_roles(role)
 #           await channel.send(f"Added the {role.name} role to {member.display_name}")
 #       await context.send ("We successfully added legend roles to " + member.display_name)
 #   
 #   @commands.command(
 #       name="veteran",
 #       description="This is a command that adds boilerplate Veteran clears")
 #   @commands.has_permissions(manage_roles=True)
 #   @checks.not_blacklisted()
 #   async def veteran(self, context, member : disnake.Member = None):
 #       """
 #       This is a command that adds boilerplate Veteran clears
 #       """
 #       channel = self.bot.get_channel(config_py.LOG_CHANNEL)
 #       for x in config_py.veteran:
 #           role = context.guild.get_role(x) 
 ##           await member.add_roles(role)
  #          await channel.send(f"Added the {role.name} role to {member.display_name}")
  #      for x in config_py.veteranRemove:
  #          role = context.guild.get_role(x) 
  #          await member.remove_roles(role)
  #          await channel.send(f"Removed the {role.name} role from {member.display_name}")
  #      await context.send ("We successfully added Veteran roles to " + member.display_name)
  #  
    
    
    
    
    
def setup(bot):
    bot.add_cog(Moderation(bot))
