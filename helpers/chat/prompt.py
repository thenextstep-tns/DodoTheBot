"""
Prompt assembly — three short blocks instead of one long essay.

The prompt this replaces was around 600–900 tokens per call and spent most of
them badly: five prose paragraphs describing five relationship bands, a
drowsiness table, four numbered tasks, and a demand that the model **echo the
user's entire stored memory back** on every reply. That last one was charged
twice (in and out), grew without limit, and meant a single bad completion could
truncate somebody's history for good.

What goes out now:

``persona``
    Static, per server, ~100 tokens. Who she is. Never how she should act today —
    the moment a prompt names a mode, the model wears it as a costume.
``state``
    Numbers, not prose. Relationship bands were five buckets you could feel her
    snap between; ``close 0.78`` is continuous and the model reads it fine.
``dial`` + task
    A budget (see :mod:`dial`) and a four-key JSON contract.

Memory is now a **delta**: ``learned`` carries one new fact or null, and the
append happens in Python. Output tokens for memory go from "the whole blob" to
about ten, and the blob can no longer be destroyed by a bad generation.
"""

from __future__ import annotations

from typing import Optional

from helpers.chat.dial import Dial
from helpers.chat.state import ChatState, Tuning

# The JSON contract. Spelled once, here, because the parser in the cog reads the
# same names.
J_SAY = "say"
J_FELT = "felt"
J_LEARNED = "learned"
J_RUMOUR = "rumour"
J_RUMOUR_ABOUT = "about"
J_RUMOUR_WHAT = "what"

_TASK = (
    "Obey the dial exactly: it is a hard limit, not a suggestion.\n"
    f'Reply as Dodo. Answer with JSON only: {{"{J_SAY}": string, "{J_FELT}": -10..10, '
    f'"{J_LEARNED}": string or null, "{J_RUMOUR}": null or '
    f'{{"{J_RUMOUR_ABOUT}": number, "{J_RUMOUR_WHAT}": string}}}}\n'
    f'"{J_FELT}" is how their message landed with you. '
    f'"{J_LEARNED}" is one durable new fact they stated about themselves, else null — '
    "never repeat something already listed under recalls."
)

_RUMOUR_TASK = (
    '"{key}" is a story or fact they told about one of the people listed under targets '
    "(use that person's number). Opinions, questions and passing moods are not rumours; "
    "use null for those."
).format(key=J_RUMOUR)

_UNPROMPTED = (
    "Nobody addressed you. You are choosing to speak up in a conversation already in "
    "progress, the way a person would. Only do it if you have something genuinely worth "
    f'adding — otherwise return "{J_SAY}" as an empty string and say nothing at all.'
)


def _familiarity_phrase(state: ChatState) -> str:
    """How much shared history she is entitled to assume."""
    if state.seen <= 1:
        return "never spoken before"
    if state.familiarity < 0.15:
        return "barely know them"
    if state.familiarity < 0.5:
        return "know them a bit"
    return "know them well"


def state_block(name: str, state: ChatState, tuning: Tuning) -> str:
    """Everything she currently holds about this person, as compactly as it goes."""
    lines = [f"{name} — {_familiarity_phrase(state)}, closeness {state.closeness}"]

    grudge = state.top_grudge()
    if grudge is not None:
        fading = " (fading)" if grudge.get("strength", 1.0) < 0.4 else ""
        lines.append(f"holding against them: {grudge['text']}{fading}")

    facts = state.recall_facts(tuning)
    if facts:
        lines.append("recalls: " + "; ".join(facts))

    rumours = state.recall_rumours(tuning)
    if rumours:
        heard = "; ".join(
            f"\"{r.get('rumour')}\" (from {r.get('source_name', 'someone')})" for r in rumours
        )
        lines.append("heard about them: " + heard)

    return "\n".join(lines)


def others_block(others: list[dict]) -> str:
    """The people mentioned in the message, and the rumour targets they double as.

    Numbered because the model answers with an index — cheaper and far less
    error-prone than asking it to echo a snowflake back.
    """
    if not others:
        return ""
    lines = []
    for index, person in enumerate(others):
        detail = f"{index}. {person['name']}"
        if person.get("closeness") is not None:
            detail += f" (closeness {person['closeness']})"
        if person.get("facts"):
            detail += " — " + "; ".join(person["facts"])
        lines.append(detail)
    return "targets:\n" + "\n".join(lines)


def build(*, persona: str, name: str, state: ChatState, tuning: Tuning, dial: Dial,
          others: Optional[list[dict]] = None, recent: Optional[list[str]] = None,
          unprompted: bool = False) -> str:
    """The whole system prompt, in the order the model reads best."""
    blocks = [persona.strip(), state_block(name, state, tuning)]

    if dial.note:
        blocks.append(dial.note)
    if dial.obsession:
        blocks.append(f"on your mind today: {dial.obsession}")

    others = others or []
    if others:
        blocks.append(others_block(others))

    if recent:
        blocks.append("the conversation so far:\n" + "\n".join(recent))
    if unprompted:
        blocks.append(_UNPROMPTED)

    blocks.append(f"dial: {dial.line()}")
    blocks.append(_TASK + ("\n" + _RUMOUR_TASK if others else ""))
    return "\n\n".join(block for block in blocks if block)
