"""
Fun cog — assorted novelty commands: dice rolls, roasts, fortune/tarot, random
facts, inspirational images and (owner-only) AI image generation. Text lives in
``lang``.
"""

import asyncio
import random
from urllib.request import urlopen

import aiohttp
import inspirobot
from bs4 import BeautifulSoup
from openai import OpenAI

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"


class Fun(commands.Cog, name="fun"):
    """Novelty and dice commands."""

    def __init__(self, bot):
        self.bot = bot
        proxy_key = getattr(config_py, "PROXY_API", None)
        self.client = OpenAI(api_key=proxy_key, base_url=_PROXY_BASE_URL) if proxy_key else None

    @commands.hybrid_command(name="cringe", description="Assemble the cringe team randomly.")
    @checks.not_blacklisted()
    async def cringe(self, context: Context) -> None:
        """Draft a random member for a random cringe challenge."""
        user = await self.bot.fetch_user(random.choice(config_py.CRINGE))
        challenge = random.choice(config_py.CHALLENGES)
        await context.send(lang.FUN_CRINGE.format(user=user.mention, challenge=challenge))

    @commands.hybrid_command(name="d20", description="Roll a 20-sided die with an optional modifier.")
    @checks.not_blacklisted()
    async def d20(self, context: Context, modifier: int = 0) -> None:
        """Roll a d20, applying an optional modifier."""
        roll = random.randint(1, 20)
        if modifier == 0:
            message = lang.FUN_D20_PLAIN.format(roll=roll)
        else:
            message = lang.FUN_D20_MODIFIED.format(
                roll=roll, sign="+" if modifier > 0 else "", modifier=modifier, total=roll + modifier
            )
        if roll == 20:
            message += lang.FUN_D20_CRIT_SUCCESS
        elif roll == 1:
            message += lang.FUN_D20_CRIT_FAILURE
        await context.send(message)

    @commands.hybrid_command(name="d20m", description="Gather players and roll a d20 for everyone who joins.")
    @checks.not_blacklisted()
    async def d20m(self, context: Context) -> None:
        """Collect dice reactions for 7s, then roll a d20 for each participant."""
        join_msg = await context.send(lang.FUN_D20M_JOIN)
        await join_msg.add_reaction("\U0001F3B2")
        await asyncio.sleep(7)

        join_msg = await context.channel.fetch_message(join_msg.id)
        reaction = next((r for r in join_msg.reactions if str(r.emoji) == "\U0001F3B2"), None)
        players = [user async for user in reaction.users() if not user.bot] if reaction else []
        try:
            await join_msg.clear_reactions()
        except discord.Forbidden:
            pass

        if not players:
            await context.send(lang.FUN_D20M_NONE)
            return

        results = {player: random.randint(1, 20) for player in players}
        max_roll = max(results.values())
        winners = [player for player, roll in results.items() if roll == max_roll]

        embed = messages.embed(
            "\n".join(f"{p.mention}: **{r}**" for p, r in sorted(results.items(), key=lambda i: i[1], reverse=True)),
            title=lang.FUN_D20M_TITLE,
            color=discord.Color.blurple(),
        )
        if len(winners) == 1:
            embed.add_field(name="Winner", value=lang.FUN_D20M_WINNER.format(winner=winners[0].mention, roll=max_roll), inline=False)
        else:
            embed.add_field(
                name="Tie!",
                value=lang.FUN_D20M_TIE.format(winners=", ".join(w.mention for w in winners), roll=max_roll),
                inline=False,
            )
        await context.send(embed=embed)

    @commands.hybrid_command(name="roast", description="Insult someone in style.")
    @checks.not_blacklisted()
    async def roast(self, context: Context, member: discord.Member = None) -> None:
        """Deliver a Shakespearean roast (Dodo defends itself if roasted)."""
        if member is None:
            member = context.author
            await context.send(lang.FUN_ROAST_SELF)
        elif member.id == 824171812518494238:
            await context.send(random.choice(lang.DODO_INSULT))
            return
        insult = f"{random.choice(lang.INSULT_1)} {random.choice(lang.INSULT_2)} {random.choice(lang.INSULT_3)}"
        await context.send(lang.FUN_ROAST.format(name=member.display_name, insult=insult))

    @commands.hybrid_command(name="gay", description="Check how gay someone is at this very moment.")
    @checks.not_blacklisted()
    async def gay(self, context: Context, member: discord.Member = None) -> None:
        """Roll a light-hearted 'gayness' percentage with a matching joke."""
        member = member or context.author
        gayness = random.randint(0, 100)
        if gayness == 4:
            phrase = lang.FUN_GAY_FOUR
        elif gayness < 20:
            phrase = random.choice(lang.FUN_GAY_STRAIGHT)
        elif gayness < 40:
            phrase = random.choice(lang.FUN_GAY_SLIGHT)
        elif gayness < 60:
            phrase = random.choice(lang.FUN_GAY_MEDIUM)
        elif gayness < 80:
            phrase = random.choice(lang.FUN_GAY_HEAVY)
        else:
            phrase = random.choice(lang.FUN_GAY_FULL)
        await context.send(
            embed=messages.warning(
                lang.FUN_GAY_RESULT.format(name=member.display_name, gayness=gayness, phrase=phrase),
                title=lang.FUN_GAY_TITLE.format(name=member.display_name),
            )
        )

    @commands.hybrid_command(name="wisdom", description="Show an inspirational image.")
    @checks.not_blacklisted()
    async def wisdom(self, context: Context, member: discord.Member = None) -> None:
        """Post an InspiroBot image dedicated to a member."""
        member = member or context.author
        inspirobot.HTTPS = False
        quote = inspirobot.generate()
        embed = messages.success(title=lang.FUN_WISDOM_TITLE)
        embed.set_image(url=quote.url)
        embed.set_author(name=lang.FUN_WISDOM_AUTHOR.format(name=member.display_name))
        await context.send(embed=embed)

    @commands.hybrid_command(name="future", description="Draw a random tarot card to predict a future.")
    @checks.not_blacklisted()
    async def future(self, context: Context, member: discord.Member = None) -> None:
        """Fetch and present a random tarot card."""
        member = member or context.author
        soup = BeautifulSoup(urlopen("http://chaoticshiny.com/tarotgen.php"), "html.parser")
        tarot = soup.find_all("div", {"id": "output"})
        side = "inverted" if random.randint(0, 10) > 5 else "not inverted"
        name = tarot[0].contents[0].next_sibling.get_text()
        description = tarot[0].contents[0].next_sibling.next_sibling.next_sibling
        await context.send(lang.FUN_TAROT_CARD.format(name=member.display_name, card=name, side=side))
        await context.send(description)

    @commands.hybrid_command(name="fact", description="Get a random fact.")
    @checks.not_blacklisted()
    async def fact(self, context: Context) -> None:
        """Fetch and post a random useless fact."""
        async with aiohttp.ClientSession() as session:
            async with session.get("https://uselessfacts.jsph.pl/random.json?language=en") as request:
                if request.status == 200:
                    data = await request.json()
                    embed = messages.embed(data["text"], color=0xD75BF4)
                else:
                    embed = messages.error("There is something wrong with the API, please try again later")
        await context.send(embed=embed)

    @commands.hybrid_command(name="imagine", description="Generate an image with AI (owner only).")
    @checks.is_owner()
    async def imagine(self, context: Context, *, message: str) -> None:
        """Generate a DALL·E image from a prompt."""
        if self.client is None:
            await context.send(lang.FUN_IMAGINE_UNCONFIGURED)
            return
        thinking = await context.send(lang.FUN_IMAGINE_THINKING)
        response = self.client.images.generate(model="dall-e-3", prompt=message, n=1, size="1024x1024")
        await thinking.edit(content=response.data[0].url)


async def setup(bot):
    await bot.add_cog(Fun(bot))
