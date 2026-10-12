"""New members join the ranking system; prior decisions are not overwritten."""
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from helpers.trial_ranks import TrialRankManager, STATE_DISMISSED, STATE_ENROLLED

src = pathlib.Path("cogs/trial_ranks.py").read_text(encoding="utf-8")
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

join = ast.unparse(funcs["on_member_join"])
assert "member.bot" in join, "bots must not be enrolled"
assert "runs_here" in join, "a disabled cog still means no"
assert "config.get('ranks')" in join, "guilds with no ladder are left alone"
assert "enrollment_state" in join, "an existing decision has to be checked"
assert join.index("enrollment_state") < join.index("self.enrol"), \
    "it enrols before looking for a prior answer"
assert "source='joined'" in join, "the roster should say how they arrived"
print("on_member_join  guards: bot, cog, ladder, prior decision")

# The listener is registered, not just defined.
node = funcs["on_member_join"]
decorators = [ast.unparse(d) for d in node.decorator_list]
assert any("Cog.listener" in d for d in decorators), decorators
print("on_member_join  registered as a listener")

# Exactly one of every method, not just of the four listeners this once named.
# A duplicate definition silently wins and the earlier copy becomes dead code:
# editing it changes nothing, and nothing anywhere says so. A block of nine
# methods sat pasted twice in this file for weeks precisely because the check
# below was a hand-written list that did not mention them.
_cls = next(n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "TrialRanks")
_defined = [n.name for n in _cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
_twice = sorted({n for n in _defined if _defined.count(n) > 1})
assert not _twice, f"defined more than once, the later copy wins: {_twice}"
print(f"no duplicated method definitions ({len(_defined)} methods)")


class Col:
    def __init__(s): s.docs = []
    def _m(s, q, d): return all(d.get(k) == v for k, v in q.items())
    def find(s, q, p=None): return [d for d in s.docs if s._m(q, d)]
    def find_one(s, q, p=None): return next((d for d in s.docs if s._m(q, d)), None)
    def update_one(s, q, u, upsert=False):
        d = s.find_one(q)
        if d is None:
            d = dict(q); d.update(u.get("$setOnInsert", {})); s.docs.append(d)
        d.update(u.get("$set", {}))
    def delete_one(s, q):
        d = s.find_one(q)
        if d: s.docs.remove(d)


col = Col()
m = TrialRankManager(Col(), Col(), enrollment_collection=col)

# Never asked: no row, so a join may enrol them.
assert m.enrollment_state(42, 1) is None
# Said no: the row survives, and that is what the listener checks.
m.set_state(42, 2, STATE_DISMISSED, name="Tomtem", source="button")
assert m.enrollment_state(42, 2) == STATE_DISMISSED
assert not m.is_enrolled(42, 2), "dismissed is not enrolled"
# Already on: also has a row, so a rejoin changes nothing.
m.set_state(42, 3, STATE_ENROLLED, name="Fox", source="panel")
assert m.enrollment_state(42, 3) == STATE_ENROLLED
print("enrollment_state distinguishes 'never asked' from 'said no'")
print("PASS")
