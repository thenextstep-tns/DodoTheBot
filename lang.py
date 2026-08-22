"""
Central user-facing strings for DodoTheBot.

All text the bot says to users lives here, grouped by cog, so wording can be
edited in one place without touching command logic. Constants with ``{placeholder}``
fields are filled with ``.format(...)`` at the call site. (Internal debug/log
messages stay in the code — this file is for what users see.)
"""

# --------------------------------------------------------------------------- #
#  Common / shared
# --------------------------------------------------------------------------- #
API_ERROR = "Something was wrong with API, try again later"
SCHEDULE_INTROS = [
    "Here's what's cooking in the guild this week!",
    "Here's our current raiding schedule!",
    "Weekly schedule at your service!",
]

# --------------------------------------------------------------------------- #
#  General cog
# --------------------------------------------------------------------------- #
GENERAL_INFO_DESCRIPTION = "This is our personal mentally challenged Instagram blog"
GENERAL_INFO_AUTHOR = "Dodo, the almost useless helper"
GENERAL_INFO_OWNERS = "Salvy and Fox"
GENERAL_INFO_PREFIX_VALUE = "/ (Slash Commands) or {prefixes} for normal commands"
GENERAL_INFO_FOOTER = "Powered by electricity. Thank you, electricity"

GENERAL_COMMANDS_TITLE = "List of Loaded Commands"
GENERAL_COMMANDS_FOOTER = "Add dodo/gib/any other prefix before it and enjoy the weirdness!"
GENERAL_COMMANDS_NONE = "No commands loaded."
GENERAL_COMMANDS_CATEGORY = "**Category: {cog_name}**"

GENERAL_GUIDE_ERROR = "Something went wrong, let's try again!"

GENERAL_SERVER_TITLE = "**Server Name:**"
GENERAL_SERVER_ROLES_OVERFLOW = ">>>> Displaying [50/{total}] Roles"
GENERAL_SERVER_CREATED_AT = "Created at: {created_at}"

GENERAL_STATS_NONE = "{name}, you haven't used our Dodo yet! She's waiting!"
GENERAL_STATS_TITLE = "{name}'s Dodo Stats"
GENERAL_STATS_HEADER = "Since we started counting, {name} has used **{total} dodo commands**! :dodo:\n\n"
GENERAL_STATS_LINE = "**{command}** command - **{count}** times"

GENERAL_REMIND_SET = "Ok! I will remind you of this: '{text}' in {minutes} minute(s)!"
GENERAL_REMIND_FIRE = "Hey {mention}, you asked me to remind you of this: {text} :heart: :dodo: "

GENERAL_SCHEDULE_SENT_DM = "I sent you our current schedule in a private message!"
GENERAL_SCHEDULE_DM_FAILED = "I couldn't send you our schedule in DMs, so I will send it in here:"

GENERAL_PING_TITLE = "🏓 Pong!"
GENERAL_PING_DESCRIPTION = "The bot latency is {latency}ms."

GENERAL_INVITE_DESCRIPTION = (
    "Invite me to your server by clicking "
    "[here](https://discordapp.com/oauth2/authorize?&client_id={application_id}"
    "&scope=bot+applications.commands&permissions={permissions}). "
    "Except it won't work if you're not Fox. For now."
)
GENERAL_INVITE_SENT_DM = "I sent you a private message!"

# --------------------------------------------------------------------------- #
#  Economy cog
# --------------------------------------------------------------------------- #
ECONOMY_WALLET_BALANCE = "You have {balance} coins in your wallet!"
ECONOMY_WALLET_CREATED = (
    "Looks like you don't really have a wallet! But fear not! We will make you one this instant :dodo: "
)
SWEETROLLS_STOLEN = "{name} stole **{stolen}** sweetrolls including **{golden}** golden sweetrolls..."
SWEETROLLS_STOLEN_FROM = "People stole **{stolen_from}** sweetrolls from {name}. :pleading_face: "
SWEETROLLS_GIFTS = "{name} has given away **{given}** sweetrolls and received **{received}** as gifts!"
SWEETROLLS_RHUBARB = "{name} has suffered **{count}** rhubarb betrayal(s)!"
SWEETROLLS_NEMESIS = "{name}'s arch-nemesis is **{nemesis}** with **{count}** stolen sweetrolls. :smirk:"
SWEETROLLS_NO_NEMESIS = "{name} don't have an arch-nemesis (yet). "
SWEETROLLS_SUGAR_DADDY = "{name}'s sugar doddy is **{daddy}** with **{count}** sweetrolls gifted. :smirk:"
SWEETROLLS_NO_SUGAR_DADDY = "{name} don't have a sugar doddy (yet). "

# --------------------------------------------------------------------------- #
#  Parsing cog
# --------------------------------------------------------------------------- #
PARSING_TOP_TITLE = "Top 10 Parses"
PARSING_BOTTOM_TITLE = "Bottom 10 Parses"
PARSING_LEADERBOARD_VALUE = "\U0001F3AF Parse: {parse} | {date} | Difficulty: {difficulty}"
PARSEOLD_TIERS = [
    (15000, "{parse} DPS... Please leave the server",
     "{name} couldn't handle pressing 5 buttons, and gave up after {minutes} of whatever it was with the result of..."),
    (50000, "{parse} DPS. You must be new here :) ",
     "{name}, is that... a heavy attack build? {minutes} minutes well wasted, your result is..."),
    (70000, "{parse} DPS. A little bit more and you will look like a proper Veteran!",
     "{name} parsed the dummy for {minutes} minutes with the result of..."),
    (100000, "{parse} DPS! Sub 100k is so 2020",
     "{name} parsed the dummy for {minutes} minutes with a result of..."),
    (120000, "{parse} DPS! Is that an actual redguard magden?",
     "{name} demolished the trial dummy in {minutes} minutes with a result of..."),
    (140000, "{parse} DPS! Keegan would be proud. Ping him if you dare xD ",
     "{name} evaporated the poor atronach dummy in {minutes} minutes with a result of..."),
]
PARSEOLD_TOP_TIER = ("{parse} DPS! vote to kick", "Deniz, relog.")

# --------------------------------------------------------------------------- #
#  Death roll cog
# --------------------------------------------------------------------------- #
ROLL_OVER_LIMIT = " :eyes: Looks like someone should donate to the guild bank at this point, we still need a lot of attunable crafting stations :expressionless: :rofl: . I will set your current bet to match the current limit."
ROLL_NO_OPPONENT = "You forgot the mention your opponent after the bet, please try again with something like 'dodo roll 10 <@824171812518494238>'"
ROLL_DUEL_CALLED = "**{challengername}** just challenged **{opponentname}** for **{betfinal} gold**! **<@{opponentid}>**, if you are willing to accept the fight, press the dice emoji under this message and let the battle begin!"
ROLL_TIMEOUT_CANCEL = "This duel is cancelled because the time to accept it has run out"
ROLL_DUEL_ACCEPTED = "The game is on!"
ROLL_TITLE_LOSS = "Bad luck..."
ROLL_DUEL_OVER = "The duel is over, I saved results to the database! Don't forget to send gold when you're online!"
ROLL_SELF_PLAY = "Oi, if you wanna play with yourself, go to <#862007906176991242>"

# --------------------------------------------------------------------------- #
#  Fun cog — insults
# --------------------------------------------------------------------------- #
DODO_INSULT = [":face_with_raised_eyebrow:", "https://tenor.com/zQLn.gif", "I don't think so, sweetheart", ":angry:", "No way!", "Insulting bots is a weird kink.", "Dodo, you are such an awesome bot!", "You're really lucky the first law of Robotics is what it is right now :angry: ", "https://tenor.com/2g2n.gif", "https://tenor.com/bs7gh.gif", "...", "Oi!", "Nope, not doing that", "https://tenor.com/baDIy.gif"]
INSULT_1 = ["artless", "bawdy", "beslubbering", "bootless", "churlish", "cockered", "clouted", "craven",
"currish", "dankish", "dissembling", "droning", "errant", "fawning", "fobbing", "froward", "frothy",
"gleeking", "goatish", "gorbellied", "impertinent", "infectious", "jarring", "loggerheaded", "lumpish",
"mammering","mangled", "mewling", "paunchy", "pribbling", "puking", "puny", "qualling", "rank",
"reeky", "roguish", "ruttish", "saucy", "spleeny", "spongy", "surly", "tottering", "unmuzzled",
"vain", "venomed", "villainous", "warped", "wayward", "weedy", "yeasty"]
INSULT_2 = ["base-court","bat-fowling", "beef-witted","beetle-headed", "boil-brained", "clapper-clawed",
"clay-brained","common-kissing", "crook-pated", "dismal-dreaming", "dizzy-eyed","doghearted",
"dread-bolted","earth-vexing", "elf-skinned","fat-kidneyed","fen-sucked","flap-mouthed",
"fly-bitten","folly-fallen","fool-born","full-gorged","guts-griping","half-faced","hasty-witted",
"hedge-born","hell-hated","idle-headed","ill-breeding","ill-nurtured","knotty-pated",
"milk-livered","motley-minded","onion-eyed","plume-plucked","pottle-deep","pox-marked","reeling-ripe",
"rough-hewn","rude-growing","rump-fed","shard-borne","sheep-biting","spur-galled","swag-bellied",
"tardy-gaited","tickle-brained","toad-spotted","unchin-snouted","weather-bitten"]
INSULT_3 = ["apple-john","baggage","barnacle", "bladder", "boar-pig", "bugbear", "canker-blossom",
"clack-dish", "clotpole", "coxcomb", "codpiece", "death-token", "dewberry", "flap-dragon",
"flax-wench", "flirt-gill", "foot-licker", "fustilarian", "giglet", "gudgeon", "haggard",
"harpy", "hedge-pig", "horn-beast", "hugger-mugger", "joithead", "lout", "maggot-pie", "malt-worm",
"mammet", "measle", "minnow", "miscreant", "moldwarp", "mumble-news", "nut-hook", "pigeon-egg",
"pignut", "puttock", "pumpion", "ratsbane", "scut", "skainmate", "varlot", "vassal", "whey-face", "wagtail"]

