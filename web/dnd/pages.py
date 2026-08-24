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
from random import Random

from aiohttp import web

from helpers import panel_access
from helpers.dnd import parameters as dnd_parameters
from helpers.dnd import registry as dnd_registry
from helpers.dnd import minds
from helpers.dnd import catalogue
from helpers.dnd import interactions as interaction_registry
from helpers.dnd import packs as pack_registry
from helpers.dnd import rules
from helpers.dnd import tuning as tuning_registry
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.rules.ruleset import AFFORDANCES, AFFORDANCE_LABELS
from helpers.dnd.world.entity import KIND_FACTION, KIND_NPC, KIND_PC
from helpers.dnd.mind import behaviour as behaviour_math
from helpers.dnd.world import interaction as interaction_model
from helpers.dnd.mind import decide as decide_math
from helpers.dnd.mind import goals as goal_math
from helpers.dnd.mind import needs as needs_mod
from helpers.dnd.mind.needs import NEED_LABELS
from helpers.dnd.mind.traits import DRIVES, FACULTIES, TEMPERAMENT, TRAIT_LABELS
from helpers.dnd.world.goal import KIND_LABELS as GOAL_KIND_LABELS, KINDS as GOAL_KINDS
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

    # Admin tools that are about the engine rather than about one game. The
    # catalogue is the owner's view of every knob there is, including the ones
    # that do not have a control yet.
    counts = catalogue.summary()
    admin = f"""
<div class="ttadmin">
  <h2>Admin</h2>
  <p class="paramlink"><a href="/guild/{guild.id}/tabletop/parameters">
    📐 <b>List of parameters</b></a>
  <span class="muted small">— all {counts['total']} of them: what each one does,
  what else it moves, its default and range, and where it can be set.
  {counts['baked']} are still baked into the source with no control, and they are
  listed too.</span></p>
</div>""" if can_configure else ""

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
  {admin}
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
        if event.kind == "acted":
            # An NPC did something of their own accord, and the event carries
            # the reasoning that produced it. Showing the top two terms turns a
            # log line into an answer to "why did she do that", weeks later,
            # when nothing else remembers the state she decided from.
            payload = event.payload
            trace = payload.get("trace") or {}
            terms = sorted((trace.get("terms") or {}).items(), key=lambda p: -abs(p[1]))
            why = " · ".join(f"{_TERM_LABELS.get(name, name)} {value:+.2f}"
                             for name, value in terms[:2] if abs(value) >= 0.005)
            target = f" → {_escape(payload.get('target'))}" if payload.get("target") else ""
            detail = (f"{_escape(payload.get('name', ''))} "
                      f"<b>{_escape(payload.get('verb', ''))}</b>{target}"
                      + (f'<div class="muted small">{_escape(why)}</div>' if why else ""))
            rows += (
                f"<tr><td class='muted'>{event.seq}</td>"
                f"<td>{_escape(event.kind)}</td>"
                f"<td class='small'>{detail}</td></tr>"
            )
            continue
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

    day = campaign.world_time // 1440 + 1
    fact_count = len(store.knowledge.campaign_facts())
    scenes = store.scenes.recent(5)
    scene_lines = "".join(
        f"<li>{_escape(s.title)} <span class='muted small'>· {s.status}</span></li>" for s in scenes
    ) or '<li class="muted">No scenes yet.</li>'

    attribution = getattr(ruleset, "attribution", "")

    # Sections, not one scroll. A campaign page is a place you play from, and a
    # single column that ran characters into lore into engine settings meant
    # hunting for everything. Same shape as trial ranks and the tuning page.
    #
    # Server-level configuration is deliberately absent: the Engine section and
    # the server defaults live on the Tabletop index, one level up, because they
    # belong to the whole guild and have no business inside one game.
    sections = [
        ("cast", "👥", "Cast", f"{len(pcs)} player, {len(others)} other", f"""
  <h2 class="panelhead">Characters</h2>
  {table(pcs, "Nobody has made a character yet.")}
  <h2 class="panelhead">NPCs &amp; factions</h2>
  {table(others, "No NPCs yet — make one with <code>/npc create</code>.")}"""),
        ("scenes", "🎭", "Scenes", f"{len(scenes)} recent", f"""
  <h2 class="panelhead">Recent scenes</h2>
  <ul>{scene_lines}</ul>
  <h2 class="panelhead">Recent events</h2>
  <p class="muted small">Every change is an event, which is what makes replay possible.</p>
  {_events_table(store, guild)}"""),
        ("lore", "📚", "Lore &amp; facts", f"{fact_count} fact(s)",
         _knowledge_section(store, campaign, is_gm)),
    ]
    if is_gm:
        sections.append(
            ("canon", "⚖️", "Canon queue", "invented facts awaiting a ruling",
             _canon_section(store, is_gm))
        )
        sections.append(
            ("packs", "🧭", "Archetypes", "what people reach for",
             _packs_section(guild, campaign, store, is_gm))
        )
        sections.append(
            ("kinds", "↔️", "What people do to each other",
             "and what each of them is worth",
             _interactions_section(guild, campaign,
                                   minds.tuning_for(store, campaign), is_gm))
        )
        sections.append(
            ("safety", "🛑", "Lines", "what never appears",
             _safety_section(campaign, minds.tuning_for(store, campaign)))
        )
        sections.append(
            ("tuning", "🎛️", "This game's rules", "campaign only",
             _tuning_section(minds.tuning_for(store, campaign), campaign, is_gm))
        )

    nav, panels = "", ""
    for index, (key, emoji, label, hint, body) in enumerate(sections):
        if not body.strip():
            continue
        nav += f"""
<a class="campnavitem sidenavitem{' active' if index == 0 else ''}"
   href="#{key}" data-panel="{key}">
  <span class="navemoji">{emoji}</span>
  <span class="navlabel">{label}</span>
  <span class="navhint">{_escape(hint)}</span></a>"""
        panels += f"""
<section class="camppanel" data-panel="{key}"{'' if index == 0 else ' hidden'}>{body}</section>"""

    return f"""
<div class="ttpage camppage">
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
  <div class="sidepanels">
    <aside class="sidebar sidenav">{nav}</aside>
    <main class="content">{panels}</main>
  </div>
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
  // A checkbox's .value is "on" whether or not it is ticked, so reading it
  // would make every switch permanently on and look like the save was ignored.
  const tuneValue = (el) => el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
  // A number input that cannot parse what was typed reports "" — and "" is how
  // this API says *clear the override*. So a typo used to silently revert a
  // setting to inherited and flash "Saved." while doing it. Refuse instead; the
  // reset arrow stays the only way to clear something.
  const unusable = (el) =>
    el.type === "number" && (el.value === "" || el.validity.badInput);
  // What to put back when it is refused. Seeded from the rendered value and
  // moved forward only by a save that actually landed.
  document.querySelectorAll(".dndtune, .dndtune-server").forEach((el) => {{
    el.dataset.was = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
  }});
  function restore(el) {{
    el.value = el.dataset.was;
    flash("That is not a number — use the arrow to clear a setting.", false);
  }}
  function remember(el) {{
    el.dataset.was = tuneValue(el);
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
  // Server-level controls exist only on the Tabletop index; a campaign page must
  // not even carry the wiring for guild-wide configuration.
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
    el.addEventListener("change", async () => {{
      if (unusable(el)) return restore(el);
      const data = await post(`/api/guild/${{gid}}/dnd/tune-server`,
        {{key: el.dataset.key, value: tuneValue(el)}});
      if (data.ok) remember(el);
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
    el.addEventListener("change", async () => {{
      if (unusable(el)) return restore(el);
      const data = await post(`/api/guild/${{gid}}/dnd/tune`,
        {{campaign_id: cid, key: el.dataset.key, value: tuneValue(el)}});
      if (data.ok) remember(el);
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
  // Two independent side menus can be on one page: the campaign's sections, and
  // the tuning groups nested inside one of them. Each binds only its own, or the
  // outer one would swallow the inner one's clicks.
  const menus = [
    [".camppage", ".campnavitem", ".camppanel"],
    [".tunepage", ".sidenavitem:not(.campnavitem)", ".sidepanel"],
  ];
  menus.forEach(([host, itemSel, panelSel]) => {{
  document.querySelectorAll(host).forEach((page) => {{
    const items = Array.from(page.querySelectorAll(itemSel));
    const panels = Array.from(page.querySelectorAll(panelSel));
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
  // Lines. Separate endpoint from the tuning on purpose: a line is not a
  // setting, and it outranks one.
  document.querySelectorAll(".dndline-remove").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/safety`,
        {{campaign_id: cid, action: "remove", line: el.dataset.line}});
      if (data.ok) location.reload();
    }});
  }});
  const lineAdd = document.getElementById("safetyadd");
  if (lineAdd) {{
    lineAdd.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/safety`, {{
        campaign_id: cid, action: "add",
        line: document.getElementById("safetyline").value,
      }});
      if (data.ok) location.reload();
    }});
  }}
  // Archetypes. A card's weights live in the card, so one handler serves them
  // all and adding an archetype needs no new wiring.
  const packWeights = (root) => {{
    const out = {{}};
    root.querySelectorAll("input[data-verb]").forEach((i) => {{
      const n = parseFloat(i.value);
      if (!isNaN(n) && n > 0) out[i.dataset.verb] = n;
    }});
    return out;
  }};
  document.querySelectorAll(".dndpack-save").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const card = el.closest(".packcard");
      const data = await post(`/api/guild/${{gid}}/dnd/pack`, {{
        campaign_id: cid, action: "save", key: el.dataset.key,
        label: (card.querySelector(".packname") || {{}}).value || el.dataset.key,
        description: (card.querySelector(".packdesc") || {{}}).value || "",
        weights: packWeights(card),
      }});
      if (data.ok) location.reload();
    }});
  }});
  document.querySelectorAll(".dndpack-remove").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/pack`,
        {{campaign_id: cid, action: "remove", key: el.dataset.key}});
      if (data.ok) location.reload();
    }});
  }});
  const packAdd = document.getElementById("packadd");
  if (packAdd) {{
    packAdd.addEventListener("click", async () => {{
      // One name, not two. The short key is derived from it — asking for both
      // and then only letting one be edited afterwards is a form that lies.
      // No key: a new archetype is named once and the server slugs it. An
      // existing one sends its key, so renaming edits it instead of forking it.
      const data = await post(`/api/guild/${{gid}}/dnd/pack`, {{
        campaign_id: cid, action: "save",
        label: document.getElementById("packlabel").value,
        description: document.getElementById("packdesc").value,
        weights: packWeights(document.getElementById("packnewweights")),
      }});
      if (data.ok) location.reload();
    }});
  }}
  // What people do to each other. Same card-scoped shape as the archetypes
  // above; the deltas differ in running -1..1, and zero means "this axis is not
  // part of this act" rather than "this act does nothing to it".
  const kindDeltas = (root) => {{
    const out = {{}};
    root.querySelectorAll("input[data-axis]").forEach((i) => {{
      const n = parseFloat(i.value);
      if (!isNaN(n) && n !== 0) out[i.dataset.axis] = n;
    }});
    return out;
  }};
  const kindMagnitude = (root, id) => {{
    const el = root ? root.querySelector(".kindmagnitude")
                    : document.getElementById(id);
    const n = el ? parseFloat(el.value) : NaN;
    return isNaN(n) ? 0.4 : n;
  }};
  document.querySelectorAll(".dndkind-save").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const card = el.closest(".packcard");
      const data = await post(`/api/guild/${{gid}}/dnd/interaction`, {{
        campaign_id: cid, action: "save", key: el.dataset.key,
        label: (card.querySelector(".kindname") || {{}}).value || el.dataset.key,
        phrase: (card.querySelector(".kindphrase") || {{}}).value || "",
        description: (card.querySelector(".kinddesc") || {{}}).value || "",
        magnitude: kindMagnitude(card),
        deltas: kindDeltas(card),
      }});
      if (data.ok) location.reload();
    }});
  }});
  document.querySelectorAll(".dndkind-remove").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/interaction`,
        {{campaign_id: cid, action: "remove", key: el.dataset.key}});
      if (data.ok) location.reload();
    }});
  }});
  const kindAdd = document.getElementById("kindadd");
  if (kindAdd) {{
    // No key, same as a new archetype: named once, and the server slugs it.
    kindAdd.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/interaction`, {{
        campaign_id: cid, action: "save",
        label: document.getElementById("kindlabel").value,
        phrase: document.getElementById("kindphrase").value,
        description: document.getElementById("kinddesc").value,
        magnitude: kindMagnitude(null, "kindmagnitude"),
        deltas: kindDeltas(document.getElementById("kindnewdeltas")),
      }});
      if (data.ok) location.reload();
    }});
  }}
  // Goals: the one part of a mind the panel is *meant* to author.
  const goalAdd = document.getElementById("goaladd");
  if (goalAdd) {{
    goalAdd.addEventListener("click", async () => {{
      const data = await post(`/api/guild/${{gid}}/dnd/entity-goals`, {{
        campaign_id: cid, entity_id: eid, action: "add",
        kind: document.getElementById("goalkind").value,
        text: document.getElementById("goaltext").value,
        subject_id: document.getElementById("goalsubject").value,
        priority: document.getElementById("goalpriority").value,
        deadline_days: document.getElementById("goaldeadline").value,
      }});
      if (data.ok) location.reload();
    }});
  }}
  document.querySelectorAll(".dndgoal-priority").forEach((el) => {{
    el.addEventListener("change", async () => {{
      if (el.value === "" || el.validity.badInput) return;
      const data = await post(`/api/guild/${{gid}}/dnd/entity-goals`, {{
        campaign_id: cid, entity_id: eid, key: el.dataset.key,
        action: "priority", priority: el.value,
      }});
      if (data.ok) location.reload();   // every other goal's share moves too
    }});
  }});
  document.querySelectorAll(".dndgoal-advance, .dndgoal-drop").forEach((el) => {{
    el.addEventListener("click", async () => {{
      const drop = el.classList.contains("dndgoal-drop");
      const data = await post(`/api/guild/${{gid}}/dnd/entity-goals`, {{
        campaign_id: cid, entity_id: eid, key: el.dataset.key,
        action: drop ? "drop" : "advance", amount: 0.25,
      }});
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
    "Relationships": "🤝", "Stakes": "⚖️", "Perception": "👁️",
    "Actions": "🎬", "Goals": "🎯", "Behaviour": "🧭",
    "Deciding": "🧮",
    "Continuity": "⏳", "Reporting": "📣", "Remembering": "💭",
    "Knowledge": "📚", "Generation": "🎲",
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


def _tune_control(item: dict, css_class: str) -> str:
    """The control itself, matched to the tunable's type.

    Every row used to be a number input. That is fine for the thirty-odd numeric
    settings and wrong for the others: ``time_mode`` shipped as an empty number
    box with ``min=0 max=1``, so the one setting that decides whether a campaign
    ages at all could not be changed from the panel at all. A control that cannot
    express its own value is the same defect as a control wired to nothing.
    """
    key, kind, value = item["key"], item["type"], item["value"]
    common = f'class="{css_class}" data-key="{key}" data-type="{kind}"'
    if kind == "choice":
        options = "".join(
            f'<option value="{_escape(choice)}"{" selected" if choice == value else ""}>'
            f'{_escape(choice)}</option>'
            for choice in (item.get("choices") or ())
        )
        return f"<select {common}>{options}</select>"
    if kind == "bool":
        return (f'<input type="checkbox" {common}'
                f'{" checked" if value else ""}>')
    step = "1" if kind == "int" else "any"
    return (f'<input type="number" step="{step}" {common} '
            f'value="{_escape(value)}" min="{item["min"]}" max="{item["max"]}">')


def _tune_range(item: dict) -> str:
    """What the value may be, said the way that type says it."""
    if item["type"] == "choice":
        return " / ".join(_escape(c) for c in (item.get("choices") or ()))
    if item["type"] == "bool":
        return "on / off"
    return f"{item['min']}–{item['max']}"


def _tune_row(item: dict, css_class: str, own_label: str) -> str:
    """One setting: a wide label column, a narrow control, and where it came from."""
    source = item["source"]
    badge = (
        f'<span class="chip">{_escape(own_label)}</span>'
        if source == item.get("own_source")
        else f'<span class="muted small">from {_escape(source)}</span>'
    )
    return f"""
