import json
import os
import random
import sys
import asyncio
import uuid
import math # Added for ceil function
from collections import defaultdict
import disnake
from disnake.ext import commands
from disnake.ext.commands import Context
from datetime import datetime, timedelta
from helpers import checks # Assuming you have this helper file

# --- Load Config Files ---

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

# --- Cog Definition ---

class Pumpkin(commands.Cog, name="Pumpkin"):
    def __init__(self, bot):
        self.bot = bot
        # --- Database Collections ---
        self.pumpkin_gains_db = config_py.pumpkins
        self.pull_db = config_py.pull
        self.pumpkin_expenses_db = config_py.pumpkinstats
        self.pumpkin_match_log_db = config_py.pumpkinlog
        self.renown_db = config_py.renown # NEW: Renown collection
        
        # --- Game Emojis ---
        self.JOIN_EMOJI = "🎃"
        self.ACTION_CHARGE_EMOJI = "💥" # Attack
        self.ACTION_BLOCK_EMOJI = "🛡️" # Block
        self.ACTION_DODGE_EMOJI = "💨" # Dodge
        
        # --- Game Constants ---
        self.PUMPKIN_ROLE_ID = 1430471888412475413 # The "covered in guts" role
        self.TEAM_SIZE = 10
        self.FIGHT_JOIN_COST = 5
        self.BASE_STRENGTH = 50        # Default strength for new players
        self.ACTION_POINTS_PER_ROUND = 5 # NEW: 5 AP per round
        self.ATTACK_COST_PER_AP = 3      # NEW: 3kg per 1 AP (This is the *base* cost for the first AP)
        self.BOT_USER_ID = "bot"         # Special ID for the bot player
        self.WINNER_STRENGTH_BONUS = 15
        self.WINNER_SEED_BONUS = 10
        
        # Block mapping: clicks -> % reduction
        self.BLOCK_MAP = {
            0: 0.0,
            1: 0.10,
            2: 0.25,
            3: 0.40,
            4: 0.65,
            5: 0.90
        }
        
        # NEW: Berserker Rage mapping: Atk AP -> Dmg Taken Multiplier
        self.BERSERKER_MAP = {
            0: 1.0,   # 0 AP = 1.0x damage taken
            1: 1.1,   # 1 AP = 1.1x damage taken
            2: 1.2,   # 2 AP = 1.2x damage taken
            3: 1.4,   # 3 AP = 1.4x damage taken
            4: 1.75,  # 4 AP = 1.75x damage taken
            5: 2.1    # 5 AP = 2.1x damage taken (Assumed ramp up)
        }

        # --- NEW: Survivor Bonus Map ---
        self.SURVIVOR_BONUS_MAP = {
            0: (1.0, 1.0),    # 0% dead
            1: (1.02, 0.98),  # 10% dead
            2: (1.04, 0.96),  # 20% dead
            3: (1.06, 0.94),  # 30% dead
            4: (1.08, 0.92),  # 40% dead
            5: (1.10, 0.90),  # 50% dead
            6: (1.13, 0.87),  # 60% dead
            7: (1.16, 0.84),  # 70% dead
            8: (1.20, 0.80),  # 80% dead
            9: (1.25, 0.75),  # 90% dead (Last one standing)
            10: (1.25, 0.75)  # 100% dead (Shouldn't happen, but safeguard)
        }
        
        # --- NEW: Targeting Probability Maps ---
        self.TARGETING_WEIGHTS_MAP = {
            1: {0: 1.0}, # 1v1, always hit
            2: {0: 0.8, 1: 0.2}, # 2v2
            3: {0: 0.6, 1: 0.3, 2: 0.1}, # 3v3
            4: {0: 0.5, 1: 0.35, 2: 0.1, 3: 0.05}, # 4v4
            5: {0: 0.45, 1: 0.3, 2: 0.15, 3: 0.07, 4: 0.03}, # 5v5
            6: {0: 0.4, 1: 0.25, 2: 0.15, 3: 0.1, 4: 0.05, 5: 0.05}, # 6v6
            7: {0: 0.35, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05, 6: 0.05}, # 7v7
            8: {0: 0.3, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05, 6: 0.05, 7: 0.05}, # 8v8
            9: {0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05, 6: 0.05, 7: 0.05, 8: 0.05}, # 9v9
            10: {0: 0.2, 1: 0.15, 2: 0.1, 3: 0.1, 4: 0.1, 5: 0.05, 6: 0.05, 7: 0.05, 8: 0.05, 9: 0.05} # 10v10
        }
        
        # --- NEW: Miss Chance Map ---
        self.MISS_CHANCE_ON_DEAD_TARGET = {
            0: 0.10, # 10% chance to miss if you target your dead opposite
            1: 0.20, # 20% chance to miss if you target a dead offset 1
            2: 0.30, # 30%
            3: 0.40, # 40%
            4: 0.50, # 50%
            # And so on
        }

        # NEW: Team Name List
        self.TEAM_NAMES = [
            "Foxes", "Salvys", "Firmlys", "Apos", "Lynas", "Tomtems", "Gilanes", 
            "Corvins", "Capos", "Ryans", "Kitis", "Obiis", "Vulpys", "Rosas", 
            "Norns", "Overs", "Straders", "Teas", "Bellas", "Ereds", "Schnitzels", 
            "Ores", "Ghosts", "Cobbles", "Duckies", "Stefans", "Rabs", "Gilas",
            "Deis", "Huskies", "Koalas", "Ellanders", "Gelthors"
        ]

        # --- NEW: PUMPKIN RENOWN SYSTEM ---
        self.RENOWN_TITLES = {
            100: "Seed-stained",
            250: "The Pulp Friction",
            600: "The Final Clobber",
            1000: "The Harvester of Sorrow",
            2000: "The Squash Warlord",
            float('inf'): "The PumpKing"
        }
        self.RENOWN_BASE_TITLE = "Seed-stained" # Title for 0-50 renown
        
        # Renown point mapping
        self.RENOWN_AWARDS = {
            "win": 10,
            "survivor": 5,
            "splat": 3,
            "dodge": 2,
            "damage_50kg": 1,
            "last_stand": 5,
            "loss": -2,
            "splatted": -1,
            "fizzle": -3
        }

    # --- Role Removal Helper (from original bot) ---
    
    async def remove_role_later(self, member: disnake.Member, role: disnake.Role):
        """
        Waits 1 hour, then removes the specified role from the member if they still have it.
        This is not persistent; if the bot restarts, the timer is lost.
        """
        await asyncio.sleep(3600)  # 1 hour
        try:
            if role in member.roles:
                await member.remove_roles(role)
        except disnake.HTTPException:
            pass  # Member might have left, or permissions changed

    # --- Internal Helper Functions ---

    async def _get_user_strength(self, user_id: int) -> int:
        """Fetches a user's pull strength, defaulting to BASE_STRENGTH."""
        if user_id == self.BOT_USER_ID:
            return self.BASE_STRENGTH
        user_data = self.pull_db.find_one({"_id": user_id})
        return user_data.get("strength", self.BASE_STRENGTH) if user_data else self.BASE_STRENGTH

    async def _update_user_strength(self, user_id: int, new_strength: int):
        """Updates a user's pull strength in the database."""
        if user_id == self.BOT_USER_ID:
            return
        self.pull_db.update_one(
            {"_id": user_id},
            {"$set": {"strength": new_strength, "last_pull": datetime.now()}},
            upsert=True
        )

    async def _get_total_pumpkin_collected(self, user_id: int) -> int:
        """Calculates total pumpkin (kg) collected from the original game."""
        pipeline = [
            {"$match": {"collector": user_id}},
            {"$group": {"_id": "$collector", "total": {"$sum": "$weight_collected"}}}
        ]
        result = list(self.pumpkin_gains_db.aggregate(pipeline))
        return result[0]["total"] if result else 0

    async def _get_total_pumpkin_spent(self, user_id: int) -> int:
        """Calculates total pumpkin (kg) spent from the new stats collection."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$user_id", "total": {"$sum": "$amount"}}}
        ]
        result = list(self.pumpkin_expenses_db.aggregate(pipeline))
        return result[0]["total"] if result else 0

    async def get_pumpkin_balance(self, user_id: int) -> int:
        """Gets the user's final pumpkin balance (Collected - Spent)."""
        if user_id == self.BOT_USER_ID:
            return 999999 # Bot has "infinite" pumpkins
        collected = await self._get_total_pumpkin_collected(user_id)
        spent = await self._get_total_pumpkin_spent(user_id) # spent is already negative
        return collected + spent

    async def _has_enough_pumpkin(self, user_id: int, cost: int) -> bool:
        """Checks if a user has enough pumpkin (kg) to spend."""
        if user_id == self.BOT_USER_ID:
            return True
        balance = await self.get_pumpkin_balance(user_id)
        return balance >= cost

    async def _spend_pumpkin(self, user_id: int, amount: int, reason: str):
        """Logs a pumpkin expense in the pumpkinstats collection."""
        if user_id == self.BOT_USER_ID:
            return
        if amount <= 0:
            return 
        
        doc = {
            "user_id": user_id,
            "amount": -abs(amount), # Store as a negative number
            "reason": reason,
            "date": datetime.now()
        }
        self.pumpkin_expenses_db.insert_one(doc)
    
    async def _add_pumpkin(self, user_id: int, amount: int, reason: str):
        """Adds pumpkins to a user's balance (a positive entry in the expenses db)."""
        if user_id == self.BOT_USER_ID:
            return
        if amount <= 0:
            return
        
        doc = {
            "user_id": user_id,
            "amount": abs(amount), # Store as a positive number
            "reason": reason,
            "date": datetime.now()
        }
        self.pumpkin_expenses_db.insert_one(doc)

    # --- NEW SEED HELPER FUNCTIONS ---
    
    async def _get_seed_balance(self, user_id: int) -> int:
        """Checks how many Pumpkin Seeds a user has."""
        if user_id == self.BOT_USER_ID: return 0
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$user_id", "total": {"$sum": "$seeds_earned"}}}
        ]
        result = list(self.pumpkin_match_log_db.aggregate(pipeline))
        # Ensure we handle potential None result if the aggregation returns nothing
        total_seeds = result[0]["total"] if result and "total" in result[0] else 0
        return total_seeds


    async def _spend_seeds(self, user_id: int, amount: int, reason: str):
        """Spends a user's Pumpkin Seeds."""
        if user_id == self.BOT_USER_ID: return
        if amount <= 0:
            return
        
        doc = {
            "user_id": user_id,
            "seeds_earned": -abs(amount), # Store as a negative number
            "event_description": reason,
            "timestamp": datetime.now()
        }
        self.pumpkin_match_log_db.insert_one(doc)

    async def _log_pumpkin_event(self, match_id: str, event: str, user_id: int = None, seeds: int = 0):
        """Logs a narrative event for a specific pumpkin match."""
        if user_id == self.BOT_USER_ID: return
        doc = {
            "match_id": match_id,
            "event_description": event,
            "timestamp": datetime.now()
        }
        if user_id:
            doc["user_id"] = user_id
        if seeds != 0: # Can be positive or negative
            doc["seeds_earned"] = seeds
            
        self.pumpkin_match_log_db.insert_one(doc)
    
    # --- NEW RENOWN HELPER FUNCTIONS ---
    
    def _get_renown_title(self, renown_score: int) -> str:
        """Gets the player's title based on their renown score."""
        for score_cap, title in self.RENOWN_TITLES.items():
            if renown_score <= score_cap:
                return title
        return self.RENOWN_BASE_TITLE # Fallback, though 'inf' should cover it

    async def _get_renown_score(self, user_id: int) -> int:
        """Calculates a user's total renown score from the renown db."""
        if user_id == self.BOT_USER_ID:
            return 0
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$user_id", "total_renown": {"$sum": "$renown_change"}}}
        ]
        result = list(self.renown_db.aggregate(pipeline))
        return result[0]["total_renown"] if result else 0

    async def _add_renown(self, user_id: int, amount: int, reason: str, match_id: str, match_stats: dict = None):
        """Logs a renown change event in the database."""
        if user_id == self.BOT_USER_ID:
            return
        if amount == 0:
            return
        
        doc = {
            "user_id": user_id,
            "renown_change": amount,
            "reason": reason,
            "match_id": match_id,
            "timestamp": datetime.now()
        }
        
        # If this is a final match log, add the stats
        if match_stats:
            doc.update(match_stats)
            
        self.renown_db.insert_one(doc)

    async def _get_renown_stats(self, user_id: int) -> dict:
        """Aggregates all renown stats for a user."""
        if user_id == self.BOT_USER_ID:
            return {}
        
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$user_id",
                "total_renown": {"$sum": "$renown_change"},
                "wins": {"$sum": {"$cond": [{"$eq": ["$reason", "win"]}, 1, 0]}},
                "losses": {"$sum": {"$cond": [{"$eq": ["$reason", "loss"]}, 1, 0]}},
                "splats": {"$sum": "$splats"},
                "splatted": {"$sum": "$splatted"},
                "dodges": {"$sum": "$dodges"},
                "damage_dealt": {"$sum": "$damage_dealt"},
                "fizzles": {"$sum": "$fizzles"},
                "last_stands": {"$sum": "$last_stands"}
            }}
        ]
        result = list(self.renown_db.aggregate(pipeline))
        return result[0] if result else {}

    # --- (End Renown Helpers) ---

    def _roll_d20(self) -> int:
        """Rolls a 20-sided die."""
        return random.randint(1, 20)

    async def _get_temporary_role(self, guild: disnake.Guild) -> disnake.Role:
        """Safely gets the "covered in guts" role."""
        if not guild:
            return None
        return guild.get_role(self.PUMPKIN_ROLE_ID)

    async def _apply_splat_role(self, member: disnake.Member, role: disnake.Role, channel: disnake.TextChannel):
        """Applies the temporary splat role and schedules its removal."""
        if not member or not role or member.id == self.BOT_USER_ID:
            return
        try:
            if role not in member.roles:
                await member.add_roles(role)
                self.bot.loop.create_task(self.remove_role_later(member, role))
        except disnake.Forbidden:
            pass # Silently fail, log will show it
        except Exception as e:
            print(f"Error adding temporary pumpkin role: {e}")

    def _calculate_ramping_attack_cost(self, attack_ap: int) -> int:
        """
        Calculates the total pumpkin cost for a given number of attack AP,
        where each consecutive AP costs 1 more kg than the last.
        Base cost (self.ATTACK_COST_PER_AP) is for the first AP.
        Example (base 3): 1 AP = 3. 2 AP = 3+4=7. 3 AP = 3+4+5=12.
        """
        if attack_ap <= 0:
            return 0
        
        base_cost = self.ATTACK_COST_PER_AP
        total_cost = 0
        for i in range(attack_ap):
            total_cost += (base_cost + i)
        return total_cost

    # --- NEW: TARGETING HELPER FUNCTIONS ---
    
    def _get_targeting_weights(self, num_opponents: int) -> dict:
        """
        Gets the targeting weight map {offset: probability} for a given team size.
        """
        if num_opponents <= 0:
            return {0: 1.0} # Should not happen, but safeguard
        # Get the map for the closest size, clamping at 1 and 10
        clamped_size = max(1, min(10, num_opponents))
        return self.TARGETING_WEIGHTS_MAP.get(clamped_size, {0: 1.0})

    def _get_miss_chance_for_dead_target(self, offset: int) -> float:
        """
        Gets the miss chance float (0.0 to 1.0) for targeting a dead player
        at a specific offset.
        """
        offset = abs(offset)
        # Get the defined miss chance, or default to a high value if offset is large
        return self.MISS_CHANCE_ON_DEAD_TARGET.get(offset, 0.75)

    def _select_target(self, attacker_index: int, opponent_team_list: list, living_opponents: list):
        """
        Selects a target based on the new weighted random logic.
        Returns a tuple of (target_player, intended_offset, log_message)
        target_player can be None if it's a miss.
        """
        num_opponents = len(opponent_team_list)
        if num_opponents == 0 or not living_opponents:
            return None, 0, "No targets left!" # No one to hit

        # 1. Get the base probability map for this team size
        base_weights = self._get_targeting_weights(num_opponents)
        
        # 2. Build the *actual* probability map based on clamping
        #    This combines probabilities for clamped targets.
        #    e.g., for attacker[0], offset -1 and -2 both clamp to index 0.
        target_probs = defaultdict(float)
        # Store the *first* offset that leads to this index, for miss chance calculation
        target_original_offset = {} 

        # Iterate through all possible offsets from the base map
        for offset, prob in base_weights.items():
            # Apply to positive and negative offsets
            for o in [offset, -offset]:
                if o == 0 and offset != 0: # Don't double-count offset 0
                    continue

                clamped_index = max(0, min(attacker_index + o, num_opponents - 1))
                target_probs[clamped_index] += prob

                if clamped_index not in target_original_offset:
                         # Store the *smallest absolute offset* that maps here
                         # This is a bit arbitrary, but we need *an* offset
                         target_original_offset[clamped_index] = o

        # 3. Create lists for random.choices
        choices_indices = list(target_probs.keys())
        choices_weights = list(target_probs.values())

        # 4. Make the weighted random choice
        chosen_index = random.choices(choices_indices, weights=choices_weights, k=1)[0]
        
        # 5. Get the chosen opponent and the offset that was *intended*
        chosen_opponent = opponent_team_list[chosen_index]
        intended_offset = target_original_offset[chosen_index]

        # 6. --- APPLY NEW "DEAD TARGET" LOGIC ---
        if chosen_opponent["hp"] > 0:
            # Happy path: Target is alive
            return chosen_opponent, intended_offset, f"🎯 targets {chosen_opponent['obj'].display_name}!"
        else:
            # Unhappy path: Target is DEAD!
            miss_chance = self._get_miss_chance_for_dead_target(intended_offset)
            
            if random.random() < miss_chance:
                # --- MISS ---
                return None, intended_offset, f"🎯 targets {chosen_opponent['obj'].display_name}'s corpse but **MISSES** entirely! (Offset {intended_offset}, {miss_chance*100}% miss)"
            else:
                # --- RE-TARGET ---
                # Hit a *random* living opponent instead
                new_target = random.choice(living_opponents)
                return new_target, intended_offset, f"🎯 targets {chosen_opponent['obj'].display_name}'s corpse, but hits {new_target['obj'].display_name} instead!"

    # --- NEW: SURVIVOR BONUS HELPER ---
    
    def _get_survivor_bonus(self, player_team_data: list) -> (float, float):
        """
        Calculates the Survivor Bonus multipliers for a player based on their team's status.
        Returns (damage_dealt_multiplier, damage_taken_multiplier)
        """
        original_size = len(player_team_data)
        
        # Only apply bonus if team size was > 2
        if original_size <= 2:
            return 1.0, 1.0
            
        alive_count = len([p for p in player_team_data if p["hp"] > 0])
        dead_count = original_size - alive_count
        
        # Get percentage of team dead, as an int key from 0-10
        dead_percent_key = round((dead_count / original_size) * 10)
        
        return self.SURVIVOR_BONUS_MAP.get(dead_percent_key, (1.0, 1.0))

    # --- User Commands ---

    @commands.command(name="pumpkinstats", description="Check your pumpkin balance.")
    @checks.not_blacklisted()
    async def pumpkinstats(self, context: Context, member : disnake.Member = None):
        """
        Calculates and displays your total pumpkin stats.
        Shows how much you've collected vs. how much you've spent.
        """
        if not member:
            member = context.author
        user_id = member.id
        await context.trigger_typing()

        collected = await self._get_total_pumpkin_collected(user_id)
        spent = await self._get_total_pumpkin_spent(user_id) # This is a negative number
        balance = collected + spent

        embed = disnake.Embed(
            title=f"🎃 {context.author.display_name}'s Pumpkin Accounting Department 🎃",
            color=disnake.Color.orange()
        )
        #embed.add_field(name="Total Pumpkin Collected", value=f"**{collected} kg**", inline=False)
        #embed.add_field(name="Total Pumpkin Thrown/Spent", value=f"**{abs(spent)} kg**", inline=False)
        embed.add_field(name="Available Pumpkin Balance", value=f"**{balance} kg**", inline=False)
        embed.set_footer(text="There's no such thing as enough pumpkin, go pull out some more!")

        await context.send(embed=embed)
    
    # --- NEW RENOWN COMMAND ---
    
    @commands.command(name="reputation", aliases=["fightstats", "pumpking"], description="Check your Pumpkin Renown and stats.")
    @checks.not_blacklisted()
    async def renown(self, context: Context, user: disnake.Member = None):
        """
        Displays your Pumpkin Renown score, title, and career stats from pumpkin fights.
        """
        if user is None:
            user = context.author
        
        await context.trigger_typing()
        
        renown_score = await self._get_renown_score(user.id)
        renown_title = self._get_renown_title(renown_score)
        stats = await self._get_renown_stats(user.id)
        
        embed = disnake.Embed(
            title=f"👑 {user.display_name}'s Reputation 👑",
            description=f"**Title:** *{renown_title}*\n**Reputation Score:** **{renown_score}**",
            color=disnake.Color.gold()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total_matches = wins + losses
        win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
        
        splats = stats.get("splats", 0)
        splatted = stats.get("splatted", 0)
        kd_ratio = (splats / splatted) if splatted > 0 else splats # Handle divide by zero
        
        embed.add_field(
            name="Career Stats",
            value=f"**Matches:** {total_matches} ({wins} W / {losses} L)\n"
                  f"**Win Rate:** {win_rate:.1f}%\n"
                  f"**Splat/Splat'd:** {splats} / {splatted} ({kd_ratio:.2f} K/D)",
            inline=False
        )
        
        embed.add_field(
            name="Performance",
            value=f"**Total Damage Dealt:** {stats.get('damage_dealt', 0)}kg\n"
                  f"**Successful Dodges:** {stats.get('dodges', 0)}\n"
                  f"**Last Stands:** {stats.get('last_stands', 0)}\n"
                  f"**Attack Fizzles:** {stats.get('fizzles', 0)}",
            inline=False
        )
        
        await context.send(embed=embed)


    # --- NEW TEAM TOURNAMENT GAME ---

    def _build_tournament_embed(self, team_a, team_b, team_a_name, team_b_name, round_num, action_text: str = None, log_list: list = None):
        """Helper to build the all-in-one status/action/log embed."""
        embed = disnake.Embed(title=f"🎃 Pumpkin Deathmatch: The {team_a_name} vs. The {team_b_name} - Round {round_num} 💀", color=disnake.Color.orange())
        
        def get_player_string(player):
            name = player['obj'].display_name
            title = player['renown_title'] # NEW: Get title
            hp_str = f"**HP:** {player['hp']}/{player['max_hp']}" # Show HP fraction
            # Display pumpkin balance for attacking
            balance_str = f"🎃 {player['balance']}kg" if player['id'] != self.BOT_USER_ID else "🎃 ∞ kg"
            # NEW: Add title to the string
            return f"**{name}**\n*{title}*\n{hp_str}\n{balance_str}"

        # --- 1. Roster Section ---
        # MODIFIED: These are now passed in as ALIVE lists
        gourds_alive_players = [get_player_string(p) for p in team_a]
        reapers_alive_players = [get_player_string(p) for p in team_b]
        
        embed.add_field(name=f"Team {team_a_name} ({len(gourds_alive_players)} left)", value="\n\n".join(gourds_alive_players) or "None", inline=True)
        embed.add_field(name=f"Team {team_b_name} ({len(reapers_alive_players)} left)", value="\n\n".join(reapers_alive_players) or "None", inline=True)
        
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Spacer

        # --- 2. Action Section ---
        if action_text:
            embed.add_field(name="TIME TO ACT", value=action_text, inline=False)

        # --- 3. Log Section ---
        if log_list:
            log_content = "\n".join(log_list)
            if not log_content:
                log_content = "Everyone blinked at each other menacingly."
            # Show results of the *previous* round
            embed.add_field(name=f"ROUND {round_num-1} RESULTS", value=log_content, inline=False)
            
        return embed

    def _bot_choose_action(self, bot_player):
        """Simple AI for the bot player. Returns dict of AP spent."""
        actions = {"attack": 0, "block": 0, "dodge": 0}
        ap_left = self.ACTION_POINTS_PER_ROUND
        
        # Bot's personality: "Tanky"
        # Prioritize blocking
        block_ap = random.randint(2, 3)
        actions["block"] = block_ap
        ap_left -= block_ap
        
        # Spend the rest
        actions["attack"] = ap_left
        
        return actions

    async def _resolve_1v1_attack(self, attacker, defender, attacker_actions, defender_actions, attacker_team_data, defender_team_data, log_list, match_id, total_spent_pot, round_num: int):
        """Resolves a single 1v1 attack based on new AP rules."""
        
        # --- NEW: Handle MISS ---
        if defender is None:
            # Attacker's target was dead, they missed the re-roll
            # No pumpkin is spent on a total miss
            log_list.append(f"💨 {attacker['obj'].display_name}'s attack missed everyone!")
            return total_spent_pot # No cost, no damage

        attack_ap = attacker_actions["attack"]
        attack_damage = self._calculate_ramping_attack_cost(attack_ap) # NEW: Ramping cost
        
        # --- NEW: Check if attacker has enough pumpkin ---
        if attacker["balance"] < attack_damage:
            # Player tried to attack for more than they have
            actual_spend = attacker["balance"] # The amount they *actually* had
            log_list.append(f"❌ {attacker['obj'].display_name} tried to attack with {attack_damage}kg, but only had **{actual_spend}kg**! The attack isn't successful!")
            # Spend their remaining pumpkin on the fizzled attack
            await self._spend_pumpkin(attacker["id"], actual_spend, f"tournament_fizzle_{match_id}")
            total_spent_pot += actual_spend # Add fizzled amount to pot
            attacker["fizzles"] += 1 # NEW: Track fizzle
            attack_damage = 0 # Attack fails
        
        if attack_damage == 0:
            return total_spent_pot # Attacker didn't attack or fizzled.

        # --- NEW: Get Survivor Bonus Multipliers ---
        atk_survivor_dealt_mult, atk_survivor_taken_mult = self._get_survivor_bonus(attacker_team_data)
        def_survivor_dealt_mult, def_survivor_taken_mult = self._get_survivor_bonus(defender_team_data)
        
        # --- Apply Survivor Bonus to Attack Damage ---
        original_attack_damage = attack_damage
        attack_damage = round(attack_damage * atk_survivor_dealt_mult)
        survivor_log = f" (x{atk_survivor_dealt_mult} survivor)" if atk_survivor_dealt_mult > 1.0 else ""

        log_list.append(f"💥 {attacker['obj'].display_name} attacks {defender['obj'].display_name} with **{attack_damage}**kg!{survivor_log}")
        
        # 1. Spend the pumpkin from inventory (spend original, un-multiplied cost)
        await self._spend_pumpkin(attacker["id"], original_attack_damage, f"tournament_attack_{match_id}")
        total_spent_pot += original_attack_damage # Add to the pot

        # 2. Determine Defender's action
        block_charge = defender_actions["block"]
        dodge_charge = defender_actions["dodge"]

        # --- 3a. Defender DODGES ---
        # MODIFIED: Dodge succeeds on >=, with a d20 roll for equality
        
        dodge_success = False
        roll_log = ""

        if dodge_charge > attack_ap:
            dodge_success = True
        elif dodge_charge == attack_ap:
            # --- NEW: d20 roll for equal AP ---
            # DC 11: 50% chance (10/20 outcomes fail, 10/20 succeed)
            roll = self._roll_d20()
            if roll >= 11:
                dodge_success = True
                roll_log = f" (Rolled {roll} vs DC 11)"
            else:
                dodge_success = False
                roll_log = f" (Rolled {roll} vs DC 11)"
        
        # --- NEW: Apply Block Deterioration ---
        # Deterioration is 2% per round, starting round 2. (Round 1 = 0%)
        block_deterioration_percent = max(0, (round_num - 1) * 0.02)

        if dodge_success:
            # --- SUCCESSFUL DODGE & REFLECT! ---
            defender["dodges"] += 1 # NEW: Track dodge
            # --- Apply Defender's Survivor Bonus to Reflected Damage ---
            reflected_damage = round((attack_damage / 2) * def_survivor_dealt_mult) 
            def_survivor_log = f" (x{def_survivor_dealt_mult} survivor)" if def_survivor_dealt_mult > 1.0 else ""
            log_list.append(f"💨 {defender['obj'].display_name} **DODGES!** (Dodge AP {dodge_charge} >= Atk AP {attack_ap}){roll_log}. Reflects **{reflected_damage}kg** back!{def_survivor_log}")
            await self._log_pumpkin_event(match_id, f"Successful dodge & reflect", defender["id"], 1) # +1 seed for a reflect
            
            # --- Now, Attacker must defend ---
            attacker_block_charge = attacker_actions["block"] # Check if attacker *also* blocked
            
            # --- NEW: Apply Attacker's Berserker Rage multiplier ---
            attacker_atk_ap = attacker_actions["attack"]
            berserk_mult = self.BERSERKER_MAP.get(attacker_atk_ap, 1.0)
            
            # Apply block deterioration
            base_block_percent = self.BLOCK_MAP.get(attacker_block_charge, 0.0)
            final_block_percent = max(0, base_block_percent - block_deterioration_percent)
            block_log = f" ({base_block_percent*100}%"
            if block_deterioration_percent > 0:
                block_log += f" - {block_deterioration_percent*100}% weaker block"
            block_log += ")"

            # --- Apply Attacker's Survivor Bonus (taken) and Berserker Rage ---
            damage_taken = round(reflected_damage * (1 - final_block_percent) * berserk_mult * atk_survivor_taken_mult) 
            
            # --- NEW: Track Damage Dealt (by the defender, in this case)
            defender["damage_dealt"] += damage_taken 
            
            attacker["hp"] -= damage_taken
            
            berserk_log = f" (x{berserk_mult} rage)" if berserk_mult > 1.0 else ""
            atk_survivor_log = f" (x{atk_survivor_taken_mult} survivor)" if atk_survivor_taken_mult < 1.0 else ""
            
            if attacker_block_charge > 0:
                log_list.append(f"🛡️ {attacker['obj'].display_name} **blocks**{block_log} the reflection and takes **{damage_taken}** damage!{berserk_log}{atk_survivor_log}")
            else:
                log_list.append(f"💥 {attacker['obj'].display_name} was **caught open** and takes the full reflected **{damage_taken}** damage!{berserk_log}{atk_survivor_log}")
            
            # NEW: Check for splat on reflect
            if attacker["hp"] <= 0:
                defender["splats"] += 1 # Defender gets the splat
                attacker["splatted"] = True # Mark attacker as splatted this match


        # --- 3b. Defender FAILS DODGE or BLOCKS ---
        else:
            if dodge_charge > 0:
                log_list.append(f"❌ {defender['obj'].display_name} **failed to dodge** (Dodge AP {dodge_charge} < Atk AP {attack_ap}){roll_log}!")
            
            # --- NEW: Apply Defender's Berserker Rage multiplier ---
            defender_atk_ap = defender_actions["attack"]
            berserk_mult = self.BERSERKER_MAP.get(defender_atk_ap, 1.0)
            
            # Apply block deterioration
            base_block_percent = self.BLOCK_MAP.get(block_charge, 0.0)
            final_block_percent = max(0, base_block_percent - block_deterioration_percent)
            block_log = f" ({base_block_percent*100}%"
            if block_deterioration_percent > 0:
                block_log += f" - {block_deterioration_percent*100}% deterioriation"
            block_log += ")"
            
            # --- Apply Defender's Survivor Bonus (taken) and Berserker Rage ---
            damage_taken = round(attack_damage * (1 - final_block_percent) * berserk_mult * def_survivor_taken_mult)
            
            # --- NEW: Track Damage Dealt ---
            attacker["damage_dealt"] += damage_taken
            
            defender["hp"] -= damage_taken

            berserk_log = f" (x{berserk_mult} rage)" if berserk_mult > 1.0 else ""
            def_survivor_log = f" (x{def_survivor_taken_mult} survivor)" if def_survivor_taken_mult < 1.0 else ""


            if block_charge > 0:
                log_list.append(f"🛡️ {defender['obj'].display_name} **blocks**{block_log} and takes **{damage_taken}** damage!{berserk_log}{def_survivor_log}")
            else:
                 log_list.append(f"😴 {defender['obj'].display_name} was **wide open** and takes **{damage_taken}** damage!{berserk_log}{def_survivor_log}")
            
            # NEW: Check for splat
            if defender["hp"] <= 0:
                attacker["splats"] += 1 # Attacker gets the splat
                defender["splatted"] = True # Mark defender as splatted this match

        return total_spent_pot


    @commands.command(name="fight", aliases=["pt"])
    @checks.not_blacklisted()
    async def pumpkintournament(self, context: Context):
        """
        Starts a 2-team (max 10v10) pumpkin tournament!
        React to join a team. Spend 5 AP per round on Attack, Block, or Dodge!
        """
        match_id = str(uuid.uuid4())
        lobby_time = 30 # 30 seconds to join
        
        # 1. Lobby Phase
        team_a_name, team_b_name = random.sample(self.TEAM_NAMES, 2)
        team_a = [] # Use lists to preserve order (of user objects)
        team_b = [] # Use lists to preserve order (of user objects)
        join_log = []

        base_lobby_text = (
            f"A team pumpkin deathmatch fight is starting! React to join and be assigned a team.\n"
            f"Cost to join: **{self.FIGHT_JOIN_COST}kg** of pumpkin.\n\n"
        )
        
        def build_lobby_embed(time_left):
            embed = disnake.Embed(
                title="🎃 Pumpkin Deathmatch Lobby 💀",
                description=base_lobby_text + f"Sign-ups are closed in **{time_left}** seconds!",
                color=disnake.Color.orange()
            )
            
            # NEW: Show player lists
            team_a_players = [p.display_name for p in team_a]
            team_b_players = [p.display_name for p in team_b]
            
            embed.add_field(name=f"Team {team_a_name} ({len(team_a)}/{self.TEAM_SIZE})", value="\n".join(team_a_players) or "Waiting...", inline=True)
            embed.add_field(name=f"Team {team_b_name} ({len(team_b)}/{self.TEAM_SIZE})", value="\n".join(team_b_players) or "Waiting...", inline=True)
            return embed

        lobby_embed = build_lobby_embed(lobby_time)
        
        # --- NEW: Use Buttons for Lobby ---
        class LobbyView(disnake.ui.View):
            def __init__(self, timeout, pumpkin_cog): # Pass cog in
                super().__init__(timeout=timeout)
                self.pumpkin_cog = pumpkin_cog # Store cog
                self.all_players = {} # Store user objects
                self.view_timeout_time = datetime.now() + timedelta(seconds=timeout)

            @disnake.ui.button(label="Join Fight!", style=disnake.ButtonStyle.primary, emoji="🎃", custom_id="join_fight")
            async def join_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
                user = interaction.user
                
                if user.id in self.all_players:
                    await interaction.response.send_message("You've already joined!", ephemeral=True)
                    return
                
                # Check cost
                if not await self.pumpkin_cog._has_enough_pumpkin(user.id, self.pumpkin_cog.FIGHT_JOIN_COST):
                    join_log.append(f"❌ {user.display_name} didn't have {self.pumpkin_cog.FIGHT_JOIN_COST}kg!")
                    # Send ephemeral message instead of public chat
                    await interaction.response.send_message(f"You don't have enough pumpkin to join! You need {self.pumpkin_cog.FIGHT_JOIN_COST}kg.", ephemeral=True)
                    return

                # Defer to make sure the "Join" click doesn't fail
                await interaction.response.defer()

                await self.pumpkin_cog._spend_pumpkin(user.id, self.pumpkin_cog.FIGHT_JOIN_COST, f"join_tournament_{match_id}")
                
                self.all_players[user.id] = user
                
                # Alternating assignment logic
                if len(team_a) <= len(team_b):
                    if len(team_a) < self.pumpkin_cog.TEAM_SIZE:
                        team_a.append(user)
                        join_log.append(f"🎃 {user.display_name} joined **Team {team_a_name}**!")
                    else:
                        team_b.append(user) # Overflow to other team
                        join_log.append(f"💀 {user.display_name} joined **Team {team_b_name}**!")
                else:
                    if len(team_b) < self.pumpkin_cog.TEAM_SIZE:
                        team_b.append(user)
                        join_log.append(f"💀 {user.display_name} joined **Team {team_b_name}**!")
                    else:
                        team_a.append(user) # Overflow to other team
                        join_log.append(f"🎃 {user.display_name} joined **Team {team_a_name}**!")
                
                # Update the lobby embed with new player lists
                time_left = int((self.view_timeout_time - datetime.now()).total_seconds())
                new_lobby_embed = build_lobby_embed(time_left)
                await interaction.edit_original_message(embed=new_lobby_embed)

        lobby_view = LobbyView(timeout=lobby_time, pumpkin_cog=self) # Pass self (the cog)
        lobby_msg = await context.send(embed=lobby_embed, view=lobby_view)

        # Timer loop to update countdown
        for i in range(lobby_time - 5, 0, -5): # Start 5 seconds in
            await asyncio.sleep(5)
            time_left = max(0, i)
            new_lobby_embed = build_lobby_embed(time_left)
            try:
                await lobby_msg.edit(embed=new_lobby_embed)
            except disnake.HTTPException:
                return # Message was deleted
        
        await asyncio.sleep(5) # Wait for the last 5 seconds
        
        try:
            await lobby_msg.edit(content="Lobby closed!", view=None)
        except disnake.HTTPException:
            pass # Message deleted, fine

        # 3. Check for enough players *before* ready check
        all_human_players_list = team_a + team_b # List of user objects
        all_human_players_ids = {u.id for u in all_human_players_list} # Set of user IDs
        num_human_players = len(all_human_players_list)
        
        if num_human_players < 1: # Min 1 player
            await context.send("Not enough players for a fight. Try again!")
            return

        if join_log:
            await context.send("\n".join(join_log), delete_after=10)

        # --- 4. NEW: Ready Check Phase (REWRITTEN) ---
        rules_text = (
            f"Each round you have **15 seconds** to allocate **{self.ACTION_POINTS_PER_ROUND} Action Points** to charge specific action types:\n\n"
            f"{self.ACTION_CHARGE_EMOJI} **Attacking**: Makes your hits more powerful but exposes you to more damage.\n"
            f"{self.ACTION_BLOCK_EMOJI} **Blocking**: Reduces damage taken but gets weaker every round.\n"
            f"{self.ACTION_DODGE_EMOJI} **Dodging**: Adds the chance of reflecting half of the damage to your opponent, but isn't guaranteed.\n\n"
            "You throw pumpkins at the opposing team. You'll *try* to hit your direct opponent, but there's a chance you'll hit their neighbour or miss completely!\n\n"
            "You're out of the game when your HP hits 0. (You start with HP equal to your strength).\n\n"
            "Overrun the opposing team to win!\n\n"
            "**Press ✅ when you're ready to start!**"
        )
        
        rules_embed = disnake.Embed(
            title="🎃 How to Fight 🎃",
            description=rules_text,
            color=disnake.Color.orange()
        )
        
        required_reactions = math.ceil(num_human_players * 0.55)
        rules_embed.set_footer(text=f"The fight will start when {required_reactions} (55%) of players are ready. (60s timer)")
        
        ready_msg = await context.send(embed=rules_embed)
        await ready_msg.add_reaction("✅")
        
        ready_players = set()
        
        def check_ready(reaction: disnake.Reaction, user: disnake.User):
            """Check if the reaction is valid for the ready-up."""
            return (
                user.id in all_human_players_ids and   # Is a human player in this game
                user.id != self.bot.user.id and       # Is not the bot
                str(reaction.emoji) == "✅" and         # Is the correct emoji
                reaction.message.id == ready_msg.id   # Is on the correct message
            )

        end_time = datetime.now() + timedelta(seconds=60)
        while datetime.now() < end_time:
            # Calculate remaining time
            timeout_left = (end_time - datetime.now()).total_seconds()
            if timeout_left <= 0:
                break # Time's up
            
            try:
                # Wait for a valid reaction
                reaction, user = await self.bot.wait_for(
                    'reaction_add', 
                    check=check_ready, 
                    timeout=timeout_left
                )
                
                # Add player to set and check if we have enough
                ready_players.add(user.id)
                if len(ready_players) >= required_reactions:
                    break # We have enough, start the game early
                    
            except asyncio.TimeoutError:
                # This will be caught on the next loop iteration
                break 
        
        # --- Check results of ready-up ---
        if len(ready_players) >= required_reactions:
            await context.send(f"**{len(ready_players)}/{num_human_players}** players are ready! The fight begins!")
            await ready_msg.delete()
        else:
            await context.send(f"Not enough players were ready (**{len(ready_players)}/{required_reactions}**). The fight is cancelled.")
            await ready_msg.delete()
            return # Exit the command

        # --- 5. Finalize Teams & Add Bot ---
        team_a_data = []
        team_b_data = []

        for user in team_a:
            strength = await self._get_user_strength(user.id)
            balance = await self.get_pumpkin_balance(user.id)
            renown_score = await self._get_renown_score(user.id) # NEW
            renown_title = self._get_renown_title(renown_score) # NEW
            
            team_a_data.append({
                "id": user.id, "hp": strength, "max_hp": strength, "action": None, 
                "obj": user, "strength": strength, "balance": balance,
                "renown_score": renown_score, "renown_title": renown_title, # NEW
                "splats": 0, "dodges": 0, "damage_dealt": 0, "fizzles": 0, # NEW: Stats
                "splatted": False, "is_last_stand": False
            })

        for user in team_b:
            strength = await self._get_user_strength(user.id)
            balance = await self.get_pumpkin_balance(user.id)
            renown_score = await self._get_renown_score(user.id) # NEW
            renown_title = self._get_renown_title(renown_score) # NEW
            
            team_b_data.append({
                "id": user.id, "hp": strength, "max_hp": strength, "action": None, 
                "obj": user, "strength": strength, "balance": balance,
                "renown_score": renown_score, "renown_title": renown_title, # NEW
                "splats": 0, "dodges": 0, "damage_dealt": 0, "fizzles": 0, # NEW: Stats
                "splatted": False, "is_last_stand": False
            })

        bot_strength = self.BASE_STRENGTH
        bot_renown_score = 0 # NEW
        bot_renown_title = self._get_renown_title(bot_renown_score) # NEW
        bot_data = {
            "id": self.BOT_USER_ID, "hp": bot_strength, "max_hp": bot_strength, 
            "action": None, "obj": self.bot.user, "strength": bot_strength, "balance": 999999,
            "renown_score": bot_renown_score, "renown_title": bot_renown_title, # NEW
            "splats": 0, "dodges": 0, "damage_dealt": 0, "fizzles": 0, # NEW: Stats
            "splatted": False, "is_last_stand": False
        }
        
        if len(team_a_data) > len(team_b_data):
            team_b_data.append(bot_data)
            await context.send(f"{self.bot.user.display_name} joins **Team {team_b_name}** to balance the scales!")
        elif len(team_b_data) > len(team_a_data):
            team_a_data.append(bot_data)
            await context.send(f"{self.bot.user.display_name} joins **Team {team_a_name}** to balance the scales!")
            
        splatted_role = await self._get_temporary_role(context.guild)
        
        # --- 6. Main Game Loop ---
        game_message = None # This will be our one embed
        round_num = 1
        log_list = ["The match begins!"] # Initialize log
        total_pumpkin_spent_this_match = 0 # NEW: Reward pot
        
        # --- NEW: Create persistent Action Button View ---
        class ActionView(disnake.ui.View):
            def __init__(self, timeout, pumpkin_cog): # Pass cog in
                super().__init__(timeout=timeout)
                self.pumpkin_cog = pumpkin_cog # Store cog
                self.player_actions = defaultdict(lambda: {"attack": 0, "block": 0, "dodge": 0, "ap_spent": 0})
                self.gourds_alive = []
                self.reapers_alive = []
                self.end_time = datetime.now() + timedelta(seconds=timeout)

            async def update_embed(self, interaction: disnake.MessageInteraction, team_a, team_b, team_a_name, team_b_name, round_num, log_list):
                """Dynamically updates the embed with AP info."""
                time_left = (self.end_time - datetime.now()).total_seconds()
                if time_left < 0: time_left = 0
                
                ap_track_lines = []
                for p_update in self.gourds_alive + self.reapers_alive:
                        if p_update["id"] != self.pumpkin_cog.BOT_USER_ID:
                            cur_actions = self.player_actions[p_update["id"]]
                            ap_track_lines.append(f"{p_update['obj'].display_name}: 💥{cur_actions['attack']} 🛡️{cur_actions['block']} 💨{cur_actions['dodge']} ({cur_actions['ap_spent']}/{self.pumpkin_cog.ACTION_POINTS_PER_ROUND} AP)")
                
                action_log_str = '\n'.join(ap_track_lines)
                if not action_log_str:
                    action_log_str = "No actions yet."
                
                # --- SYNTAX FIX ---
                action_text = f"""**Spend {self.pumpkin_cog.ACTION_POINTS_PER_ROUND} Action Points! ({int(time_left)}s left)**

{self.pumpkin_cog.ACTION_CHARGE_EMOJI} **Attack (1 AP)**: Spend {self.pumpkin_cog.ATTACK_COST_PER_AP}kg pumpkin...
{self.pumpkin_cog.ACTION_BLOCK_EMOJI} **Block (1 AP)**: Charge 1 block point...
{self.pumpkin_cog.ACTION_DODGE_EMOJI} **Dodge (1 AP)**: Charge 1 dodge point...

**Action Log:**
`{action_log_str}`"""
                
                status_embed = self.pumpkin_cog._build_tournament_embed(team_a, team_b, team_a_name, team_b_name, round_num, action_text=action_text, log_list=log_list)
                
                try:
                    # Use the interaction to edit, not the message
                    await interaction.edit_original_message(embed=status_embed)
                except disnake.HTTPException:
                    pass # Ignore edit conflicts or rate limits

            async def handle_click(self, interaction: disnake.MessageInteraction, emoji: str):
                user = interaction.user
                
                # Find the player in our game
                player = None
                for p in self.gourds_alive + self.reapers_alive:
                    if p["id"] == user.id:
                        player = p
                        break
                
                if not player:
                    await interaction.response.send_message("You're not in this fight or you've been splatted!", ephemeral=True)
                    return

                actions = self.player_actions[user.id]
                
                if actions["ap_spent"] >= self.pumpkin_cog.ACTION_POINTS_PER_ROUND:
                    await interaction.response.send_message("You are out of Action Points for this round!", ephemeral=True)
                    return
                
                action_taken = False
                if emoji == self.pumpkin_cog.ACTION_CHARGE_EMOJI:
                    # --- RAMPING COST LOGIC ---
                    next_attack_ap = actions["attack"] + 1
                    cost_to_attack = self.pumpkin_cog._calculate_ramping_attack_cost(next_attack_ap)
                    if player["balance"] >= cost_to_attack:
                        actions["attack"] += 1
                        actions["ap_spent"] += 1
                        action_taken = True
                    else:
                        await interaction.response.send_message(f"You don't have enough pumpkins! You need {cost_to_attack}kg to attack {next_attack_ap} times.", ephemeral=True)
                
                elif emoji == self.pumpkin_cog.ACTION_BLOCK_EMOJI:
                    if actions["block"] < 5: 
                        actions["block"] += 1
                        actions["ap_spent"] += 1
                        action_taken = True
                    else:
                         await interaction.response.send_message("You can't charge Block more than 5 times!", ephemeral=True)
                
                elif emoji == self.pumpkin_cog.ACTION_DODGE_EMOJI:
                    if actions["dodge"] < 5: 
                        actions["dodge"] += 1
                        actions["ap_spent"] += 1
                        action_taken = True
                    else:
                        await interaction.response.send_message("You can't charge Dodge more than 5 times!", ephemeral=True)
                
                if action_taken:
                    # Acknowledge the click, then update embed
                    await interaction.response.defer()
                    
                    # Corrected call signature:
                    await self.update_embed(interaction, self.gourds_alive, self.reapers_alive, team_a_name, team_b_name, round_num, log_list)
            
            @disnake.ui.button(label="Attack", style=disnake.ButtonStyle.danger, emoji="💥", custom_id="atk_button")
            async def attack_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
                await self.handle_click(interaction, self.pumpkin_cog.ACTION_CHARGE_EMOJI)

            @disnake.ui.button(label="Block", style=disnake.ButtonStyle.primary, emoji="🛡️", custom_id="blk_button")
            async def block_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
                await self.handle_click(interaction, self.pumpkin_cog.ACTION_BLOCK_EMOJI)
            
            @disnake.ui.button(label="Dodge", style=disnake.ButtonStyle.success, emoji="💨", custom_id="ddg_button")
            async def dodge_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
                await self.handle_click(interaction, self.pumpkin_cog.ACTION_DODGE_EMOJI)

        
        while True:
            # --- (PRE-ROUND) ---
            # Check for win condition
            gourds_alive = [p for p in team_a_data if p["hp"] > 0]
            reapers_alive = [p for p in team_b_data if p["hp"] > 0]
            
            # --- NEW: Check for Last Stand ---
            if len(gourds_alive) == 1:
                gourds_alive[0]["is_last_stand"] = True # Mark player as being in last stand
            if len(reapers_alive) == 1:
                reapers_alive[0]["is_last_stand"] = True # Mark player as being in last stand
            
            if not gourds_alive:
                final_embed = self._build_tournament_embed(gourds_alive, reapers_alive, team_a_name, team_b_name, round_num, log_list=log_list)
                final_embed.title = f"💀 Team {team_b_name} Wins! 💀"
                final_embed.description = f"Team {team_a_name} has been completely splatted!"
                await game_message.edit(embed=final_embed, content=None, view=None)
                break # Reapers win
            if not reapers_alive:
                final_embed = self._build_tournament_embed(gourds_alive, reapers_alive, team_a_name, team_b_name, round_num, log_list=log_list)
                final_embed.title = f"🎃 Team {team_a_name} Wins! 🎃"
                final_embed.description = f"Team {team_b_name} has been completely splatted!"
                await game_message.edit(embed=final_embed, content=None, view=None)
                break # Gourds win
            
            # --- Out of Pumpkin Check ---
            all_out_of_pumpkins = True
            for p in gourds_alive + reapers_alive:
                if p["id"] == self.BOT_USER_ID:
                    continue # Bot has infinite
                if p["id"] != self.BOT_USER_ID: 
                    p["balance"] = await self.get_pumpkin_balance(p["id"])
                if p["balance"] > 0:
                    all_out_of_pumpkins = False
                    break
            
            if all_out_of_pumpkins:
                gourd_total_hp = sum(p["hp"] for p in gourds_alive)
                reaper_total_hp = sum(p["hp"] for p in reapers_alive)

                win_embed = self._build_tournament_embed(gourds_alive, reapers_alive, team_a_name, team_b_name, round_num, log_list=log_list)
                win_embed.title = "🎃 Fight Over! Everyone's Out of Ammo! 🎃"
                win_embed.add_field(name=f"Team {team_a_name} Total HP", value=str(gourd_total_hp))
                win_embed.add_field(name=f"Team {team_b_name} Total HP", value=str(reaper_total_hp))

                if gourd_total_hp > reaper_total_hp:
                    win_embed.description = f"**Team {team_a_name} wins** by having more HP remaining!"
                elif reaper_total_hp > gourd_total_hp:
                    win_embed.description = f"**Team {team_b_name} wins** by having more HP remaining!"
                else:
                    win_embed.description = "It's a draw! Both teams have the same HP!"
                
                await game_message.edit(embed=win_embed, content=None, view=None)
                break # End game

                
            # --- 7. Build and send ACTION embed ---
            action_view = ActionView(timeout=15.0, pumpkin_cog=self) # Pass cog
            action_view.gourds_alive = gourds_alive
            action_view.reapers_alive = reapers_alive
            
            action_text = (
                f"**Spend {self.ACTION_POINTS_PER_ROUND} Action Points! (15s left)**\n\n"
                f"{self.ACTION_CHARGE_EMOJI} **Attack (1 AP)**: Spend {self.ATTACK_COST_PER_AP}kg pumpkin...\n"
                f"{self.ACTION_BLOCK_EMOJI} **Block (1 AP)**: Charge 1 block point...\n"
                f"{self.ACTION_DODGE_EMOJI} **Dodge (1 AP)**: Charge 1 dodge point...\n\n"
                f"**Action Log:**\n`No actions yet.`"
            )
            
            status_embed = self._build_tournament_embed(gourds_alive, reapers_alive, team_a_name, team_b_name, round_num, action_text=action_text, log_list=log_list)
            
            if game_message:
                game_message = await game_message.edit(embed=status_embed, content=None, view=action_view)
            else:
                game_message = await context.send(embed=status_embed, view=action_view)
            
            # --- 8. Action Phase (Real-time click collection and embed update) ---
            
            # Update player balances
            for p in gourds_alive + reapers_alive:
                if p["id"] != self.BOT_USER_ID:
                    p["balance"] = await self.get_pumpkin_balance(p["id"])

            end_time = datetime.now() + timedelta(seconds=15)
            
            # This loop now just updates the timer
            while datetime.now() < end_time:
                time_left = (end_time - datetime.now()).total_seconds()
                if time_left <= 0: break
                
                # Update embed timer
                ap_track_lines = []
                for p_update in gourds_alive + reapers_alive:
                        if p_update["id"] != self.BOT_USER_ID:
                            cur_actions = action_view.player_actions[p_update["id"]]
                            ap_track_lines.append(f"{p_update['obj'].display_name}: 💥{cur_actions['attack']} 🛡️{cur_actions['block']} 💨{cur_actions['dodge']} ({cur_actions['ap_spent']}/{self.ACTION_POINTS_PER_ROUND} AP)")
                
                action_log_str = '\n'.join(ap_track_lines)
                if not action_log_str:
                    action_log_str = "No actions yet."
                
                # --- SYNTAX FIX ---
                action_text = f"""**Spend {self.ACTION_POINTS_PER_ROUND} Action Points! ({int(time_left)}s left)**

{self.ACTION_CHARGE_EMOJI} **Attack (1 AP)**: Spend {self.ATTACK_COST_PER_AP}kg pumpkin...
{self.ACTION_BLOCK_EMOJI} **Block (1 AP)**: Charge 1 block point...
{self.ACTION_DODGE_EMOJI} **Dodge (1 AP)**: Charge 1 dodge point...

**Action Log:**
`{action_log_str}`"""

                status_embed = self._build_tournament_embed(gourds_alive, reapers_alive, team_a_name, team_b_name, round_num, action_text=action_text, log_list=log_list)
                try:
                    await game_message.edit(embed=status_embed)
                except disnake.HTTPException:
                    pass
                
                await asyncio.sleep(1) # Update timer every second
            
            # --- End of Action Phase ---
            player_actions = action_view.player_actions # Get final actions
            
            # --- 9. Resolution Phase ---
            log_list = [] # Reset log for this round
            
            # --- 9a. Bot AI ---
            for p in gourds_alive + reapers_alive:
                if p["id"] == self.BOT_USER_ID:
                    player_actions[self.BOT_USER_ID] = self._bot_choose_action(p)
            
            # --- 9b. REWRITTEN: Resolve Fights with new targeting ---
            
            # We must iterate over the *original* data lists to preserve index
            num_pairs = max(len(team_a_data), len(team_b_data))
            
            # Store targets to resolve simultaneously
            attacks_to_resolve = [] # (attacker, defender, attacker_actions, defender_actions, attacker_team_data, defender_team_data)

            # --- 1. Select all targets first ---
            for i in range(num_pairs):
                # --- Gourd Attack ---
                if i < len(team_a_data):
                    gourd_p = team_a_data[i]
                    if gourd_p["hp"] > 0: # Attacker must be alive
                        target_reaper, offset, log_msg = self._select_target(i, team_b_data, reapers_alive)
                        log_list.append(f"🎃 {gourd_p['obj'].display_name} {log_msg}")
                        
                        if target_reaper: # Can be None if it was a miss
                            g_actions = player_actions[gourd_p["id"]]
                            r_def_actions = player_actions[target_reaper["id"]]
                            attacks_to_resolve.append((gourd_p, target_reaper, g_actions, r_def_actions, team_a_data, team_b_data, round_num))

                # --- Reaper Attack ---
                if i < len(team_b_data):
                    reaper_p = team_b_data[i]
                    if reaper_p["hp"] > 0: # Attacker must be alive
                        target_gourd, offset, log_msg = self._select_target(i, team_a_data, gourds_alive)
                        log_list.append(f"💀 {reaper_p['obj'].display_name} {log_msg}")
                        
                        if target_gourd: # Can be None if it was a miss
                            r_actions = player_actions[reaper_p["id"]]
                            g_def_actions = player_actions[target_gourd["id"]]
                            attacks_to_resolve.append((reaper_p, target_gourd, r_actions, g_def_actions, team_b_data, team_a_data, round_num))

            # --- 2. Resolve all attacks ---
            # Shuffle to make attack order random
            random.shuffle(attacks_to_resolve)
            
            for (attacker, defender, atk_actions, def_actions, atk_team, def_team, r_num) in attacks_to_resolve:
                # Check if attacker or defender was splatted *during* this round's
                # simultaneous resolution before their attack goes off.
                if attacker["hp"] <= 0:
                    log_list.append(f"🦴 {attacker['obj'].display_name}'s attack fizzles (splatted)!")
                    continue
                if defender["hp"] <= 0:
                    # Defender is already dead, attack auto-hits corpse, no effect
                    log_list.append(f"🦴 {attacker['obj'].display_name} attacks {defender['obj'].display_name}'s corpse!")
                    continue

                total_pumpkin_spent_this_match = await self._resolve_1v1_attack(
                    attacker, defender, atk_actions, def_actions, 
                    atk_team, def_team, # Pass in the new team data
                    log_list, match_id, total_pumpkin_spent_this_match, r_num
                )

            # --- 10. Report & Clean up Splatted ---
            splatted_this_round = []
            
            # Check *living* lists from *before* the round
            for p in gourds_alive + reapers_alive:
                # if p["hp"] <= 0: # This is the old logic
                # NEW logic: Check if they were alive, and now are dead
                if p["hp"] <= 0 and p["splatted"] == False: # They were alive, but now have <= 0 hp
                    # This logic is flawed. "splatted" is set *during* resolution.
                    # We need to check the list of players who *were* alive
                    # but are *no longer* in the *new* alive list.
                    
                    # Simpler: check all players, if hp <= 0 and we haven't logged their splat
                    pass # This logic is handled inside _resolve_1v1_attack now
            
            # Find all players who were splatted *this match* (hp <= 0)
            # and haven't had the role applied yet
            
            # This is complex. Let's simplify:
            # Check all players in the main data lists.
            # If their HP is <= 0 AND we haven't splatted them yet, do it.
            
            splat_log_names = []
            for p_data in team_a_data + team_b_data:
                if p_data["hp"] <= 0 and p_data.get("splat_role_applied", False) == False:
                    splat_log_names.append(p_data["obj"].display_name)
                    p_data["splat_role_applied"] = True # Mark as role applied
                    
                    if p_data["id"] != self.BOT_USER_ID:
                        member = p_data["obj"]
                        if isinstance(member, disnake.Member):
                             await self._apply_splat_role(member, splatted_role, context.channel)
                        else:
                            try:
                                guild = context.guild
                                if guild:
                                    fetched_member = await guild.fetch_member(member.id)
                                    if fetched_member:
                                        await self._apply_splat_role(fetched_member, splatted_role, context.channel)
                            except Exception:
                                pass # Failed to fetch, oh well

            if splat_log_names:
                log_list.append(f"💀 **Splatted this round:** {', '.join(splat_log_names)}")


            # --- 11. Show Results Embed ---
            # Re-get alive players *after* resolution
            gourds_alive_after = [p for p in team_a_data if p["hp"] > 0]
            reapers_alive_after = [p for p in team_b_data if p["hp"] > 0]
            
            # Build the RESULTS embed
            # Show results log in context of the *next* round's start
            results_embed = self._build_tournament_embed(gourds_alive_after, reapers_alive_after, team_a_name, team_b_name, round_num + 1, action_text=None, log_list=log_list) 
            await game_message.edit(embed=results_embed, view=None) # Remove buttons

            round_num += 1
            await asyncio.sleep(7) # Pause to read results
                
        # 12. (Outside loop) Reward Winners & RENOWN
        gourds_alive = [p for p in team_a_data if p["hp"] > 0]
        reapers_alive = [p for p in team_b_data if p["hp"] > 0]
        
        # Get *all* players from the original teams for reward distribution
        all_team_a_humans = [p for p in team_a_data if p["id"] != self.BOT_USER_ID]
        all_team_b_humans = [p for p in team_b_data if p["id"] != self.BOT_USER_ID]
        all_human_players_in_match = all_team_a_humans + all_team_b_humans
        
        winning_team_players = [] # Survivors
        winning_team_all = []
        losing_team_all = []
        
        if gourds_alive and not reapers_alive: # Gourds won
            winning_team_players = [p for p in gourds_alive if p["id"] != self.BOT_USER_ID]
            winning_team_all = all_team_a_humans
            losing_team_all = all_team_b_humans
            await context.send(f"**Team {team_a_name} is victorious!**")
        elif reapers_alive and not gourds_alive: # Reapers won
            winning_team_players = [p for p in reapers_alive if p["id"] != self.BOT_USER_ID]
            winning_team_all = all_team_b_humans
            losing_team_all = all_team_a_humans
            await context.send(f"**Team {team_b_name} is victorious!**")
        else:
            # This handles draws (like out of ammo)
            losing_team_all = all_human_players_in_match # Everyone is a "loser" in a draw
            await context.send("The match is a draw!")

        reward_msg = ""
        
        # --- NEW: Pumpkin Reward system ---
        if winning_team_players:
            # Winners get 100% of the pot, divided by survivors
            winner_reward = 0
            if len(winning_team_players) > 0:
                winner_reward = round(total_pumpkin_spent_this_match / len(winning_team_players))
            
            if winner_reward > 0:
                reward_msg += f"**Winning team survivors ({team_a_name if gourds_alive else team_b_name}) rewarded!**\n"
                for player in winning_team_players:
                    user_obj = player["obj"]
                    await self._add_pumpkin(user_obj.id, winner_reward, f"tournament_win_pot_{match_id}")
                    reward_msg += f"{user_obj.mention} gains **{winner_reward}kg** of pumpkin!\n"

        if losing_team_all: # Changed from all_losers
            # Losers get 50% of the pot, divided by *all* original members
            loser_reward = 0
            if len(losing_team_all) > 0:
                loser_reward = round((total_pumpkin_spent_this_match / 2) / len(losing_team_all))
                
            if loser_reward > 0:
                reward_msg += f"\n**Losing team ({team_b_name if gourds_alive else team_a_name}) consolation prize!**\n"
                for player in losing_team_all:
                    user_obj = player["obj"]
                    await self._add_pumpkin(user_obj.id, loser_reward, f"tournament_loss_pot_{match_id}")
                    reward_msg += f"{user_obj.mention} gains **{loser_reward}kg** of pumpkin.\n"

        if reward_msg:
            await context.send(reward_msg)
        
        # --- NEW: RENOWN CALCULATION ---
        renown_report_lines = ["**--- 🎃 Ranks Update 🎃 ---**"]
        
        for player in all_human_players_in_match:
            user_id = player["id"]
            user_obj = player["obj"]
            renown_change = 0
            renown_reasons = []
            
            # Base stats for DB log
            match_stats = {
                "splats": player["splats"],
                "splatted": 1 if player["splatted"] else 0,
                "dodges": player["dodges"],
                "damage_dealt": player["damage_dealt"],
                "fizzles": player["fizzles"],
                "last_stands": 1 if player["is_last_stand"] else 0
            }

            # 1. Win/Loss
            if player in winning_team_all:
                renown_change += self.RENOWN_AWARDS["win"]
                renown_reasons.append(f"+{self.RENOWN_AWARDS['win']} (Win)")
                # Log win for stats
                await self._add_renown(user_id, 0, "win", match_id, match_stats)
            elif player in losing_team_all:
                renown_change += self.RENOWN_AWARDS["loss"]
                renown_reasons.append(f"{self.RENOWN_AWARDS['loss']} (Loss)")
                # Log loss for stats
                await self._add_renown(user_id, 0, "loss", match_id, match_stats)
            
            # 2. Survivor
            if player in winning_team_players:
                renown_change += self.RENOWN_AWARDS["survivor"]
                renown_reasons.append(f"+{self.RENOWN_AWARDS['survivor']} (Survivor)")
            
            # 3. Splats
            if player["splats"] > 0:
                points = player["splats"] * self.RENOWN_AWARDS["splat"]
                renown_change += points
                renown_reasons.append(f"+{points} ({player['splats']} Splats)")

            # 4. Splatted
            if player["splatted"]:
                renown_change += self.RENOWN_AWARDS["splatted"]
                renown_reasons.append(f"{self.RENOWN_AWARDS['splatted']} (Splatted)")
                
            # 5. Dodges
            if player["dodges"] > 0:
                points = player["dodges"] * self.RENOWN_AWARDS["dodge"]
                renown_change += points
                renown_reasons.append(f"+{points} ({player['dodges']} Dodges)")
            
            # 6. Damage Dealt (per 50kg)
            damage_bonus_times = player["damage_dealt"] // 50
            if damage_bonus_times > 0:
                points = damage_bonus_times * self.RENOWN_AWARDS["damage_50kg"]
                renown_change += points
                renown_reasons.append(f"+{points} ({player['damage_dealt']}kg Dealt)")

            # 7. Last Stand
            if player["is_last_stand"]:
                renown_change += self.RENOWN_AWARDS["last_stand"]
                renown_reasons.append(f"+{self.RENOWN_AWARDS['last_stand']} (Last Stand)")

            # 8. Fizzles
            if player["fizzles"] > 0:
                points = player["fizzles"] * self.RENOWN_AWARDS["fizzle"]
                renown_change += points
                renown_reasons.append(f"{points} ({player['fizzles']} Fizzles)")
            
            # Log the final change
            await self._add_renown(user_id, renown_change, "match_total", match_id)
            
            # Add to report
            sign = "+" if renown_change >= 0 else ""
            renown_report_lines.append(f"{user_obj.mention}: **{sign}{renown_change} Reputation** ({', '.join(renown_reasons)})")

        if len(renown_report_lines) > 1:
            await context.send("\n".join(renown_report_lines))


# --- Setup Function ---
def setup(bot):
    bot.add_cog(Pumpkin(bot))