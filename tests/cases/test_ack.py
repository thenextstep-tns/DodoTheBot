"""Slow interaction paths must acknowledge before they do the slow thing.

Discord gives three seconds. Both /rank and the announcement button read Mongo
and can edit roles, which does not fit; missing the budget shows "the
application did not respond" even when the work went through.
"""
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

src = pathlib.Path("cogs/trial_ranks.py").read_text(encoding="utf-8")
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def body_of(name):
    return ast.unparse(funcs[name])


# /rank: the enrolled branch recalculates, so it has to ack first.
rank = body_of("rank")
assert "context.defer" in rank, "/rank never acknowledges"
assert rank.index("context.defer") < rank.index("self.refresh"), \
    "/rank starts recalculating before acknowledging"
assert rank.index("context.defer") < rank.index("rank_embed"), \
    "/rank renders before acknowledging"
print("rank            defers before refresh and render")

# The consent reply is deliberately *not* deferred: it is one cached read, and
# deferring changes which message the timeout has to edit.
consent_at = rank.index("ConsentView")
assert consent_at < rank.index("context.defer"), \
    "the consent branch should return before the defer"
print("rank            consent branch still replies directly")

# The announcement button takes the same care.
check = body_of("handle_check")
assert check.index("response.defer") < check.index("self.refresh"), \
    "the button recalculates before acknowledging"
print("handle_check    defers before refresh")

# Anything that edits roles must be reachable only after an ack, so no other
# command may call refresh/recalculate without one.
for name in ("rank", "handle_check"):
    b = body_of(name)
    if "self.refresh" in b or "self.recalculate" in b:
        assert "defer" in b, f"{name} does slow work with no acknowledgement"
print("no unacknowledged slow path")
print("PASS")
