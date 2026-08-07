"""
Chat cog — ``chat`` talks to users through an LLM with per-user long-term memory,
a relationship score, and a rumour system. Invoked as a command and by the
mention handler in bot.py.
"""

import json
import random

from openai import OpenAI, OpenAIError

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang

_PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1"
_MODEL = "gpt-4o-mini"


def _relationship_description(score: int) -> str:
    """Turn a 0–1000 relationship score into a personality instruction for the LLM."""
    if score < 250:
        return (
            f"You are very grumpy and annoyed with this user (Relationship Score: {score}/1000). "
            "Be childishly angry, pouty, and use short, curt sentences. You don't feel like talking to them."
        )
    if score < 500:
        return (
            f"You are a little grumpy with this user (Relationship Score: {score}/1000). "
            "Be slightly sassy and reluctant, but still answer their questions."
        )
    if score > 750:
        return (
            f"You are overjoyed to see this user! (Relationship Score: {score}/1000). They are one of your best "
            "friends. Be extremely enthusiastic, use exclamation points, and be very cheerful."
        )
    if score > 500:
        return (
            f"You are happy to talk to this user (Relationship Score: {score}/1000). "
            "Be friendly, warm, and engaging."
        )
    return (
        f"You have a neutral relationship with this user (Relationship Score: {score}/1000). "
        "Be your normal, helpful self."
    )


