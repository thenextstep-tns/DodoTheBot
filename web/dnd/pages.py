"""
Tabletop panel pages — campaign overview and the entity list.

Kept in its own module rather than appended to ``web/routes.py``, which is
already past three thousand lines; a whole subsystem's pages going in there would
be the last straw. The shared chrome (``_page``, ``require_scope``, the nav) is
imported from ``routes`` — ``create_app`` imports this package inside the
function body, so the cycle never closes at import time.

Server-rendered HTML strings, matching the style and CSS classes of the existing
pages, so this looks native rather than bolted on.
"""

from __future__ import annotations

import html

from aiohttp import web

from helpers import panel_access
from helpers.dnd import parameters as dnd_parameters
from helpers.dnd import registry as dnd_registry
from helpers.dnd import rules
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.world.entity import KIND_FACTION, KIND_NPC, KIND_PC
from helpers.dnd.world.knowledge import KINDS
from web.dnd import access


def _escape(value) -> str:
    return html.escape(str(value))


def _member_name(guild, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    return member.display_name if member else f"User {user_id}"


# --------------------------------------------------------------------------- #
#  Campaign list
# --------------------------------------------------------------------------- #
def _campaign_card(guild, campaign, scope: str, counts: dict) -> str:
    ruleset = rules.get(campaign.ruleset)
    gms = ", ".join(_escape(_member_name(guild, uid)) for uid in campaign.gm_ids) or "—"
    day = campaign.world_time // 1440 + 1
    badge = "GM" if scope == access.CAMPAIGN_GM else "Player"
    return f"""
<div class="cogcard">
  <div class="coghead">
    <div>
      <h3>{_escape(campaign.name)} <span class="chip">{badge}</span></h3>
      <p class="muted small">{_escape(ruleset.label)} · {_escape(campaign.status)} ·
      day {day} · {campaign.seq} events</p>
    </div>
    <a class="navtool" href="/guild/{guild.id}/tabletop/{campaign.id}">Open →</a>
  </div>
  <div class="catbody">
    <p class="muted small"><b>GMs:</b> {gms}</p>
    <p class="muted small"><b>Characters:</b> {counts.get('pcs', 0)} ·
    <b>NPCs:</b> {counts.get('npcs', 0)} · <b>Scenes:</b> {counts.get('scenes', 0)}</p>
    {f'<p class="muted small">{_escape(campaign.settings.get("tone", ""))}</p>'
     if campaign.settings.get("tone") else ""}
  </div>
</div>"""


def campaigns_html(bot, guild, guild_scope: str, viewer_id: int) -> str:
    """The server's campaign list, filtered to what this viewer may see."""
    campaigns = campaigns_for(guild.id).list(include_archived=True)
    visible = access.visible_campaigns(campaigns, viewer_id, guild_scope)

    cards = ""
    for campaign, scope in visible:
        store = campaign_store(guild.id, campaign.id)
        counts = {
            "pcs": store.entities.count({"kind": KIND_PC, "retired": False}),
            "npcs": store.entities.count({"kind": KIND_NPC, "retired": False}),
            "scenes": store.scenes.count(),
        }
        cards += _campaign_card(guild, campaign, scope, counts)

    if not cards:
        hidden = len(campaigns) - len(visible)
        cards = (
            '<p class="muted">No campaigns you can see here. '
            + (f"{hidden} campaign(s) on this server belong to other groups."
               if hidden else "A GM can start one in Discord with <code>/campaign create</code>.")
            + "</p>"
        )

    # Engine settings are for people who can configure the server, not for
    # every player who can see the campaign list.
    can_configure = panel_access.at_least(guild_scope, panel_access.SCOPE_FULL)
    settings = _engine_settings(bot, guild) if can_configure else ""
    script = _dnd_script(guild.id) if can_configure else ""

    enabled = bot.visibility.cog_enabled(guild.id, "dnd")
    # The switch lives in the Engine section below, not on the main cog page —
    # tabletop is filtered out of that page entirely.
    warning = (
        "" if enabled else
        '<p class="muted"><b>The tabletop engine is currently off for this server.</b> '
        + ("Turn it back on under <b>Engine</b> below.</p>" if can_configure
           else "An admin can turn it back on.</p>")
    )
    return f"""
<div class="guildpage">
  <div class="statshead">
    <div><span class="muted">{_escape(guild.name)}</span>
      <h1>Tabletop <span class="muted">· {len(visible)} campaign(s)</span></h1></div>
  </div>
  {warning}
  <p class="muted small">Campaigns are per server and per group: you see the ones you run or
  play in. Anyone with Manage Server sees all of them.</p>
  {cards}
  {settings}
</div>{script}"""


# --------------------------------------------------------------------------- #
#  One campaign
# --------------------------------------------------------------------------- #
_KIND_LABELS = {KIND_PC: "Character", KIND_NPC: "NPC", KIND_FACTION: "Faction"}


def _entity_row(guild, entity, ruleset) -> str:
    owner = (
        _escape(_member_name(guild, entity.owner_id)) if entity.owner_id else '<span class="muted">—</span>'
    )
    stat_summary = " · ".join(f"{label} {value}" for label, value in ruleset.sheet_fields(entity.stats)[:4])
    retired = ' <span class="chip">retired</span>' if entity.retired else ""
    return f"""
<tr>
  <td><b>{_escape(entity.identity.name)}</b>{retired}<br>
      <span class="muted small">{_escape(entity.identity.pronouns)}</span></td>
  <td>{_escape(_KIND_LABELS.get(entity.kind, entity.kind))}</td>
  <td>{_escape(entity.identity.role) or '<span class="muted">—</span>'}</td>
  <td>{owner}</td>
  <td>{_escape(entity.tier)}</td>
  <td class="muted small">{stat_summary}</td>
</tr>"""


def _events_table(store, guild, limit: int = 15) -> str:
    recent = store.events.recent(limit)
    if not recent:
        return '<p class="muted">Nothing has happened yet.</p>'
    rows = ""
    for event in recent:
        detail = ""
        if event.kind == "check":
            detail = (
                f"{event.payload.get('approach', '')} → "
                f"{event.payload.get('degree', '')} "
                f"({event.payload.get('total')} vs DC {event.payload.get('dc')})"
            )
        elif event.payload.get("name"):
            detail = str(event.payload["name"])
        elif event.payload.get("title"):
            detail = str(event.payload["title"])
        rows += (
            f"<tr><td class='muted'>{event.seq}</td>"
            f"<td>{_escape(event.kind)}</td>"
            f"<td class='muted small'>{_escape(detail)}</td></tr>"
        )
    return f"""
<table class="ranktable">
  <thead><tr><th>#</th><th>Event</th><th>Detail</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def campaign_html(bot, guild, campaign, scope: str) -> str:
    """One campaign: its people and its recent history."""
    store = campaign_store(guild.id, campaign.id)
    ruleset = rules.get(campaign.ruleset)
    is_gm = scope == access.CAMPAIGN_GM

    entities = store.entities.list(include_retired=True, limit=200)
    pcs = [e for e in entities if e.kind == KIND_PC]
    others = [e for e in entities if e.kind != KIND_PC]

    def table(rows: list, empty: str) -> str:
        if not rows:
            return f'<p class="muted">{empty}</p>'
        body = "".join(_entity_row(guild, e, ruleset) for e in rows)
        return f"""
<table class="ranktable">
  <thead><tr><th>Name</th><th>Kind</th><th>Role</th><th>Player</th><th>Tier</th><th>Stats</th></tr></thead>
  <tbody>{body}</tbody>
</table>"""

    attribution = getattr(ruleset, "attribution", "")
    day = campaign.world_time // 1440 + 1
    scenes = store.scenes.recent(5)
    scene_lines = "".join(
        f"<li>{_escape(s.title)} <span class='muted small'>· {s.status}</span></li>" for s in scenes
    ) or '<li class="muted">No scenes yet.</li>'

    return f"""
<div class="guildpage">
  <div class="statshead">
    <div><span class="muted">{_escape(guild.name)} ·
      <a href="/guild/{guild.id}/tabletop">Tabletop</a></span>
      <h1>{_escape(campaign.name)}</h1></div>
  </div>
  <div class="chips">
    <span class="chip">{_escape(ruleset.label)}</span>
    <span class="chip">{_escape(campaign.status)}</span>
    <span class="chip">Day {day}</span>
    <span class="chip">{campaign.seq} events</span>
    <span class="chip">{'GM' if scope == access.CAMPAIGN_GM else 'Player'}</span>
  </div>

  <h2>Characters</h2>
  {table(pcs, "Nobody has made a character yet.")}

  <h2>NPCs &amp; factions</h2>
  {table(others, "No NPCs yet — they arrive with the world engine in a later phase.")}

  <h2>Recent scenes</h2>
  <ul>{scene_lines}</ul>

  {_knowledge_section(store, campaign, is_gm)}

  {_canon_section(store, is_gm)}

  <h2>Recent events</h2>
  <p class="muted small">Every change is an event, which is what makes replay and undo possible.</p>
  {_events_table(store, guild)}

  {f'<p class="muted small">{_escape(attribution)}</p>' if attribution else ''}
</div>
{_dnd_script(guild.id, str(campaign.id))}"""


# --------------------------------------------------------------------------- #
#  Engine settings
#
#  These live here rather than on the main guild page because tabletop cogs are
#  filtered out of that page entirely (``helpers/dnd/registry.py``). Removing
#  them from the dashboard without providing this section would have removed the
#  only way to switch the engine off.
# --------------------------------------------------------------------------- #
def _engine_settings(bot, guild) -> str:
    """Cog switches and tabletop parameters, for server admins."""
    toggles = ""
    for cog in sorted(dnd_registry.DND_COGS):
        enabled = bot.visibility.cog_enabled(guild.id, cog)
        loaded = any(ext.endswith(cog) or f".{cog}." in ext for ext in bot.extensions)
        note = "" if loaded else ' <span class="muted small">(not loaded)</span>'
        toggles += (
            f'<div class="featrow"><label>'
            f'<input type="checkbox" class="dndcog" data-cog="{cog}" '
            f'{"checked" if enabled else ""}> <b>{cog}</b>{note}</label></div>'
        )

    rows = ""
    for spec in dnd_parameters.entries(guild.id):
        rows += (
            f'<div class="paramrow"><div><b>{_escape(spec["label"])}</b>'
            f'<div class="muted small">{_escape(spec["description"])}</div></div>'
            f'<div>{_dnd_param_input(spec)}</div></div>'
        )

    return f"""
<div class="cogcard" data-guild="{guild.id}">
  <div class="coghead"><div><h3>&#9881;&#65039; Engine</h3>
  <p class="muted small">Tabletop is managed here, not on the main cog page.</p></div></div>
  <div class="catbody">
    {toggles}
    <div class="fields">{rows}</div>
  </div>
</div>"""


def _dnd_param_input(spec: dict) -> str:
    """A typed control for one tabletop parameter.

    A small local renderer rather than the panel's ``_param_input``: tabletop
    only uses int/float/choice, and the shared one drags in role and channel
    pickers that would need a guild object this section never has a use for.
    """
    key, ptype, value = spec["key"], spec["type"], spec["value"]
    common = f'class="dndparam" data-key="{key}" data-type="{ptype}"'
    if ptype == "choice":
        opts = "".join(
            f'<option value="{c}"{" selected" if c == value else ""}>{c}</option>'
            for c in spec.get("choices", [])
        )
        return f"<select {common}>{opts}</select>"
    if ptype in ("int", "float"):
        step = "1" if ptype == "int" else "any"
        return f'<input type="number" step="{step}" {common} value="{_escape(value)}">'
    if ptype == "bool":
        return f'<input type="checkbox" {common} {"checked" if value else ""}>'
    return f'<input type="text" {common} value="{_escape(value)}">'


# --------------------------------------------------------------------------- #
#  Campaign knowledge
# --------------------------------------------------------------------------- #
def _knowledge_section(store, campaign, is_gm: bool) -> str:
    """The campaign's world knowledge, grouped by kind.

    Players see the page too, so secrets are filtered here rather than only being
    hidden with CSS — the server must never send a secret it does not intend the
    viewer to have.
    """
    facts = store.knowledge.campaign_facts()
    if not is_gm:
        facts = [f for f in facts if not f.secret]

    by_kind: dict = {}
    for fact in facts:
        by_kind.setdefault(fact.kind, []).append(fact)

    blocks = ""
    for kind in sorted(by_kind):
        rows = ""
        for fact in sorted(by_kind[kind], key=lambda f: -f.weight):
            lock = ' <span class="chip">secret</span>' if fact.secret else ""
            remove = (
                f'<button class="dndlore-remove" data-id="{fact.id}">Remove</button>'
                if is_gm else ""
            )
            tags = " ".join(f'<span class="chip">{_escape(t)}</span>' for t in fact.tags[:6])
            rows += f"""
<tr><td><b>{_escape(fact.title)}</b>{lock}<br>
<span class="muted small">{_escape(fact.text[:240])}</span><br>{tags}</td>
<td class="muted small">{fact.weight:.2f}</td><td>{remove}</td></tr>"""
        blocks += f"""
<h3>{_escape(kind.title())} ({len(by_kind[kind])})</h3>
<table class="ranktable"><tbody>{rows}</tbody></table>"""

    if not facts:
        blocks = ('<p class="muted">Nothing written down yet.'
                  + (" Add the first fact below." if is_gm else "") + "</p>")

    form = ""
    if is_gm:
        kinds = "".join(f'<option value="{k}">{k.title()}</option>' for k in KINDS)
        form = f"""
<div class="cogcard">
  <div class="coghead"><div><h3>Add a fact</h3>
  <p class="muted small">Small facts retrieve better than long ones. Tags are worked out for you.</p></div></div>
  <div class="catbody">
    <input id="lore-title" placeholder="Title" maxlength="100">
    <textarea id="lore-text" rows="3" placeholder="What is true"></textarea>
    <select id="lore-kind">{kinds}</select>
    <label><input type="checkbox" id="lore-secret"> GM only</label>
    <button id="lore-add">Add</button>
  </div>
</div>"""

    return f"""
<h2>World knowledge</h2>
<p class="muted small">Layered scene &rarr; campaign &rarr; server &rarr; global; the most
specific wins. A player never sees a fact marked GM-only.</p>
{blocks}
{form}"""


def _canon_section(store, is_gm: bool) -> str:
    """Facts a narrator invented, waiting on a ruling. Empty until P4."""
    if not is_gm:
        return ""
    pending = store.canon.pending()
    if not pending:
        return """
<h2>Proposed canon</h2>
<p class="muted">Nothing waiting for review. Invented facts land here once the
narrator is switched on, and stay out of canon until you accept them.</p>"""

    rows = ""
    for proposal in pending:
        body = proposal.get("proposal") or {}
        rows += f"""
<tr><td><b>{_escape(body.get('title', '?'))}</b><br>
<span class="muted small">{_escape(str(body.get('text', ''))[:240])}</span></td>
<td class="muted small">{proposal.get('confidence', 0):.2f}</td>
<td><button class="canon-accept" data-id="{proposal['_id']}">Accept</button>
<button class="canon-reject" data-id="{proposal['_id']}">Reject</button></td></tr>"""
    return f"""
<h2>Proposed canon <span class="muted">&middot; {len(pending)} awaiting review</span></h2>
<table class="ranktable"><tbody>{rows}</tbody></table>"""


def _dnd_script(guild_id: int, campaign_id: str = "") -> str:
    """Tabletop's own panel script.

    Deliberately not part of ``panel.js``: that file binds ``.param`` controls to
    the bot's general settings endpoint, and reusing it would route tabletop
    settings back through the shared API this separation exists to avoid.
    """
    return f"""
<script>
(function() {{
  const gid = {guild_id};
  const cid = "{campaign_id}";
  const status = document.getElementById("status");
  async function post(url, body) {{
    const res = await fetch(url, {{
      method: "POST", headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify(body),
    }});
    const data = await res.json().catch(() => ({{ok: false}}));
    if (status) {{
      status.textContent = data.ok ? "Saved." : ("Error: " + (data.error || "failed"));
    }}
    return data;
  }}
  document.querySelectorAll(".dndparam").forEach((el) => {{
    el.addEventListener("change", () => {{
      const value = el.type === "checkbox" ? el.checked : el.value;
      post(`/api/guild/${{gid}}/dnd/param`, {{key: el.dataset.key, value}});
    }});
  }});
  document.querySelectorAll(".dndcog").forEach((el) => {{
    el.addEventListener("change", () => {{
      post(`/api/guild/${{gid}}/dnd/cog`, {{cog: el.dataset.cog, enabled: el.checked}});
    }});
  }});
  const add = document.getElementById("lore-add");
  if (add) {{
    add.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/lore`, {{
        campaign_id: cid, action: "add",
        title: document.getElementById("lore-title").value,
        text: document.getElementById("lore-text").value,
        kind: document.getElementById("lore-kind").value,
        secret: document.getElementById("lore-secret").checked,
      }});
      if (data.ok) location.reload();
    }});
  }}
  document.querySelectorAll(".dndlore-remove").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/lore`,
        {{campaign_id: cid, action: "remove", id: el.dataset.id}});
      if (data.ok) location.reload();
    }});
  }});
  document.querySelectorAll(".canon-accept, .canon-reject").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const action = el.classList.contains("canon-accept") ? "accept" : "reject";
      const data = await post(`/api/guild/${{gid}}/dnd/canon`,
        {{campaign_id: cid, id: el.dataset.id, action}});
      if (data.ok) location.reload();
    }});
  }});
}})();
</script>
<p id="status" class="status"></p>"""


# --------------------------------------------------------------------------- #
#  Handlers
# --------------------------------------------------------------------------- #
async def tabletop_page(request: web.Request):
    from web.routes import _page   # imported lazily; see the module docstring

    guild, scope, uid = request["guild"], request["scope"], request["uid"]
    return _page(
        f"Tabletop · {guild.name}",
        campaigns_html(request.app["bot"], guild, scope, uid),
        scope=scope,
        guild=guild,
        current="tabletop",
    )


async def campaign_page(request: web.Request):
    from web.routes import _page

    guild, guild_scope, uid = request["guild"], request["scope"], request["uid"]
    raw_id = request.match_info.get("cid", "")

    campaign = None
    for candidate in campaigns_for(guild.id).list(include_archived=True):
        if str(candidate.id) == raw_id:
            campaign = candidate
            break

    campaign_scope = access.campaign_scope(campaign, uid, guild_scope)
    if campaign is None or campaign_scope == access.CAMPAIGN_NONE:
        # 404 rather than 403, matching the rest of the panel: it doesn't confirm
        # the existence of things the viewer has nothing to do with.
        return web.Response(status=404, text="Campaign not found.", content_type="text/plain")

    return _page(
        f"{campaign.name} · {guild.name}",
        campaign_html(request.app["bot"], guild, campaign, campaign_scope),
        scope=guild_scope,
        guild=guild,
        current="tabletop",
    )
