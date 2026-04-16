"""T-070: Transcript injection – 마이크 없이 음성 이벤트 주입.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics


class TranscriptInjection:
    """텍스트 기반 음성 이벤트 주입."""

    def __init__(self, bus: QueueBus) -> None:
        self._bus = bus

    def inject_voice_intent(self, intent: str, text: str = "", confidence: float = 0.9) -> None:
        """voice.activity.started → voice.intent.detected 시퀀스 주입."""
        now = time.time()

        self._bus.publish(Event(
            topic=Topics.VOICE_ACTIVITY_STARTED,
            source="simulation",
            timestamp=now,
        ))

        self._bus.publish(Event(
            topic=Topics.VOICE_INTENT_DETECTED,
            source="simulation",
            payload={"intent": intent, "text": text or intent, "confidence": confidence},
            timestamp=now + 0.5,
        ))

    def inject_unknown_intent(self, text: str = "알 수 없는 말") -> None:
        """unknown intent 주입."""
        now = time.time()

        self._bus.publish(Event(
            topic=Topics.VOICE_ACTIVITY_STARTED,
            source="simulation",
            timestamp=now,
        ))

        self._bus.publish(Event(
            topic=Topics.VOICE_INTENT_UNKNOWN,
            source="simulation",
            payload={"text": text, "confidence": 0.3},
            timestamp=now + 0.5,
        ))

    def inject_voice_only(self) -> None:
        """음성 시작/종료만 (intent 없음)."""
        now = time.time()
        self._bus.publish(Event(
            topic=Topics.VOICE_ACTIVITY_STARTED,
            source="simulation",
            timestamp=now,
        ))
        self._bus.publish(Event(
            topic=Topics.VOICE_ACTIVITY_ENDED,
            source="simulation",
            timestamp=now + 1.0,
        ))


class TestTranscriptInjection(unittest.TestCase):
    def test_inject_intent(self):
        bus = QueueBus()
        injector = TranscriptInjection(bus)
        injector.inject_voice_intent("camera.capture", "사진 찍어줘")
        events = bus.drain()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].topic, Topics.VOICE_ACTIVITY_STARTED)
        self.assertEqual(events[1].topic, Topics.VOICE_INTENT_DETECTED)
        self.assertEqual(events[1].payload["intent"], "camera.capture")

    def test_inject_unknown(self):
        bus = QueueBus()
        injector = TranscriptInjection(bus)
        injector.inject_unknown_intent()
        events = bus.drain()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].topic, Topics.VOICE_INTENT_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
