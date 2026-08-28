"""
Per-guild tunables for DodoLand — **separate from ``helpers/parameters.py``.**

Same idea and the same typed-spec shape as the bot's parameter registry, but its
own list and its own collection, so town settings never appear among the general
cog settings. The DodoLand panel page renders these itself, the way tabletop
does (see ``helpers/dnd/parameters.py``, which this follows deliberately).

**The per-metric knobs are generated, not written.** Every entry in
:data:`helpers.dodoland.metrics.METRICS` produces a weight, a daily cap and (for
social acts) a per-partner cap. Nobody has to remember to expose a new metric's
numbers, because there is nowhere to forget: adding the metric adds the
parameters. That is the standing "everything is tweakable" rule made structural
instead of aspirational.

``ParamManager`` and ``coerce`` are reused from ``helpers/parameters.py`` rather
than reimplemented — that is machinery, not surface, and forking it would mean
fixing every coercion bug twice. What is separate is the spec list and the
collection.
"""

from __future__ import annotations

from config.database import db
from helpers.dodoland import metrics as metric_registry
from helpers.parameters import ParamManager

# DodoLand's own store, so a general settings reset never rewrites a server's
# town economy and vice versa.
dodoland_params_col = db["DodoLandParams"]

# Prefixes for the generated per-metric knobs. Kept as constants because the
# store and the panel both have to rebuild these keys.
WEIGHT_PREFIX = "dodoland_w_"
DAILY_CAP_PREFIX = "dodoland_cap_"
PARTNER_CAP_PREFIX = "dodoland_pcap_"
CHANNELS_PREFIX = "dodoland_ch_"


def weight_key(metric_key: str) -> str:
    return f"{WEIGHT_PREFIX}{metric_key}"


def daily_cap_key(metric_key: str) -> str:
    return f"{DAILY_CAP_PREFIX}{metric_key}"


def partner_cap_key(metric_key: str) -> str:
    return f"{PARTNER_CAP_PREFIX}{metric_key}"


def channels_key(metric_key: str) -> str:
    return f"{CHANNELS_PREFIX}{metric_key}"


def metric_setup(params, guild_id: int, metric_key: str) -> dict:
    """Every knob for one metric, resolved. What the panel renders a block from.

    One function so the panel, the scorer and any future surface can never
    disagree about what a metric's configuration is.
    """
    from helpers.dodoland import metrics as metric_registry

    metric = metric_registry.get(metric_key)
    setup = {
        "key": metric.key,
        "label": metric.label,
        "description": metric.description,
        "kind": metric.kind,
        "backfill": metric.backfill,
        "weight": int(params.get(guild_id, weight_key(metric.key))),
        "daily_cap": int(params.get(guild_id, daily_cap_key(metric.key))),
        "channels": list(params.get(guild_id, channels_key(metric.key)) or []),
    }
    setup["partner_cap"] = (
        int(params.get(guild_id, partner_cap_key(metric.key))) if metric.is_social else None
    )
    return setup


