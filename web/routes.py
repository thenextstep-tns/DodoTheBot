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

import functools
import html
import os
import secrets
from functools import wraps

from aiohttp import web

import discord

from config import guild_config
from config.secrets import WEB_PUBLIC_URL
from helpers import cog_categories, events, names, panel_access, stats
from helpers.visibility import LEVEL_ADMIN, LEVEL_OWNER, LEVEL_VISIBLE, VALID_LEVELS
from web import auth, charts

_SECURE = WEB_PUBLIC_URL.startswith("https")
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _asset_version() -> str:
    """Newest static-asset mtime, appended to CSS/JS URLs to bust stale caches.
    Recomputed each process start (we restart to deploy), so edits always show."""
    try:
        return str(int(max(os.path.getmtime(os.path.join(_STATIC_DIR, f)) for f in ("panel.css", "panel.js"))))
    except OSError:
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


async def _member_of(bot, guild, user_id):
    """The user's member object in a guild, fetching if the cache misses.

    Membership is the hard gate: someone who isn't in the server gets nothing
    there, no matter what grants exist.
    """
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def resolve_scope(bot, guild, user_id) -> str:
    """This user's panel scope in this guild (``owner`` short-circuits)."""
    if bot.visibility.is_owner(user_id):
        return panel_access.SCOPE_OWNER
    member = await _member_of(bot, guild, user_id)
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
        scope = await resolve_scope(bot, guild, user_id)
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


def _cog_detail(bot, guild_id: int, cog_name: str) -> dict:
    """Per-guild enabled state + command levels for one cog (commands may be empty
    for listener-only cogs like cheese/spam — they're still toggleable)."""
    cog = bot.cogs.get(cog_name)
    commands = []
    if cog is not None:
        for command in sorted(cog.get_commands(), key=lambda c: c.name):
            stored = bot.visibility.stored_level(guild_id, command.name)
            level = stored or (LEVEL_OWNER if command.hidden else LEVEL_VISIBLE)
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
        "commands": commands,
        "features": features,
        "params": bot.params.entries_for_cog(guild_id, cog_name),
    }


# --------------------------------------------------------------------------- #
#  HTML rendering
# --------------------------------------------------------------------------- #
def _page(title: str, body: str, *, scope: str = panel_access.SCOPE_OWNER) -> web.Response:
    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Dodo Control Panel</title>
<link rel="stylesheet" href="/static/panel.css?v={_ASSET_VER}">
</head><body>
<header>
<a href="/" class="brand">🦤 Dodo Control Panel</a>
<nav><a href="/">Dashboard</a>{'<a href="/lang">Strings</a>' if scope == panel_access.SCOPE_OWNER else ""}<a href="/logout" class="logout">Log out</a></nav>
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
<h1>Guilds</h1>
<div class="guildgrid">{cards}</div>
<h1>Cogs <span class="muted">(process-wide — affects every guild)</span></h1>
<table class="cogs"><thead><tr><th>Cog</th><th>State</th><th>Actions</th></tr></thead>
<tbody>{cog_rows}</tbody></table>
<p id="status" class="status"></p>
"""


_LEVEL_ICON = {LEVEL_VISIBLE: "🌐", LEVEL_ADMIN: "🛡️", LEVEL_OWNER: "🔒"}


def _command_cards(commands: list[dict], scope: str = panel_access.SCOPE_OWNER) -> str:
    """Each command as a small card with a name, description and level selector."""
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
        if cmd["level"] == LEVEL_OWNER and scope != panel_access.SCOPE_OWNER:
            # Owner-locked here: show it, but don't let them change it.
            options = f'<option value="{LEVEL_OWNER}" selected>{_LEVEL_ICON[LEVEL_OWNER]} owner</option>'
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
    if ptype in ("role", "channel"):
        source = (guild.roles if ptype == "role" else guild.text_channels) if guild else []
        rows = '<option value="0">— none —</option>'
        for obj in source:
            if getattr(obj, "is_default", lambda: False)():  # skip @everyone
                continue
            rows += f'<option value="{obj.id}"{" selected" if obj.id == value else ""}>{html.escape(obj.name)}</option>'
        return f'<select {common}>{rows}</select>'
    if ptype in ("list_role", "list_channel"):
        source = (guild.roles if ptype == "list_role" else guild.text_channels) if guild else []
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


def _cog_block(detail: dict, guild, *, toggleable: bool, scope: str = panel_access.SCOPE_OWNER) -> str:
    """One cog inside a category: optional per-cog toggle, passive-feature toggles,
    per-server parameters, and its per-command visibility cards."""
    body = _command_cards(detail["commands"], scope)
    if not detail["commands"] and not detail["features"] and not detail["params"]:
        body = '<p class="muted small">No slash commands — passive/listener cog.</p>'
    toggle = (
        f'<label class="switch"><input type="checkbox" class="cogtoggle" {"checked" if detail["enabled"] else ""}> enabled</label>'
        if toggleable else '<span class="muted small">always on</span>'
    )
    return f"""
