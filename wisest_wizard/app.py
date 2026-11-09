from __future__ import annotations

import asyncio
import logging

import aiosqlite
import discord
from discord.ext import commands

from wisest_wizard.config import Settings, load_settings
from wisest_wizard.database import Database
from wisest_wizard.errors import handle_command_error
from wisest_wizard.help import WizardHelpCommand
from wisest_wizard.logging_config import configure_logging
from wisest_wizard.services.audit import AuditService
from wisest_wizard.services.cooldowns import PersistentCooldowns
from wisest_wizard.services.scheduler import ScheduledEffects
from wisest_wizard.services.wisdom import WisdomRewardService, WisdomService

logger = logging.getLogger(__name__)
PREFIXES = ("i cast ", "cast ")


def get_prefix(bot: commands.Bot, message: discord.Message) -> str | tuple[str, ...]:
    content = message.content
    for prefix in PREFIXES:
        if content.lower().startswith(prefix):
            return content[: len(prefix)]
    return PREFIXES


class WizardBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            case_insensitive=True,
            help_command=WizardHelpCommand(),
        )
        self.settings = settings
        self.database = database
        self.cooldowns = PersistentCooldowns(database)
        self.audit = AuditService(database, settings.audit_retention_days)
        self.scheduled_effects = ScheduledEffects(database)
        self.wisdom = WisdomService(database, settings.wisdom, self.cooldowns)
        self.wisdom_rewards = WisdomRewardService(self.wisdom)
        self._audit_cleanup_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        await self.database.open()
        await self.database.migrate()
        if self.settings.audit_retention_days is not None:
            await self.audit.purge_expired()
            self._audit_cleanup_task = asyncio.create_task(
                self._audit_cleanup_loop(), name="audit-retention-cleanup"
            )
        await self.load_extension("wisest_wizard.cogs.core")
        await self.load_extension("wisest_wizard.cogs.wisdom")
        recovered = await self.scheduled_effects.recover_in_flight()
        if recovered:
            logger.warning("Recovered %s interrupted scheduled effects.", recovered)
        await self.scheduled_effects.start()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (id=%s)", self.user, self.user.id if self.user else None)

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        await handle_command_error(ctx, error)

    async def close(self) -> None:
        if self._audit_cleanup_task is not None:
            self._audit_cleanup_task.cancel()
            try:
                await self._audit_cleanup_task
            except asyncio.CancelledError:
                pass
            self._audit_cleanup_task = None
        await self.scheduled_effects.close()
        await super().close()
        await self.database.close()

    async def _audit_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                await self.audit.purge_expired()
            except aiosqlite.Error:
                logger.exception("Audit-retention cleanup failed.")


async def main() -> None:
    configure_logging()
    settings = load_settings()
    database = Database(settings.database_path)
    bot = WizardBot(settings, database)
    try:
        await bot.start(settings.discord_token)
    finally:
        await bot.close()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested.")
