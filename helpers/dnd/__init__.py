"""
Dodo Tabletop — the living-world tabletop engine.

The design lives in ``docs/dnd/``; read ``README.md`` there before changing
anything in this package, and ``14-CONVENTIONS.md`` before writing code.

The one idea everything else follows from: **the world is a deterministic
simulation, and a language model is only ever a translator at the edges.**
Nothing a model says is true until the simulation says it is. That is why the
layers below are pure, seeded and synchronous, and why the game is fully
playable with no model reachable at all.

Layering (each may import only from layers below it)::

    surfaces      cogs/dnd/, web/dnd/
    orchestration session, turn, tick
    narrative     narrative/            (P5)
    minds         mind/                 (P2-P3)
    world         world/
    rules         rules/
    storage       store/

``llm/`` (P4) is a leaf service: called by orchestration, never imported by
``world/``, ``rules/``, ``mind/`` or ``store/``.
"""
