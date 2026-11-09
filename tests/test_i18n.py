import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from discord.ext import commands

from wisest_wizard.errors import handle_command_error
from wisest_wizard.i18n import translate


ROOT = Path(__file__).resolve().parents[1]


class TranslationTests(unittest.TestCase):
    def test_formatting_preserves_values_and_numeric_precision(self) -> None:
        self.assertEqual(translate("core.hello", name="{Wizard}"), "Hello, {Wizard}! ✨")
        self.assertEqual(translate("wisdom.check.value", value=12.3456), "Your wisdom is 12.346.")
        self.assertEqual(
            translate("wisdom.rep.cooldown", duration="3 seconds"),
            "You can + or - rep again in 3 seconds.",
        )

    def test_missing_keys_and_placeholders_raise(self) -> None:
        with self.assertRaises(KeyError):
            translate("not.a.key")
        with self.assertRaises(KeyError):
            translate("core.hello")

    def test_catalog_matches_translation_calls(self) -> None:
        package = ROOT / "wisest_wizard"
        catalog = json.loads((package / "locales" / "en.json").read_text(encoding="utf-8"))
        keys = set()
        for path in package.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "translate"
                ):
                    self.assertTrue(node.args and isinstance(node.args[0], ast.Constant), str(path))
                    keys.add(node.args[0].value)
        self.assertEqual(keys, set(catalog))
        self.assertTrue(all(isinstance(value, str) for value in catalog.values()))


class TranslatedErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unhandled_command_error_is_logged_and_not_sent_verbatim(self) -> None:
        ctx = SimpleNamespace(send=AsyncMock(), command="test", author=SimpleNamespace(id=1))
        with self.assertLogs("wisest_wizard.errors", level="ERROR"):
            await handle_command_error(ctx, commands.CommandError("internal detail"))
        ctx.send.assert_awaited_once_with(
            "The command failed unexpectedly. The error has been logged."
        )
