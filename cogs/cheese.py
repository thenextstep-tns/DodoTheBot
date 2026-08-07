"""
Cheese cog — a co-op push-your-luck cheese-stretching minigame.

A 🧀 rarely drops on a message. The first grab launches a stretch: players
👌-pull to stretch the cheese (each pull adds a random amount of stretch),
growing a shared pot but risking a HIDDEN snap limit. Cut (✂️) in time to split
the pot — every puller bonds with a random mouse — or Steal (💰) a fraction for
yourself and leave the rest with nothing. Pull too far and the cheese snaps and
flies away. If a participant owns an adopted mouse, it may peek out (🐭); its
owner can let it gobble the cheese, ending the stretch but showering every
puller in sweetrolls.
"""

import asyncio
import json
import math
import random
from collections import defaultdict
from datetime import datetime

import discord
from discord.ext import commands

import config_py
import lang
from helpers import messages

CHEESE = "\U0001F9C0"        # 🧀 — the dropped cheese / stretch anchor
CHEESE_PULL = "\U0001F44C"   # 👌 ok_hand — the pulling hand
CHEESE_CUT = "✂️"           # ✂️ — cut and split the pot
CHEESE_STEAL = "\U0001F4B0"  # 💰 — steal a fraction for yourself
CHEESE_MOUSE = "\U0001F42D"  # 🐭 — an adopted mouse peeking out to gobble the cheese
CHEESE_STRETCH = "🟨"    # 🟨 — one segment of stretched cheese (a plain ~ renders as strikethrough)
CHEESE_BOOM = "💥"       # 💥 — the stretch segments become explosions when it snaps
CHEESE_SHOCK = "<:spooky_shock:1482068392696611069>"  # replaces the 👌 hand on a snap


