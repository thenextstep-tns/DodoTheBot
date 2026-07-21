import json
import os
import random
import sys
import openai

import disnake
from disnake.ext import commands
from disnake.ext.commands import Context

# --- Configuration Loading ---
if not os.path.isfile("config.json"):
    raise FileNotFoundError("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

try:
    import config_py
    import lang
except ImportError as e:
    raise ImportError(f"'{e.name}.py' not found! Please add it and try again.")

def get_relationship_description(score):
    """Generates a personality instruction based on the relationship score."""
    if score < 250:
        return f"You are very grumpy and annoyed with this user (Relationship Score: {score}/1000). Be childishly angry, pouty, and use short, curt sentences. You don't feel like talking to them."
    elif score < 500:
        return f"You are a little grumpy with this user (Relationship Score: {score}/1000). Be slightly sassy and reluctant, but still answer their questions."
    elif score > 750:
        return f"You are overjoyed to see this user! (Relationship Score: {score}/1000). They are one of your best friends. Be extremely enthusiastic, use exclamation points, and be very cheerful."
    elif score > 500:
        return f"You are happy to talk to this user (Relationship Score: {score}/1000). Be friendly, warm, and engaging."
    else:  # score == 500
        return f"You have a neutral relationship with this user (Relationship Score: {score}/1000). Be your normal, helpful self."


class Chat(commands.Cog, name="chat"):
    def __init__(self, bot):
        self.bot = bot
        # --- OpenAI Client Initialization ---
        if hasattr(config_py, 'PROXY_API') and config_py.PROXY_API:
            openai.api_key = config_py.PROXY_API
            openai.api_base = "https://api.proxyapi.ru/openai/v1"
        else:
            raise ValueError("PROXY_API key not found in config_py.py.")

    @commands.command(
        name="chat",
        description="Chat with Dodo! Dodo will try to remember important things about you.",
    )
    async def chat(self, context: Context, *, message: str):
        """
        Chat with DodoGPT, featuring long-term memory, relationship scoring,
        and a unique personality, all handled in a single, optimized API call.
        """
        async with context.typing():
            author_id = str(context.author.id)

            # -------------------- 1. Load Memory & Rumours for Author --------------------
            user_memory_doc = config_py.memory.find_one({"user_id": author_id})
            if not user_memory_doc:
                user_memory_doc = {"user_id": author_id, "memory": "No memories yet.", "relationship": 500, "rumours_heard": []}
            
            current_memory = user_memory_doc.get("memory", "No memories yet.")
            current_relationship = user_memory_doc.get("relationship", 500)
            current_rumours = user_memory_doc.get("rumours_heard", [])

            # ---------------- 2. Prepare Mention and System Context ----------------
            mention_context = ""
            mentioned_users = [user for user in context.message.mentions if user.id != context.author.id and not user.bot]
            valid_rumour_targets = [{"index": i, "name": user.display_name} for i, user in enumerate(mentioned_users)]

            if mentioned_users:
                for user in mentioned_users:
                    other_memory = config_py.memory.find_one({"user_id": str(user.id)})
                    if other_memory:
                        mention_context += (
                            f"Context for {user.display_name} (ID: {user.id}):\n"
                            f"- Memory: {other_memory.get('memory', 'None')}\n"
                            f"- Relationship: {other_memory.get('relationship', 500)}\n\n"
                        )
            
            drowsiness_roll = random.randint(0, 10)
            relationship_desc = get_relationship_description(current_relationship)
            
            rumours_context = ""
            if current_rumours:
                rumour_list = "\n".join([f'- "{r.get("rumour")}" (heard from {r.get("source_name", "an unknown bird")})' for r in current_rumours])
                rumours_context = f"**Rumours you've heard about {context.author.display_name}:**\n{rumour_list}"


            # ---------------- 3. Construct the Single API Prompt -----------------
            system_prompt = f"""
You are Dodo, a bird from "ESO for Dodos". Your personality has two layers: your base mood and your current drowsiness. You say things that are extremely stupid and silly but at the same time extremely wise and profound.
**1. Your Base Mood:**
{relationship_desc}

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
{mention_context if mention_context else ""}
End of memory.

---
Respond with a single, syntactically correct JSON object with four keys: "chat_reply", "sentiment_score", "updated_memory", and "new_rumour".
The "new_rumour" key should be `null` or an object like `{{"target_index": 0, "rumour_fact": "The new fact about them."}}`.
"""

            try:
                # -------------------- 4. Make the Single API Call --------------------
                chat_completion = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    temperature=1.3,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ]
                )

                response_content = chat_completion.choices[0].message.content
                
                # ---------------- 5. Parse the JSON Response Safely ----------------
                try:
                    data = json.loads(response_content)
                    bot_reply = data.get("chat_reply", "I... I think I forgot what I was saying. My apologies!")
                    sentiment_score = int(data.get("sentiment_score", 0))
                    new_memory = data.get("updated_memory", current_memory).strip()
                    new_rumour_data = data.get("new_rumour")

                except (json.JSONDecodeError, ValueError, TypeError):
                    bot_reply = "My thoughts got all tangled up! Could you say that again?"
                    sentiment_score = 0
                    new_memory = current_memory
                    new_rumour_data = None

                # -------------------- 6. Send Reply to Discord --------------------
                for i in range(0, len(bot_reply), 2000):
                    await context.send(bot_reply[i:i+2000])

                # ---------------- 7. Persist Updated Data to DB -----------------
                new_relationship = max(0, min(1000, current_relationship + sentiment_score))
                config_py.memory.update_one(
                    {"user_id": author_id},
                    {"$set": {"memory": new_memory, "relationship": new_relationship}},
                    upsert=True,
                )

                # If a new rumour was detected, save it to the target's document
                if new_rumour_data and isinstance(new_rumour_data, dict) and mentioned_users:
                    target_index = new_rumour_data.get("target_index")
                    rumour_fact = new_rumour_data.get("rumour_fact")
                    
                    if isinstance(target_index, int) and rumour_fact:
                        if 0 <= target_index < len(mentioned_users):
                            target_user = mentioned_users[target_index]
                            
                            config_py.memory.update_one(
                                {"user_id": str(target_user.id)},
                                {
                                    "$push": {
                                        "rumours_heard": {
                                            "rumour": rumour_fact,
                                            "source_id": str(context.author.id),
                                            "source_name": context.author.display_name
                                        }
                                    },
                                    "$setOnInsert": {"relationship": 500, "memory": "No memories yet."}
                                },
                                upsert=True
                            )

            except openai.error.OpenAIError as e:
                await context.send(f"Oh dear, my brain feels a bit fuzzy... I couldn't connect to my thoughts. (Error: {e})")
            except Exception as e:
                await context.send("Whoops! I stumbled and dropped my thoughts. Something went wrong.")
                print(f"An unexpected error occurred in the chat command: {e}")


def setup(bot):
    bot.add_cog(Chat(bot))

