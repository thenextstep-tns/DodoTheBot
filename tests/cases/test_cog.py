"""Enrollment gating in the manager, plus the cog's views and bar."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
from helpers.trial_ranks import TrialRankManager, STATE_ENROLLED, STATE_READ, STATE_DISMISSED


class FakeCol:
    """The slice of pymongo these methods actually use."""
    def __init__(self): self.docs = []
    def _match(self, q, d): return all(d.get(k) == v for k, v in q.items())
    def find(self, q, projection=None): return [d for d in self.docs if self._match(q, d)]
    def find_one(self, q, projection=None):
        return next((d for d in self.docs if self._match(q, d)), None)
    def update_one(self, q, update, upsert=False):
        doc = self.find_one(q)
        if doc is None:
            if not upsert: return
            doc = dict(q); doc.update(update.get("$setOnInsert", {})); self.docs.append(doc)
        doc.update(update.get("$set", {}))
    def delete_one(self, q):
        doc = self.find_one(q)
        if doc is not None: self.docs.remove(doc)


enrol_col, image_col = FakeCol(), FakeCol()
mgr = TrialRankManager(FakeCol(), FakeCol(),
                       enrollment_collection=enrol_col, image_collection=image_col)

assert mgr.enrolled_ids(1) == set(), "nobody is automated by default"
assert not mgr.is_enrolled(1, 99)

mgr.set_state(1, 99, STATE_READ, name="nik", source="button")
assert not mgr.is_enrolled(1, 99), "reading the explanation is not consent"

mgr.set_state(1, 99, STATE_ENROLLED, name="nik", source="button")
assert mgr.is_enrolled(1, 99), "consent enrols"
row = enrol_col.find_one({"user_id": 99})
assert row["read_at"] and row["enrolled_at"], "each stage keeps its own stamp"
print("stages kept:", sorted(k for k in row if k.endswith("_at")))

mgr.set_state(1, 100, STATE_DISMISSED, name="other", source="button")
assert mgr.enrolled_ids(1) == {99}, mgr.enrolled_ids(1)
assert not mgr.is_enrolled(2, 99), "enrollment is per guild"

mgr.forget(1, 99)
assert mgr.enrolled_ids(1) == set(), "taking someone off works"

mgr.set_image(1, 555, b"\x89PNG-ish", "image/png")
assert mgr.image_role_ids(1) == {555}
assert mgr.image(1, 555)["content_type"] == "image/png"
mgr.clear_image(1, 555)
assert mgr.image_role_ids(1) == set()
assert mgr.image(1, 555) is None, "no picture is a clean absence, not an error"

# The cog imports and its bar behaves at both ends.
from cogs.trial_ranks import (progress_bar, rank_stars, TrialRanks, RankBoardView,
                              ConsentView, BAR_WIDTH, BAR_FULL, BAR_EMPTY, MAX_STARS)
assert progress_bar(0.0) == BAR_EMPTY * BAR_WIDTH, "empty only when truly at zero"
assert progress_bar(1.0) == BAR_FULL * BAR_WIDTH, "full only on arrival"
assert progress_bar(0.5).count(BAR_FULL) == BAR_WIDTH // 2
assert progress_bar(3.0).count(BAR_FULL) == BAR_WIDTH, "never overflows"
assert progress_bar(0.001).count(BAR_FULL) == 1, "any progress shows"
assert progress_bar(0.999).count(BAR_FULL) == BAR_WIDTH - 1, "nearly there isn't there"
print("bar:", progress_bar(0.6))

from cogs.trial_ranks import STAR_EARNED, STAR_TODO
assert rank_stars(3, 7) == STAR_EARNED * 3 + STAR_TODO * 4
assert rank_stars(0, 7) == STAR_TODO * 7, "unranked shows an empty ladder"
assert rank_stars(7, 7) == STAR_EARNED * 7
assert rank_stars(6, MAX_STARS + 8) == f"{STAR_EARNED} 6/{MAX_STARS + 8}", "long ladders count"
assert rank_stars(0, 0) == "", "no ladder, no stars"
print("stars:", rank_stars(5, 7))
print("PASS")