# --------------------------------------------------------------------------- #
#  Moderation cog
# --------------------------------------------------------------------------- #
MOD_KICK_ADMIN = "You can't kick other admins like that, ask Fox, he will gladly do it."
MOD_KICK_TITLE = "User Kicked!"
MOD_KICK_DESCRIPTION = "**{member}** was kicked by **{author}**!"
MOD_KICK_DM = "You were kicked by **{author}**!\nReason: {reason}"
MOD_KICK_ERROR = "An error occurred while trying to kick the user. Make sure my role is above theirs."
MOD_BAN_ADMIN = "Don't ban admins! Do you have any idea how hard it is to find a good admin?"
MOD_BAN_TITLE = "User Banned!"
MOD_BAN_DESCRIPTION = "**{member}** was banned by **{author}**!"
MOD_BAN_DM = "You were banned by **{author}**!\nReason: {reason}"
MOD_BAN_ERROR = "An error occurred while trying to ban the user. Make sure my role is above theirs."
MOD_ZOOMIES_DM = "There is an urgent task for you! Activate your SalvyFoxBumblephant and start the ZOOMIES at zoomies.dodos.fun"
MOD_NICK_TITLE = "Changed Nickname!"
MOD_NICK_DESCRIPTION = "**{member}'s** new nickname is **{nickname}**!"
MOD_NICK_ERROR = "An error occurred while changing the nickname. Make sure my role is above theirs."
MOD_PURGE_INVALID = "`{amount}` is not a valid number."
MOD_PURGE_TOO_MANY = "Oi, chief, if you wanna sabotage the whole server, at least suffer and delete it in small chunks"
MOD_PURGE_ALERT_FOX = "Someone is trying to purge more than 50 messages at once, check on them"
MOD_PURGE_TITLE = "Purged!"
MOD_PURGE_DESCRIPTION = "**{author}** has purged the chat from the filth and deleted **{count}** message(s)!"
MOD_PIN_ANNOYED = [
    "You really don't have permission to pin messages here.",
    "Still not allowed.",
    "Nope. Try asking someone with permissions.",
    "Persistent, aren't you? Still no.",
    "This isn't working, stop.",
    "Seriously, stop.",
    "You're starting to annoy me.",
    "Enough already.",
    "Final warning: stop it.",
    "STOP.",
]
MOD_PIN_RAGE = "I won't be gentle. On your knees."
MOD_PIN_THREAT = "Try to pin me once more, and I'll pin you so hard you won't even be able to squeak."
MOD_PIN_NO_PERMISSION = "You do not have permission to pin messages."
MOD_PIN_NO_REFERENCE = ":shrug: I have no idea which message to pin, please reply to a message."
MOD_PIN_FAILED = "Something went wrong, I couldn't pin that."
MOD_UNPIN_NO_PERMISSION = "You do not have permission to unpin messages."
MOD_UNPIN_NO_REFERENCE = ":shrug: I have no idea which message to unpin, please reply to a message."
MOD_UNPIN_DONE = "Message unpinned by {mention}."
MOD_ROLE_BOT_NO_PERMISSION = "I don't have the **Manage Roles** permission here, so I can't touch anybody's roles."
MOD_ROLE_ABOVE_ME = "**{role}** sits above my highest role, so I can't hand it out or take it away."
MOD_ROLE_ABOVE_YOU = "**{role}** is not below your highest role, so you can't mass-assign it."
MOD_ROLE_UNMANAGEABLE = "**{role}** is managed by an integration (or is @everyone) — nobody can add or remove it manually."
MOD_ROLE_NOBODY_ADD = "Everyone on the server already has **{role}**. Nothing to do."
MOD_ROLE_NOBODY_REMOVE = "Nobody on the server has **{role}**. Nothing to do."
MOD_ROLE_CONFIRM_TITLE = "Hold on, let me count..."
MOD_ROLE_CONFIRM_ADD = (
    "I'm about to give **{role}** to **{targets}** member(s).\n"
    "**{skipped}** already have it and will be skipped.\n\nShould we go on?"
)
MOD_ROLE_CONFIRM_REMOVE = (
    "I'm about to strip the **{role}** from **{targets}** member(s).\n"
    "**{skipped}** don't have it and will be skipped.\n\nShould we go on?"
)
MOD_ROLE_CANCELLED = "The interaction was cancelled, I didn't touch anyone. Pinky promise"
MOD_ROLE_WORKING = "Working through **{targets}** users... {done} done."
MOD_ROLE_REASON = "Mass {action} of {role} by {author}"
MOD_ROLE_ADD_TITLE = "Role Assigned!"
MOD_ROLE_REMOVE_TITLE = "Role Removed!"
MOD_ROLE_RESULT_ADD = "**{count}** members have been assigned the **{role}** by **{author}**."
MOD_ROLE_RESULT_REMOVE = "**{count}** members have been stripped of the **{role}** by **{author}**."
MOD_ROLE_FIELD_SKIPPED_ADD = "Already had it"
MOD_ROLE_FIELD_SKIPPED_REMOVE = "Didn't have it"
MOD_ROLE_FIELD_FAILED = "Caused issues"
MOD_ROLE_FAILURES_TITLE = "Members I couldn't handle"
MOD_ROLE_FAILURE_LINE = "**{member}** — {error}"
MOD_ROLE_FAILURES_FOOTER = "Page {page}/{pages}"

# --------------------------------------------------------------------------- #
#  PP cog
# --------------------------------------------------------------------------- #
PP_BAR = "8{bars}D"
PP_TOO_SMALL_TITLE = "{name}'s pp when thinking of {target}! Oops!"
PP_TOO_SMALL = "This pp is too small to display. Maybe it's cold where you are?"
PP_RESULT_TITLE = "We caught {name} thinking of {target}! :smirk: "
PP_CHECK_NONE = "We haven't checked how this combination would affect their pps yet! Use dodo pp to check it!"
PP_CHECK_TITLE = "How much does {name} like {target} on average??"
PP_NONE = "You haven't used our dodo pp command yet! Never late to start! :eggplant:"
PP_PRIORITIES = "Here are your priorities, {mention}:\n{ranking}"
PP_HOTTIES_NONE = "Nobody has been thought of yet! :thinking:"
PP_HOTTIES = "Here are the most desired hot girls in your area :tired_face: :\n{ranking}"
PP_RANKING_LINE = "{index}. **{name}**: \n {bar}"

# --------------------------------------------------------------------------- #
#  Race-stats cog
# --------------------------------------------------------------------------- #
RACESTATS_MICE_NONE = "Looks like you don't have any race records yet! Start participating in races to see your stats :dodo:"
RACESTATS_MICE_HEADER = "**{name}'s Most Successful Mice:**\n"
RACESTATS_MICE_LINE = "{index}. **{mouse}**, Wins: {wins}, Avg Position: {avg:.2f}\n"
RACESTATS_TOP_TITLE = "Top 10 Mice!"
RACESTATS_TOP_DESCRIPTION = "Only showing mice who participated in 5 or more races:"
RACESTATS_TOP_LINE = "Starts: {starts}, Avg. Position: {avg:.2f}, Fav. Handler: {handler}"