# --------------------------------------------------------------------------- #
#  Hand-written parameters: what is tracked, and over what window
# --------------------------------------------------------------------------- #
_BASE_PARAMETERS: list[dict] = [
    {"key": "dodoland_tracked_channels", "cog": "dodoland", "type": "list_channel", "default": [],
     "label": "Tracked channels",
     "description": "Channels DodoLand counts activity in. Leave empty to count every channel the bot can see, minus the ignored list."},
    {"key": "dodoland_ignored_channels", "cog": "dodoland", "type": "list_channel", "default": [],
     "label": "Ignored channels",
     "description": "Never counted, even when the tracked list is empty. Bot-spam and command channels belong here, or the town gets built out of /pumpkin presses."},
    {"key": "dodoland_min_message_chars", "cog": "dodoland", "type": "int", "default": 4,
     "label": "Minimum message length",
     "description": "Shorter messages are not counted at all. Stops 'k', '+' and 'f' from being currency."},
    {"key": "dodoland_max_mentions", "cog": "dodoland", "type": "int", "default": 5,
     "label": "Mentions counted per message",
     "description": "Distinct people one message can credit. A cost ceiling, not a game rule: each named person costs two writes, so a message listing thirty people should not spend thirty times a normal message's budget."},
    {"key": "dodoland_public_base_url", "cog": "dodoland", "type": "str", "default": "",
     "label": "Public address",
     "description": "Where this panel is reachable from outside, e.g. https://dodobot.nextstep.team. Used to build the private link /town settle hands a player. Blank makes that link relative, which will not work in Discord."},
    {"key": "dodoland_map_min_zoom", "cog": "dodoland", "type": "float", "default": 0.4,
     "label": "Minimum zoom",
     "description": "How far out the map can be pulled. Below 1 the whole world fits in the frame with room around it."},
    {"key": "dodoland_map_max_zoom", "cog": "dodoland", "type": "float", "default": 8.0,
     "label": "Maximum zoom",
     "description": "How far in the map can be pushed. High values are only useful on a large, detailed base image."},
    {"key": "dodoland_map_name_zoom", "cog": "dodoland", "type": "float", "default": 1.8,
     "label": "Zoom names appear at",
     "description": "Town names stay hidden until the map is zoomed at least this far. Three hundred labels drawn at once is a grey mat rather than a map, so they arrive as you look closer."},
    {"key": "dodoland_town_width_pct", "cog": "dodoland", "type": "float", "default": 3.0,
     "label": "Town width (% of the map)",
     "description": "How wide a town is drawn, as a percentage of the map's width. A proportion rather than a pixel count, for the same reason positions are: re-uploading the map at another resolution then changes neither where a town sits nor how big it looks. An absolute size meant the same setting made towns a twentieth of a large map and a third of a small one."},
    {"key": "dodoland_detail_above", "cog": "dodoland", "type": "int", "default": 150,
     "label": "Show close-up detail above (px)",
     "description": "When a town is drawn wider than this many screen pixels, its high-tier flourishes appear: smoke from chimneys, lit windows, waving banners, a lantern's halo. At map scale those would be noise on three hundred towns at once; up close they are the reward for having built the thing."},
    {"key": "dodoland_town_dot_below", "cog": "dodoland", "type": "int", "default": 26,
     "label": "Collapse to a dot below (px)",
     "description": "When a town would be drawn narrower than this many screen pixels, it is replaced by a dot. Buildings at that size are illegible smudges, and every real map does the same thing as you zoom out."},
    {"key": "dodoland_big_town", "cog": "dodoland", "type": "float", "default": 2.2,
     "label": "Always-labelled size",
     "description": "Towns at least this many times the base size keep their name at every zoom level, so the map has landmarks to orient on."},
    {"key": "dodoland_asset_size", "cog": "dodoland", "type": "int", "default": 28,
     "label": "Decor size (px)",
     "description": "How large a placed decoration is drawn at 100% zoom."},
    {"key": "dodoland_newcomer_days", "cog": "dodoland", "type": "int", "default": 3,
     "label": "Newcomer window (days)",
     "description": "How long after joining somebody still counts as new, so talking to them scores as welcoming. Short on purpose: it is a welcome, not a friendship."},
    {"key": "dodoland_voice_min_minutes", "cog": "dodoland", "type": "int", "default": 5,
     "label": "Minimum shared voice (min)",
     "description": "How long two people must be in a voice channel together before it counts as sharing one. Stops walking through a channel from making you everybody's friend."},
    {"key": "dodoland_count_bots", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Count bots",
     "description": "Whether bot accounts earn and grant standing. Off, in every sane configuration."},
    {"key": "dodoland_count_self_acts", "cog": "dodoland", "type": "bool", "default": False,
     "label": "Count acts on yourself",
     "description": "Whether reacting to or replying to your own message scores. Off: it is the cheapest farm there is."},
    {"key": "dodoland_window_days", "cog": "dodoland", "type": "int", "default": 365,
     "label": "Standing window (days)",
     "description": "How far back standing is totalled. This is a window, not a decay: days outside it are still stored and still count toward all-time records."},
    {"key": "dodoland_lit_days", "cog": "dodoland", "type": "int", "default": 30,
     "label": "Lit window (days)",
     "description": "A town with activity inside this window is drawn lit, otherwise dim. This is the only thing dormancy ever costs anyone: brightness, never progress."},
    {"key": "dodoland_keep_days", "cog": "dodoland", "type": "int", "default": 1095,
     "label": "Keep daily rows (days)",
     "description": "How long the per-day rows are retained. Three years by default. Lowering this permanently discards history."},
    {"key": "dodoland_partner_weight", "cog": "dodoland", "type": "int",
     "default": metric_registry.PARTNER_WEIGHT,
     "label": f"Points: {metric_registry.PARTNER_LABEL}",
     "description": metric_registry.PARTNER_DESCRIPTION},
    {"key": "dodoland_partner_daily_cap", "cog": "dodoland", "type": "int",
     "default": metric_registry.PARTNER_DAILY_CAP,
     "label": "Daily cap: new people reached",
     "description": "How many different people can score in one day. A ceiling on a genuinely good day, not a limit on how many people you may talk to."},
]


# --------------------------------------------------------------------------- #
#  Generated parameters: three per metric
# --------------------------------------------------------------------------- #
def _metric_parameters() -> list[dict]:
    """A weight, a daily cap and (for social acts) a partner cap per metric."""
    out: list[dict] = []
    for metric in metric_registry.METRICS:
        out.append({
            "key": weight_key(metric.key), "cog": "dodoland", "type": "int",
            "default": metric.weight,
            "label": f"Points: {metric.label}",
            "description": f"{metric.description} Set to 0 to stop this counting toward standing without losing the record of it.",
        })
        out.append({
            "key": daily_cap_key(metric.key), "cog": "dodoland", "type": "int",
            "default": metric.daily_cap,
            "label": f"Daily cap: {metric.label}",
            "description": "How many of these can score for one person in a day. 0 removes the cap entirely.",
        })
        out.append({
            "key": channels_key(metric.key), "cog": "dodoland", "type": "list_channel",
            "default": [],
            "label": f"Channels: {metric.label}",
            "description": (
                "Channels this metric counts in. Empty means wherever DodoLand tracks at all, "
                "which is the setting most metrics want; narrow it when a metric only makes "
                "sense somewhere specific, such as pictures in the fashion and housing rooms."
            ),
        })
        if metric.is_social:
            out.append({
                "key": partner_cap_key(metric.key), "cog": "dodoland", "type": "int",
                "default": metric.partner_cap,
                "label": f"Per-person cap: {metric.label}",
                "description": (
                    "How many of these can score from one other person in a day. This is the "
                    "anti-farm number: past it the act still happens and simply stops scoring, "
                    "so two friends cannot build each other a city. 0 removes the cap."
                ),
            })
    return out


DODOLAND_PARAMETERS: list[dict] = _BASE_PARAMETERS + _metric_parameters()


def manager() -> ParamManager:
    """A ``ParamManager`` over DodoLand's own specs and collection."""
    return ParamManager(dodoland_params_col, DODOLAND_PARAMETERS)
