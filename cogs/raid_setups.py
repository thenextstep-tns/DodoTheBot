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


def _markers_hint(data: RaidData) -> str | None:
    """A one-line '/markers' nudge, shown with /setups only when the raid has markers."""
    return lang.RAID_MARKERS_HINT if (data.markers or "").strip() else None


def _chunk_code(text: str, limit: int = 1900) -> list[str]:
    """Split ``text`` into code-block messages that fit under Discord's 2000-char cap."""
    return [f"```\n{text[i:i + limit]}\n```" for i in range(0, len(text), limit)]


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


# --------------------------------------------------------------------------- #
#  Group ("fight") view
# --------------------------------------------------------------------------- #
_TANK_ICON, _HEAL_ICON, _DPS_ICON, _OTHER_ICON = "🛡️", "⚕️", "⚔️", "▫️"
_FIGHTS_PER_PAGE = 8          # ALL view: fights per page
_EMBED_CHAR_BUDGET = 5900     # hard cap under Discord's 6000-char embed limit
_FIELD_LIMIT = 1024           # Discord's per-field value limit


def _role_icon(role: str) -> str:
    """Role → icon: tanks get a shield, healers a staff, DDs crossed swords."""
    r = (role or "").strip().upper()
    if r in ("MT", "OT") or "TANK" in r:
        return _TANK_ICON
    if r.startswith("H") or "HEAL" in r:
        return _HEAL_ICON
    if r.startswith("D") or "DPS" in r:
        return _DPS_ICON
    return _OTHER_ICON


def _fmt_gear(gear: dict[str, str], columns: list[str]) -> str:
    return " · ".join(v for v in (gear.get(c, "") for c in columns) if v) or lang.RAID_SETUPS_EMPTY_STAGE


def _group_line(entry: dict[str, str], gear: dict[str, str], columns: list[str]) -> str:
    """One player's line in a fight's group view: role icon, bold name, normal gear."""
    icon = _role_icon(entry.get("Role", ""))
    name = entry.get("Name", "")
    gear_text = _fmt_gear(gear, columns)
    return f"{icon} **{name}** — {gear_text}"


def _fight_lines(data: RaidData, stage_name: str) -> list[str]:
    return [_group_line(entry, gear, data.columns) for entry, gear, _bold in data.group(stage_name)]


def _stage_starred(data: RaidData, stage_name: str) -> bool:
    """A fight is 'starred' (a boss) when any of its rows are ★-checked."""
    return any(bold for _entry, _gear, bold in data.group(stage_name))


def _fight_title(data: RaidData, stage_name: str) -> str:
    """The fight's display name, with a ⭐ next to it when it's a starred fight."""
    return f"⭐ {stage_name}" if _stage_starred(data, stage_name) else stage_name


def _render_fight(data: RaidData, raid_name: str, stage_name: str) -> discord.Embed:
    """A single fight, whole group, organised in roster order (tanks → heals → DDs)."""
    description = "\n".join(_fight_lines(data, stage_name)) or lang.RAID_SETUPS_EMPTY_FIGHT
    if len(description) > 4096:
        description = description[:4093] + "…"
    embed = discord.Embed(title=_fight_title(data, stage_name), description=description, color=_ACCENT)
    embed.set_footer(text=raid_name)
    return embed


def _build_all_pages(data: RaidData, raid_name: str) -> list[discord.Embed]:
    """One field per fight, chunked into pages (≤8 fights and within the char budget)."""
    fields = []
    for stage_name in data.stage_names:
        value = "\n".join(_fight_lines(data, stage_name)) or lang.RAID_SETUPS_EMPTY_FIGHT
        if len(value) > _FIELD_LIMIT:
            value = value[: _FIELD_LIMIT - 1] + "…"
        fields.append((_fight_title(data, stage_name), value))

    pages: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_chars = 0
    for name, value in fields:
        size = len(name) + len(value)
        if current and (len(current) >= _FIGHTS_PER_PAGE or current_chars + size > _EMBED_CHAR_BUDGET):
            pages.append(current)
            current, current_chars = [], 0
        current.append((name, value))
        current_chars += size
    if current:
        pages.append(current)

    embeds = []
    for index, page in enumerate(pages, start=1):
        embed = discord.Embed(title=lang.RAID_SETUPS_ALL_TITLE.format(raid=raid_name), color=_ACCENT)
        for name, value in page:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=f"{raid_name} · page {index}/{len(pages)}")
        embeds.append(embed)
    return embeds or [discord.Embed(title=lang.RAID_SETUPS_ALL_TITLE.format(raid=raid_name),
                                    description=lang.RAID_SETUPS_EMPTY_FIGHT, color=_ACCENT)]


