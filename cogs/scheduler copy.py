import re
import uuid
from datetime import datetime
import disnake
from disnake.ext import commands, tasks

# Import your custom config where your DB collections are defined
import config_py

# --- Configuration & Constants ---
FORUM_CHANNEL_ID = 1518727469191135293
SETUP_THREAD_ID = 1518727802919321601

# --- Helper Functions ---
def build_raid_embed(raid_data: dict) -> disnake.Embed:
    embed = disnake.Embed(
        title=raid_data["name"],
        description=raid_data["description"],
        color=0x2b2d31
    )
    embed.add_field(name="Event lead", value=f"<@{raid_data['lead_id']}>", inline=False)
    
    timestamp = raid_data["unix_time"]
    embed.add_field(name="Time", value=f"<t:{timestamp}:F> · <t:{timestamp}:R>", inline=False)

    tanks = "\n".join(raid_data["roster"]["tanks"]) or "Empty"
    heals = "\n".join(raid_data["roster"]["healers"]) or "Empty"
    dds = "\n".join(raid_data["roster"]["dds"]) or "Empty"
    bench = ", ".join(raid_data["roster"]["bench"]) or "None"

    embed.add_field(name=f"🛡️ Tank ({len(raid_data['roster']['tanks'])}/{raid_data['limits']['tanks']})", value=tanks, inline=True)
    embed.add_field(name=f"💚 Healer ({len(raid_data['roster']['healers'])}/{raid_data['limits']['healers']})", value=heals, inline=True)
    embed.add_field(name=f"⚔️ DD ({len(raid_data['roster']['dds'])}/{raid_data['limits']['dds']})", value=dds, inline=True)
    embed.add_field(name="🪑 Bench", value=bench, inline=False)
    
    return embed

