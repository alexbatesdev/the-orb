import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from discord.ext import commands

from wisest_wizard.app import WizardBot
from wisest_wizard.config import Settings
from wisest_wizard.database import Database, DatabaseError

_DEFAULT_GUILD = object()


def member(
    user_id: int, name: str, display_name: str | None = None, *, bot: bool = False
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        name=name,
        display_name=display_name or name,
        bot=bot,
    )


class CommandPhraseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(Path(":memory:"))
        self.bot = WizardBot(Settings("test-token", Path(":memory:"), None), self.database)
        await self.bot._async_setup_hook()
        await self.bot.setup_hook()
        self.bot._connection.user = SimpleNamespace(id=999, bot=True)
        self.author = member(1, "Giver")
        self.alex = member(2, "AlexBates", "The Wizard")
        self.sasha = member(3, "Sasha")
        self.bot_member = member(4, "HelperBot", bot=True)
        self.guild = SimpleNamespace(
            id=10,
            me=SimpleNamespace(id=999, display_name="Wizard"),
            chunked=True,
            members=[self.author, self.alex, self.sasha, self.bot_member],
            chunk=AsyncMock(),
        )
        self.guild.get_member = lambda member_id: next(
            (entry for entry in self.guild.members if entry.id == member_id), None
        )
        self.send = AsyncMock()
        self.channel = SimpleNamespace(send=AsyncMock())
        self.send_patch = patch.object(commands.Context, "send", self.send)
        self.send_patch.start()

    async def asyncTearDown(self) -> None:
        self.send_patch.stop()
        await self.bot.close()

    async def invoke(self, content: str, *, guild: object = _DEFAULT_GUILD) -> None:
        message = SimpleNamespace(
            content=content,
            author=self.author,
            guild=self.guild if guild is _DEFAULT_GUILD else guild,
            channel=self.channel,
            attachments=[],
            _state=self.bot._connection,
        )
        context = await self.bot.get_context(message)
        await self.bot.invoke(context)
        await asyncio.sleep(0)

    async def test_check_wisdom_and_existing_commands_use_real_parser(self) -> None:
        await self.invoke("i cast check wisdom")
        self.send.assert_awaited_with("Your wisdom is 0.000.")
        await self.invoke("I CAST CHECK WISDOM")
        self.send.assert_awaited_with("Your wisdom is 0.000.")
        await self.invoke("i cast hello")
        self.send.assert_awaited_with("Hello, Giver! ✨")
        await self.invoke("cast check wisdom")
        self.send.assert_awaited_with("Your wisdom is 0.000.")

    async def test_cast_rep_resolves_partial_name_and_shares_cooldown(self) -> None:
        await self.invoke("i cast +rep alex")
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 1)
        await self.invoke("i cast -rep sasha")
        self.assertIn("give reputation again", self.send.await_args.args[0])
        self.assertEqual(await self.bot.wisdom.get_value(10, 3), 0)

    async def test_negative_rep(self) -> None:
        await self.bot.wisdom.change_reputation(10, 5, 2, 1)
        await self.invoke("i cast -rep the wiz")
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 0)

    async def test_translated_reputation_results(self) -> None:
        await self.invoke("i cast +rep alex")
        self.assertEqual(self.send.await_args.args[0], "The Wizard gained 1.000 wisdom.")
        self.author = member(6, "Other")
        await self.invoke("i cast -rep alex")
        self.assertEqual(self.send.await_args.args[0], "The Wizard lost 1.000 wisdom.")
        self.author = member(7, "Third")
        await self.invoke("i cast -rep alex")
        self.assertEqual(self.send.await_args.args[0], "The Wizard has no wisdom to remove.")

    async def test_translated_check_and_health_messages(self) -> None:
        await self.invoke("i cast check")
        self.send.assert_awaited_with("Check what? (The only available check right now is `wisdom`.)")
        await self.invoke("i cast health")
        self.send.assert_awaited_with("The wizard is awake; persistence is ready.")
        with patch.object(self.database, "ping", side_effect=DatabaseError("test")):
            with self.assertLogs("wisest_wizard.cogs.core", level="ERROR"):
                await self.invoke("i cast health")
        self.send.assert_awaited_with("The bot is online, but persistence is unavailable.")

    async def test_old_command_forms_do_not_invoke_commands(self) -> None:
        for content in ("cast karma", "i cast karma", "+rep AlexBates", "-rep AlexBates"):
            with self.subTest(content=content):
                self.send.reset_mock()
                await self.invoke(content)
                self.send.assert_not_awaited()
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 0)

    async def test_exact_name_precedes_partial_and_matching_is_case_insensitive(self) -> None:
        self.guild.members.append(member(7, "Alex"))
        await self.invoke("I CAST +REP aLeX")
        self.assertEqual(await self.bot.wisdom.get_value(10, 7), 1)
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 0)

    async def test_ambiguous_missing_self_and_bot_targets_do_not_consume_cooldown(self) -> None:
        self.guild.members.append(member(7, "Alexandria"))
        await self.invoke("i cast +rep alex")
        self.assertIn("multiple server members", self.send.await_args.args[0])
        await self.invoke("i cast +rep notfound")
        self.assertIn("No server member matched", self.send.await_args.args[0])
        await self.invoke("i cast +rep giver")
        self.assertIn("yourself", self.send.await_args.args[0])
        await self.invoke("i cast +rep helper")
        self.assertIn("a bot", self.send.await_args.args[0])
        await self.invoke("i cast +rep sasha")
        self.assertEqual(await self.bot.wisdom.get_value(10, 3), 1)

    async def test_user_id_and_member_chunking(self) -> None:
        self.guild.chunked = False
        await self.invoke("i cast +rep 2")
        self.guild.chunk.assert_awaited_once_with(cache=True)
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 1)

    async def test_display_name_with_spaces_and_mention(self) -> None:
        await self.invoke("i cast +rep The Wizard")
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 1)
        self.author = member(6, "Other")
        await self.invoke("i cast +rep <@2>")
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 2)

    async def test_dms_and_missing_arguments_are_rejected(self) -> None:
        await self.invoke("i cast check wisdom", guild=None)
        self.assertIn("only tracked inside a server", self.send.await_args.args[0])
        await self.invoke("i cast +rep alex", guild=None)
        self.assertIn("only be given inside a server", self.send.await_args.args[0])
        await self.invoke("i cast +rep")
        self.assertIn("Missing required argument", self.send.await_args.args[0])
        self.assertEqual(await self.bot.wisdom.get_value(10, 2), 0)

    async def test_help_uses_catalog_for_descriptions_and_generated_text(self) -> None:
        await self.invoke("i cast help")
        page = self.channel.send.await_args.args[0]
        self.assertIn("Shows this message", page)
        self.assertIn("Check wizard information.", page)
        self.assertIn("Type i cast help command for more info on a command.", page)
        self.channel.send.reset_mock()
        await self.invoke("i cast help +rep")
        page = self.channel.send.await_args.args[0]
        self.assertIn("Give reputation with `i cast +rep username`.", page)
        self.assertIn("Arguments:", page)
        self.assertIn("No description given", page)

    async def test_help_lookup_errors_use_catalog(self) -> None:
        for content, expected in (
            ("i cast help unknown", 'No command called "unknown" found.'),
            ("i cast help check unknown", 'Command "check" has no subcommand named unknown'),
            ("i cast help hello unknown", 'Command "hello" has no subcommands.'),
        ):
            with self.subTest(content=content):
                self.channel.send.reset_mock()
                await self.invoke(content)
                self.assertIn(expected, self.channel.send.await_args.args[0])
