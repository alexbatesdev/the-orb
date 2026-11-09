from __future__ import annotations

import re

import discord
from discord.ext import commands

from wisest_wizard.duration import format_duration
from wisest_wizard.i18n import translate
from wisest_wizard.services.wisdom import WisdomService


async def find_member(guild: discord.Guild, query: str) -> discord.Member:
    if not guild.chunked:
        await guild.chunk(cache=True)

    match = re.fullmatch(r"<@!?(\d+)>|(\d+)", query)
    if match:
        member = guild.get_member(int(match.group(1) or match.group(2)))
        if member is None:
            raise commands.BadArgument(translate("wisdom.member.id_not_found"))
        return member

    needle = query.casefold()
    members = guild.members
    exact = [
        member
        for member in members
        if needle in {member.name.casefold(), member.display_name.casefold()}
    ]
    matches = exact or [
        member
        for member in members
        if needle in member.name.casefold() or needle in member.display_name.casefold()
    ]
    if not matches:
        raise commands.BadArgument(translate("wisdom.member.name_not_found"))
    if len(matches) > 1:
        raise commands.BadArgument(translate("wisdom.member.ambiguous"))
    return matches[0]


class WisdomCog(commands.Cog, name=translate("help.category.wisdom")):
    def __init__(
        self, wisdom: WisdomService, check_command: commands.Group
    ) -> None:
        self.wisdom = wisdom
        self.check_command = check_command
        self.check_wisdom_command = commands.Command(
            WisdomCog.check_wisdom,
            name="wisdom",
            aliases=["wis"],
            case_insensitive=True,
            help=translate("help.check_wisdom"),
        )
        self.check_wisdom_command.cog = self

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        await self.wisdom.process_message(
            message.guild.id,
            message.author.id,
            message.content,
        )

    async def cog_load(self) -> None:
        self.check_command.add_command(self.check_wisdom_command)

    def cog_unload(self) -> None:
        self.check_command.remove_command(self.check_wisdom_command.name)

    async def check_wisdom(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send(translate("wisdom.check.server_only"))
            return
        value = await self.wisdom.get_value(ctx.guild.id, ctx.author.id)
        await ctx.send(translate("wisdom.check.value", value=value))

    async def _change_reputation(
        self, ctx: commands.Context, direction: int, target_query: str
    ) -> None:
        if ctx.guild is None:
            await ctx.send(translate("wisdom.rep.server_only"))
            return
        target_query = target_query.strip()
        if not target_query:
            await ctx.send(translate("wisdom.rep.target_required"))
            return
        try:
            target = await find_member(ctx.guild, target_query)
        except commands.BadArgument as error:
            await ctx.send(str(error))
            return
        if target.bot:
            await ctx.send(translate("wisdom.rep.bot"))
            return
        if target.id == ctx.author.id:
            await ctx.send(translate("wisdom.rep.self"))
            return

        result = await self.wisdom.change_reputation(
            ctx.guild.id,
            ctx.author.id,
            target.id,
            direction,
            recipient_is_bot=target.bot,
        )
        if result.reason == "cooldown":
            await ctx.send(
                translate("wisdom.rep.cooldown", duration=format_duration(result.retry_after))
            )
            return
        if direction > 0:
            response = translate("wisdom.rep.gained", name=target.display_name, amount=result.amount)
        elif result.amount == 0:
            response = translate("wisdom.rep.empty", name=target.display_name)
        else:
            response = translate("wisdom.rep.lost", name=target.display_name, amount=result.amount)
        await ctx.send(response, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="+rep", help=translate("help.positive_rep"))
    async def positive_reputation(
        self, ctx: commands.Context, *, target: str
    ) -> None:
        await self._change_reputation(ctx, 1, target)

    @commands.command(name="-rep", help=translate("help.negative_rep"))
    async def negative_reputation(
        self, ctx: commands.Context, *, target: str
    ) -> None:
        await self._change_reputation(ctx, -1, target)

async def setup(bot: commands.Bot) -> None:
    wisdom = getattr(bot, "wisdom", None)
    if not isinstance(wisdom, WisdomService):
        raise RuntimeError("The bot must expose its initialized WisdomService before loading cogs.")
    check_command = bot.get_command("check")
    if not isinstance(check_command, commands.Group):
        raise RuntimeError("The Core check command must be loaded before the Wisdom cog.")
    await bot.add_cog(WisdomCog(wisdom, check_command))
