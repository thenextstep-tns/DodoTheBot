"""
Rebuilding the past out of the message archive.

``Messages with Channels`` holds every message this bot has ever seen: the raw
text, the author, the channel, and (on newer rows) the guild. Three of
DodoLand's metrics are reconstructable from exactly that, so the map can open
with towns that already have history and a relation graph that already knows who
talks to whom, instead of a continent of empty plots nobody opens twice.

Three properties this has to have, and the design follows from them.

**It must value a rebuilt day exactly as the live listener would.** Both paths go
through :func:`helpers.dodoland.intake.acts_from_message`, and both cap through
:func:`helpers.dodoland.store.allowance`. There is no second set of rules here,
only a second place the same rules are driven from.

**It must be repeatable.** Aggregating in memory and writing whole days with
``$set`` means running it twice produces the same numbers rather than double
them. Doing it with ``$inc``, one act at a time, would be both 600,000 round
trips and a landmine.

**It must never touch a day the listener owns.** It stops strictly before the
earliest day with a live row. A rebuilt day overwriting a real one would be
silent and unrecoverable.

Two quirks of the archive shape the reader, both inherited from
``helpers/stats.py``:

* **No timestamp field.** Nothing was stored with one, so the day comes from the
  ObjectId in ``_id``, which embeds its creation time.
* **No guild field on older rows.** A guild's history is therefore "activity in
  this guild's channels", which is why the caller passes the channel ids.
"""

from __future__ import annotations

import datetime
from typing import Iterable, Optional

from helpers.dodoland import intake
from helpers.dodoland import metrics as metric_registry
from helpers.dodoland import parameters as dodo_params
from helpers.dodoland.store import allowance

# Only these three exist in the archive. Everything else (images, reply targets,
# thread parents, voice, RSVPs, invites) was never stored and can only be
# counted forward.
REBUILDABLE = ("message", "mention_given", "mention_received")


class Plan:
    """One guild's rebuilt history, aggregated in memory before anything is written."""

    def __init__(self) -> None:
        # (user, day) -> {"acts": {...}, "scored": {...}, "channels": {chan: {...}}}
        self.activity: dict[tuple[int, str], dict] = {}
        # (day, a, b) -> {"acts": {...}, "n": int}
        self.pairs: dict[tuple[str, int, int], dict] = {}
        self.messages = 0
        self.skipped = 0
        self.first_day: Optional[str] = None
        self.last_day: Optional[str] = None

    # -- accumulation ---------------------------------------------------- #
    def _bucket(self, user_id: int, day: str) -> dict:
        return self.activity.setdefault(
            (user_id, day), {"acts": {}, "scored": {}, "channels": {}}
        )

    def _pair(self, day: str, one: int, two: int) -> dict:
        low, high = sorted((int(one), int(two)))
        return self.pairs.setdefault((day, low, high), {"acts": {}, "n": 0})

    def add(self, act, day: str, *, daily_caps: dict, partner_caps: dict) -> None:
        """Fold one act in, applying the same caps the live path applies."""
        bucket = self._bucket(int(act.user_id), day)
        bucket["acts"][act.metric] = bucket["acts"].get(act.metric, 0) + 1

        within_partner = True
        if act.partner_id is not None:
            pair = self._pair(day, act.user_id, act.partner_id)
            done = pair["acts"].get(act.metric, 0)
            pair["acts"][act.metric] = done + 1
            pair["n"] += 1
            cap = int(partner_caps.get(act.metric, 0))
            within_partner = cap <= 0 or (done + 1) <= cap

        if not within_partner:
            return
        done_before = bucket["scored"].get(act.metric, 0)
        if allowance(done_before, 1, int(daily_caps.get(act.metric, 0))) <= 0:
            return
        bucket["scored"][act.metric] = done_before + 1
        if act.channel_id:
            channel = bucket["channels"].setdefault(str(int(act.channel_id)), {})
            channel[act.metric] = channel.get(act.metric, 0) + 1

    # -- output ---------------------------------------------------------- #
    def activity_rows(self) -> list[dict]:
        return [{"user_id": user_id, "day": day, **values}
                for (user_id, day), values in self.activity.items()]

    def pair_rows(self) -> list[dict]:
        return [{"day": day, "a": a, "b": b, **values}
                for (day, a, b), values in self.pairs.items()]

    def summary(self) -> dict:
        return {
            "messages": self.messages,
            "skipped": self.skipped,
            "people": len({user_id for user_id, _day in self.activity}),
            "days": len({day for _user, day in self.activity}),
            "activity_rows": len(self.activity),
            "pair_rows": len(self.pairs),
            "first_day": self.first_day,
            "last_day": self.last_day,
        }


