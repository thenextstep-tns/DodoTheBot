"""
Event tracker cog — logs configured "behaviors" (messages, image uploads,
reactions) in channels that have tracking set up in the database.

Note: the companion configuration cog was removed, so this only does anything
for channels that already have a tracking document in ``botServerRoles``.
"""

from typing import Optional

import discord
from discord.ext import commands

import config_py

BEHAVIOR_MESSAGES = "messages"
BEHAVIOR_IMAGES = "image_uploads"
BEHAVIOR_REACTIONS = "reaction_added"


class EventTracker(commands.Cog, name="event_tracker"):
    """Listens for tracked behaviors in configured channels and logs them."""

    def __init__(self, bot):
        self.bot = bot

    def _get_channel_config(self, channel_id: int) -> Optional[dict]:
        """Return a channel's tracking configuration from the database, if any."""
        return config_py.botServerRoles.find_one({"channel_id": str(channel_id)})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        config = self._get_channel_config(message.channel.id)
        if not config or not config.get("category"):
            return

        tracked = config.get("tracked_behaviors", [])
        if BEHAVIOR_IMAGES in tracked and message.attachments:
            if any(att.content_type and att.content_type.startswith("image/") for att in message.attachments):
                self.bot.logger.info(
                    f"[EVENT: {BEHAVIOR_IMAGES}] User {message.author.id} uploaded an image "
                    f"in channel {message.channel.id} (Category: {config['category']})"
                )
        elif BEHAVIOR_MESSAGES in tracked:
            self.bot.logger.info(
                f"[EVENT: {BEHAVIOR_MESSAGES}] User {message.author.id} sent a message "
                f"in channel {message.channel.id} (Category: {config['category']})"
            )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == self.bot.user.id:
            return
        config = self._get_channel_config(payload.channel_id)
        if not config or not config.get("category"):
            return
        if BEHAVIOR_REACTIONS in config.get("tracked_behaviors", []):
            self.bot.logger.info(
                f"[EVENT: {BEHAVIOR_REACTIONS}] User {payload.user_id} reacted with {payload.emoji.name} "
                f"in channel {payload.channel_id} (Category: {config['category']})"
            )


async def setup(bot):
    await bot.add_cog(EventTracker(bot))