<div class="paramrow tunerow">
  <div class="tunelabel">
    <b>{_escape(item['label'])}</b> {badge}
    <div class="muted small tunedesc">{_emphasise(_escape(item['description']))}</div>
    {f'<div class="tuneblocked">{_escape(item["blocked"])}</div>' if item.get("blocked") else ""}
    <div class="muted small tunemeta"><code>{item['key']}</code>
      <span>{_tune_range(item)}</span></div>
  </div>
  <div class="tunectl">
    {_tune_control(item, css_class)}
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


def _meter(value: float, low: float = 0.0, high: float = 1.0,
           neutral: float | None = None) -> str:
    """A bar drawn from an axis's **neutral point**, not from its left edge.

    Every axis on the sheet has a resting value, and it is not always the bottom
    of the range. Temperament is −1…1 resting at 0; drives are 0…1 resting at
    **0.5**; a need is 0…1 resting at 0, because no hunger really is none.

    Filling from the left regardless got both halves wrong in the same column:
    warmth −0.33 drew a third of a bar and read as mildly warm, and greed 0.54 —
    a hair above neutral — drew a half-full bar and read as grasping.
    ``traits.strongest()`` has always measured drives from 0.5 for exactly this
    reason; the meter now agrees with it.

    ``neutral`` defaults to 0 for signed axes and to ``low`` for magnitudes.
    """
    span = (high - low) or 1.0
    if neutral is None:
        neutral = 0.0 if low < 0 else low
    at = lambda v: max(0.0, min(100.0, (v - low) / span * 100.0))
    zero, mark = at(neutral), at(value)
    left, width = min(zero, mark), abs(mark - zero)
    sign = "pos" if value >= neutral else "neg"
    tick = (
        f'<b style="left:{zero:.1f}%"></b>' if 1.0 < zero < 99.0 else ""
    )
    return (
        f'<span class="meter">{tick}<i class="{sign}" '
        f'style="left:{left:.1f}%;width:{max(width, 1.2):.1f}%"></i></span>'
    )


