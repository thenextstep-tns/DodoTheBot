"""
DodoTheBot — entry point.

Defines the ``DodoBot`` client (a discord.py ``commands.Bot`` subclass), wires up
logging, loads every cog under ``cogs/``, syncs the application-command tree, and
registers the server-wide event listeners. Feature commands live in their own
cogs as hybrid commands (usable both as ``/slash`` and via a text prefix).
"""

import asyncio
import json
import os
import platform
import random
import sys
from datetime import date, datetime, timedelta

import requests

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config_py
import exceptions
import lang
from config.guild_config import GuildConfigManager
from helpers import messages
from helpers.logger import setup_logger
from helpers.state_machine import StateStore
from helpers.visibility import VisibilityManager
from helpers.command_sync import CommandSyncer
from helpers.lang_manager import LangManager
from helpers.parameters import ParamManager
from helpers.dodoland import parameters as dodoland_parameters
from helpers.dodoland.assets import AssetStore
from helpers.dodoland.buildings import BuildingStore
from helpers.dodoland.store import ActivityStore
from helpers.dodoland.towns import TownStore
from helpers.events import EventRuleManager
from helpers.chat.triggers import ChatTriggerManager
from helpers.chat.activity import ChatActivity
from helpers.panel_access import PanelAccessManager
from helpers.audit_notify import OwnerNotifier
from helpers.audit_log import AuditLog
from helpers.event_log import EventLogStore
from helpers.tribes import TribeManager
from helpers.trial_ranks import TrialRankManager
from helpers.health import HealthMonitor, SAMPLE_MINUTES
from helpers.share_tokens import ShareTokenStore

# --------------------------------------------------------------------------- #
#  Configuration & logging
# --------------------------------------------------------------------------- #
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
with open("config.json", encoding="utf-8") as file:
    config = json.load(file)

logger = setup_logger()

# Populated hourly from the WordPress guide API; consumed by the tag helpers below.
tag_dict: dict = {}


# --------------------------------------------------------------------------- #
#  Client
# --------------------------------------------------------------------------- #
def _build_intents() -> discord.Intents:
    """Intents the bot needs. ``message_content`` is required for prefix commands
    and for the message-scanning listeners to see message text."""
    intents = discord.Intents.default()
    intents.reactions = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    return intents


