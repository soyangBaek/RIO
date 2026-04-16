"""T-063: Intent parser 단위 테스트.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.domains.speech.intent_parser import IntentParser


class TestIntentParser(unittest.TestCase):
    def setUp(self):
        self.parser = IntentParser()

    def test_exact_match_korean(self):
        intent, conf = self.parser.parse("사진 찍어줘")
        self.assertEqual(intent, "camera.capture")

    def test_partial_match(self):
        intent, conf = self.parser.parse("에어컨 켜줘")
        self.assertEqual(intent, "smarthome.aircon.on")

    def test_dance_intent(self):
        intent, conf = self.parser.parse("춤 춰")
        self.assertEqual(intent, "dance.start")

    def test_cancel_intent(self):
        intent, conf = self.parser.parse("취소해줘")
        self.assertEqual(intent, "system.cancel")

    def test_unknown_text(self):
        intent, conf = self.parser.parse("아무 의미 없는 말")
        self.assertIsNone(intent)

    def test_empty_text(self):
        intent, conf = self.parser.parse("")
        self.assertIsNone(intent)
        self.assertEqual(conf, 0.0)

    def test_weather(self):
        intent, conf = self.parser.parse("오늘 날씨 어때?")
        self.assertEqual(intent, "weather.current")


if __name__ == "__main__":
    unittest.main()
