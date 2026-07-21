"""
Gym cog — ``gym`` lets a user pick one of their eligible cats and send it to
train a chosen attribute; the attribute is increased after the session ends.
"""

import asyncio
import datetime

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

import config_py

_MUSCLE_GROUPS = [
    "Chest and Arms",
    "Core and Cardio",
    "Brain by reading clever books",
    "Beauty by attending the Grooming center",
]
# NOTE (pre-existing): these mapping keys don't match the muscle-group labels
# above ('Library'/'Grooming' vs 'Brain…'/'Beauty…'), so intellect/charm training
# currently can't resolve. Preserved as-is — behaviour unchanged.
_ATTRIBUTE_MAPPING = {
    "Chest and Arms": "strength",
    "Core and Cardio": "agility",
    "Library": "intellect",
    "Grooming": "charm",
}


class _PetSelect(discord.ui.Select):
    """Dropdown for choosing which eligible cat to send to the gym."""

    def __init__(self, pets: list[dict]):
        options = [discord.SelectOption(label=pet["name"], description=str(pet["_id"])) for pet in pets]
        super().__init__(placeholder="Choose your pet for the gym", min_values=1, max_values=1, options=options)
        self.selected: str | None = None

    async def callback(self, interaction: discord.Interaction) -> None:
        self.selected = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class _MuscleGroupSelect(discord.ui.Select):
    """Dropdown for choosing what to train, which starts the session."""

    def __init__(self, cog: "Gym", user_id: int, pet_id: str, member: discord.Member):
        options = [discord.SelectOption(label=group) for group in _MUSCLE_GROUPS]
        super().__init__(placeholder="What do you wanna train today?", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id
        self.pet_id = pet_id
        self.member = member

    async def callback(self, interaction: discord.Interaction) -> None:
        muscle_group = self.values[0]
        await self.cog.register_gym_session(self.user_id, self.pet_id, muscle_group)
        await interaction.response.send_message(
            f"{self.member.display_name}'s pet is now training their {muscle_group}.", ephemeral=True
        )
        self.view.stop()


class Gym(commands.Cog, name="gym"):
    """Send cats to the gym to raise their attributes."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="gym", aliases=["train"], description="Send one of your cats to the gym to train an attribute."
    )
    async def gym(self, context: Context, member: discord.Member = None) -> None:
        """Pick an eligible cat and a muscle group, then start a training session."""
        member = member or context.author

        pets = await self.fetch_gym_eligible_pets(member.id)
        if not pets:
            await context.send("You do not own any pets eligible for the gym.")
            return

        pet_id = await self._select_pet(pets, context)
        if pet_id is None:
            return

        view = discord.ui.View(timeout=180)
        view.add_item(_MuscleGroupSelect(self, member.id, pet_id, member))
        await context.send("Select what you wanna train today!", view=view)

    async def _select_pet(self, pets: list[dict], context: Context) -> str | None:
        """Show the pet dropdown and return the chosen pet's identifier (or None)."""
        select = _PetSelect(pets)
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await context.send("Select your pet:", view=view)
        await view.wait()
        if select.selected is None:
            await context.send("You took too long to choose a pet.")
        return select.selected

    async def fetch_gym_eligible_pets(self, user_id: int) -> list[dict]:
        """Return the user's gym-eligible cats that aren't already training."""
        all_pets = list(config_py.catcollection.find({"owner": user_id, "GYM": 1}))
        training = {session["cat_id"] for session in config_py.gym_sessions.find()}
        return [pet for pet in all_pets if pet["name"] not in training]

    async def register_gym_session(self, user_id: int, cat_id: str, muscle_group: str) -> None:
        """Record a 24h training session and schedule the attribute increase."""
        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(hours=24)
        config_py.gym_sessions.insert_one(
            {"cat_id": cat_id, "start_time": start_time, "end_time": end_time, "muscle_group": muscle_group}
        )
        self._schedule_attribute_increase(cat_id, muscle_group, end_time)

    def _schedule_attribute_increase(self, cat_id: str, muscle_group: str, end_time: datetime.datetime) -> None:
        """Increase the trained attribute once the session's end time is reached."""

        @tasks.loop(count=1)
        async def increase_attribute():
            await asyncio.sleep((end_time - datetime.datetime.now()).total_seconds())
            await self._increase_cat_attribute(cat_id, muscle_group)

        increase_attribute.start()

    async def _increase_cat_attribute(self, cat_id: str, muscle_group: str) -> None:
        """Apply +1 to the cat's trained attribute."""
        attribute = _ATTRIBUTE_MAPPING[muscle_group]
        # NOTE (pre-existing): writes to db["catcollection"] rather than the real
        # Cats collection (config_py.catcollection). Preserved as-is.
        config_py.db["catcollection"].update_one({"_id": cat_id}, {"$inc": {attribute: 1}})
        self.bot.logger.debug(f"Updated {attribute} for cat {cat_id}")


async def setup(bot):
    await bot.add_cog(Gym(bot))
