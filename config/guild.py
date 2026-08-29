"""
Per-guild settings — channel IDs, role IDs and the trap/autoban config for the
ESO for Dodos server.

These are currently hardcoded for the one guild. To support multiple servers,
this is the layer that would move into a per-guild MongoDB document loaded at
runtime (see the ``guild_config`` collection groundwork).
"""

import datetime

# --- Channels ---
E4D_LOG = 1230598294850240674
E4D_ROLE_LOG = 1230598294850240674
LOG_CHANNEL = 855701669168807936
MAIN_LOG = 791208411853357056
WAYSHRINE = 823096909219889162
SELECT_ROLES = 1238458858515599381
RANK_REQ = 860166864683925504
ADMIN = 853201230121402379
DODO_CHANNEL = 986220407210262528
PET_CHANNEL = 986220407210262528
ROLL_CHANNEL = 986220407210262528
HUNT_CHANNEL = 1019913722929627156
VALENTINE_CHANNEL = 1072068365117562981
WEEKLY_CHANNEL = 1068106379262431232
WEEKLY_MESSAGE = 1103190356226494565
META_CHANNEL = 1079374143759327312
META_MESSAGE = 1079375503770796092
IMPROVING_DPS_CHANNEL = 783631231392415774
TIME_CHANNEL = 1154493240880398416
FISHING_LOG = 1131600861290823803
FISHING_POND = 1131600702037295134
DAILY_CHANNEL = 1020315185942110218
DOTY_CHANNEL = 1183470942928765028
ANNOUNCEMENT_CHANNEL = 805879133930127371
OPEN_RAID_CHANNEL = 1292859278901776507
DND_FORUM_CHANNEL_ID = 1344418513950871722
CONCLAVE_CHANNEL = 1370389125689118750
NEW_LOG_CHANNEL = 791208411853357056
PAT_DECODE_CHANNEL = 844107411614466048
roll_log = 951482552684777482
xmas_hunt_submissions_channel = 1314741685640495164
xmas_hunt_channels = [783594414085111840, 986220407210262528, 805879133930127371, 1081456941232050216, 790181796578328609, 783630617438191627]
boss_spawn_channels = [986220407210262528]
public_channels = [
    783594414085111840, 986220407210262528, 1081595613340258314, 1192144724920893480, 1020227637513306142,
    1020222103473115216, 1020221746995011615, 1020220157878075433, 1081456941232050216, 799654786537881641,
    783631231392415774, 1081450115052605461,
]

# --- Welcome ---
# Posted by on_member_join. Placeholders: {mention} {name} {guild} {rank_req}
# {select_roles} — the two channel ones render as clickable channel mentions.
WELCOME_CHANNEL = WAYSHRINE
WELCOME_MESSAGE = (
    "Welcome, {mention}! If you want to raid with us, post your clearsies in {rank_req} "
    "and choose the trials you would like to join in {select_roles}. Ping any of the admins "
    "if you have questions, and happy raiding! :hearts:"
)
WELCOME_BACK_MESSAGE = (
    "Welcome back, {mention}! I have saved your roles from the last visit and reassigned them "
    "to you. If anything has changed, update your roles in {rank_req} and pick the trials you "
    "want to be notified about in {select_roles}. Ping any of the admins if you have questions, "
    "and happy raiding! :hearts:"
)

# --- Users / special IDs ---
BLACKLIST = []
CRINGE = [645590542125629470, 416986446612660235]
DODOLOVE = [727257254683869195]
SWEETROLLAMULET = [685399203996106764]

# --- Autoban / trap ---
TRAP_ROLE_ID = 1472509763467088045
ALERT_CHANNEL_ID = 1060472908188749904
BAN_EMOJI = "🔨"
SALUTE_EMOJI = "🫡"
TIMEOUT_DURATION = datetime.timedelta(days=1)
WAIT_DURATION = 8 * 60 * 60  # 8 hours in seconds

# --- Roles ---
lodestar_role = 1314761216836636702
base_roles_msg = 967767923794006026
starter_roles = [860463705107726367, 860463432598683668, 860463544306892801, 860465085783736331, 860456372595458069, 860465893305745438, 885850447137603596, 907295536598642738, 798229065898917889, 787933341806624818]
allowed_roles = [833693874219384833, 309719542115074049, 852793776064692264, 1081093094600085504, 783670458398277652]
player_roles = {"\U0001F6E1": 860466479400353853, "⚕": 860466414237384714, "⚔": 860466132380549130}

veteran = [798230299389460490, 861297811592839188, 861298098344558603, 861298387802783754,
           861298603821629490, 861300841536815124, 861300902450167809, 861301829047287888,
           861603555134668800, 861604679221641267, 861605625809207346, 967757139072417832]
veteranRemove = [798229065898917889, 789767590149881856, 798228054118760459, 798228055625695242]
legend = [789767611269120020, 861297811592839188, 861298098344558603, 861298387802783754, 861300693477359656,
          861301036127223868, 861301105605738497, 861603298176139294, 861603911281541120,
          861605027672227881, 861605943002005504]

