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

    def test_matches_tv_off_alias(self) -> None:
        parsed = parse_intent("티비 꺼줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.tv.off")

    def test_matches_music_stop_alias(self) -> None:
        parsed = parse_intent("음악 멈춰줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.music.stop")

    def test_matches_robot_cleaner_stop_alias(self) -> None:
        parsed = parse_intent("청소기 멈춰줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.robot_cleaner.stop")

    def test_normalizes_common_tv_misrecognition(self) -> None:
        parsed = parse_intent("팁이 켜줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.tv.on")

    def test_normalizes_common_aircon_misrecognition(self) -> None:
        parsed = parse_intent("에어콘 꺼줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.aircon.off")

    def test_matches_compact_dance_phrase(self) -> None:
        parsed = parse_intent("댄스모드", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "dance.start")

    def test_matches_timer_phrase_dynamically(self) -> None:
        parsed = parse_intent("3분 뒤에 알려줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "timer.create")

    def test_dynamic_heater_temperature_command(self) -> None:
        parsed = parse_intent("난방 26도로 맞춰줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.heater.set_temperature")
        self.assertEqual(parsed.payload["temperature_c"], 26)

    def test_static_computer_on_alias(self) -> None:
        parsed = parse_intent("컴퓨터 켜줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.computer.on")

    def test_matches_all_off_alias(self) -> None:
        parsed = parse_intent("다 꺼줘", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.all.off")

    def test_matches_all_off_outing_mode(self) -> None:
        parsed = parse_intent("외출 모드", stt_confidence=0.95)
        self.assertTrue(parsed.is_known)
        self.assertEqual(parsed.intent, "smarthome.all.off")


if __name__ == "__main__":
    unittest.main()
