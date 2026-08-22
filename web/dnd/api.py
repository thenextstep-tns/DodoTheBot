"""
JSON endpoints for the Tabletop panel.

Separate from the bot's general panel API for the reason the whole engine is
separate: tabletop settings must not travel through the same handlers as the
bot's ordinary cog settings, or the two grow entangled again through shared
validation and shared assumptions about which registry a key belongs to.

Two access layers, and both are enforced here rather than by hiding controls in
the HTML:

* :func:`require_scope` gates the **guild** — you must already be able to open
  this server's panel;
* the **campaign** scope in ``web/dnd/access.py`` then decides whether you may
  touch a particular campaign's knowledge.

MERGE NOTE: the coercion helpers (``parameters.coerce``, ``validate``) and the
audit trail (``_record_change``) are shared machinery, not surface, and are
deliberately reused. If tabletop is ever extracted, those three imports are the
seam.
"""

from __future__ import annotations

from aiohttp import web

from helpers import parameters as shared_parameters
from helpers import validate
from helpers.dnd import parameters as dnd_parameters
from helpers.dnd import registry as dnd_registry
from helpers.dnd import tuning as tuning_registry
from helpers.dnd.store import campaign_store, campaigns_for
from helpers.dnd.mind.traits import DRIVES, FACULTIES, TEMPERAMENT
from helpers.dnd.world.knowledge import KINDS, Fact
from web.dnd import access


def _bad(error, status: int = 200):
    """Mirror the general panel's error shape so one client script handles both."""
    return web.json_response({"ok": False, "error": str(error)}, status=status)


def _campaign_or_none(guild_id: int, raw_id: str):
    for candidate in campaigns_for(guild_id).list(include_archived=True):
        if str(candidate.id) == raw_id:
            return candidate
    return None


async def _gm_context(request: web.Request, data: dict):
    """Resolve (campaign, store) if this viewer may GM it, else an error response."""
    guild = request["guild"]
    campaign = _campaign_or_none(guild.id, str(data.get("campaign_id", "")))
    if campaign is None:
        return None, None, _bad("Campaign not found.")
    scope = access.campaign_scope(campaign, request["uid"], request["scope"])
    if scope != access.CAMPAIGN_GM:
        # 404-shaped rather than 403: the panel does not confirm the contents of
        # games the viewer has nothing to do with.
        return None, None, _bad("Campaign not found.")
    return campaign, campaign_store(guild.id, campaign.id), None


# --------------------------------------------------------------------------- #
#  Engine settings
# --------------------------------------------------------------------------- #
async def api_dnd_param(request: web.Request):
    """Set a tabletop parameter: body ``{key, value}``.

    Reads from tabletop's own registry, never the bot's — an unknown key is
    rejected rather than silently falling through to a general setting.
    """
    from web.routes import _record_change

    gid = int(request.match_info["gid"])
    data = await request.json()
    try:
        key = validate.text(data.get("key"), field="key", max_length=64, allow_empty=False)
    except validate.ValidationError as error:
        return _bad(error)

    spec = next((p for p in dnd_parameters.DND_PARAMETERS if p["key"] == key), None)
    if spec is None:
        return _bad("Unknown tabletop parameter.")

    value = data.get("value")
    if spec["type"] in ("str", "text", "secret"):
        try:
            value = validate.text(value, field=key, max_length=validate.MAX_TEXT)
        except validate.ValidationError as error:
            return _bad(error)

    was = dnd_parameters.params.get(gid, key)
    try:
        now = dnd_parameters.params.set(gid, key, value)
    except (KeyError, ValueError) as error:
        return _bad(error)

    await _record_change(
        request, "dnd_param", key, was, now, f"changed tabletop **{spec['label']}**"
    )
    return web.json_response({"ok": True, "value": now})


