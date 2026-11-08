from __future__ import annotations

import json
import time
from collections.abc import Mapping
from math import isfinite
from typing import Any

import aiosqlite

from wisest_wizard.database import Database


class AuditService:
    def __init__(self, database: Database, retention_days: int | None = None) -> None:
        if retention_days is not None and retention_days <= 0:
            raise ValueError("Audit retention must be a positive number of days.")
        self.database = database
        self.retention_days = retention_days

    async def record(
        self,
        action: str,
        actor_id: int | str,
        *,
        guild_id: int | str | None = None,
        target_type: str | None = None,
        target_id: int | str | None = None,
        reason: str | None = None,
        details: Mapping[str, Any] | None = None,
        created_at: float | None = None,
    ) -> int:
        async with self.database.transaction() as connection:
            return await self.record_in_transaction(
                connection,
                action,
                actor_id,
                guild_id=guild_id,
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                details=details,
                created_at=created_at,
            )

    async def record_in_transaction(
        self,
        connection: aiosqlite.Connection,
        action: str,
        actor_id: int | str,
        *,
        guild_id: int | str | None = None,
        target_type: str | None = None,
        target_id: int | str | None = None,
        reason: str | None = None,
        details: Mapping[str, Any] | None = None,
        created_at: float | None = None,
    ) -> int:
        timestamp, serialized_details = self._validate_record(
            action, actor_id, guild_id, target_id, details, created_at
        )
        cursor = await connection.execute(
            """
            INSERT INTO audit_log (
                action, actor_id, guild_id, target_type, target_id,
                reason, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                str(actor_id),
                None if guild_id is None else str(guild_id),
                target_type,
                None if target_id is None else str(target_id),
                reason,
                serialized_details,
                timestamp,
            ),
        )
        if cursor.lastrowid is None:
            raise aiosqlite.Error("Audit insert did not return an ID.")
        return cursor.lastrowid

    @staticmethod
    def _validate_record(
        action: str,
        actor_id: int | str,
        guild_id: int | str | None,
        target_id: int | str | None,
        details: Mapping[str, Any] | None,
        created_at: float | None,
    ) -> tuple[float, str]:
        if not action.strip():
            raise ValueError("Audit action must be non-empty.")
        if details is not None and not isinstance(details, Mapping):
            raise ValueError("Audit details must be a mapping.")
        if not str(actor_id).strip():
            raise ValueError("Audit actor ID must be non-empty.")
        if guild_id is not None and not str(guild_id).strip():
            raise ValueError("Audit guild ID must be non-empty.")
        if target_id is not None and not str(target_id).strip():
            raise ValueError("Audit target ID must be non-empty.")
        timestamp = time.time() if created_at is None else created_at
        if not isfinite(timestamp):
            raise ValueError("Audit timestamp must be finite.")
        details_json = json.dumps(
            details or {}, separators=(",", ":"), sort_keys=True, allow_nan=False
        )
        return timestamp, details_json

    async def purge_expired(self, *, now: float | None = None, batch_size: int = 500) -> int:
        if batch_size <= 0:
            raise ValueError("Audit cleanup batch size must be positive.")
        if self.retention_days is None:
            return 0
        timestamp = time.time() if now is None else now
        if not isfinite(timestamp):
            raise ValueError("Audit cleanup time must be finite.")
        cutoff = timestamp - self.retention_days * 86400
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM audit_log
                WHERE id IN (
                    SELECT id FROM audit_log
                    WHERE created_at < ?
                    ORDER BY created_at
                    LIMIT ?
                )
                """,
                (cutoff, batch_size),
            )
            return cursor.rowcount
