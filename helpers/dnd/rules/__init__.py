"""
Rules layer — dice, resolution, and the rulesets themselves.

Pure and seeded: no I/O, no wall clock, no module-level ``random``. Everything
here is a function of its arguments, which is what makes a campaign replayable
and the whole simulation testable from a recorded event log.

This layer sits **below** ``world/``, so it deals in stat dictionaries rather
than entities. Importing the entity model here would invert the layering and
make a third ruleset impossible to add without touching the world.

Importing this package registers the built-in rulesets, so ``ruleset.get(key)``
works from anywhere without the caller knowing which modules exist.
"""

from helpers.dnd.rules import dice  # noqa: F401  (re-exported for convenience)
from helpers.dnd.rules.ruleset import (  # noqa: F401
    COST,
    DEGREES,
    FAIL,
    SUCCESS,
    TRIUMPH,
    Action,
    Outcome,
    Ruleset,
    all_rulesets,
    get,
    keys,
    register,
)

# Importing these for their registration side effect is the point — ``get()``
# can only answer for rulesets whose modules have been imported.
from helpers.dnd.rules import freeform as _freeform  # noqa: F401,E402
from helpers.dnd.rules import srd5e as _srd5e  # noqa: F401,E402
