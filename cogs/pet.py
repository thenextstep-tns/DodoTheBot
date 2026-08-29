"""
Pet cog — the cat/dog/waifu pet system: claim new pets from image APIs, list and
summon them, toggle their fishing/gym abilities, and pit them against each other.
User-facing text lives in ``lang``.
"""

import asyncio
import difflib
import io
import random

import aiohttp
import bson
import numpy as np
import requests
from PIL import Image

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages, scrap, scrap_lobby

# Per-pet-kind configuration for the claim flow (cats can additionally fish).
_PET_KINDS = {
    "cat": {
        "api": "https://api.thecatapi.com/v1/images/search?api_key=7fdd47a8-1509-4c98-91a0-30ef4c1dc6c5",
        "api_name": "CatAPI",
        "classes": lambda: config_py.catclasses,
        "claim_skill": 1.2,
        "claim_multiplier": 1.2,
        "extra_fields": {"FISHING": 0},
        "stop_msg": lang.PET_STOP_CATS,
        "dodge_msg": lang.PET_DODGE_CAT,
        "noun": "cat",
    },
    "dog": {
        "api": "https://api.thedogapi.com/v1/images/search?api_key=fb056807-277f-4e58-8373-fe5c39d8e9f2",
        "api_name": "DogAPI",
        "classes": lambda: config_py.dogclasses,
        "claim_skill": 2,
        "claim_multiplier": 1.7,
        "extra_fields": {},
        "stop_msg": lang.PET_STOP_DOGS,
        "dodge_msg": lang.PET_DODGE_DOG,
        "noun": "dog",
    },
}
_CLAIM_REACTIONS = {"\U0001F44D": 0, "\U0001F44E": 1, "⛔": 2}  # yes / no / stop
_AGAIN_REACTIONS = {"\U0001F44D": 0, "⛔": 1}  # find another / stop


