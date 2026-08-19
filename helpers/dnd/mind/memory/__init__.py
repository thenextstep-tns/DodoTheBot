"""
The memory subsystem.

Split by verb rather than by tier, because the tiers share their machinery and
the verbs do not:

    salience.py     how much a memory matters — drives everything else
    encode.py       forming one, from one witness's point of view
    decay.py        field-wise degradation, confabulation, imprint promotion
    recall.py       cue-triggered retrieval, and rewriting on recall
    consolidate.py  working -> mid -> long, budgets, pruning

The model itself is ``helpers/dnd/world/memory.py`` — it is persisted state, and
``store/`` sits below this layer.
"""

from helpers.dnd.mind.memory import (  # noqa: F401
    consolidate,
    decay,
    encode,
    recall,
    salience,
)
