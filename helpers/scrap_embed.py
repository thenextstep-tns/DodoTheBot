"""
What a scrap looks like while it is happening.

Plain text in, plain text out — no discord objects — so the preview page and the
tests render exactly what the channel will see. The cog's only job is to put
:func:`render` into an embed description and edit the message once a second.

The layout is a monospace block because the whole point is two teams facing each
other: names left, names right, health between them, and the middle strip
showing where something just happened. Proportional text cannot line that up,
and a column that does not line up reads as noise rather than as a battlefield.
"""

from __future__ import annotations

BAR_WIDTH = 8
FIELD_WIDTH = 44          # the middle strip, between the two health bars
NAME_WIDTH = 12

INVITE = "Show them something. Any emoji, anything at all. It happens to every cat in the room."


def _bar(hp: int, max_hp: int, *, flip: bool = False) -> str:
    filled = 0 if max_hp <= 0 else max(0, min(BAR_WIDTH, round(hp / max_hp * BAR_WIDTH)))
    bar = "█" * filled + "·" * (BAR_WIDTH - filled)
    return bar[::-1] if flip else bar


def _clip(name: str, width: int = NAME_WIDTH) -> str:
    return name if len(name) <= width else name[:width - 1] + "…"


def _middle(left, right, events: list[dict]) -> str:
    """The strip between two cats: quiet, or showing what just landed there."""
    names = {e.get("target") for e in events}
    marks = []
    for event in events:
        if event.get("target") in (getattr(left, "name", None), getattr(right, "name", None)):
            marks.append({"crit": "💥", "hit": "✳", "ko": "🪦", "miss": "·"}.get(event["kind"], ""))
    token = "".join(dict.fromkeys(m for m in marks if m)) or ""
    if not token:
        return "─" * FIELD_WIDTH
    pad = FIELD_WIDTH - len(token) * 2
    side = max(1, pad // 2)
    return "─" * side + token + "─" * max(1, FIELD_WIDTH - side - len(token) * 2)


class _Slot:
    """A cat, or an empty place opposite one — so uneven teams still line up."""

    def __init__(self, cat: dict = None):
        self.cat = cat
        self.name = cat["name"] if cat else None

    def left(self) -> str:
        if not self.cat:
            return " " * (NAME_WIDTH + BAR_WIDTH + 6)
        state = "" if self.cat["alive"] else "†"
        return (f"{_clip(self.cat['name']):<{NAME_WIDTH}} "
                f"{_bar(self.cat['hp'], self.cat['max_hp'], flip=True)} "
                f"{self.cat['hp']:>3}{state:<1}")

    def right(self) -> str:
        if not self.cat:
            return ""
        state = "" if self.cat["alive"] else "†"
        return (f"{state:>1}{self.cat['hp']:<3} "
                f"{_bar(self.cat['hp'], self.cat['max_hp'])} "
                f"{_clip(self.cat['name'])}")


def battlefield(state: dict, events: list[dict] = None) -> str:
    """The two teams facing each other, one row per pairing."""
    left = [c for c in state["cats"] if c["side"] == "A"]
    right = [c for c in state["cats"] if c["side"] == "B"]
    rows = []
    for index in range(max(len(left), len(right))):
        a = _Slot(left[index] if index < len(left) else None)
        b = _Slot(right[index] if index < len(right) else None)
        rows.append(f"{a.left()} {_middle(a, b, events or [])} {b.right()}".rstrip())
    return "\n".join(rows)


def scoreboard(state: dict, *, seconds_left: int = None, teams: tuple = ("Side A", "Side B"),
               events: list[dict] = None, finished: bool = False) -> str:
    """The whole live view: invitation, clock, battlefield, recent moves."""
    head = [INVITE, ""]
    if finished:
        head.append(f"Round {state['round']} · over")
    elif seconds_left is not None:
        # A bare number counts down more legibly than a progress bar, and it is
        # one character to edit each second rather than a redrawn widget.
        head.append(f"Round {state['round']} · ends in {max(0, int(seconds_left))}s")
    else:
        head.append(f"Round {state['round']}")

    left_name, right_name = teams
    header = f"{_clip(left_name, NAME_WIDTH + 12):<{NAME_WIDTH + 12}}{right_name:>{FIELD_WIDTH}}"
    block = "```\n" + header + "\n" + battlefield(state, events) + "\n```"

    lines = head + [block]
    history = state.get("history") or []
    if history:
        lines.append("**Last moves**")
        lines.extend(history)
    return "\n".join(lines)
