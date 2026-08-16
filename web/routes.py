"""
aiohttp routes for the control panel.

Pages are server-rendered HTML; mutations go through small JSON endpoints called
by ``static/panel.js``. Because the app runs in the bot process, handlers act on
the live bot directly (``request.app["bot"]``).

Access has two tiers. ``require_owner`` guards the bot-wide tooling (loading cogs
into the process, the shared strings editor). Everything under ``/guild/{gid}``
goes through ``require_scope``, which resolves the caller's per-guild scope from
``helpers/panel_access.py`` — so a guild admin only ever reaches servers they are
a member of, and only the parts their scope allows. The HTML hides what a scope
can't use, but the decorators are what actually enforce it.
"""

from __future__ import annotations

import datetime
import functools
import html
import io
import os
import secrets
from functools import wraps

from aiohttp import web

import discord

from config import guild_config
from config.secrets import WEB_PUBLIC_URL
from helpers import audit_log, cog_categories, events, health, names, panel_access, parameters, stats, validate
from helpers import tribes as tribe_rules
from helpers import trial_ranks, trial_image
from helpers.visibility import LEVEL_ADMIN, LEVEL_OWNER, LEVEL_VISIBLE, VALID_LEVELS
from web import auth, charts

_SECURE = WEB_PUBLIC_URL.startswith("https")
# Repeat sign-ins inside this window aren't logged again.
LOGIN_QUIET_PERIOD = 3600
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _asset_version() -> str:
    """Newest static-asset mtime, appended to CSS/JS URLs to bust stale caches.
    Recomputed each process start (we restart to deploy), so edits always show."""
    try:
        # Every static file, so a swapped icon busts the cache too — not just CSS/JS.
        return str(int(max(
            os.path.getmtime(os.path.join(_STATIC_DIR, name)) for name in os.listdir(_STATIC_DIR)
        )))
    except (OSError, ValueError):
        return "1"


_ASSET_VER = _asset_version()


# --------------------------------------------------------------------------- #
#  Session / auth plumbing
# --------------------------------------------------------------------------- #
def _session_user(request: web.Request):
    payload = auth.read_session(request.cookies.get(auth.SESSION_COOKIE))
    return payload.get("uid") if payload else None


def _set_cookie(response: web.Response, name: str, value: str, *, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, httponly=True, samesite="Lax", secure=_SECURE, path="/"
    )


def require_owner(handler):
    """Wrap a handler so only a logged-in bot owner reaches it.

    Used for the bot-wide tooling (loading cogs into the process, the shared
    strings editor) that no guild admin should reach.
    """

    @wraps(handler)
    async def wrapper(request: web.Request):
        uid = _session_user(request)
        bot = request.app["bot"]
        if uid is None:
            raise web.HTTPFound("/login")
        if not bot.visibility.is_owner(uid):
            return web.Response(status=403, text="Not authorised (bot owners only).", content_type="text/plain")
        request["uid"] = uid
        request["scope"] = panel_access.SCOPE_OWNER
        return await handler(request)

    return wrapper


async def _member_of(bot, guild, user_id, *, fetch: bool = True):
    """The user's member object in a guild, optionally fetching on a cache miss.

    Membership is the hard gate: someone who isn't in the server gets nothing
    there, no matter what grants exist. ``fetch=False`` keeps it to the local
    member cache — used when sweeping every guild at once, where a miss per
    guild would otherwise be an API call each.
    """
    member = guild.get_member(user_id)
    if member is not None or not fetch:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def resolve_scope(bot, guild, user_id, *, fetch: bool = True) -> str:
    """This user's panel scope in this guild (``owner`` short-circuits)."""
    if bot.visibility.is_owner(user_id):
        return panel_access.SCOPE_OWNER
    member = await _member_of(bot, guild, user_id, fetch=fetch)
    return bot.panel_access.scope_for_member(guild.id, member)


def require_scope(minimum: str):
    """Gate a ``/guild/{gid}`` route on the caller's scope in *that* guild.

    Every guild route and every guild API endpoint goes through this, so hiding
    a control in the HTML is never the only thing standing in the way of it.
    A user without access gets 404, not 403 — the panel doesn't confirm the
    existence of servers they have nothing to do with.
    """

    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: web.Request):
            uid = _session_user(request)
            if uid is None:
                raise web.HTTPFound("/login")
            bot = request.app["bot"]
            try:
                guild = bot.get_guild(int(request.match_info["gid"]))
            except (TypeError, ValueError):
                guild = None
            if guild is None:
                return web.Response(status=404, text="Guild not found.", content_type="text/plain")
            scope = await resolve_scope(bot, guild, uid)
            if not panel_access.at_least(scope, minimum):
                return web.Response(status=404, text="Guild not found.", content_type="text/plain")
            request["uid"] = uid
            request["scope"] = scope
            request["guild"] = guild
            return await handler(request)

        return wrapper

    return decorator


async def accessible_guilds(bot, user_id) -> list[tuple]:
    """``(guild, scope)`` for every guild this user may see, best scope first."""
    if bot.visibility.is_owner(user_id):
        return [(guild, panel_access.SCOPE_OWNER) for guild in bot.guilds]
    out = []
    for guild in bot.guilds:
        # Cache-only: the members intent keeps this authoritative, and a fetch
        # per guild would turn one login into one API call per server.
        scope = await resolve_scope(bot, guild, user_id, fetch=False)
        if panel_access.at_least(scope, panel_access.SCOPE_STATS):
            out.append((guild, scope))
    return out


# --------------------------------------------------------------------------- #
#  Inventory helpers
# --------------------------------------------------------------------------- #
def _cog_inventory(bot) -> list[dict]:
    """Every discoverable extension (file) under cogs/, with loaded state."""
    loaded = {ext.rsplit(".", 1)[-1]: ext for ext in bot.extensions}
    names = set(loaded)
    for root_dir, _dirs, files in os.walk("cogs"):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("__"):
                names.add(filename[:-3])
    return sorted(
        ({"name": n, "loaded": n in loaded, "extension": loaded.get(n, f"cogs.{n}")} for n in names),
        key=lambda c: c["name"],
    )


LEVEL_CUSTOM = "custom"


def cog_level(commands: list[dict]) -> str:
    """The level shared by every command in a cog, or ``custom`` when they differ.

    ``custom`` isn't stored anywhere — it's derived, so a cog shows it the moment
    its commands stop agreeing (including when one is changed individually).
    """
    levels = {command["level"] for command in commands}
    if not levels:
        return LEVEL_VISIBLE
    return levels.pop() if len(levels) == 1 else LEVEL_CUSTOM


def hides_owner_level(scope: str) -> bool:
    """Whether this panel scope must not be shown the owner level at all.

    A guild admin can't set the owner level, so showing them owner-only commands
    (or the cogs that hold nothing else) only advertises tooling they can neither
    use nor change. They are filtered out of the page rather than rendered locked.
    """
    return scope != panel_access.SCOPE_OWNER


def _cog_detail(bot, guild_id: int, cog_name: str, *, scope: str = panel_access.SCOPE_OWNER) -> dict:
    """Per-guild enabled state + command levels for one cog (commands may be empty
    for listener-only cogs like cheese/spam — they're still toggleable).

    ``hidden`` counts the commands withheld from ``scope``, which lets the caller
    tell "owner-only cog" apart from "genuinely command-less passive cog".
    """
    cog = bot.cogs.get(cog_name)
    commands = []
    hidden = 0
    if cog is not None:
        for command in sorted(cog.get_commands(), key=lambda c: c.name):
            stored = bot.visibility.stored_level(guild_id, command.name)
            level = stored or (LEVEL_OWNER if command.hidden else LEVEL_VISIBLE)
            if level == LEVEL_OWNER and hides_owner_level(scope):
                hidden += 1
                continue
            commands.append({"name": command.name, "description": command.description or "", "level": level})
    features = [
        {
            "key": feat["key"],
            "label": feat["label"],
            "description": feat["description"],
            "enabled": bot.visibility.feature_enabled(guild_id, feat["key"]),
        }
        for feat in cog_categories.features_for_cog(cog_name)
    ]
    return {
        "cog": cog_name,
        "enabled": bot.visibility.cog_enabled(guild_id, cog_name),
        # One level if every command agrees, otherwise "custom" (display only).
        # Derived from the commands this scope can see, so a hidden owner-only
        # command can't leak as an unexplained "custom".
        "level": cog_level(commands),
        "commands": commands,
        "hidden": hidden,
        "features": features,
        "params": bot.params.entries_for_cog(guild_id, cog_name),
    }


# --------------------------------------------------------------------------- #
#  HTML rendering
# --------------------------------------------------------------------------- #
def _guild_nav(guild, scope: str, current: str) -> str:
    """The per-guild links in the top bar. The brand is the way back to the
    dashboard, so there is no separate link for it."""
    if guild is None:
        return ""
    links = [("settings", "⚙️ Settings", panel_access.SCOPE_CONFIG),
             ("events", "⚡ Events", panel_access.SCOPE_CONFIG),
             ("trials", "🏆 Trial ranks", panel_access.SCOPE_CONFIG),
             ("stats", "📊 Stats", panel_access.SCOPE_STATS),
             ("log", "📝 Change log", panel_access.SCOPE_CONFIG),
             # Tribes is bot-owner tooling: the rule engine can hand out any role.
             ("tribes", "🏅 Tribes", panel_access.SCOPE_OWNER)]
    out = ""
    if panel_access.at_least(scope, panel_access.SCOPE_FULL):
        active = " class=\"active\"" if current == "cogs" else ""
        out += f'<a href="/guild/{guild.id}"{active}>🧩 Cogs</a>'
    for key, label, needed in links:
        if not panel_access.at_least(scope, needed):
            continue
        active = " class=\"active\"" if current == key else ""
        out += f'<a href="/guild/{guild.id}/{key}"{active}>{label}</a>'
    return f'<span class="navguild">{html.escape(guild.name)}</span>{out}'


def _page(title: str, body: str, *, scope: str = panel_access.SCOPE_OWNER,
          guild=None, current: str = "") -> web.Response:
    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Dodo Control Panel</title>
<link rel="icon" href="/static/favicon-32.png?v={_ASSET_VER}" sizes="32x32">
<link rel="icon" href="/static/favicon-192.png?v={_ASSET_VER}" sizes="192x192">
<link rel="apple-touch-icon" href="/static/favicon-192.png?v={_ASSET_VER}">
<link rel="stylesheet" href="/static/panel.css?v={_ASSET_VER}">
</head><body>
<header>
<a href="/" class="brand">🦤 Dodo Control Panel</a>
<nav>{_guild_nav(guild, scope, current)}
{'<a href="/lang" class="navtool">🔤 Strings</a>' if scope == panel_access.SCOPE_OWNER else ""}<a href="/logout" class="logout">Log out</a></nav>
</header>
<main>{body}</main>
<script src="/static/panel.js?v={_ASSET_VER}"></script>
</body></html>"""
    return web.Response(text=doc, content_type="text/html")


def _nav_chips(guild_id: int, scope: str, current: str) -> str:
    """Cross-links between a guild's pages, limited to what the scope allows."""
    links = []
    if panel_access.at_least(scope, panel_access.SCOPE_FULL) and current != "cogs":
        links.append((f"/guild/{guild_id}", "🧩 Cogs & commands"))
    if panel_access.at_least(scope, panel_access.SCOPE_CONFIG) and current != "settings":
        links.append((f"/guild/{guild_id}/settings", "⚙️ Settings"))
    if panel_access.at_least(scope, panel_access.SCOPE_CONFIG) and current != "events":
        links.append((f"/guild/{guild_id}/events", "⚡ Events"))
    if panel_access.at_least(scope, panel_access.SCOPE_STATS) and current != "stats":
        links.append((f"/guild/{guild_id}/stats", "📊 Stats"))
    # Tribes is bot-owner tooling (the rule engine can hand out any role), same
    # as in the top bar — the page itself is owner-gated, so anyone else only
    # got a chip that 403s.
    if panel_access.at_least(scope, panel_access.SCOPE_OWNER) and current != "tribes":
        links.append((f"/guild/{guild_id}/tribes", "🏅 Tribes"))
    if panel_access.at_least(scope, panel_access.SCOPE_CONFIG) and current != "log":
        links.append((f"/guild/{guild_id}/log", "📝 Change log"))
    return "".join(f'<a class="chip" href="{href}">{label}</a>' for href, label in links)


def _guild_avatar(guild, *, size: int = 64) -> str:
    """A guild's icon <img>, or a lettered placeholder tile. ``size`` is only the
    display size (any int); the source asset uses its default size to avoid
    Discord's power-of-two constraint on Asset.replace()."""
    if guild.icon:
        return f'<img class="glogo" src="{guild.icon.url}" alt="" width="{size}" height="{size}">'
    initial = html.escape((guild.name or "?")[:1].upper())
    return f'<div class="glogo placeholder" style="width:{size}px;height:{size}px">{initial}</div>'


def _landing_for(guild_id: int, scope: str) -> str:
    """Where a card should take someone — the first page their scope allows."""
    if panel_access.at_least(scope, panel_access.SCOPE_FULL):
        return f"/guild/{guild_id}"
    if panel_access.at_least(scope, panel_access.SCOPE_CONFIG):
        return f"/guild/{guild_id}/settings"
    return f"/guild/{guild_id}/stats"


def _status_board(bot) -> str:
    """Bot-wide health: what's true now, and what was true over the last 90 days.

    Days with no samples are drawn as blanks rather than green — the bot being
    off is precisely when nothing gets recorded, so colouring a gap "fine" would
    make the board lie about the only thing it exists to report.
    """
    monitor = getattr(bot, "health", None)
    latency = getattr(bot, "latency", None)
    # discord.py yields nan before the first heartbeat: not measured, not zero.
    latency_ms = None if latency is None or latency != latency else latency * 1000
    connected = bool(getattr(bot, "is_ready", lambda: False)()) and latency_ms is not None
    state = health.classify(latency_ms, connected)

    banner = {health.STATUS_OK: ("ok", "All Systems Operational"),
              health.STATUS_DEGRADED: ("warn", "Degraded, the gateway is slow"),
              health.STATUS_DOWN: ("down", "Not connected to Discord")}[state]

    bars, measured = "", None
    if monitor is not None:
        rows = health.day_bars(monitor.samples())
        measured = health.uptime_percent(rows)
        for bar in rows:
            # Everything the popover needs travels on the bar, so hovering costs
            # no request and the markup stays the single source of truth.
            state = bar["state"] or "none"
            bars += (
                f'<span class="hbar {state}" tabindex="0"'
                f' data-day="{bar["day"].strftime("%d %b %Y").lstrip("0")}"'
                f' data-state="{state}"'
                f' data-uptime="{"" if bar["uptime"] is None else format(bar["uptime"], ".2f")}"'
                f' data-samples="{bar["samples"]}"'
                f' data-down="{health.human_minutes(bar.get("down_minutes") or 0)}"'
                f' data-downmins="{bar.get("down_minutes") or 0}"'
                f' data-degraded="{health.human_minutes(bar.get("degraded_minutes") or 0)}"'
                f' data-degradedmins="{bar.get("degraded_minutes") or 0}"'
                f'></span>'
            )

    uptime = health.human_duration(monitor.uptime_seconds()) if monitor else "—"
    guilds = list(getattr(bot, "guilds", []))
    members = sum(g.member_count or 0 for g in guilds)
    loaded = sum(1 for c in _cog_inventory(bot) if c["loaded"])
    total_cogs = len(_cog_inventory(bot))
    commands_count = len({c.qualified_name for c in getattr(bot, "commands", [])})

    uptime_line = (f"{measured:.2f}% uptime over the past 90 days"
                   if measured is not None
                   else "no history recorded yet, the board fills in from here")
    tiles = [
        ("Servers", f"{len(guilds)}", "installations"),
        ("Members", f"{members:,}", "reachable"),
        ("Uptime", uptime, "since last restart"),
        ("Latency", f"{latency_ms:.0f} ms" if latency_ms is not None else "—", "to Discord"),
        ("Cogs", f"{loaded}/{total_cogs}", "loaded"),
        ("Commands", f"{commands_count}", "registered"),
    ]
    tile_html = "".join(
        f'<div class="statustile"><span class="tilevalue">{html.escape(value)}</span>'
        f'<span class="tilelabel">{html.escape(label)}</span>'
        f'<span class="tilehint">{html.escape(hint)}</span></div>'
        for label, value, hint in tiles
    )

    return f"""
<div class="statusbanner {banner[0]}">{html.escape(banner[1])}</div>
<div class="statustiles">{tile_html}</div>
<div class="statuscard">
  <div class="statushead"><b>Dodo</b><span class="muted small">{html.escape(uptime_line)}</span></div>
  <div class="hbars" id="hbars">{bars}</div>
  <div class="hpop" id="hpop" hidden></div>
  <div class="hscale"><span>90 days ago</span><span>Today</span></div>
</div>"""


