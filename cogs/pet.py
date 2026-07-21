"""
Pet cog — the cat/dog/waifu pet system: claim new pets from image APIs, list and
summon them, toggle their fishing/gym abilities, and pit them against each other.
"""

import asyncio
import io
import random
import re

import aiohttp
import bson
import numpy as np
import requests
from PIL import Image

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import checks, messages

# Per-pet-kind configuration for the claim flow (cats can additionally fish).
_PET_KINDS = {
    "cat": {
        "api": "https://api.thecatapi.com/v1/images/search?api_key=7fdd47a8-1509-4c98-91a0-30ef4c1dc6c5",
        "api_name": "CatAPI",
        "classes": lambda: config_py.catclasses,
        "claim_skill": 1.2,
        "claim_multiplier": 1.2,
        "extra_fields": {"FISHING": 0},
        "stop_msg": "Alright, let's stop LFC (looking for cats!) :hearts: ",
        "dodge_msg": "This cat was quite nimble, they dodged the claim and ran away! Wanna look for the next one?",
        "noun": "cat",
    },
    "dog": {
        "api": "https://api.thedogapi.com/v1/images/search?api_key=fb056807-277f-4e58-8373-fe5c39d8e9f2",
        "api_name": "DogAPI",
        "classes": lambda: config_py.dogclasses,
        "claim_skill": 2,
        "claim_multiplier": 1.7,
        "extra_fields": {},
        "stop_msg": "Alright, let's stop LFD (looking for dogs!) :hearts: ",
        "dodge_msg": "This dog didn't trust you enough and they ran away! Wanna look for the next one?",
        "noun": "dog",
    },
}
_CLAIM_REACTIONS = {"\U0001F44D": 0, "\U0001F44E": 1, "⛔": 2}  # yes / no / stop
_AGAIN_REACTIONS = {"\U0001F44D": 0, "⛔": 1}  # find another / stop


