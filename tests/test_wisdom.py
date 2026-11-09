import asyncio
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path
from unittest.mock import patch

from wisest_wizard.config import WisdomSettings
from wisest_wizard.cogs.wisdom import WisdomCog
from wisest_wizard.database import Database
from wisest_wizard.scoring import (
    check_32_character_groups,
    check_leading_capital,
    check_punctuation,
    check_repeated_letters,
    check_run_on,
    check_space_ratio,
    check_trigrams,
    get_all_trigrams,
    load_trigrams,
    quality,
    raw_score,
)
from wisest_wizard.services.cooldowns import PersistentCooldowns
from wisest_wizard.services.events import (
    InteractionEvent,
    InteractionEventType,
    InteractionSource,
)
from wisest_wizard.services.wisdom import WisdomRewardService, WisdomService


class ScoringTests(unittest.TestCase):
    def test_punctuation_rules(self) -> None:
        self.assertEqual(check_punctuation("Hi. Abc"), 10)
        self.assertEqual(check_punctuation("Hi. abc"), -10)
        self.assertEqual(check_punctuation("Hi."), 20)
        self.assertEqual(check_punctuation("Hi. A"), 0)
        self.assertEqual(check_punctuation("Hi!"), 20)

    def test_trigram_extraction_and_bug_compatible_lookup(self) -> None:
        self.assertEqual(get_all_trigrams("a bc def"), ("a b", "bc ", "def"))
        table = ("~C~", "zz", "~D~", "at", "og")
        self.assertEqual(check_trigrams("Cat Dog", table), 6)
        self.assertEqual(check_trigrams("1cat", table), 0)
        self.assertEqual(check_trigrams("Cat", ("~C~\r", "at\r")), 3)
        self.assertEqual(check_trigrams("Cat", ("~C~", "at")), 3)
        self.assertEqual(check_trigrams("a Cat", table), 3)

    def test_trigram_loader_handles_line_endings_and_real_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trigrams.txt"
            path.write_bytes(b"~A~\r\nbc\r\n")
            self.assertEqual(load_trigrams(path), ("~A~", "bc"))
        self.assertIn("~A~", load_trigrams())
        self.assertIn("~~~", load_trigrams())

    def test_leading_capital_and_empty_text(self) -> None:
        self.assertEqual(check_leading_capital("  Apple"), 20)
        self.assertEqual(check_leading_capital(" apple"), -10)
        self.assertEqual(check_leading_capital(" \t"), 0)
        self.assertEqual(check_leading_capital("\N{NO-BREAK SPACE}Apple"), 20)

    def test_repeated_letters_ignore_spaces_and_only_match_ascii_letters(self) -> None:
        self.assertEqual(check_repeated_letters("A A A"), -50)
        self.assertEqual(check_repeated_letters("ABBA"), 0)
        self.assertEqual(check_repeated_letters("💚💚💚"), 0)

    def test_space_ratio_including_empty_and_all_space_inputs(self) -> None:
        self.assertEqual(check_space_ratio("A    B"), 20)
        self.assertEqual(check_space_ratio("AB"), -20)
        self.assertEqual(check_space_ratio("    "), -20)
        self.assertEqual(check_space_ratio(""), -20)

    def test_run_on_at_75_character_boundary(self) -> None:
        self.assertEqual(check_run_on("A" * 74), 0)
        self.assertEqual(check_run_on("A" * 75), -150)
        self.assertEqual(check_run_on("A" * 74 + "."), 0)
        self.assertEqual(check_run_on("A" * 75 + "."), -150)

    def test_32_character_groups(self) -> None:
        self.assertEqual(check_32_character_groups("A" * 31), 0)
        self.assertEqual(check_32_character_groups("A" * 32), -20)
        self.assertEqual(check_32_character_groups("A" * 64), -40)
        self.assertEqual(
            check_32_character_groups("A" * 31 + " " + "A" * 8 + " " + "A" * 23),
            0,
        )

    def test_raw_score_truncates_input(self) -> None:
        text = "A" * 192 + "!"
        self.assertEqual(raw_score(text), raw_score(text[:192]))
        self.assertEqual(raw_score("A" * 8 + "!", max_chars=8), raw_score("A" * 8, max_chars=8))
        self.assertEqual(raw_score("Hello."), 23)
        self.assertEqual(raw_score("hello."), -7)
        self.assertEqual(raw_score(""), -20)

    def test_quality_clamps_and_applies_curve(self) -> None:
        settings = WisdomSettings(score_floor=0, score_ceil=100, quality_curve=2)
        self.assertEqual(quality(-1, settings), 0)
        self.assertEqual(quality(0, settings), 0)
        self.assertEqual(quality(50, settings), 0.25)
        self.assertEqual(quality(100, settings), 1)
        self.assertEqual(quality(101, settings), 1)


class WisdomServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "wisdom.sqlite3")
        await self.database.open()
        await self.database.migrate()
        self.settings = WisdomSettings(
            message_cooldown_seconds=30,
            gain=1,
            grace_days=1,
            decay_per_day=0.5,
            reputation_cooldown_seconds=86400,
            reputation_change=1,
            reward_cooldown_seconds=86400,
            reward_gain=0.5,
        )
        self.cooldowns = PersistentCooldowns(self.database)
        self.wisdom = WisdomService(self.database, self.settings, self.cooldowns)
        self.rewards = WisdomRewardService(self.wisdom)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_empty_read_does_not_create_a_wisdom_row(self) -> None:
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100), 0)
        row = await self.database.fetch_one("SELECT COUNT(*) AS count FROM wisdom")
        self.assertEqual(row["count"], 0)

    async def test_zero_quality_does_not_consume_message_cooldown(self) -> None:
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=0):
            rejected = await self.wisdom.process_message(1, 2, "text", now=100)
        self.assertFalse(rejected.earned)
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=100):
            earned = await self.wisdom.process_message(1, 2, "text", now=100)
        self.assertTrue(earned.earned)
        self.assertEqual(earned.value, 1)
        row = await self.database.fetch_one(
            "SELECT context_json FROM wisdom_ledger WHERE source = 'message'"
        )
        self.assertNotIn("text", row["context_json"])

    async def test_cooldown_boundaries_and_guild_user_isolation(self) -> None:
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=100):
            first = await self.wisdom.process_message(1, 2, "text", now=100)
            before = await self.wisdom.process_message(1, 2, "text", now=129.999)
            other_user = await self.wisdom.process_message(1, 3, "text", now=100)
            other_guild = await self.wisdom.process_message(2, 2, "text", now=100)
            at_expiry = await self.wisdom.process_message(1, 2, "text", now=130)
            after_expiry = await self.wisdom.process_message(1, 4, "text", now=100)
            after_expiry = await self.wisdom.process_message(1, 4, "text", now=130.001)
        self.assertTrue(first.earned)
        self.assertFalse(before.earned)
        self.assertAlmostEqual(before.retry_after, 0.001)
        self.assertTrue(other_user.earned)
        self.assertTrue(other_guild.earned)
        self.assertTrue(at_expiry.earned)
        self.assertTrue(after_expiry.earned)
        self.assertEqual(at_expiry.value, 2)

    async def test_concurrent_messages_only_earn_once(self) -> None:
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=100):
            results = await asyncio.gather(
                self.wisdom.process_message(1, 2, "first", now=100),
                self.wisdom.process_message(1, 2, "second", now=100),
            )
        self.assertEqual(sum(result.earned for result in results), 1)
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100), 1)

    async def test_failed_ledger_insert_rolls_back_cooldown_and_wisdom(self) -> None:
        await self.database.connection.execute(
            """
            CREATE TRIGGER fail_wisdom_ledger BEFORE INSERT ON wisdom_ledger
            BEGIN SELECT RAISE(ABORT, 'ledger failure'); END
            """
        )
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=100):
            with self.assertRaises(sqlite3.IntegrityError):
                await self.wisdom.process_message(1, 2, "text", now=100)
        await self.database.connection.execute("DROP TRIGGER fail_wisdom_ledger")
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=100):
            result = await self.wisdom.process_message(1, 2, "text", now=100)
        self.assertTrue(result.earned)
        self.assertEqual(result.value, 1)

    async def test_decay_grace_clamping_and_clock_rollback(self) -> None:
        async with self.database.transaction() as connection:
            await connection.execute(
                "INSERT INTO wisdom VALUES ('1', '2', 2, 100)"
            )
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100 + 86400 - 1), 2)
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100 + 86400), 2)
        self.assertAlmostEqual(
            await self.wisdom.get_value(1, 2, now=100 + 86400 + 1),
            2 - 0.5 / 86400,
        )
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100 + 2 * 86400), 1.5)
        self.assertEqual(await self.wisdom.get_value(1, 2, now=100 + 10 * 86400), 0)
        self.assertEqual(await self.wisdom.get_value(1, 2, now=50), 2)

    async def test_refresh_on_any_message_updates_decay_anchor(self) -> None:
        settings = WisdomSettings(
            refresh_on_any_message=True,
            grace_days=0,
            decay_per_day=0.1,
        )
        service = WisdomService(self.database, settings, self.cooldowns)
        async with self.database.transaction() as connection:
            await connection.execute("INSERT INTO wisdom VALUES ('1', '2', 2, 0)")
        with patch("wisest_wizard.services.wisdom.raw_score", return_value=0):
            result = await service.process_message(1, 2, "text", now=86400)
        self.assertFalse(result.earned)
        self.assertAlmostEqual(result.value, 1.9)
        row = await self.database.fetch_one(
            "SELECT last_active FROM wisdom WHERE guild_id = '1' AND user_id = '2'"
        )
        self.assertEqual(row["last_active"], 86400)

    async def test_reputation_cooldown_is_shared_and_updates_ledger_atomically(self) -> None:
        positive = await self.wisdom.change_reputation(1, 10, 20, 1, now=100)
        negative = await self.wisdom.change_reputation(1, 10, 21, -1, now=101)
        other_giver = await self.wisdom.change_reputation(1, 11, 21, 1, now=101)
        self.assertTrue(positive.accepted)
        self.assertEqual(positive.value, 1)
        self.assertFalse(negative.accepted)
        self.assertEqual(negative.reason, "cooldown")
        self.assertTrue(other_giver.accepted)
        row = await self.database.fetch_one(
            "SELECT COUNT(*) AS count FROM reputation_ledger"
        )
        self.assertEqual(row["count"], 2)

    async def test_reputation_rejects_self_and_bot_without_spending_cooldown(self) -> None:
        self_result = await self.wisdom.change_reputation(1, 10, 10, 1, now=100)
        bot_result = await self.wisdom.change_reputation(
            1, 10, 20, 1, recipient_is_bot=True, now=100
        )
        valid = await self.wisdom.change_reputation(1, 10, 20, 1, now=100)
        self.assertEqual(self_result.reason, "self_target")
        self.assertEqual(bot_result.reason, "bot_target")
        self.assertTrue(valid.accepted)

    async def test_reputation_never_reduces_wisdom_below_zero(self) -> None:
        result = await self.wisdom.change_reputation(1, 10, 20, -1, now=100)
        self.assertTrue(result.accepted)
        self.assertEqual(result.amount, 0)
        self.assertEqual(result.value, 0)

    async def test_failed_reputation_ledger_rolls_back_cooldown_and_value(self) -> None:
        await self.database.connection.execute(
            """
            CREATE TRIGGER fail_reputation_ledger BEFORE INSERT ON reputation_ledger
            BEGIN SELECT RAISE(ABORT, 'ledger failure'); END
            """
        )
        with self.assertRaises(sqlite3.IntegrityError):
            await self.wisdom.change_reputation(1, 10, 20, 1, now=100)
        await self.database.connection.execute("DROP TRIGGER fail_reputation_ledger")
        result = await self.wisdom.change_reputation(1, 10, 20, 1, now=100)
        self.assertTrue(result.accepted)

    async def test_reward_is_idempotent_and_limited_by_typed_source(self) -> None:
        event = InteractionEvent(
            InteractionEventType.ITEM_USED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.INVENTORY,
            context={"item_id": "potion-1"},
            event_id="event-1",
        )
        granted = await self.rewards.grant(event, now=100)
        duplicate = await self.rewards.grant(event, now=100)
        another_source = InteractionEvent(
            InteractionEventType.ITEM_USED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.INVENTORY,
            context={"item_id": "potion-2"},
            event_id="event-2",
        )
        limited = await self.rewards.grant(another_source, now=101)
        another_type = InteractionEvent(
            InteractionEventType.GAME_COMPLETED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.GAME,
            event_id="event-3",
        )
        independent = await self.rewards.grant(another_type, now=101)
        self.assertTrue(granted.granted)
        self.assertEqual(duplicate.reason, "duplicate_event")
        self.assertEqual(limited.reason, "cooldown")
        self.assertTrue(independent.granted)
        rows = await self.database.fetch_one(
            "SELECT COUNT(*) AS count FROM wisdom_ledger WHERE event_id IS NOT NULL"
        )
        self.assertEqual(rows["count"], 2)

    async def test_reward_context_cannot_store_message_content(self) -> None:
        event = InteractionEvent(
            InteractionEventType.ITEM_USED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.INVENTORY,
            context={"message_content": "private text"},
        )
        with self.assertRaises(ValueError):
            await self.rewards.grant(event, now=100)

    async def test_reward_event_requires_matching_typed_source(self) -> None:
        event = InteractionEvent(
            InteractionEventType.ITEM_USED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.GAME,
            event_id="event-4",
        )
        with self.assertRaises(ValueError):
            await self.rewards.grant(event, now=100)

    async def test_failed_reward_ledger_rolls_back_cooldown_and_wisdom(self) -> None:
        event = InteractionEvent(
            InteractionEventType.ITEM_USED,
            actor_id=10,
            guild_id=1,
            source=InteractionSource.INVENTORY,
            event_id="event-5",
        )
        await self.database.connection.execute(
            """
            CREATE TRIGGER fail_reward_ledger BEFORE INSERT ON wisdom_ledger
            WHEN NEW.event_id IS NOT NULL
            BEGIN SELECT RAISE(ABORT, 'ledger failure'); END
            """
        )
        with self.assertRaises(sqlite3.IntegrityError):
            await self.rewards.grant(event, now=100)
        await self.database.connection.execute("DROP TRIGGER fail_reward_ledger")
        result = await self.rewards.grant(event, now=100)
        self.assertTrue(result.granted)


class WisdomCogTests(unittest.IsolatedAsyncioTestCase):
    async def test_listener_ignores_dms_and_bots_but_scores_commands(self) -> None:
        wisdom = SimpleNamespace(process_message=AsyncMock())
        cog = WisdomCog(wisdom)
        await cog.on_message(
            SimpleNamespace(guild=None, author=SimpleNamespace(bot=False))
        )
        await cog.on_message(
            SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(bot=True))
        )
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            author=SimpleNamespace(id=2, bot=False),
            content="cast karma",
        )
        await cog.on_message(message)
        wisdom.process_message.assert_awaited_once_with(1, 2, "cast karma")
