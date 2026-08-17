"""
Trial ranking runtime — clears/achievements into points, points into a rank role.

Recalculated at the two moments that matter: the instant a scoring role changes,
and whenever someone asks where they stand. There is no periodic sweep — an
hourly pass over the whole guild spent nearly all its effort confirming nothing
had changed, and left an answer up to an hour stale when it hadn't.

**Nobody is automated until they opt in.** Enrolment is the only switch there
is: every path skips anyone who isn't on the list, so nothing here can rewrite a
role for somebody who never said yes. People arrive on the
list one of two ways — an admin enrols a specific user tag from the panel, or
the person presses the button on the announcement and says yes. Both are
recorded, and every action the automation takes is logged to the server's log
channel, because roles changing by themselves needs to be auditable.
"""

from __future__ import annotations

import asyncio
import io
import math

import discord
from discord.ext import commands

import lang
from helpers import trial_ranks, trial_image

# Role edits per guild per manual recalculation, paced — the first run after a
# rebalance can re-rank everyone at once.
MAX_EDITS = 200
EDIT_PAUSE = 0.35
# How long the "may I switch you over?" ask waits before letting it go.
CONSENT_TIMEOUT = 120.0
# Segments in the /rank progress bar. Discord's font renders these two cleanly
# at any size; the block characters (█/░) turn into visual static instead.
BAR_FULL, BAR_EMPTY = "▰", "▱"
BAR_WIDTH = 12
# Past this many ranks a star row stops being readable and becomes a wall.
MAX_STARS = 12
# Both halves of the row have to be emoji. Mixing ⭐ with the text glyph ☆ put
# two different rendering systems side by side — different size, weight and
# baseline — which looked like a mistake rather than like an empty slot. ⚪ is
# the grey counterpart: same size, same baseline, recedes against the gold.
# (⚫ is the dark-theme-only version of the same idea; it vanishes on light.)
STAR_EARNED, STAR_TODO = "⭐", "⚪"
# How close a raid (or a single clear) is to having a group, at a glance. Same
# bands as the panel's colours, so the two never disagree.
INTEREST_MARKS = {trial_ranks.LEVEL_READY: "🟢", trial_ranks.LEVEL_WARM: "🟡",
                  trial_ranks.LEVEL_COLD: "⚪"}
# Badge file extension per stored type — Discord renders an attachment by its
# name, so a JPEG called .png is a broken thumbnail.
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg",
               "image/webp": "webp", "image/gif": "gif"}

# Every user-facing string lives in lang.py so it can be edited from the panel's
# Strings page. They are read through the module (``lang.TRIAL_…``) at call time,
# never bound to a local at import, because that is what makes an override on a
# running bot take effect without a restart.


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
        return f"{STAR_EARNED} {position}/{total}"
    return STAR_EARNED * position + STAR_TODO * (total - position)


