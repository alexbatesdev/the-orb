from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

import aiosqlite

from wisest_wizard.config import WisdomSettings
from wisest_wizard.database import Database
from wisest_wizard.scoring import quality, raw_score
from wisest_wizard.services.cooldowns import (
    CooldownResult,
    CooldownScope,
    PersistentCooldowns,
)
from wisest_wizard.services.events import (
    InteractionEvent,
    InteractionEventType,
    InteractionSource,
)

_REWARD_SOURCES = {
    InteractionEventType.ITEM_USED: InteractionSource.INVENTORY,
    InteractionEventType.ITEM_CRAFTED: InteractionSource.CRAFTING,
    InteractionEventType.GAME_COMPLETED: InteractionSource.GAME,
    InteractionEventType.DAILY_CLAIMED: InteractionSource.DAILY,
    InteractionEventType.DUNGEON_RUN_COMPLETED: InteractionSource.DUNGEON,
    InteractionEventType.DUNGEON_OWNER_REWARDED: InteractionSource.DUNGEON_OWNER,
    InteractionEventType.DUNGEON_GROWN: InteractionSource.DUNGEON_GROWTH,
    InteractionEventType.OTHER_INTERACTION: InteractionSource.OTHER,
}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_CONTEXT_KEY = re.compile(
    r"^(?:[a-z][a-z0-9_]*_id|quantity|outcome|result_code)$"
)


@dataclass(frozen=True)
class WisdomMessageResult:
    raw_score: int
    quality: float
    earned: bool
    amount: float
    value: float
    retry_after: float = 0.0


@dataclass(frozen=True)
class ReputationResult:
    accepted: bool
    amount: float
    value: float
    retry_after: float = 0.0
    reason: str | None = None


@dataclass(frozen=True)
class WisdomRewardResult:
    granted: bool
    amount: float
    value: float
    retry_after: float = 0.0
    reason: str | None = None


