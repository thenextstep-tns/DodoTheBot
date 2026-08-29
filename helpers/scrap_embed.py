"""
What a scrap looks like while it is happening.

Plain text in, plain text out — no discord objects — so the preview and the
tests render exactly what the channel sees. The cog puts :func:`scoreboard` in
an embed description and edits the message once a second.

This used to be a monospace code block, on the theory that two teams facing each
other need columns that line up. That was wrong twice over: emoji do not render
inside a code block, so every cat was a blank, and the line was far too wide for
a phone so it wrapped into nonsense. It is ordinary embed text now, one line per
pairing, reading left to right the way the fight does:

    **Fox** · Steak 🍞 ▰▰▰▱▱ 12  💥  13 ▱▱▰▰▰ 🐅 Bobo · **Lyna**
"""

from __future__ import annotations

BAR = 5
NAME = 11

INVITE = "React with anything at all. Whatever you show them, every cat in the ring reacts."

# What happened on a row this round, in the order it is worth reporting.
MARKS = {"ko": "🪦", "crit": "💥", "hit": "⚔️", "miss": "💨"}
QUIET = "⋯"


def _clip(name: str, width: int = NAME) -> str:
    name = str(name or "")
    return name if len(name) <= width else name[:width - 1] + "…"


def _bar(hp: int, max_hp: int, *, flip: bool = False) -> str:
    """A short block bar. The left side fills toward the middle, so the two
    teams lean into each other rather than both pointing the same way."""
    filled = 0 if max_hp <= 0 else max(0, min(BAR, round(hp / max_hp * BAR)))
    bar = "▰" * filled + "▱" * (BAR - filled)
    return bar[::-1] if flip else bar


def _mark(cat: dict, events: list) -> str:
    """The single most interesting thing that happened to this cat this round."""
    if cat is None:
        return ""
    kinds = {e.get("kind") for e in (events or []) if e.get("target") == cat["name"]}
    for kind, glyph in MARKS.items():
        if kind in kinds:
            return glyph
    return ""


def _side(cat: dict, owner: str, *, left: bool) -> str:
    name = _clip(cat["name"])
    if not cat["alive"]:
        name = f"~~{name}~~"
    who = f"**{_clip(owner or '?')}**"
    if left:
        return f"{who} · {name} {cat['emoji']} {_bar(cat['hp'], cat['max_hp'], flip=True)} `{cat['hp']:>3}`"
    return f"`{cat['hp']:<3}` {_bar(cat['hp'], cat['max_hp'])} {cat['emoji']} {name} · {who}"


def battlefield(state: dict, owners: dict = None, events: list = None) -> str:
    """Both teams facing each other, one line per pairing."""
    owners = owners or {}
    left = [c for c in state["cats"] if c["side"] == "A"]
    right = [c for c in state["cats"] if c["side"] == "B"]

    rows = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        middle = _mark(a, events) or _mark(b, events) or QUIET
        parts = [
            _side(a, owners.get(a["name"]), left=True) if a else "​",
            middle,
            _side(b, owners.get(b["name"]), left=False) if b else "​",
        ]
        rows.append("  ".join(parts))
    return "\n".join(rows)


def scoreboard(state: dict, *, seconds_left: int = None, owners: dict = None,
               events: list = None, finished: bool = False) -> str:
    """The whole live view: invitation, clock, battlefield, recent moves."""
    if finished:
        head = f"**Round {state['round']}** · over"
    elif seconds_left is not None:
        head = f"**Round {state['round']}** · ends in **{max(0, int(seconds_left))}s**"
    else:
        head = f"**Round {state['round']}**"

    lines = [INVITE, "", head, "", battlefield(state, owners, events)]

    history = state.get("history") or []
    if history:
        lines += ["", "**Last moves**"] + list(history)
    return "\n".join(lines)


def shown_line(added: dict) -> str:
    """Who has thrown what in, for the line above the embed.

    Reactions are taken off the message as they arrive, so this is the only
    record of them: without it a fight is a wall of cat noise with no sign of
    who caused any of it.
    """
    if not added:
        return ""
    return "\n".join(f"**{who}** added {' '.join(emoji)}" for who, emoji in added.items())
