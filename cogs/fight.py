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
    """The minute before the bell. Lives on the fight message itself."""

    def __init__(self, cog: "Fight", timeout: float):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.fight_id: int = 0          # set once the message exists

    @discord.ui.button(label="Send a cat to fight", style=discord.ButtonStyle.blurple, emoji="🥊")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.take_signup(interaction, self.fight_id)


class _PickBest(discord.ui.View):
    """Offered privately to somebody who owns cats but has never chosen one."""

    def __init__(self, cog: "Fight", fight_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.cog, self.fight_id = cog, fight_id

    @discord.ui.button(label="Send my best cat", style=discord.ButtonStyle.green, emoji="⭐")
    async def best(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.send_best(interaction, self.fight_id)


class _FighterButton(discord.ui.Button):
    """One cat off the roster, sent in by name."""

    def __init__(self, cog: "Fight", fight_id: int, pet: dict, row: int):
        super().__init__(label=str(pet.get("name"))[:70], style=discord.ButtonStyle.blurple,
                         emoji="\U0001F408", row=row)
        self.cog, self.fight_id, self.ident = cog, fight_id, str(pet["_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.send_one(interaction, self.fight_id, self.ident)


class _OtherBestButton(discord.ui.Button):
    """The next best cat that is not already on the roster."""

    def __init__(self, cog: "Fight", fight_id: int, row: int):
        super().__init__(label="Pick my other best cat", style=discord.ButtonStyle.green,
                         emoji="\u2B50", row=row)
        self.cog, self.fight_id = cog, fight_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.send_best(interaction, self.fight_id, beyond_roster=True)


def _chooser(cog: "Fight", fight_id: int, roster: list, already: set) -> discord.ui.View:
    """A private button per cat you have picked, plus the shortcut.

    Pressing "send a cat to fight" used to just throw the whole roster in, which
    takes the choice away from the one person who has actually thought about it.
    """
    view = discord.ui.View(timeout=60)
    row = 0
    for index, pet in enumerate(roster):
        if str(pet["_id"]) in already:
            continue
        view.add_item(_FighterButton(cog, fight_id, pet, row=min(4, index // 3)))
        row = min(4, index // 3)
    view.add_item(_OtherBestButton(cog, fight_id, row=min(4, row + 1)))
    return view


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
        state = {"sides": {"A": [], "B": []}, "owners": {}, "guild": context.guild, "shows": []}
        message = await context.send(embed=self._signup_embed(state, seconds), view=view)
        view.fight_id = message.id
        state["message"] = message
        self.live[message.id] = state

        await self._countdown(message, seconds, state)
        view.stop()

        state = self.live.get(message.id)
        if not state or not state["sides"]["A"] or not state["sides"]["B"]:
            self.live.pop(message.id, None)
            await message.edit(embed=messages.warning(lang.FIGHT_NOBODY_CAME), view=None)
            return
        await self._run(message, state)

    def _signup_embed(self, state: dict, seconds: int) -> discord.Embed:
        """The sign-up card, including who has actually turned up.

        The roster is the point: a sign-up window with no visible list is a
        minute of people wondering whether their click did anything.
        """
        embed = messages.embed(lang.FIGHT_SIGNUP.format(seconds=max(0, seconds)),
                               title=lang.FIGHT_SIGNUP_TITLE)
        for side, label in (("A", lang.FIGHT_SIDE_A), ("B", lang.FIGHT_SIDE_B)):
            fighters = state["sides"][side]
            if fighters:
                lines = "\n".join(
                    f"{scrap.classify(f).emoji} **{f['name']}** · {state['owners'].get(f['ident'], '?')}"
                    for f in fighters)
            else:
                lines = lang.FIGHT_SIDE_EMPTY
            embed.add_field(name=f"{label} ({len(fighters)})", value=lines, inline=True)
        return embed

    async def _refresh(self, state: dict, seconds: int) -> None:
        try:
            await state["message"].edit(embed=self._signup_embed(state, seconds))
        except (discord.HTTPException, KeyError):
            pass

    async def _countdown(self, message, seconds: int, state: dict) -> None:
        """Tick the sign-up clock down in place, redrawing the roster with it."""
        for remaining in range(seconds, 0, -1):
            state["seconds_left"] = remaining
            # Every second would breach the per-channel edit limit; this is
            # often enough to feel live, and a join redraws it immediately.
            if remaining % 5 == 0 or remaining <= 5:
                await self._refresh(state, remaining)
            await asyncio.sleep(1)

    def _already(self, state: dict) -> set:
        return {f["ident"] for side in state["sides"].values() for f in side}

    async def take_signup(self, interaction: discord.Interaction, fight_id: int) -> None:
        """Somebody pressed the button. Offer them their own cats, by name."""
        state = self.live.get(fight_id)
        if state is None:
            await interaction.response.send_message(lang.FIGHT_OVER_ALREADY, ephemeral=True)
            return

        already = self._already(state)
        roster = [p for p in scrap_lobby.roster(interaction.user.id) if str(p["_id"]) not in already]
        if roster:
            await interaction.response.send_message(
                lang.FIGHT_CHOOSE.format(hint=lang.FIGHT_SUMMON_HINT),
                view=_chooser(self, fight_id, roster, already), ephemeral=True)
            return

        result = scrap_lobby.join(interaction.user.id, already=already)
        view = _PickBest(self, fight_id) if result["status"] == scrap_lobby.NO_ROSTER else None
        await interaction.response.send_message(scrap_lobby.explain(result),
                                                view=view, ephemeral=True)

    async def send_best(self, interaction: discord.Interaction, fight_id: int,
                        *, beyond_roster: bool = False) -> None:
        """Enrol the best cat they own and send it in.

        ``beyond_roster`` skips the cats already on the roster, so "my other best
        cat" means the next one down rather than the one already fighting.
        """
        state = self.live.get(fight_id)
        if state is None:
            await interaction.response.edit_message(content=lang.FIGHT_OVER_ALREADY, view=None)
            return

        skip = self._already(state)
        if beyond_roster:
            skip |= {str(p["_id"]) for p in scrap_lobby.roster(interaction.user.id)}
        pets = [p for p in scrap_lobby.owned(interaction.user.id) if str(p["_id"]) not in skip]
        best = scrap_lobby.best_of(pets)
        if best is None:
            await interaction.response.edit_message(content=lang.FIGHT_NO_MORE_CATS, view=None)
            return

        scrap_lobby.enrol(interaction.user.id, str(best["_id"]))
        await self._put_in(interaction, state, best)

    async def send_one(self, interaction: discord.Interaction, fight_id: int, ident: str) -> None:
        """Send one named cat off the roster."""
        state = self.live.get(fight_id)
        if state is None:
            await interaction.response.edit_message(content=lang.FIGHT_OVER_ALREADY, view=None)
            return
        pet = next((p for p in scrap_lobby.owned(interaction.user.id) if str(p["_id"]) == ident), None)
        if pet is None:
            await interaction.response.edit_message(content=lang.FIGHT_CAT_GONE, view=None)
            return
        await self._put_in(interaction, state, pet)

    async def _put_in(self, interaction: discord.Interaction, state: dict, pet: dict) -> None:
        """Place one cat on the thinner side and redraw the roster."""
        cap = int(scrap.TUNING["roster_max"])
        side = "A" if len(state["sides"]["A"]) <= len(state["sides"]["B"]) else "B"
        if len(state["sides"][side]) >= cap:
            await interaction.response.edit_message(content=lang.FIGHT_SIDES_FULL, view=None)
            return

        fighter = scrap_lobby.as_fighter(pet)
        state["sides"][side].append(fighter)
        state["owners"][fighter["ident"]] = interaction.user.display_name
        await interaction.response.edit_message(
            content=lang.FIGHT_JOINED.format(names=fighter["name"]), view=None)
        await self._refresh(state, state.get("seconds_left", 0))

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
