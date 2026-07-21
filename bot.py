"""
DodoTheBot — entry point.

Defines the ``DodoBot`` client (a ``commands.Bot`` subclass), wires up logging,
loads every cog under ``cogs/``, registers the global event handlers, and starts
the bot. Feature commands live in their own cogs; this file only holds the
client, the shared background tasks, and the server-wide event listeners.
"""

import asyncio
import json
import os
import platform
import random
import sys
from datetime import date, datetime, timedelta

import requests

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands, tasks
from disnake.ext.commands import Context

import config_py
import exceptions
from helpers.logger import setup_logger

# --------------------------------------------------------------------------- #
#  Configuration & logging
# --------------------------------------------------------------------------- #
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
with open("config.json", encoding="utf-8") as file:
    config = json.load(file)

logger = setup_logger()

# Populated hourly from the WordPress guide API; consumed by the tag-reaction
# helpers below. Kept module-level so both the task and the listeners share it.
tag_dict: dict = {}


# --------------------------------------------------------------------------- #
#  Client
# --------------------------------------------------------------------------- #
def _build_intents() -> disnake.Intents:
    """Intents the bot needs. ``message_content`` is required for prefix commands
    and for the message-scanning listeners to see message text."""
    intents = disnake.Intents.default()
    intents.reactions = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    return intents


class DodoBot(commands.Bot):
    """The Dodo client."""

    def __init__(self) -> None:
        super().__init__(command_prefix=config["prefix"], intents=_build_intents())
        self.logger = logger
        self.config = config
        # We provide a custom help command elsewhere; drop the built-in one.
        self.remove_command("help")

    def load_all_cogs(self) -> None:
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
                    self.load_extension(extension)
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
    await bot.change_presence(activity=disnake.Game(random.choice(config_py.statuses)))


@tasks.loop(minutes=60.0)
async def api_import() -> None:
    """Refresh the guide-article tag lookup from the WordPress API hourly."""
    global tag_dict
    tag_dict = await get_tags_from_wordpress_api()
    bot.logger.info("Guide tag list updated successfully.")


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
                except disnake.HTTPException as error:
                    bot.logger.error(f"Failed to add reaction {emoji} to {message_id}: {error}")


