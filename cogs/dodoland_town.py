"""
``/town`` — the only thing about DodoLand a player ever touches.

**One grouped command, deliberately.** Discord caps an application at 100
top-level slash commands and this bot sits at the safe ceiling, so every
subcommand added here costs nothing while a second top-level command would cost
the last slot in the bot.

Two subcommands:

``/town`` shows where somebody stands: their buildings, what tier each has
reached, their standing, and the flourish their trial rank earns them.

``/town settle`` hands them a private link to pick where they live. The link is
a per-person capability token, so it names exactly one person and its only power
is to move that person's town. Choosing where you live is most of the fun, which
is why it is a player action and not something an admin does to people.

Everything is ephemeral. The point of DodoLand is a map worth looking at, not a
channel full of bot output.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from helpers import share_tokens
from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import standing
from helpers.dodoland import store as store_module

# How long a settle link lives. Long enough to come back to it after a week,
# short enough that a link pasted somewhere public stops working.
LINK_TTL_DAYS = 14


class Town(commands.Cog, name="dodoland_town"):
    """A player's own view of their town."""

    def __init__(self, bot):
        self.bot = bot

    town = app_commands.Group(name="town", description="Your settlement in DodoLand.")

    # ------------------------------------------------------------------ #
    #  Shared
    # ------------------------------------------------------------------ #
    def _standing_for(self, guild, user_id: int) -> tuple[dict, dict]:
        """That person's row and the resolved tiers. Blocking; call in a thread."""
        buildings = self.bot.dodoland_buildings.buildings(guild.id)
        window = int(self.bot.dodoland_params.get(guild.id, "dodoland_window_days"))
        result = standing.guild_standings(
            self.bot.dodoland, self.bot.dodoland_params, guild.id, buildings,
            since=store_module.days_back(window),
        )
        return result, result["people"].get(int(user_id)) or {}

    # ------------------------------------------------------------------ #
    #  /town
    # ------------------------------------------------------------------ #
    @town.command(name="profile", description="See a town: yours, or somebody else's.")
    @app_commands.describe(member="Whose town to look at. Yours if left blank.")
    async def profile(self, interaction: discord.Interaction,
                      member: discord.Member | None = None) -> None:
        # Scoring reads the whole guild's rows, which does not fit in Discord's
        # three seconds, so acknowledge before doing any of it.
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("DodoLand only exists on a server.")
            return

        who = member or interaction.user
        result, person = await self.bot.loop.run_in_executor(
            None, self._standing_for, guild, who.id
        )
        glow = (await self.bot.loop.run_in_executor(
            None, flourish_rules.flourish_map, self.bot, guild.id
        )).get(who.id) or flourish_rules.BLANK

        if not person:
            await interaction.followup.send(
                f"{who.display_name} has no town yet. It appears as soon as they "
                "have taken part somewhere DodoLand is watching."
            )
            return

        embed = discord.Embed(
            title=f"\U0001F3D8 The settlement of {who.display_name}",
            colour=discord.Colour.from_str("#8b5a2b"),
        )
        embed.set_thumbnail(url=who.display_avatar.url)
        embed.add_field(
            name="Standing",
            value=(f"**{person['power']:,}** town power\n"
                   f"#{person['place']} of {len(result['people'])}\n"
                   f"{person['reached']:,} people reached"),
            inline=True,
        )
        if glow["level"]:
            embed.add_field(
                name="Flourish",
                value=(f"**{glow['label']}**\n{glow['description']}\n"
                       + (f"from {glow['rank_name']}" if glow["rank_name"] else "")),
                inline=True,
            )

        built = []
        for score in person["buildings"].values():
            icon = score.get("icon") or ""
            if score.get("tier") is None:
                built.append(f"{icon} {score['name']}: not started")
            else:
                built.append(f"{icon} {score['name']}: **{score['tier_title']}** "
                             f"({score['points']:,})")
        embed.add_field(name="What stands there", value="\n".join(built) or "Nothing yet.",
                        inline=False)
        embed.set_footer(text="Buildings come from taking part. Flourish comes from your rank.")
        await interaction.followup.send(embed=embed)

    @town.command(name="settle", description="Choose where on the map your town sits.")
    async def settle(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "DodoLand only exists on a server.", ephemeral=True)
            return
        if not self.bot.dodoland_buildings.map_image(guild.id):
            await interaction.response.send_message(
                "This server has no map yet. An admin needs to upload one first.",
                ephemeral=True)
            return

        token = self.bot.share_tokens.issue(
            guild.id, kind=share_tokens.KIND_USER, user_id=interaction.user.id,
            ttl_days=LINK_TTL_DAYS,
        )
        if not token:
            await interaction.response.send_message(
                "Links are not available right now. Try again later.", ephemeral=True)
            return

        base = (self.bot.dodoland_params.get(guild.id, "dodoland_public_base_url")
                or "").rstrip("/")
        link = f"{base}/t/{guild.id}/{token}" if base else f"/t/{guild.id}/{token}"
        embed = discord.Embed(
            title="\U0001F5FA Choose where you live",
            description=(
                f"[Open the map]({link})\n\n"
                "Click anywhere to put your town there. You can move it as often "
                "as you like, and where you build never changes what you have "
                "earned.\n\n"
                f"This link is yours alone and lasts {LINK_TTL_DAYS} days. Anyone "
                "you give it to could move your town, so keep it to yourself."
            ),
            colour=discord.Colour.from_str("#8b5a2b"),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Town(bot))