class DodoBot(commands.Bot):
    """The Dodo client."""

    def __init__(self) -> None:
        super().__init__(command_prefix=config["prefix"], intents=_build_intents(), help_command=None)
        self.logger = logger
        self.config = config
        # Per-guild settings (channel/role IDs, …), backed by MongoDB with the
        # config.guild constants as built-in defaults. Cogs and events read guild
        # settings via ``self.guild_config.get(guild_id, "KEY")``.
        self.guild_config = GuildConfigManager()
        # Mongo-backed persistence for in-progress interactive flows. Flows opt in
        # by registering a resume handler (see helpers/state_machine.py); every
        # still-active flow is auto-resumed once, from on_ready.
        self.state = StateStore(config_py.active_states, logger=logger)
        self._resumed = False
        # Per-guild, role-based command/cog visibility (managed from the control
        # panel). Enforced at runtime for every invocation path via the checks
        # registered below, and mirrored to Discord by helpers/command_sync.py.
        self.visibility = VisibilityManager(
            visibility_col=config_py.command_visibility,
            cog_state_col=config_py.cog_guild_state,
            guild_admins_col=config_py.guild_admins,
            feature_col=config_py.feature_state,
            owners=config.get("owners", []),
        )
        # Who may open the control panel for a guild, and how much of it (roles
        # and users can be granted a scope by the owner; see helpers/panel_access.py).
        self.panel_access = PanelAccessManager(config_py.panel_access, visibility=self.visibility)
        self.add_check(self._global_visibility_check)
        self.tree.interaction_check = self._app_visibility_check
        # Applies the visibility settings to each guild's slash picker (per-guild
        # command trees), on startup and live on config changes from the panel.
        self.command_syncer = CommandSyncer(self, hash_col=config_py.command_sync_hashes)
        self._synced = False
        # Editable user-facing strings: snapshots lang.py defaults and applies any
        # stored overrides onto the live module, so cogs' ``lang.KEY`` reads reflect
        # edits made from the control panel. Done here (before cogs load) so the
        # first use of any string already sees its override.
        self.lang = LangManager(lang, config_py.lang_overrides)
        # Per-server command parameters (thresholds, limits, role lists, …).
        # Cogs read via self.params.get(guild_id, "key"); edited from the panel.
        self.params = ParamManager(config_py.command_params)
        # DodoLand's own tunables and activity store, deliberately separate from
        # the general registry above so a server's town economy never appears
        # among the ordinary cog settings (the same split tabletop uses).
        self.dodoland_params = dodoland_parameters.manager()
        self.dodoland = ActivityStore(
            config_py.dodoland_activity, config_py.dodoland_pairs, self.dodoland_params
        )
        # The towns themselves: which buildings a server has, what feeds them,
        # and what a tier costs. Per-guild data, edited on the DodoLand page.
        self.dodoland_buildings = BuildingStore(config_py.dodoland_config)
        # Decor an admin uploads for people to place once they have earned it.
        self.dodoland_assets = AssetStore(config_py.dodoland_assets)
        # Names, descriptions and pictures. Authored by their owner,
        # and deliberately unable to move a single number.
        self.dodoland_towns = TownStore(config_py.dodoland_towns)
        # "When X happens, post this" rules built on the panel's Events page;
        # executed by the event_actions cog.
        self.event_rules = EventRuleManager(config_py.event_rules)
        # "When someone says X, react like this" — the chat cog's string
        # listeners, edited on the same Events page. Consulted on every message,
        # so it keeps compiled patterns cached per guild.
        self.chat_triggers = ChatTriggerManager(config_py.chat_triggers)
        # What the chat cog decided about recent messages, and why. In memory
        # only — the panel reads it from this same process.
        self.chat_activity = ChatActivity()
        # DMs the owner when a guild admin changes their server's config — those
        # changes now bind everyone, owners included (see helpers/visibility.py).
        # Durable record of every panel change (owner's included).
        self.audit_log = AuditLog(config_py.config_audit)
        # The other log: what Discord did, which the log cog has been writing
        # to Logs all along with nothing able to read it back.
        self.event_log = EventLogStore(config_py.logs)
        # Role rules ("tribes") built on the panel; applied hourly by cogs/tribes.py.
        self.tribes = TribeManager(config_py.tribes, config_py.tribe_members)
        # Trial ranking: clears/achievements -> points -> rank role.
        self.trial_ranks = TrialRankManager(
            config_py.trial_ranks, config_py.trial_standings,
            enrollment_collection=config_py.trial_enrollment,
            image_collection=config_py.trial_rank_images,
            interest_collection=config_py.trial_interest,
            preset_collection=config_py.trial_presets,
            wr_collection=config_py.trial_wr,
        )
        # Samples the gateway every few minutes so the dashboard can show what
        # was true, not just what is true right now.
        self.health = HealthMonitor(config_py.bot_health)
        # Capability links for the public leaderboard; hashes only.
        self.share_tokens = ShareTokenStore(config_py.share_tokens)
        self.audit_notify = OwnerNotifier(
            self, config.get("owners", []), panel_url=config_py.WEB_PUBLIC_URL
        )

    # ------------------------------------------------------------------ #
    #  Visibility enforcement (prefix/hybrid + slash)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _command_meta(command) -> "tuple[str, str | None]":
        """Top-level command name + owning cog name, keyed the way the panel stores them."""
        top = command.root_parent or command
        cog = getattr(command, "cog", None)
        return top.name, (cog.qualified_name if cog else None)

    async def _global_visibility_check(self, context: "commands.Context") -> bool:
        """Global check for prefix + hybrid-text invocations."""
        if context.command is None:
            return True
        name, cog = self._command_meta(context.command)
        has_manage = bool(
            context.guild and getattr(context.author, "guild_permissions", None)
            and context.author.guild_permissions.manage_guild
        )
        guild_id = context.guild.id if context.guild else None
        if not self.visibility.can_run(guild_id, context.author.id, name, cog, has_manage_guild=has_manage):
            raise exceptions.CommandHidden()
        return True

    async def _app_visibility_check(self, interaction: "discord.Interaction") -> bool:
        """``tree.interaction_check`` for slash/app-command invocations."""
        command = interaction.command
        # Only gate real application-command invocations (not autocomplete/components).
        if not isinstance(command, app_commands.Command):
            return True
        name = (command.root_parent or command).name
        cog = getattr(command, "binding", None)
        cog_name = cog.qualified_name if cog else None
        perms = getattr(interaction.user, "guild_permissions", None)
        has_manage = bool(interaction.guild_id and perms and perms.manage_guild)
        if not self.visibility.can_run(
            interaction.guild_id, interaction.user.id, name, cog_name, has_manage_guild=has_manage
        ):
            raise exceptions.CommandHidden()
        return True

    def guild_setting(self, guild: "discord.Guild | int | None", key: str):
        """Convenience: resolve a per-guild setting from a guild object or ID."""
        guild_id = guild.id if isinstance(guild, discord.Guild) else guild
        return self.guild_config.get(guild_id, key)

    async def get_prefix(self, message: "discord.Message"):
        """Per-server command prefix: a guild's ``command_prefix`` param if set,
        otherwise the default from config.json."""
        guild_id = message.guild.id if message.guild else None
        override = self.params.get(guild_id, "command_prefix")
        return override or self.config["prefix"]

    async def setup_hook(self) -> None:
        """Runs once before ``on_ready``: load cogs. Application commands are synced
        per-guild from ``on_ready`` (via ``command_syncer``), where ``self.guilds``
        is populated and each guild's tree can be computed from its visibility
        settings."""
        await self.load_all_cogs()

    async def load_all_cogs(self) -> None:
        """Recursively load every cog under ``cogs/``.

        Files that are plain helper modules (no ``setup`` function) are skipped
        quietly — only genuine load failures are logged as errors.
        """
        for root_dir, _dirs, files in os.walk("cogs"):
            for filename in files:
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                extension = os.path.join(root_dir, filename[:-3]).replace(os.sep, ".")
                try:
                    await self.load_extension(extension)
                    self.logger.info(f"Loaded cog '{extension}'")
                except commands.errors.NoEntryPointError:
                    self.logger.debug(f"Skipped non-cog module '{extension}'")
                except Exception as error:
                    self.logger.error(f"Failed to load cog '{extension}': {error}")


