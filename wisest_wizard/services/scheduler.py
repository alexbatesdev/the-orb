from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from wisest_wizard.database import Database

logger = logging.getLogger(__name__)

EffectHandler = Callable[["ScheduledEffect"], Awaitable[None]]


@dataclass(frozen=True)
class ScheduledEffect:
    id: str
    effect_type: str
    payload: dict[str, Any]
    guild_id: str | None
    due_at: float
    attempts: int


class ScheduledEffects:
    def __init__(
        self,
        database: Database,
        *,
        poll_interval: float = 1.0,
        lease_seconds: float = 120.0,
        max_attempts: int = 5,
    ) -> None:
        if poll_interval <= 0 or lease_seconds <= 0 or max_attempts <= 0:
            raise ValueError("Scheduler intervals and attempt limits must be positive.")
        self.database = database
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self._handlers: dict[str, EffectHandler] = {}
        self._task: asyncio.Task[None] | None = None
        self._closing = asyncio.Event()

    def register(self, effect_type: str, handler: EffectHandler) -> None:
        effect_type = effect_type.strip()
        if not effect_type:
            raise ValueError("Effect type must be non-empty.")
        if effect_type in self._handlers:
            raise ValueError(f"Handler already registered for {effect_type!r}.")
        self._handlers[effect_type] = handler

    async def schedule(
        self,
        effect_type: str,
        payload: Mapping[str, Any],
        due_at: float,
        *,
        effect_id: str | None = None,
        guild_id: int | str | None = None,
        now: float | None = None,
    ) -> str:
        effect_type = effect_type.strip()
        if effect_type not in self._handlers:
            raise ValueError(f"No handler registered for {effect_type!r}.")
        if not isfinite(due_at):
            raise ValueError("Scheduled-effect due time must be finite.")
        if guild_id is not None and not str(guild_id).strip():
            raise ValueError("Scheduled-effect guild ID must be non-empty.")
        payload_json = json.dumps(
            dict(payload), separators=(",", ":"), sort_keys=True, allow_nan=False
        )
        identifier = effect_id or str(uuid.uuid4())
        timestamp = time.time() if now is None else now
        if not isfinite(timestamp):
            raise ValueError("Scheduled-effect creation time must be finite.")
        async with self.database.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO scheduled_effects (
                    id, effect_type, payload_json, guild_id, status, due_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    identifier,
                    effect_type,
                    payload_json,
                    None if guild_id is None else str(guild_id),
                    due_at,
                    timestamp,
                    timestamp,
                ),
            )
        return identifier

    async def claim_due(self, *, now: float | None = None) -> ScheduledEffect | None:
        timestamp = time.time() if now is None else now
        if not isfinite(timestamp):
            raise ValueError("Scheduled-effect claim time must be finite.")
        lease_until = timestamp + self.lease_seconds
        if not isfinite(lease_until):
            raise ValueError("Scheduled-effect lease time must be finite.")
        ready = await self.database.fetch_one(
            """
            SELECT 1 FROM scheduled_effects
            WHERE (status IN ('pending', 'retry') AND due_at <= ?)
               OR (status = 'running' AND lease_until <= ?)
            LIMIT 1
            """,
            (timestamp, timestamp),
        )
        if ready is None:
            return None
        async with self.database.transaction() as connection:
            row = await (
                await connection.execute(
                    """
                    SELECT id, effect_type, payload_json, guild_id, due_at, attempts
                    FROM scheduled_effects
                    WHERE (status IN ('pending', 'retry') AND due_at <= ?)
                       OR (status = 'running' AND lease_until <= ?)
                    ORDER BY due_at, id
                    LIMIT 1
                    """,
                    (timestamp, timestamp),
                )
            ).fetchone()
            if row is None:
                return None

            attempts = row["attempts"] + 1
            await connection.execute(
                """
                UPDATE scheduled_effects
                SET status = 'running', attempts = ?, lease_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (attempts, lease_until, timestamp, row["id"]),
            )
            return ScheduledEffect(
                id=row["id"],
                effect_type=row["effect_type"],
                payload=json.loads(row["payload_json"]),
                guild_id=row["guild_id"],
                due_at=row["due_at"],
                attempts=attempts,
            )

    async def recover_in_flight(self, *, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        if not isfinite(timestamp):
            raise ValueError("Scheduled-effect recovery time must be finite.")
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                """
                UPDATE scheduled_effects
                SET status = 'retry', due_at = MIN(due_at, ?),
                    lease_until = NULL, updated_at = ?
                WHERE status = 'running'
                """,
                (timestamp, timestamp),
            )
            return cursor.rowcount

    async def complete(self, effect_id: str, *, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                """
                UPDATE scheduled_effects
                SET status = 'completed', lease_until = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (timestamp, effect_id),
            )
            return cursor.rowcount == 1

    async def cancel(self, effect_id: str, *, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                """
                UPDATE scheduled_effects
                SET status = 'cancelled', updated_at = ?
                WHERE id = ? AND status IN ('pending', 'retry')
                """,
                (timestamp, effect_id),
            )
            return cursor.rowcount == 1

    async def fail(
        self,
        effect_id: str,
        attempts: int,
        error: Exception,
        *,
        now: float | None = None,
    ) -> None:
        timestamp = time.time() if now is None else now
        retry = attempts < self.max_attempts
        delay = min(60 * 2 ** max(0, attempts - 1), 3600)
        status = "retry" if retry else "failed"
        due_at = timestamp + delay if retry else timestamp
        error_text = f"{type(error).__name__}: {error}"[:500]
        async with self.database.transaction() as connection:
            await connection.execute(
                """
                UPDATE scheduled_effects
                SET status = ?, due_at = ?, lease_until = NULL,
                    last_error = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (status, due_at, error_text, timestamp, effect_id),
            )

    async def run_once(self, *, now: float | None = None) -> bool:
        effect = await self.claim_due(now=now)
        if effect is None:
            return False
        handler = self._handlers.get(effect.effect_type)
        if handler is None:
            error = RuntimeError(f"No handler registered for {effect.effect_type!r}.")
            await self.fail(effect.id, effect.attempts, error, now=now)
            logger.error("Scheduled effect %s has no registered handler.", effect.id)
            return True
        try:
            await handler(effect)
        except Exception as error:
            logger.exception(
                "Scheduled effect %s (%s) failed on attempt %s.",
                effect.id,
                effect.effect_type,
                effect.attempts,
            )
            await self.fail(effect.id, effect.attempts, error, now=now)
        else:
            await self.complete(effect.id, now=now)
        return True

    async def start(self) -> None:
        if self._task is not None:
            return
        self._closing.clear()
        self._task = asyncio.create_task(self._run(), name="scheduled-effects")

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        self._closing.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while not self._closing.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("Scheduled-effect worker encountered an infrastructure error.")
                processed = False
            if not processed:
                try:
                    await asyncio.wait_for(self._closing.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
