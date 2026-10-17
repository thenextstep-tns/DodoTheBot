"""
A random thing a member once said, for the card of their traveller on the
roads: from the archived messages in the server's public channels (the quote
game's pool, ``config_py.messages``), with the quote game's own filters - no
commands, no links-only or emoji-only lines, nothing too short to mean
anything.

``GET .../dodoland/quote?user=<id>`` (and the member's reader): ``{quote}``,
empty when they never said anything quotable in public.
"""

from __future__ import annotations

import asyncio

from aiohttp import web


def random_quote(guild_id: int, author: str) -> str:
    """One meaningful public message by ``author``, or "". Blocking."""
    import config_py
    from cogs import quote as quote_cog

    if not str(author).isdigit():
        return ""
    public = list(getattr(config_py, "public_channels", []) or [])
    channels = public + [str(c) for c in public]
    docs = config_py.messages.aggregate([
        {"$match": {"author": {"$in": [str(author), int(author)]}, "channel": {"$in": channels}}},
        {"$sample": {"size": 40}},
    ])
    for doc in docs:
        text = str(doc.get("message") or "").strip()
        if not text or text.lower().startswith(("dodo", "!", "/", ".", "?", "$")):
            continue
        core = quote_cog._EMOJI_RE.sub("", quote_cog._CUSTOM_EMOJI_RE.sub(
            "", quote_cog._URL_RE.sub("", quote_cog._MENTION_RE.sub("", text))))
        if len(core.split()) >= quote_cog._MIN_WORDS and sum(c.isalpha() for c in core) >= quote_cog._MIN_ALPHA:
            return text[:280]
    return ""


async def quote_layer(request: web.Request):
    """``GET .../dodoland/quote?user=<id>``: something they once said."""
    guild = request["guild"]
    text = await asyncio.get_running_loop().run_in_executor(
        None, random_quote, guild.id, request.query.get("user") or "")
    return web.json_response({"ok": True, "quote": text})
