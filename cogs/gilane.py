"""
Gilane cog — the ``gilane`` event. Starts a 20-second reaction window, then
fires one of three randomly-chosen Gilane events for everyone who joined:

* **Hä?** — pings the participants with Gilane's signature „Hä?".
* **Reaction** — everyone spam-presses the Gilane emoji for 10s to build their
  Gilane meter… then a winner is picked completely at random anyway.
* **Spreadsheet** — pings everyone that a spreadsheet has been created, linking
  to something *definitely* work-related.

Participation is tallied in the database (with unreliable, very-Gilane counting)
and shown as a top-10 leaderboard on the concluded-event embed. There is also a
small chance the command gets confused and runs a completely different command.
"""

import asyncio
import random
import time

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks

_JOIN_EMOJI = "✋"
_JOIN_SECONDS = 20
_MISS_CHANCE = 20  # 1-in-N chance participation isn't counted
_DOUBLE_CHANCE = 20  # 1-in-N chance it's counted twice (only if it wasn't missed)
_MEDALS = ["🥇", "🥈", "🥉"]

_CONFUSED_CHANCE = 35  # 1-in-N chance Gilane gets confused and runs a different command
_CONFUSED_REDIRECTS = ["d20", "roast", "gay", "cringe", "fact"]

_WEEK_SECONDS = 7 * 24 * 60 * 60  # once per week, per person

_GILANE_EMOJI_ID = 784469282268512338
_GILANE_EMOJI_NAME = "gilane_uwot"
_GILANE_EMOJI_TEXT = f"<:{_GILANE_EMOJI_NAME}:{_GILANE_EMOJI_ID}>"
_GILANE_PARTIAL = discord.PartialEmoji(name=_GILANE_EMOJI_NAME, id=_GILANE_EMOJI_ID)
_REACTION_SECONDS = 10


