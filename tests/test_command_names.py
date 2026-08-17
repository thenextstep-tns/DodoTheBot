"""
Top-level command names must be unique across every cog.

This exists because it wasn't checked. Tabletop's ``/roll`` collided with the
deathroll minigame's, which had owned that name for a long time — and the cog
loaded fine in isolation, so nothing caught it until the bot refused to load the
cog in production. ``CommandAlreadyRegistered`` is raised at *load* time, so one
duplicate name takes a whole cog offline.

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
_TOP_LEVEL_MARKERS = (
    "commands.hybrid_command",
    "commands.hybrid_group",
    "commands.command",
    "commands.group",
    "app_commands.command",
)


def _relative(path: str) -> str:
    return os.path.relpath(path, os.path.dirname(COG_DIR)).replace(os.sep, "/")


def collect() -> dict[str, list[str]]:
    """``{command name: [files that define it]}`` for top-level names only."""
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
                    if not any(func.startswith(marker) for marker in _TOP_LEVEL_MARKERS):
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
    names = collect()
    collisions = {
        name: sorted(set(files)) for name, files in names.items() if len(set(files)) > 1
    }

    for name, files in sorted(collisions.items()):
        print(f"  FAIL /{name} is defined in {len(files)} cogs: {', '.join(files)}")

    if collisions:
        print(
            f"\n{len(collisions)} collision(s). Discord raises CommandAlreadyRegistered at "
            "load time, so this takes a whole cog offline."
        )
        return 1

    print(f"  ok   {len(names)} top-level command names, all unique")
    return 0


if __name__ == "__main__":
    sys.exit(main())