# --------------------------------------------------------------------------- #
#  Fun cog (non-insult text)
# --------------------------------------------------------------------------- #
FUN_CRINGE = (
    "{user} You have been chosen for the cringe team! \n"
    "HEED THE CALL, your cringe challenge is: {challenge}! Good luck, and may the cringe be with you!"
)
FUN_D20_PLAIN = "You rolled: **{roll}**"
FUN_D20_MODIFIED = "You rolled: **{roll}** {sign}{modifier} = **{total}**"
FUN_D20_CRIT_SUCCESS = "\n **Critical Success!**"
FUN_D20_CRIT_FAILURE = "\n **Critical Failure!**"
FUN_D20M_JOIN = "React with the dice emoji within 7 seconds to join the d20 roll!"
FUN_D20M_NONE = "No one joined the roll in time."
FUN_D20M_TITLE = "Multiplayer d20 Results"
FUN_D20M_WINNER = "{winner} wins with a roll of {roll}!"
FUN_D20M_TIE = "{winners} tied with a roll of {roll}!"
FUN_ROAST_SELF = "Do you really wanna insult yourself? Even to a Dodo like me, it's a bit too much."
FUN_ROAST = "{name}, thou {insult}!"
FUN_GAY_FOUR = "I once yelled COW! at a woman on a bicycle and she gave me the middle finger. Then she plowed her bike straight into the cow... I know it's unrelated, just wanted to share"
FUN_GAY_STRAIGHT = [
    "The only thing you see in the LGBT flag are straight lines...",
    "When you play chess you only use rooks, because they go straight.",
    "When someone asks you directions, you always tell them to go straight",
    "Straighter than a ruler!",
    "You must be really good at playing poker, since you always keep a straight face",
    "Keep it up, breeder :heart: ",
]
FUN_GAY_SLIGHT = ["You are on the right path!"]
FUN_GAY_MEDIUM = ["That actually explains so much... :open_mouth: "]
FUN_GAY_HEAVY = [
    "I hope you never have to pass the walk and turn test :pleading_face: ",
    "It made me remember that argument we had, when we were constantly going in circles...",
]
FUN_GAY_FULL = [
    "You look fantastic, no hetero :smirk: Must be all the time you've spent in the closet!",
    "The time has come for the Vestige to know the truth!",
    "I would ask you how it feels to be so gay, but I'm afraid I wouldn't get a straight answer",
]
FUN_GAY_TITLE = "{name}, we checked your momentary gayness, and here's the result!"
FUN_GAY_RESULT = "{name}, you are {gayness}% gay! {phrase}"
FUN_WISDOM_TITLE = "This may change your life"
FUN_WISDOM_AUTHOR = "{name},"
FUN_TAROT_CARD = "{name}, I see {card}. The card is {side}"
FUN_IMAGINE_UNCONFIGURED = "Image generation isn't configured."
FUN_IMAGINE_THINKING = ":thinking: Give me a few seconds please, I'm gonna do my very best!"

# --------------------------------------------------------------------------- #
#  Throw cog
# --------------------------------------------------------------------------- #
THROW_PUZZLE = "To charge your throw, solve this puzzle within {timeout} seconds: {num1} * {num2} * {num3}"
THROW_COUNTDOWN = "To charge your throw, solve this puzzle: {num1} * {num2} * {num3}\nTime left: {remaining} seconds"
THROW_TIMEOUT = "{mention}, you took too long!"
THROW_THROWING = "The correct answer was {answer}!\nTHROWING {member} AT AN ANGLE OF {angle} degrees...\n{gif}"
THROW_RESULT = (
    "{member} landed {distance} meters away!\n{funny}\n"
    "{thrower}'s power increased to {new_thrower_power}!\n"
    "{member}'s power decreased to {new_target_power}."
)
THROW_FUNNY_PART1 = [
    "{member} was launched with tremendous force!",
    "{member} was thrown into the great unknown!",
    "{member} took off like a rocket!",
]
THROW_FUNNY_PART2 = [
    "They were seen soaring through the sky,",
    "They disappeared into the clouds,",
    "They flew straight past the stratosphere,",
]
THROW_FUNNY_PART3 = [
    "defying all known laws of physics.",
    "creating a new constellation in the process.",
    "breaking the sound barrier on the way.",
]
THROW_FUNNY_PART4 = [
    "Authorities are still investigating the exact trajectory.",
    "It's unlikely they'll return anytime soon.",
    "Observers are in shock and awe.",
]

# --------------------------------------------------------------------------- #
#  Owner cog
# --------------------------------------------------------------------------- #
OWNER_SHUTDOWN = "Ah shit, not again! Family, here I come :wave:"
OWNER_SYNCED = "Re-synced command visibility across {count} guild(s)."
OWNER_RELOAD_DONE = "🔄 Reloaded cog `{cog}`. Run `/sync` if its commands changed."
OWNER_LOAD_DONE = "✅ Loaded cog `{cog}`. Run `/sync` if it added commands."
OWNER_UNLOAD_DONE = "🛑 Unloaded cog `{cog}`. Run `/sync` if it removed commands."
OWNER_UNLOAD_SELF = "I won't unload the owner cog — I'd lose these controls. Use `/reload owner` instead."
OWNER_COG_NOT_LOADED = "Cog `{cog}` isn't loaded."
OWNER_COG_NOT_FOUND = "No cog named `{cog}` was found under cogs/."
OWNER_COG_NO_ENTRY = "`{cog}` is a helper module, not a cog (no setup function)."
OWNER_COG_ERROR = "Failed on cog `{cog}`: {error}"
OWNER_RELOADALL_TITLE = "Reloaded {ok}/{total} cog(s)"
OWNER_CLEANROLE_NOT_FOUND = "Role '{role}' not found."
OWNER_CLEANROLE_DONE = "Role '{role}' removed from all members who had it."
OWNER_ADDONS_TITLE = "Hey! Here's the list of add-ons that we would recommend!"
OWNER_ADDONS_URL = "http://dodos.fun/add-ons/"
OWNER_ADDONS_IMAGE = "http://dodos.fun/wp-content/uploads/2022/03/unknown-4-1-1024x579-1.png"
OWNER_BLACKLIST_TITLE = "There are currently {count} blacklisted IDs"
OWNER_BLACKLIST_ADD_ALREADY = "**{name}** is already blacklisted."
OWNER_BLACKLIST_ADD_TITLE = "User Blacklisted"
OWNER_BLACKLIST_ADD_DONE = "**{name}** has been added to the blacklist."
OWNER_BLACKLIST_FOOTER = "There are now {count} users in the blacklist."
OWNER_BLACKLIST_REMOVE_NONE = "**{name}** is not in the blacklist."
OWNER_BLACKLIST_REMOVE_TITLE = "User removed from blacklist"
OWNER_BLACKLIST_REMOVE_DONE = "**{name}** has been removed from the blacklist."

# --------------------------------------------------------------------------- #
#  Spam cog
# --------------------------------------------------------------------------- #
SPAM_ALERT = (
    "🛡️ **Anti-Spam Triggered!**\n"
    "I have banned {mention} (`{user_id}`).\n"
    "**Reason:** {reason}\n"
    "Their recent messages have been purged."
)

# --------------------------------------------------------------------------- #
#  PAT cog
# --------------------------------------------------------------------------- #
PAT_DOWNLOAD_FAILED = "Failed to download image."
PAT_NO_ROLES = "{mention}, no roles detected from this image."
PAT_ASSIGNED_TITLE = "Assigned Roles"
PAT_ASSIGNED_DESCRIPTION = "{mention}, you've been assigned the following roles:"

# --------------------------------------------------------------------------- #
#  Talk-engine cog
# --------------------------------------------------------------------------- #
TALKENGINE_THINKING = "🤔 Hmmmm let me think... "
TALKENGINE_NO_MESSAGES = "No public messages found for user {name}."
TALKENGINE_FAILED = "Unable to generate a coherent message for {name}."
TALKENGINE_RESULT = "Hi, my name is {name}, and this is what I think:"

# --------------------------------------------------------------------------- #
#  Gym cog
# --------------------------------------------------------------------------- #
GYM_NO_PETS = "You do not own any pets eligible for the gym."
GYM_SELECT_PET_PROMPT = "Select your pet:"
GYM_SELECT_PET_PLACEHOLDER = "Choose your pet for the gym"
GYM_SELECT_PET_TIMEOUT = "You took too long to choose a pet."
GYM_SELECT_TRAIN_PROMPT = "Select what you wanna train today!"
GYM_SELECT_TRAIN_PLACEHOLDER = "What do you wanna train today?"
GYM_TRAINING_STARTED = "{name}'s pet is now training their {muscle_group}."
GYM_MUSCLE_GROUPS = [
    "Chest and Arms",
    "Core and Cardio",
    "Brain by reading clever books",
    "Beauty by attending the Grooming center",
]

# --------------------------------------------------------------------------- #
#  Chat cog (user-facing replies; the persona and triggers are per-server data)
# --------------------------------------------------------------------------- #
CHAT_API_ERROR = "Oh dear, my brain feels a bit fuzzy... I couldn't connect to my thoughts. (Error: {error})"
CHAT_NO_KEY = "This server hasn't set up a chat API key yet — an admin can add one in the control panel to enable me here. :hearts:"
CHAT_REPLY_FALLBACK = "I... I think I forgot what I was saying. My apologies!"
CHAT_PARSE_ERROR = "My thoughts got all tangled up! Could you say that again?"
# How a trigger-inflicted grudge is written down. It reaches the prompt, so it
# reads as something that happened rather than as a database row.
CHAT_GRUDGE = "the {name} thing"
# Stands in for the user turn when she speaks without being spoken to.
CHAT_EMPTY_TURN = "(nobody said anything to you)"