class WisdomService:
    def __init__(
        self,
        database: Database,
        settings: WisdomSettings,
        cooldowns: PersistentCooldowns,
    ) -> None:
        self.database = database
        self.settings = settings
        self.cooldowns = cooldowns

    async def get_value(
        self, guild_id: int, user_id: int, *, now: float | None = None
    ) -> float:
        _validate_identity(guild_id, user_id)
        current_time = _current_time(now)
        row = await self.database.fetch_one(
            "SELECT value, last_active FROM wisdom WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        )
        return 0.0 if row is None else self._decayed_value(row, current_time)

    async def process_message(
        self,
        guild_id: int,
        user_id: int,
        content: str,
        *,
        now: float | None = None,
    ) -> WisdomMessageResult:
        _validate_identity(guild_id, user_id)
        current_time = _current_time(now)
        scored_text = content[: self.settings.max_chars]
        score = raw_score(scored_text, max_chars=self.settings.max_chars)
        message_quality = quality(score, self.settings)

        if message_quality <= 0 and not self.settings.refresh_on_any_message:
            return WisdomMessageResult(
                score,
                message_quality,
                False,
                0.0,
                await self.get_value(guild_id, user_id, now=current_time),
            )

        async with self.database.transaction() as connection:
            cooldown = CooldownResult(True, 0.0)
            if message_quality > 0:
                cooldown = await self.cooldowns.acquire_in_transaction(
                    connection,
                    "wisdom.message",
                    self.settings.message_cooldown_seconds,
                    scope=CooldownScope.USER,
                    guild_id=guild_id,
                    user_id=user_id,
                    now=current_time,
                )

            row = await self._fetch_wisdom(connection, guild_id, user_id)
            value = 0.0 if row is None else self._decayed_value(row, current_time)
            earned = message_quality > 0 and cooldown.acquired
            amount = self.settings.gain * message_quality if earned else 0.0
            if earned:
                value += amount
                if not isfinite(value):
                    raise ValueError("Wisdom value exceeded the supported numeric range.")
                await self._upsert_value(
                    connection,
                    guild_id,
                    user_id,
                    value,
                    self._activity_time(row, current_time),
                )
                await connection.execute(
                    """
                    INSERT INTO wisdom_ledger (
                        guild_id, user_id, amount, source, event_type, context_json, created_at
                    ) VALUES (?, ?, ?, 'message', ?, ?, ?)
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        amount,
                        InteractionEventType.MESSAGE_ACTIVITY.value,
                        json.dumps(
                            {"raw_score": score, "quality": message_quality},
                            separators=(",", ":"),
                            sort_keys=True,
                            allow_nan=False,
                        ),
                        current_time,
                    ),
                )
            elif self.settings.refresh_on_any_message and row is not None:
                await self._upsert_value(
                    connection,
                    guild_id,
                    user_id,
                    value,
                    self._activity_time(row, current_time),
                )

        return WisdomMessageResult(
            score,
            message_quality,
            earned,
            amount,
            value,
            0.0 if cooldown.acquired else cooldown.retry_after,
        )

    async def change_reputation(
        self,
        guild_id: int,
        giver_id: int,
        recipient_id: int,
        direction: int,
        *,
        recipient_is_bot: bool = False,
        now: float | None = None,
    ) -> ReputationResult:
        _validate_identity(guild_id, giver_id)
        _validate_identity(guild_id, recipient_id)
        if direction not in {-1, 1}:
            raise ValueError("Reputation direction must be -1 or 1.")
        if giver_id == recipient_id:
            return ReputationResult(False, 0.0, 0.0, reason="self_target")
        if recipient_is_bot:
            return ReputationResult(False, 0.0, 0.0, reason="bot_target")

        current_time = _current_time(now)
        async with self.database.transaction() as connection:
            cooldown = await self.cooldowns.acquire_in_transaction(
                connection,
                "wisdom.reputation",
                self.settings.reputation_cooldown_seconds,
                scope=CooldownScope.USER,
                guild_id=guild_id,
                user_id=giver_id,
                now=current_time,
            )
            if not cooldown.acquired:
                row = await self._fetch_wisdom(connection, guild_id, recipient_id)
                value = 0.0 if row is None else self._decayed_value(row, current_time)
                return ReputationResult(
                    False, 0.0, value, cooldown.retry_after, reason="cooldown"
                )

            row = await self._fetch_wisdom(connection, guild_id, recipient_id)
            value = 0.0 if row is None else self._decayed_value(row, current_time)
            requested = self.settings.reputation_change
            next_value = max(0.0, value + direction * requested)
            amount = abs(next_value - value)
            if not isfinite(next_value):
                raise ValueError("Wisdom value exceeded the supported numeric range.")
            await self._upsert_value(
                connection,
                guild_id,
                recipient_id,
                next_value,
                self._activity_time(row, current_time),
            )
            await connection.execute(
                """
                INSERT INTO reputation_ledger (
                    guild_id, giver_id, recipient_id, direction, amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(giver_id), str(recipient_id), direction, amount, current_time),
            )
        return ReputationResult(True, amount, next_value)

    @staticmethod
    async def _fetch_wisdom(
        connection: aiosqlite.Connection, guild_id: int, user_id: int
    ) -> aiosqlite.Row | None:
        return await (
            await connection.execute(
                "SELECT value, last_active FROM wisdom WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
        ).fetchone()

    async def _upsert_value(
        self,
        connection: aiosqlite.Connection,
        guild_id: int,
        user_id: int,
        value: float,
        last_active: float,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO wisdom (guild_id, user_id, value, last_active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET value = excluded.value, last_active = excluded.last_active
            """,
            (str(guild_id), str(user_id), value, last_active),
        )

    def _decayed_value(self, row: Any, now: float) -> float:
        elapsed = max(0.0, now - row["last_active"])
        idle_days = elapsed / 86400
        decay_days = max(0.0, idle_days - self.settings.grace_days)
        return max(0.0, row["value"] - self.settings.decay_per_day * decay_days)

    @staticmethod
    def _activity_time(row: Any | None, now: float) -> float:
        return now if row is None else max(now, row["last_active"])


class WisdomRewardService:
    def __init__(self, wisdom: WisdomService) -> None:
        self.wisdom = wisdom

    async def grant(
        self, event: InteractionEvent, *, now: float | None = None
    ) -> WisdomRewardResult:
        if not isinstance(event, InteractionEvent):
            raise ValueError("Wisdom rewards require an InteractionEvent.")
        expected_source = _REWARD_SOURCES.get(event.event_type)
        if expected_source is None:
            raise ValueError("This interaction event type cannot grant wisdom.")
        if event.source is not expected_source:
            raise ValueError("Wisdom reward source does not match its event type.")
        if event.guild_id is None:
            raise ValueError("Wisdom reward events must be associated with a guild.")
        _validate_identity(event.guild_id, event.actor_id)
        if not _SAFE_IDENTIFIER.fullmatch(event.event_id):
            raise ValueError("Wisdom reward event ID must be a non-empty identifier.")
        context_json = _serialize_safe_context(event.context)
        current_time = _current_time(now)
        settings = self.wisdom.settings

        async with self.wisdom.database.transaction() as connection:
            duplicate = await (
                await connection.execute(
                    "SELECT 1 FROM wisdom_ledger WHERE event_id = ?",
                    (event.event_id,),
                )
            ).fetchone()
            if duplicate is not None:
                row = await self.wisdom._fetch_wisdom(
                    connection, event.guild_id, event.actor_id
                )
                value = (
                    0.0 if row is None else self.wisdom._decayed_value(row, current_time)
                )
                return WisdomRewardResult(
                    False, 0.0, value, reason="duplicate_event"
                )

            cooldown = await self.wisdom.cooldowns.acquire_in_transaction(
                connection,
                f"wisdom.reward.{event.event_type.value}",
                settings.reward_cooldown_seconds,
                scope=CooldownScope.USER,
                guild_id=event.guild_id,
                user_id=event.actor_id,
                now=current_time,
            )
            row = await self.wisdom._fetch_wisdom(
                connection, event.guild_id, event.actor_id
            )
            value = (
                0.0 if row is None else self.wisdom._decayed_value(row, current_time)
            )
            if not cooldown.acquired:
                return WisdomRewardResult(
                    False,
                    0.0,
                    value,
                    cooldown.retry_after,
                    reason="cooldown",
                )

            amount = settings.reward_gain
            value += amount
            if not isfinite(value):
                raise ValueError("Wisdom value exceeded the supported numeric range.")
            await self.wisdom._upsert_value(
                connection,
                event.guild_id,
                event.actor_id,
                value,
                self.wisdom._activity_time(row, current_time),
            )
            await connection.execute(
                """
                INSERT INTO wisdom_ledger (
                    guild_id, user_id, amount, source, event_type, event_id,
                    context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.guild_id),
                    str(event.actor_id),
                    amount,
                    event.source.value,
                    event.event_type.value,
                    event.event_id,
                    context_json,
                    current_time,
                ),
            )
        return WisdomRewardResult(True, amount, value)


def _validate_identity(guild_id: int, user_id: int) -> None:
    if guild_id <= 0 or user_id <= 0:
        raise ValueError("Guild and user IDs must be positive.")


def _current_time(now: float | None) -> float:
    current_time = time.time() if now is None else now
    if not isfinite(current_time):
        raise ValueError("Wisdom timestamp must be finite.")
    return current_time


def _serialize_safe_context(context: Mapping[str, Any]) -> str:
    if not isinstance(context, Mapping):
        raise ValueError("Wisdom event context must be a mapping.")
    safe_context: dict[str, int | float | str | bool | None] = {}
    for key, value in context.items():
        if not isinstance(key, str) or not _SAFE_CONTEXT_KEY.fullmatch(key):
            raise ValueError("Wisdom event context keys must identify metadata, not content.")
        if isinstance(value, str) and not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("Wisdom event context strings must be identifiers.")
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("Wisdom event context numbers must be finite.")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Wisdom event context values must be scalar metadata.")
        safe_context[key] = value
    return json.dumps(
        safe_context, separators=(",", ":"), sort_keys=True, allow_nan=False
    )
