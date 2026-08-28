"""
The buildings editor: linking a building to the channels that build it.

Kept out of ``pages.py`` because it is the densest surface on the page and the
one most likely to keep changing.

**Every building is edited as a form, not as JSON.** The first version of this
page shipped a validated JSON textarea, which was technically complete and
practically useless: the whole design rests on saying "these rooms build this
building", and that has to be a channel picker, not a paragraph somebody types
ids into.

The channel picker is the panel's own `.multiselect` widget, which
``panel.js:bindMultiSelect`` makes interactive. That binding only runs for
controls inside a ``.cogcard``, which this page has none of, so the DodoLand
page binds its own — see ``pages._script``. Rendering the markup without binding
it is exactly how this shipped broken the first time.

Weights are shown per already-attached channel. Attach a room, save, and its
weight box appears; that is one extra round trip and it keeps the widget honest
rather than trying to invent a control that does membership and weighting at
once.
"""

from __future__ import annotations

import html
import json

from helpers.dodoland import metrics as metric_registry


def _e(value) -> str:
    return html.escape(str(value))


def _channel_name(guild, channel_id: int) -> str:
    channel = guild.get_channel(int(channel_id))
    return f"#{channel.name}" if channel else f"channel {channel_id}"


def ordered_channels(guild) -> list:
    """This guild's channels in the order Discord itself draws them.

    Categories in their own order, then channels within each category in theirs.
    With sixty-odd channels an alphabetical or arbitrary list is unusable: the
    only ordering anybody knows is the one in their sidebar, so that is the one
    to show.

    Threads are deliberately absent. A thread is a room inside a channel and is
    charged to its parent, so offering one here would promise an attachment the
    scorer would never honour.
    """
    import discord

    kinds = (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel)
    rooms = [c for c in getattr(guild, "channels", []) if isinstance(c, kinds)]

    def sort_key(channel):
        category = getattr(channel, "category", None)
        # Channels above every category sort first, the way Discord shows them.
        return (getattr(category, "position", -1) if category is not None else -1,
                getattr(category, "id", 0) or 0,
                getattr(channel, "position", 0),
                getattr(channel, "id", 0))

    return sorted(rooms, key=sort_key)


def channel_label(channel) -> str:
    """``Category / name`` — so searching a category finds all of its rooms."""
    category = getattr(channel, "category", None)
    name = getattr(channel, "name", "?")
    return f"{category.name} / {name}" if category is not None else name


def channel_options_template(guild) -> str:
    """Every channel, once, as a template the pickers are filled from.

    There are around thirty pickers on this page (one per metric, one per
    building) and sixty-odd channels, so writing the options into each of them
    put roughly two thousand elements in the HTML. They are identical apart from
    which are ticked, so they are sent once and cloned in the browser.
    """
    options = "".join(
        f'<div class="ms-opt" data-id="{channel.id}" '
        f'data-name="{_e(channel_label(channel))}" '
        f'data-selected="0">{_e(channel_label(channel))}</div>'
        for channel in ordered_channels(guild)
    )
    return f'<template id="dlchanoptions">{options}</template>'


def channel_multiselect(guild, *, key: str, selected, extra_class: str = "") -> str:
    """The panel's chip multi-select, ordered and labelled the way Discord is.

    Emits no options of its own: ``data-chosen`` says which channels are ticked
    and the script fills the rest from the shared template before binding.
    """
    chosen = ",".join(str(int(c)) for c in sorted(int(x) for x in (selected or [])))
    classes = ("multiselect " + extra_class).strip()
    return (
        f'<div class="{classes}" data-key="{_e(key)}" data-chosen="{chosen}">'
        f'<div class="ms-chips"></div>'
        f'<input class="ms-search" placeholder="Search channels or categories…" '
        f'autocomplete="off">'
        f'<div class="ms-options"></div></div>'
    )


def _channel_picker(guild, building: dict) -> str:
    return channel_multiselect(guild, key=building["key"],
                               selected=(building.get("channels") or {}),
                               extra_class="dlchannels")


def _weight_rows(guild, building: dict) -> str:
    channels = building.get("channels") or {}
    if not channels:
        return ('<div class="muted small">No rooms attached yet, so nothing builds '
                'this. Pick channels above and save.</div>')
    rows = ""
    for channel_id, weight in sorted(channels.items()):
        rows += f"""
    <label class="dlfield"><span class="muted small">{_e(_channel_name(guild, channel_id))}</span>
      <input type="number" step="0.1" min="0" max="10" class="dlchw"
             data-channel="{int(channel_id)}" value="{float(weight):g}"></label>"""
    return f'<div class="dlfields">{rows}</div>'


