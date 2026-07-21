"""
Dungeons & Dragons cog — a lightweight, LLM-driven DnD session manager. GMs
create sessions (posted as forum messages with join buttons); players make
characters and take actions that the LLM narrates, with per-session and
per-character history. Combat tracks initiative order.

All commands are slash-only because the flow is built on modals and buttons.
"""

import random
import re
from datetime import datetime

from openai import OpenAI

import discord
from discord import app_commands
from discord.ext import commands

import config_py
import lang

# Separate logical database for DnD data (re-uses the shared Mongo client).
_db = config_py.client["dodo_dnd"]
sessions_collection = _db["sessions"]
characters_collection = _db["characters"]
actions_collection = _db["actions"]

_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"
_MODEL = "gpt-4o"
_openai = (
    OpenAI(api_key=config_py.PROXY_API, base_url=_PROXY_BASE_URL) if getattr(config_py, "PROXY_API", None) else None
)


# --------------------------------------------------------------------------- #
#  Modals
# --------------------------------------------------------------------------- #
class SessionCreationModal(discord.ui.Modal, title="Create New Session"):
    session_title = discord.ui.TextInput(label="Session Title", placeholder="Enter the title of your session", max_length=100)
    scenario = discord.ui.TextInput(
        label="Scenario Description", style=discord.TextStyle.paragraph,
        placeholder="Describe the scenario for this session", max_length=1000,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        session_id = int(datetime.utcnow().timestamp())
        sessions_collection.insert_one(
            {
                "session_id": session_id,
                "title": str(self.session_title),
                "description": str(self.scenario),
                "players": [],
                "combat": None,
                "history": "",
                "created_at": datetime.utcnow(),
                "status": "active",
            }
        )
        channel = self.bot.get_channel(config_py.DND_FORUM_CHANNEL_ID)
        if channel is None:
            await interaction.response.send_message(lang.DND_NO_SESSION_CHANNEL, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Session: {self.session_title}", description=str(self.scenario),
            color=discord.Color.blurple(), timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"Session ID: {session_id}")
        message = await channel.send(embed=embed, view=SessionJoinView(self.bot, session_id))
        sessions_collection.update_one({"session_id": session_id}, {"$set": {"message_id": message.id}})
        await interaction.response.send_message(
            lang.DND_SESSION_CREATED.format(title=self.session_title, channel=channel.mention), ephemeral=True
        )


class CharacterCreationModal(discord.ui.Modal, title="Create Your Character"):
    char_name = discord.ui.TextInput(label="Character Name", placeholder="Enter your character's name", max_length=50)
    char_class = discord.ui.TextInput(label="Character Class", placeholder="e.g., Fighter, Wizard, Rogue", max_length=50)
    char_race = discord.ui.TextInput(label="Character Race", placeholder="e.g., Human, Elf, Dwarf", max_length=50)

    def __init__(self, bot, session_id, user):
        super().__init__()
        self.bot, self.session_id, self.user = bot, session_id, user

    async def on_submit(self, interaction: discord.Interaction) -> None:
        characters_collection.update_one(
            {"player_id": self.user.id, "session_id": self.session_id},
            {
                "$set": {
                    "player_id": self.user.id,
                    "session_id": self.session_id,
                    "name": str(self.char_name),
                    "class": str(self.char_class),
                    "race": str(self.char_race),
                    "stats": {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8},
                    "hp": 10,
                    "ac": 10,
                    "equipment": [],
                    "relationships": {},
                    "history": "",
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        sessions_collection.update_one({"session_id": self.session_id}, {"$addToSet": {"players": self.user.id}})
        await interaction.response.send_message(
            lang.DND_CHARACTER_CREATED.format(name=self.char_name, session_id=self.session_id), ephemeral=True
        )


class ActionModal(discord.ui.Modal, title="Take an Action"):
    action = discord.ui.TextInput(
        label="Describe your action", style=discord.TextStyle.paragraph,
        placeholder="Describe what your character does...", max_length=1000,
    )

    def __init__(self, bot, session_id, user):
        super().__init__()
        self.bot, self.session_id, self.user = bot, session_id, user

    def _complete(self, system: str, user: str, temperature: float) -> str | None:
        if _openai is None:
            return None
        try:
            completion = _openai.chat.completions.create(
                model=_MODEL, temperature=temperature,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return completion.choices[0].message.content
        except Exception as error:
            self.bot.logger.error(f"DnD LLM call failed: {error}")
            return None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        action_desc = str(self.action)
        character = characters_collection.find_one({"player_id": self.user.id, "session_id": self.session_id})
        if not character:
            await interaction.response.send_message(lang.DND_NO_CHARACTER, ephemeral=True)
            return

        session_doc = sessions_collection.find_one({"session_id": self.session_id})
        session_history = session_doc.get("history", "") if session_doc else ""
        character_history = character.get("history", "")
        context_block = (
            f"Session History:\n{session_history}\n\nCharacter History:\n{character_history}\n\nNew Action:\n{action_desc}\n"
        )

        gm_narrative = self._complete(
            "You are a genius Dungeon Master for a DnD 5e game. You keep a detailed but concise history of the session "
            "and each character. Provide an immersive and context-aware narrative resolution for the following action.",
            context_block, 1.0,
        ) or lang.DND_GM_ERROR

        summary = self._complete(
            "You produce concise bullet-point summaries for game events.",
            "Based on the following session history, character history, and new action, produce a concise bullet-point "
            "summary update (max 3 bullets) of key events, inventory changes, dialogue notes, and outcomes.\n\n"
            + context_block + "\nBullet Summary:", 0.7,
        )
        summary = (summary or "- No summary available.").strip()

        sessions_collection.update_one(
            {"session_id": self.session_id}, {"$set": {"history": (session_history + "\n" + summary).strip()}}
        )
        characters_collection.update_one(
            {"player_id": self.user.id, "session_id": self.session_id},
            {"$set": {"history": (character_history + "\n" + summary).strip()}},
        )
        actions_collection.insert_one(
            {
                "session_id": self.session_id,
                "player_id": self.user.id,
                "character_id": character.get("_id"),
                "action_description": action_desc,
                "gm_narrative": gm_narrative,
                "summary": summary,
                "timestamp": datetime.utcnow(),
            }
        )

        session_doc = sessions_collection.find_one({"session_id": self.session_id})
        if session_doc and "message_id" in session_doc:
            channel = self.bot.get_channel(config_py.DND_FORUM_CHANNEL_ID)
            if channel:
                try:
                    message = await channel.fetch_message(session_doc["message_id"])
                    await message.reply(
                        f"**{character['name']}**: {action_desc}\n**GM**: {gm_narrative}\n\n**Update:**\n{summary}"
                    )
                except discord.HTTPException as error:
                    self.bot.logger.error(f"Failed to send reply in session channel: {error}")

        await interaction.response.send_message(lang.DND_ACTION_SUBMITTED, ephemeral=True)


class InitiativeModal(discord.ui.Modal, title="Enter Initiative"):
    initiative = discord.ui.TextInput(label="Initiative roll (1d20 + modifier)", placeholder="e.g., 15", max_length=3)

    def __init__(self, bot, session_id, user):
        super().__init__()
        self.bot, self.session_id, self.user = bot, session_id, user

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(str(self.initiative))
        except ValueError:
            await interaction.response.send_message(lang.DND_INITIATIVE_INVALID, ephemeral=True)
            return

        session = sessions_collection.find_one({"session_id": self.session_id})
        if not session:
            await interaction.response.send_message(lang.DND_SESSION_NOT_FOUND, ephemeral=True)
            return

        combat = session.get("combat") or {"active": True, "initiative_order": [], "current_turn": 0}
        character = characters_collection.find_one({"player_id": self.user.id, "session_id": self.session_id})
        combat["initiative_order"] = [e for e in combat.get("initiative_order", []) if e["player_id"] != self.user.id]
        combat["initiative_order"].append(
            {"initiative": value, "player_id": self.user.id, "character_name": character["name"] if character else "Unknown"}
        )
        combat["initiative_order"].sort(key=lambda x: x["initiative"], reverse=True)
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": combat}})
        await interaction.response.send_message(lang.DND_INITIATIVE_RECORDED.format(value=value), ephemeral=True)


class DiceRollModal(discord.ui.Modal, title="Roll Dice"):
    dice = discord.ui.TextInput(label="Dice Roll (e.g., 1d20, 2d6)", placeholder="Enter dice roll in NdM format", max_length=10)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        match = re.match(r"(\d+)d(\d+)", str(self.dice).lower())
        if not match:
            await interaction.response.send_message(lang.DND_DICE_INVALID, ephemeral=True)
            return
        num_dice, dice_size = int(match.group(1)), int(match.group(2))
        results = [random.randint(1, dice_size) for _ in range(num_dice)]
        await interaction.response.send_message(
            lang.DND_DICE_RESULT.format(dice=self.dice, results=results, total=sum(results)), ephemeral=True
        )


# --------------------------------------------------------------------------- #
#  Views
# --------------------------------------------------------------------------- #
class SessionJoinView(discord.ui.View):
    """Sign-up / sign-off buttons attached to a posted session."""

    def __init__(self, bot, session_id):
        super().__init__(timeout=None)
        self.bot, self.session_id = bot, session_id

    @discord.ui.button(label="Sign Up", style=discord.ButtonStyle.green, custom_id="session_join_sign_up")
    async def sign_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = characters_collection.find_one({"player_id": interaction.user.id, "session_id": self.session_id})
        if existing:
            await interaction.response.send_message(lang.DND_ALREADY_SIGNED.format(name=existing["name"]), ephemeral=True)
            return
        await interaction.response.send_modal(CharacterCreationModal(self.bot, self.session_id, interaction.user))

    @discord.ui.button(label="Sign Off", style=discord.ButtonStyle.red, custom_id="session_join_sign_off")
    async def sign_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions_collection.update_one({"session_id": self.session_id}, {"$pull": {"players": interaction.user.id}})
        await interaction.response.send_message(lang.DND_SIGNED_OFF, ephemeral=True)


class SessionControlView(discord.ui.View):
    """Combined action + combat controls for an active session."""

    def __init__(self, bot, session_id):
        super().__init__(timeout=None)
        self.bot, self.session_id = bot, session_id

    @discord.ui.button(label="Take Action", style=discord.ButtonStyle.primary)
    async def take_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActionModal(self.bot, self.session_id, interaction.user))

    @discord.ui.button(label="Roll Dice", style=discord.ButtonStyle.secondary)
    async def roll_dice(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DiceRollModal())

    @discord.ui.button(label="Enter Initiative", style=discord.ButtonStyle.primary)
    async def enter_initiative(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InitiativeModal(self.bot, self.session_id, interaction.user))

    @discord.ui.button(label="Next Turn", style=discord.ButtonStyle.secondary)
    async def next_turn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = sessions_collection.find_one({"session_id": self.session_id})
        combat = session.get("combat") if session else None
        order = combat.get("initiative_order", []) if combat else []
        if not order:
            await interaction.response.send_message(lang.DND_NO_INITIATIVE, ephemeral=True)
            return
        combat["current_turn"] = (combat.get("current_turn", 0) + 1) % len(order)
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": combat}})
        entry = order[combat["current_turn"]]
        await interaction.response.send_message(
            lang.DND_NEXT_TURN.format(
                name=entry["character_name"], player_id=entry["player_id"], initiative=entry["initiative"]
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="End Combat", style=discord.ButtonStyle.danger)
    async def end_combat(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions_collection.update_one({"session_id": self.session_id}, {"$set": {"combat": None}})
        await interaction.response.send_message(lang.DND_COMBAT_ENDED, ephemeral=True)


# --------------------------------------------------------------------------- #
#  Cog
# --------------------------------------------------------------------------- #
class DodoDnD(commands.Cog, name="dnd"):
    """LLM-driven DnD session management."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start_session", description="(GM only) Start a new DnD session in DM.")
    async def start_session(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(lang.DND_DM_ONLY, ephemeral=True)
            return
        await interaction.response.send_modal(SessionCreationModal(self.bot))

    @app_commands.command(name="session_controls", description="Display controls for an active session.")
    async def session_controls(self, interaction: discord.Interaction, session_id: int) -> None:
        await interaction.response.send_message(
            "Session Controls:", view=SessionControlView(self.bot, session_id), ephemeral=True
        )

    @app_commands.command(name="end_session", description="End an active DnD session.")
    async def end_session(self, interaction: discord.Interaction, session_id: int) -> None:
        if not sessions_collection.find_one({"session_id": session_id}):
            await interaction.response.send_message(lang.DND_SESSION_NOT_FOUND, ephemeral=True)
            return
        sessions_collection.update_one({"session_id": session_id}, {"$set": {"status": "completed"}})
        await interaction.response.send_message(lang.DND_SESSION_ENDED.format(session_id=session_id), ephemeral=True)

    @app_commands.command(name="save_stats", description="Display final stats for a session.")
    async def save_stats(self, interaction: discord.Interaction, session_id: int) -> None:
        actions = list(actions_collection.find({"session_id": session_id}))
        if not actions:
            await interaction.response.send_message(lang.DND_NO_ACTIONS, ephemeral=True)
            return
        counts: dict[int, int] = {}
        for action in actions:
            counts[action["player_id"]] = counts.get(action["player_id"], 0) + 1
        summary = lang.DND_STATS_HEADER
        for player_id, count in counts.items():
            user = await self.bot.fetch_user(player_id)
            summary += lang.DND_STATS_LINE.format(name=user.display_name, count=count)
        await interaction.response.send_message(summary, ephemeral=True)


async def setup(bot):
    await bot.add_cog(DodoDnD(bot))
