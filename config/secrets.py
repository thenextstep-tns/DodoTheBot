"""
Secrets, loaded from the git-ignored ``config.json`` so no tokens or connection
strings live in tracked source.
"""

import json

with open("config.json", encoding="utf-8") as _file:
    _config = json.load(_file)

MONGO_URI = _config["mongo_uri"]
DATABASE_NAME = _config.get("database_name", "DummiesBotDB")
OPENAI_API = _config.get("openai_api_key", "")
PROXY_API = _config.get("proxy_api_key", "")
tenor_api = _config.get("tenor_api_key", "")

# Control-panel web server + Discord OAuth2 (see cogs/control_panel.py & web/).
# Absent/disabled by default so the bot runs fine without a panel configured.
WEB = _config.get("web", {})
WEB_ENABLED = bool(WEB.get("enabled", False))
WEB_HOST = WEB.get("host", "127.0.0.1")
WEB_PORT = int(WEB.get("port", 8080))
WEB_PUBLIC_URL = WEB.get("public_url", f"http://{WEB_HOST}:{WEB_PORT}").rstrip("/")
WEB_CLIENT_ID = str(WEB.get("client_id") or _config.get("application_id", ""))
WEB_CLIENT_SECRET = WEB.get("client_secret", "")
WEB_SESSION_SECRET = WEB.get("session_secret", "")