<div class="cogcard" id="cog-{html.escape(detail["cog"])}" data-cog="{html.escape(detail["cog"])}">
  <div class="coghead"><h3>{html.escape(detail["cog"])}</h3>{toggle}</div>
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
        members = [_cog_detail(bot, guild.id, name) for name in category["present"]]
        if not toggleable:
            # Core: no enable/disable, only per-command visibility for cogs that have commands.
            members = [m for m in members if m["commands"]]
            if not members:
                continue
            blocks = "".join(_cog_block(m, guild, toggleable=False, scope=scope) for m in members)
            master = '<span class="muted small">always on</span>'
        else:
            states = [m["enabled"] for m in members]
            state = "on" if all(states) else ("off" if not any(states) else "mixed")
            checked = "checked" if state == "on" else ""
            master = (
                f'<label class="switch master"><input type="checkbox" class="cattoggle" '
                f'data-category="{category["key"]}" data-state="{state}" {checked}> on</label>'
            )
            blocks = "".join(_cog_block(m, guild, toggleable=True, scope=scope) for m in members)

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
    <div class="chips sidechips">{_nav_chips(guild.id, scope, "cogs")}</div>
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
    features, parameters and per-command visibility (<b>🌐 visible</b> / <b>🛡️ admin</b> /
    <b>🔒 owner</b>). Changes apply to this guild within a few seconds.</p>
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
        source = guild.roles if kind == "list_role" else guild.channels
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
        ("channel_id", "Audit log channel", "Joins, leaves, role changes, edits — the full audit feed."),
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
    <div class="chips">{_nav_chips(guild.id, scope, "settings")}</div>
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
    <div class="chips">{_nav_chips(guild.id, scope, "events")}</div>
  </div>
  <p class="muted">When something happens on this server, post a message — optionally pinging
  people. All {len(catalog)} events this discord.py build dispatches are available.
  {"" if active else "<b>The event rules feature is currently off for this server</b> — turn it on under the event_actions cog on the "}
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


def _stats_html(guild, data: dict, users: dict, channels: dict, scope: str = panel_access.SCOPE_OWNER) -> str:
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
    <div><div class="chips">{_nav_chips(guild.id, scope, "stats")}</div>
      <h1>Server stats <span class="muted">· {html.escape(data["period_label"])}</span></h1></div>
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


