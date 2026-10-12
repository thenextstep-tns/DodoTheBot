"""
Persistent state machine for in-progress interactive flows.

Most of Dodo's interactive features (the co-op games, confirmations, reaction
pagers) hold their state in memory inside a ``bot.wait_for("reaction_add")``
loop. A crash or a restart silently drops every one of them mid-play. This
module is the reusable, Mongo-backed framework a flow can opt into so its state
survives a restart and is **auto-resumed** on the next ``on_ready``.

The framework is deliberately flow-agnostic: it stores a small envelope
(``kind`` + ids + an arbitrary ``data`` blob) and, on startup, hands each still
``active`` record back to the handler registered for its ``kind``.

--------------------------------------------------------------------------- #
State document schema (collection ``config_py.active_states``)
--------------------------------------------------------------------------- #
    {
        "_id":        ObjectId,
        "kind":       "cheese",        # selects the resume handler
        "status":     "active" | "done" | "interrupted",
        "guild_id":   int | None,
        "channel_id": int,
        "message_id": int | None,      # the live game message, once it exists
        "data":       {...},           # arbitrary per-flow primitives (BSON-safe)
        "version":    int,             # bumped on every save (optimistic concurrency)
        "created_at": datetime,
        "updated_at": datetime,
    }

Only BSON-safe primitives belong in ``data`` — **never** store ``discord``
objects. Store ids (user/message/channel ids, counters, dicts) and re-fetch the
live objects on resume via ``bot.get_channel`` / ``channel.fetch_message`` /
``bot.get_user``.

--------------------------------------------------------------------------- #
Writing a resumable flow (reference template)
--------------------------------------------------------------------------- #
A flow subclasses :class:`PersistentFlow`, sets a unique ``kind``, and registers
itself (the base ``__init__`` does that for you). It creates a state when the
flow starts, saves after each meaningful mutation, closes it when the flow ends,
and knows how to rebuild itself from a stored document in ``resume``::

    from helpers.state_machine import PersistentFlow, StateHandle

    class WidgetFlow(PersistentFlow):
        kind = "widget"

        async def start(self, channel, initiator):
            msg = await channel.send(embed=self._embed(count=1))
            await msg.add_reaction("👍")
            handle = self.new_state(
                guild_id=channel.guild.id,
                channel_id=channel.id,
                message_id=msg.id,
                data={"count": 1, "players": [initiator.id]},
            )
            await self._loop(handle, msg)

        async def resume(self, bot, handle: StateHandle):
            # Rebuild live objects from stored ids; bail (mark interrupted) if
            # the channel/message is gone. resume MUST be idempotent — never
            # re-award a reward that a save already recorded as paid out.
            channel = bot.get_channel(handle.channel_id)
            if channel is None:
                return await self.cannot_resume(handle)
            try:
                msg = await channel.fetch_message(handle.message_id)
            except discord.HTTPException:
                return await self.cannot_resume(handle)
            await self._loop(handle, msg)

        async def _loop(self, handle, msg):
            while True:
                emoji, user = await messages.wait_for_reaction(self.bot, msg, ["👍"], add=False)
                if emoji is None:
                    handle.close()                     # timeout → done
                    return
                count = handle.data["count"] + 1
                handle.save({"count": count})          # persist before/at each step
                if count >= 10:
                    handle.close()
                    return

Then in the cog's ``__init__``::

    def __init__(self, bot):
        self.bot = bot
        self.flow = WidgetFlow(bot)   # registers "widget" for auto-resume

On the next startup ``StateStore.resume_all`` (called once from ``on_ready``)
finds every ``active`` document and calls the matching handler's ``resume``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterator, Optional

import discord
from bson import ObjectId

STATUS_ACTIVE = "active"
STATUS_DONE = "done"
STATUS_INTERRUPTED = "interrupted"

# A resume handler: given the bot and the reconstructed handle, continue the flow.
ResumeHandler = Callable[["object", "StateHandle"], Awaitable[None]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StateHandle:
    """A live view over one state document, so a flow can mutate it without
    re-passing its id. Reads come from the cached ``doc``; writes go straight to
    Mongo and update the cache. ``handle.data`` is the per-flow blob."""

    def __init__(self, store: "StateStore", doc: dict):
        self._store = store
        self._doc = doc

    @property
    def id(self) -> ObjectId:
        return self._doc["_id"]

    @property
    def kind(self) -> str:
        return self._doc["kind"]

    @property
    def status(self) -> str:
        return self._doc.get("status", STATUS_ACTIVE)

    @property
    def data(self) -> dict:
        return self._doc.get("data", {})

    @property
    def version(self) -> int:
        return self._doc.get("version", 0)

    @property
    def guild_id(self) -> Optional[int]:
        return self._doc.get("guild_id")

    @property
    def channel_id(self) -> Optional[int]:
        return self._doc.get("channel_id")

    @property
    def message_id(self) -> Optional[int]:
        return self._doc.get("message_id")

    def save(self, data_patch: dict, *, expected_version: Optional[int] = None) -> bool:
        """Merge ``data_patch`` into the ``data`` sub-document and bump the version.

        Pass ``expected_version`` for optimistic concurrency: the write only
        applies if the stored version still matches, and the method returns
        ``False`` (leaving the cache untouched) when it doesn't. Without it the
        write is unconditional and always returns ``True``.
        """
        updated = self._store.update(
            self.id, {f"data.{k}": v for k, v in data_patch.items()}, expected_version=expected_version
        )
        if updated is None:
            return False
        self._doc = updated
        return True

    def attach_message(self, message_id: int) -> None:
        """Record the live game message id once it has been sent."""
        updated = self._store.update(self.id, {"message_id": message_id})
        if updated is not None:
            self._doc = updated

    def close(self, status: str = STATUS_DONE) -> None:
        """Mark the flow finished (``done`` normally, ``interrupted`` on failure)."""
        updated = self._store.update(self.id, {"status": status})
        if updated is not None:
            self._doc = updated

    def refresh(self) -> "StateHandle":
        """Re-read the document from Mongo into the cache."""
        fresh = self._store.get_doc(self.id)
        if fresh is not None:
            self._doc = fresh
        return self


class StateStore:
    """CRUD over the state collection plus the ``kind → resume handler`` registry
    and the startup auto-resume dispatch. One instance lives on the bot as
    ``bot.state``."""

    def __init__(self, collection, *, logger: Optional[logging.Logger] = None):
        self._col = collection
        self._handlers: dict[str, ResumeHandler] = {}
        self._logger = logger or logging.getLogger(__name__)

    # ----------------------------------------------------------------- #
    #  Registry
    # ----------------------------------------------------------------- #
    def register(self, kind: str, handler: ResumeHandler) -> None:
        """Register the resume handler for a ``kind``. Last registration wins, so
        reloading a cog cleanly re-points the handler at the new code."""
        self._handlers[kind] = handler
        self._logger.debug(f"Registered state resume handler for kind '{kind}'.")

    # ----------------------------------------------------------------- #
    #  CRUD
    # ----------------------------------------------------------------- #
    def create(
        self,
        kind: str,
        *,
        guild_id: Optional[int],
        channel_id: int,
        message_id: Optional[int] = None,
        data: Optional[dict] = None,
    ) -> StateHandle:
        """Insert a new ``active`` state and return a handle to it."""
        now = _now()
        doc = {
            "kind": kind,
            "status": STATUS_ACTIVE,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "data": data or {},
            "version": 0,
            "created_at": now,
            "updated_at": now,
        }
        doc["_id"] = self._col.insert_one(doc).inserted_id
        return StateHandle(self, doc)

    def update(self, state_id, patch: dict, *, expected_version: Optional[int] = None) -> Optional[dict]:
        """Apply ``$set`` ``patch`` (dotted keys allowed), bump ``version`` and
        ``updated_at``, and return the post-update document — or ``None`` if the
        ``expected_version`` guard didn't match / the doc is gone."""
        query: dict = {"_id": state_id}
        if expected_version is not None:
            query["version"] = expected_version
        return self._col.find_one_and_update(
            query,
            {"$set": {**patch, "updated_at": _now()}, "$inc": {"version": 1}},
            return_document=True,  # pymongo.ReturnDocument.AFTER == True
        )

    def get_doc(self, state_id) -> Optional[dict]:
        return self._col.find_one({"_id": state_id})

    def get(self, state_id) -> Optional[StateHandle]:
        doc = self.get_doc(state_id)
        return StateHandle(self, doc) if doc is not None else None

    def close(self, state_id, status: str = STATUS_DONE) -> None:
        self.update(state_id, {"status": status})

    def iter_active(self, kind: Optional[str] = None) -> Iterator[StateHandle]:
        """Yield a handle for every ``active`` state (optionally filtered by kind)."""
        query: dict = {"status": STATUS_ACTIVE}
        if kind is not None:
            query["kind"] = kind
        for doc in self._col.find(query):
            yield StateHandle(self, doc)

    # ----------------------------------------------------------------- #
    #  Auto-resume
    # ----------------------------------------------------------------- #
    async def resume_all(self, bot) -> None:
        """Dispatch every ``active`` state to its handler's resume, once at startup.

        Each resume is isolated: an exception (or a missing handler) marks that
        one ``interrupted`` and moves on, so a single bad record can't block the
        rest or crash startup.
        """
        states = list(self.iter_active())
        if not states:
            self._logger.info("No interrupted flows to resume.")
            return
        self._logger.info(f"Resuming {len(states)} interrupted flow(s)...")
        for handle in states:
            handler = self._handlers.get(handle.kind)
            if handler is None:
                self._logger.warning(
                    f"No resume handler registered for kind '{handle.kind}' "
                    f"(state {handle.id}); marking interrupted."
                )
                handle.close(STATUS_INTERRUPTED)
                continue
            try:
                await handler(bot, handle)
            except Exception as error:  # noqa: BLE001 — one bad flow must not sink the rest
                self._logger.error(f"Failed to resume {handle.kind} state {handle.id}: {error}")
                handle.close(STATUS_INTERRUPTED)


