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
