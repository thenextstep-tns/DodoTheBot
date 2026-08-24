"""
Fight cog — ``fight`` opens a scrap and runs it in one message.

Three phases, one embed, edited throughout:

**Sign-up**, one minute. A button reading "Send a cat to fight". Whoever presses
it gets their roster in, or a private reply telling them what to do about not
having one, with the shortcut of letting the bot pick their best. Sides are
balanced as people arrive, so it is never a queue of nine against one.

**Rounds**, five seconds each. You show the cats an object by reacting to the
message with any emoji at all. Every cat in the room reacts to it, each
according to its class, and the countdown ticks down in the embed once a second.

**Spoils.** Records are written, the winners take a point of each of the losers'
governing attributes, and everything the objects did is thrown away.

The engine, the grid, the scoreboard and the roster all live in ``helpers`` and
none of them import discord; this file is the part that knows about Discord and
almost nothing else.
"""

import asyncio

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages, reactions, scrap, scrap_embed, scrap_lobby, scrap_store


class _SignUp(discord.ui.View):
    """The minute before the bell."""

    def __init__(self, cog: "Fight", timeout: float):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(label="Send a cat to fight", style=discord.ButtonStyle.blurple, emoji="🥊")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.take_signup(interaction, auto=False)

    @discord.ui.button(label="Just pick my best", style=discord.ButtonStyle.grey, emoji="⭐")
    async def best(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.take_signup(interaction, auto=True)


class _PickBest(discord.ui.View):
    """Offered privately to somebody who owns cats but has never chosen one."""

    def __init__(self, cog: "Fight", timeout: float = 60):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(label="Send my best cat", style=discord.ButtonStyle.green, emoji="⭐")
    async def best(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.take_signup(interaction, auto=True, edit=True)


class Fight(commands.Cog, name="fight"):
    """Cat scraps: sign up, show them things, take their stats."""

    def __init__(self, bot):
        self.bot = bot
        # message id -> the state of the scrap being fought on it
        self.live: dict[int, dict] = {}

    def _param(self, context_or_guild, key: str):
        guild = getattr(context_or_guild, "guild", context_or_guild)
        return self.bot.params.get(guild.id if guild else None, key)

    # ------------------------------------------------------------------ #
    #  Sign-up
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="fight", description="Start a cat fight. Anyone can join and interfere.")
    @checks.not_blacklisted()
    async def fight(self, context: Context) -> None:
        """Open a scrap, take sign-ups for a minute, then run it."""
        if context.interaction:
            await context.defer()
        seconds = int(self._param(context, "fight_signup_seconds"))
        view = _SignUp(self, seconds)
        embed = messages.embed(lang.FIGHT_SIGNUP.format(seconds=seconds),
                               title=lang.FIGHT_SIGNUP_TITLE)
        message = await context.send(embed=embed, view=view)

        self.live[message.id] = {"sides": {"A": [], "B": []}, "owners": {},
                                 "message": message, "guild": context.guild, "shows": []}
        await self._countdown(message, seconds, embed)
        view.stop()

        state = self.live.get(message.id)
        if not state or not state["sides"]["A"] or not state["sides"]["B"]:
            self.live.pop(message.id, None)
            await message.edit(embed=messages.warning(lang.FIGHT_NOBODY_CAME), view=None)
            return
        await self._run(message, state)

    async def _countdown(self, message, seconds: int, embed) -> None:
        """Tick the sign-up clock down in place, once a second."""
        for remaining in range(seconds, 0, -1):
            if remaining % 5 == 0 or remaining <= 5:
                embed.description = lang.FIGHT_SIGNUP.format(seconds=remaining)
                try:
                    await message.edit(embed=embed)
                except discord.HTTPException:
                    pass
            await asyncio.sleep(1)

    def _state_for(self, interaction: discord.Interaction) -> dict | None:
        return self.live.get(interaction.message.id if interaction.message else 0)

    async def take_signup(self, interaction: discord.Interaction, *, auto: bool, edit: bool = False) -> None:
        """Somebody pressed the button. Work out what they actually have."""
        state = self._state_for(interaction)
        if state is None:
            await interaction.response.send_message(lang.FIGHT_OVER_ALREADY, ephemeral=True)
            return

        already = [f["ident"] for side in state["sides"].values() for f in side]
        result = scrap_lobby.join(interaction.user.id, already=already, auto=auto)
        if result["status"] != scrap_lobby.READY:
            # Never a wall of instructions: one sentence, and a button if there
            # is anything to press.
            view = _PickBest(self) if result["status"] == scrap_lobby.NO_ROSTER else None
            text = scrap_lobby.explain(result)
            if edit:
                await interaction.response.edit_message(content=text, view=None)
            else:
                await interaction.response.send_message(text, view=view, ephemeral=True)
            return

        # Balance as they arrive: whichever side has fewer cats takes the next one.
        cap = int(scrap.TUNING["roster_max"])
        added = []
        for pet in result["cats"]:
            side = "A" if len(state["sides"]["A"]) <= len(state["sides"]["B"]) else "B"
            if len(state["sides"][side]) >= cap:
                break
            fighter = scrap_lobby.as_fighter(pet)
            state["sides"][side].append(fighter)
            state["owners"][fighter["ident"]] = interaction.user.display_name
            added.append(fighter["name"])
        if not added:
            await interaction.response.send_message(lang.FIGHT_SIDES_FULL, ephemeral=True)
            return

        line = lang.FIGHT_JOINED.format(names=", ".join(added))
        if edit:
            await interaction.response.edit_message(content=line, view=None)
        else:
            await interaction.response.send_message(line, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  The fight
    # ------------------------------------------------------------------ #
    def _lookup(self, guild):
        """Resolve a cell for this guild, through every layer, once per fight."""
        guild_rows = reactions.stored(guild.id if guild else 0)
        global_rows = reactions.stored(reactions.GLOBAL)

        def lookup(emoji: str, cls: str):
            cell = reactions.resolve(emoji, cls, guild_rows, global_rows)
            return cell if cell.get("text") else None

        return lookup

    async def _run(self, message, state: dict) -> None:
        guild = state["guild"]
        fight = scrap.Scrap(state["sides"]["A"], state["sides"]["B"],
                            lookup=self._lookup(guild))
        teams = self._team_names(state)
        seconds = int(self._param(guild, "fight_round_seconds"))

        await message.edit(content=None, embed=self._embed(fight, None, teams, seconds), view=None)
        try:
            await message.clear_reactions()
        except discord.HTTPException:
            pass

        while not fight.over():
            shows = await self._collect(message, fight, teams, seconds)
            snapshot = fight.step(shows)
            await message.edit(embed=self._embed(fight, snapshot, teams, 0,
                                                 events=snapshot["events"]))
            await asyncio.sleep(1)

        await self._finish(message, fight, teams)

    async def _collect(self, message, fight, teams, seconds: int) -> list:
        """Watch for emoji during a round, ticking the clock as it goes.

        Anything anybody reacts with counts, including emoji nobody has written a
        cell for: those simply do nothing, which is its own small joke.
        """
        shown: list = []

        def check(reaction, user):
            return (reaction.message.id == message.id and not user.bot)

        for remaining in range(seconds, 0, -1):
            snapshot = fight.rounds[-1] if fight.rounds else self._blank(fight)
            try:
                await message.edit(embed=self._embed(fight, snapshot, teams, remaining))
            except discord.HTTPException:
                pass
            try:
                reaction, user = await asyncio.wait_for(
                    self.bot.wait_for("reaction_add", check=check), timeout=1.0)
                shown.append((str(reaction.emoji), user.display_name))
            except (asyncio.TimeoutError, TimeoutError):
                continue
        return shown

    def _blank(self, fight) -> dict:
        return {"round": fight.round_no + 1,
                "cats": [f.public(fight.tuning) for f in fight.fighters],
                "events": [], "history": list(fight.history)}

    def _team_names(self, state: dict) -> tuple:
        names = {"A": [], "B": []}
        for side, fighters in state["sides"].items():
            for fighter in fighters:
                owner = state["owners"].get(fighter["ident"])
                if owner and owner not in names[side]:
                    names[side].append(owner)
        return (", ".join(names["A"]) or "Side A", ", ".join(names["B"]) or "Side B")

    def _embed(self, fight, snapshot, teams, seconds, events=None) -> discord.Embed:
        snapshot = snapshot or self._blank(fight)
        body = scrap_embed.scoreboard(snapshot, seconds_left=seconds or None,
                                      teams=teams, events=events)
        return messages.embed(body, title=lang.FIGHT_TITLE)

    async def _finish(self, message, fight, teams) -> None:
        outcome = fight.outcome()
        snapshot = fight.rounds[-1]
        body = scrap_embed.scoreboard(snapshot, teams=teams, finished=True)

        winner = outcome["winner"]
        lines = [lang.FIGHT_WINNER.format(team=teams[0] if winner == "A" else teams[1])
                 if winner else lang.FIGHT_NO_WINNER]
        lines.extend(scrap_store.describe(outcome))
        try:
            scrap_store.apply_outcome(outcome)
        except Exception as error:                       # noqa: BLE001
            # The fight happened whatever the database says. Never let a write
            # failure eat the result the channel just watched.
            self.bot.logger.exception("Scrap: could not write the outcome: %s", error)
            lines.append(lang.FIGHT_NOT_SAVED)

        embed = messages.success(body + "\n\n" + "\n".join(lines), title=lang.FIGHT_TITLE)
        await message.edit(embed=embed)
        self.live.pop(message.id, None)


async def setup(bot):
    await bot.add_cog(Fight(bot))
