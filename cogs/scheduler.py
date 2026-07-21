"""
Scheduler cog — ``schedule_raid`` walks a raid leader through picking a trial,
run type, time and group composition, then posts a forum thread with a live
sign-up roster (tank/heal/dd/reserve buttons).

Natural-language time and composition are parsed by the LLM.
"""

import json

from datetime import datetime

from openai import OpenAI

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
from helpers import messages

_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"
_MODEL = "gpt-4o-mini"
_RUN_TYPES = ["free for all", "vet training", "hm training", "farm run", "farm hm run", "achievement run"]


class Scheduler(commands.Cog, name="scheduler"):
    """Schedule raids and manage sign-ups."""

    def __init__(self, bot):
        self.bot = bot
        proxy_key = getattr(config_py, "PROXY_API", None)
        self.client = OpenAI(api_key=proxy_key, base_url=_PROXY_BASE_URL) if proxy_key else None

    @commands.hybrid_command(name="schedule_raid", description="Schedule a new raid.")
    async def schedule_raid(self, context: Context) -> None:
        """Interactive wizard: trial → run type → time → composition → forum post."""
        await context.defer()

        trials = list(config_py.trial_ping_roles.keys())
        trial = await messages.prompt_select(
            context, "Please select the trial:", [(t, t) for t in trials], placeholder="Select a trial"
        )
        if not trial:
            return

        run_type = await messages.prompt_select(
            context, "Please select the type of run:", [(r, r) for r in _RUN_TYPES], placeholder="Select the type of run"
        )
        if not run_type:
            return

        raid_time = await self._ask_raid_time(context)
        if not raid_time:
            return

        group_comp = await self._ask_group_composition(context)
        if not group_comp:
            return

        await self._create_raid_channel(context, trial, run_type, raid_time, group_comp)

    async def _ask_raid_time(self, context: Context) -> dict | None:
        """Prompt for and parse a raid date/time into a timestamp."""
        await context.send(
            "Please enter the date and time for the raid (e.g., `2023-10-12 18:30` or `next Friday at 6pm`):"
        )
        reply = await self._await_reply(context)
        if reply is None:
            return None

        timestamp = self._parse_timestamp(reply)
        if timestamp is None:
            await context.send("Sorry, I couldn't parse the date and time. Please try again.")
            return None
        return {"datetime": datetime.fromtimestamp(timestamp), "timestamp": f"<t:{timestamp}:R>"}

    async def _ask_group_composition(self, context: Context) -> dict | None:
        """Prompt for and parse the group composition into tank/heal/dd counts."""
        await context.send(
            "Please enter the group composition (e.g., `2 tanks, 2 heals, 8 dds` or `1 tank 3 heal 8 dd`):"
        )
        reply = await self._await_reply(context)
        if reply is None:
            return None

        comp = self._parse_composition(reply)
        if comp is None:
            await context.send("Sorry, I couldn't parse the group composition. Please try again.")
            return None
        return comp

    async def _await_reply(self, context: Context) -> str | None:
        """Wait (5 min) for the raid leader's next message in this channel."""
        def check(message):
            return message.author == context.author and message.channel == context.channel

        try:
            message = await self.bot.wait_for("message", check=check, timeout=300)
            return message.content.strip()
        except TimeoutError:
            await context.send("You took too long to respond. Please try scheduling the raid again.")
            return None

    def _complete(self, prompt: str, *, as_json: bool) -> str | None:
        """Single LLM call returning the trimmed response text (or None on error)."""
        if self.client is None:
            return None
        try:
            kwargs = {"response_format": {"type": "json_object"}} if as_json else {}
            completion = self.client.chat.completions.create(
                model=_MODEL, temperature=0, messages=[{"role": "user", "content": prompt}], **kwargs
            )
            return completion.choices[0].message.content.strip()
        except Exception as error:
            self.bot.logger.error(f"Scheduler LLM call failed: {error}")
            return None

    def _parse_timestamp(self, user_input: str) -> int | None:
        """Ask the LLM to convert a natural-language time to a Unix timestamp."""
        text = self._complete(
            f"Convert this date and time to a Unix timestamp: '{user_input}'. "
            'Reply with JSON: {"timestamp": <integer>}.',
            as_json=True,
        )
        try:
            return int(json.loads(text)["timestamp"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _parse_composition(self, user_input: str) -> dict | None:
        """Ask the LLM to extract tank/heal/dd counts from free text."""
        text = self._complete(
            f"Extract the number of tanks, heals, and dds from this input: '{user_input}'. "
            'Reply with JSON: {"tanks": int, "heals": int, "dds": int}.',
            as_json=True,
        )
        try:
            comp = json.loads(text)
            return {"tanks": int(comp["tanks"]), "heals": int(comp["heals"]), "dds": int(comp["dds"])}
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None

    async def _create_raid_channel(self, context, trial, run_type, raid_time, group_comp) -> None:
        """Create the forum thread with the roster embed and sign-up buttons."""
        forum_channel = self.bot.get_channel(config_py.OPEN_RAID_CHANNEL)
        if not forum_channel:
            await context.send("Could not find the raid forum channel.")
            return

        date_str = raid_time["datetime"].strftime("%Y-%m-%d %H:%M")
        trial_abbr = config_py.trial_abbreviations.get(trial, trial)
        channel_name = f"{date_str} {trial_abbr} {run_type}"

        embed = messages.embed(
            f"Raid scheduled for {raid_time['timestamp']}", title=f"{trial} - {run_type}", color=discord.Color.blue()
        )
        if trial_image := config_py.raid_pictures.get(trial):
            embed.set_image(url=trial_image)
        embed.add_field(name="Tanks", value=f"0/{group_comp['tanks']}", inline=False)
        embed.add_field(name="Healers", value=f"0/{group_comp['heals']}", inline=False)
        embed.add_field(name="DDs", value=f"0/{group_comp['dds']}", inline=False)
        embed.add_field(name="Reserves", value="0", inline=False)

        await forum_channel.create_thread(
            name=channel_name,
            content=f"<@&{config_py.trial_ping_roles[trial]}>",
            embed=embed,
            view=RaidSignUpView(group_comp),
        )
        await context.send("Raid scheduled successfully.")


class RaidSignUpView(discord.ui.View):
    """Roster with tank/heal/dd/unsign buttons that update the embed live."""

    def __init__(self, group_comp: dict):
        super().__init__(timeout=None)
        self.group_comp = group_comp
        self.signups = {"tanks": [], "heals": [], "dds": [], "reserves": []}
        self.add_item(RoleButton(label="Tank", custom_id="signup_tank"))
        self.add_item(RoleButton(label="Healer", custom_id="signup_heal"))
        self.add_item(RoleButton(label="DD", custom_id="signup_dd"))
        self.add_item(RoleButton(label="Unsign", custom_id="unsign", style=discord.ButtonStyle.danger))

    async def update_embed(self, message: discord.Message) -> None:
        """Re-render the roster embed from the current sign-ups."""
        embed = message.embeds[0]
        for index, (role, label) in enumerate((("tanks", "Tanks"), ("heals", "Healers"), ("dds", "DDs"))):
            members = "\n".join(user.mention for user in self.signups[role]) or "None"
            embed.set_field_at(
                index, name=f"{label} ({len(self.signups[role])}/{self.group_comp[role]})", value=members, inline=False
            )
        reserves = "\n".join(user.mention for user in self.signups["reserves"]) or "None"
        embed.set_field_at(3, name=f"Reserves ({len(self.signups['reserves'])})", value=reserves, inline=False)
        await message.edit(embed=embed, view=self)


class RoleButton(discord.ui.Button):
    """A single sign-up (or unsign) button."""

    def __init__(self, label: str, custom_id: str, style: discord.ButtonStyle = discord.ButtonStyle.primary):
        super().__init__(label=label, custom_id=custom_id, style=style)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RaidSignUpView = self.view
        user = interaction.user

        if self.custom_id == "unsign":
            removed = False
            for role in view.signups:
                if user in view.signups[role]:
                    view.signups[role].remove(user)
                    removed = True
            if removed:
                await interaction.response.send_message("You have been removed from the sign-up.", ephemeral=True)
                await view.update_embed(interaction.message)
            else:
                await interaction.response.send_message("You are not signed up.", ephemeral=True)
            return

        role = self.custom_id.split("_")[-1] + "s"  # signup_tank -> tanks
        if user in view.signups[role]:
            await interaction.response.send_message("You are already signed up for this role.", ephemeral=True)
            return

        if len(view.signups[role]) < view.group_comp[role]:
            for other_role in view.signups:
                if user in view.signups[other_role]:
                    view.signups[other_role].remove(user)
            view.signups[role].append(user)
            await interaction.response.send_message(f"You have signed up as a {self.label}.", ephemeral=True)
        elif user not in view.signups["reserves"]:
            view.signups["reserves"].append(user)
            await interaction.response.send_message("All slots are full. You have been added to reserves.", ephemeral=True)
        else:
            await interaction.response.send_message("You are already in the reserves.", ephemeral=True)
        await view.update_embed(interaction.message)


async def setup(bot):
    await bot.add_cog(Scheduler(bot))
