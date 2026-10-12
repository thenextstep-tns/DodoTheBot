"""
Where the panel's time goes: a request-timing middleware.

Every request slower than :data:`SLOW_S` is written to the bot's log
(``logs/dodo.log``) with how long it took. While the file
``logs/profile_web`` exists, each slow request also logs the functions that took
the most time inside it (a ``cProfile`` of the event loop's thread for the
request's duration), which is what tells a slow page apart from a busy bot.
Create the file to turn that on and delete it to turn it off; no restart.

Diagnostic only: it never changes a response.
"""

from __future__ import annotations

import cProfile
import io
import logging
import os
import pstats
import time

from aiohttp import web

SLOW_S = 1.5
_FLAG = os.path.join("logs", "profile_web")
_log = logging.getLogger("dodo")


@web.middleware
async def timing(request: web.Request, handler):
    started = time.perf_counter()
    profiler = cProfile.Profile() if os.path.exists(_FLAG) else None
    if profiler:
        try:
            profiler.enable()
        except ValueError:   # another request is already being profiled
            profiler = None
    try:
        return await handler(request)
    finally:
        if profiler:
            profiler.disable()
        took = time.perf_counter() - started
        if took >= SLOW_S:
            _log.info("Slow panel request: %s %s took %.2fs", request.method, request.path, took)
            if profiler:
                out = io.StringIO()
                pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(18)
                _log.info("Profile of %s:\n%s", request.path, out.getvalue()[-3500:])
