"""
Owner cog — bot-management commands restricted to the owners listed in
``config.json`` (shutdown, command-tree sync, per-cog reloads, bulk role removal,
add-on info and the blacklist). All commands are hybrid and marked ``hidden`` so
they never show up in the ``/commands`` listing for non-owners (see
``cogs/general.py``).

Owner-only *visibility* in Discord's slash picker is handled by the unified
visibility system: these commands are ``hidden=True``, which the per-guild command
sync (``helpers/command_sync.py``) treats as owner-level and omits from every
guild picker. The runtime ``@checks.is_owner()`` on every command is the actual
enforcement; owners invoke these via prefix or the control panel.
"""

import json
import os

import discord
from discord import app_commands
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


def _extension_name(cog: str) -> str:
    """Normalise a user-supplied cog name to its dotted extension path.

    Accepts ``cheese`` or the already-qualified ``cogs.cheese``.
    """
    cog = cog.strip().replace("/", ".").replace("\\", ".")
    return cog if cog.startswith("cogs.") else f"cogs.{cog}"


def _discover_extensions() -> list[str]:
    """Every loadable extension path under ``cogs/`` (mirrors bot.load_all_cogs)."""
    found: list[str] = []
    for root_dir, _dirs, files in os.walk("cogs"):
        for filename in files:
            if not filename.endswith(".py") or filename.startswith("__"):
                continue
            found.append(os.path.join(root_dir, filename[:-3]).replace(os.sep, "."))
    return sorted(found)


