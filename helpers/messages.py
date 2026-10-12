"""
Message & embed helpers.

Collects the little patterns that were duplicated across cogs: building the
standard coloured embeds, sending a self-deleting message, mentioning a user,
and prompting for a reaction choice.
"""

import asyncio
from typing import Iterable, Optional, Sequence, Union

import discord

# Brand palette (previously scattered as config_py.success/error/… literals).
SUCCESS = 0x2ECC71
ERROR = 0xE74C3C
WARNING = 0xF1C40F
INFO = 0x3498DB
ACCENT = 0x9C84EF

# Discord's hard limit on an embed description.
EMBED_DESCRIPTION_LIMIT = 4096
VIEW_TIMEOUT = 180.0


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


class _SafeValues(dict):
    """Formatting map that leaves unknown placeholders untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(template: str, **values) -> str:
    """Fill ``{placeholders}`` in admin-authored text.

    Anything the caller doesn't supply is left visible rather than raising, so a
    typo in a server's welcome message can't break joining.
    """
    try:
        return template.format_map(_SafeValues(values))
    except (ValueError, IndexError):
        # Unbalanced or positional braces — show the text as written.
        return template


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


# ------------------------------- pagination ---------------------------------- #
class Paginator(discord.ui.View):
    """A minimal Previous/Next button view for paging through a list of embeds."""

    def __init__(self, embeds: list[discord.Embed], *, timeout: float = VIEW_TIMEOUT):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.index = 0
        self.prev_button.disabled = True
        self.next_button.disabled = len(embeds) <= 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self.next_button.disabled = False
        self.prev_button.disabled = self.index == 0
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self.prev_button.disabled = False
        self.next_button.disabled = self.index == len(self.embeds) - 1
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)


def chunk_blocks(
    blocks: Iterable[str], *, separator: str = "\n\n", limit: int = EMBED_DESCRIPTION_LIMIT
) -> list[str]:
    """Join ``blocks`` into as few strings as possible, none longer than ``limit``.

    A block is never split, so a single oversized block still gets its own page.
    """
    pages: list[str] = []
    current: list[str] = []
    length = 0
    for block in blocks:
        extra = len(separator) if current else 0
        if current and length + extra + len(block) > limit:
            pages.append(separator.join(current))
            current, length = [block], len(block)
        else:
            current.append(block)
            length += extra + len(block)
    if current:
        pages.append(separator.join(current))
    return pages


def paged_embeds(
    blocks: Iterable[str],
    *,
    title: str = None,
    color: int = INFO,
    separator: str = "\n\n",
    footer: str = None,
) -> list[discord.Embed]:
    """Build one embed per page of ``blocks``.

    ``footer`` may contain ``{page}`` / ``{pages}`` placeholders.
    """
    pages = chunk_blocks(blocks, separator=separator)
    embeds = []
    for index, page in enumerate(pages, start=1):
        page_embed = embed(page, title=title, color=color)
        if footer:
            page_embed.set_footer(
                text=footer.format(page=index, pages=len(pages)) if "{page" in footer else footer
            )
        embeds.append(page_embed)
    return embeds


async def send_paged(
    destination: discord.abc.Messageable, embeds: Sequence[discord.Embed]
) -> Optional[discord.Message]:
    """Send the first embed, attaching Previous/Next buttons when there is more than one."""
    if not embeds:
        return None
    view = Paginator(list(embeds)) if len(embeds) > 1 else None
    return await destination.send(embed=embeds[0], view=view)


# ------------------------------- prompting ----------------------------------- #
class _OwnedView(discord.ui.View):
    """A view only ``member`` may interact with (or anyone, when ``member`` is None)."""

    def __init__(self, member: Optional[discord.abc.User], timeout: float):
        super().__init__(timeout=timeout)
        self.member = member

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.member is None or interaction.user.id == self.member.id:
            return True
        await interaction.response.send_message("This one isn't yours to answer.", ephemeral=True)
        return False


class _ConfirmView(_OwnedView):
    """Confirm/Cancel buttons that only the requesting member may press."""

    def __init__(self, member: discord.abc.User, timeout: float):
        super().__init__(member, timeout)
        self.value: Optional[bool] = None

    async def _resolve(self, interaction: discord.Interaction, value: bool) -> None:
        self.value = value
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, False)


async def prompt_confirm(
    destination: discord.abc.Messageable,
    member: discord.abc.User,
    *,
    content: str = None,
    embed: discord.Embed = None,
    timeout: float = 60.0,
) -> bool:
    """Ask ``member`` to confirm; return ``True`` only if they press Confirm in time."""
    view = _ConfirmView(member, timeout)
    await destination.send(content=content, embed=embed, view=view)
    await view.wait()
    return view.value is True


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
    member: Optional[discord.abc.User] = None,
) -> Optional[str]:
    """Show a single-select dropdown and return the chosen value (or ``None`` on timeout).

    ``options`` may be ``discord.SelectOption`` objects or ``(label, value)`` pairs.
    Pass ``member`` to let only that member answer; otherwise anyone may.
    """
    select_options = [
        opt if isinstance(opt, discord.SelectOption) else discord.SelectOption(label=opt[0], value=opt[1])
        for opt in options
    ]
    select = _ValueSelect(placeholder, select_options)
    view = _OwnedView(member, timeout)
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
