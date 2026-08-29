"""
Gameplay constants and static content: embed colours, presence statuses,
economy/relationship tuning, and the big pools of GIFs, quotes and self-care
prompts the fun cogs draw from.

Nothing here is secret or guild-specific — see ``config.secrets`` and
``config.guild`` for those.
"""

# --- Embed colours ---
main_color = 0xD75BF4
error = 0xE02B2B
success = 0x42F56C
warning = 0xF59E42
info = 0x4299F5

# --- Presence statuses ("Dodo is playing ...") ---
statuses = [
    "piano! Try typing dodo wisdom in the chat!",
    "it safe! Have you tried dodo future command?",
    "the Dodo card! Try catching a cat using dodo cat and summoning them with dodo summon (name of the cat here)!",
    "the goat. Steal a sweetroll from other players by pressing an emoji!",
    "gooseberry. Have you tried dodo parse? How about dodo pp?",
    "a big part in society. If you type 'schedule' or 'trials' i can send you our current schedule in DMs!",
    "it cool. Spread more love by typing dodo love (name of the user) in the chat!",
    "the system. If you wanna check how many cats you have, you can use dodo showcats command!",
    "the fool. If you want to catch a dog, spawn one with dodo dog",
    "with itself. Try dodo roll!",
    "ESO. If you wanna see the best or the worst parses, try dodo topparses/dodo bottomparses!",
    "dead",
    "on Fox's nerves",
    "dumb",
    "with fire",
]

# --- Relationship / pet system tuning ---
MOUSE_ADOPTION_RANK = 250        # Relationship points needed for adoption
RELATIONSHIP_BASE_POINTS = 20    # Base points in the relationship calculation formula
CHEESE_DROP_THRESHOLD = 985      # In a 0-1000 roll, drop cheese if roll > this (~1%)
STAR_INSPIRATION_BOOST = 5       # Extra steps when the starry-eyes (race) event triggers
STAR_INSPIRATION_DURATION = 5    # Number of moves the starry boost lasts

# --- Cheese co-op stretch minigame ---
# When a dropped 🧀 is grabbed, we roll which cheese it is (weighted by ``weight``).
# Players 👌-pull to stretch it: every pull adds a random amount of stretch and
# grows the pot, but risks crossing a HIDDEN snap limit rolled between ``snap_min``
# and ``snap_max`` for that drop. Relationship reward = the stretch shared out,
# then multiplied by the cheese's ``like_mult`` and rounded up (rarer cheese is
# adored by the mice, so it pays much more). ``image`` is a small thumbnail shown
# in the embed so players can recognise each cheese.
# name, emoji, weight, snap_min, snap_max, like_mult, image.
CHEESE_TYPES = [
    {"name": "Mozzarella", "emoji": "🧀", "weight": 50, "snap_min": 12, "snap_max": 25, "like_mult": 1,
     "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Mozzarella_di_bufala3.jpg/250px-Mozzarella_di_bufala3.jpg"},
    {"name": "Cheddar", "emoji": "🧀", "weight": 25, "snap_min": 6, "snap_max": 15, "like_mult": 2,
     "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/Somerset-Cheddar.jpg/250px-Somerset-Cheddar.jpg"},
    {"name": "Gouda", "emoji": "🧀", "weight": 14, "snap_min": 5, "snap_max": 12, "like_mult": 1.5,
     "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Chesses_gouda_affinage.JPG/250px-Chesses_gouda_affinage.JPG"},
    {"name": "Aged Gruyere", "emoji": "🧀", "weight": 8, "snap_min": 4, "snap_max": 10, "like_mult": 5,
     "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Gruyere_alpage_th_wa.jpg/250px-Gruyere_alpage_th_wa.jpg"},
    {"name": "Aged Parmigiano Reggiano", "emoji": "🧀", "weight": 3, "snap_min": 3, "snap_max": 6, "like_mult": 10,
     "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/Parmigiano_Reggiano%2C_Italien%2C_Europ%C3%A4ische_Union.jpg/250px-Parmigiano_Reggiano%2C_Italien%2C_Europ%C3%A4ische_Union.jpg"},
]
CHEESE_PULL_STRENGTHS = [2, 3, 4]  # A single 👌-pull adds a random amount from this pool
CHEESE_STEAL_DIVISOR = 5         # A thief grabs ceil(stretch / this) for themselves
CHEESE_EVENT_TIMEOUT = 25        # Seconds of inactivity before the cheese hardens (fizzle)
CHEESE_MOUSE_CHANCE = 0.02       # Per-pull chance an adopted mouse peeks out to snatch the cheese (~1 in 50)
CHEESE_MOUSE_SWEETROLLS = 5      # Sweetrolls the mouse brings each participant if it eats the cheese
# Hidden owner-only trigger: if a bot owner types this phrase anywhere in a
# message, a cheese is force-dropped on it (bypassing the random roll).
CHEESE_SECRET_TRIGGER = "abracadabrie"

