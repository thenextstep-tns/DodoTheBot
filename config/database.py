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
emoji_reactions = db["EmojiReactions"]   # {guild_id, emoji, cls, text, stats} - per-server overrides
reaction_lines = db["ReactionLines"]      # {emoji, cls, text, stats, written} - the base library
scrap_roster = db["ScrapRoster"]          # {owner, idents} - the cats that fight for you
left_roles = db["LeftRoles"]
mouse_classes = db["MouseClasses"]
user_mice = db["UserMice"]
user_power = db["ThrowingPower"]
throws = db["Throws"]
waifus = db["Waifus"]
memory = db["Memories"]
chat_triggers = db["ChatTriggers"]
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
# Named snapshots of a whole ruleset, so a rebalance can be tried and put back.
trial_presets = db["TrialPresets"]            # {guild_id, name, points, ranks, trials}
# Periodic health samples behind the dashboard status board (helpers/health.py).
bot_health = db["BotHealth"]                  # {at, status, latency_ms, guilds, members}
# World-record holders: a per-person bonus on top of the role-derived score.
trial_wr = db["TrialWorldRecords"]           # {guild_id, user_id, name, current, former}
# Capability links (public leaderboard, later per-recipient). Hash only.
share_tokens = db["ShareTokens"]              # {guild_id, kind, token_hash, expires_at}
command_params = db["CommandParams"]          # {guild_id, key, value} — per-server tunables

# --------------------------------------------------------------------------- #
#  Dodo Tabletop — the living-world DnD engine (see docs/dnd/)
# --------------------------------------------------------------------------- #
# Every document here carries BOTH guild_id and campaign_id (except the global
# knowledge tier, which is unscoped and read-only at runtime). Reads go through
# helpers/dnd/store/repo.py, which requires a scope and injects the filter —
# raw access to these handles outside store/ is a review failure.
dnd_campaigns = db["DndCampaigns"]            # {guild_id, name, ruleset, settings, gm_ids}
dnd_entities = db["DndEntities"]              # PCs, NPCs, factions, creatures — one model
dnd_scenes = db["DndScenes"]                  # what is on screen right now
dnd_events = db["DndEvents"]                  # append-only log; the spine of the sim
dnd_knowledge = db["DndKnowledge"]            # KB facts, all four tiers (P1)
dnd_memories = db["DndMemories"]              # per-entity memory entries (P2)
dnd_beliefs = db["DndBeliefs"]                # who believes what, from whom, how surely (P2)
dnd_relations = db["DndRelations"]            # directed pair state (P2)
dnd_clocks = db["DndClocks"]                  # faction agendas / fronts (P3)
dnd_canon_queue = db["DndCanonQueue"]         # LLM inventions awaiting GM promotion (P4)
dnd_snapshots = db["DndSnapshots"]            # event-log compaction checkpoints

# --------------------------------------------------------------------------- #
#  DodoLand — the socialite tribe's town map (see docs/DODOLAND.md)
# --------------------------------------------------------------------------- #
# Both carry guild_id and are keyed by day. helpers/dodoland/store.py is the only
# module that touches them, and it refuses an unscoped query: DodoLand is
# multiserver from its first write and no code path reads across guilds.
dodoland_activity = db["DodoLandActivity"]   # {guild_id, user_id, day, acts, scored, channels}
# One row per pair per day, a < b. Enforces the per-partner caps, and is also the
# relation graph the map places neighbours from.
dodoland_pairs = db["DodoLandPairs"]         # {guild_id, day, a, b, acts, n}
dodoland_params = db["DodoLandParams"]       # {guild_id, key, value} — DodoLand's own tunables
# The per-guild DodoLand configuration: buildings, their channels and tiers, and
# later the uploaded map. One row per guild, read through helpers/dodoland/buildings.py.
dodoland_config = db["DodoLandConfig"]       # {_id: guild_id, buildings, map, plots}
# Decor and landmark images an admin uploads for people to place on their plots.
# Kept out of DodoLandConfig: images are large and that row is read on every
# page load, so binaries do not belong in it.
dodoland_assets = db["DodoLandAssets"]       # {guild_id, asset_id, name, data, min_tier}
# What a person calls their town, what they say about it, and its picture.
# Authored, never scored: nothing in here changes a single number.
dodoland_towns = db["DodoLandTowns"]    # {guild_id, user_id, name, blurb, image, building_names}
