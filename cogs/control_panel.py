"""
Control-panel cog — runs the aiohttp web panel inside the bot process.

Starting the server here (rather than as a separate service) lets the panel call
``bot.reload_extension`` and the visibility manager directly on the bot's event
loop. The server is started in ``cog_load`` and torn down in ``cog_unload`` so
``/reload control_panel`` cleanly restarts it. It is a no-op unless the ``web``
block in ``config.json`` sets ``enabled: true`` and provides the OAuth secrets.
"""

from aiohttp import web
from discord.ext import commands

from config.secrets import (
    WEB_CLIENT_SECRET,
    WEB_ENABLED,
    WEB_HOST,
    WEB_PORT,
    WEB_PUBLIC_URL,
    WEB_SESSION_SECRET,
)
from web.routes import create_app


class ControlPanel(commands.Cog, name="control_panel"):
    """Owns the lifecycle of the in-process control-panel web server."""

    def __init__(self, bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    async def cog_load(self) -> None:
        if not WEB_ENABLED:
            self.bot.logger.info("Control panel disabled (config web.enabled is false); not starting.")
            return
        if not WEB_SESSION_SECRET or not WEB_CLIENT_SECRET:
            self.bot.logger.warning(
                "Control panel enabled but web.session_secret / web.client_secret are missing; not starting."
            )
            return
        app = create_app(self.bot)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, WEB_HOST, WEB_PORT)
        await self.site.start()
        self.bot.logger.info(f"Control panel listening on {WEB_HOST}:{WEB_PORT} (public: {WEB_PUBLIC_URL}).")

    async def cog_unload(self) -> None:
        if self.site is not None:
            await self.site.stop()
            self.site = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
        self.bot.logger.info("Control panel stopped.")


async def setup(bot):
    await bot.add_cog(ControlPanel(bot))