class Chat(commands.Cog, name="chat"):
    """LLM chat with memory, relationship scoring and rumours."""

    def __init__(self, bot):
        self.bot = bot
        # The bot-wide default key (used when a guild hasn't set its own).
        self._default_key = getattr(config_py, "PROXY_API", None)
        self._clients: dict[str, OpenAI] = {}

    def _client_for(self, guild_id) -> "OpenAI | None":
        """The OpenAI client for a guild: its own per-server API key if set,
        otherwise the bot's default key. Clients are cached by key. Returns None
        when no key is available anywhere."""
        key = self.bot.params.get(guild_id, "chat_api_key") or self._default_key
        if not key:
            return None
        if key not in self._clients:
            self._clients[key] = OpenAI(api_key=key, base_url=_PROXY_BASE_URL)
        return self._clients[key]

    def _build_system_prompt(self, context, current_memory, current_relationship, current_rumours) -> str:
        """Assemble the LLM system prompt from the user's memory, mood and rumours."""
        mentioned_users = [u for u in self._mentions(context) if u.id != context.author.id and not u.bot]
        valid_rumour_targets = [{"index": i, "name": u.display_name} for i, u in enumerate(mentioned_users)]

        mention_context = ""
        for user in mentioned_users:
            other = config_py.memory.find_one({"user_id": str(user.id)})
            if other:
                mention_context += (
                    f"Context for {user.display_name} (ID: {user.id}):\n"
                    f"- Memory: {other.get('memory', 'None')}\n"
                    f"- Relationship: {other.get('relationship', 500)}\n\n"
                )

        rumours_context = ""
        if current_rumours:
            rumour_list = "\n".join(
                f'- "{r.get("rumour")}" (heard from {r.get("source_name", "an unknown bird")})'
                for r in current_rumours
            )
            rumours_context = f"**Rumours you've heard about {context.author.display_name}:**\n{rumour_list}"

        drowsiness_roll = random.randint(0, 10)
        return f"""
You are Dodo, a bird from "ESO for Dodos". You give out concise wise and profound things, but also sometimes randomly unhinged and stupid.
**1. Your Base Mood:**
{_relationship_description(current_relationship)}

**2. Your Current Drowsiness ({drowsiness_roll}/10):**
Combine this with your Base Mood.
- **0-3 (Low):** Sharp but tired. Short, direct answers.
- **4-7 (Medium):** Normal, friendly, a bit clumsy.
- **8-10 (High):** Very sleepy. Long, rambling, silly messages.

---
**YOUR TASKS:**

1.  **CHAT**: Respond to the user based on your Mood and Drowsiness. Weave details from their HIDDEN MEMORY into the conversation naturally. If a topic related to a rumour comes up, you can playfully mention it.
2.  **ANALYZE SENTIMENT**: Rate the user's message sentiment as an integer from -10 to +10.
3.  **UPDATE MEMORY**: Critically analyze if the user (`{context.author.display_name}`) states a new fact *about themselves*. If so, update their memory. If not, return the existing memory value EXACTLY without prefixes or changes.
4.  **DETECT RUMOUR**: Analyze the user's message to see if it states a rumour about one of the "Valid Targets". A rumour can be a funny story, a joke, or a stated fact. Do not save simple opinions (e.g., "is cool"), questions, or temporary information.
    - If a valid rumour (a joke, story, or fact) is detected, populate the `new_rumour` object with the `target_index` and the `rumour_fact`.
    - If NO valid rumour is detected, `new_rumour` MUST be `null`.
    - **Valid Targets for Rumours:** {json.dumps(valid_rumour_targets) if valid_rumour_targets else "[]"}

---
**HIDDEN MEMORY (for internal reference):**
- User's Personal Memory: {current_memory}
{rumours_context}
{mention_context}
End of memory.

---
Respond with a single, syntactically correct JSON object with four keys: "chat_reply", "sentiment_score", "updated_memory", and "new_rumour".
The "new_rumour" key should be `null` or an object like `{{"target_index": 0, "rumour_fact": "The new fact about them."}}`.
"""

    @staticmethod
    def _mentions(context):
        """Mentions from the triggering message (empty for slash invocations)."""
        return context.message.mentions if context.message else []

    @commands.hybrid_command(
        name="chat", description="Chat with Dodo! Dodo will try to remember important things about you."
    )
    async def chat(self, context: Context, *, message: str) -> None:
        """Chat with Dodo — single LLM call handles reply, memory, mood and rumours."""
        client = self._client_for(context.guild.id if context.guild else None)
        if client is None:
            await context.send(lang.CHAT_API_ERROR.format(error="no API key configured for this server"))
            return
        async with context.typing():
            author_id = str(context.author.id)
            memory_doc = config_py.memory.find_one({"user_id": author_id}) or {}
            current_memory = memory_doc.get("memory", "No memories yet.")
            current_relationship = memory_doc.get("relationship", 500)
            current_rumours = memory_doc.get("rumours_heard", [])

            system_prompt = self._build_system_prompt(
                context, current_memory, current_relationship, current_rumours
            )

            try:
                completion = client.chat.completions.create(
                    model=_MODEL,
                    temperature=1.3,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                )
            except OpenAIError as error:
                await context.send(lang.CHAT_API_ERROR.format(error=error))
                return

            try:
                data = json.loads(completion.choices[0].message.content)
                bot_reply = data.get("chat_reply", lang.CHAT_REPLY_FALLBACK)
                sentiment_score = int(data.get("sentiment_score", 0))
                new_memory = data.get("updated_memory", current_memory).strip()
                new_rumour = data.get("new_rumour")
            except (json.JSONDecodeError, ValueError, TypeError):
                bot_reply = lang.CHAT_PARSE_ERROR
                sentiment_score, new_memory, new_rumour = 0, current_memory, None

            for chunk in range(0, len(bot_reply), 2000):
                await context.send(bot_reply[chunk : chunk + 2000])

            new_relationship = max(0, min(1000, current_relationship + sentiment_score))
            config_py.memory.update_one(
                {"user_id": author_id},
                {"$set": {"memory": new_memory, "relationship": new_relationship}},
                upsert=True,
            )
            self._save_rumour(context, new_rumour)

    def _save_rumour(self, context, new_rumour) -> None:
        """Persist a detected rumour against the mentioned target, if valid."""
        mentioned_users = [u for u in self._mentions(context) if u.id != context.author.id and not u.bot]
        if not (isinstance(new_rumour, dict) and mentioned_users):
            return
        target_index = new_rumour.get("target_index")
        rumour_fact = new_rumour.get("rumour_fact")
        if not (isinstance(target_index, int) and rumour_fact and 0 <= target_index < len(mentioned_users)):
            return
        target_user = mentioned_users[target_index]
        config_py.memory.update_one(
            {"user_id": str(target_user.id)},
            {
                "$push": {
                    "rumours_heard": {
                        "rumour": rumour_fact,
                        "source_id": str(context.author.id),
                        "source_name": context.author.display_name,
                    }
                },
                "$setOnInsert": {"relationship": 500, "memory": "No memories yet."},
            },
            upsert=True,
        )


async def setup(bot):
    await bot.add_cog(Chat(bot))