class RankBoardView(discord.ui.View):
    """The announcement's button. Persistent: it has to survive a restart, since
    the message stays pinned long after the process that posted it is gone."""

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        # The decorator's label is fixed at import; the live string isn't.
        self.check.label = lang.TRIAL_BUTTON_LABEL

    @discord.ui.button(label="✨ CHECK MY RANK ✨",
                       style=discord.ButtonStyle.success,
                       custom_id="trialranks:check")
    async def check(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.bot.get_cog("trial_ranks")
        if cog is None:
            await interaction.response.send_message(
                lang.TRIAL_ERROR_UNAVAILABLE, ephemeral=True)
            return
        await cog.handle_check(interaction)


class InterestView(discord.ui.View):
    """One button under the recommendations: "I'd join a prog for one of those".

    Deliberately the whole interaction. No menu, no follow-up question, no
    "which one?" — the card already lists what they'd be signing up for, so a
    single press records the lot and says thank you. Anything more would be a
    form, and nobody fills in a form to say "yeah, I'd raid".

    Not persistent: the card it hangs under is ephemeral and short-lived, so the
    button dies with the process rather than being restored on boot.
    """

    def __init__(self, cog, member, role_ids: list[int]) -> None:
        super().__init__(timeout=900)
        self.cog = cog
        self.member = member
        self.role_ids = list(role_ids)
        self.interest.label = lang.TRIAL_INTEREST_BUTTON

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.member.id

    @discord.ui.button(label="I'd join a prog for one of those 🔥",
                       style=discord.ButtonStyle.success)
    async def interest(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.record_interest(interaction, self.member, self.role_ids)
        self.stop()


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
        self.accept.label = lang.TRIAL_CONSENT_YES
        self.explain.label = lang.TRIAL_CONSENT_EXPLAIN

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                lang.TRIAL_CONSENT_NOT_YOURS, ephemeral=True)
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
        text = lang.TRIAL_CONSENT_TIMEOUT
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
        # When each distinct problem was last reported, per guild. A role
        # hierarchy that blocks one member blocks all of them, and the automatic
        # paths run constantly — without this the log channel would get the same
        # complaint every time anybody touched a role.
        self._reported: dict[int, dict[str, float]] = {}

    async def report_problems(self, guild, problems: list[str], *, context: str) -> None:
        """Log role-edit failures from the automatic paths, at most hourly each.

        The automation failing quietly is the thing that makes it untrustworthy:
        a card shows a rank nobody was given and nothing anywhere says why. So
        these are reported — just not forty times an hour.
        """
        if not problems:
            return
        now = asyncio.get_running_loop().time()
        seen = self._reported.setdefault(int(guild.id), {})
        fresh = [p for p in problems if now - seen.get(p, -math.inf) > 3600]
        if not fresh:
            return
        for problem in fresh:
            seen[problem] = now
        await self.log_event(
            guild,
            f"⚠️ **Ranks could not be applied** ({context}):\n"
            + "\n".join(f"• {problem}" for problem in fresh),
            title="Trial ranks: needs attention")

    def why_not_running(self, guild) -> str:
        """Why the automation is inert here, or "" if it isn't.

        Kept apart from :meth:`runs_here` so the listener can *say* what stopped
        it, rather than swallowing a role change in silence.
        """
        if not self.bot.visibility.cog_enabled(guild.id, "trial_ranks"):
            return "the **trial_ranks** cog is disabled for this server"
        return ""

    def runs_here(self, guild) -> bool:
        """Whether the automation should act in this guild at all.

        Enrolment is the switch. There is no separate feature toggle: a master
        flag above an opt-in list only ever meant one more way for a setup to be
        silently inert, and it is the enrolled list that decides who is touched.
        The cog's own per-guild state is still honoured, because the panel offers
        that toggle and a listener ignoring it would make the toggle a lie.
        """
        return self.bot.visibility.cog_enabled(guild.id, "trial_ranks")

    async def cog_load(self) -> None:
        # Re-attach the pinned message's button to this process.
        self.bot.add_view(RankBoardView(self.bot))

    # ------------------------------------------------------------------ #
    #  Logging to Discord
    # ------------------------------------------------------------------ #
    def log_channel(self, guild):
        """Where trial-rank activity is reported.

        Its own setting first — this is role-request traffic, not moderation, so
        it doesn't belong in the moderation log by default. Falling back to the
        role-request log keeps it in the right neighbourhood if nothing is
        chosen; the moderation log is only ever the last resort, so a server
        that has configured neither still gets its records somewhere.
        """
        chosen = int(self.bot.trial_ranks.get(guild.id).get("log_channel_id") or 0)
        if chosen:
            channel = guild.get_channel(chosen)
            if channel is not None:
                return channel
        for key in ("E4D_ROLE_LOG", "LOG_CHANNEL"):
            try:
                channel_id = int(self.bot.guild_config.get(guild.id, key) or 0)
            except (TypeError, ValueError):
                continue
            channel = guild.get_channel(channel_id) if channel_id else None
            if channel is not None:
                return channel
        return None

    async def log_event(self, guild, description: str, *, title: str = "Trial ranks") -> None:
        """Say what happened in the trial-rank log channel. Never raises: a
        missing log channel must not stop a role change that already happened."""
        try:
            channel = self.log_channel(guild)
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
               "cleared_names": [], "rank_name": None, "errors": [],
               "interest_dropped": 0}

        # Refusals used to be swallowed, which produced the worst possible
        # outcome: a card confidently showing a rank the member had not been
        # given, and nothing anywhere saying why. Every failure is collected and
        # reported now — a rank that couldn't be applied is a bug to fix, not a
        # detail to hide.
        me = member.guild.me
        if edit and (me is None or not me.guild_permissions.manage_roles):
            out["errors"].append(
                "I don't have the **Manage Roles** permission, so I can't change anyone's roles.")
            edit = False
        elif edit:
            # The rule that actually bites: Discord blocks a bot from touching
            # *any* role on a member whose highest role is at or above the
            # bot's own — the rank role being safely below me counts for
            # nothing. This is why it silently did nothing for staff while
            # working fine for everyone else.
            if member.id == getattr(member.guild, "owner_id", None):
                out["errors"].append(
                    "Discord never lets a bot change the **server owner's** roles, "
                    "whatever the hierarchy says. This one has to be done by hand.")
                edit = False
            elif member.top_role >= me.top_role:
                out["errors"].append(
                    f"**{member.display_name}**'s highest role "
                    f"(**{member.top_role.name}**) is above mine, so Discord won't let me "
                    f"change *any* of their roles, including ones below me. "
                    f"Drag my role above **{member.top_role.name}** in "
                    f"Server Settings → Roles.")
                edit = False

        async def edit_roles(action, roles, reason, what):
            """Apply one role change, turning a refusal into a plain sentence."""
            blocked = [role for role in roles if me is not None and role >= me.top_role]
            if blocked:
                out["errors"].append(
                    f"{', '.join(f'**{r.name}**' for r in blocked)} "
                    f"{'sit' if len(blocked) > 1 else 'sits'} above my highest role, "
                    f"so I can't {what} it. Drag my role above it in Server Settings → Roles.")
                roles = [role for role in roles if role not in blocked]
            if not roles:
                return []
            try:
                await action(*roles, reason=reason)
                return roles
            except discord.Forbidden:
                out["errors"].append(
                    f"Discord refused to let me {what} "
                    f"{', '.join(f'**{r.name}**' for r in roles)} (permissions).")
            except discord.HTTPException as error:
                out["errors"].append(f"Discord error while trying to {what} a role: {error}")
            return []

        if stale and edit:
            roles = [member.guild.get_role(role_id) for role_id in stale]
            roles = [role for role in roles if role is not None]
            if roles:
                removed = await edit_roles(member.remove_roles, roles,
                                           "Superseded by a better clear", "remove")
                if removed:
                    out["cleared"] = len(removed)
                    out["cleared_names"] = [role.name for role in removed]
                    held -= {role.id for role in removed}

        # World records are a person's, not a role's, so they're added here
        # rather than priced on the board with the clears.
        score = (trial_ranks.score_for(held, points, trials=trials)
                 + trial_ranks.wr_points(
                     self.bot.trial_ranks.wr_for(member.guild.id, member.id)))
        rank = trial_ranks.rank_for(score, ranks)

        # A want they have since satisfied is not a want. Every real
        # recalculation passes through here, so this is the one place it needs
        # to happen; a preview (edit=False) must not quietly edit anything.
        if edit:
            row = self.bot.trial_ranks.interest_rows(member.guild.id)
            mine = next((r for r in row if int(r["user_id"]) == member.id), None)
            if mine:
                done = trial_ranks.stale_interest(mine.get("role_ids") or [], held, trials)
                if done:
                    out["interest_dropped"] = self.bot.trial_ranks.drop_interest_roles(
                        member.guild.id, member.id, done)
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
        if to_add:
            out["granted"] = len(await edit_roles(
                member.add_roles, to_add,
                f"Trial rank: {out['rank_name']} ({score} pts)", "give"))
        if to_remove:
            out["removed"] = len(await edit_roles(
                member.remove_roles, to_remove, "Trial rank changed", "remove"))
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
        if outcome["errors"]:
            lines.append("⚠️ **The roles were not changed:**")
            lines.extend(f"• {problem}" for problem in outcome["errors"])
        await self.log_event(member.guild, "\n".join(lines), title="Trial ranks: enrolled")
        return outcome

    async def run_for_guild(self, guild, *, edit: bool = True) -> dict:
        config = self.bot.trial_ranks.get(guild.id)
        summary = {"members": 0, "ranked": 0, "granted": 0, "removed": 0, "cleared": 0,
                   "enrolled": 0, "errors": []}
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
            # Distinct problems only — one misplaced role produces the same
            # complaint for every member, and 40 copies of it help nobody.
            for problem in outcome["errors"]:
                if problem not in summary["errors"]:
                    summary["errors"].append(problem)
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
            trials=config.get("trials") or [],
            bonus=trial_ranks.wr_points(
                self.bot.trial_ranks.wr_for(member.guild.id, member.id)))

    async def rank_embed(self, member) -> tuple[discord.Embed, list, discord.ui.View | None]:
        """The pretty card: where they are, how far along, and what's next.

        Returns the view too — the interest button only exists when there are
        recommendations for it to refer to.
        """
        state = self.rank_view(member)
        current, upcoming = state["current"], state["next"]
        current_name = trial_ranks.rank_name(current, member.guild) if current else None

        config = self.bot.trial_ranks.get(member.guild.id)
        if not config.get("ranks"):
            # No rungs configured: "you're at the top of the ladder" would be a
            # lie about a ladder that doesn't exist yet.
            embed = discord.Embed(
                title=lang.TRIAL_NO_LADDER_TITLE,
                description=lang.TRIAL_NO_LADDER_BODY,
                colour=discord.Colour.blurple())
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name=lang.TRIAL_CARD_POINTS.format(points=state["score"]),
                            value=lang.TRIAL_NO_LADDER_POINTS, inline=False)
            return embed, [], None

        # The rank line lives in the description, not the title: a title renders
        # a role mention as literal text, while a description renders it in the
        # role's own colour — and mentions inside an embed never notify anyone.
        # The stars go on their own line so a phone can't wrap them into the name.
        stars = rank_stars(state["position"], state["total"])
        role = member.guild.get_role(int(current["role_id"])) if current else None
        name = role.mention if role is not None else f"**{current_name or lang.TRIAL_CARD_NO_RANK}**"
        blocks = [lang.TRIAL_CARD_HEADING.format(rank=name, stars=stars).strip()]
        if current and current.get("description"):
            blocks.append(current["description"])

        embed = discord.Embed(
            description="\n\n".join(blocks),
            colour=role.colour if role is not None and role.colour.value
            else (member.colour if member.colour.value else discord.Colour.blurple()),
        )
        # Records are the person's, so they sit with their name rather than
        # with the rank they helped earn.
        medals = trial_ranks.wr_medals(
            self.bot.trial_ranks.wr_for(member.guild.id, member.id))
        embed.set_author(name=f"{member.display_name} {medals}".strip(),
                         icon_url=member.display_avatar.url)

        points_label = lang.TRIAL_CARD_POINTS.format(points=state["score"])
        if upcoming is None:
            embed.add_field(name=points_label,
                            value=f"{progress_bar(1.0)}\n{lang.TRIAL_CARD_TOP}",
                            inline=False)
        else:
            next_role = member.guild.get_role(int(upcoming["role_id"]))
            next_name = (next_role.mention if next_role is not None
                         else f"**{trial_ranks.rank_name(upcoming, member.guild)}**")
            # Points, not a percentage: "1%" right after a rank-up told nobody
            # anything, while "252 → 375" is the actual question being asked.
            embed.add_field(
                name=points_label,
                value=(f"{progress_bar(state['fraction'])}  "
                       f"{state['score']} → {upcoming['min_points']}\n"
                       + lang.TRIAL_CARD_PROGRESS.format(needed=state["needed"],
                                                         next=next_name)),
                inline=False)
            if state["steps"]:
                lines = [f"• **+{step['gain']}** · {step['name']}" for step in state["steps"]]
                value = "\n".join(lines)[:1024]
            else:
                value = lang.TRIAL_CARD_STEPS_EMPTY
            embed.add_field(name=lang.TRIAL_CARD_STEPS_TITLE, value=value, inline=False)

        embed.add_field(name="​", value=lang.TRIAL_CARD_OUTRO, inline=False)

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
        embed.set_footer(text=lang.TRIAL_CARD_FOOTER)
        # The button refers to "one of those", so it only makes sense when the
        # card actually listed something.
        # Only trial roles can be progged for, so the button offers only those,
        # and doesn't appear at all when the advice is achievements alone.
        proggable = [step["role_id"] for step in state["steps"] if step["trial"] is not None]
        view = InterestView(self, member, proggable) if proggable else None
        return embed, files, view

    # ------------------------------------------------------------------ #
    #  The consent flow
    # ------------------------------------------------------------------ #
    async def handle_check(self, interaction: discord.Interaction) -> None:
        """The announcement button: show the rank, or ask to switch them over."""
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                lang.TRIAL_ERROR_GUILD_ONLY, ephemeral=True)
            return
        if self.bot.trial_ranks.is_enrolled(guild.id, member.id):
            # thinking=True makes a fresh ephemeral message the "original
            # response", so editing it can't touch the pinned announcement.
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.refresh(member)
            embed, files, view = await self.rank_embed(member)
            await interaction.edit_original_response(embed=embed, attachments=files,
                                                     view=view)
            await self.log_event(guild, f"{member.mention} checked their rank.")
            return

        self.bot.trial_ranks.set_state(guild.id, member.id, trial_ranks.STATE_PROMPTED,
                                       name=member.display_name, source="button")
        view = ConsentView(self, member)
        await interaction.response.send_message(
            content=lang.TRIAL_CONSENT_ASK.format(mention=member.mention),
            view=view, ephemeral=True)
        view.interaction = interaction
        await self.log_event(guild, f"{member.mention} was asked to switch to automatic ranking.")

    async def accept_consent(self, interaction: discord.Interaction, member) -> None:
        # Deferred *without* thinking, so the original response stays the
        # question — answering it turns that same message into the rank card.
        await interaction.response.defer()
        await self.enrol(member, source="button")
        embed, files, view = await self.rank_embed(member)
        await interaction.edit_original_response(
            content=lang.TRIAL_CONSENT_DONE,
            embed=embed, attachments=files, view=view)

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
        await interaction.edit_original_response(content=lang.TRIAL_HOW_IT_WORKS, attachments=files)
        await self.log_event(
            member.guild, f"{member.mention} read how automatic ranking works.")

    # ------------------------------------------------------------------ #
    #  Prog interest
    # ------------------------------------------------------------------ #
    async def record_interest(self, interaction: discord.Interaction, member,
                              role_ids: list[int]) -> None:
        """Bank the "I'd prog for one of those" press and thank them for it."""
        config = self.bot.trial_ranks.get(member.guild.id)
        mapped = set(trial_ranks.slot_of(config.get("trials") or []))
        role_ids = [r for r in role_ids if int(r) in mapped]
        await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.record_interest, member.guild.id, member.id,
            member.display_name, role_ids)
        # edit_message keeps the card on screen and takes the button away, so
        # the whole interaction is one press and one thank-you.
        await interaction.response.edit_message(content=lang.TRIAL_INTEREST_THANKS, view=None)

        wanted = []
        for role_id in role_ids:
            role = member.guild.get_role(int(role_id))
            label = trial_ranks.trial_of_role(role_id, config.get("trials") or [])
            wanted.append(label or (role.name if role else str(role_id)))
        await self.log_event(
            member.guild,
            f"{member.mention} would join a prog for: "
            # dict.fromkeys keeps first-seen order while dropping the repeats a
            # hardmode and its trifecta produce for the same raid.
            + ", ".join(list(dict.fromkeys(wanted))[:20]),
            title="Trial ranks: prog interest")

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
                lang.TRIAL_CONSENT_ASK.format(mention=member.mention),
                view=view, ephemeral=True)
            # A prefix invocation has no interaction, so the message it sent is
            # what gets the closing word when the ask times out.
            view.interaction = context.interaction
            view.message = message
            await self.log_event(context.guild,
                                 f"{member.mention} was asked to switch to automatic ranking.")
            return
        # Acknowledge before doing anything slow. From here the command reads
        # Mongo and can edit roles, which does not fit inside Discord's three
        # second budget, and blowing it shows "the application did not respond"
        # even though the work went through. Deferred only on this branch: the
        # consent reply below is one cached read, and deferring it would change
        # which message the timeout has to edit.
        await context.defer(ephemeral=True)
        await self.refresh(member)
        embed, files, view = await self.rank_embed(member)
        await context.send(embed=embed, files=files, view=view or discord.utils.MISSING,
                           ephemeral=True)
        await self.log_event(context.guild, f"{member.mention} checked their rank.")

    async def trial_autocomplete(self, interaction: discord.Interaction, current: str):
        """Offer the raids people have actually shown interest in, busiest first."""
        guild = interaction.guild
        if guild is None:
            return []
        config = self.bot.trial_ranks.get(guild.id)
        rows = await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.interest_rows, guild.id)
        buckets = trial_ranks.interest_buckets(guild, config, rows)
        query = (current or "").lower()
        return [
            discord.app_commands.Choice(
                name=f"{bucket['name']} · {bucket['count']}/{trial_ranks.GROUP_SIZE}",
                value=bucket["name"])
            for bucket in buckets if query in bucket["name"].lower()
        ][:25]

    @commands.hybrid_command(
        name="interest",
        description="Who would join a prog, and which clears they still need.")
    @commands.guild_only()
    @discord.app_commands.describe(trial="Which trial, e.g. vRG. Leave empty for all of them")
    @discord.app_commands.autocomplete(trial=trial_autocomplete)
    async def interest(self, context: commands.Context, *, trial: str = "") -> None:
        config = self.bot.trial_ranks.get(context.guild.id)
        rows = await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.interest_rows, context.guild.id)
        buckets = trial_ranks.interest_buckets(context.guild, config, rows)
        if not buckets:
            await context.send(lang.TRIAL_INTEREST_EMPTY, ephemeral=True)
            return

        wanted = (trial or "").strip().lower()
        if not wanted:
            await context.send(embed=self._interest_overview(buckets), ephemeral=True)
            return

        bucket = next((b for b in buckets if b["name"].lower() == wanted), None)
        if bucket is None:
            # A near miss is far more likely than a typo nobody meant, so try a
            # contains-match before giving up.
            bucket = next((b for b in buckets if wanted in b["name"].lower()), None)
        if bucket is None:
            await context.send(lang.TRIAL_INTEREST_UNKNOWN.format(trial=trial), ephemeral=True)
            return
        await context.send(embed=self._interest_detail(context.guild, bucket), ephemeral=True)

    def _interest_overview(self, buckets: list[dict]) -> discord.Embed:
        """Every raid at a glance, busiest first."""
        embed = discord.Embed(title=lang.TRIAL_INTEREST_OVERVIEW,
                              colour=discord.Colour.blurple())
        lines = [f"{INTEREST_MARKS[b['level']]} **{b['count']}**/{trial_ranks.GROUP_SIZE}"
                 f" · {b['name']}" for b in buckets[:25]]
        embed.description = "\n".join(lines)
        embed.set_footer(text="/interest <trial> for who, and what they still need.")
        return embed

    def _interest_detail(self, guild, bucket: dict) -> discord.Embed:
        """One raid, down to the individual clear each person is missing."""
        colour = {trial_ranks.LEVEL_READY: discord.Colour.green(),
                  trial_ranks.LEVEL_WARM: discord.Colour.gold()}.get(
                      bucket["level"], discord.Colour.dark_grey())
        embed = discord.Embed(
            title=lang.TRIAL_INTEREST_TITLE.format(trial=bucket["name"]),
            description=lang.TRIAL_INTEREST_SUMMARY.format(
                count=bucket["count"], group=trial_ranks.GROUP_SIZE),
            colour=colour)

        # The whole point: a raid lead needs to know it's the Bahsei hardmode
        # three people are short of, not just that three people want vRG.
        breakdown = [
            f"{INTEREST_MARKS[entry['level']]} **{entry['count']}**/{trial_ranks.GROUP_SIZE}"
            f" · {entry['name']}"
            for entry in bucket["by_role"]
        ]
        if breakdown:
            embed.add_field(name=lang.TRIAL_INTEREST_BREAKDOWN,
                            value="\n".join(breakdown)[:1024], inline=False)

        lines = []
        for entry in sorted(bucket["members"], key=lambda m: m["name"].lower()):
            member = guild.get_member(entry["user_id"])
            who = member.mention if member else entry["name"]
            needs = ", ".join(role["name"] for role in entry.get("roles") or ())
            when = entry.get("at")
            stamp = f" · {when:%Y-%m-%d}" if hasattr(when, "strftime") else ""
            lines.append(f"• {who} · {needs}{stamp}" if needs else f"• {who}{stamp}")
        embed.add_field(name=lang.TRIAL_INTEREST_WHO,
                        value="\n".join(lines)[:1024] or "—", inline=False)
        return embed

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
                await message.edit(content=lang.TRIAL_ANNOUNCEMENT, view=view)
            except discord.HTTPException:
                message = None
        if message is None:
            message = await channel.send(lang.TRIAL_ANNOUNCEMENT, view=view)
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
        changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        scoring = {int(role_id) for role_id in (config.get("points") or {})}
        scoring |= set(trial_ranks.slot_of(config.get("trials") or []))
        rank_roles = {rank["role_id"] for rank in config.get("ranks") or []}
        # Only react to scoring roles, and never to our own rank changes.
        if not (changed & scoring) or changed <= rank_roles:
            return
        touched = ", ".join(
            role.name for role in (after.guild.get_role(r) for r in changed & scoring)
            if role is not None) or "a scoring role"
        # The master switch is checked here rather than at the top, so that a
        # scoring role changing while the feature is off produces an explanation
        # instead of nothing at all.
        stopped = self.why_not_running(after.guild)
        if stopped:
            await self.report_problems(
                after.guild,
                [f"{after.mention} changed **{touched}**, but {stopped}. "
                 "Nothing was recalculated."],
                context="not running")
            return

        # A scoring role moved on somebody the automation won't touch. Silence
        # here reads as "the bot is broken" rather than "that person opted out",
        # so it says which, once an hour per person rather than per role edit.
        if not self.bot.trial_ranks.is_enrolled(after.guild.id, after.id):
            await self.report_problems(
                after.guild,
                [f"{after.mention} changed **{touched}**, but they are not on "
                 "automatic ranking, so nothing was recalculated."],
                context="skipped")
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
            # Logged every time, not only when a role moved. A recalculation
            # that lands on the same rank is still the system working, and
            # without a line for it there is no way to tell that apart from the
            # listener never having fired at all.
            previous = trial_ranks.rank_name(was, after.guild) if was else "none"
            now_named = outcome["rank_name"] or "none"
            moved = previous != now_named
            lines_out = [f"{after.mention} · **{touched}**",
                         f"Score: **{outcome['score']}** · Rank: "
                         + (f"**{previous}** to **{now_named}**" if moved
                            else f"**{now_named}** (unchanged)")]
            if outcome["cleared_names"]:
                lines_out.append("Removed superseded: "
                                 + ", ".join(outcome["cleared_names"][:20]))
            if outcome.get("interest_dropped"):
                lines_out.append(f"Prog interest: {outcome['interest_dropped']} "
                                 "entry(s) cleared, now earned.")
            await self.log_event(after.guild, chr(10).join(lines_out),
                                 title="Trial ranks: recalculated")
            # A recalculation that changed nothing *because it was refused* is
            # not a quiet success, and this is the path that runs unattended.
            await self.report_problems(after.guild, outcome["errors"],
                                       context=f"{after.display_name} gained or lost a clear role")
        except Exception as error:  # noqa: BLE001 - never break the gateway
            self.bot.logger.error(f"Trial rank update failed for {after.id}: {error}")

    async def recalculate(self, member, *, why: str = "checked their rank") -> dict:
        """Re-score one person and apply it, returning what happened.

        The single path for "do this member now": the card uses it, and so does
        the panel's per-person button. Enrolment is still the gate, because a
        forced recalculation is not consent.
        """
        config = self.bot.trial_ranks.get(member.guild.id)
        outcome = await self.apply(member, config)
        await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.save_standing, member.guild.id, member.id,
            member.display_name, outcome["score"], outcome["rank_name"])
        if outcome["granted"] or outcome["removed"] or outcome["cleared"]:
            lines = [f"{member.mention} recalculated ({why}).",
                     f"Score: **{outcome['score']}** · "
                     f"Rank: **{outcome['rank_name'] or 'none'}**"]
            if outcome["cleared_names"]:
                lines.append("Removed superseded: "
                             + ", ".join(outcome["cleared_names"][:20]))
            if outcome.get("interest_dropped"):
                lines.append(f"Prog interest: {outcome['interest_dropped']} "
                             "entry(s) cleared, now earned.")
            await self.log_event(member.guild, chr(10).join(lines),
                                 title="Trial ranks: recalculated")
        await self.report_problems(member.guild, outcome["errors"], context=why)
        return outcome

    async def refresh(self, member) -> None:
        """Bring one person up to date before showing them their card.

        Replaces the hourly sweep: a whole-guild pass every hour spent almost
        all of its work confirming that nothing had changed. The two moments
        that actually matter are a scoring role changing (the listener) and the
        person asking where they stand, so checking then covers the same ground
        without the churn.
        """
        if not self.runs_here(member.guild):
            return
        if not self.bot.trial_ranks.is_enrolled(member.guild.id, member.id):
            return
        try:
            await self.recalculate(member)
        except Exception as error:  # noqa: BLE001 - showing the card matters more
            self.bot.logger.error(f"Trial rank refresh failed for {member.id}: {error}")

    # ------------------------------------------------------------------ #
    #  The rank card
    # ------------------------------------------------------------------ #
    def rank_view(self, member) -> dict:
        """Everything /rank needs, computed off the roles the member holds."""
        config = self.bot.trial_ranks.get(member.guild.id)
        held = {role.id for role in member.roles}
        return trial_ranks.missing_for_next(
            member.guild, held, config.get("points") or {}, config.get("ranks") or [],
            trials=config.get("trials") or [],
            bonus=trial_ranks.wr_points(
                self.bot.trial_ranks.wr_for(member.guild.id, member.id)))

    async def rank_embed(self, member) -> tuple[discord.Embed, list, discord.ui.View | None]:
        """The pretty card: where they are, how far along, and what's next.

        Returns the view too — the interest button only exists when there are
        recommendations for it to refer to.
        """
        state = self.rank_view(member)
        current, upcoming = state["current"], state["next"]
        current_name = trial_ranks.rank_name(current, member.guild) if current else None

        config = self.bot.trial_ranks.get(member.guild.id)
        if not config.get("ranks"):
            # No rungs configured: "you're at the top of the ladder" would be a
            # lie about a ladder that doesn't exist yet.
            embed = discord.Embed(
                title=lang.TRIAL_NO_LADDER_TITLE,
                description=lang.TRIAL_NO_LADDER_BODY,
                colour=discord.Colour.blurple())
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.add_field(name=lang.TRIAL_CARD_POINTS.format(points=state["score"]),
                            value=lang.TRIAL_NO_LADDER_POINTS, inline=False)
            return embed, [], None

        # The rank line lives in the description, not the title: a title renders
        # a role mention as literal text, while a description renders it in the
        # role's own colour — and mentions inside an embed never notify anyone.
        # The stars go on their own line so a phone can't wrap them into the name.
        stars = rank_stars(state["position"], state["total"])
        role = member.guild.get_role(int(current["role_id"])) if current else None
        name = role.mention if role is not None else f"**{current_name or lang.TRIAL_CARD_NO_RANK}**"
        blocks = [lang.TRIAL_CARD_HEADING.format(rank=name, stars=stars).strip()]
        if current and current.get("description"):
            blocks.append(current["description"])

        embed = discord.Embed(
            description="\n\n".join(blocks),
            colour=role.colour if role is not None and role.colour.value
            else (member.colour if member.colour.value else discord.Colour.blurple()),
        )
        # Records are the person's, so they sit with their name rather than
        # with the rank they helped earn.
        medals = trial_ranks.wr_medals(
            self.bot.trial_ranks.wr_for(member.guild.id, member.id))
        embed.set_author(name=f"{member.display_name} {medals}".strip(),
                         icon_url=member.display_avatar.url)

        points_label = lang.TRIAL_CARD_POINTS.format(points=state["score"])
        if upcoming is None:
            embed.add_field(name=points_label,
                            value=f"{progress_bar(1.0)}\n{lang.TRIAL_CARD_TOP}",
                            inline=False)
        else:
            next_role = member.guild.get_role(int(upcoming["role_id"]))
            next_name = (next_role.mention if next_role is not None
                         else f"**{trial_ranks.rank_name(upcoming, member.guild)}**")
            # Points, not a percentage: "1%" right after a rank-up told nobody
            # anything, while "252 → 375" is the actual question being asked.
            embed.add_field(
                name=points_label,
                value=(f"{progress_bar(state['fraction'])}  "
                       f"{state['score']} → {upcoming['min_points']}\n"
                       + lang.TRIAL_CARD_PROGRESS.format(needed=state["needed"],
                                                         next=next_name)),
                inline=False)
            if state["steps"]:
                lines = [f"• **+{step['gain']}** · {step['name']}" for step in state["steps"]]
                value = "\n".join(lines)[:1024]
            else:
                value = lang.TRIAL_CARD_STEPS_EMPTY
            embed.add_field(name=lang.TRIAL_CARD_STEPS_TITLE, value=value, inline=False)

        embed.add_field(name="​", value=lang.TRIAL_CARD_OUTRO, inline=False)

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
        embed.set_footer(text=lang.TRIAL_CARD_FOOTER)
        # The button refers to "one of those", so it only makes sense when the
        # card actually listed something.
        # Only trial roles can be progged for, so the button offers only those,
        # and doesn't appear at all when the advice is achievements alone.
        proggable = [step["role_id"] for step in state["steps"] if step["trial"] is not None]
        view = InterestView(self, member, proggable) if proggable else None
        return embed, files, view

    # ------------------------------------------------------------------ #
    #  The consent flow
    # ------------------------------------------------------------------ #
    async def handle_check(self, interaction: discord.Interaction) -> None:
        """The announcement button: show the rank, or ask to switch them over."""
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                lang.TRIAL_ERROR_GUILD_ONLY, ephemeral=True)
            return
        if self.bot.trial_ranks.is_enrolled(guild.id, member.id):
            # thinking=True makes a fresh ephemeral message the "original
            # response", so editing it can't touch the pinned announcement.
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.refresh(member)
            embed, files, view = await self.rank_embed(member)
            await interaction.edit_original_response(embed=embed, attachments=files,
                                                     view=view)
            await self.log_event(guild, f"{member.mention} checked their rank.")
            return

        self.bot.trial_ranks.set_state(guild.id, member.id, trial_ranks.STATE_PROMPTED,
                                       name=member.display_name, source="button")
        view = ConsentView(self, member)
        await interaction.response.send_message(
            content=lang.TRIAL_CONSENT_ASK.format(mention=member.mention),
            view=view, ephemeral=True)
        view.interaction = interaction
        await self.log_event(guild, f"{member.mention} was asked to switch to automatic ranking.")

    async def accept_consent(self, interaction: discord.Interaction, member) -> None:
        # Deferred *without* thinking, so the original response stays the
        # question — answering it turns that same message into the rank card.
        await interaction.response.defer()
        await self.enrol(member, source="button")
        embed, files, view = await self.rank_embed(member)
        await interaction.edit_original_response(
            content=lang.TRIAL_CONSENT_DONE,
            embed=embed, attachments=files, view=view)

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
        await interaction.edit_original_response(content=lang.TRIAL_HOW_IT_WORKS, attachments=files)
        await self.log_event(
            member.guild, f"{member.mention} read how automatic ranking works.")

    # ------------------------------------------------------------------ #
    #  Prog interest
    # ------------------------------------------------------------------ #
    async def record_interest(self, interaction: discord.Interaction, member,
                              role_ids: list[int]) -> None:
        """Bank the "I'd prog for one of those" press and thank them for it."""
        config = self.bot.trial_ranks.get(member.guild.id)
        mapped = set(trial_ranks.slot_of(config.get("trials") or []))
        role_ids = [r for r in role_ids if int(r) in mapped]
        await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.record_interest, member.guild.id, member.id,
            member.display_name, role_ids)
        # edit_message keeps the card on screen and takes the button away, so
        # the whole interaction is one press and one thank-you.
        await interaction.response.edit_message(content=lang.TRIAL_INTEREST_THANKS, view=None)

        wanted = []
        for role_id in role_ids:
            role = member.guild.get_role(int(role_id))
            label = trial_ranks.trial_of_role(role_id, config.get("trials") or [])
            wanted.append(label or (role.name if role else str(role_id)))
        await self.log_event(
            member.guild,
            f"{member.mention} would join a prog for: "
            # dict.fromkeys keeps first-seen order while dropping the repeats a
            # hardmode and its trifecta produce for the same raid.
            + ", ".join(list(dict.fromkeys(wanted))[:20]),
            title="Trial ranks: prog interest")

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
                lang.TRIAL_CONSENT_ASK.format(mention=member.mention),
                view=view, ephemeral=True)
            # A prefix invocation has no interaction, so the message it sent is
            # what gets the closing word when the ask times out.
            view.interaction = context.interaction
            view.message = message
            await self.log_event(context.guild,
                                 f"{member.mention} was asked to switch to automatic ranking.")
            return
        # Acknowledge before doing anything slow. From here the command reads
        # Mongo and can edit roles, which does not fit inside Discord's three
        # second budget, and blowing it shows "the application did not respond"
        # even though the work went through. Deferred only on this branch: the
        # consent reply below is one cached read, and deferring it would change
        # which message the timeout has to edit.
        await context.defer(ephemeral=True)
        await self.refresh(member)
        embed, files, view = await self.rank_embed(member)
        await context.send(embed=embed, files=files, view=view or discord.utils.MISSING,
                           ephemeral=True)
        await self.log_event(context.guild, f"{member.mention} checked their rank.")

    async def trial_autocomplete(self, interaction: discord.Interaction, current: str):
        """Offer the raids people have actually shown interest in, busiest first."""
        guild = interaction.guild
        if guild is None:
            return []
        config = self.bot.trial_ranks.get(guild.id)
        rows = await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.interest_rows, guild.id)
        buckets = trial_ranks.interest_buckets(guild, config, rows)
        query = (current or "").lower()
        return [
            discord.app_commands.Choice(
                name=f"{bucket['name']} · {bucket['count']}/{trial_ranks.GROUP_SIZE}",
                value=bucket["name"])
            for bucket in buckets if query in bucket["name"].lower()
        ][:25]

    @commands.hybrid_command(
        name="interest",
        description="Who would join a prog, and which clears they still need.")
    @commands.guild_only()
    @discord.app_commands.describe(trial="Which trial, e.g. vRG. Leave empty for all of them")
    @discord.app_commands.autocomplete(trial=trial_autocomplete)
    async def interest(self, context: commands.Context, *, trial: str = "") -> None:
        config = self.bot.trial_ranks.get(context.guild.id)
        rows = await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.interest_rows, context.guild.id)
        buckets = trial_ranks.interest_buckets(context.guild, config, rows)
        if not buckets:
            await context.send(lang.TRIAL_INTEREST_EMPTY, ephemeral=True)
            return

        wanted = (trial or "").strip().lower()
        if not wanted:
            await context.send(embed=self._interest_overview(buckets), ephemeral=True)
            return

        bucket = next((b for b in buckets if b["name"].lower() == wanted), None)
        if bucket is None:
            # A near miss is far more likely than a typo nobody meant, so try a
            # contains-match before giving up.
            bucket = next((b for b in buckets if wanted in b["name"].lower()), None)
        if bucket is None:
            await context.send(lang.TRIAL_INTEREST_UNKNOWN.format(trial=trial), ephemeral=True)
            return
        await context.send(embed=self._interest_detail(context.guild, bucket), ephemeral=True)

    def _interest_overview(self, buckets: list[dict]) -> discord.Embed:
        """Every raid at a glance, busiest first."""
        embed = discord.Embed(title=lang.TRIAL_INTEREST_OVERVIEW,
                              colour=discord.Colour.blurple())
        lines = [f"{INTEREST_MARKS[b['level']]} **{b['count']}**/{trial_ranks.GROUP_SIZE}"
                 f" · {b['name']}" for b in buckets[:25]]
        embed.description = "\n".join(lines)
        embed.set_footer(text="/interest <trial> for who, and what they still need.")
        return embed

    def _interest_detail(self, guild, bucket: dict) -> discord.Embed:
        """One raid, down to the individual clear each person is missing."""
        colour = {trial_ranks.LEVEL_READY: discord.Colour.green(),
                  trial_ranks.LEVEL_WARM: discord.Colour.gold()}.get(
                      bucket["level"], discord.Colour.dark_grey())
        embed = discord.Embed(
            title=lang.TRIAL_INTEREST_TITLE.format(trial=bucket["name"]),
            description=lang.TRIAL_INTEREST_SUMMARY.format(
                count=bucket["count"], group=trial_ranks.GROUP_SIZE),
            colour=colour)

        # The whole point: a raid lead needs to know it's the Bahsei hardmode
        # three people are short of, not just that three people want vRG.
        breakdown = [
            f"{INTEREST_MARKS[entry['level']]} **{entry['count']}**/{trial_ranks.GROUP_SIZE}"
            f" · {entry['name']}"
            for entry in bucket["by_role"]
        ]
        if breakdown:
            embed.add_field(name=lang.TRIAL_INTEREST_BREAKDOWN,
                            value="\n".join(breakdown)[:1024], inline=False)

        lines = []
        for entry in sorted(bucket["members"], key=lambda m: m["name"].lower()):
            member = guild.get_member(entry["user_id"])
            who = member.mention if member else entry["name"]
            needs = ", ".join(role["name"] for role in entry.get("roles") or ())
            when = entry.get("at")
            stamp = f" · {when:%Y-%m-%d}" if hasattr(when, "strftime") else ""
            lines.append(f"• {who} · {needs}{stamp}" if needs else f"• {who}{stamp}")
        embed.add_field(name=lang.TRIAL_INTEREST_WHO,
                        value="\n".join(lines)[:1024] or "—", inline=False)
        return embed

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
                await message.edit(content=lang.TRIAL_ANNOUNCEMENT, view=view)
            except discord.HTTPException:
                message = None
        if message is None:
            message = await channel.send(lang.TRIAL_ANNOUNCEMENT, view=view)
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
        changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        scoring = {int(role_id) for role_id in (config.get("points") or {})}
        scoring |= set(trial_ranks.slot_of(config.get("trials") or []))
        rank_roles = {rank["role_id"] for rank in config.get("ranks") or []}
        # Only react to scoring roles, and never to our own rank changes.
        if not (changed & scoring) or changed <= rank_roles:
            return
        touched = ", ".join(
            role.name for role in (after.guild.get_role(r) for r in changed & scoring)
            if role is not None) or "a scoring role"
        # The master switch is checked here rather than at the top, so that a
        # scoring role changing while the feature is off produces an explanation
        # instead of nothing at all.
        stopped = self.why_not_running(after.guild)
        if stopped:
            await self.report_problems(
                after.guild,
                [f"{after.mention} changed **{touched}**, but {stopped}. "
                 "Nothing was recalculated."],
                context="not running")
            return

        # A scoring role moved on somebody the automation won't touch. Silence
        # here reads as "the bot is broken" rather than "that person opted out",
        # so it says which, once an hour per person rather than per role edit.
        if not self.bot.trial_ranks.is_enrolled(after.guild.id, after.id):
            await self.report_problems(
                after.guild,
                [f"{after.mention} changed **{touched}**, but they are not on "
                 "automatic ranking, so nothing was recalculated."],
                context="skipped")
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
            # Logged every time, not only when a role moved. A recalculation
            # that lands on the same rank is still the system working, and
            # without a line for it there is no way to tell that apart from the
            # listener never having fired at all.
            previous = trial_ranks.rank_name(was, after.guild) if was else "none"
            now_named = outcome["rank_name"] or "none"
            moved = previous != now_named
            lines_out = [f"{after.mention} · **{touched}**",
                         f"Score: **{outcome['score']}** · Rank: "
                         + (f"**{previous}** to **{now_named}**" if moved
                            else f"**{now_named}** (unchanged)")]
            if outcome["cleared_names"]:
                lines_out.append("Removed superseded: "
                                 + ", ".join(outcome["cleared_names"][:20]))
            if outcome.get("interest_dropped"):
                lines_out.append(f"Prog interest: {outcome['interest_dropped']} "
                                 "entry(s) cleared, now earned.")
            await self.log_event(after.guild, chr(10).join(lines_out),
                                 title="Trial ranks: recalculated")
            # A recalculation that changed nothing *because it was refused* is
            # not a quiet success, and this is the path that runs unattended.
            await self.report_problems(after.guild, outcome["errors"],
                                       context=f"{after.display_name} gained or lost a clear role")
        except Exception as error:  # noqa: BLE001 - never break the gateway
            self.bot.logger.error(f"Trial rank update failed for {after.id}: {error}")

    async def recalculate(self, member, *, why: str = "checked their rank") -> dict:
        """Re-score one person and apply it, returning what happened.

        The single path for "do this member now": the card uses it, and so does
        the panel's per-person button. Enrolment is still the gate, because a
        forced recalculation is not consent.
        """
        config = self.bot.trial_ranks.get(member.guild.id)
        outcome = await self.apply(member, config)
        await self.bot.loop.run_in_executor(
            None, self.bot.trial_ranks.save_standing, member.guild.id, member.id,
            member.display_name, outcome["score"], outcome["rank_name"])
        if outcome["granted"] or outcome["removed"] or outcome["cleared"]:
            lines = [f"{member.mention} recalculated ({why}).",
                     f"Score: **{outcome['score']}** · "
                     f"Rank: **{outcome['rank_name'] or 'none'}**"]
            if outcome["cleared_names"]:
                lines.append("Removed superseded: "
                             + ", ".join(outcome["cleared_names"][:20]))
            if outcome.get("interest_dropped"):
                lines.append(f"Prog interest: {outcome['interest_dropped']} "
                             "entry(s) cleared, now earned.")
            await self.log_event(member.guild, chr(10).join(lines),
                                 title="Trial ranks: recalculated")
        await self.report_problems(member.guild, outcome["errors"], context=why)
        return outcome

    async def refresh(self, member) -> None:
        """Bring one person up to date, quietly.

        Replaces the hourly sweep: a whole-guild pass every hour spent almost
        all of its work confirming that nothing had changed. The two moments
        that actually matter are a scoring role changing (the listener) and the
        person asking where they stand — so checking then covers the same ground
        without the churn, and is current at the moment it's read rather than up
        to an hour stale.
        """
        if not self.runs_here(member.guild):
            return
        if not self.bot.trial_ranks.is_enrolled(member.guild.id, member.id):
            return
        try:
            config = self.bot.trial_ranks.get(member.guild.id)
            outcome = await self.apply(member, config)
            await self.bot.loop.run_in_executor(
                None, self.bot.trial_ranks.save_standing, member.guild.id, member.id,
                member.display_name, outcome["score"], outcome["rank_name"])
            if outcome["granted"] or outcome["removed"] or outcome["cleared"]:
                await self.log_event(
                    member.guild,
                    f"{member.mention} brought up to date when they checked their rank.\n"
                    f"Score: **{outcome['score']}** · Rank: **{outcome['rank_name'] or 'none'}**")
            await self.report_problems(member.guild, outcome["errors"],
                                       context=f"{member.display_name} checked their rank")
        except Exception as error:  # noqa: BLE001 - showing the card matters more
            self.bot.logger.error(f"Trial rank refresh failed for {member.id}: {error}")


async def setup(bot):
    await bot.add_cog(TrialRanks(bot))
