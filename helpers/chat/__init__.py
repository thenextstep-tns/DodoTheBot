"""
Dodo's chat mind — the cheap half of the personality.

Four modules, none of which call a language model:

* :mod:`state`    — what she knows and feels about one person, and how that rots
* :mod:`triggers` — per-server string listeners, with fatigue so a bit wears out
* :mod:`dial`     — how much flourish this particular reply is allowed
* :mod:`router`   — whether to answer at all, and whether it needs the model

The cog assembles a prompt from their output (:mod:`prompt`) and makes at most
one API call. Everything else is arithmetic.
"""