def _axis_cell(value: float, low: float = 0.0, high: float = 1.0,
               neutral: float | None = None) -> str:
    """Meter plus its number, aligned so a column of them can be read down.

    Signed axes print their sign; a magnitude does not, because ``+0.54`` on a
    0…1 scale implies a direction the number does not have.
    """
    text = f"{value:+.2f}" if low < 0 else f"{value:.2f}"
    return f'<span class="metrow">{_meter(value, low, high, neutral)}<span class="metval">{text}</span></span>'


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


_TERM_LABELS = {
    "need": "their body wants it",
    "impulse": "an urge they keep coming back to",
    "goal": "it serves what they are after",
    "relation": "how they feel about them",
    "risk": "what it might cost",
    "trait": "the sort of thing they do",
    "imprint": "something they cannot forget",
    "norm": "what it would look like",
    "archetype": "the sort of person they are",
}


def _decision_section(campaign, entity, store, world_time: int) -> str:
    """What they would do right now, and the whole working behind it.

    The explainability feature, and the debugger. A GM who can read *why* an NPC
    did something is a GM collaborating with the simulation; one who cannot is a
    GM suspicious of it, and that difference is most of whether this is worth
    using. Read-only: asking what somebody would do must not make them do it.
    """
    scene = None
    if entity.position.scene_id is not None:
        scene = store.scenes.get(entity.position.scene_id)
    if scene is None:
        scene = next((s for s in store.scenes.open_scenes() if entity.id in s.present), None)

    # Seeded from the campaign and the entity, so the page shows the same answer
    # on a refresh rather than rerolling the softmax under the reader.
    seed = f"{campaign.seed}:{entity.id}:{world_time}"
    decision = minds.decide_for(
        store, entity, scene, world_time=world_time,
        rng=Random(abs(hash(seed)) % (2 ** 32)), campaign=campaign,
    )
    if not decision.considered:
        return """
  <h2>What they would do next</h2>
  <p class="muted small">Nothing to weigh: they are in no open scene, so the
  engine has no room to offer them options in.</p>"""

    names = store.entities.identities_of(
        [s.target_id for s in decision.considered if s.target_id is not None]
    )

    def _who(target_id):
        if target_id is None:
            return ""
        return " → " + _escape((names.get(target_id) or {}).get("name") or "someone")

    rows = ""
    for scored in decision.considered[:8]:
        chosen = scored is decision.chosen
        working = "".join(
            f'<span class="chip">{_escape(_TERM_LABELS.get(name, name))} {value:+.2f}</span>'
            for name, value in scored.top_terms(5)
        ) or '<span class="muted small">nothing pulled either way</span>'
        rows += f"""
<tr{' class="chosenrow"' if chosen else ''}>
  <td><b>{_escape(scored.verb)}</b>{_who(scored.target_id)}
    {'<span class="chip">chosen</span>' if chosen else ''}
    {f'<div class="muted small">proposed by {_escape(scored.pack)}</div>' if scored.pack else ''}</td>
  <td class="utilcell">{scored.utility:+.2f}</td>
  <td><div class="chips wrap">{working}</div></td>
</tr>"""

    where = f"in <b>{_escape(scene.title or 'the open scene')}</b>" if scene else "alone"
    close = ("It was close — they could easily have done something else."
             if decision.margin < 0.1 else
             "That was a clear choice.")
    return f"""
  <h2>What they would do next</h2>
  <p class="muted small">Every option this character is weighing {where}, and the
  terms that decided it. <b>Nothing here has happened</b> — asking what somebody
  would do must not make them do it. Choice is a weighted draw rather than
  always-the-highest, so a steady character is predictable and a volatile one is
  not: this one is being drawn at <b>T {decision.temperature:.2f}</b>. {close}</p>
  <table class="ranktable decisiontable"><thead><tr>
    <th>Option</th><th>Score</th><th>Why</th></tr></thead>
    <tbody>{rows}</tbody></table>
  <p class="muted small">Weights are global and tunable under <b>Deciding</b>;
  what varies per character is the <i>terms</i>, not the weights — two hundred
  NPCs with their own weights would be untunable.</p>"""


