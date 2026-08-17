"""Scene repository — campaign-scoped."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from config.database import dnd_scenes
from helpers.dnd.store.repo import ScopedRepo
from helpers.dnd.world.scene import STATUS_CLOSED, STATUS_OPEN, Scene


class SceneRepo(ScopedRepo):
    """Scenes in one campaign."""

    collection = dnd_scenes
    requires_campaign = True

    def get(self, scene_id: Any) -> Optional[Scene]:
        doc = self.by_id(scene_id)
        return Scene.from_doc(doc) if doc else None

    def open_in_channel(self, channel_id: int) -> Optional[Scene]:
        """The open scene bound to a channel, if any.

        A channel holds at most one open scene: two live scenes in one thread
        would give the event log two interleaved presents and no way to tell
        which one a message belonged to.
        """
        doc = self.find_one({"channel_id": int(channel_id), "status": STATUS_OPEN})
        return Scene.from_doc(doc) if doc else None

    def open_scenes(self) -> list[Scene]:
        return [
            Scene.from_doc(d)
            for d in self.find({"status": STATUS_OPEN}, sort=[("opened_at", 1)])
        ]

    def recent(self, limit: int = 10) -> list[Scene]:
        return [Scene.from_doc(d) for d in self.find(sort=[("opened_at", -1)], limit=limit)]

    def create(self, scene: Scene) -> Scene:
        doc = scene.to_doc()
        doc.pop("_id", None)
        scene.id = self.insert(doc)
        return scene

    def attach_message(self, scene_id: Any, message_id: int) -> int:
        return self.update_by_id(scene_id, {"message_id": int(message_id)})

    def set_present(self, scene_id: Any, entity_ids: list) -> int:
        return self.update_by_id(scene_id, {"present": list(entity_ids)})

    def add_present(self, scene_id: Any, entity_id: Any) -> int:
        return self.apply({"_id": scene_id}, {"$addToSet": {"present": entity_id}})

    def close(self, scene_id: Any) -> int:
        return self.update_by_id(
            scene_id, {"status": STATUS_CLOSED, "closed_at": datetime.now(timezone.utc)}
        )
