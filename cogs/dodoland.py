"""
DodoLand's listeners — the only things that write activity as it happens.

They count what a socialite actually does: talking, naming people, answering
them, showing pictures, opening threads other people turn up in, sitting in
voice with company, hosting and attending events, welcoming newcomers, and
bringing people in.

Three of those (message, mention given, mention received) can be rebuilt from
the message archive. Nothing else can: no image, reply target, thread parent,
voice session, RSVP or invite use was ever stored. That asymmetry is the whole
reason this ships before any panel or map exists. Every day it is not running is
a day of the better signals that cannot be recovered.

There is no command surface here on purpose. This gathers and shows nobody
anything.

**Failures are swallowed and logged, never raised.** The message listener runs
for every message on the server. A Mongo hiccup must cost a point, never a
conversation.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from helpers.dodoland import intake, invites as invite_rules
from helpers.dodoland import parameters as dodo_params
from helpers.dodoland.voice import VoiceTracker

FEATURE = "dodoland_tracking"


class DodoLand(commands.Cog, name="dodoland"):
    """Records what people did together, per guild, per day."""

    def __init__(self, bot):
        self.bot = bot
        self._indexed = False
        self.voice = VoiceTracker()
        # {guild_id: {code: uses}} and {guild_id: {code: inviter_id}}, refreshed
        # around every join. Empty for any guild where we lack Manage Guild,
        # which makes joins unattributed rather than misattributed.
        self._invite_uses: dict[int, dict[str, int]] = {}
        self._invite_owners: dict[int, dict[str, int]] = {}

    # --------------------------------------------------------------------- #
    #  Shared helpers
    # --------------------------------------------------------------------- #
    def _on(self, guild_id: int) -> bool:
        return self.bot.visibility.feature_active(guild_id, FEATURE, "dodoland")

    def _param(self, guild_id: int, key: str):
        return self.bot.dodoland_params.get(guild_id, key)

    def _channel_id(self, channel) -> int:
        """The channel an act belongs to, with a thread charged to its parent.

        A thread is a room inside a channel, not a channel of its own. Charging
        threads to their parent keeps a building definable as "these channels"
        without every new thread silently escaping the definition.
        """
        parent = getattr(channel, "parent", None)
        return int(getattr(parent, "id", 0) or getattr(channel, "id", 0) or 0)

    def _tracked(self, guild_id: int, channel_id: int) -> bool:
        return intake.counts_channel(
            channel_id,
            tracked=self._param(guild_id, "dodoland_tracked_channels"),
            ignored=self._param(guild_id, "dodoland_ignored_channels"),
        )

    def _is_newcomer(self, guild, user_id: int) -> bool:
        """Whether somebody is still inside this server's newcomer window."""
        member = guild.get_member(int(user_id)) if guild else None
        joined = getattr(member, "joined_at", None)
        if joined is None:
            return False
        days = int(self._param(guild.id, "dodoland_newcomer_days"))
        age = datetime.datetime.now(datetime.timezone.utc) - joined
        return age <= datetime.timedelta(days=max(0, days))

    def _humans(self, guild_id: int, *members) -> bool:
        """Whether every one of these should be counted at all."""
        if self._param(guild_id, "dodoland_count_bots"):
            return True
        return not any(getattr(m, "bot", False) for m in members if m is not None)

    def _metric_allowed_here(self, guild_id: int, act) -> bool:
        """Whether a metric counts in the channel this act happened in.

        Each metric has its own optional channel list. Empty means "wherever
        DodoLand tracks at all", which is what most of them want; narrowing it
        is for metrics that only make sense somewhere specific, such as pictures
        in the fashion and housing rooms.
        """
        only = self._param(guild_id, dodo_params.channels_key(act.metric))
        if not only:
            return True
        return int(act.channel_id or 0) in {int(c) for c in only}

    def _write(self, guild_id: int, acts) -> None:
        """Record a batch, never letting a storage failure escape."""
        acts = [act for act in acts if self._metric_allowed_here(guild_id, act)]
        if not acts:
            return
        try:
            self._ensure_indexes()
            for act in acts:
                self.bot.dodoland.record(
                    guild_id, act.user_id, act.metric,
                    channel_id=act.channel_id, partner_id=act.partner_id,
                )
        except Exception as error:
            self.bot.logger.error(f"DodoLand failed to record activity: {error}")

    def _ensure_indexes(self) -> None:
        """Create the indexes once per process, lazily.

        Deliberately not in ``__init__``: cogs load before the bot is connected,
        and a cog that cannot reach Mongo at import time takes itself offline for
        the whole session.
        """
        if self._indexed:
            return
        self.bot.dodoland.ensure_indexes()
        self._indexed = True

    # --------------------------------------------------------------------- #
    #  Messages: talking, naming, answering, showing, welcoming
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        guild_id = message.guild.id
        if not self._on(guild_id) or not self._humans(guild_id, message.author):
            return

        channel_id = self._channel_id(message.channel)
        if not self._tracked(guild_id, channel_id):
            return

        has_image = any(
            (attachment.content_type or "").startswith("image/")
            or attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
            for attachment in message.attachments
        )

        # Who they answered. resolved is None for a reply to a deleted message,
        # which is a reply that reached nobody.
        reply_to = None
        reference = message.reference
        resolved = getattr(reference, "resolved", None) if reference else None
        if isinstance(resolved, discord.Message) and not getattr(resolved.author, "bot", False):
            reply_to = resolved.author.id

        # Whose thread they turned up in. A forum post's owner is its starter.
        thread_owner = None
        if isinstance(message.channel, discord.Thread):
            owner_id = message.channel.owner_id
            if owner_id:
                owner = message.guild.get_member(owner_id)
                if self._humans(guild_id, owner) or owner is None:
                    thread_owner = owner_id

        acts = intake.acts_from_message(
            message.author.id, message.content,
            channel_id=channel_id,
            has_image=has_image,
            reply_to=reply_to,
            thread_owner=thread_owner,
            min_chars=int(self._param(guild_id, "dodoland_min_message_chars")),
            max_mentions=int(self._param(guild_id, "dodoland_max_mentions")),
            count_self=bool(self._param(guild_id, "dodoland_count_self_acts")),
        )
        if not acts:
            return

        # Welcoming is judged only against people this message actually reached,
        # so the join dates are looked up for a handful of ids rather than the
        # whole server.
        reached = {act.partner_id for act in acts if act.partner_id is not None}
        newcomers = {uid for uid in reached if self._is_newcomer(message.guild, uid)}
        if newcomers:
            acts = intake.acts_from_message(
                message.author.id, message.content,
                channel_id=channel_id, has_image=has_image, reply_to=reply_to,
                thread_owner=thread_owner, newcomers=newcomers,
                min_chars=int(self._param(guild_id, "dodoland_min_message_chars")),
                max_mentions=int(self._param(guild_id, "dodoland_max_mentions")),
                count_self=bool(self._param(guild_id, "dodoland_count_self_acts")),
            )
        self._write(guild_id, acts)

    # --------------------------------------------------------------------- #
    #  Bot commands: what the statue is built from
    # --------------------------------------------------------------------- #
    # Counted live rather than from the ``Commands Usage`` archive, which records
    # no channel at all. Without a channel a command could not feed a building,
    # since a building is defined as a set of rooms.
    @commands.Cog.listener()
    async def on_command_completion(self, context) -> None:
        if context.guild is None:
            return
        self._count_command(context.guild, context.author, context.channel)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction, command) -> None:
        if interaction.guild is None:
            return
        self._count_command(interaction.guild, interaction.user, interaction.channel)

    def _count_command(self, guild, user, channel) -> None:
        """Bot use counts wherever it happens.

        Deliberately **not** subject to the tracked/ignored channel lists. The
        bot channel is the first thing anybody ignores, precisely so command
        spam does not build towns, and that would have left the Dodo Statue
        permanently unbuildable. Commands are a thing you did, not a room you
        were in, so they are counted anywhere and the statue is fed by total
        bot use rather than by location.

        The daily cap is what keeps this sane; a metric's own channel list still
        applies in ``_write``, so it can be narrowed by hand if that is wanted.
        """
        if not self._on(guild.id) or not self._humans(guild.id, user):
            return
        self._write(guild.id, [intake.Act(metric="command_used", user_id=user.id,
                                          channel_id=self._channel_id(channel))])

    # --------------------------------------------------------------------- #
    #  Threads: starting a conversation
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        guild = thread.guild
        if guild is None or not self._on(guild.id):
            return
        owner_id = thread.owner_id
        if not owner_id:
            return
        owner = guild.get_member(owner_id)
        if owner is not None and not self._humans(guild.id, owner):
            return
        channel_id = self._channel_id(thread)
        if not self._tracked(guild.id, channel_id):
            return
        self._write(guild.id, [intake.Act(metric="thread_start", user_id=owner_id,
                                          channel_id=channel_id)])

    # --------------------------------------------------------------------- #
    #  Voice: being somewhere with somebody
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        guild = member.guild
        if guild is None or not self._on(guild.id) or not self._humans(guild.id, member):
            return
        if before.channel == after.channel:
            return  # a mute or a deafen, not a movement

        if before.channel is not None:
            credit = self.voice.leave(guild.id, member.id)
            if credit is not None:
                self._credit_voice(guild.id, credit)
        if after.channel is not None and self._tracked(guild.id, after.channel.id):
            self.voice.join(guild.id, member.id, after.channel.id)

    def _credit_voice(self, guild_id: int, credit) -> None:
        """Turn a finished voice session into acts.

        Recorded with **no channel**, deliberately: voice counts toward town
        power but builds nothing. Attaching voice channels to buildings is a
        one-line change (pass ``credit.channel_id`` below) and is held back
        until the text side is tuned, because voice minutes arrive in much
        larger numbers than messages and would dominate whichever building they
        landed in.
        """
        minimum = int(self._param(guild_id, "dodoland_voice_min_minutes"))
        partners = {other: shared for other, shared in credit.partners.items()
                    if shared >= minimum}
        if not partners:
            return  # alone, or nobody stayed long enough
        try:
            self._ensure_indexes()
            # Minutes are credited in one write rather than one per minute.
            self.bot.dodoland.record(
                guild_id, credit.user_id, "voice_minute", amount=credit.minutes,
            )
            for other in partners:
                self.bot.dodoland.record(
                    guild_id, credit.user_id, "voice_together", partner_id=other,
                )
                self.bot.dodoland.record(
                    guild_id, other, "voice_together", partner_id=credit.user_id,
                )
        except Exception as error:
            self.bot.logger.error(f"DodoLand failed to record a voice session: {error}")

    # --------------------------------------------------------------------- #
    #  Events: hosting, and turning up
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent) -> None:
        guild = event.guild
        creator_id = getattr(event, "creator_id", None)
        if guild is None or not self._on(guild.id) or not creator_id:
            return
        self._write(guild.id, [intake.Act(metric="event_hosted", user_id=int(creator_id),
                                          channel_id=self._event_channel(event))])

    @commands.Cog.listener()
    async def on_scheduled_event_user_add(self, event: discord.ScheduledEvent,
                                          user: discord.User) -> None:
        guild = event.guild
        if guild is None or not self._on(guild.id) or not self._humans(guild.id, user):
            return
        channel_id = self._event_channel(event)
        acts = [intake.Act(metric="event_rsvp", user_id=user.id, channel_id=channel_id)]
        host_id = getattr(event, "creator_id", None)
        if host_id and int(host_id) != user.id:
            acts.append(intake.Act(metric="event_interest_received", user_id=int(host_id),
                                   partner_id=user.id, channel_id=channel_id))
        self._write(guild.id, acts)

    def _event_channel(self, event) -> int:
        """An event's channel, or 0 for an external one with only a location.

        0 means the act still scores toward standing and simply feeds no
        building, which is right: an event held somewhere else is not activity
        in any of this server's rooms.
        """
        channel = getattr(event, "channel", None)
        return int(getattr(channel, "id", 0) or 0)

    # --------------------------------------------------------------------- #
    #  Joins: who brought them in
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            if self._on(guild.id):
                await self._refresh_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        guild = invite.guild
        if guild is not None and self._on(guild.id):
            await self._refresh_invites(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None or not self._on(guild.id) or not self._humans(guild.id, member):
            return
        before = dict(self._invite_uses.get(guild.id, {}))
        owners = dict(self._invite_owners.get(guild.id, {}))
        await self._refresh_invites(guild)
        after = self._invite_uses.get(guild.id, {})

        recruiter = invite_rules.recruiter_for(before, after, owners, member.id)
        if recruiter is None:
            return  # unattributable, which is correct rather than a guess
        self._write(guild.id, [intake.Act(metric="member_recruited", user_id=recruiter,
                                          partner_id=member.id)])

    async def _refresh_invites(self, guild) -> None:
        """Re-read the guild's invite table. Silently a no-op without permission."""
        try:
            found = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            # Manage Guild is missing, or Discord declined. Either way every join
            # is simply unattributed; nothing here is worth an error line per join.
            self._invite_uses.setdefault(guild.id, {})
            self._invite_owners.setdefault(guild.id, {})
            return
        except Exception as error:
            self.bot.logger.error(f"DodoLand could not read invites: {error}")
            return
        self._invite_uses[guild.id] = invite_rules.snapshot(found)
        self._invite_owners[guild.id] = invite_rules.inviter_ids(found)


async def setup(bot) -> None:
    await bot.add_cog(DodoLand(bot))