class Owner(commands.Cog, name="owner"):
    """Owner-only bot management."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #
    def _cog_choices(self, current: str) -> list["app_commands.Choice"]:
        """Autocomplete choices: loaded cog names (short form) matching ``current``."""
        names = sorted(name[len("cogs."):] for name in self.bot.extensions)
        return [
            app_commands.Choice(name=name, value=name)
            for name in names
            if current.lower() in name.lower()
        ][:25]

    @commands.hybrid_command(name="kill", description="Shut the bot down (owner only).", hidden=True)
    @checks.is_owner()
    async def shutdown(self, context: Context) -> None:
        """Gracefully shut the bot down."""
        await context.send(embed=discord.Embed(description=lang.OWNER_SHUTDOWN, color=_ACCENT))
        await self.bot.close()

    @commands.hybrid_command(name="sync", description="Re-sync the slash-command tree (owner only).", hidden=True)
    @checks.is_owner()
    async def sync(self, context: Context) -> None:
        """Re-apply per-guild command visibility to every guild's slash picker."""
        if context.interaction:
            await context.defer(ephemeral=True)
        await self.bot.command_syncer.sync_all(force=True)
        await context.send(lang.OWNER_SYNCED.format(count=len(self.bot.guilds)))

    # ------------------------------------------------------------------ #
    #  Per-cog lifecycle
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="reload", description="Reload a single cog (owner only).", hidden=True)
    @app_commands.describe(cog="The cog to reload, e.g. 'cheese'.")
    @checks.is_owner()
    async def reload(self, context: Context, *, cog: str) -> None:
        """Reload one cog without restarting the bot."""
        extension = _extension_name(cog)
        try:
            await self.bot.reload_extension(extension)
        except commands.ExtensionNotLoaded:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NOT_LOADED.format(cog=cog), color=_ERROR))
        except commands.ExtensionNotFound:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NOT_FOUND.format(cog=cog), color=_ERROR))
        except Exception as error:  # noqa: BLE001 — surface any load-time error to the owner
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_ERROR.format(cog=cog, error=error), color=_ERROR))
        else:
            await context.send(embed=discord.Embed(description=lang.OWNER_RELOAD_DONE.format(cog=extension), color=_ACCENT))

    @commands.hybrid_command(name="load", description="Load a cog that isn't loaded (owner only).", hidden=True)
    @app_commands.describe(cog="The cog to load, e.g. 'cheese'.")
    @checks.is_owner()
    async def load(self, context: Context, *, cog: str) -> None:
        """Load a cog that isn't currently loaded."""
        extension = _extension_name(cog)
        try:
            await self.bot.load_extension(extension)
        except commands.ExtensionAlreadyLoaded:
            await context.send(embed=discord.Embed(description=lang.OWNER_RELOAD_DONE.format(cog=extension), color=_ACCENT))
        except commands.ExtensionNotFound:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NOT_FOUND.format(cog=cog), color=_ERROR))
        except commands.NoEntryPointError:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NO_ENTRY.format(cog=cog), color=_ERROR))
        except Exception as error:  # noqa: BLE001
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_ERROR.format(cog=cog, error=error), color=_ERROR))
        else:
            await context.send(embed=discord.Embed(description=lang.OWNER_LOAD_DONE.format(cog=extension), color=_ACCENT))

    @commands.hybrid_command(name="unload", description="Unload a loaded cog (owner only).", hidden=True)
    @app_commands.describe(cog="The cog to unload, e.g. 'cheese'.")
    @checks.is_owner()
    async def unload(self, context: Context, *, cog: str) -> None:
        """Unload a currently loaded cog."""
        extension = _extension_name(cog)
        if extension == f"cogs.{self.__cog_name__}" or extension.endswith(".owner"):
            await context.send(embed=discord.Embed(description=lang.OWNER_UNLOAD_SELF, color=_ERROR))
            return
        try:
            await self.bot.unload_extension(extension)
        except commands.ExtensionNotLoaded:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NOT_LOADED.format(cog=cog), color=_ERROR))
        except commands.ExtensionNotFound:
            await context.send(embed=discord.Embed(description=lang.OWNER_COG_NOT_FOUND.format(cog=cog), color=_ERROR))
        else:
            await context.send(embed=discord.Embed(description=lang.OWNER_UNLOAD_DONE.format(cog=extension), color=_ACCENT))

    @commands.hybrid_command(name="reloadall", description="Reload every loaded cog (owner only).", hidden=True)
    @checks.is_owner()
    async def reloadall(self, context: Context) -> None:
        """Reload every currently loaded cog, reporting per-cog success/failure."""
        extensions = sorted(self.bot.extensions)
        lines: list[str] = []
        ok = 0
        for extension in extensions:
            try:
                await self.bot.reload_extension(extension)
            except Exception as error:  # noqa: BLE001
                lines.append(f"❌ `{extension}` — {error}")
            else:
                ok += 1
                lines.append(f"✅ `{extension}`")
        embed = discord.Embed(
            title=lang.OWNER_RELOADALL_TITLE.format(ok=ok, total=len(extensions)),
            description="\n".join(lines) or "No cogs are loaded.",
            color=_ACCENT if ok == len(extensions) else _ERROR,
        )
        await context.send(embed=embed)

    # Autocomplete the cog name for the lifecycle commands (slash only). Defined as
    # cog methods so discord.py passes ``self`` when resolving choices.
    @reload.autocomplete("cog")
    async def _reload_cog_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._cog_choices(current)

    @unload.autocomplete("cog")
    async def _unload_cog_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._cog_choices(current)

    @load.autocomplete("cog")
    async def _load_cog_autocomplete(self, interaction: discord.Interaction, current: str):
        """Suggest on-disk cogs that aren't currently loaded."""
        loaded = set(self.bot.extensions)
        names = sorted(name[len("cogs."):] for name in _discover_extensions() if name not in loaded)
        return [
            app_commands.Choice(name=name, value=name)
            for name in names
            if current.lower() in name.lower()
        ][:25]

    @commands.hybrid_command(name="cleanrole", description="Remove a role from every member who has it (owner only).", hidden=True)
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

    @commands.hybrid_command(name="addons", description="Show the add-ons we recommend.", hidden=True)
    @checks.is_owner()
    async def addons(self, context: Context) -> None:
        """Post the recommended add-ons link/image."""
        embed = discord.Embed(title=lang.OWNER_ADDONS_TITLE, description=lang.OWNER_ADDONS_URL)
        embed.set_image(url=lang.OWNER_ADDONS_IMAGE)
        await context.send(embed=embed)

    @commands.hybrid_group(name="blacklist", fallback="list", description="Manage the bot blacklist.", hidden=True)
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