def _day_of(document) -> Optional[str]:
    """The archive has no timestamp, so the day comes out of the ObjectId."""
    identifier = document.get("_id")
    generated = getattr(identifier, "generation_time", None)
    if generated is None:
        return None
    return generated.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d")


def build_plan(documents: Iterable[dict], *, params, guild_id: int,
               channel_ids: Iterable[int], before: Optional[str] = None) -> Plan:
    """Aggregate an archive cursor into a writable plan.

    ``before`` is the exclusive upper bound: nothing on or after it is rebuilt,
    because that is where the live listener's own rows begin.
    """
    plan = Plan()
    known = {int(c) for c in channel_ids}

    tracked = params.get(guild_id, "dodoland_tracked_channels")
    ignored = params.get(guild_id, "dodoland_ignored_channels")
    min_chars = int(params.get(guild_id, "dodoland_min_message_chars"))
    max_mentions = int(params.get(guild_id, "dodoland_max_mentions"))
    count_self = bool(params.get(guild_id, "dodoland_count_self_acts"))
    count_bots = bool(params.get(guild_id, "dodoland_count_bots"))

    daily_caps = {m.key: int(params.get(guild_id, dodo_params.daily_cap_key(m.key)))
                  for m in metric_registry.METRICS}
    partner_caps = {m.key: int(params.get(guild_id, dodo_params.partner_cap_key(m.key)))
                    for m in metric_registry.METRICS if m.is_social}
    # A metric's own channel list applies here exactly as it does live.
    metric_channels = {m.key: {int(c) for c in
                               (params.get(guild_id, dodo_params.channels_key(m.key)) or [])}
                       for m in metric_registry.METRICS}

    for document in documents:
        author = document.get("author")
        channel = document.get("channel")
        if not author or not channel:
            plan.skipped += 1
            continue
        channel_id = int(channel)
        if channel_id not in known:
            plan.skipped += 1
            continue  # not this guild's room
        if document.get("bot") and not count_bots:
            plan.skipped += 1
            continue
        if not intake.counts_channel(channel_id, tracked=tracked, ignored=ignored):
            plan.skipped += 1
            continue
        day = _day_of(document)
        if day is None or (before and day >= before):
            plan.skipped += 1
            continue

        acts = [act for act in intake.acts_from_message(
            int(author), document.get("message") or "", channel_id=channel_id,
            min_chars=min_chars, max_mentions=max_mentions, count_self=count_self,
        ) if act.metric in REBUILDABLE]
        if not acts:
            plan.skipped += 1
            continue

        plan.messages += 1
        plan.first_day = day if plan.first_day is None else min(plan.first_day, day)
        plan.last_day = day if plan.last_day is None else max(plan.last_day, day)
        for act in acts:
            only = metric_channels.get(act.metric) or set()
            if only and int(act.channel_id or 0) not in only:
                continue
            plan.add(act, day, daily_caps=daily_caps, partner_caps=partner_caps)
    return plan


def run(bot, guild, *, archive, dry_run: bool = False) -> dict:
    """Rebuild this guild's archivable history. Returns what it did.

    ``dry_run`` aggregates and reports without writing, which is how anybody
    should look at this before letting it near real rows.
    """
    store = bot.dodoland
    params = bot.dodoland_params
    channel_ids = [c.id for c in guild.channels]

    # Stop strictly before the listener's own earliest day.
    live_from = store.first_day(guild.id)
    boundary = live_from or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    cursor = archive.find(
        {"channel": {"$in": channel_ids}},
        {"_id": 1, "author": 1, "channel": 1, "message": 1, "bot": 1},
    )
    plan = build_plan(cursor, params=params, guild_id=guild.id,
                      channel_ids=channel_ids, before=boundary)

    result = {**plan.summary(), "boundary": boundary, "dry_run": bool(dry_run),
              "written": 0}
    if not dry_run:
        result["written"] = store.replace_days(
            guild.id, plan.activity_rows(), plan.pair_rows()
        )
    return result
