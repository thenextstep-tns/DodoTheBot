"""
Raid-setups cog — import a raid's gear plan from a shared Google Sheet and let
players look up their per-stage setups in Discord.

* ``/create_raid name:<text> sheet:<google-sheets-link>`` — a raid manager imports
  a sheet (see ``helpers.sheets`` for the template) and binds it to the current
  channel. Restricted to the roles in ``RAID_MANAGER_ROLES`` (server admins may
  always manage).
* ``/setups`` — anyone runs it in a raid channel; the bot finds that channel's
  raid, shows a player dropdown, and renders the picked player's gear across
  every stage (the "Lookup" view).

Both commands are hybrid. User-facing text lives in ``lang``.
"""

from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import messages
from helpers.sheets import RaidData, SheetError, load_raid

# Roles allowed to create/refresh raids. Kept here so it's easy to edit per server.
RAID_MANAGER_ROLES = {
    "Fairy Godmother": 783670458398277652,
    "Moderator": 833693874219384833,
}

_ACCENT = 0x9C84EF
_MAX_CELL = 18          # truncate long gear cells so the table stays readable
_SELECT_LIMIT = 25      # Discord's hard cap on select options


def _can_manage(member: discord.Member) -> bool:
    """Whether a member may manage raids (a manager role, or server admin)."""
    if getattr(member.guild_permissions, "administrator", False):
        return True
    member_role_ids = {role.id for role in getattr(member, "roles", [])}
    return any(role_id in member_role_ids for role_id in RAID_MANAGER_ROLES.values())


def _truncate(text: str, width: int = _MAX_CELL) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _render_lookup(data: RaidData, raid_name: str, player: str) -> discord.Embed:
    """Build the per-player, per-stage gear table as a monospaced embed."""
    entry = data.roster_entry(player) or {"Name": player, "Role": "", "Class": "", "Slayer": ""}
    rows = data.lookup(player)

    # Only show gear columns this player actually uses somewhere, to keep it tight.
    used_cols = [c for c in data.columns if any(vals.get(c) for _stage, vals in rows)]
    headers = ["Stage", *used_cols]

    table = [[stage, *[_truncate(vals.get(c, "")) for c in used_cols]] for stage, vals in rows]
    widths = [len(h) for h in headers]
    for row in table:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    for stage, vals in rows:
        display = [stage] + [(_truncate(vals.get(c, "")) or lang.RAID_SETUPS_EMPTY_STAGE) for c in used_cols]
        lines.append(fmt(display))

    header = lang.RAID_SETUPS_HEADER.format(
        name=entry.get("Name", player), role=entry.get("Role", ""), cls=entry.get("Class", "")
    )
    if entry.get("Slayer"):
        header += lang.RAID_SETUPS_SLAYER.format(slayer=entry["Slayer"])

    embed = discord.Embed(
        title=lang.RAID_SETUPS_TITLE.format(player=player, raid=raid_name),
        description=f"{header}\n```\n" + "\n".join(lines) + "\n```",
        color=_ACCENT,
    )
    return embed


