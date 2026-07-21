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

import config_py
import lang

_DAY_IN_SECONDS = 86400


class SpamProtector(commands.Cog, name="spam"):
    """Detects and bans spam bots based on message rate and channel spread."""

    def __init__(self, bot):
        self.bot = bot
        # {user_id: [(timestamp, channel_id), ...]}
        self._user_msg_data: dict[int, list[tuple[float, int]]] = defaultdict(list)
        self.background_ram_cleanup.start()

    def cog_unload(self) -> None:
        self.background_ram_cleanup.cancel()

    @tasks.loop(seconds=30)
    async def background_ram_cleanup(self) -> None:
        """Drop message records that are older than the longest detection window."""
        try:
            max_window = max(
                getattr(config_py, "SPAM_TIME_WINDOW", 2.0),
                getattr(config_py, "MULTI_CHANNEL_WINDOW", 1.0),
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

            alert_channel_id = getattr(config_py, "ALERT_CHANNEL_ID", None)
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
        if getattr(message.author.guild_permissions, "administrator", False):
            return

        spam_threshold = getattr(config_py, "SPAM_THRESHOLD", 3)
        spam_window = getattr(config_py, "SPAM_TIME_WINDOW", 2.0)
        multi_threshold = getattr(config_py, "MULTI_CHANNEL_THRESHOLD", 3)
        multi_window = getattr(config_py, "MULTI_CHANNEL_WINDOW", 1.0)
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
