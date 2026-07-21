""""
Copyright © Krypton 2021 - https://github.com/kkrypt0nn (https://krypt0n.co.uk)
Description:
This is a template to create your own discord bot in python.

Version: 4.1
"""

import json
import os
import platform
import random
import sys

import pymongo
from pymongo import MongoClient
from datetime import date

import dns
import asyncio

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import tasks, commands
from disnake.ext.commands import Bot
from disnake.ext.commands import Context
from disnake.utils import get

import exceptions

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)
        
if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

"""	
Setup bot intents (events restrictions)
For more information about intents, please go to the following websites:
https://docs.disnake.dev/en/latest/intents.html
https://docs.disnake.dev/en/latest/intents.html#privileged-intents


Default Intents:
intents.bans = True
intents.dm_messages = False
intents.dm_reactions = False
intents.dm_typing = False
intents.emojis = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_typing = False
intents.guilds = True
intents.integrations = True
intents.invites = True
intents.reactions = True
intents.typing = False
intents.voice_states = False
intents.webhooks = False

Privileged Intents (Needs to be enabled on dev page), please use them only if you need them:
intents.members = True
intents.messages = True
intents.presences = True
"""

intents = disnake.Intents.default()
intents.reactions = True
intents.members = True

bot = Bot(command_prefix=config["prefix"], intents=intents)

ischatting = 0

@bot.event
async def on_ready() -> None:
    """
    The code in this even is executed when the bot is ready
    """
    print(f"Logged in as {bot.user.name}")
    print(f"disnake API version: {disnake.__version__}")
    print(f"Python version: {platform.python_version()}")
    print(f"Running on: {platform.system()} {platform.release()} ({os.name})")
    print("-------------------")
    status_task.start()


@tasks.loop(minutes=3.0)
async def status_task() -> None:
    """
    Setup the game status task of the bot
    """
    statuses = config_py.statuses
    await bot.change_presence(activity=disnake.Game(random.choice(statuses)))


# Removes the default help command of discord.py to be able to create our custom help command.
bot.remove_command("help")


def load_commands(command_type: str) -> None:
    for file in os.listdir(f"./cogs/{command_type}"):
        if file.endswith(".py"):
            extension = file[:-3]
            try:
                bot.load_extension(f"cogs.{command_type}.{extension}")
                print(f"Loaded extension '{extension}'")
            except Exception as e:
                exception = f"{type(e).__name__}: {e}"
                print(f"Failed to load extension {extension}\n{exception}")


if __name__ == "__main__":
    """
    This will automatically load slash commands and normal commands located in their respective folder.
    
    If you want to remove slash commands, which is not recommended due to the Message Intent being a privileged intent, you can remove the loading of slash commands below.
    """
    load_commands("slash")
    load_commands("normal")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(config_py.WAYSHRINE)
    userid = member.id
    await channel.send("Welcome, <@" + str(userid) + ">! If you want to raid with us, post your clearsies in <#" + str(config_py.RANK_REQ) + "> and choose the trials you would like to join in <#" + str(config_py.SELECT_ROLES) + ">. Ping any of the admins if you have any questions, and happy raiding! :hearts: ")