class _InvokerView(discord.ui.View):
    """A view only the person who ran the command may interact with."""

    def __init__(self, author_id: int, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu isn't for you — run `/setups` yourself.", ephemeral=True)
            return False
        return True


class _PlayerSelect(discord.ui.Select):
    """Dropdown of roster players; on pick, edit the message to show their setups."""

    def __init__(self, raid_doc: dict):
        self.raid_doc = raid_doc
        self.data = RaidData.from_mongo(raid_doc)
        options = [
            discord.SelectOption(label=name[:100]) for name in self.data.player_names[:_SELECT_LIMIT]
        ]
        super().__init__(placeholder=lang.RAID_SETUPS_PLAYER_PLACEHOLDER, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        player = self.values[0]
        embed = _render_lookup(self.data, self.raid_doc["name"], player)
        await interaction.response.edit_message(content=None, embed=embed, view=self.view)


class _RaidSelect(discord.ui.Select):
    """Fallback dropdown when a channel isn't bound to exactly one raid (managers only)."""

    def __init__(self, raids: list[dict]):
        self.raids = {str(r["_id"]): r for r in raids}
        options = [
            discord.SelectOption(label=r["name"][:100], value=str(r["_id"]))
            for r in raids[:_SELECT_LIMIT]
        ]
        super().__init__(placeholder=lang.RAID_SETUPS_RAID_PLACEHOLDER, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        raid = self.raids[self.values[0]]
        view = _InvokerView(interaction.user.id)
        view.add_item(_PlayerSelect(raid))
        await interaction.response.edit_message(content=lang.RAID_SETUPS_PICK_PLAYER, view=view)


def _discord_candidates(member: discord.Member) -> set[str]:
    """The caller's identities to match against a roster Discord tag (all lower-cased)."""
    values = {str(member.id), (member.name or "").lower(), (getattr(member, "global_name", "") or "").lower()}
    return {v for v in values if v}


class RaidSetups(commands.Cog, name="raid_setups"):
    """Import raid gear plans from Google Sheets and look them up in Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.raids = config_py.raid_setups

    @commands.hybrid_command(name="create_raid", description="Import a raid's gear plan from a Google Sheet (managers only).")
    @commands.guild_only()
    async def create_raid(self, context: Context, name: str, *, sheet: str) -> None:
        """Import a shared Google Sheet and bind it to this channel."""
        if not _can_manage(context.author):
            roles = " or ".join(RAID_MANAGER_ROLES)
            await context.send(lang.RAID_NO_PERMISSION.format(roles=roles), ephemeral=True)
            return

        await context.defer()
        try:
            sheet_id, data = load_raid(sheet)
        except SheetError as error:
            await context.send(embed=messages.error(lang.RAID_IMPORT_FAILED.format(reason=error)), ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        doc = {
            "guild_id": context.guild.id,
            "channel_id": context.channel.id,
            "name": name,
            "sheet_id": sheet_id,
            "sheet_url": sheet,
            "active": True,
            "created_by": context.author.id,
            "updated_at": now,
            **data.to_mongo(),
        }
        # One active raid per channel: replace any existing binding for this channel.
        self.raids.update_one(
            {"guild_id": context.guild.id, "channel_id": context.channel.id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        embed = messages.success(
            lang.RAID_CREATED_BODY.format(
                channel=context.channel.mention, players=len(data.roster), stages=len(data.stages)
            ),
            title=lang.RAID_CREATED_TITLE.format(name=name),
        )
        embed.add_field(name=lang.RAID_CREATED_STAGES, value=", ".join(s.name for s in data.stages), inline=False)
        if data.warnings:
            preview = "\n".join(f"• {w}" for w in data.warnings[:8])
            embed.add_field(name=lang.RAID_CREATED_WARNINGS, value=preview[:1024], inline=False)
        await context.send(embed=embed)

    @commands.hybrid_command(name="setups", description="Look up your gear setups for this channel's raid.")
    @commands.guild_only()
    async def setups(self, context: Context) -> None:
        """Show setups for the raid bound to this channel.

        A raid manager gets a dropdown to look up anyone. Everyone else is matched
        to the roster by their Discord tag and shown their own setups; if their tag
        isn't on the roster, the command is refused.
        """
        ephemeral = context.interaction is not None
        is_manager = _can_manage(context.author)
        channel_raid = self.raids.find_one(
            {"guild_id": context.guild.id, "channel_id": context.channel.id, "active": True}
        )

        if channel_raid:
            if is_manager:
                view = _InvokerView(context.author.id)
                view.add_item(_PlayerSelect(channel_raid))
                await context.send(content=lang.RAID_SETUPS_PICK_PLAYER, view=view, ephemeral=ephemeral)
                return
            data = RaidData.from_mongo(channel_raid)
            matched = data.match_discord(_discord_candidates(context.author))
            if not matched:
                await context.send(
                    lang.RAID_SETUPS_NOT_ON_ROSTER.format(tag=context.author.name), ephemeral=True
                )
                return
            embed = _render_lookup(data, channel_raid["name"], matched["Name"])
            await context.send(embed=embed, ephemeral=ephemeral)
            return

        # No raid bound to this channel. Managers may browse other active raids.
        if is_manager:
            active = list(self.raids.find({"guild_id": context.guild.id, "active": True}))
            if active:
                view = _InvokerView(context.author.id)
                view.add_item(_RaidSelect(active))
                await context.send(content=lang.RAID_SETUPS_PICK_RAID, view=view, ephemeral=ephemeral)
                return
        await context.send(lang.RAID_SETUPS_NONE, ephemeral=ephemeral)


async def setup(bot):
    await bot.add_cog(RaidSetups(bot))