bot = DodoBot()


# --------------------------------------------------------------------------- #
#  Background tasks
# --------------------------------------------------------------------------- #
@tasks.loop(minutes=3.0)
async def status_task() -> None:
    """Rotate the bot's 'Playing …' status every few minutes."""
    await bot.change_presence(activity=discord.Game(random.choice(config_py.statuses)))


@tasks.loop(minutes=60.0)
async def api_import() -> None:
    """Refresh the guide-article tag lookup from the WordPress API hourly."""
    global tag_dict
    tag_dict = await get_tags_from_wordpress_api()
    bot.logger.info("Guide tag list updated successfully.")


@tasks.loop(minutes=SAMPLE_MINUTES)
async def health_sample() -> None:
    """One health sample: is the gateway up, how far behind, and how big is the bot."""
    latency = bot.latency
    # discord.py reports nan before the first heartbeat; that's "not measured
    # yet", not "instant".
    latency_ms = None if latency != latency else latency * 1000
    bot.health.record(
        latency_ms=latency_ms,
        connected=not bot.is_closed() and latency_ms is not None,
        guilds=len(bot.guilds),
        members=sum(g.member_count or 0 for g in bot.guilds),
    )


@health_sample.before_loop
async def before_health_sample() -> None:
    await bot.wait_until_ready()


@tasks.loop(hours=24)
async def check_reactions() -> None:
    """Ensure the configured reaction-role messages still carry the bot's reactions."""
    for message_id, reactions in config_py.reaction_roles.items():
        message = await _find_message(message_id)
        if not message:
            bot.logger.warning(f"Reaction-role message {message_id} not found in any channel.")
            continue
        for emoji in reactions:
            if not await _bot_already_reacted(message, emoji):
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException as error:
                    bot.logger.error(f"Failed to add reaction {emoji} to {message_id}: {error}")


async def _find_message(message_id: int):
    """Search every text channel the bot can see for a message by ID."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                return await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
    return None


async def _bot_already_reacted(message: discord.Message, emoji: str) -> bool:
    """Return whether the bot has already reacted to ``message`` with ``emoji``."""
    for reaction in message.reactions:
        if str(reaction.emoji) == emoji:
            users = [user async for user in reaction.users()]
            if bot.user in users:
                return True
    return False


# --------------------------------------------------------------------------- #
#  Lifecycle
# --------------------------------------------------------------------------- #
@bot.event
async def on_ready() -> None:
    """Log connection details and start the background tasks."""
    bot.logger.info(f"Logged in as {bot.user} (discord.py {discord.__version__})")
    bot.logger.info(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")
    if not status_task.is_running():
        status_task.start()
    if not api_import.is_running():
        api_import.start()
    if not check_reactions.is_running():
        check_reactions.start()
    if not health_sample.is_running():
        health_sample.start()
    # Apply per-guild command visibility to Discord's pickers. Guarded + hash-gated
    # so gateway reconnects and unchanged guilds don't trigger needless re-syncs.
    if not bot._synced:
        bot._synced = True
        await bot.command_syncer.sync_all()
    # Resume any interactive flows that were mid-play when the bot last stopped.
    # Guarded so gateway reconnects (which re-fire on_ready) don't re-resume.
    if not bot._resumed:
        bot._resumed = True
        await bot.state.resume_all(bot)


# --------------------------------------------------------------------------- #
#  Member events
# --------------------------------------------------------------------------- #
@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Handle a new (or returning) member joining.

    1. If they arrive already carrying the bot-trap role, ban immediately.
    2. Grant the configured starter roles.
    3. Restore saved roles from a previous membership (welcome-back) or post a
       first-time welcome.
    """
    settings = bot.guild_config.get_all(member.guild.id)
    try:
        trap_role_id = int(settings["TRAP_ROLE_ID"])
        if any(role.id == trap_role_id for role in member.roles):
            await handle_trap_trigger(member)
            return
    except (KeyError, TypeError, ValueError):
        pass

    starter_roles = [member.guild.get_role(rid) for rid in settings["starter_roles"]]
    starter_roles = [role for role in starter_roles if role is not None]
    if starter_roles:
        await member.add_roles(*starter_roles, reason="Automatic starter roles on join")

    # The welcome channel/text are editable per server from the control panel;
    # WAYSHRINE stays the fallback so servers that never set one keep working.
    channel = bot.get_channel(settings.get("WELCOME_CHANNEL") or settings["WAYSHRINE"])
    if not channel:
        return

    saved = config_py.left_roles.find_one({"_id": member.id})
    returning = bool(saved and "roles" in saved)
    if returning:
        restored = [member.guild.get_role(rid) for rid in saved["roles"]]
        restored = [role for role in restored if role is not None]
        if restored:
            await member.add_roles(*restored, reason="Restoring roles from previous membership")
        config_py.left_roles.delete_one({"_id": member.id})

    template = settings.get("WELCOME_BACK_MESSAGE" if returning else "WELCOME_MESSAGE")
    if template:
        await channel.send(
            messages.render_template(
                template,
                mention=member.mention,
                name=member.display_name,
                guild=member.guild.name,
                rank_req=f"<#{settings['RANK_REQ']}>",
                select_roles=f"<#{settings['SELECT_ROLES']}>",
            )
        )


