import os
import sys
import json
import disnake
from disnake.ext import commands
import random
import markovify
import re

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

class MessageImitator(commands.Cog, name="MessageImitator"):
    def __init__(self, bot):
        self.bot = bot

    # Helper function to remove any symbols that can ping people
    def remove_ping_symbols(self, text):
        text = re.sub(r'[@#&!<>]', '', text)  # Remove common ping-related symbols
        text = re.sub(r'@everyone|@here', '', text)  # Remove special mentions
        return text

    @commands.command()
    async def imitate(self, ctx, user: disnake.User = None):
        """Imitate the specified user's messages found in public channels"""
        if user is None:
            user = ctx.author

        # Send a quick "thinking" message
        thinking_message = await ctx.send("🤔 Hmmmm let me think... ")

        # Fetch all messages from the specified user that were sent in public channels
        messages_collection = config_py.messages
        user_messages_cursor = messages_collection.find({
            "author": user.id,
            "channel": {"$in": config_py.public_channels}
        }).limit(10000)

        # Convert cursor to a list of message texts
        messages_list = [msg['message'] for msg in user_messages_cursor]

        # If no messages found, bail out
        if not messages_list:
            await thinking_message.edit(content=f"No public messages found for user {user.display_name}.")
            return

        # Shuffle messages to introduce randomness in how they're concatenated
        random.shuffle(messages_list)

        # ---- RANDOM PARAMS FOR MARKOVIFY ----
        state_size = random.choice([1, 2, 3, 4])
        max_overlap_ratio = random.uniform(0.3, 0.9)
        max_overlap_total = random.randint(5, 15)
        min_words = random.randint(10, 24)
        max_words = random.randint(25, 50)

        # Grab the context of the current command, cleaned up to remove pings
        context_message = ctx.message.content
        cleaned_context_message = self.remove_ping_symbols(context_message)

        # Combine the user’s message history and the current context message
        combined_messages = ' '.join(
            [cleaned_context_message] +
            [self.remove_ping_symbols(msg) for msg in messages_list]
        )

        # Build a Markov chain model based on the combined text
        text_model = markovify.Text(combined_messages, state_size=state_size)

        # Try to generate a coherent sentence multiple times
        imitation_message = None
        for _ in range(150):
            imitation_message = text_model.make_sentence(
                tries=1000,
                max_overlap_ratio=max_overlap_ratio,
                max_overlap_total=max_overlap_total,
                min_words=min_words,
                max_words=max_words,
                test_output=False  # set to True if you want to avoid direct duplicates
            )
            if imitation_message:
                break

        if not imitation_message:
            await thinking_message.edit(content=f"Unable to generate a coherent message for {user.display_name}.")
            return
        
        # --- CREATE AN EMBED FOR THE IMITATION MESSAGE ---
        embed = disnake.Embed(
            description=imitation_message,
            color=disnake.Color.random()
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

        # Update the "thinking" message to show final result
        await thinking_message.edit(
            content=f"Hi, my name is {user.display_name}, and this is what I think:",
            embed=embed
        )

def setup(bot):
    bot.add_cog(MessageImitator(bot))