def _allure_row(entity, tuning) -> str:
    """How strongly people tend to be drawn to them. Only for campaigns that
    switched desire on — a table that did not opt in should not find a beauty
    slider on their harbourmaster."""
    if not minds.romance_allowed(tuning):
        return ""
    return f"""
    <tr><td>Allure <span class="muted small">(how they strike people)</span></td>
      <td>{_meter(entity.allure)}
        <input type="number" class="dndtrait" data-axis="allure"
               step="0.05" min="0" max="1" value="{entity.allure:.2f}">
        <div class="muted small">One input among several, and the smallest.
        Whether somebody is drawn to them turns mostly on what the two of them
        already are to each other — a plain, trusted, familiar person is wanted
        more than a striking stranger, and fear puts it out altogether.</div>
      </td></tr>"""


def _archetype_section(guild, campaign, entity, tuning) -> str:
    """What this person reaches for, and how well the archetype actually suits them.

    The fit is the interesting number and the reason priors are read backwards:
    an NPC drawn as a predator who fits at −0.3 is a reluctant one, and saying
    so out loud is the difference between an emergent oddity and a wasted one.
    """
    assignments = minds.packs_of(entity)
    registry = pack_registry.Packs.for_campaign(guild.id, campaign)
    available = registry.available()
    traits = minds.traits_of(entity)

    if tuning.behaviour().off:
        return """
  <h2>What they reach for</h2>
  <p class="muted small">Archetypes are switched off for this campaign
  (<code>pack_count</code> is 0), so everyone weighs everything the scene allows
  evenly and only disposition and circumstance tell them apart.</p>"""

    rows = ""
    for assignment in assignments:
        pack = available.get(assignment.key)
        if pack is None:
            rows += (
                f'<tr><td>{_escape(assignment.key)}</td>'
                f'<td class="muted small" colspan="2">no longer defined in this '
                'campaign — it proposes nothing</td></tr>'
            )
            continue
        value = behaviour_math.fit(traits, pack)
        rows += f"""
<tr>
  <td><b>{_escape(pack.label)}</b>
    <div class="muted small">{_escape(behaviour_math.describe_fit(value, pack.label))}</div></td>
  <td>{_meter(assignment.weight)}<span class="muted small">
    {assignment.weight * 100:.0f}% of them</span></td>
  <td>{_axis_cell(value, -1.0, 1.0, 0.0)}<span class="muted small">fit</span></td>
</tr>"""
    if not rows:
        rows = ('<tr><td class="muted" colspan="3">Drawn from no archetype. They '
                'consider everything the scene allows, evenly.</td></tr>')

    reaches = {}
    for assignment in assignments:
        pack = available.get(assignment.key)
        if pack is None:
            continue
        for verb in pack.reaches_for:
            reaches[verb] = max(reaches.get(verb, 0.0),
                                pack.weight_for(verb) * assignment.weight)
    leaning = ", ".join(
        _escape(AFFORDANCE_LABELS.get(v, v).lower())
        for v, _ in sorted(reaches.items(), key=lambda p: -p[1])[:4]
    )
    return f"""
  <h2>What they reach for</h2>
  <p class="muted small">Archetypes are <b>noticed, not assigned</b>: these were
  drawn from the disposition above, weighted by how well each fits, so the timid
  soldier and the gentle thug still happen. The fit column is that read backwards
  — a predator who fits badly is a reluctant one. They can only ever reach for
  what a scene actually offers.</p>
  <table class="ranktable"><tbody>{rows}</tbody></table>
  {f'<p class="muted small">In a room with options, they go for: <b>{leaning}</b>.</p>'
   if leaning else ''}"""


