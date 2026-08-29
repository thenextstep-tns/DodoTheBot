"""
DodoLand — the socialite tribe's town map.

The design conversation lives in ``docs/DODOLAND.md``. The one idea everything
else follows from: **a town is a profile, not a ladder.** A socialite's reward is
being seen by other people, so the whole system optimises for the glance, the
screenshot and the neighbour, not for a number going up.

Three consequences that shape every module here:

* **Reach, not volume.** What is counted is how many *different* people you
  reached and who reached back, never how much you posted. Volume metrics
  crown the loudest person in the server; a socialite is the one who talks to
  the most people. See :mod:`helpers.dodoland.metrics`.
* **Every act is capped per partner per day.** Two friends reacting to each
  other all evening is the obvious exploit, and the only defence that actually
  works is refusing to score the repetition. The caps are parameters, and the
  pair rows they are enforced from are also the social graph the map places
  neighbours with, so the anti-farm data and the fun data are the same data.
* **Nothing is ever taken away.** There is no decay anywhere in this package.
  Dormancy is a *view* (a town is drawn lit or dim from its recent window), so
  a fortnight away costs you brightness and never progress.

**Multiserver from the first write.** Every document carries ``guild_id`` and
every store call demands one; :mod:`helpers.dodoland.store` raises rather than
running an unscoped query. Continents do not join up: nothing here reads one
guild's rows to answer a question about another, and nothing publishes which
other servers a person is in.

Layering (each may import only from layers below it)::

    surfaces    cogs/dodoland.py, web/dodoland/
    scoring     standing.py            (P1)
    storage     store.py
    definition  metrics.py, parameters.py
"""