# --------------------------------------------------------------------------- #
#  Scheduler cog
# --------------------------------------------------------------------------- #
SCHED_SELECT_TRIAL = "Please select the trial:"
SCHED_SELECT_TRIAL_PLACEHOLDER = "Select a trial"
SCHED_SELECT_RUN = "Please select the type of run:"
SCHED_SELECT_RUN_PLACEHOLDER = "Select the type of run"
SCHED_RUN_TYPES = ["free for all", "vet training", "hm training", "farm run", "farm hm run", "achievement run"]
SCHED_ASK_TIME = "Please enter the date and time for the raid (e.g., `2023-10-12 18:30` or `next Friday at 6pm`):"
SCHED_TIME_PARSE_FAILED = "Sorry, I couldn't parse the date and time. Please try again."
SCHED_ASK_COMP = "Please enter the group composition (e.g., `2 tanks, 2 heals, 8 dds` or `1 tank 3 heal 8 dd`):"
SCHED_COMP_PARSE_FAILED = "Sorry, I couldn't parse the group composition. Please try again."
SCHED_TIMEOUT = "You took too long to respond. Please try scheduling the raid again."
SCHED_NO_FORUM = "Could not find the raid forum channel."
SCHED_RAID_DESCRIPTION = "Raid scheduled for {timestamp}"
SCHED_SUCCESS = "Raid scheduled successfully."
SCHED_SIGNUP_REMOVED = "You have been removed from the sign-up."
SCHED_SIGNUP_NOT_SIGNED = "You are not signed up."
SCHED_SIGNUP_ALREADY = "You are already signed up for this role."
SCHED_SIGNUP_DONE = "You have signed up as a {role}."
SCHED_SIGNUP_RESERVES = "All slots are full. You have been added to reserves."
SCHED_SIGNUP_ALREADY_RESERVE = "You are already in the reserves."

# --------------------------------------------------------------------------- #
#  Seasonal cog
# --------------------------------------------------------------------------- #
SEASONAL_THREAD_GONE = "Just like my family, this thread will now disappear. Thank you! :heart: "
LOVE_INTRO = (
    "Hey there, {mention}! I created this private thread for you to send a message. "
    "I will memorise it and send it to <#{channel}>, which will be available on "
    "Valentine's day! This thread is private. I'll ask a few questions, then save it all and delete the thread :heart: "
)
LOVE_Q_WHO = "QUESTION 1: **Who is your message for?**"
LOVE_Q_FROM = "Now I need to know **who is the message FROM?** You can stay anonymous if you want to!"
LOVE_Q_MESSAGE = "Nice! **Now is the time to write and send your message!**"
LOVE_CONFIRM = "Perfection! I will send a message from {sender} to {who}! The message will be:"
LOVE_EMBED_DESCRIPTION = "To: {who}! From: {sender}"
LOVE_NOTIFY = "<@{member_id}>! You got a valentine! :heart:"
LOVE_HEARTS = "= :heart: ="
LOVE_LOG = "New valentine added! :smirk: {author} who said their name was {sender} sent this message to {who}: {message}"

VOTE_ALREADY = (
    "Looks like you have already voted in this round! If you feel like you did some oopsie :dodo: "
    "in your votes, please poke Fox!"
)
VOTE_INTRO = (
    "Hey there, {mention}! This private thread collects your nominations. "
    "They'll be posted to <#{channel}> at the end of round 1.\n"
    "## Please note that both Salvy and Fox are not participating in the votes.\n"
    "Don't vote for them even if you really want to :hearts: You have 180 seconds per question."
)
VOTE_Q1 = (
    "# NOMINATION 1: **THE ROLE MODEL**\nThe person who sets an example with exceptional skills, knowledge and "
    "dedication, always ready to support others."
)
VOTE_Q2 = (
    "# NOMINATION 2: **THE PROGRESS OF THE YEAR**\nThe person who achieved a breakthrough in their progress or "
    "found a fundamentally new role in the community."
)
VOTE_Q3 = (
    "# NOMINATION 3: **THE COMMUNITY BUILDER OF THE YEAR**\nThe special someone who creates the cosiness and "
    "respect that made you find your place here."
)
VOTE_EMBED_TITLE = "Nominations from {author}"
VOTE_EMBED_DESCRIPTION = "THE ROLE MODEL: {role_model}!\nPROGRESS OF THE YEAR: {progress}\nCOMMUNITY BUILDER: {community}"
VOTE_CLOSE = "The first round of the votes closes on 17.12! Thank you for participating! :heart: "
RESETVOTE_DONE = "Vote status for {mention} has been reset."
RESETVOTE_NONE = "User not found in the voting status records."

# --------------------------------------------------------------------------- #
#  Parse-tournament cog
# --------------------------------------------------------------------------- #
PARSEFEST_INVALID_ATTEMPTS = "The number of attempts must be between 1 and 3. Usage: dodo parse <1-3>"
PARSEFEST_LOBBY = "React with ✅ to participate! You have 20 seconds to join.\nEach player has {max_attempts} attempts."
PARSEFEST_TITLE = "Dodos Parse Championship"
PARSEFEST_STOPPED = "The parsefest has been stopped."
PARSEFEST_WR = "World Record: {parse} DPS by {name}"
PARSEFEST_NO_WR = "No world record set yet."
PARSEFEST_DIFFICULTY_MENU = (
    "{name}, choose your difficulty level:\n"
    "1️⃣ - Easy (-2 actions, -35000 from max DPS)\n"
    "2️⃣ - Medium (-1 action, -25000 from max DPS)\n"
    "3️⃣ - Baseline (5 actions, no changes)\n"
    "4️⃣ - Very Hard (+2 actions, +25000 to max DPS)\n"
    "5️⃣ - Insane (+4 actions, +40000 to max DPS)"
)
PARSEFEST_DIFFICULTY_TIMEOUT = "{name}, you took too long to choose! Defaulting to the normal difficulty."
PARSEFEST_PREBUFF = "{name}, prebuff and get ready to parse!"
PARSEFEST_GO = "{name}, click the right emoji as fast as you can once you see it here!"
PARSEFEST_ACTION = "{mention}, click the right emoji as fast as you can once you see it here!\nAction #{index}: {action} ({emoji})"
PARSEFEST_MISSED = "{name}, you missed the action!"
PARSEFEST_DPS = "{name}, your DPS was: {parse}{wr} (Difficulty: {difficulty})"
PARSEFEST_WR_UPDATE = "World Record: {parse} DPS by {name} (Difficulty: {difficulty})"
PARSEFEST_SCORES = "Participants and Scores"
PARSEFEST_FINAL_TITLE = "Dodos Parse Championship - Final Results"
PARSEFEST_FINAL_DESCRIPTION = "Here are the final results of the parse competition."

# --------------------------------------------------------------------------- #
#  Fishing cog
# --------------------------------------------------------------------------- #
FISHING_NO_COINS = "Sorry, you don't have enough coins to go fishing. Try doing dodo dailies to earn more coins!"
FISHING_NO_CATS = "You don't have any cats available to fish with. Summon one of your cats and toggle fishing for them! 🐱"
FISHING_SELECT_CAT = "Please select a cat to fish with! 🐱 Choose wisely! Different cats are good for different types of loot!"
FISHING_SELECT_CAT_PLACEHOLDER = "Select a cat to fish with"
FISHING_REEL_IN = ":thinking: Hmmm, what is this? Looks like you can reel in!"
FISHING_ITEM_APPEARED = "A new item has appeared for fishing!"
FISHING_STATUS = (
    "\nLet's see how your stats are looking for this reel in!\n {agility}\n {intellect}\n {strength}\n\n "
    "YOUR CAT IS TRYING REALLY HARD TO REEL IN! WAIT JUST A BIT LONGER :fish:"
)
FISHING_PARAM_EXCELLENT = ":white_check_mark: Wow! Fishing this item with so much {parameter} should be a piece of cake for your cat!"
FISHING_PARAM_GOOD = ":ballot_box_with_check: Great! Your cat's {parameter} is looking good for fishing this item."
FISHING_PARAM_OK = ":warning: Not bad! Your cat's {parameter} is somewhat sufficient, but it might be not enough... :pleading_face:"
FISHING_PARAM_LOW = ":no_entry: Uh-oh! Your cat's {parameter} is a bit low for this fishing trip."
FISHING_VICTORY_TITLE = "You have successfully fished out\n**{item_name}**!"
FISHING_VICTORY_DESCRIPTION = (
    "Now you have to decide what to do with the item!\n"
    "Use the BACKPACK icon to stash it in your goodies bag if you have space!\n"
    "Use the COIN PURSE icon to sell it immediately\n"
    "Use the EXPLOSION icon to throw it away!"
)
FISHING_COST_NOTE = "The Fishing Bait cost you {cost} coins. We subtracted them from your wallet :3"
FISHING_FAILED = "Unfortunately, you couldn't fish that {item_name}. Better luck next time!"
FISHING_STASHED = "Item stashed in the goodies bag!"
FISHING_BAG_FULL = "Sorry, your goodies bag is full! There's no more space to store anything else."
FISHING_SOLD = "Item sold! You earned {price} dodo coins!"
FISHING_THROWN = "We threw it away! EW!"

