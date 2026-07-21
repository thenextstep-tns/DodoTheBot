import disnake
import json
import os
import random
import asyncio
from disnake.ext import commands
import requests
import openai

# Load config
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

# OpenAI Proxy API Key and Base URL
openai.api_key = config_py.PROXY_API
openai.api_base = "https://api.proxyapi.ru/openai/v1"

class WaifuCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.waifus_db = config_py.waifus  # Collection reference for storing waifus
        self.waifu_classes = [
            {"name": "Motivator", "description": "This waifu excels at boosting your morale and sending encouraging daily messages!", "perk": "Increases your daily rewards and sends positive notes."},
            {"name": "Racer", "description": "A competitive spirit who loves speed! She makes your mice extra fast in races.", "perk": "Grants a speed boost to your mice during races."},
            {"name": "Fisher", "description": "A quiet and patient companion who is great at fishing rare items.", "perk": "Improves your chances of fishing out treasures."},
            {"name": "Collector", "description": "This waifu loves finding and collecting pets! She’s skilled at catching elusive cats and dogs.", "perk": "Increases your chances of successfully claiming pets."},
            {"name": "Strategist", "description": "A calm and collected waifu who helps you think clearly during duels and games.", "perk": "Improves your dice rolls and parse results."},
        ]

    async def ensure_waifu_defaults(self, waifu):
        """
        Ensure waifu has all necessary default attributes.
        If not present, add them and update the database.
        """
        default_fields = {
            'affection_points': 500,
            'relationship_stage': 'Acquaintance',
            'affinity_trait': random.choice(["Clingy", "Stoic", "Energetic", "Kinky", "Gentle"]),
            'catchphrase': "No catchphrase yet!",
            'summoned_by_name': "Unknown",
            'claimed_at': asyncio.get_event_loop().time(),
        }

        update_needed = False
        for key, default_value in default_fields.items():
            if key not in waifu:
                waifu[key] = default_value
                update_needed = True

        if update_needed:
            self.waifus_db.update_one({'_id': waifu['_id']}, {'$set': waifu})

    async def generate_catchphrase(self, waifu_class):
        """
        Generates a catchphrase for the waifu based on her class using OpenAI proxy API.
        """
        prompt = (
            f"You are a waifu personality expert. Based on the following waifu characteristics, generate a short, humorous, and unique catchphrase that she would say:\n\n"
            f"Waifu Class: {waifu_class['name']}\n"
            f"Description: {waifu_class['description']}\n"
            f"Perk: {waifu_class['perk']}\n\n"
            "The catchphrase should be endearing, fun, and characteristic of her personality. But sometimes contain darker or goofier undertones."
        )

        try:
            chat_completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                temperature=0.8,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant generating catchphrases for waifus."},
                    {"role": "user", "content": prompt}
                ]
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating catchphrase: {e}")
            return "I'm your waifu now! Let's go on an adventure!"

    @commands.command()
    async def waifu(self, ctx):
        """Summon a random waifu."""
        # Fetch random waifu from an API
        response = requests.get('https://api.waifu.pics/sfw/waifu')
        waifu_data = response.json()
        waifu_image_url = waifu_data['url']

        # Check if the waifu's image URL already exists in the database
        while self.waifus_db.find_one({'image_url': waifu_image_url}):
            response = requests.get('https://api.waifu.pics/sfw/waifu')
            waifu_data = response.json()
            waifu_image_url = waifu_data['url']

        # Randomly select a personality from the waifu_classes
        chosen_personality = random.choice(self.waifu_classes)

        # Generate catchphrase using OpenAI API
        catchphrase = await self.generate_catchphrase(chosen_personality)

        # Create embed with waifu image and personality description
        waifu_embed = disnake.Embed(
            title="You've summoned a waifu!",
            description=f"**Class:** {chosen_personality['name']}\n{chosen_personality['description']}\n**Perk:** {chosen_personality['perk']}\n**Catchphrase:** \"{catchphrase}\"",
            color=disnake.Color.purple()
        )
        waifu_embed.set_image(url=waifu_image_url)
        waifu_message = await ctx.send(embed=waifu_embed)

        # Add reactions
        await waifu_message.add_reaction('👍')
        await waifu_message.add_reaction('👎')
        await waifu_message.add_reaction('🚫')

        def reaction_check(reaction, user):
            return reaction.message.id == waifu_message.id and not user.bot

        try:
            reaction, user = await self.bot.wait_for('reaction_add', check=reaction_check, timeout=60)
            if str(reaction.emoji) == '👍':
                await ctx.send(f"{user.display_name} has claimed this waifu! What will you name her? Hurry up, ANYONE can give her a name!")
                await waifu_message.clear_reactions()

                def name_check(msg):
                    return msg.channel == ctx.channel and len(msg.content.strip()) > 0

                try:
                    name_response = await self.bot.wait_for('message', check=name_check, timeout=30)
                    waifu_name = name_response.content.strip()

                    # Save waifu to the database with summoner information
                    waifu_entry = {
                        'user_id': user.id,
                        'waifu_name': waifu_name,
                        'class': chosen_personality['name'],
                        'description': chosen_personality['description'],
                        'perk': chosen_personality['perk'],
                        'catchphrase': catchphrase,
                        'image_url': waifu_image_url,
                        'claimed_at': asyncio.get_event_loop().time(),
                        'summoned_by_name': ctx.author.display_name,
                        'affection_points': 499,
                        'relationship_stage': 'Acquaintance',
                        'affinity_trait': random.choice(["Clingy", "Stoic", "Energetic", "Kinky", "Gentle"])
                    }
                    self.waifus_db.insert_one(waifu_entry)

                    await ctx.send(f"Congratulations {user.mention}! {waifu_name} is now by your side!")
                except asyncio.TimeoutError:
                    await ctx.send(f"{user.mention} took too long to name the waifu. She ran away in disappointment.")
            elif str(reaction.emoji) == '👎':
                await waifu_message.delete()
                await ctx.invoke(self.waifu)
            elif str(reaction.emoji) == '🚫':
                await waifu_message.delete()
                await ctx.send("Command stopped. No more waifus for now!")
        except asyncio.TimeoutError:
            await waifu_message.delete()
            await ctx.send("The waifu got bored and left!")

    @commands.command()
    
    async def callwaifus(self, ctx):
        """Show all waifus owned by the user."""
        waifus = list(self.waifus_db.find({'user_id': ctx.author.id}))
        if not waifus:
            await ctx.send("You don't have any waifus yet!")
            return

        current_index = 0

        def get_waifu_embed(index):
            waifu = waifus[index]
            catchphrase = waifu.get('catchphrase', "This waifu has no catchphrase... yet!")
            affinity_trait = waifu.get('affinity_trait', "Unknown")
            affection_points = waifu.get('affection_points', 500)
            relationship_stage = waifu.get('relationship_stage', "Acquaintance")

            embed = disnake.Embed(
                title=f"Waifu: {waifu['waifu_name']}",
                description=(
                    f"**Class:** {waifu['class']}\n"
                    f"**Catchphrase:** {catchphrase}\n"
                    f"**Affinity Trait:** {affinity_trait}\n"
                    f"**Affection Points:** {affection_points}/1000\n"
                    f"**Relationship Stage:** {relationship_stage}"
                ),
                color=disnake.Color.purple()
            )
            embed.set_image(url=waifu['image_url'])
            return embed

        # Send the first waifu
        embed = get_waifu_embed(current_index)
        message = await ctx.send(embed=embed)
        await message.add_reaction('⬅️')
        await message.add_reaction('➡️')

        def scroll_check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️'] and reaction.message.id == message.id

        while True:
            try:
                reaction, _ = await self.bot.wait_for('reaction_add', check=scroll_check, timeout=30)
                await message.remove_reaction(reaction.emoji, ctx.author)

                if str(reaction.emoji) == '⬅️':
                    current_index = (current_index - 1) % len(waifus)
                else:
                    current_index = (current_index + 1) % len(waifus)

                # Edit the existing message with the new embed
                new_embed = get_waifu_embed(current_index)
                await message.edit(embed=new_embed)

            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

    async def update_affection(self, waifu, action):
        """
        Updates affection points based on the waifu's personality type and action.
        """
        affection_changes = {
            "Pat": 1,
            "Slap": -2,
            "Feed": 3,
            "Hold hands": 5,
            "Release": -1000
        }

        personality_modifiers = {
            "Clingy": {"Pat": 5, "Slap": -5, "Feed": 4, "Hold hands": 7},
            "Stoic": {"Pat": 1, "Slap": -1, "Feed": 4, "Hold hands": 2},
            "Kinky": {"Pat": -1, "Slap": 3, "Feed": 1, "Hold hands": -5},
            "Energetic": {"Pat": 2, "Slap": -3, "Feed": 2, "Hold hands": 3},
            "Gentle": {"Pat": 3, "Slap": -4, "Feed": 4, "Hold hands": 5}
        }

        trait = waifu.get("affinity_trait", "Gentle")
        base_change = affection_changes.get(action, 0)
        trait_modifier = personality_modifiers.get(trait, {}).get(action, 0)

        affection_points = waifu.get('affection_points', 500) + base_change + trait_modifier
        affection_points = max(0, min(1000, affection_points))

        if affection_points == 1000:
            stage = "Soulmate"
        elif affection_points >= 700:
            stage = "Significant Other"
        elif affection_points >= 700:
            stage = "Close Companion"
        elif affection_points >= 500:
            stage = "Friend"
        elif affection_points >= 300:
            stage = "Acquaintance"
        else:
            stage = "Distant"

        waifu['affection_points'] = affection_points
        waifu['relationship_stage'] = stage
        self.waifus_db.update_one({'_id': waifu['_id']}, {'$set': waifu})

        return affection_points, stage

    @commands.command()
    async def call(self, ctx, *, waifu_name: str):
        """Summon a waifu by name and interact with her."""
        waifu = self.waifus_db.find_one({'user_id': ctx.author.id, 'waifu_name': waifu_name})
        if not waifu:
            await ctx.send(f"You don't have a waifu named '{waifu_name}'!")
            return

        # Get bucket for cooldown check
        bucket = ctx.command._buckets.get_bucket(ctx)
        tokens = bucket.get_tokens() if bucket else None

        if tokens is not None and tokens == 0:
            retry_after = bucket.get_retry_after() if bucket else 0
            await ctx.send(f"{ctx.author.mention}, {waifu_name} needs some me-time! Please wait {round(retry_after, 2)} seconds before calling her again.")
            return

        # Apply cooldown only after successful waifu summoning
        if bucket:
            bucket.update_rate_limit()

        # Ensure waifu has necessary attributes
        await self.ensure_waifu_defaults(waifu)

        affection_points = waifu.get('affection_points', 500)
        relationship_stage = waifu.get('relationship_stage', 'Acquaintance')
        affinity_trait = waifu.get('affinity_trait', "Unknown")

        embed = disnake.Embed(
            title=f"{waifu_name} is summoned!",
            description=(
                f"**Relationship Status:**\n"
                f"**Affection Points:** {affection_points}/1000\n"
                f"**Stage:** {relationship_stage}\n"
                f"**Trait:** {affinity_trait}\n\n"
                "Choose an action:\n1. 🥰 Pat\n2. 👋 Slap\n3. 🎁 Feed\n4. ✋ Hold hands\n5. 🕊️ Release\n6. 🚫 Shoo away"
            ),
            color=disnake.Color.magenta()
        )
        embed.set_image(url=waifu['image_url'])
        message = await ctx.send(embed=embed)


        actions = {
            '🥰': "Pat",
            '👋': "Slap",
            '🎁': "Feed",
            '✋': "Hold hands",
            '🕊️': "Release",
            '🚫': "Shoo away"
        }
        
        # Convert keys to a list and shuffle
        emojis = list(actions.keys())
        random.shuffle(emojis)
        
        # Add reactions in random order
        for emoji in emojis:
            await message.add_reaction(emoji)

        def action_check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in actions and reaction.message.id == message.id

        actions_taken = 0

        try:
            while actions_taken < 3:
                reaction, _ = await self.bot.wait_for('reaction_add', check=action_check, timeout=300)
                action_name = actions[str(reaction.emoji)]

                if action_name == "Release":
                    roll = random.randint(0, 10)
                    release_message = await self.generate_release_message(waifu_name, dark=(roll in [0, 1]))
                    await ctx.send(release_message)
                    self.waifus_db.delete_one({'user_id': ctx.author.id, 'waifu_name': waifu_name})
                    return
                elif action_name == "Shoo away":
                    await ctx.send(f"{waifu_name} huffs and disappears in a puff of smoke!")
                    return
                else:
                    interaction_phrase = await self.generate_interaction_phrase(waifu_name, action_name)
                    affection_points, relationship_stage = await self.update_affection(waifu, action_name)

                    # Send updated relationship embed
                    updated_embed = disnake.Embed(
                        title=f"{waifu_name} responds!",
                        description=(
                            f"You chose to {action_name.lower()} {waifu_name}.\n\n"
                            f"{interaction_phrase}\n\n"
                            f"**Updated Relationship Status:**\n"
                            f"**Affection Points:** {affection_points}/1000\n"
                            f"**Stage:** {relationship_stage}"
                        ),
                        color=disnake.Color.green() if affection_points >= 500 else disnake.Color.red()
                    )
                    updated_embed.set_image(url=waifu['image_url'])
                    await message.edit(embed=updated_embed)

                    actions_taken += 1

        except asyncio.TimeoutError:
            await ctx.send("You took too long. The waifu looks confused and disappears for some me-time!")



    async def generate_interaction_phrase(self, waifu_name, action):
        prompt = (
            f"You are a waifu named {waifu_name}. You have been interacted with in the following way: '{action}'. Based on the story of this character, "
            "Respond with a cute, funny, or goofy response in one sentence."
        )
        try:
            chat_completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                temperature=0.8,
                messages=[
                    {"role": "system", "content": "You are a waifu creating unique phrases for interactions."},
                    {"role": "user", "content": prompt}
                ]
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating interaction phrase: {e}")
            return "This waifu has no words... but she looks at you fondly."

    async def generate_release_message(self, waifu_name, dark=False):
        prompt = (
            f"Describe a farewell moment where the waifu '{waifu_name}' says goodbye to her owner. Make it one short paragraph and choose the tone out of: heartfelt, tear-jerking, kinky, evil, dumb, goofy, awkward, extremely cringeworthy. Make any choice over the top" if not dark else
            f"Describe a darkly funny and over-the-top way that the waifu '{waifu_name}' is released, including absurd humor."
        )
        try:
            chat_completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                temperature=0.9,
                messages=[
                    {"role": "system", "content": "You are a storyteller generating release messages for waifus."},
                    {"role": "user", "content": prompt}
                ]
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating release message: {e}")
            return "The waifu leaves without saying anything. The air feels empty."

#def setup(bot):
#    bot.add_cog(WaifuCog(bot))
