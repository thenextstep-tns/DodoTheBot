"""
DodoLand's activity, written behind the bot's back.

Every counted act used to be up to three round trips to the database (its pair
row, its day row, then what scored), made inside the Discord event that saw
it: with the database across the internet that held up the whole bot for a
tenth of a second or more per message. Now the cog only queues the act
(:meth:`ActivityWriter.put`, instant) and one background thread writes.

It waits a moment for acts to gather (``dodoland_write_batch_seconds``), takes
everything queued, adds up the acts that differ only in how many there were
(the same person, kind of act, room, partner and day) and records each sum once
through :meth:`ActivityStore.record`, which takes an amount and clips it at the
daily cap. So what scores is exactly what scored before, in a fraction of the
writes. Each act carries the day it happened on, so a batch that spans
midnight still counts each act on its own day.

The writer belongs to the bot (``bot.dodoland_writer``), not the cog: a
``reload dodoland`` keeps the same writer and nothing queued is lost. Whatever
is still queued when the process exits is written first (``atexit``).
"""

from __future__ import annotations

import atexit
import queue
import threading
import time
from typing import Optional

from helpers.dodoland.store import today

DEFAULT_BATCH_S = 2.0


class ActivityWriter:
    def __init__(self, store, logger=None) -> None:
        self._store = store
        self._log = logger
        self._q: "queue.SimpleQueue" = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._guild = 0       # the last guild seen, for reading the batch setting
        self.written = 0      # acts written, for anyone asking how it is doing
        self.batches = 0
        self._thread = threading.Thread(target=self._run, name="dodoland-writer", daemon=True)
        self._thread.start()
        atexit.register(self.flush)

    # --------------------------------------------------------------- queueing
    def put(self, guild_id: int, user_id: int, metric: str, *, channel_id: int = 0,
            partner_id: Optional[int] = None, link: bool = True, amount: int = 1,
            day: Optional[str] = None) -> None:
        """Queue one act (``amount`` of it). Never touches the database."""
        self._guild = int(guild_id)
        self._q.put((int(guild_id), int(user_id), str(metric), int(channel_id or 0),
                     None if partner_id is None else int(partner_id), bool(link),
                     day or today(), int(amount)))

    def pending(self) -> int:
        return self._q.qsize()

    # ---------------------------------------------------------------- writing
    def _batch_seconds(self, guild_id: int) -> float:
        try:
            return max(0.0, min(60.0, float(self._store._params.get(guild_id, "dodoland_write_batch_seconds"))))
        except Exception:  # noqa: BLE001 - a setting added since startup is not known yet
            return DEFAULT_BATCH_S

    def _drain(self) -> list:
        items = []
        while True:
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                return items

    def _write(self, items: list) -> None:
        """Add up the acts that differ only in amount, and record each sum once."""
        sums: dict = {}
        for g, u, m, ch, partner, link, day, amount in items:
            key = (g, u, m, ch, partner, link, day)
            sums[key] = sums.get(key, 0) + amount
        for (g, u, m, ch, partner, link, day), amount in sums.items():
            try:
                self._store.record(g, u, m, channel_id=ch, partner_id=partner, link=link,
                                   day=day, amount=amount)
            except Exception as error:  # noqa: BLE001 - one bad act never stops the rest
                if self._log is not None:
                    self._log.error(f"DodoLand failed to record activity: {error}")
        self.written += len(items)
        self.batches += 1

    def _run(self) -> None:
        # Wait, then take everything at once: nothing is ever held outside the
        # queue, so a flush (a reload, the process exiting) misses nothing.
        while True:
            time.sleep(max(0.05, self._batch_seconds(self._guild)))
            if self._q.empty():
                continue
            with self._lock:
                items = self._drain()
                if items:
                    self._write(items)

    def flush(self) -> None:
        """Write everything queued now, in the caller's thread."""
        with self._lock:
            items = self._drain()
            if items:
                self._write(items)


def writer_for(bot) -> ActivityWriter:
    """The bot's one writer, made the first time it is asked for."""
    writer = getattr(bot, "dodoland_writer", None)
    if writer is None:
        writer = bot.dodoland_writer = ActivityWriter(bot.dodoland, getattr(bot, "logger", None))
    return writer
