"""
The DodoLand page — every number in the system, in one place.

Four things it has to show, and they are the four things that were asked for:

1. each building, the channels that feed it, and what participation in each is
   worth there;
2. each building's tiers, and what reaching the next one currently costs;
3. a live preview of where everybody actually stands, computed from real data,
   **visible only here** until the numbers are right;
4. the total ranking, town power, and the map the towns sit on.

Plus the whole metric registry with its full setup, because a weight or a cap
that only exists in a Python file is exactly the black box this project keeps
deciding not to build.

**The preview is the point of the page.** It exists so the economy can be tuned
against the live server before a single player is shown anything, which is why
this page is admin-scoped and the map is not linked from anywhere public yet.

Server-rendered, matching the existing pages' classes. The behaviour is a small
inline script rather than an addition to ``panel.js``, which is already 123KB
and shared by every other page.
"""

from __future__ import annotations

import asyncio
import base64
import html

from aiohttp import web

from helpers.dodoland import buildings as building_rules
from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import parameters as dodo_params
from helpers.dodoland import standing
from helpers.dodoland import store as store_module


def _e(value) -> str:
    return html.escape(str(value))


def _name_of(guild, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    return member.display_name if member else f"User {user_id}"


def _channel_name(guild, channel_id: int) -> str:
    channel = guild.get_channel(int(channel_id))
    return f"#{channel.name}" if channel else f"channel {channel_id}"


# --------------------------------------------------------------------------- #
#  Metrics: the full setup for every one
# --------------------------------------------------------------------------- #
def _metric_block(guild, setup: dict) -> str:
    """One metric with every knob it has, as editable controls."""
    from web.routes import _param_input

    kind = "counts against another person" if setup["kind"] == "social" else "counts on its own"
    origin = ("rebuildable from the message archive" if setup["backfill"]
              else "counted forward only, from the day tracking started")

    controls = ""
    fields = [("weight", dodo_params.weight_key(setup["key"]), "int", "Points each"),
              ("daily_cap", dodo_params.daily_cap_key(setup["key"]), "int", "Daily cap")]
    if setup["partner_cap"] is not None:
        fields.append(("partner_cap", dodo_params.partner_cap_key(setup["key"]),
                       "int", "Cap per person, per day"))
    for value_key, param_key, ptype, label in fields:
        controls += f"""
    <label class="dlfield"><span class="muted small">{_e(label)}</span>
      {_param_input({"key": param_key, "type": ptype, "value": setup[value_key]}, guild)}
    </label>"""

    channels = _param_input(
        {"key": dodo_params.channels_key(setup["key"]), "type": "list_channel",
         "value": setup["channels"]}, guild)
    where = ("everywhere DodoLand tracks" if not setup["channels"]
             else ", ".join(_channel_name(guild, c) for c in setup["channels"][:6]))

    return f"""
<div class="rulecard dlmetric">
  <div class="rulehead"><b>{_e(setup['label'])}</b>
    <span class="chip">{_e(kind)}</span>
    <code>{_e(setup['key'])}</code></div>
  <div class="muted small">{_e(setup['description'])}</div>
  <div class="muted small">{_e(origin)}</div>
  <div class="dlfields">{controls}</div>
  <div class="paramrow wide">
    <div><b>Channels it counts in</b>
      <div class="muted small">Currently {_e(where)}. Empty means wherever
      DodoLand tracks at all.</div></div>
    {channels}
  </div>
</div>"""


def _metrics_html(bot, guild) -> str:
    blocks = "".join(
        _metric_block(guild, dodo_params.metric_setup(bot.dodoland_params, guild.id, m.key))
        for m in metric_registry.METRICS
    )
    return f"""
<section class="sidepanel" data-panel="dl-metrics" hidden>
  <h2 class="panelhead">\U0001F4CF What counts</h2>
  <p class="muted">Every act DodoLand records, what it is worth, and the caps that
  stop it being farmed. A social act is capped <b>per person per day</b>: past
  the cap the act still happens and simply stops scoring, so no score can grow
  without involving more people.</p>
  {blocks}
</section>"""


# --------------------------------------------------------------------------- #
#  Buildings
# --------------------------------------------------------------------------- #
def _tier_rows(resolved: list[dict]) -> str:
    rows = ""
    for index, tier in enumerate(resolved, start=1):
        decided = ("its floor" if tier["source"] == "floor"
                   else f"the {tier['percentile']:g}th percentile of this server")
        rows += f"""
  <tr><td class="rankindex">{index}</td>
      <td><b>{_e(tier['title'])}</b></td>
      <td class="nowrap">{tier['threshold']:,}</td>
      <td class="muted small">{_e(decided)} · percentile {tier['percentile']:g},
          floor {tier['floor']:,}, live {tier['derived']:,}</td></tr>"""
    return rows or '<tr><td colspan="4" class="muted">No tiers set.</td></tr>'


def _building_card(guild, building: dict, resolved: list[dict], population: int) -> str:
    channels = building.get("channels") or {}
    chips = "".join(
        f'<span class="chip">{_e(_channel_name(guild, cid))} &times;{weight:g}</span>'
        for cid, weight in sorted(channels.items())
    ) or '<span class="muted small">No channels yet, so nothing builds this.</span>'
    emphasis = "".join(
        f'<span class="chip">{_e(key)} &times;{weight:g}</span>'
        for key, weight in sorted((building.get("metric_weights") or {}).items())
    ) or '<span class="muted small">No extra emphasis.</span>'

    return f"""
<div class="rulecard dlbuilding" data-key="{_e(building['key'])}">
  <div class="rulehead">
    <b>{_e(building.get('icon') or '')} {_e(building['name'])}</b>
    <code>{_e(building['key'])}</code>
  </div>
  <div class="paramrow wide"><div><b>Channels that build it</b>
    <div class="muted small">A weight is a multiplier on everything earned in
    that room. 0 means the room does not feed this building.</div></div>
    <div class="chips">{chips}</div></div>
  <div class="paramrow wide"><div><b>Its own emphasis</b>
    <div class="muted small">Multiplies one metric for this building only,
    without touching what that act is worth anywhere else.</div></div>
    <div class="chips">{emphasis}</div></div>
  <table class="previewtable dltiers">
    <thead><tr><th></th><th>Tier</th><th>Costs now</th><th>Where that came from</th></tr></thead>
    <tbody>{_tier_rows(resolved)}</tbody>
  </table>
  <p class="muted small">Thresholds are derived from the {population} people who
  currently score in this building, so a tier means the same thing on a quiet
  server and a busy one. The floor is what stops a top tier being cheap while
  the server is young.</p>
</div>"""


def _buildings_html(bot, guild, result: dict) -> str:
    buildings = bot.dodoland_buildings.buildings(guild.id)
    configured = bot.dodoland_buildings.is_configured(guild.id)
    cards = ""
    for building in buildings:
        key = building["key"]
        population = sum(
            1 for person in result["people"].values()
            if person["buildings"].get(key, {}).get("points", 0) > 0
        )
        cards += _building_card(guild, building, result["tiers"].get(key, []), population)

    warning = "" if configured else """
  <div class="tuneblocked">These are the starting buildings, and no channels are
  attached to any of them yet, so nothing is being built. Point each one at the
  rooms it belongs to and save.</div>"""

    import json
    editor = _e(json.dumps(buildings, indent=2, ensure_ascii=False))
    return f"""
<section class="sidepanel" data-panel="dl-buildings" hidden>
  <h2 class="panelhead">\U0001F3D8 Buildings</h2>
  <p class="muted">A building is a place, so it scores from <b>channels</b>.
  Every building is reachable by anyone through ordinary sociable activity;
  trial rank adds flourish on top and never the tier itself.</p>
  {warning}
  {cards}
  <h3 class="panelhead">Edit</h3>
  <p class="muted small">Names, icons, channel weights, per-building emphasis and
  tiers. Saving validates everything before it is stored, and refuses rather
  than half-applying.</p>
  <textarea id="dlbuildings" class="dljson" rows="18" spellcheck="false">{editor}</textarea>
  <div class="rulebtns">
    <button id="dlsavebuildings">Save buildings</button>
    <span id="dlbuildingsmsg" class="muted small"></span>
  </div>
</section>"""


# --------------------------------------------------------------------------- #
#  Preview and ranking
# --------------------------------------------------------------------------- #
def _preview_html(bot, guild, result: dict, buildings: list[dict],
                  flourish: dict) -> str:
    heads = "".join(f"<th>{_e(b.get('icon') or '')} {_e(b['name'])}</th>" for b in buildings)
    rows = ""
    for person in result["order"][:200]:
        cells = ""
        for building in buildings:
            score = person["buildings"].get(building["key"], {})
            tier = score.get("tier")
            label = (f"<b>{_e(score.get('tier_title'))}</b>" if tier is not None
                     else '<span class="muted">not started</span>')
            cells += (f'<td>{label}<div class="muted small">'
                      f'{score.get("points", 0):,} pts</div></td>')
            glow = flourish.get(person["user_id"]) or flourish_rules.BLANK
        badge = (f'<div class="muted small">{_e(glow["label"])}'
                 + (f' · {_e(glow["rank_name"])}' if glow["rank_name"] else "")
                 + "</div>") if glow["level"] else ""
        rows += f"""
  <tr><td class="rankindex">{person['place']}</td>
      <td><b>{_e(_name_of(guild, person['user_id']))}</b>{badge}</td>
      <td class="nowrap"><b>{person['power']:,}</b></td>
      <td class="muted small nowrap">{person['reached']:,} people
          ({person['reach_points']:,} pts)</td>
      {cells}</tr>"""
    if not rows:
        rows = ('<tr><td colspan="4" class="muted">Nothing recorded yet. The '
                'listener started with this build; give it a day.</td></tr>')

    return f"""
<section class="sidepanel" data-panel="dl-preview">
  <h2 class="panelhead">\U0001F441 Preview</h2>
  <p class="muted">Where everybody stands right now, worked out live from real
  activity. <b>Nobody outside this panel can see any of this.</b> It is here so
  the economy can be tuned against the actual server before a single player is
  shown a town.</p>
  <p class="muted small">The name column also carries <b>flourish</b>: the
  visual effect a person's trial rank earns. Flourish is cosmetic and never
  changes a building tier, so every building stays reachable by anybody, and the
  scarce thing is the one that costs nothing to grant and cannot be farmed.</p>
  <table class="previewtable">
    <thead><tr><th></th><th>Person</th><th>Town power</th><th>People reached</th>
    {heads}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""


# --------------------------------------------------------------------------- #
#  The map
# --------------------------------------------------------------------------- #
def _map_html(bot, guild) -> str:
    image = bot.dodoland_buildings.map_image(guild.id)
    plots = bot.dodoland_buildings.plots(guild.id)
    if image:
        raw = image.get("data")
        blob = bytes(raw) if raw is not None else b""
        encoded = base64.b64encode(blob).decode("ascii")
        preview = (f'<img class="dlmap" alt="The server map" '
                   f'src="data:{_e(image.get("content_type"))};base64,{encoded}">')
        state = f"A map is set ({len(blob):,} bytes). Uploading another replaces it."
    else:
        preview = '<div class="muted">No map uploaded yet.</div>'
        state = "Upload the image this server's continent is drawn on."

    settled = "".join(
        f'<span class="chip">{_e(_name_of(guild, uid))} '
        f'({spot.get("x", 0):g}, {spot.get("y", 0):g})</span>'
        for uid, spot in sorted(plots.items())
    ) or '<span class="muted small">Nobody has settled yet.</span>'

    return f"""
<section class="sidepanel" data-panel="dl-map" hidden>
  <h2 class="panelhead">\U0001F5FA The map</h2>
  <p class="muted">The world is an image you upload, not one the bot generates.
  That removes the vector editor, the procedural coastlines and the elevation
  polygons from the build entirely, and it means the map is handcrafted and
  yours on day one. Players pick their own plot on it.</p>
  <p class="muted small">{_e(state)} PNG, JPEG, WebP or SVG, under 4MB. Plots are
  stored as percentages of the image, so redrawing the map at a different size
  never moves anybody's town.</p>
  {preview}
  <div class="rulebtns">
    <input type="file" id="dlmapfile" accept="image/png,image/jpeg,image/webp,image/svg+xml">
    <button id="dlmapclear">Remove map</button>
    <span id="dlmapmsg" class="muted small"></span>
  </div>
  <div class="paramrow wide"><div><b>Settled towns</b>
    <div class="muted small">Where people have chosen to build.</div></div>
    <div class="chips">{settled}</div></div>
</section>"""


# --------------------------------------------------------------------------- #
#  Settings and the page
# --------------------------------------------------------------------------- #
def _settings_html(bot, guild) -> str:
    from web.routes import _param_input

    generated = {dodo_params.weight_key(m.key) for m in metric_registry.METRICS}
    generated |= {dodo_params.daily_cap_key(m.key) for m in metric_registry.METRICS}
    generated |= {dodo_params.partner_cap_key(m.key) for m in metric_registry.METRICS}
    generated |= {dodo_params.channels_key(m.key) for m in metric_registry.METRICS}

    rows = ""
    for spec in dodo_params.DODOLAND_PARAMETERS:
        if spec["key"] in generated:
            continue  # shown with its metric instead
        entry = {**spec, "value": bot.dodoland_params.get(guild.id, spec["key"])}
        wide = " wide" if spec["type"] in ("list_channel", "list_role", "list_str") else ""
        rows += f"""
  <div class="paramrow{wide}">
    <div><b>{_e(spec['label'])}</b>
      <div class="muted small">{_e(spec['description'])}</div>
      <div class="muted small"><code>{_e(spec['key'])}</code></div></div>
    {_param_input(entry, guild)}
  </div>"""
    return f"""
<section class="sidepanel" data-panel="dl-settings" hidden>
  <h2 class="panelhead">⚙️ Settings</h2>
  <p class="muted">What is tracked, over what window, and how forgiving the
  intake is. The per-metric knobs live with their metric under "What counts".</p>
  <div class="params">{rows}</div>
</section>"""


def _script(guild_id: int) -> str:
    """This page's own behaviour. Snowflakes are strings: a 64-bit id parsed as a
    JavaScript number loses its last digits and every request 404s."""
    return """
<script>
(function () {
  var GID = "%s";
  function post(path, body, done) {
    fetch("/api/guild/" + GID + "/dodoland/" + path, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(done)
      .catch(function (e) { done({ok: false, error: String(e)}); });
  }
  // The side menu, same behaviour as the other multi-panel pages.
  document.querySelectorAll('.sidenavitem[data-panel]').forEach(function (item) {
    item.addEventListener('click', function (event) {
      event.preventDefault();
      document.querySelectorAll('.sidenavitem').forEach(function (n) {
        n.classList.remove('active');
      });
      item.classList.add('active');
      document.querySelectorAll('.sidepanel').forEach(function (panel) {
        panel.hidden = panel.dataset.panel !== item.dataset.panel;
      });
    });
  });
  // Scalar knobs save on change; multiselects announce themselves the same way
  // the rest of the panel's do.
  function valueOf(el) {
    if (el.type === 'checkbox') return el.checked;
    return el.value;
  }
  document.querySelectorAll('.sidepanel .param').forEach(function (el) {
    el.addEventListener('change', function () {
      post('param', {key: el.dataset.key, value: valueOf(el)}, function (res) {
        el.classList.toggle('act-bad', !res.ok);
        el.classList.toggle('act-ok', !!res.ok);
      });
    });
  });
  document.querySelectorAll('.sidepanel .multiselect').forEach(function (box) {
    box.addEventListener('mschange', function () {
      var ids = Array.prototype.map.call(
        box.querySelectorAll('.ms-opt[data-selected="1"]'),
        function (o) { return o.dataset.id; });
      post('param', {key: box.dataset.key, value: ids}, function () {});
    });
  });
  var save = document.getElementById('dlsavebuildings');
  if (save) save.addEventListener('click', function () {
    var msg = document.getElementById('dlbuildingsmsg');
    var parsed;
    try { parsed = JSON.parse(document.getElementById('dlbuildings').value); }
    catch (e) { msg.textContent = 'That is not valid JSON: ' + e.message; return; }
    msg.textContent = 'Saving...';
    post('buildings', {buildings: parsed}, function (res) {
      msg.textContent = res.ok ? 'Saved. Reload to see the new tiers.'
                               : ('Refused: ' + res.error);
    });
  });
  var file = document.getElementById('dlmapfile');
  if (file) file.addEventListener('change', function () {
    var chosen = file.files && file.files[0];
    var msg = document.getElementById('dlmapmsg');
    if (!chosen) return;
    var reader = new FileReader();
    reader.onload = function () {
      msg.textContent = 'Uploading...';
      post('map', {data: String(reader.result).split(',').pop(),
                   content_type: chosen.type}, function (res) {
        msg.textContent = res.ok ? 'Map saved. Reload to see it.'
                                 : ('Refused: ' + res.error);
      });
    };
    reader.readAsDataURL(chosen);
  });
  var clear = document.getElementById('dlmapclear');
  if (clear) clear.addEventListener('click', function () {
    post('map', {data: null}, function (res) {
      document.getElementById('dlmapmsg').textContent =
        res.ok ? 'Map removed. Reload.' : ('Refused: ' + res.error);
    });
  });
})();
</script>""" % guild_id


async def dodoland_page(request: web.Request):
    from web.routes import _page

    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    buildings = bot.dodoland_buildings.buildings(guild.id)
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)

    # Every read here is blocking pymongo, and this handler runs on the bot's own
    # event loop. Doing it inline stops the bot responding while Mongo works.
    def compute():
        return standing.guild_standings(bot.dodoland, bot.dodoland_params,
                                        guild.id, buildings, since=since)

    result = await asyncio.get_running_loop().run_in_executor(None, compute)
    # Read-only, and the only thing DodoLand reads from outside itself.
    flourish = await asyncio.get_running_loop().run_in_executor(
        None, flourish_rules.flourish_map, bot, guild.id)

    tracking = bot.visibility.feature_active(guild.id, "dodoland_tracking", "dodoland")
    counted = len(result["people"])
    status = ("counting now" if tracking else
              "switched off, so nothing is being recorded")

    nav = ""
    for key, emoji, label, hint in (
        ("dl-preview", "\U0001F441", "Preview", f"{counted} scoring"),
        ("dl-buildings", "\U0001F3D8", "Buildings", f"{len(buildings)}"),
        ("dl-metrics", "\U0001F4CF", "What counts", f"{len(metric_registry.METRICS)} metrics"),
        ("dl-map", "\U0001F5FA", "The map", "upload"),
        ("dl-settings", "⚙️", "Settings", "intake"),
    ):
        active = " active" if key == "dl-preview" else ""
        nav += (f'<a class="sidenavitem{active}" href="#{key}" data-panel="{key}">'
                f'<span class="navemoji">{emoji}</span>'
                f'<span class="navlabel">{_e(label)}</span>'
                f'<span class="navhint">{_e(hint)}</span></a>')

    body = f"""
<h1>\U0001F3D8 DodoLand</h1>
<p class="muted">The socialite tribe's town map. Tracking is <b>{_e(status)}</b>,
looking back {window} days, with <b>{counted}</b> people scoring.
Nothing here is visible to anybody but this panel.</p>
<div class="sidepanels">
  <nav class="sidenav">{nav}</nav>
  <div class="content">
    {_preview_html(bot, guild, result, buildings, flourish)}
    {_buildings_html(bot, guild, result)}
    {_metrics_html(bot, guild)}
    {_map_html(bot, guild)}
    {_settings_html(bot, guild)}
  </div>
</div>
{_script(guild.id)}"""
    return _page(f"DodoLand · {guild.name}", body, scope=scope, guild=guild,
                 current="dodoland")
