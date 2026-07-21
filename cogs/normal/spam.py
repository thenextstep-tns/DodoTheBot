import disnake
import time
import asyncio
from disnake.ext import commands, tasks
from collections import defaultdict
import config_py

# =========================================================
# ANTISPAM BOT PROTECTOR (COG EDITION)
# =========================================================

class SpamProtector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Store message data: {user_id: [(timestamp, channel_id), ...]}
        self._user_msg_data = defaultdict(list)
        # Start the background cleanup task
        self.background_ram_cleanup.start()
        print("DEBUG: Anti-Spam Cog loaded and RAM cleanup task started.")

    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.background_ram_cleanup.cancel()
        print("DEBUG: Anti-Spam Cog unloaded.")

    @tasks.loop(seconds=30)
    async def background_ram_cleanup(self):
        """
        Background task to clear memory of users who are no longer active.
        """
        try:
            # Load all windows to find the maximum time we need to keep data
            spam_window = getattr(config_py, "SPAM_TIME_WINDOW", 2.0)
            multi_window = getattr(config_py, "MULTI_CHANNEL_WINDOW", 1.0)
            max_window = max(spam_window, multi_window)
            
            current_time = time.time()
            users_in_memory = list(self._user_msg_data.keys())
            
            for i, user_id in enumerate(users_in_memory):
                if i % 100 == 0: await asyncio.sleep(0)

                # Filter keeps only recent messages based on the largest window
                recent_data = [
                    (t, c) for (t, c) in self._user_msg_data[user_id] 
                    if current_time - t <= max_window
                ]
                
                if not recent_data:
                    del self._user_msg_data[user_id]
                else:
                    self._user_msg_data[user_id] = recent_data
                    
        except Exception as e:
            print(f"ERROR: Error in spam RAM cleanup task: {e}")

    @background_ram_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def _ban_and_alert(self, message, reason_log, reason_public):
        """Helper function to ban a user and send an alert."""
        guild = message.guild
        member = message.author
        alert_channel_id = getattr(config_py, "ALERT_CHANNEL_ID", None)
        
        if alert_channel_id:
            alert_channel_id = int(alert_channel_id)

        try:
            # Ban and purge
            await guild.ban(
                member, 
                delete_message_days=1, 
                reason=reason_log
            )
            print(f"DEBUG: Banned spammer {member.name} - Reason: {reason_log}")

            if alert_channel_id:
                alert_channel = guild.get_channel(alert_channel_id)
                if alert_channel:
                    await alert_channel.send(
                        f"🛡️ **Anti-Spam Triggered!**\n"
                        f"I have banned {member.mention} (`{member.id}`).\n"
                        f"**Reason:** {reason_public}\n"
                        f"Their recent messages have been purged."
                    )
            
            # Clear memory
            if member.id in self._user_msg_data:
                del self._user_msg_data[member.id]
            return True

        except disnake.Forbidden:
            print(f"ERROR: Lack permission to ban spammer {member.name}")
            return False
        except disnake.HTTPException as e:
            print(f"ERROR: HTTP error banning spammer: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        """
        Listener to detect and ban spam bots.
        """
        # 1. Ignore bots
        if message.author.bot:
            return

        # 2. Ignore Direct Messages
        if not message.guild:
            return

        # 3. Security Bypass: Ignore Admins
        # I HAVE COMMENTED THIS OUT SO YOU CAN TEST IT. 
        # UNCOMMENT IT WHEN YOU ARE DONE TESTING TO PROTECT ADMINS.
        if getattr(message.author.guild_permissions, "administrator", False):
            return

        # Load configuration
        try:
            # Standard Rate Limit
            spam_threshold = getattr(config_py, "SPAM_THRESHOLD", 3)
            spam_window = getattr(config_py, "SPAM_TIME_WINDOW", 2.0)
            
            # Multi-Channel Limit
            multi_threshold = getattr(config_py, "MULTI_CHANNEL_THRESHOLD", 3)
            multi_window = getattr(config_py, "MULTI_CHANNEL_WINDOW", 1.0)
            
        except AttributeError:
            # Defaults
            spam_threshold, spam_window = 5, 5.0
            multi_threshold, multi_window = 3, 1.0

        user_id = message.author.id
        current_time = time.time()
        
        # Calculate max window to clean up lists efficiently
        max_window = max(spam_window, multi_window)

        # 4. Record timestamp AND channel
        self._user_msg_data[user_id].append((current_time, message.channel.id))

        # 5. Filter list (keep data relevant to the longest check)
        self._user_msg_data[user_id] = [
            (t, c) for (t, c) in self._user_msg_data[user_id] 
            if current_time - t <= max_window
        ]
        
        user_data = self._user_msg_data[user_id]

        # --- CHECK 1: Multi-Channel Spam ---
        # "3 channels within 1s"
        msgs_in_multi_window = [
            c for (t, c) in user_data 
            if current_time - t <= multi_window
        ]
        unique_channels = len(set(msgs_in_multi_window))
        
        if unique_channels >= multi_threshold:
            print(f"DEBUG: Multi-channel spam detected from {message.author.name}")
            await self._ban_and_alert(
                message, 
                reason_log="Anti-Spam: Multi-channel spam detected",
                reason_public=f"Spamming across {unique_channels} channels in {multi_window}s."
            )
            return

        # --- CHECK 2: Volume Spam ---
        # "5 messages within 5s"
        msgs_in_spam_window = [
            t for (t, c) in user_data 
            if current_time - t <= spam_window
        ]
        
        if len(msgs_in_spam_window) > spam_threshold:
            print(f"DEBUG: Volume spam detected from {message.author.name}")
            await self._ban_and_alert(
                message,
                reason_log="Anti-Spam: Rate limit exceeded",
                reason_public=f"Sending {len(msgs_in_spam_window)} messages in {spam_window}s."
            )
            return
def setup(bot):
    bot.add_cog(SpamProtector(bot))