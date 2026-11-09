from __future__ import annotations

from discord.ext import commands

from wisest_wizard.i18n import translate


async def require_guild(ctx: commands.Context) -> int:
    if ctx.guild is None:
        raise commands.NoPrivateMessage(translate("errors.server_only"))
    return ctx.guild.id


def has_guild_permissions(**permissions: bool) -> commands.Check[commands.Context]:
    return commands.has_guild_permissions(**permissions)


def bot_has_guild_permissions(**permissions: bool) -> commands.Check[commands.Context]:
    return commands.bot_has_guild_permissions(**permissions)
