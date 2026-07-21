# Compatibility stub for the `waifuim` module.
#
# pet-normal.py does `from waifuim import WaifuAioClient` but never actually
# uses the symbol. The real package has no Python 3.8 release, so this stub
# just exposes a no-op WaifuAioClient so the import resolves. Replace with the
# real library if a cog starts using it.


class WaifuAioClient:
    """No-op placeholder. The bot imports this name but does not use it."""

    def __init__(self, *args, **kwargs):
        pass
