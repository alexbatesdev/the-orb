from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required environment configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    discord_token: str
    database_path: Path
    audit_retention_days: int | None


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
    )
