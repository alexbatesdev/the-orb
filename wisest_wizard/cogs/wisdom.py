from __future__ import annotations

import re

import discord
from discord.ext import commands

from wisest_wizard.services.wisdom import WisdomService


async def find_member(guild: discord.Guild, query: str) -> discord.Member:
    if not guild.chunked:
        await guild.chunk(cache=True)

    match = re.fullmatch(r"<@!?(\d+)>|(\d+)", query)
    if match:
        member = guild.get_member(int(match.group(1) or match.group(2)))
        if member is None:
            raise commands.BadArgument("No server member matched that user ID or mention.")
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
        raise commands.BadArgument("No server member matched that name.")
    if len(matches) > 1:
        raise commands.BadArgument(
            "That name matches multiple server members; use a more specific name or user ID."
        )
    return matches[0]


class WisdomCog(commands.Cog):
    def __init__(self, wisdom: WisdomService) -> None:
        self.wisdom = wisdom

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        await self.wisdom.process_message(
            message.guild.id,
            message.author.id,
            message.content,
        )

    @commands.group(name="check", invoke_without_command=True, case_insensitive=True)
    async def check(self, ctx: commands.Context) -> None:
        """Check wizard information."""
        await ctx.send("Check what? (The only available check right now is `wisdom`.)")

    @check.command(name="wisdom")
    async def check_wisdom(self, ctx: commands.Context) -> None:
        """Show the caller's current lazily-decayed wisdom."""
        if ctx.guild is None:
            await ctx.send("Wisdom is only tracked inside a server.")
            return
        value = await self.wisdom.get_value(ctx.guild.id, ctx.author.id)
        await ctx.send(f"Your wisdom is {value:.3f}.")

    async def _change_reputation(
        self, ctx: commands.Context, direction: int, target_query: str
    ) -> None:
        if ctx.guild is None:
            await ctx.send("Reputation can only be given inside a server.")
            return
        target_query = target_query.strip()
        if not target_query:
            await ctx.send("Provide a server member's username or user ID.")
            return
        try:
            target = await find_member(ctx.guild, target_query)
        except commands.BadArgument as error:
            await ctx.send(str(error))
            return
        if target.bot:
            await ctx.send("You cannot give reputation to a bot.")
            return
        if target.id == ctx.author.id:
            await ctx.send("You cannot give reputation to yourself.")
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
                f"You can give reputation again in {result.retry_after:.1f} seconds."
            )
            return
        if direction > 0:
            response = f"{target.display_name} gained {result.amount:.3f} wisdom."
        elif result.amount == 0:
            response = f"{target.display_name} has no wisdom to remove."
        else:
            response = f"{target.display_name} lost {result.amount:.3f} wisdom."
        await ctx.send(response, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="+rep")
    async def positive_reputation(
        self, ctx: commands.Context, *, target: str
    ) -> None:
        """Give reputation with `i cast +rep username`."""
        await self._change_reputation(ctx, 1, target)

    @commands.command(name="-rep")
    async def negative_reputation(
        self, ctx: commands.Context, *, target: str
    ) -> None:
        """Remove reputation with `i cast -rep username`."""
        await self._change_reputation(ctx, -1, target)

async def setup(bot: commands.Bot) -> None:
    wisdom = getattr(bot, "wisdom", None)
    if not isinstance(wisdom, WisdomService):
        raise RuntimeError("The bot must expose its initialized WisdomService before loading cogs.")
    await bot.add_cog(WisdomCog(wisdom))
