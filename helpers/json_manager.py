"""
Small helpers for reading and writing the file-based blacklist (``blacklist.json``).
"""

import json

BLACKLIST_FILE = "blacklist.json"


def add_user_to_blacklist(user_id: int) -> None:
    """Add a user ID to the blacklist."""
    with open(BLACKLIST_FILE, encoding="utf-8") as file:
        data = json.load(file)
    if user_id not in data["ids"]:
        data["ids"].append(user_id)
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def remove_user_from_blacklist(user_id: int) -> None:
    """Remove a user ID from the blacklist (no-op if not present)."""
    with open(BLACKLIST_FILE, encoding="utf-8") as file:
        data = json.load(file)
    if user_id in data["ids"]:
        data["ids"].remove(user_id)
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
