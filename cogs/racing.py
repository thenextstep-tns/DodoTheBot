"""
Racing cog — the skeevaton (mouse) racing game: register mice with classes,
run races with reaction-driven cheese/wine/bomb/treasure events, track
relationships, handle mouse adoption, and browse relationships.
"""

import asyncio
import math
import random
import time
from collections import defaultdict

from openai import OpenAI

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"

MOUSE = "\U0001F401"
CHEESE = "\U0001F9C0"
WINE = "\U0001F377"
BOMB = "\U0001F4A3"
STAR = "✨"
MAP = "🗺️"


class Racing(commands.Cog, name="racing"):
    """The skeevaton racing minigame."""

    def __init__(self, bot):
        self.bot = bot
        proxy_key = getattr(config_py, "PROXY_API", None)
        self.client = OpenAI(api_key=proxy_key, base_url=_PROXY_BASE_URL) if proxy_key else None

    # --------------------------------------------------------------------- #
    #  Commands
    # --------------------------------------------------------------------- #
    @commands.hybrid_command(name="newmouse", description="Register a new mouse and choose its class.")
    async def newmouse(self, context: Context, *, mouse_name: str) -> None:
        """Add a new mouse and let the caller pick its class by reaction."""
        if config_py.user_mice.find_one({"name": mouse_name}):
            await context.send(lang.RACING_MOUSE_EXISTS.format(name=mouse_name))
            return

        classes = list(config_py.mouse_classes.find())
        class_emojis = {c["emoji"]: c["name"] for c in classes}
        class_message = await context.send(
            lang.RACING_CHOOSE_CLASS.format(
                classes="\n".join(f"{c['emoji']} {c['name']}: {c['description']}" for c in classes)
            )
        )

        emoji, _ = await messages.wait_for_reaction(
            self.bot, class_message, class_emojis, member=context.author, timeout=60.0
        )
        if emoji is None:
            await context.send(lang.RACING_CLASS_TIMEOUT)
            return

        mouse_class = class_emojis[emoji]
        config_py.user_mice.insert_one({"user_id": context.author.id, "name": mouse_name, "class": mouse_class})
        await context.send(lang.RACING_MOUSE_ADDED.format(name=mouse_name, mouse_class=mouse_class))

    @commands.hybrid_command(name="race", description="Challenge your guildies to a skeevaton race!")
    @checks.not_blacklisted()
    async def race(self, context: Context, countdown: int = 20) -> None:
        """Start a race in this channel with a short sign-up countdown."""
        race_message = await context.send(
            lang.RACING_START.format(mention=context.author.mention, countdown=countdown)
        )
        track_length = random.randint(15, 45)
        await race_message.add_reaction(MOUSE)
        await self._countdown_message(race_message, context.author, track_length, countdown, giga=False)
        await self._run_full_race(context, race_message, context.author, track_length, f"{context.author}'s race")

    @commands.hybrid_command(name="gigarace", description="Challenge your guildies to a gigarace!")
    @checks.not_blacklisted()
    @checks.is_owner()
    async def gigarace(self, context: Context) -> None:
        """Start a gigarace announced in the announcement channel with a 9h countdown."""
        announcement_channel = self.bot.get_channel(self.bot.guild_setting(context.guild, "ANNOUNCEMENT_CHANNEL"))
        race_message = await announcement_channel.send(lang.RACING_GIGA_START)
        await race_message.add_reaction(MOUSE)
        await self._countdown_message(race_message, context.author, 45, 32400, giga=True)
        await self._run_full_race(context, race_message, context.author, 45, f"{context.author}'s gigarace")

    async def _run_full_race(self, context, race_message, race_starter, track_length, race_name) -> None:
        """Shared race pipeline used by both ``race`` and ``gigarace``."""
        await asyncio.sleep(1)
        race_message = await race_message.channel.fetch_message(race_message.id)
        mouse_users = await self.get_reaction_users(race_message, MOUSE)
        if not mouse_users:
            await context.send(lang.RACING_NO_JOIN)
            return
        # A lone sign-up has nobody to race and would be waved home on move one, so
        # Dodo takes a mouse itself to make a race of it. It drives, but it doesn't
        # play the reaction games — see ``grabbers`` in run_race.
        if len(mouse_users) == 1:
            mouse_users.append(self.bot.user)

        mice = self.assign_mice_classes(mouse_users)
        left_out = [user for user in mouse_users if user.id not in mice]
        mouse_users = [user for user in mouse_users if user.id in mice]
        if not mouse_users:
            await context.send(lang.RACING_NO_MICE)
            return
        if left_out:
            await context.send(lang.RACING_SHORT_ON_MICE.format(count=len(left_out)))

        await self.send_lineup_embed(race_message, context, mice)
        await self.run_race_lights(race_message, race_starter, track_length, mice)

        positions, completed_mice, finished_order = self.initialize_race(mouse_users)
        await self.run_race(
            context, race_message, race_starter, mouse_users, mice, positions, completed_mice,
            track_length, finished_order, [],
        )
        race_results = self.calculate_race_results(finished_order)
        await self.send_race_summary(context, race_starter, mice, race_results)
        self.save_race_results(race_name, race_starter, mice, race_results)
        await self.update_relationships(context, race_results, mice)
        await self.adoption_check(context, mice)

    # --------------------------------------------------------------------- #
    #  Sign-up message handling
    # --------------------------------------------------------------------- #
    async def _countdown_message(self, race_message, race_starter, track_length, time_left, *, giga: bool) -> None:
        """Tick the sign-up message's countdown until it runs out."""
        end_time = time.time() + time_left
        interval = 100 if giga else 1
        while time.time() < end_time:
            remaining = int(end_time - time.time())
            if giga:
                content = lang.RACING_GIGA_COUNTDOWN.format(remaining=remaining)
            else:
                content = lang.RACING_COUNTDOWN.format(
                    mention=race_starter.mention, track_length=track_length, remaining=remaining
                )
            await race_message.edit(content=content)
            await asyncio.sleep(interval)

    async def get_reaction_users(self, race_message, emoji) -> list:
        """Return every non-bot user who reacted to ``race_message`` with ``emoji``.

        The bot seeds the sign-up reaction itself, so without the filter it joins
        its own races as an extra mouse.
        """
        for reaction in race_message.reactions:
            if str(reaction.emoji) == emoji:
                return [user async for user in reaction.users() if not user.bot]
        return []

    def assign_mice_classes(self, mouse_users) -> dict:
        """Assign a random registered mouse (with its class) to each racer.

        A mouse whose class no longer exists in ``MouseClasses`` is passed over
        rather than handed out, and racers are only left out once the pen runs
        dry — so the returned mapping always covers exactly the racers the caller
        should race, and the two can't drift apart.
        """
        available_mice = list(config_py.user_mice.find())
        random.shuffle(available_mice)
        classes = {doc["name"]: doc for doc in config_py.mouse_classes.find()}
        assigned = {}
        for user in mouse_users:
            while available_mice:
                mouse = available_mice.pop()
                mouse_class = classes.get(mouse.get("class"))
                if mouse_class:
                    assigned[user.id] = {
                        "name": mouse["name"],
                        "class": mouse_class["name"],
                        "class_description": mouse_class["description"],
                    }
                    break
        return assigned

    async def send_lineup_embed(self, race_message, context, mice) -> None:
        """Show the starting line-up embed."""
        embed = discord.Embed(title=lang.RACING_LINEUP_TITLE, description=lang.RACING_LINEUP_DESCRIPTION, color=0xFF0000)
        for user_id, mouse_info in mice.items():
            user = context.guild.get_member(user_id)
            embed.add_field(name=f"{user.display_name}'s {mouse_info['name']} ({mouse_info['class']})", value="")
        await race_message.edit(embed=embed, content="")

    async def run_race_lights(self, race_message, race_starter, track_length, mice) -> None:
        """Play the red→green starting-lights animation."""
        black, red, green = "\U000026AB", "\U0001F534", "\U0001F7E2"
        roster = "\n".join(f"{info['name']} ({info['class']})" for info in mice.values())
        embed = discord.Embed(
            title=lang.RACING_LIGHTS_TITLE,
            description=lang.RACING_LIGHTS_DESCRIPTION.format(roster=roster),
            color=0xFFFF00,
        )
        for i in range(5):
            embed.set_footer(text="".join(red if j <= i else black for j in range(5)))
            await race_message.edit(embed=embed)
            await asyncio.sleep(1)
        await asyncio.sleep(1)
        embed.set_footer(text=green * 5)
        embed.description = lang.RACING_LIGHTS_GO.format(roster=roster)
        await race_message.edit(embed=embed)

    def initialize_race(self, mouse_users):
        """Return fresh (positions, completed set, finish order) trackers."""
        return {user.id: 0 for user in mouse_users}, set(), []

    # --------------------------------------------------------------------- #
    #  Core race loop
    # --------------------------------------------------------------------- #
    def _roll_move_plan(self, moves: int, lucky_ids, non_lucky_classes) -> list:
        """Roll ``moves`` worth of per-move randomness in one go.

        Everything that used to be decided (and re-queried) in the middle of a move
        lives here: the event roll, and which class each Lucky Mouse is wearing.
        Deciding it up front keeps the move loop off the database entirely, and
        means a Lucky Mouse's class for a move is known *before* the event phase —
        which is what lets one summon and read a treasure map.
        """
        return [
            {
                "event_roll": random.randint(1, 100),
                "lucky_classes": {uid: random.choice(non_lucky_classes) for uid in lucky_ids},
            }
            for _ in range(moves)
        ]

    async def run_race(self, context, race_message, race_starter, mouse_users, user_mouse_names_classes,
                       positions, completed_mice, track_length, finished_order, debug_log):
        """Main race loop: random events, per-mouse dice rolls, and finishing logic."""
        initial_players = len(mouse_users)
        move_counter = 0
        green_flag = lang.RACING_EVENT_RACING
        grab_window = self.bot.params.get(
            context.guild.id if context.guild else None, "race_reaction_window"
        )

        adopted_owners = {}
        for user in mouse_users:
            mouse_name = user_mouse_names_classes[user.id]["name"]
            doc = config_py.user_mice.find_one({"name": mouse_name})
            if doc and doc.get("adopted_by") == user.id:
                adopted_owners[user.id] = True

        # The class table is a handful of documents that can't change mid-race, so
        # read it once here instead of once per mouse per move.
        classes_by_name = {doc["name"]: doc for doc in config_py.mouse_classes.find()}
        non_lucky_classes = [doc for name, doc in classes_by_name.items() if name != "Lucky Mouse"]
        lucky_ids = (
            [u.id for u in mouse_users if user_mouse_names_classes[u.id]["class"] == "Lucky Mouse"]
            if non_lucky_classes
            else []
        )
        move_plan = self._roll_move_plan(track_length * 2, lucky_ids, non_lucky_classes)

        def effective_class(user_id, plan):
            """The class a mouse is wearing this move — a Lucky Mouse rerolls each move."""
            name = user_mouse_names_classes[user_id]["class"]
            if name == "Lucky Mouse" and user_id in plan["lucky_classes"]:
                return plan["lucky_classes"][user_id]
            return classes_by_name.get(name)

        starry_boost = {}
        bomb_dodges_used = defaultdict(int)

        while len(finished_order) < initial_players:
            await race_message.clear_reactions()
            if move_counter >= len(move_plan):
                move_plan.extend(self._roll_move_plan(track_length, lucky_ids, non_lucky_classes))
            plan = move_plan[move_counter]
            event_roll = plan["event_roll"]
            event_text = green_flag

            # Events only concern mice still on the track, and a grab lasts exactly
            # one move — nobody carries a bonus into a later event.
            racing_users = [u for u in mouse_users if u.id not in completed_mice]
            # Dodo drives a mouse when a race would otherwise be a solo lap, but it
            # can't click anything — so it moves and takes blasts like any racer
            # while the events belong to the humans.
            grabbers = [u for u in racing_users if not u.bot]
            cheese_user = wine_user = bomb_user = None
            # Resolved before the event phase, so a Lucky Mouse wearing Navigator
            # this move can both summon a map and read it.
            move_classes = {u.id: effective_class(u.id, plan) for u in racing_users}
            navigator_racing = any(
                move_classes[u.id] and move_classes[u.id]["name"] == "Navigator" for u in grabbers
            )

            # --- POSSIBLE EVENTS ---
            if navigator_racing and event_roll == 95:
                event_text = lang.RACING_EVENT_MAP
                await race_message.edit(content=event_text)
                map_reader = await self._grab_event(race_message, grabbers, MAP, grab_window)
                if map_reader is not None:
                    reader_class = move_classes[map_reader.id]
                    if reader_class and reader_class["name"] == "Navigator":
                        positions[map_reader.id] += 20
                        debug_log.append(
                            f"Move {move_counter + 1}: {user_mouse_names_classes[map_reader.id]['name']} used the Treasure Map! +20 move."
                        )
                    else:
                        debug_log.append(
                            f"Move {move_counter + 1}: Mouse picked up a map but doesn't know how to read, so it just looks at it in confusion and nothing happens."
                        )

            elif 81 <= event_roll <= 82 and (
                star_eligible := [u for u in grabbers if u.id in adopted_owners]
            ):
                event_text = lang.RACING_EVENT_STARRY
                await race_message.edit(content=event_text)
                star_owner = await self._grab_event(race_message, star_eligible, STAR, grab_window)
                if star_owner:
                    starry_boost[star_owner.id] = config_py.STAR_INSPIRATION_DURATION

            elif 86 <= event_roll <= 88:
                event_text = lang.RACING_EVENT_CHEESE
                await race_message.edit(content=event_text)
                cheese_user = await self._grab_event(race_message, grabbers, CHEESE, grab_window)

            elif 89 <= event_roll <= 92:
                event_text = lang.RACING_EVENT_WINE
                await race_message.edit(content=event_text)
                wine_user = await self._grab_event(race_message, grabbers, WINE, grab_window)

            elif 93 <= event_roll <= 94:
                event_text = lang.RACING_EVENT_BOMB
                await race_message.edit(content=event_text)
                bomb_user = await self._grab_event(race_message, grabbers, BOMB, grab_window)
            else:
                await asyncio.sleep(1)

            # --- PER-USER MOVE LOGIC ---
            bomb_hits, bomb_dodgers = [], []
            for user in mouse_users:
                if user.id in completed_mice:
                    continue
                roll = self.roll_dice()
                mouse_info = user_mouse_names_classes[user.id]
                class_data = move_classes[user.id]
                debug_message = f"Move {move_counter + 1}: {mouse_info['name']}: {roll} "

                if mouse_info["class"] == "Lucky Mouse" and class_data:
                    debug_message += f"[Lucky Mouse: randomly got {class_data['name']}!] "

                if user.id in starry_boost and starry_boost[user.id] > 0:
                    roll += config_py.STAR_INSPIRATION_BOOST
                    debug_message += f"({mouse_info['name']} got a +{config_py.STAR_INSPIRATION_BOOST} starry boost!) "
                    starry_boost[user.id] -= 1
                    if starry_boost[user.id] == 0:
                        del starry_boost[user.id]

                if user == cheese_user:
                    roll += 1
                    debug_message += f"({mouse_info['name']} munched on cheese! +1) "
                    if "cheese_bonus" in class_data.get("bonus", {}):
                        cheese_bonus = class_data["bonus"]["cheese_bonus"]
                        roll += cheese_bonus
                        debug_message += f"(Cheese Seeker bonus +{cheese_bonus}!) "

                if user == wine_user:
                    # Read the *effective* class so a Lucky Mouse that rolled Wine
                    # Connoisseur this move gets its perk, like every other class.
                    if class_data and class_data["name"] == "Wine Connoisseur":
                        if roll < 0:
                            roll = 0
                            debug_message += "(Wine Connoisseur negated negative roll to 0!) "
                        else:
                            roll = roll * 2
                            debug_message += f"(Wine Connoisseur doubled the roll to {roll}!) "
                    else:
                        roll = roll * 2
                        debug_message += f"(Wine event doubled the roll to {roll}!) "

                bomb_damage_taken = False
                guardian_absorbed_bomb = False
                if bomb_user and user != bomb_user:
                    if class_data and class_data["name"] == "Bomb Dodger":
                        if bomb_dodges_used[user.id] < 3:
                            bomb_dodges_used[user.id] += 1
                            bomb_dodgers.append(mouse_info["name"])
                            debug_message += f"({mouse_info['name']} dodged the bomb! {bomb_dodges_used[user.id]}/3) "
                        else:
                            roll -= 5
                            bomb_damage_taken = True
                            bomb_hits.append(mouse_info["name"])
                            debug_message += f"({mouse_info['name']} couldn't dodge any more bombs and got hit by one, -5 => {roll}) "
                    elif class_data and "reduce_negative" in class_data.get("bonus", {}) and class_data["name"] == "Guardian":
                        half_damage = int(5 * class_data["bonus"]["reduce_negative"])
                        roll -= half_damage
                        bomb_damage_taken = True
                        # This *is* the Guardian perk applied to the blast — flag it so
                        # the generic negative-roll halving below can't apply it twice.
                        guardian_absorbed_bomb = True
                        bomb_hits.append(mouse_info["name"])
                        debug_message += f"(Guardian halved bomb effect to -{half_damage} => {roll}) "
                    else:
                        roll -= 5
                        bomb_damage_taken = True
                        bomb_hits.append(mouse_info["name"])
                        debug_message += f"({mouse_info['name']} got hit by a bomb => {roll}) "

                if "speed_bonus" in class_data.get("bonus", {}):
                    if random.randint(1, 100) <= 15:
                        bonus_amount = class_data["bonus"]["speed_bonus"]
                        roll += bonus_amount
                        debug_message += f"(Speedster triggered +{bonus_amount}!) "

                if (
                    class_data
                    and not guardian_absorbed_bomb
                    and "reduce_negative" in class_data.get("bonus", {})
                    and roll < 0
                ):
                    original_roll = roll
                    roll = math.ceil(roll * class_data["bonus"]["reduce_negative"])
                    debug_message += f"(Guardian halved negative roll from {original_roll} to {roll}) "

                # A mouse never backs off the start line under its own steam, but a
                # bomb can throw it clean off the back of the track — and it has to
                # crawl all the way back from there.
                target = min(positions[user.id] + roll, track_length)
                if bomb_damage_taken:
                    positions[user.id] = target
                else:
                    positions[user.id] = max(min(0, positions[user.id]), target)

                if positions[user.id] >= track_length and user.id not in completed_mice:
                    positions[user.id] = track_length
                    completed_mice.add(user.id)
                    finished_order.append(user)
                    debug_message += f"({mouse_info['name']} finished!) "

                debug_log.append(debug_message)
                if positions[user.id] < 0:
                    debug_log.append(
                        lang.RACING_LOG_YEETED.format(
                            move=move_counter + 1,
                            mouse=mouse_info["name"],
                            position=positions[user.id],
                        )
                    )

            # Who threw the bomb and who caught the blast — reported after everyone
            # has moved so these land at the end of the footer, where they're visible.
            if bomb_user:
                move_number = move_counter + 1
                debug_log.append(
                    lang.RACING_LOG_BOMB_THROWN.format(
                        move=move_number, mouse=user_mouse_names_classes[bomb_user.id]["name"]
                    )
                )
                if bomb_hits:
                    debug_log.append(
                        lang.RACING_LOG_BOMB_HITS.format(move=move_number, mice=", ".join(bomb_hits))
                    )
                if bomb_dodgers:
                    debug_log.append(
                        lang.RACING_LOG_BOMB_DODGED.format(move=move_number, mice=", ".join(bomb_dodgers))
                    )
                if not bomb_hits and not bomb_dodgers:
                    debug_log.append(lang.RACING_LOG_BOMB_FIZZLE.format(move=move_number))

            # Everyone has moved: if a single mouse is left it has nobody to race,
            # so wave it home rather than make it crawl the rest alone.
            if len(mouse_users) - len(completed_mice) == 1:
                last_user = next(u for u in mouse_users if u.id not in completed_mice)
                positions[last_user.id] = track_length
                completed_mice.add(last_user.id)
                finished_order.append(last_user)
                debug_log.append(
                    f"Move {move_counter + 1}: "
                    f"{user_mouse_names_classes[last_user.id]['name']} forced finish!"
                )

            move_counter += 1
            await self.update_race_progress(
                race_message, race_starter, mouse_users, user_mouse_names_classes, positions,
                track_length, debug_log, event_text, move_counter,
            )

    async def _grab_event(self, race_message, eligible_users, emoji, timeout):
        """Add ``emoji`` and return the first eligible racer to click it (or None).

        Unifies the cheese / wine / bomb / starry-eyes / treasure-map events, which
        only differ by emoji and eligibility.

        Listens on ``raw_reaction_add`` rather than ``reaction_add``: the latter
        only fires for messages still in the gateway's message cache, which a
        gigarace sign-up message — nine hours old by the time the race starts —
        has long since been evicted from.
        """
        await race_message.add_reaction(emoji)
        eligible_by_id = {user.id: user for user in eligible_users}

        def check(payload):
            return (
                payload.message_id == race_message.id
                and str(payload.emoji) == emoji
                and payload.user_id in eligible_by_id
            )

        try:
            payload = await self.bot.wait_for("raw_reaction_add", timeout=timeout, check=check)
            user = eligible_by_id[payload.user_id]
            await race_message.remove_reaction(emoji, user)
            await race_message.remove_reaction(emoji, self.bot.user)
            return user
        except asyncio.TimeoutError:
            await race_message.clear_reaction(emoji)
            return None

    def roll_dice(self) -> int:
        """Weighted move roll: mostly +1, sometimes -1/+2/+3."""
        roll = random.randint(0, 10)
        if roll <= 1:
            return -1
        if roll <= 7:
            return 1
        if roll <= 9:
            return 2
        return 3

    async def update_race_progress(self, race_message, race_starter, mouse_users, user_mouse_names_classes,
                                   positions, track_length, debug_log, event_text, move_counter) -> None:
        """Redraw the track embed with everyone's position and recent actions."""
        race_lines = [
            f"{user.mention}'s {user_mouse_names_classes[user.id]['name']} \n"
            f":triangular_flag_on_post: "
            f"{''.join('-' if i != positions[user.id] else MOUSE for i in range(track_length))} :checkered_flag:"
            for user in mouse_users
        ]
        embed = discord.Embed(
            title=lang.RACING_PROGRESS_TITLE,
            description=f"{race_starter.mention}'s race:\nMove {move_counter}\n" + "\n".join(race_lines),
            color=0x00FF00,
        )
        embed.set_footer(text="\n".join(debug_log[-10:]))
        await race_message.edit(embed=embed, content=event_text)

    # --------------------------------------------------------------------- #
    #  Results
    # --------------------------------------------------------------------- #
    def calculate_race_results(self, finished_order) -> dict:
        """Map each finisher to their position and points."""
        return {user: {"position": i + 1, "points": self.get_points(i)} for i, user in enumerate(finished_order)}

    def get_points(self, position: int) -> int:
        """Points awarded for a finishing position (0-indexed)."""
        points = [10, 6, 4, 3, 2, 1]
        return points[position] if position < 6 else 0

    async def send_race_summary(self, context, race_starter, mice, race_results) -> None:
        """Post the plain-text results summary."""
        summary = lang.RACING_SUMMARY_HEADER
        for user, result in race_results.items():
            summary += lang.RACING_SUMMARY_LINE.format(mention=user.mention, mouse=mice[user.id]["name"], points=result["points"])
        await context.send(summary)

    def save_race_results(self, race_name, race_starter, mice, race_results) -> None:
        """Persist the race outcome to the database."""
        config_py.races.insert_one(
            {
                "race_name": race_name,
                "race_starter_id": race_starter.id,
                "participants": [
                    {
                        "user_id": user.id,
                        "mouse_name": mice[user.id]["name"],
                        "position": result["position"],
                        "points": result["points"],
                        "is_winner": result["position"] <= 6,
                    }
                    for user, result in race_results.items()
                ],
            }
        )

    # --------------------------------------------------------------------- #
    #  Relationships & adoption
    # --------------------------------------------------------------------- #
    async def mousechat(self, context, *, message) -> None:
        """Relay an in-character LLM message (used by the adoption prompts)."""
        if self.client is None:
            return
        completion = self.client.chat.completions.create(
            model="gpt-4o",
            temperature=1,
            messages=[
                {"role": "system", "content": "You return the message in the form of direct speech playing your role:"},
                {"role": "user", "content": message},
            ],
        )
        content = completion.choices[0].message.content
        for chunk in range(0, len(content), 1990):
            await context.send(content[chunk : chunk + 1990])

    async def update_relationships(self, context, race_results, user_mouse_names_classes) -> None:
        """Adjust relationship points based on finishing positions and report them."""
        participants_count = len(race_results)
        base_points = config_py.RELATIONSHIP_BASE_POINTS
        points_distribution = {}

        if participants_count == 2:
            points_distribution = {1: 10, 2: -10}
        else:
            top_half_size = participants_count // 2
            for pos in range(1, top_half_size + 1):
                points_distribution[pos] = math.ceil((base_points / pos) * participants_count)
            if participants_count % 2 == 1:
                points_distribution[top_half_size + 1] = 0
                bottom_start = top_half_size + 2
            else:
                bottom_start = top_half_size + 1
            for pos in range(bottom_start, participants_count + 1):
                mirror_pos = participants_count + 1 - pos
                points_distribution[pos] = int(round(-0.25 * points_distribution.get(mirror_pos, 0)))

        message_lines = []
        for user in race_results:
            if getattr(user, "bot", False):
                continue
            points_gained = points_distribution.get(race_results[user]["position"], 0)
            mouse_name = user_mouse_names_classes[user.id]["name"]
            rel_list = config_py.user_mice.find_one({"name": mouse_name}).get("Relationship", [])
            for entry in rel_list:
                if entry["user_id"] == user.id:
                    entry["relationship_points"] += points_gained
                    break
            else:
                rel_list.append({"user_id": user.id, "relationship_points": points_gained})
            config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"Relationship": rel_list}})
            message_lines.append(lang.RACING_RELATIONSHIP_LINE.format(mention=user.mention, points=points_gained, mouse=mouse_name))

        if message_lines:
            embed = messages.embed(
                "\n".join(message_lines), title=lang.RACING_RELATIONSHIP_TITLE, color=config_py.main_color
            )
            await context.send(embed=embed)

    async def adoption_check(self, context, user_mouse_names_classes) -> None:
        """After a race, prompt adoption for any mouse that crossed the threshold."""
        threshold = config_py.MOUSE_ADOPTION_RANK
        for user_id, info in user_mouse_names_classes.items():
            user = self.bot.get_user(user_id)
            mouse_name = info["name"]
            mouse_doc = config_py.user_mice.find_one({"name": mouse_name})
            rel_list = mouse_doc.get("Relationship", [])
            user_points = next((e["relationship_points"] for e in rel_list if e["user_id"] == user_id), 0)

            if user_points >= threshold and not mouse_doc.get("adopted_by"):
                await self.mousechat(context, message=lang.RACING_ADOPT_MOUSECHAT.format(mouse=mouse_name, name=user.name))
                await self._adoption_prompt(context, user, mouse_name, decline_penalty=500, verb="adopt")

            elif user_points >= threshold and mouse_doc.get("adopted_by") and mouse_doc.get("adopted_by") != user_id:
                current_owner = mouse_doc["adopted_by"]
                current_owner_points = next((e["relationship_points"] for e in rel_list if e["user_id"] == current_owner), 0)
                if current_owner_points < threshold:
                    await self.mousechat(context, message=lang.RACING_READOPT_MOUSECHAT.format(mouse=mouse_name))
                    await self._adoption_prompt(context, user, mouse_name, decline_penalty=500, verb="readopt")

    async def _adoption_prompt(self, context, user, mouse_name, *, decline_penalty, verb) -> None:
        """Ask ``user`` to (re)adopt ``mouse_name`` via 👍/👎 in the command channel."""
        adopt_msg = await context.send(lang.RACING_ADOPT_PROMPT.format(mention=user.mention, verb=verb, mouse=mouse_name))
        emoji, _ = await messages.wait_for_reaction(self.bot, adopt_msg, ["👍", "👎"], member=user, timeout=20.0)
        if emoji is None:
            await adopt_msg.clear_reactions()
            return
        if emoji == "👍":
            config_py.user_mice.update_one({"name": mouse_name}, {"$set": {"adopted_by": user.id}})
            success = (
                lang.RACING_ADOPT_SUCCESS.format(mouse=mouse_name)
                if verb == "adopt"
                else lang.RACING_READOPT_SUCCESS.format(mouse=mouse_name)
            )
            await context.send(success)
        else:
            config_py.user_mice.update_one(
                {"name": mouse_name, "Relationship.user_id": user.id},
                {"$inc": {"Relationship.$.relationship_points": -decline_penalty}},
            )
            await context.send(lang.RACING_ADOPT_DECLINE.format(mouse=mouse_name))
        await adopt_msg.clear_reactions()

    @commands.hybrid_command(name="relationships", description="Show your relationships with mice.")
    async def relationships(self, context: Context) -> None:
        """List the caller's mouse relationships, paginated with ◀️/▶️."""
        mouse_docs = list(config_py.user_mice.find({"Relationship.user_id": context.author.id}))
        rel_list = []
        for doc in mouse_docs:
            for rel in doc.get("Relationship", []):
                if rel["user_id"] == context.author.id:
                    rel_list.append({"name": doc["name"], "class": doc.get("class", "Unknown"), "points": rel["relationship_points"]})
                    break
        if not rel_list:
            await context.send(lang.RACING_REL_NONE)
            return

        rel_list.sort(key=lambda x: x["points"], reverse=True)
        pages = [rel_list[i : i + 10] for i in range(0, len(rel_list), 10)]
        current_page = 0

        def render(page_index):
            embed = messages.embed(
                "\n".join(
                    lang.RACING_REL_LINE.format(name=r["name"], mouse_class=r["class"], points=r["points"])
                    for r in pages[page_index]
                ),
                title=lang.RACING_REL_TITLE,
                color=config_py.main_color,
            )
            embed.set_footer(text=lang.RACING_REL_FOOTER.format(page=page_index + 1, total=len(pages)))
            return embed

        msg = await context.send(embed=render(current_page))
        if len(pages) == 1:
            return
        await msg.add_reaction("◀️")
        await msg.add_reaction("▶️")

        def check(reaction, user):
            return user == context.author and str(reaction.emoji) in ("◀️", "▶️") and reaction.message.id == msg.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except discord.HTTPException:
                    pass
                break
            current_page = (current_page + (1 if str(reaction.emoji) == "▶️" else -1)) % len(pages)
            await msg.edit(embed=render(current_page))
            await msg.remove_reaction(reaction.emoji, user)


async def setup(bot):
    await bot.add_cog(Racing(bot))