# --------------------------------------------------------------------------- #
#  Pet cog
# --------------------------------------------------------------------------- #
PET_STOP_CATS = "Alright, let's stop LFC (looking for cats!) :hearts: "
PET_STOP_DOGS = "Alright, let's stop LFD (looking for dogs!) :hearts: "
PET_DODGE_CAT = "This cat was quite nimble, they dodged the claim and ran away! Wanna look for the next one?"
PET_DODGE_DOG = "This dog didn't trust you enough and they ran away! Wanna look for the next one?"
PET_API_ERROR = "{api_name} is being weird at the moment, try again or later"
PET_SHOWCATS_INTRO = "Ok, {name}, here comes your meow army! :cat: "
PET_SHOW_NONE = "Doesn't look like you have any {kind}s :pleading_face: , try dodo {kind} command to find a new one!"
PET_SHOW_COUNT = "I found {count} {kind}s"
PET_SNAKE = ":snake:"
PET_CLAIM_OFFER = "Strength = {strength}, Agility = {agility}, Intellect = {intellect}, Charm = {charm}, your chance to claim them is {claim_chance}%"
PET_CLAIM_AUTHOR = "{name}, this {pet_type} is free! Are you gonna claim them?"
PET_CLAIM_SUCCESS = "You have successfully claimed this pet! :white_check_mark: How are you going to name them? Hurry up, the others may name it too!"
PET_CLAIM_DUPLICATE = "I won't be able to distinguish between different {name}s. Please choose a unique name for your unique {kind}! Meow :3"
PET_CLAIM_ADDED = "{name} has been added to your collection!"
PET_RETRY_YES = "Okie dokie, find a new {noun}!"
PET_RETRY_STOP = "Alright, {name} let's stop looking for {noun}s"
PET_SUMMON_NOT_FOUND = "I couldn't find '{pet_name}' in your collections. Please check the spelling and try again."
PET_SUMMON_MULTIPLE_TITLE = "Looks like you have several pets with that name!"
PET_SUMMON_CHOOSE = "You have several pets matching '{pet_name}' — which one do you want to summon?"
PET_SUMMON_TIMEOUT = "Oops, too slow! Please try the command again."
PET_SUMMON_UNKNOWN_ACTION = "This action is not recognized."
PET_PET_STATUS = "Type: {type}, Wins: {wins}, Losses: {losses}"
PET_PET_AUTHOR = "{name} at your service"
PET_PET_ACTION_FIELD = "React with {emoji}"
PET_FIGHT_NO_MY_PET = "I couldn't find any pets with that name in your collection :slight_frown: . Please check spelling and try again"
PET_FIGHT_NO_THEIR_PET = "I couldn't find any pets with that name in your opponent's collection :angry: . Please check spelling and try again"
PET_FIGHT_BOTH = "I found a cat and a dog with this name{label}! Who would you want to fight? :eyes: "
PET_FIGHT_PROPOSAL = (
    "Duel has been proposed! \n {challenger}'s **{attacker}** \n Strength: **{a_str}** \n Agility: **{a_agi}** \n "
    "Intellect: **{a_int}** \n Charm: **{a_cha}** \n \n is challenging {opponent}'s **{defender}** \n \n "
    "Strength: **{d_str}** \n Agility: **{d_agi}** \n Intellect: **{d_int}** \n Charm: **{d_cha}** \n "
    "Will {opponent} accept the duel? "
)
PET_FISHING_ENABLED = "{name} can now fish!"
PET_FISHING_DISABLED = "You took away {name}'s fishing pole. They won't be able to fish anymore."
PET_FISHING_FULL = "You already have 25 cats that can fish. Toggle one off, and {name} will be able to join!"
PET_GYM_ENABLED = "{name} can now use the gym!"
PET_GYM_DISABLED = "{name} is no longer allowed to use the gym."
PET_GYM_FULL = "You already have 25 cats using the gym. Toggle one off, and {name} will be able to join!"

# --------------------------------------------------------------------------- #
#  Log cog (audit-log formats)
# --------------------------------------------------------------------------- #
LOG_SET_CHANNEL = "✅ Standard server logs will now be sent to {channel}."
LOG_SET_DELETE_CHANNEL = "✅ Message edit and deletion logs will now be sent to {channel}."
LOG_ROLE_UPDATE = "👤 **{mention}** (`{id}`) roles updated{actor} - <t:{now}:f>"
LOG_ROLE_ADDED = "➕ Added"
LOG_ROLE_REMOVED = "➖ Removed"
LOG_MEMBER_JOIN = "📥 **{mention}** (`{id}`) joined the server - <t:{now}:f>"
LOG_INVITE_USED = "📨 Invite Used"
LOG_INVITE_USED_VALUE = "`{code}` by {inviter} (Uses: {uses})"
LOG_MEMBER_KICK = "👢 **{mention}** was kicked by {actor} - <t:{now}:f>\n**Reason:** {reason}"
LOG_MEMBER_LEAVE = "📤 **{mention}** left the server - <t:{now}:f>"
LOG_ROLES_HELD = "Roles Held"
LOG_MEMBER_BAN = "🔨 **{mention}** was banned by {actor} - <t:{now}:f>\n**Reason:** {reason}"
LOG_MEMBER_UNBAN = "🔓 **{mention}** was unbanned by {actor} - <t:{now}:f>"
LOG_NICK_CHANGE = "✏️ **{mention}** (`{id}`) nickname changed by {actor} - <t:{now}:f>\n\n**From:** `{old}`\n**To:** `{new}`"
LOG_TIMEOUT_ADD = "⏳ **{mention}** (`{id}`) was timed out by {actor} - <t:{now}:f>\n**Until:** <t:{until}:f>\n**Reason:** {reason}"
LOG_TIMEOUT_REMOVE = "⌛ **{mention}** (`{id}`) timeout removed by {actor} - <t:{now}:f>\n**Reason:** {reason}"
LOG_AUTOMOD = "🛡️ **AutoMod Executed:** {action} on **{mention}** (`{id}`) - <t:{now}:f>\n**Rule:** `{rule}`"
LOG_INVITE_CREATE = "✉️ **Invite Created** by {inviter} in {channel} - <t:{now}:f>\n**Code:** `{code}` | **Age:** {age} | **Uses:** {uses}"
LOG_INVITE_DELETE = "🗑️ **Invite Deleted:** `{code}`{actor} - <t:{now}:f>\n**Channel:** {channel}"
LOG_MESSAGE_EDIT = "✏️ **{mention}** (`{id}`) edited a message in {channel} - <t:{now}:f> [Jump]({jump})"
LOG_MESSAGE_DELETE = "🗑️ **{mention}** (`{id}`) message deleted in {channel}{deleter} - <t:{now}:f>"
LOG_DELETED_BY = " (Deleted by {mention})"
LOG_BULK_DELETE = "🧹 **Bulk Delete:** {count} messages purged in {channel}{actor} - <t:{now}:f>"
LOG_ROLE_CREATE = "🏷️ **Role Created:** {mention} (`{name}`){actor} - <t:{now}:f>"
LOG_ROLE_DELETE = "🗑️ **Role Deleted:** `{name}`{actor} - <t:{now}:f>"
LOG_ROLE_EDIT = "✏️ **Role Updated:** {mention}{actor} - <t:{now}:f>\n\n{changes}"
LOG_CHANNEL_CREATE = "📁 **{entity} Created:** {display}{actor} - <t:{now}:f>"
LOG_CHANNEL_DELETE = "🗑️ **{entity} Deleted:** `#{name}`{actor} - <t:{now}:f>"
LOG_CHANNEL_EDIT = "✏️ **{entity} Updated:** {display}{actor} - <t:{now}:f>\n\n{changes}"
LOG_THREAD_CREATE = "🧵 **Thread Created:** {mention} (`{name}`){actor} - <t:{now}:f>\n**Parent:** {parent}"
LOG_THREAD_DELETE = "🗑️ **Thread Deleted:** `#{name}`{actor} - <t:{now}:f>\n**Parent:** {parent}"
LOG_THREAD_EDIT = "✏️ **Thread Updated:** {mention}{actor} - <t:{now}:f>\n\n{changes}"
LOG_VOICE_JOIN = "🎙️ **{mention}** (`{id}`) joined {channel} - <t:{now}:f>"
LOG_VOICE_LEAVE = "🎙️ **{mention}** (`{id}`) left {channel} - <t:{now}:f>"
LOG_VOICE_MOVE = "🎙️ **{mention}** (`{id}`) moved from {before} to {after} - <t:{now}:f>"
LOG_VOICE_MUTE = "🔇 **{mention}** (`{id}`) was {action} by {actor} in {channel} - <t:{now}:f>"
LOG_VOICE_DEAFEN = "🎧 **{mention}** (`{id}`) was {action} by {actor} in {channel} - <t:{now}:f>"
LOG_VOICE_STREAM = "📺 **{mention}** (`{id}`) {action} streaming in {channel} - <t:{now}:f>"
LOG_VOICE_CAMERA = "📷 **{mention}** (`{id}`) {action} their camera in {channel} - <t:{now}:f>"
LOG_EMOJI_CREATE = "😀 **Emoji Created:** {emoji} (`{name}`){actor} - <t:{now}:f>"
LOG_EMOJI_DELETE = "🗑️ **Emoji Deleted:** `{name}`{actor} - <t:{now}:f>"
LOG_EMOJI_EDIT = "✏️ **Emoji Updated:** {emoji}{actor} - <t:{now}:f>\n\n**Name:** `{old}` ➔ `{new}`"
LOG_STICKER_CREATE = "🌠 **Sticker Created:** `{name}`{actor} - <t:{now}:f>"
LOG_STICKER_DELETE = "🗑️ **Sticker Deleted:** `{name}`{actor} - <t:{now}:f>"
LOG_STICKER_EDIT = "✏️ **Sticker Updated:** `{name}`{actor} - <t:{now}:f>\n\n**Name:** `{old}` ➔ `{new}`"
LOG_EVENT_CREATE = "📅 **Event Created:** `{name}`{actor} - <t:{now}:f>"
LOG_EVENT_DELETE = "🗑️ **Event Deleted / Cancelled:** `{name}`{actor} - <t:{now}:f>"
LOG_EVENT_EDIT = "✏️ **Event Updated:** `{name}`{actor} - <t:{now}:f>\n\n{changes}"
LOG_GUILD_UPDATE = "⚙️ **Server Settings Updated**{actor} - <t:{now}:f>\n\n{changes}"

