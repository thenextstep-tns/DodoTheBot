"""
Fishing cog — pick one of your fishing-enabled cats and try to reel in a random
item. The cat's stats are compared against the item's agility/intellect/strength
requirements; on success you choose to stash, sell, or throw away the loot.
Costs coins per attempt (deducted from the Dodo Bank wallet).
"""

import asyncio
import datetime
import os
import random
import uuid

from bson import ObjectId
from PIL import Image

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import messages

_ITEM_IMG_DIR = "item_imgs"
_TEMP_THUMB = "temp_thumbnail.png"
_MAX_BAG = 24


class Fishing(commands.Cog, name="fishing"):
    """The cat-fishing minigame."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="fish", aliases=["fishing"], description="Send a cat to fish for a rare treasure!")
    async def fish(self, context: Context, member: discord.Member = None) -> None:
        """Run a full fishing attempt for the caller."""
        member = context.author
        user_id = member.id
        guild_id = context.guild.id if context.guild else None
        fishing_cost = self.bot.params.get(guild_id, "fishing_cost")
        bag_max = self.bot.params.get(guild_id, "fishing_bag_max")

        if not self.has_enough_balance(user_id, fishing_cost):
            await context.send(lang.FISHING_NO_COINS)
            return

        cats_list = await self.fetch_owned_cats(user_id)
        selected_cat_id = await self.select_cat(cats_list, context)
        if selected_cat_id is None:
            return

        agility_needed, intellect_needed, strength_needed, item_name = await self.spawn_fishing_drop(context)
        cat_agility, cat_intellect, cat_strength = self.fetch_cat_parameters(selected_cat_id)
        ratios = self.calculate_fishing_ratios(
            agility_needed, intellect_needed, strength_needed, cat_agility, cat_intellect, cat_strength
        )

        status = await context.send(
            self.write_fishing_message(*(self.get_parameter_message(name, ratio) for name, ratio in
                                         zip(("agility", "intellect", "strength"), ratios)))
        )
        await asyncio.sleep(random.uniform(4, 7))
        await status.delete()

        item_info = self.find_item_by_name(item_name)
        if self.define_fishing_outcome(*ratios):
            stashed, sold, thrown_away = await self.draw_victory_embed(context, item_name, user_id)
            fishing_success = 1
            text = self.process_fishing_results(user_id, stashed, sold, thrown_away, item_info, bag_max)
            await context.send(f"{text}\n{lang.FISHING_COST_NOTE.format(cost=fishing_cost)}")
        else:
            fishing_success = 0
            await context.send(lang.FISHING_FAILED.format(item_name=item_name))
            await context.send(lang.FISHING_COST_NOTE.format(cost=fishing_cost))

        self.subtract_fishing_cost(user_id, fishing_cost)
        self.save_fishing_result(item_info, user_id, selected_cat_id, *ratios, fishing_success)

    # ------------------------------------------------------------------ #
    #  Cats
    # ------------------------------------------------------------------ #
    async def fetch_owned_cats(self, user_id: int) -> list:
        """Return the user's fishing-enabled cats, sorted by name."""
        cats = config_py.catcollection.find({"owner": user_id, "FISHING": 1})
        return sorted(cats, key=lambda cat: cat["name"])

    async def select_cat(self, cats_list: list, context: Context) -> str | None:
        """Prompt the user to pick a cat; return its id (or None)."""
        if not cats_list:
            await context.send(lang.FISHING_NO_CATS)
            return None
        options = [
            discord.SelectOption(
                label=f"{cat['name']} - S: {cat['strength']} A: {cat['agility']} I: {cat['intellect']}",
                value=str(cat["_id"]),
            )
            for cat in cats_list[:25]
        ]
        selected = await messages.prompt_select(
            context, lang.FISHING_SELECT_CAT, options, placeholder=lang.FISHING_SELECT_CAT_PLACEHOLDER, timeout=30.0
        )
        if selected:
            await context.send(lang.FISHING_REEL_IN)
        return selected

    def fetch_cat_parameters(self, selected_cat_id: str):
        """Return (agility, intellect, strength) for the chosen cat."""
        cat = config_py.catcollection.find_one({"_id": ObjectId(selected_cat_id)})
        if not cat:
            self.bot.logger.warning("Fishing: selected cat not found.")
            return None
        return cat["agility"], cat["intellect"], cat["strength"]

    # ------------------------------------------------------------------ #
    #  Items & thumbnails
    # ------------------------------------------------------------------ #
    def pick_random_item(self) -> dict:
        """Pick a uniformly random item document."""
        count = config_py.items.count_documents({})
        return config_py.items.find().skip(random.randint(0, count - 1)).limit(1)[0]

    def _thumbnail(self, img_name: str) -> discord.File | None:
        """Build a 128px thumbnail File for an item image, or None if it's missing."""
        path = os.path.join(_ITEM_IMG_DIR, img_name)
        if not os.path.exists(path):
            return None
        image = Image.open(path)
        image.thumbnail((128, 128))
        image.save(_TEMP_THUMB)
        return discord.File(_TEMP_THUMB, filename="thumbnail.png")

    async def _send_with_thumbnail(self, context, embed, img_name):
        """Send an embed, attaching the item thumbnail when the image exists."""
        thumb = self._thumbnail(img_name)
        if thumb:
            embed.set_thumbnail(url="attachment://thumbnail.png")
            message = await context.send(embed=embed, file=thumb)
            if os.path.exists(_TEMP_THUMB):
                os.remove(_TEMP_THUMB)
            return message
        return await context.send(embed=embed)

    async def spawn_fishing_drop(self, context: Context):
        """Pick an item, announce it, and return its (agility, intellect, strength, name) requirements."""
        item = self.pick_random_item()
        item_type = config_py.itemtypes.find_one({"_id": item["type_id"]})
        item_quality = config_py.itemqualities.find_one({"_id": item["quality_id"]})
        base = config_py.base_modifiers

        agility_needed = item_type["agility_modifier"] * base.find_one({"name": "base_agility_modifier"})["modifier"]
        intellect_needed = item_quality["intellect_modifier"] * base.find_one({"name": "base_intellect_modifier"})["modifier"]
        strength_needed = item["weight"] * base.find_one({"name": "base_strength_modifier"})["modifier"]

        embed = discord.Embed(title=item["name"], description=lang.FISHING_ITEM_APPEARED, color=discord.Color.random())
        embed.add_field(name="Quality", value=item_quality["quality"], inline=True)
        embed.add_field(name="Type", value=item_type["type"], inline=True)
        embed.add_field(name="Cost", value=f"{item['cost']} dodo coins", inline=True)
        embed.add_field(name="Agility Needed", value=agility_needed, inline=True)
        embed.add_field(name="Intellect Needed", value=intellect_needed, inline=True)
        embed.add_field(name="Strength Needed", value=strength_needed, inline=True)
        await self._send_with_thumbnail(context, embed, item["img"])
        return agility_needed, intellect_needed, strength_needed, item["name"]

    def find_item_by_name(self, item_name: str) -> dict | None:
        """Return a normalized info dict for the named item."""
        item = config_py.items.find_one({"name": item_name})
        if not item:
            return None
        return {
            "item_id": item["_id"],
            "item_img": item["img"],
            "item_cost": item["cost"],
            "item_weight": item["weight"],
        }

    async def draw_victory_embed(self, context: Context, item_name: str, user_id: int):
        """Show the caught item and ask the user what to do with it."""
        item = config_py.items.find_one({"name": item_name})
        item_quality = config_py.itemqualities.find_one({"_id": item["quality_id"]})
        item_type = config_py.itemtypes.find_one({"_id": item["type_id"]})

        embed = discord.Embed(
            title=lang.FISHING_VICTORY_TITLE.format(item_name=item_name),
            description=lang.FISHING_VICTORY_DESCRIPTION,
            color=discord.Color.random(),
        )
        embed.add_field(name="Quality", value=item_quality["quality"], inline=True)
        embed.add_field(name="Type", value=item_type["type"], inline=True)
        embed.add_field(name="Cost", value=f"{item['cost']} dodo coins", inline=True)
        victory_message = await self._send_with_thumbnail(context, embed, item["img"])
        return await self.prompt_item_action(victory_message, user_id)

    # ------------------------------------------------------------------ #
    #  Outcome maths
    # ------------------------------------------------------------------ #
    def calculate_fishing_ratios(self, agility_needed, intellect_needed, strength_needed, cat_agility, cat_intellect, cat_strength):
        """Cat stat / requirement ratios, with a little noise."""
        noise = 0.05
        return (
            cat_agility / (agility_needed + random.uniform(-noise, noise)),
            cat_intellect / (intellect_needed + random.uniform(-noise, noise)),
            cat_strength / (strength_needed + random.uniform(-noise, noise)),
        )

    def define_fishing_outcome(self, agility_ratio, intellect_ratio, strength_ratio) -> bool:
        """Success when the average stat ratio exceeds 1."""
        return (agility_ratio + intellect_ratio + strength_ratio) / 3 > 1

    def get_parameter_message(self, parameter_name: str, ratio: float) -> str:
        """Flavour text for how a cat's stat measures up."""
        if ratio > 2:
            return lang.FISHING_PARAM_EXCELLENT.format(parameter=parameter_name)
        if ratio > 1:
            return lang.FISHING_PARAM_GOOD.format(parameter=parameter_name)
        if ratio > 0.5:
            return lang.FISHING_PARAM_OK.format(parameter=parameter_name)
        return lang.FISHING_PARAM_LOW.format(parameter=parameter_name)

    def write_fishing_message(self, agility_message, intellect_message, strength_message) -> str:
        """Compose the pre-result status message."""
        return lang.FISHING_STATUS.format(agility=agility_message, intellect=intellect_message, strength=strength_message)

    # ------------------------------------------------------------------ #
    #  Inventory / wallet
    # ------------------------------------------------------------------ #
    def count_goodies_bag(self, user_id: int) -> int:
        """Number of un-equipped, un-sold, un-thrown items in the user's bag."""
        return config_py.goodies_bag.count_documents(
            {"user": user_id, "equipped": 0, "sold": 0, "thrown_away": 0}
        )

    async def prompt_item_action(self, message: discord.Message, user_id: int):
        """React on ``message`` and return (stashed, sold, thrown_away) based on the choice."""
        emoji, _ = await messages.wait_for_reaction(
            self.bot, message, config_py.fishing_result_actions, member=discord.Object(id=user_id), timeout=20
        )
        if emoji is None:
            await message.clear_reactions()
            return 0, 0, 0
        action = config_py.fishing_result_actions[emoji]
        await message.clear_reactions()
        if action == "Put in the goodies bag":
            await message.edit(content="You have decided to put the item in your inventory")
            return 1, 0, 0
        if action == "Sell":
            await message.edit(content="You sold the item")
            return 0, 1, 0
        if action == "Throw away":
            await message.edit(content="You decided to throw the item away")
            return 0, 0, 1
        return 0, 0, 0

    def _store_item(self, user_id, item_info, *, sold=0, thrown_away=0) -> None:
        """Insert a goodies-bag record for an item in the given state."""
        config_py.goodies_bag.insert_one(
            {
                "user": user_id,
                "item_instance_id": str(uuid.uuid4()),
                "item_id": item_info["item_id"],
                "cost": item_info["item_cost"],
                "sold": sold,
                "thrown_away": thrown_away,
                "equipped": 0,
            }
        )

    def process_fishing_results(self, user_id, stashed, sold, thrown_away, item_info, bag_max=_MAX_BAG) -> str:
        """Apply the chosen disposition (stash/sell/throw) and return a status line."""
        if stashed:
            if self.count_goodies_bag(user_id) >= bag_max:
                return lang.FISHING_BAG_FULL
            self._store_item(user_id, item_info)
            return lang.FISHING_STASHED

        if sold:
            self._store_item(user_id, item_info, sold=1)
            price = item_info["item_cost"]
            wallet = config_py.wallets.find_one({"user_id": user_id})
            if wallet:
                config_py.wallets.update_one(
                    {"user_id": user_id}, {"$set": {"balance": wallet.get("balance", 0) + price}}
                )
            else:
                config_py.wallets.insert_one({"user_id": user_id, "balance": price})
            return lang.FISHING_SOLD.format(price=price)

        if thrown_away:
            self._store_item(user_id, item_info, thrown_away=1)
            return lang.FISHING_THROWN
        return ""

    def has_enough_balance(self, user_id: int, cost: int) -> bool:
        """Whether the user can afford a fishing attempt."""
        wallet = config_py.wallets.find_one({"user_id": user_id})
        return bool(wallet) and wallet.get("balance", 0) >= cost

    def subtract_fishing_cost(self, user_id: int, cost: int) -> None:
        """Deduct the fishing cost from the user's wallet."""
        wallet = config_py.wallets.find_one({"user_id": user_id})
        if not wallet:
            raise ValueError("User does not have a wallet.")
        if wallet.get("balance", 0) < cost:
            raise ValueError("User does not have enough coins.")
        config_py.wallets.update_one(
            {"user_id": user_id}, {"$set": {"balance": wallet["balance"] - cost}}
        )

    def save_fishing_result(self, item_info, user_id, selected_cat_id, agility_ratio, intellect_ratio, strength_ratio, fishing_success) -> None:
        """Record the outcome of a fishing attempt."""
        config_py.fishing_results.insert_one(
            {
                "user_id": user_id,
                "cat_id": selected_cat_id,
                "time": datetime.datetime.now(),
                "item_id": item_info["item_id"],
                "agility_ratio": agility_ratio,
                "intellect_ratio": intellect_ratio,
                "strength_ratio": strength_ratio,
                "fishing_success": fishing_success,
            }
        )


async def setup(bot):
    await bot.add_cog(Fishing(bot))
