"""
Minds — traits, needs, memory and relationships.

The layer that makes NPCs people rather than statblocks. Everything here is
**pure and deterministic**: functions of their arguments and an injected RNG, no
I/O, no wall clock, no language model. That is what lets a campaign replay
exactly and what lets the whole of it be tested without a database.

Layering (``docs/dnd/01-ARCHITECTURE.md`` section 1): ``mind/`` may import
``world/``, ``rules/`` and ``store/``. It must never import ``narrative/`` or
``llm/`` — a mind that needed a model to remember something would put the model
back on the critical path, which is the one thing this design refuses.

Reading order, if you are new to it: ``memory/salience.py`` (the master value),
then ``memory/encode.py`` (why two witnesses differ), then ``memory/decay.py``
(why memories rot rather than vanish).
"""

from helpers.dnd.mind import needs, relationships, traits  # noqa: F401
from helpers.dnd.mind.needs import Impulse, Needs  # noqa: F401
from helpers.dnd.mind.traits import Traits, derive_traits  # noqa: F401
