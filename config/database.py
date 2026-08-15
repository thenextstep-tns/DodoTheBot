"""
MongoDB connection and collection handles. The connection string comes from
``config.json`` via ``config.secrets``.
"""

from pymongo import MongoClient

from config.secrets import DATABASE_NAME, MONGO_URI

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# --- Collections ---
collection = db["Dummies"]
dailies = db["Dailies"]
wallets = db["Wallets"]
catcollection = db["Cats"]
dogcollection = db["Dogs"]
waifucollection = db["Waifu"]
petownerscollection = db["Petowners"]
dodoroll = db["Rolls"]
parses = db["Parses"]
duels = db["Duels"]
commands_use = db["Commands Usage"]
messages = db["Messages with Channels"]
pps = db["PPs"]
items = db["Items"]
itemtypes = db["ItemTypes"]
itemsources = db["ItemSourcing"]
itemqualities = db["ItemQualities"]
base_modifiers = db["BaseModifiers"]
goodies_bag = db["GoodiesBag"]
fishing_results = db["FishingResults"]
sweetrolls = db["Sweetrolls"]
races = db["Races"]
mice = db["Mice"]
votes = db["Votes"]
gym_sessions = db["GymSessions"]
left_roles = db["LeftRoles"]
mouse_classes = db["MouseClasses"]
user_mice = db["UserMice"]
user_power = db["ThrowingPower"]
throws = db["Throws"]
waifus = db["Waifus"]
memory = db["Memories"]
cardinals_col = db["Cardinals"]
orders_col = db["Orders"]
rumours_col = db["Rumours"]
votes_col = db["Votes"]
state_col = db["Conclave_state"]
favor_col = db["Favor_tokens"]
pin_fails = db["Pin_fails"]
pumpkins = db["Pumpkins"]
pull = db["Pull"]
pumpkinstats = db["Pumpkinstats"]
pumpkinlog = db["Pumpkinlog"]
renown = db["Pumpkinrep"]
raid_templates = db["RaidTemplates"]
active_raids = db["ActiveRaids"]
botServerRoles = db["BotServerRoles"]
botServerCategories = db["BotServerCategories"]
logs = db["Logs"]
raid_setups = db["RaidSetups"]
gilane_scores = db["GilaneScores"]
quote_scores = db["QuoteScores"]
# Persistent state for in-progress interactive flows (see helpers/state_machine.py).
active_states = db["ActiveStates"]
# Multiserver command/cog visibility (see helpers/visibility.py & the control panel).
command_visibility = db["CommandVisibility"]  # {guild_id, command, level}
cog_guild_state = db["CogGuildState"]         # {guild_id, cog, enabled}
feature_state = db["FeatureState"]            # {guild_id, feature, enabled} — passive listeners
guild_admins = db["GuildAdmins"]              # {guild_id, user_ids: [...]}
command_sync_hashes = db["CommandSyncHashes"] # {guild_id, hash} — startup resync guard
lang_overrides = db["LangOverrides"]          # {key, value} — editable user-facing strings
# Display names for ids the gateway cache can't answer for (members who left,
# deleted channels). Filled in as the panel resolves them — see helpers/names.py.
entity_names = db["EntityNames"]              # {_id: "user:123", name, updated_at}
# "When X happens, post this there" rules built on the panel (see helpers/events.py).
event_rules = db["EventRules"]                # {guild_id, event, channel_id, message, ...}
# Who may open the control panel for a guild, and how much of it they see.
panel_access = db["PanelAccess"]              # {guild_id, kind: role|user, target_id, scope}
# Every configuration change made from the panel: who, when, old -> new.
config_audit = db["ConfigAudit"]              # {guild_id, actor_id, kind, target, old, new, at}
# Role rules built on the panel ("tribes") and the membership each sweep produces.
tribes = db["Tribes"]                         # {guild_id, name, condition, role_ids, ...}
tribe_members = db["TribeMembers"]            # {guild_id, tribe_id, user_id, rank, position}
# Trial ranking: clears/achievements -> points -> rank role (helpers/trial_ranks.py).
trial_ranks = db["TrialRanks"]                # {_id: guild_id, points, ranks, enabled}
trial_standings = db["TrialStandings"]        # {guild_id, user_id, score, rank}
# Who has opted in to automated ranking, and how far the ask got with everyone
# else — the automation only ever touches an "enrolled" row.
trial_enrollment = db["TrialEnrollment"]      # {guild_id, user_id, state, name, source, *_at}
trial_rank_images = db["TrialRankImages"]     # {guild_id, role_id, data, content_type}
# "I'd join a prog for one of those" — one row per person, latest press wins.
trial_interest = db["TrialInterest"]          # {guild_id, user_id, name, role_ids, at}
command_params = db["CommandParams"]          # {guild_id, key, value} — per-server tunables
