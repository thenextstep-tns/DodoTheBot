import logging
from typing import Optional

import disnake
from disnake.ext import commands

import config_py

logger = logging.getLogger("event_tracker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Constants matching category_manager
BEHAVIOR_MESSAGES = "messages"
BEHAVIOR_IMAGES = "image_uploads"
BEHAVIOR_REACTIONS = "reaction_added"


class EventTracker(commands.Cog, name="event_tracker"):
    """Listens for tracked behaviors in configured channels and logs them."""
    
    def __init__(self, bot):
        self.bot = bot

    def _get_channel_config(self, channel_id: int) -> Optional[dict]:
        """Retrieves channel tracking configuration from DB."""
        return config_py.botServerRoles.find_one({"channel_id": str(channel_id)})

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot:
            return

        config = self._get_channel_config(message.channel.id)
        if not config or not config.get("category"):
            return

        tracked_behaviors = config.get("tracked_behaviors", [])
        
        # Check for image uploads
        if BEHAVIOR_IMAGES in tracked_behaviors and message.attachments:
            # Simple check for image content types
            has_image = any(att.content_type and att.content_type.startswith("image/") for att in message.attachments)
            if has_image:
                logger.info(
                    f"[EVENT: {BEHAVIOR_IMAGES}] User {message.author.id} uploaded an image "
                    f"in channel {message.channel.id} (Category: {config['category']})"
                )
        
        # Check for standard messages
        elif BEHAVIOR_MESSAGES in tracked_behaviors:
            logger.info(
                f"[EVENT: {BEHAVIOR_MESSAGES}] User {message.author.id} sent a message "
                f"in channel {message.channel.id} (Category: {config['category']})"
            )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent):
        # Ignore bot reactions to prevent loop/spam
        if payload.user_id == self.bot.user.id:
            return

        config = self._get_channel_config(payload.channel_id)
        if not config or not config.get("category"):
            return

        tracked_behaviors = config.get("tracked_behaviors", [])
        
        if BEHAVIOR_REACTIONS in tracked_behaviors:
             logger.info(
                f"[EVENT: {BEHAVIOR_REACTIONS}] User {payload.user_id} reacted with {payload.emoji.name} "
                f"in channel {payload.channel_id} (Category: {config['category']})"
            )


def setup(bot):
    bot.add_cog(EventTracker(bot))