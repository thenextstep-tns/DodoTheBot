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
