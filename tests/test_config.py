import unittest
from pathlib import Path

from wisest_wizard.config import ConfigurationError, load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_defaults_and_optional_retention(self) -> None:
        settings = load_settings({"DISCORD_TOKEN": "token"})
        self.assertEqual(settings.discord_token, "token")
        self.assertEqual(settings.database_path, Path("data/wisest-wizard.sqlite3"))
        self.assertIsNone(settings.audit_retention_days)

    def test_retention_must_be_positive_integer(self) -> None:
        for value in ("0", "-1", "one"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                load_settings({"DISCORD_TOKEN": "token", "AUDIT_RETENTION_DAYS": value})

    def test_required_token_must_be_nonempty_and_whitespace_free(self) -> None:
        for value in ("", "  ", "token value"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                load_settings({"DISCORD_TOKEN": value})

    def test_database_path_cannot_be_empty(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings({"DISCORD_TOKEN": "token", "DATABASE_PATH": " "})