def _emphasis_rows(building: dict) -> str:
    """A multiplier per metric, for this building only."""
    current = building.get("metric_weights") or {}
    rows = ""
    for metric in metric_registry.METRICS:
        value = float(current.get(metric.key, 1.0))
        rows += f"""
    <label class="dlfield"><span class="muted small">{_e(metric.label)}</span>
      <input type="number" step="0.5" min="0" max="10" class="dlemph"
             data-metric="{_e(metric.key)}" value="{value:g}"></label>"""
    return f'<div class="dlfields">{rows}</div>'


def _tier_rows(building: dict, resolved: list[dict]) -> str:
    rows = ""
    for index, tier in enumerate(building.get("tiers") or []):
        live = resolved[index] if index < len(resolved) else {}
        costs = (f"costs <b>{live.get('threshold', 0):,}</b> now, set by "
                 f"{'its floor' if live.get('source') == 'floor' else 'the percentile'}"
                 if live else "")
        rows += f"""
  <div class="dltier">
    <input type="text" class="dltiertitle" value="{_e(tier.get('title'))}"
           placeholder="Tier name" maxlength="60">
    <label class="dlfield"><span class="muted small">Percentile</span>
      <input type="number" step="1" min="0" max="100" class="dltierpct"
             value="{float(tier.get('percentile', 0)):g}"></label>
    <label class="dlfield"><span class="muted small">Floor</span>
      <input type="number" step="1" min="0" class="dltierfloor"
             value="{int(tier.get('floor', 0))}"></label>
    <span class="muted small dltiernow">{costs}</span>
    <button class="dltierdel" title="Remove this tier">&times;</button>
  </div>"""
    return rows


def building_card(guild, building: dict, resolved: list[dict], population: int) -> str:
    """One building, fully editable."""
    return f"""
<div class="rulecard dlbuilding" data-key="{_e(building['key'])}"
     data-hints="{_e(json.dumps(building.get('hints') or []))}">
  <div class="dlbhead">
    <input type="text" class="dlbicon" value="{_e(building.get('icon') or '')}"
           maxlength="8" title="Icon" aria-label="Icon">
    <input type="text" class="dlbname" value="{_e(building['name'])}"
           maxlength="60" aria-label="Building name">
    <code>{_e(building['key'])}</code>
    <button class="dlbdel" title="Remove this building">Remove</button>
  </div>

  <div class="paramrow wide">
    <div><b>Rooms that build it</b>
      <div class="muted small">Everything earned in these channels builds this
      one. A room may feed more than one building, at different weights: a busy
      general channel really is both the tavern and somewhere else.</div></div>
    {_channel_picker(guild, building)}
  </div>

  <div class="paramrow wide">
    <div><b>What each room is worth</b>
      <div class="muted small">A multiplier on everything earned there. 0 stops
      the room counting without detaching it.</div></div>
    {_weight_rows(guild, building)}
  </div>

  <details class="dlmore">
    <summary class="muted small">This building's own emphasis</summary>
    <div class="muted small">Multiplies one metric here only, leaving what that
    act is worth everywhere else alone.</div>
    {_emphasis_rows(building)}
  </details>

  <div class="dltiers">
    <div class="muted small feathead">Tiers &middot; {population} people currently score here</div>
    {_tier_rows(building, resolved)}
    <button class="dltieradd">Add a tier</button>
  </div>
</div>"""


def buildings_section(bot, guild, result: dict) -> str:
    buildings = bot.dodoland_buildings.buildings(guild.id)
    configured = bot.dodoland_buildings.is_configured(guild.id)
    cards = ""
    for building in buildings:
        key = building["key"]
        population = sum(
            1 for person in result["people"].values()
            if person["buildings"].get(key, {}).get("points", 0) > 0
        )
        cards += building_card(guild, building, result["tiers"].get(key, []), population)

    warning = "" if configured else """
  <div class="tuneblocked">These are the starting buildings and none of them has
  any rooms attached, so nothing is being built yet. Press <b>Suggest from
  channel names</b> to match them against this server's channels, correct
  whatever it got wrong, then save.</div>"""

    return f"""
<section class="sidepanel" data-panel="dl-buildings" hidden>
  <h2 class="panelhead">\U0001F3D8 Buildings</h2>
  <p class="muted">A building is a place, so it scores from <b>channels</b>.
  Every building is reachable by anyone through ordinary sociable activity;
  trial rank adds flourish on top and never the tier itself.</p>
  {warning}
  <div class="rulebtns dlbtnbar">
    <button id="dlsuggest">Suggest from channel names</button>
    <button id="dlbadd">Add a building</button>
    <button id="dlsavebuildings">Save buildings</button>
    <span id="dlbuildingsmsg" class="muted small"></span>
  </div>
  <div id="dlbuildinglist">{cards}</div>
</section>"""
