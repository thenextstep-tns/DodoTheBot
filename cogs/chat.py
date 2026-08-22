"""
Chat cog — Dodo talking, and mostly Dodo *not* talking.

Three ways in, in descending order of how often they cost money:

* **Addressed** — a mention, a ping of a role she has, a reply to her, or the
  ``chat`` command. Always answered.
* **String listeners** — per-server triggers (:mod:`helpers.chat.triggers`,
  editable on the panel's Events page). A match always updates how she feels;
  whether she *says* anything is a per-trigger chance, and what she says is often
  a canned line rather than an API call.
* **Uninvited** — very rarely, she reads the last few messages and joins a
  conversation nobody addressed, like a regular user would.

The mind lives in ``helpers/chat``; this file is the Discord end of it. The
division matters: everything that runs on every message is pure arithmetic over
in-memory state, and the model is only reached once a decision to speak has
already been made.
"""

import json
import random
import time

from openai import OpenAI, OpenAIError

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers.chat import dial as dial_model
from helpers.chat import prompt as prompt_model
from helpers.chat import router as router_model
from helpers.chat import state as state_model

COG_NAME = "chat"
FEATURE_LISTEN = "chat_listeners"
FEATURE_UNPROMPTED = "chat_unprompted"

# Discord's per-message ceiling.
_MESSAGE_LIMIT = 2000