def _lang_html(bot) -> str:
    entries = bot.lang.all_entries()
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["group"], []).append(entry)

    overridden = sum(1 for e in entries if e["overridden"])
    sections = ""
    for group in sorted(groups):
        rows = ""
        for e in groups[group]:
            value = "\n".join(e["current"]) if e["is_list"] else e["current"]
            default = "\n".join(e["default"]) if e["is_list"] else e["default"]
            rows_n = min(10, max(1, value.count("\n") + 1))
            fields = (
                '<span class="fields">' + " ".join(f"<code>{{{html.escape(f)}}}</code>" for f in e["fields"]) + "</span>"
                if e["fields"] else ""
            )
            list_note = '<span class="muted"> · list (one item per line)</span>' if e["is_list"] else ""
            badge = '<span class="on">overridden</span>' if e["overridden"] else ""
            rows += f"""
<div class="langrow" data-key="{html.escape(e["key"])}" data-list="{1 if e["is_list"] else 0}"
     data-search="{html.escape((e["key"] + " " + default).lower())}">
  <div class="langhead"><code class="k">{html.escape(e["key"])}</code>{fields}{list_note} {badge}</div>
  <textarea rows="{rows_n}" spellcheck="false">{html.escape(value)}</textarea>
  <details class="def"><summary>default</summary><pre>{html.escape(default)}</pre></details>
  <div class="langbtns"><button data-do="save">Save</button><button data-do="reset" class="ghost">Reset</button></div>
</div>"""
        sections += f'<details class="group"><summary>{html.escape(group)} <span class="muted">({len(groups[group])})</span></summary>{rows}</details>'

    return f"""
<h1>User-facing strings <span class="muted">({len(entries)} strings · {overridden} overridden)</span></h1>
<p class="muted">Edits apply to the live bot immediately and persist across restarts. Keep any
<code>{{placeholder}}</code> shown next to a string — removing one is fine, but adding a new one
the command doesn't provide is rejected. These strings are global (shared by all guilds).</p>
<input id="langsearch" type="search" placeholder="Filter by key or text…" autocomplete="off">
<div id="langlist">{sections}</div>
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
    if not request.app["bot"].visibility.is_owner(uid):
        return web.Response(status=403, text="This panel is for bot owners only.", content_type="text/plain")
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
    return _page(guild.name, _guild_html(bot, guild, scope), scope=scope)


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_settings_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · settings", _settings_html(bot, guild, scope), scope=scope)


@require_scope(panel_access.SCOPE_CONFIG)
async def guild_events_page(request: web.Request):
    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    return _page(f"{guild.name} · events", _events_html(bot, guild, scope), scope=scope)


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

    scope = stats.Scope(guild)
    data = await bot.loop.run_in_executor(
        None,
        functools.partial(
            stats.collect,
            scope,
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
    return _page(f"{guild.name} · stats", _stats_html(guild, data, users, channels, scope), scope=scope)


@require_owner
async def lang_page(request: web.Request):
    return _page("Strings", _lang_html(request.app["bot"]))


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
    cog, enabled = data.get("cog"), bool(data.get("enabled"))
    if not cog:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    bot.visibility.set_cog_enabled(gid, cog, enabled)
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_command(request: web.Request):
    """Body: {command: <name>, level: visible|admin|owner}."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    command, level = data.get("command"), data.get("level")
    if not command or level not in VALID_LEVELS:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    # Only the bot owner may set or clear the owner level — otherwise a guild
    # admin could lock the owner out of a command, or unlock one for themselves.
    if request["scope"] != panel_access.SCOPE_OWNER:
        if level == LEVEL_OWNER or bot.visibility.stored_level(gid, command) == LEVEL_OWNER:
            return web.json_response({"ok": False, "error": "owner-only setting"}, status=200)
    bot.visibility.set_level(gid, command, level)
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_category(request: web.Request):
    """Toggle a whole meta-cog category: body {category, enabled}. Sets every
    (non-core) member cog and resyncs the guild once."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    category, enabled = data.get("category"), bool(data.get("enabled"))
    members = cog_categories.member_cogs(category)
    if not members:
        return web.json_response({"ok": False, "error": "unknown or empty category"}, status=400)
    for cog in members:
        if cog_categories.is_core(cog):
            continue
        bot.visibility.set_cog_enabled(gid, cog, enabled)
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_feature(request: web.Request):
    """Toggle a passive-listener feature: body {feature, enabled}. No command
    resync needed — features gate listeners, not slash commands."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    feature, enabled = data.get("feature"), bool(data.get("enabled"))
    if not feature or not any(f["key"] == feature for f in cog_categories.FEATURES):
        return web.json_response({"ok": False, "error": "unknown feature"}, status=400)
    bot.visibility.set_feature_enabled(gid, feature, enabled)
    return web.json_response({"ok": True})


