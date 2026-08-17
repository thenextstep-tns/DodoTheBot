"""One actor's role edits must never be merged into another's."""
import sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
# Mirrors the cog's debounce: bucket, then net the sets per bucket.
def buckets(events, key_by_actor):
    pending = {}
    for guild, member, actor, added, removed in events:
        key = (guild, member, actor) if key_by_actor else (guild, member)
        slot = pending.setdefault(key, {"added": set(), "removed": set(), "actor": actor})
        slot["added"].update(added)
        slot["removed"].update(removed)
        if not key_by_actor and actor != "Unknown":
            slot["actor"] = actor      # the old overwrite
    out = []
    for key, d in pending.items():
        fa, fr = d["added"] - d["removed"], d["removed"] - d["added"]
        if fa or fr:
            out.append((d["actor"], sorted(fa), sorted(fr)))
    return out


# Exactly what happened: Fox removes then re-adds a trifecta, and between the
# two the bot re-ranks the member.
events = [
    (1, 7, "Fox",  [],          ["Trifecta"]),
    (1, 7, "Fox",  ["Trifecta"], []),
    (1, 7, "Dodo", ["Legend"],  ["Master"]),
]

old = buckets(events, key_by_actor=False)
print("keyed by member only:", old)
assert old == [("Dodo", ["Legend"], ["Master"])], old
print("   -> Fox's edit vanished and the entry was credited to Dodo")

new = buckets(events, key_by_actor=True)
print("keyed by member + actor:", sorted(new))
actors = {a for a, _, _ in new}
assert "Dodo" in actors, "the bot's rank change still logs"
assert ("Dodo", ["Legend"], ["Master"]) in new, "and is attributed correctly"
# Fox's own remove+add still nets to zero, which is the debounce working: the
# member ended up exactly where they started. What must not happen is Fox's
# edits being folded into Dodo's entry.
assert all(a != "Fox" or ("Legend" not in add and "Master" not in rem)
           for a, add, rem in new), "actors must not contaminate each other"

# A one-way edit by each person gives one entry each.
two = buckets([(1, 7, "Fox", ["Trifecta"], []),
               (1, 7, "Dodo", ["Legend"], ["Master"])], key_by_actor=True)
print("one edit each:", sorted(two))
assert len(two) == 2 and {a for a, _, _ in two} == {"Fox", "Dodo"}
print("PASS")