def _goals_section(entity, store, tuning, world_time: int) -> str:
    """What they are trying to bring about, and a way to author it.

    Deliberately open rather than folded behind a warning the way disposition
    is. Who somebody *is* should move through what happens to them; what they
    are currently *after* is plot, and plot is the GM's to write.
    """
    goal_tuning = tuning.goals()
    everything = minds.all_goals_of(entity)
    live = {g.key for g in minds.goals_of(entity, world_time, tuning)}
    attention = minds.attention_of(entity, world_time, tuning)
    shares = attention["shares"]

    rows = ""
    for goal in sorted(everything, key=lambda g: (g.status != "open", g.key)):
        # With their share applied, so this column is the number the scorer
        # actually multiplies by — the Attention column beside it explains why.
        pressing = goal_math.pressure(goal, world_time, goal_tuning,
                                      shares.get(goal.key, 0.0))
        caring = goal_math.faded(goal, world_time, goal_tuning)
        when = ""
        if goal.deadline is not None:
            days = (goal.deadline - world_time) / 1440
            when = (f"{days:.1f} days left" if days >= 0 else f"{-days:.1f} days overdue")
        state = goal.status
        if state == "open" and goal.key not in live:
            # Carried, but not currently in contention: faded past caring, or
            # squeezed out by the cap. Saying which is the whole point of showing
            # it at all — otherwise a goal that quietly stopped mattering looks
            # identical to one that never existed.
            state = "set aside"
        controls = "" if goal.status != "open" else (
            f'<button class="dndgoal-advance ghost" data-key="{_escape(goal.key)}">+25%</button> '
            f'<button class="dndgoal-drop ghost" data-key="{_escape(goal.key)}">Give up</button>'
        )
        share = shares.get(goal.key, 0.0)
        attends = (
            f'{_meter(share)}<span class="muted small">{share * 100:.0f}% of them</span>'
            if goal.status == "open"
            else '<span class="muted small">—</span>'
        )
        cares = (
            f'<input type="number" class="dndgoal-priority" data-key="{_escape(goal.key)}" '
            f'step="0.05" min="0" max="1" value="{goal.priority:.2f}">'
            if goal.status == "open" else f'<span class="muted small">{goal.priority:.2f}</span>'
        )
        rows += f"""
<tr>
  <td><b>{_escape(GOAL_KIND_LABELS.get(goal.kind, goal.kind))}</b>
    <div>{_escape(goal.text) or '<span class="muted">no words yet</span>'}</div>
    <div class="muted small">{_escape(state)} · from {_escape(goal.origin)}
      {(" · " + _escape(when)) if when else ""}</div></td>
  <td>{cares}<div class="muted small">now worth {caring:.2f}</div></td>
  <td>{attends}</td>
  <td>{_meter(goal.progress)}<span class="muted small">{int(goal.progress * 100)}% done</span></td>
  <td>{_meter(pressing)}<span class="muted small">pressing {pressing:.2f}</span></td>
  <td>{controls}</td>
</tr>"""
    if not rows:
        rows = ('<tr><td class="muted" colspan="6">Wants nothing in particular. '
                'An NPC with no goal only ever reacts.</td></tr>')

    kinds = "".join(
        f'<option value="{k}">{_escape(GOAL_KIND_LABELS[k])}</option>'
        for k in GOAL_KINDS
    )
    people = "".join(
        f'<option value="{e.id}">{_escape(e.identity.name)}</option>'
        for e in store.entities.list(limit=200) if e.id != entity.id
    )
    return f"""
  <h2>What they want</h2>
  <p class="muted small">Needs are what a body is short of; a goal is what a
  <i>person</i> is after, and it outlives the scene it was formed in. Each kind
  names the actions that serve it, so the engine can weigh a choice against a
  goal without planning a route to it. <b>Wanting fades</b> when nothing moves —
  the clock runs from the last time the goal advanced.</p>
  <p class="muted small"><b>There is no limit on goals; there is a limit on
  attention.</b> {_escape(entity.identity.name)} has
  <b>{attention['budget']:.2f}</b> to give, carrying
  {attention['carrying']} goal{'' if attention['carrying'] == 1 else 's'} costs
  <b>{attention['overhead']:.2f}</b> of it before anything is pursued, and
  <b>{attention['usable']:.2f}</b> is left to actually get things done with. That
  is split by <i>how much they care</i>, so one real ambition beside a scatter of
  half-wants still gets somewhere — and enough half-wants leaves nothing for
  anything. Every part of it is tunable under Goals.</p>
  <table class="ranktable"><thead><tr>
    <th>Goal</th><th>Cares</th><th>Attention</th><th>Progress</th>
    <th>Pressing</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table>
  <div class="paramrow goaladd">
    <select id="goalkind">{kinds}</select>
    <input type="text" id="goaltext" placeholder="what they are after, in your words" maxlength="200">
    <select id="goalsubject"><option value="">nobody in particular</option>{people}</select>
    <input type="number" id="goalpriority" step="0.05" min="0" max="1" value="0.60"
           title="how much they care">
    <input type="number" id="goaldeadline" step="1" min="0" placeholder="days"
           title="days until it stops being worth anything (optional)">
    <button id="goaladd">Give them this goal</button>
  </div>"""


def _pack_sliders(pack, lead=()) -> str:
    """Nine leanings as sliders. Nine number boxes is a spreadsheet, and reading
    an archetype off one is exactly as pleasant as it sounds."""
    out = ""
    for verb in AFFORDANCES:
        value = pack.weight_for(verb) if pack is not None else 0.0
        strong = " lead" if verb in lead else ""
        out += (
            f'<label class="packweight{strong}">'
            f'<span>{_escape(AFFORDANCE_LABELS.get(verb, verb))}</span>'
            f'<input type="range" step="0.05" min="0" max="1" data-verb="{verb}" '
            f'value="{value:.2f}" oninput="this.nextElementSibling.value = '
            f'(+this.value).toFixed(2)">'
            f'<output>{value:.2f}</output></label>'
        )
    return out


def _safety_section(campaign, tuning) -> str:
    """The campaign's lines, and what they are currently switching off.

    Small, and load-bearing. A line outranks a tunable, so without somewhere to
    see and clear one a GM can switch an optional need on and watch nothing
    happen with no explanation anywhere — which is how a working feature reads
    as a broken one.
    """
    safety = (campaign.settings or {}).get("safety") or {}
    lines = [str(item) for item in (safety.get("lines") or [])]

    rows = ""
    for line in lines:
        blocking = [
            name for name, words in tuning_registry.Tuning.OPTIONAL_NEED_LINES.items()
            if any(word in line.lower() for word in words)
        ]
        note = (f'<div class="muted small">Currently switching off: '
                f'<b>{_escape(", ".join(blocking))}</b>, whatever the tuning says.</div>'
                if blocking else "")
        rows += f"""
<tr><td>{_escape(line)}{note}</td>
  <td><button class="dndline-remove ghost" data-line="{_escape(line)}">Clear</button></td></tr>"""
    if not rows:
        rows = ('<tr><td class="muted" colspan="2">No lines set. Everything this '
                'engine can do, it will.</td></tr>')

    return f"""
  <p class="muted small">A <b>line</b> is something that never appears in this
  game. Set at session zero, editable by anyone at the table, and it
  <b>outranks the settings</b> — while a line covers something, the machinery for
  it stays off however <i>This game's rules</i> is configured. A fresh campaign
  starts with the conservative ones already on.</p>
  <p class="muted small">Clearing a line and switching the matching feature on
  are deliberately two separate acts. A table agreeing to play something and a
  GM enabling the machinery for it are different decisions.</p>
  <table class="ranktable"><tbody>{rows}</tbody></table>
  <div class="paramrow">
    <input type="text" id="safetyline" maxlength="120"
           placeholder="something that never appears in this game">
    <button id="safetyadd">Add a line</button>
  </div>"""


