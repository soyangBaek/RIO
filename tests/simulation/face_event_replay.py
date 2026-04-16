"""T-069: Face event replay – 카메라 없이 face event 재생.

시뮬레이션 기반 테스트.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics


class FaceEventReplay:
    """face 이벤트 시퀀스를 큐에 재생."""

    def __init__(self, bus: QueueBus) -> None:
        self._bus = bus

    def replay_face_appear_disappear(self, duration: float = 2.0) -> None:
        """얼굴 등장 → 이동 → 사라짐 시퀀스."""
        now = time.time()

        # face detected
        self._bus.publish(Event(
            topic=Topics.VISION_FACE_DETECTED,
            source="simulation",
            payload={"bbox": [0.3, 0.3, 0.2, 0.2], "center": [0.4, 0.4], "confidence": 0.9},
            timestamp=now,
        ))

        # face moved (여러 프레임)
        for i in range(5):
            self._bus.publish(Event(
                topic=Topics.VISION_FACE_MOVED,
                source="simulation",
                payload={"center": [0.4 + i * 0.02, 0.4], "delta": [0.02, 0.0]},
                timestamp=now + (i + 1) * 0.1,
            ))

        # face lost
        self._bus.publish(Event(
            topic=Topics.VISION_FACE_LOST,
            source="simulation",
            payload={"last_seen_at": now + 0.6},
            timestamp=now + duration,
        ))

    def replay_reappearance(self, away_duration: float = 5.0) -> None:
        """장시간 부재 후 재등장."""
        now = time.time()

        self._bus.publish(Event(
            topic=Topics.VISION_FACE_LOST,
            source="simulation",
            payload={"last_seen_at": now - away_duration},
            timestamp=now - away_duration,
        ))

        self._bus.publish(Event(
            topic=Topics.VISION_FACE_DETECTED,
            source="simulation",
            payload={"bbox": [0.3, 0.3, 0.2, 0.2], "center": [0.4, 0.4], "confidence": 0.85},
            timestamp=now,
        ))


class TestFaceEventReplay(unittest.TestCase):
    def test_replay_publishes_events(self):
        bus = QueueBus()
        replay = FaceEventReplay(bus)
        replay.replay_face_appear_disappear()
        events = bus.drain(max_events=20)
        topics = [e.topic for e in events]
        self.assertIn(Topics.VISION_FACE_DETECTED, topics)
        self.assertIn(Topics.VISION_FACE_MOVED, topics)
        self.assertIn(Topics.VISION_FACE_LOST, topics)

    def test_replay_reappearance(self):
        bus = QueueBus()
        replay = FaceEventReplay(bus)
        replay.replay_reappearance()
        events = bus.drain()
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
