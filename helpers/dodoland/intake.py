"""
What a message is worth. The one place that decides.

The live listener and the archive backfill both call :func:`acts_from_message`,
and neither contains a rule of its own. That is the whole point of this module:
a message posted today and the same message read back out of ``Messages with
Channels`` in a year must produce identical acts, or the backfilled history and
the live history are two different economies wearing one name.

It is also why mentions are parsed out of the **raw text** rather than taken
from ``discord.Message.mentions``. The archive only ever stored the text, so
text is the common denominator; using the resolved list live and a regex in the
backfill would be exactly the silent divergence this module exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from helpers.dodoland import metrics as metric_registry

# ``<@123>`` and the older ``<@!123>``. Deliberately does not match ``<@&123>``
# (a role) or ``@everyone``: naming a role is not reaching a person, and if it
# scored, one ping of @Members would be worth more than a year of conversation.
MENTION_RE = re.compile(r"<@!?(\d+)>")


@dataclass(frozen=True)
class Act:
    """One thing to record: a metric, whose it is, and who else was involved."""

    metric: str
    user_id: int
    partner_id: Optional[int] = None
    channel_id: int = 0


def mentioned_ids(content: str) -> list[int]:
    """Distinct user ids named in the text, in the order they first appear."""
    seen: list[int] = []
    for raw in MENTION_RE.findall(content or ""):
        value = int(raw)
        if value not in seen:
            seen.append(value)
    return seen


def counts_channel(channel_id: int, *, tracked: list[int], ignored: list[int]) -> bool:
    """Whether activity in a channel counts.

    An empty tracked list means "everywhere", which is the setting a server
    wants on day one; the ignored list always wins, so bot-spam channels stay
    out either way.
    """
    channel_id = int(channel_id or 0)
    if not channel_id:
        return False
    if channel_id in {int(c) for c in ignored or ()}:
        return False
    if tracked:
        return channel_id in {int(c) for c in tracked}
    return True


def acts_from_message(author_id: int, content: str, *, channel_id: int,
                      has_image: bool = False, reply_to: Optional[int] = None,
                      thread_owner: Optional[int] = None,
                      newcomers: Iterable[int] = (),
                      min_chars: int = 4, max_mentions: int = 5,
                      count_self: bool = False) -> list[Act]:
    """Every act one message produces, for the author and for everyone reached.

    Only ``message`` and the two mention metrics come out of ``content``; the
    rest need context the archive never kept, so the backfill simply passes
    none of it and produces exactly the three backfillable acts. That is the
    property that keeps the two paths honest: same function, fewer arguments.

    ``max_mentions`` is a cost ceiling rather than a game rule — each named
    person costs two writes, and one message listing thirty people should not
    spend thirty times a normal message's budget. Distinct ids only, so naming
    the same person five times in one message is one mention.

    ``newcomers`` is whichever of the people this message reached joined the
    server recently. Welcoming is scored against the person doing it, once per
    newcomer per day.
    """
    author_id = int(author_id)
    text = content or ""
    acts: list[Act] = []

    # The message itself. Length is measured on the raw text, so a message that
    # is nothing but a ping is not a free point.
    if len(text.strip()) >= max(0, min_chars):
        acts.append(Act(metric="message", user_id=author_id, channel_id=channel_id))

    if has_image:
        acts.append(Act(metric="image", user_id=author_id, channel_id=channel_id))

    # Everyone this message actually reached: named, replied to, or the owner of
    # the thread it was posted in. Collected so welcoming can be judged once
    # against the whole message rather than per mechanism.
    reached: list[int] = []

    for target in mentioned_ids(text)[: max(0, max_mentions)]:
        if target == author_id and not count_self:
            continue
        acts.append(Act(metric="mention_given", user_id=author_id,
                        partner_id=target, channel_id=channel_id))
        acts.append(Act(metric="mention_received", user_id=target,
                        partner_id=author_id, channel_id=channel_id))
        reached.append(target)

    if reply_to is not None and (int(reply_to) != author_id or count_self):
        target = int(reply_to)
        acts.append(Act(metric="reply_given", user_id=author_id,
                        partner_id=target, channel_id=channel_id))
        acts.append(Act(metric="reply_received", user_id=target,
                        partner_id=author_id, channel_id=channel_id))
        reached.append(target)

    # A thread's owner is credited for every other person who turns up in it,
    # which is the only thing that makes opening a thread worth anything.
    if thread_owner is not None and (int(thread_owner) != author_id or count_self):
        owner = int(thread_owner)
        acts.append(Act(metric="thread_reply_given", user_id=author_id,
                        partner_id=owner, channel_id=channel_id))
        acts.append(Act(metric="thread_reply_received", user_id=owner,
                        partner_id=author_id, channel_id=channel_id))
        reached.append(owner)

    fresh = {int(n) for n in newcomers}
    for target in dict.fromkeys(reached):  # distinct, order preserved
        if target in fresh:
            acts.append(Act(metric="newcomer_welcomed", user_id=author_id,
                            partner_id=target, channel_id=channel_id))
    return acts


# Sanity: every metric this module can emit has to exist in the registry, or a
# rename would fail at the first live message instead of at import.
for _key in ("message", "image", "mention_given", "mention_received",
             "reply_given", "reply_received", "thread_reply_given",
             "thread_reply_received", "newcomer_welcomed"):
    metric_registry.get(_key)
del _key
