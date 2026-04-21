from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.terminal_input import TerminalVoiceInput
from src.app.core.events import topics
from src.app.domains.speech.dedupe import IntentDeduper


class TerminalVoiceInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_builds_voice_start_intent_end_sequence_for_known_phrase(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("사진 찍어줘", now=self.now)

        self.assertEqual([event.topic for event in events], [
            topics.VOICE_ACTIVITY_STARTED,
            topics.VOICE_INTENT_DETECTED,
            topics.VOICE_ACTIVITY_ENDED,
        ])
        self.assertEqual(events[1].payload["intent"], "camera.capture")
        self.assertTrue(all(event.trace_id == events[0].trace_id for event in events))

    def test_builds_unknown_sequence_for_unmatched_phrase(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("오늘 저녁 메뉴 뭐야", now=self.now)

        self.assertEqual([event.topic for event in events], [
            topics.VOICE_ACTIVITY_STARTED,
            topics.VOICE_INTENT_UNKNOWN,
            topics.VOICE_ACTIVITY_ENDED,
        ])

    def test_empty_text_is_ignored(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("   ", now=self.now)

        self.assertEqual(events, [])

    def test_deduped_phrase_falls_back_to_start_end(self) -> None:
        normalizer = IntentNormalizer(deduper=IntentDeduper(cooldown_ms=1500))
        terminal = TerminalVoiceInput(normalizer)

        first = terminal.build_events("불 켜줘", now=self.now)
        second = terminal.build_events("불 켜줘", now=self.now)

        self.assertEqual(first[1].topic, topics.VOICE_INTENT_DETECTED)
        self.assertEqual([event.topic for event in second], [
            topics.VOICE_ACTIVITY_STARTED,
            topics.VOICE_ACTIVITY_ENDED,
        ])

    def test_builds_tv_off_sequence_for_common_phrase(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("티비 꺼줘", now=self.now)

        self.assertEqual(events[1].topic, topics.VOICE_INTENT_DETECTED)
        self.assertEqual(events[1].payload["intent"], "smarthome.tv.off")

    def test_builds_music_stop_sequence_for_stop_phrase(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("음악 멈춰줘", now=self.now)

        self.assertEqual(events[1].topic, topics.VOICE_INTENT_DETECTED)
        self.assertEqual(events[1].payload["intent"], "smarthome.music.stop")

    def test_builds_dance_sequence_for_compact_phrase(self) -> None:
        terminal = TerminalVoiceInput(IntentNormalizer())

        events = terminal.build_events("댄스모드", now=self.now)

        self.assertEqual(events[1].topic, topics.VOICE_INTENT_DETECTED)
        self.assertEqual(events[1].payload["intent"], "dance.start")


if __name__ == "__main__":
    unittest.main()
