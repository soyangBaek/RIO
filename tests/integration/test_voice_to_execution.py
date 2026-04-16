"""T-065: 음성 → 실행 통합 테스트.

voice.activity.started → intent.detected → Executing → task.succeeded → Idle.
scenarios VOICE-01 ~ VOICE-07 대응.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import ActivityState, ContextState, ExecutingKind, Mood
from src.app.core.state.reducers import reduce
from src.app.core.state.store import Store

CONFIG = {
    "presence": {"face_lost_timeout_ms": 800, "away_timeout_ms": 60000, "welcome_min_away_ms": 3000},
    "behavior": {"idle_to_sleepy_timeout_ms": 120000},
}


class TestVoiceToExecution(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.context_state = ContextState.ENGAGED
        self.store.face_present = True
        self.store.last_face_seen_at = time.time()
        self.store.last_interaction_at = time.time()

    def test_photo_flow(self):
        """VOICE-03: 사진 찍어줘 → Executing(photo) → 완료 → Idle."""
        # voice started
        ev1 = Event(topic=Topics.VOICE_ACTIVITY_STARTED, source="audio_worker")
        r1 = reduce(self.store, ev1, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.LISTENING)

        # intent detected
        ev2 = Event(
            topic=Topics.VOICE_INTENT_DETECTED, source="audio_worker",
            payload={"intent": "camera.capture", "text": "사진 찍어", "confidence": 0.9},
        )
        r2 = reduce(self.store, ev2, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.EXECUTING)
        self.assertEqual(self.store.active_executing_kind, ExecutingKind.PHOTO)

        # task succeeded
        ev3 = Event(
            topic=Topics.TASK_SUCCEEDED, source="main/executor",
            payload={"task_id": "t1", "kind": "photo"},
        )
        r3 = reduce(self.store, ev3, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.IDLE)

    def test_smarthome_flow(self):
        """VOICE-05: 스마트홈 명령 → Executing(smarthome) → 성공 → happy."""
        # skip to intent
        self.store.activity_state = ActivityState.LISTENING
        ev = Event(
            topic=Topics.VOICE_INTENT_DETECTED, source="audio_worker",
            payload={"intent": "smarthome.aircon.on", "text": "에어컨 켜"},
        )
        r = reduce(self.store, ev, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.EXECUTING)
        self.assertEqual(self.store.active_executing_kind, ExecutingKind.SMARTHOME)

    def test_weather_flow(self):
        """VOICE-04: 날씨 조회 flow."""
        self.store.activity_state = ActivityState.LISTENING
        ev = Event(
            topic=Topics.VOICE_INTENT_DETECTED, source="audio_worker",
            payload={"intent": "weather.current", "text": "날씨"},
        )
        r = reduce(self.store, ev, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.EXECUTING)
        self.assertEqual(self.store.active_executing_kind, ExecutingKind.WEATHER)

    def test_unknown_intent_confused(self):
        """VOICE-08: unknown intent → confused oneshot."""
        self.store.activity_state = ActivityState.LISTENING
        ev = Event(
            topic=Topics.VOICE_INTENT_UNKNOWN, source="audio_worker",
            payload={"text": "알 수 없는 말", "confidence": 0.3},
        )
        r = reduce(self.store, ev, CONFIG)
        self.assertEqual(self.store.activity_state, ActivityState.IDLE)
        # confused oneshot
        from src.app.core.state.models import OneshotName
        self.assertIsNotNone(r.oneshot_triggered)
        self.assertEqual(r.oneshot_triggered, OneshotName.CONFUSED)


if __name__ == "__main__":
    unittest.main()