class Gilane(commands.Cog, name="gilane"):
    """The Gilane event."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="gilane", description="Start the Gilane event.")
    @checks.not_blacklisted()
    async def gilane(self, context: Context) -> None:
        """Open a 20s reaction window, fire a random Gilane event, then tally participation."""
        # Weekly per-person cooldown, persisted in the DB so it survives restarts.
        now = time.time()
        record = config_py.gilane_scores.find_one({"User ID": context.author.id})
        if record and now - record.get("Last Used", 0) < _WEEK_SECONDS:
            await context.send(lang.GILANE_COOLDOWN)
            return
        config_py.gilane_scores.update_one(
            {"User ID": context.author.id}, {"$set": {"Last Used": now}}, upsert=True
        )

        # Every so often Gilane loses the plot entirely and runs a different command.
        if random.randint(1, _CONFUSED_CHANCE) == 1:
            await context.send(lang.GILANE_CONFUSED_REDIRECT)
            command = self.bot.get_command(random.choice(_CONFUSED_REDIRECTS))
            if command is not None:
                await context.invoke(command)
            return

        starter = await context.send(
            embed=discord.Embed(
                title=lang.GILANE_EVENT_TITLE,
                description=lang.GILANE_EVENT_DESC.format(seconds=_JOIN_SECONDS),
                color=discord.Color.gold(),
            )
        )
        await starter.add_reaction(_JOIN_EMOJI)
        await asyncio.sleep(_JOIN_SECONDS)

        starter = await context.channel.fetch_message(starter.id)
        reaction = next((r for r in starter.reactions if str(r.emoji) == _JOIN_EMOJI), None)
        participants = [u async for u in reaction.users() if not u.bot] if reaction else []

        if participants:
            event = random.choice(
                [self._event_hae, self._event_reaction, self._event_spreadsheet, self._event_rename]
            )
        else:
            event = self._event_hae
        await event(context, participants)

        self._tally(participants)
        await starter.edit(embed=self._concluded_embed())

    # ------------------------------------------------------------------ #
    #  Events
    # ------------------------------------------------------------------ #
    async def _event_hae(self, context, participants) -> None:
        """Ping everyone who joined with „Hä?"."""
        mentions = " ".join(u.mention for u in participants)
        await context.send(f"{mentions} {lang.GILANE_HAE}".strip())

    async def _event_spreadsheet(self, context, participants) -> None:
        """Announce a freshly-created 'spreadsheet' linking somewhere work-related (no pings)."""
        await context.send(
            lang.GILANE_SPREADSHEET.format(
                filename=random.choice(lang.GILANE_SPREADSHEET_FILES),
                url=random.choice(lang.GILANE_SPREADSHEET_LINKS),
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _event_rename(self, context, participants) -> None:
        """Rename everyone who joined to 'Gilane' (whoever the bot has permission for)."""
        renamed = False
        for user in participants:
            member = context.guild.get_member(user.id) if context.guild else None
            if member is None:
                continue
            try:
                await member.edit(nick=lang.GILANE_RENAME_NICK, reason="Gilane event")
                renamed = True
            except discord.HTTPException:
                pass  # higher role, server owner, or missing Manage Nicknames
        await context.send(lang.GILANE_RENAME if renamed else lang.GILANE_RENAME_NONE)

    async def _event_reaction(self, context, participants) -> None:
        """Spam-press the Gilane emoji for 10s to build a meter, then pick a random winner."""
        meters = {u.id: 0 for u in participants}
        msg = await context.send(embed=self._reaction_embed(participants, meters))
        try:
            await msg.add_reaction(_GILANE_PARTIAL)
        except discord.HTTPException:
            pass  # bot may not share a server with the emoji; the spam just won't register

        def check(_reaction, user):
            return not user.bot and user.id in meters and getattr(_reaction.emoji, "id", None) == _GILANE_EMOJI_ID

        end = time.time() + _REACTION_SECONDS
        last_edit = 0.0
        while (remaining := end - time.time()) > 0:
            try:
                react, user = await self.bot.wait_for("reaction_add", timeout=remaining, check=check)
            except asyncio.TimeoutError:
                break
            meters[user.id] += 1  # each press bumps that player's Gilane meter
            try:
                await msg.remove_reaction(react.emoji, user)  # remove so they can press again
            except discord.HTTPException:
                pass
            if time.time() - last_edit > 1.2:  # throttle edits to avoid rate limits
                last_edit = time.time()
                try:
                    await msg.edit(embed=self._reaction_embed(participants, meters))
                except discord.HTTPException:
                    pass

        winner = random.choice(participants)
        try:
            await msg.clear_reactions()
        except discord.HTTPException:
            pass
        await msg.edit(embed=self._reaction_embed(participants, meters, winner=winner))

    def _reaction_embed(self, participants, meters, *, winner=None) -> discord.Embed:
        """Render the Gilane-meter standings; if ``winner`` is set, show the (random) result."""
        if winner is None:
            embed = discord.Embed(
                title=lang.GILANE_REACTION_TITLE,
                description=lang.GILANE_REACTION_DESC.format(emoji=_GILANE_EMOJI_TEXT),
                color=discord.Color.gold(),
            )
        else:
            embed = discord.Embed(
                title=lang.GILANE_REACTION_RESULT_TITLE,
                description=lang.GILANE_REACTION_WINNER.format(winner=winner.mention, emoji=_GILANE_EMOJI_TEXT),
                color=discord.Color.green(),
            )
        ranked = sorted(participants, key=lambda u: meters[u.id], reverse=True)
        body = "\n".join(
            lang.GILANE_REACTION_LINE.format(
                medal=_MEDALS[i] if i < 3 else "▫️", mention=u.mention, count=meters[u.id]
            )
            for i, u in enumerate(ranked)
        )
        embed.add_field(name=lang.GILANE_REACTION_HEADER, value=body or "—", inline=False)
        return embed

    # ------------------------------------------------------------------ #
    #  Participation tally & leaderboard
    # ------------------------------------------------------------------ #
    def _tally(self, participants) -> None:
        """Record each participant, with Gilane's flaky counting quirks."""
        for user in participants:
            if random.randint(1, _MISS_CHANCE) == 1:
                continue  # Gilane forgot to write this one down
            increment = 2 if random.randint(1, _DOUBLE_CHANCE) == 1 else 1
            config_py.gilane_scores.update_one(
                {"User ID": user.id},
                {"$inc": {"Participations": increment}},
                upsert=True,
            )

    def _concluded_embed(self) -> discord.Embed:
        """Build the concluded-event embed with the all-time top-10 attendees."""
        embed = discord.Embed(
            title=lang.GILANE_EVENT_CONCLUDED_TITLE,
            description=lang.GILANE_EVENT_CONCLUDED_DESC,
            color=discord.Color.green(),
        )
        top = list(
            config_py.gilane_scores.find({"Participations": {"$gt": 0}}).sort("Participations", -1).limit(10)
        )
        if top:
            lines = "\n".join(
                lang.GILANE_LEADERBOARD_LINE.format(
                    medal=_MEDALS[i] if i < 3 else f"{i + 1}.",
                    mention=f"<@{doc['User ID']}>",
                    count=doc.get("Participations", 0),
                )
                for i, doc in enumerate(top)
            )
        else:
            lines = lang.GILANE_LEADERBOARD_EMPTY
        embed.add_field(name=lang.GILANE_LEADERBOARD_TITLE, value=lines, inline=False)
        return embed


async def setup(bot):
    await bot.add_cog(Gilane(bot))
