import datetime
import logging
import re
from typing import List, Dict, Tuple

import disnake
from disnake.ext import commands, tasks
from disnake.ext.commands import Context

import config_py

logger = logging.getLogger("category_manager")

# --- Constants ---
BEHAVIOR_MESSAGES = "messages"
BEHAVIOR_IMAGES = "image_uploads"
BEHAVIOR_REACTIONS = "reaction_added"
LOG_THREAD_ID = 1521095581068693655

TRACKABLE_BEHAVIORS = [
    disnake.SelectOption(label="Messages", value=BEHAVIOR_MESSAGES, description="Track standard text messages"),
    disnake.SelectOption(label="Image Uploads", value=BEHAVIOR_IMAGES, description="Track messages containing attachments"),
    disnake.SelectOption(label="Reaction Added", value=BEHAVIOR_REACTIONS, description="Track when a user adds a reaction"),
]


class BehaviorSelect(disnake.ui.Select):
    def __init__(self, category_name: str, channel_id: str, current_behaviors: List[str]):
        self.category_name = category_name
        self.channel_id = channel_id
        
        # Pre-select existing behaviors if configuring an already assigned channel
        options = []
        for opt in TRACKABLE_BEHAVIORS:
            new_opt = disnake.SelectOption(
                label=opt.label, 
                value=opt.value, 
                description=opt.description,
                default=(opt.value in current_behaviors)
            )
            options.append(new_opt)

        super().__init__(
            placeholder="Select behaviors to track...",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: disnake.MessageInteraction):
        selected_behaviors = self.values

        # Update Channel (Roles) Collection
        config_py.botServerRoles.update_one(
            {"channel_id": self.channel_id},
            {"$set": {
                "category": self.category_name,
                "tracked_behaviors": selected_behaviors
            }},
            upsert=True
        )

        # Update Category Collection
        config_py.botServerCategories.update_one(
            {"name": self.category_name, "guild_id": str(interaction.guild_id)},
            {"$addToSet": {"associated_channels": self.channel_id}}
        )

        await interaction.response.edit_message(
            content=f"Successfully assigned <#{self.channel_id}> to **{self.category_name}** tracking: {', '.join(selected_behaviors)}.",
            view=None
        )


class BehaviorSelectView(disnake.ui.View):
    def __init__(self, category_name: str, channel_id: str, current_behaviors: List[str]):
        super().__init__(timeout=120)
        self.add_item(BehaviorSelect(category_name, channel_id, current_behaviors))


class UnassignSelect(disnake.ui.Select):
    def __init__(self, category_name: str, channels: List[Dict], guild_id: str):
        self.category_name = category_name
        self.guild_id = guild_id
        
        options = []
        for ch in channels[:25]: # Select menus have a max of 25 options
            options.append(disnake.SelectOption(
                label=ch.get("name", "Unknown Channel"),
                value=ch["channel_id"],
                description=f"ID: {ch['channel_id']}"
            ))

        super().__init__(
            placeholder="Select a channel to unassign...",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: disnake.MessageInteraction):
        # We can unassign multiple at once
        for channel_id in self.values:
            config_py.botServerRoles.update_one(
                {"channel_id": channel_id},
                {"$set": {"category": None, "tracked_behaviors": []}}
            )
            config_py.botServerCategories.update_one(
                {"name": self.category_name, "guild_id": self.guild_id},
                {"$pull": {"associated_channels": channel_id}}
            )

        await interaction.response.edit_message(
            content=f"Successfully unassigned {len(self.values)} channel(s) from **{self.category_name}**.",
            view=None
        )

class UnassignSelectView(disnake.ui.View):
    def __init__(self, category_name: str, channels: List[Dict], guild_id: str):
        super().__init__(timeout=120)
        self.add_item(UnassignSelect(category_name, channels, guild_id))


