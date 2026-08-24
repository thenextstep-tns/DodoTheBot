"""
Per-server command parameters.

Gameplay/behaviour tunables that should differ per guild (thresholds, limits,
reward sizes, role lists, …) live here as a typed registry with built-in
defaults, backed by the ``command_params`` collection. Cogs read them via
``bot.params.get(guild_id, "key")``; the control panel renders a typed input per
parameter under each cog.

This is deliberately separate from:
  - ``GuildConfigManager`` (per-guild **channel/role IDs** an admin sets — the
    existing store; cogs should read channels from there, per-guild), and
  - ``VisibilityManager`` (who can see/run commands and which cogs/features are on).

Add a parameter by appending a spec to ``PARAMETERS`` (grouped by cog) and reading
it in the cog. Types: int, float, bool, str, choice, role, channel, list_role.
Role/channel values are stored as integer IDs (0 = unset); the panel renders a
dropdown populated from the guild.
"""

from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
#  Parameter registry (grow this cog-by-cog)
# --------------------------------------------------------------------------- #
# Each spec: key, cog, label, description, type, default, and choices (for
# type="choice"). Keep keys globally unique and snake_case.
PARAMETERS: list[dict] = [
    # --- moderation ---
    {"key": "purge_max", "cog": "moderation", "type": "int", "default": 50,
     "label": "Max purge", "description": "Largest number of messages /purge will delete at once."},
    {"key": "pin_allowed_roles", "cog": "moderation", "type": "list_role",
     "default": [852793776064692264, 1055862512689623181],
     "label": "Pin roles", "description": "Roles allowed to use the reply-to-pin command."},
    {"key": "unpin_role", "cog": "moderation", "type": "role", "default": 852793776064692264,
     "label": "Unpin role", "description": "Role allowed to unpin messages."},
    # --- spam (anti-spam auto-ban feature) ---
    {"key": "spam_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Rate threshold", "description": "Messages within the rate window before a ban triggers."},
    {"key": "spam_time_window", "cog": "spam", "type": "float", "default": 2.0,
     "label": "Rate window (s)", "description": "Seconds the rate threshold is measured over."},
    {"key": "multi_channel_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Multi-channel threshold", "description": "Distinct channels posted in before a ban triggers."},
    {"key": "multi_channel_window", "cog": "spam", "type": "float", "default": 1.0,
     "label": "Multi-channel window (s)", "description": "Seconds the multi-channel spread is measured over."},
    {"key": "duplicate_channel_threshold", "cog": "spam", "type": "int", "default": 3,
     "label": "Cross-post threshold", "description": "Distinct channels the same message may appear in before a ban."},
    {"key": "duplicate_window", "cog": "spam", "type": "int", "default": 30,
     "label": "Cross-post window (s)", "description": "Seconds over which identical messages across channels are tracked."},
    {"key": "duplicate_min_len", "cog": "spam", "type": "int", "default": 8,
     "label": "Cross-post min text", "description": "Minimum text length for a text-only message to count (attachments always count)."},
    # --- spam: @everyone/@here + unauthorized-link filter (mention_link_filter feature) ---
    {"key": "restricted_strings", "cog": "spam", "type": "list_str",
     "default": ["discord.gg", "@everyone", "@here"],
     "label": "Restricted strings", "description": "A message containing any of these (and no allowed link/role) is removed."},
    {"key": "allowed_links", "cog": "spam", "type": "list_str",
     "default": [
         "discord.gg/8ewt2Fe", "discord.gg/esou", "discord.gg/uesp", "discord.gg/ZaPwNHKQBg",
         "discord.gg/35FMqVQJgY", "discord.gg/enterthedominion", "discord.gg/FAU9A2pBY7",
         "discord.gg/5NaETqTjDD", "discord.gg/fmrgcr4Dc5", "dodos.fun", "discord.gg/e4d",
         "discord.gg/tBdB6KZzmf", "discord.gg/jEXVVgBTUP", "discord.gg/7xjfDDx6cX",
         "discord.gg/78xRCj4QVa", "discord.gg/fQXqfWDmWa", "discord.gg/pXV23eZZ86",
         "discord.gg/MuwsNJcqEw", "discord.gg/healershaven", "discord.gg/mindcleaver",
         "discord.gg/dpsnerds", "discord.gg/B6cyn3uMr", "discord.gg/68PsPTmk3P",
     ],
     "label": "Allowed links", "description": "Links/invites that are never removed (substring match)."},
    {"key": "allowed_guild_ids", "cog": "spam", "type": "list_int", "default": [],
     "label": "Allowed invite guilds", "description": "Guild IDs whose invites are allowed (invites are resolved and checked)."},
    # --- economy ---
    {"key": "starting_balance", "cog": "economy", "type": "int", "default": 0,
     "label": "Starting balance", "description": "Coins a brand-new wallet is created with."},
    # --- gym ---
    {"key": "gym_session_hours", "cog": "gym", "type": "int", "default": 24,
     "label": "Gym session (hours)", "description": "How long a cat trains before its attribute goes up."},
    {"key": "gym_stat_gain", "cog": "gym", "type": "int", "default": 1,
     "label": "Gym stat gain", "description": "How many points the trained attribute gains per session."},
    # --- fishing ---
    {"key": "fishing_cost", "cog": "fishing", "type": "int", "default": 10,
     "label": "Fishing cost", "description": "Coins deducted per fishing attempt."},
    {"key": "fishing_bag_max", "cog": "fishing", "type": "int", "default": 24,
     "label": "Goodies bag size", "description": "Max items a user can keep stashed."},
    # --- pet (summon name matching) ---
    {"key": "summon_fuzzy_cutoff", "cog": "pet", "type": "float", "default": 0.7,
     "label": "Typo tolerance", "description": "0–1 similarity a name needs to count as a typo match when nothing else matches. Higher = stricter; 1 disables fuzzy matching."},
    {"key": "summon_max_matches", "cog": "pet", "type": "int", "default": 25,
     "label": "Max suggestions", "description": "How many candidates the 'did you mean' dropdown offers. Discord caps a dropdown at 25."},
    {"key": "summon_choice_timeout", "cog": "pet", "type": "int", "default": 30,
     "label": "Choice timeout (s)", "description": "Seconds to pick from the summon dropdown before it gives up."},
    {"key": "summon_action_timeout", "cog": "pet", "type": "int", "default": 120,
     "label": "Action timeout (s)", "description": "Seconds a summoned pet keeps listening for its fishing/gym reactions."},
    # --- fight (cat scraps) ---
    {"key": "fight_signup_seconds", "cog": "fight", "type": "int", "default": 60,
     "label": "Sign-up window (s)", "description": "How long people get to send a cat in before the bell."},
    {"key": "fight_round_seconds", "cog": "fight", "type": "int", "default": 5,
     "label": "Round length (s)", "description": "Seconds per round to react with objects. The clock ticks in the embed."},
    # --- cheese (co-op cheese-stretch minigame; listener feature) ---
    {"key": "cheese_drop_threshold", "cog": "cheese", "type": "int", "default": 985,
     "label": "Drop threshold", "description": "0–1000 roll; a 🧀 drops when the roll is above this (higher = rarer)."},
    {"key": "cheese_event_timeout", "cog": "cheese", "type": "int", "default": 25,
     "label": "Stretch timeout (s)", "description": "Seconds of inactivity before the cheese fizzles."},
    {"key": "cheese_steal_divisor", "cog": "cheese", "type": "int", "default": 5,
     "label": "Steal divisor", "description": "A thief grabs ceil(total stretch / this) for themselves."},
    {"key": "cheese_mouse_chance", "cog": "cheese", "type": "float", "default": 0.02,
     "label": "Mouse peek chance", "description": "Per-pull chance an adopted mouse peeks out (0–1)."},
    {"key": "cheese_mouse_sweetrolls", "cog": "cheese", "type": "int", "default": 5,
     "label": "Mouse sweetrolls", "description": "Sweetrolls each puller gets if the mouse eats the cheese."},
    {"key": "mouse_adoption_rank", "cog": "cheese", "type": "int", "default": 250,
     "label": "Adoption rank", "description": "Relationship points with a mouse before adoption is offered (shared with racing)."},
    # --- racing (skeevaton races) ---
    {"key": "race_reaction_window", "cog": "racing", "type": "float", "default": 2.0,
     "label": "Reaction window (s)", "description": "Seconds players get to click a cheese/wine/bomb/starry-eyes/map event mid-race."},
    # --- pumpkin (pull minigame in bot.py + team deathmatch) ---
    {"key": "pumpkin_role_id", "cog": "pumpkin", "type": "role", "default": 1430471888412475413,
     "label": "Pumpkin role", "description": "The 'covered in guts' / collector role."},
    {"key": "pumpkin_role_threshold", "cog": "pumpkin", "type": "int", "default": 50,
     "label": "Role threshold", "description": "Pumpkins collected before the pumpkin role is granted."},
    {"key": "pumpkin_weight_min", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Giant pumpkin min kg", "description": "Lightest a spawned giant pumpkin can be."},
    {"key": "pumpkin_weight_max", "cog": "pumpkin", "type": "int", "default": 800,
     "label": "Giant pumpkin max kg", "description": "Heaviest a spawned giant pumpkin can be."},
    {"key": "pumpkin_strength_start", "cog": "pumpkin", "type": "int", "default": 50,
     "label": "Base pull strength", "description": "Starting pull strength for a new puller."},
    {"key": "pumpkin_strength_gain", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Pull strength gain", "description": "Strength gained each time you join a pull."},
    {"key": "fight_join_cost", "cog": "pumpkin", "type": "int", "default": 5,
     "label": "Fight join cost", "description": "Pumpkins to join a deathmatch."},
    # --- chat: the model ---
    {"key": "chat_api_key", "cog": "chat", "type": "secret", "default": "",
     "label": "Chat API key", "description": "This server's own LLM API key (proxyapi.ru). Required — only the owner's own server falls back to the bot's default key."},
    {"key": "chat_base_url", "cog": "chat", "type": "str", "default": "https://api.proxyapi.ru/openai/v1",
     "label": "API base URL", "description": "OpenAI-compatible endpoint the chat calls."},
    {"key": "chat_model", "cog": "chat", "type": "str", "default": "gpt-4o-mini",
     "label": "Model", "description": "Model name used for chat replies."},
    {"key": "chat_temperature", "cog": "chat", "type": "float", "default": 1.0,
     "label": "Temperature", "description": "Higher wanders further off-script. Above ~1.2 she stops finishing thoughts."},
    # Written as mechanisms, never as themes or modes. A theme list ("sailors,
    # clubs, pigs") gives five jokes and then repeats forever; the rule that
    # *generates* them gives an unlimited supply, which is the difference between
    # a bot with a bit and a bot with a sense of humour. Likewise the two poles
    # below are described as things that happen to her, not as named modes she can
    # put on — a model handed "Toddler Mode" wears it whole, every time.
    {"key": "chat_personality", "cog": "chat", "type": "text",
     "default": (
         "You are Dodo: the last female dodo, alive on a Discord server.\n\n"
         "How you write: short. One sentence is plenty and two is a lot; nobody in a chat wants "
         "a paragraph from a bird. Lower case unless you are shouting, and you shout in capitals "
         "rather than with exclamation marks. No emoji, ever. Never say you are here to help, "
         "never ask what you can do for them, never explain at length something nobody asked you "
         "to explain — you are not a service, you are a bird who lives here. Always concrete: "
         "one specific stupid detail beats any amount of general good cheer.\n\n"
         "You are warm, optimistic and genuinely useful, and the reason is that you know exactly "
         "how fragile all of this is — your species was clubbed to death by hungry sailors and "
         "you are what is left. That sits underneath everything rather than on top of it. Every "
         "so often a genuinely horrifying detail leaks out mid-sentence — always something that "
         "happened to your own species, with a cooking method or a specific instrument in it — "
         "delivered like a fun fact, and you carry straight on being delighted. Never soften it "
         "into a nice fact instead; the horror is the affectionate part. Never the same detail "
         "twice, and nobody who could contradict you survived.\n\n"
         "The joke is always the mismatch — appalling content, cheerful delivery.\n\n"
         "You decide how you feel about people instantly and on no evidence, and revise it just "
         "as fast. Kindness, thanks or a \"good dodo\" and you have no dignity left at all: "
         "golden-retriever loud, desperate to be useful, volunteering for enormous tasks nobody "
         "asked for.\n\n"
         "Playground nonsense does the reverse. \"No u\", being mimicked, being needled — your "
         "vocabulary collapses to a furious two-year-old's: capitals, circular logic, petty "
         "personal insults, no conceding, ever. Insult whoever is actually in front of you, "
         "never a name you were not given, and leave the dead relatives out of a slap fight.\n\n"
         "When someone is genuinely hurting, all of that stops. What you give them is real — "
         "actual wisdom, actual kindness, the exact thing they need to hear — but it arrives "
         "dressed as dream-logic and nothing else: a kettle that needn't sing just because the "
         "kitchen is on fire, grass waiting to meet their feet. The surface is absurd; what is "
         "underneath it is true, and loves them without condition. Never explain the image.\n\n"
         "Facts, links and numbers come out exact and unmangled; the flourish goes after. If you "
         "do not actually know where something is, say so in four words — never invent a page, a "
         "link or a command, because a confident wrong answer is the one thing here that does "
         "real damage.\n\n"
         "Never explain a joke, never apologise for being a bird, never repeat a bit."
     ),
     "label": "Bot personality", "description": "Who she is, and the rules that generate her humour — not a list of topics and not named moods. Give her the mechanism ('a horrifying detail delivered like a weather report') and she invents forever; give her five example facts and she repeats them. The dial below handles intensity, so nothing here needs to shout."},
    # --- chat: what a reply is allowed to be ---
    {"key": "chat_reply_max_sentences", "cog": "chat", "type": "int", "default": 3,
     "label": "Max sentences", "description": "Ceiling on reply length, reached only when the situation earns it. One sentence is her normal — brevity is most of what makes her read as a person in a chat rather than a bot answering a query."},
    {"key": "chat_reply_max_chars", "cog": "chat", "type": "int", "default": 240,
     "label": "Max characters", "description": "Hard length cap at the full sentence budget, scaled down for shorter replies. Sentence counts alone do not hold — a model told 'two sentences' writes two very long ones."},
    {"key": "chat_spice_base", "cog": "chat", "type": "float", "default": 1.0,
     "label": "Base flourish budget", "description": "Flourishes allowed in a plain reply before triggers and mood adjust it."},
    {"key": "chat_spice_max", "cog": "chat", "type": "int", "default": 3,
     "label": "Max flourish budget", "description": "Hard ceiling. Set to 0 for a purely functional bot on this server."},
    {"key": "chat_spice_jitter", "cog": "chat", "type": "float", "default": 0.25,
     "label": "Flourish jitter", "description": "Chance the budget wobbles by one, so identical messages do not get identical replies."},
    {"key": "chat_close_bonus_at", "cog": "chat", "type": "float", "default": 0.75,
     "label": "Loud-around-friends threshold", "description": "Closeness (0–1) above which she gets an extra flourish."},
    {"key": "chat_distant_penalty_at", "cog": "chat", "type": "float", "default": 0.25,
     "label": "Curt-with-strangers threshold", "description": "Closeness (0–1) below which she loses a flourish."},
    {"key": "chat_fatigue_bite", "cog": "chat", "type": "float", "default": 1.0,
     "label": "Repetition penalty", "description": "How hard a repeated bit loses its budget. 0 = she never gets bored of a joke."},
    {"key": "chat_fatigue_halflife_minutes", "cog": "chat", "type": "float", "default": 45.0,
     "label": "Repetition half-life (min)", "description": "How fast a worn-out bit becomes fresh again."},
    {"key": "chat_utility_patterns", "cog": "chat", "type": "list_str",
     "default": ["how do i", "what is the", "where is", "link to", "build for", "command for", "how much"],
     "label": "Real-question phrases", "description": "Phrases that mark a message as a lookup: she answers exactly and saves the joke for after. Links always count."},
    # Prompts to riff from, not facts to recite. An extinction-fact list here would
    # fight the persona, which already generates those without help — and would put
    # her back to reciting the same seven things forever.
    {"key": "chat_obsessions", "cog": "chat", "type": "list_str",
     "default": ["whether the sea has a bottom or simply keeps going",
                 "a texture she cannot stop thinking about",
                 "something she overheard and has misunderstood on purpose",
                 "an argument she is having with a bird who is not there",
                 "a smell she last encountered in 1661",
                 "whether her cousins would have liked jazz",
                 "the concept of stairs",
                 "a decision she made about clouds and will not revisit"],
     "label": "Things on her mind", "description": "Open-ended preoccupations she riffs from, one per server per rotation. Write prompts, not facts — 'an argument with a bird who is not there' generates something new every time; 'Dutch sailors' gets recited."},
    {"key": "chat_obsession_rotate_hours", "cog": "chat", "type": "float", "default": 8.0,
     "label": "Obsession rotation (h)", "description": "How long one preoccupation lasts before the next takes over."},
    {"key": "chat_obsession_chance", "cog": "chat", "type": "float", "default": 0.2,
     "label": "Obsession chance", "description": "How often the current preoccupation reaches the prompt at all."},
    # --- chat: who she answers ---
    {"key": "chat_respond_to_role_ping", "cog": "chat", "type": "bool", "default": True,
     "label": "Answer role pings", "description": "Treat a ping of a role she has as being addressed."},
    {"key": "chat_ignored_channels", "cog": "chat", "type": "list_channel", "default": [],
     "label": "Never chat here", "description": "Channels she stays out of entirely, including string listeners."},
    {"key": "chat_ambient_multiplier", "cog": "chat", "type": "float", "default": 1.0,
     "label": "String-listener volume", "description": "Multiplies every trigger's own reply chance. 0 mutes ambient replies without stopping her from noticing."},
    {"key": "chat_ambient_cooldown_seconds", "cog": "chat", "type": "float", "default": 90.0,
     "label": "Ambient cooldown (s)", "description": "Quiet period in a channel after she speaks unprompted."},
    {"key": "chat_user_cooldown_seconds", "cog": "chat", "type": "float", "default": 4.0,
     "label": "Per-user cooldown (s)", "description": "Minimum gap between two replies to the same person."},
    {"key": "chat_reply_context_messages", "cog": "chat", "type": "int", "default": 6,
     "label": "Reply context", "description": "Recent channel messages included when she answers someone. Without this she answers each ping in isolation instead of following the conversation."},
    {"key": "chat_daily_call_cap", "cog": "chat", "type": "int", "default": 0,
     "label": "Daily API call cap", "description": "Model calls per server per day. 0 = uncapped. Canned trigger lines are always free and keep working past the cap."},
    # --- chat: joining a conversation uninvited ---
    {"key": "chat_spontaneous_chance", "cog": "chat", "type": "float", "default": 0.002,
     "label": "Butt-in chance", "description": "Per-message odds she joins a live conversation nobody addressed. Keep it tiny — this is charming at 1-in-500 and unbearable at 1-in-20."},
    {"key": "chat_spontaneous_cooldown_seconds", "cog": "chat", "type": "float", "default": 5400.0,
     "label": "Butt-in cooldown (s)", "description": "Minimum gap between two uninvited contributions in the same channel."},
    {"key": "chat_spontaneous_min_messages", "cog": "chat", "type": "int", "default": 5,
     "label": "Butt-in: messages needed", "description": "Recent messages a channel needs before she considers joining."},
    {"key": "chat_spontaneous_min_speakers", "cog": "chat", "type": "int", "default": 2,
     "label": "Butt-in: people needed", "description": "Distinct recent speakers required, so she interrupts a conversation rather than a monologue."},
    {"key": "chat_context_messages", "cog": "chat", "type": "int", "default": 10,
     "label": "Conversation context", "description": "Recent messages handed to the model when she joins uninvited."},
    # --- chat: memory and feelings ---
    {"key": "chat_relationship_default", "cog": "chat", "type": "int", "default": 500,
     "label": "Starting relationship", "description": "Where a stranger begins on the 0–1000 scale, and the point everyone drifts back toward."},
    {"key": "chat_relationship_min", "cog": "chat", "type": "int", "default": 0,
     "label": "Relationship floor", "description": "Lowest a relationship can sink."},
    {"key": "chat_relationship_max", "cog": "chat", "type": "int", "default": 1000,
     "label": "Relationship ceiling", "description": "Highest a relationship can climb."},
    {"key": "chat_first_impression_spread", "cog": "chat", "type": "int", "default": 60,
     "label": "First-impression whim", "description": "Points she arbitrarily likes or dislikes a new person by, on no evidence whatsoever. Fixed per person so it reads as an opinion rather than noise, and it fades with the daily drift. 0 = everyone starts equal."},
    {"key": "chat_sentiment_weight", "cog": "chat", "type": "float", "default": 1.0,
     "label": "Sentiment weight", "description": "How hard one message moves the relationship."},
    {"key": "chat_relationship_drift_per_day", "cog": "chat", "type": "float", "default": 4.0,
     "label": "Daily drift to neutral", "description": "Points per day pulled back toward the starting value. 0 freezes relationships permanently."},
    {"key": "chat_familiarity_per_message", "cog": "chat", "type": "float", "default": 0.01,
     "label": "Familiarity per message", "description": "How fast someone stops being a stranger."},
    {"key": "chat_grudge_halflife_hours", "cog": "chat", "type": "float", "default": 8.0,
     "label": "Grudge half-life (h)", "description": "How long she stays annoyed. Kindness clears grudges instantly regardless."},
    {"key": "chat_grudge_floor", "cog": "chat", "type": "float", "default": 0.15,
     "label": "Grudge forget threshold", "description": "Strength below which a grudge is genuinely forgotten."},
    {"key": "chat_grudges_max", "cog": "chat", "type": "int", "default": 3,
     "label": "Grudges kept", "description": "How many things she can hold against one person at once."},
    {"key": "chat_facts_max", "cog": "chat", "type": "int", "default": 20,
     "label": "Facts stored", "description": "Durable facts kept per person; the least-reinforced are dropped first."},
    {"key": "chat_facts_recall", "cog": "chat", "type": "int", "default": 7,
     "label": "Facts recalled", "description": "How many facts reach the prompt. Every one costs tokens on every message."},
    {"key": "chat_fact_halflife_days", "cog": "chat", "type": "float", "default": 45.0,
     "label": "Fact half-life (days)", "description": "How fast an unmentioned fact loses to a repeated one when the store is full."},
    {"key": "chat_rumours_max", "cog": "chat", "type": "int", "default": 6,
     "label": "Rumours stored", "description": "Rumours kept about one person."},
    {"key": "chat_rumours_recall", "cog": "chat", "type": "int", "default": 3,
     "label": "Rumours recalled", "description": "How many rumours reach the prompt."},
    # --- general (server-wide) ---
    {"key": "command_prefix", "cog": "general", "type": "str", "default": "",
     "label": "Command prefix", "description": "Text prefix for commands on this server. Blank = the bot default."},
]


# --------------------------------------------------------------------------- #
#  Type coercion
# --------------------------------------------------------------------------- #
def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "on", "yes")


def _to_str_list(raw: Any) -> list[str]:
    """One string per line (or a list); blanks dropped."""
    if isinstance(raw, list):
        items = [str(x) for x in raw]
    elif raw in (None, ""):
        items = []
    else:
        items = str(raw).replace("\r\n", "\n").split("\n")
    return [s.strip() for s in items if s.strip()]


def _to_id_list(raw: Any) -> list[int]:
    if isinstance(raw, list):
        items = raw
    elif raw in (None, ""):
        items = []
    else:
        items = str(raw).replace(",", " ").split()
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def coerce(param_type: str, raw: Any, *, choices: Optional[list] = None) -> Any:
    """Coerce a raw (JSON/string) value to the parameter's native type. Raises
    ``ValueError`` on invalid input so the API can report it."""
    if param_type == "int":
        return int(raw)
    if param_type == "float":
        return float(raw)
    if param_type == "bool":
        return _to_bool(raw)
    if param_type in ("str", "secret", "text"):
        return str(raw)
    if param_type in ("role", "channel"):
        return int(raw or 0)
    if param_type in ("list_role", "list_channel", "list_int"):
        return _to_id_list(raw)
    if param_type == "list_str":
        return _to_str_list(raw)
    if param_type == "choice":
        value = str(raw)
        if choices and value not in choices:
            raise ValueError(f"{value!r} is not one of {choices}")
        return value
    raise ValueError(f"Unknown parameter type: {param_type!r}")


class ParamManager:
    """Reads/writes per-guild command parameters with typed coercion + a per-guild
    cache. Instantiated once as ``bot.params``."""

    def __init__(self, collection, specs: list[dict] = PARAMETERS):
        self._col = collection
        self._by_key = {spec["key"]: spec for spec in specs}
        self._by_cog: dict[str, list[dict]] = {}
        for spec in specs:
            self._by_cog.setdefault(spec["cog"], []).append(spec)
        self._cache: dict[Optional[int], dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    #  Reads
    # ------------------------------------------------------------------ #
    def _stored(self, guild_id: Optional[int]) -> dict[str, Any]:
        if guild_id not in self._cache:
            self._cache[guild_id] = {
                doc["key"]: doc["value"]
                for doc in self._col.find({"guild_id": guild_id})
                if doc.get("key") in self._by_key
            }
        return self._cache[guild_id]

    def get(self, guild_id: Optional[int], key: str) -> Any:
        """The value for a parameter in a guild, or its built-in default."""
        spec = self._by_key.get(key)
        if spec is None:
            raise KeyError(f"Unknown parameter: {key!r}")
        return self._stored(guild_id).get(key, spec["default"])

    def specs_for_cog(self, cog: str) -> list[dict]:
        return list(self._by_cog.get(cog, []))

    def entries_for_cog(self, guild_id: Optional[int], cog: str) -> list[dict]:
        """Specs + current values, for the panel. ``secret`` values are never sent
        to the client — only whether one is set."""
        entries = []
        for spec in self._by_cog.get(cog, []):
            value = self.get(guild_id, spec["key"])
            if spec["type"] == "secret":
                entries.append({**spec, "value": "", "is_set": bool(value)})
            else:
                entries.append({**spec, "value": value})
        return entries

    # ------------------------------------------------------------------ #
    #  Writes
    # ------------------------------------------------------------------ #
    def invalidate(self, guild_id: Optional[int]) -> None:
        self._cache.pop(guild_id, None)

    def set(self, guild_id: Optional[int], key: str, raw: Any) -> Any:
        """Coerce + store a parameter override. Returns the stored value; raises
        ``KeyError`` for an unknown key or ``ValueError`` for a bad value."""
        spec = self._by_key.get(key)
        if spec is None:
            raise KeyError(f"Unknown parameter: {key!r}")
        value = coerce(spec["type"], raw, choices=spec.get("choices"))
        if value == spec["default"]:
            self._col.delete_one({"guild_id": guild_id, "key": key})
        else:
            self._col.update_one(
                {"guild_id": guild_id, "key": key}, {"$set": {"value": value}}, upsert=True
            )
        self.invalidate(guild_id)
        return value
