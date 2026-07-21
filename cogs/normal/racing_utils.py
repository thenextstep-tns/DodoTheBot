import asyncio
import time
import random
import math
from collections import defaultdict
import disnake
import config_py

# MESSAGE UPDATES
async def update_race_message(race_message, race_starter, track_length, time_left):
    end_time = time.time() + time_left
    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        await race_message.edit(content=(
            f"{race_starter.mention} started the race of {track_length} laps! You have {remaining_time} seconds "
            "to react and add your skeevaton to the race roster.\nReact with 🐁 to join the race."
        ))
        await asyncio.sleep(1)

async def update_gigarace_message(race_message, race_starter, track_length, time_left):
    end_time = time.time() + time_left
    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        await race_message.edit(content=(
            f"THE **GIGARACE** HAS JUST BEEN ANNOUNCED! You have {remaining_time} seconds to react and add "
            "your skeevaton to the race roster.\nReact with 🐁 to join the race.\n "
            "1st place - 100 000 gold\n 2nd place - 50 000 gold\n 3rd place - 10 000 gold "
        ))
        await asyncio.sleep(100)

# REACTION HANDLING
async def get_reaction_users(race_message, emoji):
    for reaction in race_message.reactions:
        if str(reaction.emoji) == emoji:
            return [user async for user in reaction.users()]  # if not user.bot
    return []

# ASSIGNMENT & EMBEDS
def assign_mice_classes(mouse_users):
    available_mice = list(config_py.user_mice.find())
    random.shuffle(available_mice)
    assigned = {}
    for user in mouse_users:
        mouse = available_mice.pop()
        mouse_class = config_py.mouse_classes.find_one({"name": mouse['class']})
        if mouse_class:
            assigned[user.id] = {
                "name": mouse['name'],
                "class": mouse_class['name'],
                "class_description": mouse_class['description']
            }
    return assigned

async def send_lineup_embed(race_message, context, user_mouse_names_classes):
    embed = disnake.Embed(
        title="Race Line-up",
        description="The race is about to start!\n",
        color=0xFF0000,
    )
    for user_id, mouse_info in user_mouse_names_classes.items():
        user = context.guild.get_member(user_id)
        embed.add_field(
            name=f"{user.display_name}'s {mouse_info['name']} ({mouse_info['class']})",
            value="",
        )
    await race_message.edit(embed=embed, content="")

async def run_race_lights(race_message, race_starter, track_length, user_mouse_names_classes):
    black_circle = u"\U000026AB"
    red_circle = u"\U0001F534"
    green_circle = u"\U0001F7E2"
    roster_description = "\n".join([
        f"{mouse_info['name']} ({mouse_info['class']})" for mouse_info in user_mouse_names_classes.values()
    ])
    embed = disnake.Embed(
        title="Race is about to start!",
        description=(
            f"{roster_description}\n\n"
            "Reactions:\n"
            "🧀 Cheese: Increases your move by 1\n"
            "🍷 Wine: Multiplies your move by 2\n"
            "💣 Bomb: Drops everyone else back by 5"
        ),
        color=0xFFFF00
    )
    for i in range(5):
        lights = [red_circle if j <= i else black_circle for j in range(5)]
        embed.set_footer(text=''.join(lights))
        await race_message.edit(embed=embed)
        await asyncio.sleep(1)
    await asyncio.sleep(1)
    embed.set_footer(text=''.join([green_circle] * 5))
    embed.description = f"{roster_description}\n\nGOOOO!!!"
    await race_message.edit(embed=embed)

def initialize_race(mouse_users):
    positions = {user.id: 0 for user in mouse_users}
    completed = set()
    finished = []
    return positions, completed, finished

def roll_dice():
    roll = random.randint(0, 10)
    if roll <= 1:
        return -1
    elif 1 < roll <= 7:
        return 1
    elif 7 < roll <= 9:
        return 2
    else:
        return 3

