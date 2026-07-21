"""
Message & embed helpers.

Collects the little patterns that were duplicated across cogs: building the
standard coloured embeds, sending a self-deleting message, mentioning a user,
and prompting for a reaction choice.
"""

import asyncio
from typing import Iterable, Optional, Union

import discord

# Brand palette (previously scattered as config_py.success/error/… literals).
SUCCESS = 0x2ECC71
ERROR = 0xE74C3C
WARNING = 0xF1C40F
INFO = 0x3498DB
ACCENT = 0x9C84EF


def embed(description: str = None, *, title: str = None, color: int = INFO, **kwargs) -> discord.Embed:
    """Build a ``discord.Embed`` with our default colour. Extra kwargs pass through."""
    return discord.Embed(title=title, description=description, color=color, **kwargs)


def success(description: str = None, *, title: str = None) -> discord.Embed:
    """A green 'success' embed."""
    return embed(description, title=title, color=SUCCESS)


def error(description: str = None, *, title: str = "Error!") -> discord.Embed:
    """A red 'error' embed."""
    return embed(description, title=title, color=ERROR)


def warning(description: str = None, *, title: str = None) -> discord.Embed:
    """A yellow 'warning' embed."""
    return embed(description, title=title, color=WARNING)


def mention(user: Union[discord.abc.User, int]) -> str:
    """Return a mention string for a user object or a raw user ID."""
    return user.mention if isinstance(user, discord.abc.User) else f"<@{user}>"


async def send_temp(channel: discord.abc.Messageable, content: str, *, delay: float = 5.0) -> None:
    """Send a message and delete it after ``delay`` seconds."""
    message = await channel.send(content)
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except discord.HTTPException:
        pass


class _ValueSelect(discord.ui.Select):
    """A single-choice dropdown that records the picked value and stops its view."""

    def __init__(self, placeholder: str, options: list[discord.SelectOption]):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.value: Optional[str] = None

    async def callback(self, interaction: discord.Interaction) -> None:
        self.value = self.values[0]
        await interaction.response.defer()
        self.view.stop()


async def prompt_select(
    destination: discord.abc.Messageable,
    content: str,
    options: Iterable,
    *,
    placeholder: str = "Select an option",
    timeout: float = 180.0,
) -> Optional[str]:
    """Show a single-select dropdown and return the chosen value (or ``None`` on timeout).

    ``options`` may be ``discord.SelectOption`` objects or ``(label, value)`` pairs.
    """
    select_options = [
        opt if isinstance(opt, discord.SelectOption) else discord.SelectOption(label=opt[0], value=opt[1])
        for opt in options
    ]
    select = _ValueSelect(placeholder, select_options)
    view = discord.ui.View(timeout=timeout)
    view.add_item(select)
    await destination.send(content, view=view)
    await view.wait()
    return select.value


async def wait_for_reaction(
    bot,
    message: discord.Message,
    emojis: Iterable[str],
    *,
    member: Optional[discord.abc.User] = None,
    timeout: float = 60.0,
    add: bool = True,
):
    """Add ``emojis`` to ``message`` and wait for one to be clicked.

    Returns ``(emoji_str, user)`` on a valid reaction, or ``(None, None)`` on
    timeout. If ``member`` is given, only that member's reaction counts; otherwise
    any non-bot user counts.
    """
    emojis = list(emojis)
    if add:
        for emoji in emojis:
            await message.add_reaction(emoji)

    def check(reaction, user):
        if user.bot:
            return False
        if member is not None and user.id != member.id:
            return False
        return str(reaction.emoji) in emojis

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=timeout, check=check)
        return str(reaction.emoji), user
    except asyncio.TimeoutError:
        return None, None
