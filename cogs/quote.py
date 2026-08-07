"""
Guess-the-Quote cog — a "who said this?" game built on Dodo's message archive.

A real logged message is shown and players pick its author from four options.
It's reaction-time based (first correct answer takes the round; a wrong answer
locks you out of that round), rounds last 10 seconds, and points for correct
answers escalate with your streak. Play solo or duel someone. Runs in a single
updatable embed and stops after two idle rounds. Best scores go on a leaderboard.

The quote pool is ``config_py.messages`` (the archived ``{message, author,
channel}`` docs), restricted to ``config_py.public_channels`` and filtered to
drop command invocations, emoji-only spam, and messages too short to mean
anything. Text lives in ``lang``.
"""

import asyncio
import json
import random
import re

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import checks, messages

_ROUND_SECONDS = 10
_BASE_POINTS = 100
_IDLE_LIMIT = 2
_OPTIONS = 4
_SAMPLE_SIZE = 300
_MIN_WORDS = 4
_MIN_ALPHA = 15
_REVEAL_PAUSE = 2.0
_MEDALS = ["🥇", "🥈", "🥉"]

_MENTION_RE = re.compile(r"<@[!&]?\d+>|<#\d+>")
_URL_RE = re.compile(r"https?://\S+")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\U00002190-\U000021ff\U00002b00-\U00002bff️‍]",
    re.UNICODE,
)


class _OptionButton(discord.ui.Button):
    """One of four author choices for the current quote."""

    def __init__(self, label: str, author_id: int):
        super().__init__(label=label[:80], style=discord.ButtonStyle.secondary)
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "_RoundView" = self.view
        uid = interaction.user.id
        if uid not in view.allowed_ids:
            await interaction.response.send_message(lang.QUOTE_NOT_PLAYING, ephemeral=True)
            return
        if uid in view.answered:  # already guessed this round — locked in
            await interaction.response.defer()
            return
        view.answered.add(uid)
        if self.author_id == view.correct_id and view.first_correct is None:
            view.first_correct = uid
        await interaction.response.defer()
        if view.first_correct is not None or view.allowed_ids <= view.answered:
            view.done.set()


class _RoundView(discord.ui.View):
    """Four answer buttons for one round; resolves on first correct or all-answered."""

    def __init__(self, options, correct_id, allowed_ids):
        super().__init__(timeout=_ROUND_SECONDS + 5)
        self.correct_id = correct_id
        self.allowed_ids = set(allowed_ids)
        self.answered = set()
        self.first_correct = None
        self.done = asyncio.Event()
        for label, author_id in options:
            self.add_item(_OptionButton(label, author_id))

    def reveal(self) -> None:
        """Disable buttons and colour the correct one green."""
        for child in self.children:
            child.disabled = True
            if child.author_id == self.correct_id:
                child.style = discord.ButtonStyle.success