def _dashboard_html(bot, entries: list, scope: str) -> str:
    """``entries`` is the ``(guild, scope)`` list the caller is allowed to see."""
    cards = "".join(
        f'<a class="guildcard" href="{_landing_for(g.id, s)}">'
        f'{_guild_avatar(g)}'
        f'<div class="ginfo"><b>{html.escape(g.name)}</b>'
        f'<span class="muted small">{g.member_count or "?"} members · '
        f'{html.escape(panel_access.SCOPE_LABELS.get(s, "Full access"))}</span></div></a>'
        for g, s in sorted(entries, key=lambda e: e[0].name.lower())
    ) or '<p class="muted">No servers you can manage.</p>'

    if scope != panel_access.SCOPE_OWNER:
        # Guild admins get their servers and nothing bot-wide.
        return f'<h1>Your servers</h1><div class="guildgrid">{cards}</div><p id="status" class="status"></p>'

    cog_rows = ""
    for cog in _cog_inventory(bot):
        badge = '<span class="on">loaded</span>' if cog["loaded"] else '<span class="off">unloaded</span>'
        buttons = (
            f'<button data-action="reload" data-cog="{cog["name"]}">Reload</button>'
            f'<button data-action="unload" data-cog="{cog["name"]}" class="ghost">Unload</button>'
            if cog["loaded"]
            else f'<button data-action="load" data-cog="{cog["name"]}">Load</button>'
        )
        cog_rows += f'<tr><td>{html.escape(cog["name"])}</td><td>{badge}</td><td class="cogbtns">{buttons}</td></tr>'

    return f"""
<h1>Status</h1>
{_status_board(bot)}
<h1>Guilds</h1>
<div class="guildgrid">{cards}</div>
<h1>Cogs <span class="muted">(process-wide, affects every guild)</span></h1>
<table class="cogs"><thead><tr><th>Cog</th><th>State</th><th>Actions</th></tr></thead>
<tbody>{cog_rows}</tbody></table>
<p id="status" class="status"></p>
"""


_LEVEL_ICON = {LEVEL_VISIBLE: "🌐", LEVEL_ADMIN: "🛡️", LEVEL_OWNER: "🔒"}


def _level_legend(scope: str) -> str:
    """The "visible / admin / owner" key, listing only the levels this scope uses."""
    levels = VALID_LEVELS if scope == panel_access.SCOPE_OWNER else (LEVEL_VISIBLE, LEVEL_ADMIN)
    return " / ".join(f"<b>{_LEVEL_ICON[lvl]} {lvl}</b>" for lvl in levels)


def _command_cards(commands: list[dict], scope: str = panel_access.SCOPE_OWNER) -> str:
    """Each command as a small card with a name, description and level selector."""
    # Owner-only commands are not shown to anyone else. _cog_detail already drops
    # them; repeated here so no caller can render one by accident.
    if hides_owner_level(scope):
        commands = [c for c in commands if c["level"] != LEVEL_OWNER]
    if not commands:
        return ""
    # Only the bot owner may mark a command owner-only; a guild admin who could
    # set that level could hide commands from the owner.
    levels = VALID_LEVELS if scope == panel_access.SCOPE_OWNER else (LEVEL_VISIBLE, LEVEL_ADMIN)
    cards = ""
    for cmd in commands:
        options = "".join(
            f'<option value="{lvl}"{" selected" if lvl == cmd["level"] else ""}>{_LEVEL_ICON[lvl]} {lvl}</option>'
            for lvl in levels
        )
        cards += (
            f'<div class="cmdcard lvl-{cmd["level"]}">'
            f'<code class="cmdname">/{html.escape(cmd["name"])}</code>'
            f'<div class="muted small cmddesc">{html.escape(cmd["description"] or "—")}</div>'
            f'<select class="level" data-command="{html.escape(cmd["name"])}">{options}</select>'
            f'</div>'
        )
    return f'<div class="cmdgrid">{cards}</div>'


def _feature_rows(features: list[dict]) -> str:
    """Per-listener feature toggles (passive behaviors), nested under a cog."""
    if not features:
        return ""
    rows = ""
    for feat in features:
        checked = "checked" if feat["enabled"] else ""
        rows += f"""
    <div class="featrow" data-feature="{html.escape(feat["key"])}">
      <div><b>{html.escape(feat["label"])}</b><div class="muted small">{html.escape(feat["description"])}</div></div>
      <label class="switch"><input type="checkbox" class="feattoggle" {checked}> on</label>
    </div>"""
    return f'<div class="features"><div class="muted small feathead">Passive features (listeners)</div>{rows}</div>'


def _param_input(param: dict, guild) -> str:
    """The typed control for one parameter (role/channel dropdowns come from the guild)."""
    ptype, value = param["type"], param["value"]
    common = f'class="param" data-key="{html.escape(param["key"])}" data-type="{ptype}"'
    if ptype == "secret":
        placeholder = "•••••• set (blank keeps it)" if param.get("is_set") else "not set"
        return f'<input type="password" {common} placeholder="{html.escape(placeholder)}" autocomplete="new-password">'
    if ptype == "bool":
        return f'<input type="checkbox" {common} {"checked" if value else ""}>'
    if ptype == "text":
        rows = min(8, max(2, (str(value).count(chr(10)) + 1)))
        return f'<textarea {common} rows="{rows}" spellcheck="false">{html.escape(str(value))}</textarea>'
    if ptype == "list_str":
        text = "\n".join(value) if isinstance(value, list) else str(value)
        rows = min(10, max(2, len(value) + 1)) if isinstance(value, list) else 3
        return f'<textarea {common} rows="{rows}" spellcheck="false" placeholder="one per line">{html.escape(text)}</textarea>'
    if ptype == "list_int":
        text = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        return f'<input type="text" {common} value="{html.escape(text)}" placeholder="comma-separated ids">'
    if ptype in ("int", "float"):
        step = "1" if ptype == "int" else "any"
        return f'<input type="number" step="{step}" {common} value="{html.escape(str(value))}">'
    if ptype == "choice":
        opts = "".join(
            f'<option value="{html.escape(c)}"{" selected" if c == value else ""}>{html.escape(c)}</option>'
            for c in param.get("choices", [])
        )
        return f'<select {common}>{opts}</select>'
    if ptype == "role":
        return f'<select {common}>{_role_options(guild, value)}</select>' if guild else ""
    if ptype == "channel":
        # Same picker as the settings page: forums and voice count as channels,
        # and a text-only list silently hides them.
        return f'<select {common}>{_channel_options(guild, value)}</select>' if guild else ""
    if ptype in ("list_role", "list_channel"):
        source = (_sorted_roles(guild) if ptype == "list_role"
                  else [c for c in guild.channels
                        if isinstance(c, (discord.TextChannel, discord.ForumChannel,
                                          discord.VoiceChannel))]) if guild else []
        selected = set(value)
        opts = ""
        for obj in source:
            if getattr(obj, "is_default", lambda: False)():  # skip @everyone
                continue
            opts += (
                f'<div class="ms-opt" data-id="{obj.id}" data-name="{html.escape(obj.name)}" '
                f'data-selected="{1 if obj.id in selected else 0}">{html.escape(obj.name)}</div>'
            )
        return (
            f'<div class="multiselect" data-key="{html.escape(param["key"])}" data-type="{ptype}">'
            f'<div class="ms-chips"></div>'
            f'<input class="ms-search" placeholder="Search…" autocomplete="off">'
            f'<div class="ms-options">{opts}</div></div>'
        )
    return f'<input type="text" {common} value="{html.escape(str(value))}">'


def _param_rows(params: list[dict], guild) -> str:
    if not params:
        return ""
    rows = ""
    for param in params:
        # Multiline inputs get a stacked, full-width row.
        wide = " wide" if param["type"] in ("text", "list_str", "list_role", "list_channel") else ""
        rows += f"""
    <div class="paramrow{wide}">
      <div><b>{html.escape(param["label"])}</b><div class="muted small">{html.escape(param["description"])}</div></div>
      {_param_input(param, guild)}
    </div>"""
    return f'<div class="params"><div class="muted small feathead">Parameters</div>{rows}</div>'


def _cog_level_select(detail: dict, scope: str) -> str:
    """Set every command in the cog to one level at once.

    ``custom`` is shown (and selected) when the cog's commands disagree, but it
    can't be chosen — you get back to a single level by picking one.
    """
    if not detail["commands"]:
        return ""
    current = detail["level"]
    levels = VALID_LEVELS if scope == panel_access.SCOPE_OWNER else (LEVEL_VISIBLE, LEVEL_ADMIN)
    options = ""
    if current == LEVEL_CUSTOM:
        options += f'<option value="{LEVEL_CUSTOM}" selected>\u2699 custom</option>'
    for level in levels:
        selected = " selected" if level == current else ""
        options += f'<option value="{level}"{selected}>{_LEVEL_ICON[level]} all {level}</option>'
    return (
        f'<select class="coglevel" title="Set every command in this cog">{options}</select>'
    )


def _cog_block(detail: dict, guild, *, toggleable: bool, scope: str = panel_access.SCOPE_OWNER) -> str:
    """One cog inside a category: optional per-cog toggle, passive-feature toggles,
    per-server parameters, and its per-command visibility cards."""
    body = _command_cards(detail["commands"], scope)
    if not detail["commands"] and not detail["features"] and not detail["params"]:
        body = '<p class="muted small">No slash commands. Passive listener cog.</p>'
    toggle = (
        f'<label class="switch"><input type="checkbox" class="cogtoggle" {"checked" if detail["enabled"] else ""}> enabled</label>'
        if toggleable else '<span class="muted small">always on</span>'
    )
    return f"""
<div class="cogcard" id="cog-{html.escape(detail["cog"])}" data-cog="{html.escape(detail["cog"])}">
  <div class="coghead"><h3>{html.escape(detail["cog"])}</h3>
    {_cog_level_select(detail, scope)}{toggle}</div>
  {_feature_rows(detail["features"])}
  {_param_rows(detail["params"], guild)}
  {body}
</div>"""


def _access_html(bot, guild) -> str:
    """Owner-only card: hand roles (or single users) a panel scope for this guild."""
    grants = bot.panel_access.grants(guild.id)
    scope_options = "".join(
        f'<option value="{key}">{html.escape(panel_access.SCOPE_LABELS[key])}</option>'
        for key in panel_access.GRANTABLE_SCOPES
    )
    role_options = "".join(
        f'<option value="{role.id}">@{html.escape(role.name)}</option>'
        for role in sorted(guild.roles, key=lambda r: -r.position)
        if not role.is_default()
    )

    rows = ""
    for grant in grants:
        if grant["kind"] == "role":
            role = guild.get_role(grant["target_id"])
            label = f"@{role.name}" if role else f"Deleted role ({grant['target_id']})"
        else:
            member = guild.get_member(grant["target_id"])
            label = member.display_name if member else f"User {grant['target_id']}"
        rows += (
            f'<tr><td>{html.escape(label)}</td>'
            f'<td class="muted small">{grant["kind"]}</td>'
            f'<td>{html.escape(panel_access.SCOPE_LABELS.get(grant["scope"], grant["scope"]))}</td>'
            f'<td><button class="ghost grantdel" data-kind="{grant["kind"]}" '
            f'data-target="{grant["target_id"]}">Remove</button></td></tr>'
        )
    rows = rows or '<tr><td colspan="4" class="muted">No grants yet.</td></tr>'

    return f"""
<section class="catcard" id="cat-access">
  <div class="cathead"><div class="cattitle"><span class="catemoji">🔑</span>
    <h2>Panel access</h2>
    <span class="muted small">who may open this server's panel, and how much of it</span></div></div>
  <div class="accessbody">
    <p class="muted small">Anyone with Discord's <b>Manage Server</b> permission already has full access.
    Grants below add access for a role (or one person) on top of that. Members who aren't in this
    server can never reach it, whatever is listed here. Only you (bot owner) can edit this card, and
    only you see the bot-wide tooling.</p>
    <table class="stats"><thead><tr><th>Who</th><th>Type</th><th>Access</th><th></th></tr></thead>
      <tbody id="grantrows">{rows}</tbody></table>
    <div class="grantadd">
      <select id="grantkind"><option value="role">Role</option><option value="user">User id</option></select>
      <select id="grantrole">{role_options}</select>
      <input id="grantuser" placeholder="user id" style="display:none">
      <select id="grantscope">{scope_options}</select>
      <button id="grantadd">Grant access</button>
    </div>
  </div>
</section>"""


def _guild_html(bot, guild, scope: str = panel_access.SCOPE_OWNER) -> str:
    sections = ""
    nav = ""
    for category in cog_categories.group_loaded_cogs(bot.cogs.keys()):
        toggleable = category["toggleable"]
        members = [_cog_detail(bot, guild.id, name, scope=scope) for name in category["present"]]
        if hides_owner_level(scope):
            # A cog whose whole surface is owner-only (e.g. the owner cog) drops
            # out entirely — an empty shell would just advertise it. A cog that
            # never had commands is a real passive cog and keeps its toggle.
            members = [
                m for m in members
                if m["commands"] or m["features"] or m["params"] or not m["hidden"]
            ]
        if not toggleable:
            # Core: no enable/disable, only per-command visibility for cogs that have commands.
            members = [m for m in members if m["commands"]]
        if not members:
            continue
        if toggleable:
            states = [m["enabled"] for m in members]
            state = "on" if all(states) else ("off" if not any(states) else "mixed")
            checked = "checked" if state == "on" else ""
            master = (
                f'<label class="switch master"><input type="checkbox" class="cattoggle" '
                f'data-category="{category["key"]}" data-state="{state}" {checked}> on</label>'
            )
            blocks = "".join(_cog_block(m, guild, toggleable=True, scope=scope) for m in members)
        else:
            blocks = "".join(_cog_block(m, guild, toggleable=False, scope=scope) for m in members)
            master = '<span class="muted small">always on</span>'

        sections += f"""
<section class="catcard" id="cat-{category["key"]}" data-category="{category["key"]}">
  <div class="cathead">
    <div class="cattitle"><span class="catemoji">{category["emoji"]}</span>
      <h2>{html.escape(category["label"])}</h2>
      <span class="muted small">{len(members)} cog(s) · {html.escape(category["description"])}</span>
    </div>
    {master}
  </div>
  <details class="catbody" open><summary>per-cog & per-command controls</summary>{blocks}</details>
</section>"""

        # Reload/Unload load code into the running process (every guild), so they
        # are owner-only; admins get the navigation link alone.
        show_cog_buttons = scope == panel_access.SCOPE_OWNER
        nav_cogs = "".join(
            f'<div class="navcog" data-cog="{html.escape(m["cog"])}">'
            f'<a href="#cog-{html.escape(m["cog"])}">{html.escape(m["cog"])}</a>'
            + (
                f'<span class="navbtns">'
                f'<button data-action="reload" data-cog="{html.escape(m["cog"])}" title="Reload">Reload</button>'
                f'<button data-action="unload" data-cog="{html.escape(m["cog"])}" title="Unload">Unload</button>'
                f'</span>' if show_cog_buttons else ""
            )
            + '</div>'
            for m in members
        )
        nav += (
            f'<details class="navcat" open><summary>{category["emoji"]} {html.escape(category["label"])}</summary>'
            f'{nav_cogs}</details>'
        )

    return f"""
<div class="guildpage" data-guild="{guild.id}">
  <aside class="sidebar">
    <a href="/" class="back">← all guilds</a>
    <div class="ghead">{_guild_avatar(guild, size=48)}
      <div class="ginfo"><b>{html.escape(guild.name)}</b><span class="muted small">{guild.id}</span></div></div>

    <div class="toolbar">
      <input id="cogfilter" type="search" placeholder="Filter cogs…" autocomplete="off">
      <button id="expandall" class="ghost">Expand all</button>
      <button id="collapseall" class="ghost">Collapse all</button>
    </div>
    <nav class="cognav"><div class="navroot">All categories</div>{nav}</nav>
  </aside>
  <main class="content">
    {_access_html(bot, guild) if scope == panel_access.SCOPE_OWNER else ""}
    <p class="muted">Toggle a whole category on/off for this server, or expand a cog for its
    features, parameters and per-command visibility ({_level_legend(scope)}).
    Changes apply to this guild within a few seconds.</p>
    {sections}
  </main>
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Settings page
# --------------------------------------------------------------------------- #
def _channel_options(guild, selected, *, blank: str = "— none —") -> str:
    """Channel dropdown covering everything a setting might point at (text, news,
    forum, voice), not just text channels."""
    options = f'<option value="0">{blank}</option>'
    usable = [
        channel for channel in guild.channels
        if isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel))
    ]
    for channel in sorted(usable, key=lambda c: (c.category.name if c.category else "", c.position)):
        if isinstance(channel, discord.ForumChannel):
            prefix = "🗂"
        elif isinstance(channel, discord.VoiceChannel):
            prefix = "🔊"
        else:
            prefix = "#"
        category = f" · {channel.category.name}" if channel.category else ""
        options += (
            f'<option value="{channel.id}"{" selected" if channel.id == selected else ""}>'
            f"{html.escape(prefix + channel.name + category)}</option>"
        )
    return options


def _sorted_roles(guild) -> list:
    """This guild's roles in the server's own hierarchy order (highest first),
    minus @everyone — the order people expect to see in a picker."""
    return [role for role in sorted(guild.roles, key=lambda r: -r.position) if not role.is_default()]


def _role_options(guild, selected) -> str:
    options = '<option value="0">— none —</option>'
    for role in sorted(guild.roles, key=lambda r: -r.position):
        if role.is_default():
            continue
        options += (
            f'<option value="{role.id}"{" selected" if role.id == selected else ""}>'
            f"@{html.escape(role.name)}</option>"
        )
    return options


def _setting_input(spec: dict, value, guild) -> str:
    kind = spec["type"]
    common = f'class="setting" data-key="{html.escape(spec["key"])}" data-type="{kind}"'
    if kind == "channel":
        return f'<select {common}>{_channel_options(guild, value)}</select>'
    if kind == "role":
        return f'<select {common}>{_role_options(guild, value)}</select>'
    if kind == "message":
        return f'<input type="text" {common} value="{html.escape(str(value or ""))}" placeholder="message id" inputmode="numeric">'
    if kind == "text":
        text = str(value or "")
        return f'<textarea {common} rows="{min(8, max(3, text.count(chr(10)) + 2))}" spellcheck="false">{html.escape(text)}</textarea>'
    if kind == "emoji":
        return f'<input type="text" {common} value="{html.escape(str(value or ""))}" class="setting emoji" size="4">'
    if kind in ("list_role", "list_channel"):
        source = _sorted_roles(guild) if kind == "list_role" else guild.channels
        selected = set(value or [])
        options = ""
        for obj in source:
            if getattr(obj, "is_default", lambda: False)():
                continue
            if kind == "list_channel" and not isinstance(obj, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel)):
                continue
            label = ("@" if kind == "list_role" else "#") + obj.name
            options += (
                f'<div class="ms-opt" data-id="{obj.id}" data-name="{html.escape(label)}" '
                f'data-selected="{1 if obj.id in selected else 0}">{html.escape(label)}</div>'
            )
        return (
            f'<div class="multiselect setting" data-key="{html.escape(spec["key"])}" data-type="{kind}">'
            f'<div class="ms-chips"></div><input class="ms-search" placeholder="Search…" autocomplete="off">'
            f'<div class="ms-options">{options}</div></div>'
        )
    return f'<input type="text" {common} value="{html.escape(str(value or ""))}">'


def _settings_html(bot, guild, scope: str = panel_access.SCOPE_OWNER) -> str:
    values = bot.guild_config.get_all(guild.id)
    overridden_keys = bot.guild_config.overridden_keys(guild.id)
    log_cog = bot.get_cog("log")
    audit = log_cog.guild_log_channels(guild) if log_cog else {}

    sections = ""
    for group in guild_config.GROUPS:
        rows = ""
        for spec in guild_config.SETTING_SPECS:
            if spec["group"] != group:
                continue
            overridden = spec["key"] in overridden_keys
            unused = "" if spec["used_by"] else '<span class="muted small"> · not read by any command yet</span>'
            badge = '<span class="on">set</span>' if overridden else ""
            wide = " wide" if spec["type"] in ("text", "list_role", "list_channel") else ""
            rows += f"""
    <div class="setrow{wide}" data-key="{html.escape(spec["key"])}">
      <div><b>{html.escape(spec["label"])}</b> {badge}
        <div class="muted small">{html.escape(spec["description"])}</div>
        <div class="muted small"><code>{html.escape(spec["key"])}</code>{unused}</div></div>
      <div class="setctl">{_setting_input(spec, values.get(spec["key"]), guild)}
        <button class="ghost setreset" data-key="{html.escape(spec["key"])}" title="Restore the default">Reset</button>
      </div>
    </div>"""
        sections += (
            f'<details class="group" open><summary>{html.escape(group)}</summary>'
            f'<div class="settings">{rows}</div></details>'
        )

    # The audit logger keeps its own store (guilds.json), so it gets its own block.
    audit_rows = ""
    for key, label, description in (
        ("channel_id", "Audit log channel", "Joins, leaves, role changes, edits. The full audit feed."),
        ("delete_channel_id", "Deleted/edited messages", "Separate destination for deletions and edits. "
                                                        "Falls back to the audit channel when unset."),
    ):
        audit_rows += f"""
    <div class="setrow" data-key="{key}">
      <div><b>{html.escape(label)}</b><div class="muted small">{html.escape(description)}</div></div>
      <div class="setctl"><select class="auditchannel" data-key="{key}">
        {_channel_options(guild, audit.get(key) or 0)}</select></div>
    </div>"""

    return f"""