class Cheese(commands.Cog, name="cheese"):
    """The co-op cheese-stretching minigame."""

    def __init__(self, bot):
        self.bot = bot
        # Owner IDs for the hidden force-drop trigger; loaded once at startup.
        try:
            with open("config.json", encoding="utf-8") as file:
                self.owner_ids = set(json.load(file).get("owners", []))
        except (OSError, json.JSONDecodeError):
            self.owner_ids = set()

    # --------------------------------------------------------------------- #
    #  Drop listener
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Rarely drop a 🧀 on a message; the first grab starts the stretch game."""
        if message.author.bot:
            return
        if message.guild and not self.bot.visibility.feature_active(message.guild.id, "cheese_drop", "cheese"):
            return
        # Hidden owner-only trigger guarantees a drop; otherwise roll the odds.
        forced = (
            message.author.id in self.owner_ids
            and config_py.CHEESE_SECRET_TRIGGER in message.content.lower()
        )
        if forced or random.randint(0, 1000) > config_py.CHEESE_DROP_THRESHOLD:
            try:
                await message.add_reaction(CHEESE)
                self.bot.loop.create_task(self.handle_cheese_drop(message))
            except discord.HTTPException:
                pass

    async def handle_cheese_drop(self, message: discord.Message) -> None:
        """First grab on a dropped 🧀 kicks off the co-op stretch, in that channel."""
        emoji, initiator = await messages.wait_for_reaction(self.bot, message, [CHEESE], timeout=3.0, add=False)
        try:
            await message.clear_reaction(CHEESE)
        except discord.HTTPException:
            pass
        if emoji is None:
            return
        # No registered mice means there's nothing to bond with — skip silently.
        if not config_py.user_mice.find_one({}):
            return
        await self.run_cheese_game(message.channel, initiator)

    # --------------------------------------------------------------------- #
    #  Game helpers
    # --------------------------------------------------------------------- #
    def _roll_cheese_type(self) -> dict:
        """Pick a cheese type, weighted by its drop rate."""
        types = config_py.CHEESE_TYPES
        return random.choices(types, weights=[t["weight"] for t in types], k=1)[0]

    def _roll_pull_strength(self) -> int:
        """A single 👌-pull adds a random amount of stretch — sometimes even 0 (it slips)."""
        return random.choice(config_py.CHEESE_PULL_STRENGTHS)

    def _cheese_bar(self, stretch: int, snap_limit: int, *, snapped: bool = False) -> str:
        """The stretch visual: one 🟨 per unit pulled, never drawn past this drop's snap limit.

        On a snap the 🟨 segments become 💥 explosions and the 👌 hand becomes the spooky-shock emoji.
        """
        segments = min(stretch, snap_limit)
        segment_emoji = CHEESE_BOOM if snapped else CHEESE_STRETCH
        hand = CHEESE_SHOCK if snapped else CHEESE_PULL
        return f"{CHEESE}{segment_emoji * segments}{hand}"

    def _cheese_embed(self, cheese: dict, stretch: int, snap_limit: int, mouse: dict | None = None) -> discord.Embed:
        """Build the live status embed for an in-progress cheese stretch."""
        description = lang.CHEESE_GAME_DESC.format(
            bar=self._cheese_bar(stretch, snap_limit), cheese=cheese["name"], pulls=stretch,
        )
        if mouse is not None:
            description += lang.CHEESE_MOUSE_NOTE.format(mouse=mouse["name"], owner=mouse["owner_name"])
        embed = messages.embed(
            description,
            title=lang.CHEESE_GAME_TITLE.format(cheese=cheese["name"]),
            color=config_py.warning,
        )
        if cheese.get("image"):
            embed.set_thumbnail(url=cheese["image"])
        return embed

    def _award_to_random_mouse(self, user_id: int, points: int) -> dict | None:
        """Add ``points`` to ``user_id``'s bond with a random mouse. Returns bond info."""
        mice = list(config_py.user_mice.find())
        if not mice:
            return None
        chosen = random.choice(mice)
        rel_list = chosen.get("Relationship", [])
        for entry in rel_list:
            if entry["user_id"] == user_id:
                entry["relationship_points"] += points
                new_points = entry["relationship_points"]
                break
        else:
            new_points = points
            rel_list.append({"user_id": user_id, "relationship_points": points})
        config_py.user_mice.update_one({"_id": chosen["_id"]}, {"$set": {"Relationship": rel_list}})
        return {"name": chosen["name"], "points": new_points, "adopted_by": chosen.get("adopted_by")}

    def _maybe_spawn_mouse(self, participant_ids) -> dict | None:
        """Roll for an adopted mouse (owned by a participant) to peek out for the cheese."""
        if random.random() >= config_py.CHEESE_MOUSE_CHANCE:
            return None
        # Only mice that a participant has actually adopted (adopted_by set to their id).
        owner_ids = [uid for uid in participant_ids if uid]
        candidates = [
            m for m in config_py.user_mice.find({"adopted_by": {"$in": owner_ids}})
            if m.get("adopted_by") in owner_ids
        ]
        if not candidates:
            return None
        chosen = random.choice(candidates)
        owner = self.bot.get_user(chosen["adopted_by"])
        owner_name = owner.display_name if owner else "its owner"
        return {"name": chosen["name"], "owner_id": chosen["adopted_by"], "owner_name": owner_name}

    # --------------------------------------------------------------------- #
    #  Main game loop
    # --------------------------------------------------------------------- #
    async def run_cheese_game(self, channel: discord.TextChannel, initiator: discord.abc.User) -> None:
        """Run the whole co-op stretch: pull / cut / steal / snap / mouse, all in one embed."""
        cheese = self._roll_cheese_type()
        snap_limit = random.randint(cheese["snap_min"], cheese["snap_max"])  # hidden, never shown
        stretch_by_user: dict[int, int] = defaultdict(int)
        users_by_id: dict[int, discord.abc.User] = {}
        mouse: dict | None = None  # {"name", "owner_id"} while a 🐭 is peeking

        # Grabbing the cheese counts as the initiator's first tug.
        stretch_by_user[initiator.id] = 1
        users_by_id[initiator.id] = initiator
        total_stretch = 1

        game_msg = await channel.send(embed=self._cheese_embed(cheese, total_stretch, snap_limit))
        for control in (CHEESE_PULL, CHEESE_CUT, CHEESE_STEAL):
            await game_msg.add_reaction(control)

        def check(reaction: discord.Reaction, user: discord.abc.User) -> bool:
            return (
                not user.bot
                and reaction.message.id == game_msg.id
                and str(reaction.emoji) in (CHEESE_PULL, CHEESE_CUT, CHEESE_STEAL, CHEESE_MOUSE)
            )

        while True:
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=config_py.CHEESE_EVENT_TIMEOUT, check=check
                )
            except asyncio.TimeoutError:
                await self._end_cheese_fizzle(game_msg, cheese)
                return

            emoji = str(reaction.emoji)
            try:
                await game_msg.remove_reaction(emoji, user)  # let players press again
            except discord.HTTPException:
                pass

            if emoji == CHEESE_MOUSE:
                # Only the peeking mouse's owner can let it pounce.
                if mouse is not None and user.id == mouse["owner_id"]:
                    await self._end_cheese_mouse(game_msg, cheese, mouse, stretch_by_user, users_by_id)
                    return
                continue

            if emoji == CHEESE_CUT:
                await self._end_cheese_cut(game_msg, channel, cheese, stretch_by_user, users_by_id)
                return
            if emoji == CHEESE_STEAL:
                await self._end_cheese_steal(game_msg, channel, cheese, user, total_stretch)
                return

            # --- A 👌 pull: add a random amount of stretch ---
            users_by_id[user.id] = user
            pull = self._roll_pull_strength()
            total_stretch += pull
            stretch_by_user[user.id] += pull
            if total_stretch > snap_limit:
                await self._end_cheese_snap(game_msg, cheese, total_stretch, snap_limit)
                return

            # Every pull is a chance for an adopted mouse to peek out for the cheese.
            if mouse is None:
                mouse = self._maybe_spawn_mouse(stretch_by_user.keys())
                if mouse is not None:
                    try:
                        await game_msg.add_reaction(CHEESE_MOUSE)
                    except discord.HTTPException:
                        mouse = None

            try:
                await game_msg.edit(embed=self._cheese_embed(cheese, total_stretch, snap_limit, mouse))
            except discord.HTTPException:
                pass

    # --------------------------------------------------------------------- #
    #  Endings
    # --------------------------------------------------------------------- #
    async def _end_cheese_cut(self, game_msg, channel, cheese, stretch_by_user, users_by_id) -> None:
        """Split the stretch evenly among everyone who pulled; each bonds with a random mouse."""
        total = sum(stretch_by_user.values())
        num_participants = len(stretch_by_user)
        reward_each = math.ceil((total / num_participants) * cheese["like_mult"]) if num_participants else 0
        lines = []
        adoption_targets = []
        for user_id in stretch_by_user:
            bond = self._award_to_random_mouse(user_id, reward_each)
            if bond is None:
                continue
            lines.append(lang.CHEESE_CUT_LINE.format(
                mention=messages.mention(users_by_id.get(user_id, user_id)),
                mouse=bond["name"], points=reward_each,
            ))
            if bond["points"] >= config_py.MOUSE_ADOPTION_RANK and not bond["adopted_by"]:
                adoption_targets.append((users_by_id.get(user_id), bond["name"]))

        await self._finish_cheese(game_msg, "\n".join(lines) or lang.CHEESE_FIZZLE.format(cheese=cheese["name"]),
                                  lang.CHEESE_CUT_TITLE.format(cheese=cheese["name"]), messages.SUCCESS)
        for user, mouse_name in adoption_targets:
            if user is not None:
                await self._adoption_prompt_channel(channel, user, mouse_name)

    async def _end_cheese_steal(self, game_msg, channel, cheese, thief, total_stretch) -> None:
        """The thief grabs a fraction of the whole pot; everyone else gets nothing."""
        stolen = math.ceil((total_stretch / config_py.CHEESE_STEAL_DIVISOR) * cheese["like_mult"])
        bond = self._award_to_random_mouse(thief.id, stolen)
        if bond is None:
            await self._end_cheese_fizzle(game_msg, cheese)
            return
        await self._finish_cheese(
            game_msg,
            lang.CHEESE_STEAL.format(mention=thief.mention, points=stolen, cheese=cheese["name"], mouse=bond["name"]),
            lang.CHEESE_STEAL_TITLE, messages.WARNING,
        )
        if bond["points"] >= config_py.MOUSE_ADOPTION_RANK and not bond["adopted_by"]:
            await self._adoption_prompt_channel(channel, thief, bond["name"])

    async def _end_cheese_mouse(self, game_msg, cheese, mouse, stretch_by_user, users_by_id) -> None:
        """An adopted mouse gobbles the cheese: no stretch reward, but sweetrolls for every puller."""
        each = config_py.CHEESE_MOUSE_SWEETROLLS
        now = datetime.now()
        recipient_lines = []
        for user_id in stretch_by_user:
            config_py.sweetrolls.insert_many([
                {"gifted_to": user_id, "gifter": mouse["owner_id"], "date": now, "source": "cheese_mouse"}
                for _ in range(each)
            ])
            recipient_lines.append(lang.CHEESE_MOUSE_RECIPIENT.format(
                mention=messages.mention(users_by_id.get(user_id, user_id)), sweetrolls=each,
            ))

        await self._finish_cheese(
            game_msg,
            lang.CHEESE_MOUSE_EATEN.format(
                mouse=mouse["name"], cheese=cheese["name"], sweetrolls=each,
                recipients="\n".join(recipient_lines),
            ),
            lang.CHEESE_MOUSE_EATEN_TITLE.format(mouse=mouse["name"]), messages.SUCCESS,
        )

    async def _end_cheese_snap(self, game_msg, cheese, total_stretch, snap_limit) -> None:
        """Stretched past the hidden limit — the cheese snaps and nobody scores."""
        await self._finish_cheese(
            game_msg,
            lang.CHEESE_SNAP.format(bar=self._cheese_bar(total_stretch, snap_limit, snapped=True), cheese=cheese["name"]),
            lang.CHEESE_SNAP_TITLE, messages.ERROR,
        )

    async def _end_cheese_fizzle(self, game_msg, cheese) -> None:
        """Nobody acted before the timeout — the cheese goes stale."""
        await self._finish_cheese(
            game_msg, lang.CHEESE_FIZZLE.format(cheese=cheese["name"]),
            lang.CHEESE_FIZZLE_TITLE, messages.INFO,
        )

    async def _finish_cheese(self, game_msg, description, title, color) -> None:
        """Edit the game embed into its final result and drop the controls."""
        try:
            await game_msg.edit(embed=messages.embed(description, title=title, color=color))
            await game_msg.clear_reactions()
        except discord.HTTPException:
            pass

    # --------------------------------------------------------------------- #
    #  Adoption prompt (channel context)
    # --------------------------------------------------------------------- #
    async def _adoption_prompt_channel(self, channel, target_user, mouse_name) -> None:
        """Ask ``target_user`` to adopt ``mouse_name`` via 👍/👎 in the game channel."""
        msg = await channel.send(
            embed=messages.embed(
                lang.CHEESE_ADOPT_DESCRIPTION.format(mention=target_user.mention, mouse=mouse_name),
                title=lang.CHEESE_ADOPT_TITLE.format(mouse=mouse_name),
                color=config_py.main_color,
            )
        )
        emoji, _ = await messages.wait_for_reaction(self.bot, msg, ["👍", "👎"], member=target_user, timeout=60.0)
        if emoji is None:
            await msg.clear_reactions()
            return
        if emoji == "👍":
            config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"adopted_by": target_user.id}})
            await channel.send(lang.CHEESE_ADOPT_SUCCESS.format(mouse=mouse_name))
        else:
            config_py.user_mice.update_one(
                {"name": mouse_name, "Relationship.user_id": target_user.id},
                {"$inc": {"Relationship.$.relationship_points": -100}},
            )
            await channel.send(lang.RACING_ADOPT_DECLINE.format(mouse=mouse_name))
        await msg.clear_reactions()


async def setup(bot):
    await bot.add_cog(Cheese(bot))