@bot.event
async def on_member_remove(member: discord.Member) -> None:
    """Save a leaving member's roles so they can be restored if they return."""
    excluded_role_ids = set()
    for role_mapping in config_py.reaction_roles.values():
        excluded_role_ids.update(role_mapping.values())

    roles = [
        role.id
        for role in member.roles
        if role.id != member.guild.default_role.id and role.id not in excluded_role_ids
    ]
    config_py.left_roles.update_one({"_id": member.id}, {"$set": {"roles": roles}}, upsert=True)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """Catch users who gain the bot-trap role after joining (e.g. via onboarding)."""
    try:
        trap_role_id = int(bot.guild_config.get(after.guild.id, "TRAP_ROLE_ID"))
    except (TypeError, ValueError):
        return
    if not any(r.id == trap_role_id for r in before.roles) and any(r.id == trap_role_id for r in after.roles):
        await handle_trap_trigger(after)


# --------------------------------------------------------------------------- #
#  Message events
# --------------------------------------------------------------------------- #
@bot.event
async def on_message(message: discord.Message) -> None:
    """Main message listener: moderation, logging, fun reactions and command dispatch."""
    source_channel_id = 1109080900030955604  # ATG sign-up channel.
    mod_channel_id = 1113035754923368478  # Moderator notification channel.

    if message.channel.id == source_channel_id:
        if message.author.id != 824171812518494238:
            source_channel = bot.get_channel(source_channel_id)
            mod_channel = bot.get_channel(mod_channel_id)
            await mod_channel.send(
                f"**NEW ATG SIGN-UP from {source_channel.name}**\n"
                f"Author: {message.author.mention}\nContent: {message.content}"
            )
            await bot.process_commands(message)
        return

    # Restricted-content filtering now lives in the spam cog (mention_link_filter
    # feature) so it's per-server configurable and unified with the anti-spam.

    try:
        config_py.messages.insert_one(
            {
                "tag": "",
                "message": message.content,
                "intent": "",
                "author": message.author.id,
                "channel": message.channel.id,
                # Recorded for the panel's stats; older docs are scoped by channel
                # and dated from their ObjectId (see helpers/stats.py).
                "guild": message.guild.id if message.guild else None,
                "bot": message.author.bot,
            }
        )
    except Exception as error:
        bot.logger.error(f"Failed to archive message: {error}")

    # The phrase listeners that used to live here — "no u", the raid-signup
    # keywords, "support cat" — are chat triggers now (helpers/chat/triggers.py,
    # edited on the panel's Events page). They were unconditional, invisible and
    # unreachable from the panel, and the "no u" one fired *ahead* of the chat
    # cog's own banter trigger, so the tunable version never got a word in.

    if message.author.id in config_py.DODOLOVE:
        await message.add_reaction(random.choice(["❤️", "💖", "💕", "💞", "💘", "❣️"]))

    bot.logger.debug(f"{message.guild}: {message.channel}: {message.author}: {message.content}")

    # Everything Dodo says on her own initiative — answering a ping, reacting to
    # a phrase, or joining a conversation uninvited — is decided inside the chat
    # cog. This hook only hands it the message; see cogs/chat.py.
    await _dispatch_chat(message)

    await check_sweetroll_chance(message)
    await bot.process_commands(message)
    await check_tags(message)


async def _dispatch_chat(message: discord.Message) -> None:
    """Hand a message to the chat cog, if it is loaded.

    Wrapped because chat is the one listener that reaches an external API: a
    failure in it must never stop the rest of ``on_message`` (sweetrolls,
    commands, tags) from running.
    """
    cog = bot.get_cog("chat")
    if cog is None:
        return
    try:
        await cog.handle_message(message)
    except Exception as error:  # noqa: BLE001 - never break the gateway over chat
        bot.logger.exception(f"chat listener failed: {error}")


@bot.event
async def on_message_delete(message: discord.Message) -> None:
    """Log deleted messages to the audit channel."""
    guild_id = message.guild.id if message.guild else None
    channel = bot.get_channel(bot.guild_config.get(guild_id, "LOG_CHANNEL"))
    if not channel:
        return
    embed = discord.Embed(
        title=f"{message.author.display_name} just deleted a message in #{message.channel}",
        description=f"**{message.content}**",
        color=config_py.error,
    )
    embed.set_author(name="A message was deleted", icon_url=message.author.display_avatar)
    await channel.send(embed=embed)


