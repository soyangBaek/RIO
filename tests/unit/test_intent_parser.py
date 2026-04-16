from __future__ import annotations

import unittest

from src.app.domains.speech.intent_parser import parse_intent


class IntentParserTest(unittest.TestCase):
    def test_matches_korean_alias(self) -> None:
        parsed = parse_intent("사진 찍어줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "camera.capture")

    def test_matches_english_alias(self) -> None:
        parsed = parse_intent("turn on the light", stt_confidence=0.9)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.light.on")

    def test_matches_aircon_off_alias(self) -> None:
        parsed = parse_intent("에어컨 꺼줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.aircon.off")

    def test_matches_weather_lookup_alias(self) -> None:
        parsed = parse_intent("날씨 조회", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "weather.current")

    def test_matches_light_on_noun_phrase_alias(self) -> None:
        parsed = parse_intent("조명 켜기", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.light.on")

    def test_low_stt_confidence_becomes_unknown(self) -> None:
        parsed = parse_intent("날씨 알려줘", stt_confidence=0.3)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "low_stt_confidence")

    def test_unknown_phrase(self) -> None:
        parsed = parse_intent("오늘 저녁 메뉴 뭐야", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "unknown_intent")

    def test_dynamic_aircon_temperature_command(self) -> None:
        parsed = parse_intent("온도 28도로 맞춰줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.aircon.set_temperature")
        self.assertEqual(parsed.payload["temperature_c"], 28)

    def test_out_of_range_temperature_becomes_unknown(self) -> None:
        parsed = parse_intent("온도 45도로 맞춰줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "temperature_out_of_range")


if __name__ == "__main__":
    unittest.main()
