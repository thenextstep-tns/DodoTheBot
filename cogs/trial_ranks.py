"""
Trial ranking runtime — clears/achievements into points, points into a rank role.

Recalculated the moment a scoring role changes, so getting a clear role hands
you the rank immediately, and swept hourly so nothing drifts if an event is
missed.

**Nobody is automated until they opt in.** The feature being enabled is not
consent: the sweep and the role listener both skip anyone who isn't enrolled, so
switching this on cannot rewrite a single role by itself. People arrive on the
list one of two ways — an admin enrols a specific user tag from the panel, or
the person presses the button on the announcement and says yes. Both are
recorded, and every action the automation takes is logged to the server's log
channel, because roles changing by themselves needs to be auditable.
"""

from __future__ import annotations

import asyncio
import io

import discord
from discord.ext import commands, tasks

from helpers import trial_ranks, trial_image

# Role edits per guild per sweep, paced — a first run can re-rank everyone.
MAX_EDITS = 200
EDIT_PAUSE = 0.35
# How long the "may I switch you over?" ask waits before letting it go.
CONSENT_TIMEOUT = 120.0
# Segments in the /rank progress bar. Discord's font renders these two cleanly
# at any size; the block characters (█/░) turn into visual static instead.
BAR_FULL, BAR_EMPTY = "▰", "▱"
BAR_WIDTH = 12
# Past this many rungs a star row stops being readable and becomes a wall.
MAX_STARS = 12
# Badge file extension per stored type — Discord renders an attachment by its
# name, so a JPEG called .png is a broken thumbnail.
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg",
               "image/webp": "webp", "image/gif": "gif"}

ANNOUNCEMENT_TEXT = (
    "## ✨ Dodo does the ranks now\n"
    "Your clears, added up, straight into a rank — no more waiting for someone to notice.\n"
    "Press the button to see where you stand. Only you will see it."
)

HOW_IT_WORKS = (
    "## ✨ How it works\n"
    "• Every clear is worth points — **the newer and harder it is, the more it's worth.**\n"
    "• Only your **best clear per trial** counts, so a trifecta doesn't pay twice.\n"
    "• **More points, higher rank.** Hit the number, get the role.\n"
    "• New clear role? Your rank moves within seconds.\n\n"
    "The chart below has every price on it. 👇"
)


def progress_bar(fraction: float, width: int = BAR_WIDTH) -> str:
    """A bar whose ends mean what they look like.

    Rounding alone renders the first points after a rank-up as an empty bar
    ("broken", not "just started") and the last point before one as a full bar
    ("arrived", when they haven't). Both ends are reserved for the real thing.
    """
    filled = max(0, min(width, round(fraction * width)))
    if fraction > 0:
        filled = max(1, filled)
    if fraction < 1:
        filled = min(width - 1, filled)
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def rank_stars(position: int, total: int) -> str:
    """The ladder as stars: how far up, out of how many rungs there are."""
    if total <= 0:
        return ""
    if total > MAX_STARS:
        return f"⭐ {position}/{total}"
    return "★" * position + "☆" * (total - position)