async def _find_message(message_id: int):
    """Search every text channel the bot can see for a message by ID."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                return await channel.fetch_message(message_id)
            except disnake.NotFound:
                continue
            except (disnake.Forbidden, disnake.HTTPException):
                continue
    return None


async def _bot_already_reacted(message: disnake.Message, emoji: str) -> bool:
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
    bot.logger.info(f"Logged in as {bot.user} (disnake {disnake.__version__})")
    bot.logger.info(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")
    status_task.start()
    api_import.start()
    check_reactions.start()


# --------------------------------------------------------------------------- #
#  Member events
# --------------------------------------------------------------------------- #
@bot.event
async def on_member_join(member: disnake.Member) -> None:
    """Handle a new (or returning) member joining.

    Order of operations:
    1. If they arrive already carrying the bot-trap role, ban immediately.
    2. Grant the configured starter roles.
    3. If we have saved roles from a previous membership, restore them and post a
       'welcome back' message; otherwise post a first-time welcome.

    (This merges two previously-separate ``on_member_join`` handlers — the second
    used to silently override the first, so the welcome/returning-player logic
    never actually ran.)
    """
    # 1. Trap role check.
    try:
        trap_role_id = int(config_py.TRAP_ROLE_ID)
        if any(role.id == trap_role_id for role in member.roles):
            await handle_trap_trigger(member)
            return
    except (AttributeError, ValueError):
        pass

    # 2. Starter roles.
    starter_roles = [member.guild.get_role(rid) for rid in config_py.starter_roles]
    starter_roles = [role for role in starter_roles if role is not None]
    if starter_roles:
        await member.add_roles(*starter_roles, reason="Automatic starter roles on join")

    # 3. Welcome / returning-player restoration.
    channel = bot.get_channel(config_py.WAYSHRINE)
    if not channel:
        return

    saved = config_py.left_roles.find_one({"_id": member.id})
    if saved and "roles" in saved:
        restored = [member.guild.get_role(rid) for rid in saved["roles"]]
        restored = [role for role in restored if role is not None]
        if restored:
            await member.add_roles(*restored, reason="Restoring roles from previous membership")
        await channel.send(
            f"Welcome back, {member.mention}! I have saved your roles from the last visit and "
            f"reassigned them to you. If anything has changed, update your roles in "
            f"<#{config_py.RANK_REQ}> and pick the trials you want to be notified about in "
            f"<#{config_py.SELECT_ROLES}>. Ping any of the admins if you have questions, and happy raiding! :hearts:"
        )
        config_py.left_roles.delete_one({"_id": member.id})
    else:
        await channel.send(
            f"Welcome, {member.mention}! If you want to raid with us, post your clearsies in "
            f"<#{config_py.RANK_REQ}> and choose the trials you would like to join in "
            f"<#{config_py.SELECT_ROLES}>. Ping any of the admins if you have questions, and happy raiding! :hearts:"
        )


@bot.event
async def on_member_remove(member: disnake.Member) -> None:
    """Save a leaving member's roles so they can be restored if they return.

    Reaction-role-managed roles and @everyone are excluded from the snapshot.
    """
    excluded_role_ids = set()
    for role_mapping in config_py.reaction_roles.values():
        excluded_role_ids.update(role_mapping.values())

    roles = [
        role.id
        for role in member.roles
        if role.id != member.guild.default_role.id and role.id not in excluded_role_ids
    ]
    config_py.left_roles.update_one(
        {"_id": member.id}, {"$set": {"roles": roles}}, upsert=True
    )


@bot.event
async def on_member_update(before: disnake.Member, after: disnake.Member) -> None:
    """Catch users who gain the bot-trap role after joining (e.g. via onboarding)."""
    try:
        trap_role_id = int(config_py.TRAP_ROLE_ID)
    except (AttributeError, ValueError):
        return

    had_role = any(role.id == trap_role_id for role in before.roles)
    has_role = any(role.id == trap_role_id for role in after.roles)
    if not had_role and has_role:
        await handle_trap_trigger(after)


# --------------------------------------------------------------------------- #
#  Message events
# --------------------------------------------------------------------------- #
@bot.event
async def on_message(message: disnake.Message) -> None:
    """Main message listener: moderation, logging, fun reactions and command dispatch."""
    source_channel_id = 1109080900030955604  # ATG sign-up channel.
    mod_channel_id = 1113035754923368478  # Moderator notification channel.

    # Relay ATG sign-ups (from non-bot authors) to the mod channel.
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

    await check_for_harmful_messages(message)

    # Archive every message for analytics.
    try:
        config_py.messages.insert_one(
            {
                "tag": "",
                "message": message.content,
                "intent": "",
                "author": message.author.id,
                "channel": message.channel.id,
            }
        )
    except Exception as error:
        bot.logger.error(f"Failed to archive message: {error}")

    content = message.content.lower()

    # "no u" call-and-response.
    if "no u" in content or "no you" in content:
        channel = bot.get_channel(message.channel.id)
        nou_answers = [
            "no u", "no you", "No, you", "No You!", "NO YOU!", "NO YOUUU!!",
            "No, Tomtem!", "no, Ducky.", "no, this time it's definitely you", "nope, you all the way",
        ]
        taunted_answers = [
            "Ah sh*t, here we go again.", "Don't make me angy. You wouldn't like me when I'm angy",
            "...", "it's time to stop", "http://dodos.fun/wp-content/uploads/2021/05/angy.jpg",
            "a trolling is happening",
        ]
        if random.randint(0, 10) < 5:
            await channel.send(random.choice(taunted_answers))
        else:
            await channel.send(random.choice(nou_answers))

    # Offer the schedule when raid-related keywords show up.
    elif (
        any(keyword in content for keyword in ("schedule", "trials", "chappelles-tyrone-tyrone-biggums-gif", "raids", "happening"))
        and not message.author.bot
    ):
        for reaction in config_py.addons:
            await message.add_reaction(reaction)

        def check(reaction, user):
            return str(reaction) in config_py.addons and user.id == message.author.id

        try:
            reaction, _user = await bot.wait_for("reaction_add", timeout=15, check=check)
            if config_py.addons[reaction.emoji] == 0:
                context = await bot.get_context(message)
                await context.invoke(bot.get_command("schedule123"))
                await message.clear_reactions()
        except asyncio.TimeoutError:
            await message.clear_reactions()

    # Summon the support cat on request.
    elif any(phrase in content for phrase in ("support cat", "goodnight cat", "good night cat")):
        context = await bot.get_context(message)
        await context.invoke(bot.get_command("cat"))

    # Shower loved-ones with heart reactions.
    if message.author.id in config_py.DODOLOVE:
        await message.add_reaction(random.choice(["❤️", "💖", "💕", "💞", "💘", "❣️"]))

    bot.logger.debug(f"{message.guild}: {message.channel}: {message.author}: {message.content}")

    # Reply when the bot is mentioned directly (invokes the chat command).
    if bot.user.id in (user.id for user in message.mentions) and message.author.id != bot.user.id:
        context = await bot.get_context(message)
        if message.reference:
            replied = await message.channel.fetch_message(message.reference.message_id)
            await context.invoke(
                bot.get_command("chat"),
                message=f"{replied.author.display_name} previously said: {replied.content}. "
                f"Then {message.author} said: {message.content}",
            )
        else:
            await context.invoke(bot.get_command("chat"), message=message.content)

    await check_sweetroll_chance(message)
    await bot.process_commands(message)
    await check_tags(message)


@bot.event
async def on_message_delete(message: disnake.Message) -> None:
    """Log deleted messages to the audit channel."""
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    embed = disnake.Embed(
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
async def on_reaction_add(reaction: disnake.Reaction, user: disnake.User) -> None:
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

    embed = disnake.Embed(title="📚 Potentially helpful resources found!", color=disnake.Color.brand_green())
    for tag in tags:
        try:
            links = await context.invoke(bot.get_command("guide"), tag=tag)
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
async def on_raw_reaction_add(payload: disnake.RawReactionActionEvent) -> None:
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
async def on_raw_reaction_remove(payload: disnake.RawReactionActionEvent) -> None:
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
async def on_slash_command(interaction: ApplicationCommandInteraction) -> None:
    """Log every successful slash command."""
    bot.logger.info(
        f"Executed /{interaction.data.name} in {interaction.guild.name} "
        f"(ID: {interaction.guild.id}) by {interaction.author} (ID: {interaction.author.id})"
    )


@bot.event
async def on_slash_command_error(interaction: ApplicationCommandInteraction, error: Exception) -> None:
    """Turn slash-command errors into friendly, ephemeral responses."""
    if isinstance(error, exceptions.UserBlacklisted):
        bot.logger.info("A blacklisted user tried to run a slash command.")
        return await interaction.send(
            embed=disnake.Embed(title="Error!", description=error.message, color=0xE02B2B),
            ephemeral=True,
        )
    if isinstance(error, commands.errors.MissingPermissions):
        return await interaction.send(
            embed=disnake.Embed(
                title="Error!",
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to run this command!",
                color=0xE02B2B,
            ),
            ephemeral=True,
        )
    raise error


@bot.event
async def on_command_completion(context: Context) -> None:
    """Log every successful prefix command to the DB and the audit channel."""
    executed_command = context.command.qualified_name.split(" ")[0]
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    config_py.commands_use.insert_one(
        {
            "Command": executed_command,
            "Guild": context.guild.name,
            "Name": context.message.author.display_name,
            "User ID": context.message.author.id,
            "Date": date.today().isoformat(),
        }
    )
    await channel.send(
        f"Executed {executed_command} command in {context.guild.name} "
        f"(ID: {context.guild.id}) by {context.author} (ID: {context.author.id})"
    )
    bot.logger.info(f"Executed {executed_command} by {context.author} in {context.guild.name}")


@bot.event
async def on_command_error(context: Context, error) -> None:
    """Turn common prefix-command errors into friendly responses."""
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        parts = []
        if round(hours):
            parts.append(f"{round(hours)} hours")
        if round(minutes):
            parts.append(f"{round(minutes)} minutes")
        if round(seconds):
            parts.append(f"{round(seconds)} seconds")
        await context.send(
            embed=disnake.Embed(
                title="Hey, please slow down!",
                description=f"You can use this command again in {' '.join(parts)}.",
                color=0xE02B2B,
            )
        )
    elif isinstance(error, commands.MissingPermissions):
        await context.send(
            embed=disnake.Embed(
                title="Error!",
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to run this command!",
                color=0xE02B2B,
            )
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await context.send(
            embed=disnake.Embed(title="Error!", description=str(error).capitalize(), color=0xE02B2B)
        )
    else:
        raise error


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


async def check_for_harmful_messages(message: disnake.Message) -> None:
    """Delete (and, for invite+@everyone spam, ban) messages with restricted content."""
    if any(link in message.content for link in config_py.allowed_links):
        return
    if not any(s in message.content.lower() for s in config_py.restricted_strings):
        return

    member_roles = [role.id for role in message.author.roles]
    if any(role in member_roles for role in config_py.allowed_roles):
        return

    log_channel = bot.get_channel(config_py.E4D_LOG)
    embed = disnake.Embed(
        title="Oi!!",
        description=f"**User:** {message.author}\n**Content:** {message.content}",
        color=disnake.Color.red(),
    )

    # Invite link + @everyone = immediate ban.
    if "@everyone" in message.content and "discord.gg" in message.content.lower():
        user_embed = disnake.Embed(
            title="You have been banned!",
            description=f"You have been banned from {message.guild.name} for unauthorized activities.",
            color=disnake.Color.dark_red(),
        )
        user_embed.set_thumbnail(url=message.guild.icon.url if message.guild.icon else None)
        user_embed.add_field(name="Reason", value="Unauthorized invite link with @everyone mention", inline=False)
        user_embed.set_footer(text="Contact the server admin for more information.")
        try:
            await message.author.send(embed=user_embed)
        except disnake.errors.HTTPException:
            bot.logger.warning("Failed to DM the banned user.")
        embed.title = "Immediate Ban for Unauthorized Mention and Link"
        embed.description = (
            f"**User:** {message.author}\n**Content:** {message.content}\n"
            f"**Action:** Banned for an unauthorized invite link together with '@everyone'."
        )
        embed.color = disnake.Color.dark_red()
        await log_channel.send(embed=embed)
        await message.guild.ban(message.author, reason="Unauthorized invite link with @everyone mention")
        await message.delete()
        return

    # Otherwise just delete and warn.
    embed.title = "Deleted Message with Restricted Content"
    embed.description = (
        f"**User:** {message.author}\n**Content:** {message.content}\n"
        f"**Action:** Message deleted due to restricted content."
    )
    embed.color = disnake.Color.orange()
    await log_channel.send(embed=embed)
    await message.delete()
    await message.channel.send(
        "Oi! Something doesn't look right in this chat! I will delete the message. :hearts: "
        "Please poke any of the admins if you think I'm being crazy."
    )


async def check_tags(message: disnake.Message) -> None:
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


async def add_role_to_user(member: disnake.Member, role_id: int, message: disnake.Message) -> None:
    """Add a reaction-role, log it, and (for the in-game guild role) ping moderators."""
    role = message.guild.get_role(role_id)
    if not role:
        return
    await member.add_roles(role)
    log_channel = bot.get_channel(config_py.E4D_ROLE_LOG)
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


async def remove_role_from_user(member: disnake.Member, role_id: int, message: disnake.Message) -> None:
    """Remove a reaction-role and log it."""
    role = message.guild.get_role(role_id)
    if not role:
        return
    await member.remove_roles(role)
    log_channel = bot.get_channel(config_py.E4D_ROLE_LOG)
    await log_channel.send(f"Removed {role.name} from {member.display_name} in {message.guild.name}.")
    temp_message = await message.channel.send(f"The {role.name} role has been removed from you, {member.display_name}.")
    await asyncio.sleep(5)
    await temp_message.delete()


async def remove_role_later(member: disnake.Member, role: disnake.Role) -> None:
    """Remove ``role`` from ``member`` after one hour (non-persistent across restarts)."""
    await asyncio.sleep(3600)
    try:
        if role in member.roles:
            await member.remove_roles(role)
    except disnake.HTTPException:
        pass


async def run_pumpkin_game(
    channel: disnake.TextChannel,
    original_message: disnake.Message,
    discoverer: disnake.User,
    bot: "DodoBot",
    config_py,
) -> None:
    """Run the cooperative 'pull the giant pumpkin' minigame."""
    pumpkins = config_py.pumpkins
    pull_collection = config_py.pull
    weight = random.randint(5, 800)  # Pumpkin weight in kg.
    explosion_time = datetime.now() + timedelta(minutes=weight / 8)

    discoverer_data = pull_collection.find_one({"_id": discoverer.id})
    base_strength = discoverer_data.get("strength", 50) if discoverer_data else 50
    pullers = {discoverer.id: base_strength}
    total_strength = base_strength

    PUMPKIN_ROLE_ID = 1430471888412475413
    GAME_EMOJI = "\U0001F383"
    guild = original_message.guild
    if not guild:
        return

    embed = disnake.Embed(
        title="🎃 A GIANT PUMPKIN APPEARS! 🎃",
        description=(
            "A massive pumpkin just burst from the ground! It looks unstable...\n"
            "React with 🎃 to help pull it out before it explodes!"
        ),
        color=disnake.Color.orange(),
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
    except disnake.HTTPException:
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
                pullers[user.id] = user_data.get("strength", 50) if user_data else 50
                total_strength = sum(pullers.values())
                puller_list = "\n".join(f"<@{uid}>: {strength}kg" for uid, strength in pullers.items())
                embed.set_field_at(2, name="Total Strength", value=f"**{total_strength} kg**", inline=True)
                embed.set_field_at(4, name=f"Pullers ({len(pullers)})", value=puller_list, inline=False)
                await game_message.edit(embed=embed)

            if total_strength >= weight:
                reward_per_person = round(weight / len(pullers))
                win_embed = disnake.Embed(
                    title="🎃 SUCCESS! 🎃",
                    description=f"You did it! The **{weight}kg** pumpkin was pulled from the ground!",
                    color=disnake.Color.green(),
                )
                win_embed.add_field(name="Total Pullers", value=str(len(pullers)), inline=True)
                win_embed.add_field(name="Reward Each", value=f"**{reward_per_person} kg** of pumpkin!", inline=True)
                win_embed.set_footer(text="Your pumpkin stats and pull strength (+5kg!) have been updated.")
                await game_message.edit(embed=win_embed)
                await game_message.clear_reactions()

                for user_id, current_strength in pullers.items():
                    pull_collection.update_one(
                        {"_id": user_id},
                        {"$set": {"strength": current_strength + 5, "last_pull": datetime.now()}},
                        upsert=True,
                    )
                    pumpkins.insert_one(
                        {"collector": user_id, "date": datetime.now(), "weight_collected": reward_per_person}
                    )
                    if pumpkins.count_documents({"collector": user_id}) >= 50:
                        try:
                            role = guild.get_role(PUMPKIN_ROLE_ID)
                            member = await guild.fetch_member(user_id)
                            if role and member and role not in member.roles:
                                await member.add_roles(role)
                                await channel.send(
                                    f"**Wow!** <@{user_id}> has collected 50 pumpkins and earned the **{role.name}** role!"
                                )
                        except disnake.Forbidden:
                            await channel.send(f"I tried to give <@{user_id}> the pumpkin role, but I don't have permissions!")
                        except Exception as error:
                            bot.logger.error(f"Error adding pumpkin role: {error}")
                return
        except asyncio.TimeoutError:
            break

    # Explosion (nobody managed to pull it out in time).
    if total_strength < weight:
        explode_embed = disnake.Embed(
            title="💥 BOOOOOOM! 💥",
            description=(
                f"Oh no! The **{weight}kg** pumpkin was too strong!\n"
                f"It exploded, covering everyone in pumpkin guts!"
            ),
            color=disnake.Color.red(),
        )
        explode_embed.add_field(
            name="Covered in Guts",
            value="\n".join(f"<@{uid}>" for uid in pullers) or "Nobody...",
            inline=False,
        )
        explode_embed.set_footer(text="You've... earned a temporary role. Your strength (+5kg!) has been saved.")
        await game_message.edit(embed=explode_embed)
        await game_message.clear_reactions()

        for user_id, current_strength in pullers.items():
            pull_collection.update_one(
                {"_id": user_id},
                {"$set": {"strength": current_strength + 5, "last_pull": datetime.now()}},
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
                except disnake.Forbidden:
                    await channel.send(f"I tried to give <@{user_id}> the sticky pumpkin role, but I don't have permissions!")
                except Exception as error:
                    bot.logger.error(f"Error adding temporary pumpkin role: {error}")


async def _run_sweetroll_event(
    message: disnake.Message, sweetrolls, pumpkins, channel, spawn_emoji, is_rhubarb, is_pumpkin
) -> None:
    """Run a single sweetroll / rhubarb / pumpkin spawn as a non-blocking task."""
    try:
        await message.add_reaction(spawn_emoji)

        def check(reaction, user):
            return user != bot.user and str(reaction.emoji) == spawn_emoji

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=config_py.SWEETROLL_COOLDOWN, check=check)

            # Rhubarb betrayal.
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

            # Pumpkin minigame.
            if is_pumpkin:
                await run_pumpkin_game(channel, message, user, bot, config_py)
                return

            # Normal sweetroll — owner reclaims it.
            if user and user.id == message.author.id:
                await channel.send(
                    "A sweetroll fell out but the owner picked it up before anyone else could! Great job! :cupcake:"
                )
                await message.remove_reaction(spawn_emoji, bot.user)
                return

            # Someone else grabbed it.
            if user and user.id != message.author.id:
                # Amulet protection.
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

                # Steal-or-gift roll.
                target_is_ghost = message.author.id == 305162419733397505
                target_name = "Ghost" if target_is_ghost else message.author.mention
                if random.randint(1, 100) < config_py.SWEETROLL_GIFTING:
                    sweetrolls.insert_one({"stolen_from": message.author.id, "thief": user.id, "date": datetime.now()})
                    await message.remove_reaction(spawn_emoji, bot.user)
                    await channel.send(f"{user.mention} just stole the sweetroll from {target_name}!")
                else:
                    sweetrolls.insert_one({"gifted_to": message.author.id, "gifter": user.id, "date": datetime.now()})
                    await message.remove_reaction(spawn_emoji, bot.user)
                    await channel.send(
                        f"{user.mention} suddenly gifted a sweetroll to {target_name}! Extreme generosity!"
                    )

        except asyncio.TimeoutError:
            try:
                await message.remove_reaction(spawn_emoji, bot.user)
            except disnake.HTTPException:
                pass
    except Exception as error:
        bot.logger.error(f"Error in sweetroll event: {error}")
        try:
            await message.remove_reaction(spawn_emoji, bot.user)
        except disnake.HTTPException:
            pass


async def check_sweetroll_chance(message: disnake.Message) -> None:
    """Roll for a sweetroll/rhubarb/pumpkin spawn and, if it hits, launch the event."""
    channel = bot.get_channel(config_py.PET_CHANNEL)
    if random.randint(1, 100) <= config_py.SWEETROLL_NEEDED:
        return

    is_rhubarb = random.randint(1, 1000) >= 995
    is_pumpkin = not is_rhubarb and random.randint(1, 100) > 60
    spawn_emoji = "\U0001F383" if is_pumpkin else "\U0001F9C1"

    asyncio.create_task(
        _run_sweetroll_event(
            message, config_py.sweetrolls, config_py.pumpkins, channel, spawn_emoji, is_rhubarb, is_pumpkin
        )
    )


async def handle_trap_trigger(member: disnake.Member) -> None:
    """Ban a member who took the bot-trap role, alert admins, and allow a reaction-undo."""
    try:
        alert_channel_id = int(config_py.ALERT_CHANNEL_ID)
        ban_emoji = config_py.BAN_EMOJI
        check_emoji = getattr(config_py, "CHECK_EMOJI", "✅")
        wait_duration = config_py.WAIT_DURATION
    except AttributeError as error:
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
    except disnake.Forbidden:
        await alert_channel.send(
            f"⚠️ I caught {member.mention} triggering the trap role, but I lack permissions to ban them!"
        )
        return
    except disnake.HTTPException as error:
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
        except (disnake.Forbidden, disnake.NotFound):
            pass

        if str(reaction.emoji) == str(check_emoji):
            try:
                await guild.unban(member, reason=f"Ban cancelled by {user.display_name}")
                await alert_channel.send(
                    f"✅ Ban revoked for **{member.name}** by {user.mention}.\n"
                    f"*Note: they were removed from the server and will need a new invite to rejoin.*"
                )
            except disnake.Forbidden:
                await alert_channel.send(
                    f"⚠️ I don't have permission to unban {member.name}! {user.mention}, please do it manually."
                )
        else:
            await alert_channel.send(f"🔒 Ban confirmed for **{member.name}** by {user.mention}.")
    except asyncio.TimeoutError:
        try:
            await alert_message.clear_reactions()
        except (disnake.Forbidden, disnake.NotFound):
            pass


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    bot.load_all_cogs()
    bot.run(config["token"])
