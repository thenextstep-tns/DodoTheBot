"""
General cog — bot/server info, command listing, usage stats, reminders and the
guide-link helper. All user-facing commands are hybrid (usable as ``/slash`` and
via a text prefix). User-facing text lives in ``lang``.
"""

import asyncio
import platform

import requests
from bs4 import BeautifulSoup

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages


class General(commands.Cog, name="general"):
    """General-purpose informational and utility commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="info", description="Get some useful (or not) information about the bot.")
    @checks.not_blacklisted()
    async def botinfo(self, context: Context) -> None:
        """Show basic information about Dodo."""
        embed = discord.Embed(description=lang.GENERAL_INFO_DESCRIPTION, color=config_py.success)
        embed.set_author(name=lang.GENERAL_INFO_AUTHOR)
        embed.add_field(name="Owner:", value=lang.GENERAL_INFO_OWNERS, inline=True)
        embed.add_field(name="Python Version:", value=platform.python_version(), inline=True)
        embed.add_field(
            name="Prefix:",
            value=lang.GENERAL_INFO_PREFIX_VALUE.format(prefixes=self.bot.config["prefix"]),
            inline=False,
        )
        embed.set_footer(text=lang.GENERAL_INFO_FOOTER)
        await context.send(embed=embed)

    @commands.hybrid_command(name="commands", description="Lists all loaded commands.")
    async def list_commands(self, context: Context) -> None:
        """List every loaded command, grouped by cog across paginated embeds."""
        cog_blocks: list[str] = []

        # Only list commands the caller may actually run in this guild, per the
        # per-guild visibility settings (owner-only tooling drops out for non-owners,
        # admin-only for non-admins, and anything in a cog disabled here).
        guild_id = context.guild.id if context.guild else None
        perms = getattr(context.author, "guild_permissions", None)
        has_manage = bool(context.guild and perms and perms.manage_guild)

        def _can_see(command) -> bool:
            top = command.root_parent or command
            cog = getattr(command, "cog", None)
            return self.bot.visibility.can_run(
                guild_id, context.author.id, top.name,
                cog.qualified_name if cog else None, has_manage_guild=has_manage,
            )

        for cog_name, cog in self.bot.cogs.items():
            command_list = sorted(
                (
                    f"- **{command.name}** - {command.description}"
                    for command in cog.get_commands()
                    if _can_see(command)
                ),
                key=str.lower,
            )
            if not command_list:
                continue

            cog_blocks.append(
                lang.GENERAL_COMMANDS_CATEGORY.format(cog_name=cog_name) + "\n" + "\n".join(command_list)
            )

        if not cog_blocks:
            await context.send(lang.GENERAL_COMMANDS_NONE)
            return

        embeds = messages.paged_embeds(
            cog_blocks, title=lang.GENERAL_COMMANDS_TITLE, footer=lang.GENERAL_COMMANDS_FOOTER
        )
        await messages.send_paged(context, embeds)

    @commands.command(name="guide")
    @checks.not_blacklisted()
    async def guide(self, context: Context, tag: str):
        """Internal helper: return guide-article links for a tag from the website.

        Not a slash command — it's invoked programmatically by the 📖 reaction
        listener and returns its results rather than replying to the user.
        """
        search_url = f"https://dodo.nextstep.team/tag/{tag}"
        try:
            response = requests.get(search_url)
        except requests.RequestException:
            await context.send(lang.GENERAL_GUIDE_ERROR)
            return []

        if response.status_code != 200:
            await context.send(lang.GENERAL_GUIDE_ERROR)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        article_links = soup.find_all("h2", class_="wp-block-post-title")
        return [(link.get_text(), link.a["href"]) for link in article_links if link.a]

    @commands.hybrid_command(name="server", description="Basic info on our server.")
    @checks.not_blacklisted()
    async def serverinfo(self, context: Context) -> None:
        """Show basic information about the current server."""
        roles = [role.name for role in context.guild.roles]
        if len(roles) > 50:
            roles = roles[:50] + [lang.GENERAL_SERVER_ROLES_OVERFLOW.format(total=len(context.guild.roles))]

        embed = discord.Embed(title=lang.GENERAL_SERVER_TITLE, description=str(context.guild), color=0x9C84EF)
        if context.guild.icon:
            embed.set_thumbnail(url=context.guild.icon.url)
        embed.add_field(name="Server ID", value=context.guild.id)
        embed.add_field(name="Member Count", value=context.guild.member_count)
        embed.add_field(name="Text/Voice Channels", value=len(context.guild.channels))
        embed.add_field(name=f"Roles ({len(context.guild.roles)})", value=", ".join(roles))
        embed.set_footer(text=lang.GENERAL_SERVER_CREATED_AT.format(created_at=context.guild.created_at))
        await context.send(embed=embed)

    @commands.hybrid_command(name="dodostats", description="Show how many times someone has used commands.")
    async def dodostats(self, context: Context, member: discord.Member = None) -> None:
        """Show a member's command-usage stats, broken down by command."""
        member = member or context.author
        commands_use = config_py.commands_use

        total_used = commands_use.count_documents({"User ID": member.id})
        if total_used == 0:
            await context.send(lang.GENERAL_STATS_NONE.format(name=member.display_name))
            return

        command_stats = [
            (command, commands_use.count_documents({"User ID": member.id, "Command": command}))
            for command in commands_use.distinct("Command")
        ]
        command_stats = sorted((c for c in command_stats if c[1] > 0), key=lambda item: item[1], reverse=True)

        header = lang.GENERAL_STATS_HEADER.format(name=member.display_name, total=total_used)
        pages = messages.chunk_blocks(
            (lang.GENERAL_STATS_LINE.format(command=command, count=count) for command, count in command_stats),
            separator="\n",
            limit=1999 - len(header),
        )

        embeds = [
            messages.embed(header + page, title=lang.GENERAL_STATS_TITLE.format(name=member.display_name))
            for page in pages
        ]
        await messages.send_paged(context, embeds)

    @commands.hybrid_command(
        name="remind",
        description="Set yourself an alarm in minutes; Dodo will poke you in due time.",
        aliases=["alarm", "poke", "remember"],
    )
    @checks.not_blacklisted()
    async def reminder(self, context: Context, minutes: int, *, reminder_text: str) -> None:
        """Remind the caller of ``reminder_text`` after ``minutes`` minutes."""
        await context.send(lang.GENERAL_REMIND_SET.format(text=reminder_text, minutes=minutes))
        await asyncio.sleep(minutes * 60)
        await context.channel.send(
            lang.GENERAL_REMIND_FIRE.format(mention=context.author.mention, text=reminder_text)
        )

    @commands.hybrid_command(name="schedule123", description="Sends you the current schedule in DMs.")
    @checks.not_blacklisted()
    async def schedule_dm(self, context: Context) -> None:
        """DM the caller the current weekly schedule (falls back to the channel)."""
        weekly_channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "WEEKLY_CHANNEL"))
        schedule = await weekly_channel.fetch_message(self.bot.guild_setting(context.guild, "WEEKLY_MESSAGE"))
        try:
            await context.author.send(schedule.content)
            await context.send(lang.GENERAL_SCHEDULE_SENT_DM)
        except discord.Forbidden:
            await context.send(lang.GENERAL_SCHEDULE_DM_FAILED)
            await context.send(schedule.content)

    @commands.hybrid_command(name="ping", description="Check if the bot is alive.")
    @checks.not_blacklisted()
    async def ping(self, context: Context) -> None:
        """Report the bot's gateway latency."""
        embed = discord.Embed(
            title=lang.GENERAL_PING_TITLE,
            description=lang.GENERAL_PING_DESCRIPTION.format(latency=round(self.bot.latency * 1000)),
            color=config_py.success,
        )
        await context.send(embed=embed)

    @commands.hybrid_command(name="invite", description="Get the bot's invite link (Fox only, for now).")
    @checks.not_blacklisted()
    async def invite(self, context: Context) -> None:
        """DM the caller the bot's invite link."""
        config = self.bot.config
        embed = discord.Embed(
            description=lang.GENERAL_INVITE_DESCRIPTION.format(
                application_id=config["application_id"], permissions=config["permissions"]
            ),
            color=config_py.warning,
        )
        try:
            await context.author.send(embed=embed)
            await context.send(lang.GENERAL_INVITE_SENT_DM)
        except discord.Forbidden:
            await context.send(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))
