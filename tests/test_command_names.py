"""
Top-level command names must be unique across every cog.

This exists because it wasn't checked. Tabletop's ``/roll`` collided with the
deathroll minigame's, which had owned that name for a long time — and the cog
loaded fine in isolation, so nothing caught it until the bot refused to load the
cog in production. ``CommandAlreadyRegistered`` is raised at *load* time, so one
duplicate name takes a whole cog offline.

It also enforces **Discord's hard cap of 100 top-level application commands per
application**. Exceeding it raises ``CommandLimitReached`` at cog-load time, which
took the tabletop cog offline in production the first time P2 was deployed — the
bot was already sitting at exactly 100. A group costs one slot no matter how many
subcommands it holds, so the fix is always to group, not to delete.

Static analysis rather than a live load: importing every cog needs a Discord
token, a Mongo connection and real config, none of which a name check should
require. Parsing the decorators is enough, because the name is always a literal.

Group **sub**commands are namespaced by their group and are deliberately not
compared — ``/campaign create`` and ``/character create`` are both fine.

Run with ``py tests/test_command_names.py``.
"""

from __future__ import annotations

import ast
import collections
import os
import sys

COG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")

# Decorator forms that create a *top-level* command or group.
# Decorators that put a command in the *application* (slash) tree. Plain
# ``commands.command``/``commands.group`` are prefix-only and cost no slot.
_APP_MARKERS = (
    "commands.hybrid_command",
    "commands.hybrid_group",
    "app_commands.command",
)
_PREFIX_ONLY_MARKERS = ("commands.command", "commands.group")
_TOP_LEVEL_MARKERS = _APP_MARKERS + _PREFIX_ONLY_MARKERS

# Discord's limit. We fail a little under it so a phase can land without an
# emergency regroup; going over is a production outage for a whole cog.
APP_COMMAND_LIMIT = 100
SAFE_CEILING = 96


def _relative(path: str) -> str:
    return os.path.relpath(path, os.path.dirname(COG_DIR)).replace(os.sep, "/")


def collect(app_only: bool = False) -> dict[str, list[str]]:
    """``{command name: [files that define it]}`` for top-level names only.

    ``app_only`` counts just the commands that occupy a slash-command slot.
    """
    names: dict[str, list[str]] = collections.defaultdict(list)

    for root, _dirs, files in os.walk(COG_DIR):
        if "__pycache__" in root:
            continue
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(root, filename)
            tree = ast.parse(open(path, encoding="utf-8").read())

            for node in ast.walk(tree):
                for decorator in getattr(node, "decorator_list", []):
                    if not isinstance(decorator, ast.Call):
                        continue
                    func = ast.unparse(decorator.func)
                    # A group's subcommands decorate with the group's own name
                    # (``@campaign.command``), which is not a top-level marker.
                    markers = _APP_MARKERS if app_only else _TOP_LEVEL_MARKERS
                    if not any(func.startswith(marker) for marker in markers):
                        continue
                    for keyword in decorator.keywords:
                        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                            names[keyword.value.value].append(_relative(path))

                # Class-level ``app_commands.Group(name=...)`` attributes.
                if isinstance(node, ast.Call) and "app_commands.Group" in ast.unparse(node.func):
                    for keyword in node.keywords:
                        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                            names[keyword.value.value].append(_relative(path))

    return names


def main() -> int:
    failed = False

    # --- 1. no two cogs may claim the same top-level name ----------------- #
    names = collect()
    collisions = {
        name: sorted(set(files)) for name, files in names.items() if len(set(files)) > 1
    }
    for name, files in sorted(collisions.items()):
        print(f"  FAIL /{name} is defined in {len(files)} cogs: {', '.join(files)}")
    if collisions:
        print(
            f"       {len(collisions)} collision(s). Discord raises "
            "CommandAlreadyRegistered at load time, which takes a whole cog offline."
        )
        failed = True
    else:
        print(f"  ok   {len(names)} top-level command names, all unique")

    # --- 2. the application must stay under Discord's slash-command cap --- #
    app = collect(app_only=True)
    count = len(app)
    if count > SAFE_CEILING:
        print(
            f"  FAIL {count} top-level slash commands — over the safe ceiling of "
            f"{SAFE_CEILING} (Discord's hard cap is {APP_COMMAND_LIMIT})."
        )
        print(
            "       Group related commands under one parent: a group costs one "
            "slot however many subcommands it holds."
        )
        failed = True
    else:
        print(
            f"  ok   {count} top-level slash commands "
            f"({APP_COMMAND_LIMIT - count} of {APP_COMMAND_LIMIT} slots free)"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
