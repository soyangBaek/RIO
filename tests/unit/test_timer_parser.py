from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.app.domains.speech.timer_parser import parse_timer_text


class TimerParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)

    def test_parses_five_minutes_later(self) -> None:
        result = parse_timer_text("5분 있다 알려줘", now=self.now)
        self.assertTrue(result.ok)
        self.assertEqual(result.payload["delay_seconds"], 300)

    def test_parses_thirty_seconds_later(self) -> None:
        result = parse_timer_text("30초 뒤에 알려줘", now=self.now)
        self.assertTrue(result.ok)
        self.assertEqual(result.payload["delay_seconds"], 30)

    def test_parses_absolute_time(self) -> None:
        result = parse_timer_text("오후 3시에 알려줘", now=self.now)
        self.assertTrue(result.ok)
        self.assertGreater(int(result.payload["delay_seconds"]), 0)

    def test_failure_returns_error(self) -> None:
        result = parse_timer_text("타이머 알아서 해줘", now=self.now)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "timer_parse_failed")


if __name__ == "__main__":
    unittest.main()
