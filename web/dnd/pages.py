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

from helpers.dnd import rules
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.world.entity import KIND_FACTION, KIND_NPC, KIND_PC
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

    enabled = bot.visibility.cog_enabled(guild.id, "dnd")
    warning = (
        "" if enabled else
        '<p class="muted"><b>The tabletop cog is currently off for this server.</b> '
        f'Turn it back on from the <a href="/guild/{guild.id}">main page</a>.</p>'
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
</div>"""


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

  <h2>Recent events</h2>
  <p class="muted small">Every change is an event, which is what makes replay and undo possible.</p>
  {_events_table(store, guild)}

  {f'<p class="muted small">{_escape(attribution)}</p>' if attribution else ''}
</div>"""


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
