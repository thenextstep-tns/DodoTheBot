import os
import sys
import json
import math
import disnake
from disnake.ext import commands
import pymongo

# --- Configuration Loading ---
def load_config():
    """
    Loads configuration from both config.json and config_py.py.
    This simplified version is only for the cog, but the cog
    still needs access to the config_py object for DB and roles.
    """
    if not os.path.isfile("config.json"):
        pass 
    
    if not os.path.isfile("config_py.py"):
        sys.exit("'config_py.py' not found! Please add it and try again.")
    
    import config_py
    
    if isinstance(config_py.trial_ping_roles, dict):
        config_py.trial_ping_roles_list = [role_id for role_id in config_py.trial_ping_roles.values()]
    else:
        sys.exit("'trial_ping_roles' in config_py.py must be a dictionary of trial names to role IDs!")

    return {}, config_py 

# --- Paginator View ---
class LeechPaginator(disnake.ui.View):
    """
    A simple paginator view for navigating through embeds.
    """
    def __init__(self, embeds):
        super().__init__(timeout=120) 
        self.embeds = embeds
        self.current = 0
        self.update_button_states()

    def update_button_states(self):
        self.children[0].disabled = self.current == 0
        self.children[1].disabled = self.current == len(self.embeds) - 1

    @disnake.ui.button(label="Previous", style=disnake.ButtonStyle.primary)
    async def previous(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if self.current > 0:
            self.current -= 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()

    @disnake.ui.button(label="Next", style=disnake.ButtonStyle.primary)
    async def next(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if self.current < len(self.embeds) - 1:
            self.current += 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()

# --- Leech Calculation Cog ---
class LeechCalc(commands.Cog, name="Leech Calculation"):
    def __init__(self, bot):
        self.bot = bot
        _, self.config_py = load_config() 

        self.SIGNUP_WEIGHT = 10.0      
        self.PING_WEIGHT = 2.0         
        self.ACTIVITY_WEIGHT = 5.0     
        self.PING_DAMPER_EXPONENT = 0.5 

        self.DODO_USER_ID = 824171812518494238 

    @commands.command()
    @commands.has_permissions(manage_messages=True) 
    async def leech(self, ctx):
        """
        Calculates and displays a leaderboard based on a Weighted Contribution Score (WCS).
        This formula rewards signups and overall activity, and applies a stronger penalty
        for pings when signup activity is low. Higher WCS is better.
        Custom signup parsing rules are applied (no user mentions for signups).
        Dodo (824171812518494238) is excluded.
        """
        thinking_message = await ctx.send("`🧮` Calculating weighted contribution scores...")

        trial_roles = self.config_py.trial_ping_roles_list
        
        # --- MongoDB Aggregation Pipeline ---
        pipeline_base = [
            # Stage 0: Exclude messages from the specified user (Dodo)
            {
                "$match": {
                    "author": {"$ne": self.DODO_USER_ID}
                }
            },
            # Stage 1: Pre-process each message to extract author_id, check for trial pings, and calculate signup value.
            {
                "$project": {
                    "author_id": "$author", 
                    "is_trial_ping": {
                        "$gt": [
                            {"$size": {
                                "$setIntersection": [
                                    {"$map": {
                                        "input": {"$regexFindAll": {"input": "$message", "regex": r"<@&(\d+)>"}},
                                        "in": {"$toLong": {"$arrayElemAt": ["$$this.captures", 0]}}
                                    }},
                                    trial_roles
                                ]
                            }},
                            0
                        ]
                    },
                    "signup_value": {
                        "$cond": {
                            # Condition 1: Specific +keywords (e.g., +dd, +h, +healer) OR "+ " followed by text (1.0 point)
                            # User mentions are no longer counted as signups.
                            "if": { "$or": [
                                # Check for specific +keywords (case-insensitive)
                                { "$regexMatch": { 
                                    "input": "$message", 
                                    "regex": "\\+(?:dd\\d*|h|healer|tank|mt|ot|gh|group\\s*heal(?:er)?|kh|kite\\s*heal(?:er)?|oh|off-?\\s*heal(?:er)?|hl|healer\\s*left|hr|healer\\s*right)\\b", 
                                    "options": "i" 
                                } },
                                # Check for "+ " followed by any characters (e.g., "+ healer", "+ LF tank", "+ DPS")
                                { "$regexMatch": { "input": "$message", "regex": "^\\s*\\+\\s+.+", "options": "i" } } 
                            ]},
                            "then": 1.0,
                            "else": {
                                "$cond": {
                                    # Condition 2: Exactly "+" with optional surrounding whitespace (0.5 point)
                                    # This must be the *only* content if no other full signup condition is met.
                                    "if": { "$regexMatch": { "input": "$message", "regex": "^\\s*\\+\\s*$" } },
                                    "then": 0.5,
                                    "else": 0.0 # No recognized signup pattern
                                }
                            }
                        }
                    }
                }
            },
            # Stage 2: Group by user to sum up all their relevant stats.
            {
                "$group": {
                    "_id": "$author_id",
                    "total_messages": {"$sum": 1},
                    "trial_count": {"$sum": {"$cond": ["$is_trial_ping", 1, 0]}},
                    "signup_score": {"$sum": "$signup_value"}
                }
            },
            # Stage 3: Filter out users below a minimum message count.
            {"$match": {"total_messages": {"$gte": 5}}},
            # Stage 4: Filter out users with 0 pings AND 0 signups.
            {"$match": {"$or": [{"trial_count": {"$gt": 0}}, {"signup_score": {"$gt": 0}}]}}
        ]

        try:
            cursor = self.config_py.messages.aggregate(pipeline_base)
            results_raw = list(cursor)
        except pymongo.errors.OperationFailure as e:
            await thinking_message.edit(content=f"**An error occurred during aggregation:**\n```\n{e.details['errmsg']}\n```")
            return
        except Exception as e:
            await thinking_message.edit(content=f"A Python error occurred: {e}")
            return

        if not results_raw:
            return await thinking_message.edit(content="`🚫` No data found for any users meeting the criteria.")

        # --- Python-based Weighted Contribution Score (WCS) Calculation and Sorting ---
        processed_results = []
        for entry in results_raw:
            signup_score = entry['signup_score']
            trial_count = entry['trial_count']
            total_messages = entry['total_messages']

            safe_total_messages = total_messages if total_messages > 0 else 1 

            leech_amplification_factor = 1 + (trial_count / (signup_score + 1))

            ping_damper_denominator = (safe_total_messages + 1) ** self.PING_DAMPER_EXPONENT
            
            wcs = (self.SIGNUP_WEIGHT * signup_score) - \
                  (self.PING_WEIGHT * trial_count * leech_amplification_factor / ping_damper_denominator) + \
                  (self.ACTIVITY_WEIGHT * math.log(safe_total_messages + 1)) 

            processed_results.append({
                'user_id': entry['_id'],
                'total_messages': total_messages,
                'signups': signup_score,
                'trial_count': trial_count,
                'wcs': wcs, 
            })
        
        processed_results.sort(key=lambda x: x['wcs'], reverse=True)

        processed_results = processed_results[:100]

        # --- Build Embed Pages ---
        lines = []
        for rank, entry in enumerate(processed_results, start=1):
            user_display_name = f"Unknown User ({entry['user_id']})" 
            try:
                user_obj = await self.bot.fetch_user(entry['user_id'])
                user_display_name = str(user_obj) 
            except disnake.NotFound:
                user_display_name = f"User Left ({entry['user_id']})"
            except Exception as e:
                print(f"Error fetching user {entry['user_id']}: {e}")

            lines.append(
                f"**{rank}.** {user_display_name}\n"
                f"› **Contribution Score:** `{entry['wcs']:.2f}`\n" 
                f"› **Stats:** {entry['signups']:.1f} Signups / {entry['trial_count']} Pings / {entry['total_messages']} Msgs"
            )

        pages = []
        if not lines: 
            return await thinking_message.edit(content="`🚫` No data found for any users meeting the refined criteria.")

        for i in range(0, len(lines), 5): 
            embed = disnake.Embed(
                title="Server Contribution Leaderboard", 
                description="\n\n".join(lines[i:i+5]),
                color=0x2b2d31 
            )
            embed.set_footer(text=f"Page {i//5 + 1} of {math.ceil(len(lines) / 5)} | Higher score is better")
            pages.append(embed)

        if not pages:
            return await thinking_message.edit(content="`❌` Failed to generate leaderboard pages.")

        view = LeechPaginator(pages)
        await thinking_message.edit(content=None, embed=pages[0], view=view)

@commands.Cog.listener()
async def on_command_error(self, ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("`🔒` You do not have the required permissions to use this command.")
    else:
        print(f"An error occurred in command {ctx.command}: {error}")


#def setup(bot):
#    bot.add_cog(LeechCalc(bot))