<div class="settingspage" data-guild="{guild.id}">
  <div class="statshead">
    <div><span class="muted">{html.escape(guild.name)}</span>
      <h1>Server settings</h1></div>

  </div>
  <p class="muted">Channels, roles and messages this server's commands read. Anything left at its
  default is inherited from the bot's built-in configuration; <b>Reset</b> puts a setting back.
  Gameplay tunables (thresholds, costs, prefixes) live under each cog on the
  <a href="/guild/{guild.id}">main page</a>.</p>
  <input id="setsearch" type="search" placeholder="Filter settings…" autocomplete="off">
  <details class="group" open><summary>Audit log <span class="muted">(log cog)</span></summary>
    <div class="settings">{audit_rows}</div></details>
  {sections}
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Event rules page
# --------------------------------------------------------------------------- #
# Placeholder hints for the events people actually build rules on. Anything not
# listed still works — the runtime derives names from the argument types — so
# the page says so rather than pretending the list is exhaustive.
_EVENT_HINTS = {
    "member_join": "{member} {member_name} {member_mention} {guild_name}",
    "member_remove": "{member} {member_name} {member_mention} {guild_name}",
    "member_ban": "{guild_name} {user_name} {user_mention}",
    "member_unban": "{guild_name} {user_name} {user_mention}",
    "member_update": "{before} {after} {after_name} {after_mention}",
    "message": "{message} {content} {jump_url} {member_name} {channel_name}",
    "message_delete": "{message} {content} {channel_name} {member_name}",
    "message_edit": "{before} {after} {jump_url}",
    "reaction_add": "{reaction} {user_name} {user_mention}",
    "guild_channel_create": "{channel} {channel_name}",
    "guild_channel_delete": "{channel} {channel_name}",
    "guild_role_create": "{role} {role_name}",
    "guild_role_delete": "{role} {role_name}",
    "voice_state_update": "{member_name} {member_mention} {before} {after}",
    "thread_create": "{thread} {thread_name}",
    "invite_create": "{invite}",
    "audit_log_entry_create": "{entry} {guild_name}",
}


def _event_options(selected: str) -> str:
    """The event picker: every catalog entry, grouped, with the current one chosen."""
    options = ""
    for group, event_names in events.grouped_events().items():
        options += f'<optgroup label="{html.escape(group)}">'
        for event in event_names:
            options += (
                f'<option value="{event}"{" selected" if event == selected else ""}>'
                f"on_{html.escape(event)}</option>"
            )
        options += "</optgroup>"
    return options


def _rule_card(rule: dict, guild) -> str:
    """One rule: event, destination, message, pings — editable in place."""
    rule_id = str(rule["_id"])
    event = rule.get("event", "")
    hint = _EVENT_HINTS.get(event)
    hint_html = (
        f'<div class="muted small">Placeholders: <code>{html.escape(hint)}</code></div>'
        if hint else
        '<div class="muted small">Placeholders come from the event\'s arguments '
        '(<code>{guild_name}</code> is always available). Fire it once and check the result.</div>'
    )
    pinged_users = " ".join(str(uid) for uid in rule.get("ping_user_ids") or [])
    role_options = ""
    for role in guild.roles:
        if role.is_default():
            continue
        chosen = 1 if role.id in (rule.get("ping_role_ids") or []) else 0
        role_options += (
            f'<div class="ms-opt" data-id="{role.id}" data-name="@{html.escape(role.name)}" '
            f'data-selected="{chosen}">@{html.escape(role.name)}</div>'
        )

    return f"""
<div class="rulecard{"" if rule.get("enabled", True) else " off"}" data-rule="{rule_id}">
  <div class="rulehead">
    <input class="rulename" value="{html.escape(rule.get("name") or event)}" placeholder="Rule name">
    <label class="switch"><input type="checkbox" class="ruletoggle"
      {"checked" if rule.get("enabled", True) else ""}> on</label>
    <button class="ghost ruledelete" title="Delete this rule">Delete</button>
  </div>
  <div class="rulegrid">
    <label>When <select class="ruleevent">{_event_options(event)}</select></label>
    <label>post in <select class="rulechannel">{_channel_options(guild, rule.get("channel_id") or 0,
                                                                 blank="— pick a channel —")}</select></label>
  </div>
  <textarea class="rulemessage" rows="3" spellcheck="false"
    placeholder="Message to post…">{html.escape(rule.get("message") or "")}</textarea>
  {hint_html}
  <div class="rulegrid">
    <label>Ping roles
      <div class="multiselect ruleroles"><div class="ms-chips"></div>
        <input class="ms-search" placeholder="Search roles…" autocomplete="off">
        <div class="ms-options">{role_options}</div></div>
    </label>
    <label>Ping user ids
      <input class="ruleusers" value="{html.escape(pinged_users)}" placeholder="123456789 987654321"></label>
  </div>
  <div class="rulebtns"><button class="rulesave">Save</button>
    <span class="muted small">{html.escape(event)}</span></div>
</div>"""


def _events_html(bot, guild, scope: str = panel_access.SCOPE_OWNER) -> str:
    rules = bot.event_rules.for_guild(guild.id)
    cards = "".join(_rule_card(rule, guild) for rule in rules) or (
        '<p class="muted">No rules yet. Add one to get started.</p>'
    )
    catalog = events.selectable_events()
    skipped = sorted(events.NON_GUILD_EVENTS)
    active = bot.visibility.feature_enabled(guild.id, "event_rules")
    return f"""
<div class="eventspage" data-guild="{guild.id}">
  <div class="statshead">
    <div><span class="muted">{html.escape(guild.name)}</span>
      <h1>Event rules <span class="muted">· {len(rules)} rule(s)</span></h1></div>

  </div>
  <p class="muted">When something happens on this server, post a message, optionally pinging
  people. All {len(catalog)} events this discord.py build dispatches are available.
  {"" if active else "<b>The event rules feature is currently off for this server</b>. Turn it on under the event_actions cog on the "}
  {"" if active or not panel_access.at_least(scope, panel_access.SCOPE_FULL) else f'<a href="/guild/{guild.id}">main page</a>.'}</p>
  <p class="muted small">Rules ignore anything the bot itself caused, and each rule is capped at
  {event_actions_limit()} messages per minute so a busy event can't flood a channel.
  {len(skipped)} events aren't listed because they carry no server
  (<code>{html.escape(", ".join(skipped[:6]))}…</code>).</p>
  <button id="addrule">+ New rule</button>
  <div id="rulelist">{cards}</div>
</div>
<p id="status" class="status"></p>
"""


def event_actions_limit() -> int:
    """The runtime's per-rule rate limit, shown on the page so the two agree."""
    from cogs.event_actions import RATE_LIMIT

    return RATE_LIMIT


# --------------------------------------------------------------------------- #
#  Tribes page
# --------------------------------------------------------------------------- #
def _tribe_pickers(guild) -> str:
    """Role and channel option lists the builder clones for each condition."""
    roles = "".join(
        f'<option value="{role.id}">@{html.escape(role.name)}</option>' for role in _sorted_roles(guild)
    )
    channels = ""
    for channel in guild.channels:
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel)):
            continue
        prefix = "🗂" if isinstance(channel, discord.ForumChannel) else "#"
        channels += f'<option value="{channel.id}">{html.escape(prefix + channel.name)}</option>'
    return (
        f'<datalist id="tribe-roles">{roles}</datalist>'
        f'<datalist id="tribe-channels">{channels}</datalist>'
        f'<script type="application/json" id="tribe-role-options">{_json_options(_sorted_roles(guild), "@")}</script>'
        f'<script type="application/json" id="tribe-channel-options">{_json_channel_options(guild)}</script>'
    )


def _json_options(items, prefix: str) -> str:
    import json as _json
    return _json.dumps([{"id": str(i.id), "name": prefix + i.name} for i in items])


def _json_channel_options(guild) -> str:
    import json as _json
    out = []
    for channel in guild.channels:
        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            prefix = "🗂" if isinstance(channel, discord.ForumChannel) else "#"
            out.append({"id": str(channel.id), "name": prefix + channel.name})
    return _json.dumps(out)


def _tribe_card(tribe: dict, guild) -> str:
    import json as _json
    tribe_id = str(tribe["_id"])
    mode = tribe.get("mode") or tribe_rules.MODE_CONDITION
    condition = tribe.get("condition") or {"type": "all", "children": []}
    role_options = "".join(
        f'<div class="ms-opt" data-id="{role.id}" data-name="@{html.escape(role.name)}" '
        f'data-selected="{1 if role.id in (tribe.get("role_ids") or []) else 0}">@{html.escape(role.name)}</div>'
        for role in _sorted_roles(guild)
    )
    if mode == tribe_rules.MODE_POINTS:
        summary = html.escape(tribe_rules.describe_points(tribe, guild))
    elif condition.get("children"):
        summary = html.escape(tribe_rules.describe(condition, guild))
    else:
        summary = '<span class="muted">no conditions yet, matches nobody</span>'
    return f"""
<div class="tribecard{"" if tribe.get("enabled", True) else " off"}" data-tribe="{tribe_id}">
  <div class="rulehead">
    <input class="rulename tribename" value="{html.escape(tribe.get("name") or "")}" placeholder="Tribe name">
    <label class="switch"><input type="checkbox" class="tribetoggle"
      {"checked" if tribe.get("enabled", True) else ""}> on</label>
    <button class="ghost tribedelete">Delete</button>
  </div>
  <div class="tribesummary muted small">{summary}</div>
  <div class="rulegrid">
    <label>Grant these roles
      <div class="multiselect triberoles"><div class="ms-chips"></div>
        <input class="ms-search" placeholder="Search roles…" autocomplete="off">
        <div class="ms-options">{role_options}</div></div>
    </label>
    <label>When someone stops matching
      <select class="triberemove">
        <option value="0"{"" if tribe.get("remove_when_unmatched") else " selected"}>Keep the role</option>
        <option value="1"{" selected" if tribe.get("remove_when_unmatched") else ""}>Take the role back</option>
      </select>
    </label>
  </div>
  <div class="modeswitch">
    <label><input type="radio" name="mode-{tribe_id}" value="condition"
      {"checked" if mode != tribe_rules.MODE_POINTS else ""}> Rule (you match, you're in)</label>
    <label><input type="radio" name="mode-{tribe_id}" value="points"
      {"checked" if mode == tribe_rules.MODE_POINTS else ""}> Points (earn a rank)</label>
  </div>
  <div class="rulebuilder" data-condition='{html.escape(_json.dumps(condition))}'
       {"hidden" if mode == tribe_rules.MODE_POINTS else ""}></div>
  <div class="pointsbuilder" data-sources='{html.escape(_json.dumps(tribe.get("sources") or []))}'
       data-tiers='{html.escape(_json.dumps(tribe.get("tiers") or []))}'
       {"hidden" if mode != tribe_rules.MODE_POINTS else ""}>
    <div class="pointshead">
      <b>What earns points</b>
      <span class="muted small">holding several scoring roles adds up</span>
    </div>
    <div class="sourcerows"></div>
    <button class="ghost addsource">+ scoring role</button>
    <div class="pointshead">
      <b>Ranks</b>
      <span class="muted small">reaching a threshold grants that rank; lower ranks come off</span>
    </div>
    <div class="tierrows"></div>
    <button class="ghost addtier">+ rank</button>
    <label class="switch exclusivewrap"><input type="checkbox" class="tribeexclusive"
      {"checked" if tribe.get("exclusive", True) else ""}> only hold the highest rank</label>
  </div>
  <div class="rulebtns"><button class="tribesave">Save tribe</button>
    <span class="muted small">{len(tribe.get("role_ids") or [])} role(s)</span></div>
</div>"""


