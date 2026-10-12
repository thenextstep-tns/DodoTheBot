"""
Event-rule runtime — the "do this when that happens" half of the constructor.

Rules are authored in the control panel (see ``helpers/events.py``); this cog
listens for every event in the catalog and, when one fires, posts the rule's
message in its channel.

Two safeguards matter more than the feature itself:

* **Self-trigger guard.** A rule on ``message`` posts a message, which dispatches
  ``message`` again. Anything the bot itself caused is ignored, so a rule cannot
  feed itself.
* **Rate limit.** Even without a loop, a busy event can fire hundreds of times a
  minute. Each rule gets a small budget and goes quiet (with one warning) until
  the window rolls over.
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands

from helpers import events, messages

# Per rule, per window: enough for real notifications, not enough to flood.
RATE_LIMIT = 5
RATE_WINDOW = 60.0
# How long a rate-limited rule stays quiet before it may warn again.
WARN_COOLDOWN = 600.0


class EventActions(commands.Cog, name="event_actions"):
    """Runs the per-server event rules built in the control panel."""

    def __init__(self, bot):
        self.bot = bot
        self._buckets: dict[str, tuple[float, int]] = {}
        self._warned: dict[str, float] = {}
        self._listeners: list[tuple[str, object]] = []
        self._register()

    def _register(self) -> None:
        """Attach one listener per catalog event.

        Listening explicitly (rather than wrapping ``Bot.dispatch``) keeps this
        removable on unload and leaves the library's own dispatch untouched.
        """
        for event in events.selectable_events():

            async def handler(*args, _event=event):
                await self._handle(_event, args)

            name = f"on_{event}"
            self.bot.add_listener(handler, name)
            self._listeners.append((name, handler))

    def cog_unload(self) -> None:
        for name, handler in self._listeners:
            self.bot.remove_listener(handler, name)
        self._listeners.clear()

    # ------------------------------------------------------------------ #
    #  Guards
    # ------------------------------------------------------------------ #
    def _is_self_caused(self, args: tuple) -> bool:
        """Whether this event was caused by the bot itself."""
        me = self.bot.user
        if me is None:
            return False
        for value in args:
            author = getattr(value, "author", None) or getattr(value, "user", None)
            if isinstance(author, (discord.User, discord.Member)) and author.id == me.id:
                return True
            if isinstance(value, (discord.User, discord.Member)) and value.id == me.id:
                return True
        return False

    def _allowed(self, rule_id: str) -> bool:
        """Token bucket per rule; ``False`` once the window's budget is spent."""
        now = time.monotonic()
        window_start, used = self._buckets.get(rule_id, (now, 0))
        if now - window_start >= RATE_WINDOW:
            window_start, used = now, 0
        if used >= RATE_LIMIT:
            self._buckets[rule_id] = (window_start, used)
            return False
        self._buckets[rule_id] = (window_start, used + 1)
        return True

    def _should_warn(self, rule_id: str) -> bool:
        now = time.monotonic()
        if now - self._warned.get(rule_id, 0.0) < WARN_COOLDOWN:
            return False
        self._warned[rule_id] = now
        return True

    # ------------------------------------------------------------------ #
    #  Execution
    # ------------------------------------------------------------------ #
    async def _handle(self, event: str, args: tuple) -> None:
        manager = getattr(self.bot, "event_rules", None)
        # The cheap checks first: this runs on every dispatch, including messages.
        if manager is None or not manager.listens_for(event):
            return
        guild_id = events.guild_id_from(args)
        if guild_id is None:
            return
        rules = manager.matching(guild_id, event)
        if not rules:
            return
        if not self.bot.visibility.feature_active(guild_id, "event_rules", "event_actions"):
            return
        if self._is_self_caused(args):
            return

        context = events.build_context(event, args)
        for rule in rules:
            try:
                await self._run(rule, context)
            except Exception as error:  # noqa: BLE001 - one bad rule must not kill the listener
                self.bot.logger.error(f"Event rule {rule.get('name')} failed: {error}")

    async def _run(self, rule: dict, context: dict) -> None:
        channel = self.bot.get_channel(int(rule.get("channel_id") or 0))
        if channel is None:
            return
        rule_id = str(rule.get("_id"))
        if not self._allowed(rule_id):
            if self._should_warn(rule_id):
                await channel.send(
                    f"⚠️ Rule **{rule.get('name')}** fired more than {RATE_LIMIT} times in a minute "
                    f"and is paused for the rest of it."
                )
            return

        body = messages.render_template(rule.get("message") or "", **context)
        pings = " ".join(
            [f"<@{uid}>" for uid in rule.get("ping_user_ids") or []]
            + [f"<@&{rid}>" for rid in rule.get("ping_role_ids") or []]
        )
        content = f"{pings} {body}".strip() if pings else body
        if not content:
            return
        await channel.send(
            content[:2000],
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=True, everyone=False, replied_user=False
            ),
        )


async def setup(bot):
    await bot.add_cog(EventActions(bot))
