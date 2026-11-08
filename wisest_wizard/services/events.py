from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


class InteractionEventType(StrEnum):
    MESSAGE_ACTIVITY = "message_activity"
    REPUTATION_GIVEN = "reputation_given"
    ITEM_USED = "item_used"
    ITEM_CRAFTED = "item_crafted"
    GAME_COMPLETED = "game_completed"
    DAILY_CLAIMED = "daily_claimed"
    DUNGEON_RUN_COMPLETED = "dungeon_run_completed"
    DUNGEON_OWNER_REWARDED = "dungeon_owner_rewarded"
    DUNGEON_GROWN = "dungeon_grown"


@dataclass(frozen=True)
class InteractionEvent:
    event_type: InteractionEventType
    actor_id: int
    source: str
    guild_id: int | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, InteractionEventType):
            raise ValueError("Interaction event type must be a known InteractionEventType.")
        if self.actor_id <= 0:
            raise ValueError("Interaction event actor ID must be positive.")
        if not self.source.strip():
            raise ValueError("Interaction event source must be non-empty.")
        if self.guild_id is not None and self.guild_id <= 0:
            raise ValueError("Interaction event guild ID must be positive.")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Interaction event timestamp must be timezone-aware.")
        if not self.event_id.strip():
            raise ValueError("Interaction event ID must be non-empty.")
