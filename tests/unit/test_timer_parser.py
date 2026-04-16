"""T-064: Timer parser 단위 테스트.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.domains.speech.timer_parser import TimerParser


class TestTimerParser(unittest.TestCase):
    def setUp(self):
        self.parser = TimerParser()

    def test_minutes_korean(self):
        ms, label = self.parser.parse("5분 타이머 맞춰줘")
        self.assertEqual(ms, 5 * 60_000)

    def test_seconds_korean(self):
        ms, label = self.parser.parse("30초 후 알려줘")
        self.assertEqual(ms, 30_000)

    def test_minutes_seconds_korean(self):
        ms, label = self.parser.parse("3분 30초 타이머")
        self.assertEqual(ms, 3 * 60_000 + 30_000)

    def test_hours_korean(self):
        ms, label = self.parser.parse("1시간 타이머")
        self.assertEqual(ms, 3_600_000)

    def test_english_minutes(self):
        ms, label = self.parser.parse("set a 10 minute timer")
        self.assertEqual(ms, 10 * 60_000)

    def test_no_time_found(self):
        ms, label = self.parser.parse("타이머 맞춰줘")
        self.assertIsNone(ms)

    def test_format_duration(self):
        self.assertEqual(self.parser.format_duration(30_000), "30초")
        self.assertEqual(self.parser.format_duration(300_000), "5분")
        self.assertEqual(self.parser.format_duration(210_000), "3분 30초")


if __name__ == "__main__":
    unittest.main()
