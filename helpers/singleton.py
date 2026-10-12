"""
Single-instance guard.

On startup the bot calls :func:`terminate_duplicates` to kill any *other* running
instance — either another process running the same entry script (``bot.py``) or
whatever is holding the control-panel port — before it connects. This prevents a
second gateway login and the "address already in use" the in-process web panel
would otherwise hit when an old instance is still around.

The current process and its ancestors (e.g. the ``py`` launcher that started it)
are always protected.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None


def _protected_pids() -> set[int]:
    """This process plus its ancestor chain — never terminate these."""
    protected = {os.getpid()}
    if psutil is None:
        return protected
    try:
        proc = psutil.Process(os.getpid())
        while proc.ppid():
            proc = psutil.Process(proc.ppid())
            protected.add(proc.pid)
    except (psutil.Error, OSError):
        pass
    return protected


def _is_python(name: str) -> bool:
    name = (name or "").lower()
    return "python" in name or name in ("py.exe", "py")


def terminate_duplicates(*, script_marker: str = "bot.py", port: Optional[int] = None, logger=None) -> list[int]:
    """Terminate other instances by matching entry script and/or listening port.

    Returns the list of PIDs it acted on. Safe to call unconditionally: it never
    targets the current process or its launcher, and swallows permission errors.
    """
    if psutil is None:
        if logger:
            logger.warning("psutil not installed; skipping single-instance cleanup.")
        return []

    protected = _protected_pids()
    victims: set[int] = set()

    # 1) Other Python processes running the same entry script.
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.pid in protected or not _is_python(proc.info.get("name")):
                continue
            cmdline = proc.info.get("cmdline") or []
            if any(script_marker in (arg or "") for arg in cmdline):
                victims.add(proc.pid)
        except (psutil.Error, OSError):
            continue

    # 2) Whatever is listening on our port (any process type).
    if port:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if (
                    conn.laddr
                    and conn.laddr.port == port
                    and conn.status == psutil.CONN_LISTEN
                    and conn.pid
                    and conn.pid not in protected
                ):
                    victims.add(conn.pid)
        except (psutil.Error, OSError) as error:
            if logger:
                logger.debug(f"Could not enumerate port {port} owners: {error}")

    if not victims:
        return []

    procs = []
    for pid in victims:
        try:
            procs.append(psutil.Process(pid))
        except psutil.Error:
            continue

    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            continue
    gone, alive = psutil.wait_procs(procs, timeout=3)
    for proc in alive:  # escalate to SIGKILL / TerminateProcess for stubborn ones
        try:
            proc.kill()
        except psutil.Error:
            continue

    acted = sorted(p.pid for p in procs)
    if logger:
        logger.info(f"Single-instance guard terminated existing instance(s): {acted}")
    return acted
