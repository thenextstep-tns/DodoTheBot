"""
Minimal inspirobot client.

Reconstructed to satisfy the bot's usage: `inspirobot.generate()` returns an
object exposing `.url` (a generated image link), and the module-level `HTTPS`
flag is settable. Replace with your original module if it differs.
"""

import requests

# Settable module-level flag (the cogs toggle this; kept for compatibility).
HTTPS = True

_API = "https://inspirobot.me/api?generate=true"


class Generated:
    """Result of a generation call. Exposes `.url` (and `.text` alias)."""

    def __init__(self, url: str):
        self.url = url
        self.text = url

    def __str__(self) -> str:
        return self.url


def generate() -> "Generated":
    """Ask InspiroBot for a fresh image and return it wrapped with a `.url`."""
    resp = requests.get(_API, timeout=15)
    resp.raise_for_status()
    return Generated(resp.text.strip())
