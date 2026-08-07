"""
aiohttp routes for the control panel (owner phase).

Pages are server-rendered HTML; mutations go through small JSON endpoints called
by ``static/panel.js``. Every route is gated on a signed session whose user id is
in the bot owners list (see ``web/auth.py``). Because the app runs in the bot
process, handlers act on the live bot directly (``request.app["bot"]``).
"""

from __future__ import annotations

import html
import os
import secrets
from functools import wraps

from aiohttp import web

from config.secrets import WEB_PUBLIC_URL
from helpers import cog_categories
from helpers.visibility import LEVEL_ADMIN, LEVEL_OWNER, LEVEL_VISIBLE, VALID_LEVELS
from web import auth

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
    """Wrap a handler so only a logged-in bot owner reaches it."""

    @wraps(handler)
    async def wrapper(request: web.Request):
        uid = _session_user(request)
        bot = request.app["bot"]
        if uid is None:
            raise web.HTTPFound("/login")
        if not bot.visibility.is_owner(uid):
            return web.Response(status=403, text="Not authorised (bot owners only).", content_type="text/plain")
        request["uid"] = uid
        return await handler(request)

    return wrapper


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
def _page(title: str, body: str) -> web.Response:
    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Dodo Control Panel</title>
<link rel="stylesheet" href="/static/panel.css?v={_ASSET_VER}">
</head><body>
<header>
<a href="/" class="brand">🦤 Dodo Control Panel</a>
<nav><a href="/">Dashboard</a><a href="/lang">Strings</a><a href="/logout" class="logout">Log out</a></nav>
</header>
<main>{body}</main>
<script src="/static/panel.js?v={_ASSET_VER}"></script>
</body></html>"""
    return web.Response(text=doc, content_type="text/html")


def _guild_avatar(guild, *, size: int = 64) -> str:
    """A guild's icon <img>, or a lettered placeholder tile. ``size`` is only the
    display size (any int); the source asset uses its default size to avoid
    Discord's power-of-two constraint on Asset.replace()."""
    if guild.icon:
        return f'<img class="glogo" src="{guild.icon.url}" alt="" width="{size}" height="{size}">'
    initial = html.escape((guild.name or "?")[:1].upper())
    return f'<div class="glogo placeholder" style="width:{size}px;height:{size}px">{initial}</div>'


def _dashboard_html(bot) -> str:
    cards = "".join(
        f'<a class="guildcard" href="/guild/{g.id}">'
        f'{_guild_avatar(g)}'
        f'<div class="ginfo"><b>{html.escape(g.name)}</b>'
        f'<span class="muted small">{g.member_count or "?"} members · {g.id}</span></div></a>'
        for g in sorted(bot.guilds, key=lambda g: g.name.lower())
    ) or '<p class="muted">The bot is not in any guilds yet.</p>'

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


def _command_cards(commands: list[dict]) -> str:
    """Each command as a small card with a name, description and level selector."""
    if not commands:
        return ""
    cards = ""
    for cmd in commands:
        options = "".join(
            f'<option value="{lvl}"{" selected" if lvl == cmd["level"] else ""}>{_LEVEL_ICON[lvl]} {lvl}</option>'
            for lvl in VALID_LEVELS
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


def _cog_block(detail: dict, guild, *, toggleable: bool) -> str:
    """One cog inside a category: optional per-cog toggle, passive-feature toggles,
    per-server parameters, and its per-command visibility cards."""
    body = _command_cards(detail["commands"])
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


def _guild_html(bot, guild) -> str:
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
            blocks = "".join(_cog_block(m, guild, toggleable=False) for m in members)
            master = '<span class="muted small">always on</span>'
        else:
            states = [m["enabled"] for m in members]
            state = "on" if all(states) else ("off" if not any(states) else "mixed")
            checked = "checked" if state == "on" else ""
            master = (
                f'<label class="switch master"><input type="checkbox" class="cattoggle" '
                f'data-category="{category["key"]}" data-state="{state}" {checked}> on</label>'
            )
            blocks = "".join(_cog_block(m, guild, toggleable=True) for m in members)

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

        nav_cogs = "".join(
            f'<div class="navcog" data-cog="{html.escape(m["cog"])}">'
            f'<a href="#cog-{html.escape(m["cog"])}">{html.escape(m["cog"])}</a>'
            f'<span class="navbtns">'
            f'<button data-action="reload" data-cog="{html.escape(m["cog"])}" title="Reload">Reload</button>'
            f'<button data-action="unload" data-cog="{html.escape(m["cog"])}" title="Unload">Unload</button>'
            f'</span></div>'
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
    <p class="muted">Toggle a whole category on/off for this server, or expand a cog for its
    features, parameters and per-command visibility (<b>🌐 visible</b> / <b>🛡️ admin</b> /
    <b>🔒 owner</b>). Changes apply to this guild within a few seconds.</p>
    {sections}
  </main>
</div>
<p id="status" class="status"></p>
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


@require_owner
async def dashboard(request: web.Request):
    return _page("Dashboard", _dashboard_html(request.app["bot"]))


@require_owner
async def guild_page(request: web.Request):
    bot = request.app["bot"]
    guild = bot.get_guild(int(request.match_info["gid"]))
    if guild is None:
        return web.Response(status=404, text="Guild not found.", content_type="text/plain")
    return _page(guild.name, _guild_html(bot, guild))


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


@require_owner
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


@require_owner
async def api_guild_command(request: web.Request):
    """Body: {command: <name>, level: visible|admin|owner}."""
    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()
    command, level = data.get("command"), data.get("level")
    if not command or level not in VALID_LEVELS:
        return web.json_response({"ok": False, "error": "bad request"}, status=400)
    bot.visibility.set_level(gid, command, level)
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True})


@require_owner
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


@require_owner
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


@require_owner
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
