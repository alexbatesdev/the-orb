from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from wisest_wizard.database import Database


class CooldownScope(StrEnum):
    GLOBAL = "global"
    GUILD = "guild"
    USER = "user"


@dataclass(frozen=True)
class CooldownResult:
    acquired: bool
    retry_after: float


class PersistentCooldowns:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def acquire(
        self,
        key: str,
        duration_seconds: float,
        *,
        scope: CooldownScope,
        guild_id: int | str | None = None,
        user_id: int | str | None = None,
        now: float | None = None,
    ) -> CooldownResult:
        key = key.strip()
        if not key:
            raise ValueError("Cooldown key must be non-empty.")
        if not isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError("Cooldown duration must be nonnegative.")
        if not isinstance(scope, CooldownScope):
            try:
                scope = CooldownScope(scope)
            except ValueError as error:
                raise ValueError("Cooldown scope must be global, guild, or user.") from error
        if scope is CooldownScope.GUILD and guild_id is None:
            raise ValueError("Guild-scoped cooldowns require a guild ID.")
        if scope is CooldownScope.USER and user_id is None:
            raise ValueError("User-scoped cooldowns require a user ID.")
        if scope is CooldownScope.GLOBAL and (guild_id is not None or user_id is not None):
            raise ValueError("Global cooldowns cannot be bound to a guild or user.")
        if scope is CooldownScope.GUILD and user_id is not None:
            raise ValueError("Guild-scoped cooldowns cannot be bound to a user.")
        if guild_id is not None and not str(guild_id).strip():
            raise ValueError("Guild ID must be non-empty.")
        if user_id is not None and not str(user_id).strip():
            raise ValueError("User ID must be non-empty.")

        guild_value = (
            str(guild_id)
            if scope is CooldownScope.GUILD
            or (scope is CooldownScope.USER and guild_id is not None)
            else ""
        )
        user_value = str(user_id) if scope is CooldownScope.USER else ""
        current_time = time.time() if now is None else now
        if not isfinite(current_time):
            raise ValueError("Cooldown timestamp must be finite.")
        async with self.database.transaction() as connection:
            row = await (
                await connection.execute(
                    """
                    SELECT expires_at FROM cooldowns
                    WHERE cooldown_key = ? AND scope = ? AND guild_id = ? AND user_id = ?
                    """,
                    (key, scope.value, guild_value, user_value),
                )
            ).fetchone()
            if row is not None and row["expires_at"] > current_time:
                return CooldownResult(False, row["expires_at"] - current_time)

            expires_at = current_time + duration_seconds
            if not isfinite(expires_at):
                raise ValueError("Cooldown expiration time must be finite.")
            await connection.execute(
                """
                INSERT INTO cooldowns (
                    cooldown_key, scope, guild_id, user_id, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (cooldown_key, scope, guild_id, user_id)
                DO UPDATE SET expires_at = excluded.expires_at, updated_at = excluded.updated_at
                """,
                (key, scope.value, guild_value, user_value, expires_at, current_time),
            )
        return CooldownResult(True, 0.0)