async def api_dnd_cog(request: web.Request):
    """Enable or disable a tabletop cog for this server: ``{cog, enabled}``.

    Tabletop cogs are absent from the general dashboard, so this is the only way
    to switch the engine off — and it must exist, or removing them from that page
    would have removed the switch with them.
    """
    from web.routes import _record_change

    bot = request.app["bot"]
    gid = int(request.match_info["gid"])
    data = await request.json()

    cog = str(data.get("cog", ""))
    if not dnd_registry.is_dnd_cog(cog):
        return _bad("Not a tabletop cog.")
    enabled = bool(data.get("enabled"))

    was = bot.visibility.cog_enabled(gid, cog)
    bot.visibility.set_cog_enabled(gid, cog, enabled)
    await _record_change(
        request, "dnd_cog", cog, was, enabled,
        f"{'enabled' if enabled else 'disabled'} tabletop **{cog}**",
    )
    # Flipping the switch has to reach Discord, or the engine is on and every
    # command is still missing. The general cog endpoint has always done this;
    # this one did not, so switching tabletop back on visibly changed nothing.
    bot.command_syncer.request_sync(gid)
    return web.json_response({"ok": True, "enabled": enabled})


# --------------------------------------------------------------------------- #
#  Campaign knowledge
# --------------------------------------------------------------------------- #
async def api_dnd_lore(request: web.Request):
    """Add or remove a campaign fact: ``{campaign_id, action, ...}``."""
    data = await request.json()
    campaign, store, error = await _gm_context(request, data)
    if error is not None:
        return error

    action = str(data.get("action", "add"))

    if action == "remove":
        removed = store.knowledge.remove(_fact_id(store, str(data.get("id", ""))))
        return web.json_response({"ok": bool(removed)})

    if action == "edit":
        fact_id = _fact_id(store, str(data.get("id", "")))
        patch = {}
        for field in ("title", "text"):
            if data.get(field) is not None:
                patch[field] = str(data[field])[:2000]
        if data.get("weight") is not None:
            patch["weight"] = max(0.0, min(1.0, float(data["weight"])))
        if data.get("secret") is not None:
            patch["secret"] = bool(data["secret"])
        return web.json_response({"ok": bool(store.knowledge.edit(fact_id, patch))})

    # add
    try:
        title = validate.text(data.get("title"), field="title", max_length=100, allow_empty=False)
        text = validate.text(data.get("text"), field="text", max_length=1500, allow_empty=False)
    except validate.ValidationError as err:
        return _bad(err)

    kind = str(data.get("kind", "lore"))
    if kind not in KINDS:
        return _bad("Unknown kind.")

    fact = store.knowledge.add(
        Fact(
            kind=kind,
            title=title,
            text=text,
            secret=bool(data.get("secret")),
            weight=max(0.0, min(1.0, float(data.get("weight", 0.5)))),
        )
    )
    return web.json_response({"ok": True, "id": str(fact.id), "tags": fact.tags})


def _fact_id(store, raw: str):
    """Map a string id back to the real one, within this campaign only."""
    for fact in store.knowledge.campaign_facts():
        if str(fact.id) == raw:
            return fact.id
    return None


async def api_dnd_canon(request: web.Request):
    """Accept or reject a proposed fact: ``{campaign_id, id, action}``."""
    data = await request.json()
    campaign, store, error = await _gm_context(request, data)
    if error is not None:
        return error

    raw = str(data.get("id", ""))
    target = next((p["_id"] for p in store.canon.pending(limit=200) if str(p["_id"]) == raw), None)
    if target is None:
        return _bad("Proposal not found.")

    if str(data.get("action")) == "accept":
        fact = store.canon.accept(target, store.knowledge, actor_id=request["uid"])
        return web.json_response({"ok": fact is not None})
    store.canon.reject(target, actor_id=request["uid"])
    return web.json_response({"ok": True})