def _packs_section(guild, campaign, store, is_gm: bool) -> str:
    """The behaviour archetypes this campaign can draw on, and a way to add one.

    ``04-ENTITIES.md`` §9 asks for this and the role and culture tables still do
    not have it — they are Python, so a GM cannot add a trade. Archetypes are
    the first of those tables to ship as data a GM can actually edit, which is
    the whole reason they are not a dict in a module.
    """
    if not is_gm:
        return ""

    registry = pack_registry.Packs.for_campaign(guild.id, campaign)
    available = registry.available()
    counts: dict = {}
    for entity in store.entities.list(limit=300):
        for assignment in minds.packs_of(entity):
            counts[assignment.key] = counts.get(assignment.key, 0) + 1

    cards = ""
    for key, pack in available.items():
        source = registry.source_of(key)
        # Name the campaign rather than saying "this campaign": the page you are
        # on is a campaign, and a badge that assumes you remember that reads like
        # a claim about the whole server.
        badge = (
            f'<span class="chip">only in {_escape(campaign.name)}</span>'
            if source == "campaign"
            else '<span class="muted small">ships with the bot</span>'
            if source == "builtin"
            else '<span class="muted small">set for this server</span>'
        )
        reset = (
            f'<button class="dndpack-remove ghost" data-key="{_escape(key)}">'
            f'Back to the shipped one</button>'
            if source == "campaign" and key in pack_registry.built_in() else ""
        )
        used = counts.get(key, 0)
        cards += f"""
<details class="packcard" data-key="{_escape(key)}">
  <summary><b>{_escape(pack.label)}</b> {badge}
    <span class="muted small">reaches for {_escape(', '.join(pack.reaches_for))}
    · {used} character{'' if used == 1 else 's'}</span></summary>
  <input type="text" class="packname" value="{_escape(pack.label)}" maxlength="40"
         placeholder="what to call it">
  <input type="text" class="packdesc" value="{_escape(pack.description)}" maxlength="200"
         placeholder="who this is, in a sentence">
  <div class="packweights">{_pack_sliders(pack, pack.reaches_for)}</div>
  <button class="dndpack-save" data-key="{_escape(key)}">Save for this campaign</button>
  {reset}
</details>"""

    return f"""
  <p class="muted small">An archetype is a set of leanings across the things a
  scene can offer — a coward reaches for the door, a merchant reaches for a
  conversation. It works <b>both ways</b>: ask for one when you create an NPC and
  it shapes the person you get, or let one be recognised in somebody you rolled
  and it shapes what they consider doing. An archetype can never widen what is
  possible, only weight it.</p>
  <p class="packlayer">You are editing <b>{_escape(campaign.name)}</b>. Saving here
  changes an archetype for this campaign only; the six that ship are untouched
  everywhere else, and <i>Back to the shipped one</i> undoes an override.</p>
  {cards}
  <details class="packcard packnew">
    <summary><b>Add an archetype</b></summary>
    <input type="text" class="packname" id="packlabel" maxlength="40"
           placeholder="what to call it — Smuggler, Zealot of the Drowned Court">
    <input type="text" class="packdesc" id="packdesc" maxlength="200"
           placeholder="who this is, in a sentence">
    <div class="packweights" id="packnewweights">{_pack_sliders(None)}</div>
    <button id="packadd">Add it</button>
  </details>"""


def _delta_sliders(kind) -> str:
    """What one act does to the two people in it, per axis.

    Same shape as the archetype weights next door, and for the same reason: six
    number boxes is a spreadsheet. Unlike a weight these run **−1…1**, because
    the negative half is a real state and not the absence of the positive one —
    an act that costs trust is not an act that fails to build it.
    """
    out = ""
    for axis in interaction_model.DELTA_FIELDS:
        value = float((kind.deltas if kind is not None else {}).get(axis, 0) or 0)
        if axis == "debt":
            # Debt is a count people tally, not a feeling they hold, so it gets
            # a box. Whole numbers, and the sign is the whole meaning: positive
            # is *this person now owes the other*.
            out += (
                f'<label class="packweight"><span>Debt incurred</span>'
                f'<input type="number" step="1" min="-5" max="5" data-axis="debt" '
                f'value="{int(value)}"><output>{int(value):+d}</output></label>'
            )
            continue
        out += (
            f'<label class="packweight">'
            f'<span>{_escape(axis.title())}</span>'
            f'<input type="range" step="0.05" min="-1" max="1" data-axis="{axis}" '
            f'value="{value:.2f}" oninput="this.nextElementSibling.value = '
            f'(+this.value).toFixed(2)">'
            f'<output>{value:.2f}</output></label>'
        )
    return out


