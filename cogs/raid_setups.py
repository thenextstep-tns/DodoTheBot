"""
Raid-setups cog — import a raid's gear plan from a shared Google Sheet and let
players look up their per-stage setups in Discord.

* ``/create_raid name:<text> sheet:<google-sheets-link>`` — a raid manager imports
  a sheet (see ``helpers.sheets`` for the template) and binds it to the current
  channel. Restricted to the roles in ``RAID_MANAGER_ROLES`` (server admins may
  always manage).
* ``/setups`` — run it in a raid channel; you're matched to the roster by your
  Discord tag and shown your own gear across every stage. Raid managers may pass
  ``player:<name>`` to look someone else up.

Both commands are hybrid. User-facing text lives in ``lang``.
"""

import asyncio
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

import config_py
import lang
from helpers import messages
from helpers.sheets import RaidData, SheetError, load_raid

# Roles allowed to create/refresh raids and look up other players. Edit per server.
RAID_MANAGER_ROLES = {
    "Fairy Godmother": 783670458398277652,
    "Moderator": 833693874219384833,
}

_ACCENT = 0x9C84EF
# /setups re-reads the sheet live so edits show up without re-importing. This
# short cache only coalesces bursts (e.g. a whole team running it at once) so we
# don't refetch the same sheet many times a second; edits appear within it.
_REFRESH_TTL = 10.0
_live_cache: dict[str, tuple[float, RaidData]] = {}


def _can_manage(member: discord.Member) -> bool:
    """Whether a member may manage raids (a manager role, or server admin)."""
    if getattr(member.guild_permissions, "administrator", False):
        return True
    member_role_ids = {role.id for role in getattr(member, "roles", [])}
    return any(role_id in member_role_ids for role_id in RAID_MANAGER_ROLES.values())


def _discord_candidates(member: discord.Member) -> set[str]:
    """The caller's identities to match against a roster Discord tag (all lower-cased)."""
    values = {str(member.id), (member.name or "").lower(), (getattr(member, "global_name", "") or "").lower()}
    return {v for v in values if v}


def _render_lookup(data: RaidData, raid_name: str, player: str) -> discord.Embed:
    """Build a tidy per-stage gear embed for one player; ★-checked pulls are bold."""
    entry = data.roster_entry(player) or {"Name": player, "Role": "", "Class": "", "Slayer": ""}

    identity = " · ".join(bit for bit in (entry.get("Role", ""), entry.get("Class", "")) if bit)
    if entry.get("Slayer"):
        identity = f"{identity} · Slayer: {entry['Slayer']}" if identity else f"Slayer: {entry['Slayer']}"

    # Header: identity, then the roster's Notes for this player (shown once, on top).
    header_lines = [identity] if identity else []
    if entry.get("Notes"):
        header_lines.append(f"📝 {entry['Notes']}")

    lines = []
    for stage, values, bold in data.lookup(player):
        gear = " · ".join(v for v in (values.get(c, "") for c in data.columns) if v) or lang.RAID_SETUPS_EMPTY_STAGE
        # Monospace "pill" for the stage; the whole gear line goes bold when ticked.
        lines.append(f"`{stage}`  ⭐ **{gear}**" if bold else f"`{stage}`  {gear}")

    description = ("\n".join(header_lines) + "\n\n" if header_lines else "") + "\n".join(lines)
    if len(description) > 4096:
        description = description[:4093] + "…"

    embed = discord.Embed(title=entry.get("Name", player), description=description, color=_ACCENT)
    embed.set_footer(text=raid_name)
    return embed


class RaidSetups(commands.Cog, name="raid_setups"):
    """Import raid gear plans from Google Sheets and look them up in Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.raids = config_py.raid_setups

    def _channel_raid(self, context: Context) -> dict | None:
        return self.raids.find_one(
            {"guild_id": context.guild.id, "channel_id": context.channel.id, "active": True}
        )

    async def _fresh_data(self, raid: dict) -> RaidData:
        """Return the raid's current data, re-read live from the sheet.

        Uses a short per-sheet cache to coalesce bursts. On a successful fetch the
        stored snapshot is refreshed too; if the sheet is unreachable we fall back
        to the last stored snapshot so ``/setups`` still works offline.
        """
        sheet_id = raid.get("sheet_id", "")
        cached = _live_cache.get(sheet_id)
        if cached and time.monotonic() - cached[0] < _REFRESH_TTL:
            return cached[1]
        try:
            _, data = await asyncio.to_thread(load_raid, raid.get("sheet_url") or sheet_id)
        except SheetError as error:
            self.bot.logger.warning(f"Live setups refresh failed for raid '{raid.get('name')}': {error}")
            return RaidData.from_mongo(raid)

        _live_cache[sheet_id] = (time.monotonic(), data)
        self.raids.update_one(
            {"_id": raid["_id"]},
            {"$set": {**data.to_mongo(), "updated_at": datetime.now(timezone.utc)}},
        )
        return data

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
        _live_cache.pop(sheet_id, None)   # force the next /setups to refetch

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

    @commands.hybrid_command(name="setups", description="See your gear setups for this channel's raid.")
    @commands.guild_only()
    @app_commands.describe(player="Raid managers only: look up another player by name.")
    async def setups(self, context: Context, *, player: str = None) -> None:
        """Show your own setups (matched by Discord tag), or a named player's (managers)."""
        raid = self._channel_raid(context)
        if not raid:
            await context.send(lang.RAID_SETUPS_NONE, ephemeral=True)
            return
        await context.defer()
        data = await self._fresh_data(raid)   # re-read the sheet live each time

        if player:
            if not _can_manage(context.author):
                await context.send(lang.RAID_SETUPS_LOOKUP_DENIED, ephemeral=True)
                return
            entry = data.roster_entry(player)
            if not entry:
                await context.send(lang.RAID_SETUPS_NOT_FOUND.format(player=player), ephemeral=True)
                return
            target = entry["Name"]
        else:
            entry = data.match_discord(_discord_candidates(context.author))
            if not entry:
                await context.send(lang.RAID_SETUPS_NOT_ON_ROSTER.format(tag=context.author.name), ephemeral=True)
                return
            target = entry["Name"]

        await context.send(embed=_render_lookup(data, raid["name"], target))

    @setups.autocomplete("player")
    async def _setups_player_autocomplete(self, interaction: discord.Interaction, current: str):
        """Suggest roster names (managers only) for the optional player argument."""
        if not _can_manage(interaction.user):
            return []
        raid = self.raids.find_one(
            {"guild_id": interaction.guild_id, "channel_id": interaction.channel_id, "active": True}
        )
        if not raid:
            return []
        current = current.lower()
        names = [row.get("Name", "") for row in raid.get("roster", []) if row.get("Name")]
        return [app_commands.Choice(name=n, value=n) for n in names if current in n.lower()][:25]


async def setup(bot):
    await bot.add_cog(RaidSetups(bot))
