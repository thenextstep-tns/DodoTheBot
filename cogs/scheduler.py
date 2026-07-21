import json
import os
import sys
import asyncio
from datetime import datetime
import disnake
from disnake.ext import commands

# Configuration
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

if not os.path.isfile("lang.py"):
    sys.exit("Language file not found! Please add it and try again.")
else:
    import lang

class Scheduler(commands.Cog, name="scheduler"):
    """Cog for scheduling raids and managing sign-ups."""
    def __init__(self, bot):
        self.bot = bot
        # Initialize any required variables here

    @commands.slash_command(name="schedule_raid", description="Schedule a new raid.")
    async def schedule_raid(self, inter):
        """Main command to start scheduling a raid."""
        await inter.response.defer()

        # Step 1: Ask for the trial
        trial = await self.ask_trial(inter)
        if not trial:
            return

        # Step 2: Ask for the run type
        run_type = await self.ask_run_type(inter)
        if not run_type:
            return

        # Step 3: Ask for the raid time
        raid_time = await self.ask_raid_time(inter)
        if not raid_time:
            return

        # Step 4: Ask for the group composition
        group_comp = await self.ask_group_composition(inter)
        if not group_comp:
            return

        # Step 5: Create the raid channel and post the roster
        await self.create_raid_channel(inter, trial, run_type, raid_time, group_comp)

    async def ask_trial(self, inter):
        """Ask the raid leader which trial they want to schedule."""
        trials = list(config_py.trial_ping_roles.keys())

        # Create select options
        options = [
            disnake.SelectOption(label=trial, value=trial)
            for trial in trials
        ]

        select = disnake.ui.Select(
            placeholder="Select a trial",
            options=options,
            min_values=1,
            max_values=1
        )

        # Define the interaction handler
        async def select_callback(interaction):
            await interaction.response.defer()
            select.stop()

        select.callback = select_callback

        # Create and send the message with the select menu
        view = disnake.ui.View()
        view.add_item(select)
        await inter.followup.send("Please select the trial:", view=view)
        await select.wait()

        selected_trial = select.values[0]
        return selected_trial

    async def ask_run_type(self, inter):
        """Ask the raid leader what type of run it will be."""
        run_types = [
            "free for all",
            "vet training",
            "hm training",
            "farm run",
            "farm hm run",
            "achievement run"
        ]

        options = [
            disnake.SelectOption(label=run_type, value=run_type)
            for run_type in run_types
        ]

        select = disnake.ui.Select(
            placeholder="Select the type of run",
            options=options,
            min_values=1,
            max_values=1
        )

        async def select_callback(interaction):
            await interaction.response.defer()
            select.stop()

        select.callback = select_callback

        view = disnake.ui.View()
        view.add_item(select)
        await inter.followup.send("Please select the type of run:", view=view)
        await select.wait()

        selected_run_type = select.values[0]
        return selected_run_type

    async def ask_raid_time(self, inter):
        """Ask the raid leader when the raid is scheduled, using OpenAI API for parsing."""
        await inter.followup.send(
            "Please enter the date and time for the raid (e.g., `2023-10-12 18:30` or `next Friday at 6pm`):"
        )

        def check(message):
            return message.author == inter.author and message.channel == inter.channel

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=300)
            user_input = msg.content.strip()

            # Use OpenAI API to parse the date and time
            response = await self.parse_raid_time(user_input)

            if response:
                timestamp = response.get('timestamp')
                raid_datetime = datetime.fromtimestamp(timestamp)
                discord_timestamp = f"<t:{timestamp}:R>"
                return {'datetime': raid_datetime, 'timestamp': discord_timestamp}
            else:
                await inter.followup.send("Sorry, I couldn't parse the date and time. Please try again.")
                return None

        except asyncio.TimeoutError:
            await inter.followup.send("You took too long to respond. Please try scheduling the raid again.")
            return None

    async def parse_raid_time(self, user_input):
        """Use OpenAI API to parse the date and time from user input."""
        # Create a concise prompt to minimize token usage
        prompt = f"Convert the following date and time to a Unix timestamp: '{user_input}'. Return only the timestamp as an integer."

        # Make the API call
        try:
            completion = await openai.Completion.acreate(
                engine="text-davinci-003",  # You can choose the appropriate model
                prompt=prompt,
                max_tokens=10,
                temperature=0,
                n=1,
                stop=None
            )

            # Extract the timestamp from the response
            response_text = completion.choices[0].text.strip()
            timestamp = int(response_text)
            return {'timestamp': timestamp}
        except Exception as e:
            print(f"Error parsing raid time: {e}")
            return None

    async def ask_group_composition(self, inter):
        """Ask the raid leader for the group composition, using OpenAI API for parsing."""
        await inter.followup.send(
            "Please enter the group composition (e.g., `2 tanks, 2 heals, 8 dds` or `1 tank 3 heal 8 dd`):"
        )

        def check(message):
            return message.author == inter.author and message.channel == inter.channel

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=300)
            user_input = msg.content.strip()

            # Use OpenAI API to parse the group composition
            response = await self.parse_group_composition(user_input)

            if response:
                return response  # Contains 'tanks', 'heals', 'dds'
            else:
                await inter.followup.send("Sorry, I couldn't parse the group composition. Please try again.")
                return None

        except asyncio.TimeoutError:
            await inter.followup.send("You took too long to respond. Please try scheduling the raid again.")
            return None

    async def parse_group_composition(self, user_input):
        """Use OpenAI API to parse the group composition from user input."""
        # Create a concise prompt to minimize token usage
        prompt = (
            f"Extract the number of tanks, heals, and dds from the following input: '{user_input}'. "
            f"Return the result as JSON in the format: {{'tanks': int, 'heals': int, 'dds': int}}."
        )

        # Make the API call
        try:
            completion = await openai.Completion.acreate(
                engine="text-davinci-003",
                prompt=prompt,
                max_tokens=20,
                temperature=0,
                n=1,
                stop=None
            )

            # Extract the JSON from the response
            response_text = completion.choices[0].text.strip()
            group_comp = json.loads(response_text)
            return group_comp
        except Exception as e:
            print(f"Error parsing group composition: {e}")
            return None

    async def create_raid_channel(self, inter, trial, run_type, raid_time, group_comp):
        """Create the raid channel and post the roster message."""
        # Get the forum channel
        forum_channel = self.bot.get_channel(config_py.OPEN_RAID_CHANNEL)
        if not forum_channel:
            await inter.followup.send("Could not find the raid forum channel.")
            return

        # Create the channel name
        date_str = raid_time['datetime'].strftime('%Y-%m-%d %H:%M')
        trial_abbr = config_py.trial_abbreviations.get(trial, trial)
        channel_name = f"{date_str} {trial_abbr} {run_type}"

        # Get the trial image
        trial_image = config_py.raid_pictures.get(trial, None)

        # Create the forum post
        embed = disnake.Embed(
            title=f"{trial} - {run_type}",
            description=f"Raid scheduled for {raid_time['timestamp']}",
            color=disnake.Color.blue()
        )
        if trial_image:
            embed.set_image(url=trial_image)

        # Add the roster fields
        embed.add_field(name="Tanks", value=f"0/{group_comp['tanks']}", inline=False)
        embed.add_field(name="Healers", value=f"0/{group_comp['heals']}", inline=False)
        embed.add_field(name="DDs", value=f"0/{group_comp['dds']}", inline=False)
        embed.add_field(name="Reserves", value="0", inline=False)

        # Create the view with sign-up buttons
        view = RaidSignUpView(group_comp)

        # Create the forum post
        await forum_channel.create_thread(
            name=channel_name,
            content=f"<@&{config_py.trial_ping_roles[trial]}>",
            embed=embed,
            view=view
        )

        await inter.followup.send("Raid scheduled successfully.")