@require_scope(panel_access.SCOPE_FULL)
async def api_guild_param(request: web.Request):
    """Set a per-server command parameter: body {key, value}. Coerced/validated by
    the ParamManager; no command resync needed."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    key = data.get("key")
    if not key:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    try:
        bot.params.set(gid, key, data.get("value"))
    except KeyError:
        return web.json_response({"ok": False, "error": "unknown parameter"}, status=400)
    except (ValueError, TypeError) as error:
        return web.json_response({"ok": False, "error": f"invalid value: {error}"}, status=200)
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
            return web.json_response({"ok": False, "error": "log cog not loaded"}, status=200)
        try:
            log_cog.set_guild_log_channel(guild, key, int(data.get("value") or 0))
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "invalid channel"}, status=200)
        return web.json_response({"ok": True})

    try:
        if data.get("action") == "reset":
            bot.guild_config.reset(gid, key)
            value = guild_config.DEFAULTS.get(key)
        else:
            value = guild_config.coerce(key, data.get("value"))
            bot.guild_config.set(gid, key, value)
    except KeyError:
        return web.json_response({"ok": False, "error": "unknown setting"}, status=400)
    except (TypeError, ValueError) as error:
        return web.json_response({"ok": False, "error": f"invalid value: {error}"}, status=200)
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

    try:
        if action == "create":
            event = data.get("event") or "member_join"
            if event not in events.selectable_events():
                return web.json_response({"ok": False, "error": "unknown event"}, status=200)
            rule = bot.event_rules.create(gid, {**data, "event": event})
            return web.json_response({"ok": True, "id": str(rule["_id"])})
        if action == "delete":
            bot.event_rules.delete(gid, data["id"])
            return web.json_response({"ok": True})
        if action == "update":
            if "event" in data and data["event"] not in events.selectable_events():
                return web.json_response({"ok": False, "error": "unknown event"}, status=200)
            bot.event_rules.update(gid, data["id"], data)
            return web.json_response({"ok": True})
    except (KeyError, TypeError, ValueError) as error:
        return web.json_response({"ok": False, "error": f"invalid rule: {error}"}, status=200)
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
    data = await request.json()
    kind = data.get("kind")
    try:
        target_id = int(data.get("target_id") or 0)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid id"}, status=200)
    if not target_id:
        return web.json_response({"ok": False, "error": "pick a role or user"}, status=200)
    try:
        if data.get("action") == "remove":
            bot.panel_access.remove_grant(gid, kind, target_id)
        else:
            bot.panel_access.set_grant(gid, kind, target_id, data.get("scope"))
    except ValueError as error:
        return web.json_response({"ok": False, "error": str(error)}, status=200)
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
    return web.json_response({"ok": True})


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
            web.post("/api/guild/{gid}/setting", api_guild_setting),
            web.post("/api/guild/{gid}/event-rule", api_guild_event_rule),
            web.post("/api/guild/{gid}/access", api_guild_access),
            web.get("/lang", lang_page),
            web.post("/api/cog", api_cog),
            web.post("/api/guild/{gid}/cog", api_guild_cog),
            web.post("/api/guild/{gid}/command", api_guild_command),
            web.post("/api/guild/{gid}/category", api_guild_category),
            web.post("/api/guild/{gid}/feature", api_guild_feature),
            web.post("/api/guild/{gid}/param", api_guild_param),
            web.post("/api/lang", api_lang),
            web.static("/static", os.path.join(os.path.dirname(__file__), "static")),
        ]
    )
    return app
