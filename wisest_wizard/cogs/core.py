from __future__ import annotations

import logging

from discord.ext import commands

from wisest_wizard.database import Database, DatabaseError
from wisest_wizard.i18n import translate

logger = logging.getLogger(__name__)


class CoreCog(commands.Cog, name=translate("help.category.core")):
    def __init__(self, database: Database) -> None:
        self.database = database

    @commands.group(
        name="check",
        invoke_without_command=True,
        case_insensitive=True,
        help=translate("help.check"),
    )
    async def check(self, ctx: commands.Context) -> None:
        await ctx.send(
            translate("core.check.prompt", prefix=ctx.clean_prefix)
        )

    @commands.command(name="hello", help=translate("help.hello"))
    async def hello(self, ctx: commands.Context) -> None:
        await ctx.send(translate("core.hello", name=ctx.author.display_name))

    @commands.command(name="health", help=translate("help.health"))
    async def health(self, ctx: commands.Context) -> None:
        try:
            await self.database.ping()
        except DatabaseError:
            logger.exception("Public health check found persistence unavailable.")
            await ctx.send(translate("core.health.unavailable"))
            return
        await ctx.send(translate("core.health.ready"))


async def setup(bot: commands.Bot) -> None:
    database = getattr(bot, "database", None)
    if not isinstance(database, Database):
        raise RuntimeError("The bot must expose its initialized Database before loading cogs.")
    await bot.add_cog(CoreCog(database))