# Summon name-match tiers, best first: an earlier tier beats a later one outright.
_MATCH_TIERS = ("exact", "prefix", "substring", "fuzzy")
_SELECT_LIMIT = 25  # Discord's hard cap on options in a single select.


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

    def _param(self, context: Context, key: str):
        """Read a per-guild tunable for this command (editable from the panel)."""
        return self.bot.params.get(context.guild.id if context.guild else None, key)

    # ------------------------------------------------------------------ #
    #  Listing
    # ------------------------------------------------------------------ #
    async def _show_pets(self, context: Context, member, kind: str) -> None:
        """List a member's pets of a given kind, chunked under the embed limit."""
        member = member or context.author
        pets = list(self._collection(kind).find({"owner": member.id}))
        channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "PET_CHANNEL"))
        if kind == "cat":
            await context.send(lang.PET_SHOWCATS_INTRO.format(name=member.display_name))

        if not pets:
            await channel.send(lang.PET_SHOW_NONE.format(kind=kind))
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
        await channel.send(lang.PET_SHOW_COUNT.format(count=len(pets), kind=kind))

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
        await context.send(lang.PET_SNAKE)

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
                            embed=messages.error(lang.PET_API_ERROR.format(api_name=config["api_name"]), title="Nope")
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
        channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "PET_CHANNEL"))

        looking = True
        while looking:
            url = await self._fetch_unowned_image(kind, channel)
            if url is None:
                return

            pet_class = random.choice(config["classes"]())
            stats = self._roll_stats(pet_class)
            claim_chance = round(config["claim_skill"] * stats["claimres"] * 100 * config["claim_multiplier"])

            embed = messages.success(
                lang.PET_CLAIM_OFFER.format(
                    strength=stats["strength"], agility=stats["agility"], intellect=stats["intellect"],
                    charm=stats["charm"], claim_chance=claim_chance,
                )
            )
            embed.set_image(url=url)
            embed.set_author(name=lang.PET_CLAIM_AUTHOR.format(name=member.display_name, pet_type=pet_class[0]))
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
        """Ask for a unique name and insert the claimed pet.

        Anyone in the channel may name someone else's new pet — that race is the
        point of the claim message. So the name has to be unique in the
        *claimer's* collection, never the namer's: it is ``member`` who ends up
        owning the pet and ``member`` who later has to summon it by that name.
        """
        await channel.send(lang.PET_CLAIM_SUCCESS)

        def is_a_name(message) -> bool:
            # Any human in the claim channel may name it; the bot's own messages
            # must not, or a listing or log line becomes the pet's name.
            return message.channel.id == channel.id and not message.author.bot

        while True:
            try:
                name_msg = await self.bot.wait_for("message", timeout=60, check=is_a_name)
            except asyncio.TimeoutError:
                await suggestion.clear_reactions()
                return
            name = str(name_msg.content).replace("@", " ")
            if collection.find_one({"name": name, "owner": member.id}):
                await channel.send(lang.PET_CLAIM_DUPLICATE.format(name=name, kind=kind))
                continue
            collection.insert_one(
                {"name": name, "type": pet_type, "url": url, "owner": member.id, "fightswon": 0, "fightslost": 0,
                 **stats, **extra_fields}
            )
            await channel.send(lang.PET_CLAIM_ADDED.format(name=name))
            await suggestion.clear_reactions()
            return

    async def _offer_retry(self, context, channel, member, config) -> bool:
        """After a dodge, ask whether to keep looking. Returns whether to continue."""
        dodge_msg = await channel.send(config["dodge_msg"])
        choice, _ = await messages.wait_for_reaction(self.bot, dodge_msg, _AGAIN_REACTIONS, member=context.author, timeout=15)
        await dodge_msg.clear_reactions()
        if choice is None or _AGAIN_REACTIONS.get(choice) == 1:
            if choice is not None:
                await channel.send(lang.PET_RETRY_STOP.format(name=member.display_name, noun=config["noun"]))
            return False
        await channel.send(lang.PET_RETRY_YES.format(noun=config["noun"]))
        return True

    # ------------------------------------------------------------------ #
    #  Summon
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="summon", description="Summon one of your pets (case-insensitive).")
    @checks.not_blacklisted()
    async def summon(self, context: Context, *, pet_name: str) -> None:
        """Summon a pet by name.

        Only the pet literally called what you typed is summoned outright.
        Anything less than that -- a prefix, a substring, a typo -- is offered
        back as a suggestion first, because ``summon Bobo`` quietly producing
        "Bobobo" is worse than one extra click.
        """
        tier, pets = self.find_pets(
            context.author.id, pet_name, cutoff=self._param(context, "summon_fuzzy_cutoff")
        )
        if not pets:
            await context.send(lang.PET_SUMMON_NOT_FOUND.format(pet_name=pet_name))
        elif tier == "exact" and len(pets) == 1:
            await self.handle_pet_interaction(context, pets[0])
        elif len(pets) == 1:
            await self.confirm_pet_guess(context, pets[0], pet_name)
        else:
            await self.ask_user_to_choose_pet(context, pets, pet_name, exact=tier == "exact")

    def find_pets(self, owner_id: int, pet_name: str, *, cutoff: float = 0.7) -> tuple:
        """Find an owner's pets by name, returning ``(tier, pets)``.

        Every pet the owner has is sorted into a tier -- the exact name, names
        starting with the query, names containing it, then near-misses at or
        above ``cutoff`` similarity -- and the best non-empty tier wins outright,
        so a pet actually called "Bo" is never beaten by "Bobobo". Within a tier
        the closest name comes first. Returns ``(None, [])`` when nothing is
        close enough; each pet is tagged with its ``collection``.
        """
        query = pet_name.strip().casefold()
        if not query:
            return None, []

        scored = []
        for kind, collection in self.pet_collections.items():
            for pet in collection.find({"owner": owner_id}):
                name = str(pet.get("name", "")).casefold()
                ratio = difflib.SequenceMatcher(None, query, name).ratio()
                if name == query:
                    tier = 0
                elif name.startswith(query):
                    tier = 1
                elif query in name:
                    tier = 2
                elif ratio >= cutoff:
                    tier = 3
                else:
                    continue
                pet["collection"] = kind
                scored.append((tier, ratio, len(name), pet))

        if not scored:
            return None, []
        best = min(match[0] for match in scored)
        winners = sorted(
            (match for match in scored if match[0] == best), key=lambda match: (-match[1], match[2])
        )
        return _MATCH_TIERS[best], [match[3] for match in winners]

    async def confirm_pet_guess(self, context: Context, pet: dict, pet_name: str) -> None:
        """One near-miss and nothing exact: ask before summoning something else."""
        confirmed = await messages.prompt_confirm(
            context, context.author,
            content=lang.PET_SUMMON_DID_YOU_MEAN.format(
                pet_name=pet_name, name=pet["name"], kind=pet["collection"]
            ),
            timeout=self._param(context, "summon_choice_timeout"),
        )
        if not confirmed:
            await context.send(lang.PET_SUMMON_CANCELLED)
            return
        await self.handle_pet_interaction(context, pet)

    async def ask_user_to_choose_pet(self, context: Context, pets: list, pet_name: str, *, exact: bool) -> None:
        """Disambiguate several matches with a select dropdown."""
        limit = max(1, min(self._param(context, "summon_max_matches"), _SELECT_LIMIT))
        options = [
            discord.SelectOption(
                label=pet["name"][:100], description=pet["collection"].title(), value=str(index)
            )
            for index, pet in enumerate(pets[:limit])
        ]
        prompt = lang.PET_SUMMON_CHOOSE if exact else lang.PET_SUMMON_CHOOSE_INEXACT
        choice = await messages.prompt_select(
            context, prompt.format(pet_name=pet_name), options,
            placeholder=lang.PET_SUMMON_PLACEHOLDER,
            timeout=self._param(context, "summon_choice_timeout"),
            member=context.author,
        )
        if choice is None:
            await context.send(lang.PET_SUMMON_TIMEOUT)
            return
        await self.handle_pet_interaction(context, pets[int(choice)])

    async def handle_pet_interaction(self, context: Context, pet: dict) -> None:
        """Show a summoned pet and react to fishing/gym toggle choices."""
        pet_msg = await context.send(embed=self.create_pet_embed(pet))
        emoji, _ = await messages.wait_for_reaction(
            self.bot, pet_msg, config_py.pet_actions, member=context.author,
            timeout=self._param(context, "summon_action_timeout"),
        )
        if emoji is None:
            await pet_msg.clear_reactions()
            return
        if emoji == "\U0001F41F":  # fishing
            await self.toggle_fishing(pet["_id"], context.author.id, context.channel.id)
        elif emoji == "\U0001F4AA":  # gym
            await self.toggle_gym(pet["_id"], context.author.id, context.channel.id)
        elif emoji == "\U0001F94A":  # boxing glove
            await self.enrol_for_fights(context, pet)
        else:
            await context.send(lang.PET_SUMMON_UNKNOWN_ACTION)

    async def enrol_for_fights(self, context: Context, pet: dict) -> None:
        """Toggle the summoned pet on or off the owner's fighting roster.

        A toggle, exactly like the fish and the dumbbell beside it. Pressing it
        again used to quietly re-add the same cat and shuffle it to the front,
        so there was no way to take a cat *off* the roster from the one screen
        that talks about the roster.

        The cap pushes the oldest cat off the end rather than refusing: being
        told "no, go and remove one first" three clicks into a joke is how
        people stop playing.
        """
        ident = str(pet["_id"])
        owner = context.author.id

        # Summon reaches into cats, dogs and waifus; only one of those fights.
        if pet.get("collection", "cat") != "cat" or not scrap_lobby.is_fighter(ident):
            await context.send(lang.PET_ROSTER_NOT_A_CAT.format(name=pet.get("name")))
            return

        # Ask what is stored, not what resolves: see scrap_lobby.on_roster.
        if scrap_lobby.on_roster(owner, ident):
            scrap_lobby.release(owner, ident)
            roster = scrap_lobby.roster(owner)
            await context.send(lang.PET_ROSTER_REMOVED.format(
                name=pet.get("name"), roster=scrap_lobby.describe_roster(roster)))
            return

        result = scrap_lobby.enrol(owner, ident)
        roster = scrap_lobby.roster(owner)
        await context.send(lang.PET_ROSTER_ADDED.format(
            name=pet.get("name"), roster=scrap_lobby.describe_roster(roster)))
        if result["dropped"]:
            await context.send(lang.PET_ROSTER_FULL.format(
                cap=int(scrap.TUNING["roster_max"])))

    def create_pet_embed(self, pet: dict) -> discord.Embed:
        """Build the summoned-pet embed with its stats and action prompts."""
        embed = messages.success(
            lang.PET_PET_STATUS.format(
                type=pet["collection"].title(), wins=pet.get("fightswon", 0), losses=pet.get("fightslost", 0)
            )
        )
        embed.set_image(url=pet["url"])
        embed.set_author(name=lang.PET_PET_AUTHOR.format(name=pet["name"]), icon_url=pet["url"])
        for emoji, action in config_py.pet_actions.items():
            embed.add_field(name=lang.PET_PET_ACTION_FIELD.format(emoji=emoji), value=action, inline=False)
        return embed

    # ------------------------------------------------------------------ #
    #  Fighting
    # ------------------------------------------------------------------ #
    async def _resolve_pet(self, context: Context, name: str, owner_id: int, *, collection_label: str) -> dict | None:
        """Find a named pet for an owner, asking which if a cat and dog both match."""
        cat = config_py.catcollection.find_one({"name": name, "owner": owner_id})
        dog = config_py.dogcollection.find_one({"name": name, "owner": owner_id})
        if cat and dog:
            prompt = await context.send(lang.PET_FIGHT_BOTH.format(label=collection_label))
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
            await context.send(lang.PET_FIGHT_NO_MY_PET)
            return
        defender = await self._resolve_pet(context, theirpet, opponent.id, collection_label=" in your opponents collection")
        if not defender:
            await context.send(lang.PET_FIGHT_NO_THEIR_PET)
            return

        duel_image = self._compose_duel_image(attacker["url"], defender["url"])
        embed = messages.success(
            lang.PET_FIGHT_PROPOSAL.format(
                challenger=context.author.display_name, attacker=attacker["name"], a_str=attacker["strength"],
                a_agi=attacker["agility"], a_int=attacker["intellect"], a_cha=attacker["charm"],
                opponent=opponent.display_name, defender=defender["name"], d_str=defender["strength"],
                d_agi=defender["agility"], d_int=defender["intellect"], d_cha=defender["charm"],
            )
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
            await channel.send(disabled_msg.format(name=cat["name"]))
            return
        if cats.count_documents({"owner": user_id, flag: 1}) >= 25:
            await channel.send(full_msg.format(name=cat["name"]))
            return
        cats.update_one({"_id": object_id}, {"$set": {flag: 1}})
        await channel.send(enabled_msg.format(name=cat["name"]))

    async def toggle_fishing(self, cat_id, user_id, channel_id) -> None:
        await self._toggle_flag(
            cat_id, user_id, channel_id, flag="FISHING",
            enabled_msg=lang.PET_FISHING_ENABLED, disabled_msg=lang.PET_FISHING_DISABLED, full_msg=lang.PET_FISHING_FULL,
        )

    async def toggle_gym(self, cat_id, user_id, channel_id) -> None:
        await self._toggle_flag(
            cat_id, user_id, channel_id, flag="GYM",
            enabled_msg=lang.PET_GYM_ENABLED, disabled_msg=lang.PET_GYM_DISABLED, full_msg=lang.PET_GYM_FULL,
        )


async def setup(bot):
    await bot.add_cog(Pet(bot))