class CategoryManager(commands.Cog, name="category_manager"):
    def __init__(self, bot):
        self.bot = bot
        self.channel_scanner.start()

    def cog_unload(self):
        self.channel_scanner.cancel()
        
    async def log_to_discord(self, content: str):
        """Helper to log events directly to a Discord thread."""
        thread = self.bot.get_channel(LOG_THREAD_ID)
        
        if not thread:
            try:
                thread = await self.bot.fetch_channel(LOG_THREAD_ID)
            except (disnake.NotFound, disnake.HTTPException):
                logger.error(f"Could not fetch log thread {LOG_THREAD_ID}")
                return
        
        try:
            await thread.send(content)
        except disnake.HTTPException as e:
            logger.error(f"Failed to send log to thread: {e}")

    # --- Tasks ---
    @tasks.loop(hours=2.0)
    async def channel_scanner(self):
        """Scans all guilds and extracts channels/threads to the DB without overwriting categories."""
        logger.info("Starting scheduled channel scan...")
        await self.log_to_discord("🔍 Starting scheduled background channel scan...")
        
        total_found, total_added = await self._execute_scan()
        
        logger.info(f"Scheduled channel scan complete. Found: {total_found}, Added: {total_added}.")
        await self.log_to_discord(
            f"✅ Scheduled background channel scan complete.\n"
            f"📊 **Results:** {total_found} channels scanned, {total_added} new channels added."
        )

    @channel_scanner.before_loop
    async def before_scanner(self):
        await self.bot.wait_until_ready()

    async def _execute_scan(self) -> Tuple[int, int]:
        total_found = 0
        total_added = 0
        
        for guild in self.bot.guilds:
            # Standard channels and Forum channels
            for channel in guild.channels:
                total_found += 1
                if self._upsert_channel(channel):
                    total_added += 1
            
            # Active threads (includes threads in text channels and active forum posts)
            for thread in guild.threads:
                total_found += 1
                if self._upsert_channel(thread):
                    total_added += 1
                    
        return total_found, total_added

    def _upsert_channel(self, channel) -> bool:
        """Returns True if the channel was newly added, False if updated/existed."""
        existing = config_py.botServerRoles.find_one({"channel_id": str(channel.id)})
        
        update_data = {
            "name": channel.name,
            "guild_id": str(channel.guild.id),
            "type": str(channel.type)
        }

        # If it doesn't exist, set the mandatory fields as requested
        if not existing:
            update_data["category"] = None
            update_data["tracked_behaviors"] = []

        result = config_py.botServerRoles.update_one(
            {"channel_id": str(channel.id)},
            {"$set": update_data},
            upsert=True
        )
        
        return result.upserted_id is not None

    # --- Commands ---
    @commands.slash_command(name="roles_scan", description="Manually scan and register all server channels and threads.")
    @commands.has_permissions(administrator=True)
    async def roles_scan(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        total_found, total_added = await self._execute_scan()
        await inter.edit_original_response(
            content=f"Channel scan complete. Found **{total_found}** channels/threads, "
                    f"added **{total_added}** new entries. Database updated without overwriting existing categories."
        )

    @commands.slash_command(name="categories_create", description="Create a new channel tracking category.")
    @commands.has_permissions(administrator=True)
    async def categories_create(
        self, 
        inter: disnake.ApplicationCommandInteraction, 
        name: str = commands.Param(description="Name of the new category")
    ):
        if not inter.guild:
            await inter.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        existing = config_py.botServerCategories.find_one({"name": name, "guild_id": str(inter.guild.id)})
        if existing:
            await inter.response.send_message(f"Category **{name}** already exists.", ephemeral=True)
            return

        config_py.botServerCategories.insert_one({
            "name": name,
            "guild_id": str(inter.guild.id),
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "created_by": str(inter.author.id),
            "associated_channels": [],
            "is_active": True
        })
        
        await inter.response.send_message(f"Category **{name}** created successfully.")

    @commands.slash_command(name="categories_assign", description="Assign a channel to a category and set tracked behaviors.")
    @commands.has_permissions(administrator=True)
    async def categories_assign(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        category: str,
        channel: str
    ):
        if not inter.guild:
            await inter.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        # Extract channel ID from the autocomplete string format "name (id)"
        try:
            channel_id = channel.split("(")[-1].strip(")")
        except IndexError:
            await inter.response.send_message("Invalid channel format selected.", ephemeral=True)
            return

        cat_doc = config_py.botServerCategories.find_one({"name": category, "guild_id": str(inter.guild.id)})
        if not cat_doc:
            await inter.response.send_message("Category not found.", ephemeral=True)
            return

        ch_doc = config_py.botServerRoles.find_one({"channel_id": channel_id, "guild_id": str(inter.guild.id)})
        current_behaviors = ch_doc.get("tracked_behaviors", []) if ch_doc else []

        view = BehaviorSelectView(category, channel_id, current_behaviors)
        await inter.response.send_message(f"Select behaviors to track for <#{channel_id}> in category **{category}**:", view=view)

    @commands.slash_command(name="categories_delete", description="Delete an existing category.")
    @commands.has_permissions(administrator=True)
    async def categories_delete(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        category: str
    ):
        if not inter.guild:
            await inter.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        cat_doc = config_py.botServerCategories.find_one({"name": category, "guild_id": str(inter.guild.id)})
        if not cat_doc:
            await inter.response.send_message("Category not found.", ephemeral=True)
            return

        if cat_doc.get("associated_channels"):
            await inter.response.send_message(
                f"Cannot delete **{category}**. It still has {len(cat_doc['associated_channels'])} channels assigned to it. Unassign them first.", 
                ephemeral=True
            )
            return

        config_py.botServerCategories.delete_one({"name": category, "guild_id": str(inter.guild.id)})
        await inter.response.send_message(f"Category **{category}** has been deleted.")

    @commands.slash_command(name="categories_unassign", description="Unassign channels from a category.")
    @commands.has_permissions(administrator=True)
    async def categories_unassign(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        category: str
    ):
        if not inter.guild:
            await inter.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        cat_doc = config_py.botServerCategories.find_one({"name": category, "guild_id": str(inter.guild.id)})
        if not cat_doc or not cat_doc.get("associated_channels"):
            await inter.response.send_message("Category not found or has no channels assigned.", ephemeral=True)
            return

        # Fetch channel documents for the UI
        channels = list(config_py.botServerRoles.find({"channel_id": {"$in": cat_doc["associated_channels"]}, "guild_id": str(inter.guild.id)}))
        
        if not channels:
            await inter.response.send_message("No channel data found for assigned IDs.", ephemeral=True)
            return

        view = UnassignSelectView(category, channels, str(inter.guild.id))
        await inter.response.send_message(f"Select channels to unassign from **{category}**:", view=view)

    @commands.slash_command(name="categories_show", description="Show current allocation of categories.")
    @commands.has_permissions(administrator=True)
    async def categories_show(self, inter: disnake.ApplicationCommandInteraction):
        if not inter.guild:
            await inter.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        categories = config_py.botServerCategories.find({"is_active": True, "guild_id": str(inter.guild.id)})
        
        embed = disnake.Embed(title="Channel Category Allocations", color=disnake.Color.blurple())
        
        count = 0
        for cat in categories:
            channels = cat.get("associated_channels", [])
            if not channels:
                value = "*No channels assigned*"
            else:
                value = ", ".join([f"<#{ch}>" for ch in channels])
            
            embed.add_field(name=f"📁 {cat['name']}", value=value, inline=False)
            count += 1

        if count == 0:
            embed.description = "No active categories found for this server."

        await inter.response.send_message(embed=embed)

# --- Autocompleters ---
    @categories_assign.autocomplete("category")
    @categories_delete.autocomplete("category")
    @categories_unassign.autocomplete("category")
    async def _category_autocomplete(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        if not inter.guild_id:
            return []
        
        # Limit to 25 to stay within Discord's UI limit
        query = {"guild_id": str(inter.guild_id)}
        if user_input:
            query["name"] = {"$regex": re.escape(user_input), "$options": "i"}
            
        categories = list(config_py.botServerCategories.find(query).limit(25))
        
        # Ensure labels are unique
        results = []
        for cat in categories:
            name = cat.get("name", "Unnamed Category")
            # If names are duplicated, this helps distinguish them
            results.append(name[:100])
            
        return list(set(results)) # Ensure uniqueness

    @categories_assign.autocomplete("channel")
    async def _channel_autocomplete(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        if not inter.guild_id:
            return []
            
        query = {"guild_id": str(inter.guild_id)}
        if user_input:
            query["name"] = {"$regex": re.escape(user_input), "$options": "i"}
            
        channels = list(config_py.botServerRoles.find(query).limit(25))
        
        results = []
        for ch in channels:
            name = ch.get("name", "Unknown")
            cid = ch.get("channel_id", "0")
            # Force unique labels by including the ID
            label = f"{name} ({cid})"[:100]
            results.append(label)
            
        return results


#def setup(bot):
  #  bot.add_cog(CategoryManager(bot))