# --------------------------------------------------------------------------- #
#  Racing cog (user-facing copy; whole-field battle-log announcements live here
#  too — only the per-mouse roll fragments stay inline in the cog)
# --------------------------------------------------------------------------- #
RACING_MOUSE_EXISTS = "The mouse name '{name}' already exists in the list."
RACING_CHOOSE_CLASS = "Choose a class for your mouse:\n{classes}"
RACING_CLASS_TIMEOUT = "You took too long to choose a class. Please try again."
RACING_MOUSE_ADDED = "The mouse name '{name}' with class '{mouse_class}' has been added to the list."
RACING_START = (
    "{mention} started the race! You have {countdown} seconds to react and add your skeevaton to the race roster.\n"
    "React with 🐁 to join the race."
)
RACING_COUNTDOWN = (
    "{mention} started the race of {track_length} laps! You have {remaining} seconds to react and add your "
    "skeevaton to the race roster.\nReact with 🐁 to join the race."
)
RACING_GIGA_START = (
    "THE **GIGARACE** HAS JUST BEEN ANNOUNCED! You have 9 hours (32400 seconds) to react and add your "
    "skeevaton to the race roster.\nReact with 🐁 to join the race.\n"
    " 1st place - 100 000 gold \n 2nd place - 50 000 gold \n 3rd place - 10 000 gold  "
)
RACING_GIGA_COUNTDOWN = (
    "THE **GIGARACE** HAS JUST BEEN ANNOUNCED! You have {remaining} seconds to react and add "
    "your skeevaton to the race roster.\nReact with 🐁 to join the race.\n "
    "1st place - 100 000 gold\n 2nd place - 50 000 gold\n 3rd place - 10 000 gold "
)
RACING_NO_JOIN = "No one joined the race. Race cancelled."
RACING_NO_MICE = (
    "There isn't a single skeevaton with a valid class in the pen, so there's nothing to race. "
    "Register one with `newmouse` first!"
)
RACING_SHORT_ON_MICE = "The pen ran dry — {count} racer(s) couldn't be given a skeevaton and have to sit this one out."
RACING_LINEUP_TITLE = "Race Line-up"
RACING_LINEUP_DESCRIPTION = "The race is about to start!\n"
RACING_LIGHTS_TITLE = "Race is about to start!"
RACING_LIGHTS_DESCRIPTION = (
    "{roster}\n\nReactions:\n"
    "🧀 Cheese: Increases your move by 1\n"
    "🍷 Wine: Multiplies your move by 2\n"
    "💣 Bomb: Drops everyone else back by 5\n"
    "✨ Starry Eyes: +5 to your move for 5 moves — only a mouse racing for the owner who adopted it can grab this\n"
    "🗺️ Treasure Map: teleports you 20 steps ahead — only a Navigator can read it, anyone else wastes it"
)
RACING_LIGHTS_GO = "{roster}\n\nGOOOO!!!"
RACING_EVENT_RACING = "## We are racing :mouse2:"
RACING_EVENT_MAP = "## A Treasure Map just appeared! Click the map emoji to pick it up!"
RACING_EVENT_STARRY = "## Starry Eyes! Click ✨ to inspire your mouse!"
RACING_EVENT_CHEESE = "## Cheese appeared! Click the cheese emoji to grab it!"
RACING_EVENT_WINE = "## Wine appeared! Click the wine emoji to grab it!"
RACING_EVENT_BOMB = "## Bomb appeared! Click the bomb emoji to grab it!"
# Battle-log lines for the race footer. The per-mouse roll fragments stay inline in
# the cog; these are the shared, whole-field announcements.
RACING_LOG_BOMB_THROWN = "Move {move}: 💣 {mouse} set off the bomb!"
RACING_LOG_BOMB_HITS = "Move {move}: the blast caught {mice}."
RACING_LOG_BOMB_DODGED = "Move {move}: {mice} dodged the blast."
RACING_LOG_BOMB_FIZZLE = "Move {move}: the bomb went off with nobody left to catch the blast."
RACING_LOG_YEETED = "Move {move}: 💥 {mouse} was blasted clean off the back of the track (position {position})!"
RACING_PROGRESS_TITLE = "THE SKEEVATON RACE IS ON!"
RACING_SUMMARY_HEADER = "The race has ended!\nRace Results:\n"
RACING_SUMMARY_LINE = "{mention}'s {mouse} - {points} points\n"
RACING_RELATIONSHIP_TITLE = "Relationship Points Adjusted"
RACING_RELATIONSHIP_LINE = "{mention} gains {points} relationship points with **{mouse}**!"
RACING_ADOPT_PROMPT = "{mention}, do you want to {verb} {mouse}? React with 👍 for yes or 👎 for no."
RACING_ADOPT_SUCCESS = "**{mouse}** happily chirps that it will serve you with all its smol heart!"
RACING_READOPT_SUCCESS = "{mouse} joyfully announces its readoption and vows to serve you faithfully!"
RACING_ADOPT_DECLINE = "{mouse} is heartbroken... :pleading_face: it slinks away and hides in shame and neglect. :broken_heart:"
RACING_ADOPT_MOUSECHAT = (
    "You are a little {mouse}, and your relationship with {name} just reached a new height! Look at tham with sad, "
    "hopeful eyes and ask them in the mousy cutest way possible to adopt you. When prompted for adoption, return your "
    "message strictly in the following format: **Name of the mouse**: Your direct speech. Don't add any additional text"
)
RACING_READOPT_MOUSECHAT = (
    "{mouse} feels neglected by its current owner and turns to you with pleading eyes. It wonders if you'll adopt it instead!"
)
# --- Cheese co-op stretch minigame ---
CHEESE_GAME_TITLE = "🧀 You found {cheese}! **EVERYONE** quickly pull if you want some too!"
CHEESE_GAME_DESC = (
    "{bar}\n\n"
    "The **{cheese}** is stretching! "
    "Be careful not to pull too hard or it's gonna snap!\n\n"
    "👌 **Pull** — stretch: grows the pot, but pull too far and it **snaps**!\n"
    "✂️ **Cut** — split the pot *now*. Don't cut too early, maybe you still have some to pull!\n"
    "💰 **Steal** — grab a fifth of the whole stretch just for yourself; everyone else gets nothing!\n"
    "Pulls so far: **{pulls}**"
)
CHEESE_CUT_TITLE = "✂️ You just carefully cut off the {cheese}!"
CHEESE_CUT_LINE = "{mention} gained **+{points}** points with **{mouse}**!"
CHEESE_SNAP_TITLE = "💥 BOOM!"
CHEESE_SNAP = (
    "{bar}\n\nOH NO! Someone pulled too hard! The **{cheese}** was stretched too far and exploded! Nobody gets anything!"
)
CHEESE_STEAL_TITLE = "💰 Cheese STOLEN!"
CHEESE_STEAL = (
    "{mention} STOLE **{points}** meters of **{cheese}** and bonded with **{mouse}**!\n"
    "Everyone else who pulled got **nothing**. Betrayal fills the room."
)
CHEESE_FIZZLE_TITLE = "🧀 The cheese expired..."
CHEESE_FIZZLE = "Nobody made a move in time. The **{cheese}** went stale and crumbled away. Nobody got anything."
CHEESE_MOUSE_NOTE = "\n\n🐭 **{mouse}** ({owner}'s mouse) is eyeing the cheese — only {owner} can let it pounce!"
CHEESE_MOUSE_EATEN_TITLE = "🐭 {mouse} gobbled the cheese!"
CHEESE_MOUSE_EATEN = (
    "**{mouse}** pounced on the **{cheese}** and scoffed the whole thing, overjoyed! 🧀✨\n"
    "The happy mouse scurried off and brought **everyone who pulled** "
    "**{sweetrolls}** sweetrolls each!\n\n{recipients}"
)
CHEESE_MOUSE_RECIPIENT = "{mention} +{sweetrolls} 🧁"
CHEESE_ADOPT_TITLE = "{mouse} wants to be adopted. Do you want to be their mouse parent?"
CHEESE_ADOPT_DESCRIPTION = (
    "{mention}, your bond with {mouse} has grown strong.\nReact with 👍 to ADOPT them or 👎 to REJECT them(and break its little heart)"
)
CHEESE_ADOPT_SUCCESS = "{mouse} happily chirps that it will serve you with all its heart!"
RACING_REL_NONE = "You have no relationships with any mice yet."
RACING_REL_TITLE = "Your Mouse Relationships"
RACING_REL_LINE = "**{name}** ({mouse_class}) - {points} points"
RACING_REL_FOOTER = "Page {page}/{total}"