def _tribes_html(bot, guild, scope: str) -> str:
    tribes = bot.tribes.for_guild(guild.id)
    cards = "".join(_tribe_card(t, guild) for t in tribes) or \
        '<p class="muted">No tribes yet. Add one to start.</p>'
    cog = bot.get_cog("tribes")
    last = (cog.last_run.get(guild.id) if cog else None) or {}
    when = last.get("at")
    last_line = (
        f"Last sweep {when:%Y-%m-%d %H:%M} UTC · {last.get('matched', 0)} membership(s), "
        f"{last.get('granted', 0)} role(s) granted, {last.get('removed', 0)} removed"
        if when else "No sweep has run yet this session."
    )
    active = bot.visibility.feature_enabled(guild.id, "tribes")
    return f"""
<div class="tribespage" data-guild="{guild.id}">
  <div class="statshead">
    <div><h1>Tribes <span class="muted">· {len(tribes)} rule(s)</span></h1></div>
  </div>
  <p class="muted">Build a rule from roles, tenure and activity; everyone who matches gets the
  role(s). Rules are re-evaluated <b>hourly</b>, and you can run one now.
  {"" if active else "<b>The tribes feature is off for this server</b>. Turn it on under the tribes cog."}</p>
  <p class="muted small">{html.escape(last_line)}</p>
  <div class="tribeactions">
    <button id="addtribe">+ New tribe</button>
    <button id="runtribes" class="ghost">Run now</button>
  </div>
  {_tribe_pickers(guild)}
  <div id="tribelist">{cards}</div>
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Trial ranking page
# --------------------------------------------------------------------------- #
def _role_picker(guild, *, key: str, selected_id: int = 0, placeholder: str = "Type a role name…") -> str:
    """A text box that filters roles as you type, backed by a hidden id.

    A plain <select> means scrolling a hundred roles; this lets you type three
    letters and pick. The visible input never carries the value — the hidden
    field does — so a half-typed name can't be mistaken for a choice. The id
    stays a string all the way to the server: it doesn't fit in a JS number.
    """
    role = guild.get_role(selected_id) if selected_id else None
    return (
        f'<div class="rolepick" data-key="{html.escape(key)}">'
        f'<input class="rolepick-text" placeholder="{html.escape(placeholder)}" '
        f'value="{html.escape("@" + role.name) if role else ""}" autocomplete="off" spellcheck="false">'
        f'<input type="hidden" class="rolepick-id" value="{selected_id or 0}">'
        f'<button type="button" class="rolepick-clear" title="Clear">×</button>'
        f'<div class="rolepick-list" hidden></div></div>'
    )


def _rank_image_cell(guild_id: int, role_id: int, *, has_image: bool) -> str:
    """Upload / preview / remove for one rank's badge.

    The picture is optional everywhere it's used: no upload simply means the
    /rank card carries no image, not a broken one.
    """
    preview = (
        f'<img class="rankimg-preview" alt="" '
        f'src="/guild/{guild_id}/trials/image/{role_id}.png?v={_ASSET_VER}">'
        if has_image and role_id else '<span class="rankimg-empty">no picture</span>'
    )
    return (
        f'<div class="rankimg" data-has="{1 if has_image and role_id else 0}">'
        f'{preview}'
        f'<input type="file" class="rankimg-file" accept="image/png,image/jpeg,image/webp,image/gif" hidden>'
        f'<button type="button" class="ghost rankimg-pick">Picture…</button>'
        f'<button type="button" class="ghost rankimg-del"'
        f'{"" if has_image and role_id else " hidden"}>Remove</button>'
        f'</div>'
    )


def _rank_rows(bot, guild, config: dict) -> str:
    """One row per rank: a role, a threshold, a description and a badge.

    There is no fixed ladder — a server adds as many ranks as it wants and calls
    them whatever its roles are called. Rows render cheapest-first because that
    is the only ordering the ranks have.
    """
    with_images = bot.trial_ranks.image_role_ids(guild.id)
    rows = ""
    for index, rank in enumerate(trial_ranks.rank_rows(config, guild)):
        rows += f"""
    <div class="rankrow mapped" data-index="{index}">
      <div class="rankmain">
        <span class="rankindex">{index + 1}</span>
        {_role_picker(guild, key="rank", selected_id=rank["role_id"])}
        <span class="rankmid">at</span>
        <input type="number" class="rankmin" value="{rank["min_points"]}" placeholder="0">
        <span class="rankmid">points</span>
        {_rank_image_cell(guild.id, rank["role_id"], has_image=rank["role_id"] in with_images)}
        <button type="button" class="ghost rankdel" title="Remove this rank">×</button>
      </div>
      <textarea class="rankdesc" rows="2" maxlength="{trial_ranks.MAX_DESCRIPTION}"
        placeholder="Optional. Shown on the /rank card for this rank"
        >{html.escape(rank["description"])}</textarea>
    </div>"""
    return rows


def _json_loads_safe(value):
    """Stringify ids on the way out, the same way ``_json_dumps`` does.

    A Discord id doesn't survive JavaScript's number type, so anything the
    browser will read back and send again travels as a string.
    """
    if isinstance(value, dict):
        return {k: _json_loads_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_loads_safe(v) for v in value]
    return str(value) if isinstance(value, int) and value > 2**53 else value


def _json_dumps(value) -> str:
    """JSON for an inline <script> block, with ids kept as strings."""
    import json as _json

    def _stringify(item):
        if isinstance(item, dict):
            return {k: _stringify(v) for k, v in item.items()}
        if isinstance(item, list):
            return [_stringify(v) for v in item]
        # Discord ids don't survive JavaScript's number type.
        return str(item) if isinstance(item, int) and item > 2**53 else item

    return _json.dumps(_stringify(value))


def _slot_cell(guild, slot: str, role_id: int, points: dict) -> str:
    """One slot: the role it maps to, and — once mapped — what it's worth.

    Score and mapping used to live on different pages, which meant pricing a
    clear and saying which trial it belonged to were two unrelated chores. A
    slot with no role has nothing to price, so the box only appears once there
    is something to put a number on.
    """
    value = (points or {}).get(str(int(role_id))) if role_id else None
    if not value and role_id:
        role = guild.get_role(int(role_id))
        value = trial_ranks.default_points_for(role) if role is not None else 0
    return (
        f'<label class="slotcell"><span class="slotlabel">'
        f'{html.escape(trial_ranks.SLOT_LABELS[slot])}</span>'
        f'{_role_picker(guild, key=slot, selected_id=role_id or 0, placeholder="—")}'
        f'<input type="number" class="rolepoints slotpoints" data-role="{int(role_id or 0)}" '
        f'value="{value or ""}" placeholder="pts"{"" if role_id else " hidden"}>'
        f"</label>"
    )


def _trial_map_rows(guild, trials: list[dict], points: dict) -> str:
    """One row per trial: a name, and for each slot a role plus its score."""
    rows = ""
    for index, trial in enumerate(trials):
        slots = trial.get("slots") or {}
        pickers = "".join(
            _slot_cell(guild, slot, slots.get(slot) or 0, points)
            for slot in trial_ranks.SLOTS
        )
        name = trial.get("name") or ""
        # Searchable on the trial's name and every role it maps, so "Bahsei"
        # finds Rockgrove without anyone remembering which trial that is.
        haystack = " ".join(
            [name] + [(guild.get_role(int(rid)).name if guild.get_role(int(rid)) else "")
                      for rid in slots.values()]
        ).lower()
        rows += (
            f'<div class="trialrow" data-index="{index}" '
            f'data-search="{html.escape(haystack)}">'
            f'<div class="trialhead">'
            f'<input class="trialname" value="{html.escape(name)}" '
            f'placeholder="Trial name (e.g. Kyne\'s Aegis)">'
            f'<button class="ghost trialdel" title="Remove this trial">×</button></div>'
            f'<div class="slotgrid">{pickers}</div></div>'
        )
    return rows


def _extra_score_rows(guild, config: dict) -> str:
    """Scoring roles that belong to no trial — standalone achievements.

    Sourced from what is actually priced rather than from a divider, so this
    survives the role list being reorganised. Anything with points that isn't
    mapped to a trial slot lands here and stays editable.
    """
    points = config.get("points") or {}
    mapped = set(trial_ranks.slot_of(config.get("trials") or []))
    rows = ""
    for role_id, value in sorted(points.items(), key=lambda kv: -int(kv[1])):
        role_id = int(role_id)
        if role_id in mapped:
            continue
        role = guild.get_role(role_id)
        if role is None:
            continue
        rows += (
            f'<div class="extrarow" data-search="{html.escape(role.name.lower())}">'
            f'{_role_picker(guild, key="extra", selected_id=role_id)}'
            f'<input type="number" class="rolepoints" data-role="{role_id}" '
            f'value="{int(value)}" placeholder="pts">'
            f'<button type="button" class="ghost extradel" title="Remove">×</button></div>'
        )
    return rows


def _trial_map_html(guild, config: dict) -> str:
    """The mapping section: what belongs to which trial, and in what order."""
    trials = config.get("trials") or []
    suggestion_count = 0 if trials else len(trial_ranks.suggest_trials(guild))
    hint = (
        f'<p class="muted small">Nothing mapped yet. <b>Suggest from role names</b> will '
        f'propose {suggestion_count} trial(s) from your clear roles for you to check. '
        f'trifectas can\'t be guessed, so add those yourself.</p>'
        if not trials else ""
    )
    points = config.get("points") or {}
    return f"""
    <div class="explain">
      <p>Within one trial the roles are a progression: <b>veteran clear → partial hardmode 1 →
      partial hardmode 2 → full hardmode → trifecta</b>. Holding a stronger one means the weaker
      ones are already implied, so the bot keeps <b>one role per person per trial</b> and takes the
      rest off.</p>
      <p><b>Extra achievement</b> is the exception: it adds its points on top and removes nothing.
      Pointing it at the same role as the trifecta is fine, that role still scores once.</p>
      <p>Leave a slot empty if the trial doesn't have it. The order above is what counts, not the
      points.</p>
    </div>
    {hint}
    <input class="rolefilter" id="trialsearch"
      placeholder="Type to find a trial, a boss or a title…">
    <div class="trialactions">
      <button class="ghost" id="addtrial">+ Add a trial</button>
      <button class="ghost" id="suggesttrials">Suggest from role names</button>
    </div>
    <div id="trialmap">{_trial_map_rows(guild, trials, points)}</div>

    <h3 class="subhead">Everything else that scores</h3>
    <p class="muted small">Achievements and one-off roles that don't belong to a trial. These
    aren't read from any divider. Whatever is listed here is what counts.</p>
    <div id="extrascores">{_extra_score_rows(guild, config)}</div>
    <div class="trialactions"><button class="ghost" id="addextra">+ Add a role</button></div>"""


_STATE_LABELS = {
    trial_ranks.STATE_ENROLLED: "✅ on the new system",
    trial_ranks.STATE_READ: "📖 read the explanation",
    trial_ranks.STATE_DISMISSED: "💤 let it time out",
    trial_ranks.STATE_PROMPTED: "❓ asked, no answer yet",
}


def _conversion_stats(bot, guild, config: dict) -> dict:
    """The funnel: who's converted, who read it, who walked away, who's left.

    Counted off the timestamps rather than the current state, so "23 people read
    how it works" stays true after those 23 go on to enrol.
    """
    roster = bot.trial_ranks.roster(guild.id)
    known = {int(row["user_id"]) for row in roster}
    enrolled = [row for row in roster if row.get("state") == trial_ranks.STATE_ENROLLED]
    enrolled_ids = {int(row["user_id"]) for row in enrolled}
    # "Still to change" is only meaningful for people the system would rank at
    # all — someone with no clears isn't waiting on anything.
    scoring = {int(role_id) for role_id in (config.get("points") or {})}
    candidates = [
        member for member in guild.members
        if not member.bot and scoring & {role.id for role in member.roles}
    ]
    return {
        "roster": roster,
        "enrolled": len(enrolled),
        "read": sum(1 for row in roster if row.get("read_at")),
        "dismissed": sum(1 for row in roster
                         if row.get("dismissed_at") and int(row["user_id"]) not in enrolled_ids),
        "waiting": sum(1 for row in roster
                       if int(row["user_id"]) not in enrolled_ids
                       and not row.get("dismissed_at") and row.get("prompted_at")),
        "untouched": sum(1 for member in candidates if member.id not in known),
        "candidates": len(candidates),
    }


def _unreachable_member(guild, member) -> str:
    """Why the bot can't change this member's roles, or ``""`` if it can.

    Separate from the role checks because it's a separate Discord rule, and the
    one that actually catches people out: a member whose highest role is at or
    above the bot's is untouchable *entirely*, even for roles the bot could
    otherwise hand out freely.
    """
    me = guild.me
    if me is None or member is None:
        return ""
    if member.id == getattr(guild, "owner_id", None):
        return "server owner, so Discord never lets a bot change their roles"
    if member.top_role >= me.top_role:
        return f"their top role ({member.top_role.name}) is above mine"
    return ""


def _rank_role_warnings(guild, config: dict) -> list[str]:
    """Reasons the bot won't actually be able to hand out the ranks configured.

    Checked on the page rather than only at the moment of failure: a rank role
    sitting above the bot is invisible until someone notices their roles didn't
    change, and by then the card has already told them they're a Master.
    """
    me = guild.me
    problems = []
    if me is None:
        return problems
    if not me.guild_permissions.manage_roles:
        problems.append("I don't have the <b>Manage Roles</b> permission, so I can't "
                        "change anyone's roles at all.")
        return problems
    blocked = []
    for rank in config.get("ranks") or []:
        role = guild.get_role(int(rank.get("role_id") or 0))
        if role is not None and role >= me.top_role:
            blocked.append(role.name)
    if blocked:
        problems.append(
            "These rank roles sit above my highest role, so I can't give or take them: "
            + ", ".join(f"<b>{html.escape(name)}</b>" for name in blocked)
            + ". Drag my role above them in <b>Server Settings → Roles</b>.")
    # The clear roles matter too: superseded ones can't be tidied up without the
    # same reach, even though ranks are what people notice.
    unreachable = sum(
        1 for role_id in trial_ranks.slot_of(config.get("trials") or [])
        if (role := guild.get_role(int(role_id))) is not None and role >= me.top_role)
    if unreachable:
        problems.append(f"{unreachable} clear role(s) also sit above my highest role, so "
                        "superseded ones can't be tidied up.")
    # By far the most common cause, and the least obvious: staff sit above the
    # bot, so nothing can be done to them however the rank roles are ordered.
    stuck = sorted(
        {member.top_role.name
         for member in guild.members
         if not member.bot and member.top_role >= me.top_role}
    )
    if stuck:
        problems.append(
            "Anyone whose highest role is "
            + ", ".join(f"<b>{html.escape(name)}</b>" for name in stuck[:8])
            + " is out of my reach entirely. Discord won't let me change <i>any</i> of "
            "their roles, even ones below me. Drag my role above those in "
            "<b>Server Settings → Roles</b>.")
    return problems


def _pilot_html(bot, guild, config: dict) -> str:
    """The rollout board: who is automated, and how the ask is going."""
    stats = _conversion_stats(bot, guild, config)
    warnings = _rank_role_warnings(guild, config)
    warning_html = ("".join(f'<p class="warnline">⚠️ {problem}</p>' for problem in warnings)
                    if warnings else "")
    rows = ""
    for entry in stats["roster"]:
        member = guild.get_member(int(entry["user_id"]))
        name = member.display_name if member else (entry.get("name") or str(entry["user_id"]))
        tag = f"@{member.name}" if member else "left the server"
        when = entry.get("at")
        stamp = when.strftime("%Y-%m-%d %H:%M") if hasattr(when, "strftime") else "—"
        state = entry.get("state") or ""
        blocked = _unreachable_member(guild, member)
        # An enrolled member the bot can't touch is the failure mode that looks
        # like success: their card shows a rank they were never given.
        flag = (f'<div class="warnline small">⚠️ Roles can\'t be changed, '
                f'{html.escape(blocked)}</div>' if blocked and state ==
                trial_ranks.STATE_ENROLLED else "")
        rows += (
            f'<tr data-user="{int(entry["user_id"])}">'
            f'<td>{html.escape(name)}<div class="muted small">{html.escape(tag)}</div>{flag}</td>'
            f'<td>{html.escape(_STATE_LABELS.get(state, state))}</td>'
            f'<td class="muted small">{html.escape(entry.get("source") or "—")}</td>'
            f'<td class="muted small">{stamp}</td>'
            f'<td><button class="ghost pilotdel" data-user="{int(entry["user_id"])}">'
            f'Take off</button></td></tr>'
        )
    rows = rows or '<tr><td colspan="5" class="muted">Nobody yet.</td></tr>'

    announce_id = int(config.get("announce_channel_id") or 0)
    if not announce_id:
        # Nothing chosen yet: start on the admin channel rather than "— none —",
        # since a first announcement wants a quiet room, not the whole server.
        try:
            announce_id = int(bot.guild_config.get(guild.id, "ADMIN") or 0)
        except Exception:  # noqa: BLE001 - a missing setting is not an error here
            announce_id = 0
    posted = int(config.get("announce_message_id") or 0)
    where = guild.get_channel(int(config.get("announce_channel_id") or 0))
    posted_line = (
        f"Currently posted in #{html.escape(where.name)}."
        if where is not None and posted else "Not posted anywhere yet."
    )
    # Where the running commentary goes. Resolved the same way the cog resolves
    # it, so the page names the channel that will actually be written to rather
    # than "— none —" over a working fallback.
    log_id = int(config.get("log_channel_id") or 0)
    log_source = "chosen here"
    if not log_id:
        for key, why in (("E4D_ROLE_LOG", "your role request log"),
                         ("LOG_CHANNEL", "your moderation log")):
            try:
                candidate = int(bot.guild_config.get(guild.id, key) or 0)
            except Exception:  # noqa: BLE001 - an unset key is not an error
                continue
            if candidate and guild.get_channel(candidate) is not None:
                log_id, log_source = candidate, f"defaulting to {why}"
                break

    return f"""
    <div class="explain">
      <p>Right now, people need to opt in to switch to the new system. We can add people
      here manually.</p>
    </div>
    {warning_html}
    <div class="pilotstats">
      <span class="pilotstat"><b>{stats["enrolled"]}</b> converted</span>
      <span class="pilotstat"><b>{stats["read"]}</b> read how it works</span>
      <span class="pilotstat"><b>{stats["dismissed"]}</b> let it time out</span>
      <span class="pilotstat"><b>{stats["waiting"]}</b> asked, no answer</span>
      <span class="pilotstat"><b>{stats["untouched"]}</b> still to change</span>
      <span class="muted small">of {stats["candidates"]} member(s) holding a scoring role</span>
    </div>
    <div class="pilotadd">
      <input id="pilottag" placeholder="Discord user tag, e.g. nikladushkin" autocomplete="off">
      <button id="pilotenrol">Turn trial ranks on for this user</button>
      <span class="muted small">Exact tag only, not a nickname. This edits their roles.</span>
    </div>
    <table class="stats"><thead><tr><th>Who</th><th>Stage</th><th>How</th><th>When</th><th></th></tr></thead>
      <tbody id="pilotrows">{rows}</tbody></table>

    <div class="announcebar">
      <div><b>Announcement</b>
        <div class="muted small">Posts the pinned message with the
        "Check my rank (only I will see)" button. {posted_line}</div></div>
      <select id="announcechannel">{_channel_options(guild, announce_id)}</select>
      <button id="announcepost" class="ghost">Post / update announcement</button>
    </div>

    <div class="announcebar">
      <div><b>Log channel</b>
        <div class="muted small">Enrolments, recalculations, rank checks and consent all get
        reported here, {html.escape(log_source)}.</div></div>
      <select id="triallogchannel">{_channel_options(guild, log_id)}</select>
    </div>"""


def _interest_html(bot, guild, config: dict) -> str:
    """Who would prog what, per raid, against the twelve a group needs.

    A count on its own doesn't answer the only question being asked — "can we
    run this yet" — so every row is drawn against the same twelve slots and
    coloured by how close it is.
    """
    rows = bot.trial_ranks.interest_rows(guild.id)
    buckets = trial_ranks.interest_buckets(guild, config, rows)
    if not buckets:
        return ('<p class="muted">Nobody has pressed <b>"I\'d join a prog for one of those"</b> '
                'yet. The button shows up under the recommendations on someone\'s '
                '<code>/rank</code> card.</p>')

    cards = ""
    for bucket in buckets:
        filled = min(bucket["count"], trial_ranks.GROUP_SIZE)
        pips = ('<span class="pip on"></span>' * filled
                + '<span class="pip"></span>' * (trial_ranks.GROUP_SIZE - filled))
        # Down to the individual clear: "three people want vRG" doesn't tell a
        # raid lead which boss to build the night around.
        by_role = ""
        for entry in bucket["by_role"]:
            width = min(100, round(entry["count"] / trial_ranks.GROUP_SIZE * 100))
            by_role += (
                f'<div class="progclear lvl-{entry["level"]}">'
                f'<span class="progclearname">{html.escape(entry["name"])}</span>'
                f'<span class="progclearbar"><i style="width:{width}%"></i></span>'
                f'<span class="progclearcount">{entry["count"]}/{trial_ranks.GROUP_SIZE}</span>'
                f'</div>'
            )

        names = ""
        for entry in sorted(bucket["members"], key=lambda m: m["name"].lower()):
            member = guild.get_member(entry["user_id"])
            # The stored name is a snapshot from when they pressed; the live
            # member is better when they're still around.
            label = member.display_name if member is not None else entry["name"]
            when = entry.get("at")
            stamp = (f'<span class="muted small"> · {when:%Y-%m-%d}</span>'
                     if hasattr(when, "strftime") else "")
            needs = ", ".join(role["name"] for role in entry.get("roles") or ())
            wants = (f'<span class="progneeds">{html.escape(needs)}</span>' if needs else "")
            names += f'<li>{html.escape(label)}{wants}{stamp}</li>'
        over = (f' <span class="muted small">+{bucket["count"] - trial_ranks.GROUP_SIZE} more</span>'
                if bucket["count"] > trial_ranks.GROUP_SIZE else "")
        cards += f"""
    <details class="progrow lvl-{bucket["level"]}">
      <summary>
        <span class="progname">{html.escape(bucket["name"])}</span>
        <span class="progpips">{pips}</span>
        <span class="progcount">{bucket["count"]}/{trial_ranks.GROUP_SIZE}</span>{over}
      </summary>
      <div class="progbody">
        <div class="progclears">{by_role}</div>
        <ul class="proglist">{names}</ul>
      </div>
    </details>"""

    ready = sum(1 for b in buckets if b["level"] == trial_ranks.LEVEL_READY)
    warm = sum(1 for b in buckets if b["level"] == trial_ranks.LEVEL_WARM)
    return f"""
    <div class="explain">
      <p>One press of <b>"I'd join a prog for one of those"</b> on a <code>/rank</code> card
      registers everything that card was recommending. Interest lasts for
      {trial_ranks.INTEREST_TTL_DAYS} days, pressing the button again restarts the duration.</p>
    </div>
    <div class="pilotstats">
      <span class="pilotstat"><b>{ready}</b> ready to run</span>
      <span class="pilotstat"><b>{warm}</b> getting there</span>
      <span class="pilotstat"><b>{len(rows)}</b> people signed up in total</span>
    </div>
    <div class="proggrid">{cards}</div>"""


def _suggested_note(guild, config: dict) -> str:
    """Say when slot boxes are showing a built-in suggestion, not a decision."""
    pending = [row for row in trial_ranks.unpriced_slots(guild, config) if row["suggested"]]
    if not pending:
        return ""
    return '<p class="muted small">Roles pre-filled with suggested values</p>'


def _unpriced_warning(guild, config: dict) -> str:
    """Slots you've mapped but never priced — they score nothing.

    Replaces two checks that both asked the divider sections what *should* have
    points. Now that nothing is read from dividers, the only unanswered question
    left is the one you created yourself by mapping a role to a trial.
    """
    missing = trial_ranks.unpriced_slots(guild, config)
    if not missing:
        return ""
    listed = ", ".join(
        f'<b>{html.escape(row["name"])}</b>'
        + (f' <span class="muted">(suggest {row["suggested"]})</span>'
           if row["suggested"] else "")
        for row in missing[:10])
    more = f" and {len(missing) - 10} more" if len(missing) > 10 else ""
    return (f'<p class="warnline">⚠️ {len(missing)} mapped clear(s) are worth 0 points, '
            f'so they score nothing: {listed}{more}. Price them under '
            f'<b>Trials Setup</b>.</p>')


def _trials_html(bot, guild, scope: str, viewer_id: int = 0) -> str:
    config = bot.trial_ranks.get(guild.id)
    points = config.get("points") or {}
    cog = bot.get_cog("trial_ranks")
    last = (cog.last_run.get(guild.id) if cog else None) or {}
    # Only says anything when there is something to say. "Not run yet this
    # session" was reporting in-memory state that resets on restart, which told
    # you nothing about whether the system works.
    last_line = ""
    if last and last.get("members"):
        last_line = (f"Last recalculation: {last['members']} member(s), "
                     f"{last.get('granted', 0)} rank(s) granted, "
                     f"{last.get('removed', 0)} replaced.")
    elif last and last.get("skipped"):
        last_line = f"Last recalculation did nothing: {last['skipped']}."
    total_possible = sum(int(v) for v in points.values()) if points else 0

    # One panel at a time, picked from the sidebar. Six stacked accordions meant
    # scrolling past a 46-row score table to reach the rollout board; the cogs
    # page already solved this shape, so this borrows it rather than inventing a
    # second navigation idiom. Hidden panels stay in the DOM — Save and Push read
    # every input on the page, so unmounting one would quietly drop its values.
    enrolled = len(bot.trial_ranks.enrolled_ids(guild.id))
    candidates = _conversion_stats(bot, guild, config)["candidates"]
    panels = [
        ("ranks", "🏆", "Ranks", f'{len(config.get("ranks") or [])} ranks'),
        ("pilot", "👥", "Users", f"{enrolled}/{candidates}"),
        ("interest", "🔥", "Prog interest", ""),
        ("trialmap", "🗺️", "Trials Setup", f"{len(config.get('trials') or [])} trials"),
        ("sandbox", "🧪", "Preview", ""),
    ]
    presets = bot.trial_ranks.presets(guild.id)
    preset_options = ('<option value="" data-author="">— pick a preset —</option>' + "".join(
        f'<option value="{html.escape(p["name"])}" '
        f'data-author="{int(p.get("author_id") or 0)}">{html.escape(p["name"])}'
        f' ({len(p.get("points") or {})} priced'
        + (f' · {html.escape(p["author_name"])}' if p.get("author_name") else "")
        + ')</option>' for p in presets))

    nav = "".join(
        f'<a class="trialnavitem{" active" if key == "ranks" else ""}" '
        f'href="#{key}" data-panel="{key}">'
        f'<span class="navemoji">{emoji}</span>'
        f'<span class="navlabel">{html.escape(label)}</span>'
        f'<span class="navhint">{html.escape(hint)}</span></a>'
        for key, emoji, label, hint in panels
    )

    return f"""