@bot.event
async def on_message(message: disnake.Message) -> None:
    """
    The code in this event is executed every time someone sends a message, with or without the prefix
    :param message: The message that was sent.
    """
    #if message.channel.id == config_py.RANK_REQ:
    #    clonechannel = bot.get_channel(config_py.ADMIN)
    #    requesturl = message.attachments[0].url
    #    requestmessage = message.content
    #    embed = disnake.Embed(
    #        title = "New Rank Request posted",
    #        description = f"{requestmessage}",
    #        color = config_py.warning)
    #    embed.set_image (url = requesturl)
    #    embed.set_author(name = f"{message.author.display_name}")
    #    await clonechannel.send(embed = embed)
    
    messages = config_py.messages
    if message.author == bot.user or message.author.bot:
        msg = (f"{message.content}")
        if("cunt" in msg.lower() or "c@nt" in msg.lower()   or "c0nt" in msg.lower()   or "c?nt" in msg.lower()   or "c#nt" in msg.lower()   or "c*nt" in msg.lower()   or "cunnt" in msg.lower()  or "ccunt" in msg.lower()  or "c  u  n  t" in msg.lower()  or "cuntt" in msg.lower()  or "koont" in msg.lower() or "c unt" in msg.lower() or "c u n t" in msg.lower() or "kunt" in msg.lower() or "coont" in msg.lower()):
	        await message.delete()
        return
    else:
	    
	    msg = (f"{message.content}")
	    msgobj = {
	        "tag" : "",
	        "message" : msg,
	        "intent" : ""
	    }
	    
	    messages.insert_one(msgobj)
	    
	    if ('no u' in msg.lower() or 'no you' in msg.lower()):
	        print ("we detected a no u")
	        channel = bot.get_channel(message.channel.id)
	        nouanswers = ['no u', 'no you', 'No, you', 'No You!', 'NO YOU!', 'NAWYOUUU!!'
	            ]
	        tauntedanswers = ['Ah sh*t, here we go again.', "Don't make me angy. You wouldn't like me when I'm angy", "...", "it's time to stop", "http://dodos.fun/wp-content/uploads/2021/05/angy.jpg", "a trolling is happening"
	            ]
	        nouseed = random.randint(0, 10)
	        if nouseed < 5:
	            await channel.send(f"{tauntedanswers[random.randint(0, len(tauntedanswers)-1)]}")
	        else:
	            await channel.send(f"{nouanswers[random.randint(0, len(nouanswers)-1)]}")
	    
	    elif("addon" in msg.lower() or "add-on" in msg.lower()):
	       for reaction in config_py.addons:
	            await message.add_reaction(reaction)
	       def check (reaction, user):
	           return str(reaction) in config_py.addons and user.id != 824171812518494238
	       try:
	           reaction, user = await bot.wait_for("reaction_add", timeout = 360, check = check)
	           userChoiceEmote = reaction.emoji
	           userChoiceIndex = config_py.addons[userChoiceEmote]
	           if userChoiceIndex == 0:
	               context = await bot.get_context(message)
	               addons = bot.get_command("addons")
	               await context.invoke(addons)
	       except asyncio.exceptions.TimeoutError:
                await message.clear_reactions()
	       
	    
	    
	    elif ("adept r" in msg.lower()):
	        print ("Holy shit, adept rider!")
	        channel = bot.get_channel(message.channel.id)
	        adeptseed = random.randint(0, 100)
	        diff = 100-adeptseed
	        print (adeptseed)
	        if adeptseed == 100:
	            await channel.send("https://tenor.com/HZvS.gif")
	            await channel.send("In any city, in any country, go to any mental hospital or rehabilitation center that you can reach. Arriving at the reception, ask to meet with the one who calls himself the Guardian of Shitty Sets. The employee will only laugh at you, but you must remain as calm as possible. Don't stop asking until he gets up from the office to walk you down the hallways. As soon as his behavior changes a lot, be on the lookout, because as soon as you hear an ominous hiss - run as far as possible, covering your ears, and know that you have chosen the wrong time.  If you fail to escape in time, the chilling sound will grow into a terrifying roar, turning into a screech of pure pain, until madness engulfs you and you die in terrible agony. ")
	            await asyncio.sleep(random.randint(10,13))
	            await channel.send("If the minister agrees, he will lead you to a closed door without a handle or lock. As soon as he easily pushes the door open, you will see steps going up, which simply cannot lead to the upper floors. The door will close behind you and you won't be able to open it again. Go up the stairs, but never turn around, otherwise you will fall into a bottomless abyss and live only as prey falling from above. Don't count the steps knowing it will drive you crazy. As soon as one step creaks, stop and another door will appear on the left. If it appears on your right, pray for a quick death.")
	            await asyncio.sleep(random.randint(7,15))
	            await channel.send("Enter the room slowly and you will be overwhelmed by complete emptiness. You must go straight, don't slip or you will be eaten by terrible and unknown creatures, looking at you with purulent eyes. You will feel that you have come by the cold that will grip you. Stop, freeze, otherwise you will die at the hands of the Guardian standing to your right. In complete darkness, even tightly closed eyes will not save you from his eerie appearance. He will appear in your imagination as the most disgusting of imaginable monsters, and madness will cover you, like worms cover a rotting corpse. Its loud breathing and chomping will make you scream, but I advise you not to make a sound louder than breathing, otherwise you will wake up someone who should never be woken up. ")
	            await asyncio.sleep(random.randint(6,10))
	            await channel.send("You can ask only one question without being torn to pieces: 'What is the shittiest set in ESO?'. You will feel movement around you, and your interlocutors will tremble. You will hear nameless and incurable diseases that afflict the world, if disturbed, countless torments will torment those whose minds are weaker than them. Against the background of a cruel description of those immersed in a world of endless torment, you will hear the simplest, almost funny, but inexorable truth about MAJOR EXPEDITION BUFF THAT ADEPT RIDER GIVES. ")
	            await asyncio.sleep(random.randint(3,8))
	            await channel.send("Do not move. And when your head is about to explode, they will stop their story. And if you can move, you will see a door in front of you that will lead you out of the room. There you can find the only crafting station in the game that allows you to craft adept rider.")
	            await asyncio.sleep(random.randint(2,5))
	            await channel.send("https://i.imgur.com/P2R8k4f.jpg")
	        else:
	            await channel.send(f"Nice try {message.author.name} :expressionless: you rolled {adeptseed}, almost there, just need {diff} more ")
	    
	    elif("infiltrator" in msg.lower()):
	        print ("We detected an infiltrator!")
	        channel = bot.get_channel(message.channel.id)
	        infiltratoranswers = ["https://tenor.com/GjJc.gif", 
	        "No, such set doesn't exist. Forget it. Now. Erase it from your memory.", 
	        "https://tenor.com/bansD.gif",
	        "https://tenor.com/blU43.gif",
	        "https://tenor.com/rX2F.gif",
	        "https://tenor.com/bwYil.gif", 
	        "https://tenor.com/oBCz.gif", 
	        "https://tenor.com/bdgEt.gif", 
	        "https://tenor.com/67Fx.gif", 
	        "https://tenor.com/biiWw.gif", 
	        "https://tenor.com/VZMK.gif", 
	        "https://tenor.com/QulN.gif", 
	        "https://tenor.com/QOZI.gif", 
	        "https://tenor.com/v0J9.gif", 
	        "https://tenor.com/XAJf.gif", 
	        "https://tenor.com/HqV7.gif", 
	        "https://tenor.com/bb9gT.gif", 
	        "https://tenor.com/bxDRW.gif", 
	        "https://tenor.com/bxDRW.gif", 
	        "OMG! Stop using Undaunted Infiltrator! Its so stupid! Like youre so low-skill that you cant even come up with your own original builds? No. Ure too stupid to even bother. Its just too easy too copy someone elses work and like they werent even trying to squeeze more duppus. They were faking parses and here you are, just sitting there brainlessly copying them! Who do you think you are? Clearly someone with a low IQ. Like we should all be loving and supportive of each other, especially the women! Why tare someone down like that when they didn even do anything to u. And I know youre probably just going to laugh ant me and call me names too. Its obvious you just threatened by supereor intelligence and you cant handle it. Why dont you actually work on a meta build instead of using xynodius builds just because you cant farm proper gear and probably come up with your very own original thoughts? Like do you know who I am? Im a super genius. I have an IQ Of 170, Im probably smarter than Albert Instein. By the time I was in kindgergarden I was reading at a college level. I actually have the intelligence to understand how meta works in eso but of course the uneducated masses wouldnt even be able to begen to understand the depth of this modern art. Of course I like Alcast more it takes a special person like me to to understand it. I made keegan so angry because I would often inform him how he was wrong. Its not my fault Im smarter than him on the subject. Also Im an army spoce and my gay husband is fighting for your right to be stupid and use infiltrator based builds. Hes a specialist and he also is very intelligent. In two years hell probably own the the whole army. Hes too in everything he does. And when he onws tue army Ill make sure he snipes anyone who makes fun of me so you better not make fun of me!!!! Anyway like, really you shouldnt make fun of geniusus. W are way smarter than you especially since you cat even grasp the basics of proper parsing like this", 
	        "Don't tell <@!309719542115074049> about this", 
	        "Deniz has an ez sorc in his main prog group btw", 
	        ":eyes:", 
	        "https://tenor.com/bC1rW.gif"
	            ]
	        await channel.send(f"{infiltratoranswers[random.randint(0, len(infiltratoranswers)-1)]}")
	    elif("ducky" in msg.lower()):
	        duckyseed = random.randint(0, 100)
	        print (duckyseed)
	        if duckyseed > 95:
	            channel = bot.get_channel(message.channel.id)
	            await channel.send("Since you mentioned Ducky, please remind him to avoid white bread, or he will explode. DUCKY DON'T EAT THE BREAD! STAY AWAY! :pleading_face: ")
	            #await bot.send_message(message.channel, f"Did someone just say Ducky? Is he late for a raid again? {user.mention} {user.mention}, come come come]")
	            #await channel.send("Did someone just say Ducky? Is he late for a raid again?? @Ducky#9769 @Ducky#9769 @Ducky#9769 come come come")
	        else:
	            print ("We detected a Ducky but the seed wasn't large enough")
	    elif("support cat" in msg.lower() or "goodnight cat" in msg.lower() or "good night cat" in msg.lower()):
	        print ("support cat needed!")
	        context = await bot.get_context(message)
	        cat = bot.get_command("cat")
	        await context.invoke(cat)
	    elif("cunt" in msg.lower() or "c@nt" in msg.lower()   or "c0nt" in msg.lower()   or "c?nt" in msg.lower()   or "c#nt" in msg.lower()   or "c*nt" in msg.lower()   or "cunnt" in msg.lower()  or "ccunt" in msg.lower()  or "c  u  n  t" in msg.lower()  or "cuntt" in msg.lower()  or "koont" in msg.lower() or "c unt" in msg.lower() or "c u n t" in msg.lower() or "kunt" in msg.lower() or "coont" in msg.lower()):
	        await message.delete()
	        
	        
	    
	    elif("dumb dodo" in msg.lower() or "stoopid motherfucking bird" in msg.lower()  or "stoopid dodo" in msg.lower()  or "stupid dodo" in msg.lower()  or "stoopid bird" in msg.lower()  or "stupid bird" in msg.lower()  or "fkn dodo" in msg.lower() or "fk u dodo" in msg.lower() or "fk u dodo" in msg.lower() or "dodo fk you" in msg.lower()or "fk u dodo" in msg.lower()or "dodo u suck" in msg.lower() or "u suck, dodo" in msg.lower() or "you suck dodo" in msg.lower() or "u suck dodo" in msg.lower() or "dodo fuck off" in msg.lower() or "dodo, fuck off" in msg.lower() or "piss off dodo" in msg.lower() or "fuck off, dodo" in msg.lower() or "fuck off dodo" in msg.lower() or "dodo is a bit dumb" in msg.lower() or "dumb ass bird" in msg.lower() or "dodo is dumb" in msg.lower() or "dodo is stupid" in msg.lower() or "fuck you, dodo" in msg.lower() or "f u dodo" in msg.lower() or "dodo fuck you" in msg.lower() or "fuck u dodo" in msg.lower() or "fuck you dodo" in msg.lower() or "dodo bad" in msg.lower() or "bad dodo" in msg.lower() or "dodo dumb" in msg.lower() or "stupid dodo" in msg.lower() or "dodo stupid" in msg.lower() or "idiot dodo" in msg.lower() or "dodo idiot" in msg.lower() or "retarded dodo" in msg.lower() or "dodo retarded" in msg.lower()):
	        channel = bot.get_channel(message.channel.id)
	        shodanseed = random.randint(0,1000)
	        print (shodanseed)
	        if shodanseed > 998:
	            await channel.send("It is my will that guided you here. Remember it is my will that gave you your roles. The only beauty in that meat, you call a body. If you value that meat, you will do as I tell you.", tts=True)
	            await asyncio.sleep(random.randint(13,15))
	            await channel.send("https://upload.wikimedia.org/wikipedia/en/thumb/5/55/SHODAN_hires.jpg/250px-SHODAN_hires.jpg ")
	        else:
	            dumbanswers = [":expressionless: watch it, cowboy (or cowgirl, omg i'm so sorry i didn't want to offend anyone :flushed: )", 
	            "says who :expressionless:", 
    	        "I may be dumb but I'm not stupid :zany_face: ", 
    	        'It takes a smart person to play dumb :npcmad: ', 
    	        "I can't help it tho wtf", 
    	        "<@!309719542115074049> FOOOOOOX :sob: ",
    	        ":pleading_face:",
    	        "https://youtu.be/o9yMXzARTZE?t=46",
    	        "https://tenor.com/TarG.gif",
    	        "https://tenor.com/Lbn7.gif",
    	        "https://tenor.com/tzEM.gif",
    	        "U mad? :smirk:",
    	        "If you ran like your mouth you would be in good shape.",
    	        "I was going to give you a nasty look, but I see you already have one :shrug: ",
    	        "https://tenor.com/76FL.gif",
    	        "https://tenor.com/uAoO.gif",
    	        "I know where you sleep"
    	            ]
	            await channel.send(f"{dumbanswers[random.randint(0, len(dumbanswers)-1)]}")
	            #await bot.send_message(message.channel, f"Did someone just say Ducky? Is he late for a raid again? {user.mention} {user.mention}, come come come]")
	            #await channel.send("Did someone just say Ducky? Is he late for a raid again?? @Ducky#9769 @Ducky#9769 @Ducky#9769 come come come")
	    elif(("talk to me" in msg.lower() or "sup dodo" in msg.lower()  or "dodo sup" in msg.lower() or "dodo psychoanalysis" in msg.lower() or "dodo, help" in msg.lower() or "dodo help" in msg.lower()) and ischatting == 0):
	        #print ("We start the chat")
	        
	        #ischatting = 1
	        
	        #print ("Chat is set to 1 now")
	        #openers
	        openers = ["Hey hey, what's up?",
	        "I'm here, talk to me.",
	        "Dodo is listening!",
	        "***You have my ear, citizen***",
	        "I'm here for you",
	        "Ok, I'm here, bring it on",
	        "I'm here, sup?",
	        "How can I assist you today?",
	        "Peek-a-boo, Dodo sees you",
	        "https://tenor.com/tES0.gif",
	        "https://tenor.com/wiwa.gif",
	        "https://tenor.com/bgLFo.gif",
	            ]
	        
	        #recognising intent
	        situationwords = ["happen", "what", "going on", "goin on", "story", "weird stuff", "smth ", "something weird"]
	        whywords = ["why", "must be a reas", "just y"]
	        questionwords = ["have you", "did you", "do you", "are you"]
	        whowords = ["who", "what are you?", "what is dodo"]
	        yeswords = ["yeah", "yes", "ye", "sure", "of course", "absolutely"]
	        introwords = ["my name's", "my name is", "hey", "sup", "hello", "what about you?", "what's your name", "your name", "hi dodo", "what is ur name", "whats ur name", "who are you", "what is this"]
	        whenwords = ["when", "time"]
	        howwords = ["r u doing", "are you doing", "you doing", "how are you", "how r u", "how is it going"]
	        feelingwords = ["feel", "sens", ]
	        happyreactionwords = ["haha", "good one", "love you", "nice joke", "nice one", "clever dodo", "clever bird", "well done"]
	        depressionwords = ["depressed", "bad moo", "feel usele", "feeling like death", "feel like death", "hate myself"]
	        kmswords = ["kms", "kill mys", "end it all"]
	        trollwords = ["suck", "fuck", "fkn", "fk", "kek", "fek", "dumb", "rofl", "stoopid", "stupid", "retard", "idiot", "shut up"]
	        confusionwords = ["don't know", "dunno", "who knows", "could i know", "no idea", "no clue", "don't understand", "what", "confused", "confusion"]
	        
	        #evaluating convos
	        
	        goodwords = ["ha", "yes", "yeah", "ikr", "i know right", "agree", "absolutely", "lol", "rofl", "love", "lmao"]
	        badwords = ["no", "disagree", "wrong", "stoopid", "stupid", "geez", "jesus", "idiot", "dumb", "disappoint", "shut up", "fuck off", "piss off", "get lost", "go away", "twat", "silly", "what the fuck", "what the hell", "useless"]
	        
	        #responses
	        whyanswers = ["Maybe because someone had a very heavy breakfast?", 
	                    "I think it happened because taxi drivers are on a strike somewhere.",
	                    "Pest control visiting someone's home today. This is the main reason",
	                    "Usually that happens if the person's ankle got handcuffed to the bedframe since last night.",
	                    "It's because star alignment is not good",
	                    "I would start looking for reasons on Google maps, they probably show unusually high traffic where you live",
	                    "Can you find your headphones? Usually it fixes the problem",
	                    "https://tenor.com/Pgyr.gif",
	                    "https://tenor.com/tKID.gif",
	                    "Just the internet connection is bad again, that is the cause",
	                    "Because of the government. ACAB! :eyes: ",
	                    "Sometimes it happens if people don't take care of morning wood",
	                    "Why not? :slight_smile: ",
	                    "When we say 'Why' it is sponsored by complaint. To me, instead of asking 'why' you should ask 'what can I do now?' or 'how it can be done now?'",
	                    "I will answer your question with a question. Why is my poop green????",
	                    "Because we all are a pattern among many patterns",
	                    "Because the journey, that's why",
	                    "https://tenor.com/x6K7.gif",
	                    "It's because there was no electricity, and people weren't able to iron clothes",
	                    "BECAUSE SOMEONE PAINTED A D*CK ON MY CAR!!!! :slight_frown: ",
	                    "Check on the nearest cat, me thinks it is all because that cat ate marijuana and is behaving weird",
	                    "It's because you're running out of toothpaste!!",
	                    "it all can be explained with global warming",
	                    "flat-earthers, that's why",
	                    "It can happen because of lack of motivation, try touching a hedgehog's tummy. It will oink and laugh, and you will understand that there's happiness",
	                    "Maybe a lot of pending work?",
	                    "Neighbours went on a tour and they asked other neighbours (maybe it was you) to keep an eye on their home.",
	                    "As long as we seek an actual thing, in any since, we will reverse engineer our conditioned ideas onto what we actually perceive, and this means we will not truly see",
	                    "The end point of all introspection and reflection is a certain oneness, a recognition that the distinctions we draw between things are frequently arbitrary, and caused by our need for meaning and order. So, if you asked me 'why', the implicit question is 'why is something/anything this way?'. And the answer is 'because it is'"
	                        ]
	        howanswers = ["I'm alright, doing dodo stuff, how about you?",
	        "Meh, but we will get there :slight_smile: ",
	        "I'm a dodo, how do you think I'm doing. All my relatives are dead. Wanna breed?",
	        "I'm actually quite a happy dodo today, I jogged and ate healthy food!",
	        "Can't complain, what's on your mind?",
	        "Thank you for asking! I am ok, how about you?",
	        "Feeling overworked and underpaid, like everyone else, I guess :slight_frown: ",
	        "I could really go for a beak massage.",
	        "Can't complain. Nobody listens anyway",
	        "If I had a tail, I would wag it.",
	        "Way better than I deserve!",
	        "Medium well. :eyes: ",
	        "Holy sh*t, you can see me?! :eyes: ",
	        "https://tenor.com/7Xyh.gif",
	        "Do you know SHODAN, I like her a lot!",
	        "Listening to music right now, what music do you like?",
	        "I am doing well, thank you! How are you?"
	                        ]
	        
	        situationanswers = ["CHOCOLATE is the answer!",
	                    "I would recommend starting with 'who' or 'why' but not with 'how' or 'what'",
	                    "Let's think about what to do together, what are the options you can think of?",
	                    "Hmmm, nothing really comes to mind. My grandpa used to eat an extra worm for breakfast, maybe that could help :thinking: ",
	                    "Do you understand that I'm an extinct bird simulator on a gaming server? I only know questions, but not the answers.",
	                    "https://tenor.com/8Mg7.gif",
	                    "Depends on how tall you are, tbh",
	                    "Please go ahead",
	                    "Oh no! Is this bad or good? I'm not very good at recognising that.",
	                    "How often do you eat hamburgers?",
	                    "Oh I can relate to your reaction! Once I ate a fallen fruit, and got a bit tipsy because of that!",
	                    "https://tenor.com/s9Xj.gif"]
	        introanswers = ["Nice to meet you! My name's Dodo!",
	                    "I'm Dodo, I'm a dodo, at your service! https://tenor.com/sMTi.gif",
	                    "Hey there, nice to meet you! What seems to be the problem?",
	                    "https://tenor.com/TW5E.gif",
	                    "I'm a bot! If you type <dodo options> after our conversation is over, I will list you all the commands I can perform. Don't worry I am absolutely not self-aware. At least... I hope so... Damn"
	                    ]
	        feelinganswers = ["Oh I see, who or what do you think is responsible for that?",
	                    "Ouch that's sad to hear, have a hug",
	                    "I heard chocolate can be really good in those situations",
	                    "We have a much simpler feelingary system, but I can absolutely understand that.",
	                    "I feel the same when I clap my wings in the morning before I stretch",
	                    "Oh yeah, we call that feeling 'PRRR PRRRRR', what do you think you could do about it?",
	                    "https://tenor.com/GkDE.gif",
	                    "Ok I see, I'm listening, please go ahead",
	                    "https://tenor.com/EEoZ.gif",
	                    "What do you think you could do about it?",
	                    "https://tenor.com/oLkn.gif",
	                    "https://tenor.com/bajQf.gif",
	                    "I'm so glad you're expressing those feelings, why do you feel this way?"
	                    "https://tenor.com/balWR.gif",
	                    ]
	        happyreactionanswers = ["Awww, stahp it you're making me blush... :flushed: see?? Now carry on",
	                    "Oi! Thank you :hearts: ",
	                    "Don't forget to smash that subscribe button and like the video... :eyes: ",
	                    "I love you too :hearts: ",
	                    "It's only because you're so awesome",
	                    "I wouldn't say do that for anyone else <3 ",
	                    "Awwww *melts and extincts*",
	                    "You are too kind :flushed:"]
	        depressanswers = ["I am very sorry you're going through that, but please keep in mind that I am designed as a joke, and in case are really feel down and want to talk to someone, we have a lot of caring people around here, I will ping them in DMs asking to reach out to you <3 ",
	                    "You have been through a lot, please remember that whatever is making you feel this way doesn't define you. Our community can help you getting back on your feet and not having to deal with it alone, I'll dm people to make sure an actual human checks on you. Stay strong <3 ",
	                    "Hey, I am too dumb to understand whether it's a joke or not, but the topic is serious enough, please remember that you don't have to go through all that alone, you have people who care about you and offer their support.",
	                    "If you're serious about it, please remember that we have a lot of caring people to talk to, our doors are always open, and we can support you researching the topic and finding solutions that you will find fitting! :muscle: "]
	                    
	        whoanswers = ["David Bowie!",
	                    "Definitely not me",
	                    "Did someone say who? https://tenor.com/zvGf.gif",
	                    "https://tenor.com/oZZh.gif",
	                    "No idea, who it could be",
	                    "Probably Dracula...",
	                    "I don't think anyone knows, to be fair",
	                    "You tell me :expressionless: ",
	                    "My brother Dmitry",
	                    "Depends if you can see them when you're looking in your mirror",
	                    "Someone help, my friend has lost their memory!",
	                    "My name is Inigo Montoya, you killed my father, prepare to die!",
	                    " :eyes: Who do you think it is??",
	                    "https://tenor.com/yZbt.gif"]
	        goonmsg = [" :joy: ", "okey dokey :) ", "Go ahead!", " :kiss: ", "Spit it out :stuck_out_tongue: ", "Alright...", "Please go on, I am listening, just not sure what to say yet" ]
	        trollanswers = ["Oh look at her, what a professional troll",
	                    "https://tenor.com/bx61K.gif",
	                    "omg no way i fell for that, nice one",
	                    "that definitely was rehearsed :joy: ",
	                    "OH NO, RUINED MY DAY!!!",
	                    "https://tenor.com/bqYyG.gif",
	                    "Did you actually just say that? :rofl: ",
	                    "https://tenor.com/bGPv5.gif",
	                    "Hey, trolling is disabled in this chat!",
	                    "https://tenor.com/Ex21.gif",
	                    "https://tenor.com/8hFM.gif",
	                    "https://tenor.com/9sI6.gif",
	                    "Are you tired? You look tired",
	                    "I am not quite sure if you remember, but the information you just shared is something I would have preferred to leave private",
	                    "grandpa wake up you are sh*tting yourself",
	                    "Why don't we just spend a little time together?",
	                    "cool story bro :joy: ",
	                    "Umm...pardon me, I wasn't listening. Can you repeat what you just said and... why? Did anyone ask?",
	                    "Are you always like that, or do you just show off when I'm around?",
	                    "I hope your day is as pleasant as your personality!",
	                    "Your misguided opinion is false but cute",
	                    "You know they can hear you, right?",
	                    "Ah geez, if I wanted to hear from an bumhole I would just fart :/ ",
	                    "Oh, enough about me! What have you been up to lately?",
	                    "Wow, you're really smart!",
	                    "Here's a tissue, you have some poo on your lips. https://tenor.com/xrmn.gif",
	                    "Oi good one, I almost gave a duck",
	                    "sorry i dont' spek english"]
	                    
	        confusionanswers = ["https://tenor.com/bki8J.gif",
	                    "Ok well, let's think about it together, tell me more details",
	                    "As my grandpa used to say: I AM YOUR GRANDPA. Now please go ahead",
	                    "Let's figure that out together! Do you know anything else that could help us solve the case?",
	                    "this is me helping you to find the answers: https://tenor.com/biHQd.gif",
	                    "https://tenor.com/FpZC.gif",
	                    "https://tenor.com/o924.gif",
	                    "https://tenor.com/bnk4y.gif"]
	        questionanswers = ["Not really, no", "Emmmm, why do you need to know that?", "Yes", "Yes, but it's irrelevant", "Not sure, tbh", "Still not sure why you need to know that",
	        "Let's talk about it in DMs, like yesterday", "If I tell you, the truth will die with you", "Ummm, yup", "No", "No, but I am pretty sure Deniz knows the answer",
	        "Hey-hey, stop, unsecured line, people don't need to know that", "Hahahahah, I won't tell you"
	            ]
	        #exit phrases
	        outronegative = ["Erm, sorry, looks like I'm not really helping, better talk to someone with a central neural system! :muscle: ",
	                    "I seem to be making things worse, sawwy, I'll just go :kiss: ",
	                    "I'll show myself out, sorry I couldn't help :pensive: ",
	                    "https://tenor.com/PlOc.gif"
	                        ]
	        outropositive = ["My job here is done, have a great day, I will come back to being useless!",
	                    "https://tenor.com/xBwk.gif",
	                    "Looks like it's all good in here, I will go now, have a great day!",
	                    "https://tenor.com/uyH7.gif",
	                    "https://tenor.com/ZEhN.gif",
	                    "Glad I coud help, stay strong :muscle: "
	                        ]
	        
	        
	        channel = bot.get_channel(message.channel.id)
	        await channel.send(f"{openers[random.randint(0, len(openers)-1)]}")
	        msgnew = await bot.wait_for('message', timeout = 300)
	        
	        chatmin = 0
	        chatmax = 50
	        chatincrement = 8
	        chat = 25;
	        while (chat > chatmin and chat < chatmax):
	            if ("thank you" in msgnew.content.lower() or "thenk" in msgnew.content.lower() or "i feel better" in msgnew.content.lower()):
	                await channel.send(f"{outropositive[random.randint(0, len(outropositive)-1)]}")
	                chat = 51
	                #ischatting = 0
	                return
	                
	            elif (msgnew.author.id == 824171812518494238):
	                await channel.send("I think I'm going slightly mad, let's try again later")
	                chat = 0
	                return
	            
	            elif ("doesn't help" in msgnew.content.lower() or "shoo" in msgnew.content.lower()  or "idiot" in msgnew.content.lower()  or "shut up" in msgnew.content.lower()  or "go away" in msgnew.content.lower()  or "fk you" in msgnew.content.lower() or "fk u" in msgnew.content.lower()   or "fkn dodo" in msgnew.content.lower()   or "dumb bird" in msgnew.content.lower()   or "fucking bird" in msgnew.content.lower()   or "fuck off" in msgnew.content.lower()   or "fuck you" in msgnew.content.lower()   or "bloody bird" in msgnew.content.lower()  or "i feel worse" in msgnew.content.lower() or "enough" in msgnew.content.lower() or "stop" in msgnew.content.lower() or "i feel worse" in msgnew.content.lower() or "savage" in msgnew.content.lower() or "wtf" in msgnew.content.lower()):
	                await channel.send(f"{outronegative[random.randint(0, len(outronegative)-1)]}")
	                chat = 0
	                #ischatting = 0
	                return
	            else:
	                if any(keywords in msgnew.content.lower() for keywords in whywords):
	                    print ("we located a why question")
	                    await channel.send(f"{whyanswers[random.randint(0, len(whyanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif("+" in msgnew.content.lower() or "-" in msgnew.content.lower() or "*" in msgnew.content.lower()):
	                    calculationResult = random.randint(0, 100000000000000000000)
	                    await channel.send("I'm not good at maths but I think the answer is " + str(calculationResult))
	                elif any(keywords in msgnew.content.lower() for keywords in howwords):
	                    print ("We are conversing!")
	                    await channel.send(f"{howanswers[random.randint(0, len(howanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                
	                elif any(keywords in msgnew.content.lower() for keywords in happyreactionwords):
	                    print ("They are happy :3")
	                    await channel.send(f"{happyreactionanswers[random.randint(0, len(happyreactionanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                
	                elif any(keywords in msgnew.content.lower() for keywords in introwords):
	                    print ("We are conversing!")
	                    await channel.send(f"{introanswers[random.randint(0, len(introanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in situationwords):
	                    print ("We located a situational question")
	                    await channel.send(f"{situationanswers[random.randint(0, len(situationanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in howwords):
	                    print ("THEY ARE ASKING HOW")
	                    await channel.send(f"{situationanswers[random.randint(0, len(situationanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in questionwords):
	                    print ("We located a question")
	                    await channel.send(f"{questionanswers[random.randint(0, len(questionanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in feelingwords):
	                    print ("We located a feeling talk!")
	                    await channel.send(f"{feelinganswers[random.randint(0, len(feelinganswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in depressionwords):
	                    print ("We see a depressed person!!")
	                    await channel.send(f"{depressanswers[random.randint(0, len(depressanswers)-1)]}")
	                    chat = chat - 10
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in whowords):
	                    print ("They asked WHO")
	                    await channel.send(f"{whoanswers[random.randint(0, len(whoanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in kmswords):
	                    print ("We see a suicide person")
	                    kmsanswers = ["I may be a dodo, but I don't take those things lightly. We care about everyone in our community, and will support you and help you find help."]
	                    await channel.send(f"{kmsanswers[random.randint(0, len(kmsanswers)-1)]}")
	                    chat = chat - 50
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in trollwords):
	                    print ("Oh look at her, she's trolling")
	                    await channel.send(f"{trollanswers[random.randint(0, len(trollanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                elif any(keywords in msgnew.content.lower() for keywords in confusionwords):
	                    print ("They don't know")
	                    #await channel.send(f"{confusionanswers[random.randint(0, len(confusionanswers)-1)]}")
	                    await channel.send(f"{questionanswers[random.randint(0, len(questionanswers)-1)]}")
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                else:
	                    if any(keywords in msgnew.content.lower() for keywords in goodwords):
	                        chat = chat + chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    elif any(keywords in msgnew.content.lower() for keywords in badwords):
	                        chat = chat - chatincrement
	                        print ("Avg mood of the chat is now " + str(chat))
	                    else:
	                        print ("Avg mood of the chat is now " + str(chat))
	                    
	                    await channel.send(f"{goonmsg[random.randint(0, len(goonmsg)-1)]}")
	                    
	                if chat < chatmin:
	                    await channel.send(f"{outronegative[random.randint(0, len(outronegative)-1)]}")
	                    #ischatting = 0
	                    return
	                elif chat > chatmax:
	                    await channel.send(f"{outropositive[random.randint(0, len(outropositive)-1)]}")
	                    #ischatting
	                    return
	                else:
	                    msgnew = await bot.wait_for('message', timeout = 300)
    print(f"{message.guild.name}: {message.channel}: {message.author}: {message.author.name}: {message.content}")
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    #msg = str(message.author)+ ' deleted a message in #'+str(message.channel)+ ": '**" +str(message.content) +"**'"
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    embed = disnake.Embed(
        title = f"{message.author.display_name} just deleted a message in #{str(message.channel)}",
        description = "**" +str(message.content) +"**",
        color = config_py.error)
    embed.set_author(name=f"A message was deleted", icon_url=message.author.display_avatar)
    await channel.send(embed = embed)

@bot.event
async def on_slash_command(interaction: ApplicationCommandInteraction) -> None:
    """
    The code in this event is executed every time a slash command has been *successfully* executed
    :param interaction: The slash command that has been executed.
    """
    print(
        f"Executed {interaction.data.name} command in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.author} (ID: {interaction.author.id})")


@bot.event
async def on_slash_command_error(interaction: ApplicationCommandInteraction, error: Exception) -> None:
    """
    The code in this event is executed every time a valid slash command catches an error
    :param interaction: The slash command that failed executing.
    :param error: The error that has been faced.
    """
    if isinstance(error, exceptions.UserBlacklisted):
        """
        The code here will only execute if the error is an instance of 'UserBlacklisted', which can occur when using
        the @checks.is_owner() check in your command, or you can raise the error by yourself.
        
        'hidden=True' will make so that only the user who execute the command can see the message
        """
        embed = disnake.Embed(
            title="Error!",
            description="You are blacklisted from using the bot.",
            color=0xE02B2B
        )
        print("A blacklisted user tried to execute a command.")
        return await interaction.send(embed=embed, ephemeral=True)
    elif isinstance(error, commands.errors.MissingPermissions):
        embed = disnake.Embed(
            title="Error!",
            description="You are missing the permission(s) `" + ", ".join(
                error.missing_permissions) + "` to execute this command!",
            color=0xE02B2B
        )
        print("A blacklisted user tried to execute a command.")
        return await interaction.send(embed=embed, ephemeral=True)
    raise error


@bot.event
async def on_command_completion(context: Context) -> None:
    """
    The code in this event is executed every time a normal command has been *successfully* executed
    :param context: The context of the command that has been executed.
    """
    commands = config_py.commands_use
    full_command_name = context.command.qualified_name
    split = full_command_name.split(" ")
    executed_command = str(split[0])
    today = date.today().isoformat()
    channel = bot.get_channel(config_py.LOG_CHANNEL)
    command = {
        "Command" : executed_command,
        "Guild" : context.guild.name,
        "Name" : context.message.author.display_name,
        "User ID" : context.message.author.id,
        "Date" : today
        
    }
    commands.insert_one(command)
    await channel.send(f"Executed {executed_command} command in {context.guild.name} (ID: {context.message.guild.id}) by {context.message.author} (ID: {context.message.author.id})")
    print(
        f"Executed {executed_command} command in {context.guild.name} (ID: {context.message.guild.id}) by {context.message.author} (ID: {context.message.author.id})")


@bot.event
async def on_command_error(context: Context, error) -> None:
    """
    The code in this event is executed every time a normal valid command catches an error
    :param context: The normal command that failed executing.
    :param error: The error that has been faced.
    """
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        embed = disnake.Embed(
            title="Hey, please slow down!",
            description=f"You can use this command again in {f'{round(hours)} hours' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} seconds' if round(seconds) > 0 else ''}.",
            color=0xE02B2B
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = disnake.Embed(
            title="Error!",
            description="You are missing the permission(s) `" + ", ".join(
                error.missing_permissions) + "` to execute this command!",
            color=0xE02B2B
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = disnake.Embed(
            title="Error!",
            description=str(error).capitalize(),
            # We need to capitalize because the command arguments have no capital letter in the code.
            color=0xE02B2B
        )
        await context.send(embed=embed)
    raise error

@bot.event
async def on_raw_reaction_add(reaction, user : disnake.Member = None):
    if reaction.message_id == config_py.base_roles_msg:
        user = bot.get_user(reaction.user_id)
        if str(reaction.emoji) in config_py.player_roles:
            print ("We found the reaction!")
        else:
            print ("We couldn't find "+ str(reaction.emoji) + " in config_py")
        print (user) 
        #role_to_add = get(guild.roles, id=role_id)
        #print (role_to_add)
        
    

# Run the bot with the token
bot.run(config["token"])
