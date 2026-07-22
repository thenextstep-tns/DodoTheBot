"""
Backwards-compatible configuration shim.

The configuration used to live entirely in this file. It has since been split
into the ``config`` package:

    config.secrets    - tokens / connection strings (loaded from config.json)
    config.database   - MongoDB client and collection handles
    config.constants  - embed colours, statuses, gameplay tuning, GIF/quote pools
    config.guild      - per-guild channel IDs, role IDs and autoban settings

Every cog still imports ``config_py`` and reads e.g. ``config_py.collection`` or
``config_py.main_color``, so this module simply re-exports everything from the
new package to keep those references working. New code should import from the
``config`` sub-modules directly.
"""

from config.secrets import *      # noqa: F401,F403  (MONGO_URI, OPENAI_API, PROXY_API, tenor_api, ...)
from config.database import *     # noqa: F401,F403  (client, db, collection, wallets, ...)
from config.constants import *    # noqa: F401,F403  (main_color, statuses, catclasses, ...)
from config.guild import *        # noqa: F401,F403  (channel IDs, role IDs, reaction_roles, ...)
