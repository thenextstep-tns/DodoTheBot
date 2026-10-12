"""
Log cog — a comprehensive server audit logger. Per-guild log channels are read
from ``guilds.json``; events are batched to avoid rate limits and also archived
to MongoDB. ``/setlogchannel`` and ``/setdeletechannel`` configure destinations.
"""

import asyncio
import json
import os
from collections import defaultdict

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

import config_py
import lang
from helpers import event_log

# Colors for consistent visual logging
COLOR_JOIN = 0x43b581     # Green
COLOR_LEAVE = 0xf04747    # Red
COLOR_EDIT = 0xfaa61a     # Orange
COLOR_DELETE = 0xf04747   # Red
COLOR_CREATE = 0x43b581   # Green
COLOR_INFO = 0x7289da     # Blue

GUILDS_FILE = "guilds.json"

# Discord caps a message at 10 embeds *and* 6000 characters summed across all of
# them; a batch that breaks either limit is rejected wholesale, so we stay under.
MAX_EMBEDS_PER_MESSAGE = 10
MAX_CHARS_PER_MESSAGE = 5900

def load_guilds():
    """Load the guild log channel configurations."""
    if not os.path.isfile(GUILDS_FILE) or os.path.getsize(GUILDS_FILE) == 0:
        return {}
    try:
        with open(GUILDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Handle cases where the file exists but is corrupted
        return {}

def save_guilds(data):
    """Save the guild log channel configurations."""
    with open(GUILDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class Log(commands.Cog, name="log"):
    def __init__(self, bot):
        self.bot = bot
        self.invites = {}
        self.log_queue = asyncio.Queue()
        self.pending_role_updates = {}
        self.batch_logger.start()

    def cog_unload(self):
        self.batch_logger.cancel()

    def get_log_channel(self, guild):
        """Helper to fetch the log channel using the dictionary from guilds.json."""
        if not guild:
            return None
        # Audit logging is a per-guild toggleable feature; when off, resolve no
        # channel so every listener no-ops (and nothing is archived).
        if not self.bot.visibility.feature_active(guild.id, "audit_log", "log"):
            return None

        log_channels = load_guilds()
        guild_data = log_channels.get(str(guild.id))
        
        if not guild_data:
            return None
            
        # Support both the new dict format and the old integer format
        if isinstance(guild_data, dict):
            channel_id = guild_data.get("channel_id")
        else:
            channel_id = guild_data
        
        if channel_id:
            return guild.get_channel(int(channel_id))
        return None

    def guild_log_channels(self, guild) -> dict:
        """This guild's stored destinations as ``{channel_id, delete_channel_id}``.

        Read straight from ``guilds.json`` (not resolved to channels) so the
        control panel can show what is configured even if a channel is gone.
        """
        data = load_guilds().get(str(guild.id)) if guild else None
        if isinstance(data, dict):
            return {
                "channel_id": int(data["channel_id"]) if data.get("channel_id") else 0,
                "delete_channel_id": int(data["delete_channel_id"]) if data.get("delete_channel_id") else 0,
            }
        # Legacy integer format: a bare audit channel id.
        return {"channel_id": int(data), "delete_channel_id": 0} if data else {}

    def set_guild_log_channel(self, guild, key: str, channel_id: int) -> None:
        """Point one of this guild's log destinations at a channel (0 clears it)."""
        if key not in ("channel_id", "delete_channel_id"):
            raise KeyError(key)
        store = load_guilds()
        entry = store.get(str(guild.id))
        if not isinstance(entry, dict):
            # Upgrade the legacy integer format on first write.
            entry = {"channel_id": int(entry)} if entry else {}
        entry["guild_name"] = guild.name
        if channel_id:
            entry[key] = int(channel_id)
        else:
            entry.pop(key, None)
        store[str(guild.id)] = entry
        save_guilds(store)

    def get_delete_log_channel(self, guild):
        """Helper to fetch the delete/edit log channel, falling back to standard log channel."""
        if not guild:
            return None
        if not self.bot.visibility.feature_active(guild.id, "audit_log", "log"):
            return None

        log_channels = load_guilds()
        guild_data = log_channels.get(str(guild.id))
        
        if not guild_data:
            return None
            
        if isinstance(guild_data, dict):
            delete_channel_id = guild_data.get("delete_channel_id")
            if delete_channel_id:
                return guild.get_channel(int(delete_channel_id))
                
        # Fallback to standard log channel if delete channel is not configured
        return self.get_log_channel(guild)

    def truncate(self, text, limit=1024):
        """Helper to safely truncate strings for embed fields."""
        if not text:
            return ""
        return text[:limit - 3] + "..." if len(text) > limit else text

    async def _get_audit_entry(self, guild, action, target_id=None, max_age_sec=15):
        """Helper to fetch a recent audit log entry."""
        try:
            async for entry in guild.audit_logs(action=action, limit=10):
                if target_id is None or entry.target.id == target_id:
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < max_age_sec:
                        return entry
        except discord.Forbidden:
            pass
        return None

    #############################################
    #          BATCHING & DB LOGGING            #
    #############################################

    def _insert_db(self, data):
        """Synchronous method to insert log data into MongoDB."""
        try:
            # Assumes config_py has a 'logs' collection defined (e.g. config_py.logs)
            if hasattr(config_py, "logs"):
                config_py.logs.insert_one(data)
        except Exception as error:
            self.bot.logger.error(f"Failed to insert log to DB: {error}")

    async def send_log(self, channel, embed, event_type, guild):
        """Queues an embed for batch sending and sends data to the database."""
        if not channel:
            return

        # Queue the Discord message
        await self.log_queue.put({"channel": channel, "embed": embed})

        # Prepare and execute the DB insertion without blocking the event loop
        fields = {field.name: field.value for field in embed.fields}
        # Who and where, pulled out of the rendered text rather than passed in by
        # each listener: there are thirty-odd listeners and one of this, so this
        # is the version that cannot be half-done. It is what lets the panel's
        # server log filter by person and by channel.
        named = event_log.subjects(embed.description, fields)
        db_data = {
            "guild_id": guild.id,
            "event_type": event_type,
            "description": embed.description,
            "fields": fields,
            "timestamp": discord.utils.utcnow().isoformat(),
            "user_ids": named["user_ids"],
            "channel_ids": named["channel_ids"],
            # Who it happened to, and who did it. Kept apart because they are
            # different questions: filtering on a moderator should not return
            # every role change they ever made to somebody else.
            "subject_id": named["subject_id"],
            "actor_id": named["actor_id"],
        }
        self.bot.loop.run_in_executor(None, self._insert_db, db_data)

    @staticmethod
    def _batch_embeds(embeds):
        """Split ``embeds`` into groups that fit in one message.

        ``len(embed)`` is Discord's own accounting (title + description + field
        names/values + footer + author), which is what the 6000 limit counts.
        """
        chunk, chunk_chars = [], 0
        for embed in embeds:
            size = len(embed)
            if chunk and (len(chunk) >= MAX_EMBEDS_PER_MESSAGE or chunk_chars + size > MAX_CHARS_PER_MESSAGE):
                yield chunk
                chunk, chunk_chars = [], 0
            chunk.append(embed)
            chunk_chars += size
        if chunk:
            yield chunk

    @tasks.loop(seconds=2.0)
    async def batch_logger(self):
        """Background task that groups pending embeds by channel to avoid rate limits."""
        # Process pending role updates to debounce role spam
        if hasattr(self, 'pending_role_updates') and self.pending_role_updates:
            updates = self.pending_role_updates.copy()
            self.pending_role_updates.clear()
            
            for (guild_id, member_id, _actor), data in updates.items():
                member = data["member"]
                guild = member.guild
                channel = self.get_log_channel(guild)
                if not channel: continue
                
                final_added = data["added"] - data["removed"]
                final_removed = data["removed"] - data["added"]
                
                if not final_added and not final_removed:
                    continue

                now = int(discord.utils.utcnow().timestamp())
                actor_str = f" by {data['actor']}" if data['actor'] != "Unknown" else ""
                desc = lang.LOG_ROLE_UPDATE.format(mention=member.mention, id=member.id, actor=actor_str, now=now)

                embed = discord.Embed(description=desc, color=COLOR_INFO)

                if final_added:
                    embed.add_field(name=lang.LOG_ROLE_ADDED, value=" ".join(final_added)[:1024], inline=False)
                if final_removed:
                    embed.add_field(name=lang.LOG_ROLE_REMOVED, value=" ".join(final_removed)[:1024], inline=False)
                
                await self.send_log(channel, embed, "MEMBER_ROLE_UPDATE", guild)

        if self.log_queue.empty():
            return

        pending = []
        while not self.log_queue.empty():
            pending.append(self.log_queue.get_nowait())

        # Group embeds by destination channel
        grouped = defaultdict(list)
        for item in pending:
            grouped[item["channel"]].append(item["embed"])

        # Send in batches that respect both the embed-count and character limits
        for channel, embeds in grouped.items():
            for chunk in self._batch_embeds(embeds):
                try:
                    await channel.send(embeds=chunk)
                except Exception as error:
                    self.bot.logger.error(f"Failed to send log batch to {channel.id}: {error}")

    @batch_logger.before_loop
    async def before_batch_logger(self):
        await self.bot.wait_until_ready()

    #############################################
    #                 COMMANDS                  #
    #############################################

    @commands.hybrid_command(name="setlogchannel", description="Set the channel where server logs are sent.")
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, context: Context, channel: discord.TextChannel) -> None:
        """Configure the standard log channel for this guild."""
        log_channels = load_guilds()
        guild_id = str(context.guild.id)
        guild_data = log_channels.get(guild_id, {})
        if not isinstance(guild_data, dict):  # migrate legacy integer config
            guild_data = {"channel_id": guild_data}
        guild_data["channel_id"] = channel.id
        guild_data["guild_name"] = context.guild.name
        log_channels[guild_id] = guild_data
        save_guilds(log_channels)
        await context.send(lang.LOG_SET_CHANNEL.format(channel=channel.mention), ephemeral=True)

    @commands.hybrid_command(name="setdeletechannel", description="Set a separate channel for edit/deletion logs.")
    @commands.has_permissions(administrator=True)
    async def set_delete_channel(self, context: Context, channel: discord.TextChannel) -> None:
        """Configure a dedicated log channel for message edits and deletions."""
        log_channels = load_guilds()
        guild_id = str(context.guild.id)
        guild_data = log_channels.get(guild_id, {})
        if not isinstance(guild_data, dict):
            guild_data = {"channel_id": guild_data}
        guild_data["delete_channel_id"] = channel.id
        guild_data["guild_name"] = context.guild.name
        log_channels[guild_id] = guild_data
        save_guilds(log_channels)
        await context.send(lang.LOG_SET_DELETE_CHANNEL.format(channel=channel.mention), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Cache invites on startup to track invite usage, only for configured guilds."""
        log_channels = load_guilds()
        
        for guild in self.bot.guilds:
            if str(guild.id) in log_channels:
                try:
                    self.invites[guild.id] = await guild.invites()
                except discord.Forbidden:
                    pass

    #############################################
    #              MEMBER EVENTS                #
    #############################################

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = self.get_log_channel(member.guild)
        if not channel: return

        now = int(discord.utils.utcnow().timestamp())
        desc = lang.LOG_MEMBER_JOIN.format(mention=member.mention, id=member.id, now=now)

        # Check which invite was used
        used_invite = None
        try:
            new_invites = await member.guild.invites()
            old_invites = self.invites.get(member.guild.id, [])
            for old_inv in old_invites:
                for new_inv in new_invites:
                    if old_inv.code == new_inv.code and old_inv.uses < new_inv.uses:
                        used_invite = new_inv
                        break
            self.invites[member.guild.id] = new_invites
        except discord.Forbidden:
            pass

        embed = discord.Embed(description=desc, color=COLOR_JOIN)
        
        if used_invite:
            inviter = used_invite.inviter
            inviter_text = f"**{inviter.name}** (`{inviter.id}`)" if inviter else "Unknown"
            embed.add_field(name=lang.LOG_INVITE_USED, value=lang.LOG_INVITE_USED_VALUE.format(code=used_invite.code, inviter=inviter_text, uses=used_invite.uses), inline=False)

        await self.send_log(channel, embed, "MEMBER_JOIN", member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = self.get_log_channel(member.guild)
        if not channel: return

        # Wait briefly for audit logs to populate
        await asyncio.sleep(1.5)
        now = int(discord.utils.utcnow().timestamp())

        ban_entry = await self._get_audit_entry(member.guild, discord.AuditLogAction.ban, member.id)
        if ban_entry:
            # Let on_member_ban handle the logging
            return

        kick_entry = await self._get_audit_entry(member.guild, discord.AuditLogAction.kick, member.id)
        if kick_entry:
            actor = kick_entry.user.mention if kick_entry.user else "Unknown"
            reason = kick_entry.reason or "No reason provided"
            desc = lang.LOG_MEMBER_KICK.format(mention=member.mention, actor=actor, now=now, reason=reason)
            event_type = "MEMBER_KICK"
        else:
            desc = lang.LOG_MEMBER_LEAVE.format(mention=member.mention, now=now)
            event_type = "MEMBER_LEAVE"

        embed = discord.Embed(description=desc, color=COLOR_LEAVE)
        embed.set_author(name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url if member.display_avatar else None)
        
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            embed.add_field(name=lang.LOG_ROLES_HELD, value=" ".join(roles)[:1024], inline=False)

        await self.send_log(channel, embed, event_type, member.guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        channel = self.get_log_channel(guild)
        if not channel: return

        await asyncio.sleep(1.5)
        now = int(discord.utils.utcnow().timestamp())
        ban_entry = await self._get_audit_entry(guild, discord.AuditLogAction.ban, user.id)
        
        actor = ban_entry.user.mention if ban_entry and ban_entry.user else "Unknown"
        reason = ban_entry.reason if ban_entry and ban_entry.reason else "No reason provided"
        
        desc = lang.LOG_MEMBER_BAN.format(mention=user.mention, actor=actor, now=now, reason=reason)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        embed.set_author(name=f"{user.name} ({user.id})", icon_url=user.display_avatar.url if user.display_avatar else None)
        
        await self.send_log(channel, embed, "MEMBER_BAN", guild)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        channel = self.get_log_channel(guild)
        if not channel: return

        await asyncio.sleep(1.5)
        now = int(discord.utils.utcnow().timestamp())
        unban_entry = await self._get_audit_entry(guild, discord.AuditLogAction.unban, user.id)
        
        actor = unban_entry.user.mention if unban_entry and unban_entry.user else "Unknown"
        
        desc = lang.LOG_MEMBER_UNBAN.format(mention=user.mention, actor=actor, now=now)
        embed = discord.Embed(description=desc, color=COLOR_JOIN)
        embed.set_author(name=f"{user.name} ({user.id})", icon_url=user.display_avatar.url if user.display_avatar else None)
        
        await self.send_log(channel, embed, "MEMBER_UNBAN", guild)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        channel = self.get_log_channel(before.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())

        # Role updates (debounced)
        if before.roles != after.roles:
            # A running addrole/removerole sweep touches every member at once. Logging
            # each one would flood the channel and burn an audit-log request per member,
            # so those roles are skipped here — the moderation cog posts one summary.
            sweeping = getattr(self.bot, "bulk_role_ops", ())
            added = [
                role.mention for role in after.roles
                if role not in before.roles and (after.guild.id, role.id) not in sweeping
            ]
            removed = [
                role.mention for role in before.roles
                if role not in after.roles and (after.guild.id, role.id) not in sweeping
            ]

            if added or removed:
                entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.member_role_update, after.id)
                actor = entry.user.mention if entry and entry.user else "Unknown"

                # Keyed by actor as well as member. Debouncing on the member
                # alone merged unrelated people's edits into one entry and let
                # the last actor overwrite the first: a moderator adding a role
                # and the bot re-ranking a second later became a single line
                # credited to the bot, with the moderator's change cancelled out
                # against the bot's. Two people did two things; that is two
                # entries.
                key = (after.guild.id, after.id, actor)
                if key not in self.pending_role_updates:
                    self.pending_role_updates[key] = {"added": set(), "removed": set(),
                                                      "actor": actor, "member": after}

                self.pending_role_updates[key]["added"].update(added)
                self.pending_role_updates[key]["removed"].update(removed)

        # Nickname changes
        if before.nick != after.nick:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.member_update, after.id)
            actor = entry.user.mention if entry and entry.user else "Unknown"
            
            old_nick = before.nick if before.nick else before.name
            new_nick = after.nick if after.nick else after.name
            
            desc = lang.LOG_NICK_CHANGE.format(mention=after.mention, id=after.id, actor=actor, now=now, old=old_nick, new=new_nick)
            embed = discord.Embed(description=desc, color=COLOR_INFO)
            await self.send_log(channel, embed, "MEMBER_NICK_UPDATE", before.guild)

        # Timeout changes
        if before.timed_out_until != after.timed_out_until:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.member_update, after.id)
            actor = entry.user.mention if entry and entry.user else "Unknown"
            reason = entry.reason if entry and entry.reason else "No reason provided"

            if after.timed_out_until:
                timeout_until = int(after.timed_out_until.timestamp())
                desc = lang.LOG_TIMEOUT_ADD.format(mention=after.mention, id=after.id, actor=actor, now=now, until=timeout_until, reason=reason)
                color = COLOR_DELETE
                event_type = "MEMBER_TIMEOUT_ADD"
            else:
                desc = lang.LOG_TIMEOUT_REMOVE.format(mention=after.mention, id=after.id, actor=actor, now=now, reason=reason)
                color = COLOR_JOIN
                event_type = "MEMBER_TIMEOUT_REMOVE"
                
            embed = discord.Embed(description=desc, color=color)
            await self.send_log(channel, embed, event_type, before.guild)

    #############################################
    #             AUTOMOD EVENTS                #
    #############################################

    @commands.Cog.listener()
    async def on_automod_action(self, execution):
        channel = self.get_log_channel(execution.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        user = execution.member or execution.user
        user_mention = user.mention if user else "Unknown User"
        user_id = user.id if user else "Unknown ID"
        
        rule_name = execution.rule.name if getattr(execution, "rule", None) else "Unknown Rule"
        action_type = execution.action.type.name.replace("_", " ").title() if getattr(execution, "action", None) else "Unknown Action"
        
        desc = lang.LOG_AUTOMOD.format(action=action_type, mention=user_mention, id=user_id, now=now, rule=rule_name)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        
        if getattr(execution, "matched_keyword", None):
            embed.add_field(name="Keyword", value=f"`{execution.matched_keyword}`", inline=True)
        if getattr(execution, "channel", None):
            embed.add_field(name="Channel", value=execution.channel.mention, inline=True)
        
        content = self.truncate(getattr(execution, "content", ""))
        if content:
            embed.add_field(name="Message Content", value=content, inline=False)
            
        await self.send_log(channel, embed, "AUTOMOD_ACTION", execution.guild)

    #############################################
    #              INVITE EVENTS                #
    #############################################

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        channel = self.get_log_channel(invite.guild)
        if not channel: return

        try:
            self.invites[invite.guild.id] = await invite.guild.invites()
        except discord.Forbidden:
            pass

        now = int(discord.utils.utcnow().timestamp())
        
        if invite.inviter:
            inviter = f"**{invite.inviter.name}** (`{invite.inviter.id}`)"
        else:
            inviter = "Unknown"
            
        def format_age(seconds):
            if seconds == 0: return "Infinite"
            d, remainder = divmod(seconds, 86400)
            h, remainder = divmod(remainder, 3600)
            m, s = divmod(remainder, 60)
            parts = []
            if d: parts.append(f"{d}d")
            if h: parts.append(f"{h}h")
            if m: parts.append(f"{m}m")
            if s: parts.append(f"{s}s")
            return " ".join(parts)

        max_age = format_age(invite.max_age)
        max_uses = "Infinite" if invite.max_uses == 0 else invite.max_uses
        
        desc = lang.LOG_INVITE_CREATE.format(inviter=inviter, channel=invite.channel.mention, now=now, code=invite.code, age=max_age, uses=max_uses)

        embed = discord.Embed(description=desc, color=COLOR_CREATE)
        await self.send_log(channel, embed, "INVITE_CREATE", invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        channel = self.get_log_channel(invite.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        entry = await self._get_audit_entry(invite.guild, discord.AuditLogAction.invite_delete)
        actor_str = f" by **{entry.user.name}**" if entry and entry.user else ""
        
        desc = lang.LOG_INVITE_DELETE.format(code=invite.code, actor=actor_str, now=now, channel=invite.channel.mention if invite.channel else "Unknown")
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(channel, embed, "INVITE_DELETE", invite.guild)

    #############################################
    #             MESSAGE EVENTS                #
    #############################################

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        channel = self.get_delete_log_channel(before.guild)
        if not channel: return

        now = int(discord.utils.utcnow().timestamp())
        desc = lang.LOG_MESSAGE_EDIT.format(mention=before.author.mention, id=before.author.id, channel=before.channel.mention, now=now, jump=after.jump_url)

        embed = discord.Embed(description=desc, color=COLOR_EDIT)
        embed.add_field(name="Before", value=self.truncate(before.content) or "*[Empty]*", inline=False)
        embed.add_field(name="After", value=self.truncate(after.content) or "*[Empty]*", inline=False)

        await self.send_log(channel, embed, "MESSAGE_EDIT", before.guild)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return

        log_channel = self.get_delete_log_channel(message.guild)
        if not log_channel: return

        deleter = None
        try:
            async for entry in message.guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=5):
                if entry.target.id == message.author.id and entry.extra.channel.id == message.channel.id:
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                        deleter = entry.user
                    break
        except discord.Forbidden:
            pass

        now = int(discord.utils.utcnow().timestamp())
        deleter_text = lang.LOG_DELETED_BY.format(mention=deleter.mention) if deleter and deleter.id != message.author.id else ""
        desc = lang.LOG_MESSAGE_DELETE.format(mention=message.author.mention, id=message.author.id, channel=message.channel.mention, deleter=deleter_text, now=now)

        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        
        content = self.truncate(message.content)
        if content:
            embed.add_field(name="Content", value=content, inline=False)
        
        if message.attachments:
            files = "\n".join([att.filename for att in message.attachments])
            embed.add_field(name="Attachments", value=self.truncate(files), inline=False)

        await self.send_log(log_channel, embed, "MESSAGE_DELETE", message.guild)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages: return
        first_msg = messages[0]
        if not first_msg.guild: return
        
        log_channel = self.get_delete_log_channel(first_msg.guild)
        if not log_channel: return
        
        entry = await self._get_audit_entry(first_msg.guild, discord.AuditLogAction.message_bulk_delete)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        now = int(discord.utils.utcnow().timestamp())
        
        desc = lang.LOG_BULK_DELETE.format(count=len(messages), channel=first_msg.channel.mention, actor=actor_str, now=now)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(log_channel, embed, "MESSAGE_BULK_DELETE", first_msg.guild)

    #############################################
    #               ROLE EVENTS                 #
    #############################################

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        channel = self.get_log_channel(role.guild)
        if not channel: return

        entry = await self._get_audit_entry(role.guild, discord.AuditLogAction.role_create, role.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        now = int(discord.utils.utcnow().timestamp())
        desc = lang.LOG_ROLE_CREATE.format(mention=role.mention, name=role.name, actor=actor_str, now=now)

        embed = discord.Embed(description=desc, color=COLOR_CREATE)
        await self.send_log(channel, embed, "ROLE_CREATE", role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        channel = self.get_log_channel(role.guild)
        if not channel: return

        entry = await self._get_audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        now = int(discord.utils.utcnow().timestamp())
        desc = lang.LOG_ROLE_DELETE.format(name=role.name, actor=actor_str, now=now)

        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(channel, embed, "ROLE_DELETE", role.guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        channel = self.get_log_channel(before.guild)
        if not channel: return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` ➔ `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` ➔ `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"**Hoisted:** `{before.hoist}` ➔ `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` ➔ `{after.mentionable}`")

        if changes:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.role_update, after.id)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            now = int(discord.utils.utcnow().timestamp())
            
            desc = lang.LOG_ROLE_EDIT.format(mention=after.mention, actor=actor_str, now=now, changes="\n".join(changes))
            embed = discord.Embed(description=desc, color=COLOR_EDIT)
            await self.send_log(channel, embed, "ROLE_UPDATE", before.guild)

    #############################################
    #             CHANNEL EVENTS                #
    #############################################

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        log_channel = self.get_log_channel(channel.guild)
        if not log_channel: return

        entry = await self._get_audit_entry(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        now = int(discord.utils.utcnow().timestamp())
        is_cat = channel.type == discord.ChannelType.category
        entity = "Category" if is_cat else "Channel"
        display = channel.name if is_cat else channel.mention

        desc = lang.LOG_CHANNEL_CREATE.format(entity=entity, display=display, actor=actor_str, now=now)
        embed = discord.Embed(description=desc, color=COLOR_CREATE)
        await self.send_log(log_channel, embed, "CHANNEL_CREATE", channel.guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        log_channel = self.get_log_channel(channel.guild)
        if not log_channel: return

        entry = await self._get_audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        now = int(discord.utils.utcnow().timestamp())
        entity = "Category" if channel.type == discord.ChannelType.category else "Channel"

        desc = lang.LOG_CHANNEL_DELETE.format(entity=entity, name=channel.name, actor=actor_str, now=now)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(log_channel, embed, "CHANNEL_DELETE", channel.guild)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        log_channel = self.get_log_channel(before.guild)
        if not log_channel: return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `#{before.name}` ➔ `#{after.name}`")
        if hasattr(before, 'topic') and hasattr(after, 'topic') and before.topic != after.topic:
            changes.append(f"**Topic:** `{self.truncate(before.topic, 100) or 'None'}` ➔ `{self.truncate(after.topic, 100) or 'None'}`")
        if before.category != after.category:
            changes.append(f"**Category:** `{before.category.name if before.category else 'None'}` ➔ `{after.category.name if after.category else 'None'}`")
        if getattr(before, 'nsfw', False) != getattr(after, 'nsfw', False):
            changes.append(f"**NSFW:** `{before.nsfw}` ➔ `{after.nsfw}`")
        if getattr(before, 'slowmode_delay', 0) != getattr(after, 'slowmode_delay', 0):
            changes.append(f"**Slowmode:** `{before.slowmode_delay}s` ➔ `{after.slowmode_delay}s`")

        if changes:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.channel_update, after.id)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            now = int(discord.utils.utcnow().timestamp())
            
            is_cat = after.type == discord.ChannelType.category
            entity = "Category" if is_cat else "Channel"
            display = after.name if is_cat else after.mention

            desc = lang.LOG_CHANNEL_EDIT.format(entity=entity, display=display, actor=actor_str, now=now, changes="\n".join(changes))
            embed = discord.Embed(description=desc, color=COLOR_EDIT)
            await self.send_log(log_channel, embed, "CHANNEL_UPDATE", before.guild)

    #############################################
    #             THREAD EVENTS                 #
    #############################################

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        channel = self.get_log_channel(thread.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        actor_str = f" by {thread.owner.mention}" if thread.owner else ""
        desc = lang.LOG_THREAD_CREATE.format(mention=thread.mention, name=thread.name, actor=actor_str, now=now, parent=thread.parent.mention)
        embed = discord.Embed(description=desc, color=COLOR_CREATE)
        await self.send_log(channel, embed, "THREAD_CREATE", thread.guild)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread):
        channel = self.get_log_channel(thread.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        entry = await self._get_audit_entry(thread.guild, discord.AuditLogAction.thread_delete, thread.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        desc = lang.LOG_THREAD_DELETE.format(name=thread.name, actor=actor_str, now=now, parent=thread.parent.mention)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(channel, embed, "THREAD_DELETE", thread.guild)

    @commands.Cog.listener()
    async def on_thread_update(self, before, after):
        channel = self.get_log_channel(before.guild)
        if not channel: return
        
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `#{before.name}` ➔ `#{after.name}`")
        if before.archived != after.archived:
            changes.append(f"**Archived:** `{before.archived}` ➔ `{after.archived}`")
        if before.locked != after.locked:
            changes.append(f"**Locked:** `{before.locked}` ➔ `{after.locked}`")
            
        if changes:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.thread_update, after.id)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            now = int(discord.utils.utcnow().timestamp())
            
            desc = lang.LOG_THREAD_EDIT.format(mention=after.mention, actor=actor_str, now=now, changes="\n".join(changes))
            embed = discord.Embed(description=desc, color=COLOR_EDIT)
            await self.send_log(channel, embed, "THREAD_UPDATE", before.guild)

    #############################################
    #              VOICE EVENTS                 #
    #############################################

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        channel = self.get_log_channel(member.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        # Channel Join / Leave / Move
        if before.channel != after.channel:
            if before.channel is None and after.channel is not None:
                desc = lang.LOG_VOICE_JOIN.format(mention=member.mention, id=member.id, channel=after.channel.mention, now=now)
                color = COLOR_JOIN
                event_type = "VOICE_JOIN"
            elif before.channel is not None and after.channel is None:
                desc = lang.LOG_VOICE_LEAVE.format(mention=member.mention, id=member.id, channel=before.channel.mention, now=now)
                color = COLOR_LEAVE
                event_type = "VOICE_LEAVE"
            else:
                desc = lang.LOG_VOICE_MOVE.format(mention=member.mention, id=member.id, before=before.channel.mention, after=after.channel.mention, now=now)
                color = COLOR_INFO
                event_type = "VOICE_MOVE"
                
            embed = discord.Embed(description=desc, color=color)
            await self.send_log(channel, embed, event_type, member.guild)

        # Server Mute / Deafen
        if before.mute != after.mute:
            entry = await self._get_audit_entry(member.guild, discord.AuditLogAction.member_update, member.id)
            actor = entry.user.mention if entry and entry.user else "Unknown"
            action = "server muted" if after.mute else "server unmuted"
            desc = lang.LOG_VOICE_MUTE.format(mention=member.mention, id=member.id, action=action, actor=actor, channel=after.channel.mention, now=now)
            await self.send_log(channel, discord.Embed(description=desc, color=COLOR_EDIT if after.mute else COLOR_INFO), "VOICE_MUTE", member.guild)
            
        if before.deaf != after.deaf:
            entry = await self._get_audit_entry(member.guild, discord.AuditLogAction.member_update, member.id)
            actor = entry.user.mention if entry and entry.user else "Unknown"
            action = "server deafened" if after.deaf else "server undeafened"
            desc = lang.LOG_VOICE_DEAFEN.format(mention=member.mention, id=member.id, action=action, actor=actor, channel=after.channel.mention, now=now)
            await self.send_log(channel, discord.Embed(description=desc, color=COLOR_EDIT if after.deaf else COLOR_INFO), "VOICE_DEAFEN", member.guild)

        # Self Streaming / Video
        if before.self_stream != after.self_stream:
            action = "started" if after.self_stream else "stopped"
            desc = lang.LOG_VOICE_STREAM.format(mention=member.mention, id=member.id, action=action, channel=after.channel.mention, now=now)
            await self.send_log(channel, discord.Embed(description=desc, color=COLOR_INFO), "VOICE_STREAM", member.guild)

        if before.self_video != after.self_video:
            action = "turned on" if after.self_video else "turned off"
            desc = lang.LOG_VOICE_CAMERA.format(mention=member.mention, id=member.id, action=action, channel=after.channel.mention, now=now)
            await self.send_log(channel, discord.Embed(description=desc, color=COLOR_INFO), "VOICE_CAMERA", member.guild)

    #############################################
    #       EMOJI & STICKER EVENTS              #
    #############################################

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        channel = self.get_log_channel(guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        before_dict = {e.id: e for e in before}
        after_dict = {e.id: e for e in after}
        
        added = [e for e in after if e.id not in before_dict]
        removed = [e for e in before if e.id not in after_dict]
        edited = [e for e in after if e.id in before_dict and e.name != before_dict[e.id].name]

        if added:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.emoji_create)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for e in added:
                embed = discord.Embed(description=lang.LOG_EMOJI_CREATE.format(emoji=e, name=e.name, actor=actor_str, now=now), color=COLOR_CREATE)
                await self.send_log(channel, embed, "EMOJI_CREATE", guild)
            
        if removed:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.emoji_delete)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for e in removed:
                embed = discord.Embed(description=lang.LOG_EMOJI_DELETE.format(name=e.name, actor=actor_str, now=now), color=COLOR_DELETE)
                await self.send_log(channel, embed, "EMOJI_DELETE", guild)
            
        if edited:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.emoji_update)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for e in edited:
                old_e = before_dict[e.id]
                embed = discord.Embed(description=lang.LOG_EMOJI_EDIT.format(emoji=e, actor=actor_str, now=now, old=old_e.name, new=e.name), color=COLOR_EDIT)
                await self.send_log(channel, embed, "EMOJI_UPDATE", guild)

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        channel = self.get_log_channel(guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        before_dict = {s.id: s for s in before}
        after_dict = {s.id: s for s in after}
        
        added = [s for s in after if s.id not in before_dict]
        removed = [s for s in before if s.id not in after_dict]
        edited = [s for s in after if s.id in before_dict and s.name != before_dict[s.id].name]

        if added:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.sticker_create)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for s in added:
                desc = lang.LOG_STICKER_CREATE.format(name=s.name, actor=actor_str, now=now)
                embed = discord.Embed(description=desc, color=COLOR_CREATE)
                embed.set_image(url=s.url)
                await self.send_log(channel, embed, "STICKER_CREATE", guild)
                
        if removed:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.sticker_delete)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for s in removed:
                desc = lang.LOG_STICKER_DELETE.format(name=s.name, actor=actor_str, now=now)
                embed = discord.Embed(description=desc, color=COLOR_DELETE)
                await self.send_log(channel, embed, "STICKER_DELETE", guild)
                
        if edited:
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.sticker_update)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            for s in edited:
                old_s = before_dict[s.id]
                desc = lang.LOG_STICKER_EDIT.format(name=s.name, actor=actor_str, now=now, old=old_s.name, new=s.name)
                embed = discord.Embed(description=desc, color=COLOR_EDIT)
                await self.send_log(channel, embed, "STICKER_UPDATE", guild)

    #############################################
    #          SCHEDULED EVENTS                 #
    #############################################

    @commands.Cog.listener()
    async def on_guild_scheduled_event_create(self, event):
        channel = self.get_log_channel(event.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        actor_str = f" by {event.creator.mention}" if event.creator else ""
        desc = lang.LOG_EVENT_CREATE.format(name=event.name, actor=actor_str, now=now)
        embed = discord.Embed(description=desc, color=COLOR_CREATE)
        
        if event.channel:
            embed.add_field(name="Location", value=event.channel.mention, inline=True)
        if event.scheduled_start_time:
            embed.add_field(name="Start Time", value=f"<t:{int(event.scheduled_start_time.timestamp())}:f>", inline=True)
            
        await self.send_log(channel, embed, "EVENT_CREATE", event.guild)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_delete(self, event):
        channel = self.get_log_channel(event.guild)
        if not channel: return
        now = int(discord.utils.utcnow().timestamp())
        
        entry = await self._get_audit_entry(event.guild, discord.AuditLogAction.guild_scheduled_event_delete, event.id)
        actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
        
        desc = lang.LOG_EVENT_DELETE.format(name=event.name, actor=actor_str, now=now)
        embed = discord.Embed(description=desc, color=COLOR_DELETE)
        await self.send_log(channel, embed, "EVENT_DELETE", event.guild)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_update(self, before, after):
        channel = self.get_log_channel(before.guild)
        if not channel: return
        
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` ➔ `{after.name}`")
        if before.description != after.description:
            changes.append(f"**Description updated**")
        if before.status != after.status:
            changes.append(f"**Status:** `{before.status.name}` ➔ `{after.status.name}`")
            
        if changes:
            entry = await self._get_audit_entry(after.guild, discord.AuditLogAction.guild_scheduled_event_update, after.id)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            now = int(discord.utils.utcnow().timestamp())
            
            desc = lang.LOG_EVENT_EDIT.format(name=after.name, actor=actor_str, now=now, changes="\n".join(changes))
            embed = discord.Embed(description=desc, color=COLOR_EDIT)
            await self.send_log(channel, embed, "EVENT_UPDATE", before.guild)


    #############################################
    #             SERVER EVENTS                 #
    #############################################

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        channel = self.get_log_channel(before)
        if not channel: return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` ➔ `{after.name}`")
        if before.owner_id != after.owner_id:
            changes.append(f"**Owner:** <@{before.owner_id}> ➔ <@{after.owner_id}>")
        if before.verification_level != after.verification_level:
            changes.append(f"**Verification:** `{before.verification_level.name}` ➔ `{after.verification_level.name}`")
        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append(f"**Content Filter:** `{before.explicit_content_filter.name}` ➔ `{after.explicit_content_filter.name}`")
        if before.afk_channel != after.afk_channel:
            changes.append(f"**AFK Channel:** {before.afk_channel.mention if before.afk_channel else 'None'} ➔ {after.afk_channel.mention if after.afk_channel else 'None'}")
        if before.system_channel != after.system_channel:
            changes.append(f"**System Channel:** {before.system_channel.mention if before.system_channel else 'None'} ➔ {after.system_channel.mention if after.system_channel else 'None'}")

        if changes:
            entry = await self._get_audit_entry(after, discord.AuditLogAction.guild_update)
            actor_str = f" by {entry.user.mention}" if entry and entry.user else ""
            now = int(discord.utils.utcnow().timestamp())
            
            desc = lang.LOG_GUILD_UPDATE.format(actor=actor_str, now=now, changes="\n".join(changes))
            embed = discord.Embed(description=desc, color=COLOR_EDIT)
            await self.send_log(channel, embed, "GUILD_UPDATE", before)


async def setup(bot):
    await bot.add_cog(Log(bot))