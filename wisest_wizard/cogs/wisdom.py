from __future__ import annotations

import discord
from discord.ext import commands

from wisest_wizard.services.wisdom import WisdomService


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

    @commands.command(name="karma")
    async def karma(self, ctx: commands.Context) -> None:
        """Show the caller's current lazily-decayed wisdom."""
        if ctx.guild is None:
            await ctx.send("Wisdom is only tracked inside a server.")
            return
        value = await self.wisdom.get_value(ctx.guild.id, ctx.author.id)
        await ctx.send(f"Your wisdom is {value:.3f}.")

    @commands.command(name="rep")
    async def reputation(self, ctx: commands.Context, target: discord.Member) -> None:
        """Use `+rep @member` or `-rep @member` once per day."""
        if ctx.guild is None:
            await ctx.send("Reputation can only be given inside a server.")
            return
        content = ctx.message.content.lstrip().lower()
        if content.startswith("+rep"):
            direction = 1
        elif content.startswith("-rep"):
            direction = -1
        else:
            await ctx.send("Use `+rep @member` or `-rep @member`.")
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
            await ctx.send(f"{target.display_name} gained {result.amount:.3f} wisdom.")
        elif result.amount == 0:
            await ctx.send(f"{target.display_name} has no wisdom to remove.")
        else:
            await ctx.send(f"{target.display_name} lost {result.amount:.3f} wisdom.")


async def setup(bot: commands.Bot) -> None:
    wisdom = getattr(bot, "wisdom", None)
    if not isinstance(wisdom, WisdomService):
        raise RuntimeError("The bot must expose its initialized WisdomService before loading cogs.")
    await bot.add_cog(WisdomCog(wisdom))