class PersistentFlow:
    """Optional convenience base for a resumable flow.

    Subclass it, set a unique class-level :attr:`kind`, and implement
    :meth:`resume`. Constructing the flow registers its resume handler, so a cog
    just does ``self.flow = MyFlow(bot)`` in ``__init__``.
    """

    kind: str = ""

    def __init__(self, bot):
        if not self.kind:
            raise ValueError(f"{type(self).__name__} must set a non-empty 'kind'.")
        self.bot = bot
        bot.state.register(self.kind, self.resume)

    def new_state(
        self,
        *,
        guild_id: Optional[int],
        channel_id: int,
        message_id: Optional[int] = None,
        data: Optional[dict] = None,
    ) -> StateHandle:
        """Create a state stamped with this flow's ``kind``."""
        return self.bot.state.create(
            self.kind, guild_id=guild_id, channel_id=channel_id, message_id=message_id, data=data
        )

    async def resume(self, bot, handle: StateHandle) -> None:  # pragma: no cover - abstract
        """Rebuild live objects from the stored ids and continue the flow.

        Implementations **must be idempotent**: resuming a flow whose reward was
        already recorded must not pay it out again. Re-fetch the channel/message
        and, if anything essential is gone, call :meth:`cannot_resume`.
        """
        raise NotImplementedError

    async def cannot_resume(self, handle: StateHandle, notice: Optional[str] = None) -> None:
        """Give up on a flow that can't be re-entered: best-effort edit the live
        message to an 'interrupted' note, then close the state as ``interrupted``."""
        notice = notice or "This interactive event was interrupted by a restart and can't be resumed."
        if handle.channel_id and handle.message_id:
            channel = self.bot.get_channel(handle.channel_id)
            if channel is not None:
                try:
                    message = await channel.fetch_message(handle.message_id)
                    await message.edit(embed=discord.Embed(description=notice, color=0xE74C3C))
                    await message.clear_reactions()
                except discord.HTTPException:
                    pass
        handle.close(STATUS_INTERRUPTED)
