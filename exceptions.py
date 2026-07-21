"""
Custom exception types for DodoTheBot.

Raised by command checks (see ``helpers/checks.py``) and surfaced to users by
the centralized error handlers in ``bot.py``.
"""


class DodoError(Exception):
    """Base class for every custom error raised by the bot."""

    def __init__(self, message: str = "An error occurred."):
        self.message = message
        super().__init__(self.message)


class UserBlacklisted(DodoError):
    """Raised when a blacklisted user tries to run a command."""

    def __init__(self, message: str = "You are blacklisted from using this bot."):
        super().__init__(message)


class UserNotOwner(DodoError):
    """Raised when a non-owner tries to run an owner-only command."""

    def __init__(self, message: str = "You are not an owner of this bot."):
        super().__init__(message)


class GuildNotConfigured(DodoError):
    """Raised when a command needs per-guild config that hasn't been set up yet."""

    def __init__(self, message: str = "This server has not been configured yet."):
        super().__init__(message)
