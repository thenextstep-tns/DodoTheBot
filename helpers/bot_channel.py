"""
Posting to a server's bot channel: the "Bot channel" of its settings
(guild config ``DODO_CHANNEL``, "Main channel for bot chatter").

One helper for anything that wants to say something there (a horse caught in
DodoLand, ...): :func:`post`. People are named, never pinged, unless asked.
"""

from __future__ import annotations

from typing import Optional


async def post(bot, guild, text: str, *, ping: bool = False) -> Optional[object]:
    """Send ``text`` to ``guild``'s bot channel. The sent message, or None (no
    channel set, or it could not be sent) - logged either way, never raised."""
    import discord

    log = getattr(bot, "logger", None)
    try:
        channel_id = int(bot.guild_config.get(guild.id, "DODO_CHANNEL") or 0)
    except (AttributeError, TypeError, ValueError):
        channel_id = 0
    channel = guild.get_channel(channel_id) or (bot.get_channel(channel_id) if channel_id else None)
    if channel is None and channel_id:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:  # noqa: BLE001 - deleted, or no access
            channel = None
    if channel is None:
        if log:
            log.warning(f"Bot channel post skipped: no bot channel (DODO_CHANNEL={channel_id}) on {guild.id}.")
        return None
    try:
        return await channel.send(str(text)[:2000],
                                  allowed_mentions=None if ping else discord.AllowedMentions.none())
    except Exception as error:  # noqa: BLE001 - a missing permission never breaks the caller
        if log:
            log.warning(f"Bot channel post to {channel_id} failed: {error}")
        return None
