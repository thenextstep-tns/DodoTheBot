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
import re

from aiohttp import web

from helpers import panel_access
from helpers.dnd import parameters as dnd_parameters
from helpers.dnd import registry as dnd_registry
from helpers.dnd import minds
from helpers.dnd import rules
from helpers.dnd import tuning as tuning_registry
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.world.entity import KIND_FACTION, KIND_NPC, KIND_PC
from helpers.dnd.mind.needs import NEED_LABELS
from helpers.dnd.mind.traits import DRIVES, FACULTIES, TEMPERAMENT, TRAIT_LABELS
from helpers.dnd.world.knowledge import KINDS
from helpers.dnd.world.memory import TIER_IMPRINT, TIER_LONG, TIER_MID, TIER_WORKING
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
<div class="ttpage">
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


def _entity_row(guild, entity, ruleset, *, campaign_id=None, is_gm: bool = False) -> str:
    owner = (
        _escape(_member_name(guild, entity.owner_id)) if entity.owner_id else '<span class="muted">—</span>'
    )
    stat_summary = " · ".join(f"{label} {value}" for label, value in ruleset.sheet_fields(entity.stats)[:4])
    retired = ' <span class="chip">retired</span>' if entity.retired else ""
    return f"""
<tr>
  <td>{_name_cell(entity, campaign_id, guild, is_gm)}{retired}<br>
      <span class="muted small">{_escape(entity.identity.pronouns)}</span></td>
  <td>{_escape(_KIND_LABELS.get(entity.kind, entity.kind))}</td>
  <td>{_escape(entity.identity.role) or '<span class="muted">—</span>'}</td>
  <td>{owner}</td>
  <td>{_escape(entity.tier)}</td>
  <td class="muted small">{stat_summary}</td>
</tr>"""


def _name_cell(entity, campaign_id, guild, is_gm: bool) -> str:
    """A GM can click through to the inspector; a player just reads the name."""
    name = f"<b>{_escape(entity.identity.name)}</b>"
    if not is_gm or campaign_id is None:
        return name
    return (
        f'<a href="/guild/{guild.id}/tabletop/{campaign_id}/entity/{entity.id}">{name}</a>'
    )


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
        body = "".join(
            _entity_row(guild, e, ruleset, campaign_id=campaign.id, is_gm=is_gm)
            for e in rows
        )
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
<div class="ttpage">
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

  {_tuning_section(minds.tuning_for(store, campaign), campaign, is_gm)}

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
    <div class="params">{rows}</div>
  </div>
</div>
{_server_tuning_section(guild)}"""


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


def _dnd_script(guild_id: int, campaign_id: str = "", entity_id: str = "") -> str:
    """Tabletop's own panel script.

    Deliberately not part of ``panel.js``: that file binds ``.param`` controls to
    the bot's general settings endpoint, and reusing it would route tabletop
    settings back through the shared API this separation exists to avoid.
    """
    return f"""
