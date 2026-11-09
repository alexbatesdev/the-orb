from __future__ import annotations

import logging

from discord.ext import commands

from wisest_wizard.database import DatabaseError
from wisest_wizard.i18n import translate

logger = logging.getLogger(__name__)


async def handle_command_error(
    ctx: commands.Context, error: commands.CommandError
) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandInvokeError):
        error = error.original
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send(translate("errors.server_only"))
        return
    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send(translate("errors.bot_permissions"))
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(translate("errors.user_permissions"))
        return
    if isinstance(error, commands.CheckFailure):
        await ctx.send(translate("errors.check_failed"))
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(translate("errors.missing_argument", name=error.param.name))
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send(translate("errors.bad_argument"))
        return
    if isinstance(error, DatabaseError):
        logger.error(
            "Database error while handling command %s.",
            ctx.command,
            exc_info=(type(error), error, error.__traceback__),
        )
        await ctx.send(translate("errors.database"))
        return
    logger.error(
        "Unexpected error in command %s by user %s.",
        ctx.command,
        ctx.author.id,
        exc_info=(type(error), error, error.__traceback__),
    )
    await ctx.send(translate("errors.unexpected"))
