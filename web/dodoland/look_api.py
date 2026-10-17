"""
Searching a town owner's cats and dogs, for the pets that follow their
traveller (chosen on the town card; helpers/dodoland/pets.py).

``api_my_pets`` is the member's own (never a user id from the request: the
player routes' rule); ``api_town_pets`` is the panel's, for any town's owner.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from helpers.dodoland import pets as pet_rules


async def _answer(owner, q: str) -> web.Response:
    found = await asyncio.get_running_loop().run_in_executor(None, pet_rules.search, owner, q)
    return web.json_response({"ok": True, "pets": found, "most": pet_rules.MAX_FOLLOW})


async def api_my_pets(request: web.Request):
    return await _answer(request["uid"], request.query.get("q") or "")


async def api_town_pets(request: web.Request):
    owner = request.query.get("user_id") or ""
    if not owner.isdigit():
        return web.json_response({"ok": False, "error": "Whose pets?"}, status=400)
    return await _answer(owner, request.query.get("q") or "")