<div class="trialspage" data-guild="{guild.id}" data-uid="{viewer_id}">
  <script type="application/json" id="all-roles">{_json_options(_sorted_roles(guild), "@")}</script>
  <script type="application/json" id="trial-suggestions">{_json_dumps(trial_ranks.suggest_trials(guild))}</script>
  <script type="application/json" id="trial-slots">{_json_dumps(list(trial_ranks.SLOTS))}</script>
  <h1>Trial ranking</h1>
  <p class="muted">Clears and achievements are worth points, ranks are assigned automatically
  upon reaching a threshold. Only the people under <b>Users</b> are affected.</p>
  <div class="trialbar">
    <label class="switch"><input type="checkbox" id="trialsexclusive"
      {"checked" if config.get("exclusive", True) else ""}> only hold the highest rank</label>
    <span class="muted small">{len(points)} priced role(s) · {total_possible} points on the board</span>
    {'<button id="trialpush">Push to live</button>' if scope == panel_access.SCOPE_OWNER else ''}
    <button id="trialsave" class="ghost">Save draft</button>
    <button id="trialrun" class="ghost"
      title="Re-apply the saved setup to everyone enrolled, without saving what's on screen"
      >Recalculate now</button>
    <a class="chip" href="/guild/{guild.id}/trials.png" target="_blank" rel="noopener"
       title="A shareable chart of the current values">🖼 Chart</a>
  </div>
  <div class="presetbar">
    <span class="muted small">Presets</span>
    <select id="presetpick">{preset_options}</select>
    <button id="presetload" class="ghost">Load</button>
    <button id="presetsave" class="ghost" hidden>Save</button>
    <button id="presetsavenew" class="ghost">Save as new</button>
    <button id="presetdel" class="ghost" hidden>Delete</button>
  </div>
  {_unpriced_warning(guild, config)}
  {_suggested_note(guild, config)}

  <div class="triallayout">
    <aside class="sidebar trialnav">{nav}
      {f'<p class="muted small navfoot">{html.escape(last_line)}</p>' if last_line else ''}
    </aside>
    <main class="content">

      <section class="trialpanel" data-panel="ranks">
        <h2 class="panelhead">Ranks</h2>
        <div class="explain">
          <p>Points come from Clears and Achievements. When someone reaches a rank's requirement,
          the bot gives them that rank's role and takes away the previous one.</p>
        </div>
        <div class="ladder" id="rankrows">{_rank_rows(bot, guild, config)}</div>
        <div class="trialactions"><button class="ghost" id="addrank">+ Add a rank</button></div>
      </section>

      <section class="trialpanel" data-panel="pilot" hidden>
        <h2 class="panelhead">Users</h2>
        {_pilot_html(bot, guild, config)}
      </section>

      <section class="trialpanel" data-panel="interest" hidden>
        <h2 class="panelhead">Prog interest</h2>
        {_interest_html(bot, guild, config)}
      </section>

      <section class="trialpanel" data-panel="trialmap" hidden>
        <h2 class="panelhead">Trials Setup</h2>
        {_trial_map_html(guild, config)}
      </section>

      <section class="trialpanel" data-panel="sandbox" hidden>
        <h2 class="panelhead">Preview</h2>
        <div class="sandbox">
          <div class="explain"><p>Simulates ranks for the server with the selected ruleset,
          including edits you haven't saved.</p></div>
          <div class="sandboxrow">
            <button id="trialpreviewall">Recalculate ranks</button>
          </div>
          <div class="previewfilters" hidden>
            <input id="pvname" placeholder="Filter by name or username…" autocomplete="off">
            <select id="pvrank"><option value="">Any rank</option></select>
            <select id="pvrole"><option value="">Any clear role</option></select>
            <select id="pvmove">
              <option value="">Everyone</option>
              <option value="up">Promoted only</option>
              <option value="down">Demoted only</option>
              <option value="any">Changed only</option>
            </select>
            <span class="muted small" id="pvcount"></span>
          </div>
          <div id="previewout"></div>
        </div>
      </section>

    </main>
  </div>
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Change log page
# --------------------------------------------------------------------------- #
def _value_cell(value) -> str:
    """Render a stored old/new value compactly."""
    if value is None:
        return '<span class="muted">—</span>'
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        if not value:
            return '<span class="muted">(empty)</span>'
        return html.escape(", ".join(str(v) for v in value)[:120])
    text_value = str(value)
    return html.escape(text_value if len(text_value) <= 120 else text_value[:120] + "…")


def _log_html(bot, guild, data: dict, scope: str, *, kind: str = "", actor: str = "",
              allowed: list = None) -> str:
    base = f"/guild/{guild.id}/log?kind={html.escape(kind)}&amp;actor={html.escape(actor)}"
    rows = ""
    for entry in data["rows"]:
        when = entry.get("at")
        stamp = when.strftime("%Y-%m-%d %H:%M") if hasattr(when, "strftime") else "—"
        who = html.escape(entry.get("actor_name") or "unknown")
        if entry.get("actor_is_owner"):
            who += ' <span class="muted small">(owner)</span>'
        rows += (
            f'<tr><td class="muted small">{stamp}</td>'
            f"<td>{who}</td>"
            f'<td><span class="chip static">{html.escape(audit_log.KIND_LABELS.get(entry.get("kind"), entry.get("kind") or "?"))}</span></td>'
            f"<td><code>{html.escape(str(entry.get('target') or ''))}</code></td>"
            f'<td class="muted">{_value_cell(entry.get("old"))}</td>'
            f"<td>{_value_cell(entry.get('new'))}</td></tr>"
        )
    rows = rows or '<tr><td colspan="6" class="muted">Nothing recorded yet.</td></tr>'

    allowed = allowed if allowed is not None else list(audit_log.KIND_LABELS)
    kind_options = '<option value="">All kinds</option>' + "".join(
        f'<option value="{key}"{" selected" if key == kind else ""}>'
        f'{html.escape(audit_log.KIND_LABELS.get(key, key))}</option>'
        for key in audit_log.KIND_LABELS if key in allowed
    )
    actor_options = '<option value="">Anyone</option>' + "".join(
        f'<option value="{row["id"]}"{" selected" if str(row["id"]) == actor else ""}>'
        f'{html.escape(row["name"])} ({row["count"]})</option>'
        for row in bot.audit_log.actors(guild.id, allowed,
                                        hide_owner_level=hides_owner_level(scope))
    )

    return f"""
<div class="logpage" data-guild="{guild.id}">
  <div class="statshead">
    <div><h1>Change log <span class="muted">· {data["total"]:,} entr(ies)</span></h1></div>
  </div>
  <p class="muted">Every change made from this panel, newest first, including your own.
  Old and new values are kept so anything can be put back.</p>
  <form class="logfilters" method="get" action="/guild/{guild.id}/log">
    <select name="kind">{kind_options}</select>
    <select name="actor">{actor_options}</select>
    <button type="submit">Filter</button>
  </form>
  <table class="stats"><thead><tr><th>When (UTC)</th><th>Who</th><th>What</th><th>Target</th>
    <th>Was</th><th>Now</th></tr></thead><tbody>{rows}</tbody></table>
  {_pager(base, "p", data["page"], data["pages"])}
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Stats page
# --------------------------------------------------------------------------- #
def _pager(base: str, param: str, page: int, pages: int) -> str:
    """Prev/Next links that keep every other query parameter intact."""
    if pages <= 1:
        return ""
    prev_link = (
        f'<a href="{base}&amp;{param}={page - 1}">← prev</a>' if page > 1 else '<span class="muted">← prev</span>'
    )
    next_link = (
        f'<a href="{base}&amp;{param}={page + 1}">next →</a>' if page < pages else '<span class="muted">next →</span>'
    )
    return f'<div class="pager">{prev_link}<span class="muted small">page {page} / {pages}</span>{next_link}</div>'


def _rank_table(rows: list[dict], labels: dict, *, start: int, head: str) -> str:
    """A ranked count table (top users / top channels), numbered across pages."""
    if not rows:
        return '<p class="muted">Nothing recorded for this period.</p>'
    body = ""
    for offset, row in enumerate(rows):
        share = f'<div class="rankbar" style="width:{row["share"]:.1f}%"></div>' if row.get("share") else ""
        label = labels.get(row["id"], str(row["id"]))
        body += (
            f'<tr><td class="rank">{start + offset}</td>'
            f"<td>{html.escape(label)}{share}</td>"
            f'<td class="num">{row["count"]:,}</td></tr>'
        )
    return (
        f'<table class="stats"><thead><tr><th class="rank">#</th><th>{head}</th>'
        f'<th class="num">Messages</th></tr></thead><tbody>{body}</tbody></table>'
    )


def _with_share(rows: list[dict]) -> list[dict]:
    """Annotate rows with a percentage of the page's top count, for the inline bar."""
    top = max((row["count"] for row in rows), default=0)
    for row in rows:
        row["share"] = (row["count"] / top * 100) if top else 0
    return rows


def _tiles(summary: dict, guild) -> str:
    busiest_day = summary["busiest_day"]
    busiest_hour = summary["busiest_hour"]
    tiles = [
        ("Messages", f"{summary['messages']:,}", "humans only, this period"),
        ("Active people", f"{summary['active_users']:,}", f"of {guild.member_count or '?'} members"),
        ("Messages / day", f"{summary['per_day_avg']:,}", "average over the period"),
        ("Active channels", f"{summary['active_channels']:,}", "with at least one message"),
        (
            "Busiest day",
            html.escape(busiest_day["day"]) if busiest_day else "—",
            f"{busiest_day['count']:,} messages" if busiest_day else "no data",
        ),
        (
            "Busiest hour",
            f"{busiest_hour:02d}:00 UTC" if busiest_hour is not None else "—",
            "across the period",
        ),
        ("Commands run", f"{summary['commands']:,}", "successful invocations"),
        (
            "Joins / leaves",
            f"{summary['joins']:,} / {summary['leaves']:,}",
            f"{summary['kicks']:,} kicked" if summary["kicks"] else "from the audit log",
        ),
    ]
    cards = "".join(
        f'<div class="tile"><span class="tlabel">{html.escape(label)}</span>'
        f'<b class="tvalue">{value}</b><span class="muted small">{html.escape(note)}</span></div>'
        for label, value, note in tiles
    )
    return f'<div class="tiles">{cards}</div>'


