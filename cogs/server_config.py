"""
Server-config cog — lets a server's admins view and override the per-guild
settings (channel IDs, role IDs, starter-role lists, …) that used to be baked
into ``config.guild`` for the single ESO for Dodos server.

Settings are stored and merged by ``config.guild_config.GuildConfigManager``
(exposed as ``bot.guild_config``); this cog is just the user-facing surface.
All commands are hybrid and require the *Manage Server* permission. User-facing
text lives in ``lang``.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

import lang
from config.guild_config import MANAGED_KEYS

# How each managed key is parsed/displayed. Everything not listed is a single
# channel/role ID (a whole number).
_LIST_KEYS = {"starter_roles", "allowed_roles", "public_channels", "boss_spawn_channels"}
_EMOJI_KEYS = {"BAN_EMOJI", "SALUTE_EMOJI"}


class ServerConfig(commands.Cog, name="server_config"):
    """View and edit this server's Dodo settings."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(
        name="serverconfig",
        fallback="view",
        description="View this server's Dodo settings.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def serverconfig(self, context: Context) -> None:
        """Show every managed setting, flagging which are customised vs default."""
        settings = self.bot.guild_config.get_all(context.guild.id)
        lines = []
        for key in MANAGED_KEYS:
            marker = "●" if self.bot.guild_config.is_overridden(context.guild.id, key) else "○"
            lines.append(f"{marker} `{key}` = `{self._format(key, settings.get(key))}`")

        embed = discord.Embed(
            title=lang.SERVERCONFIG_VIEW_TITLE.format(guild=context.guild.name),
            description="\n".join(lines),
            color=0x9C84EF,
        )
        embed.set_footer(text=lang.SERVERCONFIG_VIEW_FOOTER)
        await context.send(embed=embed, ephemeral=True)

    @serverconfig.command(name="set", description="Override one setting for this server.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @app_commands.describe(key="The setting to change.", value="The new value (an ID, list of IDs, or emoji).")
    async def set_setting(self, context: Context, key: str, *, value: str) -> None:
        """Parse and store an override for ``key``."""
        if key not in MANAGED_KEYS:
            await context.send(lang.SERVERCONFIG_UNKNOWN_KEY.format(key=key), ephemeral=True)
            return

        parsed, expected = self._parse(key, value)
        if parsed is None:
            await context.send(lang.SERVERCONFIG_BAD_VALUE.format(value=value, key=key, expected=expected), ephemeral=True)
            return

        self.bot.guild_config.set(context.guild.id, key, parsed)
        await context.send(lang.SERVERCONFIG_SET_OK.format(key=key, value=self._format(key, parsed)), ephemeral=True)

    @serverconfig.command(name="reset", description="Revert one setting to its default for this server.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @app_commands.describe(key="The setting to reset to its built-in default.")
    async def reset_setting(self, context: Context, key: str) -> None:
        """Drop the stored override for ``key`` so it reverts to the default."""
        if key not in MANAGED_KEYS:
            await context.send(lang.SERVERCONFIG_UNKNOWN_KEY.format(key=key), ephemeral=True)
            return

        was_overridden = self.bot.guild_config.is_overridden(context.guild.id, key)
        self.bot.guild_config.reset(context.guild.id, key)
        default_value = self._format(key, self.bot.guild_config.get(context.guild.id, key))
        template = lang.SERVERCONFIG_RESET_OK if was_overridden else lang.SERVERCONFIG_RESET_NOOP
        await context.send(template.format(key=key, value=default_value), ephemeral=True)

    @set_setting.autocomplete("key")
    @reset_setting.autocomplete("key")
    async def key_autocomplete(self, interaction: discord.Interaction, current: str):
        """Suggest managed keys matching what the admin has typed so far."""
        current = current.lower()
        return [
            app_commands.Choice(name=key, value=key)
            for key in MANAGED_KEYS
            if current in key.lower()
        ][:25]

    # ------------------------------------------------------------------ #
    #  Value parsing / formatting
    # ------------------------------------------------------------------ #
    def _parse(self, key: str, value: str):
        """Parse ``value`` for ``key``. Returns ``(parsed, None)`` or ``(None, expected)``."""
        if key in _EMOJI_KEYS:
            text = value.strip()
            return (text, None) if text else (None, lang.SERVERCONFIG_EXPECT_EMOJI)

        if key in _LIST_KEYS:
            tokens = [tok for tok in value.replace(",", " ").split() if tok]
            try:
                return [int(tok) for tok in tokens], None
            except ValueError:
                return None, lang.SERVERCONFIG_EXPECT_ID_LIST

        try:
            return int(value.strip()), None
        except ValueError:
            return None, lang.SERVERCONFIG_EXPECT_ID

    def _format(self, key: str, value) -> str:
        """Render a stored value compactly for display."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) if value else "(empty)"
        return str(value)


async def setup(bot):
    await bot.add_cog(ServerConfig(bot))
