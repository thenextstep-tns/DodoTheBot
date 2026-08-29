"""
Discord OAuth2 login + tamper-proof cookie sessions for the control panel.

No third-party session library: a session is a small JSON payload signed with an
HMAC over ``WEB_SESSION_SECRET`` (stdlib only). The cookie therefore can't be
forged or altered by the client, and it carries its own expiry.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import aiohttp

from config.secrets import (
    WEB_CLIENT_ID,
    WEB_CLIENT_SECRET,
    WEB_PUBLIC_URL,
    WEB_SESSION_SECRET,
)

DISCORD_API = "https://discord.com/api"
OAUTH_SCOPE = "identify"
SESSION_COOKIE = "dodo_session"
STATE_COOKIE = "dodo_oauth_state"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days


def redirect_uri() -> str:
    return f"{WEB_PUBLIC_URL}/oauth/callback"


# --------------------------------------------------------------------------- #
#  Signed tokens
# --------------------------------------------------------------------------- #
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def sign(payload: dict) -> str:
    """Return ``<base64(json)>.<hmac>`` — opaque, tamper-evident.

    A creation timestamp (``iat``) is always stamped in so that ``unsign`` can
    enforce a ``max_age`` (the caller may override ``iat`` explicitly).
    """
    payload = {"iat": int(time.time()), **payload}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(WEB_SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def unsign(token: Optional[str], *, max_age: Optional[int] = None) -> Optional[dict]:
    """Verify a token and return its payload, or ``None`` if invalid/expired."""
    if not token or "." not in token:
        return None
    body, _, mac = token.partition(".")
    expected = hmac.new(WEB_SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if max_age is not None:
        issued = payload.get("iat", 0)
        if not isinstance(issued, (int, float)) or time.time() - issued > max_age:
            return None
    return payload


def make_session(user_id: int, username: str = "") -> str:
    return sign({"uid": int(user_id), "name": username, "iat": int(time.time())})


def read_session(cookie: Optional[str]) -> Optional[dict]:
    return unsign(cookie, max_age=SESSION_MAX_AGE)


# --------------------------------------------------------------------------- #
#  OAuth2 flow
# --------------------------------------------------------------------------- #
def authorize_url(state: str) -> str:
    from urllib.parse import urlencode

    query = urlencode(
        {
            "client_id": WEB_CLIENT_ID,
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "state": state,
            "prompt": "none",
        }
    )
    return f"{DISCORD_API}/oauth2/authorize?{query}"


async def exchange_code(code: str) -> Optional[dict]:
    """Exchange an auth code for a token; then fetch and return the Discord user."""
    data = {
        "client_id": WEB_CLIENT_ID,
        "client_secret": WEB_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers) as resp:
            if resp.status != 200:
                return None
            token = await resp.json()
        access = token.get("access_token")
        if not access:
            return None
        async with session.get(
            f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access}"}
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