<p id="status" class="status"></p>
<script>
(function() {{
  // Snowflakes are 64-bit. As a bare numeric literal 806174526383325225 parses
  // as ...200 — a guild that does not exist — so every tabletop request 404'd
  // at the scope check, silently. Strings, exactly as panel.js's header says.
  const gid = "{guild_id}";
  const cid = "{campaign_id}";
  const eid = "{entity_id}";
  // Looked up after the element above exists: it used to be emitted *below*
  // this script, so this was null and no control could ever report anything.
  const status = document.getElementById("status");
  // .status is opacity:0 until something adds "show" — setting textContent
  // alone left every tabletop control silently doing nothing visible, which is
  // exactly how a failing save looks like a dead checkbox.
  function flash(message, ok) {{
    if (!status) return;
    status.textContent = message;
    status.className = "status show " + (ok ? "ok" : "err");
    setTimeout(() => {{ status.className = "status"; }}, 3000);
  }}
  async function post(url, body) {{
    let res, raw = "", data = {{}};
    try {{
      res = await fetch(url, {{
        method: "POST", headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(body),
      }});
    }} catch (err) {{
      flash("Network error: " + err.message, false);
      return {{ok: false}};
    }}
    try {{ raw = await res.text(); data = JSON.parse(raw); }} catch (_) {{ }}
    // Say what actually came back. A non-JSON reply — a login redirect, a 404
    // from the scope check, a proxy error — used to surface as nothing at all.
    if (!res.ok || !data.ok) {{
      flash(data.error || `HTTP ${{res.status}} — ${{raw.slice(0, 120) || "empty reply"}}`, false);
      return data.ok ? data : {{ok: false}};
    }}
    flash("Saved.", true);
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
  document.querySelectorAll(".dndtune-server").forEach((el) => {{
    el.addEventListener("change", () => {{
      post(`/api/guild/${{gid}}/dnd/tune-server`, {{key: el.dataset.key, value: el.value}});
    }});
  }});
  document.querySelectorAll(".dndtune-server-clear").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/tune-server`,
        {{key: el.dataset.key, value: null}});
      if (data.ok) location.reload();
    }});
  }});
  document.querySelectorAll(".dndtune").forEach((el) => {{
    el.addEventListener("change", () => {{
      post(`/api/guild/${{gid}}/dnd/tune`,
        {{campaign_id: cid, key: el.dataset.key, value: el.value}});
    }});
  }});
  document.querySelectorAll(".dndtune-clear").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/tune`,
        {{campaign_id: cid, key: el.dataset.key, value: null}});
      if (data.ok) location.reload();
    }});
  }});
  // Tuning side menu: one group at a time. Panels are hidden rather than
  // removed, so a control in a group you are not looking at still posts.
  document.querySelectorAll(".tunepage").forEach((page) => {{
    const items = Array.from(page.querySelectorAll(".sidenavitem"));
    const panels = Array.from(page.querySelectorAll(".sidepanel"));
    if (!items.length) return;
    const show = (key) => {{
      if (!panels.some((p) => p.dataset.panel === key)) key = panels[0].dataset.panel;
      panels.forEach((p) => {{ p.hidden = p.dataset.panel !== key; }});
      items.forEach((a) => a.classList.toggle("active", a.dataset.panel === key));
      return key;
    }};
    items.forEach((item) => {{
      item.addEventListener("click", (e) => {{
        e.preventDefault();
        // Replace rather than push: back should leave the page, not walk you
        // through every group you glanced at.
        history.replaceState(null, "", "#" + show(item.dataset.panel));
      }});
    }});
    const wanted = (location.hash || "").replace("#", "");
    if (panels.some((p) => p.dataset.panel === wanted)) show(wanted);
  }});
  // Traits are editable per NPC: generation hands you the middle of a
  // distribution, and the outliers are the interesting people.
  document.querySelectorAll(".dndtrait").forEach((el) => {{
    el.addEventListener("change", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/entity-traits`, {{
        campaign_id: cid, entity_id: eid,
        axis: el.dataset.axis, value: el.value,
      }});
      if (data.ok) location.reload();   // the meters and the read-line follow
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
</script>"""


# --------------------------------------------------------------------------- #
#  Simulation tuning
#
#  Nothing in the engine is baked in: every constant is a tunable resolved
#  default -> server -> campaign. This page is the campaign layer, so a GM can
#  retune their own game without touching anyone else's.
# --------------------------------------------------------------------------- #

# One emoji per tuning group, so the side menu is scannable without reading it.
_GROUP_EMOJI = {
    "Memory": "🧠", "Forgetting": "🌫️", "Salience": "⚡", "Needs": "🍞",
    "Relationships": "🤝", "Knowledge": "📚", "Generation": "🎲",
}


def _emphasise(escaped: str) -> str:
    """Render the ``**bold**`` and ``*italic*`` in a tunable's description.

    The descriptions are written as prose with markdown emphasis — several of
    them lean on it to shout that a setting can be switched off entirely — and
    were reaching the panel with the asterisks still in. Runs *after* escaping,
    so the tags it adds are the only markup in the string.
    """
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", out)


def _tune_row(item: dict, css_class: str, own_label: str) -> str:
    """One setting: a wide label column, a narrow control, and where it came from."""
    source = item["source"]
    badge = (
        f'<span class="chip">{_escape(own_label)}</span>'
        if source == item.get("own_source")
        else f'<span class="muted small">from {_escape(source)}</span>'
    )
    step = "1" if item["type"] == "int" else "any"
    return f"""
<div class="paramrow tunerow">
  <div class="tunelabel">
    <b>{_escape(item['label'])}</b> {badge}
    <div class="muted small tunedesc">{_emphasise(_escape(item['description']))}</div>
    <div class="muted small tunemeta"><code>{item['key']}</code>
      <span>{item['min']}–{item['max']}</span></div>
  </div>
  <div class="tunectl">
    <input type="number" step="{step}" class="{css_class}" data-key="{item['key']}"
           value="{item['value']}" min="{item['min']}" max="{item['max']}">
    <button class="{css_class}-clear tuneclear" data-key="{item['key']}"
            title="Back to inherited">↺</button>
  </div>
</div>"""


def _tuning_rows(entries: list[dict], css_class: str, *, own_label: str) -> str:
    """One tuning layer, as a side menu with one group showing at a time.

    Shared by the server and campaign sections so the two can never drift into
    showing the same setting differently. ``own_label`` is what an override *at
    this layer* is called; anything else is inherited and says where from.

    Thirty-four settings stacked as seven cards became seven narrow columns of
    two-word lines, so this borrows the trial-ranks shape: the groups are the
    menu, and the panel gets the full width a sentence needs.
    """
    by_group: dict = {}
    for entry in entries:
        by_group.setdefault(entry["group"], []).append(entry)

    groups = [g for g in tuning_registry.GROUPS if by_group.get(g)]
    if not groups:
        return ""

    # Namespaced so the campaign and server layers can never fight over the hash.
    slug = css_class.replace("dndtune", "tune").replace("-", "") or "tune"

    nav, panels = "", ""
    for index, group in enumerate(groups):
        items = by_group[group]
        overridden = sum(1 for i in items if i["source"] == i.get("own_source"))
        hint = f"{len(items)} setting{'' if len(items) == 1 else 's'}"
        if overridden:
            hint += f" · {overridden} changed"
        key = f"{slug}-{group.lower()}"
        nav += f"""
<a class="sidenavitem{' active' if index == 0 else ''}" href="#{key}" data-panel="{key}">
  <span class="navemoji">{_GROUP_EMOJI.get(group, '•')}</span>
  <span class="navlabel">{_escape(group)}</span>
  <span class="navhint">{hint}</span></a>"""
        rows = "".join(_tune_row(item, css_class, own_label) for item in items)
        panels += f"""
<section class="sidepanel" data-panel="{key}"{'' if index == 0 else ' hidden'}>
  <h2 class="panelhead">{_GROUP_EMOJI.get(group, '')} {_escape(group)}</h2>
  {rows}
</section>"""

    return f"""
<div class="tunepage sidepanels">
  <aside class="sidebar sidenav">{nav}</aside>
  <main class="content">{panels}</main>
</div>"""


def _server_tuning_section(guild) -> str:
    """The server layer: the house style every campaign inherits.

    Sits under Engine on the Tabletop index, because it is server configuration
    rather than anything to do with one game.
    """
    tuning = tuning_registry.Tuning(
        server=dnd_parameters.tuning_overrides(guild.id)
    )
    entries = [
        {**entry, "own_source": "server"}
        for entry in tuning.entries(scope=tuning_registry.SCOPE_SERVER)
    ]
    return f"""
<h2>Simulation defaults</h2>
<p class="muted small">The house style for <b>every campaign on this server</b>.
A campaign that sets its own value overrides this; one that doesn't inherits it.
The ↺ button clears yours and falls back to the built-in default.</p>
{_tuning_rows(entries, "dndtune-server", own_label="server")}"""


def _tuning_section(tuning, campaign, is_gm: bool) -> str:
    """The campaign layer: this game's own opinions, overriding the server's."""
    if not is_gm:
        return ""
    entries = [{**entry, "own_source": "campaign"} for entry in tuning.entries()]
    return f"""
<h2>Simulation settings</h2>
<p class="muted small">These apply to <b>this campaign only</b> and override the
server's defaults. The ↺ button clears yours and goes back to inheriting. Setting
<b>Forgetting speed</b> to 0 switches forgetting off entirely.</p>
{_tuning_rows(entries, "dndtune", own_label="yours")}"""


# --------------------------------------------------------------------------- #
#  Entity inspector — the page that shows this is a simulation
# --------------------------------------------------------------------------- #
_TIER_LABELS = {
    TIER_IMPRINT: "⚡ Imprints — never fade",
    TIER_LONG: "Long-term",
    TIER_MID: "This arc",
    TIER_WORKING: "Right now",
}


def _meter(value: float, low: float = 0.0, high: float = 1.0) -> str:
    """A proportional bar. Rendered with a plain div so it needs no new CSS."""
    pct = max(0, min(100, round((value - low) / (high - low) * 100)))
    return (
        f'<span style="display:inline-block;width:90px;height:8px;background:#3a3a3a;'
        f'border-radius:4px;vertical-align:middle">'
        f'<span style="display:block;width:{pct}%;height:100%;background:currentColor;'
        f'border-radius:4px"></span></span>'
    )


def _memory_card(entity, memory, explain) -> str:
    """One memory, with its clarity per field and the reason it is sticking."""
    fields = ""
    for field in ("gist", "valence", "participants", "details", "when"):
        clarity = memory.fidelity.get(field, 1.0)
        flagged = field in memory.confabulated
        colour = "#e74c3c" if flagged else ("#2ecc71" if clarity > 0.7 else "#e67e22")
        label = {"gist": "what", "valence": "feeling", "participants": "who",
                 "details": "details", "when": "when"}[field]
        fields += (
            f'<div style="color:{colour};font-size:0.85em">{_meter(clarity)} '
            f'{label} {clarity:.2f}{" ⚠️ misremembered" if flagged else ""}</div>'
        )

    reason = _escape(explain(memory)) if explain else ""
    badges = f'<span class="chip">salience {memory.salience:.2f}</span> '
    badges += f'<span class="chip">{memory.feels}</span> '
    if memory.recall_count:
        badges += f'<span class="chip">recalled ×{memory.recall_count}</span> '
    if memory.confabulated:
        badges += '<span class="chip">⚠️ will misremember</span> '

    return f"""
<tr><td>
  <b>{_escape(memory.describe())}</b><br>{badges}
  <div class="muted small">{reason}</div>
</td><td>{fields}</td></tr>"""


def _inspector_html(bot, guild, campaign, entity, store) -> str:
    """Everything inside one head: disposition, body, memory, beliefs, relations.

    Read-only by construction — recall is *not* run here, because recalling a
    memory rewrites it and looking at an NPC must not change them.
    """
    tuning = minds.tuning_for(store, campaign)
    traits = minds.traits_of(entity)
    world_time = campaign.world_time
    needs = minds.needs_of(entity, world_time, tuning)
    memories = store.memories.for_entity(entity.id)

    # --- disposition ---
    # Editable, because rolling until an interesting person appears is not a
    # design tool. A moral thief, a warm killer, an honourable vampire — the
    # outliers are the point, and generation can only ever hand you the middle
    # of the distribution. Every axis is settable per NPC.
    trait_rows = ""
    for axis in TEMPERAMENT + DRIVES + FACULTIES:
        value = traits.axis(axis)
        low = -1.0 if axis in TEMPERAMENT else 0.0
        trait_rows += (
            f'<tr><td>{_escape(TRAIT_LABELS.get(axis, axis))}</td>'
            f'<td>{_meter(value, low, 1.0)} '
            f'<input type="number" class="dndtrait" data-axis="{axis}" '
            f'step="0.01" min="{low}" max="1.0" value="{value:.2f}"></td></tr>'
        )
    trait_rows += (
        '<tr><td colspan="2" class="muted small">Set any axis directly — this is '
        'how you build the exception rather than waiting for one to be rolled. '
        'Temperament runs −1…1, drives and retention 0…1.</td></tr>'
    )

    # --- body ---
    need_rows = ""
    for name, label in NEED_LABELS.items():
        value = needs.value(name)
        urgency = needs.urgency(name, tuning.needs())
        need_rows += (
            f'<tr><td>{_escape(label)}</td>'
            f'<td>{_meter(value)} {value:.2f} <span class="muted small">'
            f'(urgency {urgency:.3f})</span></td></tr>'
        )

    impulses = minds.impulses_of(entity, world_time, tuning)
    impulse_html = ", ".join(
        f'<span class="chip">{_escape(i.kind)} {i.strength:.2f}</span>' for i in impulses
    ) or '<span class="muted">No urges pulling at them.</span>'

    # --- memory, by tier ---
    by_tier: dict = {}
    for memory in memories:
        by_tier.setdefault(memory.tier, []).append(memory)

    memory_html = ""
    for tier, label in _TIER_LABELS.items():
        entries = by_tier.get(tier)
        if not entries:
            continue
        entries.sort(key=lambda m: -m.salience)
        rows = "".join(
            _memory_card(entity, m, lambda mm: minds.explain_retention(entity, mm))
            for m in entries[:20]
        )
        memory_html += f"""
<h3>{label} <span class="muted">· {len(entries)}</span></h3>
<table class="ranktable"><tbody>{rows}</tbody></table>"""
    if not memories:
        memory_html = '<p class="muted">Nothing worth remembering yet.</p>'

    # --- beliefs ---
    beliefs = store.beliefs.held_by(entity.id)
    belief_rows = "".join(
        f'<tr><td>{_escape(b.claim)}</td><td class="muted small">{b.certainty} '
        f'({b.confidence:.2f}) · {_escape(b.source_kind)}'
        f'{" · <b>false</b>" if b.is_wrong() else ""}</td></tr>'
        for b in beliefs
    ) or '<tr><td class="muted" colspan="2">Believes nothing in particular.</td></tr>'

    # --- relationships, both directions ---
    def _rel_rows(rels, key):
        out = ""
        for rel in rels[:12]:
            other = store.entities.get(getattr(rel, key))
            name = other.identity.name if other else "someone"
            out += (
                f'<tr><td>{_escape(name)}</td><td class="muted small">{_escape(rel.summary())}</td>'
                f'<td class="muted small">aff {rel.affinity:+.2f} · trust {rel.trust:+.2f} '
                f'· fear {rel.fear:+.2f}</td></tr>'
            )
        return out or '<tr><td class="muted" colspan="3">Nobody yet.</td></tr>'

    budget = store.memories.tier_counts(entity.id)
    return f"""
<div class="ttpage">
  <div class="statshead">
    <div><span class="muted">{_escape(guild.name)} ·
      <a href="/guild/{guild.id}/tabletop/{campaign.id}">{_escape(campaign.name)}</a></span>
      <h1>{_escape(entity.identity.name)}</h1>
      <p class="muted">{_escape(entity.identity.role)} · {_escape(entity.identity.pronouns)}
      · <i>{_escape(traits.describe())}</i></p></div>
  </div>
  <div class="chips">
    <span class="chip">{_escape(entity.kind)}</span>
    <span class="chip">tier {_escape(entity.tier)}</span>
    <span class="chip">importance {entity.importance:.2f}</span>
    <span class="chip">retention {traits.retention:.2f}</span>
    <span class="chip">{sum(budget.values())} memories</span>
  </div>

  <h2>Disposition</h2>
  <p class="muted small">Temperament is stable; drives shift slowly with experience.
  <b>Retention</b> is a faculty, not a personality trait — it decides how long this
  particular mind holds on to things.</p>
  <table class="ranktable"><tbody>{trait_rows}</tbody></table>

  <h2>Body</h2>
  <p class="muted small">Urgency is cubed, so a need is barely felt until it suddenly isn't.</p>
  <table class="ranktable"><tbody>{need_rows}</tbody></table>
  <p>{impulse_html}</p>

  <h2>Memory</h2>
  <p class="muted small">Each memory shows how clear every part of it still is.
  Fields in red have been <b>misremembered</b> — replaced with a plausible wrong
  value drawn from this character's other memories. The line underneath says why
  the memory is sticking, or why it isn't.</p>
  {memory_html}

  <h2>Beliefs</h2>
  <p class="muted small">What they think is true. They cannot see the "false" marker.</p>
  <table class="ranktable"><tbody>{belief_rows}</tbody></table>

  <h2>Feelings toward others</h2>
  <table class="ranktable"><tbody>{_rel_rows(store.relations.outgoing(entity.id), "to_id")}</tbody></table>

  <h2>How others feel about them</h2>
  <p class="muted small">Often the more interesting direction, and the one easy to forget to ask about.</p>
  <table class="ranktable"><tbody>{_rel_rows(store.relations.incoming(entity.id), "from_id")}</tbody></table>
</div>{_dnd_script(guild.id, str(campaign.id), str(entity.id))}"""


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


async def entity_page(request: web.Request):
    """The inspector. GM-only: it shows truth flags and decision-grade internals."""
    from web.routes import _page

    guild, guild_scope, uid = request["guild"], request["scope"], request["uid"]
    campaign = _find_campaign(guild.id, request.match_info.get("cid", ""))
    scope = access.campaign_scope(campaign, uid, guild_scope)
    if campaign is None or scope != access.CAMPAIGN_GM:
        return web.Response(status=404, text="Not found.", content_type="text/plain")

    store = campaign_store(guild.id, campaign.id)
    raw_id = request.match_info.get("eid", "")
    entity = next(
        (e for e in store.entities.list(include_retired=True, limit=500)
         if str(e.id) == raw_id),
        None,
    )
    if entity is None:
        return web.Response(status=404, text="Not found.", content_type="text/plain")

    return _page(
        f"{entity.identity.name} · {campaign.name}",
        _inspector_html(request.app["bot"], guild, campaign, entity, store),
        scope=guild_scope,
        guild=guild,
        current="tabletop",
    )


def _find_campaign(guild_id: int, raw_id: str):
    for candidate in campaigns_for(guild_id).list(include_archived=True):
        if str(candidate.id) == raw_id:
            return candidate
    return None


async def campaign_page(request: web.Request):
    from web.routes import _page

    guild, guild_scope, uid = request["guild"], request["scope"], request["uid"]
    raw_id = request.match_info.get("cid", "")

    campaign = _find_campaign(guild.id, raw_id)

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
