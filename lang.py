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
OWNER_SYNCED = "Synced {count} command(s)."
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
#  Chat cog (user-facing replies; the LLM system prompt stays in the cog)
# --------------------------------------------------------------------------- #
CHAT_API_ERROR = "Oh dear, my brain feels a bit fuzzy... I couldn't connect to my thoughts. (Error: {error})"
CHAT_REPLY_FALLBACK = "I... I think I forgot what I was saying. My apologies!"
CHAT_PARSE_ERROR = "My thoughts got all tangled up! Could you say that again?"

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
#  DnD cog
# --------------------------------------------------------------------------- #
DND_SESSION_CREATED = "Session **{title}** created and posted in {channel}."
DND_NO_SESSION_CHANNEL = "Error: Session channel not found."
DND_CHARACTER_CREATED = "Character **{name}** created and added to session {session_id}!"
DND_NO_CHARACTER = "No character found in this session. Please sign up first."
DND_ACTION_SUBMITTED = "Action submitted! Check the session channel for the outcome."
DND_GM_ERROR = "Error generating GM response. Please try again."
DND_INITIATIVE_INVALID = "Invalid input. Please enter a numeric value."
DND_SESSION_NOT_FOUND = "Session not found."
DND_INITIATIVE_RECORDED = "Your initiative ({value}) has been recorded."
DND_DICE_INVALID = "Invalid dice format. Please use NdM (e.g., 1d20)."
DND_DICE_RESULT = "Rolled {dice}: {results} (Total: {total})"
DND_ALREADY_SIGNED = "You are already signed up as **{name}**. Use Sign Off to remove yourself."
DND_SIGNED_OFF = "You have been signed off from this session. Your character data remains saved."
DND_NO_INITIATIVE = "No initiative order recorded."
DND_NEXT_TURN = "Next turn: **{name}** (Player ID: {player_id}) with initiative {initiative}."
DND_COMBAT_ENDED = "Combat ended."
DND_DM_ONLY = "Please use this command in DMs with the bot."
DND_SESSION_ENDED = "Session {session_id} has ended."
DND_NO_ACTIONS = "No actions recorded for this session."
DND_STATS_HEADER = "Session Stats:\n"
DND_STATS_LINE = "- {name}: {count} actions\n"