# --------------------------------------------------------------------------- #
#  Reaction events
# --------------------------------------------------------------------------- #
@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None:
    """When an author reacts with 📖 to their own message, surface matching guide links."""
    if user.bot or str(reaction.emoji) != "\U0001F4D6":
        return
    message = reaction.message
    if message.guild is None or user != message.author:
        return

    context = await bot.get_context(message)
    tags = [tag for tag in tag_dict if tag.lower() in message.content.lower()]
    if not tags:
        await message.clear_reactions()
        return

    guide = bot.get_command("guide")
    if guide is None:
        return

    embed = discord.Embed(title="📚 Potentially helpful resources found!", color=discord.Color.brand_green())
    for tag in tags:
        try:
            links = await context.invoke(guide, tag=tag)
            if links:
                embed.add_field(
                    name=f"✨ {tag.capitalize()}",
                    value="\n".join(f"📖 [{title}]({url})" for title, url in links),
                    inline=False,
                )
        except Exception as error:
            bot.logger.error(f"Error invoking guide command for tag '{tag}': {error}")

    embed.set_footer(
        text="Hey there! We have articles on our website about the stuff mentioned above — maybe some of it helps! 💖"
    )
    await message.channel.send(embed=embed)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    """Grant a reaction-role when a tracked emoji is added."""
    if payload.message_id not in config_py.reaction_roles:
        return
    reaction_role_map = config_py.reaction_roles[payload.message_id]
    if str(payload.emoji) not in reaction_role_map:
        return
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    if payload.member:
        await add_role_to_user(payload.member, reaction_role_map[str(payload.emoji)], message)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
    """Remove a reaction-role when its tracked emoji is removed."""
    if payload.message_id not in config_py.reaction_roles:
        return
    reaction_role_map = config_py.reaction_roles[payload.message_id]
    if str(payload.emoji) not in reaction_role_map:
        return
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    member = message.guild.get_member(payload.user_id)
    if member:
        await remove_role_from_user(member, reaction_role_map[str(payload.emoji)], message)


# --------------------------------------------------------------------------- #
#  Command lifecycle & error handling
# --------------------------------------------------------------------------- #
@bot.event
async def on_command_completion(context: commands.Context) -> None:
    """Log every successful command (hybrid commands fire this for both slash and prefix)."""
    if context.command is None:
        return
    executed_command = context.command.qualified_name.split(" ")[0]
    config_py.commands_use.insert_one(
        {
            "Command": executed_command,
            "Guild": context.guild.name if context.guild else "DM",
            # Names change and repeat across servers; the id is what the panel filters on.
            "Guild ID": context.guild.id if context.guild else None,
            "Name": context.author.display_name,
            "User ID": context.author.id,
            "Date": date.today().isoformat(),
        }
    )
    channel = bot.get_channel(bot.guild_config.get(context.guild.id if context.guild else None, "LOG_CHANNEL"))
    if channel and context.guild:
        await channel.send(
            f"Executed {executed_command} command in {context.guild.name} "
            f"(ID: {context.guild.id}) by {context.author} (ID: {context.author.id})"
        )
    bot.logger.info(f"Executed {executed_command} by {context.author}")