class Quote(commands.Cog, name="quote"):
    """Guess-the-Quote game."""

    def __init__(self, bot):
        self.bot = bot
        try:
            self.prefixes = tuple(p.strip().lower() for p in json.load(open("config.json"))["prefix"] if p.strip())
        except Exception:
            self.prefixes = ("dodo",)

    # ------------------------------------------------------------------ #
    #  Quote pool
    # ------------------------------------------------------------------ #
    def _is_meaningful(self, text: str) -> bool:
        """Reject command invocations, emoji-only spam, and too-short messages."""
        stripped = text.strip()
        if not stripped or stripped.lower().startswith(self.prefixes):
            return False
        core = _EMOJI_RE.sub("", _CUSTOM_EMOJI_RE.sub("", _URL_RE.sub("", _MENTION_RE.sub("", stripped))))
        alpha = sum(c.isalpha() for c in core)
        return len(core.split()) >= _MIN_WORDS and alpha >= _MIN_ALPHA

    def _load_pool(self, guild):
        """Sample the archive and return (list of (text, author_id), option-member list)."""
        docs = config_py.messages.aggregate(
            [{"$match": {"channel": {"$in": config_py.public_channels}}}, {"$sample": {"size": _SAMPLE_SIZE}}]
        )
        quotes = []
        members = {}
        for doc in docs:
            member = guild.get_member(doc.get("author"))
            if member is None or member.bot:
                continue
            if self._is_meaningful(doc.get("message", "")):
                quotes.append((doc["message"].strip(), member.id))
                members[member.id] = member

        option_members = list(members.values())
        if len(option_members) < _OPTIONS:  # top up decoys from the wider guild
            extra = [m for m in guild.members if not m.bot and m.id not in members]
            random.shuffle(extra)
            option_members += extra[: _OPTIONS - len(option_members)]
        random.shuffle(quotes)
        return quotes, option_members

    def _build_options(self, correct_member, option_members):
        """Correct author + three shuffled decoys."""
        others = [m for m in option_members if m.id != correct_member.id]
        decoys = random.sample(others, min(_OPTIONS - 1, len(others)))
        opts = [(m.display_name, m.id) for m in [correct_member, *decoys]]
        random.shuffle(opts)
        return opts

    # ------------------------------------------------------------------ #
    #  Command
    # ------------------------------------------------------------------ #
    @commands.hybrid_command(name="quote", description="Guess who said a random archived message!")
    @checks.not_blacklisted()
    async def quote(self, context: Context, opponent: discord.Member = None) -> None:
        """Play Guess-the-Quote solo, or duel ``opponent``."""
        if opponent is not None:
            if opponent.id == context.author.id:
                await context.send(lang.QUOTE_SELF_DUEL)
                return
            if opponent.bot:
                await context.send(lang.QUOTE_BOT_DUEL)
                return

        pool, option_members = self._load_pool(context.guild)
        if not pool or len(option_members) < _OPTIONS:
            await context.send(lang.QUOTE_NOT_ENOUGH)
            return

        players = {context.author.id: context.author}
        if opponent is not None:
            players[opponent.id] = opponent
        scores = {uid: 0 for uid in players}
        streaks = {uid: 0 for uid in players}
        log = []

        game_msg = await context.send(embed=messages.embed(lang.QUOTE_INTRO, title=lang.QUOTE_TITLE))
        await asyncio.sleep(1.5)

        round_no = 0
        idle_streak = 0
        while idle_streak < _IDLE_LIMIT:
            if not pool:
                pool, _ = self._load_pool(context.guild)
                if not pool:
                    break
            quote_text, author_id = pool.pop()
            correct_member = context.guild.get_member(author_id)
            if correct_member is None:
                continue
            round_no += 1

            options = self._build_options(correct_member, option_members)
            view = _RoundView(options, author_id, players)
            await game_msg.edit(
                embed=self._round_embed(players, scores, streaks, quote_text, round_no, log), view=view
            )
            try:
                await asyncio.wait_for(view.done.wait(), timeout=_ROUND_SECONDS)
            except asyncio.TimeoutError:
                pass
            view.stop()

            winner = view.first_correct
            awarded = 0
            for uid in players:
                if uid == winner:
                    streaks[uid] += 1
                    awarded = _BASE_POINTS * streaks[uid]
                    scores[uid] += awarded
                else:
                    streaks[uid] = 0
            idle_streak = 0 if view.answered else idle_streak + 1
            log.append(self._log_line(view, players, correct_member, winner, awarded))
            log[:] = log[-3:]

            view.reveal()
            await game_msg.edit(
                embed=self._round_embed(players, scores, streaks, quote_text, round_no, log, reveal=correct_member),
                view=view,
            )
            await asyncio.sleep(_REVEAL_PAUSE)

        await game_msg.edit(embed=self._final_embed(players, scores, round_no), view=None)
        self._save_scores(players, scores)
        await context.send(embed=self._leaderboard_embed())

    # ------------------------------------------------------------------ #
    #  Rendering
    # ------------------------------------------------------------------ #
    def _scoreboard(self, players, scores, streaks) -> str:
        if len(players) == 1:
            uid = next(iter(players))
            return lang.QUOTE_SCORE_SOLO.format(
                total=scores[uid], streak=streaks[uid], worth=_BASE_POINTS * (streaks[uid] + 1)
            )
        return "\n".join(
            lang.QUOTE_SCORE_LINE.format(
                name=member.display_name, total=scores[uid], streak=streaks[uid],
                worth=_BASE_POINTS * (streaks[uid] + 1),
            )
            for uid, member in players.items()
        )

    def _round_embed(self, players, scores, streaks, quote_text, round_no, log, reveal=None) -> discord.Embed:
        description = lang.QUOTE_PROMPT.format(quote=quote_text)
        if reveal is not None:
            description = lang.QUOTE_REVEAL.format(name=reveal.display_name) + "\n\n" + description
        embed = messages.embed(description, title=lang.QUOTE_TITLE, color=messages.ACCENT)
        embed.add_field(name="Score", value=self._scoreboard(players, scores, streaks), inline=False)
        embed.add_field(name=lang.QUOTE_LOG_HEADER, value="\n".join(log) or "—", inline=False)
        embed.set_footer(text=lang.QUOTE_FOOTER.format(round=round_no, seconds=_ROUND_SECONDS, idle=_IDLE_LIMIT))
        return embed

    def _log_line(self, view, players, correct_member, winner, awarded) -> str:
        answer = correct_member.display_name
        if winner is not None:
            return lang.QUOTE_LOG_CORRECT.format(who=players[winner].display_name, pts=awarded, answer=answer)
        if view.answered:
            who = ", ".join(players[uid].display_name for uid in view.answered)
            return lang.QUOTE_LOG_WRONG.format(who=who, answer=answer)
        return lang.QUOTE_LOG_IDLE.format(answer=answer)

    def _final_embed(self, players, scores, rounds) -> discord.Embed:
        if len(players) == 1:
            uid = next(iter(players))
            desc = lang.QUOTE_FINAL_SOLO.format(total=scores[uid], rounds=rounds)
        else:
            best = max(scores.values())
            leaders = [uid for uid, s in scores.items() if s == best]
            if len(leaders) == 1:
                desc = lang.QUOTE_FINAL_WINNER.format(name=players[leaders[0]].display_name, total=best)
            else:
                desc = lang.QUOTE_FINAL_TIE.format(total=best)
            desc += "\n\n" + "\n".join(
                lang.QUOTE_FINAL_LINE.format(name=m.display_name, total=scores[uid]) for uid, m in players.items()
            )
        return messages.success(desc, title=lang.QUOTE_FINAL_TITLE)

    # ------------------------------------------------------------------ #
    #  Leaderboard
    # ------------------------------------------------------------------ #
    def _save_scores(self, players, scores) -> None:
        for uid, member in players.items():
            record = config_py.quote_scores.find_one({"User ID": uid})
            if scores[uid] > (record.get("Best", 0) if record else 0):
                config_py.quote_scores.update_one(
                    {"User ID": uid}, {"$set": {"Best": scores[uid], "Name": member.display_name}}, upsert=True
                )

    def _leaderboard_embed(self) -> discord.Embed:
        top = list(config_py.quote_scores.find({"Best": {"$gt": 0}}).sort("Best", -1).limit(10))
        if top:
            body = "\n".join(
                lang.QUOTE_LEADERBOARD_LINE.format(
                    medal=_MEDALS[i] if i < 3 else f"{i + 1}.", mention=f"<@{doc['User ID']}>", best=doc["Best"]
                )
                for i, doc in enumerate(top)
            )
        else:
            body = lang.QUOTE_LEADERBOARD_EMPTY
        return messages.embed(body, title=lang.QUOTE_LEADERBOARD_TITLE, color=messages.ACCENT)

    @commands.hybrid_command(name="quotetop", description="Show the Guess-the-Quote leaderboard.")
    @checks.not_blacklisted()
    async def quotetop(self, context: Context) -> None:
        """Show the top-10 Guess-the-Quote scores."""
        await context.send(embed=self._leaderboard_embed())


async def setup(bot):
    await bot.add_cog(Quote(bot))
