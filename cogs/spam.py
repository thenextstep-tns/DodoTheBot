"""
Anti-spam cog — bans users who post too fast or across too many channels at
once, alerts the mod channel, and keeps a small rolling per-user message log in
memory (periodically pruned).
"""

import asyncio
import time
from collections import defaultdict

import discord
from discord.ext import commands, tasks

import lang

_DAY_IN_SECONDS = 86400


class SpamProtector(commands.Cog, name="spam"):
    """Detects and bans spam bots based on message rate and channel spread."""

    def __init__(self, bot):
        self.bot = bot
        # {user_id: [(timestamp, channel_id), ...]}
        self._user_msg_data: dict[int, list[tuple[float, int]]] = defaultdict(list)
        # Cross-post detection: {user_id: [(timestamp, channel_id, signature), ...]}
        self._dup_data: dict[int, list[tuple[float, int, tuple]]] = defaultdict(list)
        self.background_ram_cleanup.start()

    @staticmethod
    def _signature(message: discord.Message) -> tuple:
        """A content fingerprint: normalised text + each attachment's name & size.
        Reposting the same image/text across channels yields the same signature."""
        attachments = tuple(sorted((a.filename, a.size) for a in message.attachments))
        return (message.content.strip().lower(), attachments)

    @staticmethod
    def _is_substantial(signature: tuple, min_len: int) -> bool:
        """Only treat a message as cross-post-worthy if it has attachments or enough
        text — avoids flagging a user saying 'gg' in a few channels."""
        content, attachments = signature
        return bool(attachments) or len(content) >= min_len

    def cog_unload(self) -> None:
        self.background_ram_cleanup.cancel()

    @tasks.loop(seconds=30)
    async def background_ram_cleanup(self) -> None:
        """Drop message records that are older than the longest detection window."""
        try:
            # Use the widest window across guilds so no guild's records are pruned early.
            max_window = max(
                self.bot.params.get(None, "spam_time_window"),
                self.bot.params.get(None, "multi_channel_window"),
            )
            now = time.time()
            for index, user_id in enumerate(list(self._user_msg_data.keys())):
                if index % 100 == 0:
                    await asyncio.sleep(0)
                recent = [(t, c) for (t, c) in self._user_msg_data[user_id] if now - t <= max_window]
                if recent:
                    self._user_msg_data[user_id] = recent
                else:
                    del self._user_msg_data[user_id]
            # Cross-post records use their own (longer) window.
            dup_window = self.bot.params.get(None, "duplicate_window")
            for user_id in list(self._dup_data.keys()):
                recent = [r for r in self._dup_data[user_id] if now - r[0] <= dup_window]
                if recent:
                    self._dup_data[user_id] = recent
                else:
                    del self._dup_data[user_id]
        except Exception as error:
            self.bot.logger.error(f"Error in spam RAM cleanup task: {error}")

    @background_ram_cleanup.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    async def _ban_and_alert(self, message: discord.Message, reason_log: str, reason_public: str) -> bool:
        """Ban the message author, purge a day of their messages, and alert the mods."""
        guild, member = message.guild, message.author
        try:
            await guild.ban(member, delete_message_seconds=_DAY_IN_SECONDS, reason=reason_log)
            self.bot.logger.info(f"Banned spammer {member} — {reason_log}")

            alert_channel_id = self.bot.guild_config.get(guild.id, "ALERT_CHANNEL_ID")
            if alert_channel_id and (alert_channel := guild.get_channel(int(alert_channel_id))):
                await alert_channel.send(
                    lang.SPAM_ALERT.format(mention=member.mention, user_id=member.id, reason=reason_public)
                )
            self._user_msg_data.pop(member.id, None)
            return True
        except discord.Forbidden:
            self.bot.logger.error(f"Lack permission to ban spammer {member}")
            return False
        except discord.HTTPException as error:
            self.bot.logger.error(f"HTTP error banning spammer: {error}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Record each message and ban on volume or multi-channel spam."""
        if message.author.bot or not message.guild:
            return
        if not self.bot.visibility.feature_active(message.guild.id, "spam_autoban", "spam"):
            return
        if getattr(message.author.guild_permissions, "administrator", False):
            return

        guild_id = message.guild.id
        spam_threshold = self.bot.params.get(guild_id, "spam_threshold")
        spam_window = self.bot.params.get(guild_id, "spam_time_window")
        multi_threshold = self.bot.params.get(guild_id, "multi_channel_threshold")
        multi_window = self.bot.params.get(guild_id, "multi_channel_window")
        max_window = max(spam_window, multi_window)

        user_id = message.author.id
        now = time.time()
        self._user_msg_data[user_id].append((now, message.channel.id))
        self._user_msg_data[user_id] = [
            (t, c) for (t, c) in self._user_msg_data[user_id] if now - t <= max_window
        ]
        user_data = self._user_msg_data[user_id]

        # Multi-channel spam: posting across many channels within a short window.
        unique_channels = len({c for (t, c) in user_data if now - t <= multi_window})
        if unique_channels >= multi_threshold:
            await self._ban_and_alert(
                message,
                reason_log="Anti-Spam: Multi-channel spam detected",
                reason_public=f"Spamming across {unique_channels} channels in {multi_window}s.",
            )
            return

        # Cross-post spam: the *same* message (text + attachments) posted across
        # several channels over a longer window — the classic image cross-poster.
        dup_window = self.bot.params.get(guild_id, "duplicate_window")
        dup_threshold = self.bot.params.get(guild_id, "duplicate_channel_threshold")
        dup_min_len = self.bot.params.get(guild_id, "duplicate_min_len")
        signature = self._signature(message)
        if self._is_substantial(signature, dup_min_len):
            self._dup_data[user_id].append((now, message.channel.id, signature))
            self._dup_data[user_id] = [r for r in self._dup_data[user_id] if now - r[0] <= dup_window]
            dup_channels = {c for (t, c, sig) in self._dup_data[user_id] if sig == signature}
            if len(dup_channels) >= dup_threshold:
                await self._ban_and_alert(
                    message,
                    reason_log="Anti-Spam: Cross-post (duplicate content) detected",
                    reason_public=f"Posted the same message across {len(dup_channels)} channels in {dup_window}s.",
                )
                self._dup_data.pop(user_id, None)
                return

        # Volume spam: too many messages within the rate window.
        recent_count = sum(1 for (t, c) in user_data if now - t <= spam_window)
        if recent_count > spam_threshold:
            await self._ban_and_alert(
                message,
                reason_log="Anti-Spam: Rate limit exceeded",
                reason_public=f"Sending {recent_count} messages in {spam_window}s.",
            )


async def setup(bot):
    await bot.add_cog(SpamProtector(bot))
