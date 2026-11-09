import asyncio
import unittest
from datetime import datetime, timezone
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
            created_at=datetime.now(timezone.utc),
            edited_at=None,
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

    async def test_wisdom_aliases_use_same_value_and_support_both_prefixes(self) -> None:
        with patch.object(self.bot.wisdom, "get_value", new_callable=AsyncMock) as get_value:
            get_value.return_value = 12.3456
            for content in (
                "i cast check wisdom",
                "i cast check wis",
                "i cast chwi",
                "cast check wis",
                "cast chwi",
                "I CAST CHECK WIS",
                "I CAST CHWI",
            ):
                with self.subTest(content=content):
                    self.send.reset_mock()
                    await self.invoke(content)
                    self.send.assert_awaited_once_with("Your wisdom is 12.346.")
                    get_value.assert_awaited_with(10, 1)

    async def test_wisdom_aliases_reject_dms(self) -> None:
        for content in ("i cast check wis", "i cast chwi"):
            with self.subTest(content=content):
                self.send.reset_mock()
                await self.invoke(content, guild=None)
                self.send.assert_awaited_once_with("Wisdom is only tracked inside a server.")

    async def test_wisdom_aliases_are_in_command_help(self) -> None:
        for content in ("i cast help check wisdom", "i cast help check wis", "i cast help chwi"):
            with self.subTest(content=content):
                self.channel.send.reset_mock()
                await self.invoke(content)
                self.assertIn("`check wis`, or `chwi`", self.channel.send.await_args.args[0])

    async def test_phrase_routing_prefers_longest_and_preserves_arguments(self) -> None:
        called = AsyncMock()

        @commands.command(name="route")
        async def route(ctx: commands.Context, *, text: str) -> None:
            await called("short", text)

        @commands.command(name="route target", aliases=["rt", "route to"])
        async def route_target(ctx: commands.Context, *, text: str) -> None:
            await called("long", text)

        self.bot.add_command(route)
        self.bot.add_command(route_target)
        for content, expected in (
            ("i cast route target The Wizard", ("long", "The Wizard")),
            ("i cast ROUTE\tTO  The Wizard", ("long", "The Wizard")),
            ("cast rt The Wizard", ("long", "The Wizard")),
            ("cast route targetable", ("short", "targetable")),
        ):
            with self.subTest(content=content):
                called.reset_mock()
                await self.invoke(content)
                called.assert_awaited_once_with(*expected)
        await self.invoke("cast route target")
        self.assertIn("Missing required argument", self.send.await_args.args[0])
        self.assertIs(self.bot.get_command("route target"), route_target)
        self.assertIs(self.bot.get_command("ROUTE TO"), route_target)
        self.bot.remove_command("route target")
        self.assertIsNone(self.bot.get_command("rt"))

    async def test_phrase_command_checks_are_enforced_for_aliases(self) -> None:
        called = AsyncMock()

        @commands.command(name="restricted action", aliases=["shortcut"])
        @commands.check(lambda ctx: False)
        async def restricted(ctx: commands.Context) -> None:
            await called()

        self.bot.add_command(restricted)
        for content in ("cast restricted action", "cast shortcut"):
            with self.subTest(content=content):
                self.send.reset_mock()
                await self.invoke(content)
                self.send.assert_awaited_once_with("You cannot use this command here.")
        called.assert_not_awaited()

    async def test_phrase_aliases_share_discord_cooldown(self) -> None:
        called = AsyncMock()

        @commands.command(name="limited action", aliases=["la"])
        @commands.cooldown(1, 60, commands.BucketType.user)
        async def limited(ctx: commands.Context) -> None:
            await called()

        self.bot.add_command(limited)
        await self.invoke("cast limited action")
        with self.assertLogs("wisest_wizard.errors", level="ERROR"):
            await self.invoke("cast la")
        called.assert_awaited_once()
        self.send.assert_awaited_once_with(
            "The command failed unexpectedly. The error has been logged."
        )

    async def test_normal_discord_groups_still_work(self) -> None:
        called = AsyncMock()

        @commands.group(name="test group", invoke_without_command=True)
        async def group(ctx: commands.Context) -> None:
            await called("group")

        @group.command(name="child")
        async def child(ctx: commands.Context, *, text: str) -> None:
            await called(text)

        self.bot.add_command(group)
        await self.invoke("cast test group child hello")
        called.assert_awaited_once_with("hello")
        self.assertIs(self.bot.get_command("test group child"), child)
        self.assertIsNone(self.bot.get_command("test group missing"))

    async def test_phrase_registration_rejects_bad_spacing_and_conflicts(self) -> None:
        @commands.command(name="bad  spacing")
        async def bad(ctx: commands.Context) -> None:
            pass

        @commands.command(name="another", aliases=["CHECK WIS"])
        async def conflict(ctx: commands.Context) -> None:
            pass

        with self.assertRaisesRegex(ValueError, "single spaces"):
            self.bot.add_command(bad)
        with self.assertRaises(commands.CommandRegistrationError):
            self.bot.add_command(conflict)
        self.assertIsNone(self.bot.get_command("another"))

    async def test_wisdom_phrases_point_to_one_command(self) -> None:
        command = self.bot.get_command("check wisdom")
        self.assertIsNotNone(command)
        self.assertIs(self.bot.get_command("check wis"), command)
        self.assertIs(self.bot.get_command("chwi"), command)
        self.assertIsNone(self.bot.get_command("check wisdomish"))
        await self.invoke("cast check wisdomish")
        self.send.assert_awaited_with("Check what? (The only available check right now is `wisdom`.)")

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