class Chat(commands.Cog, name=COG_NAME):
    """LLM chat with memory, relationships, string listeners and rumours."""

    def __init__(self, bot):
        self.bot = bot
        # The bot-wide default key (used when a guild hasn't set its own).
        self._default_key = getattr(config_py, "PROXY_API", None)
        self._clients: dict[tuple, OpenAI] = {}
        self.router = router_model.Router()

    # ------------------------------------------------------------------ #
    #  Per-server configuration
    # ------------------------------------------------------------------ #
    def _param(self, guild, key):
        return self.bot.params.get(guild.id if guild else None, key)

    def _state_tuning(self, guild) -> state_model.Tuning:
        return state_model.Tuning(
            affinity_default=self._param(guild, "chat_relationship_default"),
            affinity_min=self._param(guild, "chat_relationship_min"),
            affinity_max=self._param(guild, "chat_relationship_max"),
            sentiment_weight=self._param(guild, "chat_sentiment_weight"),
            affinity_drift_per_day=self._param(guild, "chat_relationship_drift_per_day"),
            familiarity_per_message=self._param(guild, "chat_familiarity_per_message"),
            facts_max=self._param(guild, "chat_facts_max"),
            facts_recall=self._param(guild, "chat_facts_recall"),
            fact_halflife_days=self._param(guild, "chat_fact_halflife_days"),
            grudges_max=self._param(guild, "chat_grudges_max"),
            grudge_halflife_hours=self._param(guild, "chat_grudge_halflife_hours"),
            grudge_floor=self._param(guild, "chat_grudge_floor"),
            rumours_max=self._param(guild, "chat_rumours_max"),
            rumours_recall=self._param(guild, "chat_rumours_recall"),
            fatigue_halflife_minutes=self._param(guild, "chat_fatigue_halflife_minutes"),
        )

    def _dial_tuning(self, guild) -> dial_model.DialTuning:
        return dial_model.DialTuning(
            spice_base=self._param(guild, "chat_spice_base"),
            spice_max=self._param(guild, "chat_spice_max"),
            spice_jitter=self._param(guild, "chat_spice_jitter"),
            close_bonus_at=self._param(guild, "chat_close_bonus_at"),
            distant_penalty_at=self._param(guild, "chat_distant_penalty_at"),
            fatigue_bite=self._param(guild, "chat_fatigue_bite"),
            sentences_max=self._param(guild, "chat_reply_max_sentences"),
            obsession_chance=self._param(guild, "chat_obsession_chance"),
        )

    def _router_tuning(self, guild) -> router_model.RouterTuning:
        return router_model.RouterTuning(
            ambient_multiplier=self._param(guild, "chat_ambient_multiplier"),
            ambient_cooldown_seconds=self._param(guild, "chat_ambient_cooldown_seconds"),
            user_cooldown_seconds=self._param(guild, "chat_user_cooldown_seconds"),
            daily_cap=self._param(guild, "chat_daily_call_cap"),
            spontaneous_chance=self._param(guild, "chat_spontaneous_chance"),
            spontaneous_cooldown_seconds=self._param(guild, "chat_spontaneous_cooldown_seconds"),
            spontaneous_min_messages=self._param(guild, "chat_spontaneous_min_messages"),
            spontaneous_min_speakers=self._param(guild, "chat_spontaneous_min_speakers"),
            context_messages=self._param(guild, "chat_context_messages"),
        )

    # ------------------------------------------------------------------ #
    #  The API client
    # ------------------------------------------------------------------ #
    def _owner_scope(self, guild, author) -> bool:
        """Whether the bot's default (shared) key may be used here: only the bot
        owner's own server (or the owner in DMs). Everyone else must bring a key."""
        owners = self.bot.config.get("owners", [])
        if guild is not None:
            return guild.owner_id in owners
        return author.id in owners

    def _client_for(self, guild, author) -> "OpenAI | None":
        """The OpenAI client for this context: the server's own per-server API key
        if set; otherwise the bot's default key **only** for the owner's server.
        Clients are cached by key and endpoint. Returns None when none applies."""
        key = self._param(guild, "chat_api_key")
        if not key and self._owner_scope(guild, author):
            key = self._default_key
        if not key:
            return None
        base_url = self._param(guild, "chat_base_url")
        if (key, base_url) not in self._clients:
            self._clients[(key, base_url)] = OpenAI(api_key=key, base_url=base_url)
        return self._clients[(key, base_url)]

    # ------------------------------------------------------------------ #
    #  State persistence
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load(user_id: str, tuning: state_model.Tuning) -> state_model.ChatState:
        document = config_py.memory.find_one({state_model.F_USER: user_id})
        return state_model.from_document(document, user_id, tuning)

    @staticmethod
    def _save(state: state_model.ChatState) -> None:
        config_py.memory.update_one(
            {state_model.F_USER: state.user_id},
            {"$set": state_model.to_document(state)},
            upsert=True,
        )

    # ------------------------------------------------------------------ #
    #  Entry points
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(
        name="chat", description="Chat with Dodo! Dodo will try to remember important things about you."
    )
    async def chat(self, context: Context, *, message: str) -> None:
        """Chat with Dodo — one LLM call handles reply, memory, mood and rumours."""
        client = self._client_for(context.guild, context.author)
        if client is None:
            await context.send(lang.CHAT_NO_KEY)
            return
        guild_id = context.guild.id if context.guild else None
        # The command goes through the same string listeners as ordinary chat —
        # "/chat no u" should get the same bird that "no u" does.
        trigger = self.bot.chat_triggers.match(guild_id, message) if guild_id else None
        async with context.typing():
            reply = await self._engage(
                guild=context.guild,
                channel=context.channel,
                author=context.author,
                text=message,
                mentioned=self._mentions(context.message, context.author),
                client=client,
                trigger=trigger,
            )
        if reply:
            await self._send(context.send, reply)

    async def handle_message(self, message: discord.Message) -> None:
        """Called from the gateway listener in ``bot.py`` for every message.

        Cheap first: the router and the trigger match are pure arithmetic, and
        nothing here touches the database or the API until a decision to speak
        has been taken.
        """
        # Bots included: answering one is how a two-bot loop starts, and she would
        # cheerfully keep it going all night.
        if message.author.bot:
            return
        guild = message.guild
        guild_id = guild.id if guild else None
        if not self.bot.visibility.cog_enabled(guild_id, COG_NAME):
            return
        if message.channel.id in (self._param(guild, "chat_ignored_channels") or []):
            return

        text = message.content or ""
        self.router.observe(message.channel.id, message.author.display_name, text)

        addressed = self._addressed(message)
        listening = self.bot.visibility.feature_active(guild_id, FEATURE_LISTEN, COG_NAME)
        trigger = self.bot.chat_triggers.match(guild_id, text) if (listening and guild_id) else None

        decision = self.router.decide(
            addressed=addressed,
            trigger=trigger,
            guild_id=guild_id,
            channel_id=message.channel.id,
            user_id=message.author.id,
            tuning=self._router_tuning(guild),
        )
        if decision.route == router_model.SPONTANEOUS and not self.bot.visibility.feature_active(
                guild_id, FEATURE_UNPROMPTED, COG_NAME):
            return

        # A trigger is felt whether or not it is answered — noticing in silence is
        # the point of the design, not a side effect. When she does reply the
        # feelings are applied inside the same load/save the reply already needs.
        if trigger is not None and decision.route not in (
                router_model.ENGAGE, router_model.SPONTANEOUS):
            self._absorb(message, trigger)
        if not decision.speaks:
            self.bot.logger.debug(
                f"chat: {message.author} -> {decision.route} ({decision.reason})")
            return

        await self._speak(message, decision)

    # ------------------------------------------------------------------ #
    #  Routing helpers
    # ------------------------------------------------------------------ #
    def _addressed(self, message: discord.Message) -> bool:
        """Mention, reply-to-her, or a ping of a role she wears."""
        me = message.guild.me if message.guild else self.bot.user
        if any(user.id == self.bot.user.id for user in message.mentions):
            return True
        reference = message.reference
        if reference is not None and getattr(reference.resolved, "author", None) is not None:
            if reference.resolved.author.id == self.bot.user.id:
                return True
        if self._param(message.guild, "chat_respond_to_role_ping") and message.role_mentions:
            my_roles = {role.id for role in getattr(me, "roles", [])}
            if any(role.id in my_roles for role in message.role_mentions):
                return True
        return False

    async def _replied_context(self, message: discord.Message) -> "list[str] | None":
        """The message being replied to, so a reply reads as part of a thread.

        Uses the cached copy discord.py already attached; only falls back to a
        fetch when the reply itself is the thing being answered, which is rare
        enough to be worth one call.
        """
        reference = message.reference
        if reference is None:
            return None
        replied = reference.resolved if isinstance(reference.resolved, discord.Message) else None
        if replied is None and reference.message_id:
            try:
                replied = await message.channel.fetch_message(reference.message_id)
            except (discord.HTTPException, discord.Forbidden):
                return None
        if replied is None or not replied.content:
            return None
        return [f"{replied.author.display_name}: {replied.content}"]

    def _absorb(self, message: discord.Message, trigger) -> None:
        """Feel a trigger she is not going to answer. One read, one write, no model."""
        tuning = self._state_tuning(message.guild)
        state = self._load(str(message.author.id), tuning)
        self._apply_trigger(state, tuning, trigger)
        self._save(state)

    @staticmethod
    def _apply_trigger(state, tuning, trigger, *, now=None) -> None:
        """What a matched phrase does to how she feels about the speaker."""
        if trigger is None:
            return
        state.bump_fatigue(tuning, trigger.key, now=now)
        if trigger.forgives:
            state.forgive()
        if trigger.affinity:
            state.apply_sentiment(tuning, trigger.affinity)
        if trigger.grudge:
            state.add_grudge(tuning, lang.CHAT_GRUDGE.format(name=trigger.name),
                             trigger.grudge, now=now)

    async def _speak(self, message: discord.Message, decision) -> None:
        """Say the thing the router decided on."""
        channel = message.channel
        if decision.route == router_model.REFLEX:
            self.router.note_spoke(channel.id, message.author.id)
            await self._send(channel.send, random.choice(decision.trigger.reflex))
            return

        client = self._client_for(message.guild, message.author)
        if client is None:
            return

        unprompted = decision.route == router_model.SPONTANEOUS
        if unprompted:
            recent = self.router.recent(
                channel.id, self._param(message.guild, "chat_context_messages"))
        else:
            recent = await self._replied_context(message)

        async with channel.typing():
            reply = await self._engage(
                guild=message.guild,
                channel=channel,
                author=message.author,
                text=message.content or "",
                mentioned=self._mentions(message, message.author),
                client=client,
                trigger=decision.trigger,
                recent=recent,
                unprompted=unprompted,
            )
        if unprompted:
            self.router.note_unprompted(channel.id)
        if not reply:
            return
        self.router.note_spoke(channel.id, message.author.id)
        await self._send(channel.send, reply)

    # ------------------------------------------------------------------ #
    #  The one API call
    # ------------------------------------------------------------------ #
    async def _engage(self, *, guild, channel, author, text, mentioned, client,
                      trigger=None, recent=None, unprompted=False) -> str:
        """Build the prompt, make the call, fold the answer back into state.

        Returns what to say, or an empty string when she decides to stay quiet
        (only possible for uninvited contributions).
        """
        now = time.time()
        tuning = self._state_tuning(guild)
        state = self._load(str(author.id), tuning)
        state.note_message(tuning, now=now)

        # Read the wear on this bit *before* recording another use of it, so the
        # first time a phrase fires it still gets the full performance.
        fatigue = state.fatigue_of(trigger.key, tuning, now=now) if trigger is not None else 0.0
        self._apply_trigger(state, tuning, trigger, now=now)

        dial = dial_model.compute(
            state, trigger, self._dial_tuning(guild),
            text=text,
            utility_patterns=self._param(guild, "chat_utility_patterns"),
            obsessions=self._param(guild, "chat_obsessions"),
            obsession_rotate_hours=self._param(guild, "chat_obsession_rotate_hours"),
            guild_id=guild.id if guild else None,
            now=now,
            fatigue=fatigue,
        )
        others = self._others(mentioned, tuning)
        system = prompt_model.build(
            persona=self._param(guild, "chat_personality"),
            name=author.display_name,
            state=state,
            tuning=tuning,
            dial=dial,
            others=others,
            recent=recent,
            unprompted=unprompted,
        )

        self.router.note_call(guild.id if guild else None, now=now)
        try:
            completion = client.chat.completions.create(
                model=self._param(guild, "chat_model"),
                temperature=self._param(guild, "chat_temperature"),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text or lang.CHAT_EMPTY_TURN},
                ],
            )
        except OpenAIError as error:
            self.bot.logger.warning(f"chat: API error: {error}")
            self._save(state)
            return "" if unprompted else lang.CHAT_API_ERROR.format(error=error)

        data = self._parse(completion)
        if data is None:
            self._save(state)
            return "" if unprompted else lang.CHAT_PARSE_ERROR

        reply = str(data.get(prompt_model.J_SAY) or "").strip()
        state.apply_sentiment(tuning, self._as_int(data.get(prompt_model.J_FELT)))
        learned = data.get(prompt_model.J_LEARNED)
        if isinstance(learned, str):
            state.add_fact(tuning, learned, now=now)
        self._save(state)
        self._save_rumour(data.get(prompt_model.J_RUMOUR), mentioned, author, tuning)

        if not reply and not unprompted:
            return lang.CHAT_REPLY_FALLBACK
        return reply

    @staticmethod
    def _parse(completion) -> "dict | None":
        try:
            data = json.loads(completion.choices[0].message.content)
        except (json.JSONDecodeError, TypeError, IndexError, AttributeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _as_int(raw) -> int:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------ #
    #  People other than the speaker
    # ------------------------------------------------------------------ #
    @staticmethod
    def _mentions(message, author) -> list:
        """Real people mentioned in the message, excluding bots and the speaker."""
        if message is None:
            return []
        return [user for user in message.mentions if user.id != author.id and not user.bot]

    def _others(self, mentioned: list, tuning: state_model.Tuning) -> list[dict]:
        """What she knows about the people being talked about — and the numbered
        list the model picks a rumour target from."""
        others = []
        for user in mentioned:
            state = self._load(str(user.id), tuning)
            others.append({
                "name": user.display_name,
                "closeness": state.closeness if state.seen else None,
                "facts": state.recall_facts(tuning)[:2],
            })
        return others

    def _save_rumour(self, rumour, mentioned: list, author, tuning: state_model.Tuning) -> None:
        """Persist a detected rumour against the person it is about."""
        if not (isinstance(rumour, dict) and mentioned):
            return
        index = rumour.get(prompt_model.J_RUMOUR_ABOUT)
        fact = rumour.get(prompt_model.J_RUMOUR_WHAT)
        if not (isinstance(index, (int, float)) and isinstance(fact, str) and fact.strip()):
            return
        index = int(index)
        if not 0 <= index < len(mentioned):
            return
        target = mentioned[index]
        state = self._load(str(target.id), tuning)
        state.add_rumour(tuning, fact.strip(), str(author.id), author.display_name)
        self._save(state)

    # ------------------------------------------------------------------ #
    #  Output
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _send(send, text: str) -> None:
        """Post a reply, split at Discord's limit, without pinging anyone."""
        for start in range(0, len(text), _MESSAGE_LIMIT):
            await send(text[start:start + _MESSAGE_LIMIT],
                       allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Chat(bot))
