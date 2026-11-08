from __future__ import annotations

import logging

from discord.ext import commands

from wisest_wizard.database import Database, DatabaseError

logger = logging.getLogger(__name__)


class CoreCog(commands.Cog):
    def __init__(self, database: Database) -> None:
        self.database = database

    @commands.command(name="hello")
    async def hello(self, ctx: commands.Context) -> None:
        """Usage: `cast hello` or `i cast hello`"""
        await ctx.send(f"Hello, {ctx.author.display_name}! ✨")

    @commands.command(name="health")
    async def health(self, ctx: commands.Context) -> None:
        """Report whether the bot and its persistence layer are ready."""
        try:
            await self.database.ping()
        except DatabaseError:
            logger.exception("Public health check found persistence unavailable.")
            await ctx.send("The bot is online, but persistence is unavailable.")
            return
        await ctx.send("The wizard is awake; persistence is ready.")


async def setup(bot: commands.Bot) -> None:
    database = getattr(bot, "database", None)
    if not isinstance(database, Database):
        raise RuntimeError("The bot must expose its initialized Database before loading cogs.")
    await bot.add_cog(CoreCog(database))