# --- Sweetrolls ---
SWEETROLL_NEEDED = 98
SWEETROLL_COOLDOWN = 3
SWEETROLL_GIFTING = 80

# --- Parses ---
max_parse = 210000
max_parse_championship = 210000
dummy_health = 21000000

# --- Dodo Roll ---
roll_limit = 50000000
roll_challenge_emoji = {"\U0001F3B2": 0, "⛔": 1}
roll_duel_emoji = {"\U0001F3B2": 0}
dice_gifs = [
    "https://tenor.com/tXuH.gif", "https://tenor.com/bmrvd.gif", "https://tenor.com/bkjAq.gif",
    "https://tenor.com/bKduS.gif", "https://tenor.com/9MKe.gif", "https://tenor.com/blN5e.gif",
    "https://tenor.com/Uylc.gif", "https://tenor.com/6li4.gif", "https://tenor.com/bPeZX.gif",
    "https://tenor.com/bamSR.gif", "https://tenor.com/bdcvZ.gif", "https://tenor.com/2dy0.gif",
    "https://tenor.com/bia8j.gif", "https://tenor.com/bsifJ.gif", "https://tenor.com/bsifJ.gif",
    "https://tenor.com/vwYD.gif", "https://tenor.com/1ty8.gif", "https://tenor.com/L81P.gif",
    "https://tenor.com/NvVe.gif", "https://tenor.com/3OzQ.gif", "https://tenor.com/bx2Pd.gif",
]

# --- Cringe challenge prompts ---
CHALLENGES = [
    "post an embarrassing childhood photo",
    "share your worst joke",
    "tell us about your last date in detail",
    "describe your most awkward moment",
    "post a video of you doing the floss dance",
    "sing a verse from a cringey pop song",
    "imitate a meme in real life and share the picture",
    "share a story about a time you got rejected",
    "make a pun about your job or school",
    "wear socks with sandals and show us the result",
    "write a love poem about pizza",
    "try to touch your nose with your tongue in a video",
    "share your most cringeworthy text message",
    "explain why pineapple on pizza is good/bad",
    "do your best impression of a famous celebrity",
    "share a photo of your most disastrous haircut",
    "wear your clothes backwards for an hour and share a pic",
    "attempt a magic trick and fail spectacularly",
    "draw a self-portrait with your non-dominant hand",
    "create a haiku about your last meal",
    "share the last selfie you took, no matter how bad",
    "try to lick your elbow and post the video",
    "post your worst school photo",
    "write a cringe-worthy status and post it on social media",
    "share a picture of your oldest pair of footwear",
    "do your makeup in the dark and share the photo",
    "share an old poem or song you wrote",
    "take a silly selfie with the nearest object to you",
    "imitate a famous historical figure in a selfie",
    "record yourself doing a dramatic reading of a shampoo bottle",
]

# --- Valentine / kitten GIF pools ---
valentinegifs = [
    "https://tenor.com/bRGK9.gif", "https://tenor.com/bUem4.gif", "https://tenor.com/bjloR.gif",
    "https://tenor.com/bg6SN.gif", "https://tenor.com/bRfXI.gif", "https://tenor.com/t8Nt.gif",
    "https://tenor.com/bSvXT.gif", "https://tenor.com/bVHEe.gif",
]

