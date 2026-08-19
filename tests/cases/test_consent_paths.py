"""/rank and the announcement button must both ask an un-enrolled user first."""
import ast
import pathlib

COG = pathlib.Path("cogs/trial_ranks.py")   # run from the repo root
src = COG.read_text(encoding="utf-8")
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def guard_for(fn):
    """The `if ...is_enrolled...` that decides card-vs-ask."""
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and "is_enrolled" in ast.unparse(node.test):
            return node, ast.unparse(node.test)
    return None, ""


for name in ("rank", "handle_check"):
    fn = funcs[name]
    guard, test = guard_for(fn)
    assert guard is not None, f"{name} never checks enrolment"
    # Compare statement nodes, not rendered text: unparsing the guard body and
    # unparsing the whole function format the same code differently, so string
    # subtraction silently leaves everything in place.
    inside = " ".join(ast.unparse(s) for s in guard.body)
    rest = " ".join(ast.unparse(s) for s in fn.body if s is not guard)
    negated = test.strip().startswith("not ")
    # However the test is written, the card must be reachable only for an
    # enrolled member and the ask only for everyone else.
    card_branch = rest if negated else inside
    ask_branch = inside if negated else rest
    assert "rank_embed" in card_branch, f"{name}: card is not behind the enrolment check"
    assert "ConsentView" in ask_branch, f"{name}: no consent ask on the un-enrolled path"
    assert "ConsentView" not in card_branch, f"{name}: asks an already-enrolled member"
    assert "STATE_PROMPTED" in ask_branch, f"{name}: doesn't record that they were asked"
    print(f"{name:13} enrolled -> card, otherwise -> consent  OK   (test: {test})")

# Roles are only ever touched for someone enrolled.
refresh = ast.unparse(funcs["refresh"])
# refresh delegates the work to recalculate(), so the gate must come first.
assert refresh.index("is_enrolled") < refresh.index("recalculate"), \
    "refresh does role work before checking enrolment"
print("refresh       gated on enrolment before touching roles  OK")

assert 'source="command"' in src and 'source="button"' in src
print("both entry points recorded with their own source  OK")
print("PASS")
