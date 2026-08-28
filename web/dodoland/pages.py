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
from web.dodoland import buildings_ui
from helpers.dodoland import flourish as flourish_rules
from helpers.dodoland import mapview
from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import parameters as dodo_params
from helpers.dodoland import standing
from helpers.dodoland import store as store_module


# What each preview is actually answering. Two honest answers to two different
# questions: being able to hold them side by side is the difference between
# "these numbers look odd" and "these numbers look odd because of the rebuild".
_BASIS_BLURB = {
    store_module.BASIS_ALL: (
        "Everything: the rebuilt history from the message archive plus everything "
        "counted live since tracking started. This is what people would see if the "
        "map opened today, and it is the one to tune against."),
    store_module.BASIS_LIVE: (
        "Only what has been counted since the listener started, ignoring the "
        "rebuilt history entirely. This is what a brand new server looks like, and "
        "it is the honest picture of how fast the thing actually accrues."),
    store_module.BASIS_BACKFILL: (
        "Only the history rebuilt from the message archive."),
}


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

    # The shared list_channel widget lists channels in whatever order the API
    # returned them, which with sixty-odd rooms is no order at all. This one is
    # grouped and ordered the way the server's own sidebar is.
    channels = buildings_ui.channel_multiselect(
        guild, key=dodo_params.channels_key(setup["key"]), selected=setup["channels"])
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
    """The buildings editor. Lives in its own module: it is the densest
    surface here and the one most likely to keep changing."""
    return buildings_ui.buildings_section(bot, guild, result)


def _preview_html(bot, guild, result: dict, buildings: list[dict],
                  flourish: dict, *, basis: str, panel: str, shown: bool) -> str:
    """One row per person, and deliberately **not** one column per building.

    Fifteen buildings became fifteen columns, which pushed the whole page
    sideways and made the numbers unreadable. A town is described by what
    actually stands in it, so the buildings somebody has started are listed in a
    single cell and the ones at zero are simply not mentioned. That keeps the
    row width bounded however many buildings a server invents.
    """
    rows = ""
    for person in result["order"][:200]:
        glow = flourish.get(person["user_id"]) or flourish_rules.BLANK
        badge = ""
        if glow["level"]:
            badge = (f'<div class="muted small">{_e(glow["label"])}'
                     + (f' · {_e(glow["rank_name"])}' if glow["rank_name"] else "")
                     + "</div>")

        started = [score for score in person["buildings"].values()
                   if score.get("tier") is not None]
        started.sort(key=lambda score: -score.get("points", 0))
        if started:
            built = " ".join(
                f'<span class="chip">{_e(score.get("icon") or "")} '
                f'{_e(score["name"])}: <b>{_e(score["tier_title"])}</b> '
                f'({score["points"]:,})</span>'
                for score in started
            )
        else:
            built = '<span class="muted small">nothing built yet</span>'

        rows += f"""
  <tr><td class="rankindex">{person['place']}</td>
      <td><b>{_e(_name_of(guild, person['user_id']))}</b>{badge}</td>
      <td class="nowrap"><b>{person['power']:,}</b></td>
      <td class="muted small nowrap">{person['reached']:,} people
          ({person['reach_points']:,} pts)</td>
      <td><div class="chips">{built}</div></td></tr>"""

    if not rows:
        rows = ('<tr><td colspan="5" class="muted">Nothing recorded on this '
                'basis yet.</td></tr>')

    unattached = sum(1 for b in buildings if not (b.get("channels") or {}))
    note = ""
    if unattached:
        note = (f'<div class="tuneblocked">{unattached} of {len(buildings)} '
                "buildings have no rooms attached, so they cannot score for "
                "anybody. Attach channels under <b>Buildings</b>, or press "
                "<b>Suggest from channel names</b> there.</div>")

    return f"""
<section class="sidepanel" data-panel="{panel}"{'' if shown else ' hidden'}>
  <h2 class="panelhead">\U0001F441 Preview: {_e(store_module.BASIS_LABELS[basis])}</h2>
  <p class="muted">{_e(_BASIS_BLURB[basis])}
  <b>Nobody outside this panel can see any of this.</b></p>
  <p class="muted small">The name column also carries <b>flourish</b>: the
  visual effect a person's trial rank earns. Flourish is cosmetic and never
  changes a building tier, so every building stays reachable by anybody, and the
  scarce thing is the one that costs nothing to grant and cannot be farmed.</p>
  {note}
  <div class="dlscroll">
    <table class="previewtable">
      <thead><tr><th></th><th>Person</th><th>Town power</th>
      <th>People reached</th><th>What stands there</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>"""


