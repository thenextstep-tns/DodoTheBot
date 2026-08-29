"""
Turning archived ids into names.

The stats archives store ids, and the obvious look-up — the gateway cache — only
knows about things that still exist. Members leave and channels get deleted, so
resolution walks outwards:

1. the guild (nickname / current channel name — the most useful label),
2. the bot's global cache,
3. a stored name from the last time anybody resolved this id,
4. the Discord API,

and whatever comes back is written to step 3, so a name learned today still
labels the row after the member leaves or the channel is deleted. Only the ids
on the page being rendered are ever resolved.
"""

from __future__ import annotations

import datetime

import discord

import config_py

_MEMORY: dict[str, str] = {}


def _key(kind: str, entity_id: int) -> str:
    return f"{kind}:{entity_id}"


def _remember(kind: str, entity_id: int, name: str) -> None:
    """Cache a name in memory and in Mongo (so it outlives the process and the entity)."""
    key = _key(kind, entity_id)
    if _MEMORY.get(key) == name:
        return
    _MEMORY[key] = name
    try:
        config_py.entity_names.update_one(
            {"_id": key},
            {"$set": {"name": name, "updated_at": datetime.datetime.now(datetime.timezone.utc)}},
            upsert=True,
        )
    except Exception:  # noqa: BLE001 - a label is never worth an error page
        pass


def _stored(kind: str, ids: list[int]) -> dict[int, str]:
    """Names previously learned for these ids, memory first then Mongo."""
    found = {}
    missing = []
    for entity_id in ids:
        cached = _MEMORY.get(_key(kind, entity_id))
        if cached:
            found[entity_id] = cached
        else:
            missing.append(entity_id)
    if missing:
        try:
            keys = [_key(kind, entity_id) for entity_id in missing]
            for doc in config_py.entity_names.find({"_id": {"$in": keys}}):
                entity_id = int(str(doc["_id"]).split(":", 1)[1])
                found[entity_id] = doc["name"]
                _MEMORY[str(doc["_id"])] = doc["name"]
        except Exception:  # noqa: BLE001
            pass
    return found


async def resolve_users(bot, guild, ids) -> dict[int, str]:
    """Label each user id: in-guild nickname where possible, else their username."""
    ids = [i for i in dict.fromkeys(ids) if isinstance(i, int)]
    labels: dict[int, str] = {}
    unresolved = []

    for user_id in ids:
        member = guild.get_member(user_id)
        if member is not None:
            labels[user_id] = member.display_name
            _remember("user", user_id, member.display_name)
            continue
        user = bot.get_user(user_id)
        if user is not None:
            name = user.global_name or user.name
            labels[user_id] = name
            _remember("user", user_id, name)
            continue
        unresolved.append(user_id)

    stored = _stored("user", unresolved)
    for user_id in list(unresolved):
        if user_id in stored:
            # Known from an earlier visit; mark it as someone who has since left.
            labels[user_id] = f"{stored[user_id]} (left)"
            unresolved.remove(user_id)

    for user_id in unresolved:
        try:
            user = await bot.fetch_user(user_id)
        except discord.HTTPException:
            labels[user_id] = f"Unknown user ({user_id})"
            continue
        name = user.global_name or user.name
        _remember("user", user_id, name)
        labels[user_id] = f"{name} (left)"
    return labels


async def resolve_channels(bot, guild, ids) -> dict[int, str]:
    """Label each channel id, including archived threads and deleted channels."""
    ids = [i for i in dict.fromkeys(ids) if isinstance(i, int)]
    labels: dict[int, str] = {}
    unresolved = []

    for channel_id in ids:
        channel = guild.get_channel_or_thread(channel_id) or bot.get_channel(channel_id)
        if channel is not None:
            name = f"#{channel.name}"
            labels[channel_id] = name
            _remember("channel", channel_id, name)
            continue
        unresolved.append(channel_id)

    stored = _stored("channel", unresolved)
    for channel_id in list(unresolved):
        if channel_id in stored:
            labels[channel_id] = stored[channel_id]
            unresolved.remove(channel_id)

    for channel_id in unresolved:
        # Catches archived threads, which aren't in guild.threads until re-opened.
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.HTTPException, discord.InvalidData):
            labels[channel_id] = f"Deleted channel ({channel_id})"
            continue
        name = f"#{channel.name}"
        _remember("channel", channel_id, name)
        labels[channel_id] = name
    return labels
