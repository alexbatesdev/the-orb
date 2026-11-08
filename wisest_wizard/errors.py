from __future__ import annotations

import logging

from discord.ext import commands

from wisest_wizard.database import DatabaseError

logger = logging.getLogger(__name__)


async def handle_command_error(
    ctx: commands.Context, error: commands.CommandError
) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandInvokeError):
        error = error.original
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command can only be used in a server.")
        return
    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I do not have the Discord permissions needed to do that.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.")
        return
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You cannot use this command here.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: `{error.param.name}`.")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("I could not understand one of the command arguments.")
        return
    if isinstance(error, DatabaseError):
        logger.error(
            "Database error while handling command %s.",
            ctx.command,
            exc_info=(type(error), error, error.__traceback__),
        )
        await ctx.send("Persistence is temporarily unavailable; please try again later.")
        return
    if isinstance(error, commands.CommandError):
        await ctx.send(str(error))
        return
    logger.error(
        "Unexpected error in command %s by user %s.",
        ctx.command,
        ctx.author.id,
        exc_info=(type(error), error, error.__traceback__),
    )
    await ctx.send("The command failed unexpectedly. The error has been logged.")