# --------------------------------------------------------------------------- #
#  Pumpkin cog (commands + fight announcements; combat-log fragments stay inline)
# --------------------------------------------------------------------------- #
PUMPKIN_STATS_TITLE = "🎃 {name}'s Pumpkin Accounting Department 🎃"
PUMPKIN_STATS_BALANCE = "Available Pumpkin Balance"
PUMPKIN_STATS_BALANCE_VALUE = "**{balance} kg**"
PUMPKIN_STATS_FOOTER = "There's no such thing as enough pumpkin, go pull out some more!"
PUMPKIN_REP_TITLE = "👑 {name}'s Reputation 👑"
PUMPKIN_REP_DESCRIPTION = "**Title:** *{title}*\n**Reputation Score:** **{score}**"
PUMPKIN_REP_CAREER = "Career Stats"
PUMPKIN_REP_CAREER_VALUE = (
    "**Matches:** {matches} ({wins} W / {losses} L)\n**Win Rate:** {win_rate:.1f}%\n"
    "**Splat/Splat'd:** {splats} / {splatted} ({kd:.2f} K/D)"
)
PUMPKIN_REP_PERFORMANCE = "Performance"
PUMPKIN_REP_PERFORMANCE_VALUE = (
    "**Total Damage Dealt:** {damage}kg\n**Successful Dodges:** {dodges}\n"
    "**Last Stands:** {last_stands}\n**Attack Fizzles:** {fizzles}"
)
PUMPKIN_LOBBY_BASE = (
    "A team pumpkin deathmatch fight is starting! React to join and be assigned a team.\n"
    "Cost to join: **{cost}kg** of pumpkin.\n\n"
)
PUMPKIN_LOBBY_TITLE = "🎃 Pumpkin Deathmatch Lobby 💀"
PUMPKIN_LOBBY_CLOSING = "Sign-ups are closed in **{time}** seconds!"
PUMPKIN_LOBBY_CLOSED = "Lobby closed!"
PUMPKIN_JOIN_BUTTON = "Join Fight!"
PUMPKIN_JOIN_ALREADY = "You've already joined!"
PUMPKIN_JOIN_NO_PUMPKIN = "You don't have enough pumpkin to join! You need {cost}kg."
PUMPKIN_JOIN_GOURD = "🎃 {name} joined **Team {team}**!"
PUMPKIN_JOIN_REAPER = "💀 {name} joined **Team {team}**!"
PUMPKIN_NOT_ENOUGH = "Not enough players for a fight. Try again!"
PUMPKIN_RULES_TITLE = "🎃 How to Fight 🎃"
PUMPKIN_RULES_FOOTER = "The fight will start when {required} (55%) of players are ready. (60s timer)"
PUMPKIN_READY = "**{ready}/{total}** players are ready! The fight begins!"
PUMPKIN_NOT_READY = "Not enough players were ready (**{ready}/{required}**). The fight is cancelled."
PUMPKIN_BOT_JOINS = "{bot} joins **Team {team}** to balance the scales!"
PUMPKIN_TEAM_WINS_GOURD = "🎃 Team {team} Wins! 🎃"
PUMPKIN_TEAM_WINS_REAPER = "💀 Team {team} Wins! 💀"
PUMPKIN_TEAM_SPLATTED = "Team {team} has been completely splatted!"
PUMPKIN_OUT_OF_AMMO_TITLE = "🎃 Fight Over! Everyone's Out of Ammo! 🎃"
PUMPKIN_HP_WIN = "**Team {team} wins** by having more HP remaining!"
PUMPKIN_HP_DRAW = "It's a draw! Both teams have the same HP!"
PUMPKIN_VICTORIOUS = "**Team {team} is victorious!**"
PUMPKIN_DRAW = "The match is a draw!"
PUMPKIN_REWARD_WINNERS = "**Winning team survivors ({team}) rewarded!**\n"
PUMPKIN_REWARD_WINNER_LINE = "{mention} gains **{reward}kg** of pumpkin!\n"
PUMPKIN_REWARD_LOSERS = "\n**Losing team ({team}) consolation prize!**\n"
PUMPKIN_REWARD_LOSER_LINE = "{mention} gains **{reward}kg** of pumpkin.\n"
PUMPKIN_RANKS_HEADER = "**--- 🎃 Ranks Update 🎃 ---**"
PUMPKIN_RANK_LINE = "{mention}: **{sign}{change} Reputation** ({reasons})"

# ---------------------------------------------------------------------------
# Server config (per-guild settings admin)
# ---------------------------------------------------------------------------
SERVERCONFIG_GUILD_ONLY = "This command can only be used inside a server."
SERVERCONFIG_VIEW_TITLE = "Server settings for {guild}"
SERVERCONFIG_VIEW_FOOTER = "● = customised for this server · ○ = using the default"
SERVERCONFIG_UNKNOWN_KEY = "'{key}' is not a valid setting. Use `/serverconfig view` to see the available keys."
SERVERCONFIG_BAD_VALUE = "'{value}' is not valid for **{key}** — expected {expected}."
SERVERCONFIG_SET_OK = "**{key}** is now `{value}` for this server."
SERVERCONFIG_RESET_OK = "**{key}** has been reset to its default (`{value}`) for this server."
SERVERCONFIG_RESET_NOOP = "**{key}** was already using the default (`{value}`)."
SERVERCONFIG_EXPECT_ID = "a channel/role ID (a whole number)"
SERVERCONFIG_EXPECT_ID_LIST = "a list of IDs (numbers separated by spaces or commas)"
SERVERCONFIG_EXPECT_EMOJI = "an emoji or short text"

# ---------------------------------------------------------------------------
# Raid setups (gear lookup imported from Google Sheets)
# ---------------------------------------------------------------------------
RAID_NO_PERMISSION = "You need the {roles} role to manage raids."
RAID_GUILD_ONLY = "This command can only be used inside a server."
RAID_IMPORT_FAILED = "Import failed: {reason}"
RAID_CREATED_TITLE = "Raid imported: {name}"
RAID_CREATED_BODY = "Bound to {channel}.\n**{players}** players · **{stages}** stages."
RAID_CREATED_STAGES = "Stages"
RAID_CREATED_WARNINGS = "Heads up"
RAID_SETUPS_NONE = "No raid is set up in this channel yet. A raid manager can import one with `/create_raid`."
RAID_SETUPS_PICK_RAID = "Which raid?"
RAID_SETUPS_PICK_PLAYER = "Pick a player to see their setups:"
RAID_SETUPS_PLAYER_PLACEHOLDER = "Select a player…"
RAID_SETUPS_RAID_PLACEHOLDER = "Select a raid…"
RAID_SETUPS_HEADER = "{name} — {role} {cls}"
RAID_SETUPS_SLAYER = " · Slayer: {slayer}"
RAID_SETUPS_TITLE = "{player} · {raid}"
RAID_SETUPS_EMPTY_STAGE = "—"
RAID_SETUPS_NOT_FOUND = "I couldn't find '{player}' in this raid."
RAID_SETUPS_NOT_ON_ROSTER = (
    "Your Discord tag isn't on this raid's roster, so I can't show your setups. "
    "Ask a raid manager to add your Discord username (**{tag}**) to the sheet's Roster."
)
RAID_SETUPS_LOOKUP_DENIED = "Only raid managers can look up other players. Run `/setups` to see your own."
RAID_MARKERS_NONE = "No markers are set for this raid yet (the sheet's Instructions tab, cell A32, is empty)."
RAID_MARKERS_HINT = "💡 Need the raid markers? Use `/markers`."
RAID_DELETE_NONE = "There are no raids attached in this server."
RAID_DELETE_PROMPT = "Select the raid(s) to disconnect, then press **Disconnect**."
RAID_DELETE_PLACEHOLDER = "Choose raid(s) to disconnect…"
RAID_DELETE_ALL_OPTION = "All raids"
RAID_DELETE_NOTHING = "Nothing selected — pick at least one raid first."
RAID_DELETE_DONE = "Disconnected {count} raid(s): {names}"
RAID_SETUPS_UNKNOWN_FIGHT = "There's no fight called '{fight}'. Available: {fights}"
RAID_SETUPS_ALL_TITLE = "All setups · {raid}"
RAID_SETUPS_EMPTY_FIGHT = "No setups for this fight yet."
RAID_ROSTER_LINK = "🔗 Full roster / sheet: {url}"

