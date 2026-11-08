from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite


class DatabaseError(RuntimeError):
    """Raised when the database cannot provide the requested operation."""


class Database:
    def __init__(self, path: Path, migrations_dir: Path | None = None) -> None:
        self.path = path
        self.migrations_dir = migrations_dir or Path(__file__).parent / "migrations"
        self._connection: aiosqlite.Connection | None = None
        self._transaction_lock = asyncio.Lock()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise DatabaseError("Database is not open.")
        return self._connection

    async def open(self) -> None:
        if self._connection is not None:
            return
        connection: aiosqlite.Connection | None = None
        try:
            if str(self.path) != ":memory:":
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(self.path, isolation_level=None)
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA busy_timeout = 5000")
            await connection.execute("PRAGMA journal_mode = WAL")
            self._connection = connection
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                await connection.close()
            raise DatabaseError("Unable to open the SQLite database.") from error

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()

    async def fetch_one(
        self, query: str, parameters: Sequence[object] = ()
    ) -> aiosqlite.Row | None:
        async with self._transaction_lock:
            return await (await self.connection.execute(query, parameters)).fetchone()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = self.connection
        async with self._transaction_lock:
            try:
                await connection.execute("BEGIN IMMEDIATE")
                yield connection
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    async def migrate(self) -> None:
        connection = self.connection
        try:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at REAL NOT NULL
                )
                """
            )
            migration_paths = sorted(self.migrations_dir.glob("[0-9]*.sql"))
            applied_rows = await (
                await connection.execute("SELECT version FROM schema_migrations")
            ).fetchall()
            available_versions = {path.name for path in migration_paths}
            missing_migrations = {
                row["version"] for row in applied_rows
            } - available_versions
            if missing_migrations:
                versions = ", ".join(sorted(missing_migrations))
                raise DatabaseError(
                    f"Applied migration files are missing from the application: {versions}."
                )
            if not migration_paths:
                raise DatabaseError("No SQL migration files were found; startup cannot continue.")

            for migration_path in migration_paths:
                async with self.transaction() as transaction:
                    row = await (
                        await transaction.execute(
                            "SELECT 1 FROM schema_migrations WHERE version = ?",
                            (migration_path.name,),
                        )
                    ).fetchone()
                    if row is not None:
                        continue

                    script = migration_path.read_text(encoding="utf-8")
                    for statement in _split_sql_statements(script):
                        await transaction.execute(statement)
                    await transaction.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, strftime('%s', 'now'))",
                        (migration_path.name,),
                    )
        except (OSError, sqlite3.Error, aiosqlite.Error) as error:
            raise DatabaseError("Database migration failed; startup cannot continue.") from error

    async def ping(self) -> None:
        try:
            await (await self.connection.execute("SELECT 1")).fetchone()
        except aiosqlite.Error as error:
            raise DatabaseError("Database health check failed.") from error


def _split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines(keepends=True):
        current.append(line)
        if sqlite3.complete_statement("".join(current)):
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current.clear()
    remainder = "".join(current).strip()
    if remainder:
        raise DatabaseError("Migration contains an incomplete SQL statement.")
    return statements