async def api_dnd_tune(request: web.Request):
    """Set or clear one campaign-level tunable: ``{campaign_id, key, value}``.

    ``value: null`` clears the campaign's override so it goes back to inheriting
    the server's setting (or the built-in default). Out-of-range values are
    clamped rather than refused — dragging a slider past the end should give you
    the extreme, not an error.
    """
    data = await request.json()
    campaign, store, error = await _gm_context(request, data)
    if error is not None:
        return error

    key = str(data.get("key", ""))
    spec = tuning_registry.BY_KEY.get(key)
    if spec is None:
        return _bad("Unknown setting.")

    settings = dict(campaign.settings or {})
    overrides = dict(settings.get("tuning") or {})
    raw = data.get("value")
    if raw in (None, ""):
        overrides.pop(key, None)
    else:
        try:
            overrides[key] = tuning_registry.coerce(key, raw)
        except (TypeError, ValueError) as error:
            return _bad(error)
    settings["tuning"] = overrides
    store.campaigns.save_settings(campaign.id, settings)

    resolved = tuning_registry.Tuning.for_campaign(request["guild"].id, campaign)
    return web.json_response(
        {"ok": True, "value": resolved.get(key), "source": resolved.source_of(key)}
    )


async def api_dnd_tune_server(request: web.Request):
    """Set or clear one **server-level** tunable: ``{key, value}``.

    The layer beneath campaigns: a server admin sets the house style, and any
    campaign that has not formed its own opinion inherits it. ``value: null``
    clears the server override so the built-in default applies again.

    Separate handler from the campaign one because the two have different
    gatekeepers — this route is behind ``SCOPE_FULL`` (server admin), while the
    campaign route is behind a per-campaign GM check.
    """
    from web.routes import _record_change

    gid = int(request.match_info["gid"])
    data = await request.json()

    key = str(data.get("key", ""))
    spec = tuning_registry.BY_KEY.get(key)
    if spec is None:
        return _bad("Unknown setting.")

    before = tuning_registry.Tuning(server=dnd_parameters.tuning_overrides(gid))
    was = before.get(key)

    raw = data.get("value")
    if raw in (None, ""):
        dnd_parameters.set_tuning(gid, key, None)
    else:
        try:
            dnd_parameters.set_tuning(gid, key, tuning_registry.coerce(key, raw))
        except (TypeError, ValueError) as error:
            return _bad(error)

    after = tuning_registry.Tuning(server=dnd_parameters.tuning_overrides(gid))
    now = after.get(key)
    await _record_change(
        request, "dnd_tuning", key, was, now,
        f"changed the server's tabletop **{spec['label']}**",
    )
    return web.json_response(
        {"ok": True, "value": now, "source": after.source_of(key)}
    )


# --------------------------------------------------------------------------- #
#  Entity traits
# --------------------------------------------------------------------------- #
async def api_dnd_entity_traits(request: web.Request):
    """Set one trait axis on one NPC: ``{campaign_id, entity_id, axis, value}``.

    Generation can only ever hand a GM the middle of a distribution. The people
    worth building a story on are the exceptions — the moral thief, the warm
    killer, the honourable vampire — and those have to be *authored*, not waited
    for. So every axis is settable per entity, which is also the object level the
    "expose every knob" rule asks for.

    The value is clamped to the axis's own range rather than rejected, since a
    GM reaching for 2.0 means "as far as this goes".
    """
    from web.routes import _record_change

    data = await request.json()
    campaign, store, error = await _gm_context(request, data)
    if error is not None:
        return error

    axis = str(data.get("axis", ""))
    if axis not in TEMPERAMENT + DRIVES + FACULTIES:
        return _bad("Unknown trait axis.")

    raw_id = str(data.get("entity_id", ""))
    entity = next(
        (e for e in store.entities.list(include_retired=True, limit=500)
         if str(e.id) == raw_id),
        None,
    )
    if entity is None:
        return _bad("Entity not found.")

    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return _bad("Trait value must be a number.")
    low = -1.0 if axis in TEMPERAMENT else 0.0
    value = round(max(low, min(1.0, value)), 3)

    doc = dict(entity.traits or {})
    was = doc.get(axis)
    doc[axis] = value
    entity.traits = doc
    store.entities.save(entity)

    await _record_change(
        request, "dnd_trait", f"{entity.identity.name}.{axis}", was, value,
        f"set **{entity.identity.name}**'s {axis} to {value}",
    )
    return web.json_response({"ok": True, "axis": axis, "value": value})