def _interactions_section(guild, campaign, tuning, is_gm: bool) -> str:
    """What one person can do to another here, and what each of those is worth.

    This is the second table to stop being Python (archetypes were the first).
    It replaced **four** hand-maintained dicts keyed by the same strings — the
    deltas, the phrasing, the magnitudes and the list of romance-gated kinds —
    which had already drifted apart: the five romantic kinds were never added to
    the magnitude table, so lying to someone and spending the night with them
    were worth exactly the same.
    """
    if not is_gm:
        return ""

    registry = interaction_registry.Interactions.for_campaign(guild.id, campaign)
    shipped = interaction_registry.built_in()

    cards = ""
    for key, kind in registry.available().items():
        source = registry.source_of(key)
        badge = (
            f'<span class="chip">only in {_escape(campaign.name)}</span>'
            if source == "campaign"
            else '<span class="muted small">ships with the bot</span>'
            if source == "builtin"
            else '<span class="muted small">set for this server</span>'
        )
        reset = (
            f'<button class="dndkind-remove ghost" data-key="{_escape(key)}">'
            f'Back to the shipped one</button>'
            if source == "campaign" and key in shipped else ""
        )
        # A kind belonging to an optional need the campaign has not switched on
        # is not editable-but-inert, it is refused outright — say so, or the
        # sliders read as settings that do nothing.
        gate = ""
        if kind.requires and not tuning.permits_need(kind.requires):
            gate = (
                f'<div class="tuneblocked">This campaign has not switched on '
                f'<b>{_escape(kind.requires)}</b>, so nothing can record this at '
                f'all — not a command, not the engine. Clear the matching line '
                f'under <i>Lines</i> and switch the need on under '
                f'<i>This game\'s rules</i>.</div>'
            )
        cards += f"""
<details class="packcard" data-key="{_escape(key)}">
  <summary><b>{_escape(kind.label)}</b> {badge}
    <span class="muted small">"{_escape(kind.phrase)}" · worth
    {kind.magnitude:.2f}</span></summary>
  {gate}
  <input type="text" class="kindname" value="{_escape(kind.label)}" maxlength="40"
         placeholder="what to call it">
  <input type="text" class="kindphrase" value="{_escape(kind.phrase)}" maxlength="60"
         placeholder="how it reads in a memory — &quot;kept their word to&quot;">
  <input type="text" class="kinddesc" value="{_escape(kind.description)}" maxlength="200"
         placeholder="what this is, in a sentence">
  <label class="packweight kindmag"><span><b>How big it is</b></span>
    <input type="range" step="0.05" min="0" max="1" class="kindmagnitude"
           value="{kind.magnitude:.2f}" oninput="this.nextElementSibling.value =
           (+this.value).toFixed(2)"><output>{kind.magnitude:.2f}</output></label>
  <div class="packweights">{_delta_sliders(kind)}</div>
  <button class="dndkind-save" data-key="{_escape(key)}">Save for this campaign</button>
  {reset}
</details>"""

    return f"""
  <p class="muted small">Every time one person does something to another, this
  table decides what it was. <b>How big it is</b> is the act before anybody's
  circumstances apply — saving a life is large however rich you are, talking is
  small however poor — and the engine scales it per person by what they can
  absorb and what they need, which is how the same favour is the end of one
  man's troubles and an afternoon the other has already forgotten.</p>
  <p class="muted small">The sliders are written <b>from the side of the person
  it happened to</b>. Debt is positive when they now owe the other. The person
  who <i>did</i> it gets an echo of the feeling and the opposite sign of the
  debt, automatically.</p>
  <p class="packlayer">You are editing <b>{_escape(campaign.name)}</b>. Saving
  here changes an act for this campaign only, and <i>Back to the shipped one</i>
  undoes an override.</p>
  {cards}
  <details class="packcard packnew">
    <summary><b>Add something people can do to each other</b></summary>
    <input type="text" class="kindname" id="kindlabel" maxlength="40"
           placeholder="what to call it — Swore an oath to, Sold out">
    <input type="text" class="kindphrase" id="kindphrase" maxlength="60"
           placeholder="how it reads in a memory — &quot;swore an oath to&quot;">
    <input type="text" class="kinddesc" id="kinddesc" maxlength="200"
           placeholder="what this is, in a sentence">
    <label class="packweight kindmag"><span><b>How big it is</b></span>
      <input type="range" step="0.05" min="0" max="1" id="kindmagnitude"
             value="0.40" oninput="this.nextElementSibling.value =
             (+this.value).toFixed(2)"><output>0.40</output></label>
    <div class="packweights" id="kindnewdeltas">{_delta_sliders(None)}</div>
    <button id="kindadd">Add it</button>
  </details>"""


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
    # Read-only by default, and that is the point. Who someone is gets settled
    # when they are made; after that it moves through what happens to them —
    # events, beliefs, imprints, drift (`04-ENTITIES.md` §3a) — not through a GM
    # nudging a slider mid-game. A number you can reach for at any moment is a
    # number that stops meaning anything, and it makes the simulation's own
    # answer unfalsifiable: you can no longer tell whether Marla got colder
    # because of the winter or because you typed -0.4 last Tuesday.
    #
    # The override still exists, because it is the GM's world. It is folded away
    # behind a warning rather than sitting open next to the meters.
    trait_rows = ""
    override_rows = ""
    for axis in TEMPERAMENT + DRIVES + FACULTIES:
        value = traits.axis(axis)
        signed = axis in TEMPERAMENT
        low = -1.0 if signed else 0.0
        # A drive resting at 0.5 must be drawn from 0.5, or every NPC in the
        # world looks grasping the moment they are a hair above average.
        neutral = 0.0 if signed else 0.5
        label = _escape(TRAIT_LABELS.get(axis, axis))
        trait_rows += (
            f'<tr><td>{label}</td>'
            f'<td>{_axis_cell(value, low, 1.0, neutral)}</td></tr>'
        )
        override_rows += (
            f'<tr><td>{label}</td><td>'
            f'<input type="number" class="dndtrait" data-axis="{axis}" '
            f'step="0.01" min="{low}" max="1.0" value="{value:.2f}"></td></tr>'
        )
    override_rows = f"""
<details class="traitoverride">
  <summary>&#9888;&#65039; Overwrite this person by hand</summary>
  <div class="warnbox">
    <p><b>You almost certainly do not want this.</b> Disposition is set when
    someone is created and moves after that through what happens to them —
    events, imprints, long-held beliefs. That is the whole simulation.</p>
    <p class="muted small">Editing an axis directly is not a correction, it is a
    rewrite: nothing in their history explains the new value, and you will no
    longer be able to tell whether they changed because of the world or because
    of you. Use it to author someone at creation — a moral thief, a warm killer
    — and then leave it alone.</p>
  </div>
  <table class="ranktable"><tbody>{override_rows}</tbody></table>
</details>"""

    # --- body ---
    need_rows = ""
    need_view = tuning.needs()
    for name, label in NEED_LABELS.items():
        # An optional need a campaign never asked for is not shown as a row of
        # zeroes; it is not part of this game.
        if not needs_mod.enabled(name, need_view):
            continue
        value = needs.value(name)
        urgency = needs.urgency(name, tuning.needs())
        need_rows += (
            f'<tr><td>{_escape(label)}</td>'
            f'<td>{_axis_cell(value)} <span class="muted small">'
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
  {override_rows}

  <h2>Circumstances</h2>
  <p class="muted small">What they can absorb a loss with — money, rank, security,
  people who owe them. This decides whether an event costs them anything: a debt
  that ends a dock hand's life is a shrug to a merchant lord. Unlike disposition
  it is <b>meant</b> to be set and changed — someone comes into money, someone
  is ruined.</p>
  <table class="ranktable"><tbody>
    <tr><td>Standing</td><td>{_meter(entity.standing)}
      <input type="number" class="dndtrait" data-axis="standing"
             step="0.05" min="0" max="1" value="{entity.standing:.2f}"></td></tr>
    <tr><td>Importance <span class="muted small">(simulation cost only)</span></td>
      <td>{_axis_cell(entity.importance)}</td></tr>
    {_allure_row(entity, tuning)}
  </tbody></table>

  <h2>Body</h2>
  <p class="muted small">Urgency is cubed, so a need is barely felt until it suddenly isn't.</p>
  <table class="ranktable"><tbody>{need_rows}</tbody></table>
  <p>{impulse_html}</p>

  {_decision_section(campaign, entity, store, world_time)}

  {_archetype_section(guild, campaign, entity, tuning)}

  {_goals_section(entity, store, tuning, world_time)}

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
_STATUS_CHIP = {
    catalogue.STATUS_TUNABLE: '<span class="chip">tunable</span>',
    catalogue.STATUS_DATA: '<span class="chip">editable table</span>',
    catalogue.STATUS_BAKED: '<span class="parambaked">baked in — not yet exposed</span>',
}

_LAYER_TEXT = {
    catalogue.LAYER_CAMPAIGN: "campaign → server → built-in default",
    catalogue.LAYER_SERVER: "server → built-in default",
    catalogue.LAYER_DATA: "campaign → server → shipped data file",
    catalogue.LAYER_CODE: "nowhere — it is a constant in the source",
}


def _param_row(entry) -> str:
    """One parameter, with everything needed to decide whether to touch it."""
    related = ""
    if entry.affects:
        related = (
            '<div class="paramrel"><b>Also moves:</b> '
            + ", ".join(f"<code>{_escape(k)}</code>" for k in entry.affects)
            + "</div>"
        )
    siblings = ""
    if entry.siblings:
        shown = list(entry.siblings)[:8]
        more = f" and {len(entry.siblings) - len(shown)} more" \
            if len(entry.siblings) > len(shown) else ""
        siblings = (
            '<div class="paramsib"><b>Combines with:</b> '
            + ", ".join(f"<code>{_escape(k)}</code>" for k in shown)
            + _escape(more) + "</div>"
        )
    planned = ""
    if entry.planned and entry.status == catalogue.STATUS_BAKED:
        planned = (f'<div class="paramplan"><b>Should live in:</b> '
                   f'<code>{_escape(entry.planned)}</code></div>')
    note = (f'<div class="paramnote">{_emphasise(_escape(entry.note))}</div>'
            if entry.note else "")

    return f"""
<tr class="paramrow{' paramrow-baked' if entry.status == catalogue.STATUS_BAKED else ''}">
  <td class="paramkey">
    <b>{_escape(entry.label)}</b> {_STATUS_CHIP.get(entry.status, '')}
    <div class="muted small"><code>{_escape(entry.key)}</code></div>
  </td>
  <td class="paramdesc">
    <div>{_emphasise(_escape(entry.description))}</div>
    {note}{related}{siblings}{planned}
  </td>
  <td class="paramval"><code>{_escape(entry.default)}</code></td>
  <td class="paramspan">{_escape(entry.span)}</td>
  <td class="paramwhere">
    <div>{_escape(_LAYER_TEXT.get(entry.layer, entry.layer))}</div>
    <div class="muted small">read by <code>{_escape(entry.where or '—')}</code></div>
  </td>
</tr>"""


def parameters_html(guild) -> str:
    """Every parameter in the engine, in one page.

    The owner's standing rule is that **everything is a tweakable parameter
    visible to the bot owner**, and this is where that is checkable rather than
    asserted. It deliberately lists what is *not* exposed as well: a constant
    that shapes behaviour and has no control is a defect, and a defect nobody
    can see is one nobody fixes.
    """
    counts = catalogue.summary()
    sections, nav = "", ""
    for index, (group, rows) in enumerate(catalogue.grouped()):
        exposed = sum(1 for row in rows if row.exposed)
        baked = len(rows) - exposed
        slug = "".join(c if c.isalnum() else "-" for c in group.lower())
        nav += f"""
<a class="navrow{' active' if index == 0 else ''}" href="#param-{slug}"
   data-panel="param-{slug}">
  <span class="navemoji">{_GROUP_EMOJI.get(group, '📐')}</span>
  <span class="navlabel">{_escape(group)}</span>
  <span class="navhint">{exposed} tunable{'' if exposed == 1 else 's'}"""
        nav += (f", {baked} baked in" if baked else "") + "</span></a>"

        body = "".join(_param_row(row) for row in rows)
        sections += f"""
<section class="panel{'' if index == 0 else ' hidden'}" id="param-{slug}">
  <h2 class="panelhead">{_GROUP_EMOJI.get(group, '📐')} {_escape(group)}</h2>
  <table class="paramtable">
    <thead><tr><th>Parameter</th><th>What it does, and what it touches</th>
      <th>Default</th><th>Range</th><th>Where it can be set</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>"""

    return f"""
<p><a href="/guild/{guild.id}/tabletop">← Tabletop</a></p>
<h1>📐 Parameters</h1>
<p class="muted">Every number that shapes how this engine behaves, what it
touches, and where it can be changed. <b>{counts['total']}</b> in total:
<b>{counts['tunable']}</b> settings you can change per campaign or per server,
<b>{counts['data']}</b> editable tables, and <b>{counts['baked']}</b> still
written into the source with no control yet.</p>
<p class="muted small">The last number is the point of this page. A constant
that shapes behaviour and cannot be changed is a black box, and one that is not
written down anywhere is a black box nobody knows about. Those rows name the
file and the current value, so the list is a work queue rather than an
admission. <b>Adding a parameter here is part of adding a parameter</b> — the
test suite fails if a new constant appears and this page does not know about
it.</p>
<div class="tunepage sidepanels">
  <aside class="sidebar sidenav">{nav}</aside>
  <main class="content">{sections}</main>
</div>
<script>
(function () {{
  // Same one-panel-at-a-time behaviour as the tuning page, scoped to this one.
  const rows = document.querySelectorAll(".sidenav .navrow[data-panel]");
  rows.forEach((row) => {{
    row.addEventListener("click", (event) => {{
      event.preventDefault();
      rows.forEach((other) => other.classList.remove("active"));
      row.classList.add("active");
      document.querySelectorAll("main.content .panel").forEach((panel) => {{
        panel.classList.toggle("hidden", panel.id !== row.dataset.panel);
      }});
    }});
  }});
}})();
</script>"""


async def parameters_page(request: web.Request):
    """Admin-level: the whole parameter catalogue."""
    from web.routes import _page

    guild, scope = request["guild"], request["scope"]
    return _page(
        f"Parameters · {guild.name}",
        parameters_html(guild),
        scope=scope,
        guild=guild,
        current="tabletop",
    )


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