class RaidSignUpView(disnake.ui.View):
    """View containing the sign-up buttons."""
    def __init__(self, group_comp):
        super().__init__(timeout=None)
        self.group_comp = group_comp
        self.signups = {
            'tanks': [],
            'heals': [],
            'dds': [],
            'reserves': []
        }

        # Create buttons for each role
        self.add_item(RoleButton(label="Tank", custom_id="signup_tank"))
        self.add_item(RoleButton(label="Healer", custom_id="signup_heal"))
        self.add_item(RoleButton(label="DD", custom_id="signup_dd"))
        self.add_item(RoleButton(label="Unsign", custom_id="unsign", style=disnake.ButtonStyle.danger))

    async def update_embed(self, message):
        """Update the roster embed."""
        embed = message.embeds[0]

        # Prepare the lists of signed-up users
        tanks_list = '\n'.join([user.mention for user in self.signups['tanks']]) or "None"
        heals_list = '\n'.join([user.mention for user in self.signups['heals']]) or "None"
        dds_list = '\n'.join([user.mention for user in self.signups['dds']]) or "None"
        reserves_list = '\n'.join([user.mention for user in self.signups['reserves']]) or "None"

        # Update the fields
        embed.set_field_at(0, name=f"Tanks ({len(self.signups['tanks'])}/{self.group_comp['tanks']})", value=tanks_list, inline=False)
        embed.set_field_at(1, name=f"Healers ({len(self.signups['heals'])}/{self.group_comp['heals']})", value=heals_list, inline=False)
        embed.set_field_at(2, name=f"DDs ({len(self.signups['dds'])}/{self.group_comp['dds']})", value=dds_list, inline=False)
        embed.set_field_at(3, name=f"Reserves ({len(self.signups['reserves'])})", value=reserves_list, inline=False)

        # Update the message
        await message.edit(embed=embed, view=self)

