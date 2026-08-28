"""
What DodoLand counts, and what each thing is worth.

**This registry is the single source of truth.** A metric's weight, its daily
cap and its per-partner cap are not written out by hand in the parameter list —
:mod:`helpers.dodoland.parameters` *generates* them from every entry below.
That is the standing "everything is tweakable" rule enforced by construction
rather than by remembering: a metric cannot be added without its knobs
appearing on the panel, because there is no second place to forget to add them.

The corollary, and it is enforced by the same mechanism: **nothing is listed
here until something counts it.** A metric in this file is three live knobs on
the panel, and a knob that changes nothing is worse than a missing one, because
somebody will set it and expect an effect.

Two kinds of act
----------------

``SOLO`` acts have one person: posting a message. Capped per day, nothing else.

``SOCIAL`` acts have an actor and a subject who is somebody else: naming
somebody in a message. These are capped **per partner per day** as well, which
is the entire anti-farm design. The first mention from a new person is worth
full weight; the fortieth from the same person in one evening is worth nothing.
A score cannot be inflated without involving more people, which is exactly the
behaviour a socialite tribe should reward.

Why the received side is worth more than the given side
-------------------------------------------------------

Naming somebody is unilateral and free. Being named requires another person to
decide you were the one worth fetching. The weights reflect that, and both
sides are counted, because someone who is only ever mentioned is a celebrity
rather than a socialite.

Backfill, and why the list is in this order
-------------------------------------------

``backfill=True`` means the metric can be reconstructed from the message archive
(``Messages with Channels``: author, channel, guild, and raw text that still
carries its ``<@id>`` mentions). Only the first three are, and they were built
first for exactly that reason: they let DodoLand launch with real towns and a
real relation graph rather than a continent of empty plots.

Everything after them counts **forward only**, because nothing ever stored an
image, a reply target, a thread parent, a voice session, an event RSVP or an
invite use. That is not a drawback, it is the argument for starting the listener
before anything visual exists: these are the better socialite signals, and every
day without them is a day that cannot be recovered.

Reactions are still deliberately absent. Same forward-only situation, and they
will arrive as entries in this list and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

# An act with one participant, versus one that needs somebody else.
SOLO = "solo"
SOCIAL = "social"
KINDS = (SOLO, SOCIAL)


@dataclass(frozen=True)
class Metric:
    """One countable act.

    ``weight`` is points per scoring act. ``daily_cap`` is how many acts of this
    kind can score for one person in a day (0 = uncapped). ``partner_cap`` is
    how many can score from any single other person in a day, and only means
    anything for :data:`SOCIAL` metrics.
    """

    key: str
    label: str
    description: str
    kind: str
    weight: int
    daily_cap: int
    partner_cap: int = 0
    backfill: bool = False

    @property
    def is_social(self) -> bool:
        return self.kind == SOCIAL


# --------------------------------------------------------------------------- #
#  The registry
# --------------------------------------------------------------------------- #
METRICS: tuple[Metric, ...] = (
    Metric(
        key="message",
        label="Message posted",
        description=(
            "A message in a tracked channel, at least the minimum length. Worth "
            "very little on purpose: it is here so a quiet town is not a dead "
            "one, not as a way to earn. Volume crowns whoever talks most, which "
            "is not what a socialite is."
        ),
        kind=SOLO, weight=1, daily_cap=40, backfill=True,
    ),
    Metric(
        key="mention_given",
        label="Named somebody",
        description=(
            "You named another person in a message. Cheap and unilateral, so "
            "worth little, but not nothing: bringing other people into a "
            "conversation is the job."
        ),
        kind=SOCIAL, weight=3, daily_cap=40, partner_cap=4, backfill=True,
    ),
    Metric(
        key="mention_received",
        label="Named by somebody",
        description=(
            "Another person named you. Being who others think to fetch is the "
            "whole tribe in one number. The per-person cap is what stops two "
            "friends farming each other: past it the mention still happens and "
            "simply does not score."
        ),
        kind=SOCIAL, weight=8, daily_cap=40, partner_cap=4, backfill=True,
    ),
    # --- forward-only from here: none of these were ever archived ---------- #
    Metric(
        key="image",
        label="Picture posted",
        description=(
            "A message carrying an image. The fashion, housing and pets "
            "currency. Capped low daily on purpose: ten good screenshots is a "
            "good day and the hundredth is a dump."
        ),
        kind=SOLO, weight=6, daily_cap=10,
    ),
    Metric(
        key="reply_given",
        label="Replied to somebody",
        description="You replied directly to another person's message.",
        kind=SOCIAL, weight=4, daily_cap=40, partner_cap=6,
    ),
    Metric(
        key="reply_received",
        label="Replied to by somebody",
        description=(
            "Another person replied to you. Worth more than a mention because "
            "it costs them more than a ping: they had to answer something."
        ),
        kind=SOCIAL, weight=10, daily_cap=40, partner_cap=6,
    ),
    Metric(
        key="thread_start",
        label="Thread opened",
        description=(
            "You opened a thread or a forum post. Scores once and modestly. "
            "Whether it was worth opening is decided by thread_reply_received, "
            "which needs other people to agree."
        ),
        kind=SOLO, weight=10, daily_cap=5,
    ),
    Metric(
        key="thread_reply_given",
        label="Posted in someone's thread",
        description=(
            "You posted in a thread another person opened. Turning up inside "
            "somebody else's conversation is about as socialite as it gets."
        ),
        kind=SOCIAL, weight=5, daily_cap=30, partner_cap=5,
    ),
    Metric(
        key="thread_reply_received",
        label="Somebody posted in your thread",
        description=(
            "Another person posted in a thread you opened. This is what makes "
            "opening threads worth anything, and it cannot be self-awarded."
        ),
        kind=SOCIAL, weight=12, daily_cap=30, partner_cap=5,
    ),
    Metric(
        key="voice_minute",
        label="Minute in voice with company",
        description=(
            "A minute in a voice channel with at least one other person in it. "
            "Sitting alone in a channel earns nothing, however long you do it. "
            "The daily cap is the real control here: four hours is a full "
            "evening, and past it the hours stop being evidence of anything. "
            "Counts toward town power but builds nothing yet: voice minutes "
            "arrive in far larger numbers than messages and would dominate "
            "whichever building they landed in."
        ),
        kind=SOLO, weight=1, daily_cap=240,
    ),
    Metric(
        key="voice_together",
        label="Shared a voice channel",
        description=(
            "You and another person were in voice together long enough to "
            "count. Capped hard per person per day, because two friends idling "
            "in a channel is the easiest farm on this list and also, "
            "occasionally, a real friendship."
        ),
        kind=SOCIAL, weight=8, daily_cap=20, partner_cap=2,
    ),
    Metric(
        key="event_hosted",
        label="Hosted an event",
        description=(
            "You created a server event. One of the most valuable things a "
            "person can do here, which is why it is weighted like one. Hosting "
            "an event nobody attends is still worth this much and no more: the "
            "attendance is counted separately."
        ),
        kind=SOLO, weight=40, daily_cap=3,
    ),
    Metric(
        key="event_rsvp",
        label="Signed up for an event",
        description="You marked yourself interested in a server event. Turning up matters.",
        kind=SOLO, weight=5, daily_cap=10,
    ),
    Metric(
        key="event_interest_received",
        label="Somebody signed up for your event",
        description=(
            "Another person marked interest in an event you created. This is "
            "how hosting scales with how good the event was, without anyone "
            "having to judge it."
        ),
        kind=SOCIAL, weight=8, daily_cap=40, partner_cap=1,
    ),
    Metric(
        key="newcomer_welcomed",
        label="Welcomed a newcomer",
        description=(
            "You named or replied to somebody inside their first few days on "
            "the server. The single behaviour that most decides whether a "
            "server feels warm, and the one almost nothing ever rewards."
        ),
        kind=SOCIAL, weight=25, daily_cap=10, partner_cap=1,
    ),
    Metric(
        key="command_used",
        label="Used a bot command",
        description=(
            "Somebody ran one of Dodo's commands. Playing with the bot is taking "
            "part too, and it is the one thing on this list a brand new member "
            "can do on their first minute here. Note that if the bot channel is "
            "in the ignored list, this scores nowhere."
        ),
        kind=SOLO, weight=2, daily_cap=20,
    ),
    Metric(
        key="member_recruited",
        label="Brought somebody in",
        description=(
            "Somebody joined the server on your invite. The hardest thing on "
            "this list to fake, because it needs a real person to actually "
            "arrive, and the most valuable thing anybody can do for a "
            "community. It also puts the newcomer next to you in the relation "
            "graph, which is where their town should be."
        ),
        kind=SOCIAL, weight=60, daily_cap=10, partner_cap=1,
    ),
)

BY_KEY: dict[str, Metric] = {metric.key: metric for metric in METRICS}
SOCIAL_KEYS: tuple[str, ...] = tuple(m.key for m in METRICS if m.is_social)
SOLO_KEYS: tuple[str, ...] = tuple(m.key for m in METRICS if not m.is_social)
BACKFILLABLE: tuple[str, ...] = tuple(m.key for m in METRICS if m.backfill)


def get(key: str) -> Metric:
    """The metric for a key, or ``KeyError`` naming what was asked for."""
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(f"Unknown DodoLand metric: {key!r}") from None


# --------------------------------------------------------------------------- #
#  Distinct people reached
# --------------------------------------------------------------------------- #
# Not a Metric: it is not an act, it is a property of the day's pair rows, and
# it is the one number nobody can inflate however hard a fixed set of people
# try. Its weight is a parameter like everything else.
PARTNER_KEY = "partner_day"
PARTNER_LABEL = "Person reached"
PARTNER_DESCRIPTION = (
    "A different person you exchanged something with today, counted once per "
    "person per day however much passed between you. The one number that cannot "
    "be farmed without actually widening your circle, which is why it is the "
    "most valuable thing on this list."
)
PARTNER_WEIGHT = 15
PARTNER_DAILY_CAP = 25
