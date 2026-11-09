import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from wisest_wizard.app import WizardBot, get_prefix
from wisest_wizard.config import Settings
from wisest_wizard.database import Database, DatabaseError
from wisest_wizard.services.audit import AuditService
from wisest_wizard.services.cooldowns import CooldownScope, PersistentCooldowns
from wisest_wizard.services.events import (
    InteractionEvent,
    InteractionEventType,
    InteractionSource,
)
from wisest_wizard.services.scheduler import ScheduledEffects


class FoundationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "wizard.sqlite3")
        await self.database.open()
        await self.database.migrate()

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_migrations_are_repeatable(self) -> None:
        await self.database.migrate()
        rows = await (
            await self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ).fetchall()
        self.assertEqual(
            [row["version"] for row in rows],
            ["0001_foundation.sql", "0002_wisdom.sql"],
        )

    async def test_migrations_fail_if_an_applied_file_is_missing(self) -> None:
        migrations_dir = Path(self.temp_dir.name) / "incomplete-migrations"
        migrations_dir.mkdir()
        database = Database(Path(self.temp_dir.name) / "incomplete.sqlite3", migrations_dir)
        await database.open()
        try:
            async with database.transaction() as connection:
                await connection.execute(
                    """
                    CREATE TABLE schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at REAL NOT NULL
                    )
                    """
                )
                await connection.execute(
                    "INSERT INTO schema_migrations VALUES ('0001_removed.sql', 1)"
                )
            with self.assertRaisesRegex(DatabaseError, "missing"):
                await database.migrate()
        finally:
            await database.close()

    async def test_failed_migration_rolls_back_schema_changes(self) -> None:
        migrations_dir = Path(self.temp_dir.name) / "broken-migrations"
        migrations_dir.mkdir()
        (migrations_dir / "0001_broken.sql").write_text(
            "CREATE TABLE partial_change (id INTEGER PRIMARY KEY);\n"
            "THIS IS NOT VALID SQL;\n",
            encoding="utf-8",
        )
        database = Database(Path(self.temp_dir.name) / "broken.sqlite3", migrations_dir)
        await database.open()
        try:
            with self.assertRaises(DatabaseError):
                await database.migrate()
            row = await (
                await database.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'partial_change'"
                )
            ).fetchone()
            self.assertIsNone(row)
            versions = await (
                await database.connection.execute(
                    "SELECT COUNT(*) AS count FROM schema_migrations"
                )
            ).fetchone()
            self.assertEqual(versions["count"], 0)
        finally:
            await database.close()

    async def test_transaction_rolls_back_on_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            async with self.database.transaction() as connection:
                await connection.execute(
                    """
                    INSERT INTO audit_log (action, actor_id, details_json, created_at)
                    VALUES ('should-not-persist', '1', '{}', 0)
                    """
                )
                raise RuntimeError("rollback")
        row = await (
            await self.database.connection.execute(
                "SELECT COUNT(*) AS count FROM audit_log"
            )
        ).fetchone()
        self.assertEqual(row["count"], 0)

    async def test_cooldown_is_atomic_across_concurrent_calls(self) -> None:
        cooldowns = PersistentCooldowns(self.database)
        results = await asyncio.gather(
            *(
                cooldowns.acquire(
                    "daily-rep",
                    86400,
                    scope=CooldownScope.USER,
                    user_id=42,
                    now=1000,
                )
                for _ in range(2)
            )
        )
        self.assertEqual(sum(result.acquired for result in results), 1)
        blocked = next(result for result in results if not result.acquired)
        self.assertEqual(blocked.retry_after, 86400)

    async def test_cooldown_rejects_missing_scope_identity(self) -> None:
        with self.assertRaises(ValueError):
            await PersistentCooldowns(self.database).acquire(
                "guild-action", 10, scope=CooldownScope.GUILD
            )

    async def test_user_cooldowns_are_scoped_by_guild_when_given(self) -> None:
        cooldowns = PersistentCooldowns(self.database)
        first = await cooldowns.acquire(
            "rep", 100, scope=CooldownScope.USER, user_id=1, guild_id=10, now=1000
        )
        second = await cooldowns.acquire(
            "rep", 100, scope=CooldownScope.USER, user_id=1, guild_id=20, now=1000
        )
        self.assertTrue(first.acquired)
        self.assertTrue(second.acquired)

    async def test_audit_record_and_bounded_retention(self) -> None:
        audit = AuditService(self.database, retention_days=1)
        await audit.record("admin.action", 1, created_at=1, details={"target": "item"})
        await audit.record("admin.action", 1, created_at=200000)
        first = await (
            await self.database.connection.execute(
                "SELECT details_json FROM audit_log WHERE created_at = 1"
            )
        ).fetchone()
        self.assertEqual(first["details_json"], '{"target":"item"}')
        deleted = await audit.purge_expired(now=200000, batch_size=1)
        self.assertEqual(deleted, 1)
        row = await (
            await self.database.connection.execute(
                "SELECT created_at, details_json FROM audit_log"
            )
        ).fetchone()
        self.assertEqual(row["created_at"], 200000)
        self.assertEqual(row["details_json"], "{}")

    async def test_audit_record_can_share_state_transaction(self) -> None:
        audit = AuditService(self.database)
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            async with self.database.transaction() as connection:
                await connection.execute(
                    """
                    INSERT INTO audit_log (action, actor_id, details_json, created_at)
                    VALUES ('state.change', '1', '{}', 0)
                    """
                )
                await audit.record_in_transaction(
                    connection, "state.change", 1, details={"state": "new"}
                )
                raise RuntimeError("rollback")
        row = await (
            await self.database.connection.execute(
                "SELECT COUNT(*) AS count FROM audit_log"
            )
        ).fetchone()
        self.assertEqual(row["count"], 0)

    async def test_audit_retention_unset_keeps_records(self) -> None:
        audit = AuditService(self.database)
        await audit.record("admin.action", 1, created_at=1)
        self.assertEqual(await audit.purge_expired(now=999999999), 0)

    async def test_only_one_worker_claims_a_due_effect(self) -> None:
        scheduler = ScheduledEffects(self.database, lease_seconds=10)

        async def handler(effect) -> None:
            return None

        scheduler.register("test.effect", handler)
        effect_id = await scheduler.schedule(
            "test.effect", {"value": 1}, due_at=100, now=50
        )
        claims = await asyncio.gather(
            scheduler.claim_due(now=100), scheduler.claim_due(now=100)
        )
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        self.assertEqual(next(claim for claim in claims if claim).id, effect_id)
        self.assertIsNone(await scheduler.claim_due(now=109))
        self.assertEqual((await scheduler.claim_due(now=110)).id, effect_id)

    async def test_scheduler_executes_and_marks_completed(self) -> None:
        scheduler = ScheduledEffects(self.database)
        seen: list[str] = []

        async def handler(effect) -> None:
            seen.append(effect.payload["message"])

        scheduler.register("test.effect", handler)
        effect_id = await scheduler.schedule(
            "test.effect", {"message": "done"}, due_at=100, now=50
        )
        self.assertTrue(await scheduler.run_once(now=100))
        self.assertEqual(seen, ["done"])
        row = await (
            await self.database.connection.execute(
                "SELECT status FROM scheduled_effects WHERE id = ?", (effect_id,)
            )
        ).fetchone()
        self.assertEqual(row["status"], "completed")

    async def test_startup_recovers_in_flight_effects_immediately(self) -> None:
        scheduler = ScheduledEffects(self.database, lease_seconds=120)

        async def handler(effect) -> None:
            return None

        scheduler.register("test.effect", handler)
        effect_id = await scheduler.schedule(
            "test.effect", {}, due_at=100, guild_id=77, now=50
        )
        self.assertIsNotNone(await scheduler.claim_due(now=100))
        self.assertEqual(await scheduler.recover_in_flight(now=101), 1)
        recovered = await scheduler.claim_due(now=101)
        self.assertEqual(recovered.id, effect_id)
        self.assertEqual(recovered.guild_id, "77")

    async def test_pending_effect_can_be_cancelled(self) -> None:
        scheduler = ScheduledEffects(self.database)

        async def handler(effect) -> None:
            return None

        scheduler.register("test.effect", handler)
        effect_id = await scheduler.schedule("test.effect", {}, due_at=100, now=50)
        self.assertTrue(await scheduler.cancel(effect_id, now=60))
        self.assertFalse(await scheduler.cancel(effect_id, now=61))
        self.assertIsNone(await scheduler.claim_due(now=100))

    async def test_prefix_matching_preserves_typed_case(self) -> None:
        self.assertEqual(get_prefix(None, SimpleNamespace(content="CAST hello")), "CAST ")
        self.assertEqual(get_prefix(None, SimpleNamespace(content="I CAST hello")), "I CAST ")
        self.assertEqual(
            get_prefix(None, SimpleNamespace(content="hello")),
            ("i cast ", "cast ", "+", "-"),
        )
        self.assertEqual(get_prefix(None, SimpleNamespace(content="+rep @member")), "+")
        self.assertEqual(get_prefix(None, SimpleNamespace(content="-rep @member")), "-")

    async def test_bot_setup_loads_core_commands(self) -> None:
        settings = Settings("test-token", Path(":memory:"), None)
        bot = WizardBot(settings, self.database)
        await bot.setup_hook()
        try:
            self.assertIsNotNone(bot.get_command("hello"))
            self.assertIsNotNone(bot.get_command("health"))
            self.assertIsNotNone(bot.get_command("karma"))
            self.assertIsNotNone(bot.get_command("rep"))
        finally:
            await bot.close()

    async def test_interaction_event_requires_aware_timestamp(self) -> None:
        from datetime import datetime

        with self.assertRaises(ValueError):
            InteractionEvent(
                event_type=InteractionEventType.ITEM_USED,
                actor_id=1,
                source=InteractionSource.INVENTORY,
                occurred_at=datetime(2026, 1, 1),
            )
