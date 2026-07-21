import disnake
from disnake.ext import commands
import openai
import random
import re
import os
import sys
import json
from datetime import datetime
from pymongo import MongoClient

# ---------------------------
# Load Config & Setup Database
# ---------------------------
if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
with open("config.json") as file:
    config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
import config_py  # Expects: MONGO_URI, DND_FORUM_CHANNEL_ID, PROXY_API

client = MongoClient(config_py.MONGO_URI)
db = client["dodo_dnd"]
sessions_collection = db["sessions"]
characters_collection = db["characters"]
actions_collection = db["actions"]

openai.api_key = config_py.PROXY_API
openai.api_base = "https://api.proxyapi.ru/openai/v1"

# ---------------------------
# Modals
# ---------------------------
class SessionCreationModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        components = [
            disnake.ui.TextInput(
                label="Session Title",
                custom_id="session_title",
                style=disnake.TextInputStyle.short,
                placeholder="Enter the title of your session",
                max_length=100
            ),
            disnake.ui.TextInput(
                label="Scenario Description",
                custom_id="scenario_description",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Describe the scenario for this session",
                max_length=1000
            )
        ]
        super().__init__(title="Create New Session", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        session_title = inter.text_values["session_title"]
        scenario_description = inter.text_values["scenario_description"]
        session_id = int(datetime.utcnow().timestamp())

        session_data = {
            "session_id": session_id,
            "title": session_title,
            "description": scenario_description,
            "players": [],
            "combat": None,
            "history": "",  # initialize session history as empty string
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        sessions_collection.insert_one(session_data)

        channel = self.bot.get_channel(config_py.DND_FORUM_CHANNEL_ID)
        if channel is None:
            await inter.response.send_message("Error: Session channel not found.", ephemeral=True)
            return

        embed = disnake.Embed(
            title=f"Session: {session_title}",
            description=scenario_description,
            color=disnake.Color.blurple(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Session ID: {session_id}")

        view = SessionJoinView(self.bot, session_id)
        message = await channel.send(embed=embed, view=view)
        sessions_collection.update_one({"session_id": session_id}, {"$set": {"message_id": message.id}})
        await inter.response.send_message(f"Session **{session_title}** created and posted in {channel.mention}.", ephemeral=True)

class CharacterCreationModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot, session_id: int, user: disnake.User):
        self.bot = bot
        self.session_id = session_id
        self.user = user
        components = [
            disnake.ui.TextInput(
                label="Character Name",
                custom_id="character_name",
                style=disnake.TextInputStyle.short,
                placeholder="Enter your character's name",
                max_length=50
            ),
            disnake.ui.TextInput(
                label="Character Class",
                custom_id="character_class",
                style=disnake.TextInputStyle.short,
                placeholder="e.g., Fighter, Wizard, Rogue",
                max_length=50
            ),
            disnake.ui.TextInput(
                label="Character Race",
                custom_id="character_race",
                style=disnake.TextInputStyle.short,
                placeholder="e.g., Human, Elf, Dwarf",
                max_length=50
            )
        ]
        super().__init__(title="Create Your Character", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        char_name = inter.text_values["character_name"]
        char_class = inter.text_values["character_class"]
        char_race = inter.text_values["character_race"]
        # Use a standard array to keep stats balanced
        stats = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}

        character_data = {
            "player_id": self.user.id,
            "session_id": self.session_id,
            "name": char_name,
            "class": char_class,
            "race": char_race,
            "stats": stats,
            "hp": 10,
            "ac": 10,
            "equipment": [],
            "relationships": {},
            "history": "",  # initialize character history as empty string
            "created_at": datetime.utcnow()
        }
        characters_collection.update_one(
            {"player_id": self.user.id, "session_id": self.session_id},
            {"$set": character_data},
            upsert=True
        )
        sessions_collection.update_one(
            {"session_id": self.session_id},
            {"$addToSet": {"players": self.user.id}}
        )
        await inter.response.send_message(f"Character **{char_name}** created and added to session {self.session_id}!", ephemeral=True)

class ActionModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot, session_id: int, user: disnake.User):
        self.bot = bot
        self.session_id = session_id
        self.user = user
        components = [
            disnake.ui.TextInput(
                label="Describe your action",
                custom_id="action_description",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Describe what your character does...",
                max_length=1000
            )
        ]
        super().__init__(title="Take an Action", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        action_desc = inter.text_values["action_description"]
        # Fetch character; if none exists, instruct to sign up first.
        character = characters_collection.find_one({"player_id": self.user.id, "session_id": self.session_id})
        if not character:
            await inter.response.send_message("No character found in this session. Please sign up first.", ephemeral=True)
            return

        # Retrieve session and character history
        session_doc = sessions_collection.find_one({"session_id": self.session_id})
        session_history = session_doc.get("history", "") if session_doc else ""
        character_history = character.get("history", "")

        # Build a prompt that includes historical context
        system_content = (
            "You are a genius Dungeon Master for a DnD 5e game. "
            "You keep a detailed but concise history of the session and each character. "
            "Provide an immersive and context-aware narrative resolution for the following action."
        )
        user_content = (
            f"Session History:\n{session_history}\n\n"
            f"Character History:\n{character_history}\n\n"
            f"New Action:\n{action_desc}\n"
        )
        try:
            # First GPT call: generate narrative response.
            narrative_resp = openai.ChatCompletion.create(
                model="gpt-4o",
                temperature=1,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ]
            )
            gm_narrative = narrative_resp.choices[0].message.content
        except Exception as e:
            gm_narrative = "Error generating GM response. Please try again."

        # Second GPT call: generate a concise bullet summary update
        summary_prompt = (
            "Based on the following session history, character history, and new action, "
            "produce a concise bullet-point summary update that captures key events, changes in inventory, dialogue notes, and notable outcomes. "
            "Limit your answer to 3 bullet points.\n\n"
            f"Session History:\n{session_history}\n\n"
            f"Character History:\n{character_history}\n\n"
            f"New Action:\n{action_desc}\n\n"
            "Bullet Summary:"
        )
        try:
            summary_resp = openai.ChatCompletion.create(
                model="gpt-4o",
                temperature=0.7,
                messages=[
                    {"role": "system", "content": "You produce concise bullet-point summaries for game events."},
                    {"role": "user", "content": summary_prompt}
                ]
            )
            summary_text = summary_resp.choices[0].message.content.strip()
        except Exception as e:
            summary_text = "- No summary available."

        # Update session and character history by appending the new summary
        new_session_history = (session_history + "\n" + summary_text).strip()
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"history": new_session_history}})
        new_character_history = (character_history + "\n" + summary_text).strip()
        characters_collection.update_one(
            {"player_id": self.user.id, "session_id": self.session_id},
            {"$set": {"history": new_character_history}}
        )

        # Save the action in the actions collection
        action_data = {
            "session_id": self.session_id,
            "player_id": self.user.id,
            "character_id": character.get("_id"),
            "action_description": action_desc,
            "gm_narrative": gm_narrative,
            "summary": summary_text,
            "timestamp": datetime.utcnow()
        }
        actions_collection.insert_one(action_data)

        # Post the GM response in the session channel (replying to the session message)
        session_doc = sessions_collection.find_one({"session_id": self.session_id})
        if session_doc and "message_id" in session_doc:
            channel = self.bot.get_channel(config_py.DND_FORUM_CHANNEL_ID)
            if channel:
                try:
                    message = await channel.fetch_message(session_doc["message_id"])
                    await message.reply(f"**{character['name']}**: {action_desc}\n**GM**: {gm_narrative}\n\n**Update:**\n{summary_text}")
                except Exception as e:
                    print(f"Failed to send reply in session channel: {e}")

        await inter.response.send_message("Action submitted! Check the session channel for the outcome.", ephemeral=True)

class InitiativeModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot, session_id: int, user: disnake.User):
        self.bot = bot
        self.session_id = session_id
        self.user = user
        components = [
            disnake.ui.TextInput(
                label="Enter your initiative roll (1d20 + modifier)",
                custom_id="initiative_roll",
                style=disnake.TextInputStyle.short,
                placeholder="e.g., 15",
                max_length=3
            )
        ]
        super().__init__(title="Enter Initiative", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        try:
            initiative_value = int(inter.text_values["initiative_roll"])
        except ValueError:
            await inter.response.send_message("Invalid input. Please enter a numeric value.", ephemeral=True)
            return

        session = sessions_collection.find_one({"session_id": self.session_id})
        if not session:
            await inter.response.send_message("Session not found.", ephemeral=True)
            return

        combat = session.get("combat", {"active": True, "initiative_order": [], "current_turn": 0})
        character = characters_collection.find_one({"player_id": self.user.id, "session_id": self.session_id})
        char_name = character["name"] if character else "Unknown"
        entry = {"initiative": initiative_value, "player_id": self.user.id, "character_name": char_name}
        # Remove any previous initiative entry for this user
        combat["initiative_order"] = [e for e in combat.get("initiative_order", []) if e["player_id"] != self.user.id]
        combat["initiative_order"].append(entry)
        combat["initiative_order"].sort(key=lambda x: x["initiative"], reverse=True)
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": combat}})
        await inter.response.send_message(f"Your initiative ({initiative_value}) has been recorded.", ephemeral=True)

class DiceRollModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        components = [
            disnake.ui.TextInput(
                label="Dice Roll (e.g., 1d20, 2d6)",
                custom_id="dice_input",
                style=disnake.TextInputStyle.short,
                placeholder="Enter dice roll in NdM format",
                max_length=10
            )
        ]
        super().__init__(title="Roll Dice", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        dice_str = inter.text_values["dice_input"]
        match = re.match(r"(\d+)d(\d+)", dice_str.lower())
        if not match:
            await inter.response.send_message("Invalid dice format. Please use NdM (e.g., 1d20).", ephemeral=True)
            return
        num_dice = int(match.group(1))
        dice_size = int(match.group(2))
        results = [random.randint(1, dice_size) for _ in range(num_dice)]
        total = sum(results)
        await inter.response.send_message(f"Rolled {dice_str}: {results} (Total: {total})", ephemeral=True)

# ---------------------------
# Views (Buttons)
# ---------------------------
class SessionJoinView(disnake.ui.View):
    def __init__(self, bot: commands.Bot, session_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id

    @disnake.ui.button(label="Sign Up", style=disnake.ButtonStyle.green, custom_id="session_join_sign_up")
    async def sign_up(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        user = inter.user
        existing = characters_collection.find_one({"player_id": user.id, "session_id": self.session_id})
        if existing:
            await inter.response.send_message(
                f"You are already signed up as **{existing['name']}**. Use Sign Off to remove yourself.", ephemeral=True
            )
            return
        modal = CharacterCreationModal(self.bot, self.session_id, user)
        await inter.response.send_modal(modal)

    @disnake.ui.button(label="Sign Off", style=disnake.ButtonStyle.red, custom_id="session_join_sign_off")
    async def sign_off(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        user = inter.user
        sessions_collection.update_one({"session_id": self.session_id}, {"$pull": {"players": user.id}})
        await inter.response.send_message("You have been signed off from this session. Your character data remains saved.", ephemeral=True)

class SessionActionView(disnake.ui.View):
    def __init__(self, bot: commands.Bot, session_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id

    @disnake.ui.button(label="Take Action", style=disnake.ButtonStyle.primary, custom_id="session_action_take")
    async def take_action(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        user = inter.user
        modal = ActionModal(self.bot, self.session_id, user)
        await inter.response.send_modal(modal)

    @disnake.ui.button(label="Roll Dice", style=disnake.ButtonStyle.secondary, custom_id="session_action_roll")
    async def roll_dice(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        modal = DiceRollModal(self.bot)
        await inter.response.send_modal(modal)

class CombatView(disnake.ui.View):
    def __init__(self, bot: commands.Bot, session_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id

    @disnake.ui.button(label="Enter Initiative", style=disnake.ButtonStyle.primary, custom_id="combat_initiative")
    async def enter_initiative(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        user = inter.user
        modal = InitiativeModal(self.bot, self.session_id, user)
        await inter.response.send_modal(modal)

    @disnake.ui.button(label="Next Turn", style=disnake.ButtonStyle.secondary, custom_id="combat_next_turn")
    async def next_turn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        session = sessions_collection.find_one({"session_id": self.session_id})
        if not session or not session.get("combat"):
            await inter.response.send_message("No active combat in this session.", ephemeral=True)
            return
        combat = session["combat"]
        order = combat.get("initiative_order", [])
        if not order:
            await inter.response.send_message("No initiative order recorded.", ephemeral=True)
            return
        current_turn = combat.get("current_turn", 0)
        current_turn = (current_turn + 1) % len(order)
        combat["current_turn"] = current_turn
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": combat}})
        current_entry = order[current_turn]
        await inter.response.send_message(
            f"Next turn: **{current_entry['character_name']}** (Player ID: {current_entry['player_id']}) with initiative {current_entry['initiative']}.",
            ephemeral=True
        )

    @disnake.ui.button(label="End Combat", style=disnake.ButtonStyle.danger, custom_id="combat_end")
    async def end_combat(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": None}})
        await inter.response.send_message("Combat ended.", ephemeral=True)

# ---------------------------
# Main Cog
# ---------------------------
class DodoDnDCog(commands.Cog, name="DodoDnD"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="start_session", description="(GM Only) Start a new DnD session in DM.")
    async def start_session(self, inter: disnake.ApplicationCommandInteraction):
        if not isinstance(inter.channel, disnake.DMChannel):
            await inter.response.send_message("Please use this command in DMs with the bot.", ephemeral=True)
            return
        modal = SessionCreationModal(self.bot)
        await inter.response.send_modal(modal)

    @commands.slash_command(name="session_controls", description="Display controls for an active session.")
    async def session_controls(self, inter: disnake.ApplicationCommandInteraction, session_id: int):
        view = disnake.ui.View()
        # Combine action and combat controls
        view.add_item(SessionActionView(self.bot, session_id).children[0])  # Take Action
        view.add_item(SessionActionView(self.bot, session_id).children[1])  # Roll Dice
        view.add_item(CombatView(self.bot, session_id).children[0])         # Enter Initiative
        view.add_item(CombatView(self.bot, session_id).children[1])         # Next Turn
        view.add_item(CombatView(self.bot, session_id).children[2])         # End Combat
        await inter.response.send_message("Session Controls:", view=view, ephemeral=True)

    @commands.slash_command(name="end_session", description="End an active DnD session.")
    async def end_session(self, inter: disnake.ApplicationCommandInteraction, session_id: int):
        session = sessions_collection.find_one({"session_id": session_id})
        if not session:
            await inter.response.send_message("Session not found.", ephemeral=True)
            return
        sessions_collection.update_one({"session_id": session_id}, {"$set": {"status": "completed"}})
        await inter.response.send_message(f"Session {session_id} has ended.", ephemeral=True)

    @commands.slash_command(name="save_stats", description="Display final stats for a session.")
    async def save_stats(self, inter: disnake.ApplicationCommandInteraction, session_id: int):
        actions = list(actions_collection.find({"session_id": session_id}))
        if not actions:
            await inter.response.send_message("No actions recorded for this session.", ephemeral=True)
            return
        stats = {}
        for action in actions:
            pid = action["player_id"]
            stats[pid] = stats.get(pid, 0) + 1
        summary = "Session Stats:\n"
        for pid, count in stats.items():
            user = await self.bot.fetch_user(pid)
            summary += f"- {user.display_name}: {count} actions\n"
        await inter.response.send_message(summary, ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(DodoDnDCog(bot))