# --------------------------------------------------------------------------- #
#  The map
# --------------------------------------------------------------------------- #
def _town_markers(towns: list[dict]) -> str:
    """The towns, as absolutely-positioned markers over the base image.

    Flourish is a class rather than inline style so the effects live in the
    stylesheet where they can be looked at and changed, and so a town with no
    rank carries no extra rendering cost at all.
    """
    out = ""
    for town in towns:
        classes = f"dltown fl{town['flourish']}" + ("" if town["lit"] else " dim")
        title = f"{town['name']} · {town['power']:,} power"
        if town["rank_name"]:
            title += f" · {town['rank_name']}"
        if not town["settled"]:
            title += " · suggested, not yet settled"
        built = ", ".join(f"{k}: {v}" for k, v in town["tiers"].items())
        if built:
            title += f" · {built}"
        out += (
            f'<button class="{classes}" style="left:{town["x"]}%;top:{town["y"]}%;'
            f'--dl-size:{town["size"]:g}" data-user="{town["user_id"]}" '
            f'title="{_e(title)}">'
            f'<span class="dltowndot"></span>'
            f'<span class="dltownname">{_e(town["name"])}</span></button>'
        )
    return out


def _map_html(bot, guild, towns: list[dict]) -> str:
    image = bot.dodoland_buildings.map_image(guild.id)
    settled_count = sum(1 for town in towns if town["settled"])

    if image:
        raw = image.get("data")
        blob = bytes(raw) if raw is not None else b""
        encoded = base64.b64encode(blob).decode("ascii")
        canvas = f"""
  <div class="dlcanvas" id="dlcanvas">
    <img class="dlmap" alt="The server map"
         src="data:{_e(image.get('content_type'))};base64,{encoded}">
    {_town_markers(towns)}
  </div>"""
        state = f"A map is set ({len(blob):,} bytes). Uploading another replaces it."
    else:
        canvas = ('<div class="muted">No map uploaded yet. Towns are placed and '
                  'drawn as soon as there is an image to place them on.</div>')
        state = "Upload the image this server's continent is drawn on."

    return f"""
<section class="sidepanel" data-panel="dl-map" hidden>
  <h2 class="panelhead">🗺 The map</h2>
  <p class="muted">The world is an image you upload, not one the bot generates.
  That removes the vector editor, the procedural coastlines and the elevation
  polygons from the build entirely, and it means the map is handcrafted and
  yours on day one.</p>
  <p class="muted small">{_e(state)} PNG, JPEG, WebP or SVG, under 4MB. Positions
  are percentages of the image, so redrawing the map at a different size never
  moves anybody's town.</p>
  <div class="rulebtns">
    <input type="file" id="dlmapfile" accept="image/png,image/jpeg,image/webp,image/svg+xml">
    <button id="dlmapclear">Remove map</button>
    <span id="dlmapmsg" class="muted small"></span>
  </div>
  {canvas}
  <p class="muted small"><b>{settled_count}</b> of <b>{len(towns)}</b> towns have
  been settled deliberately. The rest are <i>suggested</i>: placed beside the
  people their owner actually talks to, using the relation graph the listener
  builds. Clusters on this map are friend groups, and whoever sits between two
  clusters is the person who bridges them. A suggestion is never binding, and
  anybody who settles keeps their spot forever.</p>
  <p class="muted small">Click a town to place it where you click next, or use
  this once the player-facing flow exists. Dim towns have had no activity inside
  the lit window; that is the only thing dormancy ever costs, and coming back
  lights them again. Nothing is ever taken away.</p>
</section>"""