kittengifs = [
    "https://tenor.com/YMKv.gif", "https://tenor.com/bTCjb.gif", "https://tenor.com/bQ9Vs.gif",
    "https://tenor.com/baBD1.gif", "https://tenor.com/bRtsQ.gif", "https://tenor.com/bNbkO.gif",
    "https://tenor.com/bUsxe.gif", "https://tenor.com/bPetD.gif", "https://tenor.com/5TAg.gif",
    "https://tenor.com/bU1aM.gif", "https://tenor.com/bgT0M.gif", "https://tenor.com/bICaS.gif",
    "https://tenor.com/bVMh8.gif", "https://tenor.com/bSc6x.gif", "https://tenor.com/bRxYt.gif",
    "https://tenor.com/bTHIm.gif", "https://tenor.com/bN9vV.gif", "https://tenor.com/bIVJA.gif",
    "https://tenor.com/bWF32.gif", "https://tenor.com/bR6xP.gif", "https://tenor.com/bD9vu.gif",
    "https://tenor.com/bIMIq.gif", "https://tenor.com/bWkER.gif", "https://tenor.com/bnABv.gif",
    "https://tenor.com/bbfmP.gif", "https://tenor.com/bOrCp.gif", "https://tenor.com/bICal.gif",
    "https://tenor.com/bipju.gif", "https://tenor.com/baBD1.gif", "https://tenor.com/bTjwk.gif",
    "https://tenor.com/bwSs8.gif", "https://tenor.com/bKEJM.gif", "https://tenor.com/bR2BY.gif",
    "https://tenor.com/bLImO.gif", "https://tenor.com/bOT2u.gif", "https://tenor.com/bU1aM.gif",
    "https://tenor.com/bQdlV.gif", "https://tenor.com/bT9Hn.gif", "https://tenor.com/bPdwR.gif",
    "https://tenor.com/bAaqn.gif", "https://tenor.com/bUhIj.gif", "https://tenor.com/bTLcR.gif",
    "https://tenor.com/biqXZ.gif", "https://tenor.com/bRXH9.gif", "https://tenor.com/bR1aP.gif",
    "https://tenor.com/bTY2Q.gif", "https://tenor.com/bVmnP.gif", "https://tenor.com/bx3bm.gif",
    "https://tenor.com/bFp3F.gif", "https://tenor.com/6zo3.gif", "https://tenor.com/bEwfK.gif",
    "https://tenor.com/bhBlM.gif", "https://tenor.com/bmmTP.gif", "https://tenor.com/bfI1I.gif",
    "https://tenor.com/PFAY.gif", "https://tenor.com/oZ52.gif", "https://tenor.com/bhvKs.gif",
    "https://tenor.com/rExj.gif", "https://tenor.com/bc25m.gif", "https://tenor.com/Ep58.gif",
    "https://tenor.com/o0f1.gif", "https://tenor.com/3WZV.gif", "https://tenor.com/bdR6d.gif",
    "https://tenor.com/bG96Z.gif", "https://tenor.com/7Mw3.gif", "https://tenor.com/bq11H.gif",
    "https://tenor.com/sUzo.gif", "https://tenor.com/3J6F.gif", "https://tenor.com/09BV.gif",
    "https://tenor.com/2u00.gif", "https://tenor.com/bWM6c.gif", "https://tenor.com/bnz1o.gif",
    "https://tenor.com/bLVHC.gif", "https://tenor.com/bKT5n.gif", "https://tenor.com/bq7cR.gif",
    "https://tenor.com/bmeQT.gif", "https://tenor.com/bF4EM.gif", "https://tenor.com/bfNqk.gif",
    "https://tenor.com/bheX2.gif", "https://tenor.com/9fjE.gif", "https://tenor.com/bwRvA.gif",
    "https://tenor.com/bggkn.gif", "https://tenor.com/bgSd9.gif", "https://tenor.com/bfAq7.gif",
    "https://tenor.com/bDbBm.gif", "https://tenor.com/bn67r.gif", "https://tenor.com/bl98j.gif",
    "https://tenor.com/8bZ6.gif", "PANIC! https://tenor.com/9TKd.gif", "https://tenor.com/beMDz.gif",
]