def _stats_html(guild, data: dict, users: dict, channels: dict) -> str:
    """``users`` / ``channels`` map the ids on this page to display names."""
    period = data["period"]
    base = f"/guild/{guild.id}/stats?period={period}"
    user_stats, channel_stats, commands = data["users"], data["channels"], data["commands"]

    selector = "".join(
        f'<a class="chip{" on" if key == period else ""}" href="/guild/{guild.id}/stats?period={key}">'
        f"{html.escape(label)}</a>"
        for key, label, _days in stats.PERIODS
    )

    command_rows = "".join(
        f'<tr><td><code>{html.escape(row["command"])}</code></td>'
        f'<td>{html.escape(users.get(row["user_id"]) or row["name"] or str(row["user_id"]))}</td>'
        f'<td class="muted small">{row["when"].strftime("%Y-%m-%d %H:%M") if row["when"] else "—"}</td></tr>'
        for row in commands["rows"]
    ) or '<tr><td colspan="3" class="muted">No commands recorded for this period.</td></tr>'

    top_commands = "".join(
        f'<span class="chip static"><code>{html.escape(str(row["id"]))}</code> {row["count"]:,}</span>'
        for row in data["top_commands"][:10]
    ) or '<span class="muted">Nothing yet.</span>'

    plotted = len(data["per_day"])
    return f"""
<div class="statspage">
  <div class="statshead">
    <div><h1>Server stats <span class="muted">· {html.escape(data["period_label"])}</span></h1></div>
    <div class="chips">{selector}</div>
  </div>

  {_tiles(data["summary"], guild)}

  <h2 class="sh">Messages per day <span class="muted">· humans only · last {plotted} day(s) with data</span></h2>
  {charts.bar_chart(data["per_day"], key="day", tick=lambda d: d[5:])}

  <div class="statsgrid">
    <section>
      <h2 class="sh">Most active people</h2>
      {_rank_table(_with_share(user_stats["rows"]), users,
                   start=(user_stats["page"] - 1) * stats.PAGE_SIZE + 1, head="Member")}
      {_pager(base, "up", user_stats["page"], user_stats["pages"])}
    </section>
    <section>
      <h2 class="sh">Most active channels</h2>
      {_rank_table(_with_share(channel_stats["rows"]), channels,
                   start=(channel_stats["page"] - 1) * stats.PAGE_SIZE + 1, head="Channel")}
      {_pager(base, "cp", channel_stats["page"], channel_stats["pages"])}
    </section>
  </div>

  <h2 class="sh">Activity by hour <span class="muted">· UTC</span></h2>
  {charts.hour_chart(data["per_hour"])}

  <h2 class="sh">Most used commands</h2>
  <div class="chips wrap">{top_commands}</div>

  <h2 class="sh">Command usage log <span class="muted">· {commands["total"]:,} in this period</span></h2>
  <table class="stats"><thead><tr><th>Command</th><th>Who</th><th>When (UTC)</th></tr></thead>
  <tbody>{command_rows}</tbody></table>
  {_pager(base, "mp", commands["page"], commands["pages"])}

  <p class="muted small">Message stats come from the archive of this server's channels; times are
  derived from each record's id. Bots are excluded from message counts.</p>
</div>
"""


def _lang_group(key: str) -> str:
    """Which cog a string belongs to — the prefix it already carries."""
    return key.split("_")[0]


def _lang_html(bot) -> str:
    """The strings editor: a cog at a time, searched server-side.

    Rendering all 597 as live textareas made the page unusable — there was no
    way to *find* anything, only to scroll. One group is rendered at a time and
    search filters the index rather than the DOM.
    """
    entries = bot.lang.all_entries()
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["group"], []).append(entry)
    overridden = sum(1 for e in entries if e["overridden"])

    nav = "".join(
        f'<a class="langnavitem{" active" if i == 0 else ""}" href="#{html.escape(g)}" '
        f'data-group="{html.escape(g)}">'
        f'<span class="navlabel">{html.escape(g.title())}</span>'
        f'<span class="navhint">{len(groups[g])} · '
        f'{sum(1 for e in groups[g] if e["overridden"])} edited</span></a>'
        for i, g in enumerate(sorted(groups))
    )

    panels = ""
    for index, group in enumerate(sorted(groups)):
        rows = ""
        for e in sorted(groups[group], key=lambda x: x["key"]):
            joiner = chr(10)
            value = joiner.join(e["current"]) if e["is_list"] else e["current"]
            default = joiner.join(e["default"]) if e["is_list"] else e["default"]
            fields = "".join(f'<code class="ph">{{{html.escape(f)}}}</code>'
                             for f in e["fields"])
            marks = fields
            if e["is_list"]:
                marks += '<span class="langtag">list</span>'
            if e["overridden"]:
                marks += '<span class="langtag edited">edited</span>'
            preview = value if len(value) <= 110 else value[:110] + "…"
            rows += (
                f'<div class="langrow" data-key="{html.escape(e["key"])}" '
                f'data-list="{1 if e["is_list"] else 0}" '
                f'data-search="{html.escape((e["key"] + " " + value + " " + default).lower())}" '
                f'data-edited="{1 if e["overridden"] else 0}">'
                f'<div class="langmain"><code class="k">{html.escape(e["key"])}</code>'
                f'<div class="langpreview">{html.escape(preview) or "&nbsp;"}</div></div>'
                f'<div class="langmarks">{marks}</div>'
                f'<textarea class="langvalue" hidden>{html.escape(value)}</textarea>'
                f'<pre class="langdefault" hidden>{html.escape(default)}</pre>'
                f'</div>'
            )
        panels += (f'<section class="langpanel" data-group="{html.escape(group)}"'
                   f'{"" if index == 0 else " hidden"}>{rows}</section>')

    return f"""
<div class="langpage">
  <h1>Strings <span class="muted">({len(entries)} · {overridden} edited)</span></h1>
  <p class="muted">Edits apply to the live bot immediately and persist across restarts.
  These are the <b>global</b> values — the wording every server gets unless it overrides it.</p>
  <div class="langbar">
    <input id="langsearch" type="search" autocomplete="off"
      placeholder="Search every string — key or text…">
    <label class="switch"><input type="checkbox" id="langedited"> edited only</label>
    <span class="muted small" id="langcount"></span>
  </div>
  <div class="langlayout">
    <aside class="sidebar langnav">{nav}</aside>
    <main class="content langlist">{panels}</main>
  </div>
</div>
<div class="langdrawer" id="langdrawer" hidden>
  <div class="drawerhead">
    <code class="k" id="drawerkey"></code>
    <button class="ghost" id="drawerclose">×</button>
  </div>
  <div class="drawerbody">
    <div id="drawerph" class="drawerph"></div>
    <textarea id="drawervalue" rows="8" spellcheck="false"></textarea>
    <div id="drawerwarn" class="drawerwarn" hidden></div>
    <details class="def"><summary>default</summary><pre id="drawerdefault"></pre></details>
  </div>
  <div class="drawerfoot">
    <button id="drawersave">Save</button>
    <button id="drawerreset" class="ghost">Reset to default</button>
    <span class="muted small" id="drawerlen"></span>
  </div>
</div>
<p id="status" class="status"></p>
"""


# --------------------------------------------------------------------------- #
#  Page handlers
# --------------------------------------------------------------------------- #
async def login(request: web.Request):
    state = secrets.token_urlsafe(24)
    response = web.HTTPFound(auth.authorize_url(state))
    _set_cookie(response, auth.STATE_COOKIE, auth.sign({"s": state}), max_age=600)
    raise response


async def oauth_callback(request: web.Request):
    code = request.query.get("code")
    state = request.query.get("state")
    saved = auth.unsign(request.cookies.get(auth.STATE_COOKIE), max_age=600)
    if not code or not state or not saved or saved.get("s") != state:
        return web.Response(status=400, text="Invalid OAuth state.", content_type="text/plain")
    user = await auth.exchange_code(code)
    if not user:
        return web.Response(status=400, text="OAuth exchange failed.", content_type="text/plain")
    uid = int(user["id"])
    bot = request.app["bot"]
    # Anyone with access to at least one guild may hold a session; what they can
    # then reach is decided per request by require_scope. Owners short-circuit.
    if not bot.visibility.is_owner(uid) and not await accessible_guilds(bot, uid):
        return web.Response(
            status=403,
            text=(
                "No panel access.\n\n"
                "This account isn't an admin of any server this bot is in. Access needs either "
                "the Manage Server permission in that server, or a role the bot owner has granted "
                "panel access to.\n\n"
                "If you were just given a role or permission, log in again — access is read fresh "
                "at each login."
            ),
            content_type="text/plain",
        )
    # Record the sign-in wherever it grants access, so each server's log shows
    # who has been in its panel. Quiet about repeats: signing in twice in an
    # hour isn't two events worth reading.
    try:
        who = user.get("global_name") or user.get("username") or str(uid)
        for guild, scope in await accessible_guilds(bot, uid):
            bot.audit_log.record(
                guild.id, uid, who, audit_log.KIND_LOGIN, "panel sign-in",
                None, scope, is_owner=(scope == panel_access.SCOPE_OWNER),
                once_within=LOGIN_QUIET_PERIOD,
            )
    except Exception:  # noqa: BLE001 - logging must never block a login
        pass

    response = web.HTTPFound("/")
    _set_cookie(
        response,
        auth.SESSION_COOKIE,
        auth.make_session(uid, user.get("username", "")),
        max_age=auth.SESSION_MAX_AGE,
    )
    response.del_cookie(auth.STATE_COOKIE, path="/")
    raise response


async def logout(request: web.Request):
    response = web.HTTPFound("/login")
    response.del_cookie(auth.SESSION_COOKIE, path="/")
    raise response


async def dashboard(request: web.Request):
    """Everyone with any access lands here; the list is filtered to their servers."""
    uid = _session_user(request)
    if uid is None:
        raise web.HTTPFound("/login")
    bot = request.app["bot"]
    entries = await accessible_guilds(bot, uid)
    scope = panel_access.SCOPE_OWNER if bot.visibility.is_owner(uid) else panel_access.highest(
        *[s for _g, s in entries], panel_access.SCOPE_NONE
    )
    if not entries and scope != panel_access.SCOPE_OWNER:
        return _page(
            "No access",
            '<h1>No servers</h1><p class="muted">Your Discord account has no panel access to any '
            "server this bot is in. Ask the bot owner to grant your role access.</p>",
            scope=scope,
        )
    return _page("Dashboard", _dashboard_html(bot, entries, scope), scope=scope)


@require_scope(panel_access.SCOPE_FULL)
async def guild_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(guild.name, _guild_html(bot, guild, scope), scope=scope, guild=guild, current="cogs")


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_settings_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · settings", _settings_html(bot, guild, scope),
                 scope=scope, guild=guild, current="settings")


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_events_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · events", _events_html(bot, guild, scope),
                 scope=scope, guild=guild, current="events")


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_trials_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · trial ranks",
                 _trials_html(bot, guild, scope, request.get("uid") or 0),
                 scope=scope, guild=guild, current="trials")


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_trials_image(request: web.Request):
    """The current setup as a shareable PNG.

    Rendering is CPU work in Pillow, so it goes to a worker thread rather than
    stalling the bot's event loop.
    """
    bot, guild = request.app["bot"], request["guild"]
    config = bot.trial_ranks.get(guild.id)
    try:
        data = await bot.loop.run_in_executor(
            None, functools.partial(trial_image.build, guild, config))
    except Exception as error:  # noqa: BLE001 - report instead of a 500 page
        return web.Response(status=500, text=f"Could not draw the chart: {error}",
                            content_type="text/plain")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return web.Response(
        body=data, content_type="image/png",
        headers={"Content-Disposition":
                 f'inline; filename="trial-ranks-{stamp}.png"'},
    )


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_rank_image(request: web.Request):
    """Serve one rank's badge for the panel's preview (behind the panel's auth)."""
    bot, guild = request.app["bot"], request["guild"]
    try:
        role_id = int(request.match_info["role_id"])
    except (TypeError, ValueError):
        return web.Response(status=404, text="No such rank.", content_type="text/plain")
    picture = bot.trial_ranks.image(guild.id, role_id)
    if not picture or not picture.get("data"):
        return web.Response(status=404, text="No picture.", content_type="text/plain")
    return web.Response(body=bytes(picture["data"]),
                        content_type=picture.get("content_type") or "image/png",
                        headers={"Cache-Control": "private, max-age=60"})


# What a badge is allowed to be. Pillow decides, not the filename or the
# browser's content type — both are supplied by whoever is uploading.
_IMAGE_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg",
                  "WEBP": "image/webp", "GIF": "image/gif"}


@require_scope(panel_access.SCOPE_CONFIG)
async def api_guild_rank_image(request: web.Request):
    """Upload (POST) or clear (DELETE) the badge for one rank role."""
    bot, guild = request.app["bot"], request["guild"]
    try:
        role_id = int(request.match_info["role_id"])
    except (TypeError, ValueError):
        return _bad("That isn't a role.")
    if guild.get_role(role_id) is None:
        return _bad("That role isn't in this server.")

    if request.method == "DELETE":
        bot.trial_ranks.clear_image(guild.id, role_id)
        await _record_change(request, audit_log.KIND_TRIAL, f"rank picture {role_id}",
                             "set", None, "Rank picture removed")
        return web.json_response({"ok": True})

    reader = await request.multipart()
    field = await reader.next()
    while field is not None and field.name != "image":
        field = await reader.next()
    if field is None:
        return _bad("No image was sent.")
    data = b""
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        data += chunk
        if len(data) > trial_ranks.MAX_IMAGE_BYTES:
            return _bad(f"Keep the picture under "
                        f"{trial_ranks.MAX_IMAGE_BYTES // 1024} KB — it's a small badge.")
    if not data:
        return _bad("That file was empty.")
    # Decode it before storing it: this ends up attached to a Discord message,
    # so "the browser said it was a PNG" is not good enough.
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
            image_format = probe.format
    except Exception:  # noqa: BLE001 - any failure means it isn't an image
        return _bad("That doesn't look like an image file.")
    content_type = _IMAGE_FORMATS.get(image_format or "")
    if content_type is None:
        return _bad("Use a PNG, JPEG, WEBP or GIF.")

    bot.trial_ranks.set_image(guild.id, role_id, data, content_type)
    await _record_change(request, audit_log.KIND_TRIAL, f"rank picture {role_id}",
                         None, f"{len(data) // 1024} KB {image_format}",
                         "Rank picture uploaded")
    return web.json_response({"ok": True, "url": f"/guild/{guild.id}/trials/image/{role_id}.png"})


