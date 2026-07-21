# Compatibility stub for the local `cat` module.
#
# The bot's cogs carry a leftover top-level `import cat`, but every actual
# `cat.get(...)` call in the cogs operates on a cat *record* (a dict from the
# database), not on this module — so nothing here is invoked at runtime.
# This stub only exists so `import cat` resolves. If your working server has a
# real cat.py with used functionality, drop it in here to replace this file.