async def update_race_progress(race_message, race_starter, mouse_users, user_mouse_names_classes,
                               positions, track_length, debug_log, event_text, move_counter):
    mouse_emoji = u"\U0001F401"
    race_lines = [
        f"{user.mention}'s {user_mouse_names_classes[user.id]['name']} \n"
        f":triangular_flag_on_post: {''.join(['-' if i != positions[user.id] else mouse_emoji for i in range(track_length)])} :checkered_flag:"
        for user in mouse_users
    ]
    description = "\n".join(race_lines)
    embed = disnake.Embed(
        title=f"THE SKEEVATON RACE IS ON!",
        description=f"{race_starter.mention}'s race:\nMove {move_counter}\n{description}",
        color=0x00ff00,
    )
    last10 = debug_log[-10:]
    embed.set_footer(text="\n".join(last10))
    await race_message.edit(embed=embed, content=event_text)

def calculate_race_results(finished_order):
    return {user: {"position": i + 1, "points": get_points(i)} for i, user in enumerate(finished_order)}

def get_points(position):
    points = [10, 6, 4, 3, 2, 1]
    return points[position] if position < 6 else 0

async def send_race_summary(context, race_starter, user_mouse_names_classes, race_results):
    summary = f"The race has ended!\nRace Results:\n"
    for user, result in race_results.items():
        summary += f"{user.mention}'s {user_mouse_names_classes[user.id]['name']} - {result['points']} points\n"
    await context.send(summary)

def save_race_results(race_name, race_starter, user_mouse_names_classes, race_results):
    race_data = {
        "race_name": race_name,
        "race_starter_id": race_starter.id,
        "participants": [
            {
                "user_id": user.id,
                "mouse_name": user_mouse_names_classes[user.id]['name'],
                "position": result['position'],
                "points": result['points'],
                "is_winner": result['position'] <= 6,
            }
            for user, result in race_results.items()
        ],
    }
    config_py.races.insert_one(race_data)

# EVENT UTILS
async def cheese_event(context, race_message, mouse_users, race_starter):
    cheese_emoji = u"\U0001F9C0"
    await race_message.add_reaction(cheese_emoji)
    def check(reaction, user):
        return str(reaction.emoji) == cheese_emoji and user in mouse_users and not user.bot
    try:
        reaction, user = await context.bot.wait_for('reaction_add', timeout=2.0, check=check)
        await race_message.remove_reaction(cheese_emoji, user)
        await race_message.remove_reaction(cheese_emoji, context.bot.user)
        return user
    except asyncio.TimeoutError:
        await race_message.clear_reaction(cheese_emoji)
        return None

async def wine_event(context, race_message, mouse_users, race_starter):
    wine_emoji = u"\U0001F377"
    await race_message.add_reaction(wine_emoji)
    def check(reaction, user):
        return str(reaction.emoji) == wine_emoji and user in mouse_users and not user.bot
    try:
        reaction, user = await context.bot.wait_for('reaction_add', timeout=2.0, check=check)
        await race_message.remove_reaction(wine_emoji, user)
        await race_message.remove_reaction(wine_emoji, context.bot.user)
        return user
    except asyncio.TimeoutError:
        await race_message.clear_reaction(wine_emoji)
        return None

async def bomb_event(context, race_message, mouse_users, race_starter):
    bomb_emoji = u"\U0001F4A3"
    await race_message.add_reaction(bomb_emoji)
    def check(reaction, user):
        return str(reaction.emoji) == bomb_emoji and user in mouse_users and not user.bot
    try:
        reaction, user = await context.bot.wait_for('reaction_add', timeout=2.0, check=check)
        await race_message.remove_reaction(bomb_emoji, user)
        await race_message.remove_reaction(bomb_emoji, context.bot.user)
        return user
    except asyncio.TimeoutError:
        await race_message.clear_reaction(bomb_emoji)
        return None

async def starry_eyes_event(race_message, mouse_users, adopted_owners, bot):
    star_emoji = "✨"
    await race_message.add_reaction(star_emoji)
    def check(reaction, user):
        return (str(reaction.emoji) == star_emoji and user in mouse_users and not user.bot and user.id in adopted_owners)
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=2.0, check=check)
        await race_message.remove_reaction(star_emoji, user)
        await race_message.remove_reaction(star_emoji, bot.user)
        return user
    except asyncio.TimeoutError:
        await race_message.clear_reaction(star_emoji)
        return None
