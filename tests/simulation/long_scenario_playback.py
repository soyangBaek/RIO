"""T-071: Long scenario playback – face + transcript 시나리오 재생.

SYS/VOICE/INT 시나리오를 순서대로 재생하고 상태 검증.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import ActivityState, ContextState, OneshotName
from src.app.core.state.reducers import reduce
from src.app.core.state.store import Store

CONFIG = {
    "presence": {"face_lost_timeout_ms": 800, "away_timeout_ms": 60000, "welcome_min_away_ms": 3000},
    "behavior": {"idle_to_sleepy_timeout_ms": 120000},
}


class TestLongScenarioPlayback(unittest.TestCase):
    """핵심 시나리오 순차 재생."""

    def setUp(self):
        self.store = Store()

    def test_sys01_boot_state(self):
        """SYS-01: 부팅 → Away + Idle."""
        self.assertEqual(self.store.context_state, ContextState.AWAY)
        self.assertEqual(self.store.activity_state, ActivityState.IDLE)

    def test_sys02_face_detection_idle(self):
        """SYS-02: 얼굴 감지 → Away → Idle."""
        ev = Event(
            topic=Topics.VISION_FACE_DETECTED, source="sim",
            payload={"bbox": [0.3, 0.3, 0.2, 0.2], "center": [0.4, 0.4], "confidence": 0.9},
        )
        r = reduce(self.store, ev, CONFIG)
        self.assertEqual(self.store.context_state, ContextState.IDLE)

    def test_voice_without_face_startled(self):
        """SYS-05: 얼굴 없이 음성 → startled + Listening."""
        ev = Event(topic=Topics.VOICE_ACTIVITY_STARTED, source="sim")
        r = reduce(self.store, ev, CONFIG)
        # Away → Idle (user evidence)
        self.assertEqual(self.store.context_state, ContextState.IDLE)
        self.assertEqual(self.store.activity_state, ActivityState.LISTENING)
        self.assertEqual(r.oneshot_triggered, OneshotName.STARTLED)

    def test_full_photo_scenario(self):
        """VOICE-03 full: face → voice → photo intent → success → Idle."""
        # face
        reduce(self.store, Event(
            topic=Topics.VISION_FACE_DETECTED, source="sim",
            payload={"bbox": [0.3, 0.3, 0.2, 0.2], "center": [0.4, 0.4], "confidence": 0.9},
        ), CONFIG)

        # make engaged
        self.store.face_present = True
        self.store.last_interaction_at = time.time()

        # voice started
        reduce(self.store, Event(topic=Topics.VOICE_ACTIVITY_STARTED, source="sim"), CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.LISTENING)

        # intent
        reduce(self.store, Event(
            topic=Topics.VOICE_INTENT_DETECTED, source="sim",
            payload={"intent": "camera.capture", "text": "사진"},
        ), CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.EXECUTING)

        # success
        r = reduce(self.store, Event(
            topic=Topics.TASK_SUCCEEDED, source="sim",
            payload={"task_id": "t1", "kind": "photo"},
        ), CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.IDLE)
        self.assertEqual(r.oneshot_triggered, OneshotName.HAPPY)

    def test_timer_alerting_flow(self):
        """INT-10: 타이머 만료 → Alerting → ACK → Idle."""
        # timer expired
        r = reduce(self.store, Event(
            topic=Topics.TIMER_EXPIRED, source="sim",
            payload={"timer_id": "t1", "label": "라면"},
        ), CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.ALERTING)

        # acknowledge
        r2 = reduce(self.store, Event(
            topic=Topics.TOUCH_TAP_DETECTED, source="sim",
            payload={"x": 0.5, "y": 0.5},
        ), CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.IDLE)

    def test_petting_happy(self):
        """INT-07: 쓰다듬기 → happy oneshot."""
        self.store.context_state = ContextState.ENGAGED
        r = reduce(self.store, Event(
            topic=Topics.TOUCH_STROKE_DETECTED, source="sim",
            payload={"path": [{"x": 0.3, "y": 0.3}, {"x": 0.5, "y": 0.3}], "duration": 0.5},
        ), CONFIG)
        self.assertEqual(r.oneshot_triggered, OneshotName.HAPPY)


if __name__ == "__main__":
    unittest.main()
