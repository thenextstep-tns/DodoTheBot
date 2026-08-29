"""
Dodo Tabletop — Discord surface package.

The cog itself lives in ``cog.py`` rather than here on purpose: ``load_all_cogs``
in ``bot.py`` walks ``cogs/`` and skips any filename starting with ``__``, so a
``setup`` defined in this file would never be loaded. ``embeds.py`` and
``context.py`` have no ``setup`` and are skipped quietly as plain modules, which
is the documented behaviour of that loader.
"""
