from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required environment configuration is invalid."""


@dataclass(frozen=True)
class WisdomSettings:
    max_chars: int = 192
    message_cooldown_seconds: float = 1.0
    score_floor: float = 0.0
    score_ceil: float = 100.0
    quality_curve: float = 1.0
    gain: float = 0.02
    grace_days: float = 7.0
    decay_per_day: float = 0.02
    refresh_on_any_message: bool = False
    reputation_cooldown_seconds: float = 86400.0
    reputation_change: float = 1.0
    reward_cooldown_seconds: float = 86400.0
    reward_gain: float = 0.02

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_chars, bool)
            or not isinstance(self.max_chars, int)
            or self.max_chars <= 0
        ):
            raise ConfigurationError("WISDOM_MAX_CHARS must be a positive integer.")
        for name, value in (
            ("WISDOM_MESSAGE_COOLDOWN_SECONDS", self.message_cooldown_seconds),
            ("WISDOM_SCORE_FLOOR", self.score_floor),
            ("WISDOM_SCORE_CEIL", self.score_ceil),
            ("WISDOM_QUALITY_CURVE", self.quality_curve),
            ("WISDOM_GAIN", self.gain),
            ("WISDOM_GRACE_DAYS", self.grace_days),
            ("WISDOM_DECAY_PER_DAY", self.decay_per_day),
            ("WISDOM_REPUTATION_COOLDOWN_SECONDS", self.reputation_cooldown_seconds),
            ("WISDOM_REPUTATION_CHANGE", self.reputation_change),
            ("WISDOM_REWARD_COOLDOWN_SECONDS", self.reward_cooldown_seconds),
            ("WISDOM_REWARD_GAIN", self.reward_gain),
        ):
            if not isfinite(value):
                raise ConfigurationError(f"{name} must be a finite number.")
        if self.message_cooldown_seconds < 0:
            raise ConfigurationError("WISDOM_MESSAGE_COOLDOWN_SECONDS cannot be negative.")
        if self.score_ceil <= 0:
            raise ConfigurationError("WISDOM_SCORE_CEIL must be greater than zero.")
        if self.score_ceil <= self.score_floor:
            raise ConfigurationError(
                "WISDOM_SCORE_CEIL must be greater than WISDOM_SCORE_FLOOR."
            )
        if self.quality_curve <= 0:
            raise ConfigurationError("WISDOM_QUALITY_CURVE must be greater than zero.")
        if self.gain <= 0:
            raise ConfigurationError("WISDOM_GAIN must be greater than zero.")
        if self.grace_days < 0:
            raise ConfigurationError("WISDOM_GRACE_DAYS cannot be negative.")
        if self.decay_per_day < 0:
            raise ConfigurationError("WISDOM_DECAY_PER_DAY cannot be negative.")
        if self.reputation_cooldown_seconds < 0:
            raise ConfigurationError("WISDOM_REPUTATION_COOLDOWN_SECONDS cannot be negative.")
        if self.reputation_change <= 0:
            raise ConfigurationError("WISDOM_REPUTATION_CHANGE must be greater than zero.")
        if self.reward_cooldown_seconds < 0:
            raise ConfigurationError("WISDOM_REWARD_COOLDOWN_SECONDS cannot be negative.")
        if self.reward_gain <= 0:
            raise ConfigurationError("WISDOM_REWARD_GAIN must be greater than zero.")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    database_path: Path
    audit_retention_days: int | None
    wisdom: WisdomSettings = WisdomSettings()


def _wisdom_settings(values: Mapping[str, str]) -> WisdomSettings:
    def float_value(name: str, default: float) -> float:
        value = values.get(name, str(default)).strip()
        try:
            parsed = float(value)
        except ValueError as error:
            raise ConfigurationError(f"{name} must be a finite number.") from error
        if not isfinite(parsed):
            raise ConfigurationError(f"{name} must be a finite number.")
        return parsed

    max_chars_value = values.get("WISDOM_MAX_CHARS", "192").strip()
    try:
        max_chars = int(max_chars_value)
    except ValueError as error:
        raise ConfigurationError("WISDOM_MAX_CHARS must be a positive integer.") from error

    refresh_value = values.get("WISDOM_REFRESH_ON_ANY_MESSAGE", "false").strip().lower()
    if refresh_value not in {"true", "false"}:
        raise ConfigurationError("WISDOM_REFRESH_ON_ANY_MESSAGE must be true or false.")

    return WisdomSettings(
        max_chars=max_chars,
        message_cooldown_seconds=float_value("WISDOM_MESSAGE_COOLDOWN_SECONDS", 1.0),
        score_floor=float_value("WISDOM_SCORE_FLOOR", 0.0),
        score_ceil=float_value("WISDOM_SCORE_CEIL", 100.0),
        quality_curve=float_value("WISDOM_QUALITY_CURVE", 1.0),
        gain=float_value("WISDOM_GAIN", 0.02),
        grace_days=float_value("WISDOM_GRACE_DAYS", 7.0),
        decay_per_day=float_value("WISDOM_DECAY_PER_DAY", 0.02),
        refresh_on_any_message=refresh_value == "true",
        reputation_cooldown_seconds=float_value(
            "WISDOM_REPUTATION_COOLDOWN_SECONDS", 86400.0
        ),
        reputation_change=float_value("WISDOM_REPUTATION_CHANGE", 1.0),
        reward_cooldown_seconds=float_value("WISDOM_REWARD_COOLDOWN_SECONDS", 86400.0),
        reward_gain=float_value("WISDOM_REWARD_GAIN", 0.02),
    )


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    if environ is None:
        load_dotenv()
        values = os.environ
    else:
        values = environ

    token = values.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigurationError("DISCORD_TOKEN must be set and non-empty.")
    if any(character.isspace() for character in token):
        raise ConfigurationError("DISCORD_TOKEN must not contain whitespace.")

    database_value = values.get("DATABASE_PATH", "data/wisest-wizard.sqlite3").strip()
    if not database_value:
        raise ConfigurationError("DATABASE_PATH must be set and non-empty.")
    database_path = Path(database_value).expanduser()

    retention_value = values.get("AUDIT_RETENTION_DAYS", "").strip()
    retention_days: int | None = None
    if retention_value:
        try:
            retention_days = int(retention_value)
        except ValueError as error:
            raise ConfigurationError(
                "AUDIT_RETENTION_DAYS must be a positive integer."
            ) from error
        if retention_days <= 0:
            raise ConfigurationError("AUDIT_RETENTION_DAYS must be a positive integer.")

    return Settings(
        discord_token=token,
        database_path=database_path,
        audit_retention_days=retention_days,
        wisdom=_wisdom_settings(values),
    )