# --- Trials & clears ---
trial_ping_roles = {
    "Normal Trials": 846300383982125088,
    "Aetherian Archive": 819566620183494706,
    "Hel Ra Citadel": 819566756992909353,
    "Sanctum Ophidia": 819566868649082891,
    "Maw of Lorkhaj": 819566954943479839,
    "Halls of Fabrication": 819568455056621610,
    "Asylum Sanctorium": 819567118710079509,
    "Cloudrest": 829297389280952320,
    "Sunspire": 819568232121761832,
    "Kyne's Aegis": 819568879906324490,
    "Rockgrove": 844105629445521429,
    "Dreadsail Reef": 967759030414086174,
    "Sanity's Edge": 1094675660158533744,
    "Lucent Citadel": 1238462328304046131,
    "Ossein Cage": 1362424126249111562,
}
trial_abbreviations = {
    "Normal Trials": "Normal Trial",
    "Aetherian Archive": "vAA",
    "Hel Ra Citadel": "vHRC",
    "Sanctum Ophidia": "vSO",
    "Maw of Lorkhaj": "vMoL",
    "Halls of Fabrication": "vHoF",
    "Asylum Sanctorium": "vAS",
    "Cloudrest": "vCR",
    "Sunspire": "vSS",
    "Kyne's Aegis": "vKA",
    "Rockgrove": "vRG",
    "Dreadsail Reef": "vDSR",
    "Sanity's Edge": "vSE",
    "Lucent Citadel": "vLC",
}
vet_clears = {
    "Aetherian Archive": 819568084376485888,
    "Hel Ra Citadel": 861297881117098015,
    "Sanctum Ophidia": 861298326963355719,
    "Maw of Lorkhaj": 861300841536815124,
    "Halls of Fabrication": 861300902450167809,
    "Asylum Sanctorium": 861298603821629490,
    "Cloudrest": 861603555134668800,
    "Sunspire": 861301829047287888,
    "Kyne's Aegis": 861604679221641267,
    "Rockgrove": 861605625809207346,
    "Dreadsail Reef": 967757139072417832,
    "Sanity's Edge": 1115516163338797076,
    "Lucent Citadel": 1247426403084009473,
}
hm_partial_clears_1_boss = {
    "Asylum Sanctorium": 861298486451372032,
    "Cloudrest": 861603682482782258,
    "Sunspire": 861301932584730654,
    "Kyne's Aegis": 861604784112009226,
    "Rockgrove": 861605738181558273,
    "Dreadsail Reef": 967757441196519424,
    "Sanity's Edge": 1115516265197490207,
    "Lucent Citadel": 1247554305108742155,
}
hm_partial_clears_2_boss = {
    "Asylum Sanctorium": 861298689796210740,
    "Cloudrest": 861603805682597898,
    "Sunspire": 861603155951222794,
    "Kyne's Aegis": 861604898105983007,
    "Rockgrove": 861605754368032829,
    "Dreadsail Reef": 967757626106597446,
    "Sanity's Edge": 1115516448513736784,
    "Lucent Citadel": 1247554024212004985,
}
# NOTE (pre-existing): the original config defined hm_clears twice — a populated
# dict immediately overwritten by an empty one — so at runtime it was empty and
# the PAT decoder never assigned full-HM roles. Preserved as empty for parity.
hm_clears = {}

user_ranks = ["Casual", "Raider", "Veteran", "Expert", "Master", "Legend", "Myth"]
rank_roles = {}

reaction_roles = {
    1238462248167673889: {  # Trial Roles
        "\U0001F9D9": 819566620183494706, "\U0001F4A3": 819566756992909353, "\U0001F40D": 819566868649082891,
        "\U0001F640": 819566954943479839, "\U0001F916": 819568455056621610, "\U0001F9BF": 819567118710079509,
        "\U0001F40C": 829297389280952320, "\U0001F432": 819568232121761832, "\U0001F9DB": 819568879906324490,
        "\U0001F525": 844105629445521429, "\U00002693": 967759030414086174, "\U0001F4A4": 1094675660158533744,
        "\U0001F3F0": 1238462328304046131, "\U000026D3": 1362424126249111562,
    },
    1238466517969141831: {  # Other content notifications
        "\U0001F476": 846300383982125088, "\U0001F4AA": 844105870392819723, "\U0001F393": 844160810813358100,
        "\U000023F0": 1238530302805020793, "\U0001F985": 944514526055915520, "\U0001F981": 944515219701530634,
        "\U0001F409": 944515630642638888, "\U00002694": 844473322170351637, "\U0001F419": 1246324926521020457,
    },
    1238534410240921713: {  # Social roles
        "\U0001F46A": 807064226697969686, "\U0001F973": 801802675678085121, "\U0001F3E1": 844099301021712384,
        "\U0001FA9A": 844472691372064788, "\U00002753": 967760954215530496,
    },
}

# --- Moderation ---
restricted_strings = ["discord.gg", "@everyone", "@here"]
allowed_links = [
    "discord.gg/8ewt2Fe", "discord.gg/esou", "discord.gg/uesp", "discord.gg/ZaPwNHKQBg",
    "discord.gg/35FMqVQJgY", "discord.gg/enterthedominion", "discord.gg/FAU9A2pBY7",
    "discord.gg/5NaETqTjDD", "discord.gg/fmrgcr4Dc5", "dodos.fun", "discord.gg/e4d",
    "discord.gg/tBdB6KZzmf", "discord.gg/jEXVVgBTUP", "discord.gg/7xjfDDx6cX", "discord.gg/78xRCj4QVa",
    "discord.gg/fQXqfWDmWa", "discord.gg/pXV23eZZ86", "discord.gg/MuwsNJcqEw",
    "discord.gg/healershaven", "discord.gg/mindcleaver", "discord.gg/dpsnerds", "discord.gg/B6cyn3uMr",
    "discord.gg/68PsPTmk3P",
]
anti_griefing_time = 10
anti_griefing_limit = 5