# --- Waifu quotes ---
waifuquotes = [
    "The world is not beautiful. And that, in a way, lends it a sort of beauty",
    "Even if a mirror doesn't show you, you will still appear in my eyes",
    "Sometimes we all just need to be shown a little kindness",
    "It is more fun when it hurts a little",
    "It is because I know darkness that my singing can have light",
    "The time we spend apart will be an instant in the flow of universal time.",
    "There is a special force that binds us, defying even time and space. Not even the laws of the universe can stop it... I knew it is gentle pull would prevail, it is the desire to be reunited with someone who is important to you. That pull is what brought us together.",
    "May the stars shine down on you...",
    "You are always going to be with me, and so will everyone else. Because from now on, I will be everywhere for all time. Even if you cannot see me or hear me, I will be right there by your side",
    "As long as you do not yearn for hope, you will never fall victim to despair",
    "No matter what painful things happens, even when it looks like you will lose... when no one else in the world believes in you... when you do not even believe in yourself... I will believe in you!",
    "If I do not do something, nothing iss ever going to change.",
    "There is nothing more intimate then living inside your head",
    "What is done out of love is beyond good and evil",
]

# --- Self-care prompts: [text, reward, min_minutes, max_minutes] ---
selfCareOptions = [
    ["Take a short nap when you can", 50, 20, 60],
    ["Go for a walk", 75, 30, 120],
    ["Treat yourself to a snack", 25, 5, 10],
    ["Practice yoga", 75, 30, 60],
    ["Draw something", 75, 30, 60],
    ["Exercise", 100, 10, 90],
    ["Try to cook something for yourself", 100, 30, 90],
    ["Journal your thoughts", 75, 15, 30],
    ["Listen to your favourite music", 50, 10, 60],
    ["Write down 3 things you like about yourself", 50, 5, 20],
    ["Write down 3 things you are thankful for", 50, 5, 20],
    ["Read a book", 50, 20, 90],
    ["Take a relaxing shower/bath", 50, 10, 60],
    ["Sort out your room", 100, 30, 60],
    ["Take a step outside and observe nature", 75, 30, 120],
    ["Watch your favourite movie", 50, 60, 180],
    ["Write down your goals for this week", 50, 10, 20],
    ["Go cloud watching", 50, 20, 60],
    ["Paint something", 75, 30, 60],
    ["Bake something", 80, 60, 120],
    ["Try a new hobby", 100, 30, 90],
    ["Catch up with a friend", 75, 10, 60],
    ["Make home/room decor", 100, 15, 90],
    ["Make a smoothie and enjoy it", 60, 10, 20],
    ["Have a cup of tea and close your eyes", 35, 5, 10],
    ["Drink some water and relax", 25, 5, 10],
    ["Do some creative writing", 80, 20, 60],
    ["Try/order new foods", 75, 30, 60],
    ["Do breathing exercises", 60, 5, 10],
    ["Full body stretch", 50, 10, 30],
    ["Open up all windows for a bit and let some fresh air in", 50, 5, 10],
    ["Write down 3 weird things you are grateful for", 50, 15, 25],
    ["Change into clothes that feel good", 50, 5, 10],
    ["Turn off your computer and your phone when you can", 75, 30, 90],
    ["Do a puzzle or play a board game", 50, 30, 90],
    ["Explore a local museum or art gallery", 65, 60, 180],
    ["Practice gratitude journaling", 55, 15, 30],
    ["Go on a social media detox for a day", 70, 60, 180],
    ["Try a new type of workout class", 75, 45, 90],
    ["Visit a botanical garden or nature reserve", 65, 60, 180],
    ["Have a DIY spa day at home with face masks and relaxation", 60, 30, 60],
    ["Watch a comedy show or stand-up special", 50, 30, 90],
    ["Take a dance break and move to your favorite music", 40, 5, 15],
    ["Write a letter to your future self", 60, 15, 30],
    ["Try a guided meditation or mindfulness exercise", 70, 10, 30],
    ["Do a random act of kindness for someone else", 60, 15, 30],
    ["Have a picnic in the park or backyard", 70, 30, 90],
    ["Do a home workout or follow an exercise video", 65, 20, 60],
    ["Create a vision board with your goals and dreams", 70, 30, 60],
    ["Take a digital detox and disconnect from technology", 80, 60, 180],
    ["Try a new recipe or experiment with cooking", 75, 30, 90],
    ["Engage in a creative hobby like painting or knitting", 80, 30, 90],
    ["Practice deep breathing exercises", 55, 5, 15],
    ["Have a relaxing bubble bath with candles and music", 60, 30, 60],
    ["Spend time in nature, go for a hike or nature walk", 70, 60, 120],
    ["Listen to a podcast or audiobook", 45, 30, 90],
    ["Try a new form of art, such as pottery or sculpting", 75, 60, 120],
    ["Have a movie marathon with your favorite films", 55, 120, 240],
    ["Take a scenic drive and enjoy the views", 70, 60, 120],
    ["Write a gratitude letter to someone you appreciate", 75, 15, 30],
    ["Try a new form of exercise, such as pilates or kickboxing", 80, 45, 90],
    ["Do a DIY project or crafts", 70, 30, 90],
    ["Practice mindfulness and meditation", 65, 10, 30],
    ["Have a digital declutter and organize your files", 60, 30, 60],
    ["Take a day trip to a nearby town or city", 85, 120, 240],
    ["Try a new type of tea or coffee", 50, 10, 20],
    ["Write a journal entry about your day or emotions", 55, 15, 30],
    ["Attend a virtual workshop or class on a topic of interest", 70, 30, 90],
    ["Create a self-care playlist with your favorite songs", 50, 15, 30],
    ["Practice self-compassion and positive self-talk", 55, 10, 20],
    ["Engage in a mindful eating practice and savor your meals", 60, 15, 30],
    ["Do a nature-inspired art project, such as leaf printing", 70, 30, 60],
    ["Watch the sunset or sunrise", 60, 15, 30],
    ["Take some time off from work or responsibilities", 75, 240, 480],
    ["Try a new type of massage or bodywork", 70, 60, 120],
    ["Engage in a brain teaser or puzzle game", 55, 30, 60],
    ["Write down your dreams or create a dream journal", 50, 10, 20],
    ["Have a technology-free hour and focus on offline activities", 65, 60, 120],
    ["Do a random act of kindness for yourself", 60, 10, 20],
    ["Explore a new neighborhood in your city or town", 70, 60, 120],
    ["Create a calming and cozy reading nook", 60, 30, 60],
    ["Try a new form of art therapy, such as mandala drawing", 70, 30, 60],
    ["Engage in a mindful walking or nature meditation", 65, 20, 45],
    ["Watch a motivational or inspiring TED Talk", 50, 15, 30],
    ["Try a new type of herbal tea or infusion", 55, 10, 20],
    ["Take a day trip to the beach or a nearby water body", 75, 120, 240],
    ["Practice aromatherapy with essential oils", 60, 15, 30],
    ["Try a new form of dance, such as salsa or ballet", 75, 45, 90],
    ["Do a digital detox and spend time in nature", 70, 60, 180],
    ["Create a gratitude jar and add positive moments", 60, 15, 30],
    ["Engage in a self-care spa day with facials and massages", 70, 60, 120],
    ["Practice laughter therapy and watch a comedy show", 55, 30, 60],
    ["Explore a local farmer's market or food festival", 65, 60, 120],
    ["Try a new form of relaxation, such as Tai Chi or Qigong", 75, 30, 60],
    ["Write a list of affirmations and positive statements", 50, 10, 20],
    ["Go for a challenging hike or mountain climb", 80, 120, 240],
    ["Engage in a high-intensity workout or weightlifting session", 85, 30, 90],
    ["Try a new outdoor activity, such as fishing or kayaking", 75, 60, 120],
    ["Attend a sports event or participate in a team sport", 80, 120, 240],
    ["Spend time in nature by camping or backpacking", 75, 120, 240],
    ["Learn a new skill, such as woodworking or car maintenance", 70, 30, 90],
    ["Take a road trip to explore new destinations", 80, 240, 480],
    ["Engage in a competitive game or sport with friends", 75, 30, 90],
    ["Try a new style or fashion experiment with your wardrobe", 65, 15, 30],
    ["Spend time in a workshop or garage working on DIY projects", 70, 30, 90],
    ["Have a whiskey or beer tasting experience", 60, 30, 60],
    ["Attend a concert or music festival of your favorite genre", 75, 120, 240],
    ["Explore classic car shows or museums", 70, 60, 120],
    ["Take a motorcycle ride and enjoy the freedom of the open road", 80, 60, 120],
    ["Engage in a friendly competition, such as pool or darts", 65, 30, 60],
    ["Try a new form of martial arts or self-defense training", 75, 45, 90],
    ["Spend time at a shooting range and practice marksmanship", 70, 30, 60],
    ["Engage in a strategic board game or video game", 65, 30, 60],
    ["Attend a car race or driving experience", 75, 120, 240],
    ["Challenge yourself with a tough obstacle course or adventure race", 80, 60, 120],
    ["Try a new outdoor cooking or grilling recipe", 70, 30, 60],
    ["Spend time in a quiet cabin or retreat in nature", 75, 120, 240],
    ["Engage in DIY home improvement projects", 70, 60, 180],
    ["Attend a professional development or leadership workshop", 65, 30, 90],
    ["Learn to play a musical instrument or practice your skills", 70, 30, 90],
    ["Go on a fishing trip and enjoy the tranquility of nature", 75, 120, 240],
    ["Engage in mindfulness through meditation or deep breathing", 60, 10, 30],
    ["Spend time in a woodworking or metalworking workshop", 70, 30, 90],
    ["Try a new form of outdoor exercise, such as trail running", 75, 30, 60],
    ["Watch adorable animal videos or gifs", 50, 10, 20],
    ["Have a cozy movie night with your favorite romantic comedies", 60, 60, 120],
    ["Visit a pet cafe or spend time with animals", 65, 30, 60],
    ["Try a new cute and fun workout, like hula hooping or dance aerobics", 70, 30, 60],
    ["Create a scrapbook or photo album of happy memories", 60, 30, 60],
    ["Write and send a heartfelt letter or card to someone special", 55, 15, 30],
    ["Have a pampering self-care session with face masks and bubble baths", 70, 30, 60],
    ["Visit a local park or botanical garden to admire beautiful flowers", 60, 30, 60],
    ["Do a DIY craft project, like making adorable plush toys or keychains", 70, 30, 60],
    ["Listen to soothing ASMR videos or podcasts for relaxation", 50, 10, 30],
    ["Have a picnic with cute and colorful snacks", 60, 30, 60],
    ["Try a new cute hairstyle or experiment with hair accessories", 55, 15, 30],
    ["Engage in a coloring or doodling session with cute coloring books", 60, 30, 60],
    ["Watch a feel-good animated movie or cartoon series", 55, 30, 120],
]

