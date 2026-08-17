"""A scoring-role change must always leave a trace, whichever way it goes."""
import ast, pathlib, sys
import pathlib as _pathlib, sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[2]))
src = pathlib.Path("cogs/trial_ranks.py").read_text(encoding="utf-8")
fn = next(n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_member_update")
body = ast.unparse(fn)

# The enrolment test must come *after* the scoring test: checking it first meant
# a role change on someone unenrolled returned before anything could say so.
at_scoring = body.index("changed & scoring")
at_enrolled = body.index("is_enrolled")
print("scoring test @", at_scoring, "| enrolment test @", at_enrolled)
assert at_scoring < at_enrolled, "enrolment is checked before we know it's relevant"

# Skipping someone is reported, not silent.
assert "not on automatic ranking" in body or "automatic ranking" in body
assert "context='skipped'" in body or 'context="skipped"' in body

# The recalculation log is unconditional now.
assert "Trial ranks: recalculated" in body
gated = [n for n in ast.walk(fn) if isinstance(n, ast.If)
         and "granted" in ast.unparse(n.test) and "log_event" in ast.unparse(n)]
assert not gated, "the log is still behind a 'something changed' condition"
assert "(unchanged)" in body, "a no-move recalculation must still say so"
print("recalculation logged unconditionally, including no-change")

# The names of the roles that moved travel into both messages.
assert body.count("touched") >= 3, "the changed role names should appear in the log"
# The master switch is now checked *after* relevance, so a scoring role moving
# while the feature is off produces an explanation rather than nothing. This is
# the case that actually bit: enabled was False and every change vanished.
assert "why_not_running" in body, "the listener must explain an inert feature"
at_stop = body.index("why_not_running")
assert at_scoring < at_stop, "the switch is checked before we know the change matters"
assert body.index("Nothing was recalculated") > at_stop
src_all = pathlib.Path("cogs/trial_ranks.py").read_text(encoding="utf-8")
# Enrolment is the only switch: no feature flag may gate the runtime.
assert "switched **off** for this server" not in src_all
assert 'get(guild.id).get("enabled")' not in src_all,     "a master enabled flag must not gate the automation"
assert "the **trial_ranks** cog is disabled" in src_all, "the cog toggle is still honoured"
print("enrolment is the only switch; the cog toggle still explains itself")
print("PASS")
