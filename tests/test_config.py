import unittest
from pathlib import Path

from wisest_wizard.config import ConfigurationError, WisdomSettings, load_settings


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

    def test_wisdom_defaults_and_environment_overrides(self) -> None:
        defaults = load_settings({"DISCORD_TOKEN": "token"}).wisdom
        self.assertEqual(defaults, WisdomSettings())
        settings = load_settings(
            {
                "DISCORD_TOKEN": "token",
                "WISDOM_MESSAGE_COOLDOWN_SECONDS": "0.5",
                "WISDOM_MAX_CHARS": "128",
                "WISDOM_REFRESH_ON_ANY_MESSAGE": "true",
            }
        ).wisdom
        self.assertEqual(settings.message_cooldown_seconds, 0.5)
        self.assertEqual(settings.max_chars, 128)
        self.assertTrue(settings.refresh_on_any_message)

    def test_invalid_wisdom_settings_are_rejected(self) -> None:
        invalid_values = (
            {"WISDOM_MAX_CHARS": "0"},
            {"WISDOM_MESSAGE_COOLDOWN_SECONDS": "-1"},
            {"WISDOM_SCORE_CEIL": "0"},
            {"WISDOM_SCORE_FLOOR": "-2", "WISDOM_SCORE_CEIL": "-1"},
            {"WISDOM_QUALITY_CURVE": "nan"},
            {"WISDOM_GAIN": "inf"},
            {"WISDOM_REFRESH_ON_ANY_MESSAGE": "yes"},
        )
        for overrides in invalid_values:
            with self.subTest(overrides=overrides), self.assertRaises(ConfigurationError):
                load_settings({"DISCORD_TOKEN": "token", **overrides})
