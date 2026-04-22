from __future__ import annotations

import unittest

from src.app.domains.speech.intent_parser import parse_intent


class IntentParserTest(unittest.TestCase):
    """단일 공식 발화 정책 검증. 공식 문장은 통과, 변형/영어/약어는 unknown."""

    # ── 공식 발화 (통과해야 함) ───────────────────────────────

    def test_camera_official(self) -> None:
        parsed = parse_intent("사진 찍어줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "camera.capture")

    def test_aircon_on_official(self) -> None:
        parsed = parse_intent("에어컨 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.aircon.on")

    def test_aircon_off_official(self) -> None:
        parsed = parse_intent("에어컨 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.aircon.off")

    def test_heater_on_official(self) -> None:
        parsed = parse_intent("난방 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.heater.on")

    def test_heater_off_official(self) -> None:
        parsed = parse_intent("난방 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.heater.off")

    def test_light_on_official(self) -> None:
        parsed = parse_intent("거실 등 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.light.on")

    def test_light_off_official(self) -> None:
        parsed = parse_intent("거실 등 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.light.off")

    def test_light_on_compact_variant(self) -> None:
        # whisper 가 "거실등" 으로 붙여쓸 때도 인식
        parsed = parse_intent("거실등 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.light.on")

    def test_indirect_light_on_official(self) -> None:
        parsed = parse_intent("간접등 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.indirect_light.on")

    def test_indirect_light_off_official(self) -> None:
        parsed = parse_intent("간접등 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.indirect_light.off")

    def test_tv_off_official(self) -> None:
        parsed = parse_intent("티비 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.tv.off")

    def test_computer_on_official(self) -> None:
        parsed = parse_intent("컴퓨터 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.computer.on")

    def test_music_play_official(self) -> None:
        parsed = parse_intent("음악 틀어줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.music.play")

    def test_music_stop_official(self) -> None:
        parsed = parse_intent("음악 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.music.stop")

    def test_cleaner_start_official(self) -> None:
        parsed = parse_intent("청소기 돌려줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.robot_cleaner.start")

    def test_cleaner_stop_official(self) -> None:
        parsed = parse_intent("청소기 정지", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.robot_cleaner.stop")

    def test_air_purifier_on_official(self) -> None:
        parsed = parse_intent("공기청정기 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.air_purifier.on")

    def test_all_off_official(self) -> None:
        parsed = parse_intent("다 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.all.off")

    def test_weather_official(self) -> None:
        parsed = parse_intent("날씨 알려줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "weather.current")

    def test_dance_official(self) -> None:
        parsed = parse_intent("춤춰줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "dance.start")

    def test_game_mode_official(self) -> None:
        parsed = parse_intent("게임 모드", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "ui.game_mode.enter")

    def test_timer_official(self) -> None:
        parsed = parse_intent("3분 뒤에 알려줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "timer.create")

    def test_system_cancel_official(self) -> None:
        parsed = parse_intent("멈춰줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "system.cancel")

    def test_system_cancel_not_triggered_by_combined_phrase(self) -> None:
        # "음악 멈춰줘" 처럼 다른 키워드와 결합된 경우 cancel 로 잡히면 안 된다.
        parsed = parse_intent("음악 멈춰줘", stt_confidence=0.95)
        self.assertNotEqual(parsed.intent, "system.cancel")

    def test_system_ack_official(self) -> None:
        parsed = parse_intent("확인", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "system.ack")

    # ── STT 오인식 보정 (알려진 변형만 허용) ──────────────────

    def test_indirect_light_stt_misrecognition_간접든(self) -> None:
        # whisper 가 "간접등" 을 "간접든" 으로 자주 낸다
        parsed = parse_intent("간접든 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.indirect_light.on")

    def test_tv_off_stt_misrecognition_고추(self) -> None:
        parsed = parse_intent("티비 고추", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.tv.off")

    def test_tv_off_stt_misrecognition_고중(self) -> None:
        parsed = parse_intent("티비 고중", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.tv.off")

    def test_music_stop_stt_misrecognition_고쳐(self) -> None:
        parsed = parse_intent("음악 고쳐", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.music.stop")

    def test_cleaner_start_stt_misrecognition_들려줘(self) -> None:
        parsed = parse_intent("청소기 들려줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.robot_cleaner.start")

    def test_heater_stt_misrecognition_단방(self) -> None:
        parsed = parse_intent("단방 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.heater.on")

    # ── 지원 중단된 변형 (unknown 이어야 함) ─────────────────

    def test_english_command_rejected(self) -> None:
        parsed = parse_intent("turn on the light", stt_confidence=0.9)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "unknown_intent")

    def test_outing_mode_rejected(self) -> None:
        parsed = parse_intent("외출 모드", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_pc_alias_rejected(self) -> None:
        parsed = parse_intent("pc 켜줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_aircon_variant_rejected(self) -> None:
        # "에어컨 틀어줘" 는 공식 발화 아님
        parsed = parse_intent("에어컨 틀어줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_heater_alias_rejected(self) -> None:
        parsed = parse_intent("히터 켜줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_mood_light_rejected(self) -> None:
        # "무드등" 은 공식이 아님 (공식은 "간접등")
        parsed = parse_intent("무드등 켜줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_cancel_variant_그만_rejected(self) -> None:
        parsed = parse_intent("그만", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    def test_bare_light_keyword_rejected(self) -> None:
        # 공식은 "거실 등 켜줘" — "불 켜줘" 단독은 더 이상 인식 안 함
        parsed = parse_intent("불 켜줘", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)

    # ── 기타 ─────────────────────────────────────────────────

    def test_low_stt_confidence_becomes_unknown(self) -> None:
        parsed = parse_intent("날씨 알려줘", stt_confidence=0.3)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "low_stt_confidence")

    def test_unknown_phrase(self) -> None:
        parsed = parse_intent("오늘 저녁 메뉴 뭐야", stt_confidence=0.95)
        self.assertFalse(parsed.is_known)
        self.assertEqual(parsed.reason, "unknown_intent")

    def test_normalizes_common_tv_misrecognition(self) -> None:
        parsed = parse_intent("팁이 켜줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.tv.on")

    def test_normalizes_common_aircon_misrecognition(self) -> None:
        parsed = parse_intent("에어콘 꺼줘", stt_confidence=0.95)
        self.assertEqual(parsed.intent, "smarthome.aircon.off")


if __name__ == "__main__":
    unittest.main()