@require_scope(panel_access.SCOPE_CONFIG)
async def api_guild_trials(request: web.Request):
    """Save the trial-ranking setup, or recalculate now.

    Body: {action: "save"|"run", points?, ranks?, enabled?, exclusive?}.
    """
    bot, guild = request.app["bot"], request["guild"]
    data = await request.json()
    action = data.get("action")

    # ---- dry runs: score against the weights in the browser, touch nothing ----
    if action in ("preview", "preview_all"):
        try:
            points = trial_ranks.validate_points(data.get("points"), guild=guild)
            ranks = trial_ranks.validate_ranks(data.get("ranks"), guild=guild)
            trials = trial_ranks.validate_trials(data.get("trials"), guild=guild)
        except (trial_ranks.TrialError, validate.ValidationError) as error:
            return _bad(error)

        def row_for(member):
            held = {role.id for role in member.roles}
            # Preview the tidied state: what they'd have after the weaker clears
            # come off, so nobody has to clean up the server before the numbers
            # make sense.
            dropped = trial_ranks.superseded(held, trials)
            score = trial_ranks.score_for(held, points, trials=trials)
            projected = trial_ranks.rank_for(score, ranks)
            # What they hold now, so a re-balance shows movement rather than
            # just a number.
            current_rank = next((rank for rank in ranks if rank["role_id"] in held), None)
            current = (current_rank or {}).get("name")
            # Promotion or demotion, by what the rank costs — the only ordering
            # ranks have. Without this the table can say "changed" but not which
            # way, which is the thing you actually want to see after a rebalance.
            was_at = int((current_rank or {}).get("min_points") or 0)
            now_at = int((projected or {}).get("min_points") or 0)
            if current_rank is None and projected is None:
                direction = ""
            elif current_rank is None:
                direction = "up"
            elif projected is None:
                direction = "down"
            else:
                direction = "up" if now_at > was_at else ("down" if now_at < was_at else "")
            return {
                "id": str(member.id),
                "name": member.display_name,
                "tag": member.name,
                "score": score,
                "rank": (projected or {}).get("name"),
                "current": current,
                "changed": (projected or {}).get("name") != current,
                "direction": direction,
                "breakdown": trial_ranks.breakdown_for(guild, held, points, trials),
                "cleanup": len(dropped),
            }

        if action == "preview":
            names = data.get("names") or []
            if not isinstance(names, list):
                return _bad("Give a list of names.")
            rows = []
            for found in trial_ranks.find_members(guild, names):
                if found["member"] is None:
                    rows.append({"query": found["query"], "missing": True})
                else:
                    rows.append({**row_for(found["member"]), "query": found["query"]})
            return web.json_response({"ok": True, "rows": rows})

        # preview_all is deliberately on-demand: it walks every member, so it
        # runs when asked for and never on page load.
        rows = [row_for(member) for member in guild.members if not member.bot]
        rows = [row for row in rows if row["score"] > 0]
        rows.sort(key=lambda row: (-row["score"], row["name"].lower()))
        return web.json_response({
            "ok": True, "rows": rows[:500], "total": len(rows),
            "moving": sum(1 for row in rows if row["changed"]),
        })

    if action == "log_channel":
        try:
            channel_id = int(data.get("channel_id") or 0)
        except (TypeError, ValueError):
            return _bad("That isn't a channel id.")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel_id and channel is None:
            return _bad("That channel isn't in this server.")
        if channel is not None and not channel.permissions_for(guild.me).send_messages:
            return _bad(f"I can't post in #{channel.name}.")
        was = int(bot.trial_ranks.get(guild.id).get("log_channel_id") or 0)
        bot.trial_ranks.save(guild.id, {"log_channel_id": channel_id})
        await _record_change(
            request, audit_log.KIND_TRIAL, "log channel",
            f"#{getattr(guild.get_channel(was), 'name', was)}" if was else None,
            f"#{channel.name}" if channel else None,
            f"Trial rank log channel set to **#{channel.name}**" if channel
            else "Trial rank log channel cleared")
        return web.json_response({"ok": True,
                                  "channel": channel.name if channel else ""})

    # ---- the rollout: who the automation is allowed to touch ----
    if action in ("enrol", "unenrol", "announce"):
        cog = bot.get_cog("trial_ranks")
        if cog is None:
            return _bad("The trial_ranks cog isn't loaded.")

        if action == "enrol":
            tag = str(data.get("tag") or "").strip()
            if not tag:
                return _bad("Give a Discord user tag.")
            member = trial_ranks.find_by_tag(guild, tag)
            if member is None:
                return _bad(f"No member with the tag '{tag}' — it has to be the exact "
                            "account tag, not a nickname.")
            if bot.trial_ranks.is_enrolled(guild.id, member.id):
                return _bad(f"{member.display_name} is already on the new system.")
            actor = guild.get_member(request.get("uid")) if request.get("uid") else None
            outcome = await cog.enrol(member, source="panel", actor=actor)
            await _record_change(
                request, audit_log.KIND_TRIAL, f"enrol {member.name}", None, "enrolled",
                f"Trial ranks turned on for **{member.display_name}**")
            return web.json_response({
                "ok": True,
                "member": {"id": str(member.id), "name": member.display_name,
                           "tag": member.name},
                "score": outcome["score"], "rank": outcome["rank_name"],
                "cleared": outcome["cleared"], "granted": outcome["granted"],
                # A rank that was worked out but couldn't be applied is a
                # failure, and saying "done ✓" over it is how it went unnoticed.
                "errors": outcome.get("errors") or [],
            })

        if action == "unenrol":
            try:
                user_id = int(data.get("user_id") or 0)
            except (TypeError, ValueError):
                return _bad("That isn't a user id.")
            if not user_id:
                return _bad("Which user?")
            bot.trial_ranks.forget(guild.id, user_id)
            member = guild.get_member(user_id)
            await _record_change(
                request, audit_log.KIND_TRIAL, f"unenrol {user_id}", "enrolled", None,
                f"Trial ranks turned off for **{member.display_name if member else user_id}**")
            return web.json_response({"ok": True})

        # ---- announce: posts into a live channel, so it only ever happens here ----
        try:
            channel_id = int(data.get("channel_id") or 0)
        except (TypeError, ValueError):
            return _bad("That isn't a channel id.")
        channel = guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return _bad("Pick a text channel to post the announcement in.")
        permissions = channel.permissions_for(guild.me)
        if not (permissions.send_messages and permissions.view_channel):
            return _bad(f"I can't post in #{channel.name}.")
        try:
            message = await cog.post_announcement(guild, channel)
        except discord.HTTPException as error:
            return _bad(f"Discord refused the post: {error}")
        await _record_change(
            request, audit_log.KIND_TRIAL, "announcement", None, f"#{channel.name}",
            f"Trial ranks announcement posted in **#{channel.name}**")
        return web.json_response({"ok": True, "message_id": str(message.id),
                                  "channel": channel.name})

    if action in ("preset_save", "preset_load", "preset_delete"):
        name = str(data.get("name") or "").strip()[:60]
        if not name:
            return _bad("Give the preset a name.")
        if action == "preset_save":
            try:
                clean = {
                    "points": trial_ranks.validate_points(data.get("points"), guild=guild),
                    "ranks": trial_ranks.validate_ranks(data.get("ranks"), guild=guild),
                    "trials": trial_ranks.validate_trials(data.get("trials"), guild=guild),
                }
            except (trial_ranks.TrialError, validate.ValidationError) as error:
                return _bad(error)
            uid = int(request.get("uid") or 0)
            existing = bot.trial_ranks.preset(guild.id, name)
            # Whoever made a preset keeps it. Someone else has to save their own
            # copy rather than quietly replacing another person's work — and the
            # UI hides the overwrite button, so this is the backstop.
            if existing is not None and int(existing.get("author_id") or 0) not in (0, uid):
                return _bad(f"'{name}' belongs to "
                            f"{existing.get('author_name') or 'someone else'}. "
                            "Save it under a different name.")
            actor = guild.get_member(uid) if uid else None
            bot.trial_ranks.save_preset(
                guild.id, name, clean, author_id=uid,
                author_name=getattr(actor, "display_name", "") or str(uid))
            await _record_change(request, audit_log.KIND_TRIAL, f"preset {name}", None,
                                 f"{len(clean['points'])} priced, {len(clean['ranks'])} ranks",
                                 f"Trial preset **{name}** saved")
            return web.json_response({"ok": True, "name": name})
        if action == "preset_delete":
            uid = int(request.get("uid") or 0)
            existing = bot.trial_ranks.preset(guild.id, name)
            if (existing is not None and request["scope"] != panel_access.SCOPE_OWNER
                    and int(existing.get("author_id") or 0) not in (0, uid)):
                return _bad(f"'{name}' belongs to "
                            f"{existing.get('author_name') or 'someone else'}.")
            bot.trial_ranks.delete_preset(guild.id, name)
            await _record_change(request, audit_log.KIND_TRIAL, f"preset {name}",
                                 "saved", None, f"Trial preset **{name}** deleted")
            return web.json_response({"ok": True})
        preset = bot.trial_ranks.preset(guild.id, name)
        if preset is None:
            return _bad(f"No preset called '{name}'.")
        # Loading only fills the page in. Nothing is stored until Save or Push,
        # so trying a preset can't cost anyone their current setup.
        return web.json_response({"ok": True, "preset": _json_loads_safe({
            "points": preset.get("points") or {},
            "ranks": preset.get("ranks") or [],
            "trials": preset.get("trials") or [],
        })})

    if action in ("run", "push"):
        cog = bot.get_cog("trial_ranks")
        if cog is None:
            return _bad("The trial_ranks cog isn't loaded.")
        # Push writes the weights *and* applies them to everyone at once; that
        # stays with the bot owner.
        if action == "push" and request["scope"] != panel_access.SCOPE_OWNER:
            return _bad("Only the bot owner can push a ruleset live.")
        # "push" saves the weights being previewed, then applies them.
        if action == "push":
            try:
                clean = {
                    "points": trial_ranks.validate_points(data.get("points"), guild=guild),
                    "ranks": trial_ranks.validate_ranks(data.get("ranks"), guild=guild),
                    "trials": trial_ranks.validate_trials(data.get("trials"), guild=guild),
                }
                for rank in clean["ranks"]:
                    validate.assignable_role(guild, rank["role_id"], field=f"rank '{rank['name']}'")
                for flag in ("enabled", "exclusive"):
                    if flag in data:
                        clean[flag] = validate.boolean(data.get(flag), field=flag)
            except (trial_ranks.TrialError, validate.ValidationError) as error:
                return _bad(error)
            was = bot.trial_ranks.get(guild.id)
            bot.trial_ranks.save(guild.id, clean)
            await _record_change(
                request, audit_log.KIND_TRIAL, "setup",
                f"{len(was.get('points') or {})} priced, {len(was.get('ranks') or [])} ranks",
                f"{len(clean['points'])} priced, {len(clean['ranks'])} ranks",
                "Trial ranking pushed live")
        summary = await cog.run_for_guild(guild)
        if action == "run":
            await _record_change(request, audit_log.KIND_TRIAL, "(recalculate)", None, "run",
                                 "Recalculated trial ranks")
        return web.json_response({"ok": True, "summary": summary})

    try:
        clean = {}
        if "points" in data:
            clean["points"] = trial_ranks.validate_points(data.get("points"), guild=guild)
        if "trials" in data:
            clean["trials"] = trial_ranks.validate_trials(data.get("trials"), guild=guild)
        if "ranks" in data:
            ranks = trial_ranks.validate_ranks(data.get("ranks"), guild=guild)
            for rank in ranks:
                validate.assignable_role(guild, rank["role_id"], field=f"rank '{rank['name']}'")
            clean["ranks"] = ranks
        for flag in ("enabled", "exclusive"):
            if flag in data:
                clean[flag] = validate.boolean(data.get(flag), field=flag)
    except (trial_ranks.TrialError, validate.ValidationError) as error:
        return _bad(error)

    was = bot.trial_ranks.get(guild.id)
    bot.trial_ranks.save(guild.id, clean)
    await _record_change(
        request, audit_log.KIND_TRIAL, "setup",
        f"{len(was.get('points') or {})} priced, {len(was.get('ranks') or [])} ranks",
        f"{len(clean.get('points', was.get('points') or {}))} priced, "
        f"{len(clean.get('ranks', was.get('ranks') or []))} ranks",
        "Trial ranking setup changed")
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_OWNER)
async def guild_tribes_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · tribes", _tribes_html(bot, guild, scope),
                 scope=scope, guild=guild, current="tribes")


@require_scope(panel_access.SCOPE_OWNER)
async def api_guild_tribe(request: web.Request):
    """Create / update / delete a tribe, or run the sweep now.

    Body: {action: create|update|delete|run, id?, name?, role_ids?, condition?,
    enabled?, remove_when_unmatched?}.
    """
    bot, guild = request.app["bot"], request["guild"]
    gid = guild.id
    data = await request.json()
    action = data.get("action")

    if action == "run":
        cog = bot.get_cog("tribes")
        if cog is None:
            return _bad("The tribes cog isn't loaded.")
        summary = await cog.run_for_guild(guild)
        await _record_change(request, audit_log.KIND_TRIBE, "(sweep)", None, "run now",
                             "Ran the tribe sweep")
        return web.json_response({"ok": True, "summary": {
            k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in summary.items()}})

    try:
        clean: dict = {}
        if "name" in data or action == "create":
            clean["name"] = validate.text(data.get("name") or "New tribe", field="name",
                                          max_length=validate.MAX_NAME, allow_empty=False)
        if "role_ids" in data or action == "create":
            role_ids = validate.guild_roles(guild, data.get("role_ids") or [], field="roles")
            for role_id in role_ids:
                validate.assignable_role(guild, role_id, field="role")
            clean["role_ids"] = role_ids
        if "condition" in data or action == "create":
            clean["condition"] = tribe_rules.validate_root(
                data.get("condition") or {"type": "all", "children": []}, guild=guild)
        if "mode" in data:
            clean["mode"] = validate.choice(data.get("mode"), tribe_rules.MODES, field="mode")
        if "sources" in data:
            clean["sources"] = tribe_rules.validate_sources(data.get("sources"), guild=guild)
        if "tiers" in data:
            tiers = tribe_rules.validate_tiers(data.get("tiers"), guild=guild)
            for tier in tiers:
                validate.assignable_role(guild, tier["role_id"], field=f"rank '{tier['name']}'")
            clean["tiers"] = tiers
        for flag in ("enabled", "remove_when_unmatched", "exclusive"):
            if flag in data:
                clean[flag] = validate.boolean(data.get(flag), field=flag)
        tribe_id = None
        if action in ("update", "delete"):
            tribe_id = validate.text(data.get("id"), field="tribe id", max_length=64, allow_empty=False)
    except (validate.ValidationError, tribe_rules.RuleError) as error:
        return _bad(error)

    try:
        if action == "create":
            tribe = bot.tribes.create(gid, clean)
            await _record_change(request, audit_log.KIND_TRIBE, clean["name"], None, "created",
                                 f"Tribe **{clean['name']}** created")
            return web.json_response({"ok": True, "id": str(tribe["_id"])})
        if action == "delete":
            existing = next((t for t in bot.tribes.for_guild(gid) if str(t["_id"]) == tribe_id), None)
            bot.tribes.delete(gid, tribe_id)
            await _record_change(request, audit_log.KIND_TRIBE, (existing or {}).get("name", tribe_id),
                                 "existed", None, f"Tribe **{(existing or {}).get('name')}** deleted")
            return web.json_response({"ok": True})
        if action == "update":
            existing = next((t for t in bot.tribes.for_guild(gid) if str(t["_id"]) == tribe_id), None)
            bot.tribes.update(gid, tribe_id, clean)
            await _record_change(
                request, audit_log.KIND_TRIBE, clean.get("name") or (existing or {}).get("name", tribe_id),
                tribe_rules.describe((existing or {}).get("condition") or {}, guild) if existing else None,
                tribe_rules.describe(clean["condition"], guild) if "condition" in clean else None,
                f"Tribe **{clean.get('name') or tribe_id}** edited")
            return web.json_response({"ok": True})
    except (KeyError, TypeError, ValueError) as error:
        return _bad(f"invalid tribe: {error}")
    return web.json_response({"ok": False, "error": "bad request"}, status=400)


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_log_page(request: web.Request):
    """Who changed what, when, and what it was before."""
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    try:
        page = max(1, int(request.query.get("p", 1)))
    except ValueError:
        page = 1
    kind = request.query.get("kind", "")
    actor = request.query.get("actor", "")
    allowed = audit_log.visible_kinds(scope)
    data = await bot.loop.run_in_executor(
        None,
        functools.partial(
            bot.audit_log.page, guild.id, page=page,
            kind=kind if kind in allowed else None,
            actor_id=int(actor) if actor.isdigit() else None,
            allowed_kinds=allowed,
            hide_owner_level=hides_owner_level(scope),
        ),
    )
    return _page(f"{guild.name} · log", _log_html(bot, guild, data, scope, kind=kind, actor=actor, allowed=allowed),
                 scope=scope, guild=guild, current="log")


@require_scope(panel_access.SCOPE_STATS)
async def guild_stats_page(request: web.Request):
    """Activity stats for one guild. The aggregations are blocking pymongo calls,
    so they run in a worker thread — the bot shares this event loop."""
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]

    def _page_number(name: str) -> int:
        try:
            return max(1, int(request.query.get(name, 1)))
        except ValueError:
            return 1

    # Named apart from the panel scope on purpose: reusing `scope` here handed a
    # stats.Scope to the nav builder, which reads it as a permission level, got
    # nothing, and silently dropped every link in the top bar.
    query_scope = stats.Scope(guild)
    data = await bot.loop.run_in_executor(
        None,
        functools.partial(
            stats.collect,
            query_scope,
            stats.normalise_period(request.query.get("period")),
            user_page=_page_number("up"),
            channel_page=_page_number("cp"),
            command_page=_page_number("mp"),
        ),
    )
    # Only the ids actually on screen get resolved (a miss can cost an API call).
    user_ids = [row["id"] for row in data["users"]["rows"]] + [row["user_id"] for row in data["commands"]["rows"]]
    users = await names.resolve_users(bot, guild, user_ids)
    channels = await names.resolve_channels(bot, guild, [row["id"] for row in data["channels"]["rows"]])
    return _page(f"{guild.name} · stats",
                 _stats_html(guild, data, users, channels),
                 scope=scope, guild=guild, current="stats")


@require_owner
async def lang_page(request: web.Request):
    return _page("Strings", _lang_html(request.app["bot"]))


async def _record_change(request: web.Request, kind: str, target: str, old, new, line: str) -> None:
    """Log a configuration change, and DM the owner if someone else made it.

    Everything is logged, owner included, so the history is complete; only
    non-owner changes are worth a DM. Never raises — the write it describes has
    already happened, and a failed log must not turn a successful save into an
    error.
    """
    try:
        bot = request.app["bot"]
        guild = request.get("guild") or bot.get_guild(int(request.match_info["gid"]))
        if guild is None:
            return
        uid = request.get("uid")
        actor = guild.get_member(uid) if uid else None
        is_owner = request.get("scope") == panel_access.SCOPE_OWNER
        bot.audit_log.record(
            guild.id, uid,
            getattr(actor, "display_name", None) or (str(uid) if uid else "unknown"),
            kind, target, old, new, is_owner=is_owner,
        )
        if not is_owner:
            bot.audit_notify.record(guild, actor, line)
    except Exception:  # noqa: BLE001
        pass


def _bad(error, status: int = 200):
    """A validation failure, shaped the way panel.js expects."""
    return web.json_response({"ok": False, "error": str(error)}, status=status)