@bot.event
async def on_command_error(context: commands.Context, error: commands.CommandError) -> None:
    """Friendly responses for common prefix / hybrid-text command errors."""
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, exceptions.CommandHidden):
        # Silently ignore hidden/disabled commands for prefix users — no error spam.
        return
    if isinstance(error, (exceptions.UserBlacklisted, exceptions.UserNotOwner)):
        await context.send(embed=discord.Embed(title="Error!", description=error.message, color=0xE02B2B))
    elif isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        parts = [
            f"{round(v)} {unit}"
            for v, unit in ((hours % 24, "hours"), (minutes, "minutes"), (seconds, "seconds"))
            if round(v)
        ]
        await context.send(
            embed=discord.Embed(
                title="Hey, please slow down!",
                description=f"You can use this command again in {' '.join(parts)}.",
                color=0xE02B2B,
            )
        )
    elif isinstance(error, commands.MissingPermissions):
        await context.send(
            embed=discord.Embed(
                title="Error!",
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to run this command!",
                color=0xE02B2B,
            )
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await context.send(embed=discord.Embed(title="Error!", description=str(error).capitalize(), color=0xE02B2B))
    else:
        raise error


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Friendly ephemeral responses for slash-command errors."""
    original = getattr(error, "original", error)
    if isinstance(original, (exceptions.UserBlacklisted, exceptions.UserNotOwner, exceptions.CommandHidden)):
        message = original.message
    elif isinstance(error, app_commands.MissingPermissions):
        message = "You are missing the permission(s) `" + ", ".join(error.missing_permissions) + "` to run this command!"
    else:
        bot.logger.error(f"Unhandled app command error: {error}")
        message = "Something went wrong running that command."

    embed = discord.Embed(title="Error!", description=message, color=0xE02B2B)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --------------------------------------------------------------------------- #
#  Shared helpers (moderation, roles, tags, sweetroll / pumpkin, trap)
# --------------------------------------------------------------------------- #
async def get_tags_from_wordpress_api() -> dict:
    """Fetch the guide article tag → link map from the WordPress API (paginated)."""
    api_url = "https://dodo.nextstep.team/wp-json/wp/v2/tags"
    tags: dict = {}
    page = 1
    while True:
        try:
            response = requests.get(api_url, params={"page": page})
            if response.status_code != 200:
                break
            batch = response.json()
            if not batch:
                break
            for tag in batch:
                tags[tag["name"]] = tag["link"]
            page += 1
        except Exception as error:
            bot.logger.warning(f"Could not fetch guide tags (page {page}): {error}")
            break
    return tags


async def check_tags(message: discord.Message) -> None:
    """Briefly react with 📖 to messages that mention a known guide tag."""
    if message.author == bot.user:
        return
    words = message.content.lower().split()
    reaction = "\U0001F4D6"
    reacted = False
    for tag in tag_dict:
        if tag.lower() in words:
            await message.add_reaction(reaction)
            reacted = True
    if reacted:
        await asyncio.sleep(5)
        await message.remove_reaction(reaction, bot.user)


async def add_role_to_user(member: discord.Member, role_id: int, message: discord.Message) -> None:
    """Add a reaction-role, log it, and (for the in-game guild role) ping moderators."""
    role = message.guild.get_role(role_id)
    if not role:
        return
    await member.add_roles(role)
    log_channel = bot.get_channel(bot.guild_config.get(message.guild.id, "E4D_ROLE_LOG"))
    await log_channel.send(f"Added {role.name} to {member.display_name} in {message.guild.name}.")
    if role_id == 807064226697969686:  # In-game guild role.
        moderators_channel = bot.get_channel(1060472908188749904)
        await moderators_channel.send(
            f"{member.display_name} added the in-game guild role to themselves. "
            f"Please invite them to the guild in-game."
        )
    temp_message = await message.channel.send(f"{member.display_name}, I've given you the {role.name} role.")
    await asyncio.sleep(5)
    await temp_message.delete()


async def remove_role_from_user(member: discord.Member, role_id: int, message: discord.Message) -> None:
    """Remove a reaction-role and log it."""
    role = message.guild.get_role(role_id)
    if not role:
        return
    await member.remove_roles(role)
    log_channel = bot.get_channel(bot.guild_config.get(message.guild.id, "E4D_ROLE_LOG"))
    await log_channel.send(f"Removed {role.name} from {member.display_name} in {message.guild.name}.")
    temp_message = await message.channel.send(f"The {role.name} role has been removed from you, {member.display_name}.")
    await asyncio.sleep(5)
    await temp_message.delete()


async def remove_role_later(member: discord.Member, role: discord.Role) -> None:
    """Remove ``role`` from ``member`` after one hour (non-persistent across restarts)."""
    await asyncio.sleep(3600)
    try:
        if role in member.roles:
            await member.remove_roles(role)
    except discord.HTTPException:
        pass


async def run_pumpkin_game(
    channel: discord.TextChannel, original_message: discord.Message, discoverer: discord.User, bot: "DodoBot", config_py
) -> None:
    """Run the cooperative 'pull the giant pumpkin' minigame."""
    pumpkins = config_py.pumpkins
    pull_collection = config_py.pull
    guild = original_message.guild
    if not guild:
        return
    guild_id = guild.id

    # Per-server tunables.
    strength_start = bot.params.get(guild_id, "pumpkin_strength_start")
    strength_gain = bot.params.get(guild_id, "pumpkin_strength_gain")
    role_threshold = bot.params.get(guild_id, "pumpkin_role_threshold")
    PUMPKIN_ROLE_ID = bot.params.get(guild_id, "pumpkin_role_id")

    weight = random.randint(
        bot.params.get(guild_id, "pumpkin_weight_min"), bot.params.get(guild_id, "pumpkin_weight_max")
    )
    explosion_time = datetime.now() + timedelta(minutes=weight / 8)

    discoverer_data = pull_collection.find_one({"_id": discoverer.id})
    base_strength = discoverer_data.get("strength", strength_start) if discoverer_data else strength_start
    pullers = {discoverer.id: base_strength}
    total_strength = base_strength

    GAME_EMOJI = "\U0001F383"

    embed = discord.Embed(
        title="🎃 A GIANT PUMPKIN APPEARS! 🎃",
        description=(
            "A massive pumpkin just burst from the ground! It looks unstable...\n"
            "React with 🎃 to help pull it out before it explodes!"
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Discovered by", value=discoverer.mention, inline=False)
    embed.add_field(name="🎃 Weight", value=f"**{weight} kg**", inline=True)
    embed.add_field(name="Total Strength", value=f"**{total_strength} kg**", inline=True)
    embed.add_field(name="💥 Explodes in", value=f"<t:{int(explosion_time.timestamp())}:R>", inline=True)
    embed.add_field(name="Pullers", value=f"{discoverer.mention}: {pullers[discoverer.id]}kg", inline=False)
    embed.set_footer(text="React to pull! Your strength is saved from previous pulls and grows over time!")

    game_message = await original_message.channel.send(embed=embed)
    await game_message.add_reaction(GAME_EMOJI)
    try:
        await original_message.remove_reaction(GAME_EMOJI, bot.user)
    except discord.HTTPException:
        pass

    while datetime.now() < explosion_time:
        remaining_time = (explosion_time - datetime.now()).total_seconds()
        if remaining_time <= 0:
            break
        try:
            reaction, user = await bot.wait_for(
                "reaction_add",
                timeout=remaining_time,
                check=lambda r, u: str(r.emoji) == GAME_EMOJI and u.id != bot.user and r.message.id == game_message.id,
            )
            if user.id not in pullers:
                user_data = pull_collection.find_one({"_id": user.id})
                pullers[user.id] = user_data.get("strength", strength_start) if user_data else strength_start
                total_strength = sum(pullers.values())
                puller_list = "\n".join(f"<@{uid}>: {strength}kg" for uid, strength in pullers.items())
                embed.set_field_at(2, name="Total Strength", value=f"**{total_strength} kg**", inline=True)
                embed.set_field_at(4, name=f"Pullers ({len(pullers)})", value=puller_list, inline=False)
                await game_message.edit(embed=embed)

            if total_strength >= weight:
                reward_per_person = round(weight / len(pullers))
                win_embed = discord.Embed(
                    title="🎃 SUCCESS! 🎃",
                    description=f"You did it! The **{weight}kg** pumpkin was pulled from the ground!",
                    color=discord.Color.green(),
                )
                win_embed.add_field(name="Total Pullers", value=str(len(pullers)), inline=True)
                win_embed.add_field(name="Reward Each", value=f"**{reward_per_person} kg** of pumpkin!", inline=True)
                win_embed.set_footer(text="Your pumpkin stats and pull strength (+5kg!) have been updated.")
                await game_message.edit(embed=win_embed)
                await game_message.clear_reactions()

                for user_id, current_strength in pullers.items():
                    pull_collection.update_one(
                        {"_id": user_id},
                        {"$set": {"strength": current_strength + strength_gain, "last_pull": datetime.now()}},
                        upsert=True,
                    )
                    pumpkins.insert_one(
                        {"collector": user_id, "date": datetime.now(), "weight_collected": reward_per_person}
                    )
                    if pumpkins.count_documents({"collector": user_id}) >= role_threshold:
                        try:
                            role = guild.get_role(PUMPKIN_ROLE_ID)
                            member = await guild.fetch_member(user_id)
                            if role and member and role not in member.roles:
                                await member.add_roles(role)
                                await channel.send(
                                    f"**Wow!** <@{user_id}> has collected 50 pumpkins and earned the **{role.name}** role!"
                                )
                        except discord.Forbidden:
                            await channel.send(f"I tried to give <@{user_id}> the pumpkin role, but I don't have permissions!")
                        except Exception as error:
                            bot.logger.error(f"Error adding pumpkin role: {error}")
                return
        except asyncio.TimeoutError:
            break

    if total_strength < weight:
        explode_embed = discord.Embed(
            title="💥 BOOOOOOM! 💥",
            description=(
                f"Oh no! The **{weight}kg** pumpkin was too strong!\n"
                f"It exploded, covering everyone in pumpkin guts!"
            ),
            color=discord.Color.red(),
        )
        explode_embed.add_field(
            name="Covered in Guts", value="\n".join(f"<@{uid}>" for uid in pullers) or "Nobody...", inline=False
        )
        explode_embed.set_footer(text="You've... earned a temporary role. Your strength (+5kg!) has been saved.")
        await game_message.edit(embed=explode_embed)
        await game_message.clear_reactions()

        for user_id, current_strength in pullers.items():
            pull_collection.update_one(
                {"_id": user_id},
                {"$set": {"strength": current_strength + strength_gain, "last_pull": datetime.now()}},
                upsert=True,
            )

        role_to_give = guild.get_role(PUMPKIN_ROLE_ID)
        if role_to_give:
            for user_id in pullers:
                try:
                    member = await guild.fetch_member(user_id)
                    if role_to_give not in member.roles:
                        await member.add_roles(role_to_give)
                        bot.loop.create_task(remove_role_later(member, role_to_give))
                except discord.Forbidden:
                    await channel.send(f"I tried to give <@{user_id}> the sticky pumpkin role, but I don't have permissions!")
                except Exception as error:
                    bot.logger.error(f"Error adding temporary pumpkin role: {error}")


async def _run_sweetroll_event(message, sweetrolls, pumpkins, channel, spawn_emoji, is_rhubarb, is_pumpkin) -> None:
    """Run a single sweetroll / rhubarb / pumpkin spawn as a non-blocking task."""
    try:
        await message.add_reaction(spawn_emoji)

        def check(reaction, user):
            return user != bot.user and str(reaction.emoji) == spawn_emoji

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=config_py.SWEETROLL_COOLDOWN, check=check)

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
                    "You taste betrayal seasoned with sourness—chef's kiss of misfortune.",
                ]
                await channel.send(
                    f"{user.mention} picked up the sweetroll, but it **BETRAYED** them! {random.choice(rhubarb_messages)}"
                )
                sweetrolls.insert_one({"victim": user.id, "date": datetime.now(), "rhubarb": 1})
                await message.remove_reaction(spawn_emoji, bot.user)
                return

            if is_pumpkin:
                await run_pumpkin_game(channel, message, user, bot, config_py)
                return

            if user and user.id == message.author.id:
                await channel.send(
                    "A sweetroll fell out but the owner picked it up before anyone else could! Great job! :cupcake:"
                )
                await message.remove_reaction(spawn_emoji, bot.user)
                return

            if user and user.id != message.author.id:
                if message.author.id in config_py.SWEETROLLAMULET:
                    if random.randint(1, 100) <= 98:
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
                        await message.remove_reaction(spawn_emoji, bot.user)
                        return
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
                        {"stolen_from": message.author.id, "thief": user.id, "date": datetime.now(), "golden": 1}
                    )
                    golden_count = sweetrolls.count_documents({"thief": user.id, "golden": 1})
                    await channel.send(
                        f"{random.choice(golden_messages)} {user.mention} now has {golden_count} golden sweetroll(s)!"
                    )
                    await message.remove_reaction(spawn_emoji, bot.user)
                    return

                target_is_ghost = message.author.id == 305162419733397505
                target_name = "Ghost" if target_is_ghost else message.author.mention
                if random.randint(1, 100) < config_py.SWEETROLL_GIFTING:
                    sweetrolls.insert_one({"stolen_from": message.author.id, "thief": user.id, "date": datetime.now()})
                    await message.remove_reaction(spawn_emoji, bot.user)
                    await channel.send(f"{user.mention} just stole the sweetroll from {target_name}!")
                else:
                    sweetrolls.insert_one({"gifted_to": message.author.id, "gifter": user.id, "date": datetime.now()})
                    await message.remove_reaction(spawn_emoji, bot.user)
                    await channel.send(f"{user.mention} suddenly gifted a sweetroll to {target_name}! Extreme generosity!")

        except asyncio.TimeoutError:
            try:
                await message.remove_reaction(spawn_emoji, bot.user)
            except discord.HTTPException:
                pass
    except Exception as error:
        bot.logger.error(f"Error in sweetroll event: {error}")
        try:
            await message.remove_reaction(spawn_emoji, bot.user)
        except discord.HTTPException:
            pass


async def check_sweetroll_chance(message: discord.Message) -> None:
    """Roll for a sweetroll/rhubarb/pumpkin spawn and, if it hits, launch the event."""
    guild_id = message.guild.id if message.guild else None
    channel = bot.get_channel(bot.guild_config.get(guild_id, "PET_CHANNEL"))
    if not channel or random.randint(1, 100) <= config_py.SWEETROLL_NEEDED:
        return

    is_rhubarb = random.randint(1, 1000) >= 995
    # Pumpkins are now extremely rare: only a roll of 99 or 100 spawns one.
    is_pumpkin = not is_rhubarb and random.randint(1, 100) >= 99
    spawn_emoji = "\U0001F383" if is_pumpkin else "\U0001F9C1"

    asyncio.create_task(
        _run_sweetroll_event(
            message, config_py.sweetrolls, config_py.pumpkins, channel, spawn_emoji, is_rhubarb, is_pumpkin
        )
    )


async def handle_trap_trigger(member: discord.Member) -> None:
    """Ban a member who took the bot-trap role, alert admins, and allow a reaction-undo."""
    try:
        settings = bot.guild_config.get_all(member.guild.id)
        alert_channel_id = int(settings["ALERT_CHANNEL_ID"])
        ban_emoji = settings["BAN_EMOJI"]
        check_emoji = getattr(config_py, "CHECK_EMOJI", "✅")
        wait_duration = config_py.WAIT_DURATION
    except (KeyError, TypeError, ValueError) as error:
        bot.logger.warning(f"Missing trap-listener config: {error}")
        return

    guild = member.guild
    alert_channel = guild.get_channel(alert_channel_id)
    if not alert_channel:
        bot.logger.error(f"Trap alert channel {alert_channel_id} not found in {guild.name}")
        return

    try:
        await guild.ban(member, reason="Triggered bot trap role")
        bot.logger.info(f"Banned {member} (ID: {member.id}) for triggering the trap role.")
    except discord.Forbidden:
        await alert_channel.send(
            f"⚠️ I caught {member.mention} triggering the trap role, but I lack permissions to ban them!"
        )
        return
    except discord.HTTPException as error:
        bot.logger.error(f"HTTP error while banning trap trigger: {error}")
        return

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
            and str(reaction.emoji) in (str(ban_emoji), str(check_emoji))
            and not user.bot
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=wait_duration, check=check)
        try:
            await alert_message.clear_reactions()
        except (discord.Forbidden, discord.NotFound):
            pass

        if str(reaction.emoji) == str(check_emoji):
            try:
                await guild.unban(member, reason=f"Ban cancelled by {user.display_name}")
                await alert_channel.send(
                    f"✅ Ban revoked for **{member.name}** by {user.mention}.\n"
                    f"*Note: they were removed from the server and will need a new invite to rejoin.*"
                )
            except discord.Forbidden:
                await alert_channel.send(
                    f"⚠️ I don't have permission to unban {member.name}! {user.mention}, please do it manually."
                )
        else:
            await alert_channel.send(f"🔒 Ban confirmed for **{member.name}** by {user.mention}.")
    except asyncio.TimeoutError:
        try:
            await alert_message.clear_reactions()
        except (discord.Forbidden, discord.NotFound):
            pass


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Enforce a single instance: kill any other process running this script or
    # holding the control-panel port before we connect (avoids a duplicate gateway
    # login and "address already in use" on the in-process web panel).
    from helpers.singleton import terminate_duplicates

    terminate_duplicates(script_marker="bot.py", port=config_py.WEB_PORT, logger=logger)
    bot.run(config["token"])