class RankBoardView(discord.ui.View):
    """The announcement's button. Persistent: it has to survive a restart, since
    the message stays pinned long after the process that posted it is gone."""

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="✨ CHECK MY RANK ✨",
                       style=discord.ButtonStyle.success,
                       custom_id="trialranks:check")
    async def check(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.bot.get_cog("trial_ranks")
        if cog is None:
            await interaction.response.send_message(
                "Ranking is not available right now — try again in a minute.", ephemeral=True)
            return
        await cog.handle_check(interaction)


class ConsentView(discord.ui.View):
    """The "may I switch you over?" ask, shown to someone still ranked by hand.

    Timing out is an answer too, and a polite one: nobody is enrolled by silence,
    and the message says so rather than just vanishing.
    """

    def __init__(self, cog, member) -> None:
        super().__init__(timeout=CONSENT_TIMEOUT)
        self.cog = cog
        self.member = member
        # One of these two is how we get the last word in: a slash/button reply
        # is edited through its interaction, a prefix reply through its message.
        self.interaction: discord.Interaction | None = None
        self.message: discord.Message | None = None
        self.settled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("That question wasn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Sure!", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.settled = True
        self.stop()
        await self.cog.accept_consent(interaction, self.member)

    @discord.ui.button(label="How exactly does it work?", style=discord.ButtonStyle.secondary)
    async def explain(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.explain_system(interaction, self.member)

    async def on_timeout(self) -> None:
        if self.settled:
            return
        self.cog.bot.trial_ranks.set_state(
            self.member.guild.id, self.member.id, trial_ranks.STATE_DISMISSED,
            name=self.member.display_name, source="button")
        text = ("Hey, no biggie — thank you for getting this far. "
                "Your rank stays exactly as it is, and you can press the button again "
                "whenever you like.")
        try:
            if self.interaction is not None:
                await self.interaction.edit_original_response(content=text, embed=None, view=None)
            elif self.message is not None:
                await self.message.edit(content=text, embed=None, view=None)
        except discord.HTTPException:
            pass
        await self.cog.log_event(
            self.member.guild,
            f"{self.member.mention} let the automatic-ranking question time out "
            f"(still on the manual system).")


class TrialRanks(commands.Cog, name="trial_ranks"):
    """Keeps each enrolled member's trial rank in step with their clears."""

    def __init__(self, bot):
        self.bot = bot
        self.last_run: dict[int, dict] = {}
        self.sweep.start()

    async def cog_load(self) -> None:
        # Re-attach the pinned message's button to this process.
        self.bot.add_view(RankBoardView(self.bot))

    def cog_unload(self) -> None:
        self.sweep.cancel()

    # ------------------------------------------------------------------ #
    #  Logging to Discord
    # ------------------------------------------------------------------ #
    async def log_event(self, guild, description: str, *, title: str = "Trial ranks") -> None:
        """Say what happened in the server's log channel. Never raises: a missing
        log channel must not stop a role change that already happened."""
        try:
            channel_id = self.bot.guild_config.get(guild.id, "LOG_CHANNEL")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            if channel is None:
                return
            embed = discord.Embed(title=title, description=description[:4000],
                                  colour=discord.Colour.blurple())
            await channel.send(embed=embed)
        except Exception as error:  # noqa: BLE001 - logging is never load-bearing
            self.bot.logger.error(f"Trial rank log failed for {guild.id}: {error}")

    # ------------------------------------------------------------------ #
    #  Applying
    # ------------------------------------------------------------------ #
    async def apply(self, member, config: dict, *, edit: bool = True) -> dict:
        """Tidy a member's trial roles, then set the rank their score earns."""
        points = config.get("points") or {}
        ranks = config.get("ranks") or []
        trials = config.get("trials") or []
        held = {role.id for role in member.roles}

        # One role per trial: a stronger clear replaces the weaker ones, so the
        # scoring below sees the same tidy set the member will end up with.
        stale = trial_ranks.superseded(held, trials)
        out = {"score": 0, "rank": None, "granted": 0, "removed": 0, "cleared": 0,
               "cleared_names": [], "rank_name": None}
        if stale and edit:
            roles = [member.guild.get_role(role_id) for role_id in stale]
            roles = [role for role in roles if role is not None]
            if roles:
                try:
                    await member.remove_roles(*roles, reason="Superseded by a better clear")
                    out["cleared"] = len(roles)
                    out["cleared_names"] = [role.name for role in roles]
                    held -= stale
                except discord.HTTPException:
                    pass

        score = trial_ranks.score_for(held, points, trials=trials)
        rank = trial_ranks.rank_for(score, ranks)
        out["score"], out["rank"] = score, rank
        out["rank_name"] = trial_ranks.rank_name(rank, member.guild) if rank else None
        if not ranks or not edit:
            return out

        keep = rank["role_id"] if rank else None
        exclusive = config.get("exclusive", True)
        to_add, to_remove = [], []
        for rung in ranks:
            role = member.guild.get_role(rung["role_id"])
            if role is None:
                continue
            if role.id == keep and role.id not in held:
                to_add.append(role)
            elif role.id != keep and role.id in held and exclusive:
                to_remove.append(role)
        try:
            if to_add:
                await member.add_roles(
                    *to_add, reason=f"Trial rank: {out['rank_name']} ({score} pts)")
                out["granted"] = len(to_add)
            if to_remove:
                await member.remove_roles(*to_remove, reason="Trial rank changed")
                out["removed"] = len(to_remove)
        except discord.HTTPException:
            pass
        return out

    async def enrol(self, member, *, source: str, actor=None) -> dict:
        """Switch one person onto the automated system, and bring them up to date.

        This is the whole turn-on in one call: record the consent, take off the
        clear roles a better clear has replaced, score what's left, grant the
        rank those points earn. From here the listener keeps them current,
        because the listener only acts on enrolled members.
        """
        config = self.bot.trial_ranks.get(member.guild.id)
        self.bot.trial_ranks.set_state(
            member.guild.id, member.id, trial_ranks.STATE_ENROLLED,
            name=member.display_name, source=source)
        outcome = await self.apply(member, config)
        await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.save_standing, member.guild.id, member.id,
            member.display_name, outcome["score"], outcome["rank_name"])

        by = f" (enrolled by {actor.mention})" if actor is not None else " (opted in themselves)"
        lines = [f"{member.mention} is now on automatic ranking{by}.",
                 f"Score: **{outcome['score']}** points · "
                 f"Rank: **{outcome['rank_name'] or 'none yet'}**"]
        if outcome["cleared_names"]:
            lines.append("Removed superseded clear roles: "
                         + ", ".join(outcome["cleared_names"][:20]))
        if outcome["granted"]:
            lines.append("Rank role granted.")
        if outcome["removed"]:
            lines.append("Previous rank role(s) removed.")
        await self.log_event(member.guild, "\n".join(lines), title="Trial ranks — enrolled")
        return outcome

    async def run_for_guild(self, guild, *, edit: bool = True) -> dict:
        config = self.bot.trial_ranks.get(guild.id)
        summary = {"members": 0, "ranked": 0, "granted": 0, "removed": 0, "cleared": 0,
                   "enrolled": 0}
        if not config.get("enabled"):
            return {**summary, "skipped": "feature off"}
        enrolled = self.bot.trial_ranks.enrolled_ids(guild.id)
        summary["enrolled"] = len(enrolled)
        if not enrolled:
            return {**summary, "skipped": "nobody enrolled yet"}
        edits = 0
        for member in guild.members:
            # The pilot is the point: an un-enrolled member is not touched, not
            # scored, and not written to the standings.
            if member.bot or member.id not in enrolled:
                continue
            outcome = await self.apply(member, config, edit=edit and edits < MAX_EDITS)
            summary["cleared"] += outcome.get("cleared", 0)
            if outcome["granted"] or outcome["removed"] or outcome.get("cleared"):
                edits += 1
                await asyncio.sleep(EDIT_PAUSE)
            summary["members"] += 1
            summary["granted"] += outcome["granted"]
            summary["removed"] += outcome["removed"]
            if outcome["score"]:
                summary["ranked"] += 1
                await self.bot.loop.run_in_executor(
                    None, self.bot.trial_ranks.save_standing, guild.id, member.id,
                    member.display_name, outcome["score"], outcome["rank_name"])
        self.last_run[guild.id] = summary
        return summary

    # ------------------------------------------------------------------ #
    #  The rank card
    # ------------------------------------------------------------------ #
    def rank_view(self, member) -> dict:
        """Everything /rank needs, computed off the roles the member holds."""
        config = self.bot.trial_ranks.get(member.guild.id)
        held = {role.id for role in member.roles}
        return trial_ranks.missing_for_next(
            member.guild, held, config.get("points") or {}, config.get("ranks") or [],
            trials=config.get("trials") or [])

    async def rank_embed(self, member) -> tuple[discord.Embed, list]:
        """The pretty card: where they are, how far along, and what's next."""
        state = self.rank_view(member)
        current, upcoming = state["current"], state["next"]
        current_name = trial_ranks.rank_name(current, member.guild) if current else None

        config = self.bot.trial_ranks.get(member.guild.id)
        if not config.get("ranks"):
            # No rungs configured: "you're at the top of the ladder" would be a
            # lie about a ladder that doesn't exist yet.
            embed = discord.Embed(
                title="No ranks set up yet",
                description="This server hasn't set its rank ladder up, so there's nothing "
                            "to measure you against. Your clears still count — ask an officer.",
                colour=discord.Colour.blurple())
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name=f"{state['score']} points", value="from the clears you hold",
                            inline=False)
            return embed, []

        stars = rank_stars(state["position"], state["total"])
        embed = discord.Embed(
            title=f"{current_name or 'No rank yet'}  {stars}".strip(),
            colour=member.colour if member.colour.value else discord.Colour.blurple(),
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        if current and current.get("description"):
            embed.description = current["description"]

        if upcoming is None:
            embed.add_field(
                name=f"{state['score']} points",
                value=f"{progress_bar(1.0)}\nTop of the ladder. Nothing left to prove. 🏆",
                inline=False)
        else:
            next_name = trial_ranks.rank_name(upcoming, member.guild)
            # Points, not a percentage: "1%" right after a rank-up told nobody
            # anything, while "252 → 375" is the actual question being asked.
            embed.add_field(
                name=f"{state['score']} points",
                value=(f"{progress_bar(state['fraction'])}  "
                       f"{state['score']} → {upcoming['min_points']}\n"
                       f"**{state['needed']}** more to reach **{next_name}**"),
                inline=False)
            if state["steps"]:
                lines = [f"• **+{step['gain']}** — {step['name']}" for step in state["steps"]]
                embed.add_field(name="Next steps:", value="\n".join(lines)[:1024], inline=False)
            else:
                embed.add_field(
                    name="Next steps:",
                    value="Nothing on the board is priced for you yet — ask an officer "
                          "what's worth points.",
                    inline=False)

        embed.add_field(
            name="​",
            value=("You can use `/rank` anywhere on the server, any time — and I'll always "
                   "be here too. ✨\n"
                   "If you have a minute, let the mods know how well this matches your "
                   "actual skill."),
            inline=False)

        files = []
        if current:
            picture = self.bot.trial_ranks.image(member.guild.id, current["role_id"])
            if picture and picture.get("data"):
                # Attached rather than linked: the panel sits behind a login, so
                # there is no public URL for Discord to fetch. The extension has
                # to match what was uploaded for the embed to render it.
                extension = _EXTENSIONS.get(picture.get("content_type"), "png")
                name = f"rank.{extension}"
                files.append(discord.File(io.BytesIO(bytes(picture["data"])), filename=name))
                embed.set_thumbnail(url=f"attachment://{name}")
        embed.set_footer(text="Only your best clear per trial counts towards the total.")
        return embed, files

    # ------------------------------------------------------------------ #
    #  The consent flow
    # ------------------------------------------------------------------ #
    async def handle_check(self, interaction: discord.Interaction) -> None:
        """The announcement button: show the rank, or ask to switch them over."""
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "This only works inside the server.", ephemeral=True)
            return
        if self.bot.trial_ranks.is_enrolled(guild.id, member.id):
            # thinking=True makes a fresh ephemeral message the "original
            # response", so editing it can't touch the pinned announcement.
            await interaction.response.defer(ephemeral=True, thinking=True)
            embed, files = await self.rank_embed(member)
            await interaction.edit_original_response(embed=embed, attachments=files)
            await self.log_event(guild, f"{member.mention} checked their rank.")
            return

        self.bot.trial_ranks.set_state(guild.id, member.id, trial_ranks.STATE_PROMPTED,
                                       name=member.display_name, source="button")
        view = ConsentView(self, member)
        await interaction.response.send_message(
            content=(f"Hey {member.mention}! I see that we have been updating your rank "
                     "manually up until this point. Do you mind if I switch you to the new "
                     "system?\n\nIt reads the clears you already have and works your rank out "
                     "from them. Nothing else about your roles changes."),
            view=view, ephemeral=True)
        view.interaction = interaction
        await self.log_event(guild, f"{member.mention} was asked to switch to automatic ranking.")

    async def accept_consent(self, interaction: discord.Interaction, member) -> None:
        # Deferred *without* thinking, so the original response stays the
        # question — answering it turns that same message into the rank card.
        await interaction.response.defer()
        await self.enrol(member, source="button")
        embed, files = await self.rank_embed(member)
        await interaction.edit_original_response(
            content="You're on the automatic system now — here's where you stand.",
            embed=embed, attachments=files, view=None)

    async def explain_system(self, interaction: discord.Interaction, member) -> None:
        """Send the brief description plus the chart, privately.

        A separate ephemeral message: the question keeps its buttons, so reading
        the explanation and then saying yes is one flow rather than two.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        self.bot.trial_ranks.set_state(member.guild.id, member.id, trial_ranks.STATE_READ,
                                       name=member.display_name, source="button")
        config = self.bot.trial_ranks.get(member.guild.id)
        files = []
        try:
            png = await self.bot.loop.run_in_executor(
                None, trial_image.build, member.guild, config)
            files.append(discord.File(io.BytesIO(png), filename="trial-ranks.png"))
        except Exception as error:  # noqa: BLE001 - the words matter more than the picture
            self.bot.logger.error(f"Trial rank chart failed for {member.guild.id}: {error}")
        await interaction.edit_original_response(content=HOW_IT_WORKS, attachments=files)
        await self.log_event(
            member.guild, f"{member.mention} read how automatic ranking works.")

    # ------------------------------------------------------------------ #
    #  Commands
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(
        name="rank",
        description="Show your trial rank, your points and what you need for the next one.")
    @commands.guild_only()
    async def rank(self, context: commands.Context) -> None:
        member = context.author
        if not self.bot.trial_ranks.is_enrolled(context.guild.id, member.id):
            self.bot.trial_ranks.set_state(
                context.guild.id, member.id, trial_ranks.STATE_PROMPTED,
                name=member.display_name, source="command")
            view = ConsentView(self, member)
            message = await context.send(
                f"Hey {member.mention}! I see that we have been updating your rank manually "
                "up until this point. Do you mind if I switch you to the new system?",
                view=view, ephemeral=True)
            # A prefix invocation has no interaction, so the message it sent is
            # what gets the closing word when the ask times out.
            view.interaction = context.interaction
            view.message = message
            await self.log_event(context.guild,
                                 f"{member.mention} was asked to switch to automatic ranking.")
            return
        embed, files = await self.rank_embed(member)
        await context.send(embed=embed, files=files, ephemeral=True)
        await self.log_event(context.guild, f"{member.mention} checked their rank.")

    # ------------------------------------------------------------------ #
    #  The announcement
    # ------------------------------------------------------------------ #
    async def post_announcement(self, guild, channel) -> discord.Message:
        """Post (or repost) the pinned message carrying the rank button.

        An existing message is edited in place so the pin, and any reactions on
        it, survive a wording change.
        """
        config = self.bot.trial_ranks.get(guild.id)
        view = RankBoardView(self.bot)
        existing_id = int(config.get("announce_message_id") or 0)
        message = None
        if existing_id and int(config.get("announce_channel_id") or 0) == channel.id:
            try:
                message = await channel.fetch_message(existing_id)
                await message.edit(content=ANNOUNCEMENT_TEXT, view=view)
            except discord.HTTPException:
                message = None
        if message is None:
            message = await channel.send(ANNOUNCEMENT_TEXT, view=view)
            try:
                await message.pin(reason="Trial ranks announcement")
            except discord.HTTPException:
                pass  # missing Manage Messages shouldn't lose the message itself
        self.bot.trial_ranks.save(guild.id, {"announce_channel_id": channel.id,
                                             "announce_message_id": message.id})
        await self.log_event(
            guild, f"Automatic-ranking announcement posted in {channel.mention}.")
        return message

    # ------------------------------------------------------------------ #
    #  Triggers
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_member_update(self, before, after) -> None:
        if before.roles == after.roles or after.bot:
            return
        config = self.bot.trial_ranks.get(after.guild.id)
        if not config.get("enabled"):
            return
        # Opting in is what turns the listener on for a person.
        if not self.bot.trial_ranks.is_enrolled(after.guild.id, after.id):
            return
        changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        scoring = {int(role_id) for role_id in (config.get("points") or {})}
        scoring |= set(trial_ranks.slot_of(config.get("trials") or []))
        rank_roles = {rank["role_id"] for rank in config.get("ranks") or []}
        # Only react to scoring roles, and never to our own rank changes.
        if not (changed & scoring) or changed <= rank_roles:
            return
        try:
            was = trial_ranks.rank_for(
                trial_ranks.score_for({r.id for r in before.roles}, config.get("points") or {},
                                      trials=config.get("trials") or []),
                config.get("ranks") or [])
            outcome = await self.apply(after, config)
            await self.bot.loop.run_in_executor(
                None, self.bot.trial_ranks.save_standing, after.guild.id, after.id,
                after.display_name, outcome["score"], outcome["rank_name"],
            )
            if outcome["granted"] or outcome["removed"] or outcome["cleared"]:
                previous = trial_ranks.rank_name(was, after.guild) if was else "none"
                await self.log_event(
                    after.guild,
                    f"{after.mention} recalculated after a clear-role change.\n"
                    f"Score: **{outcome['score']}** points · "
                    f"Rank: **{previous}** → **{outcome['rank_name'] or 'none'}**"
                    + (f"\nRemoved superseded: {', '.join(outcome['cleared_names'][:20])}"
                       if outcome["cleared_names"] else ""))
        except Exception as error:  # noqa: BLE001 - never break the gateway
            self.bot.logger.error(f"Trial rank update failed for {after.id}: {error}")

    @tasks.loop(hours=1)
    async def sweep(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                if self.bot.trial_ranks.get(guild.id).get("enabled"):
                    await self.run_for_guild(guild)
            except Exception as error:  # noqa: BLE001
                self.bot.logger.error(f"Trial rank sweep failed for {guild.id}: {error}")

    @sweep.before_loop
    async def before_sweep(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(45)


async def setup(bot):
    await bot.add_cog(TrialRanks(bot))