class _FightPager(discord.ui.View):
    """Button pager for the ALL view; only the invoker can flip pages."""

    def __init__(self, embeds: list[discord.Embed], author_id: int):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.author_id = author_id
        self.index = 0
        self._sync()

    def _sync(self) -> None:
        for child in self.children:
            if child.custom_id == "raid_prev":
                child.disabled = self.index == 0
            elif child.custom_id == "raid_next":
                child.disabled = self.index >= len(self.embeds) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu isn't yours — run `/setups` yourself.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.secondary, custom_id="raid_prev")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = max(0, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.secondary, custom_id="raid_next")
    async def nxt(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = min(len(self.embeds) - 1, self.index + 1)
        await self._show(interaction)


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
    @app_commands.describe(
        fight="Show the whole group for one fight, or ALL fights.",
        player="Raid managers only: look up another player by name.",
    )
    async def setups(self, context: Context, fight: str = None, *, player: str = None) -> None:
        """Your own setups (by Discord tag), a whole fight's group, or a named player (managers)."""
        raid = self._channel_raid(context)
        if not raid:
            await context.send(lang.RAID_SETUPS_NONE, ephemeral=True)
            return
        await context.defer()
        data = await self._fresh_data(raid)   # re-read the sheet live each time
        hint = _markers_hint(data)            # nudge toward /markers when the raid has them

        # Group ("fight") view — the whole team for one fight, or every fight.
        if fight:
            if fight.strip().lower() == "all":
                pages = _build_all_pages(data, raid["name"])
                view = _FightPager(pages, context.author.id) if len(pages) > 1 else None
                await context.send(content=hint, embed=pages[0], view=view)
            else:
                stage = data.stage(fight)
                if stage is None:
                    fights = ", ".join(data.stage_names) or "—"
                    await context.send(lang.RAID_SETUPS_UNKNOWN_FIGHT.format(fight=fight, fights=fights), ephemeral=True)
                    return
                await context.send(content=hint, embed=_render_fight(data, raid["name"], stage.name))
            await self._send_roster_link(context, raid)
            return

        # Per-player view.
        if player:
            if not _can_manage(context.author):
                await context.send(lang.RAID_SETUPS_LOOKUP_DENIED, ephemeral=True)
                return
            if player.strip().lower() == "all":
                pages = [_render_lookup(data, raid["name"], name) for name in data.player_names]
                if not pages:
                    await context.send(lang.RAID_SETUPS_EMPTY_FIGHT, ephemeral=True)
                    return
                for index, page in enumerate(pages, start=1):
                    page.set_footer(text=f"{raid['name']} · player {index}/{len(pages)}")
                view = _FightPager(pages, context.author.id) if len(pages) > 1 else None
                await context.send(content=hint, embed=pages[0], view=view)
                await self._send_roster_link(context, raid)
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

        await context.send(content=hint, embed=_render_lookup(data, raid["name"], target))
        await self._send_roster_link(context, raid)

    async def _send_roster_link(self, context: Context, raid: dict) -> None:
        """Privately (ephemerally) DM-style send raid managers the full sheet link."""
        if context.interaction is None or not _can_manage(context.author):
            return
        url = raid.get("sheet_url")
        if url:
            await context.interaction.followup.send(lang.RAID_ROSTER_LINK.format(url=url), ephemeral=True)

    @commands.hybrid_command(name="markers", description="Get this channel's raid marker string.")
    @commands.guild_only()
    async def markers(self, context: Context) -> None:
        """Dump the raid's marker string (Instructions!A32) in copy-ready code blocks."""
        raid = self._channel_raid(context)
        if not raid:
            await context.send(lang.RAID_SETUPS_NONE, ephemeral=True)
            return
        await context.defer(ephemeral=True)
        data = await self._fresh_data(raid)
        text = (data.markers or "").strip()
        if not text:
            await context.send(lang.RAID_MARKERS_NONE, ephemeral=True)
            return
        for chunk in _chunk_code(text):
            await context.send(chunk, ephemeral=True)

    @setups.autocomplete("fight")
    async def _setups_fight_autocomplete(self, interaction: discord.Interaction, current: str):
        """Suggest 'ALL' plus this raid's fight names."""
        raid = self.raids.find_one(
            {"guild_id": interaction.guild_id, "channel_id": interaction.channel_id, "active": True}
        )
        if not raid:
            return []
        names = ["ALL"] + [s.get("name", "") for s in raid.get("stages", []) if s.get("name")]
        current = current.lower()
        return [app_commands.Choice(name=n, value=n) for n in names if current in n.lower()][:25]

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
        names = ["All"] + [row.get("Name", "") for row in raid.get("roster", []) if row.get("Name")]
        return [app_commands.Choice(name=n, value=n) for n in names if current in n.lower()][:25]


async def setup(bot):
    await bot.add_cog(RaidSetups(bot))