# --------------------------------------------------------------------------- #
#  Settings and the page
# --------------------------------------------------------------------------- #
def _backfill_html(bot, guild) -> str:
    """The archive rebuild, and an honest account of what it can and cannot do."""
    live_from = bot.dodoland.first_day(guild.id)
    started = (f"The listener's own rows begin on <b>{_e(live_from)}</b>, and the "
               "rebuild stops strictly before that, so it can never overwrite a "
               "real day." if live_from else
               "The listener has recorded nothing yet, so the rebuild covers "
               "everything up to today.")
    rebuildable = ", ".join(
        metric_registry.get(key).label for key in ("message", "mention_given", "mention_received")
    )
    return f"""
<section class="sidepanel" data-panel="dl-backfill" hidden>
  <h2 class="panelhead">\U000023EA Rebuild history</h2>
  <p class="muted">The message archive holds every message this bot has ever
  seen, so three metrics can be reconstructed across the whole life of the
  server: <b>{_e(rebuildable)}</b>. That is what lets the map open with towns
  that already have history and a relation graph that already knows who talks to
  whom.</p>
  <p class="muted small">Everything else (pictures, replies, threads, voice,
  events, invites) was never stored anywhere and can only be counted forward
  from the day tracking started. No rebuild will ever produce them.</p>
  <p class="muted small">{started} Rebuilt days are valued by exactly the rules a
  live day is: the same intake function, the same caps, the same per-metric
  channel lists. Running it twice writes the same numbers rather than doubling
  them, so it is safe to repeat after changing a weight.</p>
  <div class="rulebtns">
    <button id="dlpreviewbackfill">Preview without writing</button>
    <button id="dlrunbackfill">Rebuild history</button>
  </div>
  <pre id="dlbackfillout" class="dljson" hidden></pre>
  <span id="dlbackfillmsg" class="muted small"></span>
</section>"""


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
    """This page's own behaviour.

    Three things this has to get right, all of which it got wrong the first time
    and each of which produced a control that looked fine and did nothing:

    * **Run after ``panel.js``.** That file defines ``bindMultiSelect``, which is
      what makes a channel picker clickable, and it loads *after* this inline
      script. Binding on ``DOMContentLoaded`` means both exist by then.
      Rendering a multiselect without binding it produces a list of dead divs.
    * **Bind our own controls.** ``panel.js`` only wires parameters and
      multiselects inside a ``.cogcard``, and this page has none, so nothing on
      it was ever bound.
    * **Say what happened.** A save with no feedback is indistinguishable from a
      save that failed. Every write here reports either way, with the server's
      own error text rather than a shrug.

    The guild id is substituted rather than %-formatted: this script is full of
    literal percent signs (map positions are percentages) and %-format reads
    every one as a conversion. It is quoted as a **string**, because a 64-bit
    snowflake parsed as a JavaScript number loses its last digits and every
    request 404s. That has caused an outage here before.
    """
    return """
<script>
document.addEventListener('DOMContentLoaded', function () {
  var GID = "__DL_GID__";

  // panel.js's flash() writes into #status and silently gives up when there is
  // none, which is how every "saved" message on this page went nowhere. The
  // element is rendered server-side now; this creates one anyway if it is ever
  // missing again, because a save with no feedback is indistinguishable from a
  // save that failed.
  function toast() {
    var el = document.getElementById('status');
    if (!el) {
      el = document.createElement('p');
      el.id = 'status';
      el.className = 'status';
      document.body.appendChild(el);
    }
    return el;
  }
  var _toastTimer = null;
  function say(el, text, ok) {
    if (el) { el.textContent = text; el.style.color = ok ? '' : '#c0392b'; }
    if (!text) return;
    var bar = toast();
    bar.textContent = text;
    bar.className = 'status show ' + (ok ? 'ok' : 'err');
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function () { bar.className = 'status'; }, 2500);
  }
  function post(path, body) {
    return fetch("/api/guild/" + GID + "/dodoland/" + path, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () {
        return {ok: false, error: "HTTP " + r.status};
      });
    }).catch(function (e) { return {ok: false, error: String(e)}; });
  }

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

  var settingsMsg = document.getElementById('dlsettingsmsg');
  document.querySelectorAll('.sidepanel .param').forEach(function (el) {
    el.addEventListener('change', function () {
      var value = (el.type === 'checkbox') ? el.checked : el.value;
      post('param', {key: el.dataset.key, value: value}).then(function (res) {
        say(settingsMsg, res.ok ? (el.dataset.key + ' saved')
                                : ('Could not save ' + el.dataset.key + ': ' + res.error),
            res.ok);
      });
    });
  });

  // Fill every picker from the one shared template before binding it. The
  // options are identical apart from which are ticked, so they are sent once
  // rather than repeated in each of the thirty-odd pickers on this page.
  var optionTemplate = document.getElementById('dlchanoptions');
  function fill(ms) {
    var host = ms.querySelector('.ms-options');
    if (!optionTemplate || !host || host.children.length) return;
    var chosen = {};
    (ms.dataset.chosen || '').split(',').forEach(function (id) {
      if (id) chosen[id] = 1;
    });
    var copy = optionTemplate.content.cloneNode(true);
    Array.prototype.forEach.call(copy.querySelectorAll('.ms-opt'), function (o) {
      o.dataset.selected = chosen[o.dataset.id] ? '1' : '0';
    });
    host.appendChild(copy);
  }
  document.querySelectorAll('.multiselect[data-chosen]').forEach(fill);

  function bind(ms, save) {
    if (typeof window.bindMultiSelect === 'function') return window.bindMultiSelect(ms, save);
    var opts = Array.prototype.slice.call(ms.querySelectorAll('.ms-opt'));
    var chosen = {};
    opts.forEach(function (o) { if (o.dataset.selected === '1') chosen[o.dataset.id] = 1; });
    opts.forEach(function (o) {
      o.style.fontWeight = o.dataset.selected === '1' ? '700' : '';
      o.addEventListener('click', function () {
        if (chosen[o.dataset.id]) { delete chosen[o.dataset.id]; o.dataset.selected = '0'; }
        else { chosen[o.dataset.id] = 1; o.dataset.selected = '1'; }
        o.style.fontWeight = o.dataset.selected === '1' ? '700' : '';
        save(Object.keys(chosen));
      });
    });
    return null;
  }

  document.querySelectorAll('.sidepanel .multiselect:not(.dlchannels)').forEach(function (ms) {
    bind(ms, function (ids) {
      post('param', {key: ms.dataset.key, value: ids}).then(function (res) {
        say(settingsMsg, res.ok ? (ms.dataset.key + ' saved')
                                : ('Could not save: ' + res.error), res.ok);
      });
    });
  });
  document.querySelectorAll('.dlchannels').forEach(function (ms) { bind(ms, function () {}); });

  var bmsg = document.getElementById('dlbuildingsmsg');

  function readBuilding(card) {
    var channels = {};
    var picker = card.querySelector('.dlchannels');
    if (picker) {
      picker.querySelectorAll('.ms-opt').forEach(function (o) {
        if (o.dataset.selected === '1') channels[o.dataset.id] = 1;
      });
    }
    card.querySelectorAll('.dlchw').forEach(function (input) {
      if (channels.hasOwnProperty(input.dataset.channel)) {
        channels[input.dataset.channel] = parseFloat(input.value || '1');
      }
    });
    var emphasis = {};
    card.querySelectorAll('.dlemph').forEach(function (input) {
      var v = parseFloat(input.value);
      if (!isNaN(v) && v !== 1) emphasis[input.dataset.metric] = v;
    });
    var tiers = [];
    card.querySelectorAll('.dltier').forEach(function (row) {
      var t = row.querySelector('.dltiertitle');
      if (!t || !t.value.trim()) return;
      var pct = row.querySelector('.dltierpct');
      var flr = row.querySelector('.dltierfloor');
      tiers.push({
        title: t.value,
        percentile: parseFloat(pct ? pct.value : '0') || 0,
        floor: parseInt(flr ? flr.value : '0', 10) || 0
      });
    });
    var name = card.querySelector('.dlbname');
    var icon = card.querySelector('.dlbicon');
    var hints = [];
    try { hints = JSON.parse(card.dataset.hints || '[]'); } catch (e) { hints = []; }
    return {
      key: card.dataset.key,
      name: name ? name.value : '',
      icon: icon ? icon.value : '',
      hints: hints,
      channels: channels, metric_weights: emphasis, tiers: tiers
    };
  }
  function collect() {
    return Array.prototype.map.call(
      document.querySelectorAll('#dlbuildinglist .dlbuilding'), readBuilding);
  }

  var save = document.getElementById('dlsavebuildings');
  if (save) save.addEventListener('click', function () {
    say(bmsg, 'Saving...', true);
    post('buildings', {buildings: collect()}).then(function (res) {
      if (res.ok) {
        say(bmsg, 'Saved. Reloading...', true);
        setTimeout(function () { location.reload(); }, 500);
      } else { say(bmsg, 'Refused: ' + res.error, false); }
    });
  });

  var suggest = document.getElementById('dlsuggest');
  if (suggest) suggest.addEventListener('click', function () {
    say(bmsg, 'Matching channel names...', true);
    post('suggest', {}).then(function (res) {
      if (res.ok) {
        say(bmsg, 'Matched ' + res.attached + ' rooms. Reloading...', true);
        setTimeout(function () { location.reload(); }, 700);
      } else { say(bmsg, 'Refused: ' + res.error, false); }
    });
  });

  document.querySelectorAll('.dlbdel').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var card = btn.closest('.dlbuilding');
      if (card && window.confirm('Remove this building? Nothing is saved until you press Save buildings.')) {
        card.remove();
      }
    });
  });
  function wireTierDelete(btn) {
    btn.addEventListener('click', function () {
      var row = btn.closest('.dltier');
      if (row) row.remove();
    });
  }
  document.querySelectorAll('.dltierdel').forEach(wireTierDelete);
  document.querySelectorAll('.dltieradd').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var row = document.createElement('div');
      row.className = 'dltier';
      row.innerHTML = '<input type="text" class="dltiertitle" placeholder="Tier name" maxlength="60">'
        + '<label class="dlfield"><span class="muted small">Percentile</span>'
        + '<input type="number" step="1" min="0" max="100" class="dltierpct" value="50"></label>'
        + '<label class="dlfield"><span class="muted small">Floor</span>'
        + '<input type="number" step="1" min="0" class="dltierfloor" value="0"></label>'
        + '<button class="dltierdel">&times;</button>';
      wireTierDelete(row.querySelector('.dltierdel'));
      btn.parentNode.insertBefore(row, btn);
    });
  });

  var addB = document.getElementById('dlbadd');
  if (addB) addB.addEventListener('click', function () {
    var name = window.prompt('What is this building called?');
    if (!name) return;
    say(bmsg, 'Adding...', true);
    post('buildings', {buildings: collect().concat([{
      name: name, icon: '', channels: {}, metric_weights: {}, hints: [],
      tiers: [{title: 'Foundations', percentile: 20, floor: 25}]
    }])}).then(function (res) {
      if (res.ok) { location.reload(); }
      else { say(bmsg, 'Refused: ' + res.error, false); }
    });
  });

  var mapMsg = document.getElementById('dlmapmsg');
  var armed = null;
  var canvas = document.getElementById('dlcanvas');
  if (canvas) {
    canvas.querySelectorAll('.dltown').forEach(function (town) {
      town.addEventListener('click', function (event) {
        event.stopPropagation();
        if (armed) armed.classList.remove('armed');
        armed = (armed === town) ? null : town;
        if (armed) {
          armed.classList.add('armed');
          say(mapMsg, 'Now click where this town should go.', true);
        }
      });
    });
    canvas.addEventListener('click', function (event) {
      if (!armed) { say(mapMsg, 'Click a town first, then click where it goes.', true); return; }
      var box = canvas.getBoundingClientRect();
      var moving = armed;
      post('settle', {user_id: moving.dataset.user,
                      x: ((event.clientX - box.left) / box.width) * 100,
                      y: ((event.clientY - box.top) / box.height) * 100}).then(function (res) {
        if (!res.ok) { say(mapMsg, 'Refused: ' + res.error, false); return; }
        moving.style.left = res.x + '%';
        moving.style.top = res.y + '%';
        moving.classList.remove('armed');
        armed = null;
        say(mapMsg, 'Moved.', true);
      });
    });
  }
  var file = document.getElementById('dlmapfile');
  if (file) file.addEventListener('change', function () {
    var chosen = file.files && file.files[0];
    if (!chosen) return;
    var reader = new FileReader();
    reader.onload = function () {
      say(mapMsg, 'Uploading...', true);
      post('map', {data: String(reader.result).split(',').pop(),
                   content_type: chosen.type}).then(function (res) {
        if (res.ok) {
          say(mapMsg, 'Map saved. Reloading...', true);
          setTimeout(function () { location.reload(); }, 500);
        } else { say(mapMsg, 'Refused: ' + res.error, false); }
      });
    };
    reader.readAsDataURL(chosen);
  });
  var clearMap = document.getElementById('dlmapclear');
  if (clearMap) clearMap.addEventListener('click', function () {
    if (!window.confirm('Remove the map? Towns keep their positions.')) return;
    post('map', {data: null}).then(function (res) {
      if (res.ok) { location.reload(); }
      else { say(mapMsg, 'Refused: ' + res.error, false); }
    });
  });

  function backfill(preview) {
    var out = document.getElementById('dlbackfillout');
    var msg = document.getElementById('dlbackfillmsg');
    if (!preview && !window.confirm('Rebuild history from the message archive? It cannot touch days the listener already recorded, and running it again writes the same numbers rather than doubling them.')) return;
    say(msg, preview ? 'Reading the archive...' : 'Rebuilding...', true);
    post('backfill', {preview: !!preview}).then(function (res) {
      out.hidden = false;
      out.textContent = JSON.stringify(res, null, 2);
      say(msg, res.ok ? (preview ? 'Preview only, nothing was written.'
                                 : 'Done. Reload to see the rebuilt towns.')
                      : ('Refused: ' + res.error), res.ok);
    });
  }
  var pv = document.getElementById('dlpreviewbackfill');
  if (pv) pv.addEventListener('click', function () { backfill(true); });
  var rn = document.getElementById('dlrunbackfill');
  if (rn) rn.addEventListener('click', function () { backfill(false); });
});
</script>
""".replace("__DL_GID__", str(guild_id))