# --- UI Components ---
class RaidRosterView(disnake.ui.View):
    def __init__(self, raid_id: str, active_raids_db):
        super().__init__(timeout=None)
        self.raid_id = raid_id
        self.db = active_raids_db

    async def update_roster(self, inter: disnake.MessageInteraction, role: str):
        # Synchronous DB call
        raid_data = self.db.find_one({"_id": self.raid_id})
        if not raid_data:
            return await inter.response.send_message("Raid data not found.", ephemeral=True)

        user_mention = inter.author.mention
        
        for r in ["tanks", "healers", "dds", "bench"]:
            if user_mention in raid_data["roster"][r]:
                raid_data["roster"][r].remove(user_mention)

        max_slots = raid_data["limits"].get(role, 99)
        if len(raid_data["roster"][role]) < max_slots or role == "bench":
            raid_data["roster"][role].append(user_mention)
        else:
            raid_data["roster"]["bench"].append(user_mention)
            await inter.followup.send(f"{role.capitalize()} is full. You were added to the bench.", ephemeral=True)

        # Synchronous DB update
        self.db.update_one({"_id": self.raid_id}, {"$set": {"roster": raid_data["roster"]}})
        
        embed = build_raid_embed(raid_data)
        await inter.message.edit(embed=embed, view=self)
        if not inter.response.is_done():
            await inter.response.defer()

    @disnake.ui.button(label="Tank", emoji="🛡️", style=disnake.ButtonStyle.primary, custom_id="raid_tank")
    async def btn_tank(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self.update_roster(inter, "tanks")

    @disnake.ui.button(label="Healer", emoji="💚", style=disnake.ButtonStyle.success, custom_id="raid_heal")
    async def btn_healer(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self.update_roster(inter, "healers")

    @disnake.ui.button(label="DD", emoji="⚔️", style=disnake.ButtonStyle.danger, custom_id="raid_dd")
    async def btn_dd(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self.update_roster(inter, "dds")

    @disnake.ui.button(label="Bench", emoji="🪑", style=disnake.ButtonStyle.secondary, custom_id="raid_bench")
    async def btn_bench(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self.update_roster(inter, "bench")

    @disnake.ui.button(label="Guide", emoji="❓", style=disnake.ButtonStyle.secondary, custom_id="raid_guide")
    async def btn_guide(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        raid_data = self.db.find_one({"_id": self.raid_id})
        if raid_data and raid_data.get("tutorial_link"):
            await inter.author.send(f"**Guide for {raid_data['name']}:**\n{raid_data['tutorial_link']}")
            await inter.response.send_message("Guide sent to your DMs.", ephemeral=True)
        else:
            await inter.response.send_message("No guide available for this raid.", ephemeral=True)

class RaidCreationModal(disnake.ui.Modal):
    def __init__(self, template: dict, cog):
        self.template = template
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label='Time (YYYY-MM-DD HH:MM)',
                placeholder='2026-06-25 20:00',
                custom_id='raid_time',
                style=disnake.TextInputStyle.short,
                required=True
            ),
            disnake.ui.TextInput(
                label='Raid Requirements & Description',
                style=disnake.TextInputStyle.paragraph,
                custom_id='description',
                placeholder='e.g., vSS clear required, parsing 100k+',
                required=True
            )
        ]
        super().__init__(title='Schedule Raid', custom_id='schedule_raid_modal', components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        try:
            dt = datetime.strptime(inter.text_values["raid_time"], "%Y-%m-%d %H:%M")
            unix_time = int(dt.timestamp())
        except ValueError:
            return await inter.response.send_message("Invalid time format. Please use YYYY-MM-DD HH:MM.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        await self.cog.execute_raid_creation(inter, self.template, unix_time, inter.text_values["description"])

class TemplateSelect(disnake.ui.Select):
    def __init__(self, templates: list, cog):
        options = [disnake.SelectOption(label=t["name"], description=f"{t['limits']['tanks']}T / {t['limits']['healers']}H / {t['limits']['dds']}DD") for t in templates]
        super().__init__(placeholder="Select a raid template...", min_values=1, max_values=1, options=options)
        self.templates = {t["name"]: t for t in templates}
        self.cog = cog

    async def callback(self, inter: disnake.MessageInteraction):
        selected_template = self.templates[self.values[0]]
        modal = RaidCreationModal(selected_template, self.cog)
        await inter.response.send_modal(modal)

class TemplateSelectView(disnake.ui.View):
    def __init__(self, templates: list, cog):
        super().__init__(timeout=60)
        self.add_item(TemplateSelect(templates, cog))

class SetupRaidView(disnake.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @disnake.ui.button(label="ADD A RAID", style=disnake.ButtonStyle.primary, custom_id="init_add_raid")
    async def add_raid_btn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Synchronous DB call for templates
        templates = list(self.cog.raid_templates_db.find({}).limit(25))
        
        if not templates:
            return await inter.response.send_message("No raid templates exist. An admin must add them first.", ephemeral=True)
        
        view = TemplateSelectView(templates, self.cog)
        await inter.response.send_message("Select the type of raid you are hosting:", view=view, ephemeral=True)


# --- Core Logic ---
class RaidPlannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.plus_regex = re.compile(r"^\+(dd|healer|tank)", re.IGNORECASE)
        
        # Load directly from config_py 
        self.raid_templates_db = config_py.raid_templates
        self.active_raids_db = config_py.active_raids

    @commands.Cog.listener()
    async def on_ready(self):
        """Fires when the bot is fully connected and event loop is running."""
        self.bot.add_view(SetupRaidView(self))
        if not self.cleanup_expired_roles.is_running():
            self.cleanup_expired_roles.start()

    def cog_unload(self):
        if self.cleanup_expired_roles.is_running():
            self.cleanup_expired_roles.cancel()

    @commands.slash_command(
        name="add_raid_template", 
        description="Owner: Define a new raid type.",
        default_member_permissions=disnake.Permissions(administrator=True)
    )
    async def add_raid_template(
        self, 
        inter: disnake.ApplicationCommandInteraction, 
        name: str, 
        interest_role: disnake.Role, 
        clear_role: disnake.Role, 
        tanks: int, 
        healers: int, 
        dds: int, 
        tutorial_link: str
    ):
        template = {
            "name": name,
            "interest_role_id": interest_role.id,
            "clear_role_id": clear_role.id,
            "limits": {"tanks": tanks, "healers": healers, "dds": dds},
            "tutorial_link": tutorial_link
        }
        self.raid_templates_db.insert_one(template)
        await inter.response.send_message(f"Raid template '{name}' saved.", ephemeral=True)

    @commands.slash_command(
        name="spawn_setup_menu", 
        description="Owner: Spawns the setup menu in the designated channel.",
        default_member_permissions=disnake.Permissions(administrator=True)
    )
    async def spawn_setup_menu(self, inter: disnake.ApplicationCommandInteraction):
        thread = self.bot.get_channel(SETUP_THREAD_ID)
        if not thread:
            return await inter.response.send_message("Setup thread not found.", ephemeral=True)
        
        await thread.send("Click below to set up a new raid.", view=SetupRaidView(self))
        await inter.response.send_message("Menu spawned.", ephemeral=True)

    async def execute_raid_creation(self, inter: disnake.ModalInteraction, template: dict, unix_time: int, description: str):
        guild = inter.guild
        temp_role_name = f"{template['name']} - <t:{unix_time}:d>"
        temp_role = await guild.create_role(name=temp_role_name, mentionable=True, reason="Active Raid Role")
        
        interest_role = guild.get_role(template["interest_role_id"])
        clear_role = guild.get_role(template["clear_role_id"])
        
        for member in guild.members:
            if interest_role in member.roles and clear_role in member.roles:
                try:
                    await member.add_roles(temp_role)
                except disnake.Forbidden:
                    pass

        raid_id = str(uuid.uuid4())
        raid_data = {
            "_id": raid_id,
            "name": template["name"],
            "description": description,
            "lead_id": inter.author.id,
            "unix_time": unix_time,
            "roster": {"tanks": [], "healers": [], "dds": [], "bench": []},
            "limits": template["limits"],
            "tutorial_link": template["tutorial_link"],
            "temp_role_id": temp_role.id,
            "role_deleted": False
        }

        forum_channel = guild.get_channel(FORUM_CHANNEL_ID)
        thread_name = f"{template['name']} - {datetime.fromtimestamp(unix_time).strftime('%Y-%m-%d')}"
        
        thread_with_msg = await forum_channel.create_thread(
            name=thread_name,
            content=f"{temp_role.mention} A new raid has been scheduled!"
        )
        
        embed = build_raid_embed(raid_data)
        view = RaidRosterView(raid_id, self.active_raids_db)
        self.bot.add_view(view)
        
        msg = await thread_with_msg.thread.send(embed=embed, view=view)
        
        raid_data["thread_id"] = thread_with_msg.thread.id
        raid_data["message_id"] = msg.id
        
        # Synchronous insert
        self.active_raids_db.insert_one(raid_data)

        await inter.followup.send("Raid created and roster posted.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot or not message.guild:
            return

        is_raid_thread = self.active_raids_db.find_one({"thread_id": message.channel.id})
        if not is_raid_thread:
            return

        match = self.plus_regex.match(message.content.strip())
        if match:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, please use the buttons on the roster to sign up.", delete_after=5)
            except disnake.Forbidden:
                pass

    @tasks.loop(minutes=5.0)
    async def cleanup_expired_roles(self):
        current_time = int(datetime.now().timestamp())
        
        expired_raids = list(self.active_raids_db.find({
            "unix_time": {"$lt": current_time},
            "role_deleted": False
        }))
        
        for raid in expired_raids:
            # Assumes bot operates in one guild primarily. 
            guild = self.bot.guilds[0] 
            role = guild.get_role(raid["temp_role_id"])
            
            if role:
                try:
                    await role.delete(reason="Raid event concluded.")
                except disnake.Forbidden:
                    pass
            
            self.active_raids_db.update_one(
                {"_id": raid["_id"]},
                {"$set": {"role_deleted": True}}
            )

def setup(bot):
    bot.add_cog(RaidPlannerCog(bot))