class Pet(commands.Cog, name="pet"):
    """Cat / dog / waifu collection and battles."""

    def __init__(self, bot):
        self.bot = bot
        self.pet_collections = {
            "cat": config_py.catcollection,
            "dog": config_py.dogcollection,
            "waifu": config_py.waifucollection,
        }

    def _collection(self, kind: str):
        return config_py.catcollection if kind == "cat" else config_py.dogcollection

    # ------------------------------------------------------------------ #
    #  Listing
    # ------------------------------------------------------------------ #
    async def _show_pets(self, context: Context, member, kind: str) -> None:
        """List a member's pets of a given kind, chunked under the embed limit."""
        member = member or context.author
        pets = list(self._collection(kind).find({"owner": member.id}))
        channel = self.bot.get_channel(config_py.PET_CHANNEL)
        if kind == "cat":
            await context.send(f"Ok, {member.display_name}, here comes your meow army! :cat: ")

        if not pets:
            await channel.send(
                f"Doesn't look like you have any {kind}s :pleading_face: , try dodo {kind} command to find a new one!"
            )
            return

        names, buffer = [], ""
        for pet in pets:
            names.append(pet.get("name"))
            buffer = ", ".join(names)
            if len(buffer) > 1500:
                await channel.send(buffer)
                names, buffer = [], ""
        if names:
            await channel.send(", ".join(names))
        await channel.send(f"I found {len(pets)} {kind}s")

    @commands.hybrid_command(name="showcats", description="Show all your cats in a list.")
    @checks.not_blacklisted()
    async def showcats(self, context: Context, member: discord.Member = None) -> None:
        """List your cats."""
        await self._show_pets(context, member, "cat")

    @commands.hybrid_command(name="showdogs", description="Show all your dogs in a list.")
    @checks.not_blacklisted()
    async def showdogs(self, context: Context, member: discord.Member = None) -> None:
        """List your dogs."""
        await self._show_pets(context, member, "dog")

    @commands.hybrid_command(name="snake", description="Show off your snake.")
    @checks.not_blacklisted()
    async def snake(self, context: Context) -> None:
        """:snake:"""
        await context.send(":snake:")

    # ------------------------------------------------------------------ #
    #  Claiming new pets
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="cat", description="Summon a new cat.")
    @checks.not_blacklisted()
    async def newcat(self, context: Context, member: discord.Member = None) -> None:
        """Find and try to claim a new cat."""
        await self._claim_pet(context, member, "cat")

    @commands.hybrid_command(name="dog", description="Summon a new dog.")
    @checks.not_blacklisted()
    async def newdog(self, context: Context, member: discord.Member = None) -> None:
        """Find and try to claim a new dog."""
        await self._claim_pet(context, member, "dog")

    async def _fetch_unowned_image(self, kind: str, channel) -> str | None:
        """Fetch image URLs from the pet API until one isn't already owned."""
        config = _PET_KINDS[kind]
        collection = self._collection(kind)
        while True:
            async with aiohttp.ClientSession() as session:
                async with session.get(config["api"]) as request:
                    if request.status != 200:
                        await channel.send(
                            embed=messages.error(f"{config['api_name']} is being weird at the moment, try again or later", title="Nope")
                        )
                        return None
                    url = (await request.json())[0].get("url")
            if collection.find_one({"url": url}) is None:
                return url

    async def _claim_pet(self, context: Context, member, kind: str) -> None:
        """Full claim loop for a cat or dog: find one, offer it, name it if claimed."""
        if context.interaction:
            await context.defer()
        config = _PET_KINDS[kind]
        member = member or context.author
        collection = self._collection(kind)
        channel = self.bot.get_channel(config_py.PET_CHANNEL)

        looking = True
        while looking:
            url = await self._fetch_unowned_image(kind, channel)
            if url is None:
                return

            pet_class = random.choice(config["classes"]())
            stats = self._roll_stats(pet_class)
            claim_chance = round(config["claim_skill"] * stats["claimres"] * 100 * config["claim_multiplier"])

            embed = messages.success(
                f"Strength = {stats['strength']}, Agility = {stats['agility']}, Intellect = {stats['intellect']}, "
                f"Charm = {stats['charm']}, your chance to claim them is {claim_chance}%"
            )
            embed.set_image(url=url)
            embed.set_author(name=f"{member.display_name}, this {pet_class[0]} is free! Are you gonna claim them?")
            suggestion = await channel.send(embed=embed)

            choice, _ = await messages.wait_for_reaction(self.bot, suggestion, _CLAIM_REACTIONS, member=member, timeout=60)
            if choice is None or _CLAIM_REACTIONS.get(choice) == 2:
                await suggestion.clear_reactions()
                if choice is not None:
                    await channel.send(config["stop_msg"])
                return
            if _CLAIM_REACTIONS[choice] == 1:  # explicit "no"
                await suggestion.clear_reactions()
                continue

            if random.randint(0, 100) > 100 - claim_chance:
                await self._name_and_save(context, channel, collection, member, kind, pet_class[0], url, stats, config["extra_fields"], suggestion)
                return
            # Dodged — offer to look for another.
            looking = await self._offer_retry(context, channel, member, config)

    def _roll_stats(self, pet_class) -> dict:
        """Roll a pet's stats from its class's stat ranges."""
        strength = random.randint(pet_class[1], pet_class[2])
        agility = random.randint(pet_class[3], pet_class[4])
        intellect = random.randint(pet_class[5], pet_class[6])
        charm = random.randint(pet_class[7], pet_class[8])
        return {
            "strength": strength,
            "agility": agility,
            "intellect": intellect,
            "charm": charm,
            "hp": strength * 5,
            "bite": strength * 0.75,
            "critchance": agility * 1.85 / 100,
            "claimres": (agility + intellect + charm) * 0.8 / 100,
            "conversionchance": (charm * 0.5 + intellect * 0.75 - strength * 0.15) / 100,
        }

    async def _name_and_save(self, context, channel, collection, member, kind, pet_type, url, stats, extra_fields, suggestion) -> None:
        """Ask for a unique name and insert the claimed pet."""
        await channel.send(
            "You have successfully claimed this pet! :white_check_mark: How are you going to name them? "
            "Hurry up, the others may name it too!"
        )
        while True:
            try:
                name_msg = await self.bot.wait_for("message", timeout=60)
            except asyncio.TimeoutError:
                await suggestion.clear_reactions()
                return
            name = str(name_msg.content).replace("@", " ")
            if collection.find_one({"name": name, "owner": name_msg.author.id}):
                await channel.send(
                    f"I won't be able to distinguish between different {name}s. Please choose a unique name for your unique {kind}! Meow :3"
                )
                continue
            collection.insert_one(
                {"name": name, "type": pet_type, "url": url, "owner": member.id, "fightswon": 0, "fightslost": 0,
                 **stats, **extra_fields}
            )
            await channel.send(f"{name} has been added to your collection!")
            await suggestion.clear_reactions()
            return

    async def _offer_retry(self, context, channel, member, config) -> bool:
        """After a dodge, ask whether to keep looking. Returns whether to continue."""
        dodge_msg = await channel.send(config["dodge_msg"])
        choice, _ = await messages.wait_for_reaction(self.bot, dodge_msg, _AGAIN_REACTIONS, member=context.author, timeout=15)
        await dodge_msg.clear_reactions()
        if choice is None or _AGAIN_REACTIONS.get(choice) == 1:
            if choice is not None:
                await channel.send(f"Alright, {member.display_name} let's stop looking for {config['noun']}s")
            return False
        await channel.send(f"Okie dokie, find a new {config['noun']}!")
        return True

    # ------------------------------------------------------------------ #
    #  Summon
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="summon", description="Summon one of your pets (case-insensitive).")
    @checks.not_blacklisted()
    async def summon(self, context: Context, *, pet_name: str) -> None:
        """Summon a pet by name, letting you interact via reactions."""
        pets = self.find_pets(context.author.id, pet_name)
        if not pets:
            await context.send(
                f"I couldn't find '{pet_name}' in your collections. Please check the spelling and try again."
            )
        elif len(pets) > 1:
            await self.ask_user_to_choose_pet(context, pets)
        else:
            await self.handle_pet_interaction(context, pets[0])

    def find_pets(self, owner_id: int, pet_name: str) -> list:
        """Find pets across all collections by case-insensitive partial name."""
        regex = re.compile(pet_name, re.IGNORECASE)
        found = []
        for pet_type, collection in self.pet_collections.items():
            for pet in collection.find({"owner": owner_id, "name": {"$regex": regex}}):
                pet["type"] = pet_type
                found.append(pet)
        return found

    async def ask_user_to_choose_pet(self, context: Context, pets: list) -> None:
        """Disambiguate multiple name matches via reactions."""
        emoji_list = list(config_py.pet_emoji.keys())[: len(pets)]
        description = "\n".join(
            f"{emoji}: {pet['type'].title()} named {pet['name']}" for emoji, pet in zip(emoji_list, pets)
        )
        embed = messages.embed(description, title="Looks like you have several pets with that name!", color=config_py.info)
        choice_message = await context.send(embed=embed)
        emoji, _ = await messages.wait_for_reaction(self.bot, choice_message, emoji_list, member=context.author, timeout=10)
        if emoji is None:
            await choice_message.edit(content="Oops, too slow! Please try the command again.", embed=None)
            return
        await self.handle_pet_interaction(context, pets[emoji_list.index(emoji)])

    async def handle_pet_interaction(self, context: Context, pet: dict) -> None:
        """Show a summoned pet and react to fishing/gym toggle choices."""
        pet_msg = await context.send(embed=self.create_pet_embed(pet))
        emoji, _ = await messages.wait_for_reaction(self.bot, pet_msg, config_py.pet_actions, member=context.author, timeout=120)
        if emoji is None:
            await pet_msg.clear_reactions()
            return
        if emoji == "\U0001F41F":  # fishing
            await self.toggle_fishing(pet["_id"], context.author.id, context.channel.id)
        elif emoji == "\U0001F4AA":  # gym
            await self.toggle_gym(pet["_id"], context.author.id, context.channel.id)
        else:
            await context.send("This action is not recognized.")

    def create_pet_embed(self, pet: dict) -> discord.Embed:
        """Build the summoned-pet embed with its stats and action prompts."""
        embed = messages.success(
            f"Type: {pet['type'].title()}, Wins: {pet.get('fightswon', 0)}, Losses: {pet.get('fightslost', 0)}"
        )
        embed.set_image(url=pet["url"])
        embed.set_author(name=f"{pet['name']} at your service", icon_url=pet["url"])
        for emoji, action in config_py.pet_actions.items():
            embed.add_field(name=f"React with {emoji}", value=action, inline=False)
        return embed

    # ------------------------------------------------------------------ #
    #  Fighting
    # ------------------------------------------------------------------ #
    async def _resolve_pet(self, context: Context, name: str, owner_id: int, *, collection_label: str) -> dict | None:
        """Find a named pet for an owner, asking which if a cat and dog both match."""
        cat = config_py.catcollection.find_one({"name": name, "owner": owner_id})
        dog = config_py.dogcollection.find_one({"name": name, "owner": owner_id})
        if cat and dog:
            prompt = await context.send(
                f"I found a cat and a dog with this name{collection_label}! Who would you want to fight? :eyes: "
            )
            emoji, _ = await messages.wait_for_reaction(self.bot, prompt, config_py.pet_emoji, member=context.author, timeout=60)
            await prompt.clear_reactions()
            if emoji is None:
                return None
            return cat if config_py.pet_emoji[emoji] == 0 else dog
        return cat or dog

    @commands.hybrid_command(name="petfight", description="Fight other pets!")
    @checks.not_blacklisted()
    @commands.has_permissions(kick_members=True)
    async def petfight(self, context: Context, mypet: str, opponent: discord.Member, theirpet: str) -> None:
        """Propose a duel between your pet and an opponent's pet."""
        attacker = await self._resolve_pet(context, mypet, context.author.id, collection_label="")
        if not attacker:
            await context.send("I couldn't find any pets with that name in your collection :slight_frown: . Please check spelling and try again")
            return
        defender = await self._resolve_pet(context, theirpet, opponent.id, collection_label=" in your opponents collection")
        if not defender:
            await context.send("I couldn't find any pets with that name in your opponent's collection :angry: . Please check spelling and try again")
            return

        duel_image = self._compose_duel_image(attacker["url"], defender["url"])
        embed = messages.success(
            f"Duel has been proposed! \n {context.author.display_name}'s **{attacker['name']}** \n "
            f"Strength: **{attacker['strength']}** \n Agility: **{attacker['agility']}** \n "
            f"Intellect: **{attacker['intellect']}** \n Charm: **{attacker['charm']}** \n \n "
            f"is challenging {opponent.display_name}'s **{defender['name']}** \n \n "
            f"Strength: **{defender['strength']}** \n Agility: **{defender['agility']}** \n "
            f"Intellect: **{defender['intellect']}** \n Charm: **{defender['charm']}** \n "
            f"Will {opponent.display_name} accept the duel? "
        )
        embed.set_image(url="attachment://duel.jpg")
        await context.send(file=duel_image, embed=embed)

    def _compose_duel_image(self, attacker_url: str, defender_url: str) -> discord.File:
        """Build the side-by-side attacker/versus/defender duel image."""
        for url, path in ((attacker_url, "duel_img/atk.jpg"), (defender_url, "duel_img/def.jpg")):
            response = requests.get(url, timeout=4.0)
            with Image.open(io.BytesIO(response.content)) as image:
                image.convert("RGB").save(path)

        images = [Image.open(p) for p in ("duel_img/atk.jpg", "duel_img/versus.jpg", "duel_img/def.jpg")]
        min_shape = sorted((np.sum(i.size), i.size) for i in images)[0][1]
        combined = Image.fromarray(np.hstack([np.asarray(i.resize(min_shape)) for i in images]))
        combined.save("duel_img/duel.jpg")
        return discord.File("duel_img/duel.jpg", filename="duel.jpg")

    # ------------------------------------------------------------------ #
    #  Fishing / gym toggles
    # ------------------------------------------------------------------ #
    async def _toggle_flag(self, cat_id, user_id, channel_id, *, flag: str, enabled_msg, disabled_msg, full_msg) -> None:
        """Toggle a per-cat boolean flag (FISHING/GYM), capped at 25 enabled."""
        cats = config_py.catcollection
        cat = cats.find_one({"_id": cat_id})
        if not cat:
            self.bot.logger.warning("Pet toggle: cat not found.")
            return

        channel = self.bot.get_channel(channel_id)
        object_id = bson.ObjectId(cat_id)
        if cat.get(flag, 0) == 1:
            cats.update_one({"_id": object_id}, {"$set": {flag: 0}})
            await channel.send(disabled_msg(cat["name"]))
            return
        if cats.count_documents({"owner": user_id, flag: 1}) >= 25:
            await channel.send(full_msg(cat["name"]))
            return
        cats.update_one({"_id": object_id}, {"$set": {flag: 1}})
        await channel.send(enabled_msg(cat["name"]))

    async def toggle_fishing(self, cat_id, user_id, channel_id) -> None:
        await self._toggle_flag(
            cat_id, user_id, channel_id, flag="FISHING",
            enabled_msg=lambda n: f"{n} can now fish!",
            disabled_msg=lambda n: f"You took away {n}'s fishing pole. They won't be able to fish anymore.",
            full_msg=lambda n: f"You already have 25 cats that can fish. Toggle one off, and {n} will be able to join!",
        )

    async def toggle_gym(self, cat_id, user_id, channel_id) -> None:
        await self._toggle_flag(
            cat_id, user_id, channel_id, flag="GYM",
            enabled_msg=lambda n: f"{n} can now use the gym!",
            disabled_msg=lambda n: f"{n} is no longer allowed to use the gym.",
            full_msg=lambda n: f"You already have 25 cats using the gym. Toggle one off, and {n} will be able to join!",
        )


async def setup(bot):
    await bot.add_cog(Pet(bot))
