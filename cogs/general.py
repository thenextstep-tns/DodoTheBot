"""
General cog — bot/server info, command listing, usage stats, reminders and the
guide-link helper. All user-facing commands are hybrid (usable as ``/slash`` and
via a text prefix).
"""

import asyncio
import platform

import requests
from bs4 import BeautifulSoup

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks

# Reusable page-turner buttons cap.
_VIEW_TIMEOUT = 180.0
_EMBED_CHAR_LIMIT = 4096


class _Paginator(discord.ui.View):
    """A minimal Previous/Next button view for paging through a list of embeds."""

    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=_VIEW_TIMEOUT)
        self.embeds = embeds
        self.index = 0
        self.prev_button.disabled = True
        self.next_button.disabled = len(embeds) <= 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self.next_button.disabled = False
        self.prev_button.disabled = self.index == 0
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self.prev_button.disabled = False
        self.next_button.disabled = self.index == len(self.embeds) - 1
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)


class General(commands.Cog, name="general"):
    """General-purpose informational and utility commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="info", description="Get some useful (or not) information about the bot.")
    @checks.not_blacklisted()
    async def botinfo(self, context: Context) -> None:
        """Show basic information about Dodo."""
        prefixes = self.bot.config["prefix"]
        embed = discord.Embed(
            description="This is our personal mentally challenged Instagram blog",
            color=config_py.success,
        )
        embed.set_author(name="Dodo, the almost useless helper")
        embed.add_field(name="Owner:", value="Salvy and Fox", inline=True)
        embed.add_field(name="Python Version:", value=platform.python_version(), inline=True)
        embed.add_field(
            name="Prefix:",
            value=f"/ (Slash Commands) or {prefixes} for normal commands",
            inline=False,
        )
        embed.set_footer(text="Powered by electricity. Thank you, electricity")
        await context.send(embed=embed)

    @commands.hybrid_command(name="commands", description="Lists all loaded commands.")
    async def list_commands(self, context: Context) -> None:
        """List every loaded command, grouped by cog across paginated embeds."""
        pages: list[str] = []
        current_parts: list[str] = []
        current_length = 0

        for cog_name, cog in self.bot.cogs.items():
            command_list = sorted(
                (f"- **{command.name}** - {command.description}" for command in cog.get_commands()),
                key=str.lower,
            )
            if not command_list:
                continue

            cog_block = f"**Category: {cog_name}**\n" + "\n".join(command_list)
            separator = 2 if current_parts else 0
            if current_length + separator + len(cog_block) > _EMBED_CHAR_LIMIT:
                pages.append("\n\n".join(current_parts))
                current_parts = [cog_block]
                current_length = len(cog_block)
            else:
                current_parts.append(cog_block)
                current_length += separator + len(cog_block)

        if current_parts:
            pages.append("\n\n".join(current_parts))

        if not pages:
            await context.send("No commands loaded.")
            return

        embeds = []
        for page in pages:
            embed = discord.Embed(title="List of Loaded Commands", description=page, color=0x3498DB)
            embed.set_footer(text="Add dodo/gib/any other prefix before it and enjoy the weirdness!")
            embeds.append(embed)

        view = _Paginator(embeds) if len(embeds) > 1 else None
        await context.send(embed=embeds[0], view=view)

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
            await context.send("Something went wrong, let's try again!")
            return []

        if response.status_code != 200:
            await context.send("Something went wrong, let's try again!")
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
            roles = roles[:50] + [f">>>> Displaying [50/{len(context.guild.roles)}] Roles"]

        embed = discord.Embed(title="**Server Name:**", description=str(context.guild), color=0x9C84EF)
        if context.guild.icon:
            embed.set_thumbnail(url=context.guild.icon.url)
        embed.add_field(name="Server ID", value=context.guild.id)
        embed.add_field(name="Member Count", value=context.guild.member_count)
        embed.add_field(name="Text/Voice Channels", value=len(context.guild.channels))
        embed.add_field(name=f"Roles ({len(context.guild.roles)})", value=", ".join(roles))
        embed.set_footer(text=f"Created at: {context.guild.created_at}")
        await context.send(embed=embed)

    @commands.hybrid_command(name="dodostats", description="Show how many times someone has used commands.")
    async def dodostats(self, context: Context, member: discord.Member = None) -> None:
        """Show a member's command-usage stats, broken down by command."""
        member = member or context.author
        commands_use = config_py.commands_use

        total_used = commands_use.count_documents({"User ID": member.id})
        if total_used == 0:
            await context.send(f"{member.display_name}, you haven't used our Dodo yet! She's waiting!")
            return

        # Count usage per distinct command, most-used first.
        command_stats = [
            (command, commands_use.count_documents({"User ID": member.id, "Command": command}))
            for command in commands_use.distinct("Command")
        ]
        command_stats = sorted((c for c in command_stats if c[1] > 0), key=lambda item: item[1], reverse=True)

        header = (
            f"Since we started counting, {member.display_name} has used "
            f"**{total_used} dodo commands**! :dodo:\n\n"
        )
        char_limit = 1999
        pages: list[str] = []
        current_parts: list[str] = []
        current_length = 0

        for command, count in command_stats:
            line = f"**{command}** command - **{count}** times"
            separator = 1 if current_parts else 0
            if current_length + separator + len(line) + len(header) > char_limit:
                pages.append("\n".join(current_parts))
                current_parts = [line]
                current_length = len(line)
            else:
                current_parts.append(line)
                current_length += separator + len(line)

        if current_parts:
            pages.append("\n".join(current_parts))

        embeds = [
            discord.Embed(title=f"{member.display_name}'s Dodo Stats", description=header + page, color=0x3498DB)
            for page in pages
        ]
        view = _Paginator(embeds) if len(embeds) > 1 else None
        await context.send(embed=embeds[0], view=view)

    @commands.hybrid_command(
        name="remind",
        description="Set yourself an alarm in minutes; Dodo will poke you in due time.",
        aliases=["alarm", "poke", "remember"],
    )
    @checks.not_blacklisted()
    async def reminder(self, context: Context, minutes: int, *, reminder_text: str) -> None:
        """Remind the caller of ``reminder_text`` after ``minutes`` minutes."""
        await context.send(f"Ok! I will remind you of this: '{reminder_text}' in {minutes} minute(s)!")
        await asyncio.sleep(minutes * 60)
        # Use the channel (not the interaction) so long delays don't hit the token expiry.
        await context.channel.send(
            f"Hey {context.author.mention}, you asked me to remind you of this: {reminder_text} :heart: :dodo: "
        )

    @commands.hybrid_command(name="schedule123", description="Sends you the current schedule in DMs.")
    @checks.not_blacklisted()
    async def schedule_dm(self, context: Context) -> None:
        """DM the caller the current weekly schedule (falls back to the channel)."""
        weekly_channel = self.bot.get_channel(config_py.WEEKLY_CHANNEL)
        schedule = await weekly_channel.fetch_message(config_py.WEEKLY_MESSAGE)
        try:
            await context.author.send(schedule.content)
            await context.send("I sent you our current schedule in a private message!")
        except discord.Forbidden:
            await context.send("I couldn't send you our schedule in DMs, so I will send it in here:")
            await context.send(schedule.content)

    @commands.hybrid_command(name="ping", description="Check if the bot is alive.")
    @checks.not_blacklisted()
    async def ping(self, context: Context) -> None:
        """Report the bot's gateway latency."""
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.bot.latency * 1000)}ms.",
            color=config_py.success,
        )
        await context.send(embed=embed)

    @commands.hybrid_command(name="invite", description="Get the bot's invite link (Fox only, for now).")
    @checks.not_blacklisted()
    async def invite(self, context: Context) -> None:
        """DM the caller the bot's invite link."""
        config = self.bot.config
        embed = discord.Embed(
            description=(
                "Invite me to your server by clicking "
                f"[here](https://discordapp.com/oauth2/authorize?&client_id={config['application_id']}"
                f"&scope=bot+applications.commands&permissions={config['permissions']}). "
                "Except it won't work if you're not Fox. For now."
            ),
            color=config_py.warning,
        )
        try:
            await context.author.send(embed=embed)
            await context.send("I sent you a private message!")
        except discord.Forbidden:
            await context.send(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))