class RoleButton(disnake.ui.Button):
    """Button for signing up as a specific role."""
    def __init__(self, label, custom_id, style=disnake.ButtonStyle.primary):
        super().__init__(label=label, custom_id=custom_id, style=style)

    async def callback(self, interaction: disnake.MessageInteraction):
        view: RaidSignUpView = self.view
        user = interaction.author

        # Handle unsign
        if self.custom_id == "unsign":
            removed = False
            for role in ['tanks', 'heals', 'dds', 'reserves']:
                if user in view.signups[role]:
                    view.signups[role].remove(user)
                    removed = True
            if removed:
                await interaction.response.send_message("You have been removed from the sign-up.", ephemeral=True)
                await view.update_embed(interaction.message)
            else:
                await interaction.response.send_message("You are not signed up.", ephemeral=True)
            return

        # Determine role
        role = self.custom_id.split('_')[-1] + 's'  # Convert to plural
        max_slots = view.group_comp[role]

        # Check if user is already signed up
        if user in view.signups[role]:
            await interaction.response.send_message("You are already signed up for this role.", ephemeral=True)
            return

        # Check if slot is available
        if len(view.signups[role]) < max_slots:
            # Remove user from other roles
            for other_role in ['tanks', 'heals', 'dds', 'reserves']:
                if user in view.signups[other_role]:
                    view.signups[other_role].remove(user)
            view.signups[role].append(user)
            await interaction.response.send_message(f"You have signed up as a {self.label}.", ephemeral=True)
        else:
            # Add to reserves
            if user not in view.signups['reserves']:
                view.signups['reserves'].append(user)
                await interaction.response.send_message("All slots are full. You have been added to reserves.", ephemeral=True)
            else:
                await interaction.response.send_message("You are already in the reserves.", ephemeral=True)
        await view.update_embed(interaction.message)

def setup(bot):
    bot.add_cog(Scheduler(bot))