# --- Misc reaction sets ---
addons = {"\U0001F440": 0}

# --- Pets ---
# Pet class rows: [Class name, StrMin, StrMax, AgiMin, AgiMax, IntMin, IntMax, CharmMin, CharmMax]
pet_emoji = {"\U0001F431": 0, "\U0001F436": 1}
versus = "versus.png"
catclasses = [
    ["Chonk", 30, 50, 1, 7, 2, 10, 5, 15],
    ["Zoomies Pro", 5, 15, 30, 50, 1, 7, 2, 10],
    ["Smarty Pants", 2, 10, 5, 15, 30, 50, 1, 7],
    ["Aww summoner", 1, 7, 2, 10, 5, 15, 30, 50],
]
dogclasses = [
    ["Working Dog", 40, 50, 1, 5, 3, 8, 20, 30],
    ["Hound Dog", 20, 30, 40, 50, 1, 5, 3, 8],
    ["Herding Dog", 3, 8, 20, 30, 40, 50, 1, 5],
    ["Companion Dog", 1, 5, 3, 8, 20, 30, 40, 50],
]
pet_actions = {"\U0001F41F": "Toggle Fishing", "\U0001F4AA": "Send the cat to the gym",
               "\U0001F94A": "Put this cat on your fighting roster"}
fishing_result_actions = {"\U0001F392": "Put in the goodies bag", "\U0001F4B0": "Sell", "\U0001F4A5": "Throw away"}
fishing_cost = 10

# --- Gym / fighting ---
gym_cost = 50
fighting_cost = 100
fight_actions = {"✊": 0, "\U0001F4A8": 1, "\U0001F6E1": 2, "\U0001F60D": 3}

# --- Items ---
item_qualities = {"\U0001F7E2": "Broken", "\U0001F535": "Affordable", "\U0001F7E3": "Superb", "\U0001F7E1": "Perfect", "\U0001F7E0": "Unique"}
item_types = {"\U0001F5D1": "Trash", "\U0001F6E1": "Armor", "\U0001F354": "Buff food", "\U0001F48E": "Treasure"}