async def dodoland_page(request: web.Request):
    from web.routes import _page

    bot, guild, scope = request.app["bot"], request["guild"], request["scope"]
    buildings = bot.dodoland_buildings.buildings(guild.id)
    window = int(bot.dodoland_params.get(guild.id, "dodoland_window_days"))
    since = store_module.days_back(window)

    # Every read here is blocking pymongo, and this handler runs on the bot's own
    # event loop. Doing it inline stops the bot responding while Mongo works.
    loop = asyncio.get_running_loop()
    lit_days = int(bot.dodoland_params.get(guild.id, "dodoland_lit_days"))
    lit_since = store_module.days_back(lit_days)

    # One read of each collection for the whole page. Previously every view
    # fetched its own copy: two previews, each also counting days, plus the map,
    # came to eight scans of a 32,000-row collection per page load. The rows are
    # split by basis in memory instead, which is the same answer far cheaper.
    def fetch():
        return (bot.dodoland.rows(guild.id, since=since),
                bot.dodoland.pair_rows(guild.id, since=since))

    all_rows, all_pairs = await loop.run_in_executor(None, fetch)

    def compute_for(basis):
        return standing.guild_standings(
            bot.dodoland, bot.dodoland_params, guild.id, buildings,
            since=since, basis=basis, rows=all_rows, pair_rows=all_pairs,
        )

    result = await loop.run_in_executor(None, compute_for, store_module.BASIS_ALL)
    scratch = await loop.run_in_executor(None, compute_for, store_module.BASIS_LIVE)
    flourish = await loop.run_in_executor(
        None, flourish_rules.flourish_map, bot, guild.id)

    def townwork():
        partners: dict = {}
        for row in all_pairs:
            a, b, n = int(row.get("a", 0)), int(row.get("b", 0)), int(row.get("n", 0))
            partners.setdefault(a, {})[b] = partners.setdefault(a, {}).get(b, 0) + n
            partners.setdefault(b, {})[a] = partners.setdefault(b, {}).get(a, 0) + n
        lit = {int(row.get("user_id", 0)) for row in all_rows
               if str(row.get("day") or "") >= lit_since}
        return mapview.towns(
            result["order"], partners=partners,
            settled=bot.dodoland_buildings.plots(guild.id), flourish=flourish,
            names={p["user_id"]: _name_of(guild, p["user_id"]) for p in result["order"]},
            lit=lit,
        )

    towns = await loop.run_in_executor(None, townwork)

    tracking = bot.visibility.feature_active(guild.id, "dodoland_tracking", "dodoland")
    counted = len(result["people"])
    status = ("counting now" if tracking else
              "switched off, so nothing is being recorded")

    nav = ""
    # Every panel in the body needs an entry here. A section with no menu item
    # renders hidden with nothing able to reveal it, which is exactly how the
    # rebuild button went missing: on the page, and unreachable.
    for key, emoji, label, hint in (
        ("dl-preview", "\U0001F441", "Preview: with history", f"{counted} scoring"),
        ("dl-scratch", "\U0001F195", "Preview: from scratch",
         f"{len(scratch['people'])} scoring"),
        ("dl-buildings", "\U0001F3D8", "Buildings", f"{len(buildings)}"),
        ("dl-metrics", "\U0001F4CF", "What counts", f"{len(metric_registry.METRICS)} metrics"),
        ("dl-map", "\U0001F5FA", "The map", "upload"),
        ("dl-backfill", "\U000023EA", "Rebuild history", "from the archive"),
        ("dl-settings", "\U00002699", "Settings", "intake"),
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
  <nav class="sidenav dlnav">{nav}</nav>
  <div class="content">
    {_preview_html(bot, guild, result, buildings, flourish,
                   basis=store_module.BASIS_ALL, panel='dl-preview', shown=True)}
    {_preview_html(bot, guild, scratch, buildings, flourish,
                   basis=store_module.BASIS_LIVE, panel='dl-scratch', shown=False)}
    {_buildings_html(bot, guild, result)}
    {_metrics_html(bot, guild)}
    {_map_html(bot, guild, towns)}
    {_backfill_html(bot, guild)}
    {_settings_html(bot, guild)}
  </div>
</div>
{buildings_ui.channel_options_template(guild)}
<p id="status" class="status"></p>
{_script(guild.id)}"""
    return _page(f"DodoLand · {guild.name}", body, scope=scope, guild=guild,
                 current="dodoland")
