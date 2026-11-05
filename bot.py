import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

PREFIXES = ("i cast ", "cast ")


def get_prefix(bot: commands.Bot, message: discord.Message):
    # Case-insensitive match; return the actual text typed so discord.py strips it correctly.
    content = message.content
    for prefix in PREFIXES:
        if content.lower().startswith(prefix):
            return content[: len(prefix)]
    return PREFIXES


intents = discord.Intents.default()
intents.message_content = True  # must also be enabled in the Developer Portal

bot = commands.Bot(command_prefix=get_prefix, intents=intents, case_insensitive=True)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.command(name="hello")
async def hello(ctx: commands.Context):
    """Usage: `cast hello` or `i cast hello`"""
    await ctx.send(f"Hello, {ctx.author.display_name}! ✨")


bot.run(os.environ["DISCORD_TOKEN"])
