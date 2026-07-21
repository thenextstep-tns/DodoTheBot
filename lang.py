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
