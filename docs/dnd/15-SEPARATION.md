# Separation from the rest of the bot

Dodo Tabletop is kept **completely separate** from DodoTheBot's ordinary
features. This file is the map: what is separate, what is deliberately shared,
and what a future merge (or extraction) would have to touch.

The one place that decides what "belongs to tabletop" is
[`helpers/dnd/registry.py`](../../helpers/dnd/registry.py). Shared code asks it
rather than hardcoding names, so adding a tabletop cog is one edit.

---

## 1. What is separate

| Surface | Tabletop's own | The bot's |
| --- | --- | --- |
| Strings | `lang_dnd.py` | `lang.py` |
| Parameters | `helpers/dnd/parameters.py` → `DndParams` collection | `helpers/parameters.py` → `CommandParams` |
| Storage | the eleven `dnd_*` collections | everything else |
| Dashboard | its own 🎲 Tabletop page, with an **Engine** section | the cog category page |
| Cog taxonomy | absent by design | `helpers/cog_categories.py` |
| Panel access | campaign scope in `web/dnd/access.py` | `helpers/panel_access.py` |
| Panel routes | `web/dnd/` | `web/routes.py` |
| Panel JS | inline, in `pages._dnd_script` | `web/static/panel.js` |
| Embeds | `cogs/dnd/embeds.py`, `cogs/dnd/knowledge.py` | per-cog |
| Tests | `tests/test_dnd_*.py` | — |

**The dashboard rule.** Tabletop cogs are filtered out of the general cog
inventory *and* the category taxonomy. That means the only way to switch the
engine off is the **Engine** section on the Tabletop page — removing them from
the dashboard without providing that would have removed the switch with them.

## 2. What is deliberately shared

Three systems are **enforcement**, not presentation. Forking them would let an
admin disable a cog and have it stay on, which is a lie the panel must never
tell. They stay shared, and each is one import:

| Shared | Why | Where tabletop touches it |
| --- | --- | --- |
| `bot.visibility` | Decides who may run a command and whether a cog is on for a guild. A parallel copy could disagree with the real one. | `web/dnd/api.py:api_dnd_cog`, `cogs/dnd/context.py` |
| `bot.panel_access` | Decides who may open a guild's panel at all. Campaign scope layers *on top*, it does not replace it. | `web/dnd/access.py` |
| `bot.state` | Resumable flows, once scenes go live (P3). | not yet used |

Plus three pieces of pure machinery, reused rather than reimplemented because a
second copy is a second place for the same bug:

- `helpers/parameters.ParamManager` — typed coercion and the per-guild cache.
  `DndParamManager` subclasses it with its own spec list and collection.
- `helpers/validate` — input validation in the panel API.
- `web/routes._page`, `require_scope`, `_record_change` — page chrome, the guild
  gate, and the config-audit trail.

## 3. Merge notes — where to look

Every seam carries a `MERGE NOTE` comment in the code. The complete list:

| File | Note |
| --- | --- |
| `lang_dnd.py` | Not panel-editable. To merge: build a second `LangManager(lang_dnd, dnd_lang_overrides)`, hang it on the bot, and teach `/lang` to render more than one module. |
| `helpers/dnd/parameters.py` | To merge: append `DND_PARAMETERS` to `PARAMETERS` and point at `command_params`. Deliberately not done — the point is that tabletop has no presence in the general settings UI. |
| `helpers/dnd/registry.py` | Names the three shared enforcement systems as the seams to cut for a full extraction. |
| `helpers/cog_categories.py` | Drop the `strip_dnd` call and add a category to fold tabletop back into the dashboard. |
| `web/routes.py:_cog_inventory` | Drop the two `dnd_registry` checks. |
| `web/dnd/api.py` | Names `parameters.coerce`, `validate` and `_record_change` as the shared machinery it reuses. |
| `web/dnd/pages.py:_dnd_script` | Why tabletop ships its own inline JS instead of extending `panel.js`. |
| `helpers/dnd/world/belief.py` | If `chat.py`'s `rumours_heard` is ever unified with beliefs, *this* is the shape to keep — it has confidence, truth and mutation count. |
| `helpers/dnd/store/knowledge.py` | Where a local embedding model would slot in, if tag scoring proves too blunt. |

## 4. Things that would re-entangle it

Watch for these in review:

- Adding a `dnd_*` key to `helpers/parameters.PARAMETERS`.
- Adding a `TT_*` or `DND_*` string to `lang.py`.
- Listing a tabletop cog in `helpers/cog_categories.CATEGORIES`.
- Posting tabletop settings to `/api/guild/{gid}/param` instead of
  `/api/guild/{gid}/dnd/param`.
- Importing a `dnd_*` collection handle outside `helpers/dnd/store/`.
- Hanging a tabletop manager on the bot object next to `bot.params` — two
  similarly-named attributes is exactly the confusion this avoids.

## 5. If tabletop is ever extracted

It would need: the `helpers/dnd/` package, `cogs/dnd/`, `web/dnd/`,
`lang_dnd.py`, the `dnd_*` collections, and reimplementations of the three shared
enforcement systems in §2. Nothing else in the bot imports tabletop except the
four integration points listed in §3 — and each of those is a deletion, not a
rewrite.
