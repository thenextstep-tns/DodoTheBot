import disnake
from disnake.ext import commands, tasks
import asyncio
import random
import datetime
import logging
import json
import os

import config_py

logger = logging.getLogger(__name__)

PRESENTS_FILE = "presents_data.json"

class XMasHunt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_presents_data()

        self.channels = config_py.xmas_hunt_channels
        self.submission_channel_id = config_py.xmas_hunt_submissions_channel
        self.started = False

        print(f"[XMasHunt] Found {len(self.presents)} images to post.")
        self.xmas_hunt_task.start()

    def cog_unload(self):
        self.xmas_hunt_task.cancel()

    def load_presents_data(self):
        # Load presents from JSON file
        if not os.path.exists(PRESENTS_FILE):
            raise FileNotFoundError(f"{PRESENTS_FILE} not found. Please create it first.")

        with open(PRESENTS_FILE, "r") as f:
            data = json.load(f)

        # data is a list of [number, url, code, description, redeemed_bool]
        # Create a dict keyed by code for easy lookups
        self.all_presents = {}
        for item in data:
            number, url, code, description, redeemed = item
            self.all_presents[code] = [number, url, code, description, redeemed]

        # Make a shallow copy for posting images
        # We'll remove items from this list as we post them
        self.presents = [list(item) for item in data if item[4] == False]  # only non-redeemed for posting
        # Note: If you still want to post redeemed images (?), keep as before:
        # self.presents = [list(item) for item in data]
        # But presumably all start not redeemed, so it's fine.

    def save_presents_data(self):
        # Writes the current state of all_presents back to the JSON file
        data = list(self.all_presents.values())  # convert dict back to list
        with open(PRESENTS_FILE, "w") as f:
            json.dump(data, f, indent=4)

    @tasks.loop(seconds=30)
    async def xmas_hunt_task(self):
        now = datetime.datetime.utcnow()
        print(f"[XMasHunt] Current UTC Date: {now.month}/{now.day}")

        if now.month == 12 and now.day == 25 and not self.started:
            self.started = True
            announcement_channel = self.bot.get_channel(config_py.ANNOUNCEMENT_CHANNEL)
            await announcement_channel.send("## The Christmas Hunt is here! :dodo: I will run around Tamriel over the course of the next 24 hours and will hide presents in popular channels, you will have to find them in the game to reveal the secret code to unlock the treasure! Only the images you post in the Christmas Hunt channel count! Stay on your toes and good luck! May the quickest win! :santa: :dodo: ")
            print("[XMasHunt] It is December 25, starting to post images.")
            await self.start_posting_images()

    async def start_posting_images(self):
        num_images = len(self.presents)
        if num_images == 0:
            print("[XMasHunt] No images to post.")
            return

        total_time = 24 * 60 * 60  # 24 hours
        baseline_interval = total_time / num_images
        jitter_factor = 0.25

        intervals = []
        for _ in range(num_images):
            offset = random.uniform(-baseline_interval * jitter_factor, baseline_interval * jitter_factor)
            interval = baseline_interval + offset
            if interval < 0:
                interval = baseline_interval / 2
            intervals.append(interval)

        actual_sum = sum(intervals)
        scale_factor = total_time / actual_sum
        intervals = [interval * scale_factor for interval in intervals]

        for interval in intervals:
            print(f"[XMasHunt] Waiting {interval:.2f} seconds before posting the next image...")
            await asyncio.sleep(interval)

            idx = random.randint(0, len(self.presents)-1)
            number, url, code, description, redeemed = self.presents.pop(idx)

            channel_id = random.choice(self.channels)
            channel = self.bot.get_channel(channel_id)

            if channel is None:
                logger.warning(f"Channel with ID {channel_id} not found.")
                print(f"[XMasHunt] Channel {channel_id} not found, skipping.")
                continue

            print(f"[XMasHunt] Attempting to post present #{number} with code {code} in channel {channel_id}")

            submissions_mention = f"<#{self.submission_channel_id}>"
            message_content = (
                "I just hid a new Christmas present! "
                f"Find this exact location, take a screenshot of your character in it and post it to {submissions_mention} to get a code to unlock the treasure box and unwrap the present!"
            )
            embed = disnake.Embed()
            if url and url != "placeholder_url":
                embed.set_image(url=url)

            try:
                await channel.send(content=message_content, embed=embed)
                logger.info(f"Sent present #{number} (code {code}) to channel {channel_id}")
                print(f"[XMasHunt] Successfully posted present #{number} with code {code}")
            except Exception as e:
                logger.error(f"Failed to send present #{number} (code {code}) to {channel_id}: {e}")
                print(f"[XMasHunt] Failed to post present #{number} with code {code} to {channel_id}: {e}")

        final_channel = self.bot.get_channel(self.submission_channel_id)
        if final_channel:
            await final_channel.send("# All presents are in the wild now! :gift: Merry Christmas! And thank you to the sugar doddy of the event, Mr Quantum :dodo: ")
        print("[XMasHunt] All images have been posted!")

    @xmas_hunt_task.before_loop
    async def before_xmas_hunt(self):
        await self.bot.wait_until_ready()

    @commands.is_owner()
    @commands.command(name="reward")
    async def reward_command(self, ctx, number: int):
        # Must reply to a user's message
        if not ctx.message.reference or not ctx.message.reference.resolved:
            await ctx.send("You have to reply to someone's message so that I would know who is getting the code :dodo: .")
            return

        user_to_reward = ctx.message.reference.resolved.author
        present = self.find_present_by_number(number)
        if not present:
            await ctx.send("I think you have entered a wrong number, we didn't have that many presents.")
            return

        p_number, p_url, p_code, p_desc, p_redeemed = present
        if p_redeemed:
            await ctx.send("This present has already been redeemed.")
            return

        instructions = (
            f"Hello {user_to_reward.name}, you have found a present during the Christmas Hunt!\n"
            f"Your code to unwrap it is: `{p_code}`\n"
            "Use it with the command `dodo redeem <code>` in the hunt channel to claim your reward!"
        )

        try:
            await user_to_reward.send(instructions)
            await ctx.send(f"Sent code to {user_to_reward.mention} via DM.")
        except disnake.Forbidden:
            await ctx.send(f"Could not DM {user_to_reward.mention}. They might have DMs disabled.")

    @commands.command(name="redeem")
    async def redeem_command(self, ctx, code: str):
        present = self.find_present_by_code(code)
        if not present:
            await ctx.send("I think you have entered a wrong code, check you DMs again.")
            return

        number, url, p_code, description, redeemed = present
        if redeemed:
            await ctx.send("This present has already been unwrapped :flushed: .")
            return

        # Mark as redeemed in memory and save to JSON
        self.set_present_redeemed(p_code, True)
        self.save_presents_data()

        # Give the lodestar role if possible
        guild = ctx.guild
        if guild:
            role = guild.get_role(config_py.lodestar_role)
            if role:
                try:
                    await ctx.author.add_roles(role)
                except disnake.Forbidden:
                    print("[XMasHunt] Could not assign lodestar role, lacking permissions.")

        await ctx.send(
            f"Congratulations {ctx.author.mention}! You have redeemed code `{p_code}`, became a true Lodestar for others "
            f"and won **{description}**! 🎉🎄🎁\n"
            "May this gift bring you joy and brighten your day!"
        )

    def find_present_by_number(self, number: int):
        for code, item in self.all_presents.items():
            if item[0] == number:
                return item
        return None

    def find_present_by_code(self, code: str):
        if code in self.all_presents:
            number, url, p_code, description, redeemed = self.all_presents[code]
            if not redeemed:
                return self.all_presents[code]
        return None

    def set_present_redeemed(self, code: str, state: bool):
        if code in self.all_presents:
            self.all_presents[code][4] = state
        # Also remove from self.presents if it still exists there
        # (In case it was never posted or reward was given before posting)
        self.presents = [p for p in self.presents if p[2] != code]


#def setup(bot):
#    bot.add_cog(XMasHunt(bot))