# --------------------------------------------------------------------------- #
#  JSON API handlers
# --------------------------------------------------------------------------- #
@require_owner
async def api_cog(request: web.Request):
    """Process-wide cog lifecycle. Body: {action: load|reload|unload, cog: <name>}."""
    bot = request.app["bot"]
    data = await request.json()
    action, cog = data.get("action"), data.get("cog")
    if action not in ("load", "reload", "unload") or not cog:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    extension = cog if cog.startswith("cogs.") else f"cogs.{cog}"
    try:
        if action == "reload":
            await bot.reload_extension(extension)
        elif action == "load":
            await bot.load_extension(extension)
        else:
            if extension.endswith(".owner"):
                return web.json_response({"ok": False, "error": "refusing to unload the owner cog"}, status=400)
            await bot.unload_extension(extension)
    except Exception as error:  # noqa: BLE001 — report the load error back to the panel
        return web.json_response({"ok": False, "error": str(error)}, status=200)
    # The command set changed process-wide → re-apply visibility to every guild.
    await bot.command_syncer.sync_all(force=True)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_cog(request: web.Request):
    """Body: {cog: <name>, enabled: bool}."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        cog = validate.text(data.get("cog"), field="cog", max_length=64, allow_empty=False)
        enabled = validate.boolean(data.get("enabled"), field="enabled")
    except validate.ValidationError as error:
        return _bad(error)
    if cog not in {c["name"] for c in _cog_inventory(bot)}:
        return _bad("Unknown cog.")
    was = bot.visibility.cog_enabled(gid, cog)
    bot.visibility.set_cog_enabled(gid, cog, enabled)
    await _record_change(
        request, audit_log.KIND_COG, cog, "enabled" if was else "disabled",
        "enabled" if enabled else "disabled",
        f"Cog **{cog}** {'enabled' if enabled else 'disabled'}",
    )
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_command(request: web.Request):
    """Body: {command: <name>, level: visible|admin|owner}."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        command = validate.text(data.get("command"), field="command", max_length=64, allow_empty=False)
        level = validate.choice(data.get("level"), VALID_LEVELS, field="level")
    except validate.ValidationError as error:
        return _bad(error)
    # Only the bot owner may set or clear the owner level — otherwise a guild
    # admin could lock the owner out of a command, or unlock one for themselves.
    if request["scope"] != panel_access.SCOPE_OWNER:
        if level == LEVEL_OWNER or bot.visibility.stored_level(gid, command) == LEVEL_OWNER:
            return web.json_response({"ok": False, "error": "owner-only setting"}, status=200)
    was = bot.visibility.level(gid, command)
    bot.visibility.set_level(gid, command, level)
    await _record_change(request, audit_log.KIND_COMMAND, command, was, level,
                         f"Command `/{command}` set to **{level}**")
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_cog_level(request: web.Request):
    """Set every command in a cog to one level. Body: {cog, level}.

    ``custom`` is a derived display state, never something you can set — you
    leave it by choosing a real level for the whole cog.
    """
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        cog_name = validate.text(data.get("cog"), field="cog", max_length=64, allow_empty=False)
        level = validate.choice(data.get("level"), VALID_LEVELS, field="level")
    except validate.ValidationError as error:
        return _bad(error)
    cog = bot.cogs.get(cog_name)
    if cog is None:
        return _bad("Unknown cog.")
    # Same rule as single commands: only owners touch the owner level, in
    # either direction.
    if request["scope"] != panel_access.SCOPE_OWNER and level == LEVEL_OWNER:
        return _bad("Only the bot owner can set the owner level.")

    detail = _cog_detail(bot, gid, cog_name)
    was = detail["level"]
    changed = 0
    for command in detail["commands"]:
        if request["scope"] != panel_access.SCOPE_OWNER and command["level"] == LEVEL_OWNER:
            continue  # owner-locked commands stay put for a guild admin
        if command["level"] != level:
            bot.visibility.set_level(gid, command["name"], level)
            changed += 1
    bot.command_syncer.request_sync(gid)
    await _record_change(request, audit_log.KIND_COG_LEVEL, cog_name, was, level,
                         f"Cog **{cog_name}** set to **{level}** ({changed} command(s))")
    return web.json_response({"ok": True, "changed": changed})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_category(request: web.Request):
    """Toggle a whole meta-cog category: body {category, enabled}. Sets every
    (non-core) member cog and resyncs the guild once."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        category = validate.text(data.get("category"), field="category", max_length=64, allow_empty=False)
        enabled = validate.boolean(data.get("enabled"), field="enabled")
    except validate.ValidationError as error:
        return _bad(error)
    members = cog_categories.member_cogs(category)
    if not members:
        return web.json_response({"ok": False, "error": "unknown or empty category"}, status=400)
    for cog in members:
        if cog_categories.is_core(cog):
            continue
        bot.visibility.set_cog_enabled(gid, cog, enabled)
    bot.command_syncer.request_sync(gid)
    # One entry for the whole category rather than one per member cog.
    await _record_change(
        request, audit_log.KIND_CATEGORY, category, None, "enabled" if enabled else "disabled",
        f"Category **{category}** {'enabled' if enabled else 'disabled'} (all its cogs)",
    )
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_feature(request: web.Request):
    """Toggle a passive-listener feature: body {feature, enabled}. No command
    resync needed — features gate listeners, not slash commands."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        feature = validate.text(data.get("feature"), field="feature", max_length=64, allow_empty=False)
        enabled = validate.boolean(data.get("enabled"), field="enabled")
    except validate.ValidationError as error:
        return _bad(error)
    if not any(f["key"] == feature for f in cog_categories.FEATURES):
        return _bad("Unknown feature.")
    was = bot.visibility.feature_enabled(gid, feature)
    bot.visibility.set_feature_enabled(gid, feature, enabled)
    await _record_change(request, audit_log.KIND_FEATURE, feature,
                         "on" if was else "off", "on" if enabled else "off",
                         f"Feature **{feature}** turned {'on' if enabled else 'off'}")
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_param(request: web.Request):
    """Set a per-server command parameter: body {key, value}. Coerced/validated by
    the ParamManager; no command resync needed."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    guild = request["guild"]
    try:
        key = validate.text(data.get("key"), field="key", max_length=64, allow_empty=False)
    except validate.ValidationError as error:
        return _bad(error)
    spec = next((p for p in parameters.PARAMETERS if p["key"] == key), None)
    if spec is None:
        return _bad("Unknown parameter.")
    value = data.get("value")
    # Ids must belong to this guild — the panel is per-guild, so accepting a
    # foreign role/channel id would let one server point at another's.
    try:
        if spec["type"] == "role":
            value = validate.guild_role(guild, value, field=key)
        elif spec["type"] == "channel":
            value = validate.guild_channel(guild, value, field=key)
        elif spec["type"] == "list_role":
            value = validate.guild_roles(guild, value, field=key)
        elif spec["type"] == "list_channel":
            value = validate.guild_channels(guild, value, field=key)
        elif spec["type"] in ("str", "text", "secret"):
            value = validate.text(value, field=key, max_length=validate.MAX_TEXT)
    except validate.ValidationError as error:
        return _bad(error)
    was = bot.params.get(gid, key)
    try:
        bot.params.set(gid, key, value)
    except KeyError:
        return _bad("Unknown parameter.")
    except (ValueError, TypeError) as error:
        return _bad(f"invalid value: {error}")
    # Never write a secret's value into the log.
    logged_old, logged_new = ("(hidden)", "(changed)") if spec["type"] == "secret" else (was, value)
    await _record_change(request, audit_log.KIND_PARAM, key, logged_old, logged_new,
                         f"Parameter `{key}` changed")
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_CONFIG)
async def api_guild_setting(request: web.Request):
    """Set or reset one guild setting: body {key, value} or {key, action:"reset"}.

    Also handles the audit logger's own two destinations, which live in
    guilds.json rather than the guild-config collection.
    """
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    guild = bot.get_guild(gid)
    if guild is None:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)
    data = await request.json()
    key = data.get("key")
    if not key:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)

    if key in ("channel_id", "delete_channel_id"):
        log_cog = bot.get_cog("log")
        if log_cog is None:
            return _bad("The log cog isn't loaded.")
        try:
            channel_id = validate.guild_channel(guild, data.get("value"), field="log channel")
        except validate.ValidationError as error:
            return _bad(error)
        was = (log_cog.guild_log_channels(guild) or {}).get(key, 0)
        log_cog.set_guild_log_channel(guild, key, channel_id)
        await _record_change(request, audit_log.KIND_SETTING, key, was, channel_id,
                             f"Log destination `{key}` changed")
        return web.json_response({"ok": True})

    spec = guild_config.SPECS_BY_KEY.get(key)
    if spec is None:
        return _bad("Unknown setting.")
    was = bot.guild_config.get(gid, key)
    try:
        if data.get("action") == "reset":
            bot.guild_config.reset(gid, key)
            value = guild_config.DEFAULTS.get(key)
        else:
            raw = data.get("value")
            # Channel/role ids are checked against THIS guild, so a foreign id
            # can't be stored (the panel is per-guild by scope alone).
            kind = spec["type"]
            if kind == "channel":
                value = validate.guild_channel(guild, raw, field=spec["label"])
            elif kind == "role":
                value = validate.guild_role(guild, raw, field=spec["label"])
            elif kind == "list_channel":
                value = validate.guild_channels(guild, raw, field=spec["label"])
            elif kind == "list_role":
                value = validate.guild_roles(guild, raw, field=spec["label"])
            elif kind == "message":
                value = validate.snowflake(raw, field=spec["label"])
            elif kind == "emoji":
                value = validate.text(raw, field=spec["label"], max_length=64)
            else:
                value = validate.text(raw, field=spec["label"], max_length=validate.MAX_TEXT)
            bot.guild_config.set(gid, key, value)
    except validate.ValidationError as error:
        return _bad(error)
    except KeyError:
        return _bad("Unknown setting.")
    except (TypeError, ValueError) as error:
        return _bad(f"invalid value: {error}")
    await _record_change(request, audit_log.KIND_SETTING, key, was, value,
                         f"Setting `{key}` changed")
    return web.json_response({"ok": True, "value": value})


@require_scope(panel_access.SCOPE_CONFIG)
async def api_guild_event_rule(request: web.Request):
    """Create / update / delete one event rule.

    Body: {action:"create"|"update"|"delete", id?, event?, channel_id?, message?,
    name?, enabled?, ping_user_ids?, ping_role_ids?}.
    """
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    if bot.get_guild(gid) is None:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)
    data = await request.json()
    action = data.get("action")

    guild = request["guild"]
    try:
        clean: dict = {}
        if "event" in data or action == "create":
            clean["event"] = validate.choice(
                data.get("event") or "member_join", events.selectable_events(), field="event")
        if "name" in data or action == "create":
            clean["name"] = validate.text(data.get("name") or "", field="name",
                                          max_length=validate.MAX_NAME)
        if "message" in data or action == "create":
            clean["message"] = validate.text(data.get("message") or "", field="message",
                                             max_length=validate.MAX_MESSAGE)
        if "channel_id" in data or action == "create":
            clean["channel_id"] = validate.guild_channel(guild, data.get("channel_id"), field="channel")
        if "ping_role_ids" in data:
            clean["ping_role_ids"] = validate.guild_roles(guild, data.get("ping_role_ids"), field="ping roles")
        if "ping_user_ids" in data:
            clean["ping_user_ids"] = validate.snowflake_list(data.get("ping_user_ids"), field="ping users")
        if "enabled" in data:
            clean["enabled"] = validate.boolean(data.get("enabled"), field="enabled")
        rule_id = None
        if action in ("update", "delete"):
            rule_id = validate.text(data.get("id"), field="rule id", max_length=64, allow_empty=False)
    except validate.ValidationError as error:
        return _bad(error)

    try:
        if action == "create":
            rule = bot.event_rules.create(gid, clean)
            await _record_change(request, audit_log.KIND_EVENT_RULE, clean.get("name") or clean["event"],
                                 None, clean.get("event"), f"Event rule **{clean.get('name')}** created")
            return web.json_response({"ok": True, "id": str(rule["_id"])})
        if action == "delete":
            existing = next((r for r in bot.event_rules.for_guild(gid) if str(r["_id"]) == rule_id), None)
            bot.event_rules.delete(gid, rule_id)
            await _record_change(request, audit_log.KIND_EVENT_RULE,
                                 (existing or {}).get("name", rule_id), (existing or {}).get("event"), None,
                                 f"Event rule **{(existing or {}).get('name', rule_id)}** deleted")
            return web.json_response({"ok": True})
        if action == "update":
            existing = next((r for r in bot.event_rules.for_guild(gid) if str(r["_id"]) == rule_id), None)
            bot.event_rules.update(gid, rule_id, clean)
            await _record_change(request, audit_log.KIND_EVENT_RULE,
                                 clean.get("name") or (existing or {}).get("name", rule_id),
                                 (existing or {}).get("event"), clean.get("event"),
                                 f"Event rule **{clean.get('name') or rule_id}** edited")
            return web.json_response({"ok": True})
    except (KeyError, TypeError, ValueError) as error:
        return _bad(f"invalid rule: {error}")
    return web.json_response({"ok": False, "error": "bad request"}, status=400)


@require_owner
async def api_guild_access(request: web.Request):
    """Grant/revoke panel access for a role or user in one guild (owner only).

    Deliberately not delegated to guild admins: whoever can edit this can hand
    out access, so it stays with the bot owner.
    """
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    if bot.get_guild(gid) is None:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)
    guild = bot.get_guild(gid)
    data = await request.json()
    try:
        kind = validate.choice(data.get("kind"), ("role", "user"), field="kind")
        if kind == "role":
            target_id = validate.guild_role(guild, data.get("target_id"), field="role", allow_zero=False)
        else:
            target_id = validate.snowflake(data.get("target_id"), field="user id", allow_zero=False)
        removing = data.get("action") == "remove"
        scope = None if removing else validate.choice(
            data.get("scope"), panel_access.GRANTABLE_SCOPES, field="access level")
    except validate.ValidationError as error:
        return _bad(error)
    try:
        if removing:
            bot.panel_access.remove_grant(gid, kind, target_id)
        else:
            bot.panel_access.set_grant(gid, kind, target_id, scope)
    except ValueError as error:
        return _bad(error)
    await _record_change(request, audit_log.KIND_ACCESS, f"{kind}:{target_id}",
                         None, "removed" if removing else scope,
                         f"Panel access for {kind} `{target_id}` "
                         f"{'removed' if removing else 'set to ' + scope}")
    return web.json_response({"ok": True})


@require_owner
async def api_lang(request: web.Request):
    """Body: {key, action:"reset"} OR {key, value:<text>, is_list:bool}."""
    bot = request.app["bot"]
    data = await request.json()
    key = data.get("key")
    if not key:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    if data.get("action") == "reset":
        bot.lang.reset(key)
        return web.json_response({"ok": True})
    text = data.get("value", "")
    if data.get("is_list"):
        lines = text.replace("\r\n", "\n").split("\n")
        while lines and lines[-1] == "":
            lines.pop()
        value = lines
    else:
        value = text
    error = bot.lang.set(key, value)
    if error:
        return web.json_response({"ok": False, "error": error}, status=200)
    # Advice travels with the success: refusing an edit over style would just
    # teach people to route around the editor.
    return web.json_response({"ok": True, "warnings": bot.lang.warnings(key, value)})


# --------------------------------------------------------------------------- #
#  App factory
# --------------------------------------------------------------------------- #
def create_app(bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.add_routes(
        [
            web.get("/login", login),
            web.get("/oauth/callback", oauth_callback),
            web.get("/logout", logout),
            web.get("/", dashboard),
            web.get("/guild/{gid}", guild_page),
            web.get("/guild/{gid}/stats", guild_stats_page),
            web.get("/guild/{gid}/settings", guild_settings_page),
            web.get("/guild/{gid}/events", guild_events_page),
            web.get("/guild/{gid}/log", guild_log_page),
            web.get("/guild/{gid}/tribes", guild_tribes_page),
            web.get("/guild/{gid}/trials", guild_trials_page),
            web.post("/api/guild/{gid}/trials", api_guild_trials),
            web.get("/guild/{gid}/trials.png", guild_trials_image),
            web.get("/guild/{gid}/trials/image/{role_id}.png", guild_rank_image),
            web.post("/api/guild/{gid}/trials/image/{role_id}", api_guild_rank_image),
            web.delete("/api/guild/{gid}/trials/image/{role_id}", api_guild_rank_image),
            web.post("/api/guild/{gid}/tribe", api_guild_tribe),
            web.post("/api/guild/{gid}/setting", api_guild_setting),
            web.post("/api/guild/{gid}/event-rule", api_guild_event_rule),
            web.post("/api/guild/{gid}/access", api_guild_access),
            web.get("/lang", lang_page),
            web.post("/api/cog", api_cog),
            web.post("/api/guild/{gid}/cog", api_guild_cog),
            web.post("/api/guild/{gid}/cog-level", api_guild_cog_level),
            web.post("/api/guild/{gid}/command", api_guild_command),
            web.post("/api/guild/{gid}/category", api_guild_category),
            web.post("/api/guild/{gid}/feature", api_guild_feature),
            web.post("/api/guild/{gid}/param", api_guild_param),
            web.post("/api/lang", api_lang),
            web.static("/static", os.path.join(os.path.dirname(__file__), "static")),
        ]
    )
    return app
