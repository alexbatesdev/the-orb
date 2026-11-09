import unittest

from wisest_wizard.duration import format_duration


class DurationTests(unittest.TestCase):
    def test_dynamic_units_and_rounding(self) -> None:
        cases = (
            (0, "0 seconds"),
            (0.001, "1 second"),
            (1, "1 second"),
            (1.01, "2 seconds"),
            (59, "59 seconds"),
            (59.01, "1 minute"),
            (61, "1 minute, 1 second"),
            (3599, "59 minutes, 59 seconds"),
            (3600, "1 hour"),
            (3661, "1 hour, 1 minute, 1 second"),
            (86400, "24 hours"),
            (90061, "25 hours, 1 minute, 1 second"),
        )
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_duration(seconds), expected)

    def test_invalid_duration_is_rejected(self) -> None:
        for seconds in (-1, float("inf"), float("nan")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                format_duration(seconds)