# --------------------------------------------------------------------------- #
#  Quote cog — Guess the Quote
# --------------------------------------------------------------------------- #
QUOTE_TITLE = "🗣️ Guess the Quote"
QUOTE_INTRO = "Starting **Guess the Quote**! Reading the archives… get ready. 📜"
QUOTE_NOT_ENOUGH = "I don't have enough quotable messages logged yet to play. Go chat more first!"
QUOTE_SELF_DUEL = "You can't duel yourself — mention someone else to challenge!"
QUOTE_BOT_DUEL = "You can't duel a bot. We'd win, obviously."
QUOTE_NOT_PLAYING = "You're not in this game! Start your own with the quote command."
QUOTE_PROMPT = "**Who said this?**\n\n> {quote}"
QUOTE_REVEAL = "✅ It was **{name}**!"
QUOTE_SCORE_SOLO = "**Total:** {total}\n**Streak:** {streak} 🔥\n**This one's worth:** {worth}"
QUOTE_SCORE_LINE = "**{name}** — {total} pts · streak {streak}🔥 · worth {worth}"
QUOTE_LOG_HEADER = "Last answers"
QUOTE_LOG_CORRECT = "✅ {who} nailed it (+{pts}) — {answer}"
QUOTE_LOG_WRONG = "❌ {who} missed — it was {answer}"
QUOTE_LOG_IDLE = "😴 nobody answered — it was {answer}"
QUOTE_FOOTER = "Round {round} · {seconds}s to answer · ends after {idle} idle rounds"
QUOTE_FINAL_TITLE = "🏁 Game over!"
QUOTE_FINAL_SOLO = "You scored **{total}** points across {rounds} rounds!"
QUOTE_FINAL_WINNER = "🏆 **{name}** wins the duel with **{total}** points!"
QUOTE_FINAL_TIE = "🤝 It's a tie at **{total}** points!"
QUOTE_FINAL_LINE = "{name}: **{total}**"
QUOTE_LEADERBOARD_TITLE = "🏆 Guess the Quote — Top 10"
QUOTE_LEADERBOARD_LINE = "{medal} {mention} — **{best}**"
QUOTE_LEADERBOARD_EMPTY = "No scores yet — be the first to play!"

# --------------------------------------------------------------------------- #
#  Gilane cog
# --------------------------------------------------------------------------- #
GILANE_EVENT_TITLE = "🇧🇷 THE GILANE EVENT HAS STARTED"
GILANE_EVENT_DESC = "React with ✋ in the next **{seconds} seconds** to take part!"
GILANE_EVENT_CONCLUDED_TITLE = "🇧🇷 THE GILANE EVENT HAS CONCLUDED"
GILANE_EVENT_CONCLUDED_DESC = "Thank you for participating!"
GILANE_LEADERBOARD_TITLE = "🏆 Most Gilane events attended"
GILANE_LEADERBOARD_LINE = "{medal} {mention} — **{count}**"
GILANE_LEADERBOARD_EMPTY = "Nobody has attended a Gilane event yet. *Hä?*"
GILANE_CONFUSED_REDIRECT = "I am confused *und verwirrt*"
GILANE_COOLDOWN = "We haven't unconfused yet, try again next week"
GILANE_HAE = "Hä?"

# Reaction event
GILANE_REACTION_TITLE = "🖐️ THE GILANE REACTION EVENT"
GILANE_REACTION_DESC = "Everyone gets their Gilane! Spam {emoji} as fast as you can — you have **10 seconds**!"
GILANE_REACTION_HEADER = "Hä meters"
GILANE_REACTION_LINE = "{medal} {mention} — **{count}**"
GILANE_REACTION_RESULT_TITLE = "🎲 THE GILANE REACTION EVENT — RESULTS"
GILANE_REACTION_WINNER = "And the winner is… {winner}, {emoji}*"

# Spreadsheet event
GILANE_SPREADSHEET = "📊 A spreadsheet has been created: [{filename}](<{url}>)"

# Rename event
GILANE_RENAME_NICK = "Gilane"
GILANE_RENAME = "🇧🇷 Everyone who joined is now **Gilane**. *Wir sind alle Gilane.*"
GILANE_RENAME_NONE = "Gilane tried to rename everyone but couldn't manage it (missing permissions?). *Hä?*"
GILANE_SPREADSHEET_FILES = [
    "Gilane_Raid_Roster.xlsx",
    "Gilane_Attendance_2026.xlsx",
    "Gilane_Setups_FINAL_final_v3.xlsx",
    "Loot_Council_Notes.xlsx",
]
GILANE_SPREADSHEET_LINKS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://docs.google.com/spreadsheets/d/1JeC_2d7c758AAiSUgx_VgPbY19q5aTr6f8D3sl7pRDI/edit?pli=1&gid=823983221#gid=823983221",
    "https://elderscrolls.fandom.com/wiki/Gilane",
    "https://www.distillerie-mean.fr/wp-content/uploads/2023/10/produit-gilane-distillerie-mean.jpg",
    "https://www.houseofnames.com/dpreview/GILLAN/IR/Gilane/family-crest-coat-of-arms.png",
    "https://www.imdb.com/title/tt0450428/"

]

# --------------------------------------------------------------------------- #
#  Trial ranks cog
# --------------------------------------------------------------------------- #
# Everything the automatic ranking says out loud. Editable from the panel's
# Strings page like the rest of this file — the cog reads these at call time, so
# an edit lands without a restart. Repost the announcement after editing it, so
# the pinned message picks the new wording up.
TRIAL_ANNOUNCEMENT = (
    "## ✨ Dodo can do your ranks now!\n"
    "We're testing a new smarty pants system to update our ranks! "
    "Press the button to see where you stand. Only you will see it."
)
TRIAL_BUTTON_LABEL = "✨ CHECK MY RANK ✨"

TRIAL_HOW_IT_WORKS = (
    "## ✨ How it works\n"
    "• Every clear is worth points. **The newer and harder it is, the more it's worth.**\n"
    "• Only your **best clear per trial** counts, so a trifecta doesn't pay twice.\n"
    "• **More points, higher rank.** Hit the number, get the role.\n"
    "• New clear role? Your rank moves within seconds.\n\n"
    "The chart below has every price on it. 👇"
)

# {mention} is the person being asked.
TRIAL_CONSENT_ASK = (
    "Hey {mention}! I see that we have been updating your rank manually up until this "
    "point. Do you mind if I switch you to the new system?\n\n"
    "It reads the clears you already have and works your rank out from them. Nothing "
    "else about your roles changes."
)
TRIAL_CONSENT_YES = "Sure!"
TRIAL_CONSENT_EXPLAIN = "How exactly does it work?"
TRIAL_CONSENT_TIMEOUT = (
    "Hey, no biggie. Thank you for getting this far. Your rank stays exactly as it is, "
    "and you can press the button again whenever you like."
)
TRIAL_CONSENT_DONE = "You're on the automatic system now. Here's where you stand."
TRIAL_CONSENT_NOT_YOURS = "That question wasn't for you."

# The /rank card. {points} {needed} {next} {score} {target} are filled in by the cog.
TRIAL_CARD_TOP = "Top of the ladder. Nothing left to prove. 🏆"
TRIAL_CARD_PROGRESS = "**{needed}** more to reach {next}"
TRIAL_CARD_POINTS = "{points} points"
TRIAL_CARD_STEPS_TITLE = "Next steps:"
TRIAL_CARD_STEPS_EMPTY = (
    "Nothing on the board is priced for you yet. Ask an officer what's worth points."
)
TRIAL_CARD_OUTRO = (
    "You can use `/rank` anywhere on the server, any time, and I'll always be here too. ✨\n"
    "If you have a minute, let the mods know how well this matches your actual skill."
)
# The rank line at the top of the card. {rank} is a role mention, so it renders
# in the role's own colour; {stars} is the earned/unearned row. The "##" makes it
# a heading — drop to "###" for smaller, or "**{rank}**" for plain bold.
TRIAL_CARD_HEADING = "## {rank}\n{stars}"
TRIAL_CARD_FOOTER = "Only your best clear per trial counts towards the total."

# "I'd join a prog for one of those" — the one-click interest button.
TRIAL_INTEREST_BUTTON = "I'd join a prog for one of those 🔥"
TRIAL_INTEREST_THANKS = (
    "🔥 Noted, thank you!\n"
    "Once we have enough people with the same answers, one of the RLs will poke you. "
    "Thank you, and have a great day!"
)
TRIAL_INTEREST_TITLE = "Prog interest: {trial}"
TRIAL_INTEREST_NONE = "Nobody has put their hand up for **{trial}** yet."
TRIAL_INTEREST_SUMMARY = "**{count}** of {group} interested"
TRIAL_INTEREST_UNKNOWN = "I don't know a trial called **{trial}**."
TRIAL_INTEREST_BREAKDOWN = "What they still need"
TRIAL_INTEREST_WHO = "Who"
TRIAL_INTEREST_OVERVIEW = "Prog interest"
TRIAL_INTEREST_EMPTY = (
    "Nobody has put their hand up yet. The button appears under the recommendations "
    "on a `/rank` card."
)
TRIAL_CARD_NO_RANK = "No rank yet"

TRIAL_NO_LADDER_TITLE = "No ranks set up yet"
TRIAL_NO_LADDER_BODY = (
    "This server hasn't set its rank ladder up, so there's nothing to measure you "
    "against. Your clears still count, ask an officer."
)
TRIAL_NO_LADDER_POINTS = "from the clears you hold"

TRIAL_ERROR_UNAVAILABLE = "Ranking is not available right now, try again in a minute."
TRIAL_ERROR_GUILD_ONLY = "This only works inside the server."
