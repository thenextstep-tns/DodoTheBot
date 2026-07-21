"""
Owner cog — bot-management commands restricted to the owners listed in
``config.json`` (shutdown, command-tree sync, bulk role removal, add-on info and
the blacklist). All commands are hybrid. User-facing text lives in ``lang``.
"""

import json

import discord
from discord.ext import commands
from discord.ext.commands import Context

import lang
from helpers import checks, json_manager

BLACKLIST_FILE = "blacklist.json"
_ACCENT = 0x9C84EF
_ERROR = 0xE02B2B


def _load_blacklist() -> dict:
    with open(BLACKLIST_FILE, encoding="utf-8") as file:
        return json.load(file)


class Owner(commands.Cog, name="owner"):
    """Owner-only bot management."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="kill", description="Shut the bot down (owner only).")
    @checks.is_owner()
    async def shutdown(self, context: Context) -> None:
        """Gracefully shut the bot down."""
        await context.send(embed=discord.Embed(description=lang.OWNER_SHUTDOWN, color=_ACCENT))
        await self.bot.close()

    @commands.hybrid_command(name="sync", description="Re-sync the slash-command tree (owner only).")
    @checks.is_owner()
    async def sync(self, context: Context) -> None:
        """Re-sync application commands to the dev guild (or globally)."""
        dev_guild_id = self.bot.config.get("test_guild_id")
        if dev_guild_id:
            guild = discord.Object(id=int(dev_guild_id))
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
        else:
            synced = await self.bot.tree.sync()
        await context.send(lang.OWNER_SYNCED.format(count=len(synced)))

    @commands.hybrid_command(name="cleanrole", description="Remove a role from every member who has it (owner only).")
    @checks.is_owner()
    @commands.has_permissions(manage_roles=True)
    async def cleanrole(self, context: Context, *, role_name: str) -> None:
        """Strip ``role_name`` from all members who currently have it."""
        role = discord.utils.get(context.guild.roles, name=role_name)
        if role is None:
            await context.send(lang.OWNER_CLEANROLE_NOT_FOUND.format(role=role_name))
            return
        for member in [m for m in context.guild.members if role in m.roles]:
            await member.remove_roles(role)
        await context.send(lang.OWNER_CLEANROLE_DONE.format(role=role_name))

    @commands.hybrid_command(name="addons", description="Show the add-ons we recommend.")
    @checks.is_owner()
    async def addons(self, context: Context) -> None:
        """Post the recommended add-ons link/image."""
        embed = discord.Embed(title=lang.OWNER_ADDONS_TITLE, description=lang.OWNER_ADDONS_URL)
        embed.set_image(url=lang.OWNER_ADDONS_IMAGE)
        await context.send(embed=embed)

    @commands.hybrid_group(name="blacklist", fallback="list", description="Manage the bot blacklist.")
    @checks.is_owner()
    async def blacklist(self, context: Context) -> None:
        """Show the current blacklist."""
        blacklist = _load_blacklist()
        embed = discord.Embed(
            title=lang.OWNER_BLACKLIST_TITLE.format(count=len(blacklist["ids"])),
            description=", ".join(str(user_id) for user_id in blacklist["ids"]) or "None",
            color=_ACCENT,
        )
        await context.send(embed=embed)

    @blacklist.command(name="add", description="Blacklist a user from using the bot.")
    @checks.is_owner()
    async def blacklist_add(self, context: Context, member: discord.User) -> None:
        """Add ``member`` to the blacklist."""
        blacklist = _load_blacklist()
        if member.id in blacklist["ids"]:
            await context.send(embed=discord.Embed(title="Error!", description=lang.OWNER_BLACKLIST_ADD_ALREADY.format(name=member.name), color=_ERROR))
            return
        json_manager.add_user_to_blacklist(member.id)
        embed = discord.Embed(
            title=lang.OWNER_BLACKLIST_ADD_TITLE, description=lang.OWNER_BLACKLIST_ADD_DONE.format(name=member.name), color=_ACCENT
        )
        embed.set_footer(text=lang.OWNER_BLACKLIST_FOOTER.format(count=len(_load_blacklist()["ids"])))
        await context.send(embed=embed)

    @blacklist.command(name="remove", description="Remove a user from the blacklist.")
    @checks.is_owner()
    async def blacklist_remove(self, context: Context, member: discord.User) -> None:
        """Remove ``member`` from the blacklist."""
        blacklist = _load_blacklist()
        if member.id not in blacklist["ids"]:
            await context.send(embed=discord.Embed(title="Error!", description=lang.OWNER_BLACKLIST_REMOVE_NONE.format(name=member.name), color=_ERROR))
            return
        json_manager.remove_user_from_blacklist(member.id)
        embed = discord.Embed(
            title=lang.OWNER_BLACKLIST_REMOVE_TITLE, description=lang.OWNER_BLACKLIST_REMOVE_DONE.format(name=member.name), color=_ACCENT
        )
        embed.set_footer(text=lang.OWNER_BLACKLIST_FOOTER.format(count=len(_load_blacklist()["ids"])))
        await context.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))
